"""lineup_protection.py — does the hitter behind you matter?

For each batter, identify the player most often hitting in the next lineup
spot (n+1) and compute that protector's career wOBA. Test whether having a
strong protector lifts walks/RBI rates for the protected batter.

Method:
  - For each game-batter row in lineup appearances, look up the player at
    lineup_spot+1 (or 1 if lineup_spot==9) in the same game.
  - Aggregate to (batter, protector) pairs across games. Pick the protector
    most frequently appearing behind that batter (the "regular protector").
  - Pull statcast PA-level events, compute per-batter walk_pct, k_pct,
    isolated power IN protected vs UNprotected games (defined by protector
    career xwOBA tertile within season).

Output: data/outputs/lineup_protection.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    pair_frames = []
    pa_frames = []
    protector_woba_by_year = {}
    for year in range(2018, 2027):
        if year == 2020:
            continue
        sc_path = CACHE / f'statcast_{year}.parquet'
        lu_path = CACHE / f'hitter_lineup_appearances_{year}.parquet'
        if not (sc_path.exists() and lu_path.exists()):
            continue
        lu = pd.read_parquet(lu_path)
        lu = lu[lu['started_game'] & lu['lineup_spot'].notna()].copy()
        lu['lineup_spot'] = lu['lineup_spot'].astype(int)

        # For each game, build a map of lineup_spot -> batter for that game
        # Then assign protector_id = batter at (spot % 9) + 1
        lu_next = lu[['game_pk', 'lineup_spot', 'batter']].rename(
            columns={'batter': 'protector', 'lineup_spot': 'protector_spot'})
        lu['protector_spot'] = (lu['lineup_spot'] % 9) + 1
        merged = lu.merge(lu_next, on=['game_pk', 'protector_spot'], how='left')
        merged['year'] = year
        pair_frames.append(merged[['game_pk', 'batter', 'protector', 'lineup_spot', 'year']])

        # Statcast PA per game per batter
        sc = pd.read_parquet(sc_path, columns=['game_pk', 'batter', 'events'])
        sc = sc[sc['events'].isin(PA_EVENTS)].copy()
        sc['tb'] = sc['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        sc['bb'] = sc['events'].isin({'walk', 'intent_walk'}).astype(int)
        sc['hbp'] = (sc['events'] == 'hit_by_pitch').astype(int)
        sc['k'] = sc['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        sc['ab'] = (~sc['events'].isin({'walk', 'intent_walk', 'hit_by_pitch', 'sac_bunt', 'sac_fly', 'catcher_interf'})).astype(int)
        sc['hr'] = (sc['events'] == 'home_run').astype(int)
        sc['hit'] = sc['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)
        sc['pa'] = 1
        sc_pa = sc.groupby(['game_pk', 'batter'], as_index=False).agg(
            pa=('pa', 'sum'), tb=('tb', 'sum'), bb=('bb', 'sum'),
            hbp=('hbp', 'sum'), k=('k', 'sum'), ab=('ab', 'sum'),
            hr=('hr', 'sum'), hit=('hit', 'sum'))
        sc_pa['year'] = year
        pa_frames.append(sc_pa)

        # Protector pool: per-year wOBA-ish proxy = per-PA core fp (full season)
        per_player = sc.groupby('batter', as_index=False).agg(
            pa=('pa', 'sum'), tb=('tb', 'sum'), bb=('bb', 'sum'),
            hbp=('hbp', 'sum'), k=('k', 'sum'))
        per_player = per_player[per_player['pa'] >= 200]
        per_player['core_per_pa'] = (per_player['tb'] + per_player['bb'] + per_player['hbp'] - per_player['k']) / per_player['pa']
        protector_woba_by_year[year] = per_player.set_index('batter')['core_per_pa'].to_dict()

    if not (pair_frames and pa_frames):
        print('  no data'); return
    pairs = pd.concat(pair_frames, ignore_index=True)
    pa_full = pd.concat(pa_frames, ignore_index=True)

    # Game-level join
    g = pairs.merge(pa_full, on=['game_pk', 'batter', 'year'], how='inner')
    # Protector quality lookup
    g['protector_quality'] = g.apply(
        lambda r: protector_woba_by_year.get(r['year'], {}).get(r['protector'], np.nan), axis=1)
    g = g[g['protector_quality'].notna()]
    if g.empty:
        print('  no merged rows'); return

    # Per-year tertile cutoffs of protector quality
    tertile_rows = []
    for yr, sub in g.groupby('year'):
        cuts = sub['protector_quality'].quantile([0.33, 0.67]).values
        sub2 = sub.copy()
        sub2['prot_tier'] = np.where(sub2['protector_quality'] <= cuts[0], 'WEAK',
                              np.where(sub2['protector_quality'] >= cuts[1], 'STRONG', 'AVG'))
        tertile_rows.append(sub2)
    g2 = pd.concat(tertile_rows, ignore_index=True)

    # Per-batter, per-tier rates
    agg = g2.groupby(['batter', 'prot_tier'], as_index=False).agg(
        games=('pa', 'count'), pa=('pa', 'sum'), bb=('bb', 'sum'),
        k=('k', 'sum'), hr=('hr', 'sum'), hit=('hit', 'sum'),
        ab=('ab', 'sum'), hbp=('hbp', 'sum'), tb=('tb', 'sum'))
    agg = agg[agg['pa'] >= 100]
    agg['bb_pct'] = (agg['bb'] / agg['pa'] * 100).round(2)
    agg['k_pct'] = (agg['k'] / agg['pa'] * 100).round(2)
    agg['iso'] = ((agg['tb'] - agg['hit']) / agg['ab'].replace(0, np.nan)).round(3)

    pivot = agg.pivot_table(index='batter', columns='prot_tier',
                              values=['pa', 'bb_pct', 'k_pct', 'iso'])
    pivot.columns = [f'{m}_{c}' for m, c in pivot.columns]
    pivot = pivot.reset_index()

    if 'bb_pct_STRONG' in pivot.columns and 'bb_pct_WEAK' in pivot.columns:
        pivot['bb_protect_lift'] = (pivot['bb_pct_STRONG'] - pivot['bb_pct_WEAK']).round(2)
    if 'iso_STRONG' in pivot.columns and 'iso_WEAK' in pivot.columns:
        pivot['iso_protect_lift'] = (pivot['iso_STRONG'] - pivot['iso_WEAK']).round(3)

    rh = PROJECTIONS.rh3()[['batter', 'player_name']].drop_duplicates('batter')
    pivot = pivot.merge(rh, on='batter', how='left')

    fname = OUT / 'lineup_protection.csv'
    pivot.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(pivot)} hitters)')

    # League-wide effect: do bb_pct / iso differ by tier?
    lw = agg.groupby('prot_tier').agg(pa=('pa', 'sum'), bb=('bb', 'sum'),
                                       k=('k', 'sum'), hr=('hr', 'sum'),
                                       hit=('hit', 'sum'), ab=('ab', 'sum'),
                                       tb=('tb', 'sum'))
    lw['bb_pct'] = (lw['bb'] / lw['pa'] * 100).round(2)
    lw['k_pct'] = (lw['k'] / lw['pa'] * 100).round(2)
    lw['iso'] = ((lw['tb'] - lw['hit']) / lw['ab']).round(3)
    print('\n  League-wide effect of protector tier:')
    print(lw[['pa', 'bb_pct', 'k_pct', 'iso']].to_string())

    # Headline: who gains MOST from strong protector
    if 'bb_protect_lift' in pivot.columns:
        sub = pivot[pivot['pa_STRONG'].notna() & pivot['pa_WEAK'].notna()
                    & (pivot['pa_STRONG'] >= 200) & (pivot['pa_WEAK'] >= 200)]
        print('\n  Top 10 walk-rate gainers from STRONG protector:')
        print(sub.sort_values('bb_protect_lift', ascending=False).head(10)[
            ['player_name', 'pa_STRONG', 'pa_WEAK', 'bb_pct_STRONG', 'bb_pct_WEAK', 'bb_protect_lift']].to_string(index=False))


if __name__ == '__main__':
    main()
