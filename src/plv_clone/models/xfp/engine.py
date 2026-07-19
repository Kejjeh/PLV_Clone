"""Shared xFP toolkit — composed by per-model `fit_and_project` orchestrators.

Not a pipeline base class. Each per-model file (`rh3.py`, `rp3.py`, `rprs2.py`)
owns its own orchestration and reaches for these helpers at load-bearing
steps. See ADR-0001 for why.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_population_means(
    df: pd.DataFrame,
    train_years: list[int],
    spec: dict,
) -> dict:
    """Denom-weighted pooled mean per rate column over training years (2020 excluded)."""
    means: dict[str, float] = {}
    sub = df[df["year"].isin(train_years) & (df["year"] != 2020)]
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


def apply_shrinkage(
    df: pd.DataFrame,
    pop_means: dict,
    spec: dict,
) -> pd.DataFrame:
    """For each (rate, (denom, k)): emit `rate_sh` = (n*obs + k*mu) / (n + k)."""
    out = df.copy()
    for rate_col, (denom_col, k) in spec.items():
        if rate_col not in out.columns or denom_col not in out.columns:
            mu = pop_means.get(rate_col, 0.0)
            out[rate_col + "_sh"] = mu
            continue
        n = out[denom_col].astype(float)
        obs = out[rate_col].astype(float)
        mean = pop_means.get(rate_col, float(np.nanmean(obs) or 0.0))
        obs_filled = obs.fillna(mean)
        n_eff = n.fillna(0.0)
        out[rate_col + "_sh"] = (n_eff * obs_filled + k * mean) / (n_eff + k)
    return out


def train_residual_table(
    *,
    df: pd.DataFrame,
    feats: list[str],
    target_col: str,
    train_years: list[int],
    min_train: int,
    min_test: int,
) -> pd.DataFrame:
    """Loop held-out years, fit Ridge on the rest, emit per-row (pred, actual, split_day, resid)."""
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rows = []
    for held in train_years:
        train = df[df["year"] != held]
        test = df[df["year"] == held]
        if len(train) < min_train or len(test) < min_test:
            continue
        pipe = Pipeline([
            ("sc", StandardScaler()),
            ("r", RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5)),
        ])
        pipe.fit(train[feats].values, train[target_col].values)
        preds = pipe.predict(test[feats].values)
        rows.append(pd.DataFrame({
            "pred": preds,
            "actual": test[target_col].values,
            "split_day": test["split_day"].values,
        }))
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["pred", "actual", "split_day"],
    )
    res["resid"] = res["actual"] - res["pred"]
    return res


def lookup_sigma(
    ci_table: dict,
    overall_sigma: float,
    split_day: int,
    pred: float,
    pred_buckets: dict[int, np.ndarray],
) -> float:
    """Map (split_day, pred) -> sigma using stored quartile cuts."""
    if split_day not in pred_buckets:
        return overall_sigma
    cuts = pred_buckets[split_day]
    q = int(np.searchsorted(cuts, pred))
    q = min(max(q, 0), len(cuts))
    return ci_table.get((split_day, q), overall_sigma)


# ── Per-model fit scaffolding (hoisted 2026-07-19, audit backlog D2) ─────────
# The bodies below were copy-pasted verbatim across rh3/rp3/rprs2, differing
# only in the eligibility filter expression, min-row constants, and the
# fingerprint's extra-constants tuple. Parametrized here; golden-output
# equivalence (byte-identical projection CSVs) verified for all three models
# on hoist day. rprs2 keeps its own cross_year_eval (indexed detail for
# subset masks + coef dumps + mae rounding differ by design).


def fit_fingerprint(rolling, feats, *, target, train_years, extra=(),
                    fp_version=1) -> str:
    """Content hash of the fit stage's inputs: TRAIN-YEAR rows (immutable
    slice), feature list, and each model's constants (spliced verbatim into
    the repr so hoisting preserved every model's existing fingerprints).
    Same fingerprint => byte-identical fit artifacts (warm-skip)."""
    import hashlib
    import pandas as pd
    sub = rolling[rolling['year'].isin(train_years)]
    cols = [c for c in sorted(set(feats + [target, 'year', 'split_day']))
            if c in sub.columns]
    h = hashlib.md5()
    h.update(pd.util.hash_pandas_object(
        sub[cols].reset_index(drop=True), index=False).values.tobytes())
    h.update(repr((sorted(feats),) + tuple(extra)
                  + (sorted(train_years), fp_version)).encode())
    return h.hexdigest()


def cross_year_eval_ridge(df, feats, *, target, train_years, filter_fn,
                          min_train, min_test):
    """LOO cross-year eval (rh3/rp3 shape): per-year r/mae + overall + a
    positional detail frame (pred/actual/split_day/resid)."""
    import pandas as pd
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [target]).copy()
    df = df[filter_fn(df)]
    per_year, preds_all, acts_all = {}, [], []
    _details = []
    for held in train_years:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < min_train or len(test) < min_test:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[target].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[target].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[target].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(test)}
        preds_all.extend(preds.tolist()); acts_all.extend(test[target].tolist())
        _details.append(pd.DataFrame({'pred': preds, 'actual': test[target].values,
                                      'split_day': test['split_day'].values}))
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    detail = (pd.concat(_details, ignore_index=True) if _details
              else pd.DataFrame(columns=['pred', 'actual', 'split_day']))
    detail['resid'] = detail['actual'] - detail['pred']
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}, detail


def fit_residual_ci_from(df, feats, *, target, train_years, filter_fn,
                         min_train, min_test, resid=None, min_split_n=None):
    """Residual CI table: (split_day, predicted_quartile) -> sigma.
    `resid`: reuse cross_year_eval's detail frame (the second LOO pass was
    fit-for-fit identical — audit 2026-07-04). `min_split_n`: rprs2 skips
    splits with <30 rows; rh3/rp3 pass None (no skip)."""
    import pandas as pd
    if resid is not None and len(resid):
        res = resid
    else:
        sub = df.dropna(subset=feats + [target]).copy()
        sub = sub[filter_fn(sub)]
        res = train_residual_table(df=sub, feats=feats, target_col=target,
                                   train_years=train_years,
                                   min_train=min_train, min_test=min_test)
    out: dict = {}
    for split in sorted(res['split_day'].unique()):
        sub2 = res[res['split_day'] == split]
        if min_split_n is not None and len(sub2) < min_split_n:
            continue
        qs = pd.qcut(sub2['pred'], q=4, duplicates='drop', labels=False)
        for q in sorted(sub2.groupby(qs).groups.keys()):
            ix = (qs == q)
            out[(int(split), int(q))] = float(sub2.loc[ix, 'resid'].std())
    return out, float(res['resid'].std())


def train_final_ridge(df, feats, *, target, train_years, filter_fn, cv=10):
    """Final production fit on all train years (filter_fn = each model's
    eligibility mask; the train-years restriction is applied here)."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [target])
    train = train[filter_fn(train) & train['year'].isin(train_years)]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=cv))])
    pipe.fit(train[feats].values, train[target].values)
    return pipe, len(train)
