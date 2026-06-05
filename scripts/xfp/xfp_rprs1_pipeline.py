"""xfp_rprs1_pipeline.py — in-season RoS RP model.

Predicts year-T full-season FP total from a (RP, year, split_day) snapshot.
Rest-of-Season FP = predicted_full_year - actual_to_date_fp_from_API.

Architecture mirrors RP3/RH3:
  - In-season rate stats through cutoff (statcast)
  - Lag features from year T-1 (role / SV / HLD / fp_per_g — the role signal)
  - Year-T workload to-date (G, IP, fp_skill_to)
  - split_day (season-progression awareness)

Decision gate: LOO cross-year r >= 0.50 (RP-S1 cross-year was 0.508 without
in-season data; in-season data should add lift).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import json
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_relievers_2018_2026.csv'
COUNTING_DIR = ROOT / 'data' / 'research' / 'xfp_cache'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rprs1_pipeline.pkl'
PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rprs1_projections.csv'

TRAIN_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]  # year T (target)
TARGET = 'fp_year_total'
EVAL_G_MIN = 5            # min in-season relief appearances
RP_SLOTS_PER_TEAM = 4
N_TEAMS = 12
REPLACEMENT_RANK_RP = RP_SLOTS_PER_TEAM * N_TEAMS  # top 48 RPs

FEATS = [
    # In-season rate stats (statcast, _to suffix)
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
    'xwoba_per_pa_to', 'avg_velo_to', 'zone_pct_to', 'o_swing_pct_to',
    # In-season workload
    'g_to', 'ip_to', 'fp_skill_to',
    # Lag from prior year (role + workload)
    'role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1',
    'sv_lag1', 'hld_lag1', 'g_lag1', 'ip_lag1',
    'fp_per_g_lag1', 'fp_lag1',
    # Team role-context (added Phase RP-2 on user feedback)
    'is_team_prior_closer', 'prior_closer_on_il',
    'prior_closer_returned_recently', 'prior_closer_days_since_return',
    # Season-progression
    'split_day',
]

# Computed from rolling substrate; helpers below.
def _aggregate_rates(pitches_to_to):
    pass


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[df['year'].isin(TRAIN_YEARS) & (df['g_to'] >= EVAL_G_MIN)]
    per_year, preds_all, acts_all = {}, [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        rmse = float(np.sqrt(np.mean((preds - test[TARGET].values) ** 2)))
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'rmse': round(rmse, 4),
                          'mae': round(mae, 4), 'n': len(test)}
        preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}


def split_day_breakdown(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[df['year'].isin(TRAIN_YEARS) & (df['g_to'] >= EVAL_G_MIN)]
    by_split = {}
    for split in sorted(df['split_day'].unique()):
        sub = df[df['split_day'] == split]
        preds, acts = [], []
        for held in TRAIN_YEARS:
            train = sub[sub['year'] != held]; test = sub[sub['year'] == held]
            if len(train) < 50 or len(test) < 15:
                continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            preds.extend(pipe.predict(test[feats].values).tolist())
            acts.extend(test[TARGET].tolist())
        if preds:
            r = float(np.corrcoef(preds, acts)[0, 1])
            mae = float(np.mean(np.abs(np.array(preds) - np.array(acts))))
            by_split[int(split)] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(preds)}
    return by_split


def fit_residual_ci(df, feats):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    sub = df.dropna(subset=feats + [TARGET]).copy()
    sub = sub[sub['year'].isin(TRAIN_YEARS) & (sub['g_to'] >= EVAL_G_MIN)]
    rows = []
    for held in TRAIN_YEARS:
        train = sub[sub['year'] != held]; test = sub[sub['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        rows.append(pd.DataFrame({'pred': preds, 'actual': test[TARGET].values,
                                  'split_day': test['split_day'].values}))
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    res['resid'] = res['actual'] - res['pred']
    out = {}
    for split in sorted(res['split_day'].unique()):
        sub2 = res[res['split_day'] == split]
        if len(sub2) < 30:
            continue
        qs = pd.qcut(sub2['pred'], q=4, duplicates='drop', labels=False)
        for q in sorted(sub2.groupby(qs).groups.keys()):
            ix = (qs == q)
            sigma = float(sub2.loc[ix, 'resid'].std())
            out[(int(split), int(q))] = sigma
    overall_sigma = float(res['resid'].std())
    return out, overall_sigma


def lookup_sigma(ci_table, overall_sigma, split_day, pred, pred_buckets):
    if split_day not in pred_buckets:
        return overall_sigma
    cuts = pred_buckets[split_day]
    q = int(np.searchsorted(cuts, pred))
    q = min(max(q, 0), len(cuts))
    return ci_table.get((split_day, q), overall_sigma)


def train_final(df, feats):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [TARGET])
    train = train[train['year'].isin(TRAIN_YEARS) & (train['g_to'] >= EVAL_G_MIN)]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def main():
    print('=== xfp_rprs1_pipeline (RoS RP model) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    print(f'rolling substrate: {len(rolling)} rows')

    # Cross-year LOO eval
    print('\n--- LOO cross-year (full-year FP target, in-season + lag features) ---')
    per_year, overall = cross_year_eval(rolling, FEATS)
    for y, m in sorted(per_year.items()):
        print(f'  {y}: r={m["r"]:.4f}  mae={m["mae"]:.2f}  n={m["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    # Compare against RP-S1 (cross-year only, no in-season info) baseline r=0.508
    rps1_baseline = 0.508
    delta = overall['r'] - rps1_baseline
    print(f'\n  Δr vs RP-S1 (cross-year-only baseline 0.508): {delta:+.4f}')

    # Also compare to PRIOR RP-RS1 (without team-context features) — gate on this
    PRIOR_RPRS1_FEATS = [f for f in FEATS if f not in
                        {'is_team_prior_closer','prior_closer_on_il',
                         'prior_closer_returned_recently','prior_closer_days_since_return'}]
    _per_yr_prior, prior = cross_year_eval(rolling, PRIOR_RPRS1_FEATS)
    delta_team = overall['r'] - prior['r']
    print(f'\n--- Prior RP-RS1 baseline (no team-context features) ---')
    print(f'  Overall: r={prior["r"]}  mae={prior["mae"]}  n={prior["n"]}')
    print(f'  Δr (RP-RS2 − RP-RS1): {delta_team:+.4f}  '
          f'{"PASS" if delta_team >= 0.005 else "FAIL"}  (gate: ≥ +0.005)')
    if delta_team < 0.005:
        print('\n  Team-context features did not pass the gate. Reverting to PRIOR_RPRS1_FEATS.')
        # Reassign the feature set
        FEATS_USED = PRIOR_RPRS1_FEATS
    else:
        FEATS_USED = FEATS

    GATE = 0.50
    passed = overall['r'] >= GATE
    print(f'\n  Decision gate: r >= {GATE}  →  {"PASS" if passed else "FAIL"}')
    if not passed:
        print('  Skipping model lock — gate failed.')
        return

    # Split-day breakdown
    print('\n--- Cross-year r by split_day ---')
    by_split = split_day_breakdown(rolling, FEATS_USED)
    for split, m in sorted(by_split.items()):
        print(f'  day {split:>3}:  r={m["r"]:.4f}  mae={m["mae"]:.2f}  n={m["n"]}')

    # Residual-CI table
    ci_table, overall_sigma = fit_residual_ci(rolling, FEATS_USED)
    print(f'\n  overall sigma = {overall_sigma:.2f} FP/season')

    # Train final
    pipe, n_train = train_final(rolling, FEATS_USED)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RP-RS1 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}, '
          f'{len(FEATS_USED)} features) ---')
    print('  Top 12 coefficients:')
    for f, c in sorted(zip(FEATS_USED, coefs), key=lambda x: -abs(x[1]))[:12]:
        print(f'    {f:<22s} {c:+.4f}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        print('No 2026 rolling data.')
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['g_to'] >= EVAL_G_MIN)]
    valid = df_26.dropna(subset=FEATS_USED).copy()
    valid['xfp_full_year'] = pipe.predict(valid[FEATS_USED].values).round(1)

    # Pred-bucket cuts for sigma
    train_for_buckets = rolling.dropna(subset=FEATS_USED + [TARGET])
    train_for_buckets = train_for_buckets[
        train_for_buckets['year'].isin(TRAIN_YEARS)
        & (train_for_buckets['g_to'] >= EVAL_G_MIN)]
    train_pred = pipe.predict(train_for_buckets[FEATS_USED].values)
    pred_buckets = {}
    for split in sorted(train_for_buckets['split_day'].unique()):
        ix = (train_for_buckets['split_day'].values == split)
        if ix.sum() < 30:
            continue
        cuts = np.quantile(train_pred[ix], [0.25, 0.5, 0.75])
        pred_buckets[int(split)] = cuts

    Z25 = 0.6745
    sigmas = []
    for _, row in valid.iterrows():
        sigmas.append(lookup_sigma(ci_table, overall_sigma, latest_split,
                                   row['xfp_full_year'], pred_buckets))
    valid['xfp_sigma'] = sigmas
    valid['xfp_p25'] = (valid['xfp_full_year'] - Z25 * valid['xfp_sigma']).clip(lower=0)
    valid['xfp_p75'] = valid['xfp_full_year'] + Z25 * valid['xfp_sigma']

    # Pull current 2026 actual to-date FP from MLB API counting stats
    cnt = json.loads((COUNTING_DIR / 'pitcher_counting_stats_2026.json').read_text())
    cnt_df = pd.DataFrame(cnt)
    def parse_ip(v):
        if v is None or pd.isna(v): return np.nan
        s = str(v)
        if '.' in s:
            whole, frac = s.split('.', 1)
            return float(whole) + (1/3 if frac.startswith('1') else 2/3 if frac.startswith('2') else 0)
        return float(v)
    cnt_df['ip'] = cnt_df['inningsPitched'].map(parse_ip)
    cnt_df['fp_actual_2026'] = (
        cnt_df['strikeOuts'] + cnt_df['ip']*3.3 + cnt_df['saves']*5
        + cnt_df['holds']*2 - cnt_df['baseOnBalls'] - 2*cnt_df['earnedRuns']
        - cnt_df['hits'] - cnt_df['hitByPitch']
    ).round(1)
    cnt_df = cnt_df[['pitcher','name','saves','holds','fp_actual_2026']].rename(
        columns={'name':'name_api','saves':'sv_2026','holds':'hld_2026'})
    valid = valid.merge(cnt_df, on='pitcher', how='left')
    valid['fp_actual_2026'] = valid['fp_actual_2026'].fillna(0)
    valid['xfp_ros'] = (valid['xfp_full_year'] - valid['fp_actual_2026']).round(1)
    valid['xfp_ros_p25'] = (valid['xfp_p25'] - valid['fp_actual_2026']).round(1).clip(lower=0)
    valid['xfp_ros_p75'] = (valid['xfp_p75'] - valid['fp_actual_2026']).round(1)

    # Replacement-level: top 48 RPs by xfp_full_year
    sorted_by_total = valid.sort_values('xfp_full_year', ascending=False).reset_index(drop=True)
    if len(sorted_by_total) >= REPLACEMENT_RANK_RP:
        repl = float(sorted_by_total['xfp_full_year'].iloc[REPLACEMENT_RANK_RP - 1])
    else:
        repl = float(sorted_by_total['xfp_full_year'].median())
    valid['replacement_xfp'] = round(repl, 1)
    valid['replacement_delta'] = (valid['xfp_full_year'] - repl).round(1)

    # Composite signal
    def signal(row):
        rd = row.get('replacement_delta')
        p25 = row.get('xfp_p25')
        p75 = row.get('xfp_p75')
        rep = row.get('replacement_xfp')
        if pd.isna(rd) or pd.isna(rep): return 'hold'
        if pd.notna(p25) and p25 > rep: return 'add'
        if pd.notna(p75) and p75 < rep: return 'drop'
        return 'hold'
    valid['signal'] = valid.apply(signal, axis=1)

    valid = valid.sort_values('xfp_full_year', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': FEATS_USED,
        'features_full_pool': FEATS,
        'features_prior_baseline': PRIOR_RPRS1_FEATS,
        'team_context_delta_r': round(delta_team, 4),
        'target': TARGET,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rps1_r': rps1_baseline,
        'delta_vs_rps1': round(delta, 4),
        'per_year_r': per_year,
        'by_split_r': by_split,
        'ci_table': ci_table,
        'pred_buckets': {k: v.tolist() for k, v in pred_buckets.items()},
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'min_g_to': EVAL_G_MIN,
        'replacement_rank': REPLACEMENT_RANK_RP,
        'gate': GATE,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rprs1',
        'note': 'RoS RP model. Predicts year-T full-season FP from in-season '
                'rate stats + prior-year role/workload lag features. '
                'RoS = predicted_full_year − actual_to_date_fp_from_API.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    keep = ['rank','pitcher','name_api','role_lag1','sv_lag1','hld_lag1',
            'g_to','ip_to','sv_2026','hld_2026',
            'fp_actual_2026','xfp_full_year','xfp_p25','xfp_p75',
            'xfp_ros','xfp_ros_p25','xfp_ros_p75',
            'replacement_xfp','replacement_delta','signal']
    keep = [c for c in keep if c in valid.columns]
    valid[keep].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} 2026 RP RoS projections')

    print('\nTop 15 by projected RoS FP:')
    show = valid.sort_values('xfp_ros', ascending=False).head(15)
    cols_show = ['rank','name_api','role_lag1','g_to','sv_2026','hld_2026',
                 'fp_actual_2026','xfp_full_year','xfp_ros','signal','replacement_delta']
    print(show[cols_show].to_string(index=False))


if __name__ == '__main__':
    main()
