"""Tests for the env-gated decision-logging hook inside triangulate_player.

The hook MUST be a strict no-op when PLV_LOG_DECISIONS is unset or "0"
so existing tests/callers are unaffected. When set to "1" it persists
one DecisionRecord JSON per call under `DECISIONS_ROOT`.

Failure to log must NEVER propagate — a logging exception is swallowed
and printed to stderr only.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plv_clone.decisions import logger as logger_mod  # noqa: E402
from scripts.xfp.lib.triangulate_core import triangulate_player  # noqa: E402


def _count_jsons(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob("*.json"))


def test_triangulate_does_not_log_when_env_unset(tmp_path, monkeypatch):
    """With PLV_LOG_DECISIONS unset, no decision JSON should appear."""
    monkeypatch.delenv("PLV_LOG_DECISIONS", raising=False)
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    result = triangulate_player("Aaron Judge")
    assert result is not None

    assert _count_jsons(tmp_path) == 0


def test_triangulate_logs_when_env_set(tmp_path, monkeypatch):
    """With PLV_LOG_DECISIONS=1, exactly one decision JSON is written
    at {tmp}/{today}/{decision_id}.json with the expected fields."""
    monkeypatch.setenv("PLV_LOG_DECISIONS", "1")
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    result = triangulate_player("Aaron Judge")
    assert result is not None

    today_dir = tmp_path / date.today().isoformat()
    assert today_dir.exists(), f"expected today's dir at {today_dir}"

    jsons = list(today_dir.glob("*.json"))
    assert len(jsons) == 1, f"expected 1 json, got {len(jsons)}: {jsons}"

    payload = json.loads(jsons[0].read_text(encoding="utf-8"))
    assert payload["snapshot_date"] == date.today().isoformat()
    assert payload["bucket"] == "H"
    # decision_id format: {date}_{norm_name}_{bucket}_{seq:03d}
    assert payload["decision_id"].startswith(f"{date.today().isoformat()}_")
    assert payload["decision_id"].endswith("_H_001")
    assert "judge" in payload["decision_id"].lower()
    # verdict_top must be a valid bucket
    assert payload["verdict_top"] in ("BUY", "HOLD", "CAUTION", "FADE", "MIXED")
    # inputs round-trip
    assert "proj_per" in payload["inputs"]
    # not yet settled
    assert payload["settled_at"] is None


def test_triangulate_logging_failure_is_swallowed(
    tmp_path, monkeypatch, capsys
):
    """If log_decision raises, triangulate_player must still return a
    normal result and emit a stderr warning — never propagate."""
    monkeypatch.setenv("PLV_LOG_DECISIONS", "1")
    monkeypatch.setattr(logger_mod, "DECISIONS_ROOT", tmp_path)

    # Patch the function as imported INSIDE triangulate_core's hook.
    # The hook imports `plv_clone.decisions.logger.log_decision` lazily,
    # so monkeypatching the module attribute is enough.
    def _boom(*a, **kw):
        raise RuntimeError("simulated log failure")

    monkeypatch.setattr(logger_mod, "log_decision", _boom)

    # No exception should escape.
    result = triangulate_player("Aaron Judge")
    assert result is not None
    assert result["bucket"] == "H"

    captured = capsys.readouterr()
    assert "decision log failed" in captured.err
    assert "simulated log failure" in captured.err
