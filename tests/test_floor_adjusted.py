"""Tests for the floor-adjusted (risk-aware) decision score.

Rule 13: floor_adj is DECISION-LAYER context — it docks/credits the displayed mean for
H2H risk but NEVER becomes a projection-model feature or moves the rp3/blended headline.
Validated 2026-06-24 (floor_adjusted_ranking_2026-06-24.md): trajectory features add ~0
OOS to mean AND bust prediction, so the fix is to SURFACE the floor model's risk, not to
add features.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

import pytest
from lib.extra_lenses import (
    floor_adjusted_xfp, floor_flag, classify_stuff_command, park_env, opp_env,
    FLOOR_BUST_BASE, FLOOR_BUST_FP_COST, FLOOR_RISK_LAMBDA,
)
from lib.triangulate_core import flatten_extra
from lib.lens_registry import is_context_only_column


def test_above_base_bust_is_docked():
    adj, pen = floor_adjusted_xfp(12.0, 45)            # 45% > 27% base
    assert pen > 0 and adj < 12.0
    expect = FLOOR_RISK_LAMBDA * (0.45 - FLOOR_BUST_BASE) * FLOOR_BUST_FP_COST
    assert pen == pytest.approx(expect, abs=1e-2)
    assert adj == pytest.approx(12.0 - expect, abs=1e-2)


def test_below_base_bust_is_credited():
    adj, pen = floor_adjusted_xfp(10.0, 12)            # SAFE-floor arm
    assert pen < 0 and adj > 10.0


def test_base_rate_is_neutral():
    adj, pen = floor_adjusted_xfp(11.0, 27)
    assert pen == pytest.approx(0.0, abs=1e-9)
    assert adj == pytest.approx(11.0, abs=1e-9)


def test_missing_inputs_return_mean_no_penalty():
    assert floor_adjusted_xfp(None, 30) == (None, 0.0)
    assert floor_adjusted_xfp(11.0, None) == (11.0, 0.0)


def test_floor_flag_is_tier_aligned():
    assert floor_flag(0.4, 'RISKY') == 'FLOOR-RISK'     # RISKY tier + docked
    assert floor_flag(-0.4, 'SAFE') == 'SAFE-FLOOR'     # SAFE tier + credited
    assert floor_flag(0.2, 'MODERATE') is None          # MODERATE never flags
    assert floor_flag(0.4, 'SAFE') is None              # wrong sign for SAFE tier
    assert floor_flag(-0.4, 'RISKY') is None            # wrong sign for RISKY tier
    assert floor_flag(None, 'RISKY') is None
    assert floor_flag(0.4, None) is None


def test_flatten_extra_sp_emits_floor_adj_and_flags_risky():
    model = {'proj': 12.0, 'floor': {'bust_prob': 48, 'tier': 'RISKY'}}
    out = flatten_extra(model, 'SP')
    assert out['floor_adj_xfp'] is not None
    assert out['floor_adj_penalty'] > 0
    assert out['floor_flag'] == 'FLOOR-RISK'


def test_flatten_extra_sp_safe_floor_credits():
    model = {'proj': 10.0, 'floor': {'bust_prob': 10, 'tier': 'SAFE'}}
    out = flatten_extra(model, 'SP')
    assert out['floor_adj_xfp'] > 10.0
    assert out['floor_flag'] == 'SAFE-FLOOR'


def test_flatten_extra_nonsp_floor_adj_none():
    out = flatten_extra({'proj': 3.0, 'floor': {}}, 'H')
    assert out['floor_adj_xfp'] is None
    assert out['floor_adj_penalty'] is None
    assert out['floor_flag'] is None


def test_flatten_extra_sp_no_floor_data_none():
    # SP with a mean but no floor lens (e.g. unranked) -> no floor_adj invented
    out = flatten_extra({'proj': 9.0, 'floor': {}}, 'SP')
    assert out['floor_adj_xfp'] is None


def test_floor_adj_columns_registered_context_only():
    for c in ('floor_adj_xfp', 'floor_adj_penalty', 'floor_flag'):
        assert is_context_only_column(c), f"{c} must be registered context-only (Rule 13)"


def test_floor_adj_never_a_projection_feature():
    from plv_clone.models.xfp.rp3 import RP3_FEATS
    for c in ('floor_adj_xfp', 'floor_adj_penalty', 'floor_flag'):
        assert c not in RP3_FEATS


# ---- stuff-vs-command divergence classifier ----

def test_classify_stuff_decline_on_swstr_collapse():
    assert classify_stuff_command(-4.0, 0.0, 1.0, 0.0) == 'STUFF-DECLINE'   # Framber pattern


def test_classify_stuff_decline_on_velo_cliff():
    assert classify_stuff_command(0.0, -1.6, 0.0, 0.0) == 'STUFF-DECLINE'


def test_classify_command_watch_soriano_pattern():
    # stuff intact (SwStr up, velo barely down), walks up sharply -> reversible
    assert classify_stuff_command(0.5, -0.7, 7.0, -2.0) == 'COMMAND-WATCH'


def test_classify_command_watch_on_zone_collapse():
    assert classify_stuff_command(0.0, 0.0, 0.0, -3.0) == 'COMMAND-WATCH'


def test_classify_none_when_stable():
    assert classify_stuff_command(0.0, 0.0, 0.0, 0.0) is None


def test_classify_none_when_stuff_ambiguous():
    # SwStr -1.6 is neither intact (>=-1.5) nor eroding (<=-2.0) -> no call
    assert classify_stuff_command(-1.6, 0.0, 5.0, 0.0) is None


def test_stuff_decline_takes_precedence_over_command():
    assert classify_stuff_command(-3.0, 0.0, 5.0, -3.0) == 'STUFF-DECLINE'


def test_classify_stuff_decline_on_yoy_swstr_drop():
    # Framber: flat within-season but SwStr fell YoY (12.4->10.1) -> STUFF-DECLINE
    assert classify_stuff_command(-0.3, 0.3, 2.0, 0.0, yoy_swstr_d=-2.3) == 'STUFF-DECLINE'


def test_yoy_stuff_gates_command_watch():
    # in-season intact + command up, but YoY stuff DOWN -> STUFF-DECLINE (not a command wobble)
    assert classify_stuff_command(0.5, -0.7, 7.0, -2.0, yoy_swstr_d=-2.5) == 'STUFF-DECLINE'
    # YoY stuff UP (Soriano: 12.2->15.4) -> COMMAND-WATCH
    assert classify_stuff_command(0.5, -0.7, 7.0, -2.0, yoy_swstr_d=3.2) == 'COMMAND-WATCH'


def test_flatten_extra_emits_stuff_cmd():
    model = {'proj': 11.0, 'floor': {},
             'stuff_cmd': {'tag': 'COMMAND-WATCH', 'swstr_d': 0.5, 'velo_d': -0.7,
                           'bb_d': 7.0, 'zone_d': -2.0, 'yoy_swstr_d': 3.2}}
    out = flatten_extra(model, 'SP')
    assert out['stuff_cmd_tag'] == 'COMMAND-WATCH'
    assert out['stuff_cmd_bb_d'] == 7.0
    assert out['stuff_cmd_yoy_swstr_d'] == 3.2


def test_stuff_cmd_columns_registered_context_only():
    for c in ('stuff_cmd_tag', 'stuff_cmd_swstr_d', 'stuff_cmd_velo_d',
              'stuff_cmd_bb_d', 'stuff_cmd_yoy_swstr_d'):
        assert is_context_only_column(c)


# ---- next-start matchup context (park/opp environment) ----

def test_park_env_tiers():
    assert park_env(1.20) == 'EXTREME-HITTER'   # Coors-class
    assert park_env(1.10) == 'EXTREME-HITTER'
    assert park_env(1.05) == 'HITTER'
    assert park_env(1.00) == 'NEUTRAL'
    assert park_env(0.93) == 'PITCHER'
    assert park_env(None) is None


def test_opp_env_tiers():
    assert opp_env(1.10) == 'tough'
    assert opp_env(1.00) == 'avg'
    assert opp_env(0.90) == 'soft'
    assert opp_env(None) is None


def test_flatten_extra_emits_next_start():
    model = {'proj': 11.0, 'floor': {},
             'next_start': {'date': '2026-06-29', 'opp': 'COL', 'venue': 'COL',
                            'is_home': False, 'park_env': 'EXTREME-HITTER', 'opp_env': 'avg'}}
    out = flatten_extra(model, 'SP')
    assert out['next_venue'] == 'COL'
    assert out['next_park_env'] == 'EXTREME-HITTER'
    assert out['next_opp_env'] == 'avg'
    assert out['next_opp'] == 'COL'


def test_next_start_columns_registered_context_only():
    for c in ('next_start_date', 'next_opp', 'next_venue', 'next_park_env', 'next_opp_env'):
        assert is_context_only_column(c)
