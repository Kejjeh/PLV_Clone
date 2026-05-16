"""validate_pitch_shape_convergence.py — at what cutoff does each metric matter?

User's question: 6 weeks might be too little. When do pitch-shape metrics
actually become reliable predictors of rest-of-season FP/start?

For cutoffs at weeks 4, 6, 8, 10, 12, 14, 16, 18:
  1. Compute pre-cutoff pitch shape per pitcher (vs 2023-2025 baseline)
  2. Target: rest-of-season FP/start from rolling_pitchers
  3. Run train 2018-2023 / test 2024-2025 OLS
  4. Report r gain over baseline for each feature subset:
       L1 only       (velo/ext/iVB — the 3 features whose sign held)
       + whiff_per_swing
       + whiff + release_x_std + spin_fb (the full deep set)

Also runs L1-only LOYO at week-6 cutoff (the user's first task).
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
TRAIN = [2018, 2019, 2021, 2022, 2023]
TEST = [2024, 2025]

WEEKS_TO_TEST = [4, 6, 8, 10, 12, 14, 16, 18]

L1_FEATS = ['d_velo_all', 'd_ext_all', 'd_ivb_all']
L1_WHIFF = L1_FEATS + ['d_whiff_per_swing']
L1_DEEP = L1_FEATS + ['d_whiff_per_swing', 'd_release_x_std', 'd_spin_fb']


def fit_eval(panel, features, train_years, test_years):
    features = [f for f in features if f in panel.columns]
    sub = panel.dropna(subset=features + ['ros_fp_per_start', 'prior_fp_per_start'])
    train = sub[sub['year'].isin(train_years)]
    test = sub[sub['year'].isin(test_years)]
    if len(train) < 50 or len(test) < 30:
        return None, None, len(test)
    X = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values]
                          + [train[c].values for c in features])
    y = train['ros_fp_per_start'].values
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    Xt = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values]
                            + [test[c].values for c in features])
    pred = Xt @ coefs
    r = float(np.corrcoef(pred, test['ros_fp_per_start'].values)[0, 1])
    return r, coefs, len(test)


def build_panel_at_cutoff(weeks_into_season):
    """Build the in-season → ros panel using a cutoff at `weeks_into_season`."""
    rolling = pd.read_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])

    # Compute career baseline shape (2023-2025 IP-weighted) — same for all cutoffs
    print(f'    loading career baselines...')
    year_shape = {}
    for y in YEARS:
        df = load_year(y)
        feats = compute_pitcher_features(df)
        feats['year'] = y
        year_shape[y] = feats

    rows = []
    for y in YEARS:
        sub = rolling[rolling['year'] == y]
        if sub.empty: continue
        season_start = pd.Timestamp(f'{y}-03-26')  # approx
        target_cd = season_start + pd.Timedelta(weeks=weeks_into_season)
        # pick closest cutoff in rolling
        rcand = sub.copy()
        rcand['gap'] = (rcand['cutoff_date'] - target_cd).abs()
        rcand = rcand.sort_values('gap')
        cd = rcand.iloc[0]['cutoff_date']

        # Load year's statcast restricted to <= cutoff
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

        rfilt = rolling[(rolling['year'] == y) & (rolling['cutoff_date'] == cd)]
        if rfilt.empty: continue
        ros_lookup = dict(zip(rfilt['pitcher'],
                                zip(rfilt['ros_fp_per_start'], rfilt['fp_per_start_to'])))

        # Career baseline rows
        baseline_rows = []
        for off in [1, 2, 3]:
            py = y - off
            if py in year_shape and not year_shape[py].empty:
                baseline_rows.append(year_shape[py])
        if not baseline_rows: continue

        for _, cur in pre_feats.iterrows():
            pid = int(cur['pitcher'])
            if pid not in ros_lookup: continue
            ros_fp, base_fp = ros_lookup[pid]
            if pd.isna(ros_fp) or pd.isna(base_fp): continue

            # baseline per col
            base_vals = {}
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
            if not base_vals: continue

            row = {'pitcher': pid, 'year': y,
                   'ros_fp_per_start': ros_fp, 'prior_fp_per_start': base_fp}
            for col in ['velo_all', 'ext_all', 'ivb_all', 'release_x_std',
                        'whiff_per_swing', 'spin_fb']:
                if col not in base_vals: continue
                base = sum(v*w for v, w in base_vals[col]) / sum(w for _, w in base_vals[col])
                cv = cur.get(col)
                if pd.isna(cv): continue
                row[f'd_{col}'] = cv - base
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    # ============== Convergence curve ==============
    print('='*78)
    print('  CONVERGENCE CURVE — when does each feature subset start working?')
    print('='*78)

    print(f'\n  Train 2018-2023 / Test 2024-2025  (r gain over baseline)')
    print(f'  {"WEEKS":<6s} {"N_test":>7s} {"BASE r":>8s} {"L1 r":>8s} {"L1+W r":>8s} {"DEEP r":>8s} '
          f'{"L1 gain":>8s} {"+W gain":>8s} {"DEEP gain":>10s}')
    summary = []
    for wks in WEEKS_TO_TEST:
        print(f'\n  --- {wks} weeks ---')
        panel = build_panel_at_cutoff(wks)
        if len(panel) < 50:
            print(f'    {wks} wks: panel too small ({len(panel)})'); continue

        r_base, _, n = fit_eval(panel, [], TRAIN, TEST)
        r_l1, _, _ = fit_eval(panel, L1_FEATS, TRAIN, TEST)
        r_w, _, _ = fit_eval(panel, L1_WHIFF, TRAIN, TEST)
        r_d, _, _ = fit_eval(panel, L1_DEEP, TRAIN, TEST)
        if r_base is None: continue
        gl1 = r_l1 - r_base if r_l1 else 0
        gw = r_w - r_base if r_w else 0
        gd = r_d - r_base if r_d else 0
        print(f'  {wks:<6d} {n:>7d} {r_base:>8.4f} {r_l1:>8.4f} {r_w:>8.4f} {r_d:>8.4f} '
              f'{gl1:>+8.4f} {gw:>+8.4f} {gd:>+10.4f}')
        summary.append({'weeks': wks, 'n_test': n, 'r_base': r_base,
                         'r_l1': r_l1, 'r_w': r_w, 'r_d': r_d,
                         'gain_l1': gl1, 'gain_w': gw, 'gain_d': gd})

    sdf = pd.DataFrame(summary)
    sdf.to_csv(RES / 'pitch_shape_convergence.csv', index=False)
    print(f'\n  wrote {RES / "pitch_shape_convergence.csv"}')

    # ============== L1-only LOYO at week 6 ==============
    print('\n' + '='*78)
    print('  L1-ONLY (velo + ext + iVB) LOYO at WEEK 6 — does L1 pass alone?')
    print('='*78)
    panel6 = build_panel_at_cutoff(6)
    gains_l1 = []
    print(f'\n  {"YEAR":<6s} {"N":>5s} {"BASE r":>8s} {"L1 r":>8s} {"GAIN":>8s}')
    for year in YEARS:
        train = [y for y in YEARS if y != year]
        test = [year]
        r_b, _, n = fit_eval(panel6, [], train, test)
        r_l, _, _ = fit_eval(panel6, L1_FEATS, train, test)
        if r_b is None or r_l is None: continue
        gain = r_l - r_b
        gains_l1.append(gain)
        print(f'  {year:<6d} {n:>5d} {r_b:>8.4f} {r_l:>8.4f} {gain:>+8.4f}')
    if gains_l1:
        n_pos = sum(1 for g in gains_l1 if g > 0)
        print(f'\n  Mean L1 gain (LOYO at week 6): {np.mean(gains_l1):+.4f}')
        print(f'  L1 beat baseline in {n_pos}/{len(gains_l1)} years')
        passes = (n_pos >= 5) and (np.mean(gains_l1) >= 0.005)
        print(f'  Promote-bar check: {"PASS" if passes else "FAIL"}')


if __name__ == '__main__':
    main()
