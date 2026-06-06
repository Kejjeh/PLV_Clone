"""Tests for plv_clone.decisions.logger — PR 5 sub-action 2."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from plv_clone.decisions.logger import (
    DecisionRecord,
    build_decision_id,
    from_triangulate_result,
    log_decision,
)


def _make_record(snapshot_date="2026-06-06", player="Eugenio Suárez", bucket="H"):
    decision_id = build_decision_id(snapshot_date, player, bucket, seq=1)
    return DecisionRecord(
        decision_id=decision_id,
        snapshot_date=snapshot_date,
        player_name=player,
        mlbam_id=553993,
        bucket=bucket,
        verdict_top="BUY",
        reason_tag="process_intact",
        confidence=0.66,
        inputs={"proj_per": 0.72, "pl_rank": 88, "model_rank": 42},
    )


def test_log_decision_writes_to_correct_path(tmp_path: Path):
    """log_decision lands the JSON at {root}/{snapshot_date}/{decision_id}.json
    with readable content matching the record."""
    record = _make_record()
    written = log_decision(record, root=tmp_path)

    expected = tmp_path / "2026-06-06" / f"{record.decision_id}.json"
    assert written == expected
    assert written.exists()

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["decision_id"] == record.decision_id
    assert payload["player_name"] == "Eugenio Suárez"
    assert payload["bucket"] == "H"
    assert payload["verdict_top"] == "BUY"
    assert payload["inputs"]["proj_per"] == 0.72
    # settled fields default to None
    assert payload["settled_at"] is None
    assert payload["settlement"] is None


def test_decision_id_format():
    """Accents are ASCII-folded (Suárez -> suarez), seq defaults to 001,
    and changing seq changes the id."""
    # accent fold
    did = build_decision_id("2026-06-06", "Eugenio Suárez", "H", seq=1)
    assert did == "2026-06-06_eugenio_suarez_H_001"

    # default seq is 1 -> 001
    did_default = build_decision_id("2026-06-06", "Max Muncy", "H")
    assert did_default.endswith("_H_001")

    # seq=2 -> 002 (different path)
    did2 = build_decision_id("2026-06-06", "Eugenio Suárez", "H", seq=2)
    assert did2 == "2026-06-06_eugenio_suarez_H_002"
    assert did != did2


def test_from_triangulate_result_minimal():
    """Smoke: a triangulate-shaped dict round-trips into a DecisionRecord
    with the expected verdict_top and inputs."""
    fake_result = {
        "player": {"display_name": "Eugenio Suárez", "id": "553993", "bucket": "H"},
        "bucket": "H",
        "verdict_top": "BUY",
        "reason_tag": "process_intact",
        "confidence": 0.66,
        "pl_rank": 88,
        "model_rank": 42,
        "model_proj": 0.72,
        "arche_overall": 55,
        "arche_label": "POWER_OR_BUST",
        "arche_traj": "stable",
        "replacement_delta": None,
        "live_marginal": 0.04,
        "blended_xfp": 0.71,
        "override_tag": None,
    }
    rec = from_triangulate_result(fake_result, snapshot_date=date(2026, 6, 6))
    assert rec.player_name == "Eugenio Suárez"
    assert rec.mlbam_id == 553993
    assert rec.bucket == "H"
    assert rec.verdict_top == "BUY"
    assert rec.inputs["proj_per"] == 0.72
    assert rec.inputs["pl_rank"] == 88
    assert rec.decision_id.startswith("2026-06-06_eugenio_suarez_H_")


def test_from_triangulate_result_empty_raises():
    with pytest.raises(ValueError):
        from_triangulate_result({}, snapshot_date=date(2026, 6, 6))
