"""SP cap arithmetic over injected data.

Pure functions over roster + WeekProbables. No remote dependencies — the
MLB Stats API fetch lives in `plv_clone.mlb_stats`. See ADR-0002.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SP_CAP = 10
RP_SLOT_CAP = 4
IL_SLOT_COUNT = 3

# ─────────────────────────────────────────────────────────────────────────────
# Period-aware SP-start cap + window (2026-07-11)
#
# BrownU is nominally a 1-week-per-matchup-period league (cap SP_CAP=10, a single
# Mon–Sun scoring week). A FEW periods break that mold and carry a DIFFERENT cap
# over a MULTI-WEEK span:
#   • the All-Star two-week block (period 15 in 2026: cap 16, Jul 6 → Jul 19,
#     skipping the ASG dead days Jul 13–15);
#   • playoff rounds that span two scoring weeks (matchupPeriods 22→[22,23],
#     23→[24,25] per ESPN settings).
#
# ── THE GENERAL RULE: cap = 10 × (number of scoring weeks in the period) ──────
# BrownU allows 10 SP starts per SCORING WEEK. So the period cap follows the
# period's week count directly:
#   • a 1-week period (every regular week, and playoff ROUND 1 / period 21) → 10
#   • a 2-week period (playoff rounds 2 & 3 / periods 22, 23)               → 20
# The week count is machine-readable from ESPN settings:
#   weeks = len(matchupPeriods[str(period)])   # e.g. 22 -> [24,25] -> 2
# so PLAYOFFS need NO hardcoding — ``sp_cap_for_period(period, weeks=weeks)``
# auto-yields 10 / 20. Callers pass ``weeks`` from ESPN (helper below).
#
# ── THE ONE EXCEPTION: the ASG two-week block (period 15 in 2026) ─────────────
# Period 15 spans 2 CALENDAR weeks (Jul 6–19) but is capped at 16, NOT 20,
# because the All-Star break removes game-days (Jul 13–15). So 10×weeks does NOT
# apply. Worse, ESPN's matchupPeriods maps period 15 -> [15] (a single week-
# index) despite the 2-week span, so the week count is ALSO untrustworthy there.
# Hence period 15 is an EXPLICIT override carrying BOTH the cap (16) AND the true
# date window — and the override takes PRECEDENCE over the 10×weeks formula.
#
# ASYMMETRY (documented on purpose): playoffs = AUTO via 10×weeks; ASG = MANUAL
# override. ESPN does not expose the period cap as one number (only a per-day
# rate, statId 33 limitValue = 10/7), and the ASG game-day loss isn't in the
# week count — so the ASG cap can't be safely auto-derived.
#
# The LIVE per-team banked-start COUNT (statId 33) *is* machine-readable from the
# ESPN matchup endpoint (cumulativeScore.statBySlot["22"].value) — consumers read
# that as the authoritative banked count and cross-check it here.
#
# ── HOW JOSH MAINTAINS THIS ──────────────────────────────────────────────────
# Regular + playoff periods need NO maintenance (10×weeks is automatic). Only add
# an override for a period that breaks 10×weeks — i.e. another ASG-style block
# where the calendar span and the game-day count disagree. Add one entry to EACH
# dict below, keyed by the ESPN matchup-period number:
#   PERIOD_CAP_OVERRIDES[<period>]    = <CAP from ESPN "Game Limits (Cur/Max)">
#   PERIOD_WINDOW_OVERRIDES[<period>] = (date(start), date(end))   # inclusive
# The window end is the last calendar day the period scores (skipped ASG days
# stay inside the span). If you add a cap but forget the window (or vice-versa),
# the leverage engine prints a LOUD warning rather than silently using 10.
PERIOD_CAP_OVERRIDES: dict[int, int] = {
    15: 16,   # 2026 All-Star two-week block (ESPN UI: P 3/16 for Ligers)
}
PERIOD_WINDOW_OVERRIDES: dict[int, tuple[date, date]] = {
    15: (date(2026, 7, 6), date(2026, 7, 19)),   # ASG span (skips Jul 13–15)
}


def weeks_in_period(matchup_periods: dict | None, matchup_period: int | None) -> int:
    """Number of scoring weeks in a matchup period, from ESPN's ``matchupPeriods``
    mapping (``settings.matchup_periods``: {period -> [scoring-week indices]}).
    ``len(matchupPeriods[str(period)])`` — e.g. playoff 22 -> [24, 25] -> 2.
    Falls back to 1 (standard single-week period) when the mapping is missing or
    the period isn't listed. NOTE: the ASG period 15 lists as [15] (1) despite
    its 2-week span — that's why period 15 uses an explicit cap override, not
    this count."""
    if not matchup_periods or matchup_period is None:
        return 1
    entry = matchup_periods.get(str(int(matchup_period)))
    if not entry:
        return 1
    try:
        return max(1, len(entry))
    except TypeError:
        return 1


def sp_cap_for_period(matchup_period: int | None, *, weeks: int = 1,
                      default: int = SP_CAP) -> int:
    """Period-aware SP-start cap.

    Precedence: an explicit ``PERIOD_CAP_OVERRIDES`` entry (the ASG block) wins;
    otherwise the general rule ``default × weeks`` (10 per scoring week). So a
    standard week (``weeks=1``) -> 10, a 2-week playoff round (``weeks=2``) -> 20,
    and period 15 -> 16 regardless of ``weeks``. ``None`` -> ``default × weeks``.

    Callers get ``weeks`` from :func:`weeks_in_period` (ESPN settings). The
    ``weeks=1`` default keeps every existing single-week caller byte-identical."""
    if matchup_period is not None:
        override = PERIOD_CAP_OVERRIDES.get(int(matchup_period))
        if override is not None:
            return override
    return default * max(1, int(weeks))


def period_window(matchup_period: int | None) -> tuple[date, date] | None:
    """(start, end) inclusive calendar span for a multi-week / ASG period, or
    ``None`` for a standard single-week period (the caller then uses its own
    Mon–Sun week — the default-preserving path). ``None`` for an unknown period."""
    if matchup_period is None:
        return None
    return PERIOD_WINDOW_OVERRIDES.get(int(matchup_period))


def is_period_covered(matchup_period: int | None) -> bool:
    """True iff ``matchup_period`` has an EXPLICIT override with BOTH a cap and a
    window (the ASG block). This is NOT the same as "handled": clean multi-week
    playoff rounds are handled by the generic 10×weeks rule + a caller-derived
    window and are intentionally NOT "covered" here. The leverage engine uses
    this only to (a) label the cap source and (b) decide when to warn loudly —
    it warns for a period that LOOKS single-week (weeks==1) yet has already
    scored across >1 week and is not explicitly covered (the ASG-without-override
    trap). A half-specified override (cap xor window) returns False on purpose."""
    if matchup_period is None:
        return False
    p = int(matchup_period)
    return p in PERIOD_CAP_OVERRIDES and p in PERIOD_WINDOW_OVERRIDES

# Empirical rate: starts per active (healthy) SP per scoring week. Owner for what
# was a floating 1.19 literal re-declared under 6 different names across 8+ modules
# (SP_STARTS_WK / HEALTHY_SP_STARTS_PER_WEEK / RATE / inline 1.19) + 4 skills.
# Every cap-projection consumer imports THIS, never re-types it (audit 2026-07-03).
STARTS_PER_SP_PER_WEEK = 1.19

from plv_clone.il_states import IL_STATES_STRICT as IL_STATUSES  # issue #28
# (widened 2026-08-20: SEVEN_DAY_DL/IR/OUT/IL* now also zero an SP's starts)


def projected_starts(n_healthy_sps: int, *, rate: float = STARTS_PER_SP_PER_WEEK) -> float:
    """Expected SP starts this week from ``n_healthy_sps`` active SPs. The single
    owner of the 1.19 projection — forced-drop-planner / sp-week-plan / roster-audit
    / monday-morning / playoff-team-build all call this instead of ``n * 1.19``."""
    return n_healthy_sps * rate


def gap_to_cap(n_healthy_sps: int, *, cap: int = SP_CAP,
               rate: float = STARTS_PER_SP_PER_WEEK) -> float:
    """Signed slack vs the weekly start cap: >0 = under cap (need streamers to fill),
    <0 = over cap (a forced drop is coming). ``gap_to_cap(6) -> +2.86``."""
    return cap - projected_starts(n_healthy_sps, rate=rate)


@dataclass(frozen=True)
class RosterPitcher:
    name: str
    mlbam_id: int | None
    injury_status: str
    position: str


@dataclass(frozen=True)
class WeekProbables:
    starts: dict[tuple[int, date], str] = field(default_factory=dict)
    # Keys that came from MLB's confirmed probable list (not rotation-gap predicted).
    # Use this to distinguish ✓ confirmed from ~ predicted in displays.
    confirmed_keys: frozenset = field(default_factory=frozenset)


@dataclass(frozen=True)
class SPStart:
    pitcher_name: str
    mlbam_id: int
    start_date: date
    opponent_team: str
    projected_fp: float
    counts_toward_cap: bool


def weekly_sp_projection(
    *,
    roster: list[RosterPitcher],
    week_start: date,
    week_end: date,
    rp3: dict[str, float],
    probables: WeekProbables,
    cap: int = SP_CAP,
) -> list[SPStart]:
    matches: list[tuple[RosterPitcher, int, date, str]] = []
    for p in roster:
        if p.injury_status in IL_STATUSES:
            continue
        for (mlbam, day), opp in probables.starts.items():
            if mlbam != p.mlbam_id:
                continue
            if not (week_start <= day <= week_end):
                continue
            matches.append((p, mlbam, day, opp))

    matches.sort(key=lambda m: (m[2], m[0].name))
    return [
        SPStart(
            pitcher_name=p.name,
            mlbam_id=mlbam,
            start_date=day,
            opponent_team=opp,
            projected_fp=rp3.get(p.name, 0.0),
            counts_toward_cap=i < cap,
        )
        for i, (p, mlbam, day, opp) in enumerate(matches)
    ]


def cap_excess_starts(fps: list[float], cap: int = SP_CAP) -> set[int]:
    """Planning cap: which SP starts this week do NOT count toward scoring,
    given each start's projected FP.

    This is the *bench-your-worst* planning view — you start your best ``cap``
    SPs and the rest score zero — used by the matchup and the optimizers. It is
    distinct from :func:`weekly_sp_projection`'s ``counts_toward_cap``, which is
    the raw chronological scoring rule (the first ``cap`` starts that occur).
    Both are real; this one answers "which starts should I let count if I manage
    my lineup optimally," the other answers "which count if I start everyone."

    Returns the INDICES (into ``fps``) of the starts beyond the top ``cap`` by
    FP. Ties keep input order (stable). Empty set when at/under the cap.
    """
    if len(fps) <= cap:
        return set()
    ranked = sorted(range(len(fps)), key=lambda i: -fps[i])  # stable: ties keep order
    return set(ranked[cap:])
