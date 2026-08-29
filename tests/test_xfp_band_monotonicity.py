"""No xfp model may clip one side of a prediction band.

The same one-sided clip shipped in three places and was fixed three times:

  * rprs2 RoS band       -- issue #29 (2026-06)
  * rprs2 full-year band -- 2026-08-29, 29/397 rows INVERTED (p25 > p75),
                            which made (p75-p25)/1.35 a NEGATIVE sigma
  * rp3 display+decision -- 2026-08-29, 47/372 rows pinned at exactly 0.0

`p25.clip(lower=0)` shoves the lower bound up while p75 stays put. Once
mean < -z*sigma the band inverts outright; short of that it is merely
asymmetric, which is quieter and arguably worse -- the IQR->sigma identity
every consumer uses silently understates sigma, and the floor/bust layer
understates real downside. A start CAN score negative FP, and a
replacement-level reliever projects below zero outright.

One shared owner now: engine.quantile_band. These tests pin the invariant and,
more importantly, DISCOVER any future site that reintroduces the clip rather
than enumerating the three we happen to know about (don't-do #18).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "src" / "plv_clone" / "models" / "xfp"

engine = pytest.importorskip("plv_clone.models.xfp.engine")


# ── the shared owner ────────────────────────────────────────────────────────

@pytest.mark.parametrize("mean", [-500.0, -167.3, -24.3, -0.1, 0.0, 4.6, 18.5, 400.0])
def test_band_never_inverts_at_any_mean(mean):
    m = np.array([mean])
    for sigma in (np.array([0.0]), np.array([8.7]), np.array([21.0])):
        p25, p75 = engine.quantile_band(m, sigma)
        assert p25[0] <= m[0] <= p75[0], f"inverted at mean={mean} sigma={sigma[0]}"


def test_band_is_symmetric_so_the_iqr_identity_recovers_sigma():
    """(p75-p25)/1.35 is how every consumer derives sigma. A one-sided clip
    breaks that identity even when the band does not invert."""
    mean, sigma = np.array([4.6]), np.array([8.7])
    p25, p75 = engine.quantile_band(mean, sigma, round_to=None)
    assert (mean[0] - p25[0]) == pytest.approx(p75[0] - mean[0])
    assert (p75[0] - p25[0]) / 1.35 == pytest.approx(sigma[0], rel=0.01)


def test_lower_bound_is_free_to_go_negative():
    p25, _ = engine.quantile_band(np.array([0.5]), np.array([8.7]), round_to=None)
    assert p25[0] < 0


def test_round_to_none_preserves_full_precision():
    """rp3 publishes full float; adopting the shared owner must change the
    clip and nothing else -- not the digits."""
    mean, sigma = np.array([15.586387]), np.array([8.7])
    p25, p75 = engine.quantile_band(mean, sigma, round_to=None)
    assert p25[0] == pytest.approx(15.586387 - 0.6745 * 8.7, abs=1e-12)
    assert p75[0] == pytest.approx(15.586387 + 0.6745 * 8.7, abs=1e-12)
    r25, _ = engine.quantile_band(mean, sigma, round_to=1)
    assert r25[0] == round(15.586387 - 0.6745 * 8.7, 1)


# ── shipped outputs ─────────────────────────────────────────────────────────

SHIPPED = [
    ("xfp_rp3_projections.csv", "xfp_rp3_p25", "xfp_rp3_per_start", "xfp_rp3_p75"),
    ("xfp_rp3_projections.csv", "xfp_rp3_decision_p25", "xfp_rp3_per_start",
     "xfp_rp3_decision_p75"),
    ("xfp_rprs2_projections.csv", "xfp_p25", "xfp_full_year", "xfp_p75"),
    ("xfp_rprs2_projections.csv", "xfp_ros_p25", "xfp_ros", "xfp_ros_p75"),
    ("xfp_rh3_projections.csv", "xfp_rh3_p25", "xfp_rh3_per_pa", "xfp_rh3_p75"),
]


@pytest.mark.parametrize("csv,lo,mid,hi", SHIPPED)
def test_shipped_bands_are_ordered(csv, lo, mid, hi):
    p = ROOT / "data" / "outputs" / csv
    if not p.exists():
        pytest.skip(f"{csv} unavailable")
    d = pd.read_csv(p)
    bad = d[(d[lo] > d[mid]) | (d[mid] > d[hi])]
    assert bad.empty, bad[[lo, mid, hi]].head(10).to_string()


@pytest.mark.parametrize("csv,lo,mid,hi", SHIPPED)
def test_shipped_lower_bounds_are_not_pinned_at_zero(csv, lo, mid, hi):
    """The clip's fingerprint: p25 == exactly 0.0 while the band is wide."""
    p = ROOT / "data" / "outputs" / csv
    if not p.exists():
        pytest.skip(f"{csv} unavailable")
    d = pd.read_csv(p)
    pinned = d[(d[lo] == 0.0) & (d[hi] - d[mid] > 0.5)]
    assert pinned.empty, (
        f"{len(pinned)} row(s) in {csv} have {lo} pinned at exactly 0.0 with a "
        f"wide band -- the one-sided clip is back:\n"
        + pinned[[lo, mid, hi]].head(10).to_string())


# ── the structural guard: DISCOVER a reintroduced clip ──────────────────────

def test_no_model_clips_one_side_of_a_band():
    """Walk the model package instead of naming the three known sites, so a
    fourth is caught the day it is written.

    Parses the AST rather than grepping text -- the docstrings and comments
    that EXPLAIN this bug all contain the literal `clip(lower=0)`, so a
    line-based check flags its own documentation.
    """
    offenders = []
    for path in sorted(MODELS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            # is the assignment target a *_p25 / *_p75 column?
            targets = ast.dump(ast.Module(body=[ast.Expr(t) for t in node.targets],
                                          type_ignores=[]))
            if not re.search(r"p25|p75", targets):
                continue
            for sub in ast.walk(node.value):
                if (isinstance(sub, ast.Call)
                        and getattr(sub.func, "attr", None) == "clip"):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "one-sided band clip reintroduced -- use engine.quantile_band: "
        + ", ".join(offenders))


def test_every_band_producing_model_uses_the_shared_owner():
    """Any module assigning a *_p25 column must route through quantile_band."""
    missing = []
    for path in sorted(MODELS.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if path.name == "engine.py":
            continue
        assigns_p25 = re.search(r"\[['\"][\w]*p25['\"]\]\s*(,|=)", src)
        if assigns_p25 and "quantile_band" not in src:
            missing.append(path.name)
    assert not missing, (
        f"these models build a band without the shared owner: {missing}")
