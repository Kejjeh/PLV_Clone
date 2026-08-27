"""Enforce CLAUDE.md #13: context lenses NEVER move the projection headline.

The lens stack (splits, expected, home/road, TTO, boom/bust, in-season trajectory,
Stuff+, SP-floor, physical trend, shadow scout) is CONTEXT-ONLY — validated 2026-06-11
as non-additive to the point forecast. This test makes that invariant mechanical, so a
future edit that wires a lens into a projection-model feature list (or a flatten_*
serializer that leaks a rogue column) fails CI loudly instead of silently regressing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.lens_registry import (
    LENS_FAMILIES, CONTEXT_ONLY_COLUMNS, is_context_only_column,
)
from lib.triangulate_core import flatten_lenses, flatten_actuals, flatten_extra

import importlib
import pkgutil

import plv_clone.models.xfp as _models_pkg


def _discover_model_feats() -> dict[str, list]:
    """Every ``*_FEATS`` list in plv_clone.models.xfp, found by walking the package.

    Hardcoding the model list is how this guard sprang a leak: it named rh3,
    rp3 and rprs2, while ``rh3_april.RH3_APRIL_FEATS`` — a real model with its
    own pipeline shim, whose docstring explicitly invites adding future
    features to it — went unchecked. A context column dropped into that list
    passed CI silently (verified 2026-08-27).

    Discovery means the NEXT model is covered on the day it is written, which
    a fourth hardcoded entry would not have achieved.
    """
    found: dict[str, list] = {}
    for mod_info in pkgutil.iter_modules(_models_pkg.__path__):
        mod = importlib.import_module(f"{_models_pkg.__name__}.{mod_info.name}")
        for attr, value in vars(mod).items():
            if not attr.endswith("FEATS"):
                continue
            if not isinstance(value, (list, tuple)) or not value:
                continue
            if not all(isinstance(x, str) for x in value):
                continue
            found[f"{mod_info.name}.{attr}"] = list(value)
    return found


ALL_MODEL_FEATS = _discover_model_feats()

#: Feature lists that MUST be found. A rename that silently drops one of these
#: would otherwise shrink the guard's coverage without failing anything.
_REQUIRED_FEATS_LISTS = {
    "rh3.RH3_FEATS",
    "rp3.RP3_FEATS",
    "rprs2.BASE_FEATS",
    "rprs2.NEW_FEATS",
    "rh3_april.RH3_APRIL_FEATS",
}


def test_discovery_finds_every_known_feature_list():
    """The guard is only as good as its coverage — pin that it stays wide."""
    missing = sorted(_REQUIRED_FEATS_LISTS - set(ALL_MODEL_FEATS))
    assert not missing, (
        f"feature list(s) no longer discovered: {missing}. If one was renamed, "
        f"update _REQUIRED_FEATS_LISTS; if a model was deleted, remove it. "
        f"Silently losing coverage is the failure mode this test exists for.\n"
        f"Discovered: {sorted(ALL_MODEL_FEATS)}")


def test_no_context_lens_is_a_projection_feature():
    """Direction 1: a lens column can NEVER be a projection-model feature (#13)."""
    assert ALL_MODEL_FEATS, "discovered no feature lists at all"
    for model, feats in ALL_MODEL_FEATS.items():
        leaked = [f for f in feats if is_context_only_column(f)]
        assert not leaked, (
            f"{model} feature list contains context-only lens columns {leaked} — "
            f"a lens leaked into the projection. CLAUDE.md #13 violation.")


def _sample_model():
    """A model dict populated enough that every flatten_* branch emits its keys."""
    return {
        "splits": {"rate_vs_L": 0.3, "rate_vs_R": 0.3, "lift_vs_L_pct": 1.0,
                   "lift_vs_R_pct": 1.0, "pa_vs_L": 50, "pa_vs_R": 50, "dominant_side": "R"},
        "expected": {"xwoba": 0.32, "woba": 0.32, "gap": 0.0, "regression": "ALIGNED"},
        "expected_splits": {"vs_L": {"xwoba": 0.3, "woba": 0.3, "regression": "ALIGNED", "pa": 40},
                            "vs_R": {"xwoba": 0.3, "woba": 0.3, "regression": "ALIGNED", "pa": 40}},
        "home_away": {"rate_home": 0.3, "rate_away": 0.3, "lift_home_pct": 1.0,
                      "lift_away_pct": 1.0, "dominant_side": "HOME"},
        "tto_decay": {"tier": "DECAY", "penalty": -0.05, "tto1_rate": 0.1, "tto3_rate": 0.05},
        "stuff": {"stuff_plus": 104.0, "proj_ros_fp": 12.0, "breakout_gap": 30, "stuff_pctl": 70},
        "floor": {"bust_prob": 25, "tier": "MODERATE"},
        "trend": {"tag": "flat"},
        "shadow": {"avg_grade": 55, "verdict": "AVG_PROCESS", "grades": {"fb_velo": 50}},
    }


def _sample_actuals():
    return {
        "boom_window": "L8 starts",
        "boom_bust": {"n": 8, "mean": 14.0, "std": 5.0, "min": 1.0, "max": 25.0,
                      "boom_pct": 50, "bust_pct": 12, "l3_mean": 16.0, "trend": "UP",
                      "last": [10.0, 20.0]},
        "trajectory": {"domains": ("STUFF", "MOVEMENT", "CONTROL"), "xkey": "start_no",
                       "points": [{"label": "#3", "OVERALL": 54, "STUFF": 60, "MOVEMENT": 50,
                                   "CONTROL": 45, "archetype": "PURE_STUFF"},
                                  {"label": "#9", "OVERALL": 50, "STUFF": 54, "MOVEMENT": 56,
                                   "CONTROL": 52, "archetype": "AVERAGE_4_5"}]},
    }


def test_every_serialized_column_is_registered_context_only():
    """Direction 2: every column the flatten_* serializers emit belongs to a registered
    context-only family — no rogue/unregistered column escapes the contract."""
    cols = set()
    cols |= set(flatten_lenses(_sample_model(), "SP"))
    cols |= set(flatten_actuals(_sample_actuals()))
    cols |= set(flatten_extra(_sample_model(), "SP"))
    unregistered = sorted(c for c in cols if not is_context_only_column(c))
    assert not unregistered, (
        f"flatten_* emitted columns not covered by lens_registry: {unregistered}. "
        f"Register the family (or fix the prefix) so the #13 contract stays complete.")


def test_registry_columns_are_disjoint_across_families():
    """No column is claimed by two families (keeps family_of unambiguous)."""
    seen = {}
    for fam, meta in LENS_FAMILIES.items():
        for c in meta["columns"]:
            assert c not in seen, f"column {c!r} shared by {seen[c]} and {fam}"
            seen[c] = fam
    assert CONTEXT_ONLY_COLUMNS  # non-empty
