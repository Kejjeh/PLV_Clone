"""counterfactual — grade the CHOICE, not the projection (C6).

THE DIFFERENT QUESTION
----------------------
``settler.settle_decision`` asks *was the projection right?* — residual of
realized FP/unit against what we projected. Real question, and the verdict
scorecard already answers it.

This module asks the question that actually decides a season: *was the CHOICE
right?* Josh executed one move out of a surface of alternatives, and the only
honest grade is

    fp_gained = realized_total(chosen) - realized_total(rejected)

over a window common to both. A projection can be beautifully calibrated while
every decision made from it is the wrong one, and vice versa — so both blocks
live side by side on a record rather than one replacing the other.

WHY TOTAL FP, NOT FP PER UNIT
-----------------------------
Deliberate, and it is the key design decision here. The existing settler measures
per-unit rate because it is grading a RATE projection. A decision is different:
**playing time is part of what you chose.** If the rejected alternative got hurt,
was demoted, or simply sat, that is not missing data — that is the decision
paying off. Per-unit accounting would either discard those cases as
"unsettleable" or, worse, credit a rejected player for being efficient across
four plate appearances. Total FP over the window captures availability, which is
most of what an add/drop decision is actually about.

Consequence, stated plainly: a zero-appearance rejected player yields
``rejected_total_fp = 0.0``, which is informative, NOT a missing value. Only the
CHOSEN side being absent is genuinely uninformative, and that is reported as
``low_sample`` rather than silently scored.

THRESHOLDS
----------
A wash band, so ordinary noise is not graded as skill. Set in total-FP units by
scaling the settler's per-unit threshold by its min_events, which keeps the two
modules' notions of "meaningful" consistent rather than inventing a second scale:

    H  : 0.02 FP/PA     x 30 PA    ->  ~0.6  ... widened to 10 FP / 21d
    SP : 1.0  FP/start  x 5 starts ->  ~5    ... widened to  8 FP / 35d
    RP : 0.5  FP/g      x 10 apps  ->  ~5    ...              5 FP / 35d

The widening is because a DECISION carries more irreducible noise than a rate
projection: one blow-up start or one hot week swings a paired comparison far more
than it swings a 35-day rate. A tight band would mostly grade variance.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Optional

from plv_clone.decisions.logger import DecisionRecord, is_pairable
from plv_clone.decisions.settler import SETTLEMENT_WINDOWS

# Total-FP wash bands (see module docstring for the derivation).
COUNTERFACTUAL_THRESHOLDS = {
    "H": 10.0,    # over 21 days
    "SP": 8.0,    # over 35 days
    "RP": 5.0,    # over 35 days
}

RIGHT_CALL = "RIGHT_CALL"
WRONG_CALL = "WRONG_CALL"
WASH = "WASH"
UNSETTLEABLE = "UNSETTLEABLE"

# Local wall-clock hour at or after which a move can no longer be assumed to
# have reached the day's slate (audit T22, 2026-08-01). 13:00 is the earliest
# ROUTINE MLB first pitch; a move stamped before it is AHEAD OF the routine
# slate, though not literally every game (holiday 11:35s, London starts, and
# doubleheader openers exist — review 2026-08-01). The residual error is a
# rare day-0 game credited to both sides symmetrically, well inside the wash
# band.
#
# TIMEZONE, stated rather than buried: ``executed_at`` is built by
# ``scripts/xfp/reconcile_decisions.py`` as
# ``datetime.fromtimestamp(int(ts)/1000.0)`` — naive LOCAL wall-clock, neither
# tz-aware nor forced to ET. The cutoff is therefore evaluated in whatever
# timezone the machine that reconciled the transaction was in; for this league
# that is Eastern, which is also the timezone the cutoff hour is chosen for.
FIRST_PITCH_CUTOFF_HOUR = 13


def effective_start(stamp) -> Optional[date]:
    """First day a move stamped ``stamp`` could actually have affected a lineup.

    The window used to start on ``str(stamp)[:10]``, and ``_games_in_window``
    filters INCLUSIVELY on both ends, so an evening move credited BOTH players a
    day-0 game it could not possibly have influenced — noise added symmetrically
    to a paired comparison whose wash band is only 10 FP for a hitter.

    A stamp carrying no time is left on its own day: absence of a clock reading
    is not evidence of lateness, and ``snapshot_date`` (the fallback) means the
    surface existed that morning.

    The ``strip()`` is a DELIBERATE, disclosed widening (review 2026-08-01): a
    whitespace-padded but otherwise valid stamp used to fail parsing and leave
    its record unsettleable forever. Trimming admits it. This settles MORE
    records; it never changes an already-settled value.
    """
    text = str(stamp).strip()
    try:
        day = date.fromisoformat(text[:10])
    except ValueError:
        return None
    if len(text) <= 10:
        return day
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return day
    return day if moment.hour < FIRST_PITCH_CUTOFF_HOUR else day + timedelta(days=1)


def window_for(record: DecisionRecord) -> Optional[tuple[date, date]]:
    """The common measurement window: first effective day + bucket days.

    Both sides are measured over the SAME interval — that is what makes the
    comparison fair, and it is why the window is derived from the record rather
    than from either player's own game availability. Applying the effective-start
    shift HERE, once, is what keeps the two legs symmetric; the end offset stays
    relative to the start so window LENGTH is unchanged.
    """
    spec = SETTLEMENT_WINDOWS.get(record.bucket)
    if spec is None:
        return None
    stamp = record.executed_at or record.snapshot_date
    if not stamp:
        return None
    start = effective_start(stamp)
    if start is None:
        return None
    return start, start + timedelta(days=int(spec["days"]))


def is_ripe(record: DecisionRecord, *, today: date) -> bool:
    """True once the window has fully elapsed.

    Grading early would systematically favour whichever side happened to play
    first, so this is a hard gate rather than a confidence adjustment.
    """
    win = window_for(record)
    return bool(win and today >= win[1])


def classify(fp_gained: float, bucket: str) -> str:
    thr = COUNTERFACTUAL_THRESHOLDS.get(bucket)
    if thr is None:
        return UNSETTLEABLE
    if fp_gained > thr:
        return RIGHT_CALL
    if fp_gained < -thr:
        return WRONG_CALL
    return WASH


def settle_counterfactual(
    record: DecisionRecord,
    *,
    today: date,
    chosen_total_fp: Optional[float],
    rejected_total_fp: Optional[float],
    n_events_chosen: int = 0,
    n_events_rejected: int = 0,
) -> DecisionRecord:
    """Attach ``counterfactual_settlement`` to *record*. Pure — returns a copy.

    Totals are supplied by the caller (the driver owns the network); this stays a
    pure function so the taxonomy is unit-testable without touching the MLB API.

    ``rejected_total_fp = 0.0`` with zero events is a VALID, informative outcome
    (the alternative was hurt, demoted, or benched — the decision paying off).
    Only a missing CHOSEN side is uninformative.
    """
    if not is_pairable(record):
        return record

    win = window_for(record)
    if win is None:
        return record
    start, end = win
    spec = SETTLEMENT_WINDOWS.get(record.bucket, {})

    if not is_ripe(record, today=today):
        return record

    if chosen_total_fp is None:
        # The chosen player produced no measurable events at all. Recorded rather
        # than scored: grading this as a WRONG_CALL would confuse "he did not
        # play" with "the alternative outperformed".
        block = {
            "classification": UNSETTLEABLE,
            "reason": "no realized events for the chosen player in the window",
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "window_days": int(spec.get("days", 0)),
            "n_events_chosen": int(n_events_chosen),
            "n_events_rejected": int(n_events_rejected),
            "low_sample": True,
        }
        return replace(record, counterfactual_settlement=block,
                       settled_at=datetime.now().isoformat(timespec="seconds"))

    rej = 0.0 if rejected_total_fp is None else float(rejected_total_fp)
    gained = float(chosen_total_fp) - rej
    thr = COUNTERFACTUAL_THRESHOLDS.get(record.bucket)
    min_ev = int(spec.get("min_events", 0) or 0)

    block = {
        "chosen_total_fp": round(float(chosen_total_fp), 2),
        "rejected_total_fp": round(rej, 2),
        "fp_gained": round(gained, 2),
        "n_events_chosen": int(n_events_chosen),
        "n_events_rejected": int(n_events_rejected),
        "event_unit": spec.get("event_unit"),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "window_days": int(spec.get("days", 0)),
        "threshold": thr,
        "classification": classify(gained, record.bucket),
        # Flag rather than gate: a thin sample still carries information about the
        # decision (especially when the thinness IS the outcome), but a reader
        # should weight it less.
        "low_sample": bool(n_events_chosen < min_ev or n_events_rejected < min_ev),
        "rejected_never_played": bool(n_events_rejected == 0),
        "dpwin_gap": (record.counterfactual or {}).get("dpwin_gap"),
    }
    return replace(record, counterfactual_settlement=block,
                   settled_at=record.settled_at
                   or datetime.now().isoformat(timespec="seconds"))


def summarize(records: list[DecisionRecord]) -> dict:
    """Aggregate paired settlements into a regret summary.

    Reports counts, mean/median fp_gained and the cumulative total per bucket —
    "the process gained or lost X FP versus the road not taken" is the single
    number that says whether the whole apparatus is earning anything.
    """
    out: dict = {"by_bucket": {}, "total_fp_gained": 0.0, "n_settled": 0,
                 "n_low_sample": 0}
    for r in records:
        blk = getattr(r, "counterfactual_settlement", None) or {}
        if not blk or blk.get("fp_gained") is None:
            continue
        b = r.bucket
        e = out["by_bucket"].setdefault(
            b, {"n": 0, RIGHT_CALL: 0, WRONG_CALL: 0, WASH: 0,
                "fp_gained_total": 0.0, "fp_gained": []})
        e["n"] += 1
        cls = blk.get("classification")
        if cls in (RIGHT_CALL, WRONG_CALL, WASH):
            e[cls] += 1
        g = float(blk["fp_gained"])
        e["fp_gained_total"] += g
        e["fp_gained"].append(g)
        out["total_fp_gained"] += g
        out["n_settled"] += 1
        if blk.get("low_sample"):
            out["n_low_sample"] += 1

    for b, e in out["by_bucket"].items():
        vals = sorted(e.pop("fp_gained"))
        e["fp_gained_mean"] = round(sum(vals) / len(vals), 2) if vals else None
        e["fp_gained_median"] = (round(vals[len(vals) // 2], 2) if vals else None)
        e["fp_gained_total"] = round(e["fp_gained_total"], 2)
        e["hit_rate"] = (round(e[RIGHT_CALL] / e["n"], 3) if e["n"] else None)
    out["total_fp_gained"] = round(out["total_fp_gained"], 2)
    return out


def dpwin_resolution(records: list[DecisionRecord], *, min_n: int = 30) -> dict:
    """Does a bigger dpwin_gap actually predict a better realized outcome?

    The honest test of whether the Delta-P(win) surface has RESOLUTION rather than
    merely being self-consistent. Bins settled pairs by dpwin_gap tercile and
    checks P(fp_gained > 0) is monotone across them.

    Under-powered below ``min_n`` and says so — the repo's POWER_N idiom. Calling
    a 6-sample trend "monotone" would be exactly the over-claim the validation
    protocol exists to prevent.
    """
    pairs = []
    for r in records:
        blk = getattr(r, "counterfactual_settlement", None) or {}
        gap = blk.get("dpwin_gap")
        g = blk.get("fp_gained")
        if gap is None or g is None:
            continue
        pairs.append((float(gap), float(g)))
    n = len(pairs)
    if n < min_n:
        return {"status": "EARLY_READ", "n": n, "min_n": min_n,
                "note": (f"{n} settled pairs; need {min_n} before a monotonicity "
                         f"claim is meaningful")}
    pairs.sort(key=lambda t: t[0])
    k = n // 3
    bins = [pairs[:k], pairs[k:2 * k], pairs[2 * k:]]
    rates = [round(sum(1 for _, g in b if g > 0) / len(b), 3) for b in bins if b]
    return {
        "status": "OK", "n": n,
        "tercile_win_rates": rates,
        "monotone": all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1)),
        "note": ("P(fp_gained>0) by ascending dpwin_gap tercile; monotone means "
                 "the dpwin surface has real resolution"),
    }


__all__ = [
    "COUNTERFACTUAL_THRESHOLDS", "RIGHT_CALL", "WRONG_CALL", "WASH",
    "UNSETTLEABLE", "window_for", "is_ripe", "classify",
    "settle_counterfactual", "summarize", "dpwin_resolution",
]
