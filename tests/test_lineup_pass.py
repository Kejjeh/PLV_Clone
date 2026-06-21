"""TDD for lib/lineup_pass — times-through-order (TTO) decay lens.

A pitcher's core_fp/PA on the 3rd time through the order vs the 1st — the
within-start durability complement to the per-start floor model. Context-only
(CLAUDE.md #13). Rates are pitcher-side core_fp/PA (negative; lower = worse).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.lineup_pass import tto_decay


def test_steep_decay_tier():
    r = tto_decay(-0.20, -0.32, 150)         # penalty -0.12
    assert abs(r["penalty"] + 0.12) < 1e-9
    assert r["tier"] == "STEEP_DECAY" and r["sample_ok"] is True


def test_average_and_durable_tiers():
    assert tto_decay(-0.20, -0.21, 150)["tier"] == "AVERAGE"   # -0.01
    assert tto_decay(-0.20, -0.13, 150)["tier"] == "DURABLE"   # +0.07
    assert tto_decay(-0.20, -0.26, 150)["tier"] == "DECAY"     # -0.06


def test_sample_floor():
    assert tto_decay(-0.20, -0.32, 60)["sample_ok"] is False   # 60 < 100


def test_none_safe():
    r = tto_decay(None, -0.3, 150)
    assert r["penalty"] is None and r["tier"] == "UNKNOWN" and r["sample_ok"] is False
