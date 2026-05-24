"""Model-accuracy-ceiling audit toolkit for the xFP ridge models.

Answers the question "is this model as accurate as the data allows?" via three
ceilings:

  1. NONLINEAR CEILING — does the same feature set + nonlinear estimator (XGB,
     RF) beat the production Ridge by a meaningful r? If yes, the relationship
     has shape Ridge cannot capture; if no, the model is at its functional-form
     ceiling and adding interactions / trees would not help.

  2. LINEAR CEILING — is the production Ridge alpha selection STABLE across a
     wide log-spaced grid, or does the held-out r swing materially with alpha?
     If unstable, the model is alpha-sensitive (collinearity / underdetermined),
     and a tighter CV or feature pruning may unlock headroom.

  3. FEATURE CEILING — given a list of candidate columns NOT currently in the
     baseline FEATS list, does a LassoCV-regularised superset deliver
     meaningfully more r? If yes, list which candidates Lasso kept (and which
     baseline feats it zeroed) so the answer is actionable.

All three reuse the **production cross_year_eval pattern**: held-out year LOO,
StandardScaler + estimator pipeline, per-row predictions concatenated, overall
Pearson r as the single scalar. The per-model filter thresholds (pa_to /
gs_to / g_to) are applied by the *caller* (the CLI driver in
``scripts/xfp/audit_model_ceiling.py``) before passing the dataframe in. This
module is generic.

XGB / RF defaults honor the older Phase-5 handoff for comparability:
  - XGB: n_estimators=300, max_depth=3, learning_rate=0.05, random_state=42
  - RF:  n_estimators=300, max_depth=5, min_samples_leaf=5, random_state=42

LassoCV: alphas=np.logspace(-4, 1, 50), cv=5, random_state=42, max_iter=10_000.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NonlinearCeiling:
    ridge_r: float
    xgb_r: float
    rf_r: float
    xgb_gap: float
    rf_gap: float
    verdict: str  # AT_CEILING | MILD_NONLINEARITY | SIGNIFICANT_NONLINEARITY


@dataclass(frozen=True)
class LinearCeiling:
    alpha_chosen: float
    alpha_range_tested: tuple[float, ...]
    r_at_chosen: float
    r_std_across_alphas: float
    verdict: str  # STABLE | ALPHA_SENSITIVE


@dataclass(frozen=True)
class FeatureCeiling:
    baseline_r: float
    extended_r: float
    survived_features: tuple[str, ...]
    new_features_kept: tuple[str, ...]
    delta_r: float
    verdict: str  # BASELINE_OPTIMAL | ADD_CANDIDATES | REPLACE_BASELINE


# ---------------------------------------------------------------------------
# Shared cross-year evaluator (generic estimator factory)
# ---------------------------------------------------------------------------
def _cross_year_r(
    *,
    df: pd.DataFrame,
    feats: list[str],
    target_col: str,
    train_years: Sequence[int],
    min_train: int,
    min_test: int,
    estimator_factory,
) -> float:
    """LOO over train_years; fit estimator on train; predict held; concat all preds.

    estimator_factory: zero-arg callable returning a fresh estimator instance
    (already wrapped in a Pipeline if scaling is needed).

    Returns Pearson r between concatenated predictions and concatenated actuals.
    Returns np.nan if no held year had enough rows.
    """
    sub = df.dropna(subset=list(feats) + [target_col]).copy()
    preds_all, acts_all = [], []
    for held in train_years:
        train = sub[sub["year"] != held]
        test = sub[sub["year"] == held]
        if len(train) < min_train or len(test) < min_test:
            continue
        est = estimator_factory()
        est.fit(train[feats].values, train[target_col].values)
        preds = est.predict(test[feats].values)
        preds_all.extend(preds.tolist())
        acts_all.extend(test[target_col].tolist())
    if not preds_all:
        return float("nan")
    return float(np.corrcoef(preds_all, acts_all)[0, 1])


# Production-equivalent ridge pipeline (matches engine.train_residual_table)
def _ridge_factory():
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([
        ("sc", StandardScaler()),
        ("r", RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5)),
    ])


def _xgb_factory():
    from xgboost import XGBRegressor
    return XGBRegressor(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        random_state=42,
        n_jobs=1,
        verbosity=0,
        tree_method="hist",
    )


def _rf_factory():
    from sklearn.ensemble import RandomForestRegressor
    return RandomForestRegressor(
        n_estimators=300,
        max_depth=5,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=1,
    )


# ---------------------------------------------------------------------------
# nonlinear_ceiling
# ---------------------------------------------------------------------------
def nonlinear_ceiling(
    *,
    df: pd.DataFrame,
    feats: list[str],
    target_col: str,
    train_years: Sequence[int],
    min_train: int,
    min_test: int,
) -> NonlinearCeiling:
    """Compare Ridge (production) to XGB and RF on the same feats / target /
    cross-year split. Verdict by max(|xgb_gap|, |rf_gap|) thresholds."""
    feats = list(feats)
    kw = dict(
        df=df,
        feats=feats,
        target_col=target_col,
        train_years=train_years,
        min_train=min_train,
        min_test=min_test,
    )
    ridge_r = _cross_year_r(estimator_factory=_ridge_factory, **kw)
    xgb_r = _cross_year_r(estimator_factory=_xgb_factory, **kw)
    rf_r = _cross_year_r(estimator_factory=_rf_factory, **kw)

    xgb_gap = xgb_r - ridge_r
    rf_gap = rf_r - ridge_r
    # Verdict is one-sided: only POSITIVE gaps indicate exploitable
    # nonlinearity. Negative gaps mean tree models can't recover Ridge's
    # signal -> Ridge IS the ceiling -> AT_CEILING.
    biggest_upside = max(max(xgb_gap, 0.0), max(rf_gap, 0.0))
    if biggest_upside < 0.003:
        verdict = "AT_CEILING"
    elif biggest_upside <= 0.010:
        verdict = "MILD_NONLINEARITY"
    else:
        verdict = "SIGNIFICANT_NONLINEARITY"

    return NonlinearCeiling(
        ridge_r=ridge_r,
        xgb_r=xgb_r,
        rf_r=rf_r,
        xgb_gap=xgb_gap,
        rf_gap=rf_gap,
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# linear_ceiling
# ---------------------------------------------------------------------------
# Same log-spaced grid the production cross_year_eval uses (np.logspace(-1, 5, 80)),
# but downsampled for the per-alpha sweep so each fixed-alpha LOO completes in
# tractable time. The held-out r is computed by re-fitting Ridge (NOT RidgeCV)
# at each fixed alpha so the sensitivity sweep is honest.
_LINEAR_ALPHA_GRID = tuple(np.logspace(-1, 5, 13).round(6).tolist())


def linear_ceiling(
    *,
    df: pd.DataFrame,
    feats: list[str],
    target_col: str,
    train_years: Sequence[int],
    min_train: int,
    min_test: int,
) -> LinearCeiling:
    """Sweep Ridge over a fixed alpha grid. For each alpha, fit per-held-year
    and compute concatenated-prediction r. Find the alpha with peak r;
    measure std of r across the grid (sensitivity to regularisation choice).
    """
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    feats = list(feats)
    grid = _LINEAR_ALPHA_GRID
    rs_per_alpha: list[float] = []
    for alpha in grid:
        def factory(a=alpha):  # bind alpha into closure
            return Pipeline([("sc", StandardScaler()), ("r", Ridge(alpha=a))])
        r = _cross_year_r(
            df=df,
            feats=feats,
            target_col=target_col,
            train_years=train_years,
            min_train=min_train,
            min_test=min_test,
            estimator_factory=factory,
        )
        rs_per_alpha.append(r)

    rs_arr = np.array(rs_per_alpha, dtype=float)
    # Ignore NaNs in argmax / std
    finite_mask = np.isfinite(rs_arr)
    if not finite_mask.any():
        return LinearCeiling(
            alpha_chosen=float("nan"),
            alpha_range_tested=grid,
            r_at_chosen=float("nan"),
            r_std_across_alphas=float("nan"),
            verdict="ALPHA_SENSITIVE",
        )
    best_idx = int(np.argmax(np.where(finite_mask, rs_arr, -np.inf)))
    alpha_chosen = float(grid[best_idx])
    r_at_chosen = float(rs_arr[best_idx])
    # r_std measured across alphas in the "reasonable zone" — those whose r
    # is at most 0.05 worse than peak. This captures: "across the band any
    # engineer might pick, how stable is r?". Well-conditioned features:
    # the reasonable zone is wide and flat (tiny std). Ill-conditioned
    # features: the zone is narrow and the r curve drops off sharply
    # (large std even within the band). Std across the full grid would
    # be dominated by the over-regularised tail and would always saturate.
    reasonable = rs_arr >= (r_at_chosen - 0.05)
    reasonable &= finite_mask
    band = rs_arr[reasonable]
    r_std = float(np.std(band)) if band.size > 1 else 0.0

    verdict = "STABLE" if (np.isfinite(r_std) and r_std < 0.005) else "ALPHA_SENSITIVE"
    return LinearCeiling(
        alpha_chosen=alpha_chosen,
        alpha_range_tested=grid,
        r_at_chosen=r_at_chosen,
        r_std_across_alphas=r_std,
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# feature_ceiling
# ---------------------------------------------------------------------------
_LASSO_ALPHAS = tuple(np.logspace(-4, 1, 50).round(6).tolist())


def _lassocv_factory():
    from sklearn.linear_model import LassoCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([
        ("sc", StandardScaler()),
        ("r", LassoCV(
            alphas=_LASSO_ALPHAS, cv=5, max_iter=10_000, random_state=42, n_jobs=1,
        )),
    ])


def feature_ceiling(
    *,
    df: pd.DataFrame,
    baseline_feats: list[str],
    candidate_feats: list[str],
    target_col: str,
    train_years: Sequence[int],
    min_train: int,
    min_test: int,
) -> FeatureCeiling:
    """Compare production-Ridge baseline r vs LassoCV-on-baseline+candidates r.

    1. baseline_r: Ridge cross-year r using baseline_feats only (matches
       production cross_year_eval pattern).
    2. extended_r: LassoCV cross-year r over baseline_feats + candidate_feats.
       Refit LassoCV per held-year on training only, predict test.
    3. Inspect Lasso's final coefficients (refit on all training data ex-2020)
       to identify which candidates survived (non-zero coef) and which
       baseline features got zeroed.

    Verdict:
      - delta_r < 0.005 AND no candidates kept → BASELINE_OPTIMAL
      - delta_r >= 0.005 AND candidates kept → ADD_CANDIDATES
      - delta_r >= 0.005 AND baseline features got zeroed → REPLACE_BASELINE
      - default → BASELINE_OPTIMAL
    """
    baseline_feats = list(baseline_feats)
    candidate_feats = list(candidate_feats)
    extended_feats = baseline_feats + candidate_feats

    # 1. Baseline Ridge r (matches production cross_year_eval)
    baseline_r = _cross_year_r(
        df=df,
        feats=baseline_feats,
        target_col=target_col,
        train_years=train_years,
        min_train=min_train,
        min_test=min_test,
        estimator_factory=_ridge_factory,
    )
    # 2. Extended LassoCV r over baseline + candidates
    extended_r = _cross_year_r(
        df=df,
        feats=extended_feats,
        target_col=target_col,
        train_years=train_years,
        min_train=min_train,
        min_test=min_test,
        estimator_factory=_lassocv_factory,
    )

    # 3. Identify survived features by refitting LassoCV on all valid training data
    sub = df.dropna(subset=extended_feats + [target_col]).copy()
    sub = sub[sub["year"].isin(train_years)]
    pipe = _lassocv_factory()
    pipe.fit(sub[extended_feats].values, sub[target_col].values)
    coefs = pipe.named_steps["r"].coef_
    # Practical "survived" threshold: features are standardized to unit
    # variance, so coefficients live on a common scale. Lasso often leaves
    # tiny non-zero coefs on noise features; we require a coef ≥ 5% of the
    # largest |coef| in the fit AND ≥ 0.01 in absolute terms to qualify
    # as "survived". This treats trace coefficients as zeroed for the
    # purpose of the verdict.
    max_abs = float(np.max(np.abs(coefs))) if len(coefs) else 0.0
    rel_floor = max(0.05 * max_abs, 0.01)
    survived = tuple(f for f, c in zip(extended_feats, coefs) if abs(c) >= rel_floor)
    new_kept = tuple(f for f in survived if f in candidate_feats)
    baseline_zeroed = tuple(f for f in baseline_feats if f not in survived)

    delta_r = float(extended_r - baseline_r)

    # Verdict
    if delta_r >= 0.005 and baseline_zeroed:
        verdict = "REPLACE_BASELINE"
    elif delta_r >= 0.005 and new_kept:
        verdict = "ADD_CANDIDATES"
    else:
        verdict = "BASELINE_OPTIMAL"

    return FeatureCeiling(
        baseline_r=float(baseline_r),
        extended_r=float(extended_r),
        survived_features=survived,
        new_features_kept=new_kept,
        delta_r=delta_r,
        verdict=verdict,
    )
