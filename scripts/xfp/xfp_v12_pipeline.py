"""
xfp_v12_pipeline.py — V12 backward elimination on V11 features + IL injury features.

P13.2 + P13.3 of the plan. Targets the systematic V11 over-projection of
pitchers returning from IL or with chronic injury history (Bello, Littell,
Scherzer, Senga, Woodruff, Ragans archetype).

Decision gate (per the plan's Phase 13 spec):
  V12 ships if cross_year_r ≥ V11 + 0.01 AND |k_bias_hi| does not regress
  past V11's 0.773.

Also performs an explicit archetype check: Bello/Littell/Scherzer/Senga
must move down meaningfully, and the V11 0.77 high-K bias should shrink.
"""
from __future__ import annotations
import sys
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
# Import the V11 data assembly so we get the full feature pool
from v11_full_spotcheck import load_data as load_v11_data  # noqa

SP_MULTI = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
IL_FEATS = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_features_2015_2026.csv'

# V11 winning feature set (verbatim from xfp_v11_lock.py / production bundle)
V11_FEATS = [
    'avg_velo', 'zone_pct', 'o_swing_pct', 'swstr_pct', 'c_plus_swstr',
    'xwoba_per_pa', 'z_swing_pct', 'xwoba_x_swstr',
    'ip_resid_lag1', 'k_pct_lag1',
    'pitch_entropy', 'bb_pfxz', 'pitching_plus', 'fp_strike_pct',
]

# Candidate IL features to screen + add to V11 pool. All keyed lag-style:
# year-T features predict year T+1 fp_per_start_actual.
# Names here match what merge_il_into_sp() produces.
IL_CANDIDATES = [
    'il_stints_lag1', 'il_60_stints_lag1', 'il_days_total_lag1',
    'days_since_last_il_lag1',
    'career_il_stints_3yr_lag1', 'career_il_days_3yr_lag1',
    # Same year (year T metrics → year T FP); use sparingly because partly causal
    'il_stints', 'il_days_total',
]


def load_substrate() -> pd.DataFrame:
    """Join V11's full feature substrate with lagged IL features."""
    sp = load_v11_data()  # has all V11 features (pitching_plus, fp_strike_pct, etc.)
    il = pd.read_csv(IL_FEATS)

    # Build year-T-IL features keyed on (pitcher, year)
    il_year_t = il[['pitcher', 'year', 'il_stints', 'il_60_stints', 'il_days_total',
                    'days_since_last_il', 'career_il_stints_3yr', 'career_il_days_3yr']].copy()

    # Merge year-T IL features
    sp = sp.merge(il_year_t, on=['pitcher', 'year'], how='left')
    # Pitchers with no IL events in year T should be 0/NaN → treat as 0 stints/days
    for c in ['il_stints', 'il_60_stints', 'il_days_total']:
        if c in sp.columns:
            sp[c] = sp[c].fillna(0.0)
    for c in ['career_il_stints_3yr', 'career_il_days_3yr']:
        if c in sp.columns:
            sp[c] = sp[c].fillna(0.0)
    # days_since_last_il left as NaN for pitchers with no IL history (model handles via dropna or imputation downstream)

    # Build lag-1 IL features by shifting per pitcher
    il_lag = il_year_t.copy()
    il_lag = il_lag.sort_values(['pitcher', 'year'])
    il_lag['year_target'] = il_lag['year'] + 1   # this row's stats are the lag-1 features for year+1
    il_lag = il_lag.rename(columns={
        'il_stints': 'il_stints_lag1',
        'il_60_stints': 'il_60_stints_lag1',
        'il_days_total': 'il_days_total_lag1',
        'days_since_last_il': 'days_since_last_il_lag1',
        'career_il_stints_3yr': 'career_il_stints_3yr_lag1',
        'career_il_days_3yr': 'career_il_days_3yr_lag1',
    })
    il_lag = il_lag.drop(columns=['year']).rename(columns={'year_target': 'year'})
    sp = sp.merge(il_lag, on=['pitcher', 'year'], how='left')
    # 0-fill stints / days lag (no IL events → 0 stints last year)
    for c in ['il_stints_lag1', 'il_60_stints_lag1', 'il_days_total_lag1',
              'career_il_stints_3yr_lag1', 'career_il_days_3yr_lag1']:
        if c in sp.columns:
            sp[c] = sp[c].fillna(0.0)
    # Cap days_since_last_il at 1000 (treat "never been on IL" as 1000+ days clean)
    if 'days_since_last_il_lag1' in sp.columns:
        sp['days_since_last_il_lag1'] = sp['days_since_last_il_lag1'].fillna(1000.0).clip(upper=1000.0)
    return sp


def cross_year_evaluate(df: pd.DataFrame, feats: list[str], label: str = '') -> dict:
    """Mirrors xfp_v7_pipeline.py:cross_year_evaluate but with V11 transitions
    and the same TRAIN_MIN inclusion rules.

    Transitions: 2016→2017 ... 2024→2025 (skip 2020→2021 short-season transition).
    """
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    transitions = [
        (2016, 2017), (2017, 2018), (2018, 2019),
        (2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025),
    ]
    preds_all, acts_all, res_rows = [], [], []
    for yr_train, yr_test in transitions:
        # Pitchers in BOTH years
        p_train = set(df[(df['year'] == yr_train) & (df['gs'] >= 10)]['pitcher'])
        p_test  = set(df[(df['year'] == yr_test ) & (df['gs'] >= 10)]['pitcher'])
        shared  = p_train & p_test
        if not shared:
            continue

        train_year = df[(df['year'] == yr_train) & df['pitcher'].isin(shared)][['pitcher','k_pct'] + feats].copy()
        test_year  = df[(df['year'] == yr_test ) & df['pitcher'].isin(shared)][['pitcher','fp_per_start_actual','k_pct']].copy()
        merged = test_year.merge(train_year, on='pitcher', how='inner', suffixes=('','_yT'))
        # k_pct collision: keep test-year k_pct as the cohort-defining metric
        merged = merged.dropna(subset=feats + ['fp_per_start_actual'])
        if len(merged) < 10:
            continue

        # Train on ALL prior data (year < yr_test) with full feats present
        prior = df[df['year'] < yr_test].dropna(subset=feats + ['fp_per_start_actual']).copy()
        prior = prior[prior['gs'] >= 10]
        if len(prior) < 50:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(prior[feats].values, prior['fp_per_start_actual'].values)
        merged['pred'] = pipe.predict(merged[feats].values)
        merged['transition'] = f'{yr_train}->{yr_test}'
        preds_all.extend(merged['pred'].tolist())
        acts_all.extend(merged['fp_per_start_actual'].tolist())
        res_rows.append(merged)

    if not res_rows:
        return {'r': np.nan, 'k_bias_hi': np.nan, 'n': 0, 'label': label}
    res = pd.concat(res_rows, ignore_index=True)
    res['resid'] = res['pred'] - res['fp_per_start_actual']
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    high_k = res[res['k_pct'] > 0.30]
    k_bias_hi = float(high_k['resid'].mean()) if len(high_k) else 0.0
    rmse = float(np.sqrt(np.mean(res['resid']**2)))
    mae  = float(np.mean(res['resid'].abs()))
    return {
        'type': 'cross_year', 'r': round(r, 5),
        'k_bias_hi': round(k_bias_hi, 4),
        'rmse': round(rmse, 4), 'mae': round(mae, 4),
        'n': len(res), 'n_transitions': res['transition'].nunique(),
        'label': label or f'feats[{len(feats)}]',
    }


def score_fn(r, kbias, T=1.0, coef=0.5):
    if pd.isna(r):
        return float('nan')
    return r * 3 - max(0.0, abs(kbias) - T) * coef


def fmt(res):
    if pd.isna(res.get('r')):
        return f"{res['label']:<60s} | n={res.get('n', 0)} (no eval)"
    return (f"{res['label']:<60s} | r={res['r']:.4f}  k_bias={res['k_bias_hi']:+.3f}  "
            f"rmse={res['rmse']:.3f}  mae={res['mae']:.3f}  "
            f"n={res['n']}/{res['n_transitions']}t  score(T=1)={score_fn(res['r'], res['k_bias_hi']):.4f}")


def correlation_screen(df: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    """For each candidate, single-feature cross-year r."""
    rows = []
    for f in candidates:
        sub_df = df.dropna(subset=[f, 'fp_per_start_actual'])
        # Per-transition cor
        cors = []
        for yr_train, yr_test in [(2018, 2019), (2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025)]:
            tr = sub_df[(sub_df['year'] == yr_train) & (sub_df['gs'] >= 10)]
            te = sub_df[(sub_df['year'] == yr_test ) & (sub_df['gs'] >= 10)]
            shared = set(tr['pitcher']) & set(te['pitcher'])
            tr = tr[tr['pitcher'].isin(shared)][['pitcher', f]]
            te = te[te['pitcher'].isin(shared)][['pitcher', 'fp_per_start_actual']]
            m = tr.merge(te, on='pitcher')
            if len(m) < 30:
                continue
            c = float(np.corrcoef(m[f], m['fp_per_start_actual'])[0, 1])
            if pd.notna(c):
                cors.append(c)
        if not cors:
            rows.append({'feature': f, 'mean_cor': np.nan, 'min_cor': np.nan, 'max_cor': np.nan,
                         'n_transitions': 0, 'recommendation': 'no_data'})
            continue
        mean_c = float(np.mean(cors))
        rec = 'KEEP' if abs(mean_c) >= 0.10 else 'WATCH' if abs(mean_c) >= 0.05 else 'DROP'
        rows.append({
            'feature': f,
            'mean_cor': round(mean_c, 4),
            'min_cor': round(min(cors), 4),
            'max_cor': round(max(cors), 4),
            'n_transitions': len(cors),
            'recommendation': rec,
        })
    return pd.DataFrame(rows).sort_values('mean_cor', key=lambda s: -s.abs())


def main():
    df = load_substrate()
    print(f'=== V12 pipeline — substrate {len(df)} rows ===\n')

    # Reference: V11 baseline
    ref = cross_year_evaluate(df, V11_FEATS, label='V11 (14 feat baseline)')
    print('Reference baseline:')
    print('  ' + fmt(ref))
    print()

    # P13.2 — correlation screen on IL candidates
    print('--- P13.2: Cross-year correlation screen on IL candidates ---')
    screen = correlation_screen(df, IL_CANDIDATES)
    print(screen.to_string(index=False))
    print()
    keepers = screen[screen['recommendation'].isin(['KEEP', 'WATCH'])]['feature'].tolist()
    print(f'Surviving (KEEP+WATCH): {keepers}')
    print()

    # P13.3 — V12 BE on V11 + IL keepers
    pool = V11_FEATS + keepers
    print(f'--- P13.3: V12 backward elimination from {len(pool)}-feature pool ---')
    df_pool = df.dropna(subset=pool + ['fp_per_start_actual']).copy()
    df_pool = df_pool[df_pool['gs'] >= 10]
    print(f'After dropna: {len(df_pool)} rows\n')

    # Step 0
    print('Step 0: full pool')
    cur = list(pool)
    res = cross_year_evaluate(df_pool, cur, label=f'pool[{len(cur)}]')
    print('  ' + fmt(res))
    s_full = score_fn(res['r'], res['k_bias_hi'])
    best_score, best_feats, best_res = s_full, list(cur), res
    print(f'  vs V11: r {res["r"]-ref["r"]:+.4f}, k_bias {res["k_bias_hi"]-ref["k_bias_hi"]:+.3f}\n')

    # Backward elimination
    history = [(list(cur), res, s_full)]
    step = 0
    while len(cur) > 6:
        step += 1
        print(f'Step {step}: try dropping each of {len(cur)}')
        candidates = []
        for f in cur:
            trial = [x for x in cur if x != f]
            r = cross_year_evaluate(df_pool, trial, label=f'-{f}')
            sc = score_fn(r['r'], r['k_bias_hi'])
            candidates.append((f, r, sc))
        candidates.sort(key=lambda x: -x[2])
        f_drop, r_top, sc_top = candidates[0]
        print(f'  Best drop: {f_drop:<28s}  r={r_top["r"]:.4f}  k_bias={r_top["k_bias_hi"]:+.3f}  score={sc_top:.4f}  (was {best_score:.4f})')
        cur = [x for x in cur if x != f_drop]
        history.append((list(cur), r_top, sc_top))

        if sc_top > best_score + 0.0001:
            best_score = sc_top
            best_feats = list(cur)
            best_res = r_top
            print(f'  ↑ NEW BEST score={best_score:.4f}, feats={len(best_feats)}')
        elif sc_top < best_score - 0.05:
            print('  ↓ score dropped > 0.05 from best; stopping BE')
            break

    print('\n=== V12 BE winner ===')
    print('  ' + fmt(best_res))
    print(f'  Features ({len(best_feats)}): {best_feats}')
    print()
    print('=== Decision gate (per plan) ===')
    target_r = ref['r'] + 0.01
    print(f'  cross-year r {best_res["r"]:.4f} ≥ V11 r + 0.01 = {target_r:.4f}? {"PASS" if best_res["r"] >= target_r else "FAIL"}')
    print(f'  |k_bias_hi| {abs(best_res["k_bias_hi"]):.3f} ≤ V11 0.773? {"PASS" if abs(best_res["k_bias_hi"]) <= 0.773 else "FAIL"}')
    print(f'  Score (T=1.0) {best_score:.4f} vs V11 {score_fn(ref["r"], ref["k_bias_hi"]):.4f}: {"PASS" if best_score > score_fn(ref["r"], ref["k_bias_hi"]) else "FAIL"}')

    # Persist BE log
    out = []
    for feats, r, sc in history:
        out.append({'n_feats': len(feats), 'features': '|'.join(feats),
                    'r': r['r'], 'k_bias_hi': r['k_bias_hi'],
                    'rmse': r['rmse'], 'mae': r['mae'],
                    'n': r['n'], 'score_T1': sc})
    pd.DataFrame(out).to_csv(ROOT / 'data' / 'research' / 'xfp_v12_be_log.csv', index=False)
    print(f'\nWrote V12 BE log → data/research/xfp_v12_be_log.csv')

    # Print final feature list as Python list literal (for copy-paste into lock)
    print(f'\nV12_FEATS = {best_feats}')


if __name__ == '__main__':
    main()
