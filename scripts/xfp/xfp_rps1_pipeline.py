"""xfp_rps1_pipeline.py — cross-year RP skill model.

Predicts year T+1 reliever fp_total from year-T features. Mirrors V12
(starter cross-year) for the relief side.

Features (lag-1 = year T values, model predicts year T+1):
  - rate stats: k_pct, bb_pct, swstr_pct, c_plus_swstr, xwoba_per_pa
  - stuff: avg_velo, avg_pfxz
  - discipline: zone_pct, o_swing_pct
  - workload + role signals: g, ip, sv, hld, gf
  - role one-hot: closer / setup / middle (long_low = baseline)
  - prior FP rate: fp_per_g, era, whip

Target: year T+1 fp_total (capped to season totals; user FP scoring already
baked into the substrate).

Decision gate: LOO cross-year r >= 0.40.
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
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'relievers_multiyr_2018_2026.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rps1_pipeline.pkl'
PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rps1_projections.csv'

LAG_FEATS = [
    'k_pct', 'bb_pct', 'swstr_pct', 'c_plus_swstr', 'xwoba_per_pa',
    'avg_velo', 'avg_pfxz', 'zone_pct', 'o_swing_pct', 'z_swing_pct',
    'g', 'ip', 'sv', 'hld', 'gf', 'era', 'whip', 'fp_per_g',
]
ROLE_FEATS = ['role_closer', 'role_setup', 'role_middle']
TRAIN_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]  # year T+1 (target)
EXCLUDE_TARGET_YEAR = 2020  # skip 60-game season as a prediction target

TARGET = 'fp'  # total FP in year T+1


def build_lagged(df: pd.DataFrame) -> pd.DataFrame:
    """For each (pitcher, year T+1), attach the year T row's features as lag-1."""
    df = df.copy()
    df['era'] = pd.to_numeric(df['era'], errors='coerce')
    df['whip'] = pd.to_numeric(df['whip'], errors='coerce')
    # Role one-hot
    df['role_closer'] = (df['role'] == 'closer').astype(int)
    df['role_setup']  = (df['role'] == 'setup').astype(int)
    df['role_middle'] = (df['role'] == 'middle').astype(int)

    lag_src = df[['pitcher', 'year'] + LAG_FEATS + ROLE_FEATS].copy()
    lag_src['year_target'] = lag_src['year'] + 1
    lag_src = lag_src.drop(columns='year').rename(columns={c: c + '_lag1' for c in LAG_FEATS + ROLE_FEATS})
    rows = df.merge(lag_src, left_on=['pitcher', 'year'], right_on=['pitcher', 'year_target'], how='left')
    return rows


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[df['year'].isin(TRAIN_YEARS) & (df['year'] != EXCLUDE_TARGET_YEAR)]
    per_year, preds_all, acts_all = {}, [], []
    eligible_years = [y for y in TRAIN_YEARS if y != EXCLUDE_TARGET_YEAR]
    for held in eligible_years:
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


def naive_baseline(df: pd.DataFrame):
    """Persistence baseline: predict next year FP = this year FP."""
    df = df.dropna(subset=['fp', 'fp_lag1'])
    df = df[df['year'].isin(TRAIN_YEARS) & (df['year'] != EXCLUDE_TARGET_YEAR)]
    if len(df) < 50:
        return {'r': np.nan, 'mae': np.nan, 'n': 0}
    r = float(np.corrcoef(df['fp_lag1'], df['fp'])[0, 1])
    mae = float(np.mean(np.abs(df['fp_lag1'] - df['fp'])))
    return {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(df)}


def train_final(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [TARGET])
    train = train[train['year'].isin(TRAIN_YEARS) & (train['year'] != EXCLUDE_TARGET_YEAR)]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def main():
    print('=== xfp_rps1_pipeline (cross-year RP skill model) ===')
    raw = pd.read_csv(SUBSTRATE)
    print(f'substrate: {len(raw)} (RP, year) rows')
    df = build_lagged(raw)
    feats = [f + '_lag1' for f in LAG_FEATS + ROLE_FEATS]
    # FP lag too — needed for naive baseline
    df['fp_lag1'] = df.merge(
        raw[['pitcher','year','fp']].rename(columns={'year':'year_lag','fp':'fp_lag1_raw'}),
        left_on=['pitcher'], right_on=['pitcher'], how='left'
    ).drop_duplicates(subset=['pitcher','year']).set_index(df.index)['fp_lag1_raw']
    # Cleaner: build via shift
    df = df.sort_values(['pitcher','year']).copy()
    df['fp_lag1'] = df.groupby('pitcher')['fp'].shift(1)

    # Coverage report
    df_eligible = df[df['year'].isin(TRAIN_YEARS) & (df['year'] != EXCLUDE_TARGET_YEAR)].copy()
    n_with_lag = df_eligible.dropna(subset=feats + [TARGET]).shape[0]
    print(f'After filtering to year-T+1 in {TRAIN_YEARS} (drop {EXCLUDE_TARGET_YEAR}) with lag features:')
    print(f'  {n_with_lag} (RP, year T+1) rows usable')

    # Naive baseline
    base = naive_baseline(df)
    print(f'\n--- Naive baseline (predict next-yr FP = this-yr FP) ---')
    print(f'  r = {base["r"]}  mae = {base["mae"]}  n = {base["n"]}')

    # Cross-year LOO
    print('\n--- LOO cross-year (Ridge with role + rate features) ---')
    per_year, overall = cross_year_eval(df, feats)
    for y, m in sorted(per_year.items()):
        print(f'  {y}: r={m["r"]:.4f}  mae={m["mae"]:.2f}  n={m["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    delta_vs_naive = overall['r'] - base['r']
    print(f'\n  Δr (Ridge − naive persistence): {delta_vs_naive:+.4f}')

    GATE = 0.40
    passed = overall['r'] >= GATE
    print(f'\n  Decision gate: r >= {GATE}  →  {"PASS" if passed else "FAIL"}')

    if not passed:
        print(f'\nGATE FAILED. Skipping model lock — would not promote a sub-gate model.')
        return

    # Train final
    pipe, n_train = train_final(df, feats)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RP-S1 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}) ---')
    print('  Top 12 standardized coefficients:')
    for f, c in sorted(zip(feats, coefs), key=lambda x: -abs(x[1]))[:12]:
        print(f'    {f:<22s} {c:+.4f}')

    # Project 2026: target year is 2026, lag features come from 2025
    proj_src = raw[raw['year'] == 2025].copy()
    proj_src['role_closer'] = (proj_src['role'] == 'closer').astype(int)
    proj_src['role_setup']  = (proj_src['role'] == 'setup').astype(int)
    proj_src['role_middle'] = (proj_src['role'] == 'middle').astype(int)
    proj_src = proj_src.rename(columns={c: c + '_lag1' for c in LAG_FEATS + ROLE_FEATS})
    proj_valid = proj_src.dropna(subset=feats).copy()
    proj_valid['xfp_rps1_total'] = pipe.predict(proj_valid[feats].values).round(1)
    proj_valid = proj_valid.sort_values('xfp_rps1_total', ascending=False).reset_index(drop=True)
    proj_valid['rank'] = proj_valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': feats,
        'target': TARGET,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_naive_r': base['r'],
        'delta_vs_naive_r': round(delta_vs_naive, 4),
        'per_year_r': per_year,
        'training_years': [y for y in TRAIN_YEARS if y != EXCLUDE_TARGET_YEAR],
        'gate': GATE,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rps1',
        'note': 'Cross-year RP skill model. Predicts year T+1 reliever FP total '
                'from year-T rate + role + workload features. Uses ESPN scoring '
                '(IP×3.3 + K + SV×5 + HLD×3 − BB − 2×ER − H − HBP).',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Dump projections
    keep = ['rank', 'pitcher', 'name', 'team_abbr', 'role',
            'g', 'ip', 'sv', 'hld', 'fp', 'fp_per_g',
            'k_pct', 'bb_pct', 'swstr_pct', 'xwoba_per_pa',
            'xfp_rps1_total']
    keep = [c for c in keep if c in proj_valid.columns or c == 'xfp_rps1_total']
    # Strip _lag1 suffix from columns we want as plain
    out = proj_valid.copy()
    for c in ['k_pct','bb_pct','swstr_pct','xwoba_per_pa','g','ip','sv','hld','fp','fp_per_g','role']:
        col = c + '_lag1'
        if col in out.columns and c not in out.columns:
            out[c] = out[col]
    out[keep].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(out)} 2026 RP projections')

    print('\nTop 15 by projected 2026 FP total:')
    print(out.head(15)[['rank','name','team_abbr','role','sv','hld','fp','xfp_rps1_total']]
          .to_string(index=False))


if __name__ == '__main__':
    main()
