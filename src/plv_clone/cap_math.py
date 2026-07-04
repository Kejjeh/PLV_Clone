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

# Empirical rate: starts per active (healthy) SP per scoring week. Owner for what
# was a floating 1.19 literal re-declared under 6 different names across 8+ modules
# (SP_STARTS_WK / HEALTHY_SP_STARTS_PER_WEEK / RATE / inline 1.19) + 4 skills.
# Every cap-projection consumer imports THIS, never re-types it (audit 2026-07-03).
STARTS_PER_SP_PER_WEEK = 1.19

IL_STATUSES = frozenset({"TEN_DAY_DL", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL"})


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
            projected_fp=rp3[p.name],
            counts_toward_cap=i < SP_CAP,
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
