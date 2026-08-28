"""A hit rate is unreadable without the base rate beside it.

WHY THIS FILE EXISTS
`/verdict-scorecard` reported a directional hit rate of 34% over 405 BUY/FADE
records. Read cold that says the process is wrong two times in three. It says
no such thing (issue #53).

`settler._classify` scores a player against HIS OWN projection:

    BUY_HIT iff (actual - proj_per) > +threshold

so a calibrated model scores well under 50% by construction — the threshold
sits strictly outside the median. The only meaningful comparison is the same
beat-rate over ALL settled records in the bucket, whatever the verdict.
Measured 2026-08-27: hitter BUY beat 23.1% against an all-verdict base of
23.0%. The honest statement is "+0.1pp", not "31%".

`n_players` was already reported per row; the base rate and the edge were not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "src"))

pd = pytest.importorskip("pandas")
vs = pytest.importorskip("run_verdict_scorecard")


def _rec(bucket, verdict, player, residual, classification, thr=0.02):
    return dict(bucket=bucket, verdict=verdict, player=player, actual=1.0,
                proj_per=1.0 - residual, residual=residual, threshold=thr,
                classification=classification, unit="PA")


def _frame(rows):
    return pd.DataFrame(rows)


def test_the_ladder_reports_a_base_rate_and_an_edge():
    df = _frame([
        _rec("H", "BUY", "a", +0.10, "BUY_HIT"),
        _rec("H", "BUY", "b", -0.10, "BUY_MISS"),
        _rec("H", "MIXED", "c", -0.20, "MIXED_NEUTRAL"),
        _rec("H", "MIXED", "d", -0.20, "MIXED_NEUTRAL"),
    ])
    out = vs.build_ladder(df)
    buy = out[out["verdict"] == "BUY"].iloc[0]
    assert buy["hit_rate"] == pytest.approx(0.5)
    assert buy["base_beat_rate"] == pytest.approx(0.25), (
        "the base rate must span EVERY verdict in the bucket, not just BUY")
    assert buy["hit_rate_edge"] == pytest.approx(0.25)


def test_a_hit_rate_matching_the_base_rate_reports_no_edge():
    """The finding that made this necessary: 23.1% BUY vs a 23.0% base."""
    rows = [_rec("H", "BUY", f"b{i}", +0.10 if i == 0 else -0.10,
                 "BUY_HIT" if i == 0 else "BUY_MISS") for i in range(4)]
    rows += [_rec("H", "MIXED", f"m{i}", +0.10 if i == 0 else -0.10,
                  "MIXED_NEUTRAL") for i in range(4)]
    out = vs.build_ladder(_frame(rows))
    buy = out[out["verdict"] == "BUY"].iloc[0]
    assert buy["hit_rate"] == pytest.approx(0.25)
    assert buy["base_beat_rate"] == pytest.approx(0.25)
    assert buy["hit_rate_edge"] == pytest.approx(0.0), (
        "a BUY that beats its projection exactly as often as the bucket does "
        "has NO edge, and the scorecard must say so")


def test_unique_player_count_is_reported():
    """Pooled n is not sample size — 509 SP records came from 14 pitchers."""
    rows = [_rec("SP", "BUY", "same guy", +2.0, "BUY_HIT", thr=1.0)
            for _ in range(5)]
    out = vs.build_ladder(_frame(rows))
    row = out.iloc[0]
    assert row["n"] == 5
    assert row["n_players"] == 1, (
        "five records from one pitcher must report n_players=1")


def test_non_directional_verdicts_get_a_base_rate_but_no_hit_rate():
    df = _frame([_rec("H", "MIXED", "c", -0.20, "MIXED_NEUTRAL")])
    row = vs.build_ladder(df).iloc[0]
    assert row["hit_rate"] is None or pd.isna(row["hit_rate"])
    assert row["base_beat_rate"] is not None
