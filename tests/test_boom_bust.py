"""TDD for lib/boom_bust — realized boom/bust actuals lens.

The variance side the model lenses can't show: realized BrownU FP per game/start
over the last N, with boom%/bust%/std/trend. Pure core is boom_bust_summary;
the per-player loaders hit the live MLB gameLog (cached) and are smoke-tested.
Context-only (CLAUDE.md #13).
"""
import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib import boom_bust
from lib.boom_bust import (
    boom_bust_summary, _series_from_box, _fp_series,
    _ip_to_float, _sp_fp, _rp_fp,
)


def test_summary_counts_and_rates():
    # SP thresholds: boom >=20, bust <5
    s = boom_bust_summary([22, 1, 30, 8, -2, 28, 5, 18], boom_thr=20, bust_thr=5)
    assert s["n"] == 8
    assert s["boom_pct"] == round(3 / 8 * 100)      # 22,30,28
    assert s["bust_pct"] == round(2 / 8 * 100)      # 1,-2 (5 is NOT <5)
    assert s["max"] == 30 and s["min"] == -2
    assert s["mean"] == round(sum([22, 1, 30, 8, -2, 28, 5, 18]) / 8, 1)


def test_summary_trend_l3_vs_full():
    s = boom_bust_summary([0, 0, 0, 0, 30, 30, 30], boom_thr=20, bust_thr=5)
    assert s["l3_mean"] == 30 and s["trend"] == "UP"     # last 3 hot


def test_summary_empty_and_short_safe():
    assert boom_bust_summary([], boom_thr=20, bust_thr=5) is None
    s = boom_bust_summary([10.0], boom_thr=20, bust_thr=5)
    assert s["n"] == 1 and s["std"] == 0.0


# --- Tier 1: materialized boxscore fast path ---

def _pitcher_box():
    """Two pitchers: a starter (gs=1) and a reliever (gs=0), out of date order."""
    return pd.DataFrame([
        # starter 100 — two starts (out of order) + one relief cameo (must be dropped for SP)
        {"mlbam_id": 100, "game_pk": 2, "game_date": "2026-04-10", "gs": 1,
         "ip": 6.0, "so": 8, "h_allowed": 4, "er": 1, "bb_allowed": 1, "hbp_allowed": 0, "sv": 0, "hld": 0},
        {"mlbam_id": 100, "game_pk": 1, "game_date": "2026-04-04", "gs": 1,
         "ip": 5.0, "so": 5, "h_allowed": 6, "er": 3, "bb_allowed": 2, "hbp_allowed": 0, "sv": 0, "hld": 0},
        {"mlbam_id": 100, "game_pk": 3, "game_date": "2026-04-20", "gs": 0,
         "ip": 1.0, "so": 2, "h_allowed": 0, "er": 0, "bb_allowed": 0, "hbp_allowed": 0, "sv": 0, "hld": 1},
        # reliever 200 — one save appearance
        {"mlbam_id": 200, "game_pk": 5, "game_date": "2026-04-11", "gs": 0,
         "ip": 1.0, "so": 2, "h_allowed": 0, "er": 0, "bb_allowed": 0, "hbp_allowed": 0, "sv": 1, "hld": 0},
    ])


def test_series_from_box_sp_filters_starts_and_orders():
    s = _series_from_box(_pitcher_box(), 100, "SP")
    # chronological: game_pk 1 (4-04) then 2 (4-10); relief cameo (gs=0) excluded
    # 4-04: 5 + 5*3.3 - 6 - 2*3 - 2 - 0 = 5+16.5-6-6-2 = 7.5
    # 4-10: 8 + 6*3.3 - 4 - 2*1 - 1 - 0 = 8+19.8-4-2-1 = 20.8
    assert s == pytest.approx([7.5, 20.8])


def test_series_from_box_rp_uses_relief_and_sv_hld():
    # reliever 200: 2 + 1*3.3 - 0 - 0 - 0 - 0 + 5*1 = 10.3
    assert _series_from_box(_pitcher_box(), 200, "RP") == pytest.approx([10.3])
    # starter 100 viewed as RP -> only the gs=0 cameo: 2 + 1*3.3 + 2*1(hld) = 7.3
    assert _series_from_box(_pitcher_box(), 100, "RP") == pytest.approx([7.3])


def test_series_from_box_hitter_all_games_ordered():
    h = pd.DataFrame([
        {"mlbam_id": 9, "game_pk": 2, "game_date": "2026-05-02",
         "r": 1, "tb": 4, "rbi": 2, "bb": 1, "hbp": 0, "sb": 1, "k": 1},
        {"mlbam_id": 9, "game_pk": 1, "game_date": "2026-05-01",
         "r": 0, "tb": 0, "rbi": 0, "bb": 0, "hbp": 0, "sb": 0, "k": 3},
    ])
    # 5-01: 0+0+0+0+0+0-3 = -3 ; 5-02: 1+4+2+1+0+1-1 = 8
    assert _series_from_box(h, 9, "H") == pytest.approx([-3.0, 8.0])


def test_series_from_box_absent_and_empty_are_none():
    assert _series_from_box(_pitcher_box(), 999, "SP") is None     # player absent
    assert _series_from_box(None, 100, "SP") is None               # store missing
    assert _series_from_box(pd.DataFrame(), 100, "SP") is None     # empty store


def test_fp_series_prefers_box_then_falls_back_to_live(monkeypatch):
    calls = {"live": 0}

    def fake_live(mlbam, bucket, season=2026):
        calls["live"] += 1
        return [1.0, 2.0]

    monkeypatch.setattr(boom_bust, "_live_series", fake_live)
    monkeypatch.setattr(boom_bust, "_load_box", lambda kind: _pitcher_box())
    # 100 is in the box -> live NOT called
    assert _fp_series(100, "SP") == pytest.approx([7.5, 20.8])
    assert calls["live"] == 0
    # 999 absent from box -> live fallback
    assert _fp_series(999, "SP") == [1.0, 2.0]
    assert calls["live"] == 1


def test_fp_series_cross_year_always_live(monkeypatch):
    monkeypatch.setattr(boom_bust, "_live_series", lambda m, b, season=2026: [float(season)])
    monkeypatch.setattr(boom_bust, "_load_box", lambda kind: _pitcher_box())
    # season != 2026 must skip the (current-season-only) box and use live
    assert _fp_series(100, "SP", season=2025) == [2025.0]


# --- live fallback correctness (regression: IP 'outs' notation + 0-IP blowups) ---

def test_ip_to_float_outs_notation():
    # '.1' = 1/3 inning, '.2' = 2/3 — NOT decimal 0.1/0.2
    assert _ip_to_float("5.0") == 5.0
    assert _ip_to_float("5.1") == pytest.approx(5 + 1 / 3)
    assert _ip_to_float("5.2") == pytest.approx(5 + 2 / 3)
    assert _ip_to_float("5") == 5.0


def test_sp_fp_uses_outs_notation_not_decimal():
    # 6.2 IP = 6⅔; naive float('6.2')*3.3 would undercount by ~1.5 FP
    s = {"gamesStarted": 1, "inningsPitched": "6.2", "strikeOuts": 6,
         "hits": 4, "earnedRuns": 1, "baseOnBalls": 1, "hitBatsmen": 0}
    # 6 + 6.667*3.3 - 4 - 2 - 1 = 21.0
    assert _sp_fp(s) == pytest.approx(6 + (6 + 2 / 3) * 3.3 - 4 - 2 - 1)
    assert _sp_fp(s) == pytest.approx(21.0, abs=0.01)


def test_rp_fp_scores_zero_out_blowup():
    # 0-out relief disaster (3 H, 4 ER) is a real -12 FP game, not a no-op
    s = {"gamesStarted": 0, "gamesPitched": 1, "inningsPitched": "0.0",
         "strikeOuts": 0, "hits": 3, "earnedRuns": 4, "baseOnBalls": 1,
         "hitBatsmen": 0, "saves": 0, "holds": 0}
    assert _rp_fp(s) == pytest.approx(-12.0)


# ── Rate precision (2026-08-07) ──────────────────────────────────────────────
# A bare percentage reads as far more certain than a handful of games can
# support. On 2026-08-07 an 8% bust rate was quoted as "the lowest on the
# slate" and used to pick a streamer — it was ONE bust in twelve starts,
# CI [1%, 35%], overlapping the alternative's [9%, 40%] almost entirely.

def test_rates_ship_with_denominator_and_interval():
    from lib.boom_bust import boom_bust_summary
    # 1 bust in 12 -> the Drohan shape.
    vals = [12.0] * 11 + [-4.5]
    s = boom_bust_summary(vals, boom_thr=17, bust_thr=5)
    assert s["n"] == 12
    assert s["bust_n"] == 1
    assert s["bust_pct"] == 8
    lo, hi = s["bust_ci"]
    assert lo < 8 < hi, "the point estimate must sit inside its own interval"
    assert hi > 25, f"a 1-in-12 rate cannot be precise; got upper bound {hi}"


def test_wilson_ci_stays_inside_zero_to_one_hundred():
    """Normal-approximation intervals go negative near p=0 and imply a
    precision that does not exist; Wilson does not."""
    from lib.boom_bust import wilson_ci
    lo, hi = wilson_ci(0, 8)
    assert lo == 0.0 and 0 < hi <= 100
    lo, hi = wilson_ci(8, 8)
    assert hi == 100.0 and 0 <= lo < 100
    for n in (1, 5, 12, 40, 200):
        for k in range(n + 1):
            lo, hi = wilson_ci(k, n)
            assert 0.0 <= lo <= hi <= 100.0


def test_interval_narrows_as_the_sample_grows():
    from lib.boom_bust import wilson_ci
    widths = []
    for mult in (1, 4, 20):
        lo, hi = wilson_ci(1 * mult, 12 * mult)   # same 8% rate throughout
        widths.append(hi - lo)
    assert widths[0] > widths[1] > widths[2], (
        "the same point estimate must get MORE precise with more events")


def test_rate_precise_gates_at_the_documented_minimum():
    from lib.boom_bust import RATE_MIN_N, boom_bust_summary, rate_is_usable
    assert rate_is_usable(RATE_MIN_N) and not rate_is_usable(RATE_MIN_N - 1)
    thin = boom_bust_summary([12.0] * (RATE_MIN_N - 1), boom_thr=17, bust_thr=5)
    assert thin["rate_precise"] is False
    ok = boom_bust_summary([12.0] * RATE_MIN_N, boom_thr=17, bust_thr=5)
    assert ok["rate_precise"] is True


def test_series_stats_carries_the_same_precision_contract():
    """leverage_engine.series_stats feeds the optimizer's regime tie-break, so
    it must expose rate_precise too — that is the code path that ranked a
    1-in-12 bust rate ahead of a 5-in-24 one."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
    from lib.leverage_engine import series_stats

    thin = series_stats([12.0] * 7 + [-4.0], 17, 5)
    assert thin["n"] == 8 and thin["rate_precise"] is False
    assert thin["bust_ci"][1] > thin["bust_pct"]

    thick = series_stats([12.0] * 20 + [-4.0] * 5, 17, 5)
    assert thick["rate_precise"] is True
    assert series_stats([], 17, 5)["rate_precise"] is False
