"""Decision settler — PR 5 sub-action 3.

Pure function. Takes a DecisionRecord + actuals + n_events + today and
returns a NEW DecisionRecord with settlement populated if the window
has fully elapsed.

The HOST script that PULLS actuals + n_events from Statcast / game logs
is out of scope for this PR — `settle_decision` is a pure function so it
can be tested in isolation and called from the materializer or any
future driver.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from typing import Optional

from .logger import DecisionRecord


# Per-bucket settlement contract.
#   days         : minimum elapsed days before we'll settle
#   min_events   : minimum n_events (PA / starts / appearances) before we'll settle
#   event_unit   : human-readable unit (display only)
#   threshold    : residual magnitude (actual - proj_per) that must be
#                  exceeded for BUY_HIT / FADE_HIT classification
SETTLEMENT_WINDOWS = {
    "H": {
        "days": 21,
        "min_events": 30,
        "event_unit": "PA",
        "threshold": 0.02,  # FP/PA
    },
    "SP": {
        "days": 35,
        "min_events": 5,
        "event_unit": "starts",
        "threshold": 1.0,  # FP/start
    },
    "RP": {
        "days": 35,
        "min_events": 10,
        "event_unit": "appearances",
        "threshold": 0.5,  # FP/g
    },
}


# Verdicts that have NO directional claim — settled but tagged NEUTRAL.
NEUTRAL_VERDICTS = {"HOLD", "CAUTION", "MIXED"}


def _parse_iso(d: str) -> date:
    """Parse an ISO date string; accept 'YYYY-MM-DD' or full ISO datetime."""
    try:
        return date.fromisoformat(d)
    except ValueError:
        return datetime.fromisoformat(d).date()


def _classify(
    verdict_top: str, residual: float, threshold: float
) -> str:
    """Map (verdict, residual) -> classification label."""
    if verdict_top == "BUY":
        return "BUY_HIT" if residual > threshold else "BUY_MISS"
    if verdict_top == "FADE":
        return "FADE_HIT" if residual < -threshold else "FADE_MISS"
    # HOLD / CAUTION / MIXED — no directional commitment, neutral tag.
    return f"{verdict_top}_NEUTRAL"


def settle_decision(
    record: DecisionRecord,
    *,
    today: date,
    actual_fp_per_unit: Optional[float],
    n_events: int,
) -> DecisionRecord:
    """Return a NEW DecisionRecord with settlement populated when ready.

    "Ready" = today >= snapshot_date + window_days AND n_events >= min_events
    AND actual_fp_per_unit is not None.

    Otherwise the input record is returned unchanged (settled_at stays
    None) so callers can re-try tomorrow.

    Classification (residual = actual_fp_per_unit - inputs['proj_per']):
      BUY  + residual >  +threshold => BUY_HIT
      BUY  + residual <= +threshold => BUY_MISS
      FADE + residual <  -threshold => FADE_HIT
      FADE + residual >= -threshold => FADE_MISS
      HOLD / CAUTION / MIXED => "{verdict}_NEUTRAL"
    """
    bucket = record.bucket
    if bucket not in SETTLEMENT_WINDOWS:
        return record
    window = SETTLEMENT_WINDOWS[bucket]

    snap = _parse_iso(record.snapshot_date)
    window_end = snap + timedelta(days=window["days"])

    # Not enough time elapsed yet.
    if today < window_end:
        return record

    # Not enough events.
    if n_events < window["min_events"]:
        return record

    # No actual available (e.g., Statcast pull failed).
    if actual_fp_per_unit is None:
        return record

    proj_per = (record.inputs or {}).get("proj_per")
    if proj_per is None:
        # Can't compute residual — leave unsettled, but flag the gap.
        return record

    residual = float(actual_fp_per_unit) - float(proj_per)
    classification = _classify(
        record.verdict_top, residual, window["threshold"]
    )

    settlement = {
        "actual_fp_per_unit": float(actual_fp_per_unit),
        "proj_per": float(proj_per),
        "residual": residual,
        "n_events": int(n_events),
        "event_unit": window["event_unit"],
        "threshold": window["threshold"],
        "classification": classification,
        "window_days": window["days"],
    }
    return dataclasses.replace(
        record,
        settled_at=today.isoformat(),
        settlement=settlement,
    )
