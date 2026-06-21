"""TDD for lib/splits — the platoon (vs L/R) lens.

The pure core is platoon_split(): given per-side (pa, value) it returns the
rates, the lift vs the player's combined rate, sample-adequacy flags, and the
dominant / reverse-split read. Hitter side reads the prebuilt handedness CSV;
pitcher side (the missing half) is computed from statcast grouped by batter stand.
Context-only lens (Rule 13) — never moves rh3/rp3.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.splits import platoon_split


def test_platoon_rates_and_lift():
    # vs L: .360 over 200 PA; vs R: .300 over 600 PA. Combined = (72+180)/800 = .315
    s = platoon_split({"pa": 200, "value": 0.360 * 200},
                      {"pa": 600, "value": 0.300 * 600}, pa_floor=50)
    assert abs(s["rate_vs_L"] - 0.360) < 1e-9
    assert abs(s["rate_vs_R"] - 0.300) < 1e-9
    assert abs(s["combined"] - 0.315) < 1e-9
    assert s["lift_vs_L_pct"] > 0 and s["lift_vs_R_pct"] < 0   # mashes LHP, weaker vs RHP
    assert s["dominant_side"] == "L"
    assert s["sample_ok_L"] and s["sample_ok_R"]


def test_platoon_sample_floor_flags():
    s = platoon_split({"pa": 30, "value": 0.5 * 30},
                      {"pa": 400, "value": 0.3 * 400}, pa_floor=50)
    assert s["sample_ok_L"] is False    # 30 < 50
    assert s["sample_ok_R"] is True


def test_platoon_reverse_split_detection():
    # A hitter better vs same-hand (reverse split): higher vs R than vs L for a RHB
    s = platoon_split({"pa": 200, "value": 0.290 * 200},
                      {"pa": 500, "value": 0.350 * 500}, pa_floor=50)
    assert s["dominant_side"] == "R"


def test_platoon_zero_pa_side_is_safe():
    s = platoon_split({"pa": 0, "value": 0.0},
                      {"pa": 300, "value": 0.31 * 300}, pa_floor=50)
    assert s["rate_vs_L"] is None and s["sample_ok_L"] is False
    assert abs(s["rate_vs_R"] - 0.31) < 1e-9
    # combined falls back to the side with data
    assert s["dominant_side"] in ("R", None)
