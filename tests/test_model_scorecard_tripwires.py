"""Injection tests for the model-health tripwires added 2026-07-11 (W1).

A tripwire that cannot FAIL is decor: each test synthesizes the failure
condition in a tmp fixture, points the scorecard module's path constants
at it, and asserts the check reports FAIL/WARN — plus a healthy fixture
asserting PASS. The checks read module-level Path constants at call time,
so monkeypatching them is the supported injection seam.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pandas as pd
import pytest

import scripts.xfp.build_model_scorecard as msc


@pytest.fixture(autouse=True)
def _clean_rows():
    """Isolate ROWS per test (module-level accumulator)."""
    saved = list(msc.ROWS)
    msc.ROWS.clear()
    yield
    msc.ROWS.clear()
    msc.ROWS.extend(saved)


def _rows(metric: str) -> list[dict]:
    return [r for r in msc.ROWS if r['metric'] == metric]


def _statuses(metric: str) -> dict[str, str]:
    return {r['segment']: r['status'] for r in _rows(metric)}


# ---------------------------------------------------------------------------
# il_grid_coverage
# ---------------------------------------------------------------------------

def _write_grid_fixtures(tmp_path, monkeypatch, *, il_grid, rolling_grid):
    il = pd.DataFrame(il_grid, columns=['year', 'split_day'])
    il['pitcher'] = 100
    il['is_on_il_at_split'] = 0
    il_path = tmp_path / 'il_split_features.csv'
    il.to_csv(il_path, index=False)

    roll = pd.DataFrame(rolling_grid, columns=['year', 'split_day'])
    roll['pitcher'] = 100
    roll_path = tmp_path / 'rolling_pitchers.csv'
    roll.to_csv(roll_path, index=False)

    monkeypatch.setattr(msc, 'IL_CSV', il_path)
    monkeypatch.setattr(msc, 'ROLLING_P_CSV', roll_path)
    # Only exercise the pitcher substrate; point the others at nothing.
    monkeypatch.setattr(msc, 'ROLLING_H_CSV', tmp_path / 'absent_h.csv')
    monkeypatch.setattr(msc, 'ROLLING_R_CSV', tmp_path / 'absent_r.csv')


def test_il_grid_coverage_fails_on_missing_cells(tmp_path, monkeypatch):
    """The 2026-07-09 shape: rolling on a weekly grid, IL cache monthly —
    the weekly cells must be reported as FAIL."""
    _write_grid_fixtures(
        tmp_path, monkeypatch,
        il_grid=[(2026, 30), (2026, 60), (2026, 90), (2026, 120)],
        rolling_grid=[(2026, s) for s in range(30, 121, 7)],
    )
    msc.check_il_grid_coverage()
    st = _statuses('il_grid_coverage')
    assert st['rolling_pitchers'] == 'FAIL'
    assert st['rolling_hitters'] == 'SKIP'
    assert st['rolling_relievers'] == 'SKIP'
    (row,) = [r for r in _rows('il_grid_coverage')
              if r['segment'] == 'rolling_pitchers']
    # weekly grid 30..120 step 7 = 13 cells; only 30 and 44+... none besides
    # 30 coincide with the monthly anchors except 30 itself → 12 missing
    assert row['value'] == 12


def test_il_grid_coverage_passes_on_exact_cover(tmp_path, monkeypatch):
    grid = [(2026, s) for s in range(30, 121, 7)] + [(2025, 30)]
    _write_grid_fixtures(tmp_path, monkeypatch,
                         il_grid=grid + [(2024, 60)],  # superset is fine
                         rolling_grid=grid)
    msc.check_il_grid_coverage()
    assert _statuses('il_grid_coverage')['rolling_pitchers'] == 'PASS'


def test_il_grid_coverage_skips_when_il_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(msc, 'IL_CSV', tmp_path / 'absent.csv')
    msc.check_il_grid_coverage()
    assert _statuses('il_grid_coverage')['all'] == 'SKIP'


# ---------------------------------------------------------------------------
# il_tx_json_freshness
# ---------------------------------------------------------------------------

def _write_tx_json(tmp_path, monkeypatch, *, events, mtime_days_ago=0):
    p = tmp_path / 'il_transactions_2026.json'
    p.write_text(json.dumps(events), encoding='utf-8')
    if mtime_days_ago:
        ts = (pd.Timestamp.now() - pd.Timedelta(days=mtime_days_ago)).timestamp()
        os.utime(p, (ts, ts))
    monkeypatch.setattr(msc, 'IL_TX_JSON', p)
    return p


def test_il_tx_freshness_fails_on_stale_mtime(tmp_path, monkeypatch):
    """Self-refresh dead (the 2026-05-06 frozen-cache mode): file untouched
    for 10 days → file_mtime FAIL, regardless of event content."""
    _write_tx_json(tmp_path, monkeypatch,
                   events=[{'date': '2026-05-06', 'pid': 1, 'desc': 'x'}],
                   mtime_days_ago=10)
    msc.check_il_tx_json_freshness()
    st = _statuses('il_tx_json_freshness')
    assert st['file_mtime'] == 'FAIL'
    # stale events are WARN-only by design (ASG break false-fire guard)
    assert st['newest_event'] == 'WARN'


def test_il_tx_freshness_passes_fresh_file_warns_old_events(tmp_path, monkeypatch):
    """ASG-break shape: refetch ran today (fresh mtime) but the league has
    produced no IL transactions for 9 days → PASS + WARN, never FAIL."""
    old = (date.today() - timedelta(days=9)).isoformat()
    _write_tx_json(tmp_path, monkeypatch,
                   events=[{'date': old, 'pid': 1, 'desc': 'x'}])
    msc.check_il_tx_json_freshness()
    st = _statuses('il_tx_json_freshness')
    assert st['file_mtime'] == 'PASS'
    assert st['newest_event'] == 'WARN'
    assert all(r['status'] != 'FAIL' for r in _rows('il_tx_json_freshness'))


def test_il_tx_freshness_all_pass_when_healthy(tmp_path, monkeypatch):
    recent = (date.today() - timedelta(days=1)).isoformat()
    _write_tx_json(tmp_path, monkeypatch,
                   events=[{'date': recent, 'pid': 1, 'desc': 'x'}])
    msc.check_il_tx_json_freshness()
    st = _statuses('il_tx_json_freshness')
    assert st == {'file_mtime': 'PASS', 'newest_event': 'PASS'}


def test_il_tx_freshness_warns_on_unreadable_json(tmp_path, monkeypatch):
    p = tmp_path / 'il_transactions_2026.json'
    p.write_text('{not json', encoding='utf-8')
    monkeypatch.setattr(msc, 'IL_TX_JSON', p)
    msc.check_il_tx_json_freshness()
    assert _statuses('il_tx_json_freshness')['newest_event'] == 'WARN'
