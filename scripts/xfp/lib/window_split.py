"""window_split — compare a player across two windows without fooling yourself.

WHY THIS EXISTS
On 2026-08-03 the question was "Teo has 3 HR in 5 games, is he waking up?" The
five-game window held 19 PA; HR rate needs 275 PA before it carries any forward
signal, so the streak was not weak evidence — it was *no* evidence. Meanwhile
the metrics that ARE readable at that scale (bat speed at 50 swings, K% at 50
PA, hard-hit at 50 BIP) said something quite different, and one of them only
said it once the LEAGUE baseline was subtracted.

Three disciplines, all of them easy to lose in prose and therefore encoded here:

1. **Gate every metric on its own denominator.** A number below its minimum is
   not reported. `plv_clone.stabilization` owns the thresholds; this module
   never invents one.
2. **A LEVEL and a CHANGE are different claims.** Reading the current window
   needs the after-window to clear. Reading the delta needs BOTH to clear.
3. **Name the unreadable metrics out loud.** Silently dropping them reads as
   "we checked and found nothing" — the same failure mode that made a quiet
   week look like a closer keeping his job in lib/closer_watch.

Plus the finding that motivated the relative fields: a raw cross-season delta
is biased whenever the league baseline drifts. Teo's bat speed fell 71.39 ->
70.47 (-0.92, unremarkable) while the league rose 69.68 -> 70.14, so his edge
went +1.71 -> +0.33 — a -1.38 relative move, three times the raw read.

RULE 13: this is a measurement/description layer. It never moves rh3/rp3/rprs2.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from plv_clone import stabilization as stab
from plv_clone.stabilization import UnknownMetric  # noqa: F401  (re-export)

# Which direction is GOOD for the player, per side. A naive sign test would
# read Teo's 8.9-point strikeout-rate DROP as a regression.
_LOWER_IS_BETTER = {
    "H": frozenset({"k_pct", "whiff", "swstr", "chase"}),
    "SP": frozenset({"woba_agn", "hard_hit", "barrel", "hr_rate", "bb_pct"}),
    "RP": frozenset({"woba_agn", "bb_pct"}),
}


@dataclass(frozen=True)
class MetricRead:
    """One metric, two windows, and an honest account of what may be said."""

    metric: str
    side: str
    before: Optional[float]
    after: Optional[float]
    before_denom: float
    after_denom: float
    minimum: int
    unit: str
    level_readable: bool
    delta_readable: bool
    delta: Optional[float]
    rel_before: Optional[float] = None
    rel_after: Optional[float] = None
    rel_delta: Optional[float] = None
    never_stabilizes: bool = False
    directional_only: bool = False
    note: str = ""

    @property
    def direction(self) -> str:
        """'better' / 'worse' / 'flat' / 'unknown' — polarity-aware."""
        if not self.delta_readable or self.delta is None:
            return "unknown"
        d = self.rel_delta if self.rel_delta is not None else self.delta
        if d == 0:
            return "flat"
        good_when_down = self.metric in _LOWER_IS_BETTER.get(self.side, frozenset())
        improved = (d < 0) if good_when_down else (d > 0)
        return "better" if improved else "worse"


@dataclass
class SplitSummary:
    improved: list = field(default_factory=list)
    worsened: list = field(default_factory=list)
    unreadable: list = field(default_factory=list)

    @property
    def net_readable(self) -> int:
        return len(self.improved) - len(self.worsened)

    @property
    def headline(self) -> str:
        if not self.improved and not self.worsened:
            return ("NOTHING READABLE — every metric is below its minimum in "
                    "this window; the window is too short to say anything")
        n = self.net_readable
        if n > 0:
            return f"READABLE METRICS IMPROVED ({len(self.improved)} up / {len(self.worsened)} down)"
        if n < 0:
            return f"READABLE METRICS WORSE ({len(self.improved)} up / {len(self.worsened)} down)"
        return f"MIXED ({len(self.improved)} up / {len(self.worsened)} down)"


def split_read(metric: str, side: str = "H", before=None, before_denom=0,
               after=None, after_denom=0, *,
               league_before: Optional[float] = None,
               league_after: Optional[float] = None) -> MetricRead:
    """Gate one metric across two windows. Pure; the whole point of the module.

    Raises :class:`UnknownMetric` for an unregistered metric — a hand-picked
    threshold is precisely the failure this repo keeps repeating, so inventing
    one here is not an option. A metric that NEVER stabilizes in-window comes
    back flagged rather than raising, so one bad column cannot take down a card.
    """
    never = metric in stab.NEVER_STABILIZES.get(side, frozenset())
    note = ""
    if never:
        # minimum() raises ValueError for these by design; keep its wording.
        try:
            stab.minimum(metric, side)
        except ValueError as exc:
            note = str(exc)
        mn, unit = 0, "n/a"
    else:
        mn, unit = stab.minimum(metric, side)   # UnknownMetric propagates

    level_ok = (not never) and stab.is_sufficient(after_denom, metric, side)
    delta_ok = level_ok and stab.is_sufficient(before_denom, metric, side)

    delta = None
    if delta_ok and before is not None and after is not None:
        delta = float(after) - float(before)

    rel_before = rel_after = rel_delta = None
    if league_before is not None and before is not None:
        rel_before = float(before) - float(league_before)
    if league_after is not None and after is not None:
        rel_after = float(after) - float(league_after)
    if rel_before is not None and rel_after is not None and delta_ok:
        rel_delta = rel_after - rel_before

    return MetricRead(
        metric=metric, side=side, before=before, after=after,
        before_denom=float(before_denom or 0), after_denom=float(after_denom or 0),
        minimum=mn, unit=unit,
        level_readable=level_ok, delta_readable=delta_ok, delta=delta,
        rel_before=rel_before, rel_after=rel_after, rel_delta=rel_delta,
        never_stabilizes=never,
        directional_only=metric in stab.NEVER_HIGH_CONFIDENCE.get(side, frozenset()),
        note=note,
    )


def summarize(reads: Sequence[MetricRead]) -> SplitSummary:
    """Bucket reads into improved / worsened / unreadable.

    Every input lands in exactly one bucket — an unreadable metric is REPORTED
    as unreadable, never dropped. Absence of a row is indistinguishable from
    absence of an effect, and that ambiguity is how a short window gets to
    masquerade as a clean bill of health.
    """
    s = SplitSummary()
    for r in reads:
        d = r.direction
        if d == "better":
            s.improved.append(r)
        elif d == "worse":
            s.worsened.append(r)
        elif d == "flat":
            continue
        else:
            s.unreadable.append(r)
    return s


def fp_per_pa_from_k_delta(k_pct_before: float, k_pct_after: float) -> float:
    """BrownU subtracts exactly 1 FP per strikeout, so a K%-point is 0.01 fp/PA.

    This is the bridge from "his K rate improved" to "and it is worth this
    much", which is what let the Teo read answer the only question that
    mattered: does the improvement close the gap to the alternative?
    """
    return (float(k_pct_before) - float(k_pct_after)) / 100.0


def closes_gap_fraction(gain_fp_per_pa: float, gap_fp_per_pa: float) -> float:
    """Fraction of a rate gap the gain would close. NaN on a zero gap.

    Deliberately returns the fraction rather than a verdict — 43% of the way
    is a fact; "not enough" is a judgement that belongs to the caller with the
    rest of the evidence in front of it.
    """
    if not gap_fp_per_pa:
        return float("nan")
    return float(gain_fp_per_pa) / float(gap_fp_per_pa)


def render(reads: Sequence[MetricRead], *, before_label="BEFORE",
           after_label="AFTER") -> str:
    """Fixed-width table. Unreadable rows keep their denominators visible so a
    reader can see HOW short the window was, not merely that it was short."""
    if not reads:
        return "(no metrics)"
    head = (f"{'metric':<12} {before_label:>9} {after_label:>9} {'delta':>8} "
            f"{'n(after)':>9} {'min':>6}  status")
    lines = [head, "-" * len(head)]
    for r in reads:
        d = f"{r.delta:+.1f}" if r.delta is not None else "  -  "
        b = f"{r.before:.1f}" if r.before is not None else "  -  "
        a = f"{r.after:.1f}" if r.after is not None else "  -  "
        if r.never_stabilizes:
            status = "NEVER STABILIZES in-window"
        elif not r.level_readable:
            status = f"UNDER ({r.after_denom:.0f} of {r.minimum} {r.unit})"
        elif not r.delta_readable:
            status = "level only (baseline undersized)"
        else:
            status = r.direction.upper()
            if r.directional_only:
                status += " (directional only)"
        lines.append(f"{r.metric:<12} {b:>9} {a:>9} {d:>8} "
                     f"{r.after_denom:>9.0f} {r.minimum:>6}  {status}")
        if r.rel_delta is not None:
            lines.append(f"{'  vs league':<12} {r.rel_before:>+9.2f} "
                         f"{r.rel_after:>+9.2f} {r.rel_delta:>+8.2f} "
                         f"{'':>9} {'':>6}  league-adjusted")
    return "\n".join(lines)


__all__ = ['MetricRead', 'SplitSummary', 'UnknownMetric', 'split_read',
           'summarize', 'fp_per_pa_from_k_delta', 'closes_gap_fraction',
           'render']
