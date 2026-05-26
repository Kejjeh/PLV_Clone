"""
validate_rh3_breakout_signals.py
=================================
Research sweep: candidate features for rh3 second-half breakout detection.
Rule 9: every candidate tested vs FULL RH3_FEATS baseline.
Holdout: 2024, 2025. Training: [2018, 2019, 2021, 2022, 2023].

Candidates:
  A. xwoba_on_contact_to_sh   -- xwOBA-on-contact (already in rolling CSV)
  B. xwoba_slope_causal        -- causal within-season slope of xwoba_per_pa_to
  C. bat_speed_level_prior     -- SKIP (Step 2.5 pre-rejected 2026-05-24, <2 training years)
  D. sprint_speed_prior        -- prior-year sprint speed (T-1 joined to rolling)
  E. hard_hit_slope_causal     -- causal slope of hard_hit_pct_to
  F. discipline_index          -- bb_pct_to * (1 - k_pct_to), continuous version
                                 (note: bb_pct_x_xwoba variant was already REJECTED 2026-05-24)
"""
from __future__ import annotations
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV  = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV  = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
H2_LOCKED    = ROOT / 'data' / 'outputs' / 'seasonality_h2_locked.csv'
XWOBA_RESID  = ROOT / 'data' / 'outputs' / 'hitter_xwoba_residual.csv'
ROS_OPP_SP   = ROOT / 'data' / 'research' / 'xfp_cache' / 'ros_opp_sp_xwoba_per_hitter.csv'

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN  = 50
ROS_PA_MIN   = 100
TRAIN_YEARS  = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
HOLDOUT_YEARS = [2024, 2025]
# For convergence curves we report per-split_day results on TRAINING only
TRAIN_ONLY   = [y for y in TRAIN_YEARS if y not in HOLDOUT_YEARS]

RH3_FEATS = [
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    'prior_fp_per_pa', 'prior_pa_eff', 'pa_to', 'split_day',
    'lift_h2_aug150',
    'xwoba_residual_career',
    'career_stage',
    'ros_opp_sp_xwoba_weighted',
]

# --- helpers ------------------------------------------------------------------

SHRINK_SPEC_TO = {
    'k_pct_to':         ('pa_to',     60),
    'bb_pct_to':        ('pa_to',    120),
    'hr_per_pa_to':     ('pa_to',    170),
    'iso_to':           ('ab_to',    160),
    'sb_per_pa_to':     ('pa_to',    300),
    'xwoba_per_pa_to':  ('pa_to',    300),
    'contact_pct_to':   ('swing_to', 100),
    'whiff_pct_to':     ('swing_to', 100),
    'swstr_pct_to':     ('pitches_to', 300),
    'hard_hit_pct_to':  ('bip_to',    50),
    'barrel_pct_to':    ('bip_to',    50),
    'chase_pct_to':     ('out_zone_to', 400),
    'in_play_pct_to':   ('pitches_to', 300),
    'xwoba_on_contact_to': ('bip_to', 50),  # for candidate A
}
SHRINK_SPEC_LAST21 = {
    'k_pct_last21':         ('pa_last21',     30),
    'bb_pct_last21':        ('pa_last21',     60),
    'iso_last21':           ('ab_last21',     80),
    'xwoba_per_pa_last21':  ('pa_last21',    150),
    'contact_pct_last21':   ('swing_last21',  50),
    'whiff_pct_last21':     ('swing_last21',  50),
    'hard_hit_pct_last21':  ('bip_last21',    25),
    'barrel_pct_last21':    ('bip_last21',    25),
    'hr_per_pa_last21':     ('pa_last21',     85),
}
PRIOR_K_PA = 200
MARCEL_WEIGHTS = (5, 4, 3)


def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if 'ab_to' not in out.columns:
        out['ab_to'] = out['pa_to'] - out['bb_to'] - out.get('hbp_to', pd.Series(0, index=out.index)).fillna(0)
    if 'out_zone_to' not in out.columns:
        out['out_zone_to'] = (out['pitches_to'] - out.get('in_zone_to', 0)).clip(lower=0)
    if 'ab_last21' not in out.columns and 'pa_last21' in out.columns:
        out['ab_last21'] = out['pa_last21'] - out['bb_last21'].fillna(0) - out.get('hbp_last21', pd.Series(0, index=out.index)).fillna(0)
    return out


def apply_shrinkage(df: pd.DataFrame, train_years: list, spec: dict) -> pd.DataFrame:
    df = _ensure_derived_denoms(df)
    # Compute population means from training only
    train = df[df['year'].isin(train_years)]
    for rate, (denom_col, k) in spec.items():
        if rate not in df.columns or denom_col not in df.columns:
            continue
        # Pool population mean (volume-weighted)
        num = (train[rate] * train[denom_col]).sum(skipna=True)
        den = train[denom_col].sum(skipna=True)
        mu = num / den if den > 0 else df[rate].mean(skipna=True)
        # Shrinkage
        sh_col = rate + '_sh'
        denom_vals = df[denom_col].fillna(0)
        rate_vals = df[rate].fillna(mu)
        df[sh_col] = (denom_vals * rate_vals + k * mu) / (denom_vals + k)
    return df


def build_prior_table(multiyr: pd.DataFrame, years: list) -> pd.DataFrame:
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('batter') for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['pa'] >= 200]
                           .groupby('year')['fp_per_pa_actual'].mean().to_dict())
    all_batters = set()
    for df in by_yr.values():
        all_batters.update(df.index)
    rows = []
    for tgt in years:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL_WEIGHTS):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for b in all_batters:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                df_y = by_yr.get(y)
                if df_y is None or b not in df_y.index:
                    continue
                row = df_y.loc[b]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                pa = float(row.get('pa', 0) or 0)
                fp = float(row.get('fp_per_pa_actual', np.nan))
                if pa >= 50 and not np.isnan(fp):
                    num += w * pa * fp; denom += w * pa
            prior = (num + PRIOR_K_PA * league_mu) / (denom + PRIOR_K_PA)
            rows.append({'batter': b, 'year': tgt, 'prior_fp_per_pa': prior,
                         'prior_pa_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    return pd.DataFrame(rows)


def cross_year_eval(df: pd.DataFrame, feats: list) -> tuple[dict, dict]:
    sub = df.dropna(subset=feats + [TARGET]).copy()
    sub = sub[(sub['pa_to'] >= EVAL_PA_MIN) & (sub['ros_pa'] >= ROS_PA_MIN) & (sub['year'] != 2020)]
    per_year = {}; preds_all = []; acts_all = []
    for held in TRAIN_YEARS:
        train = sub[sub['year'] != held]; test = sub[sub['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        per_year[held] = {'r': round(r, 4), 'n': len(test)}
        preds_all.extend(preds); acts_all.extend(test[TARGET].tolist())
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4), 'n': len(preds_all)}


def compute_delta(per_year_base: dict, per_year_ext: dict, feats_base: list, feats_ext: list,
                  df: pd.DataFrame, baseline_r: float, ext_r: float) -> dict:
    """Compute per-year delta-r."""
    delta_r = ext_r - baseline_r
    per_year_delta = {}
    for y in sorted(per_year_base.keys()):
        rb = per_year_base.get(y, {}).get('r', np.nan)
        re = per_year_ext.get(y, {}).get('r', np.nan)
        per_year_delta[y] = round(re - rb, 4) if not np.isnan(rb) and not np.isnan(re) else np.nan
    return {'overall_delta_r': round(delta_r, 4), 'per_year': per_year_delta}


def convergence_curve(df: pd.DataFrame, base_feats: list, ext_feats: list) -> dict:
    """Per-split_day delta-r using TRAINING years only (no holdout contamination)."""
    sub = df[df['year'].isin(TRAIN_ONLY)].copy()
    sub = sub.dropna(subset=base_feats + ext_feats + [TARGET])
    sub = sub[(sub['pa_to'] >= EVAL_PA_MIN) & (sub['ros_pa'] >= ROS_PA_MIN)]
    results = {}
    for sd in sorted(sub['split_day'].unique()):
        sd_sub = sub[sub['split_day'] == sd]
        if len(sd_sub) < 100:
            results[int(sd)] = None
            continue
        # LOO over TRAIN_ONLY years
        preds_b, preds_e, acts = [], [], []
        for held in TRAIN_ONLY:
            tr = sd_sub[sd_sub['year'] != held]
            te = sd_sub[sd_sub['year'] == held]
            if len(tr) < 50 or len(te) < 20:
                continue
            for feats, store in [(base_feats, preds_b), (ext_feats, preds_e)]:
                p = Pipeline([('sc', StandardScaler()),
                              ('r', RidgeCV(alphas=np.logspace(-1, 5, 40), cv=5))])
                p.fit(tr[feats].values, tr[TARGET].values)
                store.extend(p.predict(te[feats].values))
            acts.extend(te[TARGET].tolist())
        if len(acts) < 20:
            results[int(sd)] = None; continue
        acts = np.array(acts)
        rb = float(np.corrcoef(np.array(preds_b), acts)[0, 1]) if preds_b else np.nan
        re = float(np.corrcoef(np.array(preds_e), acts)[0, 1]) if preds_e else np.nan
        results[int(sd)] = round(re - rb, 4) if not np.isnan(rb) and not np.isnan(re) else None
    return results


def compute_causal_slope(df: pd.DataFrame, rate_col: str, slope_name: str,
                          weight_col: str | None = None) -> pd.DataFrame:
    """
    Causal within-season slope of rate_col across split_days.
    At each (batter, year, split_day=N), fit slope using only obs at split_days ≤ N.
    If only 1 obs exists, slope = 0 (no information).
    Returns df with new column slope_name.
    """
    df = df.copy()
    df[slope_name] = 0.0

    split_days = sorted(df['split_day'].unique())
    for batter, grp in df.groupby(['batter', 'year']):
        # sort by split_day
        grp = grp.sort_values('split_day')
        idx = grp.index.tolist()
        sds = grp['split_day'].values
        rates = grp[rate_col].values
        slopes = np.zeros(len(grp))
        for i, sd in enumerate(sds):
            # use all points at split_days <= sd (causal)
            mask = sds[:i+1]
            xs = mask  # split_day values
            ys = rates[:i+1]
            valid = ~np.isnan(ys)
            if valid.sum() < 2:
                slopes[i] = 0.0
            else:
                xs_v = xs[valid].astype(float)
                ys_v = ys[valid]
                # OLS slope
                xm = xs_v.mean(); ym = ys_v.mean()
                ssxx = ((xs_v - xm)**2).sum()
                if ssxx < 1e-9:
                    slopes[i] = 0.0
                else:
                    slopes[i] = float(((xs_v - xm) * (ys_v - ym)).sum() / ssxx)
        for j, ix in enumerate(idx):
            df.at[ix, slope_name] = slopes[j]
    return df


# --- main ---------------------------------------------------------------------

def main():
    print('=' * 70)
    print('RH3 BREAKOUT SIGNAL SWEEP')
    print('=' * 70)
    print(f'\nRH3_FEATS ({len(RH3_FEATS)} features):')
    for f in RH3_FEATS:
        print(f'  {f}')

    # -- load data ----------------------------------------------------------
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'\nrolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')
    print(f'rolling split_days: {sorted(rolling["split_day"].unique())}')
    print(f'rolling years: {sorted(rolling["year"].unique())}')

    # -- prepare base dataset (mirror rh3.py main()) ---------------------
    years_needed = sorted(rolling['year'].unique())
    prior = build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    if H2_LOCKED.exists():
        h2 = pd.read_csv(H2_LOCKED)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2, on='batter', how='left')
        rolling['lift_h2_aug150'] = rolling['lift_h2_aug150'].fillna(0.0)
    else:
        rolling['lift_h2_aug150'] = 0.0

    if XWOBA_RESID.exists():
        xw = pd.read_csv(XWOBA_RESID)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
        rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
    else:
        rolling['xwoba_residual_career'] = 0.0

    # xwoba_gap_to (not in FEATS but computed in rh3.py for reference)
    if 'xwoba_on_contact_to' in rolling.columns and 'woba_d_sum_to' in rolling.columns:
        rolling['actual_woba_per_pa_to'] = np.where(
            rolling['woba_d_sum_to'] > 0,
            rolling['woba_v_sum_to'] / rolling['woba_d_sum_to'], np.nan)
        rolling['xwoba_gap_to'] = (rolling['xwoba_on_contact_to']
                                    - rolling['actual_woba_per_pa_to']).fillna(0.0)

    # career_stage
    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    rolling['career_stage'] = rolling.apply(
        lambda r: r['year'] - first_year.get(r['batter'], r['year']), axis=1)

    # RoS opp-SP schedule
    if ROS_OPP_SP.exists():
        opp = pd.read_csv(ROS_OPP_SP)[['batter', 'year', 'split_day', 'ros_opp_sp_xwoba_weighted']]
        rolling = rolling.merge(opp, on=['batter', 'year', 'split_day'], how='left')
        year_means = rolling.groupby('year')['ros_opp_sp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(year_means)
        rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(
            rolling['ros_opp_sp_xwoba_weighted'].mean())
    else:
        print('WARNING: ros_opp_sp_xwoba_weighted missing -- fill 0 (will degrade baseline r)')
        rolling['ros_opp_sp_xwoba_weighted'] = 0.0

    # shrinkage (both specs, training-only pop means)
    rolling = apply_shrinkage(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    for col in [r + '_sh' for r in SHRINK_SPEC_LAST21]:
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)

    # -- STEP 1: Baseline cross-year r ------------------------------------
    print('\n' + '-' * 60)
    print('STEP 1: RH3 BASELINE')
    print('-' * 60)
    # Check all baseline feats present
    missing_base = [f for f in RH3_FEATS if f not in rolling.columns]
    if missing_base:
        print(f'WARNING: missing baseline feats: {missing_base}')
        print('Dropping from baseline.')
        base_feats_use = [f for f in RH3_FEATS if f in rolling.columns]
    else:
        base_feats_use = RH3_FEATS

    per_year_base, overall_base = cross_year_eval(rolling, base_feats_use)
    print(f'Baseline cross_year_r = {overall_base["r"]:.4f}  n={overall_base["n"]}')
    print('Per-year:')
    for y, v in sorted(per_year_base.items()):
        tag = ' [HOLDOUT]' if y in HOLDOUT_YEARS else ''
        print(f'  {y}: r={v["r"]:.4f}  n={v["n"]}{tag}')

    # -- STEP 2: xwoba_on_contact_to_sh (Candidate A) --------------------
    print('\n' + '-' * 60)
    print('CANDIDATE A: xwoba_on_contact_to_sh')
    print('-' * 60)
    # Coverage check
    n_avail = rolling['xwoba_on_contact_to'].notna().sum()
    print(f'xwoba_on_contact_to: {n_avail}/{len(rolling)} rows non-null')
    by_yr = rolling.groupby('year')['xwoba_on_contact_to'].apply(lambda x: x.notna().sum())
    print('Coverage by year:', by_yr.to_dict())

    # Algebraic redundancy check: does rh3 already reconstruct xwOBACON?
    # rh3 has xwoba_per_pa_to_sh but NOT k_pct+bb_pct decomposition needed to isolate contact.
    # However it DOES have k_pct_to_sh and bb_pct_to_sh as separate features.
    # xwOBA/PA = (xwOBA_on_contact * BIP + BB_component * BB + HBP_component * HBP) / PA
    # So xwoba_on_contact = (xwOBA*PA - BB_component*BB - HBP_component*HBP) / BIP
    # rh3 HAS: xwoba_per_pa_to_sh, k_pct_to_sh, bb_pct_to_sh -> could reconstruct xwOBACON
    # This is the SAME algebraic redundancy as rp3.
    print('\nAlgebraic redundancy analysis:')
    print('  rh3 has: xwoba_per_pa_to_sh + k_pct_to_sh + bb_pct_to_sh')
    print('  These 3 features together can reconstruct xwOBA-on-contact algebraically.')
    print('  (xwOBA/PA = xwOBACON * contact_fraction + BB_weight * BB/PA + ...)')
    print('  => Expected redundancy = YES, similar to rp3 rejection.')
    print('  => Testing anyway to confirm empirically.')

    # xwoba_on_contact_to_sh already computed by apply_shrinkage above
    feats_A = base_feats_use + ['xwoba_on_contact_to_sh']
    per_year_A, overall_A = cross_year_eval(rolling, feats_A)
    delta_A = overall_A['r'] - overall_base['r']
    print(f'\nBaseline r:   {overall_base["r"]:.4f}')
    print(f'Extended r:   {overall_A["r"]:.4f}')
    print(f'Delta r:      {delta_A:+.4f}')
    print(f'Gate:         >= +0.005 -> {"PASS" if delta_A >= 0.005 else "FAIL"}')
    per_yr_deltas_A = {y: round(per_year_A.get(y, {}).get('r', np.nan) -
                                per_year_base.get(y, {}).get('r', np.nan), 4)
                       for y in sorted(per_year_base.keys())}
    pos = sum(1 for v in per_yr_deltas_A.values() if v > 0 and not np.isnan(v))
    print(f'Per-year delta-r: {per_yr_deltas_A}')
    print(f'Positive years: {pos}/{len([v for v in per_yr_deltas_A.values() if not np.isnan(v)])}')
    holdout_A = {y: per_yr_deltas_A[y] for y in HOLDOUT_YEARS if y in per_yr_deltas_A}
    print(f'Holdout: {holdout_A}')
    verdict_A = 'PASS' if (delta_A >= 0.005 and pos >= 5 and all(v > 0 for v in holdout_A.values())) else \
                'MARGINAL' if delta_A > 0 else 'REJECTED'
    print(f'VERDICT A: {verdict_A}')

    if verdict_A == 'PASS':
        print('\nConvergence curve (TRAIN_ONLY):')
        cc_A = convergence_curve(rolling, base_feats_use, feats_A)
        for sd, dr in sorted(cc_A.items()):
            print(f'  split_day={sd}: dr={dr}')

    # -- STEP 3: Causal xwoba slope (Candidate B) -------------------------
    print('\n' + '-' * 60)
    print('CANDIDATE B: Causal slope of xwoba_per_pa_to (within-season trajectory)')
    print('-' * 60)
    print('Computing causal slopes...')
    rolling = compute_causal_slope(rolling, 'xwoba_per_pa_to', 'xwoba_slope_causal')

    # Validate causal computation (check at split_day=30, only 1 obs -> slope=0)
    sd30_slopes = rolling[rolling['split_day'] == 30]['xwoba_slope_causal']
    print(f'At split_day=30: slope=0 for all rows? {(sd30_slopes == 0).all()} (expected: True)')
    sd90_nz = rolling[(rolling['split_day'] == 90)]['xwoba_slope_causal'].abs().sum()
    print(f'At split_day=90: sum(|slope|) = {sd90_nz:.4f} (expected: > 0)')

    # Shrink slope (per split_day normalization via population mean from training)
    slope_mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'xwoba_slope_causal'].mean()
    slope_sd = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'xwoba_slope_causal'].std()
    rolling['xwoba_slope_causal_z'] = (rolling['xwoba_slope_causal'] - slope_mu) / max(slope_sd, 1e-9)

    feats_B = base_feats_use + ['xwoba_slope_causal_z']
    per_year_B, overall_B = cross_year_eval(rolling, feats_B)
    delta_B = overall_B['r'] - overall_base['r']
    print(f'\nBaseline r:   {overall_base["r"]:.4f}')
    print(f'Extended r:   {overall_B["r"]:.4f}')
    print(f'Delta r:      {delta_B:+.4f}')
    print(f'Gate:         >= +0.005 -> {"PASS" if delta_B >= 0.005 else "FAIL"}')
    per_yr_deltas_B = {y: round(per_year_B.get(y, {}).get('r', np.nan) -
                                per_year_base.get(y, {}).get('r', np.nan), 4)
                       for y in sorted(per_year_base.keys())}
    pos_B = sum(1 for v in per_yr_deltas_B.values() if v > 0 and not np.isnan(v))
    print(f'Per-year delta-r: {per_yr_deltas_B}')
    print(f'Positive years: {pos_B}/{len([v for v in per_yr_deltas_B.values() if not np.isnan(v)])}')
    holdout_B = {y: per_yr_deltas_B[y] for y in HOLDOUT_YEARS if y in per_yr_deltas_B}
    print(f'Holdout: {holdout_B}')
    verdict_B = 'PASS' if (delta_B >= 0.005 and pos_B >= 5 and all(v > 0 for v in holdout_B.values())) else \
                'MARGINAL' if delta_B > 0 else 'REJECTED'
    print(f'VERDICT B: {verdict_B}')

    if verdict_B == 'PASS' or delta_B > 0.002:
        print('\nConvergence curve (TRAIN_ONLY, split_day=90 only uses >=2 obs):')
        cc_B = convergence_curve(rolling, base_feats_use, feats_B)
        for sd, dr in sorted(cc_B.items()):
            print(f'  split_day={sd}: dr={dr}')

    # -- STEP 4: Bat speed (Candidate C) -- SKIPPED -----------------------
    print('\n' + '-' * 60)
    print('CANDIDATE C: bat_speed_level_prior -- SKIP (pre-rejected 2026-05-24)')
    print('  Step 2.5 failure: only 1 training year available (2025 outcomes).')
    print('  bat_speed coverage: 2026 only in hitters_multiyr; 0 prior-year rows.')
    print('  Cannot clear 5/7 sign-consistency gate. Blocked until ~2028.')
    print('-' * 60)

    # -- STEP 5: Sprint speed prior (Candidate D) -------------------------
    print('\n' + '-' * 60)
    print('CANDIDATE D: sprint_speed_prior (prior-year sprint speed)')
    print('-' * 60)

    sprint_cov = multiyr.groupby('year')['sprint_speed'].apply(lambda x: x.notna().sum())
    print('Sprint speed coverage by year:')
    print(sprint_cov.to_dict())

    # Join T-1 sprint speed as prior
    sprint_prior = multiyr[['batter', 'year', 'sprint_speed']].copy()
    sprint_prior = sprint_prior.rename(columns={'sprint_speed': 'sprint_speed_prior'})
    sprint_prior['year'] = sprint_prior['year'] + 1  # T-1 value as feature for year T
    rolling = rolling.merge(sprint_prior, on=['batter', 'year'], how='left')

    # Coverage check
    n_sprint = rolling['sprint_speed_prior'].notna().sum()
    print(f'\nsprint_speed_prior coverage: {n_sprint}/{len(rolling)} ({100*n_sprint/len(rolling):.1f}%)')
    sprint_by_yr = rolling.groupby('year')['sprint_speed_prior'].apply(lambda x: x.notna().sum())
    print('Coverage by year:', sprint_by_yr.to_dict())

    # Step 2.5: training years with >= some coverage
    train_sprint_cov = {y: int(sprint_by_yr.get(y, 0)) for y in TRAIN_ONLY}
    print(f'Training-year coverage: {train_sprint_cov}')
    years_with_sprint = sum(1 for v in train_sprint_cov.values() if v >= 50)
    print(f'Training years with >=50 coverage: {years_with_sprint}/{len(TRAIN_ONLY)}')

    # Fill NaN with year mean (within training)
    year_sprint_mean = rolling.loc[rolling['year'].isin(TRAIN_YEARS)].groupby('year')['sprint_speed_prior'].mean()
    rolling['sprint_speed_prior_filled'] = rolling.apply(
        lambda r: r['sprint_speed_prior'] if not pd.isna(r['sprint_speed_prior'])
                  else year_sprint_mean.get(r['year'], np.nan), axis=1)
    # Fill remaining with grand mean
    grand_mean_sprint = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'sprint_speed_prior_filled'].mean()
    rolling['sprint_speed_prior_filled'] = rolling['sprint_speed_prior_filled'].fillna(grand_mean_sprint)

    feats_D = base_feats_use + ['sprint_speed_prior_filled']
    per_year_D, overall_D = cross_year_eval(rolling, feats_D)
    delta_D = overall_D['r'] - overall_base['r']
    print(f'\nBaseline r:   {overall_base["r"]:.4f}')
    print(f'Extended r:   {overall_D["r"]:.4f}')
    print(f'Delta r:      {delta_D:+.4f}')
    print(f'Gate:         >= +0.005 -> {"PASS" if delta_D >= 0.005 else "FAIL"}')
    per_yr_deltas_D = {y: round(per_year_D.get(y, {}).get('r', np.nan) -
                                per_year_base.get(y, {}).get('r', np.nan), 4)
                       for y in sorted(per_year_base.keys())}
    pos_D = sum(1 for v in per_yr_deltas_D.values() if v > 0 and not np.isnan(v))
    print(f'Per-year delta-r: {per_yr_deltas_D}')
    print(f'Positive years: {pos_D}/{len([v for v in per_yr_deltas_D.values() if not np.isnan(v)])}')
    holdout_D = {y: per_yr_deltas_D[y] for y in HOLDOUT_YEARS if y in per_yr_deltas_D}
    print(f'Holdout: {holdout_D}')
    verdict_D = 'PASS' if (delta_D >= 0.005 and pos_D >= 5 and all(v > 0 for v in holdout_D.values())) else \
                'MARGINAL' if delta_D > 0 else 'REJECTED'
    print(f'VERDICT D: {verdict_D}')

    if verdict_D == 'PASS' or delta_D > 0.002:
        print('\nConvergence curve (TRAIN_ONLY):')
        cc_D = convergence_curve(rolling, base_feats_use, feats_D)
        for sd, dr in sorted(cc_D.items()):
            print(f'  split_day={sd}: dr={dr}')

    # -- STEP 6: Hard-hit causal slope (Candidate E) ----------------------
    print('\n' + '-' * 60)
    print('CANDIDATE E: Causal slope of hard_hit_pct_to')
    print('-' * 60)
    print('Computing causal hard-hit slopes...')
    rolling = compute_causal_slope(rolling, 'hard_hit_pct_to', 'hh_slope_causal')

    sd30_hh = rolling[rolling['split_day'] == 30]['hh_slope_causal']
    print(f'At split_day=30: slope=0 for all? {(sd30_hh == 0).all()}')

    hh_mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'hh_slope_causal'].mean()
    hh_sd = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'hh_slope_causal'].std()
    rolling['hh_slope_causal_z'] = (rolling['hh_slope_causal'] - hh_mu) / max(hh_sd, 1e-9)

    feats_E = base_feats_use + ['hh_slope_causal_z']
    per_year_E, overall_E = cross_year_eval(rolling, feats_E)
    delta_E = overall_E['r'] - overall_base['r']
    print(f'\nBaseline r:   {overall_base["r"]:.4f}')
    print(f'Extended r:   {overall_E["r"]:.4f}')
    print(f'Delta r:      {delta_E:+.4f}')
    print(f'Gate:         >= +0.005 -> {"PASS" if delta_E >= 0.005 else "FAIL"}')
    per_yr_deltas_E = {y: round(per_year_E.get(y, {}).get('r', np.nan) -
                                per_year_base.get(y, {}).get('r', np.nan), 4)
                       for y in sorted(per_year_base.keys())}
    pos_E = sum(1 for v in per_yr_deltas_E.values() if v > 0 and not np.isnan(v))
    print(f'Per-year delta-r: {per_yr_deltas_E}')
    print(f'Positive years: {pos_E}/{len([v for v in per_yr_deltas_E.values() if not np.isnan(v)])}')
    holdout_E = {y: per_yr_deltas_E[y] for y in HOLDOUT_YEARS if y in per_yr_deltas_E}
    print(f'Holdout: {holdout_E}')
    verdict_E = 'PASS' if (delta_E >= 0.005 and pos_E >= 5 and all(v > 0 for v in holdout_E.values())) else \
                'MARGINAL' if delta_E > 0 else 'REJECTED'
    print(f'VERDICT E: {verdict_E}')

    if verdict_E == 'PASS' or delta_E > 0.002:
        print('\nConvergence curve (TRAIN_ONLY):')
        cc_E = convergence_curve(rolling, base_feats_use, feats_E)
        for sd, dr in sorted(cc_E.items()):
            print(f'  split_day={sd}: dr={dr}')

    # -- STEP 7: Discipline index bb_pct * (1-k_pct) (Candidate F) --------
    print('\n' + '-' * 60)
    print('CANDIDATE F: Discipline index = bb_pct_to_sh * (1 - k_pct_to_sh)')
    print('Note: bb_pct_x_xwoba_per_pa_to_sh was already REJECTED 2026-05-24')
    print('This is a different interaction: bb_pct * k_pct avoidance')
    print('-' * 60)
    rolling['discipline_index'] = rolling['bb_pct_to_sh'] * (1.0 - rolling['k_pct_to_sh'])
    di_mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'discipline_index'].mean()
    di_sd = rolling.loc[rolling['year'].isin(TRAIN_YEARS), 'discipline_index'].std()
    rolling['discipline_index_z'] = (rolling['discipline_index'] - di_mu) / max(di_sd, 1e-9)

    feats_F = base_feats_use + ['discipline_index_z']
    per_year_F, overall_F = cross_year_eval(rolling, feats_F)
    delta_F = overall_F['r'] - overall_base['r']
    print(f'\nBaseline r:   {overall_base["r"]:.4f}')
    print(f'Extended r:   {overall_F["r"]:.4f}')
    print(f'Delta r:      {delta_F:+.4f}')
    print(f'Gate:         >= +0.005 -> {"PASS" if delta_F >= 0.005 else "FAIL"}')
    per_yr_deltas_F = {y: round(per_year_F.get(y, {}).get('r', np.nan) -
                                per_year_base.get(y, {}).get('r', np.nan), 4)
                       for y in sorted(per_year_base.keys())}
    pos_F = sum(1 for v in per_yr_deltas_F.values() if v > 0 and not np.isnan(v))
    print(f'Per-year delta-r: {per_yr_deltas_F}')
    print(f'Positive years: {pos_F}/{len([v for v in per_yr_deltas_F.values() if not np.isnan(v)])}')
    holdout_F = {y: per_yr_deltas_F[y] for y in HOLDOUT_YEARS if y in per_yr_deltas_F}
    print(f'Holdout: {holdout_F}')
    verdict_F = 'PASS' if (delta_F >= 0.005 and pos_F >= 5 and all(v > 0 for v in holdout_F.values())) else \
                'MARGINAL' if delta_F > 0 else 'REJECTED'
    print(f'VERDICT F: {verdict_F}')

    # -- SUMMARY ------------------------------------------------------------
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    print(f'\nBaseline RH3 cross_year_r = {overall_base["r"]:.4f}')
    print('\nCandidate results:')
    rows = [
        ('A', 'xwoba_on_contact_to_sh', delta_A, pos, verdict_A),
        ('B', 'xwoba_slope_causal_z (within-season)', delta_B, pos_B, verdict_B),
        ('C', 'bat_speed_level_prior', None, None, 'SKIP (Step 2.5 blocked)'),
        ('D', 'sprint_speed_prior', delta_D, pos_D, verdict_D),
        ('E', 'hh_slope_causal_z (hard-hit trajectory)', delta_E, pos_E, verdict_E),
        ('F', 'discipline_index_z (bb * (1-k))', delta_F, pos_F, verdict_F),
    ]
    print(f'  {"ID":<2}  {"Feature":<40}  {"dr":>7}  {"Pos/7":>6}  Verdict')
    for r_id, name, delta, pos_cnt, verdict in rows:
        d = f'{delta:+.4f}' if delta is not None else '  N/A '
        p = f'{pos_cnt}/7' if pos_cnt is not None else '  N/A'
        print(f'  {r_id:<2}  {name:<40}  {d:>7}  {p:>6}  {verdict}')

    print('\nInterpretation:')
    for r_id, name, delta, pos_cnt, verdict in rows:
        if verdict == 'PASS':
            print(f'  [{r_id}] PASS -> recommend formal /validate-feature run.')
        elif verdict == 'MARGINAL' and delta is not None and delta > 0.002:
            print(f'  [{r_id}] MARGINAL (dr={delta:+.4f}) -> borderline; consider deeper per-split_day analysis.')
        elif verdict in ('SKIP', 'SKIP (Step 2.5 blocked)'):
            print(f'  [{r_id}] {name}: un-validatable until ~2028. Skip.')
        else:
            print(f'  [{r_id}] {name}: dr={delta} -> REJECTED, do not pursue.')

    print('\nAlgebraic redundancy note (Candidate A):')
    print('  rh3 has xwoba_per_pa_to_sh + k_pct_to_sh + bb_pct_to_sh.')
    print('  These three jointly reconstruct xwOBA-on-contact (same algebra as rp3).')
    print('  If delta_A ≈ 0, the redundancy is confirmed empirically for hitters too.')

    print('\nDone.')


if __name__ == '__main__':
    main()
