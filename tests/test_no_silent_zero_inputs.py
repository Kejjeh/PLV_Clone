"""No feature input may silently default when its cache goes missing.

Background — the bug class (docs/rh3_harness_root_bug_2026-07-28.md)
--------------------------------------------------------------------
`if CSV.exists(): merge else: col = 0.0` is the pattern that rotted the rh3
audit copy: two of the top-5 features silently zeroed while 931 tests passed.
`frames.py` closed the class for the canonical assemblies (require_cache /
require_columns / frozen-cache guards, commit 93ecabe); an adversarial review
(2026-07-30) flagged the stragglers this file now pins:

* `scripts/xfp/verdict_backtest.py::build_hitter_panel` carried silent-zero
  else branches on `lift_h2_aug150` and `xwoba_residual_career` (#2/#5 of 22
  by held-out permutation importance) and a silent constant `xwoba_gap_to`.
  All three are now REQUIRED: missing cache / substrate column => raise.
* The MiLB rookie-prior cache (`xfp_milb_pitcher_priors_2026.csv`) is the one
  input that stays OPTIONAL — it is a one-off research artifact (MT3,
  2026-05-07) with no live builder, its fallback rows are explicitly labelled
  `prior_source='league_mean'`, and its absence reproduces the validated
  pre-MT3 behavior. But optional must be LOUD: the old NOTE went through the
  verbose gate (`_p`), i.e. it was SILENT for verbose=False callers such as
  the Rule-9 harness loader. The warning is now unconditional, and these
  tests fail if it ever goes quiet again.

Three layers below:
  1. assembly-level raise tests — monkeypatch a required cache path constant
     to a nonexistent location, assert the assembly raises NAMING the feature;
  2. optional-branch warning tests — capsys-assert the WARNING fires even at
     verbose=False;
  3. structural AST checks — the `exists()` calls themselves are gone from
     the builders except the one documented-optional MiLB site, so the
     pattern cannot quietly grow back.
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from plv_clone.models.xfp import rh3 as rh3_mod
from plv_clone.models.xfp import rp3 as rp3_mod
from plv_clone.models.xfp import frames as frames_mod
from plv_clone.models.xfp.frames import build_rh3_frame, build_rp3_frame

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

VB = pytest.importorskip("verdict_backtest")

# Same integration-guard stance as tests/test_xfp_frames.py: the raise tests
# exercise the REAL substrate up to the sabotaged input, so they need the
# other caches present.
_RH3_INPUTS = [
    rh3_mod.ROLLING_CSV, rh3_mod.MULTIYR_CSV, rh3_mod.H2_LOCKED_CSV,
    rh3_mod.XWOBA_RESID_CSV, rh3_mod.ROS_OPP_SP_CSV, rh3_mod.BX_PRIORS_CSV,
]
_RP3_INPUTS = [
    rp3_mod.ROLLING_CSV, rp3_mod.MULTIYR_CSV, rp3_mod.IL_CSV, rp3_mod.ROS_SCHED_CSV,
]

needs_rh3_cache = pytest.mark.skipif(
    not all(p.exists() for p in _RH3_INPUTS),
    reason="rh3 substrate caches not present in this checkout",
)
needs_rp3_cache = pytest.mark.skipif(
    not all(p.exists() for p in _RP3_INPUTS),
    reason="rp3 substrate caches not present in this checkout",
)

_MISSING = ROOT / "data" / "_nonexistent_by_test" / "gone.csv"


@pytest.fixture(scope="module")
def rh3_substrate():
    """Real rh3 rolling/multiyr, read once and copied per test."""
    return pd.read_csv(rh3_mod.ROLLING_CSV), pd.read_csv(rh3_mod.MULTIYR_CSV)


@pytest.fixture(scope="module")
def rp3_substrate():
    return (pd.read_csv(rp3_mod.ROLLING_CSV), pd.read_csv(rp3_mod.MULTIYR_CSV),
            pd.read_csv(rp3_mod.IL_CSV))


# --------------------------------------------------------------------------- #
# 1. Canonical assemblies RAISE when a required cache disappears.
#    (require_cache is unit-tested in test_xfp_frames.py; these test the
#    WIRING — the constant each site actually reads.)
# --------------------------------------------------------------------------- #
@needs_rh3_cache
@pytest.mark.parametrize("const,feature", [
    ("H2_LOCKED_CSV", "lift_h2_aug150"),
    ("XWOBA_RESID_CSV", "xwoba_residual_career"),
    ("ROS_OPP_SP_CSV", "ros_opp_sp_xwoba_weighted"),
    ("BX_PRIORS_CSV", "bx_prior_h"),
])
def test_rh3_assembly_raises_on_missing_required_cache(
        rh3_substrate, monkeypatch, const, feature):
    rolling, multiyr = rh3_substrate
    monkeypatch.setattr(rh3_mod, const, _MISSING)
    with pytest.raises(FileNotFoundError, match=feature):
        build_rh3_frame(rolling=rolling.copy(), multiyr=multiyr.copy(),
                        verbose=False)


@needs_rp3_cache
def test_rp3_assembly_raises_on_missing_ros_sched_cache(
        rp3_substrate, monkeypatch):
    rolling, multiyr, il = rp3_substrate
    monkeypatch.setattr(rp3_mod, "ROS_SCHED_CSV", _MISSING)
    with pytest.raises(FileNotFoundError, match="ros_opp_xwoba_weighted"):
        build_rp3_frame(rolling=rolling.copy(), multiyr=multiyr.copy(),
                        il=il.copy(), verbose=False)


# --------------------------------------------------------------------------- #
# 2. The one documented-optional input degrades LOUDLY — even at verbose=False.
# --------------------------------------------------------------------------- #
@needs_rp3_cache
def test_rp3_assembly_warns_loudly_when_milb_priors_missing(
        rp3_substrate, monkeypatch, capsys):
    rolling, multiyr, il = rp3_substrate
    monkeypatch.setattr(rp3_mod, "MILB_PRIORS_CSV", _MISSING)
    frame = build_rp3_frame(rolling=rolling.copy(), multiyr=multiyr.copy(),
                            il=il.copy(), verbose=False)
    out = capsys.readouterr().out
    assert "WARNING" in out, "optional-cache fallback must not be silent"
    assert str(_MISSING) in out, "warning must name the missing file"
    assert "prior_fp_per_start" in out, "warning must name the affected column"
    # ...and the degradation itself stays explicitly labelled, not silent:
    assert (frame.rolling["prior_source"] == "league_mean").any()
    # The fallback degrades the prior; it must never drop a model feature.
    assert all(f in frame.rolling.columns for f in rp3_mod.RP3_FEATS)


def test_backtest_pitcher_panel_warns_loudly_when_milb_priors_missing(
        monkeypatch, capsys):
    if not all(p.exists() for p in _RP3_INPUTS):
        pytest.skip("rp3 substrate caches not present in this checkout")
    monkeypatch.setattr(rp3_mod, "MILB_PRIORS_CSV", _MISSING)
    VB.build_pitcher_panel()
    out = capsys.readouterr().out
    assert "WARNING" in out and str(_MISSING) in out


# --------------------------------------------------------------------------- #
# 3. verdict_backtest panels RAISE on missing required caches — fail-fast,
#    before the substrate load, so a missing input can never reach a merge.
# --------------------------------------------------------------------------- #
@needs_rh3_cache          # cacheless checkout: the FIRST require_cache would
                          # fire (H2_LOCKED also absent) and mismatch the
                          # parametrized feature regex — skip, don't fail
@pytest.mark.parametrize("const,feature", [
    ("H2_LOCKED_CSV", "lift_h2_aug150"),
    ("XWOBA_RESID_CSV", "xwoba_residual_career"),
    ("BX_PRIORS_CSV", "bx_prior_h"),
    ("ROS_OPP_SP_CSV", "ros_opp_sp_xwoba_weighted"),
])
def test_backtest_hitter_panel_raises_on_missing_required_cache(
        monkeypatch, const, feature):
    monkeypatch.setattr(rh3_mod, const, _MISSING)
    with pytest.raises(FileNotFoundError, match=feature):
        VB.build_hitter_panel()


@needs_rh3_cache
def test_backtest_pitcher_panel_raises_on_missing_ros_sched_cache(monkeypatch):
    monkeypatch.setattr(rp3_mod, "ROS_SCHED_CSV", _MISSING)
    with pytest.raises(FileNotFoundError, match="ros_opp_xwoba_weighted"):
        VB.build_pitcher_panel()


# --------------------------------------------------------------------------- #
# 4. Structural: the exists()/else pattern is GONE from the builders, except
#    the single documented-optional MiLB site. Equality-today tests cannot
#    stop the pattern growing back tomorrow; this can.
# --------------------------------------------------------------------------- #
def _exists_call_targets(fn) -> set[str]:
    """Names whose `.exists()` is called inside fn's source."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    targets = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "exists"):
            t = n.func.value
            targets.add(t.attr if isinstance(t, ast.Attribute) else ast.dump(t))
    return targets


def test_no_exists_branches_left_in_canonical_assemblies():
    assert _exists_call_targets(frames_mod.build_rh3_frame) == set()
    assert _exists_call_targets(frames_mod.build_rp3_frame) == {"MILB_PRIORS_CSV"}


def test_no_exists_branches_left_in_backtest_panels():
    assert _exists_call_targets(VB.build_hitter_panel) == set()
    assert _exists_call_targets(VB.build_pitcher_panel) == {"MILB_PRIORS_CSV"}
