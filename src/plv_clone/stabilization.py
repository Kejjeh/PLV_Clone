"""
Empirical sample-size minimums for metric stabilization.

**These numbers are measured on our own data, not borrowed from literature.**
Every value below is the sample size at which a metric's *forward* reliability
— r(metric measured over the first N units, metric over the rest of the season)
— crosses 0.50, rounded up to the nearest 25. Below the minimum, a metric
carries no decision-grade information about what comes next, and the honest
render is a blank cell rather than a number that looks real.

Two studies, both pre-registered, both run 2026-07-29:

- **Hitters** — `scripts/xfp/validate_cutoff_stabilization.py`, 91,628
  batter-snapshots 2018–2026 (ex 2020).
  Memo: `data/research/validation_runs/inseason_delta_grid_2026-07-29.md` (Part A).
- **Pitchers** — `scripts/xfp/validate_cutoff_stabilization_pitchers.py`,
  26,958 SP + 42,978 RP snapshots, same window and method.
  Memo: `data/research/validation_runs/pitcher_cutoff_stabilization_2026-07-29.md`.

What the studies changed about prior practice:

- Swing-decision metrics stabilize at **150** denominator units, not the 300
  we had been hand-picking — the old gate was 2x conservative.
- Hitter **BB% needs 175 PA** (we had been using 60). A three-week walk-rate
  read is noise by construction; BB% never reaches r=0.70 inside a season.
- Hitter **HR-rate needs 275 PA** and **ISO 275 AB** — in-season power deltas
  are effectively unmeasurable at window scale.
- **Velocity is the king pitcher metric**: r≈0.90 in the very first bucket
  (~150 pitches ≈ 1–2 starts). An in-season velo move is trustworthy at once.
- **Bat speed is the hitter equivalent, and it is now measured** (2026-07-29,
  `validate_bat_speed_stabilization.py` over `bat_speed_daily.parquet`): forward
  r never drops below +0.70 at ANY sample size in the curve, clearing both
  crossings by 25-30 swings — roughly one week of playing time. It graduated out
  of LITERATURE_ONLY into HITTER_MINS.
  **But read the LEVEL, not the trajectory.** The companion study
  (`validate_bat_speed_delta.py`) rejected the in-season bat-speed DELTA against
  rh3 — 0 of 6 pre-registered cells survived BH-FDR, and the best cell's full
  22-feature Rule-9 integration came to +0.0035 against the +0.005 bar. A
  well-measured quantity can still carry no forward information beyond the level
  that already contains it; those are different questions and this module only
  answers the first.
- **Pitcher chase, pitcher BB%, and contact-quality-AGAINST (hard-hit, barrel,
  HR-rate) NEVER stabilize in-window.** Mid-season "his command improved" or
  "he's been HR-prone lately" reads are unsupportable — see NEVER_STABILIZES.
  (The /sp-board HR/9 lens survives only because it compares to CAREER, not
  to a window.)

Scope note: these are MEASUREMENT gates — "is this number knowable yet". They
are distinct from the MODEL-UNIVERSE filters (which rows a projection model
trains and projects on); those live on the model modules and are re-exported
at the bottom of this file for convenience, never redefined here.

Related: `plv_clone.utils.season_stage` (stage-aware workflow thresholds),
CLAUDE.md gotcha #12, `docs/stabilization_minimums.md`.
"""

from __future__ import annotations

from typing import Iterable, Literal, Optional

import math

Side = Literal["H", "SP", "RP"]

# ── Denominator units ────────────────────────────────────────────────────────
# Each minimum is expressed in the metric's OWN denominator. Passing a PA count
# where the metric wants out-of-zone pitches is the classic misuse, so `gate()`
# takes the unit explicitly and `DENOM_OF` records the expected one.
PITCHES = "pitches"          # all pitches seen/thrown
OOZ_PITCHES = "ooz_pitches"  # pitches outside the strike zone
IZ_PITCHES = "iz_pitches"    # pitches inside the strike zone
SWINGS = "swings"
PA = "pa"
TBF = "tbf"
BIP = "bip"                  # batted-ball events
AB = "ab"


# ── HITTER minimums (forward r >= 0.50) ──────────────────────────────────────
# From validate_cutoff_stabilization.py. r=0.70 crossings in the memo; the
# never-reaches-0.70 set is called out in NEVER_HIGH_CONFIDENCE below.
HITTER_MINS: dict[str, tuple[int, str]] = {
    # Bat speed — MEASURED 2026-07-29 (promoted out of LITERATURE_ONLY the same
    # day the daily store made it measurable). It is the most reliable in-window
    # hitter metric we have: forward r = +0.736 @ 27 swings, +0.849 @ 32,
    # +0.879 @ 52, +0.905 @ 87, +0.950 @ 612 — and NO bucket anywhere in the
    # curve falls below +0.70. Both the r>=0.50 and r>=0.70 crossings clear at or
    # below 25-30 swings; the crossing could not be resolved lower only because
    # fewer than 200 player-seasons exist below 25 swings under a weekly
    # snapshot stride. 50 is the same mechanical ceil-25 rule every other entry
    # uses (ceil(27/25)*25), so it is deliberately conservative.
    # fast_swing_rate and p90 bat speed stabilize on the same curve.
    "bat_speed":   (50, SWINGS),
    "chase":       (150, OOZ_PITCHES),
    "zswing":      (150, IZ_PITCHES),
    "z_contact":   (150, IZ_PITCHES),
    "whiff":       (150, SWINGS),
    "swstr":       (150, PITCHES),
    "k_pct":       (50,  PA),
    "hard_hit":    (50,  BIP),
    "barrel":      (50,  BIP),
    "bb_pct":      (175, PA),
    "xwoba_ppa":   (225, PA),
    "iso":         (275, AB),
    "hr_ppa":      (275, PA),
}

# ── STARTING PITCHER minimums ────────────────────────────────────────────────
SP_MINS: dict[str, tuple[int, str]] = {
    "velo":        (150, PITCHES),   # r ~= 0.90 at the first bucket
    "whiff":       (150, SWINGS),
    "swstr":       (175, PITCHES),
    "zswing":      (275, IZ_PITCHES),
    "gb":          (50,  BIP),
    "k_pct":       (100, TBF),       # ~4 starts
    "csw":         (425, PITCHES),
    "woba_agn":    (525, TBF),       # ~a full season
}

# ── RELIEF PITCHER minimums ──────────────────────────────────────────────────
RP_MINS: dict[str, tuple[int, str]] = {
    "velo":        (150, PITCHES),   # r ~= 0.93 at the first bucket
    "whiff":       (150, SWINGS),
    "zswing":      (150, IZ_PITCHES),
    "swstr":       (200, PITCHES),
    "k_pct":       (125, TBF),
    "csw":         (425, PITCHES),
}

MINS_BY_SIDE: dict[str, dict[str, tuple[int, str]]] = {
    "H": HITTER_MINS,
    "SP": SP_MINS,
    "RP": RP_MINS,
}

# ── Metrics that NEVER stabilize in-window ───────────────────────────────────
# Forward r never crosses 0.50 at ANY in-season sample size. Reading these off
# a window is not "low confidence" — it is unsupported. Route the question to a
# season-level or career comparison instead.
NEVER_STABILIZES: dict[str, frozenset[str]] = {
    "H": frozenset(),
    "SP": frozenset({"chase", "bb_pct", "hard_hit", "barrel", "hr_rate"}),
    "RP": frozenset({"chase", "bb_pct", "woba_agn"}),
}

# ── Metrics that stabilize but never reach HIGH confidence (r=0.70) in-window ─
# Usable at the minimums above for a directional read; never the load-bearing
# evidence in a drop/add decision on its own.
NEVER_HIGH_CONFIDENCE: dict[str, frozenset[str]] = {
    "H": frozenset({"bb_pct", "xwoba_ppa", "iso", "hr_ppa"}),
    "SP": frozenset({"zswing", "csw", "k_pct", "gb", "woba_agn"}),
    "RP": frozenset({"zswing", "whiff", "csw", "k_pct"}),
}

# ── Not yet re-derived on our data ───────────────────────────────────────────
# Literature values (Savant bat-tracking guidance), NOT ours. Flagged so a
# borrowed number is never mistaken for a measured one.
#
# bat_speed GRADUATED from this table on 2026-07-29 — it is now a MEASURED entry
# in HITTER_MINS. Its old literature value of 30 swings was CONFIRMED by the
# measurement (30 sits at r~=0.74-0.85, comfortably above both the 0.50 decision
# floor and the 0.70 high-confidence bar).
#
# swing_length remains literature-only: the gf bridge carries batSpeed but NOT
# swing_length, so ~1% of 2026 batter-days have no swing_length at all and the
# canonical pull lags 1-2 days. Not enough coverage to derive a crossing.
LITERATURE_ONLY: dict[str, tuple[int, str]] = {
    "swing_length": (30, SWINGS),
}


class UnknownMetric(KeyError):
    """Raised when a metric has no registered minimum for the given side."""


def minimum(metric: str, side: Side = "H") -> tuple[int, str]:
    """Return ``(min_denominator, unit)`` for *metric* on *side*.

    Raises :class:`UnknownMetric` when the metric is unregistered, and
    ``ValueError`` when it is in ``NEVER_STABILIZES`` for that side — a caller
    asking for a gate on an unstabilizable metric has a design bug, not a
    threshold problem.
    """
    if metric in NEVER_STABILIZES.get(side, frozenset()):
        raise ValueError(
            f"{metric!r} never stabilizes in-window for {side} — there is no "
            f"sample size that makes a window read valid. Compare to the "
            f"season or career level instead (see NEVER_STABILIZES)."
        )
    table = MINS_BY_SIDE.get(side)
    if table is None:
        raise UnknownMetric(f"unknown side {side!r} (expected H / SP / RP)")
    if metric in table:
        return table[metric]
    if metric in LITERATURE_ONLY:
        return LITERATURE_ONLY[metric]
    raise UnknownMetric(
        f"{metric!r} has no registered minimum for {side}. Add it to "
        f"stabilization.py only with a measured forward-r crossing — never a "
        f"hand-picked number."
    )


def is_sufficient(denom, metric: str, side: Side = "H") -> bool:
    """True when *denom* meets the empirical minimum for *metric*/*side*."""
    if denom is None:
        return False
    try:
        d = float(denom)
    except (TypeError, ValueError):
        return False
    if math.isnan(d):
        return False
    return d >= minimum(metric, side)[0]


def gate(value, denom, metric: str, side: Side = "H", *, fill=float("nan")):
    """Return *value* when *denom* clears the minimum, else *fill* (NaN).

    The one-line idiom for every board/lens column:

        row["chase"] = gate(chase_pct, ooz_pitches, "chase", "H")

    A blank cell is the honest render for an undersized sample; a number is a
    claim. Prefer this over an inline ``>=`` so the threshold stays in one place.
    """
    return value if is_sufficient(denom, metric, side) else fill


def insufficient(metrics: Iterable[str], denoms: dict[str, float],
                 side: Side = "H") -> list[str]:
    """Names from *metrics* whose denominator in *denoms* is below minimum.

    Useful for a one-line caveat under a board: "not yet knowable: bb_pct, iso".
    """
    out = []
    for m in metrics:
        if m in NEVER_STABILIZES.get(side, frozenset()):
            out.append(m)
            continue
        if not is_sufficient(denoms.get(m), m, side):
            out.append(m)
    return out


def describe(metric: str, side: Side = "H") -> str:
    """Human-readable provenance line for a metric's gate — for board footers."""
    if metric in NEVER_STABILIZES.get(side, frozenset()):
        return f"{metric} ({side}): never stabilizes in-window — season/career only"
    n, unit = minimum(metric, side)
    note = ""
    if metric in LITERATURE_ONLY:
        note = " [literature value, not yet re-derived on our data]"
    elif metric in NEVER_HIGH_CONFIDENCE.get(side, frozenset()):
        note = " [directional only — never reaches r=0.70 in-window]"
    return f"{metric} ({side}): >= {n} {unit}{note}"


# ── MODEL-UNIVERSE filters (re-exported, NOT redefined) ──────────────────────
# These answer a different question — "which rows does the model train and
# project on" — and are owned by the model modules. They are imported here so
# downstream scripts stop copy-pasting the literals (the audit found 7+ files
# with verbatim duplicates). Import from here or from the model; never retype.
#
#   rh3   EVAL_PA_MIN / ROS_PA_MIN
#   rp3   EVAL_GS_MIN / ROS_GS_MIN
#   rprs2 EVAL_G_MIN
#
# Wrapped in try/except so this module stays importable in contexts where the
# model bundles or their deps are unavailable (e.g. a bare test env).
try:  # pragma: no cover - import plumbing
    from plv_clone.models.xfp.rh3 import (  # noqa: F401
        EVAL_PA_MIN, ROS_PA_MIN,
    )
    from plv_clone.models.xfp.rp3 import (  # noqa: F401
        EVAL_GS_MIN, ROS_GS_MIN,
    )
    _MODEL_FILTERS_AVAILABLE = True
except Exception:  # pragma: no cover
    EVAL_PA_MIN = ROS_PA_MIN = EVAL_GS_MIN = ROS_GS_MIN = None
    _MODEL_FILTERS_AVAILABLE = False


__all__ = [
    "HITTER_MINS", "SP_MINS", "RP_MINS", "MINS_BY_SIDE",
    "NEVER_STABILIZES", "NEVER_HIGH_CONFIDENCE", "LITERATURE_ONLY",
    "minimum", "is_sufficient", "gate", "insufficient", "describe",
    "UnknownMetric",
    "PITCHES", "OOZ_PITCHES", "IZ_PITCHES", "SWINGS", "PA", "TBF", "BIP", "AB",
    "EVAL_PA_MIN", "ROS_PA_MIN", "EVAL_GS_MIN", "ROS_GS_MIN",
]
