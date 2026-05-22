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
OUT = ROOT / 'data' / 'outputs'

# Divergence threshold: |my_E[ROS] - rp3.per_start| > this → flag as
# disagreement between sustainability decomp and validated model.
DIVERGENCE_THRESHOLD = 1.5

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


def load_rp3_map() -> dict:
    """Load rp3 projections keyed by normalized name → {per_start, sigma}."""
    try:
        rp3 = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    except Exception:
        return {}
    rp3['_nk'] = rp3['player_name'].map(_norm)
    out = {}
    for _, r in rp3.iterrows():
        out[r['_nk']] = {
            'per_start': float(r['xfp_rp3_per_start']) if pd.notna(r.get('xfp_rp3_per_start')) else None,
            'sigma': float(r['xfp_rp3_sigma']) if pd.notna(r.get('xfp_rp3_sigma')) else None,
            'per_start_sched': float(r['xfp_rp3_per_start_sched']) if pd.notna(r.get('xfp_rp3_per_start_sched')) else None,
        }
    return out


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


MIN_2026_STARTS_FOR_CLASSIFY = 5  # below this, fall back to prior-2-year trajectory


def classify(rows: dict) -> dict:
    """Return per-pitcher dict with marker analysis + bucket verdict."""
    # Special-case: 2026 missing or n_2026 too small → use last 2 prior years
    # as the comparison (skill trajectory) and flag the limitation.
    n_2026 = int(rows[2026]['gs']) if 2026 in rows else 0
    if 2026 not in rows or n_2026 < MIN_2026_STARTS_FOR_CLASSIFY:
        # Fall back to most-recent-pair comparison
        prior_years = sorted([y for y in rows if y < 2026], reverse=True)
        if len(prior_years) < 2:
            if 2026 not in rows:
                return {'bucket': 'NO_2026_DATA',
                        'verdict': 'no 2026 starts in cache (likely post-IL or new callup with n<3)'}
            return {'bucket': 'NO_BASELINE',
                    'verdict': 'only 2026 data — no prior year to compare',
                    'current_year': 2026, 'gs_2026': n_2026,
                    'fp_2026': float(rows[2026]['fp_per_start_actual']),
                    'velo_2026': float(rows[2026]['avg_velo']),
                    'k_pct_2026': float(rows[2026]['k_pct'])}
        # Use latest two prior years as "current vs prior" — describes skill
        # trajectory pre-2026 even if 2026 sample is too small
        cur_year = prior_years[0]
        base_year = prior_years[1]
        cur = rows[cur_year]
        prior = rows[base_year]
        small_2026_note = (f' (2026 sample n={n_2026} too small; '
                           f'using {cur_year} vs {base_year} as proxy)') if 2026 in rows else ''
    else:
        cur = rows[2026]
        base_year = pick_baseline_year(rows)
        if base_year is None:
            return {
                'bucket': 'NO_BASELINE',
                'verdict': 'only 2026 data — no prior year to compare',
                'current_year': 2026, 'gs_2026': n_2026,
                'fp_2026': float(cur['fp_per_start_actual']),
                'velo_2026': float(cur['avg_velo']),
                'k_pct_2026': float(cur['k_pct']),
            }
        prior = rows[base_year]
        small_2026_note = ''
        cur_year = 2026

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

    # Skill-attributable FP estimate. Each major skill change converted to
    # expected FP impact per start (BF=22 typical):
    #   K%   change: +1 FP per extra K
    #   BB%  change: -1 FP per extra BB
    #   Barrel% change: -2.6 FP per extra HR (HR ≈ 13% conv from barrel)
    #   xwOBA-con: ~20 FP per .010 (already scaled to per-start)
    bf_per_start = 22
    k_delta = float(cur.get('k_pct', 0)) - float(prior.get('k_pct', 0))
    bb_delta = float(cur.get('bb_pct', 0)) - float(prior.get('bb_pct', 0))
    barrel_delta = float(cur.get('barrel_pct', 0)) - float(prior.get('barrel_pct', 0))
    xwoba_delta = float(prior.get('xwoba_contact', 0)) - float(cur.get('xwoba_contact', 0))
    skill_fp_k = k_delta * bf_per_start * 1.0
    skill_fp_bb = -bb_delta * bf_per_start * 1.0
    skill_fp_barrel = -barrel_delta * bf_per_start * 0.13 * 2.0  # HR×2 FP via ER
    skill_fp_contact = xwoba_delta * 20
    skill_attributable = (skill_fp_k + skill_fp_bb +
                           skill_fp_barrel + skill_fp_contact)
    luck_attributable = fp_delta - skill_attributable

    # If we fell back to prior-2-year comparison, also surface the actual 2026
    # value so the user knows what the small sample is reporting
    actual_2026 = (float(rows[2026]['fp_per_start_actual'])
                   if 2026 in rows and int(rows[2026]['gs']) > 0 else None)
    actual_2026_n = int(rows[2026]['gs']) if 2026 in rows else 0

    return {
        'bucket': bucket,
        'base_year': base_year, 'cur_year': cur_year,
        'gs_prior': int(prior['gs']), 'gs_2026': int(cur['gs']),
        'fp_prior': float(prior['fp_per_start_actual']),
        'fp_2026': float(cur['fp_per_start_actual']),
        'fp_delta': fp_delta,
        'n_favorable': n_favorable, 'n_material': n_material,
        'skill_attributable': skill_attributable,
        'luck_attributable': luck_attributable,
        'markers': marker_results,
        'small_2026_note': small_2026_note,
        'actual_2026_fp': actual_2026,
        'actual_2026_n': actual_2026_n,
    }


def divergence_signal(my_ev: float, rp3_per_start: float, bucket: str) -> tuple[str, str]:
    """Reading from the gap between my tool's E[ROS] and rp3's validated number.

    Returns (signal, interpretation) tuple:
      - BUY_LOW: bucket is LEGIT/IMPROVING but rp3 hasn't caught up
                 (model conservative; sustainability says skills support more)
      - SELL_HIGH: bucket is REGRESS but rp3 still high (model hasn't
                   penalized the regression yet)
      - AGREE: gap < threshold
      - WATCH_REGRESS: bucket REGRESS, rp3 also low — both flag concern
      - WATCH_NOISE: bucket NOISE, rp3 reasonable — production won't sustain
    """
    if rp3_per_start is None:
        return ('NO_RP3', 'rp3 has no projection for this pitcher')
    gap = my_ev - rp3_per_start
    if abs(gap) < DIVERGENCE_THRESHOLD:
        if bucket in ('LEGIT', 'IMPROVING'):
            return ('AGREE_BULLISH', 'sustainability + rp3 both bullish')
        elif bucket in ('REGRESS', 'NOISE'):
            return ('AGREE_BEARISH', 'sustainability + rp3 both bearish')
        else:
            return ('AGREE', 'sustainability + rp3 within noise')
    elif gap > DIVERGENCE_THRESHOLD:
        if bucket in ('LEGIT', 'IMPROVING'):
            return ('BUY_LOW', 'skill signals strong but rp3 conservative — '
                                'model may be lagging the breakout')
        elif bucket == 'NOISE':
            return ('SELL_HIGH', 'production up but skills do not support — '
                                  'rp3 already conservative, regression coming')
        elif bucket == 'BAD_LUCK':
            return ('BUY_LOW', 'production down but skills holding — '
                                'rp3 may catch the bounce')
        else:
            return ('DISAGREE', f'sustainability E[ROS]={my_ev:.2f} '
                                 f'>> rp3={rp3_per_start:.2f} — investigate')
    else:  # my_ev < rp3
        if bucket == 'REGRESS':
            return ('SELL_HIGH', 'skill regression real but rp3 still bullish — '
                                  'sell now before model catches up')
        else:
            return ('DISAGREE', f'sustainability E[ROS]={my_ev:.2f} '
                                 f'<< rp3={rp3_per_start:.2f} — investigate')


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


SIGNAL_PREFIX = {
    'BUY_LOW': '↑ BUY-LOW   ', 'SELL_HIGH': '↓ SELL-HIGH ',
    'AGREE_BULLISH': '✓ CONFIRM   ', 'AGREE_BEARISH': '✗ CONFIRM   ',
    'AGREE': '· AGREE     ', 'WATCH_REGRESS': '! WATCH-RGR ',
    'WATCH_NOISE': '! WATCH-NSE ', 'DISAGREE': '? INVESTIGAT',
    'NO_RP3': '— no rp3    ',
}


def print_per_pitcher(name: str, c: dict, ros: dict, rp3_info: dict | None):
    print(f'\n--- {name} ---')
    bucket = c.get('bucket', '?')
    rp3_per_start = rp3_info.get('per_start') if rp3_info else None
    rp3_sigma = rp3_info.get('sigma') if rp3_info else None
    rp3_str = f"{rp3_per_start:.2f}" if rp3_per_start is not None else "n/a"
    sigma_str = f" σ={rp3_sigma:.2f}" if rp3_sigma is not None else ""
    print(f"  rp3 per_start: {rp3_str}{sigma_str}  ← validated model (headline)")
    print(f"  Bucket: {BUCKET_EMOJI.get(bucket, bucket)}  ← confidence layer on rp3")
    if bucket in ('NO_2026_DATA', 'NO_BASELINE'):
        print(f"  {c.get('verdict','')}")
        if 'fp_2026' in c:
            print(f"  2026 (n={c.get('gs_2026','?')}): "
                  f"FP/start={c['fp_2026']:.1f}  velo={c.get('velo_2026',0):.1f}  "
                  f"K%={c.get('k_pct_2026',0):.3f}")
        return
    note = c.get('small_2026_note', '')
    if note:
        print(f"  ⚠ {note.strip(' (').rstrip(')')}")
    print(f"  {c['base_year']} (n={c['gs_prior']}): FP/start={c['fp_prior']:.1f}")
    print(f"  {c['cur_year']} (n={c['gs_2026']}): FP/start={c['fp_2026']:.1f}  "
          f"Δ={c['fp_delta']:+.1f}  ({c['n_material']}/{len(c['markers'])} skills materially favorable)")
    if c.get('actual_2026_fp') is not None and c['cur_year'] != 2026:
        print(f"  2026 actual (n={c['actual_2026_n']}): FP/start={c['actual_2026_fp']:.1f}  "
              f"(small sample — not used in classification)")
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
        print(f"  sustainability E[ROS]: bull={ros['bull']:.1f} ({ros['p_bull']*100:.0f}%)  "
              f"base={ros['base']:.1f} ({ros['p_base']*100:.0f}%)  "
              f"bear={ros['bear']:.1f} ({ros['p_bear']*100:.0f}%)  "
              f"→ E={ros['ev']:.2f}")
        # Divergence signal
        if rp3_per_start is not None:
            sig, interp = divergence_signal(ros['ev'], rp3_per_start, bucket)
            gap = ros['ev'] - rp3_per_start
            print(f"  Signal: {SIGNAL_PREFIX.get(sig, sig)}  (gap={gap:+.2f} FP) — {interp}")


def print_summary_table(results: list[dict]):
    print(f'\n\n=== SUMMARY (sorted by rp3 per_start desc) ===')
    print(f'{"Pitcher":<22} {"rp3":>6} {"Sus":<11} {"Bucket":<12} {"2026":>6} {"Skill":>6} {"Signal":<14}')
    print('-' * 95)
    for r in results:
        cls = r['classification']
        bucket = cls.get('bucket', '?')
        rp3_info = r.get('rp3') or {}
        rp3_ps = rp3_info.get('per_start')
        rp3_str = f"{rp3_ps:.2f}" if rp3_ps is not None else "  n/a"
        if bucket in ('NO_2026_DATA', 'NO_BASELINE'):
            print(f"{r['name']:<22} {rp3_str:>6} {'n/a':<11} {BUCKET_EMOJI[bucket]:<12} "
                  f"{cls.get('fp_2026', 0):>6.1f} {'n/a':>6} {'NO_RP3' if rp3_ps is None else '·  AGREE'}")
            continue
        ros = r.get('ros', {})
        my_ev = ros.get('ev', 0)
        sus_str = f"{my_ev:.2f}"
        if rp3_ps is not None:
            sig, _ = divergence_signal(my_ev, rp3_ps, bucket)
        else:
            sig = 'NO_RP3'
        sig_label = SIGNAL_PREFIX.get(sig, sig).strip()
        skill_str = f"{cls.get('skill_attributable', 0):+.1f}"
        print(f"{r['name']:<22} {rp3_str:>6} {sus_str:<11} {BUCKET_EMOJI[bucket]:<12} "
              f"{cls['fp_2026']:>6.1f} {skill_str:>6} {sig_label:<14}")


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
    rp3_map = load_rp3_map()

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
        rp3_info = rp3_map.get(_norm(n))
        results.append({'name': n, 'classification': cls, 'ros': ros, 'rp3': rp3_info})
        if not args.brief:
            print_per_pitcher(n, cls, ros, rp3_info)

    # Sort summary: rp3 per_start primary, sustainability E[ROS] fallback
    def sort_key(r):
        rp3 = r.get('rp3') or {}
        if rp3.get('per_start') is not None:
            return -rp3['per_start']
        ros = r.get('ros', {})
        if ros and 'ev' in ros:
            return -ros['ev']
        return -r['classification'].get('fp_2026', 0)
    results.sort(key=sort_key)
    print_summary_table(results)

    # Watch-list call-outs: SIGNAL flags worth surfacing
    print(f'\n=== ACTIONABLE SIGNALS ===')
    buy_low, sell_high = [], []
    for r in results:
        cls = r['classification']
        ros = r.get('ros') or {}
        rp3 = r.get('rp3') or {}
        if rp3.get('per_start') is None or 'ev' not in ros:
            continue
        sig, interp = divergence_signal(ros['ev'], rp3['per_start'], cls.get('bucket'))
        if sig == 'BUY_LOW':
            buy_low.append((r['name'], rp3['per_start'], ros['ev'], interp))
        elif sig == 'SELL_HIGH':
            sell_high.append((r['name'], rp3['per_start'], ros['ev'], interp))
    if buy_low:
        print('  BUY-LOW (sustainability bullish, rp3 hasn\'t caught up):')
        for n, rp, ev, msg in buy_low:
            print(f'    {n:<22} rp3={rp:.2f}  sus E[ROS]={ev:.2f}  Δ={ev-rp:+.2f}  — {msg}')
    if sell_high:
        print('  SELL-HIGH (sustainability bearish, rp3 still high):')
        for n, rp, ev, msg in sell_high:
            print(f'    {n:<22} rp3={rp:.2f}  sus E[ROS]={ev:.2f}  Δ={ev-rp:+.2f}  — {msg}')
    if not buy_low and not sell_high:
        print('  (none — sustainability and rp3 in agreement)')


if __name__ == '__main__':
    main()
