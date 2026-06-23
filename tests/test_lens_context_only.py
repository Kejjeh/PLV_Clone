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

from plv_clone.models.xfp.rh3 import RH3_FEATS
from plv_clone.models.xfp.rp3 import RP3_FEATS
from plv_clone.models.xfp.rprs2 import BASE_FEATS, NEW_FEATS

ALL_MODEL_FEATS = {
    "rh3": RH3_FEATS,
    "rp3": RP3_FEATS,
    "rprs2": BASE_FEATS + NEW_FEATS,
}


def test_no_context_lens_is_a_projection_feature():
    """Direction 1: a lens column can NEVER be a projection-model feature (#13)."""
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
