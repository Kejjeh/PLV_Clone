"""Characterization tests for scripts/xfp/lib/recform_hot.py.

Locks the HOT/COLD/TEPID z-thresholds, the trailing-5-start cohort z-score
math (ddof=0), the as_of leakage filter, the >=3-trailing-starts gate, and
the fp_proxy formula in the per-start loader (via a tmp parquet). No real
cache reads, no network.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

import lib.recform_hot as rh

AS_OF = '2026-06-30'


@pytest.fixture(autouse=True)
def _clear_caches():
    """_cohort_baseline is lru-cached by as_of date and _load_starts_2026 by
    process; clear both around every test so monkeypatched panels never leak."""
    rh._load_starts_2026.cache_clear()
    rh._cohort_baseline.cache_clear()
    yield
    rh._load_starts_2026.cache_clear()
    rh._cohort_baseline.cache_clear()


# ---------------------------------------------------------------------------
# recform_tag — pure threshold mapping
# ---------------------------------------------------------------------------
def test_recform_tag_thresholds():
    assert rh.recform_tag(None) is None
    assert rh.recform_tag(0.5) == 'HOT'          # >= boundary inclusive
    assert rh.recform_tag(0.499) == 'TEPID'
    assert rh.recform_tag(0.0) == 'TEPID'
    assert rh.recform_tag(-0.499) == 'TEPID'
    assert rh.recform_tag(-0.5) == 'COLD'        # <= boundary inclusive
    assert rh.recform_tag(float('nan')) is None
    assert rh.recform_tag('abc') is None


# ---------------------------------------------------------------------------
# Synthetic per-start panel for cohort math
# ---------------------------------------------------------------------------
def _panel():
    rows = []

    def add(pid, day, fp, month=6):
        rows.append({'pitcher': pid, 'game_pk': pid * 100 + day + month * 10000,
                     'game_date': pd.Timestamp(2026, month, day),
                     'BF': 20, 'fp_proxy': float(fp)})

    for d in range(1, 6):
        add(1, d, 20)    # fp_per_bf = 1.0
        add(2, d, 10)    # fp_per_bf = 0.5
        add(3, d, 0)     # fp_per_bf = 0.0
    for d in range(1, 3):
        add(4, d, 10)    # only 2 starts -> excluded from cohort
    # pitcher 5: 7 starts — first 2 huge, last 5 quiet. Trailing window must
    # use ONLY the last 5 (fp_per_bf 0.5), never the early monsters.
    add(5, 1, 100)
    add(5, 2, 100)
    for d in range(10, 15):
        add(5, d, 10)
    # pitcher 6: 3 starts pre-as_of + 2 post-as_of (July) — as_of filter test
    for d in range(20, 23):
        add(6, d, 10)
    add(6, 5, 100, month=7)
    add(6, 10, 100, month=7)
    return (pd.DataFrame(rows)
            .sort_values(['pitcher', 'game_date']).reset_index(drop=True))


# Cohort at AS_OF: pitchers 1,2,3,5,6 with fp_per_bf [1.0, 0.5, 0.0, 0.5, 0.5]
_COHORT = [1.0, 0.5, 0.0, 0.5, 0.5]
_MU = float(np.mean(_COHORT))
_SD = float(np.std(_COHORT))          # ddof=0, matches the module


def test_cohort_z_scores_and_tags(monkeypatch):
    monkeypatch.setattr(rh, '_load_starts_2026', _panel)
    z1 = rh.compute_recform_z(1, AS_OF)
    assert z1 == pytest.approx((1.0 - _MU) / _SD)
    assert rh.recform_tag(z1) == 'HOT'
    assert rh.compute_recform_z(2, AS_OF) == pytest.approx(0.0)
    z3 = rh.compute_recform_z(3, AS_OF)
    assert z3 == pytest.approx((0.0 - _MU) / _SD)
    assert rh.recform_tag(z3) == 'COLD'
    # below MIN_TRAILING_STARTS -> None
    assert rh.compute_recform_z(4, AS_OF) is None
    assert rh.compute_recform_z(999, AS_OF) is None


def test_compute_recform_structured_result(monkeypatch):
    monkeypatch.setattr(rh, '_load_starts_2026', _panel)
    out = rh.compute_recform(1, AS_OF)
    assert out['tag'] == 'HOT'
    assert out['trail_starts'] == 5
    assert out['mean_per_start_fp'] == pytest.approx(20.0)
    assert out['cohort_label'] == '2026-06'
    assert out['cohort_mean_fp_per_bf'] == pytest.approx(_MU)
    assert out['cohort_std_fp_per_bf'] == pytest.approx(_SD)
    out = rh.compute_recform(4, AS_OF)
    assert out['z'] is None and out['reason'] == 'insufficient_trailing_starts'
    out = rh.compute_recform('abc', AS_OF)
    assert out['reason'] == 'bad_pitcher_id'


def test_trailing_window_is_last_5_starts(monkeypatch):
    monkeypatch.setattr(rh, '_load_starts_2026', _panel)
    out = rh.compute_recform(5, AS_OF)
    # first-2 100-FP starts fall OUT of the trailing-5 window
    assert out['trail_starts'] == 5
    assert out['mean_per_start_fp'] == pytest.approx(10.0)
    assert out['z'] == pytest.approx(0.0)          # fp_per_bf 0.5 == cohort mean


def test_as_of_excludes_future_starts(monkeypatch):
    monkeypatch.setattr(rh, '_load_starts_2026', _panel)
    # at June 30, pitcher 6's July starts must be invisible
    out = rh.compute_recform(6, AS_OF)
    assert out['trail_starts'] == 3
    assert out['mean_per_start_fp'] == pytest.approx(10.0)
    # at July 31 they enter the window (trail = 3 June + 2 July starts)
    out = rh.compute_recform(6, '2026-07-31')
    assert out['trail_starts'] == 5
    assert out['mean_per_start_fp'] == pytest.approx((3 * 10 + 2 * 100) / 5)


def test_degenerate_cohort_returns_reason(monkeypatch):
    # single-pitcher cohort -> sd == 0 -> refuse to z-score
    def _single():
        return pd.DataFrame({
            'pitcher': [1] * 5, 'game_pk': range(5),
            'game_date': pd.to_datetime([f'2026-06-{d:02d}' for d in range(1, 6)]),
            'BF': [20] * 5, 'fp_proxy': [10.0] * 5,
        })
    monkeypatch.setattr(rh, '_load_starts_2026', _single)
    out = rh.compute_recform(1, AS_OF)
    assert out['z'] is None and out['reason'] == 'no_cohort_baseline'
    assert rh.compute_recform_z(1, AS_OF) is None


# ---------------------------------------------------------------------------
# _load_starts_2026 — fp_proxy formula + BF floor (tmp parquet)
# ---------------------------------------------------------------------------
def test_loader_fp_proxy_formula_and_bf_floor(tmp_path, monkeypatch):
    rows = []
    # pitcher 77: 15 strikeouts -> BF=15, K=15, outs=15 (IP=5), R=0
    # fp_proxy = 15 + 3.3*5 = 31.5
    for i in range(15):
        rows.append({'game_date': '2026-06-01', 'pitcher': 77, 'game_pk': 1,
                     'events': 'strikeout', 'post_bat_score': 0, 'bat_score': 0})
    # non-PA pitches (events null) must not count toward BF
    for i in range(3):
        rows.append({'game_date': '2026-06-01', 'pitcher': 77, 'game_pk': 1,
                     'events': None, 'post_bat_score': 0, 'bat_score': 0})
    # pitcher 78: 14 field outs + 1 HR scoring 1 run
    # BF=15, H=1, R=1, outs=14 (IP=14/3) -> fp = 3.3*14/3 - 1 - 2 = 12.4
    for i in range(14):
        rows.append({'game_date': '2026-06-02', 'pitcher': 78, 'game_pk': 2,
                     'events': 'field_out', 'post_bat_score': 0, 'bat_score': 0})
    rows.append({'game_date': '2026-06-02', 'pitcher': 78, 'game_pk': 2,
                 'events': 'home_run', 'post_bat_score': 1, 'bat_score': 0})
    # pitcher 79: only 10 PA -> below SP_START_BF_MIN, excluded
    for i in range(10):
        rows.append({'game_date': '2026-06-03', 'pitcher': 79, 'game_pk': 3,
                     'events': 'field_out', 'post_bat_score': 0, 'bat_score': 0})
    pq = tmp_path / 'statcast_2026.parquet'
    pd.DataFrame(rows).to_parquet(pq)
    monkeypatch.setattr(rh, '_STATCAST_2026', pq)

    g = rh._load_starts_2026()
    assert set(g['pitcher']) == {77, 78}
    r77 = g[g['pitcher'] == 77].iloc[0]
    assert r77['BF'] == 15 and r77['K'] == 15
    assert r77['IP'] == pytest.approx(5.0)
    assert r77['fp_proxy'] == pytest.approx(31.5)
    r78 = g[g['pitcher'] == 78].iloc[0]
    assert r78['H'] == 1 and r78['R'] == 1
    assert r78['fp_proxy'] == pytest.approx(12.4)
