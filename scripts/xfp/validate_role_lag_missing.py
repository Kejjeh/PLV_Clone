"""Pre-registered: data/research/validation_runs/rprs2_role_lag_missing_2026-08-18.md

Rule 9: the baseline is the FULL 28-feature production FEATS_RPRS2. No subset.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'src'))
from plv_clone.models.xfp import rprs2 as M   # noqa: E402

CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
ALPHAS = np.logspace(-1, 5, 80)
FLAG = 'role_lag_missing'
COUNT_LAGS = ['sv_lag1', 'hld_lag1', 'g_lag1', 'ip_lag1', 'fp_lag1', 'fp_per_g_lag1']
RATE_LAGS = ['sv_per_g_lag1', 'hld_per_g_lag1']


def load():
    r = pd.read_csv(CACHE / 'rolling_relievers_2018_2026.csv')
    m = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')
    r[FLAG] = r['role_lag1'].isna().astype(int)
    # population means exactly as enrich_rolling_relievers computes them
    mu = {'sv_lag1': m['sv'].mean(), 'hld_lag1': m['hld'].mean(),
          'g_lag1': m['g'].mean(), 'ip_lag1': m['ip'].mean(),
          'fp_lag1': m['fp'].mean(), 'fp_per_g_lag1': m['fp_per_g'].mean()}
    mu_rate = {'sv_per_g_lag1': (m['sv'] / m['g'].replace(0, np.nan)).mean(),
               'hld_per_g_lag1': (m['hld'] / m['g'].replace(0, np.nan)).mean()}
    return r, mu, mu_rate


def variant(df, name, mu, mu_rate):
    d = df.copy()
    miss = d[FLAG] == 1
    if name == 'B':      # consistent ZERO: counts join the rates at 0
        for c in COUNT_LAGS:
            d.loc[miss, c] = 0.0
    elif name == 'C':    # consistent MEAN: rates join the counts at the mean
        for c in RATE_LAGS:
            d.loc[miss, c] = mu_rate[c]
    return d


def loo_r(d, feats, years):
    d = d.dropna(subset=feats + [M.TARGET])
    d = d[d['year'].isin(years) & (d['g_to'] >= M.EVAL_G_MIN)]
    per_year, preds, acts, missmask = {}, [], [], []
    for held in years:
        tr, te = d[d['year'] != held], d[d['year'] == held]
        if len(tr) < 100 or len(te) < 30:
            continue
        p = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=ALPHAS, cv=5))])
        p.fit(tr[feats].values, tr[M.TARGET].values)
        pr = p.predict(te[feats].values)
        per_year[held] = float(np.corrcoef(pr, te[M.TARGET].values)[0, 1])
        preds += pr.tolist(); acts += te[M.TARGET].tolist()
        missmask += te[FLAG].tolist()
    preds, acts, missmask = np.array(preds), np.array(acts), np.array(missmask)
    pooled = float(np.corrcoef(preds, acts)[0, 1])
    sub = float(np.corrcoef(preds[missmask == 1], acts[missmask == 1])[0, 1])
    return pooled, per_year, sub, len(acts)


def holdout_r(d, feats, train_years, test_years):
    d = d.dropna(subset=feats + [M.TARGET])
    d = d[d['g_to'] >= M.EVAL_G_MIN]
    tr = d[d['year'].isin(train_years)]
    out = {}
    p = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=ALPHAS, cv=5))])
    p.fit(tr[feats].values, tr[M.TARGET].values)
    for y in test_years:
        te = d[d['year'] == y]
        if len(te) < 30:
            continue
        pr = p.predict(te[feats].values)
        out[y] = (float(np.corrcoef(pr, te[M.TARGET].values)[0, 1]), len(te))
    return out


def split_curve(d, feats, years):
    d = d.dropna(subset=feats + [M.TARGET])
    d = d[d['year'].isin(years) & (d['g_to'] >= M.EVAL_G_MIN)]
    res = {}
    for lo, hi in [(0, 60), (60, 90), (90, 120), (120, 150), (150, 999)]:
        s = d[(d['split_day'] >= lo) & (d['split_day'] < hi)]
        if len(s) < 200:
            continue
        preds, acts = [], []
        for held in years:
            tr, te = s[s['year'] != held], s[s['year'] == held]
            if len(tr) < 100 or len(te) < 30:
                continue
            p = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=ALPHAS, cv=5))])
            p.fit(tr[feats].values, tr[M.TARGET].values)
            preds += p.predict(te[feats].values).tolist(); acts += te[M.TARGET].tolist()
        if len(acts) > 50:
            res[f'{lo}-{hi}'] = round(float(np.corrcoef(preds, acts)[0, 1]), 4)
    return res


def main():
    r, mu, mu_rate = load()
    YEARS = M.TRAIN_YEARS
    base = M.FEATS_RPRS2
    print(f'Rule 9 baseline: {len(base)} production features')
    print(f'rows={len(r)}  lag_missing={int(r[FLAG].sum())}\n')

    b_pool, b_year, b_sub, n = loo_r(r, base, YEARS)
    print(f'BASELINE   pooled r={b_pool:.4f}  lag-missing-subgroup r={b_sub:.4f}  n={n}')
    print(f'           per-year {({k: round(v,4) for k,v in b_year.items()})}\n')

    rows = []
    for name in ['A', 'B', 'C']:
        d = variant(r, name, mu, mu_rate)
        feats = base + [FLAG]
        p_pool, p_year, p_sub, _ = loo_r(d, feats, YEARS)
        gain = p_pool - b_pool
        yr_gain = {k: round(p_year[k] - b_year[k], 4) for k in p_year if k in b_year}
        pos = sum(1 for v in yr_gain.values() if v > 0)
        print(f'VARIANT {name}  pooled r={p_pool:.4f}  gain={gain:+.4f}  '
              f'subgroup r={p_sub:.4f} (gain {p_sub-b_sub:+.4f})')
        print(f'           per-year gain {yr_gain}  -> {pos}/{len(yr_gain)} positive')
        rows.append((name, p_pool, gain, p_sub - b_sub, pos, len(yr_gain)))
    print()

    # strict holdout on the best cell
    best = max(rows, key=lambda x: x[2])
    print(f'--- strict holdout (train {M.TRAIN_YEARS[:1]+[2021,2022,2023]}, test 2024/2025), best cell = {best[0]} ---')
    tr_y = [2019, 2021, 2022, 2023]
    hb = holdout_r(r, base, tr_y, [2024, 2025])
    d = variant(r, best[0], mu, mu_rate)
    hv = holdout_r(d, base + [FLAG], tr_y, [2024, 2025])
    for y in sorted(hb):
        print(f'  {y}: baseline r={hb[y][0]:.4f}  variant r={hv[y][0]:.4f}  '
              f'gain={hv[y][0]-hb[y][0]:+.4f}  n={hb[y][1]}')
    print()
    print(f'--- Rule 8 convergence by split_day (cell {best[0]}) ---')
    cb = split_curve(r, base, YEARS)
    cv = split_curve(variant(r, best[0], mu, mu_rate), base + [FLAG], YEARS)
    for k in cb:
        if k in cv:
            print(f'  split {k:>8}: baseline {cb[k]:.4f} -> variant {cv[k]:.4f}  gain {cv[k]-cb[k]:+.4f}')


if __name__ == '__main__':
    main()
