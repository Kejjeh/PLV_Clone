"""validate_pitch_shape_impact.py — empirical FP/start impact of pitch-shape changes.

For each historical pitcher-year row 2018-2025:
  1. Compute career baseline pitch-shape (prior 2-3 years, IP-weighted):
     - avg_velo (overall)
     - avg_velo_4seam, avg_velo_breaking, avg_velo_offspeed (if data available)
     - avg_ext, avg_iVB
  2. Compute current year T's pitch-shape (same metrics)
  3. Compute deltas
  4. Compute current year T's FP/start
  5. Fit OLS: FP/start_T = α + β_career * career_fp + β_velo * delta_velo
     + β_ext * delta_ext + β_iVB * delta_iVB

Cross-year validation: train 2018-2023, test 2024-2025 holdout.

Apply coefficients to current 2026 pitchers (Sheehan, Strider, Rodón, etc.)
to get DOLLAR-VALUE FP/start adjustments based on pitch-shape decline.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
FB_TYPES = {'FF', 'SI', 'FC', 'FT', 'FA'}
BR_TYPES = {'SL', 'CU', 'KC', 'ST', 'SV', 'CS'}
OFF_TYPES = {'CH', 'FS', 'SC'}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def load_pitcher_shape_year(year):
    """For each pitcher in year Y, compute pitch-shape metrics from statcast."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists(): return pd.DataFrame()
    df = pd.read_parquet(path, columns=['pitcher', 'pitch_type', 'release_speed',
                                          'pfx_x', 'pfx_z', 'release_extension'])
    df = df[df['release_speed'].notna() & df['pitcher'].notna()]
    if df.empty: return pd.DataFrame()

    df['is_fb'] = df['pitch_type'].isin(FB_TYPES)
    df['is_br'] = df['pitch_type'].isin(BR_TYPES)
    df['is_off'] = df['pitch_type'].isin(OFF_TYPES)
    df['ivb_in'] = df['pfx_z'] * 12  # feet → inches
    df['hb_in'] = df['pfx_x'] * 12

    grp = df.groupby('pitcher').agg(
        n_pitches=('release_speed', 'size'),
        velo_all=('release_speed', 'mean'),
        ext_all=('release_extension', 'mean'),
        ivb_all=('ivb_in', 'mean'),
    )
    # Per-pitch-type weighted velo
    for label, mask_col in [('fb', 'is_fb'), ('br', 'is_br'), ('off', 'is_off')]:
        sub = df[df[mask_col]]
        if not sub.empty:
            sgrp = sub.groupby('pitcher').agg(
                n_pitches=('release_speed', 'size'),
                velo=('release_speed', 'mean'),
                ivb=('ivb_in', 'mean'),
                ext=('release_extension', 'mean'),
            ).rename(columns={'n_pitches': f'n_{label}', 'velo': f'velo_{label}',
                              'ivb': f'ivb_{label}', 'ext': f'ext_{label}'})
            grp = grp.join(sgrp, how='left')

    grp = grp.reset_index()
    grp['year'] = year
    return grp


def main():
    print('Loading statcast per year...')
    year_shapes = {}
    for y in YEARS:
        print(f'  {y}...')
        year_shapes[y] = load_pitcher_shape_year(y)

    # Combine
    all_shapes = pd.concat([df for df in year_shapes.values() if not df.empty], ignore_index=True)
    print(f'  combined shape data: {len(all_shapes)} pitcher-years')

    # Build career baseline: for each (pitcher, year T), avg prior 2-3 years
    # weighted by pitch count.
    rows = []
    sp_multi = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    rel_multi = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')
    fp_lookup = {}
    # SP fp_per_start
    for _, r in sp_multi[sp_multi['gs'] >= 5].iterrows():
        fp_lookup[(int(r['pitcher']), int(r['year']))] = ('SP', r['gs'], r.get('fp_per_start_actual', 0))

    shape_by_pid_year = {(int(r['pitcher']), int(r['year'])): r
                          for _, r in all_shapes.iterrows()}

    for (pid, year), (role, gs, fp_per_start) in fp_lookup.items():
        if role != 'SP' or gs < 10:
            continue
        if year not in YEARS: continue
        # Career baseline = prior 2-3 years
        baseline_shape = []
        for off in [1, 2, 3]:
            prior_year = year - off
            if prior_year in YEARS and (pid, prior_year) in shape_by_pid_year:
                baseline_shape.append(shape_by_pid_year[(pid, prior_year)])
        if not baseline_shape: continue
        # Need at least one prior year with shape data
        cur_shape = shape_by_pid_year.get((pid, year))
        if cur_shape is None: continue
        # IP-weighted baseline (proxy with n_pitches)
        weights = [s['n_pitches'] for s in baseline_shape]
        if sum(weights) < 500: continue  # need at least 500 prior-career pitches

        def w_avg(key):
            vals = [s.get(key) for s in baseline_shape]
            valid = [(v, w) for v, w in zip(vals, weights) if pd.notna(v)]
            if not valid: return np.nan
            return sum(v * w for v, w in valid) / sum(w for _, w in valid)

        baseline = {k: w_avg(k) for k in ['velo_all', 'ext_all', 'ivb_all',
                                            'velo_fb', 'velo_br', 'velo_off',
                                            'ivb_fb', 'ext_fb']}
        cur = cur_shape

        # Prior year FP/start (use closest prior with ≥5 GS)
        prior_fp = None
        for off in [1, 2, 3]:
            prior_year = year - off
            if (pid, prior_year) in fp_lookup:
                _, prior_gs, prior_fp_val = fp_lookup[(pid, prior_year)]
                if prior_gs >= 5:
                    prior_fp = prior_fp_val
                    break

        if prior_fp is None: continue

        row = {
            'pitcher': pid, 'year': year, 'gs': gs,
            'fp_per_start': fp_per_start,
            'prior_fp_per_start': prior_fp,
            'delta_velo_all': (cur['velo_all'] - baseline['velo_all']) if pd.notna(baseline['velo_all']) else np.nan,
            'delta_ext_all': (cur['ext_all'] - baseline['ext_all']) if pd.notna(baseline['ext_all']) else np.nan,
            'delta_ivb_all': (cur['ivb_all'] - baseline['ivb_all']) if pd.notna(baseline['ivb_all']) else np.nan,
            'delta_velo_fb': (cur.get('velo_fb', np.nan) - baseline['velo_fb']) if pd.notna(baseline['velo_fb']) else np.nan,
            'delta_ivb_fb': (cur.get('ivb_fb', np.nan) - baseline['ivb_fb']) if pd.notna(baseline['ivb_fb']) else np.nan,
            'delta_ext_fb': (cur.get('ext_fb', np.nan) - baseline['ext_fb']) if pd.notna(baseline['ext_fb']) else np.nan,
        }
        rows.append(row)

    panel = pd.DataFrame(rows)
    print(f'\nPanel size: {len(panel)} SP-years with both shape + prior FP data')

    # Fit OLS, holdout 2024-2025
    TRAIN = [2018, 2019, 2021, 2022, 2023]
    TEST = [2024, 2025]

    def fit_eval(feature_cols, label):
        sub = panel.dropna(subset=feature_cols + ['fp_per_start', 'prior_fp_per_start'])
        if len(sub) < 100:
            print(f'  {label}: insufficient sample {len(sub)}')
            return None
        train = sub[sub['year'].isin(TRAIN)]
        test = sub[sub['year'].isin(TEST)]
        X_train = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values]
                                     + [train[c].values for c in feature_cols])
        y_train = train['fp_per_start'].values
        coefs, *_ = np.linalg.lstsq(X_train, y_train, rcond=None)
        X_test = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values]
                                    + [test[c].values for c in feature_cols])
        pred = X_test @ coefs
        r = float(np.corrcoef(pred, test['fp_per_start'].values)[0, 1])
        print(f'\n=== {label} ===')
        print(f'  N train: {len(train)}, N test: {len(test)}')
        print(f'  test r: {r:.4f}')
        print(f'  Coefficients:')
        names = ['intercept', 'prior_fp_per_start'] + feature_cols
        for n, c in zip(names, coefs):
            print(f'    {n:<28s} {c:+.4f}')
        return dict(zip(names, coefs)), r

    # Baseline-only (prior_fp only)
    print('\n--- Baseline model: FP/start_T ~ prior_FP/start ---')
    sub = panel.dropna(subset=['fp_per_start', 'prior_fp_per_start'])
    train = sub[sub['year'].isin(TRAIN)]
    test = sub[sub['year'].isin(TEST)]
    X_train = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values])
    y_train = train['fp_per_start'].values
    coefs_base, *_ = np.linalg.lstsq(X_train, y_train, rcond=None)
    X_test = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values])
    pred_base = X_test @ coefs_base
    r_base = float(np.corrcoef(pred_base, test['fp_per_start'].values)[0, 1])
    print(f'  N train: {len(train)}, N test: {len(test)}')
    print(f'  test r: {r_base:.4f}')

    # With overall velo
    fit_eval(['delta_velo_all'], 'BASELINE + delta_velo_all')
    fit_eval(['delta_velo_all', 'delta_ext_all'], 'BASELINE + velo + ext')
    fit_eval(['delta_velo_all', 'delta_ext_all', 'delta_ivb_all'], 'BASELINE + velo + ext + iVB')
    res, r_fb = fit_eval(['delta_velo_fb', 'delta_ivb_fb', 'delta_ext_fb'], 'BASELINE + 4seam (velo + iVB + ext)')

    if res is None:
        return

    # Apply to target pitchers — Sheehan, Strider, Rodón, Bradish, Eovaldi
    print('\n' + '='*70)
    print('  APPLIED FP/start IMPACT to 2026 pitchers (4-seam shape model)')
    print('='*70)

    rp3 = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rp3['nk'] = rp3['player_name'].map(_norm)

    # 2026 shape from cache statcast vs 2023-2025 career
    cur_2026 = load_pitcher_shape_year(2026)
    cur_2026_by_pid = {int(r['pitcher']): r for _, r in cur_2026.iterrows()}

    # Career 2023-2025 IP-weighted shape per pitcher
    career_combined = pd.concat([year_shapes[y] for y in [2023, 2024, 2025] if not year_shapes[y].empty])
    career_combined_grp = career_combined.groupby('pitcher').agg(
        n_total=('n_pitches', 'sum'),
        velo_fb=('velo_fb', lambda x: x.mean()),
        ivb_fb=('ivb_fb', lambda x: x.mean()),
        ext_fb=('ext_fb', lambda x: x.mean()),
    ).reset_index()
    career_by_pid = {int(r['pitcher']): r for _, r in career_combined_grp.iterrows()}

    targets = ['Emmet Sheehan', 'Spencer Strider', 'Carlos Rodon', 'Kyle Bradish',
               'Eury Perez', 'Tyler Glasnow', 'Sonny Gray', 'Framber Valdez',
               'Max Fried', 'Robbie Ray']

    # Need pitcher_id lookup
    sp_mult = sp_multi[['pitcher', 'player_name']].drop_duplicates('player_name')
    sp_mult['nk'] = sp_mult['player_name'].map(_norm)
    id_lookup = dict(zip(sp_mult['nk'], sp_mult['pitcher']))

    print(f'\n{"PITCHER":<22s} {"d_velo_FB":>10s} {"d_iVB_FB":>10s} {"d_ext_FB":>10s} '
          f'{"FP/GS hit":>10s} {"RoS hit":>9s}')

    b_velo = res.get('delta_velo_fb', 0)
    b_ivb = res.get('delta_ivb_fb', 0)
    b_ext = res.get('delta_ext_fb', 0)
    SP_REMAINING_STARTS = 24

    for name in targets:
        nk = _norm(name)
        pid = id_lookup.get(nk)
        if pid is None:
            print(f'  {name:<22s} no id')
            continue
        cur = cur_2026_by_pid.get(int(pid))
        car = career_by_pid.get(int(pid))
        if cur is None or car is None:
            print(f'  {name:<22s} no shape data')
            continue
        d_velo = float(cur.get('velo_fb', np.nan)) - float(car.get('velo_fb', np.nan))
        d_ivb = float(cur.get('ivb_fb', np.nan)) - float(car.get('ivb_fb', np.nan))
        d_ext = float(cur.get('ext_fb', np.nan)) - float(car.get('ext_fb', np.nan))
        if pd.isna(d_velo) or pd.isna(d_ivb) or pd.isna(d_ext):
            print(f'  {name:<22s} missing shape components')
            continue
        fp_hit = b_velo * d_velo + b_ivb * d_ivb + b_ext * d_ext
        ros_hit = fp_hit * SP_REMAINING_STARTS
        print(f'  {name:<22s} {d_velo:>+10.2f} {d_ivb:>+10.2f} {d_ext:>+10.2f} '
              f'{fp_hit:>+10.3f} {ros_hit:>+9.1f}')

    panel.to_csv(RES / 'pitch_shape_impact_panel.csv', index=False)


if __name__ == '__main__':
    main()
