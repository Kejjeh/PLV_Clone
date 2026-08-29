"""Issue #29 — rprs2 RoS bands must be ordered: p25 <= mean <= p75.

The old derivation differenced independently-clipped full-year quantiles,
so a reliever who out-banked his projection got an inverted band
(p25 forced to 0 while mean and p75 went negative) — and the signal
column read the corruption as safely-above-replacement.
"""
import numpy as np
import pandas as pd
import pytest

from plv_clone.models.xfp.rprs2 import quantile_band, ros_band


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


# ── the FULL-YEAR band, fixed 2026-08-29 ────────────────────────────────────
# Issue #29 fixed the RoS band by deriving it symmetrically from its own mean.
# The full-year band kept `p25.clip(lower=0)` and rotted for two more months:
# by 2026-08-29 it shipped 29/397 inverted rows, growing with the season as
# more relievers drifted below replacement (11/389 on 08-20 -> 29/397 on
# 08-29). Classic don't-do #18 — a correct fix applied to a strict subset of
# the sites that needed it, failing silently rather than crashing.


def test_ros_band_delegates_to_the_one_owner():
    """Two band derivations is how the sites drifted apart the first time."""
    mean, sigma = np.array([-15.0, 100.0]), np.array([10.0, 20.0])
    a25, a75 = ros_band(mean, sigma)
    b25, b75 = quantile_band(mean, sigma)
    np.testing.assert_allclose(a25, b25)
    np.testing.assert_allclose(a75, b75)


@pytest.mark.parametrize("mean", [-500.0, -167.3, -15.0, -0.1, 0.0, 12.5, 400.0])
def test_quantile_band_never_inverts_at_any_mean(mean):
    """Monotone BY CONSTRUCTION — the property the clip destroyed. -167.3 is
    the most negative full-year projection shipped on 2026-08-29."""
    m = np.array([mean])
    p25, p75 = quantile_band(m, np.array([21.0]))
    assert p25[0] <= m[0] <= p75[0]


def test_quantile_band_does_not_floor_a_negative_lower_bound():
    """A below-replacement reliever's p25 is genuinely negative. Flooring it
    to 0 is what inverted the band, and it also lies about the downside."""
    p25, p75 = quantile_band(np.array([-24.3]), np.array([21.0]))
    assert p25[0] < 0, "p25 must be free to go negative"
    assert p25[0] < p75[0]


def test_band_width_is_symmetric_about_the_mean():
    """The clip narrowed the band on one side only, so the IQR->sigma identity
    every consumer uses — (p75-p25)/1.35 — silently understated sigma."""
    mean, sigma = np.array([-24.3]), np.array([21.0])
    p25, p75 = quantile_band(mean, sigma)
    assert (mean[0] - p25[0]) == pytest.approx(p75[0] - mean[0], abs=0.05)
    assert (p75[0] - p25[0]) / 1.35 == pytest.approx(sigma[0], rel=0.02)


def test_shipped_full_year_bands_are_ordered():
    df = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
    bad = df[(df['xfp_p25'] > df['xfp_full_year'])
             | (df['xfp_full_year'] > df['xfp_p75'])]
    assert bad.empty, bad[['name_api', 'xfp_p25', 'xfp_full_year',
                           'xfp_p75']].head(15).to_string()


def test_shipped_full_year_p25_is_not_pinned_at_zero():
    """The fingerprint of the old clip: p25 == exactly 0.0 on rows whose mean
    is negative. 29 rows carried it on 2026-08-29."""
    df = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
    pinned = df[(df['xfp_p25'] == 0.0) & (df['xfp_full_year'] < 0)]
    assert pinned.empty, pinned[['name_api', 'xfp_full_year', 'xfp_p25']].head().to_string()
