"""TDD for lib/expected_stats — the expected-vs-actual (luck) lens.

Surfaces xwOBA (expected) vs wOBA (actual) AS SUCH — the canonical 'is this real
or luck' read the audit found was computed internally but never displayed.
Context-only (Rule 13): the gap sizes regression, it does not move rh3/rp3.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.expected_stats import expected_vs_actual


def test_overperforming_flag():
    # actual wOBA well above xwOBA => lucky => due for negative regression
    r = expected_vs_actual(xwoba=0.320, woba=0.360, luck_threshold=0.020)
    assert abs(r["gap"] - 0.040) < 1e-9
    assert r["regression"] == "OVERPERFORMING"


def test_underperforming_flag():
    r = expected_vs_actual(xwoba=0.360, woba=0.320, luck_threshold=0.020)
    assert r["regression"] == "UNDERPERFORMING"   # bounce due


def test_aligned_within_threshold():
    r = expected_vs_actual(xwoba=0.340, woba=0.350, luck_threshold=0.020)
    assert r["regression"] == "ALIGNED"


def test_percentile_passthrough_and_none_safe():
    r = expected_vs_actual(xwoba=0.340, woba=0.340, pctl=88)
    assert r["xwoba_pctl"] == 88
    r2 = expected_vs_actual(xwoba=None, woba=0.340)
    assert r2["gap"] is None and r2["regression"] == "UNKNOWN"
