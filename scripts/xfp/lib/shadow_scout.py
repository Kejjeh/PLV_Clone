"""shadow_scout.py — process-grade lens for SPs without rp3 or archetype rows.

When a SP has insufficient IP/PA for either rp3 (career-anchored projection) or
the archetype panel (20-80 ratings + cell + trajectory), the triangulate engine
returns blank for two of its three lenses. The shadow lens fills the gap using
the pitcher's live 2026 MLB Statcast (release_speed, K%, BB%, whiff%, CSW%)
percentile-ranked against the live SP population (>=200 pitches in 2026).

Usage:
    from scripts.xfp.lib.shadow_scout import shadow_scout
    cards = shadow_scout(['Logan Henderson', 'Roki Sasaki', 'Ben Brown'])

Each card has:
    player, n_pitches, fb_velo (mph + 20-80 grade), k_pct, bb_pct, whiff_pct,
    csw_pct, avg_grade, verdict
where verdict in {NO_MLB_DATA, BELOW_AVG_HARD, BELOW_AVG, AVG_PROCESS,
PLUS_PROCESS}.

Threshold: 200 pitches gates inclusion in the population baseline AND inclusion
in the lens. Below that the verdict is NO_MLB_DATA -> caller should fall back
to MiLB Statcast via the rehab tracker pattern.

Canonical use: triangulating rookies / small-sample SPs (Henderson 354 pitches,
Sasaki 896 pitches, Ben Brown 759 pitches) where rp3/archetype panel are blank.

When the shadow lens disagrees with the archetype panel (Ben Brown 2026-06-04:
archetype CAREER_LOW vs shadow PLUS_PROCESS), TRUST the shadow lens. The
archetype panel is annual-aggregated and trails by ~6 weeks; Statcast is
current.
"""
from __future__ import annotations

import duckdb
import pandas as pd
from pathlib import Path

ROOT = Path('c:/Users/Joshua/plv_clone')
STATCAST_2026 = ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet'
POPULATION_PITCH_FLOOR = 200

_POP_CACHE = None


def _load_population():
    """Returns a DataFrame with per-pitcher aggregate metrics for the population.
    Memoized within a single process."""
    global _POP_CACHE
    if _POP_CACHE is not None:
        return _POP_CACHE
    con = duckdb.connect()
    q = f"""
    WITH base AS (
      SELECT player_name AS pitcher_name, pitcher,
             pitch_type, release_speed, description, events, type, balls, strikes,
             launch_speed, launch_angle,
             CASE WHEN events IS NOT NULL AND events != '' THEN 1 ELSE 0 END is_pa_end
      FROM read_parquet('{STATCAST_2026.as_posix()}')
    )
    SELECT pitcher_name,
           COUNT(*) n_pitches,
           AVG(CASE WHEN pitch_type IN ('FF','SI','FC') THEN release_speed END) fb_velo,
           1.0*SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) / NULLIF(SUM(is_pa_end),0) k_pct,
           1.0*SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) / NULLIF(SUM(is_pa_end),0) bb_pct,
           1.0*SUM(CASE WHEN description='swinging_strike' THEN 1 ELSE 0 END) /
             NULLIF(SUM(CASE WHEN description IN ('swinging_strike','foul','foul_tip','hit_into_play') THEN 1 ELSE 0 END),0) whiff_pct,
           1.0*SUM(CASE WHEN description IN ('swinging_strike','called_strike') THEN 1 ELSE 0 END) / COUNT(*) csw_pct
    FROM base
    GROUP BY pitcher_name
    HAVING COUNT(*) >= {POPULATION_PITCH_FLOOR}
    """
    _POP_CACHE = con.execute(q).df()
    return _POP_CACHE


def _grade(val, series):
    if val is None or pd.isna(val) or len(series.dropna()) == 0:
        return None, None
    pct = (series < val).mean() * 100
    grade_20_80 = round(20 + (pct / 100) * 60)
    return round(pct, 1), grade_20_80


def _name_to_cache(name: str) -> str:
    parts = name.split()
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def shadow_scout(names: list[str]) -> list[dict]:
    """Returns a list of scouting cards for the given pitcher names."""
    pop = _load_population()
    cards = []
    for nm in names:
        cache_name = _name_to_cache(nm)
        row = pop[pop['pitcher_name'] == cache_name]
        if row.empty:
            cards.append({
                'player': nm, 'n_pitches': 0,
                'fb_velo': None, 'k_pct': None, 'bb_pct': None,
                'whiff_pct': None, 'csw_pct': None,
                'grades': {}, 'avg_grade': None, 'verdict': 'NO_MLB_DATA',
            })
            continue
        r = row.iloc[0]
        pct_velo, g_velo = _grade(r['fb_velo'], pop['fb_velo'])
        pct_k, g_k = _grade(r['k_pct'], pop['k_pct'])
        pct_bb, g_bb = _grade(1 - r['bb_pct'], 1 - pop['bb_pct'])
        pct_whiff, g_whiff = _grade(r['whiff_pct'], pop['whiff_pct'])
        pct_csw, g_csw = _grade(r['csw_pct'], pop['csw_pct'])
        grades = {'fb_velo': g_velo, 'k_pct': g_k, 'bb_pct': g_bb,
                  'whiff_pct': g_whiff, 'csw_pct': g_csw}
        gs = [g for g in grades.values() if g is not None]
        avg = round(sum(gs) / len(gs)) if gs else None
        if avg is None: v = 'NO_MLB_DATA'
        elif avg >= 60: v = 'PLUS_PROCESS'
        elif avg >= 50: v = 'AVG_PROCESS'
        elif avg >= 40: v = 'BELOW_AVG'
        else: v = 'BELOW_AVG_HARD'
        cards.append({
            'player': nm,
            'n_pitches': int(r['n_pitches']),
            'fb_velo': round(r['fb_velo'], 1) if pd.notna(r['fb_velo']) else None,
            'k_pct': round(r['k_pct'] * 100, 1) if pd.notna(r['k_pct']) else None,
            'bb_pct': round(r['bb_pct'] * 100, 1) if pd.notna(r['bb_pct']) else None,
            'whiff_pct': round(r['whiff_pct'] * 100, 1) if pd.notna(r['whiff_pct']) else None,
            'csw_pct': round(r['csw_pct'] * 100, 1) if pd.notna(r['csw_pct']) else None,
            'grades': grades, 'avg_grade': avg, 'verdict': v,
        })
    return cards


def format_card(c: dict) -> str:
    if c['verdict'] == 'NO_MLB_DATA':
        return f"{c['player']:22s}  NO MLB 2026 data (<{POPULATION_PITCH_FLOOR} pitches) -- fall back to MiLB"
    g = c['grades']
    return (
        f"{c['player']:22s}  n={c['n_pitches']:>5d}  "
        f"FB {c['fb_velo']:.1f}mph (g{g['fb_velo']})  "
        f"K {c['k_pct']:.1f}% (g{g['k_pct']})  "
        f"BB {c['bb_pct']:.1f}% (g{g['bb_pct']})  "
        f"whiff {c['whiff_pct']:.1f}% (g{g['whiff_pct']})  "
        f"CSW {c['csw_pct']:.1f}% (g{g['csw_pct']})  "
        f"avg={c['avg_grade']}  {c['verdict']}"
    )


if __name__ == '__main__':
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*')
    ap.add_argument('--names-file', type=str)
    args = ap.parse_args()
    names = list(args.names)
    if args.names_file:
        names += [ln.strip() for ln in open(args.names_file) if ln.strip() and not ln.startswith('#')]
    if not names:
        print('Usage: shadow_scout.py "Name 1" "Name 2"  OR  --names-file file.txt', file=sys.stderr)
        sys.exit(2)
    for c in shadow_scout(names):
        print(format_card(c))
