"""Characterization tests for scripts/xfp/lib/il_return_flag.py (IL_RETURN tag).

IL-join-adjacent (historical 6-week silent regression area): locks the
gap/threshold logic, the reference-date fallback chain, the >=5-PA start
filter in the last-start join, and the past-date filter in the schedule join.
Loaders are either monkeypatched or pointed at tmp_path files — no real
cache reads.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

import lib.il_return_flag as irf


@pytest.fixture(autouse=True)
def _clear_loader_caches():
    """The two loaders are lru_cached; clear around every test so tmp-path
    monkeypatching never leaks into (or inherits from) other tests."""
    irf._load_last_start_per_pitcher_2026.cache_clear()
    irf._load_next_scheduled_start.cache_clear()
    yield
    irf._load_last_start_per_pitcher_2026.cache_clear()
    irf._load_next_scheduled_start.cache_clear()


# ---------------------------------------------------------------------------
# compute_il_return_flag — gap/threshold + fallback chain (loaders mocked)
# ---------------------------------------------------------------------------
def test_flag_fires_on_long_gap_with_scheduled_start(monkeypatch):
    monkeypatch.setattr(irf, '_load_last_start_per_pitcher_2026',
                        lambda: {10: pd.Timestamp('2026-06-01')})
    monkeypatch.setattr(irf, '_load_next_scheduled_start',
                        lambda: {10: pd.Timestamp('2026-07-05')})
    out = irf.compute_il_return_flag(10)
    assert out['is_first_back_long_il'] is True
    assert out['days_since_last_start'] == 34
    assert out['last_start_date'] == '2026-06-01'
    assert out['reference_date'] == '2026-07-05'
    assert out['reference_source'] == 'next_scheduled'
    assert out['threshold_days'] == 30
    assert out['reason'] is None


def test_gap_below_threshold_does_not_fire(monkeypatch):
    monkeypatch.setattr(irf, '_load_last_start_per_pitcher_2026',
                        lambda: {10: pd.Timestamp('2026-06-01')})
    monkeypatch.setattr(irf, '_load_next_scheduled_start',
                        lambda: {10: pd.Timestamp('2026-06-20')})
    out = irf.compute_il_return_flag(10)
    assert out['is_first_back_long_il'] is False
    assert out['days_since_last_start'] == 19
    assert out['reason'] == 'gap_19d_below_threshold'


def test_gap_exactly_30_fires(monkeypatch):
    monkeypatch.setattr(irf, '_load_last_start_per_pitcher_2026',
                        lambda: {10: pd.Timestamp('2026-06-01')})
    monkeypatch.setattr(irf, '_load_next_scheduled_start',
                        lambda: {10: pd.Timestamp('2026-07-01')})
    out = irf.compute_il_return_flag(10)
    assert out['days_since_last_start'] == 30
    assert out['is_first_back_long_il'] is True     # >= boundary is inclusive


def test_no_scheduled_start_falls_back_to_today(monkeypatch):
    last = pd.Timestamp(date.today()) - pd.Timedelta(days=40)
    monkeypatch.setattr(irf, '_load_last_start_per_pitcher_2026',
                        lambda: {10: last})
    monkeypatch.setattr(irf, '_load_next_scheduled_start', lambda: {})
    out = irf.compute_il_return_flag(10)
    assert out['reference_source'] == 'today'
    assert out['days_since_last_start'] == 40
    assert out['is_first_back_long_il'] is True


def test_missing_pitcher_and_bad_id(monkeypatch):
    monkeypatch.setattr(irf, '_load_last_start_per_pitcher_2026', lambda: {})
    monkeypatch.setattr(irf, '_load_next_scheduled_start', lambda: {})
    out = irf.compute_il_return_flag(10)
    assert out['is_first_back_long_il'] is False
    assert out['reason'] == 'no_2026_start'
    assert out['reference_source'] == 'none'
    out = irf.compute_il_return_flag('abc')
    assert out['is_first_back_long_il'] is False
    assert out['reason'] == 'bad_pitcher_id'


# ---------------------------------------------------------------------------
# _load_last_start_per_pitcher_2026 — >=5-PA start filter + max-date join
# ---------------------------------------------------------------------------
def test_last_start_loader_pa_filter_and_max(tmp_path, monkeypatch):
    rows = []
    # pitcher 10: 6 PA on 06-01 and 6 PA on 06-10 -> both starts, last = 06-10
    for d, n in (('2026-06-01', 6), ('2026-06-10', 6)):
        for _ in range(n):
            rows.append({'pitcher': 10, 'game_date': d, 'events': 'field_out'})
    # pitcher 10 on 06-15: only 3 PA-ending pitches + 5 null-event pitches
    # -> below the 5-PA floor, must NOT count as a start
    for _ in range(3):
        rows.append({'pitcher': 10, 'game_date': '2026-06-15', 'events': 'strikeout'})
    for _ in range(5):
        rows.append({'pitcher': 10, 'game_date': '2026-06-15', 'events': None})
    # pitcher 11: 4 PA on his only date -> excluded entirely
    for _ in range(4):
        rows.append({'pitcher': 11, 'game_date': '2026-06-05', 'events': 'single'})
    pq = tmp_path / 'statcast_2026.parquet'
    pd.DataFrame(rows).to_parquet(pq)
    monkeypatch.setattr(irf, '_STATCAST_2026', str(pq))
    out = irf._load_last_start_per_pitcher_2026()
    assert out == {10: pd.Timestamp('2026-06-10')}
    assert 11 not in out


def test_last_start_loader_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(irf, '_STATCAST_2026', str(tmp_path / 'nope.parquet'))
    assert irf._load_last_start_per_pitcher_2026() == {}


# ---------------------------------------------------------------------------
# _load_next_scheduled_start — past-date filter + earliest-date join
# ---------------------------------------------------------------------------
def test_next_scheduled_loader_filters_past_and_takes_min(tmp_path, monkeypatch):
    today = pd.Timestamp(date.today())
    df = pd.DataFrame({
        'pitcher': [10, 10, 10, 11],
        'game_date': [
            (today - pd.Timedelta(days=3)).strftime('%Y-%m-%d'),   # past: dropped
            (today + pd.Timedelta(days=6)).strftime('%Y-%m-%d'),
            (today + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),   # earliest future
            (today - pd.Timedelta(days=10)).strftime('%Y-%m-%d'),  # 11 all-past
        ],
    })
    csv = tmp_path / 'pitcher_schedule_2026.csv'
    df.to_csv(csv, index=False)
    monkeypatch.setattr(irf, '_PITCHER_SCHEDULE', str(csv))
    out = irf._load_next_scheduled_start()
    assert out == {10: today + pd.Timedelta(days=1)}
    assert 11 not in out


def test_next_scheduled_loader_defensive_empties(tmp_path, monkeypatch):
    # missing file -> {}
    monkeypatch.setattr(irf, '_PITCHER_SCHEDULE', str(tmp_path / 'nope.csv'))
    assert irf._load_next_scheduled_start() == {}
    irf._load_next_scheduled_start.cache_clear()
    # wrong columns -> {}
    bad = tmp_path / 'bad.csv'
    pd.DataFrame({'foo': [1], 'bar': [2]}).to_csv(bad, index=False)
    monkeypatch.setattr(irf, '_PITCHER_SCHEDULE', str(bad))
    assert irf._load_next_scheduled_start() == {}
