"""TDD for lib/home_away — home/road split (relabeled platoon_split core)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.home_away import home_away_split, hitter_home_away


def test_relabel_and_dominant():
    s = home_away_split({"pa": 200, "value": 0.360 * 200},
                        {"pa": 200, "value": 0.300 * 200}, pa_floor=50)
    assert abs(s["rate_home"] - 0.360) < 1e-9 and abs(s["rate_away"] - 0.300) < 1e-9
    assert s["dominant_side"] == "HOME"
    assert s["sample_ok_home"] and s["sample_ok_away"]


def test_road_dominant_and_floor():
    s = home_away_split({"pa": 30, "value": 0.30 * 30},
                        {"pa": 200, "value": 0.36 * 200}, pa_floor=50)
    assert s["dominant_side"] == "AWAY"
    assert s["sample_ok_home"] is False


def test_loader_splits_by_inning_topbot():
    import pandas as pd
    rows = []
    for _ in range(60):  # home (Bot) — strong
        rows.append({"batter": 1, "inning_topbot": "Bot", "events": "single",
                     "woba_value": 0.9, "woba_denom": 1, "estimated_woba_using_speedangle": 0.5})
    for _ in range(60):  # road (Top) — weak
        rows.append({"batter": 1, "inning_topbot": "Top", "events": "single",
                     "woba_value": 0.2, "woba_denom": 1, "estimated_woba_using_speedangle": 0.2})
    out = hitter_home_away(1, statcast_df=pd.DataFrame(rows), pa_floor=40)
    assert out["dominant_side"] == "HOME" and out["pa_home"] == 60
