"""Characterization tests for scripts/xfp/lib/hitter_boom_stack.py.

Locks current behavior of the pure component thresholds, the 0-4 stack
summation (incl. lineup_amp and its recursion guard), the per-stack rate
tables, and opp-SP team-abbrev normalization. All data loaders / API
fetchers are monkeypatched with synthetic frames — no parquet/CSV/network.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

import pandas as pd
import pytest

import lib.hitter_boom_stack as hbs

TODAY = date(2026, 7, 1)


# ---------------------------------------------------------------------------
# Rate tables
# ---------------------------------------------------------------------------
def test_rate_tables_cover_stack_0_to_4_and_are_monotonic():
    for table in (hbs.BOOM_RATE_BY_STACK, hbs.BUST_RATE_BY_STACK,
                  hbs.MEAN_FP_PROXY_BY_STACK):
        assert set(table) == {0, 1, 2, 3, 4}
    booms = [hbs.BOOM_RATE_BY_STACK[s] for s in range(5)]
    busts = [hbs.BUST_RATE_BY_STACK[s] for s in range(5)]
    assert booms == sorted(booms)                  # boom rises with stack
    assert busts == sorted(busts, reverse=True)    # bust falls with stack
    assert hbs.BOOM_RATE_BY_STACK[0] == pytest.approx(0.239)
    assert hbs.BOOM_RATE_BY_STACK[4] == pytest.approx(0.340)


# ---------------------------------------------------------------------------
# Component 3 — opp_soft_hitter (weak opposing SP)
# ---------------------------------------------------------------------------
def test_component_opp_soft_hitter(monkeypatch):
    monkeypatch.setattr(hbs, '_load_soft_sp_tertile',
                        lambda: (10.0, {50: 8.0, 51: 12.0, 52: 10.0}))
    fired, d = hbs._component_opp_soft_hitter(None)
    assert fired == 0 and d['reason'] == 'no_opp_sp'
    fired, d = hbs._component_opp_soft_hitter('abc')
    assert fired == 0 and d['reason'] == 'opp_sp_id_not_int'
    fired, d = hbs._component_opp_soft_hitter(999)
    assert fired == 0 and d['reason'] == 'opp_sp_not_in_rp3'
    assert hbs._component_opp_soft_hitter(50)[0] == 1   # below p33 -> soft
    assert hbs._component_opp_soft_hitter(52)[0] == 1   # exactly p33 fires (<=)
    fired, d = hbs._component_opp_soft_hitter(51)       # strong SP
    assert fired == 0 and d['opp_sp_rp3_per_start'] == 12.0


# ---------------------------------------------------------------------------
# Components 1 + 2 — synthetic per-(batter, game) panel
# ---------------------------------------------------------------------------
def _games_panel():
    rows = []
    # batter 7: 25 games in June, PA=4 each.
    #   first 15: K=2, xwoba 0.300, fp_proxy 1.0
    #   last 10:  K=1, xwoba 0.400, fp_proxy 4.0
    # -> dK = 25% - 40% = -15pp (<= -3) and dxw = .400-.340 = +.060 (>= .040)
    # -> recform delta = 4.0 - 2.2 = +1.8 (>= 1.5)
    for i in range(25):
        hot = i >= 15
        rows.append({'batter': 7, 'game_pk': 1000 + i,
                     'game_date': pd.Timestamp(2026, 6, i + 1),
                     'PA': 4, 'K': 1 if hot else 2, 'BB': 0, 'HBP': 0,
                     'TB': 4 if hot else 2, 'SB': 0,
                     'fp_proxy': 4.0 if hot else 1.0,
                     'xwoba_pg': 0.400 if hot else 0.300})
    # batter 9: 25 flat games -> neither component fires.
    for i in range(25):
        rows.append({'batter': 9, 'game_pk': 2000 + i,
                     'game_date': pd.Timestamp(2026, 6, i + 1),
                     'PA': 4, 'K': 1, 'BB': 0, 'HBP': 0, 'TB': 1, 'SB': 0,
                     'fp_proxy': 1.0, 'xwoba_pg': 0.300})
    # batter 8: only 10 games -> insufficient season comparator.
    for i in range(10):
        rows.append({'batter': 8, 'game_pk': 3000 + i,
                     'game_date': pd.Timestamp(2026, 6, i + 1),
                     'PA': 4, 'K': 1, 'BB': 0, 'HBP': 0, 'TB': 1, 'SB': 0,
                     'fp_proxy': 1.0, 'xwoba_pg': 0.300})
    return (pd.DataFrame(rows)
            .sort_values(['batter', 'game_date']).reset_index(drop=True))


def test_component_skill_spike_hitter(monkeypatch):
    monkeypatch.setattr(hbs, '_load_batter_games_2026', _games_panel)
    fired, d = hbs._component_skill_spike_hitter(7, TODAY)
    assert fired == 1
    assert d['delta_xwoba'] == pytest.approx(0.060, abs=1e-9)
    assert d['delta_k_pp'] == pytest.approx(-15.0)
    assert hbs._component_skill_spike_hitter(9, TODAY)[0] == 0
    fired, d = hbs._component_skill_spike_hitter(8, TODAY)
    assert fired == 0 and d['reason'] == 'insufficient_games'


def test_component_recform_hot_hitter(monkeypatch):
    monkeypatch.setattr(hbs, '_load_batter_games_2026', _games_panel)
    fired, d = hbs._component_recform_hot_hitter(7, TODAY)
    assert fired == 1
    assert d['season_fp_proxy_per_g'] == pytest.approx(2.2)
    assert d['last10_fp_proxy_per_g'] == pytest.approx(4.0)
    fired, d = hbs._component_recform_hot_hitter(9, TODAY)
    assert fired == 0 and d['delta'] == pytest.approx(0.0)
    fired, d = hbs._component_recform_hot_hitter(8, TODAY)
    assert fired == 0 and d['reason'] == 'insufficient_games'


def test_components_only_use_games_before_today(monkeypatch):
    # With today set BEFORE the panel's games, everything is filtered out
    # (leakage-safe construction) -> insufficient_games.
    monkeypatch.setattr(hbs, '_load_batter_games_2026', _games_panel)
    fired, d = hbs._component_skill_spike_hitter(7, date(2026, 5, 1))
    assert fired == 0 and d['reason'] == 'insufficient_games'


# ---------------------------------------------------------------------------
# compute_hitter_boom_stack — summation + recursion-guard path
# ---------------------------------------------------------------------------
def _patch_components(monkeypatch, c1=0, c2=0, c3=0):
    monkeypatch.setattr(hbs, '_component_skill_spike_hitter', lambda b, t: (c1, {}))
    monkeypatch.setattr(hbs, '_component_recform_hot_hitter', lambda b, t: (c2, {}))
    monkeypatch.setattr(hbs, '_component_opp_soft_hitter', lambda o: (c3, {}))


def test_compute_skip_lineup_amp_path(monkeypatch):
    _patch_components(monkeypatch, c1=1, c2=1, c3=1)
    out = hbs.compute_hitter_boom_stack(1, None, today=TODAY, skip_lineup_amp=True)
    assert out['boom_stack'] == 3
    assert out['components']['lineup_amp_hitter'] == 0
    assert out['detail']['lineup_amp_hitter'] == {'reason': 'skipped_for_recursion_guard'}
    assert out['boom_rate_expected'] == pytest.approx(0.306)
    assert out['bust_rate_expected'] == pytest.approx(0.375)


def test_compute_full_path_with_lineup_amp(monkeypatch):
    _patch_components(monkeypatch, c1=1, c2=1, c3=1)
    monkeypatch.setattr(hbs, '_component_lineup_amp_hitter',
                        lambda **kw: (1, {'n_teammates_lit': 3}))
    out = hbs.compute_hitter_boom_stack(1, 50, today=TODAY, team='NYY')
    assert out['boom_stack'] == 4
    assert out['components']['lineup_amp_hitter'] == 1
    assert out['boom_rate_expected'] == pytest.approx(0.340)
    assert out['mean_fp_proxy_expected'] == pytest.approx(1.73)


def test_compute_all_cold(monkeypatch):
    _patch_components(monkeypatch)
    monkeypatch.setattr(hbs, '_component_lineup_amp_hitter',
                        lambda **kw: (0, {'reason': 'own_stack_lt_1'}))
    out = hbs.compute_hitter_boom_stack(1, None, today=TODAY, team='NYY')
    assert out['boom_stack'] == 0
    assert out['boom_rate_expected'] == pytest.approx(0.239)


# ---------------------------------------------------------------------------
# Component 4 — lineup_amp gates
# ---------------------------------------------------------------------------
def test_lineup_amp_requires_own_stack(monkeypatch):
    fired, d = hbs._component_lineup_amp_hitter(
        batter_id=1, own_components_total=0, team='NYY', today=TODAY)
    assert fired == 0 and d['reason'] == 'own_stack_lt_1'


def test_lineup_amp_no_lineup(monkeypatch):
    monkeypatch.setattr(hbs, '_resolve_team_expected_lineup', lambda team, today: [])
    fired, d = hbs._component_lineup_amp_hitter(
        batter_id=1, own_components_total=2, team='NYY', today=TODAY)
    assert fired == 0 and d['reason'] == 'no_lineup_or_team'


def test_lineup_amp_counts_other_teammates(monkeypatch):
    monkeypatch.setattr(hbs, '_resolve_team_expected_lineup',
                        lambda team, today: [101, 102, 103])
    monkeypatch.setattr(hbs, 'resolve_opp_sp_id_for_today', lambda team, today: None)
    monkeypatch.setattr(hbs, 'compute_hitter_boom_stack',
                        lambda **kw: {'boom_stack': 1})
    # batter 101 is IN the lineup -> excluded from his own teammate count
    fired, d = hbs._component_lineup_amp_hitter(
        batter_id=101, own_components_total=1, team='NYY', today=TODAY)
    assert fired == 1
    assert d['teammates_checked'] == 2 and d['n_teammates_lit'] == 2
    # cold teammates -> no amp
    monkeypatch.setattr(hbs, 'compute_hitter_boom_stack',
                        lambda **kw: {'boom_stack': 0})
    fired, d = hbs._component_lineup_amp_hitter(
        batter_id=101, own_components_total=1, team='NYY', today=TODAY)
    assert fired == 0 and d['n_teammates_lit'] == 0


# ---------------------------------------------------------------------------
# resolve_opp_sp_id_for_today — team-abbrev normalization
# ---------------------------------------------------------------------------
def test_resolve_opp_sp_normalization(monkeypatch):
    monkeypatch.setattr(hbs, '_todays_team_to_opp_sp',
                        lambda iso: {'ATH': 660271, 'NYY': 543037})
    assert hbs.resolve_opp_sp_id_for_today('OAK', TODAY) == 660271   # OAK -> ATH
    assert hbs.resolve_opp_sp_id_for_today('nyy', TODAY) == 543037   # case-folded
    assert hbs.resolve_opp_sp_id_for_today('ZZZ', TODAY) is None
    assert hbs.resolve_opp_sp_id_for_today(None, TODAY) is None
    assert hbs.resolve_opp_sp_id_for_today(123, TODAY) is None       # non-str
    # 2026 audit fix: ATH maps to itself (StatsAPI uses ATH post-move)
    assert hbs._TEAM_ABBR_MAP['ATH'] == 'ATH'
    assert hbs._TEAM_ABBR_MAP['OAK'] == 'ATH'


# ---------------------------------------------------------------------------
# Characterization: misplaced lru_cache decorator (suspected latent bug)
# ---------------------------------------------------------------------------
def test_lru_cache_decorates_games_loader_not_today_et():
    """Fixed 2026-07-19: a stray blank line had bound @lru_cache(maxsize=1)
    to `_today_et` instead of `_load_batter_games_2026` — freezing "today"
    for process lifetime while the statcast panel re-read on EVERY component
    call (brutal in the lineup_amp teammate loop). The cache now sits on the
    loader; `_today_et` is live. This test locks the CORRECTED placement."""
    assert hasattr(hbs._load_batter_games_2026, 'cache_clear')
    assert not hasattr(hbs._today_et, 'cache_clear')
