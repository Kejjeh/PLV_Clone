"""TDD for lib/verdict_tiers — the shared Sustainability-bucket vocabulary + classifier.

pitcher_sustainability and hitter_sustainability had byte-identical bucket chains
differing only in the fp_delta threshold (2.0 fp/start vs 0.5 fp/game). This is
the one home for that logic + the canonical tier names consumers import instead
of literal-matching.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.verdict_tiers import classify_sustainability, SUSTAINABILITY_TIERS


def test_tier_name_set_is_canonical():
    assert SUSTAINABILITY_TIERS == {
        "LEGIT", "IMPROVING", "NOISE", "REGRESS", "BAD_LUCK", "STABLE", "MIXED"
    }


def test_classify_all_outcomes_at_threshold():
    T = 2.0
    assert classify_sustainability(T, 7, T) == "LEGIT"        # up + skills strong
    assert classify_sustainability(T, 5, T) == "IMPROVING"    # up + moderate
    assert classify_sustainability(T, 3, T) == "NOISE"        # up + skills don't support
    assert classify_sustainability(-T, 2, T) == "REGRESS"     # down + skills down
    assert classify_sustainability(-T, 5, T) == "BAD_LUCK"    # down + skills holding
    assert classify_sustainability(0.0, 5, T) == "STABLE"     # no real change
    assert classify_sustainability(T, 4, T) == "MIXED"        # up but n in the gap (4)


def test_threshold_is_parametrized():
    # delta 1.0: a meaningful move at hitter scale (0.5), noise at pitcher scale (2.0)
    assert classify_sustainability(1.0, 7, 0.5) == "LEGIT"
    assert classify_sustainability(1.0, 7, 2.0) == "STABLE"


def _reference_chain(fp_delta, n_material, thr):
    # The exact inline chain both engines used (pre-C3), for equivalence proof.
    if fp_delta >= thr and n_material >= 7:
        return "LEGIT"
    elif fp_delta >= thr and n_material >= 5:
        return "IMPROVING"
    elif fp_delta >= thr and n_material <= 3:
        return "NOISE"
    elif fp_delta <= -thr and n_material <= 2:
        return "REGRESS"
    elif fp_delta <= -thr:
        return "BAD_LUCK"
    elif abs(fp_delta) < thr:
        return "STABLE"
    else:
        return "MIXED"


def test_reproduces_both_engine_chains_over_grid():
    # classify must match the original inline chain for SP (2.0) and H (0.5) scales
    for thr in (2.0, 0.5):
        for delta in [-5, -2.5, -2.0, -0.6, -0.5, -0.4, 0.0, 0.4, 0.5, 0.6, 2.0, 2.5, 5]:
            for n in range(0, 10):
                assert classify_sustainability(delta, n, thr) == _reference_chain(delta, n, thr), \
                    (delta, n, thr)
