"""validate_rolling_trend_v2.py — three additional diagnostics.

v1 found no predictive signal for rest-of-season. Three hypotheses to test:
  A) Signal is real but short-horizon (next 2 weeks, not full season)
  B) Signal lives in EXTREME flag counts (≥5 flags), drowned in pooled mean
  C) Signal is conditional on slow start (mean-reversion confound)
"""
from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RES = ROOT / 'data' / 'research'

from scripts.xfp.rolling_skill_trend import (
    PA_EVENTS, weekly_aggregate, detect_trend)
from scripts.xfp.validate_rolling_trend import (
    load_year, skill_fp_per_pa, YEARS, CUTOFF_WEEKS)


def validate_year_short_horizon(year: int, horizon_weeks: int = 2):
    """Same as v1 but post-cutoff outcome is only the NEXT 2 weeks."""
    df = load_year(year)
    if df.empty: return []
    season_start = df['game_date'].min()
    cutoff = season_start + pd.Timedelta(weeks=CUTOFF_WEEKS)
    horizon_end = cutoff + pd.Timedelta(weeks=horizon_weeks)

    pre = df[df['game_date'] < cutoff].copy()
    post = df[(df['game_date'] >= cutoff) & (df['game_date'] < horizon_end)].copy()

    pre_pa = pre[pre['is_pa'] == 1].groupby('batter').size()
    post_pa = post[post['is_pa'] == 1].groupby('batter').size()
    qualified = set(pre_pa[pre_pa >= 50].index) & set(post_pa[post_pa >= 20].index)
    if not qualified: return []

    weekly_pre = weekly_aggregate(pre[pre['batter'].isin(qualified)])
    pre_events = pre.groupby('batter')['events']
    post_events = post.groupby('batter')['events']

    rows = []
    for bid in qualified:
        trend = detect_trend(weekly_pre, bid)
        if trend.get('trend') == 'insufficient_data': continue
        pre_r, _ = skill_fp_per_pa(pre_events.get_group(bid))
        post_r, post_n = skill_fp_per_pa(post_events.get_group(bid))
        flags = trend.get('flags', [])
        rows.append({
            'year': year, 'batter': bid,
            'trend': trend['trend'],
            'n_pos': sum(1 for f in flags if f.startswith('+')),
            'n_neg': sum(1 for f in flags if f.startswith('-')),
            'pre_skill': pre_r,
            'post_skill': post_r,
            'post_pa': post_n,
        })
    return rows


def main():
    # =========================================================
    # Diagnostic A: short-horizon (2-week) outcome
    # =========================================================
    print('=' * 70)
    print('DIAGNOSTIC A: short-horizon (next 2 weeks) outcome')
    print('=' * 70)
    rows = []
    for y in YEARS:
        rows.extend(validate_year_short_horizon(y, horizon_weeks=2))
    df = pd.DataFrame(rows)
    print(f'N = {len(df)} hitter-years')

    order = ['IMPROVING', 'slight_up', 'stable', 'slight_down', 'DECLINING']
    g = df.groupby('trend').agg(
        n=('batter', 'count'),
        pre=('pre_skill', 'mean'),
        post=('post_skill', 'mean'),
    ).reindex(order).dropna(how='all')
    print(f'\n{"LABEL":<14s} {"N":>4s} {"PRE":>8s} {"POST_2w":>9s} {"DELTA":>9s}')
    for label, row in g.iterrows():
        print(f'  {label:<14s} {int(row["n"]):>4d} {row["pre"]:>8.4f} '
              f'{row["post"]:>9.4f} {row["post"]-row["pre"]:>+9.4f}')

    print(f'\n  r(n_pos, post 2wk):  {df[["n_pos","post_skill"]].corr().iloc[0,1]:+.3f}')
    print(f'  r(n_pos, post | pre): partial = '
          f'{_partial_r(df, "n_pos", "post_skill", "pre_skill"):+.3f}')

    imp = df[df['trend']=='IMPROVING']['post_skill'].mean()
    dec = df[df['trend']=='DECLINING']['post_skill'].mean()
    print(f'  IMPROVING - DECLINING gap (2wk out): {imp-dec:+.4f}')

    # =========================================================
    # Diagnostic B: extreme flag counts only
    # =========================================================
    print('\n' + '=' * 70)
    print('DIAGNOSTIC B: extreme flag counts (rest-of-season)')
    print('=' * 70)
    df_full = pd.read_csv(RES / 'rolling_trend_validation.csv')
    for npos_min in [3, 4, 5, 6]:
        sub_pos = df_full[df_full['n_pos'] >= npos_min]
        sub_neg = df_full[df_full['n_neg'] >= npos_min]
        if len(sub_pos) < 5 or len(sub_neg) < 5: continue
        print(f'  n_flag ≥ {npos_min}: '
              f'POS n={len(sub_pos):>3d} post={sub_pos["post_skill_fp_pa"].mean():.4f} | '
              f'NEG n={len(sub_neg):>3d} post={sub_neg["post_skill_fp_pa"].mean():.4f} | '
              f'gap={sub_pos["post_skill_fp_pa"].mean()-sub_neg["post_skill_fp_pa"].mean():+.4f}')

    # =========================================================
    # Diagnostic C: conditional on slow start
    # =========================================================
    print('\n' + '=' * 70)
    print('DIAGNOSTIC C: slow vs hot starters separately')
    print('=' * 70)
    med = df_full['pre_skill_fp_pa'].median()
    print(f'Pre-cutoff median skill_fp/PA: {med:.4f}')

    for label_subset, sub in [('SLOW STARTERS (pre < median)', df_full[df_full['pre_skill_fp_pa'] < med]),
                                ('HOT STARTERS (pre ≥ median)', df_full[df_full['pre_skill_fp_pa'] >= med])]:
        print(f'\n  {label_subset}:  N={len(sub)}')
        g = sub.groupby('trend').agg(
            n=('batter','count'),
            post=('post_skill_fp_pa', 'mean'),
        ).reindex(order).dropna(how='all')
        for lbl, row in g.iterrows():
            print(f'    {lbl:<14s} N={int(row["n"]):>4d}  post={row["post"]:.4f}')
        imp_m = sub[sub['trend']=='IMPROVING']['post_skill_fp_pa'].mean()
        dec_m = sub[sub['trend']=='DECLINING']['post_skill_fp_pa'].mean()
        print(f'    IMPROVING - DECLINING gap: {imp_m-dec_m:+.4f}')


def _partial_r(df, x, y, z):
    sub = df[[x, y, z]].dropna()
    if len(sub) < 10: return float('nan')
    sx, ix = np.polyfit(sub[z], sub[x], 1)
    sy, iy = np.polyfit(sub[z], sub[y], 1)
    rx = sub[x] - (sx * sub[z] + ix)
    ry = sub[y] - (sy * sub[z] + iy)
    return float(np.corrcoef(rx, ry)[0, 1])


if __name__ == '__main__':
    main()
