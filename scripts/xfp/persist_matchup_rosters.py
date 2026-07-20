"""persist_matchup_rosters.py — daily snapshot of all 8 BrownU rosters.

Writes one row per (snapshot_date, team_id, mlbam_id) to
data/research/matchup_rosters_history.parquet. Idempotent: re-running on
the same day for the same team/player upserts (drops dupes, keeps latest).

Schema:
  snapshot_date (date)
  scoring_period (int)              # league.scoringPeriodId
  matchup_period (int)              # league.currentMatchupPeriod
  team_id (int)
  team_name (str)
  espn_player_id (int)              # ESPN's playerId
  mlbam_id (int|nullable)           # resolved via name_match — None if unresolved
  player_name (str)
  position (str)
  lineup_slot (str)
  injury_status (str)
  injured (bool)
  percent_owned (float)

Designed for daily runs. Monday rerun = period-start snapshot; mid-week
reruns capture intra-period roster shifts. Combined with
persist_transactions.py, the parquet lets us reconstruct roster state at
any point in a closed period (useful for the mid-week-roster-moves
residual study once N_periods >= 6, ~mid-July 2026).
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "data" / "research" / "matchup_rosters_history.parquet"

KEY_COLS = ["snapshot_date", "team_id", "espn_player_id"]


def _resolve_mlbam(name: str, team: str, position: str) -> int | None:
    """Best-effort: try batter cache then pitcher cache. None if neither hits."""
    try:
        from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
    except Exception:
        return None
    pos = (position or "").upper()
    # Pitchers
    if pos in {"SP", "RP", "P"}:
        role = "SP" if pos == "SP" else ("RP" if pos == "RP" else None)
        try:
            mid = resolve_pitcher_id(name, team=team or None, role=role)
            if mid is not None:
                return int(mid)
        except Exception:
            pass
        # Try the other role bucket too
        try:
            mid = resolve_pitcher_id(name, team=team or None)
            if mid is not None:
                return int(mid)
        except Exception:
            pass
        return None
    # Hitters
    try:
        mid = resolve_batter_id(name, team=team or None, position=position or None)
        return int(mid) if mid is not None else None
    except Exception:
        return None


def snapshot_today() -> pd.DataFrame:
    from app.espn_connector import _get_league
    league = _get_league()
    scoring_period = int(getattr(league, "scoringPeriodId", 0) or 0)
    matchup_period = int(getattr(league, "currentMatchupPeriod", 0) or 0)
    today = date.today()
    rows = []
    for team in league.teams:
        tid = int(getattr(team, "team_id", 0) or 0)
        tname = getattr(team, "team_name", "") or ""
        for p in team.roster:
            name = getattr(p, "name", "") or ""
            pro_team = getattr(p, "proTeam", "") or ""
            position = getattr(p, "position", "") or ""
            mlbam = _resolve_mlbam(name, pro_team, position)
            rows.append({
                "snapshot_date": today,
                "scoring_period": scoring_period,
                "matchup_period": matchup_period,
                "team_id": tid,
                "team_name": tname,
                "espn_player_id": int(getattr(p, "playerId", 0) or 0),
                "mlbam_id": mlbam,
                "player_name": name,
                "pro_team": pro_team,
                "position": position,
                "lineup_slot": getattr(p, "lineupSlot", "") or "",
                "injury_status": getattr(p, "injuryStatus", "") or "",
                "injured": bool(getattr(p, "injured", False)),
                "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
            })
    return pd.DataFrame(rows)


def atomic_upsert(new_df: pd.DataFrame, path: Path) -> int:
    """Merge new_df with existing parquet, dedupe on KEY_COLS (keep latest=new),
    atomic temp+rename. Returns total record count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            old = pd.read_parquet(path)
        except Exception as e:
            print(f"  ⚠ couldn't read existing parquet ({e}); starting fresh")
            old = pd.DataFrame(columns=new_df.columns)
        # New rows last so drop_duplicates(keep='last') prefers them.
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df.copy()

    # Normalize date dtype before dedupe
    combined["snapshot_date"] = pd.to_datetime(combined["snapshot_date"]).dt.date
    combined = combined.drop_duplicates(subset=KEY_COLS, keep="last").reset_index(drop=True)

    fd, tmp = tempfile.mkstemp(suffix=".parquet", dir=str(path.parent))
    os.close(fd)
    try:
        combined.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return len(combined)


def main():
    snap = snapshot_today()
    if snap.empty:
        print("⚠ no roster rows pulled")
        return 1
    n_new = len(snap)
    total = atomic_upsert(snap, OUT_PATH)
    n_resolved = snap["mlbam_id"].notna().sum()
    print(f"✓ persisted {n_new} roster rows ({n_resolved} with MLBAM); parquet now has {total} total rows")
    print(f"  → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
