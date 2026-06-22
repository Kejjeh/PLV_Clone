"""TDD for lib/season_snapshots — in-season archetype trajectory sampler."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.season_snapshots import sample_trajectory


def test_sample_keeps_endpoints_and_count():
    rows = list(range(20))
    s = sample_trajectory(rows, n=6)
    assert s[0] == 0 and s[-1] == 19      # endpoints always kept
    assert 6 <= len(s) <= 7               # ~n, dedup may vary by 1


def test_sample_short_returns_all():
    assert sample_trajectory([1, 2, 3], n=6) == [1, 2, 3]
    assert sample_trajectory([], n=6) == []


def test_sample_monotonic_order_preserved():
    rows = list(range(0, 100, 5))
    s = sample_trajectory(rows, n=5)
    assert s == sorted(s) and s[0] == 0 and s[-1] == 95
