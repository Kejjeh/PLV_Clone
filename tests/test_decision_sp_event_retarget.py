"""T25 — a rostered start's draws must inherit its matchup adjustment, always.

``precompute_draws._sp_event_draws`` retargets each start's draw distribution to
the model's per-start EV with a LOCATION shift (DEFECT 3, 2026-07-29: the old
multiplicative rescale inverted tail severity for a pitcher whose outlook
improved). The location shift needs no guard — that is the whole point of it —
but ``if e['model_fp'] > 0:`` survived the rewrite, so a start projected at or
below zero silently fell back to the pitcher's UNADJUSTED history, diverging
from the candidate SP path (``ensure_candidate_draws``) which shifts
unconditionally.

SP fantasy points are ``K + IP*3.3 - H - 2*ER - BB - HBP``, so non-positive
projections are a routine part of the distribution rather than a sentinel.

``precompute_draws`` had no behavioral test at all before this file — only two
``inspect.getsource`` string assertions in tests/test_leverage_engine.py — which
is why the guard could go stale unnoticed. Fixtures are synthetic state dicts
with ``emp_series`` monkeypatched to empty history, so the draws take the
pure-parametric path and the expected centre is exact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

E = pytest.importorskip("scripts.xfp.lib.leverage_engine",
                        reason="leverage engine needs the dashboard import chain")

N_SIMS = 20_000
PER_START = 8.0        # the pitcher's unadjusted history / rp3 mean


def _event(model_fp, *, confirmed=True, mlbam=605400):
    return {"name": "Test Arm", "mlbam": mlbam, "date": "2026-08-02",
            "opp": "NYY", "confirmed": confirmed, "model_fp": float(model_fp),
            "per_start": PER_START, "sigma": 5.0, "data_quality_tag": None}


def _state(events):
    return {"my_hitters": [], "opp_hitters": [], "my_rps": [], "opp_rps": [],
            "my_sp_events": events, "opp_sp_events": []}


def _centre(monkeypatch, event):
    monkeypatch.setattr(E, "emp_series", lambda *a, **k: [])
    D = E.precompute_draws(_state([event]), N_SIMS, seed=5)
    return float(np.mean(D["my_sp"][0]["fp"]))


def test_a_start_projected_below_zero_still_inherits_its_matchup_adjustment(monkeypatch):
    """A brutal matchup can push a start's projection negative. Those draws must
    centre on the model's number, not on the pitcher's unadjusted history."""
    centre = _centre(monkeypatch, _event(-3.0))
    assert centre == pytest.approx(-3.0, abs=1e-6), (
        f"draws centre on {centre:.3f}; the model projected -3.0 and the "
        f"pitcher's unadjusted per-start mean is {PER_START}")


def test_a_start_projected_at_exactly_zero_inherits_it_too(monkeypatch):
    """Zero is a projection, not a missing value."""
    assert _centre(monkeypatch, _event(0.0)) == pytest.approx(0.0, abs=1e-6)


def test_a_positive_start_is_unchanged(monkeypatch):
    """The boundary the other way: the shipped positive path must not move."""
    assert _centre(monkeypatch, _event(12.0)) == pytest.approx(12.0, abs=1e-6)


def test_an_unconfirmed_start_undoes_its_occurrence_discount(monkeypatch):
    """model_fp carries the 0.80 unconfirmed discount; occurrence is simulated
    explicitly, so the draw centre must be the undiscounted value."""
    centre = _centre(monkeypatch, _event(9.6, confirmed=False))
    assert centre == pytest.approx(9.6 / E.UNCONFIRMED_START_P, abs=1e-6)


def test_a_non_finite_projection_does_not_poison_the_draws(monkeypatch):
    """NaN must fail SAFE — fall back to the pitcher's own history rather than
    turning every simulated start for him into NaN."""
    centre = _centre(monkeypatch, _event(float("nan")))
    assert np.isfinite(centre), "a NaN projection poisoned the whole draw array"
    assert centre == pytest.approx(PER_START, abs=0.2)
