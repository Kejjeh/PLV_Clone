"""build_sp_per_start_catcher.py — per-start catcher of record + per-(SP, year)
n_pitches-weighted catcher framing.

Motivation
----------
The modal-catcher proxy (`sp_primary_catcher_2018_2025.csv`) lost catcher-change
information and the resulting `primary_catcher_framing_runs_prior` feature was
REJECTED at Δr -0.0001 against full RP3_FEATS. Per-start catcher-of-record is a
strictly more accurate exposure: it captures within-season catcher swaps,
platoons, trades, and IL replacements that the modal proxy collapses away.

Method
------
1. For each year 2018-2025 (skipping 2020), read the cached statcast parquet.
2. A "start" for pitcher P in game game_pk = P appeared in inning 1 of that
   game. Validated on 2024: 4881 starts (matches MLB total ≈4860).
3. For each start, the catcher of record = the fielder_2 with the most pitches
   caught from P in that game. Ties broken by lower mlbam id.
4. Look up that catcher's CURRENT-year framing_runs_per_100 from
   `catcher_framing_2017_2025.csv` (prior-year framing of the year-Y catcher
   is the leak-free analog of the modal proxy's "prior-year primary catcher,
   prior-year framing" double shift — we use the SAME (year-1) framing as
   the modal version, so the only thing changing is per-start vs modal
   exposure).
5. Aggregate per (pitcher, year): pitch-weighted mean of catcher framing
   across the pitcher's starts that year. Each start contributes
   n_pitches_in_start as weight.

Output
------
- `data/research/xfp_cache/sp_per_start_catcher_2018_2025.csv`
    pitcher, game_pk, game_date, year, catcher_mlbam, n_pitches
- `data/research/xfp_cache/sp_weighted_catcher_framing_2018_2025.csv`
    pitcher, year, n_starts, total_pitches, weighted_catcher_framing_runs_per_100,
    weighted_catcher_framing_runs

Validation feature builds the prior-year version: for rolling row (P, Y), grab
the row for (P, Y-1) from this cache (no separate catcher-shift needed — the
framing is already baked in to the year-Y-1 exposure).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]

FRAMING_CSV = CACHE / 'catcher_framing_2017_2025.csv'
PER_START_CSV = CACHE / 'sp_per_start_catcher_2018_2025.csv'
WEIGHTED_CSV = CACHE / 'sp_weighted_catcher_framing_2018_2025.csv'


def build_per_start_catcher() -> pd.DataFrame:
    """For each (pitcher, game_pk) where pitcher STARTED, find dominant catcher."""
    rows = []
    for year in YEARS:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            print(f'  {year}: no parquet, skipping')
            continue
        df = pd.read_parquet(
            path,
            columns=['pitcher', 'fielder_2', 'game_pk', 'game_date', 'inning'],
        )
        df = df.dropna(subset=['pitcher', 'fielder_2', 'game_pk', 'inning'])
        if df.empty:
            continue
        df = df.astype({'pitcher': int, 'fielder_2': int,
                        'game_pk': int, 'inning': int})

        # Identify starts: pitcher's min inning in that game == 1
        firsts = df.groupby(['pitcher', 'game_pk'])['inning'].min().reset_index()
        starts = firsts[firsts['inning'] == 1][['pitcher', 'game_pk']]

        # Restrict to start rows and find dominant catcher per (P, game)
        d = df.merge(starts, on=['pitcher', 'game_pk'], how='inner')
        cnt = (d.groupby(['pitcher', 'game_pk', 'fielder_2'], as_index=False)
                .size()
                .rename(columns={'size': 'n_pitches'}))
        # Pick max-pitches catcher per (P, game); ties → lower mlbam
        cnt = cnt.sort_values(
            ['pitcher', 'game_pk', 'n_pitches', 'fielder_2'],
            ascending=[True, True, False, True],
        )
        dominant = cnt.drop_duplicates(['pitcher', 'game_pk'], keep='first')

        # Attach game_date (first row per game suffices)
        gd = (d.groupby(['pitcher', 'game_pk'])['game_date']
                .first().reset_index())
        dominant = dominant.merge(gd, on=['pitcher', 'game_pk'], how='left')
        dominant['year'] = year
        dominant = dominant.rename(columns={'fielder_2': 'catcher_mlbam'})

        rows.append(dominant[['pitcher', 'game_pk', 'game_date', 'year',
                              'catcher_mlbam', 'n_pitches']])
        print(f'  {year}: {len(dominant)} starts, '
              f'{dominant["pitcher"].nunique()} SPs, '
              f'{dominant["catcher_mlbam"].nunique()} catchers')

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_weighted_framing(per_start: pd.DataFrame) -> pd.DataFrame:
    fr = pd.read_csv(FRAMING_CSV)
    fr_keep = fr[['catcher_mlbam', 'year',
                  'framing_runs_per_100', 'framing_runs']].copy()
    fr_keep['catcher_mlbam'] = fr_keep['catcher_mlbam'].astype(int)
    fr_keep['year'] = fr_keep['year'].astype(int)

    merged = per_start.merge(fr_keep, on=['catcher_mlbam', 'year'], how='left')
    nn = merged['framing_runs_per_100'].notna().sum()
    print(f'\n  per-start join: {nn}/{len(merged)} '
          f'({100*nn/len(merged):.1f}%) starts have a framing match')

    # Drop unmatched starts (catcher below 100 shadow-pitch threshold).
    # Their effective contribution to weighted mean is 0 weight rather than 0
    # framing — this matches the modal-proxy treatment.
    matched = merged.dropna(subset=['framing_runs_per_100']).copy()

    def agg(g):
        w = g['n_pitches']
        wt_per_100 = float(np.average(g['framing_runs_per_100'], weights=w))
        wt_runs = float(np.average(g['framing_runs'], weights=w))
        return pd.Series({
            'n_starts': int(len(g)),
            'total_pitches': int(w.sum()),
            'weighted_catcher_framing_runs_per_100': wt_per_100,
            'weighted_catcher_framing_runs': wt_runs,
        })

    out = (matched.groupby(['pitcher', 'year'], as_index=False)
                   .apply(agg, include_groups=False)
                   .reset_index(drop=True))
    return out


def main():
    print('=== build_sp_per_start_catcher ===')
    print('\n[1/2] Per-start catcher of record from statcast parquets')
    per_start = build_per_start_catcher()
    if per_start.empty:
        print('FAILED — no per-start rows produced.')
        return
    per_start.to_csv(PER_START_CSV, index=False)
    print(f'\n  wrote {PER_START_CSV} '
          f'({len(per_start)} starts, {per_start["year"].nunique()} years)')

    print('\n[2/2] Per-(SP, year) pitch-weighted catcher framing')
    weighted = build_weighted_framing(per_start)
    if weighted.empty:
        print('FAILED — no weighted rows produced.')
        return
    weighted.to_csv(WEIGHTED_CSV, index=False)
    print(f'  wrote {WEIGHTED_CSV} '
          f'({len(weighted)} pitcher-year rows)')

    # Eye-test: compare top/bottom SPs by 2024 weighted catcher framing
    print('\n[eye-test] 2024 SPs (>=15 starts), best catcher exposure:')
    w24 = weighted[(weighted['year'] == 2024) & (weighted['n_starts'] >= 15)]
    print(w24.sort_values('weighted_catcher_framing_runs_per_100',
                          ascending=False).head(5).to_string(index=False))
    print('\n[eye-test] 2024 SPs (>=15 starts), worst catcher exposure:')
    print(w24.sort_values('weighted_catcher_framing_runs_per_100',
                          ascending=True).head(5).to_string(index=False))

    # Modal-vs-per-start divergence sanity check on 2024
    print('\n[divergence] 2024 modal-vs-per-start framing for top-divergence SPs:')
    modal = pd.read_csv(CACHE / 'sp_primary_catcher_2018_2025.csv')
    fr = pd.read_csv(FRAMING_CSV)
    m24 = modal[modal['year'] == 2024].merge(
        fr[['catcher_mlbam', 'year', 'framing_runs_per_100']]
          .rename(columns={'catcher_mlbam': 'primary_catcher'}),
        on=['primary_catcher', 'year'], how='left',
    ).rename(columns={'framing_runs_per_100': 'modal_framing'})
    cmp_ = w24.merge(m24[['pitcher', 'modal_framing']], on='pitcher', how='inner')
    cmp_['delta'] = (cmp_['weighted_catcher_framing_runs_per_100']
                     - cmp_['modal_framing']).abs()
    print(cmp_.sort_values('delta', ascending=False).head(5)[
        ['pitcher', 'n_starts',
         'weighted_catcher_framing_runs_per_100', 'modal_framing', 'delta']
    ].to_string(index=False))


if __name__ == '__main__':
    main()
