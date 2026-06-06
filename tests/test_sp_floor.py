"""SP floor (PR 6) — average ros of the bottom-25% of the FA SP bucket.

Plan v11 Decision 8: sort DESCENDING by rank (= ASCENDING by ros),
take TOP 25% by rank (= bottom 25% by ros), average their ros.
"""
import pandas as pd
import pytest

from scripts.xfp.lib.blend_score import _compute_sp_floor_ros


def test_sp_floor_returns_mean_of_bottom_quarter() -> None:
    """8 SPs with ros 1..8. Bottom 25% = 2 SPs => ros 1, 2 => mean 1.5."""
    bucket = pd.DataFrame({"player_name": list("ABCDEFGH"), "ros": [1, 2, 3, 4, 5, 6, 7, 8]})
    assert _compute_sp_floor_ros(bucket) == pytest.approx(1.5)


def test_sp_floor_handles_three_sps_via_round_to_one() -> None:
    """3 SPs: 0.25*3 = 0.75 rounds to 1 => floor is the single worst ros."""
    bucket = pd.DataFrame({"player_name": list("ABC"), "ros": [10.0, 20.0, 30.0]})
    assert _compute_sp_floor_ros(bucket) == pytest.approx(10.0)


def test_sp_floor_returns_none_on_empty() -> None:
    assert _compute_sp_floor_ros(pd.DataFrame({"ros": []})) is None
    assert _compute_sp_floor_ros(pd.DataFrame()) is None
    assert _compute_sp_floor_ros(None) is None


def test_sp_floor_skips_nan_rows() -> None:
    """NaN-ros rows are dropped before the bottom-25% pick."""
    bucket = pd.DataFrame({
        "player_name": list("ABCDE"),
        "ros": [float("nan"), 5.0, 10.0, 15.0, 20.0],
    })
    # 4 non-NaN rows; 0.25*4=1 => bottom 1 ros = 5.0
    assert _compute_sp_floor_ros(bucket) == pytest.approx(5.0)
