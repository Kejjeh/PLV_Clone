"""Phase 3 — E[G] model for RPs.

Predicts season appearances G_year given role_lag1, prior_year_g_rp, age,
arche_overall_prior, prior_year_fp_per_g_rp.

LOYO CV across 2018,2019,2021-2025 (ex-2020). Anchor = prior_year_g_rp.
Output: R² blend vs anchor, per-feature drop test, year convergence,
sample predictions for canonical RPs.

NO PRODUCTION WIRING — research/validation only.
"""
from __future__ import annotations
from pathlib import Path
import sys, io
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')
if sys.stdout is sys.__stdout__:  # never rewrap pytest's capture stream
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_relievers_2018_2026.csv'
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]  # ex-2020
LATE_SPLIT = 184  # use late-season snapshot per (player, year)


def build_dataset() -> pd.DataFrame:
    roll = pd.read_csv(ROLLING_CSV)
    # Use only the latest available split_day per (pitcher, year) — late season
    # captures prior_year_* (lag1) features but we are predicting full-year G,
    # so a single snapshot per pl-yr is fine.
    roll = roll.sort_values(['pitcher', 'year', 'split_day'])
    roll = roll.groupby(['pitcher', 'year'], as_index=False).tail(1).copy()

    panel = pd.read_parquet(PANEL)
    rp = panel[panel.player_type == 'RP'][['mlbam_id', 'year', 'g',
                                            'age', 'arche_overall_prior',
                                            'prior_year_g_rp',
                                            'prior_year_fp_per_g_rp']].copy()
    rp = rp.rename(columns={'mlbam_id': 'pitcher'})
    df = roll.merge(rp, on=['pitcher', 'year'], how='inner')
    df = df[df.year.isin(YEARS)].copy()
    df = df[df.g.notna() & (df.g >= 5)]
    return df


FEATS_FULL = ['prior_year_g_rp', 'role_closer_lag1', 'role_setup_lag1',
              'role_middle_lag1', 'age', 'arche_overall_prior',
              'prior_year_fp_per_g_rp']
FEAT_ANCHOR = ['prior_year_g_rp']
TARGET = 'g'


def loyo_eval(df: pd.DataFrame, feats: list[str]) -> dict:
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    # Mean-impute features w/in train fold so sample size stays comparable
    # across drop-tests / anchor-vs-blend.
    sub = df.dropna(subset=[TARGET]).copy()
    for f in feats:
        if f not in sub.columns:
            sub[f] = np.nan
    # Per-fold imputation below.
    preds_all, acts_all = [], []
    per_year = {}
    for held in YEARS:
        tr = sub[sub.year != held].copy()
        te = sub[sub.year == held].copy()
        if len(tr) < 80 or len(te) < 30:
            continue
        # impute means from train
        for f in feats:
            mu = tr[f].mean()
            tr[f] = tr[f].fillna(mu)
            te[f] = te[f].fillna(mu)
        sc = StandardScaler().fit(tr[feats].values)
        Xtr, Xte = sc.transform(tr[feats].values), sc.transform(te[feats].values)
        m = RidgeCV(alphas=np.logspace(-1, 4, 40), cv=5).fit(Xtr, tr[TARGET].values)
        p = m.predict(Xte)
        r2 = 1 - np.sum((te[TARGET].values - p) ** 2) / np.sum(
            (te[TARGET].values - te[TARGET].values.mean()) ** 2)
        mae = float(np.mean(np.abs(p - te[TARGET].values)))
        per_year[held] = {'r2': round(float(r2), 4), 'mae': round(mae, 2), 'n': len(te)}
        preds_all.extend(p.tolist()); acts_all.extend(te[TARGET].tolist())
    preds_all = np.array(preds_all); acts_all = np.array(acts_all)
    r2_overall = 1 - np.sum((acts_all - preds_all) ** 2) / np.sum(
        (acts_all - acts_all.mean()) ** 2)
    mae_overall = float(np.mean(np.abs(preds_all - acts_all)))
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    return {'r2': round(float(r2_overall), 4), 'r': round(r, 4),
            'mae': round(mae_overall, 2), 'n': int(len(preds_all)),
            'per_year': per_year, 'preds': preds_all, 'acts': acts_all}


def bootstrap_r2_diff(acts, p1, p2, n_boot=200, seed=42):
    rng = np.random.default_rng(seed)
    diffs = []
    n = len(acts)
    for _ in range(n_boot):
        ix = rng.integers(0, n, n)
        a, b1, b2 = acts[ix], p1[ix], p2[ix]
        ss = np.sum((a - a.mean()) ** 2)
        r1 = 1 - np.sum((a - b1) ** 2) / ss
        r2 = 1 - np.sum((a - b2) ** 2) / ss
        diffs.append(r2 - r1)
    diffs = np.array(diffs)
    return float(diffs.mean()), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def main():
    print('=== Phase 3 E[G] model ===')
    df = build_dataset()
    print(f'rows: {len(df)}  years: {sorted(df.year.unique())}')
    print(f'target G mean={df.g.mean():.1f} std={df.g.std():.1f}')
    print()

    anchor = loyo_eval(df, FEAT_ANCHOR)
    print(f'ANCHOR (prior_year_g_rp): R²={anchor["r2"]} r={anchor["r"]} MAE={anchor["mae"]} n={anchor["n"]}')

    blend = loyo_eval(df, FEATS_FULL)
    print(f'BLEND (full feats):       R²={blend["r2"]} r={blend["r"]} MAE={blend["mae"]} n={blend["n"]}')
    print(f'  ΔR² = {blend["r2"] - anchor["r2"]:+.4f}')

    # Bootstrap CI — anchor and blend already aligned via mean-imputation.
    mean, lo, hi = bootstrap_r2_diff(blend['acts'], anchor['preds'], blend['preds'])
    print(f'  Bootstrap ΔR²: mean={mean:+.4f} CI95=[{lo:+.4f}, {hi:+.4f}]  '
          f'{"SIGNIFICANT" if lo > 0 else "NOT SIG"}')

    print('\nPer-year R² (blend):')
    pos = 0
    for y, m in sorted(blend['per_year'].items()):
        ay = anchor['per_year'].get(y, {})
        d = m['r2'] - ay.get('r2', 0)
        sign = '+' if d > 0 else '-'
        if d > 0:
            pos += 1
        print(f'  {y}: blend R²={m["r2"]:.4f}  anchor R²={ay.get("r2", "—")}  Δ={d:+.4f}  {sign}')
    print(f'  Convergence: {pos}/{len(blend["per_year"])} year-folds positive')

    print('\nDrop-test (each feature held out from blend):')
    for f in FEATS_FULL:
        reduced = [x for x in FEATS_FULL if x != f]
        r = loyo_eval(df, reduced)
        print(f'  drop {f:<32s} → R²={r["r2"]:.4f}  Δfull={r["r2"] - blend["r2"]:+.4f}')

    # Standardized coefs on full train
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    sub = df.dropna(subset=[TARGET]).copy()
    for f in FEATS_FULL:
        sub[f] = sub[f].fillna(sub[f].mean())
    sc = StandardScaler().fit(sub[FEATS_FULL].values)
    m = RidgeCV(alphas=np.logspace(-1, 4, 40), cv=5).fit(
        sc.transform(sub[FEATS_FULL].values), sub[TARGET].values)
    print(f'\nFinal coefficients (alpha={m.alpha_:.2f}, n={len(sub)}):')
    for f, c in sorted(zip(FEATS_FULL, m.coef_), key=lambda x: -abs(x[1])):
        print(f'  {f:<32s} {c:+.3f}')
    print(f'  intercept                        {m.intercept_:+.3f}')

    # Sample predictions for 2025 hold-out fold
    print('\nSample predictions (2025 hold-out fold, mean-imputed):')
    tr = df[df.year != 2025].dropna(subset=[TARGET]).copy()
    te = df[df.year == 2025].dropna(subset=[TARGET]).copy()
    for f in FEATS_FULL:
        mu = tr[f].mean()
        tr[f] = tr[f].fillna(mu)
        te[f] = te[f].fillna(mu)
    if len(te):
        sc2 = StandardScaler().fit(tr[FEATS_FULL].values)
        m2 = RidgeCV(alphas=np.logspace(-1, 4, 40), cv=5).fit(
            sc2.transform(tr[FEATS_FULL].values), tr[TARGET].values)
        p25 = m2.predict(sc2.transform(te[FEATS_FULL].values))
        te = te.assign(eg_pred=p25)
        print(te.sort_values('eg_pred', ascending=False).head(8)[
            ['pitcher', 'role_lag1', 'prior_year_g_rp', 'g', 'eg_pred']].to_string(index=False))

    # Persist preds for downstream layered eval
    out_dir = ROOT / 'data' / 'research' / 'validation_runs'
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / 'e_of_g_preds_2026-06-06.parquet'
    # Generate hold-out predictions for ALL years for use by ros_layered comparison
    rows = []
    for held in YEARS:
        tr = df[df.year != held].dropna(subset=[TARGET]).copy()
        te = df[df.year == held].dropna(subset=[TARGET]).copy()
        if len(tr) < 80 or len(te) < 30:
            continue
        for f in FEATS_FULL:
            mu = tr[f].mean()
            tr[f] = tr[f].fillna(mu)
            te[f] = te[f].fillna(mu)
        sc3 = StandardScaler().fit(tr[FEATS_FULL].values)
        m3 = RidgeCV(alphas=np.logspace(-1, 4, 40), cv=5).fit(
            sc3.transform(tr[FEATS_FULL].values), tr[TARGET].values)
        p = m3.predict(sc3.transform(te[FEATS_FULL].values))
        rows.append(te[['pitcher', 'year', 'g', 'role_lag1']].assign(eg_pred=p))
    out = pd.concat(rows, ignore_index=True)
    tmp = pred_path.with_suffix('.tmp.parquet')
    out.to_parquet(tmp); tmp.replace(pred_path)
    print(f'\nWrote {pred_path} ({len(out)} rows)')

    return {'anchor': anchor, 'blend': blend, 'boot_ci': (mean, lo, hi)}


if __name__ == '__main__':
    main()
