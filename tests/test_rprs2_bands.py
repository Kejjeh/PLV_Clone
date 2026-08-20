"""Issue #29 — rprs2 RoS bands must be ordered: p25 <= mean <= p75.

The old derivation differenced independently-clipped full-year quantiles,
so a reliever who out-banked his projection got an inverted band
(p25 forced to 0 while mean and p75 went negative) — and the signal
column read the corruption as safely-above-replacement.
"""
import numpy as np
import pandas as pd

from plv_clone.models.xfp.rprs2 import ros_band


def test_band_brackets_mean_for_normal_row():
    p25, p75 = ros_band(np.array([100.0]), np.array([20.0]))
    assert p25[0] < 100.0 < p75[0]
    # Z25 = 0.6745
    assert p25[0] == np.round(100.0 - 0.6745 * 20.0, 1)
    assert p75[0] == np.round(100.0 + 0.6745 * 20.0, 1)


def test_band_stays_ordered_when_mean_is_negative():
    """The over-banked case that produced the 12 corrupt shipped rows."""
    mean = np.array([-15.0])
    p25, p75 = ros_band(mean, np.array([10.0]))
    assert p25[0] <= mean[0] <= p75[0]
    assert not (p25[0] > p75[0])


def test_shipped_projections_have_no_inverted_bands():
    df = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
    bad = df[(df['xfp_ros_p25'] > df['xfp_ros']) | (df['xfp_ros'] > df['xfp_ros_p75'])]
    assert bad.empty, bad[['player_name', 'xfp_ros_p25', 'xfp_ros', 'xfp_ros_p75']].head(15)
