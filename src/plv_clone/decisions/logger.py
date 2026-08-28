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

    # ── schema v3 (2026-07-29): EXECUTED moves + their counterfactual ─────────
    # Every field below is optional with a default, which is what keeps the 131
    # days of existing v1/v2 records readable: settle_decisions rebuilds via
    # DecisionRecord(**payload), so a missing key simply takes its default. Same
    # backward-compatible pattern as the v1 -> v2 units fix.
    #
    # WHY v3 EXISTS. v1/v2 record a VERDICT on a player ("BUY Cam Smith") and the
    # settler asks "was the projection right?" — residual vs realized FP/unit.
    # That is a real question but it is not the one that decides a season. The
    # question that does is "was the CHOICE right?": Josh executed one move out of
    # a surface of alternatives, and the only honest grade is
    # realized(chosen) - realized(rejected) over a common window. Those are
    # different comparisons and both blocks can coexist on one record —
    # `settlement` keeps answering the projection question, and
    # `counterfactual_settlement` (filled by decisions/counterfactual.py) answers
    # the choice question.
    #
    # record_schema is explicit rather than inferred: v2 was distinguished by the
    # PRESENCE of inputs['proj_units'], which worked but meant every reader had to
    # know that trick.
    record_schema: int = 2
    # add | drop | swap | start | bench | hold. None on a legacy verdict-style
    # record, which is how the settler tells them apart without guessing.
    action: Optional[str] = None
    # ISO datetime the move actually happened in ESPN. None = advisory only, never
    # executed — a distinction the scorecard needs, since an unexecuted
    # recommendation cannot be graded as a decision.
    executed_at: Optional[str] = None
    # {rejected_name, rejected_mlbam, rejected_bucket, dpwin_chosen,
    #  dpwin_rejected, dpwin_gap, source_run_id, regime, base_pwin,
    #  dtitle_equity_chosen}
    # Presence of this block is what GATES paired settlement — no alternative
    # recorded means there is nothing to compare against, and inventing one after
    # the fact would be hindsight, not accounting.
    counterfactual: Optional[dict] = None
    # Filled by the paired settler. Sibling of `settlement`, never a replacement.
    counterfactual_settlement: Optional[dict] = None

    # ── schema v4 (2026-08-05): FALSIFIABLE predictions ──────────────────────
    # Same optional-with-default discipline, so v1-v3 records keep parsing.
    #
    # WHY v4 EXISTS. v2 asks "was the projection right?", v3 asks "was the
    # choice right?". Neither asks "was the CLAIM right?" — and a claim is the
    # thing an advisor actually owes. The season review on 2026-08-05 found ten
    # resolved swaps in four months and no way to say who had been correct
    # about anything, because "BUY" is not a statement that can turn out false.
    # A v4 record pins a number and a deadline at the moment the advice is
    # given, so it can.
    #
    # See plv_clone.decisions.prediction for the claim shape and the rules that
    # keep it honest (no settling before the horizon; zero playing time settles
    # rather than excuses).
    prediction: Optional[dict] = None
    prediction_settlement: Optional[dict] = None


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
# schema v3 — executed-move records
# ---------------------------------------------------------------------------

VALID_ACTIONS = frozenset({"add", "drop", "swap", "start", "bench", "hold"})


def build_executed_record(
    *,
    snapshot_date: str,
    player_name: str,
    mlbam_id: Optional[int],
    bucket: str,
    action: str,
    executed_at: Optional[str] = None,
    rejected: Optional[dict] = None,
    dpwin_chosen: Optional[float] = None,
    dpwin_rejected: Optional[float] = None,
    source_run_id: Optional[str] = None,
    regime: Optional[str] = None,
    base_pwin: Optional[float] = None,
    dtitle_equity_chosen: Optional[float] = None,
    reason_tag: Optional[str] = None,
    seq: int = 1,
    inputs: Optional[dict] = None,
) -> DecisionRecord:
    """Build a v3 record for a move that was (or will be) EXECUTED.

    ``rejected`` = {'name', 'mlbam', 'bucket'} — the best alternative that was
    passed on, normally the top *unexecuted* same-bucket candidate from the same
    dpwin_history run. Omitting it produces a valid v3 record that simply cannot
    be paired-settled, which is the honest state for a move made with no recorded
    alternative.

    dpwin_gap is derived rather than passed so it can never disagree with its
    own components.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"action {action!r} not in {sorted(VALID_ACTIONS)} — refusing to "
            f"write a record the settler cannot interpret")

    cf = None
    if rejected or dpwin_chosen is not None or source_run_id:
        gap = None
        if dpwin_chosen is not None and dpwin_rejected is not None:
            gap = round(float(dpwin_chosen) - float(dpwin_rejected), 6)
        cf = {
            "rejected_name": (rejected or {}).get("name"),
            "rejected_mlbam": (rejected or {}).get("mlbam"),
            "rejected_bucket": (rejected or {}).get("bucket"),
            "dpwin_chosen": dpwin_chosen,
            "dpwin_rejected": dpwin_rejected,
            "dpwin_gap": gap,
            "source_run_id": source_run_id,
            "regime": regime,
            "base_pwin": base_pwin,
            "dtitle_equity_chosen": dtitle_equity_chosen,
        }

    return DecisionRecord(
        decision_id=build_decision_id(snapshot_date, player_name, bucket, seq=seq),
        snapshot_date=snapshot_date,
        player_name=player_name,
        mlbam_id=(int(mlbam_id) if mlbam_id else None),
        bucket=bucket,
        # An executed move is not a "verdict"; carry the action so the existing
        # verdict ladder in run_verdict_scorecard cannot mistake it for one.
        verdict_top=action.upper(),
        reason_tag=reason_tag,
        confidence=None,
        inputs=dict(inputs or {}, inputs_schema=3),
        record_schema=3,
        action=action,
        executed_at=executed_at,
        counterfactual=cf,
    )


def build_prediction_record(
    *,
    snapshot_date: str,
    player_name: str,
    mlbam_id: Optional[int],
    bucket: str,
    prediction: Any,
    verdict_top: str = "PREDICT",
    reason_tag: Optional[str] = None,
    confidence: Optional[float] = None,
    seq: int = 1,
    inputs: Optional[dict] = None,
) -> DecisionRecord:
    """Build a v4 record carrying a falsifiable claim.

    ``prediction`` is a plv_clone.decisions.prediction.Prediction (or an
    equivalent dict). It is stored verbatim; nothing downstream may edit it,
    because a claim that can be revised after the fact is not a claim.
    """
    payload = prediction.as_dict() if hasattr(prediction, "as_dict") else dict(prediction)
    for required in ("claim", "metric", "threshold", "horizon_end"):
        if payload.get(required) in (None, ""):
            raise ValueError(
                f"prediction is missing {required!r} — refusing to log a claim "
                f"that cannot be settled")

    return DecisionRecord(
        decision_id=build_decision_id(snapshot_date, player_name, bucket, seq=seq),
        snapshot_date=snapshot_date,
        player_name=player_name,
        mlbam_id=(int(mlbam_id) if mlbam_id else None),
        bucket=bucket,
        verdict_top=verdict_top,
        reason_tag=reason_tag,
        confidence=confidence,
        inputs=dict(inputs or {}, inputs_schema=4),
        record_schema=4,
        prediction=payload,
    )


def is_prediction_record(rec: DecisionRecord) -> bool:
    """True for a v4 record carrying an unsettled or settled claim."""
    return bool(getattr(rec, "prediction", None))


def is_executed_record(rec: DecisionRecord) -> bool:
    """True for a v3 executed-move record (as opposed to a verdict record)."""
    return getattr(rec, "action", None) is not None


def is_pairable(rec: DecisionRecord) -> bool:
    """True when a record carries an alternative worth settling against.

    Requires an executed timestamp AND a named rejected alternative: without the
    first there is no window to measure over, and without the second there is
    nothing to measure against.
    """
    cf = getattr(rec, "counterfactual", None) or {}
    return bool(getattr(rec, "executed_at", None)) and bool(cf.get("rejected_name"))


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
        # Which lenses were suppressed when this verdict was built (issue #57).
        # A verdict logged off a degraded stack would otherwise be settled later
        # as though it were a full-stack read, with nothing in the record to say
        # it wasn't. Recorded rather than declined: declining loses the decision
        # entirely, which is strictly worse than grading it with a caveat.
        "degraded_lenses": list(result.get("degraded_lenses") or []),
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
