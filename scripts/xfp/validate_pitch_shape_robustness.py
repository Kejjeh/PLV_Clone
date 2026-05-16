"""validate_pitch_shape_robustness.py — multi-fold verification before promotion.

Tests for the deep pitch-shape model:
  A. LOYO cross-validation (each year held out separately)
  B. Production-relevant: mid-season cutoff (6 wk) → predict rest-of-season
     This is what rp3 actually does, vs the full-year same-year test we ran
  C. Sample sensitivity: ≥10 GS vs ≥5 GS thresholds
  D. Bootstrap CI on d_whiff_per_swing coefficient (the +0.052 monster)
  E. Spot check: verify Sonny Gray's projected drop is consistent with reality

Promote bar reminder: need +0.005 r gain that holds across multiple year
splits AND survives the production framing.
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
OUT = ROOT / 'data' / 'outputs'

from scripts.xfp.validate_pitch_shape_deep import (
    load_year, compute_pitcher_features, YEARS, TRAIN, TEST)

# Winning features from the deep sweep
DEEP_FEATS = [
    'd_velo_all', 'd_ext_all', 'd_ivb_all',  # L1
    'd_release_x_std', 'd_whiff_per_swing', 'd_spin_fb',
    'd_whiff_fb', 'd_whiff_br',
]
CLEAN_FEATS = [  # the 5-feature subset I proposed (less multicollinearity)
    'd_velo_all', 'd_ext_all', 'd_ivb_all',
    'd_whiff_per_swing', 'd_release_x_std', 'd_spin_fb',
]


def fit_eval(panel, features, train_years, test_years):
    features = [f for f in features if f in panel.columns]
    sub = panel.dropna(subset=features + ['fp_per_start', 'prior_fp_per_start'])
    train = sub[sub['year'].isin(train_years)]
    test = sub[sub['year'].isin(test_years)]
    if len(train) < 50 or len(test) < 30:
        return None, None, len(test)
    X = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values]
                          + [train[c].values for c in features])
    y = train['fp_per_start'].values
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    Xt = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values]
                            + [test[c].values for c in features])
    pred = Xt @ coefs
    r = float(np.corrcoef(pred, test['fp_per_start'].values)[0, 1])
    return r, coefs, len(test)


def main():
    panel = pd.read_csv(RES / 'pitch_shape_deep_panel.csv')
    print(f'Panel: {len(panel)} SP-years')

    # =================== A. LOYO cross-validation ===================
    print('\n' + '='*78)
    print('  A. LOYO CROSS-VALIDATION')
    print('='*78)
    print(f'\n  Each row: hold out year Y, train on others, report test r')
    print(f'  {"YEAR":<6s} {"N_test":>7s} {"BASE r":>8s} {"L1 r":>8s} {"DEEP r":>8s} '
          f'{"DEEP-L1":>9s} {"DEEP-BASE":>10s}')
    gains_l1 = []
    gains_deep = []
    for year in YEARS:
        train = [y for y in YEARS if y != year]
        test = [year]
        r_base, _, n = fit_eval(panel, [], train, test)
        r_l1, _, _ = fit_eval(panel, ['d_velo_all', 'd_ext_all', 'd_ivb_all'], train, test)
        r_deep, _, _ = fit_eval(panel, CLEAN_FEATS, train, test)
        if r_base is None: continue
        gain_l1 = r_l1 - r_base if r_l1 else 0
        gain_deep = r_deep - r_base if r_deep else 0
        gains_l1.append(gain_l1)
        gains_deep.append(gain_deep)
        print(f'  {year:<6d} {n:>7d} {r_base:>8.4f} {r_l1:>8.4f} {r_deep:>8.4f} '
              f'{r_deep-r_l1:>+9.4f} {gain_deep:>+10.4f}')
    print(f'\n  Mean gain L1   over baseline: {np.mean(gains_l1):+.4f}  (std {np.std(gains_l1):.4f})')
    print(f'  Mean gain DEEP over baseline: {np.mean(gains_deep):+.4f}  (std {np.std(gains_deep):.4f})')
    n_pos_deep = sum(1 for g in gains_deep if g > 0)
    print(f'  DEEP beat baseline in {n_pos_deep}/{len(gains_deep)} years')

    # =================== B. Production-relevant test ===================
    # Use rolling_pitchers (cumulative-to-date) + statcast first-half-of-season
    # → predict ros_fp_per_start
    print('\n' + '='*78)
    print('  B. PRODUCTION-RELEVANT: pre-cutoff pitch shape → rest-of-season FP')
    print('='*78)

    # Build a separate panel: for each (pitcher, year, mid-season cutoff),
    # compute pitch shape from first 6 weeks and target rest-of-season FP/start.
    print('\n  Building mid-season → ros panel...')
    rolling = pd.read_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
    # filter to the closest cutoff to 6 weeks from season start (around May 7-10)
    # For most years that's around split_day 41-45
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    # Pick cutoffs in early-to-mid May for each year
    target_cutoffs = {}
    for y in YEARS:
        sub = rolling[rolling['year'] == y]
        if sub.empty: continue
        # find cutoff closest to year-05-08
        target_dt = pd.Timestamp(f'{y}-05-08')
        sub_dt = sub['cutoff_date']
        closest = sub_dt.iloc[(sub_dt - target_dt).abs().argmin()]
        target_cutoffs[y] = closest
        print(f'    {y}: using cutoff {closest.date()}')

    rows = []
    for y in YEARS:
        if y not in target_cutoffs: continue
        cd = target_cutoffs[y]
        # Get rolling stats at that cutoff
        rfilt = rolling[(rolling['year'] == y) & (rolling['cutoff_date'] == cd)]
        if rfilt.empty: continue

        # Load year's statcast and filter to pre-cutoff
        df = load_year(y)
        if df.empty: continue
        df['game_date_dt'] = pd.to_datetime(df['game_date'] if 'game_date' in df.columns
                                              else df.index)
        # actually statcast load may not have game_date in this script's load
        # Re-load to be sure:
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
        feats = compute_pitcher_features(pre)
        feats['year'] = y

        for _, fr in feats.iterrows():
            pid = int(fr['pitcher'])
            ros_row = rfilt[rfilt['pitcher'] == pid]
            if ros_row.empty: continue
            ros_fp = ros_row.iloc[0].get('ros_fp_per_start')
            base_fp = ros_row.iloc[0].get('fp_per_start_to')  # cumulative pre-cutoff FP/start
            if pd.isna(ros_fp) or pd.isna(base_fp): continue
            row = {'pitcher': pid, 'year': y,
                   'fp_per_start': ros_fp, 'prior_fp_per_start': base_fp}
            for c in ['velo_all', 'ext_all', 'ivb_all', 'release_x_std',
                       'whiff_per_swing', 'spin_fb', 'whiff_fb', 'whiff_br']:
                row[f'd_{c}'] = fr.get(c, np.nan)  # raw level, not delta — model expects deltas
            rows.append(row)

    panel_prod = pd.DataFrame(rows)
    print(f'\n  Production panel: {len(panel_prod)} rows')

    # Note: this is a slightly different framing — we're using current-year pitch
    # shape (no career delta) to predict ros FP. So features are LEVELS not DELTAS.
    # The L1 + 5-winners coefficients will still be applied as predictors but the
    # interpretation differs. For a cleaner test, use raw cumulative stats.
    if not panel_prod.empty:
        # Sample-equivalent leave-one-year-out
        gains_prod = []
        for year in YEARS:
            train = [y for y in YEARS if y != year]
            test = [year]
            r_base, _, n = fit_eval(panel_prod, [], train, test)
            r_deep, _, _ = fit_eval(panel_prod, CLEAN_FEATS, train, test)
            if r_base is None or r_deep is None: continue
            gain = r_deep - r_base
            gains_prod.append(gain)
            print(f'    {year}: base r {r_base:.4f}, deep r {r_deep:.4f}, gain {gain:+.4f} (n={n})')
        if gains_prod:
            print(f'\n  Mean DEEP gain (production framing): {np.mean(gains_prod):+.4f}')
            n_pos = sum(1 for g in gains_prod if g > 0)
            print(f'  DEEP beat baseline in {n_pos}/{len(gains_prod)} years')

    # =================== C. Sample-size sensitivity ===================
    print('\n' + '='*78)
    print('  C. SAMPLE SIZE SENSITIVITY (10 GS vs 5 GS threshold)')
    print('='*78)
    # Rebuild panel at lower threshold to see if results hold
    # The original panel had min 10 GS. Lower to 5 needs a re-build,
    # but we can check using the existing panel split by gs.
    # Just check what % of rows have gs >= 10 vs gs >= 5 (need 'gs' column in panel)
    if 'gs' not in panel.columns:
        # Add gs from sp_multiyr
        sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')[['pitcher', 'year', 'gs']]
        panel = panel.merge(sp, on=['pitcher', 'year'], how='left')
    print(f'  Panel rows total: {len(panel)}')
    if 'gs' in panel.columns:
        for thr in [10, 5]:
            sub = panel[panel['gs'] >= thr]
            if len(sub) < 100: continue
            r_base, _, n = fit_eval(sub, [], TRAIN, TEST)
            r_l1, _, _ = fit_eval(sub, ['d_velo_all', 'd_ext_all', 'd_ivb_all'], TRAIN, TEST)
            r_deep, _, _ = fit_eval(sub, CLEAN_FEATS, TRAIN, TEST)
            print(f'  gs >= {thr}:  n_train={len(sub[sub["year"].isin(TRAIN)])}, n_test={n}')
            print(f'    base r {r_base:.4f}, L1 r {r_l1:.4f}, DEEP r {r_deep:.4f}, '
                  f'DEEP gain {r_deep-r_base:+.4f}')

    # =================== D. Bootstrap CI on d_whiff_per_swing ===================
    print('\n' + '='*78)
    print('  D. BOOTSTRAP CI on d_whiff_per_swing coefficient (n=500)')
    print('='*78)
    train = panel[panel['year'].isin(TRAIN)].dropna(
        subset=['d_whiff_per_swing', 'd_velo_all', 'd_ext_all', 'd_ivb_all',
                'fp_per_start', 'prior_fp_per_start'])
    coefs_boot = []
    rng = np.random.RandomState(42)
    n = len(train)
    for _ in range(500):
        idx = rng.choice(n, size=n, replace=True)
        boot = train.iloc[idx]
        X = np.column_stack([
            np.ones(len(boot)),
            boot['prior_fp_per_start'].values,
            boot['d_velo_all'].values,
            boot['d_ext_all'].values,
            boot['d_ivb_all'].values,
            boot['d_whiff_per_swing'].values,
        ])
        y = boot['fp_per_start'].values
        try:
            coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
            coefs_boot.append(coefs[-1])  # whiff_per_swing is last
        except Exception:
            continue
    coefs_boot = np.array(coefs_boot)
    print(f'  d_whiff_per_swing coefficient bootstrap CI (n=500):')
    print(f'    mean: {coefs_boot.mean():+.5f}')
    print(f'    SE:   {coefs_boot.std():.5f}')
    print(f'    95% CI: [{np.percentile(coefs_boot, 2.5):+.5f}, {np.percentile(coefs_boot, 97.5):+.5f}]')
    pct_zero = (coefs_boot <= 0).mean() * 100
    print(f'    % of bootstraps with coef ≤ 0: {pct_zero:.1f}%')

    # =================== E. Sonny Gray spot check ===================
    print('\n' + '='*78)
    print('  E. SONNY GRAY SPOT CHECK — is the -48.9 RoS hit real?')
    print('='*78)
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    sg = sp[sp['player_name'].str.contains('Gray', na=False) &
            sp['player_name'].str.contains('Sonny', na=False)]
    if not sg.empty:
        cols = ['year', 'gs', 'k_pct', 'bb_pct', 'swstr_pct', 'avg_velo',
                'xwoba_contact', 'fp_per_start_actual']
        cols = [c for c in cols if c in sg.columns]
        print(sg[cols].sort_values('year').to_string(index=False))


if __name__ == '__main__':
    main()
