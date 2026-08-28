"""The within-season noise floor — contract + the 2026-08-28 FP calibration.

First dedicated test file for `lib/split_floor` (the K-BB floor previously
had no direct pins). The FP floor exists because every FP-level results
screen in the decision layer (forward cards, new-leaf boards, the calibration
study's Gate 1) improvised a NAIVE Welch z until 2026-08-28 — with no
dispersion adjustment, which is too lenient by a measured factor that GROWS
with window size. Provenance: fp_split_floor_calibration_2026-08-28.md
(1,175 pitcher-seasons, 21,242 splits vs a shuffle null).
"""
from __future__ import annotations

import numpy as np
import pytest

sf = pytest.importorskip("scripts.xfp.lib.split_floor")


# ── existing K-BB contract (light pins so the owner can't drift silently) ────

def test_kbb_contract_shape_and_bars():
    out = sf.split_floor(30, 10, 100, 20, 18, 100)
    assert set(out) >= {"metric", "gap", "se", "z", "threshold", "verdict", "n_small"}
    assert sf.Z_GIVEN == 1.83 and sf.Z_SEARCHED_SP == 2.58 and sf.Z_SEARCHED_H == 2.79


def test_kbb_dispersion_constants_pinned():
    assert sf.DISPERSION["k_minus_bb"] == 1.114
    assert sf.DISPERSION_HITTER["bb_pct"] == 1.139  # the walk belongs to the batter


# ── FP floor: calibration constants ──────────────────────────────────────────

def test_fp_dispersion_constants_pinned():
    assert sf.DISPERSION_FP_SP_OVERALL == 1.180
    assert sf.DISPERSION_FP_SP[(4, 5)] == 1.121
    assert sf.DISPERSION_FP_SP[(6, 9)] == 1.165
    assert sf.DISPERSION_FP_SP[(10, None)] == 1.259
    assert sf.Z_SEARCHED_FP == 2.92


def test_fp_dispersion_grows_with_window_size():
    """The structural finding: temporal structure accumulates, so the floor
    must get STRICTER as the windows grow — the opposite of the naive
    intuition that bigger samples mean a more trustworthy z."""
    assert (sf._fp_dispersion(4) < sf._fp_dispersion(7) < sf._fp_dispersion(12))


# ── FP floor: behaviour ──────────────────────────────────────────────────────

def test_calibrated_z_is_stricter_than_naive():
    rng = np.random.default_rng(7)
    a, b = rng.normal(10, 6, 12), rng.normal(14, 6, 12)
    out = sf.split_floor_fp(a, b)
    naive_se = np.sqrt(a.var(ddof=1) / 12 + b.var(ddof=1) / 12)
    assert out["se"] > naive_se
    assert out["z"] < abs(b.mean() - a.mean()) / naive_se


def test_fp_floor_contract_matches_kbb_floor():
    out = sf.split_floor_fp([8, 9, 10, 11, 12], [12, 13, 14, 15, 16])
    assert set(out) >= {"metric", "gap", "se", "z", "threshold", "verdict", "n_small"}
    assert out["metric"] == "fp_per_start"
    assert out["n_small"] == 5


def test_fp_floor_is_symmetric():
    a, b = [5.0, 7, 9, 11, 6], [12.0, 14, 10, 15, 13]
    assert sf.split_floor_fp(a, b)["z"] == pytest.approx(sf.split_floor_fp(b, a)["z"])


def test_below_four_starts_per_side_is_unmeasurable():
    """Below the calibration's own admissibility, a z would be falsely
    precise — refuse, don't guess (the INSUFFICIENT discipline)."""
    out = sf.split_floor_fp([10, 12, 14], [1, 2, 3, 4, 5])
    assert out["verdict"] == "UNMEASURABLE"
    assert out["z"] != out["z"]  # NaN


def test_an_ordinary_gap_stays_within_noise():
    """A ~2 FP/start gap on 8v8 noisy windows — the everyday 'he's been
    better lately' observation — must not clear the given bar."""
    rng = np.random.default_rng(11)
    a, b = rng.normal(10, 7, 8), rng.normal(12, 7, 8)
    assert sf.split_floor_fp(a, b)["z"] < sf.Z_GIVEN
