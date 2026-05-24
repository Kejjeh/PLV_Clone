"""build_catcher_framing.py — per-(catcher, year) framing runs from statcast.

pybaseball.statcast_catcher_framing is broken (CSV parser error on Savant
response). Compute equivalent directly from cached statcast_<year>.parquet
files using the shadow-zone called-strike-rate methodology that
catcher_framing_pairings.py already uses, but split by year.

Output:
  data/research/xfp_cache/catcher_framing_2017_2025.csv
    catcher_mlbam, year, shadow_pitches, shadow_called_strikes,
    framing_rate, framing_rate_lg, framing_runs_per_100, framing_runs

Framing runs approximation:
  Each extra called strike (over league mean shadow CS rate) saves the
  pitcher ~0.13 runs (industry-standard runs/CS value). So:
    framing_runs = (shadow_called_strikes - shadow_pitches * lg_rate) * 0.13
    framing_runs_per_100 = (framing_rate - lg_rate) * 100 * 0.13

  This is a level approximation — Savant's own framing_runs uses a per-
  zone count weighted by called-strike probability, which is roughly
  monotone with this simpler shadow-rate. For the validation question
  (does primary-catcher framing add predictive lift to rp3?), the
  relative ordering is what matters, not the absolute units.

Also writes:
  data/research/xfp_cache/sp_primary_catcher_2018_2025.csv
    pitcher, year, primary_catcher, primary_catcher_pitches, total_pitches,
    primary_catcher_share

  Primary catcher = modal fielder_2 across the pitcher's pitches that
  year. SP filter not applied here — we keep all pitchers and let the
  downstream rolling join filter via the existing rp3 substrate.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

YEARS_FRAMING = list(range(2017, 2026))  # 2017 needed as prior for 2018 rows
YEARS_PRIMARY = list(range(2017, 2026))

# Runs per called-strike-above-mean (industry-standard 0.13 runs / CS).
RUNS_PER_CS = 0.13


def _load_taken_pitches(year: int) -> pd.DataFrame:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(
        path,
        columns=['pitcher', 'fielder_2', 'description',
                 'plate_x', 'plate_z', 'sz_top', 'sz_bot'],
    )
    df = df[df['description'].isin({'called_strike', 'ball', 'blocked_ball'})]
    return df.dropna(subset=['fielder_2', 'plate_x', 'plate_z', 'sz_top', 'sz_bot'])


def _shadow_mask(df: pd.DataFrame) -> pd.Series:
    px = df['plate_x'].abs()
    pz = df['plate_z']
    sz_top = df['sz_top']
    sz_bot = df['sz_bot']
    shadow_x = (px > 0.83) & (px <= 1.0) & (pz <= sz_top + 0.2) & (pz >= sz_bot - 0.2)
    shadow_z_top = (px <= 1.0) & (pz > sz_top) & (pz <= sz_top + 0.2)
    shadow_z_bot = (px <= 1.0) & (pz < sz_bot) & (pz >= sz_bot - 0.2)
    return shadow_x | shadow_z_top | shadow_z_bot


def build_catcher_framing() -> pd.DataFrame:
    rows = []
    for year in YEARS_FRAMING:
        df = _load_taken_pitches(year)
        if df.empty:
            print(f'  {year}: no data, skipping')
            continue
        df = df.copy()
        df['shadow'] = _shadow_mask(df)
        df['called_strike'] = (df['description'] == 'called_strike').astype(int)
        sh = df[df['shadow']]
        agg = sh.groupby('fielder_2', as_index=False).agg(
            shadow_pitches=('called_strike', 'count'),
            shadow_called_strikes=('called_strike', 'sum'),
        )
        agg = agg[agg['shadow_pitches'] >= 100].copy()
        if agg.empty:
            print(f'  {year}: no catchers cleared 100 shadow pitches')
            continue
        lg_rate = float(agg['shadow_called_strikes'].sum() / agg['shadow_pitches'].sum())
        agg['year'] = year
        agg['framing_rate'] = agg['shadow_called_strikes'] / agg['shadow_pitches']
        agg['framing_rate_lg'] = lg_rate
        agg['framing_runs_per_100'] = (agg['framing_rate'] - lg_rate) * 100 * RUNS_PER_CS
        agg['framing_runs'] = (agg['shadow_called_strikes']
                               - agg['shadow_pitches'] * lg_rate) * RUNS_PER_CS
        rows.append(agg)
        print(f'  {year}: {len(agg)} catchers, lg shadow CS rate={lg_rate:.3f}')
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out = out.rename(columns={'fielder_2': 'catcher_mlbam'})
    out['catcher_mlbam'] = out['catcher_mlbam'].astype(int)
    return out[['catcher_mlbam', 'year', 'shadow_pitches', 'shadow_called_strikes',
                'framing_rate', 'framing_rate_lg', 'framing_runs_per_100',
                'framing_runs']]


def build_primary_catcher() -> pd.DataFrame:
    rows = []
    for year in YEARS_PRIMARY:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['pitcher', 'fielder_2'])
        df = df.dropna(subset=['pitcher', 'fielder_2'])
        if df.empty:
            continue
        df = df.astype({'pitcher': int, 'fielder_2': int})
        grp = df.groupby(['pitcher', 'fielder_2'], as_index=False).size()
        total = df.groupby('pitcher', as_index=False).size().rename(columns={'size': 'total_pitches'})
        # modal catcher per pitcher
        grp = grp.sort_values(['pitcher', 'size'], ascending=[True, False])
        modal = grp.drop_duplicates('pitcher', keep='first').rename(
            columns={'fielder_2': 'primary_catcher', 'size': 'primary_catcher_pitches'})
        modal = modal.merge(total, on='pitcher')
        modal['primary_catcher_share'] = modal['primary_catcher_pitches'] / modal['total_pitches']
        modal['year'] = year
        rows.append(modal)
        print(f'  {year}: {len(modal)} pitchers with primary catcher')
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    return out[['pitcher', 'year', 'primary_catcher', 'primary_catcher_pitches',
                'total_pitches', 'primary_catcher_share']]


def main():
    print('=== build_catcher_framing ===')
    print('\n[1/2] Per-(catcher, year) framing from statcast parquets')
    fr = build_catcher_framing()
    if fr.empty:
        print('FAILED — no framing rows produced.')
        return
    out_fr = CACHE / 'catcher_framing_2017_2025.csv'
    fr.to_csv(out_fr, index=False)
    print(f'  wrote {out_fr} ({len(fr)} rows, {fr["year"].nunique()} years)')

    print('\n[2/2] Per-(pitcher, year) primary catcher from statcast parquets')
    pc = build_primary_catcher()
    if pc.empty:
        print('FAILED — no primary catcher rows produced.')
        return
    out_pc = CACHE / 'sp_primary_catcher_2018_2025.csv'
    pc.to_csv(out_pc, index=False)
    print(f'  wrote {out_pc} ({len(pc)} rows, {pc["year"].nunique()} years)')

    # Eye-test: top / bottom framers 2025
    print('\n[eye-test] top 5 framers 2025 (≥1500 shadow pitches):')
    top = fr[(fr['year'] == 2025) & (fr['shadow_pitches'] >= 1500)] \
        .sort_values('framing_runs_per_100', ascending=False).head(5)
    print(top.to_string(index=False))
    print('\n[eye-test] bottom 5 framers 2025 (≥1500 shadow pitches):')
    bot = fr[(fr['year'] == 2025) & (fr['shadow_pitches'] >= 1500)] \
        .sort_values('framing_runs_per_100', ascending=True).head(5)
    print(bot.to_string(index=False))


if __name__ == '__main__':
    main()
