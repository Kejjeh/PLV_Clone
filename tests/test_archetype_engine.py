"""Tests for the shared archetype toolkit (deduplicated from the 3 builders).

These exercise the pure 20-80 scouting helpers that hitter/SP/RP archetype
builders all used to copy-paste. Interface = the test surface.
"""
import numpy as np
import pandas as pd
import pytest

import math

from scripts.xfp.lib.archetype_engine import (
    rating_20_80, bucket, boundary_distance, boundary_tier_label, age_tier,
    rate_value, label_for_cell, rate_pillars, compute_stickiness,
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


def test_rate_value_scalar_scale():
    # Scalar sibling of rating_20_80: 50 at mean, +/-10 per SD, clipped, int.
    assert rate_value(3.0, 3.0, 1.0) == 50
    assert rate_value(5.0, 3.0, 1.0) == 70
    assert rate_value(1.0, 3.0, 1.0) == 30
    assert rate_value(100.0, 3.0, 1.0) == 80   # clipped high
    assert rate_value(-100.0, 3.0, 1.0) == 20  # clipped low
    assert isinstance(rate_value(4.0, 3.0, 1.0), int)


def test_rate_value_invert_flips():
    assert rate_value(5.0, 3.0, 1.0, invert=True) == 30  # +2 SD inverted -> 30


def test_rate_value_none_on_bad_inputs():
    assert rate_value(None, 3.0, 1.0) is None
    assert rate_value(3.0, None, 1.0) is None
    assert rate_value(3.0, 3.0, None) is None
    assert rate_value(3.0, 3.0, 0) is None       # zero SD -> undefined


def test_label_for_cell_builds_cell_and_label():
    defs = {'PLUS/AVG/MINUS': {'label': 'WILD_FIREBALLER'}}
    cell, label = label_for_cell([65, 45, 30], defs)
    assert cell == 'PLUS/AVG/MINUS'
    assert label == 'WILD_FIREBALLER'


def test_label_for_cell_unknown_cell():
    cell, label = label_for_cell([50, 50, 50], {})
    assert cell == 'AVG/AVG/AVG'
    assert label == 'UNKNOWN'


def test_rate_pillars_plain_mean_rounded_int():
    assert rate_pillars([60, 40, 50]) == 50
    assert rate_pillars([61, 40]) == int(round((61 + 40) / 2))  # match int(round()) exactly
    assert isinstance(rate_pillars([60, 40]), int)


def test_rate_pillars_drops_none_components():
    assert rate_pillars([60, None, 40]) == 50          # mean of 60,40
    assert rate_pillars([None, None]) is None          # nothing survives -> None gate
    assert rate_pillars([]) is None


def test_rate_pillars_weighted_mean():
    # (60*3 + 40*1)/4 = 55
    assert rate_pillars([60, 40], weights=[3, 1]) == 55


def test_rate_pillars_uniform_weights_equals_plain():
    # THE graft: weights all-equal must equal the plain mean (one code path).
    assert rate_pillars([60, 40, 50], weights=[1, 1, 1]) == rate_pillars([60, 40, 50])
    assert rate_pillars([66, 48, 51], weights=[2, 2, 2]) == rate_pillars([66, 48, 51])


def test_rate_pillars_weighted_drops_none_with_its_weight():
    # None component (and its weight) drop out; remaining 60,40 weighted 1,1 -> 50
    assert rate_pillars([60, None, 40], weights=[1, 5, 1]) == 50


def test_age_tier_parametrized_peak_windows():
    # hitter windows: PRE<=25, PEAK<=30
    assert age_tier(25, pre_max=25, peak_max=30) == 'PRE_PEAK'
    assert age_tier(30, pre_max=25, peak_max=30) == 'PEAK'
    assert age_tier(31, pre_max=25, peak_max=30) == 'POST_PEAK'
    # SP windows: PRE<=26, PEAK<=31 — 26 is PEAK for hitters but PRE for SPs
    assert age_tier(26, pre_max=26, peak_max=31) == 'PRE_PEAK'
    assert age_tier(np.nan, pre_max=25, peak_max=30) is None


# ── compute_stickiness hoist (item 14): equivalence vs the 3 originals ────────
def _ref_stickiness(qual, id_col, fp_col, ndigits, guard):
    """Reference = the pre-hoist per-position logic, inline."""
    careers = qual.sort_values([id_col, 'year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby(id_col)['archetype'].shift(-1)
    careers['next_year'] = careers.groupby(id_col)['year'].shift(-1)
    careers['next_fp'] = careers.groupby(id_col)[fp_col].shift(-1)
    careers['year_gap'] = careers['next_year'] - careers['year']
    current_year = int(qual['year'].max())
    trans = careers[(careers['year_gap'] == 1) & (careers['next_year'] != current_year)]
    out = {}
    for arch in qual['archetype'].unique():
        sub = trans[trans['archetype'] == arch]
        if len(sub) < 8:
            continue
        n_total = len(sub)
        n_stick = int((sub['next_arch'] == arch).sum())
        top_to = sub['next_arch'].value_counts().head(3).to_dict()

        def _fp(mask):
            if guard and not mask.any():
                return None
            return round(float(sub[mask]['next_fp'].mean()), ndigits)
        entry = {
            'n_total_transitions': n_total, 'n_stayed': n_stick,
            'retention_pct': round(100 * n_stick / n_total, 1),
            'top_destinations': [[k, int(v), round(100 * v / n_total, 1)] for k, v in top_to.items()],
            'fp_if_stayed': _fp(sub['next_arch'] == arch),
            'fp_if_left': _fp(sub['next_arch'] != arch),
            'by_age_tier': {},
        }
        for tier in ['PRE_PEAK', 'PEAK', 'POST_PEAK']:
            sub_t = sub[sub['age_tier'] == tier]
            if len(sub_t) < 5:
                continue
            ret = float((sub_t['next_arch'] == arch).mean())
            entry['by_age_tier'][tier] = {'n': int(len(sub_t)), 'retention_pct': round(100 * ret, 1)}
        out[arch] = entry
    return out


def _panel(id_col, fp_col):
    rows = []
    tiers = ['PRE_PEAK', 'PEAK', 'POST_PEAK']
    for i in range(12):                       # STICKY: never leaves -> empty 'left' subset
        for yr in (2022, 2023, 2024):
            rows.append({id_col: 1000 + i, 'year': yr, 'archetype': 'STICKY',
                         fp_col: 5.0 + (i % 3), 'age_tier': tiers[i % 3]})
    for i in range(14):                       # MOVERA/MOVERB churn
        seq = ['MOVERA', 'MOVERB', 'MOVERA'] if i % 2 == 0 else ['MOVERB', 'MOVERA', 'MOVERB']
        for j, yr in enumerate((2022, 2023, 2024)):
            rows.append({id_col: 2000 + i, 'year': yr, 'archetype': seq[j],
                         fp_col: 3.0 + (i % 4) * 0.5, 'age_tier': tiers[i % 3]})
    return pd.DataFrame(rows)


def _same(a, b):
    assert a.keys() == b.keys()
    for k in a:
        va, vb = a[k], b[k]
        if isinstance(va, dict):
            _same(va, vb)
        elif isinstance(va, float) and isinstance(vb, float) and math.isnan(va) and math.isnan(vb):
            continue
        else:
            assert va == vb, f"{k}: {va!r} != {vb!r}"


def test_stickiness_hitter_equivalence():
    q = _panel('batter', 'fp_per_pa')
    _same(compute_stickiness(q, id_col='batter', fp_col='fp_per_pa', ndigits=3),
          _ref_stickiness(q, 'batter', 'fp_per_pa', 3, False))


def test_stickiness_sp_equivalence():
    q = _panel('pitcher', 'fp_per_start')
    _same(compute_stickiness(q, id_col='pitcher', fp_col='fp_per_start', ndigits=2),
          _ref_stickiness(q, 'pitcher', 'fp_per_start', 2, False))


def test_stickiness_rp_equivalence_and_empty_guard():
    q = _panel('pitcher', 'fp_per_g')
    got = compute_stickiness(q, id_col='pitcher', fp_col='fp_per_g', ndigits=2, guard_empty=True)
    _same(got, _ref_stickiness(q, 'pitcher', 'fp_per_g', 2, True))
    assert got['STICKY']['fp_if_left'] is None   # RP guard: None, not NaN
