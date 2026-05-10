"""preseason_only_benchmark.py — predict full-year fp/PA from PRE-SEASON features only.

The strict task that public projection systems (ATC, Steamer, ZiPS, Marcel)
benchmark on: given NO in-season data, predict the season's fp/PA from prior
years' stats + age + career context.

Walk-forward setup:
  For each test year T in [2018, 2019, 2021, 2022, 2023, 2024, 2025]:
    Features computed from year T-1, T-2, T-3 only (NO leakage from year T).
    Target = fp_per_pa_actual at year T (filter to pa>=300 for stable target).
    Train Ridge on all training years < T using SAME feature construction.
    Evaluate r on year T.

Models compared:
  M0  Naive lag                : pred = Y_{T-1} fp/PA
  M1  Marcel 5/4/3             : weighted blend of Y_{T-1}, Y_{T-2}, Y_{T-3} fp/PA
  M2  Marcel + age             : Marcel + age regression term
  M3  Ridge Y_{T-1} process    : 11 process metrics from year T-1
  M4  Ridge full prior 3y      : Y_{T-1} + Y_{T-2} + Y_{T-3} process stacks
  M5  Ridge full + Marcel prior + age + career_year (kitchen sink)

Output: data/research/preseason_benchmark_results.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RES = ROOT / 'data' / 'research'

SUBSTRATE = CACHE / 'hitters_multiyr_2015_2026.csv'
TARGET = 'fp_per_pa_actual'
TEST_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
EVAL_MIN_PA = 300  # stable per-year target threshold
TRAIN_MIN_PA = 200

# Process features (year-T-1 versions etc.)
PROCESS = ['k_pct', 'bb_pct', 'swstr_pct', 'contact_pct', 'chase_pct',
           'xwoba_per_pa', 'hard_hit_pct', 'barrel_pct',
           'iso', 'hr_per_pa', 'sb_per_pa']
MARCEL_WEIGHTS = (5, 4, 3)


def build_preseason_features(df: pd.DataFrame, test_year: int) -> pd.DataFrame:
    """For each batter eligible at year T, build pre-season features from T-1/T-2/T-3.
    Returns DataFrame indexed by batter with feature cols + target."""
    # Year T target row
    yT = df[df['year'] == test_year].copy()
    yT = yT[yT['pa'] >= EVAL_MIN_PA]
    if yT.empty:
        return pd.DataFrame()

    # Year T-1 stack
    yT1 = df[df['year'] == test_year - 1]
    yT2 = df[df['year'] == test_year - 2]
    yT3 = df[df['year'] == test_year - 3]
    # Skip 2020 (shortened): if T-1 is 2020, shift back one year
    if test_year - 1 == 2020:
        yT1 = df[df['year'] == test_year - 2]; yT2 = df[df['year'] == test_year - 3]; yT3 = df[df['year'] == test_year - 4]
    if test_year - 2 == 2020:
        yT2 = df[df['year'] == test_year - 3]; yT3 = df[df['year'] == test_year - 4]
    if test_year - 3 == 2020:
        yT3 = df[df['year'] == test_year - 4]

    # Build prior-1 features
    p1 = yT1.set_index('batter')[['pa'] + PROCESS + [TARGET]].add_prefix('Y1_')
    p2 = yT2.set_index('batter')[['pa'] + PROCESS + [TARGET]].add_prefix('Y2_')
    p3 = yT3.set_index('batter')[['pa'] + PROCESS + [TARGET]].add_prefix('Y3_')

    # Age info (from year T's row — that's "deterministic given DOB", safe)
    # Use age_bat from any year — assume linear age progression
    # We don't actually have age in hitters_multiyr; use hitter_age_career.csv
    age_path = ROOT / 'data' / 'outputs' / 'hitter_age_career.csv'
    if age_path.exists():
        age_df = pd.read_csv(age_path)
        age_yT = age_df[age_df['year'] == test_year].set_index('batter')[['age', 'career_year']]
    else:
        age_yT = pd.DataFrame()

    merged = yT.set_index('batter')[[TARGET]].rename(columns={TARGET: 'target_fp_per_pa'})
    merged = merged.join(p1, how='inner')  # require Y_{T-1} to exist
    merged = merged.join(p2, how='left')
    merged = merged.join(p3, how='left')
    if not age_yT.empty:
        merged = merged.join(age_yT, how='left')

    # Marcel-blended prior (using whichever priors exist; PA-weighted)
    marcel_num = 0.0
    marcel_denom = 0.0
    for w, p_prefix in zip(MARCEL_WEIGHTS, ['Y1_', 'Y2_', 'Y3_']):
        fp = merged[p_prefix + TARGET]
        pa = merged[p_prefix + 'pa']
        eff = w * pa.fillna(0)
        marcel_num = marcel_num + (fp * eff).fillna(0)
        marcel_denom = marcel_denom + eff.fillna(0)
    # Add regression: 100 PA at league mean
    league_mean = float(yT[TARGET].mean())
    merged['marcel_prior'] = (marcel_num + 100 * league_mean) / (marcel_denom + 100)

    # Per-feature Marcel: weighted prior for each process stat
    for col in PROCESS:
        num = 0.0; denom = 0.0
        for w, p_prefix in zip(MARCEL_WEIGHTS, ['Y1_', 'Y2_', 'Y3_']):
            v = merged[p_prefix + col]
            pa = merged[p_prefix + 'pa']
            eff = w * pa.fillna(0)
            num = num + (v * eff).fillna(0)
            denom = denom + eff.fillna(0)
        merged[f'marcel_{col}'] = num / denom.replace(0, np.nan)

    merged = merged.reset_index()
    merged['test_year'] = test_year
    return merged


def fit_eval(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> tuple[float, float]:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = train.dropna(subset=feats + ['target_fp_per_pa'])
    test = test.dropna(subset=feats + ['target_fp_per_pa'])
    if len(train) < 50 or len(test) < 20:
        return np.nan, np.nan
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe.fit(train[feats].values, train['target_fp_per_pa'].values)
    pred = pipe.predict(test[feats].values)
    r = float(np.corrcoef(pred, test['target_fp_per_pa'].values)[0, 1])
    mae = float(np.mean(np.abs(pred - test['target_fp_per_pa'].values)))
    return r, mae


def naive_eval(test: pd.DataFrame, pred_col: str) -> tuple[float, float]:
    test = test.dropna(subset=[pred_col, 'target_fp_per_pa'])
    if len(test) < 20:
        return np.nan, np.nan
    r = float(np.corrcoef(test[pred_col], test['target_fp_per_pa'])[0, 1])
    mae = float(np.mean(np.abs(test[pred_col] - test['target_fp_per_pa'])))
    return r, mae


def main():
    RES.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SUBSTRATE)
    df = df[df['pa'] >= TRAIN_MIN_PA].copy()
    print(f'Substrate: {len(df)} batter-year rows, {df["year"].min()}-{df["year"].max()}')

    # Build per-test-year feature DataFrame
    yearly = []
    for ty in TEST_YEARS:
        feat_df = build_preseason_features(df, ty)
        if feat_df.empty:
            continue
        yearly.append(feat_df)
    full = pd.concat(yearly, ignore_index=True)
    print(f'Built {len(full)} batter-test-year rows')

    # Define candidate feature lists
    Y1_FEATS = [f'Y1_{c}' for c in PROCESS + ['pa']] + [f'Y1_{TARGET}']
    Y2_FEATS = [f'Y2_{c}' for c in PROCESS + ['pa']]
    Y3_FEATS = [f'Y3_{c}' for c in PROCESS + ['pa']]
    MARCEL_FEATS = ['marcel_prior'] + [f'marcel_{c}' for c in PROCESS]
    AGE_FEATS = ['age', 'career_year']

    rows = []
    for ty in TEST_YEARS:
        train = full[full['test_year'] != ty]
        test = full[full['test_year'] == ty]
        if len(test) < 20:
            continue
        print(f'\n=== Test year {ty} (n_test={len(test)}, n_train={len(train)}) ===')

        # M0: naive lag (use prior-1 fp/PA directly)
        r, mae = naive_eval(test, f'Y1_{TARGET}')
        print(f'  M0 naive lag (Y1 fp/PA)           : r={r:.4f}  mae={mae:.4f}')
        rows.append({'test_year': ty, 'model': 'M0_naive_lag', 'r': r, 'mae': mae, 'n': len(test)})

        # M1: Marcel 5/4/3 blend
        r, mae = naive_eval(test, 'marcel_prior')
        print(f'  M1 Marcel 5/4/3 blend             : r={r:.4f}  mae={mae:.4f}')
        rows.append({'test_year': ty, 'model': 'M1_marcel', 'r': r, 'mae': mae, 'n': len(test)})

        # M2: Marcel + age (Ridge)
        feats_m2 = ['marcel_prior'] + (AGE_FEATS if AGE_FEATS[0] in full.columns else [])
        r, mae = fit_eval(train, test, feats_m2)
        print(f'  M2 Marcel + age (Ridge)           : r={r:.4f}  mae={mae:.4f}')
        rows.append({'test_year': ty, 'model': 'M2_marcel_age', 'r': r, 'mae': mae, 'n': len(test)})

        # M3: Y_{T-1} process Ridge
        r, mae = fit_eval(train, test, Y1_FEATS)
        print(f'  M3 Ridge Y_T-1 process            : r={r:.4f}  mae={mae:.4f}')
        rows.append({'test_year': ty, 'model': 'M3_ridge_Y1', 'r': r, 'mae': mae, 'n': len(test)})

        # M4: Y_{T-1} + Y_{T-2} + Y_{T-3} stacked Ridge
        feats_m4 = Y1_FEATS + Y2_FEATS + Y3_FEATS
        r, mae = fit_eval(train, test, feats_m4)
        print(f'  M4 Ridge Y_T-1 + T-2 + T-3        : r={r:.4f}  mae={mae:.4f}')
        rows.append({'test_year': ty, 'model': 'M4_ridge_Y123', 'r': r, 'mae': mae, 'n': len(test)})

        # M5: Kitchen sink (everything)
        feats_m5 = Y1_FEATS + Y2_FEATS + Y3_FEATS + MARCEL_FEATS
        if AGE_FEATS[0] in full.columns:
            feats_m5 += AGE_FEATS
        r, mae = fit_eval(train, test, feats_m5)
        print(f'  M5 Ridge kitchen sink             : r={r:.4f}  mae={mae:.4f}')
        rows.append({'test_year': ty, 'model': 'M5_ridge_kitchen_sink', 'r': r, 'mae': mae, 'n': len(test)})

    out = pd.DataFrame(rows)
    out.to_csv(RES / 'preseason_benchmark_results.csv', index=False)

    print('\n' + '=' * 70)
    print('AVERAGE r ACROSS TEST YEARS')
    print('=' * 70)
    avg = out.groupby('model').agg(r_mean=('r', 'mean'),
                                    r_std=('r', 'std'),
                                    mae_mean=('mae', 'mean'),
                                    n_test=('r', 'count')).reset_index()
    avg = avg.sort_values('r_mean', ascending=False)
    for _, r in avg.iterrows():
        print(f'  {r["model"]:<26s} r={r["r_mean"]:.4f} ± {r["r_std"]:.4f}  '
              f'mae={r["mae_mean"]:.4f}  (n_years={r["n_test"]})')


if __name__ == '__main__':
    main()
