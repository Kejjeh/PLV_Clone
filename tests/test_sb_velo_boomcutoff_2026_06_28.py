"""Regression locks for the 2026-06-28 session changes (gap-audit findings):
  - recalibrated boom/bust WRAPPER defaults (SP 17, H 5/0, RP 6/0) — the decision-
    changing cutoffs were previously only tested via explicit thr args, so an accidental
    revert to 20/10/2 passed CI silently.
  - the SB 2023-rule-change REGIME GUARD in hitter_sb_sprint_trend (load-bearing new logic).
  - the directional sign of velo_in_trend (last3-first3).
"""
import os
import sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
for p in (ROOT, os.path.join(ROOT, 'scripts', 'xfp')):
    if p not in sys.path:
        sys.path.insert(0, p)

C = os.path.join(ROOT, 'data', 'research', 'xfp_cache')
_MULTIYR = os.path.join(C, 'hitters_multiyr_2015_2026.csv')
_BOX = os.path.join(C, 'boxscore_hitters.parquet')
_SC26 = os.path.join(C, 'statcast_2026.parquet')


def test_boom_bust_wrapper_cutoffs_recalibrated(monkeypatch):
    """SP boom>=17 (a 17.5 counts — the Peralta fix), H boom>=5/bust<0, RP boom>=6/bust<0."""
    from lib import boom_bust
    series = [17.5, 25.0, 3.0, 4.0, 10.0, 16.0, 0.0, -2.0]
    monkeypatch.setattr(boom_bust, '_fp_series', lambda *a, **k: list(series))

    sp = boom_bust.sp_boom_bust(0)            # boom_thr=17, bust_thr=5
    assert sp['boom_pct'] == round(2 / 8 * 100)   # 17.5, 25.0 (a 17.5 counts -> would NOT under old 20)
    assert sp['bust_pct'] == round(4 / 8 * 100)   # 3,4,0,-2 < 5

    h = boom_bust.hitter_boom_bust(0)         # boom_thr=5, bust_thr=0  (was 10/2)
    assert h['boom_pct'] == round(4 / 8 * 100)    # 17.5,25,10,16 >= 5
    assert h['bust_pct'] == round(1 / 8 * 100)    # only -2 < 0 (the old <2 would tag 0.0,3,4 too)

    rp = boom_bust.rp_boom_bust(0)            # boom_thr=6, bust_thr=0
    assert rp['boom_pct'] == round(4 / 8 * 100)   # 17.5,25,10,16 >= 6
    assert rp['bust_pct'] == round(1 / 8 * 100)


@pytest.mark.skipif(not (os.path.exists(_MULTIYR) and os.path.exists(_BOX)),
                    reason="multiyr / boxscore cache not present")
def test_sb_regime_guard():
    """z_sb suppressed when cur/base straddle the 2023 rule change; in-season sb_recent stays valid."""
    from lib.trend_signal import hitter_sb_sprint_trend, SB_RULE_YEAR
    assert SB_RULE_YEAR == 2023
    same = hitter_sb_sprint_trend(2026, 2025)     # both post-2023
    cross = hitter_sb_sprint_trend(2026, 2022)     # straddles 2023
    assert same['z_sb'].notna().any(), "same-regime YoY SB delta should compute"
    assert cross['z_sb'].notna().sum() == 0, "cross-regime z_sb must be suppressed (rule-change artifact)"
    assert cross['sb_recent'].notna().any(), "in-season L30d read is regime-internal -> always valid"


@pytest.mark.skipif(not os.path.exists(_SC26), reason="statcast_2026 not present")
def test_velo_in_trend_is_two_sided():
    """velo_in_trend = last3 - first3 starts: rising arms +, falling arms - (direction lock)."""
    from sp_decline_model import _inseason_velo_trend
    t = _inseason_velo_trend()
    assert 'velo_in_trend' in t.columns
    assert len(t) > 50
    assert (t['velo_in_trend'] > 0).any() and (t['velo_in_trend'] < 0).any(), \
        "trend must be two-sided (some arms rising, some falling) — not a one-sided peak-drop"
