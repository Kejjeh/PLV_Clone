"""Pins for the triangulate verdict guardrails (W2, 2026-07-11).

apply_overrides carries the two SP decline vetoes that protect against the
Framber trap (CLAUDE.md gotcha #14): a naive BUY standing on a fading arm.
These are pure dict-in/dict-out functions (verified: no module-level data
loads in the import chain), so the guardrails are pinned with synthetic
inputs — a refactor that silently disables a veto now fails a test instead
of a future roster decision.

Also pins the build_watch_list bucket gating (the "SP xwOBACON token" ghost:
hitter-phrased watch strings used to render on SP CAUTION cards).
"""
from __future__ import annotations

import pytest

from scripts.xfp.lib.triangulate_core import apply_overrides, build_watch_list


SP_PLAYER = {'bucket': 'SP'}
H_PLAYER = {'bucket': 'H'}
NO_ARCHE = {'have': False}


def _model(**kw):
    """Minimal SP model dict: healthy unless overridden."""
    base = {
        'velo_severity': None,
        'decline_tier': 'STABLE',
        'decline_gap': None,
        'data_quality_tag': 'data_driven_full',
        'sustainability': {'process_verdict': 'STABLE', 'process_detail': ''},
        'rank': 40,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# PROCESS_DECLINE_VETO
# ---------------------------------------------------------------------------

def test_process_decline_veto_fires_on_structural_decline():
    """BUY + quiet velo lens + STRUCTURAL_DECLINE process verdict → downgraded."""
    model = _model(sustainability={'process_verdict': 'STRUCTURAL_DECLINE',
                                   'process_detail': 'K% -4.7pp, SwStr -2.4pp YoY'})
    verdict, rationale, tag = apply_overrides(
        'BUY — archetype breakout', 'orig rationale', SP_PLAYER, NO_ARCHE, model)
    assert tag == 'PROCESS_DECLINE_VETO'
    assert verdict == 'CAUTION — process decline veto'
    assert 'K% -4.7pp' in rationale
    # Rule 13: the veto changes the LABEL only, never the point estimate
    assert 'point estimate unchanged' in rationale


def test_process_decline_veto_fires_on_strong_hold_buy():
    model = _model(sustainability={'process_verdict': 'STRUCTURAL_DECLINE',
                                   'process_detail': 'x'})
    _, _, tag = apply_overrides(
        'STRONG HOLD/BUY', 'r', SP_PLAYER, NO_ARCHE, model)
    assert tag == 'PROCESS_DECLINE_VETO'


def test_velo_veto_takes_precedence_over_process():
    """SEVERE velo fires the sibling DECLINE_VETO first — no double-downgrade."""
    model = _model(velo_severity='SEVERE',
                   sustainability={'process_verdict': 'STRUCTURAL_DECLINE',
                                   'process_detail': 'x'})
    verdict, _, tag = apply_overrides(
        'BUY — model anchored', 'r', SP_PLAYER, NO_ARCHE, model)
    assert tag == 'DECLINE_VETO'
    assert verdict == 'CAUTION — decline veto'


# ---------------------------------------------------------------------------
# DECLINE_VETO (velo / sp-decline tier)
# ---------------------------------------------------------------------------

def test_decline_veto_fires_on_severe_velo():
    verdict, rationale, tag = apply_overrides(
        'BUY — archetype breakout', 'r', SP_PLAYER, NO_ARCHE,
        _model(velo_severity='SEVERE'))
    assert tag == 'DECLINE_VETO'
    assert 'SEVERE velo fade' in rationale


def test_decline_veto_fires_on_decline_risk_tier():
    _, rationale, tag = apply_overrides(
        'BUY — archetype breakout', 'r', SP_PLAYER, NO_ARCHE,
        _model(decline_tier='DECLINE-RISK', decline_gap=-12.0))
    assert tag == 'DECLINE_VETO'
    assert 'DECLINE-RISK' in rationale


def test_decline_veto_flags_marcel_suppressed_rank_gap():
    _, rationale, tag = apply_overrides(
        'BUY — model anchored', 'r', SP_PLAYER, NO_ARCHE,
        _model(velo_severity='SEVERE', data_quality_tag='marcel_il'))
    assert tag == 'DECLINE_VETO'
    assert 'marcel_il' in rationale


# ---------------------------------------------------------------------------
# no-fire paths
# ---------------------------------------------------------------------------

def test_healthy_buy_passes_through_unchanged():
    verdict, rationale, tag = apply_overrides(
        'BUY — archetype breakout', 'orig', SP_PLAYER, NO_ARCHE, _model())
    assert (verdict, rationale, tag) == ('BUY — archetype breakout', 'orig', None)


def test_vetoes_are_sp_only():
    """The decline vetoes are SP-gated: a hitter with the same model dict
    passes through untouched."""
    model = _model(velo_severity='SEVERE',
                   sustainability={'process_verdict': 'STRUCTURAL_DECLINE',
                                   'process_detail': 'x'})
    verdict, _, tag = apply_overrides('BUY — hot bat', 'r', H_PLAYER, NO_ARCHE, model)
    assert tag is None
    assert verdict == 'BUY — hot bat'


def test_vetoes_require_bullish_verdict():
    model = _model(sustainability={'process_verdict': 'STRUCTURAL_DECLINE',
                                   'process_detail': 'x'})
    verdict, _, tag = apply_overrides('HOLD', 'r', SP_PLAYER, NO_ARCHE, model)
    assert tag is None
    assert verdict == 'HOLD'


# ---------------------------------------------------------------------------
# build_watch_list bucket gating
# ---------------------------------------------------------------------------

HITTER_ONLY_ITEMS = ('career_pct drops below current floor',
                     'L21d xwOBACON drops more than 0.020 from season')


@pytest.mark.parametrize('bucket', ['SP', 'RP'])
def test_caution_watch_list_has_no_hitter_items_for_pitchers(bucket):
    items = build_watch_list('CAUTION', 'generic', _model(), NO_ARCHE, 55,
                             bucket=bucket)
    for hitter_item in HITTER_ONLY_ITEMS:
        assert hitter_item not in items
    assert items, 'pitcher CAUTION card must still have neutral triggers'


def test_caution_watch_list_keeps_hitter_items_for_hitters():
    items = build_watch_list('CAUTION', 'generic', _model(), NO_ARCHE, 55,
                             bucket='H')
    for hitter_item in HITTER_ONLY_ITEMS:
        assert hitter_item in items


def test_unknown_bucket_emits_only_neutral_items():
    items = build_watch_list('CAUTION', 'generic', _model(), NO_ARCHE, 55)
    for hitter_item in HITTER_ONLY_ITEMS:
        assert hitter_item not in items
    assert not any('SwStr%' in i for i in items)


def test_hold_pitcher_reason_tags_gated_from_hitters():
    """process_intact / post_tj_ramp items are pitcher-phrased; a hitter with
    those reason tags gets the generic HOLD triggers instead."""
    items = build_watch_list('HOLD', 'process_intact', _model(), NO_ARCHE, 55,
                             bucket='H')
    assert not any('SwingMiss' in i or 'velo_tier' in i for i in items)
    assert any('model rank moves outside top-50' in i for i in items)


def test_watch_list_capped_at_five_all_buckets():
    for bucket in ('H', 'SP', 'RP', None):
        for verdict in ('HOLD', 'CAUTION', 'MIXED', 'BUY', 'FADE'):
            items = build_watch_list(verdict, 'generic', _model(), NO_ARCHE,
                                     55, bucket=bucket)
            assert len(items) <= 5
