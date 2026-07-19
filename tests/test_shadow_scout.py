"""Characterization tests for scripts/xfp/lib/shadow_scout.py.

Percentile-grading logic only: the 20-80 grade mapping, the BB-inversion
(lower walks = higher grade), the verdict thresholds, name->cache-key
conversion, and the NO_MLB_DATA / NaN-metric fallbacks. The duckdb
population loader is monkeypatched with a synthetic frame — no parquet
reads, no network.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

import lib.shadow_scout as ss


# ---------------------------------------------------------------------------
# _grade — percentile -> 20-80 mapping
# ---------------------------------------------------------------------------
def test_grade_percentile_mapping():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ss._grade(6.0, s) == (100.0, 80)      # above everyone
    assert ss._grade(0.0, s) == (0.0, 20)        # below everyone
    assert ss._grade(3.0, s) == (40.0, 44)       # strictly-less-than rank
    assert ss._grade(None, s) == (None, None)
    assert ss._grade(np.nan, s) == (None, None)
    assert ss._grade(3.0, pd.Series(dtype=float)) == (None, None)


# ---------------------------------------------------------------------------
# _name_to_cache — "First Last" -> "Last, First"
# ---------------------------------------------------------------------------
def test_name_to_cache():
    assert ss._name_to_cache('Logan Henderson') == 'Henderson, Logan'
    assert ss._name_to_cache('Luis Garcia') == 'Garcia, Luis'
    # characterization: suffixes are treated as the surname — a known
    # limitation of the naive split (e.g. "Michael Harris II")
    assert ss._name_to_cache('Michael Harris II') == 'II, Michael Harris'


# ---------------------------------------------------------------------------
# shadow_scout — verdict tiers over a synthetic 5-SP population
# ---------------------------------------------------------------------------
def _pop():
    # Ranks are uniform across all 5 metrics so each pitcher's grades are
    # constant: pct in {0,20,40,60,80} -> grades {20,32,44,56,68}.
    return pd.DataFrame({
        'pitcher_name': ['Best, Bob', 'Mid1, M', 'Mid2, M', 'Mid3, M', 'Worst, Wes'],
        'n_pitches':    [500, 400, 400, 400, 300],
        'fb_velo':      [97.0, 94.0, 93.0, 92.0, 89.0],
        'k_pct':        [0.32, 0.24, 0.22, 0.20, 0.15],
        'bb_pct':       [0.05, 0.08, 0.09, 0.10, 0.13],   # LOWER is better
        'whiff_pct':    [0.35, 0.28, 0.26, 0.24, 0.18],
        'csw_pct':      [0.34, 0.30, 0.29, 0.28, 0.25],
    })


def test_shadow_scout_verdict_tiers(monkeypatch):
    monkeypatch.setattr(ss, '_load_population', _pop)
    cards = {c['player']: c for c in ss.shadow_scout(
        ['Bob Best', 'M Mid1', 'M Mid2', 'Wes Worst'])}

    best = cards['Bob Best']
    assert best['avg_grade'] == 68 and best['verdict'] == 'PLUS_PROCESS'
    # BB inversion: lowest bb_pct in the pop earns the TOP bb grade
    assert best['grades']['bb_pct'] == 68
    assert best['n_pitches'] == 500
    assert best['fb_velo'] == 97.0
    assert best['k_pct'] == 32.0                  # displayed in percent

    assert cards['M Mid1']['avg_grade'] == 56
    assert cards['M Mid1']['verdict'] == 'AVG_PROCESS'      # 50 <= avg < 60
    assert cards['M Mid2']['avg_grade'] == 44
    assert cards['M Mid2']['verdict'] == 'BELOW_AVG'        # 40 <= avg < 50
    assert cards['Wes Worst']['avg_grade'] == 20
    assert cards['Wes Worst']['verdict'] == 'BELOW_AVG_HARD'


def test_shadow_scout_unknown_name_no_mlb_data(monkeypatch):
    monkeypatch.setattr(ss, '_load_population', _pop)
    (card,) = ss.shadow_scout(['Nobody Here'])
    assert card['verdict'] == 'NO_MLB_DATA'
    assert card['n_pitches'] == 0
    assert card['avg_grade'] is None
    assert card['grades'] == {}
    assert 'NO MLB 2026 data' in ss.format_card(card)


def test_shadow_scout_nan_metric_excluded_from_avg(monkeypatch):
    # A pitcher with no FF/SI/FC pitches has fb_velo NaN — the grade must be
    # None and the average must be taken over the remaining 4 grades.
    pop = pd.DataFrame({
        'pitcher_name': ['Nofb, N', 'A, A', 'B, B'],
        'n_pitches':    [300, 300, 300],
        'fb_velo':      [np.nan, 92.0, 94.0],
        'k_pct':        [0.30, 0.20, 0.25],
        'bb_pct':       [0.06, 0.10, 0.08],
        'whiff_pct':    [0.30, 0.22, 0.26],
        'csw_pct':      [0.32, 0.27, 0.29],
    })
    monkeypatch.setattr(ss, '_load_population', lambda: pop)
    (card,) = ss.shadow_scout(['N Nofb'])
    assert card['fb_velo'] is None
    assert card['grades']['fb_velo'] is None
    assert card['avg_grade'] is not None
    assert card['verdict'] != 'NO_MLB_DATA'
    # best of 3 on every graded metric -> pct 2/3 -> grade 60 -> PLUS_PROCESS
    assert card['avg_grade'] == 60
    assert card['verdict'] == 'PLUS_PROCESS'
