"""Characterization tests for scripts/xfp/lib/boom_stack.py (SP boom_stack).

Locks current behavior of the pure scoring/tier functions: tier mapping,
component thresholds, 0-4 stack summation, per-tier rate lookups, the
anti-predictive skill_spike flag, and the HIGH-K ARM z-gate. All data-touching
loaders are monkeypatched with synthetic frames — no parquet/CSV/network.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

import numpy as np
import pandas as pd
import pytest

import lib.boom_stack as bs


# ---------------------------------------------------------------------------
# tier_for_rank — boundary map
# ---------------------------------------------------------------------------
def test_tier_for_rank_boundaries():
    assert bs.tier_for_rank(1) == 'ace'
    assert bs.tier_for_rank(10) == 'ace'
    assert bs.tier_for_rank(11) == 'sp2_sp3'
    assert bs.tier_for_rank(30) == 'sp2_sp3'
    assert bs.tier_for_rank(31) == 'backend'
    assert bs.tier_for_rank(50) == 'backend'
    assert bs.tier_for_rank(51) == 'streamer'
    assert bs.tier_for_rank(200) == 'streamer'


# ---------------------------------------------------------------------------
# lookup_week_boom_rate — clamping + defensive defaults
# ---------------------------------------------------------------------------
def test_lookup_week_boom_rate_values_and_clamps():
    assert bs.lookup_week_boom_rate('ace', 3) == pytest.approx(83.3)
    assert bs.lookup_week_boom_rate('streamer', 0) == pytest.approx(20.0)
    # stack clamped into [0, 3]
    assert bs.lookup_week_boom_rate('ace', 7) == pytest.approx(83.3)
    assert bs.lookup_week_boom_rate('ace', -2) == pytest.approx(67.1)
    # unknown tier / unparseable stack -> 0.0, never a wrong tier's rate
    assert bs.lookup_week_boom_rate('nope', 2) == 0.0
    assert bs.lookup_week_boom_rate('ace', 'x') == 0.0
    assert bs.lookup_week_boom_rate('ace', None) == 0.0


def test_tier_rate_tables_cover_stack_0_to_4():
    tiers = {'ace', 'sp2_sp3', 'backend', 'streamer'}
    for table in (bs.BOOM_RATE_BY_TIER_STACK, bs.BUST_RATE_BY_TIER_STACK,
                  bs.MEAN_FP_BY_TIER_STACK):
        assert set(table) == tiers
        for tier in tiers:
            assert set(table[tier]) == {0, 1, 2, 3, 4}
    # ace + streamer boom rates are monotonically non-decreasing in stack
    for tier in ('ace', 'streamer'):
        vals = [bs.BOOM_RATE_BY_TIER_STACK[tier][s] for s in range(5)]
        assert vals == sorted(vals)


# ---------------------------------------------------------------------------
# _component_recform_hot — pure threshold
# ---------------------------------------------------------------------------
def test_component_recform_hot_threshold():
    assert bs._component_recform_hot(None) == (0, {'recency_form_gap': None})
    fired, _ = bs._component_recform_hot(float('nan'))
    assert fired == 0
    assert bs._component_recform_hot(2.99)[0] == 0
    assert bs._component_recform_hot(3.0)[0] == 1     # >= boundary fires
    fired, detail = bs._component_recform_hot(5.5)
    assert fired == 1 and detail['recency_form_gap'] == 5.5


# ---------------------------------------------------------------------------
# _component_opp_soft — soft-tertile gate (team_strength monkeypatched)
# ---------------------------------------------------------------------------
def test_component_opp_soft(monkeypatch):
    ts = pd.DataFrame({'team': ['MIA', 'NYY', 'CWS'],
                       'bat_index_recent': [0.85, 1.15, 0.90]})
    monkeypatch.setattr(bs, '_load_soft_tertile', lambda: (0.90, ts))
    assert bs._component_opp_soft(None) == (0, {'next_opp_team': None,
                                                'reason': 'no_next_opp'})
    fired, detail = bs._component_opp_soft('COL')
    assert fired == 0 and detail['reason'] == 'team_not_in_strength_csv'
    assert bs._component_opp_soft('MIA')[0] == 1      # below p33
    assert bs._component_opp_soft('CWS')[0] == 1      # exactly p33 fires (<=)
    assert bs._component_opp_soft('NYY')[0] == 0      # above p33


# ---------------------------------------------------------------------------
# _component_skill_spike — synthetic per-start panel
# ---------------------------------------------------------------------------
def _starts_panel():
    rows = []
    # pitcher 999: 10 starts, PA=20 each. First 5 K=4/BB=2; last 5 K=6/BB=1.
    # Season K%=25 BB%=7.5; L5 K%=30 BB%=5 -> dK=+5pp, dBB=-2.5pp -> FIRES.
    for i in range(10):
        rows.append({'pitcher': 999, 'game_pk': 1000 + i,
                     'game_date': f'2026-06-{i + 1:02d}',
                     'pa': 20, 'k': 4 if i < 5 else 6, 'bb': 2 if i < 5 else 1})
    # pitcher 222: K spike but no BB drop -> does NOT fire.
    for i in range(10):
        rows.append({'pitcher': 222, 'game_pk': 2000 + i,
                     'game_date': f'2026-06-{i + 1:02d}',
                     'pa': 20, 'k': 4 if i < 5 else 6, 'bb': 2})
    # pitcher 111: only 4 starts -> insufficient.
    for i in range(4):
        rows.append({'pitcher': 111, 'game_pk': 3000 + i,
                     'game_date': f'2026-06-{i + 1:02d}',
                     'pa': 20, 'k': 5, 'bb': 2})
    return pd.DataFrame(rows).sort_values(['pitcher', 'game_date']).reset_index(drop=True)


def test_component_skill_spike(monkeypatch):
    monkeypatch.setattr(bs, '_load_starts_2026', _starts_panel)
    fired, d = bs._component_skill_spike(999)
    assert fired == 1
    assert d['delta_k_pp'] == pytest.approx(5.0)
    assert d['delta_bb_pp'] == pytest.approx(-2.5)
    fired, d = bs._component_skill_spike(222)
    assert fired == 0 and d['delta_bb_pp'] == pytest.approx(0.0)
    fired, d = bs._component_skill_spike(111)
    assert fired == 0 and d['reason'] == 'insufficient_starts'
    assert d['n_starts_2026'] == 4


# ---------------------------------------------------------------------------
# _component_park_friendly — schedule/park set monkeypatched
# ---------------------------------------------------------------------------
def test_component_park_friendly(monkeypatch):
    sched = pd.DataFrame({'pitcher': [10, 10, 20],
                          'park_team': ['SD', 'COL', 'COL'],
                          'start_idx': [1, 2, 1]})
    monkeypatch.setattr(bs, '_load_pitcher_schedule', lambda: sched)
    monkeypatch.setattr(bs, '_load_park_friendly_set',
                        lambda: (frozenset({'SD', 'SEA'}), 0.29, 2025))
    monkeypatch.setattr(bs, '_pf_woba_map', lambda: {(2025, 'SD'): 0.285})
    fired, d = bs._component_park_friendly(10)     # next start (start_idx=1) is SD
    assert fired == 1 and d['park_team'] == 'SD' and d['pf_wOBA'] == 0.285
    fired, d = bs._component_park_friendly(20)     # COL not friendly
    assert fired == 0 and d['reason'] == 'park_not_in_friendly_tertile'
    fired, d = bs._component_park_friendly(99)     # not in schedule
    assert fired == 0 and d['reason'] == 'no_scheduled_start'
    fired, d = bs._component_park_friendly('abc')  # unparseable id
    assert fired == 0 and d['reason'] == 'bad_pitcher_id'
    monkeypatch.setattr(bs, '_load_pitcher_schedule', lambda: None)
    fired, d = bs._component_park_friendly(10)
    assert fired == 0 and d['reason'] == 'no_schedule_file'


# ---------------------------------------------------------------------------
# compute_boom_stack — summation, tier resolution, anti-predictive flag
# ---------------------------------------------------------------------------
def _patch_components(monkeypatch, c1=0, c2=0, c3=0, c4=0):
    monkeypatch.setattr(bs, '_component_skill_spike', lambda pid: (c1, {}))
    monkeypatch.setattr(bs, '_component_recform_hot', lambda rfg: (c2, {}))
    monkeypatch.setattr(bs, '_component_opp_soft', lambda t: (c3, {}))
    monkeypatch.setattr(bs, '_component_park_friendly', lambda pid: (c4, {}))


def test_compute_boom_stack_sums_and_tier_lookup(monkeypatch):
    _patch_components(monkeypatch, c1=1, c2=1, c3=0, c4=1)
    out = bs.compute_boom_stack(1, 5.0, 'NYY', rp3_rank=25)
    assert out['boom_stack'] == 3
    assert out['tier'] == 'sp2_sp3'
    assert out['components'] == {'skill_spike': 1, 'recform_hot': 1,
                                 'opp_soft': 0, 'park_friendly': 1}
    assert out['boom_rate_expected'] == pytest.approx(0.312)
    assert out['bust_rate_expected'] == pytest.approx(0.043)
    assert out['mean_fp_expected'] == pytest.approx(15.89)
    # sp2_sp3 + skill_spike fired + stack>=1 -> anti-predictive hint
    assert out['skill_spike_anti_predictive'] is True


def test_compute_boom_stack_tier_defaults_and_anti_pred_gating(monkeypatch):
    _patch_components(monkeypatch, c1=1, c2=0, c3=0, c4=0)
    # rank None -> legacy 'streamer' bucket; streamer is NOT anti-predictive
    out = bs.compute_boom_stack(1, None, None, rp3_rank=None)
    assert out['tier'] == 'streamer'
    assert out['skill_spike_anti_predictive'] is False
    # ace tier also not anti-predictive
    out = bs.compute_boom_stack(1, None, None, rp3_rank=5)
    assert out['tier'] == 'ace'
    assert out['skill_spike_anti_predictive'] is False
    # backend + spike -> anti-predictive
    out = bs.compute_boom_stack(1, None, None, rp3_rank=40)
    assert out['tier'] == 'backend'
    assert out['skill_spike_anti_predictive'] is True


def test_compute_boom_stack_zero_and_full(monkeypatch):
    _patch_components(monkeypatch)                       # all zero
    out = bs.compute_boom_stack(1, None, None)
    assert out['boom_stack'] == 0
    assert out['boom_rate_expected'] == pytest.approx(
        bs.BOOM_RATE_BY_TIER_STACK['streamer'][0])
    assert out['skill_spike_anti_predictive'] is False
    _patch_components(monkeypatch, c1=1, c2=1, c3=1, c4=1)  # all four
    out = bs.compute_boom_stack(1, 5.0, 'MIA', rp3_rank=60)
    assert out['boom_stack'] == 4
    assert out['boom_rate_expected'] == pytest.approx(
        bs.BOOM_RATE_BY_TIER_STACK['streamer'][4])


# ---------------------------------------------------------------------------
# compute_high_k_pitcher — z-gate against a synthetic cohort baseline
# ---------------------------------------------------------------------------
def test_compute_high_k_pitcher(monkeypatch):
    baseline = (0.22, 0.04,
                {10: {'k_pct': 0.26, 'n_starts': 8},    # z = +1.0 -> fires
                 11: {'k_pct': 0.23, 'n_starts': 8},    # z = +0.25 -> below gate
                 12: {'k_pct': 0.30, 'n_starts': 2}},   # below min starts
                '2026-07')
    monkeypatch.setattr(bs, '_load_high_k_baseline', lambda: baseline)
    out = bs.compute_high_k_pitcher(10)
    assert out['is_high_k'] is True
    assert out['z_score'] == pytest.approx(1.0)
    assert out['cohort_label'] == '2026-07'
    out = bs.compute_high_k_pitcher(11)
    assert out['is_high_k'] is False and out['reason'].startswith('z=')
    out = bs.compute_high_k_pitcher(12)
    assert out['is_high_k'] is False and out['reason'] == 'insufficient_starts'
    out = bs.compute_high_k_pitcher(999)
    assert out['reason'] == 'pitcher_below_min_starts_or_missing'


def test_compute_high_k_pitcher_degenerate_baseline(monkeypatch):
    # sd == 0 (or NaN) must refuse to z-score, not divide by zero
    monkeypatch.setattr(bs, '_load_high_k_baseline',
                        lambda: (0.22, 0.0, {10: {'k_pct': 0.5, 'n_starts': 9}}, '2026-07'))
    out = bs.compute_high_k_pitcher(10)
    assert out['is_high_k'] is False and out['reason'] == 'no_cohort_baseline'
    monkeypatch.setattr(bs, '_load_high_k_baseline',
                        lambda: (float('nan'), float('nan'), {}, ''))
    assert bs.compute_high_k_pitcher(10)['reason'] == 'no_cohort_baseline'
