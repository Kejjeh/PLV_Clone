"""week_level_eval.py — does last-21d signal predict next-7d fp/PA?

Walk-forward validation:
  Train on rows from years <= T, evaluate on rows from year T+1.
  Transitions: 2018→2019, 2019→2021 (skip 2020), 2021→2022, ..., 2024→2025

Models compared (predict NEXT7_core_fp_per_pa):
  M0  Naive recent       : NEXT7 = L21_core_fp_per_pa
  M1  Naive talent       : NEXT7 = CTD_core_fp_per_pa
  M2  Marcel blend       : weighted (L21, CTD) — fixed 0.4/0.6 split
  M3  Ridge: career-only (CTD features) — pure talent baseline
  M4  Ridge: last21-only (L21 features) — pure leading indicators
  M5  Ridge: deltas-only (DELTA_*) — pure recent-vs-career deltas
  M6  Ridge: career + last21 (combined) — kitchen sink
  M7  Ridge: career + last21 + deltas — fully kitchen sink

Reports per-model cross-year r and MAE. The key question:
  Does adding L21 leading indicators on top of CTD talent baseline (M6 vs M3)
  improve next-7d prediction r?

Output: data/research/week_level_eval_results.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

ROOT = Path('c:/Users/Joshua/plv_clone')
RES = ROOT / 'data' / 'research'

TRANSITIONS = [(2018, 2019), (2019, 2021), (2021, 2022),
               (2022, 2023), (2023, 2024), (2024, 2025)]
TARGET = 'NEXT7_core_fp_per_pa'

CTD_FEATS = [
    'CTD_pa', 'CTD_k_pct', 'CTD_bb_pct', 'CTD_swstr_pct', 'CTD_contact_pct',
    'CTD_xwoba_per_pa', 'CTD_woba_per_pa', 'CTD_xwoba_residual',
    'CTD_iso', 'CTD_hard_hit_pct', 'CTD_barrel_pct', 'CTD_hr_per_pa',
    'CTD_core_fp_per_pa',
]
L21_FEATS = [
    'L21_pa', 'L21_k_pct', 'L21_bb_pct', 'L21_swstr_pct', 'L21_contact_pct',
    'L21_xwoba_per_pa', 'L21_woba_per_pa', 'L21_xwoba_residual',
    'L21_iso', 'L21_hard_hit_pct', 'L21_barrel_pct', 'L21_hr_per_pa',
    'L21_core_fp_per_pa',
]
DELTA_FEATS = [
    'DELTA_swstr_pct', 'DELTA_contact_pct', 'DELTA_xwoba_per_pa',
    'DELTA_k_pct', 'DELTA_bb_pct', 'DELTA_hard_hit_pct', 'DELTA_barrel_pct',
]


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> tuple[float, float, np.ndarray]:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = train.dropna(subset=feats + [TARGET])
    test = test.dropna(subset=feats + [TARGET])
    if len(train) < 100 or len(test) < 30:
        return np.nan, np.nan, np.array([])
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe.fit(train[feats].values, train[TARGET].values)
    pred = pipe.predict(test[feats].values)
    r = float(np.corrcoef(pred, test[TARGET].values)[0, 1])
    mae = float(np.mean(np.abs(pred - test[TARGET].values)))
    return r, mae, pred


def evaluate_naive(train: pd.DataFrame, test: pd.DataFrame, pred_col: str) -> tuple[float, float, np.ndarray]:
    test = test.dropna(subset=[pred_col, TARGET])
    if len(test) < 30:
        return np.nan, np.nan, np.array([])
    pred = test[pred_col].values
    r = float(np.corrcoef(pred, test[TARGET].values)[0, 1])
    mae = float(np.mean(np.abs(pred - test[TARGET].values)))
    return r, mae, pred


def evaluate_marcel(train: pd.DataFrame, test: pd.DataFrame, w_l21: float = 0.4) -> tuple[float, float, np.ndarray]:
    test = test.dropna(subset=['L21_core_fp_per_pa', 'CTD_core_fp_per_pa', TARGET])
    if len(test) < 30:
        return np.nan, np.nan, np.array([])
    pred = w_l21 * test['L21_core_fp_per_pa'] + (1 - w_l21) * test['CTD_core_fp_per_pa']
    r = float(np.corrcoef(pred, test[TARGET].values)[0, 1])
    mae = float(np.mean(np.abs(pred - test[TARGET].values)))
    return r, mae, pred.values


def main():
    df = pd.read_csv(RES / 'week_level_substrate.csv')
    print(f'Loaded {len(df)} batter-eval-week rows ({df["batter"].nunique()} batters)')
    print(f'Target = {TARGET}; mean={df[TARGET].mean():.4f}, std={df[TARGET].std():.4f}\n')

    rows = []
    for yr_train_max, yr_test in TRANSITIONS:
        train = df[df['year'] <= yr_train_max].copy()
        test = df[df['year'] == yr_test].copy()
        if len(train) < 200 or len(test) < 100:
            continue
        print(f'\n=== Train ≤{yr_train_max} (n={len(train)})  →  Test {yr_test} (n={len(test)}) ===')
        models = []

        # Naive
        r, mae, _ = evaluate_naive(train, test, 'L21_core_fp_per_pa')
        models.append(('M0_naive_L21', r, mae))
        r, mae, _ = evaluate_naive(train, test, 'CTD_core_fp_per_pa')
        models.append(('M1_naive_CTD', r, mae))
        r, mae, _ = evaluate_marcel(train, test)
        models.append(('M2_marcel_blend', r, mae))

        # Ridge models
        r, mae, _ = fit_predict(train, test, CTD_FEATS)
        models.append(('M3_ridge_CTD', r, mae))
        r, mae, _ = fit_predict(train, test, L21_FEATS)
        models.append(('M4_ridge_L21', r, mae))
        r, mae, _ = fit_predict(train, test, DELTA_FEATS)
        models.append(('M5_ridge_DELTA', r, mae))
        r, mae, _ = fit_predict(train, test, CTD_FEATS + L21_FEATS)
        models.append(('M6_ridge_CTD+L21', r, mae))
        r, mae, _ = fit_predict(train, test, CTD_FEATS + L21_FEATS + DELTA_FEATS)
        models.append(('M7_ridge_ALL', r, mae))

        for name, r, mae in models:
            rstr = f'{r:.4f}' if not np.isnan(r) else 'nan'
            print(f'  {name:<22s}: r={rstr}  mae={mae:.4f}')
            rows.append({'transition': f'{yr_train_max}->{yr_test}',
                         'model': name, 'r': r, 'mae': mae,
                         'n_train': len(train), 'n_test': len(test)})

    out = pd.DataFrame(rows)
    out.to_csv(RES / 'week_level_eval_results.csv', index=False)

    print('\n' + '=' * 72)
    print('AVERAGE r ACROSS TRANSITIONS')
    print('=' * 72)
    avg = out.groupby('model').agg(r_mean=('r', 'mean'),
                                    r_std=('r', 'std'),
                                    mae_mean=('mae', 'mean'),
                                    n=('r', 'count')).reset_index()
    avg = avg.sort_values('r_mean', ascending=False)
    for _, r in avg.iterrows():
        print(f'  {r["model"]:<22s} r={r["r_mean"]:.4f} ± {r["r_std"]:.4f}  '
              f'mae={r["mae_mean"]:.4f}  (n_transitions={r["n"]})')

    print('\n=== Key comparisons ===')
    pivot = avg.set_index('model')['r_mean']
    deltas = []
    deltas.append(('M3 Ridge CTD vs M1 naive CTD', pivot.get('M3_ridge_CTD', np.nan) - pivot.get('M1_naive_CTD', np.nan)))
    deltas.append(('M4 Ridge L21 vs M0 naive L21', pivot.get('M4_ridge_L21', np.nan) - pivot.get('M0_naive_L21', np.nan)))
    deltas.append(('M6 (CTD+L21) vs M3 (CTD only) — leading-indicator lift', pivot.get('M6_ridge_CTD+L21', np.nan) - pivot.get('M3_ridge_CTD', np.nan)))
    deltas.append(('M7 (CTD+L21+DELTA) vs M6 (CTD+L21)', pivot.get('M7_ridge_ALL', np.nan) - pivot.get('M6_ridge_CTD+L21', np.nan)))
    deltas.append(('M2 Marcel blend vs M1 naive CTD', pivot.get('M2_marcel_blend', np.nan) - pivot.get('M1_naive_CTD', np.nan)))
    for name, d in deltas:
        flag = 'PASS' if d >= 0.005 else 'marginal' if d > 0 else 'NEG'
        print(f'  {name:<55s}: dr={d:+.4f}  {flag}')


if __name__ == '__main__':
    main()
