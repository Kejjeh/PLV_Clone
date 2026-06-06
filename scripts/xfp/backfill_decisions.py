"""backfill_decisions.py — PR 5 sub-action 5.

Reads `data/research/player_projection_history.parquet`, runs
`triangulate_player()` for each unique (snapshot_date, player) row, and
writes the resulting DecisionRecord under
`data/research/decisions/{snapshot_date}/{decision_id}.json`.

LOOK-AHEAD-BIAS CAVEAT (plan v11 Option A — preferred):
The current triangulate engine reads TODAY'S projection CSVs (rh3/rp3/
rprs2 + archetype panels + PL cache). For historical snapshot_dates we
CANNOT reconstruct the verdict as it would have appeared on that date;
the inputs feeding the verdict are AS-OF-TODAY data. Backfilled records
therefore carry `inputs["backfill_mode"] = "as_of_current_data"` so any
downstream consumer can filter them out of forward-looking lift tests.

Hard 2020 exclusion: any snapshot_date in 2020 is skipped (defense-in-
depth; the projection-history parquet started 2026-06-04 so this is
mostly academic but the rule stays).

The triangulate engine is invoked once per player (not per
snapshot_date × player) — because as-of-today verdicts are identical
across snapshot_dates, calling it N×M times wastes ~10s/player. We
cache per-player verdicts and stamp them onto each snapshot_date.

Usage:
    python -X utf8 scripts/xfp/backfill_decisions.py
    python -X utf8 scripts/xfp/backfill_decisions.py --limit 20  # smoke
    python -X utf8 scripts/xfp/backfill_decisions.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from plv_clone.decisions import (  # noqa: E402
    DecisionRecord,
    from_triangulate_result,
    log_decision,
)

# Try to import triangulate_player. If the import fails (e.g., the script
# is invoked from an environment that can't load triangulate_core's
# transitive deps), bail out with a clear message rather than producing
# a corrupt backfill.
try:
    sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
    from lib.triangulate_core import triangulate_player  # type: ignore
except Exception as e:  # pragma: no cover — environment-dependent
    print(f"FATAL: cannot import triangulate_player: {e}")
    triangulate_player = None  # type: ignore


HISTORY_PATH = ROOT / "data" / "research" / "player_projection_history.parquet"


def _stamp_backfill(rec: DecisionRecord) -> DecisionRecord:
    """Add the look-ahead-bias tag to the record's inputs."""
    new_inputs = dict(rec.inputs or {})
    new_inputs["backfill_mode"] = "as_of_current_data"
    return DecisionRecord(
        decision_id=rec.decision_id,
        snapshot_date=rec.snapshot_date,
        player_name=rec.player_name,
        mlbam_id=rec.mlbam_id,
        bucket=rec.bucket,
        verdict_top=rec.verdict_top,
        reason_tag=rec.reason_tag,
        confidence=rec.confidence,
        inputs=new_inputs,
        settled_at=rec.settled_at,
        settlement=rec.settlement,
    )


def backfill(
    *,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Read history parquet, triangulate each unique player, write JSONs.

    Returns a stats dict for the caller.
    """
    if triangulate_player is None:
        return {"status": "error", "reason": "triangulate_import_failed"}

    if not HISTORY_PATH.exists():
        return {"status": "error", "reason": f"missing {HISTORY_PATH}"}

    df = pd.read_parquet(HISTORY_PATH)
    if df.empty:
        return {"status": "empty"}

    # Hard 2020 exclusion (defense-in-depth — history starts 2026 anyway).
    df = df[~df["snapshot_date"].astype(str).str.startswith("2020-")].copy()

    # Iterate unique (snapshot_date, player_name) tuples; cache the
    # triangulate output per player_name across snapshots.
    df = df[["snapshot_date", "player_type", "mlbam_id", "player_name"]].drop_duplicates()
    if limit:
        df = df.head(limit)

    stats = {
        "rows_input": int(len(df)),
        "unique_players": int(df["player_name"].nunique()),
        "n_written": 0,
        "n_skipped_resolve": 0,
        "n_errors": 0,
    }
    triangulate_cache: dict[tuple[str, str], Optional[dict]] = {}
    # Per-player-per-day seq counter, so re-running doesn't collide on the
    # same path (we always overwrite seq=001 here; this is by design — a
    # rerun reproduces the same JSON).
    for row in df.itertuples(index=False):
        snap = row.snapshot_date
        if isinstance(snap, pd.Timestamp):
            snap_d = snap.date()
        elif isinstance(snap, date):
            snap_d = snap
        else:
            snap_d = datetime.fromisoformat(str(snap)).date()

        cache_key = (row.player_name, row.player_type)
        if cache_key in triangulate_cache:
            result = triangulate_cache[cache_key]
        else:
            try:
                result = triangulate_player(row.player_name, bucket=row.player_type)
            except Exception:
                stats["n_errors"] += 1
                traceback.print_exc()
                triangulate_cache[cache_key] = None
                continue
            triangulate_cache[cache_key] = result

        if not result:
            stats["n_skipped_resolve"] += 1
            continue

        try:
            rec = from_triangulate_result(result, snapshot_date=snap_d)
            rec = _stamp_backfill(rec)
        except Exception:
            stats["n_errors"] += 1
            traceback.print_exc()
            continue

        if not dry_run:
            log_decision(rec)
        stats["n_written"] += 1

    return {"status": "ok", **stats}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    result = backfill(limit=args.limit, dry_run=args.dry_run)
    print(result)
    return 0 if result.get("status") in ("ok", "empty") else 1


if __name__ == "__main__":
    sys.exit(main())
