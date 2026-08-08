"""Flag KNOWN_COLLISIONS / KNOWN_PITCHER_COLLISIONS rows whose team has gone stale.

WHY THIS EXISTS
---------------
In the collision tables, ``team`` is AUTHORITATIVE: a hint that matches no
candidate resolves to None rather than guessing. That is the right contract —
it is what stops ``resolve_batter_id("Max Muncy", team="Oak")`` handing back
the LAD Muncy. But it means a listed player who gets TRADED silently becomes
unresolvable: the caller passes his live team, no candidate matches, and the
player is dropped as though he did not exist.

That is not hypothetical. On 2026-08-07 both José Soriano (LAA -> TOR) and
Luis García Jr. (WSH -> NYY) failed to resolve, and live_monitor skipped them
— understating the day's fantasy total by ~8 FP with no error, because a
skipped player just scores zero. Two in one day, at the trade deadline.

The fix in the table is to add a row per team the player has appeared for. The
fix in the PROCESS is this script: run it after the deadline, or whenever a
resolver starts returning None for someone who is obviously playing.

Deliberately a script and NOT a pytest case: it needs the MLB Stats API, and a
network-dependent test would either be flaky in CI or silently skipped, which
is the same failure mode it is meant to catch.

    python scripts/xfp/audit_collision_team_staleness.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from plv_clone.utils.name_match import (  # noqa: E402
    KNOWN_COLLISIONS, KNOWN_PITCHER_COLLISIONS, team_key,
)

TEAMS_API = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
CACHE = ROOT / "data" / "research" / "xfp_cache"


def _team_abbr_by_id() -> dict[int, str]:
    """{team_id: abbreviation}, one API call for all 30 clubs."""
    try:
        j = requests.get(TEAMS_API, timeout=20).json()
        return {int(t["id"]): t["abbreviation"] for t in j.get("teams", [])}
    except Exception as e:
        print(f"WARN could not fetch team map ({e})", file=sys.stderr)
        return {}


def _latest_team_by_mlbam() -> dict[int, tuple[str, str, str]]:
    """{mlbam: (abbr, player_name, last game date)} from the LOCAL boxscore store.

    Deliberately not the MLB people endpoint: its ``currentTeam`` comes back
    empty for these ids (verified 2026-08-07), so an audit built on it reports
    "no stale rows" no matter what — false assurance, which is worse than no
    audit at all. The boxscore store records the club a player ACTUALLY
    appeared for, is refreshed nightly, and needs no per-player network call.
    """
    import pandas as pd
    abbr = _team_abbr_by_id()
    frames = []
    for fn in ("boxscore_hitters.parquet", "boxscore_pitchers.parquet"):
        p = CACHE / fn
        if p.exists():
            frames.append(pd.read_parquet(p)[
                ["mlbam_id", "player_name", "team_id", "game_date"]])
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").groupby("mlbam_id").tail(1)
    out = {}
    for _, r in df.iterrows():
        a = abbr.get(int(r["team_id"]))
        if a:
            out[int(r["mlbam_id"])] = (a, str(r["player_name"]),
                                       r["game_date"].date().isoformat())
    return out


def audit(table: dict, label: str, latest: dict) -> list[str]:
    """Report ids whose most recent club is absent from their candidate rows."""
    problems = []
    # Group by distinct id: the same player appears under several spellings and
    # they share one candidate list.
    ids: dict[int, set[str]] = {}
    for _name, cands in table.items():
        for team, _pos, mlbam in cands:
            ids.setdefault(int(mlbam), set()).add(team_key(team))
    print(f"\n=== {label}: {len(ids)} distinct player(s) ===")
    for mlbam, listed in sorted(ids.items()):
        rec = latest.get(mlbam)
        if not rec:
            print(f"  ?      {mlbam} — no 2026 appearances in the boxscore store")
            continue
        abbr, full, when = rec
        if team_key(abbr) not in listed:
            msg = (f"  STALE  {full} ({mlbam}): played for {abbr} on {when}, "
                   f"table lists {sorted(listed)}")
            print(msg)
            problems.append(msg)
        else:
            print(f"  ok     {full} ({mlbam}): {abbr}")
    return problems


def main() -> int:
    latest = _latest_team_by_mlbam()
    if not latest:
        print("could not read the boxscore store — audit inconclusive, NOT clean",
              file=sys.stderr)
        return 2
    problems = audit(KNOWN_COLLISIONS, "KNOWN_COLLISIONS (batters)", latest)
    problems += audit(KNOWN_PITCHER_COLLISIONS, "KNOWN_PITCHER_COLLISIONS", latest)
    print()
    if problems:
        print(f"{len(problems)} stale row(s). Add a (team, pos, mlbam) row for the "
              f"CURRENT team — keep the old one so historical callers still "
              f"resolve; same id twice is not ambiguity.")
        return 1
    print("no stale collision teams found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
