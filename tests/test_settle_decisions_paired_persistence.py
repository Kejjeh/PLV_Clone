"""settle_decisions.py — paired (counterfactual) settlement persistence (C9).

The audit finding: for a name-only record (mlbam never resolved),
``_settle_counterfactual_one`` PRODUCES the paired-settlement block, but the
driver discarded it because persistence rode the residual path, which requires
a resolved id. The grade was computed and thrown away every night, and the
rejected player's game log was re-fetched every run.

Behavioral contract pinned here:
  1. a decision with a recorded alternative is graded even when the chosen
     player's id never resolved: after one settlement run the counterfactual
     settlement is readable from disk, and a second run reuses it without
     re-fetching the game log;
  2. the run summary counts paired settlements explicitly, and a record with
     no residual settlement never inflates the classified total.

Seams (same pattern as tests/test_no_silent_zero_inputs.py): monkeypatch the
module-level network boundary ``settle_decisions._fetch_gamelog`` with a fake
that serves synthetic gamelog rows (the exact shape the module's cache holds)
and counts calls; all disk I/O goes through a tmp_path decisions root passed
via the public ``run(root=...)`` parameter.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src", ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import settle_decisions as SD  # noqa: E402
from plv_clone.decisions.logger import (  # noqa: E402
    build_executed_record, log_decision,
)

SNAP = "2026-07-01"
TODAY = date(2026, 8, 1)  # H windows (21d residual + 21d paired) fully elapsed
CHOSEN_MLBAM = 111
REJECTED_MLBAM = 222


def _hit_game(iso_day: str) -> dict:
    """One synthetic hitting gameLog row in the cache shape the module reads.

    BrownU FP = R + TB + RBI + BB + HBP + SB - K = 1+2+1+1+0+0-1 = 4.0 FP / 4 PA.
    """
    return {"date": iso_day, "plateAppearances": 4, "runs": 1, "totalBases": 2,
            "rbi": 1, "baseOnBalls": 1, "hitByPitch": 0, "stolenBases": 0,
            "strikeOuts": 1}


class FakeGamelog:
    """Stands in for the network boundary SD._fetch_gamelog; counts every call."""

    def __init__(self, games_by_mlbam: dict[int, list[dict]]):
        self.games_by_mlbam = games_by_mlbam
        self.calls: list[tuple[int, int, str]] = []

    def __call__(self, mlbam_id: int, season: int, group: str) -> list[dict]:
        self.calls.append((int(mlbam_id), int(season), group))
        return self.games_by_mlbam.get(int(mlbam_id), [])


def _rejected_games() -> list[dict]:
    # 15 games inside the July window -> 60 FP / 60 PA for the alternative.
    return [_hit_game(f"2026-07-{d:02d}") for d in range(2, 17)]


def _name_only_record():
    """An executed swap whose CHOSEN side never resolved to an mlbam id, but
    whose recorded alternative did — pairable, residual-unsettleable forever."""
    return build_executed_record(
        snapshot_date=SNAP, player_name="Chosen Guy", mlbam_id=None,
        bucket="H", action="swap", executed_at=f"{SNAP}T09:00:00",
        rejected={"name": "Passed Guy", "mlbam": REJECTED_MLBAM, "bucket": "H"},
        dpwin_chosen=0.05, dpwin_rejected=0.03)


def test_name_only_counterfactual_grade_is_readable_from_disk_after_one_run(
        tmp_path, monkeypatch):
    fake = FakeGamelog({REJECTED_MLBAM: _rejected_games()})
    monkeypatch.setattr(SD, "_fetch_gamelog", fake)
    rec = _name_only_record()
    log_decision(rec, root=tmp_path)

    SD.run(today=TODAY, root=tmp_path)

    mirror = tmp_path / "settled" / SNAP / f"{rec.decision_id}.json"
    assert mirror.exists(), (
        "paired settlement was computed but never persisted to the settled/ "
        "mirror — the grade is thrown away every night")
    payload = json.loads(mirror.read_text(encoding="utf-8"))
    blk = payload.get("counterfactual_settlement")
    assert blk, "mirror exists but carries no counterfactual_settlement block"
    # The name-only chosen side has no measurable events -> honest UNSETTLEABLE,
    # persisted rather than recomputed forever.
    assert blk["classification"] == "UNSETTLEABLE"
    assert blk["n_events_rejected"] == 60


def test_second_run_reuses_the_persisted_grade_without_refetching(
        tmp_path, monkeypatch):
    rec = _name_only_record()
    log_decision(rec, root=tmp_path)

    first = FakeGamelog({REJECTED_MLBAM: _rejected_games()})
    monkeypatch.setattr(SD, "_fetch_gamelog", first)
    SD.run(today=TODAY, root=tmp_path)
    assert first.calls, "sanity: the first run should have fetched the game log"

    second = FakeGamelog({REJECTED_MLBAM: _rejected_games()})
    monkeypatch.setattr(SD, "_fetch_gamelog", second)
    SD.run(today=TODAY, root=tmp_path)
    assert second.calls == [], (
        "second run re-fetched the game log instead of reusing the persisted "
        f"counterfactual settlement: {second.calls}")


def test_run_summary_counts_paired_settlements_explicitly(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        SD, "_fetch_gamelog", FakeGamelog({REJECTED_MLBAM: _rejected_games()}))
    log_decision(_name_only_record(), root=tmp_path)

    summary = SD.run(today=TODAY, root=tmp_path)
    assert summary["paired_settled"] == 1
    assert "paired 1 new" in capsys.readouterr().out

    # Second run: the grade already exists on disk — nothing newly paired.
    summary2 = SD.run(today=TODAY, root=tmp_path)
    assert summary2["paired_settled"] == 0
    assert "paired 0 new" in capsys.readouterr().out


def _resolved_id_record_with_thin_residual_sample():
    """Chosen id resolved, but only 12 PA in the window (< 30 min_events):
    the paired grade lands while the residual settlement must stay pending."""
    return build_executed_record(
        snapshot_date=SNAP, player_name="Chosen Guy", mlbam_id=CHOSEN_MLBAM,
        bucket="H", action="swap", executed_at=f"{SNAP}T09:00:00",
        rejected={"name": "Passed Guy", "mlbam": REJECTED_MLBAM, "bucket": "H"},
        dpwin_chosen=0.05, dpwin_rejected=0.03)


def test_paired_only_record_never_inflates_the_classified_total(
        tmp_path, monkeypatch):
    chosen_games = [_hit_game(f"2026-07-{d:02d}") for d in (3, 8, 12)]  # 12 PA
    monkeypatch.setattr(SD, "_fetch_gamelog", FakeGamelog({
        CHOSEN_MLBAM: chosen_games, REJECTED_MLBAM: _rejected_games()}))
    rec = _resolved_id_record_with_thin_residual_sample()
    log_decision(rec, root=tmp_path)

    summary = SD.run(today=TODAY, root=tmp_path)
    assert summary["paired_settled"] == 1
    # The residual settlement did NOT happen (12 PA < 30) — it must not be
    # counted as settled, and the record stays in the pending/retry pool.
    assert summary["newly_settled"] == 0
    assert summary["settled_total"] == 0
    assert summary["ripe_but_pending"] == 1

    # On disk: paired grade persisted, residual honestly absent.
    payload = json.loads(
        (tmp_path / "settled" / SNAP / f"{rec.decision_id}.json")
        .read_text(encoding="utf-8"))
    assert payload["counterfactual_settlement"]
    assert payload["settlement"] is None

    # Second run: the paired-only mirror must not masquerade as a residual
    # settlement — the classified total stays 0 and the residual is retried.
    summary2 = SD.run(today=TODAY, root=tmp_path)
    assert summary2["settled_total"] == 0
    assert summary2["reused_settled"] == 0
    assert summary2["ripe_but_pending"] == 1
