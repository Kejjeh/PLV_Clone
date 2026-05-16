"""validate_rolling_trend.py — does rolling skill trend actually predict?

Methodology:
  For each historical year 2018-2025 (skip 2020 short season):
    - Truncate to first 6 weeks of the season (mimics 2026-05-11 cutoff)
    - Run rolling_skill_trend.detect_trend on pre-cutoff weekly buckets
    - Measure post-cutoff (weeks 7..end) outcome: TB+BB+HBP-K per PA
      (skill-only core_fp proxy from statcast — drops R/RBI/SB which
       are context-driven and not the trend module's domain)
    - Compare pre-cutoff baseline to post-cutoff actual

Reports:
  1. Mean post-cutoff skill rate by trend label
  2. Correlation between n_pos_flags / n_neg_flags and post-cutoff rate
  3. Delta (post - pre) by trend label — does IMPROVING actually beat
     its own baseline more than DECLINING does?
  4. Per-year consistency check
  5. Partial r controlling for pre-cutoff baseline (i.e. does the flag
     add signal beyond what rolling FP already tells us?)
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
    PA_EVENTS, SWINGS, WHIFFS, weekly_aggregate, detect_trend
)

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
CUTOFF_WEEKS = 6


def load_year(year: int) -> pd.DataFrame:
    """Load pitch-level statcast for a year + standard derived columns."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    base_cols = ['game_date', 'batter', 'events', 'description', 'pitch_type',
                 'launch_speed', 'launch_angle']
    df = pd.read_parquet(path, columns=base_cols)
    # bat_speed only exists 2024+
    try:
        bs = pd.read_parquet(path, columns=['bat_speed'])
        df['bat_speed'] = bs['bat_speed'].values
    except Exception:
        df['bat_speed'] = np.nan
    df['game_date'] = pd.to_datetime(df['game_date'])
    df['week_start'] = df['game_date'].dt.to_period('W-SUN').apply(lambda x: x.start_time)
    df['is_pa'] = df['events'].isin(PA_EVENTS).astype(int)
    df['is_swing'] = df['description'].isin(SWINGS).astype(int)
    df['is_whiff'] = df['description'].isin(WHIFFS).astype(int)
    df['is_k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['is_bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    return df


def skill_fp_per_pa(events: pd.Series) -> tuple[float, int]:
    """TB+BB+HBP-K per PA, restricted to PA-ending events.
    Returns (rate, pa_count). 0/0 returns (nan, 0)."""
    pa = events.isin(PA_EVENTS)
    n_pa = int(pa.sum())
    if n_pa == 0:
        return float('nan'), 0
    pe = events[pa]
    tb = ((pe == 'single').sum() * 1
          + (pe == 'double').sum() * 2
          + (pe == 'triple').sum() * 3
          + (pe == 'home_run').sum() * 4)
    bb = int(pe.isin({'walk', 'intent_walk'}).sum())
    hbp = int((pe == 'hit_by_pitch').sum())
    k = int(pe.isin({'strikeout', 'strikeout_double_play'}).sum())
    return float((tb + bb + hbp - k) / n_pa), n_pa


def validate_year(year: int) -> list[dict]:
    df = load_year(year)
    if df.empty:
        return []
    season_start = df['game_date'].min()
    cutoff = season_start + pd.Timedelta(weeks=CUTOFF_WEEKS)

    pre = df[df['game_date'] < cutoff].copy()
    post = df[df['game_date'] >= cutoff].copy()

    # Qualify hitters: ≥ 50 PA pre + ≥ 50 PA post
    pre_pa_count = pre[pre['is_pa'] == 1].groupby('batter').size()
    post_pa_count = post[post['is_pa'] == 1].groupby('batter').size()
    qualified = set(pre_pa_count[pre_pa_count >= 50].index) & set(
        post_pa_count[post_pa_count >= 50].index)
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
            'year': year,
            'batter': bid,
            'pre_pa': pre_n,
            'post_pa': post_n,
            'trend': trend['trend'],
            'n_pos': sum(1 for f in flags if f.startswith('+')),
            'n_neg': sum(1 for f in flags if f.startswith('-')),
            'pre_skill_fp_pa': pre_r,
            'post_skill_fp_pa': post_r,
            'delta': post_r - pre_r,
        })
    return rows


def partial_corr(df: pd.DataFrame, x: str, y: str, z: str) -> float:
    """r(x, y | z) — partial correlation of x and y controlling for z."""
    sub = df[[x, y, z]].dropna()
    if len(sub) < 10:
        return float('nan')
    def resid(a, b):
        slope, intercept = np.polyfit(sub[b], sub[a], 1)
        return sub[a] - (slope * sub[b] + intercept)
    rx = resid(x, z)
    ry = resid(y, z)
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    all_rows = []
    for y in YEARS:
        print(f'  loading {y}...')
        all_rows.extend(validate_year(y))
    df = pd.DataFrame(all_rows)
    print(f'\nTotal sample: {len(df)} hitter-years across {df["year"].nunique()} seasons')

    df.to_csv(RES / 'rolling_trend_validation.csv', index=False)

    # Pooled summary by trend label
    order = ['IMPROVING', 'slight_up', 'stable', 'slight_down', 'DECLINING']
    g = df.groupby('trend').agg(
        n=('batter', 'count'),
        pre_skill=('pre_skill_fp_pa', 'mean'),
        post_skill=('post_skill_fp_pa', 'mean'),
        delta=('delta', 'mean'),
    ).reindex(order).dropna(how='all')
    print('\n=== Mean skill_fp/PA by trend label (pooled) ===')
    print(f'{"LABEL":<14s} {"N":>4s} {"PRE":>8s} {"POST":>8s} {"DELTA":>8s}')
    for label, row in g.iterrows():
        print(f'  {label:<14s} {int(row["n"]):>4d} '
              f'{row["pre_skill"]:>8.4f} {row["post_skill"]:>8.4f} '
              f'{row["delta"]:>+8.4f}')

    # Correlations
    print('\n=== Correlations (full pooled sample) ===')
    print(f'  n_pos      vs post_skill:  r = {df[["n_pos","post_skill_fp_pa"]].corr().iloc[0,1]:+.3f}')
    print(f'  n_neg      vs post_skill:  r = {df[["n_neg","post_skill_fp_pa"]].corr().iloc[0,1]:+.3f}')
    print(f'  n_pos-n_neg vs post_skill: r = {(df["n_pos"]-df["n_neg"]).corr(df["post_skill_fp_pa"]):+.3f}')
    print(f'  n_pos      vs delta:       r = {df[["n_pos","delta"]].corr().iloc[0,1]:+.3f}')
    print(f'  n_neg      vs delta:       r = {df[["n_neg","delta"]].corr().iloc[0,1]:+.3f}')

    # Partial r: does n_pos add signal BEYOND pre-cutoff baseline?
    print('\n=== Partial r (controls for pre-cutoff baseline) ===')
    print('  Question: does the trend flag add information BEYOND what')
    print('  the pre-cutoff rolling rate already gives us?')
    pr_pos = partial_corr(df, 'n_pos', 'post_skill_fp_pa', 'pre_skill_fp_pa')
    pr_neg = partial_corr(df, 'n_neg', 'post_skill_fp_pa', 'pre_skill_fp_pa')
    pr_diff = partial_corr(
        df.assign(diff=df['n_pos'] - df['n_neg']),
        'diff', 'post_skill_fp_pa', 'pre_skill_fp_pa')
    print(f'  r(n_pos, post | pre):      {pr_pos:+.3f}')
    print(f'  r(n_neg, post | pre):      {pr_neg:+.3f}')
    print(f'  r(n_pos-n_neg, post | pre): {pr_diff:+.3f}')

    # Per-year consistency
    print('\n=== Per-year IMPROVING vs DECLINING delta (consistency check) ===')
    print(f'{"YEAR":<6s} {"N_IMP":>5s} {"DEL_IMP":>9s} {"N_DEC":>5s} {"DEL_DEC":>9s} {"GAP":>9s}')
    for y in sorted(df['year'].unique()):
        sub = df[df['year'] == y]
        imp = sub[sub['trend'] == 'IMPROVING']
        dec = sub[sub['trend'] == 'DECLINING']
        di = imp['post_skill_fp_pa'].mean() if len(imp) else float('nan')
        dd = dec['post_skill_fp_pa'].mean() if len(dec) else float('nan')
        gap = di - dd if pd.notna(di) and pd.notna(dd) else float('nan')
        print(f'  {y:<6d} {len(imp):>5d} {di:>9.4f} {len(dec):>5d} {dd:>9.4f} '
              f'{gap:>+9.4f}')

    # Verdict
    g_imp = df[df['trend'] == 'IMPROVING']['post_skill_fp_pa']
    g_dec = df[df['trend'] == 'DECLINING']['post_skill_fp_pa']
    gap_overall = g_imp.mean() - g_dec.mean() if len(g_imp) and len(g_dec) else 0
    print(f'\nIMPROVING - DECLINING gap (pooled): {gap_overall:+.4f} skill_fp/PA')
    print(f'  → over ~300 PA remaining: {gap_overall*300:+.1f} skill_fp')

    print(f'\nwrote {RES / "rolling_trend_validation.csv"}')


if __name__ == '__main__':
    main()
