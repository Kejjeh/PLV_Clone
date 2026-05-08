"""build_hitter_lineup.py — per-(batter, game) lineup-spot derivation.

For each (game_pk, batter), derives the batting order position by finding
the batter's first plate appearance in inning 1.

Inning-1 at-bats are ordered 1-9 for each team:
  - inning=1, inning_topbot=Top, AB 1-9 = away team batting order spots 1-9
  - inning=1, inning_topbot=Bot, AB 1-9 = home team batting order spots 1-9

A batter who first appears AFTER inning 1 is a pinch-hitter / pinch-runner
(they're flagged with lineup_spot=NaN, started_game=False).

Output: data/research/xfp_cache/hitter_lineup_appearances_{year}.parquet
        per (batter, game_pk) row with lineup_spot, started_game, pa_in_game.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]


def per_game_lineup(p: pd.DataFrame) -> pd.DataFrame:
    """Compute per-(batter, game_pk) lineup-spot summary.

    Approach: per (game_pk, batting team), find the first 9 distinct batters by
    AB order — those are the starting lineup spots 1-9 in order of first
    appearance. Subsequent unique batters are PH/PR (lineup_spot=NaN, started=False).
    """
    p = p.copy()
    p['inning'] = pd.to_numeric(p['inning'], errors='coerce').fillna(0)
    p['at_bat_number'] = pd.to_numeric(p['at_bat_number'], errors='coerce').fillna(0)
    p['pitch_number'] = pd.to_numeric(p['pitch_number'], errors='coerce').fillna(0)

    # Per-(game_pk, batter) — find first plate appearance ordering
    p_first = (p.sort_values(['game_pk', 'at_bat_number', 'pitch_number'])
                .groupby(['game_pk', 'batter']).head(1).copy())
    # Tag batting team for the batter's first AB
    p_first['batting_side'] = np.where(p_first['inning_topbot'] == 'Top', 'away', 'home')

    # Within each (game_pk, batting_side), order batters by their first-AB at_bat_number
    # The first 9 = lineup spots 1-9 in order; later = PH/PR
    p_first = p_first.sort_values(['game_pk', 'batting_side', 'at_bat_number', 'pitch_number'])
    p_first['_order_in_team'] = p_first.groupby(['game_pk', 'batting_side']).cumcount() + 1
    p_first['lineup_spot'] = np.where(p_first['_order_in_team'] <= 9,
                                      p_first['_order_in_team'], np.nan)
    p_first['started_game'] = p_first['lineup_spot'].notna()
    p_first['lineup_spot'] = p_first['lineup_spot'].astype(float)

    # PAs per game per batter (using is_pa_end heuristic)
    ev = p['events'].fillna('')
    NON_PA = {'stolen_base_2b','stolen_base_3b','stolen_base_home',
              'caught_stealing_2b','caught_stealing_3b','caught_stealing_home',
              'pickoff_1b','pickoff_2b','pickoff_3b',
              'wild_pitch','passed_ball','balk'}
    p['is_pa_end'] = (ev != '') & ~ev.isin(NON_PA)
    pa_per = p.groupby(['game_pk', 'batter'])['is_pa_end'].sum().rename('pa_in_game').reset_index()

    out = p_first[['game_pk','batter','lineup_spot','started_game']].merge(
        pa_per, on=['game_pk','batter'], how='left')
    out['pa_in_game'] = out['pa_in_game'].fillna(0).astype(int)

    # Game date
    game_date = p.groupby('game_pk')['game_date'].first().rename('game_date').reset_index()
    out = out.merge(game_date, on='game_pk', how='left')
    return out


def build_year(year: int) -> pd.DataFrame:
    sc_path = CACHE / f'statcast_{year}.parquet'
    if not sc_path.exists():
        return pd.DataFrame()
    print(f'[{year}] loading statcast...', flush=True)
    keep_cols = ['game_pk','game_date','batter','inning','inning_topbot',
                 'at_bat_number','pitch_number','events']
    pitches = pd.read_parquet(sc_path, columns=keep_cols)
    pitches['game_date'] = pd.to_datetime(pitches['game_date'])
    return per_game_lineup(pitches)


def main():
    print('=== build_hitter_lineup ===')
    for yr in YEARS:
        out_path = CACHE / f'hitter_lineup_appearances_{yr}.parquet'
        df = build_year(yr)
        if df.empty:
            continue
        df['year'] = yr
        df.to_parquet(out_path, index=False)
        starters = (df['lineup_spot'].notna()).sum()
        print(f'  appearances: {len(df)} | starters (with lineup spot): {starters} '
              f'({100*starters/max(len(df),1):.0f}%)')
        # Spot check: avg lineup spot for known leadoff hitters
        if yr in (2024, 2025):
            spot_dist = df['lineup_spot'].value_counts(dropna=False).sort_index()
            print(f'  lineup_spot distribution: {dict(spot_dist.head(11))}')


if __name__ == '__main__':
    main()
