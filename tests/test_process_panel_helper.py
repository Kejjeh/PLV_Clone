"""Canary tests for ``scripts.xfp.lib.process_panel.aggregate_sp_markers_statcast``.

These five tests lock in the canonical SP marker definitions vs
``scripts/xfp/build_rolling_pitchers.py:23`` and ``pitcher_sustainability.py``.
Each test seeds rows that would FAIL under a looser definition (e.g.,
SwStr defined as only `'swinging_strike'`, barrel as the string `'barrel'`,
xwoba_contact merely requiring `events not null AND launch_speed not null`).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.xfp.lib.process_panel import (
    SWSTR_DESC,
    aggregate_sp_markers_statcast,
)


def _seed_parquet(rows: list[dict], tmp_path: Path, name: str = 'seed.parquet') -> Path:
    """Write rows to a Statcast-shaped parquet. Columns the helper requires:

    pitcher, game_date, events, description, zone, release_speed,
    launch_speed, launch_speed_angle, estimated_woba_using_speedangle.
    """
    df = pd.DataFrame(rows)
    needed = {
        'pitcher', 'game_date', 'events', 'description', 'zone',
        'release_speed', 'launch_speed', 'launch_speed_angle',
        'estimated_woba_using_speedangle',
    }
    for col in needed:
        if col not in df.columns:
            df[col] = pd.NA
    df['game_date'] = pd.to_datetime(df['game_date'])
    df['zone'] = pd.to_numeric(df['zone'], errors='coerce').astype('Int64')
    df['launch_speed_angle'] = pd.to_numeric(df['launch_speed_angle'], errors='coerce').astype('Int64')
    df['release_speed'] = pd.to_numeric(df['release_speed'], errors='coerce')
    df['launch_speed'] = pd.to_numeric(df['launch_speed'], errors='coerce')
    df['estimated_woba_using_speedangle'] = pd.to_numeric(
        df['estimated_woba_using_speedangle'], errors='coerce'
    )
    out = tmp_path / name
    df.to_parquet(out)
    return out


def _make_pitch(
    description: str = 'ball',
    events=None,
    zone: int = 1,
    *,
    pitcher: int = 999,
    game_date: str = '2026-05-01',
    release_speed: float = 95.0,
    launch_speed=None,
    launch_speed_angle=None,
    xwoba=None,
) -> dict:
    return {
        'pitcher': pitcher,
        'game_date': game_date,
        'events': events,
        'description': description,
        'zone': zone,
        'release_speed': release_speed,
        'launch_speed': launch_speed,
        'launch_speed_angle': launch_speed_angle,
        'estimated_woba_using_speedangle': xwoba,
    }


# ---------------------------------------------------------------------------
# Test 1: swstr_pct uses the FULL SWSTR_DESC set, not just 'swinging_strike'.
# ---------------------------------------------------------------------------

def test_aggregate_sp_swstr_pct(tmp_path: Path):
    """SwStr = 18 swinging_strike + 2 swinging_strike_blocked + 1 foul_tip
    + 1 missed_bunt = 22/100 = 0.220 (verifies full SWSTR_DESC set).
    """
    assert SWSTR_DESC == {
        'swinging_strike', 'swinging_strike_blocked', 'foul_tip', 'missed_bunt'
    }, 'SWSTR_DESC canonical set drifted'

    rows: list[dict] = []
    # 18 swinging_strike (zone 5 to avoid OOZ noise)
    rows += [_make_pitch(description='swinging_strike', zone=5) for _ in range(18)]
    # 2 swinging_strike_blocked
    rows += [_make_pitch(description='swinging_strike_blocked', zone=5) for _ in range(2)]
    # 1 foul_tip
    rows += [_make_pitch(description='foul_tip', zone=5) for _ in range(1)]
    # 1 missed_bunt
    rows += [_make_pitch(description='missed_bunt', zone=5) for _ in range(1)]
    # 60 balls and 18 called_strike to reach 100 total pitches
    rows += [_make_pitch(description='ball', zone=12) for _ in range(60)]
    rows += [_make_pitch(description='called_strike', zone=5) for _ in range(18)]
    assert len(rows) == 100

    pq = _seed_parquet(rows, tmp_path)
    df = aggregate_sp_markers_statcast(str(pq))
    assert len(df) == 1
    assert df['pitches'].iloc[0] == 100
    assert df['swstr_pct'].iloc[0] == pytest.approx(0.220, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 2: c_plus_swstr = (called_strike + SWSTR_DESC) / pitches.
# ---------------------------------------------------------------------------

def test_aggregate_sp_c_plus_swstr(tmp_path: Path):
    """CSW = 18 called_strike + 22 SwStr (same seeding as Test 1) = 40/100 = 0.400."""
    rows: list[dict] = []
    rows += [_make_pitch(description='swinging_strike', zone=5) for _ in range(18)]
    rows += [_make_pitch(description='swinging_strike_blocked', zone=5) for _ in range(2)]
    rows += [_make_pitch(description='foul_tip', zone=5) for _ in range(1)]
    rows += [_make_pitch(description='missed_bunt', zone=5) for _ in range(1)]
    rows += [_make_pitch(description='called_strike', zone=5) for _ in range(18)]
    rows += [_make_pitch(description='ball', zone=12) for _ in range(60)]
    assert len(rows) == 100

    pq = _seed_parquet(rows, tmp_path)
    df = aggregate_sp_markers_statcast(str(pq))
    assert len(df) == 1
    assert df['c_plus_swstr'].iloc[0] == pytest.approx(0.400, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 3: o_swing_pct = OOZ swings / OOZ pitches with zone IN (1..9) = in-zone.
# ---------------------------------------------------------------------------

def test_aggregate_sp_o_swing_pct(tmp_path: Path):
    """OOZ swings / OOZ pitches.

    Seeding:
      - 30 OOZ pitches (zone=12): 12 swings + 18 takes (ball)
      - 70 in-zone pitches (zone=5): 50 swings + 20 takes
    Expected: chase = 12 / 30 = 0.400.
    """
    rows: list[dict] = []
    # OOZ swings: 12 foul (description='foul' is in SWING_DESC but not SWSTR)
    rows += [_make_pitch(description='foul', zone=12) for _ in range(12)]
    # OOZ takes: 18 balls
    rows += [_make_pitch(description='ball', zone=12) for _ in range(18)]
    # In-zone swings: 50 foul
    rows += [_make_pitch(description='foul', zone=5) for _ in range(50)]
    # In-zone takes: 20 called_strike (NOT a swing)
    rows += [_make_pitch(description='called_strike', zone=5) for _ in range(20)]
    assert len(rows) == 100

    pq = _seed_parquet(rows, tmp_path)
    df = aggregate_sp_markers_statcast(str(pq))
    assert len(df) == 1
    assert df['o_swing_pct'].iloc[0] == pytest.approx(12 / 30, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 4: barrel uses NUMERIC launch_speed_angle = 6, NOT the string 'barrel'.
# ---------------------------------------------------------------------------

def test_aggregate_sp_barrel_pct(tmp_path: Path):
    """Barrel definition is ``launch_speed_angle = 6`` (numeric).

    Seeding 10 BIP rows:
      - 3 rows with launch_speed_angle = 6 (real barrels)
      - 2 rows with the STRING 'barrel' (must be ignored - column is numeric)
      - 5 rows with launch_speed_angle = 3 (non-barrels)

    Expected: barrel_pct = 3 / 10 = 0.300.

    Note: in the actual parquet, launch_speed_angle is BIGINT, so the
    string seeding above coerces to NULL via TRY_CAST, which means those
    rows have lsa = NULL. With launch_speed = 100 they still count as
    is_bip + is_hard_hit (launch_speed >= 95) but NOT is_barrel.
    """
    rows: list[dict] = []
    # 3 real barrels
    rows += [_make_pitch(
        description='hit_into_play', events='home_run',
        launch_speed=105.0, launch_speed_angle=6, xwoba=2.0,
    ) for _ in range(3)]
    # 2 rows with string 'barrel' (will be NULL after TRY_CAST)
    rows += [_make_pitch(
        description='hit_into_play', events='single',
        launch_speed=100.0, launch_speed_angle='barrel', xwoba=0.8,
    ) for _ in range(2)]
    # 5 non-barrels (lsa = 3)
    rows += [_make_pitch(
        description='hit_into_play', events='field_out',
        launch_speed=95.0, launch_speed_angle=3, xwoba=0.3,
    ) for _ in range(5)]

    pq = _seed_parquet(rows, tmp_path)
    df = aggregate_sp_markers_statcast(str(pq))
    assert len(df) == 1
    assert df['bip'].iloc[0] == 10
    assert df['barrel_pct'].iloc[0] == pytest.approx(0.300, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 5: xwoba_contact = AVG over BIP rows where xwoba IS NOT NULL.
# Excludes BIP rows with xwoba = NULL even when events + launch_speed are set.
# ---------------------------------------------------------------------------

def test_aggregate_sp_xwoba_contact(tmp_path: Path):
    """xwoba_contact aggregates over BIP rows with valid xwOBA only.

    Seeding 3 BIP rows:
      - 1 row events='home_run', launch_speed=105, xwoba=2.0 (included)
      - 1 row events='double',   launch_speed=100, xwoba=1.0 (included)
      - 1 row events='single',   launch_speed=95,  xwoba=NULL (EXCLUDED)

    Under a wrong looser definition (events not null AND launch_speed not null
    is sufficient) the average would be (2.0 + 1.0 + 0) / 3 = 1.0 (with 0
    coercion) or 1.5 (if NULL filtered out but the sample size 3) - either
    way different from the canonical 1.5 over n=2.

    Canonical: average is (2.0 + 1.0) / 2 = 1.5.
    """
    rows = [
        _make_pitch(description='hit_into_play', events='home_run',
                    launch_speed=105.0, launch_speed_angle=6, xwoba=2.0),
        _make_pitch(description='hit_into_play', events='double',
                    launch_speed=100.0, launch_speed_angle=5, xwoba=1.0),
        _make_pitch(description='hit_into_play', events='single',
                    launch_speed=95.0, launch_speed_angle=4, xwoba=None),
    ]
    pq = _seed_parquet(rows, tmp_path)
    df = aggregate_sp_markers_statcast(str(pq))
    assert len(df) == 1
    assert df['bip'].iloc[0] == 3
    assert df['xwoba_contact'].iloc[0] == pytest.approx(1.5, abs=1e-9)


