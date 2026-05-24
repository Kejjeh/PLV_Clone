"""build_name_resolution_cache.py — pre-resolve names → batter MLBAM IDs.

Emits ``data/research/xfp_cache/name_resolution_2026.csv`` with one row per
unique ``(player_name, team)`` combo seen across:

  - current ESPN roster (``LeagueState().my_roster()``)
  - every team's roster (``LeagueState().all_teams()``)
  - the current FA pool (``LeagueState().available_fa()``)
  - the multiyr cache (``hitters_multiyr_2015_2026.csv``, all years)

Columns:
  player_name, team, position, batter_mlbam, is_known_collision,
  resolution_status, built_at

Resolution statuses:
  - "resolved"           — batter_mlbam populated
  - "unresolved"         — name absent from multiyr cache
  - "collision-no-hint"  — name is in KNOWN_COLLISIONS and the row's
                            team didn't match any collision candidate
                            (these are bugs to triage)

Skills/pipelines should NOT re-resolve from scratch every run — they
should call ``plv_clone.utils.name_match.lookup_batter_id_cached`` which
reads this CSV.

Usage:
  python -X utf8 scripts/xfp/build_name_resolution_cache.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from plv_clone.utils.name_match import (  # noqa: E402
    KNOWN_COLLISIONS,
    resolve_batter_id,
)

MULTIYR_PATH = ROOT / "data" / "research" / "xfp_cache" / "hitters_multiyr_2015_2026.csv"
OUT_PATH = ROOT / "data" / "research" / "xfp_cache" / "name_resolution_2026.csv"


def _collect_espn_rows() -> list[dict]:
    """Pull (name, team, position) tuples from ESPN. Returns [] on failure."""
    rows: list[dict] = []
    try:
        from plv_clone.league_state import LeagueState
        state = LeagueState()
    except Exception as exc:  # pragma: no cover — env-dependent
        print(f"  ! ESPN connector unavailable ({exc}); skipping ESPN sources")
        return rows

    try:
        mine = state.my_roster()
        for _, r in mine.iterrows():
            rows.append({
                "player_name": r.get("player_name"),
                "team": (r.get("pro_team") or "").upper(),
                "position": r.get("position") or "",
                "source": "my_roster",
            })
    except Exception as exc:
        print(f"  ! my_roster() failed: {exc}")

    try:
        teams = state.all_teams()
        for _, r in teams.iterrows():
            rows.append({
                "player_name": r.get("player_name"),
                "team": (r.get("pro_team") or "").upper(),
                "position": r.get("position") or "",
                "source": "all_teams",
            })
    except Exception as exc:
        print(f"  ! all_teams() failed: {exc}")

    try:
        fa = state.available_fa()
        for _, r in fa.iterrows():
            rows.append({
                "player_name": r.get("player_name"),
                "team": (r.get("pro_team") or "").upper(),
                "position": r.get("position") or "",
                "source": "available_fa",
            })
    except Exception as exc:
        print(f"  ! available_fa() failed: {exc}")

    return rows


def _collect_multiyr_rows(multiyr: pd.DataFrame) -> list[dict]:
    """One row per (player_name, team) — most recent year wins for position."""
    if multiyr.empty:
        return []
    sub = multiyr[["player_name", "team", "year"]].dropna(subset=["player_name"])
    sub = sub.copy()
    sub["team"] = sub["team"].astype(str).str.upper()
    # Most-recent year per player_name only. We don't need a row per
    # historic (name, team) combo — batter_mlbam is name-stable, and
    # ESPN sources above already cover current-team rows. Keeping only
    # the latest multiyr row per player keeps the cache under the size
    # budget (≤ 200KB).
    idx = sub.groupby(["player_name"])["year"].idxmax()
    latest = sub.loc[idx]
    return [
        {
            "player_name": r.player_name,
            "team": r.team,
            "position": "",  # multiyr has no position column
            "source": "multiyr",
        }
        for r in latest.itertuples(index=False)
    ]


def _dedupe_keep_most_recent(rows: list[dict]) -> pd.DataFrame:
    """Collapse to one row per (player_name, team).

    ESPN sources outrank multiyr for position info; otherwise first-seen wins.
    """
    if not rows:
        return pd.DataFrame(
            columns=["player_name", "team", "position"]
        )
    df = pd.DataFrame(rows)
    df["player_name"] = df["player_name"].astype(str)
    df["team"] = df["team"].fillna("").astype(str).str.upper()
    df["position"] = df["position"].fillna("").astype(str)

    # Sort so ESPN sources come first → drop_duplicates keeps them
    src_rank = {"my_roster": 0, "all_teams": 1, "available_fa": 2, "multiyr": 3}
    df["_rank"] = df["source"].map(src_rank).fillna(9)
    df = df.sort_values("_rank").drop_duplicates(
        subset=["player_name", "team"], keep="first"
    )
    return df[["player_name", "team", "position"]].reset_index(drop=True)


def _resolve_row(
    name: str,
    team: str,
    position: str,
    multiyr: pd.DataFrame,
) -> tuple[int | None, bool, str]:
    """Return (batter_mlbam, is_known_collision, status)."""
    is_collision = name in KNOWN_COLLISIONS
    team_arg = team if team else None
    pos_arg = position if position else None

    bid = resolve_batter_id(
        name, team=team_arg, position=pos_arg, multiyr=multiyr
    )
    if bid is not None:
        return bid, is_collision, "resolved"
    if is_collision:
        return None, True, "collision-no-hint"
    return None, False, "unresolved"


def main() -> None:
    print(f"BUILD name_resolution cache — {datetime.now().isoformat(timespec='seconds')}")

    if not MULTIYR_PATH.exists():
        print(f"  ! multiyr cache missing at {MULTIYR_PATH}; aborting")
        sys.exit(1)

    multiyr = pd.read_csv(MULTIYR_PATH, usecols=["batter", "player_name", "team", "year"])
    print(f"  - multiyr rows: {len(multiyr):,}")

    rows: list[dict] = []
    rows.extend(_collect_espn_rows())
    print(f"  - ESPN rows collected: {len(rows):,}")

    rows.extend(_collect_multiyr_rows(multiyr))
    print(f"  - rows after multiyr merge: {len(rows):,}")

    deduped = _dedupe_keep_most_recent(rows)
    print(f"  - unique (name, team) rows: {len(deduped):,}")

    built_at = datetime.now().isoformat(timespec="seconds")
    out_rows = []
    for r in deduped.itertuples(index=False):
        bid, is_coll, status = _resolve_row(
            r.player_name, r.team, r.position, multiyr
        )
        out_rows.append({
            "player_name": r.player_name,
            "team": r.team,
            "position": r.position,
            "batter_mlbam": bid,
            "is_known_collision": is_coll,
            "resolution_status": status,
            "built_at": built_at,
        })

    out_df = pd.DataFrame(out_rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT_PATH, index=False)

    size_kb = OUT_PATH.stat().st_size / 1024
    counts = out_df["resolution_status"].value_counts().to_dict()
    n_resolved = counts.get("resolved", 0)
    n_unresolved = counts.get("unresolved", 0)
    n_collision = counts.get("collision-no-hint", 0)

    print(f"\n{'='*64}")
    print(f"  SUMMARY — wrote {OUT_PATH}")
    print(f"  rows: {len(out_df):,} | size: {size_kb:.1f} KB")
    print(f"  resolved:           {n_resolved:,}")
    print(f"  unresolved:         {n_unresolved:,}")
    print(f"  collision-no-hint:  {n_collision:,}")
    print(f"{'='*64}")

    if n_collision:
        print("\n  COLLISION-NO-HINT cases (triage these — wrong/missing team):")
        for r in out_df[out_df["resolution_status"] == "collision-no-hint"].itertuples(index=False):
            print(f"    - {r.player_name!r}  team={r.team!r}  pos={r.position!r}")

    if n_unresolved and n_unresolved < 50:
        print(f"\n  UNRESOLVED names (first {min(n_unresolved, 25)}):")
        for r in out_df[out_df["resolution_status"] == "unresolved"].head(25).itertuples(index=False):
            print(f"    - {r.player_name!r}  team={r.team!r}")
    elif n_unresolved:
        print(f"\n  UNRESOLVED count = {n_unresolved} (sample omitted; mostly multiyr-only names without an ESPN match)")


if __name__ == "__main__":
    main()
