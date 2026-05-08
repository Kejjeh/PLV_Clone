"""sp_stratified_diagnostic.py — does V12/RP3 underperform on rotation-change SPs?

Checks whether the existing SP RoS model (RP3) has degraded accuracy on the
cohort of pitchers experiencing mid-season role/rotation change. If yes,
similar role-usage features (analog of RP-RS2's gf_pct_to / sv_per_g_to)
might help SPs too. If no, SP role is stable enough that the existing model
captures it.

Cohort definition: SPs whose current-year GS pace differs from prior-year
GS pace by >= 0.10 GS/team_game (e.g., a pitcher who started 30% of his team's
games last year but only 15% this year — IL/demotion case).
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
ROLLING_CSV = ROOT / 'data/research/xfp_cache/rolling_pitchers_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data/research/xfp_cache/sp_multiyr_2015_2025.csv'

# Reuse RP3 setup
import sys
sys.path.insert(0, str(ROOT / 'scripts/xfp'))
from xfp_rp3_pipeline import (
    RP3_FEATS, TARGET, EVAL_GS_MIN, ROS_GS_MIN, TRAIN_YEARS,
    SHRINK_SPEC_TO, SHRINK_SPEC_LAST21,
    apply_shrinkage, build_prior_table, compute_population_means
)


def cross_year_eval(df, feats, subset_mask=None):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN) & (df['year'] != 2020)]
    preds_all, acts_all, test_indices = [], [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
        test_indices.extend(test.index.tolist())
    if subset_mask is not None:
        preds_arr = np.array(preds_all); acts_arr = np.array(acts_all)
        idx_arr = np.array(test_indices)
        keep = subset_mask.reindex(idx_arr).fillna(False).values
        preds_arr = preds_arr[keep]; acts_arr = acts_arr[keep]
        if len(preds_arr) < 30:
            return {'r': np.nan, 'mae': np.nan, 'n': len(preds_arr)}
        r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
        mae = float(np.mean(np.abs(preds_arr - acts_arr)))
        return {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(preds_arr)}
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return {'r': round(overall_r, 4), 'mae': round(overall_mae, 4), 'n': len(preds_all)}


def main():
    print('=== SP V12/RP3 stratified diagnostic ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)

    # Rebuild RP3 features (Marcel prior + shrinkage + IL)
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff']       = rolling['prior_gs_eff'].fillna(0.0)

    il = pd.read_csv(ROOT / 'data/research/xfp_cache/il_split_features_2018_2026.csv')
    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to'] = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split'] = rolling['is_on_il_at_split'].fillna(0).astype(int)
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)

    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling[col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(rolling['fp_per_start_to'])

    # Define rotation-change cohort:
    # gs_per_split_to = gs_to / approximate team games (approx split_day * 0.6 game/day)
    rolling['team_games_est'] = rolling['split_day'] * 0.6
    rolling['gs_pace_to'] = rolling['gs_to'] / rolling['team_games_est'].replace(0, np.nan)
    # Prior-year GS pace: gs_lag1 / 162 games
    multiyr_lag = multiyr[['pitcher','year','gs']].copy()
    multiyr_lag['gs_pace_lag1'] = multiyr_lag['gs'] / 162.0
    multiyr_lag['year_target'] = multiyr_lag['year'] + 1
    rolling = rolling.merge(multiyr_lag[['pitcher','year_target','gs_pace_lag1']],
                            left_on=['pitcher','year'], right_on=['pitcher','year_target'],
                            how='left').drop(columns=['year_target'], errors='ignore')

    rolling['rotation_change'] = (
        rolling['gs_pace_lag1'].notna() &
        ((rolling['gs_pace_to'] - rolling['gs_pace_lag1']).abs() >= 0.10)
    )

    print(f'\nTotal SP rolling rows: {len(rolling)}')
    print(f'Rotation-change subset (|gs_pace_to − gs_pace_lag1| >= 0.10): {rolling["rotation_change"].sum()}')
    print(f'  fraction: {100*rolling["rotation_change"].mean():.1f}%')

    print('\n--- RP3 cross-year r — full vs rotation-change subset ---')
    overall = cross_year_eval(rolling, RP3_FEATS)
    sub = cross_year_eval(rolling, RP3_FEATS, subset_mask=rolling['rotation_change'])
    stable = cross_year_eval(rolling, RP3_FEATS, subset_mask=~rolling['rotation_change'])
    print(f'  Overall:                   r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')
    print(f'  Rotation-change subset:    r={sub["r"]}     mae={sub["mae"]}     n={sub["n"]}')
    print(f'  Stable (non-change):       r={stable["r"]}  mae={stable["mae"]}  n={stable["n"]}')

    gap = overall["r"] - sub["r"]
    print(f'\n  r gap (Overall − Rotation-change): {gap:+.4f}')
    if gap < 0.05:
        print('  → Existing RP3 features adequately handle rotation-change cases.')
        print('    No action needed; SP role is stable enough that prior features capture it.')
    else:
        print('  → Significant degradation on rotation-change subset.')
        print('    Consider adding gs_pace_to / rotation_status features (analog of RP-RS2 work).')


if __name__ == '__main__':
    main()
