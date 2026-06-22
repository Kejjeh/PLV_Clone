"""TDD for lib/boom_bust — realized boom/bust actuals lens.

The variance side the model lenses can't show: realized BrownU FP per game/start
over the last N, with boom%/bust%/std/trend. Pure core is boom_bust_summary;
the per-player loaders hit the live MLB gameLog (cached) and are smoke-tested.
Context-only (CLAUDE.md #13).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.boom_bust import boom_bust_summary


def test_summary_counts_and_rates():
    # SP thresholds: boom >=20, bust <5
    s = boom_bust_summary([22, 1, 30, 8, -2, 28, 5, 18], boom_thr=20, bust_thr=5)
    assert s["n"] == 8
    assert s["boom_pct"] == round(3 / 8 * 100)      # 22,30,28
    assert s["bust_pct"] == round(2 / 8 * 100)      # 1,-2 (5 is NOT <5)
    assert s["max"] == 30 and s["min"] == -2
    assert s["mean"] == round(sum([22, 1, 30, 8, -2, 28, 5, 18]) / 8, 1)


def test_summary_trend_l3_vs_full():
    s = boom_bust_summary([0, 0, 0, 0, 30, 30, 30], boom_thr=20, bust_thr=5)
    assert s["l3_mean"] == 30 and s["trend"] == "UP"     # last 3 hot


def test_summary_empty_and_short_safe():
    assert boom_bust_summary([], boom_thr=20, bust_thr=5) is None
    s = boom_bust_summary([10.0], boom_thr=20, bust_thr=5)
    assert s["n"] == 1 and s["std"] == 0.0
