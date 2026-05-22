"""SP cap arithmetic over injected data.

Pure functions over roster + WeekProbables. No remote dependencies — the
MLB Stats API fetch lives in `plv_clone.mlb_stats`. See ADR-0002.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SP_CAP = 10

IL_STATUSES = frozenset({"TEN_DAY_DL", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL"})


@dataclass(frozen=True)
class RosterPitcher:
    name: str
    mlbam_id: int | None
    injury_status: str
    position: str


@dataclass(frozen=True)
class WeekProbables:
    starts: dict[tuple[int, date], str] = field(default_factory=dict)


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
