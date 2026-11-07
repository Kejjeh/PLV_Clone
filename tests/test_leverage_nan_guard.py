"""NaN never reaches the P(win) Monte Carlo silently.

Defect (found 2026-09-18): ``_blend_draws`` passed a NaN mean/sigma straight
into ``rng.normal`` (NaN is truthy, survives ``or``), producing an all-NaN
draw array for that player; ``pwin`` then scored every NaN trial as a LOSS
(``nan > x`` is False on both sides), so one NaN-rate rostered player dragged
P(win) toward 0.0 with no error and made "drop him" the top-ranked move.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import scripts.xfp.lib.leverage_engine as E  # tracked source: a hard import, never a guard

NAN = float("nan")


def test_blend_draws_nan_mean_is_treated_as_missing():
    rng = np.random.default_rng(0)
    out = E._blend_draws(rng, [], NAN, 5.5, E.K_PRIOR_SP, 200)
    assert np.isfinite(out).all()
    assert np.allclose(out, 0.0)            # no model mean + no history -> zeros


def test_blend_draws_nan_mean_with_history_uses_the_history():
    rng = np.random.default_rng(0)
    out = E._blend_draws(rng, [10.0, 12.0, 14.0], NAN, 5.5, E.K_PRIOR_SP, 500)
    assert np.isfinite(out).all()
    assert set(np.unique(out)) <= {10.0, 12.0, 14.0}


def test_blend_draws_nan_sigma_is_floored_not_propagated():
    rng = np.random.default_rng(0)
    out = E._blend_draws(rng, [], 8.0, NAN, E.K_PRIOR_SP, 200)
    assert np.isfinite(out).all()
    assert np.allclose(out, 8.0, atol=1e-3)


def test_pwin_refuses_non_finite_totals():
    with pytest.raises(ValueError, match="non-finite"):
        E.pwin(np.array([1.0, NAN, 3.0]), np.zeros(3))
    with pytest.raises(ValueError):
        E.pwin(np.zeros(3), np.array([np.inf, 0.0, 0.0]))


def test_pwin_finite_path_unchanged():
    assert E.pwin(np.array([1.0, 2.0, 3.0]), np.array([2.0, 2.0, 2.0])) == pytest.approx(0.5)
