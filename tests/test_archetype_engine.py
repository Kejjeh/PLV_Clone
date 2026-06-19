"""Tests for the shared archetype toolkit (deduplicated from the 3 builders).

These exercise the pure 20-80 scouting helpers that hitter/SP/RP archetype
builders all used to copy-paste. Interface = the test surface.
"""
import numpy as np
import pandas as pd
import pytest

from scripts.xfp.lib.archetype_engine import (
    rating_20_80, bucket, boundary_distance, boundary_tier_label, age_tier,
)


def test_rating_20_80_centers_at_50():
    df = pd.DataFrame({'year': [2026] * 5, 'x': [1.0, 2.0, 3.0, 4.0, 5.0]})
    g = df.groupby('year')['x']
    r = rating_20_80(df['x'], g)
    # mean (3.0) maps to 50
    assert r.iloc[2] == pytest.approx(50.0)
    # above mean -> above 50, below -> below 50
    assert r.iloc[4] > 50 and r.iloc[0] < 50


def test_rating_20_80_invert_flips():
    df = pd.DataFrame({'year': [2026] * 3, 'x': [1.0, 2.0, 3.0]})
    g = df.groupby('year')['x']
    plain = rating_20_80(df['x'], g)
    inv = rating_20_80(df['x'], g, invert=True)
    # inverting reflects around the mean (50)
    assert inv.iloc[0] == pytest.approx(100 - plain.iloc[0])


def test_rating_20_80_clipped_to_20_80():
    df = pd.DataFrame({'year': [2026] * 11, 'x': [0.0] * 10 + [1000.0]})
    g = df.groupby('year')['x']
    r = rating_20_80(df['x'], g)
    assert r.max() <= 80 and r.min() >= 20


def test_bucket_thresholds():
    assert bucket(60) == 'PLUS'
    assert bucket(59) == 'AVG'
    assert bucket(40) == 'AVG'
    assert bucket(39) == 'MINUS'


def test_boundary_distance_to_nearest_threshold():
    assert boundary_distance(50) == 10      # min(|50-40|, |50-60|)
    assert boundary_distance(41) == 1
    assert boundary_distance(59) == 1
    assert boundary_distance(60) == 0


def test_boundary_tier_label():
    assert boundary_tier_label(2) == 'EDGE'
    assert boundary_tier_label(5) == 'NEAR_EDGE'
    assert boundary_tier_label(6) == 'SOLID'


def test_age_tier_parametrized_peak_windows():
    # hitter windows: PRE<=25, PEAK<=30
    assert age_tier(25, pre_max=25, peak_max=30) == 'PRE_PEAK'
    assert age_tier(30, pre_max=25, peak_max=30) == 'PEAK'
    assert age_tier(31, pre_max=25, peak_max=30) == 'POST_PEAK'
    # SP windows: PRE<=26, PEAK<=31 — 26 is PEAK for hitters but PRE for SPs
    assert age_tier(26, pre_max=26, peak_max=31) == 'PRE_PEAK'
    assert age_tier(np.nan, pre_max=25, peak_max=30) is None
