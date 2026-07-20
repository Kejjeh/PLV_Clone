"""persist_transactions.py — daily archive of ESPN add/drop/trade activity.

Pulls league.recent_activity() (current season only — ESPN returns
"League 24080 does not exist" for 2024/2025) and appends to
data/research/transactions_history.parquet. Idempotent on
(date, team_id, player_name, action_str) so daily reruns don't dupe.

recent_activity is a rolling window (~7-14 days). Daily runs catch
transactions before they fall off the window — combined with the Monday
roster snapshot in persist_matchup_rosters.py, this lets us reconstruct
roster state at any point in any future closed period.

Schema:
  date (date)
  ts_ms (int)             # ESPN raw ms timestamp
  team_id (int)
  team_name (str)
  action_str (str)        # 'ADDED' / 'DROPPED' / 'TRADED' / etc.
  player_name (str)
  position (str)
  pro_team (str)
  espn_player_id (int|nullable)
  mlbam_id (int|nullable)
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "data" / "research" / "transactions_history.parquet"

KEY_COLS = ["date", "team_id", "player_name", "action_str"]


def _resolve_mlbam(name: str, team: str, position: str) -> int | None:
    try:
        from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
    except Exception:
        return None
    pos = (position or "").upper()
    if pos in {"SP", "RP", "P"}:
        role = "SP" if pos == "SP" else ("RP" if pos == "RP" else None)
        try:
            mid = resolve_pitcher_id(name, team=team or None, role=role)
            if mid is not None:
                return int(mid)
        except Exception:
            pass
        try:
            mid = resolve_pitcher_id(name, team=team or None)
            return int(mid) if mid is not None else None
        except Exception:
            return None
    try:
        mid = resolve_batter_id(name, team=team or None, position=position or None)
        return int(mid) if mid is not None else None
    except Exception:
        return None


def pull_activity(size: int = 500) -> pd.DataFrame:
    from app.espn_connector import _get_league
    league = _get_league()
    try:
        acts = league.recent_activity(size=size)
    except Exception as e:
        print(f"  ⚠ recent_activity failed: {e}")
        return pd.DataFrame()

    rows = []
    for a in acts or []:
        ts_ms = getattr(a, "date", None)
        if ts_ms is None:
            continue
        try:
            act_date = datetime.fromtimestamp(ts_ms / 1000).date()
        except Exception:
            continue
        for action in (getattr(a, "actions", None) or []):
            try:
                team, action_str, player = action[0], action[1], action[2]
                # action may be (team, str, player_name) OR (team, str, Player obj)
                if hasattr(player, "name"):
                    player_name = player.name
                    position = getattr(player, "position", "") or ""
                    pro_team = getattr(player, "proTeam", "") or ""
                    espn_pid = int(getattr(player, "playerId", 0) or 0) or None
                else:
                    player_name = str(player) if player is not None else ""
                    position = ""
                    pro_team = ""
                    espn_pid = None
                if not player_name:
                    continue
                tid = int(getattr(team, "team_id", 0) or 0) if team is not None else 0
                tname = getattr(team, "team_name", "") if team is not None else ""
                mlbam = _resolve_mlbam(player_name, pro_team, position)
                rows.append({
                    "date": act_date,
                    "ts_ms": int(ts_ms),
                    "team_id": tid,
                    "team_name": tname,
                    "action_str": str(action_str or "").upper(),
                    "player_name": player_name,
                    "position": position,
                    "pro_team": pro_team,
                    "espn_player_id": espn_pid,
                    "mlbam_id": mlbam,
                })
            except Exception:
                continue
    return pd.DataFrame(rows)


def atomic_upsert(new_df: pd.DataFrame, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            old = pd.read_parquet(path)
        except Exception as e:
            print(f"  ⚠ couldn't read existing parquet ({e}); starting fresh")
            old = pd.DataFrame(columns=new_df.columns)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df.copy()
    combined["date"] = pd.to_datetime(combined["date"]).dt.date
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
    df = pull_activity(size=500)
    if df.empty:
        print("⚠ no transactions returned (could be a quiet window or auth issue)")
        # Still touch the file so downstream knows we ran — but only if it exists.
        return 0
    n_new = len(df)
    total = atomic_upsert(df, OUT_PATH)
    n_resolved = df["mlbam_id"].notna().sum()
    print(f"✓ persisted {n_new} transaction rows ({n_resolved} with MLBAM); parquet now has {total} total rows")
    print(f"  → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
