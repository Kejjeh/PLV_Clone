"""validate_phase_r3.py — empirical sanity checks on Phase R3 features.

Tests, on real historical 2025 data:
  1. Does opponent-team bat_index correlate with pitcher FP/start?
  2. Are RH3/RP3 confidence intervals calibrated (50% of actuals in p25-p75)?
  3. Does recency_form_gap predict residual on the next window?
  4. Are replacement-deltas reasonable (top-N by xfp actually outscore replacement)?
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

CACHE = Path('c:/Users/Joshua/plv_clone/data/research/xfp_cache')

# ───────────────────────────────────────────────────────────────────────────
# 1) Schedule-strength signal validation: opp bat_index -> pitcher FP/start
# ───────────────────────────────────────────────────────────────────────────
def test_schedule_strength_signal():
    print('=' * 72)
    print('TEST 1: Does opp bat_index correlate with pitcher FP/start? (2025)')
    print('=' * 72)
    sc = pd.read_parquet(CACHE / 'statcast_2025.parquet')
    sc['game_date'] = pd.to_datetime(sc['game_date'])
    sc['inning'] = pd.to_numeric(sc['inning'], errors='coerce')
    sc['bat_team'] = np.where(sc['inning_topbot'] == 'Top', sc['away_team'], sc['home_team'])

    starts = (sc[sc['inning'] == 1]
              .groupby(['game_pk', 'inning_topbot'])['pitcher']
              .first().reset_index().rename(columns={'pitcher': 'starter_id'}))
    sp_pitches = sc.merge(starts, on=['game_pk', 'inning_topbot'], how='left')
    sp_pitches = sp_pitches[sp_pitches['pitcher'] == sp_pitches['starter_id']].copy()

    ev = sp_pitches['events'].fillna('')
    sp_pitches['is_k'] = ev == 'strikeout'
    sp_pitches['is_bb'] = ev == 'walk'
    sp_pitches['is_hbp'] = ev == 'hit_by_pitch'
    sp_pitches['is_h'] = ev.isin({'single', 'double', 'triple', 'home_run'})
    sp_pitches['is_pa_end'] = ev != ''
    out_events = {'strikeout', 'field_out', 'grounded_into_double_play', 'sac_fly',
                  'sac_bunt', 'force_out', 'double_play', 'triple_play',
                  'fielders_choice_out', 'caught_stealing_2b', 'caught_stealing_3b',
                  'caught_stealing_home', 'other_out'}
    sp_pitches['outs_made'] = ev.isin(out_events).astype(int)
    sp_pitches.loc[ev.isin(['grounded_into_double_play', 'double_play']), 'outs_made'] = 2
    sp_pitches.loc[ev == 'triple_play', 'outs_made'] = 3
    runs = (pd.to_numeric(sp_pitches['post_bat_score'], errors='coerce')
            - pd.to_numeric(sp_pitches['bat_score'], errors='coerce')).clip(lower=0)
    sp_pitches['runs_on_play'] = runs.where(sp_pitches['is_pa_end'], 0)

    per_start = sp_pitches.groupby(['game_pk', 'game_date', 'pitcher', 'bat_team']).agg(
        k=('is_k', 'sum'), bb=('is_bb', 'sum'), hbp=('is_hbp', 'sum'),
        h=('is_h', 'sum'), outs=('outs_made', 'sum'), er=('runs_on_play', 'sum'),
    ).reset_index()
    per_start['ip'] = per_start['outs'] / 3.0
    per_start['fp'] = (per_start['k'] + per_start['ip'] * 3.3 - per_start['h']
                       - 2 * per_start['er'] - per_start['bb'] - per_start['hbp'])

    # Per-team daily cumulative bat xwOBA, prior-only (no leakage)
    sc['woba_v'] = pd.to_numeric(sc.get('woba_value'), errors='coerce')
    sc['woba_d'] = pd.to_numeric(sc.get('woba_denom'), errors='coerce')
    xwoba = pd.to_numeric(sc.get('estimated_woba_using_speedangle'), errors='coerce')
    sc['woba_v_eff'] = sc['woba_v']
    NON_PA = {'stolen_base_2b', 'stolen_base_3b', 'stolen_base_home',
              'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
              'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
              'wild_pitch', 'passed_ball', 'balk'}
    ev_all = sc['events'].fillna('')
    sc['is_pa'] = (ev_all != '') & ~ev_all.isin(NON_PA)
    bip_with = sc['is_pa'] & ~ev_all.isin({'strikeout', 'walk', 'hit_by_pitch'}) & xwoba.notna()
    sc.loc[bip_with, 'woba_v_eff'] = xwoba[bip_with]

    team_daily = (sc[sc['is_pa']]
                  .groupby(['bat_team', 'game_date'])
                  .agg(pa=('is_pa', 'sum'), wv=('woba_v_eff', 'sum'),
                       wd=('woba_d', 'sum'))
                  .reset_index().sort_values(['bat_team', 'game_date']))
    team_daily['cum_wv'] = team_daily.groupby('bat_team')['wv'].cumsum()
    team_daily['cum_wd'] = team_daily.groupby('bat_team')['wd'].cumsum()
    team_daily['cum_pa'] = team_daily.groupby('bat_team')['pa'].cumsum()
    team_daily['cum_wv_prior'] = team_daily.groupby('bat_team')['cum_wv'].shift(1)
    team_daily['cum_wd_prior'] = team_daily.groupby('bat_team')['cum_wd'].shift(1)
    team_daily['cum_pa_prior'] = team_daily.groupby('bat_team')['cum_pa'].shift(1)
    team_daily['xwoba_prior'] = team_daily['cum_wv_prior'] / team_daily['cum_wd_prior']
    league_mu = float(team_daily['xwoba_prior'].dropna().mean())
    team_daily['bat_index_prior'] = team_daily['xwoba_prior'] / league_mu

    per_start = per_start.merge(
        team_daily[['bat_team', 'game_date', 'bat_index_prior', 'cum_pa_prior']],
        on=['bat_team', 'game_date'], how='left')
    per_start = per_start[per_start['cum_pa_prior'] >= 200].dropna(subset=['bat_index_prior'])

    cor = per_start['bat_index_prior'].corr(per_start['fp'])
    print(f'n starts:                {len(per_start)}')
    print(f'cor(opp bat_index, FP):  {cor:+.4f}   (negative expected)')
    print()
    per_start['bucket'] = pd.qcut(per_start['bat_index_prior'], q=5,
                                  labels=['Very Weak', 'Weak', 'Avg', 'Strong', 'Very Strong'])
    print('FP/start by opponent-strength bucket:')
    print(per_start.groupby('bucket', observed=False)['fp'].agg(['mean', 'std', 'count'])
          .round(2).to_string())
    swing = per_start.groupby('bucket', observed=False)['fp'].mean()
    print()
    print(f'Swing (Very Weak − Very Strong opp): {swing.iloc[0] - swing.iloc[-1]:+.2f} FP/start')
    print()
    return cor


# ───────────────────────────────────────────────────────────────────────────
# 2) Confidence-interval calibration
# ───────────────────────────────────────────────────────────────────────────
def test_ci_calibration():
    print('=' * 72)
    print('TEST 2: Are residual-based CIs calibrated? (LOO)')
    print('=' * 72)
    for tag, model_path, fn_loo in [
        ('RH3', 'data/models/xfp_rh3_pipeline.pkl', _ci_calibration_rh3),
        ('RP3', 'data/models/xfp_rp3_pipeline.pkl', _ci_calibration_rp3),
    ]:
        bundle = joblib.load(Path('c:/Users/Joshua/plv_clone') / model_path)
        feats = bundle['features']
        pop_to = bundle['pop_means_to']
        pop_l21 = bundle['pop_means_last21']
        ci_table = bundle['ci_table']
        pred_buckets = {int(k): np.array(v) for k, v in bundle['pred_buckets'].items()}
        overall_sigma = bundle['overall_sigma']
        result = fn_loo(feats, pop_to, pop_l21, ci_table, pred_buckets, overall_sigma)
        print(f'\n{tag}:')
        print(f'  in-band rate (p25–p75 should be ~50%): {result["in_band"]:.1%}')
        print(f'  empirical residual std vs predicted sigma: '
              f'{result["emp_std"]:.4f} vs {result["mean_sigma"]:.4f}  '
              f'({"under-confident" if result["emp_std"] < result["mean_sigma"]*0.9 else "over-confident" if result["emp_std"] > result["mean_sigma"]*1.1 else "calibrated"})')


def _build_features_rh3(rolling, prior_table, multiyr, pop_to, pop_l21):
    from xfp_rh3_pipeline import (apply_shrinkage, SHRINK_SPEC_TO, SHRINK_SPEC_LAST21,
                                  _ensure_derived_denoms)
    rolling = rolling.merge(prior_table, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff'] = rolling['prior_pa_eff'].fillna(0.0)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling[col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)
    return rolling


def _ci_calibration_rh3(feats, pop_to, pop_l21, ci_table, pred_buckets, overall_sigma):
    import sys
    sys.path.insert(0, 'c:/Users/Joshua/plv_clone/scripts/xfp')
    from xfp_rh3_pipeline import build_prior_table, TARGET, EVAL_PA_MIN, ROS_PA_MIN, TRAIN_YEARS
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    rolling = pd.read_csv(CACHE / 'rolling_hitters_2018_2026.csv')
    multiyr = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = _build_features_rh3(rolling, prior, multiyr, pop_to, pop_l21)

    sub = rolling.dropna(subset=feats + [TARGET]).copy()
    sub = sub[(sub['pa_to'] >= EVAL_PA_MIN) & (sub['ros_pa'] >= ROS_PA_MIN)
              & (sub['year'] != 2020)]

    in_band = 0; total = 0; emp_resid = []; sigmas = []
    for held in TRAIN_YEARS:
        train = sub[sub['year'] != held]; test = sub[sub['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        actuals = test[TARGET].values
        for pred, act, split in zip(preds, actuals, test['split_day'].values):
            split = int(split)
            if split in pred_buckets:
                cuts = pred_buckets[split]
                q = int(np.searchsorted(cuts, pred))
                q = min(max(q, 0), len(cuts))
                sigma = ci_table.get((split, q), overall_sigma)
            else:
                sigma = overall_sigma
            Z = 0.6745
            p25 = pred - Z * sigma; p75 = pred + Z * sigma
            if p25 <= act <= p75:
                in_band += 1
            total += 1
            emp_resid.append(act - pred)
            sigmas.append(sigma)
    return {'in_band': in_band/max(total,1),
            'emp_std': float(np.std(emp_resid)),
            'mean_sigma': float(np.mean(sigmas))}


def _ci_calibration_rp3(feats, pop_to, pop_l21, ci_table, pred_buckets, overall_sigma):
    import sys
    sys.path.insert(0, 'c:/Users/Joshua/plv_clone/scripts/xfp')
    from xfp_rp3_pipeline import (build_prior_table, TARGET, EVAL_GS_MIN, ROS_GS_MIN,
                                  TRAIN_YEARS, apply_shrinkage,
                                  SHRINK_SPEC_TO, SHRINK_SPEC_LAST21)
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    rolling = pd.read_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
    multiyr = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    il = pd.read_csv(CACHE / 'il_split_features_2018_2026.csv')
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff'] = rolling['prior_gs_eff'].fillna(0.0)
    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to'] = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split'] = rolling['is_on_il_at_split'].fillna(0).astype(int)
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling[col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(rolling['fp_per_start_to'])

    sub = rolling.dropna(subset=feats + [TARGET]).copy()
    sub = sub[(sub['gs_to'] >= EVAL_GS_MIN) & (sub['ros_gs'] >= ROS_GS_MIN)
              & (sub['year'] != 2020)]
    in_band = 0; total = 0; emp_resid = []; sigmas = []
    for held in TRAIN_YEARS:
        train = sub[sub['year'] != held]; test = sub[sub['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        actuals = test[TARGET].values
        for pred, act, split in zip(preds, actuals, test['split_day'].values):
            split = int(split)
            if split in pred_buckets:
                cuts = pred_buckets[split]
                q = int(np.searchsorted(cuts, pred))
                q = min(max(q, 0), len(cuts))
                sigma = ci_table.get((split, q), overall_sigma)
            else:
                sigma = overall_sigma
            Z = 0.6745
            p25 = pred - Z * sigma; p75 = pred + Z * sigma
            if p25 <= act <= p75:
                in_band += 1
            total += 1
            emp_resid.append(act - pred)
            sigmas.append(sigma)
    return {'in_band': in_band/max(total,1),
            'emp_std': float(np.std(emp_resid)),
            'mean_sigma': float(np.mean(sigmas))}


# ───────────────────────────────────────────────────────────────────────────
# 3) Recency form gap signal
# ───────────────────────────────────────────────────────────────────────────
def test_recency_form_signal():
    print('\n' + '=' * 72)
    print('TEST 3: Does recency_form_gap predict next-window outcome?')
    print('=' * 72)
    rolling = pd.read_csv(CACHE / 'rolling_hitters_2018_2026.csv')
    rolling = rolling.dropna(subset=['xwoba_per_pa_to', 'xwoba_per_pa_last21',
                                     'ros_full_fp_per_pa', 'pa_to', 'pa_last21'])
    rolling = rolling[(rolling['pa_to'] >= 50) & (rolling['ros_pa'] >= 100)
                      & (rolling['year'] != 2020)]
    rolling['recency_gap'] = rolling['xwoba_per_pa_last21'] - rolling['xwoba_per_pa_to']
    rolling['baseline_pred'] = rolling['xwoba_per_pa_to'] * 1.4  # rough RoS scaling
    rolling['ros_residual'] = rolling['ros_full_fp_per_pa'] - rolling['baseline_pred']
    cor = rolling['recency_gap'].corr(rolling['ros_residual'])
    print(f'n: {len(rolling)}')
    print(f'cor(recency_gap, ros_residual_vs_naive_baseline) = {cor:+.4f}')
    print('  Bucketize by recency_gap quintile:')
    rolling['gap_bucket'] = pd.qcut(rolling['recency_gap'], q=5,
                                    labels=['Very Cold','Cold','Avg','Hot','Very Hot'])
    print(rolling.groupby('gap_bucket', observed=False)
          .agg(mean_ros_fp=('ros_full_fp_per_pa', 'mean'),
               n=('batter', 'count')).round(4).to_string())


# ───────────────────────────────────────────────────────────────────────────
# 4) Replacement-delta sanity
# ───────────────────────────────────────────────────────────────────────────
def test_replacement_delta_sanity():
    print('\n' + '=' * 72)
    print('TEST 4: Replacement-delta distribution + position breakdown')
    print('=' * 72)
    rh3 = pd.read_csv('c:/Users/Joshua/plv_clone/data/outputs/xfp_rh3_projections.csv')
    rp3 = pd.read_csv('c:/Users/Joshua/plv_clone/data/outputs/xfp_rp3_projections.csv')
    print('Hitter Δ Repl by signal:')
    print(rh3.groupby('signal')['replacement_delta'].agg(['mean','min','max','count']).round(4).to_string())
    print()
    print('Hitter signal counts by primary_position:')
    print(rh3.groupby(['primary_position', 'signal']).size().unstack(fill_value=0).to_string())
    print()
    print('Pitcher signal counts:')
    print(rp3['signal'].value_counts().to_string())


def main():
    test_schedule_strength_signal()
    test_ci_calibration()
    test_recency_form_signal()
    test_replacement_delta_sanity()


if __name__ == '__main__':
    main()
