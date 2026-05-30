"""
FA Monitor — weekly scan across 11 signals to surface high-value pickups.

Signals:
  A - SP First-Start Alert (strong early fp_proxy, pre-claim window)
  B - RP Closer/Setup Monitor (rprs2 top-40 sitting on wire)
  C - Hitter xwOBA Monitor (sustained xwOBA >= 0.360, 75+ PA)
  D - Drafted-Then-Dropped Comeback (prior draft history, now ranked FA)
  E - IL Return Timing (elite FA pitcher returning within 14 days)
  F - Role-Change RP (sv_lag1=0 last year, now rprs2 top-50 and FA)

RP archetype-layer signals (added 2026-05-30):
  J - LEVERAGE_RISE_FA    (leverage_tier {LOW,MID} -> {HIGH,ELITE}, gmLI_26 >= 1.2)
  K - NEW_CLOSER_FA       (sv_2026 >= 3, no CLOSER tag in 2025)
  L - FIREMAN_BREAKOUT    (FIREMAN_26 True, FIREMAN_25 False)
  M - VELO_SPIKE_RP       (VELO rating +5 vs 2025 AND swstr_pct +0.5pp)
  N - MULTI_INNING_BULK_VALUE (MIB tag in 2026, rprs2 per-game rate at replacement closer)

Usage:
  python scripts/xfp/run_fa_monitor.py
  python scripts/xfp/run_fa_monitor.py --signals A,B,C
  python scripts/xfp/run_fa_monitor.py --signal-a-only
"""

import sys
import argparse
import unicodedata
import re
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

PARQ = (REPO / "data/research/xfp_cache/statcast_2026.parquet").as_posix()
DRAFT_2024 = REPO / "data/reference/league_history/draft_2024.csv"
DRAFT_2025 = REPO / "data/reference/league_history/draft_2025.csv"
RP3 = REPO / "data/outputs/xfp_rp3_projections.csv"
RH3 = REPO / "data/outputs/xfp_rh3_projections.csv"
RPRS2 = REPO / "data/outputs/xfp_rprs2_projections.csv"
RP_RATINGS = REPO / "data/research/rp_ratings_master.csv"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


def _fuzzy_in(name: str, pool: list[str]) -> str | None:
    """Return best match from pool or None."""
    n = _norm(name)
    for cand in pool:
        if n == _norm(cand):
            return cand
    # last-name partial match (fallback)
    last = n.split()[-1] if n.split() else ""
    if len(last) >= 4:
        for cand in pool:
            if last in _norm(cand):
                return cand
    return None


def _exact_match(name: str, pool: list[str]) -> str | None:
    """Exact normalized match only — no last-name fallback.

    Use this for Signal A/B/F where a false positive (wrong player matched via
    shared last name) is worse than a missed alert. The last-name fallback in
    _fuzzy_in caused Ixan Henderson (ESPN FA) to match Logan Henderson (statcast
    pitcher, my rostered SP) and Mason Miller (rprs2 closer, rostered) to match
    Erik Miller (ESP FA RP with same last name).
    """
    n = _norm(name)
    for cand in pool:
        if n == _norm(cand):
            return cand
    return None


def _rank_col(df: pd.DataFrame) -> str:
    for col in ("rank", "rp3_rank", "rh3_rank", "rprs2_rank"):
        if col in df.columns:
            return col
    return df.columns[0]


def _name_col(df: pd.DataFrame) -> str:
    for col in ("player_name", "name_api", "name"):
        if col in df.columns:
            return col
    return df.columns[0]


def load_espn():
    from app.espn_connector import _get_league

    league = _get_league()
    fas = league.free_agents(size=2000)

    rostered: set[str] = set()
    for team in league.teams:
        for p in team.roster:
            rostered.add(_norm(p.name))

    def is_fa(player_name: str) -> bool:
        return _norm(player_name) not in rostered

    fa_sps = [p for p in fas if getattr(p, "position", "") in ("SP", "P") and is_fa(p.name)]
    fa_rps = [p for p in fas if getattr(p, "position", "") == "RP" and is_fa(p.name)]
    fa_hits = [p for p in fas if getattr(p, "position", "") not in ("SP", "RP", "P") and is_fa(p.name)]

    return league, fas, fa_sps, fa_rps, fa_hits, is_fa


def load_models():
    rp3 = pd.read_csv(RP3)
    rh3 = pd.read_csv(RH3)
    rprs2 = pd.read_csv(RPRS2)
    return rp3, rh3, rprs2


def _rank_for(full_name: str, df: pd.DataFrame) -> int:
    """Return projection rank for a player by full name.

    Tries in order:
    1. Exact normalized match on 'First Last'
    2. Exact normalized match on 'Last, First' (projection CSV format)
    3. Last-name-only fallback — but takes the BEST (lowest) rank among all
       matches to avoid the Signal D explosion where 'Rodriguez' picked up
       ~20 unrelated players and returned the first row's rank arbitrarily.

    A missed rank (999) is better than a false rank from the wrong player.
    """
    nc = _name_col(df)
    rc = _rank_col(df)
    n = _norm(full_name)
    # Try 'First Last' exact
    for _, row in df.iterrows():
        if _norm(str(row[nc])) == n:
            return int(row[rc])
    # Try 'Last, First' exact
    parts = full_name.strip().split()
    if len(parts) >= 2:
        last_first = _norm(f"{parts[-1]}, {' '.join(parts[:-1])}")
        for _, row in df.iterrows():
            if _norm(str(row[nc])) == last_first:
                return int(row[rc])
    # Last-name fallback: take best rank among all surname matches
    last = parts[-1].lower() if parts else ""
    if len(last) >= 4:
        hits = df[df[nc].str.lower().str.split().str[-1] == last]
        if len(hits):
            return int(hits[rc].min())
    return 999


# ---------------------------------------------------------------------------
# Signal A — SP First-Start Alert
# ---------------------------------------------------------------------------

def signal_a(fa_sps, rp3):
    fa_sp_names = [p.name for p in fa_sps]
    if not fa_sp_names:
        return []

    con = duckdb.connect()
    # MC-validated threshold (2026-05-25): fpp >= 0.02 AND whiff >= 26%, 4-8 GS window
    # Precision: ~68% on 2025 holdout, +53pp lift vs blind pool (36.0% baseline)
    early = con.execute(f"""
        WITH per_game AS (
          SELECT pitcher, game_date::DATE AS gd,
            COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
            SUM(CASE WHEN events = 'strikeout' THEN 1 ELSE 0 END) AS k,
            SUM(CASE WHEN events = 'walk' THEN 1 ELSE 0 END) AS bb,
            SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
            SUM(CASE WHEN events = 'home_run' THEN 1 ELSE 0 END) AS hr
          FROM read_parquet('{PARQ}')
          WHERE game_date >= '2026-03-26'
          GROUP BY pitcher, game_date::DATE
          HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
        ),
        season AS (
          SELECT pitcher,
            COUNT(*) AS gs,
            SUM(bf) AS tot_bf, SUM(k) AS tot_k, SUM(bb) AS tot_bb,
            SUM(h) AS tot_h, SUM(hr) AS tot_hr
          FROM per_game
          GROUP BY pitcher
          HAVING COUNT(*) BETWEEN 4 AND 8
        )
        SELECT pitcher, gs,
          ROUND((tot_k-tot_bb-tot_h-tot_hr)*1.0/NULLIF(tot_bf,0), 4) AS fp_proxy_per_bf
        FROM season
    """).df()

    whiff = con.execute(f"""
        SELECT pitcher,
          COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END)*100.0/
            NULLIF(COUNT(CASE WHEN description IN (
              'swinging_strike','swinging_strike_bounded','foul_tip','foul','hit_into_play','foul_bunt','missed_bunt'
            ) THEN 1 END), 0) AS whiff_pct
        FROM read_parquet('{PARQ}')
        WHERE game_date >= '2026-03-26'
        GROUP BY pitcher
    """).df()

    names = con.execute(f"""
        SELECT DISTINCT pitcher, player_name
        FROM read_parquet('{PARQ}')
        WHERE game_date >= '2026-03-26'
    """).df()
    con.close()

    early = early.merge(whiff, on="pitcher", how="left").merge(names, on="pitcher", how="left")

    results = []
    for _, row in early.iterrows():
        raw = row.get("player_name", "") or ""
        display = " ".join(reversed(raw.split(", "))) if ", " in raw else raw
        # Use exact match only — last-name fallback caused Logan Henderson
        # (my rostered SP, statcast pitcher_id 701656) to fire as "Ixan Henderson"
        # (ESPN FA) via shared surname. Exact match prevents cross-person false positives.
        fa_match = _exact_match(display, fa_sp_names)
        if not fa_match:
            continue
        rp3_rank = _rank_for(fa_match, rp3)
        fp = row["fp_proxy_per_bf"]
        whiff_pct = float(row["whiff_pct"]) if row["whiff_pct"] is not None else 0.0
        # MC-validated gate: fpp >= 0.02 AND whiff >= 26%
        if pd.isna(fp) or fp < 0.02 or whiff_pct < 26.0 or rp3_rank > 150:
            continue
        priority = "HIGH"
        results.append({
            "signal": "A",
            "player": fa_match,
            "gs": int(row["gs"]),
            "fp_proxy_per_bf": float(fp),
            "whiff_pct": whiff_pct,
            "rp3_rank": rp3_rank,
            "priority": priority,
            "note": f"fp_proxy/bf={fp:+.4f}, whiff={whiff_pct:.1f}%, {int(row['gs'])} GS, rp3 #{rp3_rank}",
        })

    results.sort(key=lambda x: -x["fp_proxy_per_bf"])
    return results


# ---------------------------------------------------------------------------
# Signal B — RP Closer/Setup Monitor
# ---------------------------------------------------------------------------

def signal_b(fa_rps, rprs2):
    fa_rp_names = [p.name for p in fa_rps]
    nc = _name_col(rprs2)
    rc = _rank_col(rprs2)

    top = rprs2[rprs2[rc] <= 40].copy()
    results = []
    for _, row in top.iterrows():
        name = row.get("name_api", row.get("player_name", "")) or ""
        # Exact match only — last-name fallback matched rostered "Mason Miller" to
        # FA "Erik Miller", rostered "Cade Smith" to FA "Burch Smith", etc.
        # rprs2 name_api should normalize identically to ESPN names.
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        rank = int(row[rc])
        xfp = float(row.get("xfp_ros", 0) or 0)
        priority = "HIGH" if rank <= 20 else "MONITOR"
        results.append({
            "signal": "B",
            "player": fa_match,
            "rprs2_rank": rank,
            "xfp_ros": xfp,
            "role_lag1": row.get("role_lag1", ""),
            "sv_lag1": row.get("sv_lag1", 0),
            "priority": priority,
            "note": f"rprs2 #{rank}, xfp_ros={xfp:.0f}, role_lag1={row.get('role_lag1','?')}",
        })

    results.sort(key=lambda x: x["rprs2_rank"])
    return results


# ---------------------------------------------------------------------------
# Signal C — Hitter xwOBA Monitor
# ---------------------------------------------------------------------------

def signal_c(fa_hits, rh3):
    fa_hit_names = [p.name for p in fa_hits]
    if not fa_hit_names:
        return []

    con = duckdb.connect()
    xwoba_df = con.execute(f"""
        SELECT batter,
          AVG(estimated_woba_using_speedangle) FILTER (
            WHERE events IS NOT NULL AND events != ''
            AND estimated_woba_using_speedangle IS NOT NULL
          ) AS xwoba_season,
          COUNT(*) FILTER (WHERE events IS NOT NULL AND events != '') AS pa_season,
          AVG(estimated_woba_using_speedangle) FILTER (
            WHERE events IS NOT NULL AND events != ''
            AND estimated_woba_using_speedangle IS NOT NULL
            AND game_date >= CURRENT_DATE - INTERVAL '21 days'
          ) AS xwoba_l21d,
          COUNT(*) FILTER (
            WHERE events IS NOT NULL AND events != ''
            AND game_date >= CURRENT_DATE - INTERVAL '21 days'
          ) AS pa_l21d
        FROM read_parquet('{PARQ}')
        WHERE game_date >= '2026-03-26'
        GROUP BY batter
    """).df()

    bnames = con.execute(f"""
        SELECT DISTINCT batter, player_name
        FROM read_parquet('{PARQ}')
        WHERE game_date >= '2026-03-26'
    """).df()
    con.close()

    xwoba_df = xwoba_df.merge(bnames, on="batter", how="left")

    # Deduplicate by player name — same player can appear multiple times when
    # the xwoba_df join creates multiple rows (e.g. different batter rows with
    # the same player via the bnames merge). Keep the row with the most PA
    # (best-populated window) for each player.
    best_by_player: dict[str, dict] = {}

    for _, row in xwoba_df.iterrows():
        if row["pa_season"] < 75:
            continue
        raw = row.get("player_name", "") or ""
        display = " ".join(reversed(raw.split(", "))) if ", " in raw else raw
        fa_match = _fuzzy_in(display, fa_hit_names)
        if not fa_match:
            continue
        rh3_rank = _rank_for(fa_match, rh3)
        if rh3_rank > 100:
            continue
        xw = row["xwoba_season"]
        if pd.isna(xw) or xw < 0.360:
            continue
        l21d = row["xwoba_l21d"]
        pa_l21d = int(row["pa_l21d"])
        priority = "MONITOR"
        if xw >= 0.390 and row["pa_season"] >= 100:
            priority = "HIGH"
        if pa_l21d >= 30 and not pd.isna(l21d) and l21d >= 0.400:
            priority = "HIGH"
        entry = {
            "signal": "C",
            "player": fa_match,
            "rh3_rank": rh3_rank,
            "xwoba_season": round(float(xw), 3),
            "pa_season": int(row["pa_season"]),
            "xwoba_l21d": round(float(l21d), 3) if not pd.isna(l21d) else None,
            "pa_l21d": pa_l21d,
            "priority": priority,
            "note": f"xwOBA={xw:.3f} ({int(row['pa_season'])} PA), L21d={round(float(l21d),3) if not pd.isna(l21d) else 'n/a'}, rh3 #{rh3_rank}",
        }
        # Keep the entry with the most season PA for each player
        prev = best_by_player.get(fa_match)
        if prev is None or entry["pa_season"] > prev["pa_season"]:
            best_by_player[fa_match] = entry

    results = list(best_by_player.values())
    results.sort(key=lambda x: x["rh3_rank"])
    return results


# ---------------------------------------------------------------------------
# Signal D — Drafted-Then-Dropped Comeback
# ---------------------------------------------------------------------------

def signal_d(fas, rp3, rh3, rprs2):
    if not DRAFT_2024.exists() or not DRAFT_2025.exists():
        print("[Signal D] Draft history CSVs not found — skipping.")
        return []

    d24 = pd.read_csv(DRAFT_2024)
    d25 = pd.read_csv(DRAFT_2025)
    all_drafted = set(
        d24["player_name"].str.lower().tolist() +
        d25["player_name"].str.lower().tolist()
    )
    # build last-name lookup for partial matching
    drafted_lasts = {n.split()[-1].lower() for n in all_drafted}

    results = []
    fa_names = [p.name for p in fas]
    for fa_name in fa_names:
        n = _norm(fa_name)
        last = n.split()[-1] if n.split() else ""
        matched = n in all_drafted or (len(last) >= 4 and last in drafted_lasts)
        if not matched:
            continue
        # best model rank across all 3 models — use full name to avoid last-name explosion
        rp3_r = _rank_for(fa_name, rp3)
        rh3_r = _rank_for(fa_name, rh3)
        rprs2_r = _rank_for(fa_name, rprs2)
        best = min(rp3_r, rh3_r, rprs2_r)
        if best > 80:
            continue
        # which draft?
        which = []
        hits24 = d24[d24["player_name"].str.lower().str.contains(last, na=False)]
        if len(hits24):
            row24 = hits24.iloc[0]
            which.append(f"2024 R{int(row24['round'])} {row24['fantasy_team']}")
        hits25 = d25[d25["player_name"].str.lower().str.contains(last, na=False)]
        if len(hits25):
            row25 = hits25.iloc[0]
            which.append(f"2025 R{int(row25['round'])} {row25['fantasy_team']}")
        model_tag = "rp3" if rp3_r == best else ("rprs2" if rprs2_r == best else "rh3")
        results.append({
            "signal": "D",
            "player": fa_name,
            "best_rank": best,
            "model": model_tag,
            "draft_history": "; ".join(which),
            "priority": "HIGH",
            "note": f"{model_tag} #{best}; drafted: {'; '.join(which)}",
        })

    results.sort(key=lambda x: x["best_rank"])
    return results


# ---------------------------------------------------------------------------
# Signal E — IL Return Timing
# ---------------------------------------------------------------------------

def signal_e(fas, rp3):
    results = []
    for p in fas:
        if not getattr(p, "injured", False):
            continue
        days = getattr(p, "days_until_return", 999) or 999
        if days > 14:
            continue
        rank = _rank_for(p.name, rp3)
        if rank > 60:
            continue
        results.append({
            "signal": "E",
            "player": p.name,
            "days_until_return": days,
            "rp3_rank": rank,
            "injury_status": getattr(p, "injury_status", ""),
            "priority": "HIGH" if rank <= 30 else "MONITOR",
            "note": f"rp3 #{rank}, returns in {days}d, {getattr(p, 'injury_status', '')}",
        })
    results.sort(key=lambda x: x["days_until_return"])
    return results


# ---------------------------------------------------------------------------
# Signal F — Role-Change RP
# ---------------------------------------------------------------------------

def signal_f(fa_rps, rprs2):
    fa_rp_names = [p.name for p in fa_rps]
    rc = _rank_col(rprs2)

    results = []
    for _, row in rprs2.iterrows():
        rank = int(row[rc])
        if rank > 50:
            continue
        sv_lag = float(row.get("sv_lag1", 0) or 0)
        role_lag = row.get("role_lag1", "") or ""
        if role_lag == "closer" or sv_lag >= 10:
            continue
        name = row.get("name_api", row.get("player_name", "")) or ""
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        results.append({
            "signal": "F",
            "player": fa_match,
            "rprs2_rank": rank,
            "sv_lag1": sv_lag,
            "role_lag1": role_lag,
            "priority": "HIGH" if rank <= 25 else "MONITOR",
            "note": f"rprs2 #{rank}, was {role_lag or 'non-closer'} (sv_lag1={sv_lag:.0f}), now ranked FA",
        })

    results.sort(key=lambda x: x["rprs2_rank"])
    return results


# ---------------------------------------------------------------------------
# RP archetype-layer signals (J, K, L, M, N) — added 2026-05-30
#
# All five use the same year-over-year join on rp_ratings_master.csv (2025 vs
# 2026 by pitcher ID). The helper below builds the joined frame once.
# ---------------------------------------------------------------------------


def load_rp_archetype_join():
    """Return a DataFrame joining 2025 and 2026 RP ratings on pitcher ID.

    Columns suffixed _25 / _26. Returns empty DataFrame if the master CSV is
    missing — caller should skip signals that depend on it.
    """
    if not RP_RATINGS.exists():
        print(f"[RP signals J-N] {RP_RATINGS} missing — skipping.")
        return pd.DataFrame()
    d = pd.read_csv(RP_RATINGS)
    keep = [
        "pitcher", "player_name", "team_abbr", "leverage_tier", "gmli",
        "CLOSER", "FIREMAN", "MULTI_INNING_BULK", "HIGH_LEVERAGE",
        "VELO", "avg_velo", "swstr_pct", "ip_per_appearance", "ir",
        "sv", "hld", "fp_per_g",
    ]
    keep = [c for c in keep if c in d.columns]
    d25 = d[d["year"] == 2025][keep].copy()
    d26 = d[d["year"] == 2026][keep].copy()
    if d25.empty or d26.empty:
        return pd.DataFrame()
    joined = d26.merge(d25, on="pitcher", suffixes=("_26", "_25"), how="left")
    return joined


_LEVERAGE_LOW = {"LOW_LEVERAGE", "MID_LEVERAGE", "GARBAGE_TIME"}
_LEVERAGE_HIGH = {"HIGH_LEVERAGE", "ELITE_LEVERAGE"}


def signal_j_leverage_rise(fa_rps, rp_join, rprs2):
    """LEVERAGE_RISE_FA — FA RP whose leverage_tier rose LOW/MID -> HIGH/ELITE
    in 2026, and current gmLI >= 1.2.
    """
    if rp_join.empty:
        return []
    fa_rp_names = [p.name for p in fa_rps]
    results = []
    for _, row in rp_join.iterrows():
        name = row.get("player_name_26") or row.get("player_name_25")
        if not name or pd.isna(name):
            continue
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        lt25 = row.get("leverage_tier_25")
        lt26 = row.get("leverage_tier_26")
        gmli26 = row.get("gmli_26")
        if pd.isna(lt25) or pd.isna(lt26) or pd.isna(gmli26):
            continue
        if lt25 not in _LEVERAGE_LOW or lt26 not in _LEVERAGE_HIGH:
            continue
        if float(gmli26) < 1.2:
            continue
        rank = _rank_for(fa_match, rprs2)
        gmli25 = row.get("gmli_25")
        gmli25_str = f"{float(gmli25):.2f}" if not pd.isna(gmli25) else "n/a"
        # HIGH: rose to ELITE + gmli >= 1.6, MED if HIGH tier and gmli 1.2-1.6
        if lt26 == "ELITE_LEVERAGE" and float(gmli26) >= 1.6:
            priority = "HIGH"
        elif float(gmli26) >= 1.4:
            priority = "MED"
        else:
            priority = "LOW"
        results.append({
            "signal": "J",
            "player": fa_match,
            "leverage_25": lt25,
            "leverage_26": lt26,
            "gmli_25": float(gmli25) if not pd.isna(gmli25) else None,
            "gmli_26": float(gmli26),
            "rprs2_rank": rank,
            "priority": priority,
            "note": (
                f"gmLI {gmli25_str} ({lt25}) -> {float(gmli26):.2f} ({lt26}), "
                f"rprs2 #{rank}"
            ),
        })
    # Priority order: HIGH > MED > LOW, then by gmli_26 descending
    pri_rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    results.sort(key=lambda x: (pri_rank.get(x["priority"], 9), -x["gmli_26"]))
    return results


def signal_k_new_closer(fa_rps, rp_join, rprs2):
    """NEW_CLOSER_FA — FA RP with sv_2026 >= 3 AND no CLOSER tag in 2025.
    Proxy for 'just took the job' — they're stockpiling saves but weren't
    rostered as a closer last year.
    """
    if rp_join.empty:
        return []
    fa_rp_names = [p.name for p in fa_rps]
    results = []
    for _, row in rp_join.iterrows():
        name = row.get("player_name_26") or row.get("player_name_25")
        if not name or pd.isna(name):
            continue
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        sv26 = row.get("sv_26", 0) or 0
        closer25 = row.get("CLOSER_25")
        # NaN closer25 = no 2025 data — treat as non-closer (rookie / first-time)
        was_closer_25 = bool(closer25) if not pd.isna(closer25) else False
        if was_closer_25:
            continue
        if float(sv26) < 3:
            continue
        rank = _rank_for(fa_match, rprs2)
        sv25 = row.get("sv_25", 0) or 0
        sv25_v = float(sv25) if not pd.isna(sv25) else 0.0
        if float(sv26) >= 8:
            priority = "HIGH"
        elif float(sv26) >= 5:
            priority = "MED"
        else:
            priority = "LOW"
        results.append({
            "signal": "K",
            "player": fa_match,
            "sv_2025": sv25_v,
            "sv_2026": float(sv26),
            "rprs2_rank": rank,
            "priority": priority,
            "note": (
                f"SV {sv25_v:.0f}->{float(sv26):.0f}, was non-closer in 2025, "
                f"rprs2 #{rank}"
            ),
        })
    pri_rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    results.sort(key=lambda x: (pri_rank.get(x["priority"], 9), -x["sv_2026"]))
    return results


def signal_l_fireman_breakout(fa_rps, rp_join, rprs2):
    """FIREMAN_BREAKOUT — FA RP newly tagged FIREMAN in 2026 (was not in 2025).
    FIREMAN definition (from rp_archetype build): IS% >= 80, IR >= 20.
    """
    if rp_join.empty:
        return []
    fa_rp_names = [p.name for p in fa_rps]
    results = []
    for _, row in rp_join.iterrows():
        f26 = row.get("FIREMAN_26")
        f25 = row.get("FIREMAN_25")
        if not (bool(f26) and not bool(f25)):
            continue
        name = row.get("player_name_26")
        if not name or pd.isna(name):
            continue
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        rank = _rank_for(fa_match, rprs2)
        ir26 = row.get("ir_26") or 0
        gmli26 = row.get("gmli_26")
        gmli_v = float(gmli26) if not pd.isna(gmli26) else 0.0
        priority = "HIGH" if (rank <= 60 and gmli_v >= 1.3) else "MED"
        results.append({
            "signal": "L",
            "player": fa_match,
            "ir_2026": float(ir26),
            "gmli_2026": gmli_v,
            "rprs2_rank": rank,
            "priority": priority,
            "note": (
                f"FIREMAN tag NEW for 2026, IR={float(ir26):.0f}, "
                f"gmLI={gmli_v:.2f}, rprs2 #{rank}"
            ),
        })
    pri_rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    results.sort(key=lambda x: (pri_rank.get(x["priority"], 9), x["rprs2_rank"]))
    return results


def signal_m_velo_spike(fa_rps, rp_join, rprs2):
    """VELO_SPIKE_RP — FA RP whose VELO rating (20-80 scale) is +5 above 2025
    AND swstr_pct is up by >= 0.5pp. Real stuff jump.
    """
    if rp_join.empty:
        return []
    fa_rp_names = [p.name for p in fa_rps]
    results = []
    for _, row in rp_join.iterrows():
        v25 = row.get("VELO_25")
        v26 = row.get("VELO_26")
        s25 = row.get("swstr_pct_25")
        s26 = row.get("swstr_pct_26")
        if any(pd.isna(x) for x in (v25, v26, s25, s26)):
            continue
        velo_delta = float(v26) - float(v25)
        swstr_delta = float(s26) - float(s25)
        if velo_delta < 5 or swstr_delta < 0.5:
            continue
        name = row.get("player_name_26")
        if not name or pd.isna(name):
            continue
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        rank = _rank_for(fa_match, rprs2)
        av25 = row.get("avg_velo_25")
        av26 = row.get("avg_velo_26")
        mph_delta = (float(av26) - float(av25)) if not (pd.isna(av25) or pd.isna(av26)) else 0.0
        # HIGH: rating delta >= 8 AND swstr delta >= 1.5
        if velo_delta >= 8 and swstr_delta >= 1.5:
            priority = "HIGH"
        elif velo_delta >= 5 and swstr_delta >= 1.0:
            priority = "MED"
        else:
            priority = "LOW"
        results.append({
            "signal": "M",
            "player": fa_match,
            "velo_rating_25": float(v25),
            "velo_rating_26": float(v26),
            "velo_rating_delta": velo_delta,
            "swstr_25": float(s25),
            "swstr_26": float(s26),
            "swstr_delta": swstr_delta,
            "avg_velo_delta_mph": mph_delta,
            "rprs2_rank": rank,
            "priority": priority,
            "note": (
                f"VELO rating {float(v25):.0f}->{float(v26):.0f} (+{velo_delta:.0f}), "
                f"swstr% {float(s25):.1f}->{float(s26):.1f} (+{swstr_delta:.1f}pp), "
                f"avg_velo +{mph_delta:.1f} mph, rprs2 #{rank}"
            ),
        })
    pri_rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    results.sort(key=lambda x: (pri_rank.get(x["priority"], 9), -x["velo_rating_delta"]))
    return results


def signal_n_mib_value(fa_rps, rp_join, rprs2):
    """MULTI_INNING_BULK_VALUE — FA RP with MULTI_INNING_BULK_26 True AND
    rprs2 per-game rate at or above replacement-level closer (proxy: xfp_ros
    per remaining game in top-60 closer pool).

    Simpler implementation: require IP/G >= 1.3 (the MIB threshold itself,
    already encoded in MULTI_INNING_BULK_26 flag) AND rprs2 rank <= 80.
    These guys throw 2-IP holds + occasional saves and outproduce most
    pure-setup men over a week.
    """
    if rp_join.empty:
        return []
    fa_rp_names = [p.name for p in fa_rps]
    results = []
    for _, row in rp_join.iterrows():
        mib26 = row.get("MULTI_INNING_BULK_26")
        if not bool(mib26):
            continue
        name = row.get("player_name_26")
        if not name or pd.isna(name):
            continue
        fa_match = _exact_match(name, fa_rp_names)
        if not fa_match:
            continue
        rank = _rank_for(fa_match, rprs2)
        if rank > 80:
            continue
        ip_per = row.get("ip_per_appearance_26") or 0
        gmli = row.get("gmli_26")
        gmli_v = float(gmli) if not pd.isna(gmli) else 0.0
        mib25 = row.get("MULTI_INNING_BULK_25")
        new_mib = bool(mib26) and not bool(mib25)
        # HIGH: top 50 + gmLI >= 1.2 (real leverage) OR new MIB role
        if (rank <= 50 and gmli_v >= 1.2) or new_mib:
            priority = "HIGH"
        elif rank <= 60:
            priority = "MED"
        else:
            priority = "LOW"
        note_bits = [f"IP/G={float(ip_per):.2f}", f"gmLI={gmli_v:.2f}", f"rprs2 #{rank}"]
        if new_mib:
            note_bits.append("NEW MIB role")
        results.append({
            "signal": "N",
            "player": fa_match,
            "ip_per_appearance": float(ip_per),
            "gmli_2026": gmli_v,
            "new_mib": new_mib,
            "rprs2_rank": rank,
            "priority": priority,
            "note": ", ".join(note_bits),
        })
    pri_rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    results.sort(key=lambda x: (pri_rank.get(x["priority"], 9), x["rprs2_rank"]))
    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_SIG_LABELS = {
    "A": "SP first-start",
    "B": "RP closer/setup",
    "C": "Hitter xwOBA",
    "D": "Drafted-then-dropped",
    "E": "IL return",
    "F": "Role-change RP",
    "J": "LEVERAGE_RISE_FA",
    "K": "NEW_CLOSER_FA",
    "L": "FIREMAN_BREAKOUT",
    "M": "VELO_SPIKE_RP",
    "N": "MULTI_INNING_BULK_VALUE",
}

_RP_NEW_SIGS = {"J", "K", "L", "M", "N"}


def _bucket(priority: str) -> str:
    """Map priority labels to 3-tier bucket. MONITOR and MED both -> MED tier."""
    p = (priority or "").upper()
    if p == "HIGH":
        return "HIGH"
    if p in ("LOW",):
        return "LOW"
    return "MED"


def print_results(all_results: list[dict]):
    high = [r for r in all_results if _bucket(r["priority"]) == "HIGH"]
    med = [r for r in all_results if _bucket(r["priority"]) == "MED"]
    low = [r for r in all_results if _bucket(r["priority"]) == "LOW"]

    rp_high = [r for r in high if r["signal"] in _RP_NEW_SIGS]
    rp_med = [r for r in med if r["signal"] in _RP_NEW_SIGS]
    rp_low = [r for r in low if r["signal"] in _RP_NEW_SIGS]
    other_high = [r for r in high if r["signal"] not in _RP_NEW_SIGS]
    other_med = [r for r in med if r["signal"] not in _RP_NEW_SIGS]

    print("\n" + "=" * 70)
    print("FA MONITOR REPORT")
    print("=" * 70)

    if other_high:
        print("\n## HIGH PRIORITY — act this week\n")
        for r in other_high:
            print(f"  [Sig {r['signal']}] {r['player']:<28} {r['note']}")
            if r["signal"] == "A":
                print(f"           → run /sp-breakout-signal to confirm before adding")
            if r["signal"] in ("A", "B", "C"):
                print(f"           → run /fa-pickup-deep-dive for full writeup")
    else:
        print("\n  (no HIGH signals from A-F this week)")

    if other_med:
        print("\n## MONITOR — recheck next week\n")
        for r in other_med:
            print(f"  [Sig {r['signal']}] {r['player']:<28} {r['note']}")

    # RP archetype-layer block (signals J-N) — distinct visual section
    if rp_high or rp_med or rp_low:
        print("\n" + "-" * 70)
        print("## RP ARCHETYPE SIGNALS (J-N)")
        print("-" * 70)

        if rp_high:
            print("\n### HIGH — act this week\n")
            for r in rp_high:
                label = _SIG_LABELS.get(r["signal"], r["signal"])
                print(f"  [Sig {r['signal']}] {label} — {r['player']}")
                print(f"     {r['note']}")
                print(f"     Recommendation: deep-dive via /fa-pickup-deep-dive")
        if rp_med:
            print("\n### MED — needs another week of evidence\n")
            for r in rp_med:
                label = _SIG_LABELS.get(r["signal"], r["signal"])
                print(f"  [Sig {r['signal']}] {label} — {r['player']}")
                print(f"     {r['note']}")
        if rp_low:
            print("\n### LOW — noteworthy but speculative\n")
            for r in rp_low:
                label = _SIG_LABELS.get(r["signal"], r["signal"])
                print(f"  [Sig {r['signal']}] {label} — {r['player']}: {r['note']}")

    if not (high or med or low):
        print("\n  No signals fired. Wire looks thin or all top FAs are rostered.")

    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Weekly FA monitor — 11 signals")
    parser.add_argument("--signals", default="A,B,C,D,E,F,J,K,L,M,N",
                        help="Comma-separated list of signals to run (default: all)")
    args = parser.parse_args()

    active = set(s.strip().upper() for s in args.signals.split(","))

    print("Loading ESPN league data...")
    league, fas, fa_sps, fa_rps, fa_hits, is_fa = load_espn()
    print(f"  FA pool: {len(fas)} total | {len(fa_sps)} SP | {len(fa_rps)} RP | {len(fa_hits)} hitters")

    print("Loading model projections...")
    rp3, rh3, rprs2 = load_models()

    all_results = []

    if "A" in active:
        print("Running Signal A (SP first-start)...")
        all_results += signal_a(fa_sps, rp3)

    if "B" in active:
        print("Running Signal B (RP closer monitor)...")
        all_results += signal_b(fa_rps, rprs2)

    if "C" in active:
        print("Running Signal C (hitter xwOBA)...")
        all_results += signal_c(fa_hits, rh3)

    if "D" in active:
        print("Running Signal D (drafted-then-dropped)...")
        all_results += signal_d(fas, rp3, rh3, rprs2)

    if "E" in active:
        print("Running Signal E (IL return timing)...")
        all_results += signal_e(fas, rp3)

    if "F" in active:
        print("Running Signal F (role-change RP)...")
        all_results += signal_f(fa_rps, rprs2)

    # RP archetype-layer signals (J, K, L, M, N) — share one joined frame
    if active & {"J", "K", "L", "M", "N"}:
        print("Loading RP archetype panel (2025 vs 2026 join)...")
        rp_join = load_rp_archetype_join()
    else:
        rp_join = pd.DataFrame()

    if "J" in active:
        print("Running Signal J (LEVERAGE_RISE_FA)...")
        all_results += signal_j_leverage_rise(fa_rps, rp_join, rprs2)

    if "K" in active:
        print("Running Signal K (NEW_CLOSER_FA)...")
        all_results += signal_k_new_closer(fa_rps, rp_join, rprs2)

    if "L" in active:
        print("Running Signal L (FIREMAN_BREAKOUT)...")
        all_results += signal_l_fireman_breakout(fa_rps, rp_join, rprs2)

    if "M" in active:
        print("Running Signal M (VELO_SPIKE_RP)...")
        all_results += signal_m_velo_spike(fa_rps, rp_join, rprs2)

    if "N" in active:
        print("Running Signal N (MULTI_INNING_BULK_VALUE)...")
        all_results += signal_n_mib_value(fa_rps, rp_join, rprs2)

    print_results(all_results)


if __name__ == "__main__":
    main()
