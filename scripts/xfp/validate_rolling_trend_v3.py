"""validate_rolling_trend_v3.py — sweep both cutoff and horizon weeks.

v1 found rest-of-season = noise. v2 found 2-week horizon ≈ +0.016 signal.
This sweeps the full grid:
  cutoff_weeks (when we evaluate the trend):  4, 5, 6, 7, 8
  horizon_weeks (how far we measure outcome): 1, 2, 3, 4, 6, 12, eos

Goal: is the 2-week-horizon signal a fluke or robust? At what horizon
does it decay to noise? Does the signal also depend on when in the
season we run the trend?

For each cell reports:
  N, IMPROVING - DECLINING gap, partial r (n_pos | pre)
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
from scripts.xfp.validate_rolling_trend import load_year, skill_fp_per_pa

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
CUTOFFS = [4, 5, 6, 7, 8]
HORIZONS = [1, 2, 3, 4, 6, 12, 'eos']
MIN_PRE_PA = 50
MIN_POST_PA = {1: 10, 2: 20, 3: 30, 4: 40, 6: 50, 12: 50, 'eos': 50}


def evaluate(df_year: pd.DataFrame, cutoff_w: int, horizon: int | str) -> list[dict]:
    season_start = df_year['game_date'].min()
    cutoff = season_start + pd.Timedelta(weeks=cutoff_w)
    if horizon == 'eos':
        horizon_end = df_year['game_date'].max() + pd.Timedelta(days=1)
    else:
        horizon_end = cutoff + pd.Timedelta(weeks=horizon)

    pre = df_year[df_year['game_date'] < cutoff]
    post = df_year[(df_year['game_date'] >= cutoff) & (df_year['game_date'] < horizon_end)]

    pre_pa = pre[pre['is_pa'] == 1].groupby('batter').size()
    post_pa = post[post['is_pa'] == 1].groupby('batter').size()
    min_post = MIN_POST_PA[horizon]
    qualified = set(pre_pa[pre_pa >= MIN_PRE_PA].index) & set(
        post_pa[post_pa >= min_post].index)
    if not qualified:
        return []

    weekly_pre = weekly_aggregate(pre[pre['batter'].isin(qualified)])
    pre_events = pre.groupby('batter')['events']
    post_events = post.groupby('batter')['events']

    rows = []
    for bid in qualified:
        trend = detect_trend(weekly_pre, bid)
        if trend.get('trend') == 'insufficient_data':
            continue
        pre_r, pre_n = skill_fp_per_pa(pre_events.get_group(bid))
        post_r, post_n = skill_fp_per_pa(post_events.get_group(bid))
        flags = trend.get('flags', [])
        rows.append({
            'cutoff_w': cutoff_w,
            'horizon': horizon,
            'batter': bid,
            'trend': trend['trend'],
            'n_pos': sum(1 for f in flags if f.startswith('+')),
            'n_neg': sum(1 for f in flags if f.startswith('-')),
            'pre_skill': pre_r,
            'post_skill': post_r,
        })
    return rows


def partial_r(df, x, y, z):
    sub = df[[x, y, z]].dropna()
    if len(sub) < 10: return float('nan')
    sx, ix_ = np.polyfit(sub[z], sub[x], 1)
    sy, iy_ = np.polyfit(sub[z], sub[y], 1)
    rx = sub[x] - (sx * sub[z] + ix_)
    ry = sub[y] - (sy * sub[z] + iy_)
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    # Load all years once
    year_data = {}
    for y in YEARS:
        print(f'  loading {y}...')
        year_data[y] = load_year(y)

    grid = {}
    for cw in CUTOFFS:
        for hz in HORIZONS:
            print(f'  evaluating cutoff={cw}w horizon={hz}...')
            rows = []
            for y in YEARS:
                rows.extend(evaluate(year_data[y], cw, hz))
            df = pd.DataFrame(rows)
            if len(df) < 100:
                grid[(cw, hz)] = None
                continue
            imp = df[df['trend'] == 'IMPROVING']['post_skill']
            dec = df[df['trend'] == 'DECLINING']['post_skill']
            gap = (imp.mean() - dec.mean()) if len(imp) and len(dec) else float('nan')
            r_npos_post = df[['n_pos', 'post_skill']].corr().iloc[0, 1]
            pr = partial_r(df, 'n_pos', 'post_skill', 'pre_skill')
            # DECLINING-specific: how much do declining players underperform their pre baseline?
            dec_delta = (dec.mean() - df[df['trend']=='DECLINING']['pre_skill'].mean()) if len(dec) else float('nan')
            imp_delta = (imp.mean() - df[df['trend']=='IMPROVING']['pre_skill'].mean()) if len(imp) else float('nan')
            grid[(cw, hz)] = {
                'n': len(df),
                'n_imp': len(imp),
                'n_dec': len(dec),
                'gap': gap,
                'r_npos_post': r_npos_post,
                'partial_r_pre': pr,
                'imp_delta': imp_delta,
                'dec_delta': dec_delta,
            }

    # ===== Print grid =====
    print('\n' + '=' * 90)
    print('GRID: IMPROVING − DECLINING gap in post-cutoff skill_fp/PA')
    print('=' * 90)
    header = f'{"CUTOFF↓ / HORIZON→":<18s}'
    for hz in HORIZONS:
        header += f' {str(hz)+"w":>9s}' if hz != 'eos' else f' {"eos":>9s}'
    print(header)
    for cw in CUTOFFS:
        row = f'  {cw}w' + ' ' * 13
        for hz in HORIZONS:
            g = grid[(cw, hz)]
            cell = '   —     ' if g is None else f' {g["gap"]:>+8.4f}'
            row += cell
        print(row)

    print('\n' + '=' * 90)
    print('GRID: partial r(n_pos, post | pre) — does flag add signal beyond rolling rate?')
    print('=' * 90)
    print(header)
    for cw in CUTOFFS:
        row = f'  {cw}w' + ' ' * 13
        for hz in HORIZONS:
            g = grid[(cw, hz)]
            cell = '   —     ' if g is None else f' {g["partial_r_pre"]:>+8.3f}'
            row += cell
        print(row)

    print('\n' + '=' * 90)
    print('GRID: DECLINING delta (post - pre) — how much do flagged-down players actually drop?')
    print('=' * 90)
    print(header)
    for cw in CUTOFFS:
        row = f'  {cw}w' + ' ' * 13
        for hz in HORIZONS:
            g = grid[(cw, hz)]
            cell = '   —     ' if g is None else f' {g["dec_delta"]:>+8.4f}'
            row += cell
        print(row)

    print('\n' + '=' * 90)
    print('GRID: IMPROVING delta (post - pre) — do flagged-up players actually rise?')
    print('=' * 90)
    print(header)
    for cw in CUTOFFS:
        row = f'  {cw}w' + ' ' * 13
        for hz in HORIZONS:
            g = grid[(cw, hz)]
            cell = '   —     ' if g is None else f' {g["imp_delta"]:>+8.4f}'
            row += cell
        print(row)

    print('\n' + '=' * 90)
    print('GRID: sample size N')
    print('=' * 90)
    print(header)
    for cw in CUTOFFS:
        row = f'  {cw}w' + ' ' * 13
        for hz in HORIZONS:
            g = grid[(cw, hz)]
            cell = '   —     ' if g is None else f' {g["n"]:>8d}'
            row += cell
        print(row)

    # Save tidy CSV
    out_rows = []
    for (cw, hz), g in grid.items():
        if g is None: continue
        out_rows.append({'cutoff_w': cw, 'horizon': hz, **g})
    pd.DataFrame(out_rows).to_csv(RES / 'rolling_trend_grid.csv', index=False)
    print(f'\nwrote {RES / "rolling_trend_grid.csv"}')


if __name__ == '__main__':
    main()
