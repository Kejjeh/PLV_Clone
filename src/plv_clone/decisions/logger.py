"""Decision logger — PR 5 sub-action 2.

One JSON file per decision (NOT JSONL; one file per decision avoids
Windows append contention — plan v11 Decision 9). Atomic write via temp
file + os.replace.

Storage layout:
    data/research/decisions/{YYYY-MM-DD}/{decision_id}.json

Decision ID format:
    {iso_date}_{norm_name}_{bucket}_{seq:03d}

where `norm_name` is unicodedata.NFKD ASCII-folded lower-snake and `seq`
increments per-player-per-day.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

DECISIONS_ROOT = Path("data/research/decisions")


@dataclass
class DecisionRecord:
    """A single verdict-level decision.

    Fields mirror the contract specified in the PR 5 plan. settled_at /
    settlement remain None until the settler fills them in once the
    settlement window has fully elapsed AND we have enough events.
    """

    decision_id: str
    snapshot_date: str
    player_name: str
    mlbam_id: Optional[int]
    bucket: str
    verdict_top: str
    reason_tag: Optional[str]
    confidence: Optional[float]
    inputs: dict[str, Any] = field(default_factory=dict)
    settled_at: Optional[str] = None
    settlement: Optional[dict] = None


# ---------------------------------------------------------------------------
# Name normalization + decision_id construction
# ---------------------------------------------------------------------------


def _norm_name(name: str) -> str:
    """ASCII-fold via NFKD, lowercase, strip non-alnum -> snake.

    Suárez -> "suarez", "Max Muncy" -> "max_muncy".
    """
    if not name:
        return "unknown"
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9\s]", "", ascii_only).strip().lower()
    return re.sub(r"\s+", "_", cleaned) or "unknown"


def build_decision_id(
    snapshot_date: str, player_name: str, bucket: str, seq: int = 1
) -> str:
    """Build the canonical decision_id."""
    return f"{snapshot_date}_{_norm_name(player_name)}_{bucket}_{seq:03d}"


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp file + os.replace.

    Concurrent runs cannot corrupt the target file — at worst, the
    later writer wins.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp_path, path)


def log_decision(
    record: DecisionRecord, *, root: Optional[Path] = None
) -> Path:
    """Persist a DecisionRecord to disk.

    Returns the written path:
        {root}/{snapshot_date}/{decision_id}.json

    When `root` is None we look up `DECISIONS_ROOT` from the module at
    call time. This lets tests monkeypatch the module-level
    `DECISIONS_ROOT` to a tmp_path and have it take effect without
    having to thread the path through every caller.
    """
    if root is None:
        # Re-resolve module-level attr so monkeypatching works.
        import plv_clone.decisions.logger as _self
        root = _self.DECISIONS_ROOT
    path = Path(root) / record.snapshot_date / f"{record.decision_id}.json"
    _atomic_write_json(path, asdict(record))
    return path


# ---------------------------------------------------------------------------
# Triangulate -> DecisionRecord
# ---------------------------------------------------------------------------


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "—":
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "—":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def from_triangulate_result(
    result: dict, *, snapshot_date: date, seq: int = 1
) -> DecisionRecord:
    """Build a DecisionRecord from a triangulate_player() output dict.

    See scripts/xfp/lib/triangulate_core.py::triangulate_player for the
    dict shape. We pull verdict_top, reason_tag, confidence, bucket, and
    a small set of input signals (pl_rank, model_rank, model_proj,
    archetype overall, replacement_delta when present).
    """
    if not result:
        raise ValueError("triangulate result is empty / None")

    player = result.get("player") or {}
    display_name = (
        player.get("display_name")
        or player.get("name")
        or result.get("player_name")
        or "unknown"
    )
    bucket = result.get("bucket") or player.get("bucket") or "H"
    iso_date = snapshot_date.isoformat()

    inputs = {
        "pl_rank": _safe_int(result.get("pl_rank")),
        "model_rank": _safe_int(result.get("model_rank")),
        # inputs_schema 2 (2026-07-10): proj_per is now in SETTLEMENT units
        # (H fp_per_pa, SP fp_per_start, RP fp_per_g) — previously it logged
        # the display headline (H fp/GAME, RP RoS TOTAL), which poisoned
        # settlement residuals at a 3.4x offset for hitters. The display
        # value is kept as proj_display; proj_units makes records
        # self-describing so the settler never guesses.
        "proj_per": _safe_float(result.get("model_proj_settle")),
        "proj_units": result.get("model_proj_settle_units"),
        "proj_display": _safe_float(result.get("model_proj")),
        "inputs_schema": 2,
        "archetype_overall": _safe_int(result.get("arche_overall")),
        "archetype_label": result.get("arche_label"),
        "archetype_traj": result.get("arche_traj"),
        "replacement_delta": _safe_float(result.get("replacement_delta")),
        "live_marginal": _safe_float(result.get("live_marginal")),
        "blended_xfp": _safe_float(result.get("blended_xfp")),
        "override_tag": result.get("override_tag"),
    }

    mlbam_id = _safe_int(player.get("id") or player.get("mlbam_id"))

    return DecisionRecord(
        decision_id=build_decision_id(iso_date, display_name, bucket, seq=seq),
        snapshot_date=iso_date,
        player_name=display_name,
        mlbam_id=mlbam_id,
        bucket=bucket,
        verdict_top=result.get("verdict_top") or "HOLD",
        reason_tag=result.get("reason_tag"),
        confidence=_safe_float(result.get("confidence")),
        inputs=inputs,
    )
