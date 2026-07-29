"""Tests for the bat-speed daily accumulator (build_bat_speed_daily.py).

The store is the substrate for the in-season bat-speed study — the sole declared
re-open condition for the closed in-season-delta family — so its aggregation and
idempotency contracts need locking.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="module")
def bsd():
    spec = importlib.util.spec_from_file_location(
        "build_bat_speed_daily", ROOT / "scripts" / "xfp" / "build_bat_speed_daily.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _swings(rows):
    """rows: list of (batter, 'YYYY-MM-DD', bat_speed[, swing_length, source])"""
    recs = []
    for r in rows:
        rec = {"batter": r[0], "game_date": date.fromisoformat(r[1]),
               "bat_speed": r[2]}
        if len(r) > 3:
            rec["swing_length"] = r[3]
        if len(r) > 4:
            rec["source"] = r[4]
        recs.append(rec)
    return pd.DataFrame(recs)


# ── aggregation ──────────────────────────────────────────────────────────────

def test_aggregate_collapses_to_one_row_per_batter_day(bsd):
    df = _swings([(1, "2026-07-01", 70.0), (1, "2026-07-01", 74.0),
                  (1, "2026-07-02", 72.0), (2, "2026-07-01", 68.0)])
    out = bsd.aggregate(df)
    assert len(out) == 3
    assert set(out.columns) >= {"batter", "game_date", "n_swings",
                               "mean_bat_speed", "p90_bat_speed",
                               "fast_swing_rate", "provisional_share",
                               "mean_swing_length"}
    row = out[(out.batter == 1) & (out.game_date == date(2026, 7, 1))].iloc[0]
    assert row.n_swings == 2
    assert row.mean_bat_speed == pytest.approx(72.0)


def test_fast_swing_rate_uses_the_75mph_definition(bsd):
    df = _swings([(1, "2026-07-01", 74.9), (1, "2026-07-01", 75.0),
                  (1, "2026-07-01", 80.0), (1, "2026-07-01", 60.0)])
    out = bsd.aggregate(df)
    # 75.0 and 80.0 qualify -> 2 of 4
    assert out.iloc[0].fast_swing_rate == pytest.approx(0.5)
    assert bsd.FAST_SWING_MPH == 75.0


def test_p90_is_a_real_quantile(bsd):
    df = _swings([(1, "2026-07-01", float(v)) for v in range(60, 80)])
    out = bsd.aggregate(df)
    assert out.iloc[0].p90_bat_speed == pytest.approx(np.quantile(range(60, 80), 0.90))


def test_provisional_share_tracks_the_gf_bridge(bsd):
    df = _swings([(1, "2026-07-01", 70.0, 7.0, "gf_provisional"),
                  (1, "2026-07-01", 71.0, 7.1, ""),
                  (1, "2026-07-01", 72.0, 7.2, "")])
    out = bsd.aggregate(df)
    assert out.iloc[0].provisional_share == pytest.approx(1 / 3)


def test_swing_length_column_present_even_when_source_lacks_it(bsd):
    """gf feed carries batSpeed but NOT swing_length — schema must stay stable."""
    df = _swings([(1, "2026-07-01", 70.0)])
    out = bsd.aggregate(df)
    assert "mean_swing_length" in out.columns
    assert pd.isna(out.iloc[0].mean_swing_length)


def test_aggregate_on_empty_input_returns_empty(bsd):
    assert bsd.aggregate(pd.DataFrame()).empty


def test_batter_is_int_typed(bsd):
    df = _swings([(660271, "2026-07-01", 70.0)])
    out = bsd.aggregate(df)
    assert out.batter.dtype.kind in "iu"


# ── swing filter ─────────────────────────────────────────────────────────────

def test_sensor_junk_floor_matches_trend_signal(bsd):
    """bat_speed <= 10 is sensor junk; lib/trend_signal uses the same floor."""
    assert bsd.MIN_BAT_SPEED == 10.0


# ── idempotent upsert ────────────────────────────────────────────────────────

def test_upsert_is_idempotent_on_batter_day(bsd, tmp_path, monkeypatch):
    monkeypatch.setattr(bsd, "OUT_PARQUET", tmp_path / "bs.parquet")
    first = bsd.aggregate(_swings([(1, "2026-07-01", 70.0), (2, "2026-07-01", 68.0)]))

    added, replaced = bsd.upsert(first)
    assert (added, replaced) == (2, 0)

    # same day again -> replaces, never duplicates
    added2, replaced2 = bsd.upsert(first)
    assert added2 == 0 and replaced2 == 2
    stored = pd.read_parquet(bsd.OUT_PARQUET)
    assert len(stored) == 2


def test_upsert_last_wins_so_a_provisional_day_upgrades_in_place(bsd, tmp_path, monkeypatch):
    """The canonical pull must be able to overwrite a gf_provisional day."""
    monkeypatch.setattr(bsd, "OUT_PARQUET", tmp_path / "bs.parquet")
    prov = bsd.aggregate(_swings([(1, "2026-07-01", 70.0, 7.0, "gf_provisional")]))
    bsd.upsert(prov)
    assert pd.read_parquet(bsd.OUT_PARQUET).iloc[0].provisional_share == 1.0

    canon = bsd.aggregate(_swings([(1, "2026-07-01", 71.0, 7.0, ""),
                                   (1, "2026-07-01", 73.0, 7.0, "")]))
    bsd.upsert(canon)
    stored = pd.read_parquet(bsd.OUT_PARQUET)
    assert len(stored) == 1
    assert stored.iloc[0].provisional_share == 0.0
    assert stored.iloc[0].n_swings == 2


def test_upsert_adds_new_days_without_touching_old(bsd, tmp_path, monkeypatch):
    monkeypatch.setattr(bsd, "OUT_PARQUET", tmp_path / "bs.parquet")
    bsd.upsert(bsd.aggregate(_swings([(1, "2026-07-01", 70.0)])))
    added, replaced = bsd.upsert(bsd.aggregate(_swings([(1, "2026-07-02", 72.0)])))
    assert (added, replaced) == (1, 0)
    assert len(pd.read_parquet(bsd.OUT_PARQUET)) == 2


def test_upsert_stamps_built_at(bsd, tmp_path, monkeypatch):
    monkeypatch.setattr(bsd, "OUT_PARQUET", tmp_path / "bs.parquet")
    bsd.upsert(bsd.aggregate(_swings([(1, "2026-07-01", 70.0)])))
    assert pd.read_parquet(bsd.OUT_PARQUET)["built_at"].notna().all()


def test_upsert_leaves_no_temp_file(bsd, tmp_path, monkeypatch):
    monkeypatch.setattr(bsd, "OUT_PARQUET", tmp_path / "bs.parquet")
    bsd.upsert(bsd.aggregate(_swings([(1, "2026-07-01", 70.0)])))
    assert not (tmp_path / "bs.parquet.tmp").exists()


def test_upsert_empty_is_a_noop(bsd, tmp_path, monkeypatch):
    monkeypatch.setattr(bsd, "OUT_PARQUET", tmp_path / "bs.parquet")
    assert bsd.upsert(pd.DataFrame()) == (0, 0)
    assert not bsd.OUT_PARQUET.exists()


# ── source-of-truth wiring ───────────────────────────────────────────────────

def test_reads_xfp_cache_not_the_raw_mirror(bsd):
    """data/raw/statcast_*.parquet has NO bat_speed column — only xfp_cache does.
    Reading the wrong mirror would silently yield an empty store."""
    assert bsd._statcast_path(2026).parent.name == "xfp_cache"


def test_bat_tracking_starts_2024(bsd):
    assert bsd.FIRST_YEAR == 2024


def test_registered_as_a_nonhgating_refresh_step():
    src = (ROOT / "scripts" / "xfp" / "refresh_dashboards.py").read_text(encoding="utf-8")
    assert "build_bat_speed_daily.py" in src
    assert "1.65" in src
