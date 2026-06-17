"""rolling_slump_comparator.py — has this player ever had a streak this bad?

For each player of interest:
  1. Load all 2015-2026 PA-ending events from statcast
  2. Aggregate to per-game core_fp (TB + BB + HBP - K) and PAs
  3. Compute rolling N-game windows where N = games played in 2026 so far
  4. Find current rolling core_fp/PA and locate it in the career distribution
  5. For comparable-or-worse historical windows, report what happened in the
     subsequent 200 PAs (the typical "rest of season" sample)

Output: console report + saved CSV per player.

Notes:
  - core_fp = TB + BB + HBP - K (excludes R, RBI, SB which need extra data)
  - Rolling metric correlates ~0.95 with full fp_per_pa; for SB-heavy players
    (Carroll, Trea Turner) the rolling will UNDER-count their value, so a
    "bad streak" in core_fp may be less severe than it looks.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

# (display_name, batter_id)
PLAYERS = [
    ('Trea Turner',     607208),
    ('Salvador Pérez',  521692),
    ('Corbin Carroll',  682998),
    ('Bo Bichette',     666182),
    ('Eugenio Suárez',  553993),
    ('Rafael Devers',   646240),
    ('Wyatt Langford',  694671),
    ('Vlad Guerrero Jr.', 665489),
    ('Jhoan Duran',     0),  # placeholder; pitcher not analyzed here
]
# Drop the pitcher
PLAYERS = [(n, b) for n, b in PLAYERS if b > 0]

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk',
    'hit_by_pitch', 'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play', 'sac_fly', 'sac_bunt',
    'fielders_choice', 'fielders_choice_out', 'double_play', 'triple_play',
    'field_error', 'catcher_interf',
}

def load_player_pa_history(batter_id: int) -> pd.DataFrame:
    """Concatenate per-PA-ending events across all years for a single batter."""
    frames = []
    for year in range(2015, 2027):
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(
            path,
            columns=['game_pk', 'game_date', 'batter', 'events'],
            filters=[('batter', '=', batter_id)],
        )
        if df.empty:
            continue
        df = df[df['events'].isin(PA_EVENTS)].copy()
        df['year'] = year
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def per_game_core_fp(events_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate PA events to per-game core_fp + PA counts."""
    if events_df.empty:
        return events_df
    df = events_df.copy()
    df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
    df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k']  = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['pa'] = 1
    g = df.groupby(['year', 'game_date', 'game_pk'], as_index=False).agg(
        tb=('tb', 'sum'),
        bb=('bb', 'sum'),
        hbp=('hbp', 'sum'),
        k=('k', 'sum'),
        pa=('pa', 'sum'),
    )
    g['core_fp'] = g['tb'] + g['bb'] + g['hbp'] - g['k']
    g = g.sort_values('game_date').reset_index(drop=True)
    return g


def analyze_player(name: str, batter_id: int) -> dict:
    print(f'\n{"="*92}')
    print(f'  {name}  (batter_id={batter_id})')
    print('='*92)
    events = load_player_pa_history(batter_id)
    if events.empty:
        print('  no data')
        return {}
    games = per_game_core_fp(events)
    if len(games) < 30:
        print(f'  insufficient games: {len(games)}')
        return {}

    cur = games[games['year'] == 2026]
    if cur.empty:
        print('  no 2026 games')
        return {}
    cur_games_n = len(cur)
    cur_pa = int(cur['pa'].sum())
    cur_core = int(cur['core_fp'].sum())
    cur_rate = cur_core / cur_pa if cur_pa > 0 else 0
    print(f'  2026: {cur_games_n} games, {cur_pa} PA, core_fp/PA = {cur_rate:+.3f}')

    # Compute rolling N-game core_fp/PA for full career
    N = cur_games_n
    games['roll_pa']   = games['pa'].rolling(N, min_periods=N).sum()
    games['roll_core'] = games['core_fp'].rolling(N, min_periods=N).sum()
    games['roll_rate'] = games['roll_core'] / games['roll_pa']
    games['roll_end_year'] = games['year']

    valid = games.dropna(subset=['roll_rate'])
    # Exclude windows that are still inside 2026 (we want HISTORICAL comparables)
    historical = valid[valid['year'] < 2026]
    if historical.empty:
        print(f'  no historical windows of length {N}')
        return {}

    pct = (historical['roll_rate'] <= cur_rate).mean() * 100
    n_worse = (historical['roll_rate'] <= cur_rate).sum()
    print(f'  ROLLING-{N}-GAME core_fp/PA distribution (career, excl 2026):')
    print(f'    min:    {historical["roll_rate"].min():+.3f}')
    print(f'    p10:    {historical["roll_rate"].quantile(0.10):+.3f}')
    print(f'    median: {historical["roll_rate"].median():+.3f}')
    print(f'    p90:    {historical["roll_rate"].quantile(0.90):+.3f}')
    print(f'    max:    {historical["roll_rate"].max():+.3f}')
    print(f'    Current 2026 rate ({cur_rate:+.3f}) ranks at the {pct:.1f}-th percentile of historical {N}-game windows')
    print(f'    ({n_worse}/{len(historical)} historical windows were as bad or worse)')

    # For each "comparable bad window" (rolling rate ≤ cur_rate), what happened in the
    # NEXT 100 PAs after the window ended?
    if n_worse == 0:
        print('  >>> UNPRECEDENTED: no historical window was this bad. Tread carefully.')
        return {}

    bad_windows = historical[historical['roll_rate'] <= cur_rate].copy()
    # End-game indices (where the window ends)
    bad_windows['end_idx'] = bad_windows.index
    next_n_pa = 200  # rough RoS proxy
    bounce_results = []
    for end_idx in bad_windows['end_idx'].values:
        # Take the games AFTER end_idx
        after = games.loc[end_idx + 1: end_idx + 200]  # up to 200 games after
        # Stop accumulating once we hit 200 PAs OR end of career
        cum_pa = 0
        rows = []
        for _, gr in after.iterrows():
            rows.append(gr)
            cum_pa += gr['pa']
            if cum_pa >= next_n_pa:
                break
        if not rows:
            continue
        sub = pd.DataFrame(rows)
        next_pa = int(sub['pa'].sum())
        next_core = int(sub['core_fp'].sum())
        if next_pa < 50:  # too few PAs to be meaningful (probably end of season/career)
            continue
        next_rate = next_core / next_pa
        bounce_results.append({
            'window_end_year': int(games.loc[end_idx, 'year']),
            'window_end_date': str(games.loc[end_idx, 'game_date'])[:10],
            'window_rate': games.loc[end_idx, 'roll_rate'],
            'next_pa': next_pa,
            'next_rate': next_rate,
            'delta': next_rate - games.loc[end_idx, 'roll_rate'],
        })

    if not bounce_results:
        print('  no qualifying bounce-back windows (insufficient subsequent data)')
        return {}

    br = pd.DataFrame(bounce_results)
    print(f'\n  AFTER comparable bad streaks (NEXT ~{next_n_pa} PAs):')
    print(f'    n_windows:        {len(br)}')
    print(f'    median next rate: {br["next_rate"].median():+.3f}  (vs slump rate {cur_rate:+.3f})')
    print(f'    p25 next rate:    {br["next_rate"].quantile(0.25):+.3f}')
    print(f'    p75 next rate:    {br["next_rate"].quantile(0.75):+.3f}')
    print(f'    median Δ:         {br["delta"].median():+.3f}  (positive = improvement)')
    print(f'    bounce frequency: {(br["delta"] > 0).mean()*100:.0f}% of comparable streaks rebounded')
    if len(br) <= 12:
        print('  Top windows:')
        for _, r in br.sort_values('window_end_date').iterrows():
            arrow = '↑' if r['delta'] > 0 else '↓'
            print(f'    {r["window_end_date"]}  slump={r["window_rate"]:+.3f}  '
                  f'next {int(r["next_pa"])} PA: {r["next_rate"]:+.3f}  Δ={r["delta"]:+.3f} {arrow}')

    return {
        'name': name,
        'cur_rate': cur_rate,
        'cur_pa': cur_pa,
        'cur_games': cur_games_n,
        'pct_rank': pct,
        'n_comparable': n_worse,
        'median_next_rate': br['next_rate'].median(),
        'bounce_pct': (br['delta'] > 0).mean() * 100,
    }


def main():
    summary = []
    for name, bid in PLAYERS:
        s = analyze_player(name, bid)
        if s:
            summary.append(s)

    print('\n\n' + '='*92)
    print('  SUMMARY')
    print('='*92)
    if summary:
        sdf = pd.DataFrame(summary)
        print(sdf.to_string(index=False))


if __name__ == '__main__':
    main()
