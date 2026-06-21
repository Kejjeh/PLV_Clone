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


# --- expected stats BY SPLIT (vs L/R) ---

def test_expected_by_split_groups_and_flags():
    import pandas as pd
    from lib.expected_stats import hitter_expected_by_split
    # 60 PA vs LHP overperforming (woba >> xwoba); 60 vs RHP aligned
    rows = []
    for _ in range(60):
        rows.append({"batter": 1, "p_throws": "L", "events": "single",
                     "woba_value": 0.90, "woba_denom": 1, "estimated_woba_using_speedangle": 0.30})
    for _ in range(60):
        rows.append({"batter": 1, "p_throws": "R", "events": "single",
                     "woba_value": 0.34, "woba_denom": 1, "estimated_woba_using_speedangle": 0.34})
    df = pd.DataFrame(rows)
    out = hitter_expected_by_split(1, statcast_df=df, pa_floor=40)
    assert out["vs_L"]["regression"] == "OVERPERFORMING"   # .90 actual vs .30 expected = lucky
    assert out["vs_R"]["regression"] == "ALIGNED"
    assert out["vs_L"]["pa"] == 60


def test_expected_by_split_respects_floor():
    import pandas as pd
    from lib.expected_stats import sp_expected_by_split
    rows = [{"pitcher": 9, "stand": "L", "events": "single", "woba_value": 0.3,
             "woba_denom": 1, "estimated_woba_using_speedangle": 0.3} for _ in range(10)]
    df = pd.DataFrame(rows)
    out = sp_expected_by_split(9, statcast_df=df, bf_floor=40)
    assert out["vs_L"] is None    # 10 < 40 floor
    assert out["vs_R"] is None
