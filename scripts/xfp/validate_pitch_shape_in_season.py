"""validate_pitch_shape_in_season.py — proper in-season → ros training & test.

The deep pitch-shape model was previously TRAINED on full-year-to-full-year
data. That makes it suitable for offseason / draft work but not directly
calibrated for the rest-of-season prediction we actually need right now.

This script rebuilds the panel for the IN-SEASON USE CASE:
  Features: pre-cutoff (first ~6 weeks) pitch shape vs prior-years career
            baseline (deltas at the cumulative-to-date level)
  Target: rest-of-season FP/start (from rolling_pitchers substrate)

Train coefficients on THIS panel. Run LOYO. Decide whether to promote
the pitch-shape deltas as added features to rp3 v3.

Promotion gate (per multi-testing protocol):
  - LOYO test r gain ≥ +0.005 over baseline (current rp3-style features)
  - Gain consistent across ≥ 5 of 7 years
  - Production framing actually positive
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

from scripts.xfp.validate_pitch_shape_deep import (
    load_year, compute_pitcher_features)

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_YEARS_FOR_BASELINE = 3  # use up to 3 prior years for career baseline

# Same 6-feature subset we want to promote
PROPOSED_FEATS = ['d_velo_all', 'd_ext_all', 'd_ivb_all',
                   'd_release_x_std', 'd_whiff_per_swing', 'd_spin_fb']

# Baseline features the in-season rp3 v2 already uses (we want to BEAT this)
# Note: we'll use cumulative-to-date fp_per_start as the simplest baseline
# proxy for "what rp3 already knows".


def build_in_season_panel():
    """Build panel: pre-cutoff pitch shape (vs career baseline) → ros FP/start."""
    rolling = pd.read_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])

    # For each year, choose a cutoff around 6 weeks into the season (early-to-mid May)
    target_cutoffs = {}
    for y in YEARS:
        sub = rolling[rolling['year'] == y]
        if sub.empty: continue
        target_dt = pd.Timestamp(f'{y}-05-08')
        sub_dt = sub['cutoff_date']
        closest = sub_dt.iloc[(sub_dt - target_dt).abs().argmin()]
        target_cutoffs[y] = closest

    # Precompute per-year career baseline (3 prior years' pitch shape, IP-weighted)
    print('Loading prior-year statcast for baseline...')
    year_shape = {}
    for y in YEARS:
        df = load_year(y)
        feats = compute_pitcher_features(df)
        feats['year'] = y
        year_shape[y] = feats

    rows = []
    for y in YEARS:
        if y not in target_cutoffs: continue
        cd = target_cutoffs[y]
        print(f'  {y}: cutoff {cd.date()}, building pre-cutoff features...')

        # Load this year's statcast restricted to <= cutoff
        path = CACHE / f'statcast_{y}.parquet'
        all_cols = pd.read_parquet(path).columns.tolist()
        wanted = ['pitcher', 'game_date', 'pitch_type', 'description', 'events',
                  'release_speed', 'release_extension', 'release_spin_rate',
                  'release_pos_x', 'release_pos_z', 'plate_x', 'plate_z',
                  'pfx_x', 'pfx_z']
        wanted = [c for c in wanted if c in all_cols]
        df = pd.read_parquet(path, columns=wanted)
        df['game_date'] = pd.to_datetime(df['game_date'])
        pre = df[df['game_date'] <= cd]
        if pre.empty: continue
        pre_feats = compute_pitcher_features(pre)

        # Career baseline = weighted avg of (y-1, y-2, y-3) shape, by n_pitches
        baseline_rows = []
        baseline_weights = []
        for off in [1, 2, PRIOR_YEARS_FOR_BASELINE]:
            py = y - off
            if py in year_shape and not year_shape[py].empty:
                baseline_rows.append(year_shape[py])

        # rolling-pitchers ros target for this cutoff
        rfilt = rolling[(rolling['year'] == y) & (rolling['cutoff_date'] == cd)]
        if rfilt.empty: continue
        ros_lookup = dict(zip(rfilt['pitcher'], zip(rfilt['ros_fp_per_start'],
                                                      rfilt['fp_per_start_to'])))

        for _, cur in pre_feats.iterrows():
            pid = int(cur['pitcher'])
            if pid not in ros_lookup: continue
            ros_fp, base_fp = ros_lookup[pid]
            if pd.isna(ros_fp) or pd.isna(base_fp): continue

            # Compute career baseline for this pitcher
            base_vals = {}
            weights = []
            for prior_df in baseline_rows:
                m = prior_df[prior_df['pitcher'] == pid]
                if m.empty: continue
                w = m['n_pitches'].iloc[0]
                if pd.isna(w) or w < 200: continue
                for col in ['velo_all', 'ext_all', 'ivb_all', 'release_x_std',
                            'whiff_per_swing', 'spin_fb']:
                    if col in m.columns and pd.notna(m[col].iloc[0]):
                        base_vals.setdefault(col, [])
                        base_vals[col].append((float(m[col].iloc[0]), float(w)))
            if not base_vals or sum(len(v) for v in base_vals.values()) < 6: continue

            row = {'pitcher': pid, 'year': y,
                   'ros_fp_per_start': ros_fp,
                   'prior_fp_per_start': base_fp}
            for col in ['velo_all', 'ext_all', 'ivb_all', 'release_x_std',
                        'whiff_per_swing', 'spin_fb']:
                if col not in base_vals or not base_vals[col]: continue
                base = sum(v*w for v, w in base_vals[col]) / sum(w for _, w in base_vals[col])
                cur_v = cur.get(col)
                if pd.isna(cur_v): continue
                row[f'd_{col}'] = cur_v - base
            rows.append(row)

    panel = pd.DataFrame(rows)
    return panel


def fit_eval(panel, features, train_years, test_years,
              target='ros_fp_per_start'):
    features = [f for f in features if f in panel.columns]
    sub = panel.dropna(subset=features + [target, 'prior_fp_per_start'])
    train = sub[sub['year'].isin(train_years)]
    test = sub[sub['year'].isin(test_years)]
    if len(train) < 50 or len(test) < 30:
        return None, None, len(test)
    X = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values]
                          + [train[c].values for c in features])
    y = train[target].values
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    Xt = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values]
                            + [test[c].values for c in features])
    pred = Xt @ coefs
    r = float(np.corrcoef(pred, test[target].values)[0, 1])
    return r, coefs, len(test)


def main():
    print('Building proper in-season → ros panel...')
    panel = build_in_season_panel()
    print(f'\nPanel: {len(panel)} pitcher-cutoff rows')
    panel.to_csv(RES / 'pitch_shape_in_season_panel.csv', index=False)

    print('\n' + '='*78)
    print('  LOYO TEST — IN-SEASON FRAMING (the production-relevant setup)')
    print('='*78)
    print(f'\n  Each row: hold year out, train on others, test ros_fp prediction')
    print(f'  {"YEAR":<6s} {"N_test":>7s} {"BASE r":>8s} {"DEEP r":>8s} {"GAIN":>8s}')
    gains = []
    for year in YEARS:
        train = [y for y in YEARS if y != year]
        test = [year]
        r_base, _, n = fit_eval(panel, [], train, test)
        r_deep, _, _ = fit_eval(panel, PROPOSED_FEATS, train, test)
        if r_base is None or r_deep is None: continue
        gain = r_deep - r_base
        gains.append(gain)
        print(f'  {year:<6d} {n:>7d} {r_base:>8.4f} {r_deep:>8.4f} {gain:>+8.4f}')

    n_pos = sum(1 for g in gains if g > 0)
    print(f'\n  Mean DEEP gain (LOYO, in-season framing): {np.mean(gains):+.4f}')
    print(f'  DEEP beat baseline in {n_pos}/{len(gains)} years')
    print(f'  Sign-consistency required: 5/7 → {"PASS" if n_pos >= 5 else "FAIL"}')
    print(f'  Promote bar +0.005 → {"PASS" if np.mean(gains) >= 0.005 else "FAIL"}')

    # Train on all years (production-ready coefficients)
    print('\n  Production coefficients (trained on all 2018-2025):')
    r_full, coefs, _ = fit_eval(panel, PROPOSED_FEATS, YEARS, YEARS)
    if coefs is not None:
        names = ['α', 'prior_fp'] + PROPOSED_FEATS
        for n, c in zip(names, coefs):
            print(f'    {n:<30s} {c:+.5f}')


if __name__ == '__main__':
    main()
