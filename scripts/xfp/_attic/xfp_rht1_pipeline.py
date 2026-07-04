"""xfp_rht1_pipeline.py — RoS hitter TOTAL-FP model.

Predicts rest-of-season TOTAL FP directly (instead of FP/PA rate). This gives
volume features (lineup spot, PA history, started %) a place in the model.

Validation gates (mirrors RP-RS2 + RH4 methodology):
  1. OVERALL cross-year r on TOTAL FP must beat the indirect baseline
     (RH3 rate × naive PA projection) by >= +0.02.
  2. LINEUP-CHANGE subset r MUST improve by >= +0.05 over indirect baseline.

Target: ros_pa × ros_full_fp_per_pa = ros_total_fp (computed from substrate).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
MASTER_HITTER = ROOT / 'data' / 'outputs' / 'master_hitter_2026.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rht1_pipeline.pkl'
PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rht1_projections.csv'

TARGET = 'ros_total_fp'  # NEW: derived as ros_pa * ros_full_fp_per_pa
EVAL_PA_MIN = 50
ROS_PA_MIN = 100
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_PA = 200
MARCEL_WEIGHTS = (5, 4, 3)
SEASON_DAYS = 185  # approximate season length in days
REPLACEMENT_RANK = {'C': 12, '1B': 12, '2B': 12, 'SS': 12, '3B': 12,
                    'OF': 36, 'DH': 24, 'UTIL': 24}

SHRINK_SPEC_TO = {
    'k_pct_to':         ('pa_to', 60), 'bb_pct_to':        ('pa_to', 120),
    'hr_per_pa_to':     ('pa_to', 170), 'iso_to':           ('ab_to', 160),
    'sb_per_pa_to':     ('pa_to', 300), 'xwoba_per_pa_to':  ('pa_to', 300),
    'contact_pct_to':   ('swing_to', 100), 'whiff_pct_to':  ('swing_to', 100),
    'swstr_pct_to':     ('pitches_to', 300), 'hard_hit_pct_to': ('bip_to', 50),
    'barrel_pct_to':    ('bip_to', 50),
    'chase_pct_to':     ('out_zone_to', 400), 'in_play_pct_to': ('pitches_to', 300),
}

# Skill features (rate-side, mirrors RH3 base)
SKILL_FEATS = [
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    'prior_fp_per_pa', 'prior_pa_eff',
]
# Volume features (the new ones lineup_spot work feeds into)
VOLUME_FEATS = [
    'pa_to', 'lineup_spot_to', 'started_pct_to', 'pa_per_started_game_to',
    'lineup_spot_lag1', 'started_pct_lag1', 'pa_lag1',
]
META_FEATS = ['split_day']
RHT1_FEATS = SKILL_FEATS + VOLUME_FEATS + META_FEATS

# Baseline (indirect) needs only the rate model's features
RH3_RATE_FEATS = SKILL_FEATS + ['pa_to', 'split_day']


def _ensure_derived(df):
    out = df
    if 'ab_to' not in out.columns:
        out = out.assign(ab_to=out['pa_to'] - out['bb_to'] - out.get('hbp_to', 0))
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    return out


def build_prior_table(multiyr, years):
    rows = []
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('batter') for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['pa'] >= 200]
                           .groupby('year')['fp_per_pa_actual'].mean().to_dict())
    all_batters = set()
    for df in by_yr.values():
        all_batters.update(df.index)
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
                df_y = by_yr[y]
                if b in df_y.index:
                    row = df_y.loc[b]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    pa = float(row.get('pa', 0) or 0)
                    fp = float(row.get('fp_per_pa_actual', np.nan))
                    if pa >= 50 and not np.isnan(fp):
                        num += w * pa * fp
                        denom += w * pa
            prior = (num + PRIOR_K_PA * league_mu) / (denom + PRIOR_K_PA)
            rows.append({'batter': b, 'year': tgt,
                         'prior_fp_per_pa': prior,
                         'prior_pa_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    return pd.DataFrame(rows)


def build_lineup_lag(rolling):
    last_split_per_year = rolling.groupby('year')['split_day'].max().to_dict()
    rows = []
    for yr, max_split in last_split_per_year.items():
        sub = rolling[(rolling['year'] == yr) & (rolling['split_day'] == max_split)]
        for _, r in sub.iterrows():
            rows.append({
                'batter': int(r['batter']),
                'year_target': int(yr) + 1,
                'lineup_spot_lag1': float(r['lineup_spot_to']) if pd.notna(r['lineup_spot_to']) else np.nan,
                'started_pct_lag1': float(r['started_pct_to']) if pd.notna(r['started_pct_to']) else np.nan,
            })
    return pd.DataFrame(rows)


def compute_pop_means(df, train_years, spec):
    means = {}
    sub = _ensure_derived(df[df['year'].isin(train_years) & (df['year'] != 2020)].copy())
    for rate_col, (denom_col, _k) in spec.items():
        if rate_col not in sub.columns or denom_col not in sub.columns:
            means[rate_col] = float(sub.get(rate_col, pd.Series([0])).mean(skipna=True) or 0.0)
            continue
        d = sub[[rate_col, denom_col]].dropna()
        d = d[d[denom_col] > 0]
        if d.empty:
            means[rate_col] = float(sub[rate_col].mean(skipna=True) or 0.0)
        else:
            means[rate_col] = float((d[rate_col] * d[denom_col]).sum() / d[denom_col].sum())
    return means


def apply_shrinkage(df, pop_means, spec):
    out = _ensure_derived(df.copy())
    for rate_col, (denom_col, k) in spec.items():
        if rate_col not in out.columns or denom_col not in out.columns:
            mu = pop_means.get(rate_col, 0.0)
            out[rate_col + '_sh'] = mu
            continue
        n = out[denom_col].astype(float)
        obs = out[rate_col].astype(float)
        mean = pop_means.get(rate_col, float(np.nanmean(obs) or 0.0))
        obs_filled = obs.fillna(mean)
        n_eff = n.fillna(0.0)
        out[rate_col + '_sh'] = (n_eff * obs_filled + k * mean) / (n_eff + k)
    return out


def cross_year_total_eval(df, feats, target_col, subset_mask=None):
    """Train Ridge on TOTAL FP target; LOO cross-year r."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [target_col]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    per_year, preds_all, acts_all, test_idx = {}, [], [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[target_col].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[target_col].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[target_col].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(test)}
        preds_all.extend(preds.tolist()); acts_all.extend(test[target_col].tolist())
        test_idx.extend(test.index.tolist())
    if subset_mask is not None:
        preds_arr = np.array(preds_all); acts_arr = np.array(acts_all)
        idx_arr = np.array(test_idx)
        keep = subset_mask.reindex(idx_arr).fillna(False).values
        preds_arr = preds_arr[keep]; acts_arr = acts_arr[keep]
        if len(preds_arr) < 30:
            return per_year, {'r': np.nan, 'mae': np.nan, 'n': len(preds_arr)}
        r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
        mae = float(np.mean(np.abs(preds_arr - acts_arr)))
        return per_year, {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(preds_arr)}
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 2),
                      'n': len(preds_all)}


def cross_year_indirect_baseline(df, rate_feats, subset_mask=None):
    """Indirect baseline: train Ridge on FP/PA rate, then total = predicted_rate × naive_pa_projection.
    naive_pa_projection = pa_to * (SEASON_DAYS - split_day) / split_day.
    Evaluate the total prediction against actual ros_total_fp.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=rate_feats + ['ros_full_fp_per_pa', 'ros_total_fp']).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    preds_all, acts_all, test_idx = [], [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[rate_feats].values, train['ros_full_fp_per_pa'].values)
        rate_pred = pipe.predict(test[rate_feats].values)
        # Naive PA projection: pa_to per day × remaining days
        pa_pace_per_day = test['pa_to'].values / np.maximum(test['split_day'].values, 1)
        naive_pa_pred = pa_pace_per_day * np.maximum(SEASON_DAYS - test['split_day'].values, 0)
        total_pred = rate_pred * naive_pa_pred
        preds_all.extend(total_pred.tolist())
        acts_all.extend(test['ros_total_fp'].tolist())
        test_idx.extend(test.index.tolist())
    if subset_mask is not None:
        preds_arr = np.array(preds_all); acts_arr = np.array(acts_all)
        idx_arr = np.array(test_idx)
        keep = subset_mask.reindex(idx_arr).fillna(False).values
        preds_arr = preds_arr[keep]; acts_arr = acts_arr[keep]
        if len(preds_arr) < 30:
            return {'r': np.nan, 'mae': np.nan, 'n': len(preds_arr)}
        r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
        mae = float(np.mean(np.abs(preds_arr - acts_arr)))
        return {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(preds_arr)}
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return {'r': round(overall_r, 4), 'mae': round(overall_mae, 2), 'n': len(preds_all)}


def lineup_change_mask(df):
    has_lag = df['lineup_spot_lag1'].notna()
    gap = (df['lineup_spot_to'] - df['lineup_spot_lag1']).abs()
    return has_lag & (gap >= 1.5)


def train_final(df, feats, target_col):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [target_col])
    train = train[(train['pa_to'] >= EVAL_PA_MIN) & (train['ros_pa'] >= ROS_PA_MIN)
                  & (train['year'].isin(TRAIN_YEARS))]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[target_col].values)
    return pipe, len(train)


def main():
    print('=== xfp_rht1_pipeline (RoS hitter TOTAL-FP model) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    # Compute total target
    rolling['ros_total_fp'] = rolling['ros_pa'] * rolling['ros_full_fp_per_pa']

    # Marcel prior + lineup lag (same as RH4 setup)
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    lineup_lag = build_lineup_lag(rolling)
    rolling = rolling.merge(lineup_lag, left_on=['batter','year'],
                             right_on=['batter','year_target'], how='left').drop(columns=['year_target'], errors='ignore')
    pop_lineup_spot = float(rolling['lineup_spot_to'].mean())
    rolling['lineup_spot_lag1'] = rolling['lineup_spot_lag1'].fillna(pop_lineup_spot)
    rolling['started_pct_lag1'] = rolling['started_pct_lag1'].fillna(0.0)
    rolling['lineup_spot_to'] = rolling['lineup_spot_to'].fillna(pop_lineup_spot)
    rolling['started_pct_to'] = rolling['started_pct_to'].fillna(0.0)
    rolling['pa_per_started_game_to'] = rolling['pa_per_started_game_to'].fillna(rolling['pa_per_started_game_to'].mean())

    # pa_lag1 (prior-year PA total — volume signal)
    pa_lag = multiyr[['batter','year','pa']].rename(columns={'pa':'pa_lag1'})
    pa_lag['year_target'] = pa_lag['year'] + 1
    rolling = rolling.merge(pa_lag[['batter','year_target','pa_lag1']],
                             left_on=['batter','year'], right_on=['batter','year_target'],
                             how='left').drop(columns=['year_target'], errors='ignore')
    pop_pa_lag = float(rolling['pa_lag1'].mean())
    rolling['pa_lag1'] = rolling['pa_lag1'].fillna(pop_pa_lag)

    # Shrinkage
    pop_to = compute_pop_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)

    # Lineup-change subset
    lc_mask = lineup_change_mask(rolling)
    print(f'\nLineup-change subset (|lineup_spot_to − lineup_spot_lag1| >= 1.5 + has lag): {lc_mask.sum()} rows')

    # Indirect baseline (RH3 rate × naive PA)
    print('\n--- INDIRECT BASELINE (RH3 rate × naive PA × remaining days) ---')
    base_overall = cross_year_indirect_baseline(rolling, RH3_RATE_FEATS)
    base_lc = cross_year_indirect_baseline(rolling, RH3_RATE_FEATS, subset_mask=lc_mask)
    print(f'  Overall TOTAL-FP r:    {base_overall["r"]}  mae={base_overall["mae"]}  n={base_overall["n"]}')
    print(f'  Lineup-change subset:  r={base_lc["r"]}    mae={base_lc["mae"]}  n={base_lc["n"]}')

    # Direct RH-T1 model
    print('\n--- DIRECT RH-T1 (skill + volume features → TOTAL FP) ---')
    per_year, direct_overall = cross_year_total_eval(rolling, RHT1_FEATS, TARGET)
    _per, direct_lc = cross_year_total_eval(rolling, RHT1_FEATS, TARGET, subset_mask=lc_mask)
    for y, m in sorted(per_year.items()):
        print(f'  {y}: r={m["r"]:.4f}  mae={m["mae"]:.2f}  n={m["n"]}')
    print(f'  Overall:               r={direct_overall["r"]}  mae={direct_overall["mae"]}  n={direct_overall["n"]}')
    print(f'  Lineup-change subset:  r={direct_lc["r"]}      mae={direct_lc["mae"]}  n={direct_lc["n"]}')

    delta_overall = direct_overall['r'] - base_overall['r']
    delta_lc      = direct_lc['r'] - base_lc['r']
    print(f'\n--- GATE EVALUATION ---')
    print(f'  Δr overall (gate ≥ +0.02):        {delta_overall:+.4f}  '
          f'{"PASS" if delta_overall >= 0.02 else "FAIL"}')
    print(f'  Δr lineup-change (gate ≥ +0.05): {delta_lc:+.4f}  '
          f'{"PASS" if delta_lc >= 0.05 else "FAIL"}')

    overall_pass = (delta_overall >= 0.02)
    lc_pass = (delta_lc >= 0.05)
    if not overall_pass:
        print('\nOVERALL r REGRESSED OR INSUFFICIENT — direct total model not better than indirect baseline.')
        print('Documenting; not promoting.')
        return
    if not lc_pass:
        print('\nLINEUP-CHANGE subset DID NOT IMPROVE — features add noise where it matters.')
        print('Documenting; not promoting.')
        return

    print('\n[BOTH GATES PASSED] Promoting RH-T1 to production.')

    # Train final
    pipe, n_train = train_final(rolling, RHT1_FEATS, TARGET)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RH-T1 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}, '
          f'{len(RHT1_FEATS)} features) ---')
    print('  Top 12 coefficients:')
    for f, c in sorted(zip(RHT1_FEATS, coefs), key=lambda x: -abs(x[1]))[:12]:
        print(f'    {f:<26s} {c:+.4f}')
    print('  VOLUME feature coefficients:')
    for f, c in zip(RHT1_FEATS, coefs):
        if f in VOLUME_FEATS:
            print(f'    {f:<26s} {c:+.4f}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['pa_to'] >= EVAL_PA_MIN)]
    valid = df_26.dropna(subset=RHT1_FEATS).copy()
    valid['xfp_total_ros'] = pipe.predict(valid[RHT1_FEATS].values).round(1)

    names = multiyr[multiyr['year'] == 2026][['batter', 'player_name', 'team']].drop_duplicates('batter')
    valid = valid.drop_duplicates('batter').merge(names, on='batter', how='left')
    if MASTER_HITTER.exists():
        mh = pd.read_csv(MASTER_HITTER)
        keep = [c for c in ['batter', 'primary_position', 'fantasy_positions',
                            'fantasy_positions_display']
                if c in mh.columns]
        valid = valid.merge(mh[keep], on='batter', how='left')
    if 'primary_position' not in valid.columns:
        valid['primary_position'] = None

    # Position-aware replacement-level on TOTAL FP
    def _norm_pos(p):
        if not isinstance(p, str): return 'UTIL'
        p = p.upper().strip()
        if p in ('LF','CF','RF','OF'): return 'OF'
        if p in ('C','1B','2B','SS','3B','DH'): return p
        return 'UTIL'
    valid['_pos'] = valid['primary_position'].map(_norm_pos)
    repl = {}
    for pos, n in REPLACEMENT_RANK.items():
        sub = valid[valid['_pos'] == pos].sort_values('xfp_total_ros', ascending=False)
        if len(sub) >= n:
            repl[pos] = float(sub['xfp_total_ros'].iloc[n - 1])
        elif not sub.empty:
            repl[pos] = float(sub['xfp_total_ros'].iloc[-1])
        else:
            repl[pos] = float(valid['xfp_total_ros'].median())
    valid['replacement_total'] = valid['_pos'].map(repl)
    valid['replacement_delta_total'] = (valid['xfp_total_ros'] - valid['replacement_total']).round(1)
    valid = valid.drop(columns=['_pos'])

    valid = valid.sort_values('xfp_total_ros', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': RHT1_FEATS,
        'features_skill': SKILL_FEATS,
        'features_volume': VOLUME_FEATS,
        'cross_year_r': direct_overall['r'],
        'cross_year_mae': direct_overall['mae'],
        'baseline_indirect_r': base_overall['r'],
        'lineup_change_r': direct_lc['r'],
        'lineup_change_baseline_r': base_lc['r'],
        'delta_overall': round(delta_overall, 4),
        'delta_lineup_change': round(delta_lc, 4),
        'per_year_r': per_year,
        'training_years': TRAIN_YEARS,
        'gate_overall': 0.02,
        'gate_lineup_change': 0.05,
        'pop_means_to': pop_to,
        'shrink_spec_to': SHRINK_SPEC_TO,
        'pop_lineup_spot': pop_lineup_spot,
        'pop_pa_lag': pop_pa_lag,
        'season_days': SEASON_DAYS,
        'replacement_rank': REPLACEMENT_RANK,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rht1',
        'note': 'RoS hitter TOTAL-FP model. Direct total prediction with skill + '
                'volume features (lineup spot, started %, PA history). Beats '
                'indirect rate-times-naive-PA baseline.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    out_cols = ['rank','batter','player_name','team','primary_position',
                'pa_to','lineup_spot_to','started_pct_to','prior_fp_per_pa',
                'xfp_total_ros','replacement_total','replacement_delta_total']
    out_cols = [c for c in out_cols if c in valid.columns]
    valid[out_cols].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} hitters')

    print('\nTop 15 by RoS xFP TOTAL:')
    print(valid.head(15)[['rank','player_name','primary_position','team','pa_to',
                          'lineup_spot_to','xfp_total_ros','replacement_delta_total']].to_string(index=False))


if __name__ == '__main__':
    main()
