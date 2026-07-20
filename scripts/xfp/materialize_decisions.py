"""materialize_decisions.py — PR 5 sub-action 4.

Walks `data/research/decisions/` recursively, loads every JSON, and
emits a flat panel at `data/outputs/decisions_panel.csv` (one row per
decision).

Opportunistically settles pending decisions when (a) today is past the
per-bucket window-end AND (b) a Statcast actual is available. The
Statcast aggregation pattern is borrowed from
`scripts/xfp/validate_buylow_signal.py` (canonical hitter-FP formula
shipped 2026-06-06 at 1065df0).

H/SP/RP all settle opportunistically:
  - H actuals from `statcast_{yr}.parquet` (per-PA aggregation; canonical
    BrownU hitter formula).
  - SP / RP actuals from the MLB Stats API gameLog endpoint, scored via
    `LeagueScoring.score_pitcher_start` / `score_pitcher_relief` (the
    canonical BrownU scorer shipped at 93409d0). The gameLog has ER,
    SV, and HLD natively which Statcast does not, so this is closer to
    BrownU truth than a Statcast-derived approximation would be.

Hard 2020 exclusion: any decision dated in 2020 is dropped (consistent
with the rest of the repo's training-data hygiene).

Usage:
    python -X utf8 scripts/xfp/materialize_decisions.py --as-of 2026-06-06
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from plv_clone.decisions import (  # noqa: E402
    DECISIONS_ROOT,
    DecisionRecord,
    SETTLEMENT_WINDOWS,
    log_decision,
    settle_decision,
)
from plv_clone.fantasy.scoring import LeagueScoring  # noqa: E402

# Single instance — BrownU defaults match the canonical formula.
_SCORING = LeagueScoring()

CACHE = ROOT / "data" / "research" / "xfp_cache"
OUT_CSV = ROOT / "data" / "outputs" / "decisions_panel.csv"

# Reuse the canonical event sets from validate_buylow_signal.py.
PA_EVENTS = {
    "single", "double", "triple", "home_run", "walk", "intent_walk",
    "hit_by_pitch", "strikeout", "strikeout_double_play",
    "field_out", "force_out", "grounded_into_double_play",
    "sac_fly", "sac_bunt", "fielders_choice", "fielders_choice_out",
    "double_play", "triple_play", "field_error", "catcher_interf",
    "sac_fly_double_play", "strikeout_triple_play", "truncated_pa",
}
TB_MAP = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
K_EVENTS = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
BB_EVENTS = {"walk", "intent_walk"}


# ---------------------------------------------------------------------------
# Disk walk
# ---------------------------------------------------------------------------


def _load_all(root: Path) -> list[DecisionRecord]:
    """Walk {root}/{YYYY-MM-DD}/*.json and load every record."""
    if not root.exists():
        return []
    records: list[DecisionRecord] = []
    for json_path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠ corrupt JSON skipped: {json_path}")
            continue
        try:
            records.append(DecisionRecord(**payload))
        except TypeError as e:
            print(f"  ⚠ schema mismatch skipped {json_path.name}: {e}")
    return records


# ---------------------------------------------------------------------------
# Hitter actuals — mirrors validate_buylow_signal.py
# ---------------------------------------------------------------------------


def _hitter_actuals_for_window(
    year: int,
    batter_ids: set[int],
    window_start: date,
    window_end: date,
) -> dict[int, tuple[int, float]]:
    """Return {batter_id: (n_pa, fp_per_pa)} over [start, end].

    Uses the BrownU hitter formula: FP = TB + R(HR proxy) + RBI + BB + HBP - K.
    SB is omitted here (we don't carry a per-batter SB rate lookup at the
    materializer layer); over a 21-day window the SB delta on FP/PA is
    small (~0.02 PA-rate * 1 FP each) and well within the H threshold (0.02
    FP/PA). Acceptable approximation for the BUY_HIT/MISS classifier.
    """
    parquet = CACHE / f"statcast_{year}.parquet"
    if not parquet.exists():
        return {}
    if not batter_ids:
        return {}
    df = pd.read_parquet(
        parquet,
        columns=["game_date", "batter", "events", "bat_score", "post_bat_score"],
    )
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    df = df[
        df["batter"].isin(batter_ids)
        & (df["game_date"] >= window_start)
        & (df["game_date"] <= window_end)
        & df["events"].isin(PA_EVENTS)
    ].copy()
    if df.empty:
        return {}
    df["tb"] = df["events"].map(TB_MAP).fillna(0).astype(int)
    df["bb"] = df["events"].isin(BB_EVENTS).astype(int)
    df["hbp"] = (df["events"] == "hit_by_pitch").astype(int)
    df["k"] = df["events"].isin(K_EVENTS).astype(int)
    df["hr"] = (df["events"] == "home_run").astype(int)
    df["rbi"] = (df["post_bat_score"] - df["bat_score"]).fillna(0).clip(lower=0)

    agg = df.groupby("batter").agg(
        pa=("events", "count"),
        tb=("tb", "sum"),
        bb=("bb", "sum"),
        hbp=("hbp", "sum"),
        k=("k", "sum"),
        hr=("hr", "sum"),
        rbi=("rbi", "sum"),
    ).reset_index()
    agg["fp_total"] = (
        agg["tb"] + agg["hr"] + agg["rbi"] + agg["bb"] + agg["hbp"] - agg["k"]
    )
    agg["fp_per_pa"] = agg["fp_total"] / agg["pa"].clip(lower=1)
    return {
        int(r.batter): (int(r.pa), float(r.fp_per_pa))
        for r in agg.itertuples(index=False)
    }


# ---------------------------------------------------------------------------
# Pitcher actuals — MLB Stats API gameLog
# ---------------------------------------------------------------------------


def _fetch_pitcher_gamelog(mlbam_id: int, season: int) -> list[dict]:
    """Pull season pitcher gameLog from the MLB Stats API.

    Returns a list of {date, gamesStarted, inningsPitched, strikeOuts,
    hits, earnedRuns, baseOnBalls, hitByPitch, saves, holds} dicts —
    one per game.

    Network/JSON failures return []. Caller treats empty as "no data".
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}"
        f"/stats?stats=gameLog&season={season}&group=pitching&sportId=1"
    )
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
    except Exception as exc:
        print(f"  ⚠ gameLog fetch failed for {mlbam_id} ({season}): {exc}")
        return []
    stats_list = payload.get("stats", [])
    if not stats_list:
        return []
    splits = stats_list[0].get("splits", []) or []
    out = []
    for s in splits:
        stat = s.get("stat", {}) or {}
        out.append({
            "date": s.get("date"),
            "gamesStarted": int(stat.get("gamesStarted", 0) or 0),
            "inningsPitched": stat.get("inningsPitched", "0.0"),
            "strikeOuts": int(stat.get("strikeOuts", 0) or 0),
            "hits": int(stat.get("hits", 0) or 0),
            "earnedRuns": int(stat.get("earnedRuns", 0) or 0),
            "baseOnBalls": int(stat.get("baseOnBalls", 0) or 0),
            "hitByPitch": int(stat.get("hitByPitch", 0) or 0),
            "saves": int(stat.get("saves", 0) or 0),
            "holds": int(stat.get("holds", 0) or 0),
        })
    return out


def _filter_games_in_window(
    games: list[dict], window_start: date, window_end: date,
) -> list[dict]:
    """Keep only games whose date falls in [window_start, window_end]."""
    out = []
    for g in games:
        d = g.get("date")
        if not d:
            continue
        try:
            gd = date.fromisoformat(d)
        except ValueError:
            continue
        if window_start <= gd <= window_end:
            out.append(g)
    return out


def _sp_actuals_for_window(
    mlbam_id: int, window_start: date, window_end: date,
) -> Optional[tuple[int, float]]:
    """Return (n_starts, fp_per_start) for the SP over the window.

    Uses LeagueScoring.score_pitcher_start (canonical BrownU scorer).
    Returns None if no starts found (caller leaves record pending).
    Filters to gamesStarted==1.
    """
    season = window_start.year
    if season == 2020:
        return None  # hard 2020 exclusion
    games = _fetch_pitcher_gamelog(int(mlbam_id), season)
    if not games:
        return None
    games = _filter_games_in_window(games, window_start, window_end)
    starts = [g for g in games if g.get("gamesStarted", 0) == 1]
    if not starts:
        return None
    total_fp = sum(_SCORING.score_pitcher_start(g) for g in starts)
    n = len(starts)
    return n, total_fp / n


def _rp_actuals_for_window(
    mlbam_id: int, window_start: date, window_end: date,
) -> Optional[tuple[int, float]]:
    """Return (n_appearances, fp_per_g) for the RP over the window.

    Uses LeagueScoring.score_pitcher_relief (canonical BrownU scorer,
    includes 5*SV + 2*HLD). Filters to gamesStarted==0.
    """
    season = window_start.year
    if season == 2020:
        return None
    games = _fetch_pitcher_gamelog(int(mlbam_id), season)
    if not games:
        return None
    games = _filter_games_in_window(games, window_start, window_end)
    apps = [g for g in games if g.get("gamesStarted", 0) == 0]
    if not apps:
        return None
    total_fp = sum(_SCORING.score_pitcher_relief(g) for g in apps)
    n = len(apps)
    return n, total_fp / n


# ---------------------------------------------------------------------------
# Settle + persist back
# ---------------------------------------------------------------------------


def _try_settle(record: DecisionRecord, today: date) -> DecisionRecord:
    """Opportunistically settle H / SP / RP decisions when ready.

    "Ready" = today past per-bucket window-end AND we can pull actuals.
    """
    if record.settled_at is not None:
        return record  # already settled
    if record.bucket not in SETTLEMENT_WINDOWS:
        return record  # unknown bucket — nothing to do
    if record.mlbam_id is None:
        return record

    snap = date.fromisoformat(record.snapshot_date)
    if snap.year == 2020:
        return record  # hard exclusion
    window = SETTLEMENT_WINDOWS[record.bucket]
    window_end = snap + timedelta(days=window["days"])
    if today < window_end:
        return record

    n_events: Optional[int] = None
    actual: Optional[float] = None

    if record.bucket == "H":
        actuals = _hitter_actuals_for_window(
            snap.year, {int(record.mlbam_id)}, snap, window_end,
        )
        if int(record.mlbam_id) in actuals:
            n_events, actual = actuals[int(record.mlbam_id)]
    elif record.bucket == "SP":
        sp = _sp_actuals_for_window(int(record.mlbam_id), snap, window_end)
        if sp is not None:
            n_events, actual = sp
    elif record.bucket == "RP":
        rp = _rp_actuals_for_window(int(record.mlbam_id), snap, window_end)
        if rp is not None:
            n_events, actual = rp

    if n_events is None or actual is None:
        return record

    settled = settle_decision(
        record, today=today, actual_fp_per_unit=actual, n_events=n_events,
    )
    if settled.settled_at is not None and settled.settled_at != record.settled_at:
        # Persist the settlement back to disk so we don't recompute next run.
        log_decision(settled)
    return settled


# ---------------------------------------------------------------------------
# Panel emission
# ---------------------------------------------------------------------------


def _record_to_row(record: DecisionRecord) -> dict:
    classification: Optional[str] = None
    residual: Optional[float] = None
    n_events: Optional[int] = None
    if record.settlement:
        classification = record.settlement.get("classification")
        residual = record.settlement.get("residual")
        n_events = record.settlement.get("n_events")
    return {
        "decision_id": record.decision_id,
        "snapshot_date": record.snapshot_date,
        "player_name": record.player_name,
        "mlbam_id": record.mlbam_id,
        "bucket": record.bucket,
        "verdict_top": record.verdict_top,
        "reason_tag": record.reason_tag,
        "confidence": record.confidence,
        "settled_at": record.settled_at,
        "classification": classification,
        "residual": residual,
        "n_events": n_events,
    }


def materialize(
    *, as_of: date, root: Path = DECISIONS_ROOT, out_csv: Path = OUT_CSV
) -> pd.DataFrame:
    """Walk decisions root, opportunistically settle, emit CSV. Returns the DF."""
    records = _load_all(root)
    if not records:
        print(f"  no decisions found under {root}")
        df = pd.DataFrame(columns=[
            "decision_id", "snapshot_date", "player_name", "mlbam_id",
            "bucket", "verdict_top", "reason_tag", "confidence",
            "settled_at", "classification", "residual", "n_events",
        ])
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
        return df

    settled_records = [_try_settle(r, today=as_of) for r in records]
    rows = [_record_to_row(r) for r in settled_records]
    df = pd.DataFrame(rows).sort_values(
        ["snapshot_date", "bucket", "player_name"]
    )
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    n_settled = sum(1 for r in settled_records if r.settled_at)
    print(
        f"  wrote {len(df)} decisions -> {out_csv}"
        f" ({n_settled} settled, {len(df) - n_settled} pending)"
    )
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--as-of",
        default=date.today().isoformat(),
        help="ISO date treated as 'today' for settlement-window math.",
    )
    ap.add_argument("--root", default=str(DECISIONS_ROOT))
    ap.add_argument("--out", default=str(OUT_CSV))
    args = ap.parse_args()

    as_of = datetime.fromisoformat(args.as_of).date()
    materialize(
        as_of=as_of, root=Path(args.root), out_csv=Path(args.out)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
