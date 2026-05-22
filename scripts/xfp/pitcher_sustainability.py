"""Pitcher sustainability decomposition.

For each pitcher, decomposes the 2026 vs prior-year FP/start change into
skill-attributable (sustainable) vs luck-attributable (regression-prone)
components, using cached Statcast metrics from sp_multiyr.csv.

The 9-marker skill checklist (favored direction in parens):
  - avg_velo   (+)   pitchers don't fluke 1.5+ mph year-over-year
  - swstr_pct  (+)   swing-and-miss rate
  - c_plus_swstr (+) CSW% — Pitcher List's signature combined metric
  - o_swing_pct (+)  chase rate — hitters fooled outside zone
  - k_pct      (+)   strikeout rate
  - bb_pct     (-)   walk rate
  - hard_hit_pct (-) % of contact at 95+ mph
  - barrel_pct (-)   % of contact in the "barrel" zone
  - xwoba_contact (-) expected wOBA on contact (separates luck from quality)

Bucket logic:
  LEGIT     — ≥7/9 markers favorable AND fp_per_start change ≥ 2.0
  IMPROVING — 5-6/9 favorable, moderate fp_per_start change
  STABLE    — abs(fp_per_start change) < 2.0 (no real story to tell)
  REGRESS   — 2026 fp_per_start materially worse than prior
  NOISE     — ≤3/9 favorable but fp_per_start higher (likely BABIP fluke)

Usage:
    python scripts/xfp/pitcher_sustainability.py \\
        --players "Kyle Harrison,Framber Valdez,Will Warren"

    python scripts/xfp/pitcher_sustainability.py --scope my-roster
    python scripts/xfp/pitcher_sustainability.py --scope fa-pool --min-2026-fp 10
"""
from __future__ import annotations
import argparse
import sys
import unicodedata
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

# (column, direction, label, materiality threshold for "real" change)
MARKERS = [
    ('avg_velo',       '+', 'Velo (mph)',  0.5),
    ('swstr_pct',      '+', 'SwStr%',      0.010),
    ('c_plus_swstr',   '+', 'CSW%',        0.010),
    ('o_swing_pct',    '+', 'Chase%',      0.020),
    ('k_pct',          '+', 'K%',          0.020),
    ('bb_pct',         '-', 'BB%',         0.015),
    ('hard_hit_pct',   '-', 'HardHit%',    0.030),
    ('barrel_pct',     '-', 'Barrel%',     0.015),
    ('xwoba_contact',  '-', 'xwOBAcon',    0.020),
]


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def load_pitcher_rows(sp: pd.DataFrame, name: str):
    """Return dict {year: row} for the requested pitcher (case-insensitive,
    accent-insensitive match). Empty dict if not found."""
    sp['_nk'] = sp['player_name'].map(_norm)
    nk = _norm(name)
    rows = sp[sp['_nk'] == nk]
    if rows.empty:
        # fuzzy: last-first vs first-last
        parts = name.split()
        if len(parts) == 2:
            alt = f"{parts[1]}, {parts[0]}"
            rows = sp[sp['_nk'] == _norm(alt)]
    if rows.empty:
        return {}
    return {int(r['year']): r for _, r in rows.iterrows()}


def pick_baseline_year(rows: dict, current_year: int = 2026) -> int | None:
    """Most-recent prior year before `current_year`. None if no prior."""
    priors = sorted([y for y in rows if y < current_year], reverse=True)
    return priors[0] if priors else None


def classify(rows: dict) -> dict:
    """Return per-pitcher dict with marker analysis + bucket verdict."""
    if 2026 not in rows:
        return {'bucket': 'NO_2026_DATA', 'verdict': 'no 2026 starts in cache'}
    base_year = pick_baseline_year(rows)
    cur = rows[2026]
    if base_year is None:
        return {
            'bucket': 'NO_BASELINE',
            'verdict': 'only 2026 data — no prior year to compare',
            'current_year': 2026, 'gs_2026': int(cur['gs']),
            'fp_2026': float(cur['fp_per_start_actual']),
            'velo_2026': float(cur['avg_velo']),
            'k_pct_2026': float(cur['k_pct']),
        }
    prior = rows[base_year]

    marker_results = []
    n_favorable = 0
    n_material = 0
    for col, direction, label, thresh in MARKERS:
        try:
            cur_v = float(cur[col])
            prior_v = float(prior[col])
        except (KeyError, ValueError, TypeError):
            continue
        delta = cur_v - prior_v
        favorable = (delta > 0 and direction == '+') or (delta < 0 and direction == '-')
        material = abs(delta) >= thresh
        if favorable:
            n_favorable += 1
        if favorable and material:
            n_material += 1
        marker_results.append({
            'label': label, 'cur': cur_v, 'prior': prior_v, 'delta': delta,
            'favorable': favorable, 'material': material,
        })

    # FP/start change
    fp_delta = float(cur['fp_per_start_actual']) - float(prior['fp_per_start_actual'])

    # Bucket logic
    if fp_delta >= 2.0 and n_material >= 7:
        bucket = 'LEGIT'
    elif fp_delta >= 2.0 and n_material >= 5:
        bucket = 'IMPROVING'
    elif fp_delta >= 2.0 and n_material <= 3:
        bucket = 'NOISE'  # production up but skills don't support
    elif fp_delta <= -2.0 and n_material <= 2:
        bucket = 'REGRESS'  # production down + skills down
    elif fp_delta <= -2.0:
        bucket = 'BAD_LUCK'  # production down but skills holding
    elif abs(fp_delta) < 2.0:
        bucket = 'STABLE'
    else:
        bucket = 'MIXED'

    # Skill-attributable FP estimate (rough): how much of fp_delta is supported
    # by the K%+contact-quality changes?
    k_delta = float(cur.get('k_pct', 0)) - float(prior.get('k_pct', 0))
    xwoba_delta = float(prior.get('xwoba_contact', 0)) - float(cur.get('xwoba_contact', 0))
    # ~22 BF per start typically; K worth +1 FP, xwOBA-contact pts ≈ scaling
    bf_per_start = 22
    skill_fp_k = k_delta * bf_per_start * 1.0     # each extra K = +1 FP
    skill_fp_contact = xwoba_delta * 20            # rough: .010 xwOBA-con ≈ 0.2 FP/start
    skill_attributable = skill_fp_k + skill_fp_contact
    luck_attributable = fp_delta - skill_attributable

    return {
        'bucket': bucket,
        'base_year': base_year,
        'gs_prior': int(prior['gs']), 'gs_2026': int(cur['gs']),
        'fp_prior': float(prior['fp_per_start_actual']),
        'fp_2026': float(cur['fp_per_start_actual']),
        'fp_delta': fp_delta,
        'n_favorable': n_favorable, 'n_material': n_material,
        'skill_attributable': skill_attributable,
        'luck_attributable': luck_attributable,
        'markers': marker_results,
    }


def ros_expectation(c: dict) -> dict:
    """Bayesian ROS expectation — bull/base/bear given bucket + skill support."""
    if c['bucket'] in ('NO_2026_DATA', 'NO_BASELINE'):
        return {}
    fp_cur = c['fp_2026']
    fp_prior = c['fp_prior']

    bucket = c['bucket']
    if bucket == 'LEGIT':
        p = [0.40, 0.45, 0.15]  # bull/base/bear
    elif bucket == 'IMPROVING':
        p = [0.25, 0.50, 0.25]
    elif bucket == 'MIXED':
        p = [0.20, 0.40, 0.40]
    elif bucket == 'NOISE':
        p = [0.10, 0.30, 0.60]
    elif bucket == 'STABLE':
        p = [0.20, 0.60, 0.20]
    elif bucket == 'BAD_LUCK':
        p = [0.40, 0.40, 0.20]
    elif bucket == 'REGRESS':
        p = [0.10, 0.30, 0.60]
    else:
        p = [0.25, 0.50, 0.25]

    bull = fp_cur  # form sustains
    base = 0.5 * fp_cur + 0.5 * fp_prior  # halfway regress
    bear = fp_prior  # full revert
    ev = p[0] * bull + p[1] * base + p[2] * bear
    return {'bull': bull, 'base': base, 'bear': bear,
            'p_bull': p[0], 'p_base': p[1], 'p_bear': p[2], 'ev': ev}


# ─── Roster / FA scope helpers ────────────────────────────────────────
def get_my_sp_names() -> list[str]:
    from app.espn_connector import get_my_roster_with_injuries
    df = get_my_roster_with_injuries()
    sps = df[(df['position'] == 'SP') & (~df['injured'])]
    return sps['player_name'].tolist()


def get_fa_sp_names(min_2026_fp: float, sp_multiyr: pd.DataFrame) -> list[str]:
    """Return FA SP names whose 2026 fp_per_start ≥ min_2026_fp."""
    from app.espn_connector import _get_league
    league = _get_league()
    fas = league.free_agents(size=2000)
    fa_sps = [p.name for p in fas if (p.position or '?') == 'SP']
    # Filter by 2026 fp/start floor via sp_multiyr
    sp = sp_multiyr.copy()
    sp['_nk'] = sp['player_name'].map(_norm)
    cur_yr = sp[sp['year'] == 2026]
    by_nk = {r['_nk']: r for _, r in cur_yr.iterrows()}
    qualified = []
    for n in fa_sps:
        r = by_nk.get(_norm(n))
        if r is not None and float(r['fp_per_start_actual']) >= min_2026_fp:
            qualified.append((n, float(r['fp_per_start_actual'])))
    qualified.sort(key=lambda x: -x[1])
    return [n for n, _ in qualified]


# ─── Output ───────────────────────────────────────────────────────────
BUCKET_EMOJI = {
    'LEGIT': '✓✓ LEGIT', 'IMPROVING': '✓  IMPROV', 'STABLE': '·  STABLE',
    'MIXED': '~  MIXED', 'NOISE': '?  NOISE', 'BAD_LUCK': '!  UNLUCKY',
    'REGRESS': 'x  REGRES', 'NO_2026_DATA': '— no 26', 'NO_BASELINE': '— no prior',
}


def print_per_pitcher(name: str, c: dict, ros: dict):
    print(f'\n--- {name} ---')
    bucket = c.get('bucket', '?')
    print(f"  Bucket: {BUCKET_EMOJI.get(bucket, bucket)}")
    if bucket in ('NO_2026_DATA', 'NO_BASELINE'):
        print(f"  {c.get('verdict','')}")
        if 'fp_2026' in c:
            print(f"  2026 (n={c.get('gs_2026','?')}): "
                  f"FP/start={c['fp_2026']:.1f}  velo={c.get('velo_2026',0):.1f}  "
                  f"K%={c.get('k_pct_2026',0):.3f}")
        return
    print(f"  {c['base_year']} (n={c['gs_prior']}): FP/start={c['fp_prior']:.1f}")
    print(f"  2026 (n={c['gs_2026']}): FP/start={c['fp_2026']:.1f}  "
          f"Δ={c['fp_delta']:+.1f}  ({c['n_material']}/{len(c['markers'])} skills materially favorable)")
    print(f"  {'Metric':<11} {'Prior':>8} {'2026':>8} {'Δ':>8}  {'Sign':<3}")
    for m in c['markers']:
        sign = '✓' if m['favorable'] and m['material'] else ('·' if m['favorable'] else '✗')
        delta_str = f"{m['delta']:+.3f}" if m['label'] != 'Velo (mph)' else f"{m['delta']:+.2f}"
        prior_str = f"{m['prior']:.3f}" if m['label'] != 'Velo (mph)' else f"{m['prior']:.2f}"
        cur_str = f"{m['cur']:.3f}" if m['label'] != 'Velo (mph)' else f"{m['cur']:.2f}"
        print(f"  {m['label']:<11} {prior_str:>8} {cur_str:>8} {delta_str:>8}  {sign}")
    print(f"  FP decomposition: skill≈{c['skill_attributable']:+.1f}  "
          f"luck≈{c['luck_attributable']:+.1f}")
    if ros:
        print(f"  ROS FP/start: bull={ros['bull']:.1f} ({ros['p_bull']*100:.0f}%)  "
              f"base={ros['base']:.1f} ({ros['p_base']*100:.0f}%)  "
              f"bear={ros['bear']:.1f} ({ros['p_bear']*100:.0f}%)  "
              f"→ E[FP/start]={ros['ev']:.2f}")


def print_summary_table(results: list[dict]):
    print(f'\n\n=== SUMMARY (sorted by E[ROS FP/start] desc) ===')
    print(f'{"Pitcher":<24} {"Bucket":<12} {"2026":>6} {"Prior":>6} {"Δ":>6} '
          f'{"Skill":>5} {"Mat":>4} {"E[ROS]":>7}')
    print('-' * 80)
    for r in results:
        cls = r['classification']
        bucket = cls.get('bucket', '?')
        if bucket in ('NO_2026_DATA', 'NO_BASELINE'):
            ev = cls.get('fp_2026', 0)
            print(f"{r['name']:<24} {BUCKET_EMOJI[bucket]:<12} "
                  f"{cls.get('fp_2026', 0):>6.1f}  {'n/a':>5} {'n/a':>5}  "
                  f"{'n/a':>5} {'n/a':>4} {ev:>7.1f}")
            continue
        ros = r.get('ros', {})
        print(f"{r['name']:<24} {BUCKET_EMOJI[bucket]:<12} "
              f"{cls['fp_2026']:>6.1f} {cls['fp_prior']:>6.1f} {cls['fp_delta']:>+6.1f} "
              f"{cls['n_favorable']:>5} {cls['n_material']:>4} "
              f"{ros.get('ev', 0):>7.2f}")


def main():
    parser = argparse.ArgumentParser(description='Pitcher sustainability decomposition')
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--players', help='Comma-separated pitcher names')
    g.add_argument('--scope', choices=['my-roster', 'fa-pool'])
    parser.add_argument('--min-2026-fp', type=float, default=10.0,
                        help='Min 2026 fp/start floor for FA pool scope (default 10)')
    parser.add_argument('--brief', action='store_true',
                        help='Skip per-pitcher detail; summary table only')
    args = parser.parse_args()

    sp = pd.read_csv(CACHE / 'sp_multiyr.csv')

    if args.players:
        names = [n.strip() for n in args.players.split(',')]
    elif args.scope == 'my-roster':
        names = get_my_sp_names()
        print(f'My roster SPs (healthy, n={len(names)}): {names}')
    else:  # fa-pool
        names = get_fa_sp_names(args.min_2026_fp, sp)
        print(f'FA pool SPs with 2026 FP/start >= {args.min_2026_fp} '
              f'(n={len(names)}): {names[:20]}{"..." if len(names)>20 else ""}')

    results = []
    for n in names:
        rows = load_pitcher_rows(sp, n)
        cls = classify(rows) if rows else {'bucket': 'NOT_FOUND',
                                              'verdict': f'no rows in sp_multiyr for "{n}"'}
        ros = ros_expectation(cls)
        results.append({'name': n, 'classification': cls, 'ros': ros})
        if not args.brief:
            print_per_pitcher(n, cls, ros)

    # Sort summary by E[ROS]
    def sort_key(r):
        cls = r['classification']
        ros = r.get('ros', {})
        if ros and 'ev' in ros:
            return -ros['ev']
        return -cls.get('fp_2026', 0)
    results.sort(key=sort_key)
    print_summary_table(results)


if __name__ == '__main__':
    main()
