"""Unit tests for scripts/xfp/diagnose_pwin_mean_bias.py (track I5, 2026-07-30).

Each test pins one of the statistical mistakes the previous win-probability
calibration harness made:

* synthetic ``backfill_*`` rows and NULL-``model_version`` rows were pooled
  into the live arms (``fillna('baseline')``);
* every snapshot inside a scoring period was counted as an independent
  Bernoulli trial, even though they all resolve to the SAME win/loss — which
  inflates the apparent n ~18x and manufactures significance;
* snapshots logged after their period had already closed were kept.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

dg = importlib.import_module('scripts.xfp.diagnose_pwin_mean_bias')


def _frame(**over):
    base = {
        'period': [7, 8, 8, 9], 'date': ['2026-05-13', '2026-05-20',
                                         '2026-05-20', '2026-05-27'],
        'my_wtd': [0.0] * 4, 'my_projected_total': [300.0] * 4,
        'opp_wtd': [0.0] * 4, 'opp_projected_total': [290.0] * 4,
        'win_probability': [0.6, 0.5, 0.5, 0.4],
        'actual_my_final': [310.0] * 4, 'actual_opp_final': [300.0] * 4,
        'model_version': [None, 'baseline', 'MA_v1', 'backfill_2024_bayes_shrink'],
    }
    base.update(over)
    return pd.DataFrame(base)


# --- partitioning ----------------------------------------------------------
def test_partition_excludes_synthetic_and_legacy_null_separately():
    live, rep = dg.partition_history(_frame())
    assert rep['n_synthetic_excluded'] == 1
    assert rep['n_legacy_null_mv_excluded'] == 1
    assert rep['legacy_null_periods'] == [7]
    assert rep['n_live'] == 2
    assert sorted(live['mv'].unique()) == ['MA_v1', 'baseline']


def test_partition_does_not_relabel_null_model_version_as_baseline():
    """The old harness fillna'd NULL -> 'baseline', pooling a third version."""
    live, _ = dg.partition_history(_frame())
    assert 7 not in set(live['period'])


def test_partition_raises_on_missing_column():
    with pytest.raises(KeyError):
        dg.partition_history(_frame().drop(columns=['win_probability']))


def test_partition_raises_on_unknown_model_version():
    f = _frame()
    f.loc[1, 'model_version'] = 'some_future_arm'
    with pytest.raises(ValueError):
        dg.partition_history(f)


# --- Poisson-binomial ------------------------------------------------------
def test_poisson_binomial_moments():
    r = dg.poisson_binomial(np.array([0.5, 0.5, 0.5, 0.5]), np.array([1, 1, 0, 0]))
    assert r['expected_wins'] == pytest.approx(2.0)
    assert r['sd_wins'] == pytest.approx(1.0)
    assert r['z'] == pytest.approx(0.0)


def test_poisson_binomial_uses_heterogeneous_variance():
    """Confident-and-correct predictions carry almost no variance."""
    r = dg.poisson_binomial(np.array([0.99, 0.01]), np.array([1, 0]))
    assert r['sd_wins'] == pytest.approx(np.sqrt(0.99 * 0.01 * 2), rel=1e-9)
    assert abs(r['z']) < 0.2


def test_poisson_binomial_raises_on_empty_and_degenerate():
    with pytest.raises(ValueError):
        dg.poisson_binomial(np.array([]), np.array([]))
    with pytest.raises(ValueError):
        dg.poisson_binomial(np.array([1.0, 0.0]), np.array([1, 0]))


# --- clustering ------------------------------------------------------------
def test_collapse_to_periods_one_row_per_period():
    sub = pd.DataFrame({'period': [12, 12, 12, 13],
                        'win_probability': [0.2, 0.4, 0.6, 0.9],
                        'outcome': [0, 0, 0, 1]})
    coll = dg.collapse_to_periods(sub, 'win_probability', 'outcome')
    assert list(coll.index) == [12, 13]
    assert coll.loc[12, 'p'] == pytest.approx(0.4)
    assert coll.loc[12, 'outcome'] == 0


def test_collapse_rejects_conflicting_outcomes_within_a_period():
    sub = pd.DataFrame({'period': [12, 12], 'win_probability': [0.2, 0.4],
                        'outcome': [0, 1]})
    with pytest.raises(ValueError):
        dg.collapse_to_periods(sub, 'win_probability', 'outcome')


def test_naive_snapshot_level_test_overstates_significance():
    """18 snapshots of ONE lost period is one observation, not eighteen.

    Counting them independently is what turns z=-1.0 into z=-4.3.
    """
    rep = 18
    sub = pd.DataFrame({'period': [12] * rep + [13] * rep,
                        'win_probability': [0.7] * rep + [0.7] * rep,
                        'outcome': [0] * rep + [1] * rep})
    naive = dg.poisson_binomial(sub['win_probability'].values, sub['outcome'].values)
    coll = dg.collapse_to_periods(sub, 'win_probability', 'outcome')
    clustered = dg.poisson_binomial(coll['p'].values, coll['outcome'].values)
    assert abs(naive['z']) > 3 * abs(clustered['z'])
    assert abs(clustered['z']) < 2.0


def test_cluster_bootstrap_ci_widens_under_within_cluster_correlation():
    """Snapshots in a period are near-copies; treating them as 200 independent
    observations shrinks the CI by ~5x and is exactly the error being fixed."""
    rng = np.random.default_rng(0)
    clusters = np.repeat(np.arange(8), 25)
    vals = rng.normal(0, 1, 8)[clusters] + rng.normal(0, 0.05, 200)
    naive = dg.cluster_bootstrap_ci(vals, np.arange(200), n_boot=8000)
    clustered = dg.cluster_bootstrap_ci(vals, clusters, n_boot=8000)
    assert (clustered['hi'] - clustered['lo']) > 3 * (naive['hi'] - naive['lo'])
    assert clustered['n_clusters'] == 8 and naive['n_clusters'] == 200


def test_cluster_bootstrap_ci_raises_on_empty():
    with pytest.raises(ValueError):
        dg.cluster_bootstrap_ci([], [], n_boot=10)


# --- window filtering ------------------------------------------------------
WINDOWS = {11: {'start': '2026-06-08', 'end': '2026-06-14'},
           15: {'start': '2026-07-06', 'end': '2026-07-19'}}


def test_in_window_rejects_snapshot_logged_after_period_close():
    mask = dg.in_window(['2026-06-15', '2026-06-10'], [11, 11], WINDOWS)
    assert list(mask) == [False, True]


def test_in_window_accepts_second_week_of_the_asg_block():
    """Period 15 spans Jul 6-19; an ISO-week rule would call Jul 15 out."""
    assert list(dg.in_window(['2026-07-15'], [15], WINDOWS)) == [True]


def test_in_window_raises_for_unknown_period():
    with pytest.raises(KeyError):
        dg.in_window(['2026-07-15'], [99], WINDOWS)
