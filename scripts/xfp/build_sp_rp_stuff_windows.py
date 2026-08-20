"""Trailing-pitch-window stuff leaderboard for SP/RP — engine for /sp-rp-stuff-windows.

WHY A PITCH/SWING WINDOW AND NOT A CALENDAR WINDOW
---------------------------------------------------
Same logic as build_xwoba_l225.py, mirrored to the pitcher side. Calendar
windows (L7/L21) don't carry a fixed denominator, so two pitchers' "last 2
weeks" numbers aren't comparable. This engine instead walks back a fixed
number of PITCHES/SWINGS (the empirical stabilization minimum, owned by
``plv_clone.stabilization``) so every row in a column carries the same
exposure, and (for pitch-count-thin arms, e.g. a two-start-a-week SP) crosses
into the prior season to fill out the window — flagged via ``*_prior_in_window``
same as the hitter engine.

Columns produced (SP: L150 velo, L150 whiff%, L175 swstr% | RP: L150 velo,
L150 whiff%, L200 swstr%) are the three metrics validated 2026-07-29
(`pitcher_cutoff_stabilization_2026-07-29.md`) to actually stabilize in-window
for pitchers — see plv_clone.stabilization.SP_MINS / RP_MINS. Do NOT add a
column for chase%, BB%, hard-hit/barrel, or HR-rate against here — those are
in ``NEVER_STABILIZES`` for both sides; a window read on them is not
low-confidence, it's unsupported (CLAUDE.md gotcha #12).

OWNER MODULES (registry rule: call, never re-derive)
  stabilization minimums   plv_clone.stabilization.minimum(<metric>, side)
  name -> join key         plv_clone.utils.name_match.join_key
  live roster / FA truth   app.espn_connector

Outputs
  data/outputs/sp_rp_stuff_windows.csv           (latest — stable path)
  data/outputs/sp_rp_stuff_windows_<date>.csv    (dated snapshot)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from plv_clone import stabilization                      # noqa: E402
from plv_clone.utils.name_match import join_key           # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
OUT = ROOT / "data" / "outputs"
PIT_POS = {"SP", "RP", "P"}

SC_COLS = [
    "pitcher", "game_date", "game_pk", "at_bat_number", "pitch_number",
    "release_speed", "description", "pitch_type",
]

# Fastball family for `fb_velo_window`. `velo_window` is the pitch-weighted
# mean over ALL pitch types -- that is the quantity the stabilization study
# measured (`avg_velo`, r=.90 @ 150 pitches), so it keeps the validated gate.
# But it is MIX-CONTAMINATED as a scouting read: a heavy off-speed mix drags it
# 3-6 mph below the arm's actual fastball, and unevenly, so it MIS-RANKS.
# Measured 2026-08-18 -- Detmers all-pitch 88.7 vs FB 94.0, Imanaga 85.9 vs
# 91.1, Soriano 93.3 vs 96.6, Rasmussen 92.8 vs 93.7. Reading the all-pitch
# column as "velo" made Detmers look like a soft-tosser and hid Soriano's 96.6.
# Both are emitted: all-pitch carries the validated minimum, FB carries the
# scouting meaning that /fa-monitor, /trending and stuff_command actually use.
FB_TYPES = {"FF", "SI", "FC"}
SWING_DESC = {
    "hit_into_play", "foul", "swinging_strike", "swinging_strike_blocked",
    "foul_tip", "missed_bunt", "foul_bunt",
}
WHIFF_DESC = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}


def name_to_mlbam() -> dict[str, int]:
    """join_key -> mlbam, from the mlbam-keyed model tables.

    rp3 (SP model) and rprs2 (RP model) are separate universes (CLAUDE.md:
    "Common mistake: ranking RPs with xfp_rp3. Always use rprs2 for RPs") —
    neither alone covers the full pitcher pool, so both are merged here purely
    as a name->mlbam lookup (no ranking column is read from either).
    """
    out: dict[str, int] = {}
    for fname, namecol in (
        ("xfp_rp3_projections.csv", "player_name"),
        ("xfp_rprs2_projections.csv", "name_api"),
    ):
        path = OUT / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        for nm, mid in zip(df[namecol], df["pitcher"]):
            if pd.notna(mid):
                out.setdefault(join_key(nm), int(mid))
    return out


def load_pitches(years: list[int], keep: set[int]) -> pd.DataFrame:
    """Pitch-level rows for the given pitcher mlbam ids, chronologically ordered."""
    parts = []
    for y in years:
        path = CACHE / f"statcast_{y}.parquet"
        if not path.exists():
            print(f"  ! statcast_{y}.parquet missing — window cannot reach {y}")
            continue
        d = pd.read_parquet(path, columns=SC_COLS)
        d = d[d["pitcher"].isin(keep)].copy()
        d["season"] = y
        parts.append(d)
    if not parts:
        return pd.DataFrame(columns=SC_COLS + ["season"])
    px = pd.concat(parts, ignore_index=True)
    px["game_date"] = pd.to_datetime(px["game_date"])
    px["is_swing"] = px["description"].isin(SWING_DESC)
    px["is_whiff"] = px["description"].isin(WHIFF_DESC)
    return px.sort_values(
        ["pitcher", "game_date", "game_pk", "at_bat_number", "pitch_number"]
    )


def population(scope: str) -> dict[str, dict]:
    """join_key -> {name, pos, tm, own, inj, owner, is_mine, role} over scope."""
    from app.espn_connector import get_all_teams
    import app.espn_connector as ec
    from scripts.xfp.lib.pitcher_role import detect_pitcher_role

    pop: dict[str, dict] = {}
    teams = get_all_teams()
    rostered = {join_key(n) for n in teams["player_name"]}

    if scope in ("roster", "league", "all"):
        for _, r in teams.iterrows():
            if r["position"] not in PIT_POS:
                continue
            k = join_key(r["player_name"])
            mine = "Liger" in str(r["team_name"])
            if scope == "roster" and not mine:
                continue
            role = detect_pitcher_role(r)
            pop[k] = {
                "name": r["player_name"], "pos": r["position"], "role": role,
                "tm": r["pro_team"], "own": np.nan,
                "inj": r.get("injury_status") or "", "owner": r["team_name"],
                "is_mine": mine,
            }

    if scope in ("fa", "league", "all"):
        # gotcha #6: ONE size=2000 pull, then filter — never per-position caps.
        for p in ec._get_league().free_agents(size=2000):
            k = join_key(p.name)
            if k in rostered:          # gotcha #4: live availability, not memory
                continue
            elig = {str(s) for s in (getattr(p, "eligibleSlots", []) or [])}
            if not (p.position in PIT_POS or (elig & PIT_POS)):
                continue
            # CLAUDE.md gotcha #8, adapted for the FA object (no separate MLB
            # Stats API call needed — free_agents() already carries GS/GP in
            # p.stats[0]['breakdown']): SP-only eligibility -> SP; RP-only ->
            # RP; BOTH (a real dual-role arm, e.g. Detmers-style) -> decide on
            # GS/GP >= 0.4, same threshold detect_pitcher_role uses for the
            # roster side. Never trust the raw position tag alone for a
            # dual-eligible arm — it silently mislabels current relievers who
            # still carry SP eligibility as starters (and vice versa).
            has_sp, has_rp = "SP" in elig, "RP" in elig
            if has_sp and not has_rp:
                role = "SP"
            elif has_rp and not has_sp:
                role = "RP"
            else:
                bd = (p.stats or {}).get(0, {}).get("breakdown", {}) if hasattr(p, "stats") else {}
                gp, gs = bd.get("GP", 0) or 0, bd.get("GS", 0) or 0
                role = "SP" if (gp and gs / gp >= 0.4) else "RP"
            pop[k] = {
                "name": p.name, "pos": p.position, "role": role, "tm": p.proTeam,
                "own": float(getattr(p, "percent_owned", 0) or 0),
                "inj": str(getattr(p, "injuryStatus", "") or ""),
                "owner": "FA", "is_mine": False,
            }
    return pop


def build(scope: str, season: int) -> pd.DataFrame:
    v_sp, _ = stabilization.minimum("velo", "SP")
    w_sp, _ = stabilization.minimum("whiff", "SP")
    s_sp, _ = stabilization.minimum("swstr", "SP")
    v_rp, _ = stabilization.minimum("velo", "RP")
    w_rp, _ = stabilization.minimum("whiff", "RP")
    s_rp, _ = stabilization.minimum("swstr", "RP")
    print(f"  SP windows: velo L{v_sp} pitches | whiff L{w_sp} swings | swstr L{s_sp} pitches")
    print(f"  RP windows: velo L{v_rp} pitches | whiff L{w_rp} swings | swstr L{s_rp} pitches")

    pop = population(scope)
    print(f"  population ({scope}): {len(pop)} pitchers")

    ids = name_to_mlbam()
    by_id = {ids[k]: k for k in pop if k in ids}
    print(f"  resolved to mlbam: {len(by_id)}")
    if not by_id:
        return pd.DataFrame()

    px = load_pitches([season - 1, season], set(by_id))
    if px.empty:
        return pd.DataFrame()
    cur = px[px["season"] == season]
    asof = cur["game_date"].max() if len(cur) else px["game_date"].max()
    print(f"  statcast through {asof.date()} | {len(px):,} pitch rows")

    rows = []
    for pid, d in px.groupby("pitcher"):
        k = by_id.get(pid)
        if k is None:
            continue
        role = pop[k]["role"] if pop[k].get("role") in ("SP", "RP") else "SP"
        velo_n = v_sp if role == "SP" else v_rp
        whiff_n = w_sp if role == "SP" else w_rp
        swstr_n = s_sp if role == "SP" else s_rp

        d = d.sort_values(["game_date", "game_pk", "at_bat_number", "pitch_number"])
        n_total = len(d)

        w_velo = d.tail(velo_n)
        velo = w_velo["release_speed"].mean()

        # Fastball-only velo over the SAME window. Its denominator is the FB
        # count inside that window (typically 55-80 of 150), which is NOT a
        # separately validated stabilization minimum -- `fb_velo_window_n` is
        # emitted so a thin-FB row can be discounted rather than trusted blind.
        w_fb = w_velo[w_velo["pitch_type"].isin(FB_TYPES)]
        fb_velo = w_fb["release_speed"].mean() if len(w_fb) else np.nan
        fb_velo_n = len(w_fb)

        # whiff's minimum is in SWINGS (stabilization.SP_MINS/RP_MINS), so the
        # window must walk back until `whiff_n` SWINGS accumulate — NOT the
        # last `whiff_n` pitches, which contain far fewer swings than pitches
        # (swing rate ~45-50%) and would silently under-fill the window.
        all_swings = d[d["is_swing"]]
        swings = all_swings.tail(whiff_n)
        whiff_pct = (swings["is_whiff"].sum() / len(swings) * 100) if len(swings) else np.nan

        w_swstr = d.tail(swstr_n)
        swstr_pct = (w_swstr["is_whiff"].sum() / len(w_swstr) * 100) if len(w_swstr) else np.nan

        window_span = d.tail(max(velo_n, swstr_n, len(w_velo)))
        # widen the span to cover whichever window (pitch- or swing-based)
        # reaches furthest back, so the cross-season flag is honest for all three
        earliest_needed = min(
            w_velo["game_date"].min() if len(w_velo) else pd.Timestamp.max,
            swings["game_date"].min() if len(swings) else pd.Timestamp.max,
            w_swstr["game_date"].min() if len(w_swstr) else pd.Timestamp.max,
        )
        crosses = d[d["game_date"] >= earliest_needed]["season"].nunique() > 1

        rows.append({
            "mlbam": pid,
            "role": role,
            "n_pitches_avail": n_total,
            "velo_window": round(velo, 1) if pd.notna(velo) else np.nan,
            "velo_window_n": velo_n,
            "fb_velo_window": round(fb_velo, 1) if pd.notna(fb_velo) else np.nan,
            "fb_velo_window_n": fb_velo_n,
            "velo_window_full": n_total >= velo_n,
            "whiff_window": round(whiff_pct, 1) if pd.notna(whiff_pct) else np.nan,
            "whiff_window_swings_n": whiff_n,
            "whiff_window_swings_avail": len(all_swings),
            "whiff_window_full": len(all_swings) >= whiff_n,
            "swstr_window": round(swstr_pct, 1) if pd.notna(swstr_pct) else np.nan,
            "swstr_window_n": swstr_n,
            "swstr_window_full": n_total >= swstr_n,
            "window_crosses_prior_season": bool(crosses),
            "days_since_last_pitch": int((asof - d["game_date"].max()).days),
        })

    x = pd.DataFrame(rows)
    x["k"] = x["mlbam"].map(by_id)
    for col in ("name", "pos", "tm", "own", "inj", "owner", "is_mine"):
        x[col] = x["k"].map(lambda z, c=col: pop[z][c])
    x["asof_date"] = asof.date().isoformat()
    x["window_full"] = x["velo_window_full"] & x["whiff_window_full"] & x["swstr_window_full"]
    x = x.sort_values(["role", "velo_window"], ascending=[True, False]).reset_index(drop=True)
    return x


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", choices=["all", "fa", "roster", "league"],
                    default="fa")
    ap.add_argument("--season", type=int, default=date.today().year)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()

    print("=== SP/RP trailing-pitch-window stuff leaderboard ===")
    x = build(a.scope, a.season)
    if x.empty:
        print("  no rows produced")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    x.to_csv(OUT / "sp_rp_stuff_windows.csv", index=False)
    x.to_csv(OUT / f"sp_rp_stuff_windows_{x['asof_date'].iloc[0]}.csv", index=False)
    print(f"  wrote {len(x)} rows -> data/outputs/sp_rp_stuff_windows.csv")

    if a.top <= 0:
        return 0
    cols = ["role", "name", "pos", "tm", "owner", "inj",
            "velo_window", "fb_velo_window", "fb_velo_window_n",
            "whiff_window", "swstr_window",
            "n_pitches_avail", "window_crosses_prior_season"]
    with pd.option_context("display.width", 400, "display.max_rows", 400):
        for role in ("SP", "RP"):
            full = x[(x["role"] == role) & x["window_full"]]
            thin = int((x["role"] == role).sum()) - len(full)
            sub = full.head(a.top)
            print(f"\n--- {role} (top {len(sub)} by L-window velo, full-window only"
                  f" — {thin} thin rows excluded from ranking) ---")
            print(sub[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
