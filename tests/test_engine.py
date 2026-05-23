"""Behavioral tests for the shared xFP engine toolkit (lookup_sigma, fit_residual_ci, ...)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from plv_clone.models.xfp.engine import (
    apply_shrinkage,
    compute_population_means,
    lookup_sigma,
    train_residual_table,
)


def test_lookup_sigma_returns_overall_when_split_day_unknown():
    """Split-day not in pred_buckets -> fallback to overall_sigma (no CI table lookup)."""
    ci_table = {(30, 0): 1.0}
    pred_buckets = {30: np.array([5.0, 10.0, 15.0])}

    result = lookup_sigma(
        ci_table=ci_table,
        overall_sigma=2.5,
        split_day=99,
        pred=12.0,
        pred_buckets=pred_buckets,
    )

    assert result == 2.5


def test_lookup_sigma_indexes_pred_into_correct_quartile():
    """pred between two cuts -> q = searchsorted index -> ci_table lookup."""
    ci_table = {(30, 0): 1.0, (30, 1): 2.0, (30, 2): 3.0, (30, 3): 4.0}
    pred_buckets = {30: np.array([5.0, 10.0, 15.0])}

    assert lookup_sigma(
        ci_table=ci_table, overall_sigma=99.0, split_day=30, pred=3.0,
        pred_buckets=pred_buckets,
    ) == 1.0  # below all cuts -> q=0
    assert lookup_sigma(
        ci_table=ci_table, overall_sigma=99.0, split_day=30, pred=7.0,
        pred_buckets=pred_buckets,
    ) == 2.0  # between cuts[0]=5 and cuts[1]=10 -> q=1
    assert lookup_sigma(
        ci_table=ci_table, overall_sigma=99.0, split_day=30, pred=20.0,
        pred_buckets=pred_buckets,
    ) == 4.0  # above all cuts -> q=3


def test_lookup_sigma_falls_back_to_overall_when_ci_entry_missing():
    """split_day known but (split_day, q) absent from ci_table -> overall_sigma."""
    ci_table = {(30, 0): 1.0}  # only q=0 populated
    pred_buckets = {30: np.array([5.0, 10.0, 15.0])}

    result = lookup_sigma(
        ci_table=ci_table,
        overall_sigma=7.5,
        split_day=30,
        pred=12.0,
        pred_buckets=pred_buckets,
    )

    assert result == 7.5  # q=2 not in ci_table


def test_train_residual_table_emits_resid_for_each_held_year():
    """Loop held-out years; train Ridge; emit (pred, actual, split_day, resid). resid = actual - pred."""
    rng = np.random.default_rng(42)
    n_per = 50
    years = [2022, 2023, 2024, 2025]
    df = pd.DataFrame({
        "year": np.repeat(years, n_per),
        "split_day": rng.integers(20, 100, n_per * len(years)),
        "f1": rng.normal(0, 1, n_per * len(years)),
        "y": rng.normal(15, 3, n_per * len(years)),
    })

    result = train_residual_table(
        df=df,
        feats=["f1"],
        target_col="y",
        train_years=years,
        min_train=100,
        min_test=30,
    )

    assert set(result.columns) == {"pred", "actual", "split_day", "resid"}
    assert len(result) == 200
    assert np.allclose(result["resid"], result["actual"] - result["pred"])


def test_train_residual_table_skips_year_below_test_threshold():
    """A held-out year with < min_test rows is skipped — no residuals emitted from that block."""
    df = pd.DataFrame({
        "year": [2022] * 50 + [2023] * 50 + [2024] * 50 + [2025] * 20,
        "split_day": [60] * 170,
        "f1": np.linspace(-1, 1, 170),
        "y": np.linspace(10, 20, 170),
    })

    result = train_residual_table(
        df=df,
        feats=["f1"],
        target_col="y",
        train_years=[2022, 2023, 2024, 2025],
        min_train=100,
        min_test=30,
    )

    assert len(result) == 150  # 50 rows each from 2022/23/24 held out; 2025 (n=20) skipped


def test_compute_population_means_uses_denom_weighted_mean():
    """Pooled mean = sum(rate * denom) / sum(denom) over training years."""
    df = pd.DataFrame({
        "year":  [2022,  2022,  2023,  2023],
        "rate":  [0.300, 0.250, 0.350, 0.200],
        "denom": [100,   200,   50,    50],
    })
    spec = {"rate": ("denom", 5)}

    result = compute_population_means(df, train_years=[2022, 2023], spec=spec)

    # (0.3*100 + 0.25*200 + 0.35*50 + 0.20*50) / 400 = 107.5 / 400 = 0.26875
    assert result["rate"] == pytest.approx(0.26875)


def test_compute_population_means_excludes_2020():
    """The COVID-shortened 2020 season is excluded even when it appears in train_years."""
    df = pd.DataFrame({
        "year":  [2020,  2022],
        "rate":  [0.999, 0.200],
        "denom": [100,   100],
    })
    spec = {"rate": ("denom", 5)}

    result = compute_population_means(df, train_years=[2020, 2022], spec=spec)

    assert result["rate"] == pytest.approx(0.200)


def test_apply_shrinkage_blends_observed_with_prior_via_k():
    """Shrunk rate = (n*obs + k*mu) / (n + k). With n=k, obs and prior have equal weight."""
    df = pd.DataFrame({
        "rate":  [0.400, 0.100],
        "denom": [50,    50],
    })
    pop_means = {"rate": 0.250}
    spec = {"rate": ("denom", 50)}

    result = apply_shrinkage(df, pop_means=pop_means, spec=spec)

    # row 0: (50*0.4 + 50*0.25) / 100 = 32.5/100 = 0.325
    # row 1: (50*0.1 + 50*0.25) / 100 = 17.5/100 = 0.175
    assert result["rate_sh"].tolist() == pytest.approx([0.325, 0.175])

