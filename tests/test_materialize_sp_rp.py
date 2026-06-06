"""SP/RP opportunistic settlement in the decision materializer.

The materializer's H pathway was shipped in PR 5 sub-action 4. SP and
RP records previously stayed pending forever because no actuals fetcher
existed for them. These tests pin down the new MLB Stats API gameLog
path that feeds `LeagueScoring.score_pitcher_start` /
`score_pitcher_relief` (the canonical BrownU scorer).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plv_clone.decisions import logger as logger_mod  # noqa: E402
from plv_clone.decisions.logger import DecisionRecord, log_decision  # noqa: E402

import scripts.xfp.materialize_decisions as mat  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: stubbed gameLog fetcher and stubbed hitter Statcast aggregator
# ---------------------------------------------------------------------------


def _make_sp_games(
    starts: int, *, ip_str: str = "6.0", k: int = 7, h: int = 5,
    er: int = 2, bb: int = 1, hbp: int = 0, start_day: int = 12,
) -> list[dict]:
    """Synthetic per-start gameLog entries. All in May 2026."""
    return [
        {
            "date": f"2026-05-{start_day + i:02d}",
            "gamesStarted": 1,
            "inningsPitched": ip_str,
            "strikeOuts": k,
            "hits": h,
            "earnedRuns": er,
            "baseOnBalls": bb,
            "hitByPitch": hbp,
            "saves": 0,
            "holds": 0,
        }
        for i in range(starts)
    ]


def _make_rp_games(
    apps: int, *, ip_str: str = "1.0", k: int = 2, h: int = 0,
    er: int = 0, bb: int = 0, hbp: int = 0, sv: int = 0, hld: int = 0,
    start_day: int = 12,
) -> list[dict]:
    """Synthetic per-appearance gameLog entries."""
    return [
        {
            "date": f"2026-05-{start_day + i:02d}",
            "gamesStarted": 0,
            "inningsPitched": ip_str,
            "strikeOuts": k,
            "hits": h,
            "earnedRuns": er,
            "baseOnBalls": bb,
            "hitByPitch": hbp,
            "saves": sv,
            "holds": hld,
        }
        for i in range(apps)
    ]


# ---------------------------------------------------------------------------
# SP settlement
# ---------------------------------------------------------------------------


def test_settle_sp_decision_from_gamelog(tmp_path, monkeypatch):
    """A pending SP BUY at proj_per=14.0 with 5 stub starts averaging
    higher should settle as BUY_HIT."""
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    snap = "2026-05-01"
    rec = DecisionRecord(
        decision_id=f"{snap}_test_sp_SP_001",
        snapshot_date=snap,
        player_name="Test SP",
        mlbam_id=111111,
        bucket="SP",
        verdict_top="BUY",
        reason_tag="process_intact",
        confidence=0.66,
        inputs={"proj_per": 14.0},
    )
    log_decision(rec)

    # Stub the gameLog fetcher to return 5 strong starts:
    #   per-start FP = K + IP*3.3 - H - 2*ER - BB - HBP
    #                = 7 + 6*3.3 - 5 - 4 - 1 - 0 = 16.8
    games = _make_sp_games(starts=5)
    monkeypatch.setattr(
        mat, "_fetch_pitcher_gamelog", lambda mid, season: games,
    )

    # today after window (35d): 2026-05-01 + 35d = 2026-06-05; today=06-06.
    df = mat.materialize(
        as_of=date(2026, 6, 6),
        root=tmp_path,
        out_csv=tmp_path / "panel.csv",
    )
    assert len(df) == 1
    row = df.iloc[0]
    assert row["bucket"] == "SP"
    assert row["classification"] == "BUY_HIT", row.to_dict()
    # residual = 16.8 - 14.0 = 2.8, well above 1.0 SP threshold
    assert row["residual"] == pytest.approx(2.8, abs=0.01)
    assert row["n_events"] == 5


def test_settle_sp_stays_pending_when_too_few_starts(tmp_path, monkeypatch):
    """SP min_events=5. With only 3 starts the record must stay pending."""
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    snap = "2026-05-01"
    rec = DecisionRecord(
        decision_id=f"{snap}_test_sp_SP_001",
        snapshot_date=snap,
        player_name="Test SP",
        mlbam_id=111111,
        bucket="SP",
        verdict_top="BUY",
        reason_tag="process_intact",
        confidence=0.66,
        inputs={"proj_per": 14.0},
    )
    log_decision(rec)

    monkeypatch.setattr(
        mat, "_fetch_pitcher_gamelog",
        lambda mid, season: _make_sp_games(starts=3),
    )

    df = mat.materialize(
        as_of=date(2026, 6, 6),
        root=tmp_path,
        out_csv=tmp_path / "panel.csv",
    )
    assert len(df) == 1
    assert pd.isna(df.iloc[0]["settled_at"]) or df.iloc[0]["settled_at"] in (None, "")


# ---------------------------------------------------------------------------
# RP settlement
# ---------------------------------------------------------------------------


def test_settle_rp_decision_from_gamelog(tmp_path, monkeypatch):
    """RP BUY at proj_per=4.0 with 10 appearances averaging higher
    (including SVs) should settle as BUY_HIT.

    Per-appearance FP (with sv=1 on every game for simplicity):
        K + IP*3.3 - H - 2*ER - BB - HBP + 5*SV + 2*HLD
      = 2 + 1*3.3 - 0 - 0 - 0 - 0 + 5*1 + 0 = 10.3
    """
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    snap = "2026-05-01"
    rec = DecisionRecord(
        decision_id=f"{snap}_test_rp_RP_001",
        snapshot_date=snap,
        player_name="Test RP",
        mlbam_id=222222,
        bucket="RP",
        verdict_top="BUY",
        reason_tag="other",
        confidence=0.66,
        inputs={"proj_per": 4.0},
    )
    log_decision(rec)

    games = _make_rp_games(apps=10, sv=1)
    monkeypatch.setattr(
        mat, "_fetch_pitcher_gamelog", lambda mid, season: games,
    )

    df = mat.materialize(
        as_of=date(2026, 6, 6),
        root=tmp_path,
        out_csv=tmp_path / "panel.csv",
    )
    assert len(df) == 1
    row = df.iloc[0]
    assert row["bucket"] == "RP"
    assert row["classification"] == "BUY_HIT", row.to_dict()
    # residual = 10.3 - 4.0 = 6.3, above 0.5 RP threshold
    assert row["residual"] == pytest.approx(6.3, abs=0.01)
    assert row["n_events"] == 10


# ---------------------------------------------------------------------------
# Mixed-bucket integration
# ---------------------------------------------------------------------------


def test_materializer_handles_mixed_buckets(tmp_path, monkeypatch):
    """One H + one SP + one RP decision: all should land in the panel.
    H stays pending (no Statcast stub); SP + RP settle."""
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    snap = "2026-05-01"
    for bucket, pid, proj in [("H", 333333, 0.72),
                              ("SP", 444444, 14.0),
                              ("RP", 555555, 4.0)]:
        rec = DecisionRecord(
            decision_id=f"{snap}_test_{bucket.lower()}_{bucket}_001",
            snapshot_date=snap,
            player_name=f"Test {bucket}",
            mlbam_id=pid,
            bucket=bucket,
            verdict_top="HOLD",
            reason_tag="other",
            confidence=0.5,
            inputs={"proj_per": proj},
        )
        log_decision(rec)

    # H stub returns no data (so H stays pending).
    monkeypatch.setattr(
        mat, "_hitter_actuals_for_window",
        lambda yr, ids, ws, we: {},
    )

    # gameLog stub: SP gets 5 starts, RP gets 10 appearances. The fetcher
    # is keyed by mlbam_id so we branch on that.
    def fake_gamelog(mid: int, season: int) -> list[dict]:
        if mid == 444444:
            return _make_sp_games(starts=5)
        if mid == 555555:
            return _make_rp_games(apps=10, sv=1)
        return []

    monkeypatch.setattr(mat, "_fetch_pitcher_gamelog", fake_gamelog)

    df = mat.materialize(
        as_of=date(2026, 6, 6),
        root=tmp_path,
        out_csv=tmp_path / "panel.csv",
    )

    assert len(df) == 3
    by_bucket = {r["bucket"]: r for _, r in df.iterrows()}
    # SP + RP settled
    assert by_bucket["SP"]["classification"] == "HOLD_NEUTRAL"
    assert by_bucket["RP"]["classification"] == "HOLD_NEUTRAL"
    # H stays pending
    h_settled = by_bucket["H"]["settled_at"]
    assert pd.isna(h_settled) or h_settled in (None, "")
