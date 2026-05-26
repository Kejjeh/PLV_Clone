"""
FA Monitor — weekly scan across 6 signals to surface high-value pickups.

Signals:
  A - SP First-Start Alert (strong early fp_proxy, pre-claim window)
  B - RP Closer/Setup Monitor (rprs2 top-40 sitting on wire)
  C - Hitter xwOBA Monitor (sustained xwOBA >= 0.360, 75+ PA)
  D - Drafted-Then-Dropped Comeback (prior draft history, now ranked FA)
  E - IL Return Timing (elite FA pitcher returning within 14 days)
  F - Role-Change RP (sv_lag1=0 last year, now rprs2 top-50 and FA)

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


def _rank_for(player_last: str, df: pd.DataFrame) -> int:
    nc = _name_col(df)
    rc = _rank_col(df)
    hits = df[df[nc].str.contains(player_last, case=False, na=False)]
    if len(hits):
        return int(hits[rc].iloc[0])
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
        last = raw.split(",")[0] if "," in raw else display.split()[-1]
        rp3_rank = _rank_for(last, rp3)
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
        last = raw.split(",")[0] if "," in raw else display.split()[-1]
        rh3_rank = _rank_for(last, rh3)
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
        # best model rank across all 3 models
        rp3_r = _rank_for(last, rp3)
        rh3_r = _rank_for(last, rh3)
        rprs2_r = _rank_for(last, rprs2)
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
        last = p.name.split()[-1]
        rank = _rank_for(last, rp3)
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
# Output
# ---------------------------------------------------------------------------

def print_results(all_results: list[dict]):
    high = [r for r in all_results if r["priority"] == "HIGH"]
    monitor = [r for r in all_results if r["priority"] == "MONITOR"]

    print("\n" + "=" * 70)
    print("FA MONITOR REPORT")
    print("=" * 70)

    if high:
        print("\n## HIGH PRIORITY — act this week\n")
        for r in high:
            sig_label = {
                "A": "SP first-start",
                "B": "RP closer/setup",
                "C": "Hitter xwOBA",
                "D": "Drafted-then-dropped",
                "E": "IL return",
                "F": "Role-change RP",
            }.get(r["signal"], r["signal"])
            print(f"  [Sig {r['signal']}] {r['player']:<28} {r['note']}")
            if r["signal"] == "A":
                print(f"           → run /sp-breakout-signal to confirm before adding")
            if r["signal"] in ("A", "B", "C"):
                print(f"           → run /fa-pickup-deep-dive for full writeup")
    else:
        print("\n  (no HIGH signals this week)")

    if monitor:
        print("\n## MONITOR — recheck next week\n")
        for r in monitor:
            print(f"  [Sig {r['signal']}] {r['player']:<28} {r['note']}")

    if not high and not monitor:
        print("\n  No signals fired. Wire looks thin or all top FAs are rostered.")

    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Weekly FA monitor — 6 signals")
    parser.add_argument("--signals", default="A,B,C,D,E,F",
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

    print_results(all_results)


if __name__ == "__main__":
    main()
