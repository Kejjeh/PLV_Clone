"""Falsifiable predictions — schema v4.

WHY THIS EXISTS
---------------
v1/v2 records log a VERDICT ("BUY Cam Smith") and settle it on projection
residual. v3 logs an EXECUTED move and settles it against the alternative
that was passed on. Neither captures the thing that actually needs auditing:
a stated claim about the future, with a number and a deadline attached,
recorded BEFORE the outcome is known.

The 2026-08-05 season review found the gap concretely. Ten swaps had resolved
in four months, and neither Josh nor Claude could say who had been right about
anything, because no claim had ever been written down in a form that could be
wrong. A verdict of "BUY" is not falsifiable. "Grisham scores at least 15 more
FP than Duran over the next 21 days" is.

THE RULES THAT MAKE IT HONEST
-----------------------------
1. A prediction with no threshold and no horizon is not a prediction. Both are
   required at construction, so a claim cannot be quietly softened later.
2. Settlement never runs before the horizon. An early peek that resolved the
   good half of the book and left the rest PENDING would be survivorship, and
   the whole point is to avoid exactly that.
3. Zero playing time settles, it does not excuse. A player who got hurt and
   scored nothing produces realized=0.0 and usually a MISS. That is the
   prediction being wrong about playing time, which is part of what was
   predicted. Only a FAILED LOOKUP (realized=None) is UNSETTLEABLE.
4. The record is append-only in spirit: settlement adds a block, it never
   edits the claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

# total_fp      -- subject's realized TOTAL FP over the window vs a threshold
# fp_margin_vs  -- realized(subject) - realized(comparator) vs a threshold
VALID_METRICS = frozenset({"total_fp", "fp_margin_vs"})
VALID_DIRECTIONS = frozenset({"at_least", "at_most"})

HIT = "HIT"
MISS = "MISS"
PENDING = "PENDING"
UNSETTLEABLE = "UNSETTLEABLE"


@dataclass(frozen=True)
class Prediction:
    """An immutable claim. Frozen so settlement cannot rewrite the target."""

    claim: str
    metric: str
    direction: str
    threshold: float
    window_days: int
    horizon_end: str
    made_by: str = "claude"
    vs_name: Optional[str] = None
    vs_mlbam: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "metric": self.metric,
            "direction": self.direction,
            "threshold": float(self.threshold),
            "window_days": int(self.window_days),
            "horizon_end": self.horizon_end,
            "made_by": self.made_by,
            "vs_name": self.vs_name,
            "vs_mlbam": self.vs_mlbam,
        }


def build_prediction(
    *,
    claim: str,
    metric: str,
    threshold: float,
    window_days: int,
    stated_on: date,
    direction: str = "at_least",
    made_by: str = "claude",
    vs_name: Optional[str] = None,
    vs_mlbam: Optional[int] = None,
) -> Prediction:
    """Construct a claim, refusing anything that could not turn out false."""
    if metric not in VALID_METRICS:
        raise ValueError(f"metric {metric!r} not in {sorted(VALID_METRICS)}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction {direction!r} not in {sorted(VALID_DIRECTIONS)}")
    if not claim or not claim.strip():
        raise ValueError("a prediction needs a stated claim in plain words")
    if window_days < 1:
        raise ValueError(f"window_days must be >= 1, got {window_days}")
    if threshold is None:
        raise ValueError("a prediction without a threshold cannot be wrong")
    if metric == "fp_margin_vs" and not (vs_name or vs_mlbam):
        raise ValueError(
            "fp_margin_vs compares against somebody — pass vs_name/vs_mlbam")
    return Prediction(
        claim=claim.strip(),
        metric=metric,
        direction=direction,
        threshold=float(threshold),
        window_days=int(window_days),
        horizon_end=(stated_on + timedelta(days=int(window_days))).isoformat(),
        made_by=made_by,
        vs_name=vs_name,
        vs_mlbam=(int(vs_mlbam) if vs_mlbam else None),
    )


def is_ripe(pred: dict, today: date) -> bool:
    """True once the horizon has fully elapsed. Never settle before this."""
    return today >= date.fromisoformat(pred["horizon_end"])


def settle_prediction(
    pred: dict,
    *,
    realized: Optional[float],
    comparator_realized: Optional[float] = None,
    n_events: int = 0,
    today: date,
) -> dict:
    """Resolve a claim to HIT / MISS / PENDING / UNSETTLEABLE.

    `realized` is the subject's total FP over the window; None means the
    lookup failed, which is the ONLY thing that blocks settlement. A real
    0.0 settles — see rule 3 in the module docstring.
    """
    if not is_ripe(pred, today):
        return {"status": PENDING, "settled_on": None,
                "note": f"horizon {pred['horizon_end']} not reached"}

    if realized is None:
        return {"status": UNSETTLEABLE, "settled_on": today.isoformat(),
                "note": "no gamelog for the subject — lookup failed"}

    metric = pred["metric"]
    if metric == "fp_margin_vs":
        if comparator_realized is None:
            return {"status": UNSETTLEABLE, "settled_on": today.isoformat(),
                    "note": "no gamelog for the comparator — lookup failed"}
        observed = float(realized) - float(comparator_realized)
    else:
        observed = float(realized)

    threshold = float(pred["threshold"])
    if pred["direction"] == "at_least":
        hit = observed >= threshold
        margin = observed - threshold
    else:
        hit = observed <= threshold
        margin = threshold - observed

    return {
        "status": HIT if hit else MISS,
        "observed": round(observed, 2),
        "threshold": threshold,
        "margin": round(margin, 2),
        "realized": round(float(realized), 2),
        "comparator_realized": (None if comparator_realized is None
                                else round(float(comparator_realized), 2)),
        "n_events": int(n_events),
        "settled_on": today.isoformat(),
    }


def score_book(settlements: list[dict]) -> dict[str, Any]:
    """Aggregate a book of settled predictions.

    Reports the PENDING and UNSETTLEABLE counts alongside the hit rate rather
    than quietly dropping them: a book that is mostly unresolved has no hit
    rate worth quoting, and hiding that is how a scorecard flatters itself.
    """
    resolved = [s for s in settlements if s.get("status") in (HIT, MISS)]
    n_hit = sum(1 for s in resolved if s["status"] == HIT)
    return {
        "n_total": len(settlements),
        "n_resolved": len(resolved),
        "n_pending": sum(1 for s in settlements if s.get("status") == PENDING),
        "n_unsettleable": sum(1 for s in settlements
                              if s.get("status") == UNSETTLEABLE),
        "n_hit": n_hit,
        "hit_rate": (n_hit / len(resolved)) if resolved else None,
        "mean_margin": (sum(s.get("margin", 0.0) for s in resolved) / len(resolved)
                        if resolved else None),
    }
