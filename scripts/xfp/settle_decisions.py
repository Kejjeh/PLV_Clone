"""settle_decisions.py — the DRIVER/host that settles logged DecisionRecords.

This is the missing host that `src/plv_clone/decisions/settler.py` explicitly
left out of scope ("The HOST script that PULLS actuals + n_events from
Statcast / game logs is out of scope for this PR"). It walks every logged
DecisionRecord, pulls realized actuals from the MLB Stats API gameLog
endpoint in the player's BrownU FP/unit, calls the pure
`settle_decision(...)`, writes settled records back to a parallel `settled/`
tree, and emits an ongoing scorecard (CSV + Markdown).

FP/unit per bucket (matches LeagueScoring in src/plv_clone/fantasy/scoring.py
and the SETTLEMENT_WINDOWS contract in settler.py):
  - H  : FP / PA          (window 21d / min 30 PA)
  - SP : FP / start       (window 35d / min 5 starts)
  - RP : FP / appearance  (window 35d / min 10 appearances)

All three buckets are scored from the MLB Stats API gameLog so that ER, SV,
and HLD come from box-score truth (Statcast does not carry these). The
hitting gameLog carries `plateAppearances` natively, so FP/PA needs no
parquet dependency.

Window math (from settler.SETTLEMENT_WINDOWS):
  settle iff today >= snapshot_date + window_days AND n_events >= min_events
  AND an actual is available. Otherwise the record stays PENDING and is
  retried on the next run.

Idempotent + re-runnable: settled records are written to a parallel
`data/research/decisions/settled/{YYYY-MM-DD}/{id}.json` tree via the same
atomic temp-file + os.replace path the logger uses. Already-settled records
are loaded from there and skipped (no redundant network calls). The source
JSONs under `decisions/{YYYY-MM-DD}/` are NEVER mutated.

Usage:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 \
        python scripts/xfp/settle_decisions.py --today 2026-06-11

WIRING (do this once to self-grade going forward): in
scripts/xfp/refresh_dashboards.py, add a fail-soft step immediately AFTER
the existing "4.10b. Materialize decisions panel" block (after line ~370,
right before `if not args.no_push:`), using the file's own `run(...)`
helper so it stays non-gating:

    # 4.10c. Settle logged decisions vs realized FP + emit daily scorecard.
    ok_settle = run(
        '4.10c. Settle decisions + scorecard',
        'python -X utf8 scripts/xfp/settle_decisions.py',
        timeout=180,
    )
    if not ok_settle:
        print('  ⚠ decision settlement failed — continuing (non-gating)')

This driver is the SP/RP-and-H actuals host that the 4.10b comment notes is
"not implemented in this driver yet" — it settles all three buckets from the
MLB Stats API gameLog and is safe to run alongside (or instead of) the
materializer's opportunistic settlement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plv_clone.decisions.logger import is_pairable as _CF_is_pairable  # noqa: E402
from plv_clone.decisions.logger import is_executed_record as _CF_is_executed  # noqa: E402
from plv_clone.decisions.counterfactual import mark_ungradeable as _CF_mark_ungradeable  # noqa: E402
from plv_clone.decisions import (  # noqa: E402
    DECISIONS_ROOT,
    DecisionRecord,
    SETTLEMENT_WINDOWS,
    settle_decision,
)
from plv_clone.fantasy.scoring import LeagueScoring  # noqa: E402

# Canonical BrownU scorer (defaults match the league formula).
_SCORING = LeagueScoring()

# Default I/O roots (override-able for tests).
DEFAULT_DECISIONS_ROOT = Path(DECISIONS_ROOT)
SETTLED_SUBDIR = "settled"  # parallel tree under the decisions root


# ---------------------------------------------------------------------------
# Atomic write (mirrors logger._atomic_write_json so we don't import a private)
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Disk walk — load source records, skipping the settled/ tree
# ---------------------------------------------------------------------------


def _settled_root(root: Path) -> Path:
    return root / SETTLED_SUBDIR


def _settled_path(root: Path, rec: DecisionRecord) -> Path:
    return _settled_root(root) / rec.snapshot_date / f"{rec.decision_id}.json"


def _load_source_records(root: Path) -> list[DecisionRecord]:
    """Load every DecisionRecord under {root}/{YYYY-MM-DD}/*.json.

    Skips the parallel settled/ tree so we never double-count.
    """
    if not root.exists():
        return []
    settled_root = _settled_root(root).resolve()
    records: list[DecisionRecord] = []
    for json_path in sorted(root.rglob("*.json")):
        try:
            if settled_root in json_path.resolve().parents:
                continue  # skip the settled/ mirror
        except OSError:
            pass
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  WARN corrupt JSON skipped: {json_path}")
            continue
        try:
            records.append(DecisionRecord(**payload))
        except TypeError as exc:
            print(f"  WARN schema mismatch skipped {json_path.name}: {exc}")
    return records


def _load_existing_settlement(root: Path, rec: DecisionRecord) -> Optional[DecisionRecord]:
    """If a settled mirror already exists for this id, load it (idempotency).

    The mirror may carry a residual `settlement`, a paired
    `counterfactual_settlement`, or both — callers decide which question the
    mirror actually answers (a paired-only mirror leaves the residual open).
    """
    p = _settled_path(root, rec)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        prior = DecisionRecord(**payload)
    except (json.JSONDecodeError, TypeError):
        return None
    return prior if prior.settled_at else None


# ---------------------------------------------------------------------------
# MLB Stats API gameLog fetch (one call per player-season, cached in-run)
# ---------------------------------------------------------------------------


def _fetch_gamelog(mlbam_id: int, season: int, group: str) -> Optional[list[dict]]:
    """Pull a season gameLog from the MLB Stats API for `group` in {hitting,pitching}.

    Returns one dict per game with the box-score fields the BrownU scorer
    needs.

    Returns **None** when the fetch itself failed, and a (possibly empty)
    list when it succeeded. Those used to be the same value — [] — which
    collapsed "the API did not answer" into "this player did not play". The
    settlement layer then graded a decision against data it never received.
    (Fixed 2026-08-27.)
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}"
        f"/stats?stats=gameLog&season={season}&group={group}&sportId=1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read())
    except Exception as exc:
        print(f"  WARN gameLog fetch failed for {mlbam_id} {group} {season}: {exc}")
        return None
    stats_list = payload.get("stats", []) or []
    if not stats_list:
        return []   # answered, and he has no games this season
    splits = stats_list[0].get("splits", []) or []
    out: list[dict] = []
    for s in splits:
        stat = s.get("stat", {}) or {}
        row = {"date": s.get("date")}
        if group == "hitting":
            row.update({
                "plateAppearances": int(stat.get("plateAppearances", 0) or 0),
                "runs": int(stat.get("runs", 0) or 0),
                "totalBases": int(stat.get("totalBases", 0) or 0),
                "rbi": int(stat.get("rbi", 0) or 0),
                "baseOnBalls": int(stat.get("baseOnBalls", 0) or 0),
                "hitByPitch": int(stat.get("hitByPitch", 0) or 0),
                "stolenBases": int(stat.get("stolenBases", 0) or 0),
                "strikeOuts": int(stat.get("strikeOuts", 0) or 0),
            })
        else:  # pitching
            row.update({
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
        out.append(row)
    return out


def _games_in_window(games: list[dict], start: date, end: date) -> list[dict]:
    out = []
    for g in games:
        d = g.get("date")
        if not d:
            continue
        try:
            gd = date.fromisoformat(d)
        except ValueError:
            continue
        if start <= gd <= end:
            out.append(g)
    return out


# ---------------------------------------------------------------------------
# Per-bucket actuals in BrownU FP/unit
# ---------------------------------------------------------------------------


def _hitter_actuals(games: list[dict], start: date, end: date) -> Optional[tuple[int, float]]:
    """(n_pa, fp_per_pa) over the window from the hitting gameLog."""
    window = _games_in_window(games, start, end)
    n_pa = sum(g.get("plateAppearances", 0) for g in window)
    if n_pa <= 0:
        return None
    total_fp = sum(_SCORING.score_hitter_game(g) for g in window)
    return n_pa, total_fp / n_pa


def _sp_actuals(games: list[dict], start: date, end: date) -> Optional[tuple[int, float]]:
    """(n_starts, fp_per_start) over the window (gamesStarted==1)."""
    starts = [g for g in _games_in_window(games, start, end) if g.get("gamesStarted", 0) == 1]
    if not starts:
        return None
    total_fp = sum(_SCORING.score_pitcher_start(g) for g in starts)
    return len(starts), total_fp / len(starts)


def _rp_actuals(games: list[dict], start: date, end: date) -> Optional[tuple[int, float]]:
    """(n_appearances, fp_per_app) over the window (gamesStarted==0), incl SV/HLD."""
    apps = [g for g in _games_in_window(games, start, end) if g.get("gamesStarted", 0) == 0]
    if not apps:
        return None
    total_fp = sum(_SCORING.score_pitcher_relief(g) for g in apps)
    return len(apps), total_fp / len(apps)


# ---------------------------------------------------------------------------
# Settlement orchestration
# ---------------------------------------------------------------------------


def _ripe(rec: DecisionRecord, today: date) -> bool:
    """True iff the settlement window has fully elapsed for this record.

    'Ripe' = time gate passed (today >= snapshot + window_days). It does NOT
    guarantee enough events — that second gate is enforced inside
    settle_decision. We report ripe-but-still-pending separately.
    """
    if rec.bucket not in SETTLEMENT_WINDOWS:
        return False
    snap = date.fromisoformat(rec.snapshot_date)
    if snap.year == 2020:
        return False  # repo-wide 2020 hygiene exclusion
    window_end = snap + timedelta(days=SETTLEMENT_WINDOWS[rec.bucket]["days"])
    return today >= window_end


def _totals_in_window(mlbam: int, bucket: str, start: date, end: date,
                       gamelog_cache: dict) -> tuple[Optional[float], int]:
    """(total_fp, n_events) over [start, end] — the PAIRED-settlement metric.

    Total rather than per-unit, deliberately: a decision includes the playing time
    you chose, so a player who was hurt or benched should score 0, not be dropped
    as unsettleable. See plv_clone.decisions.counterfactual for the full argument.

    That is now what actually happens. This used to return None whenever `rel`
    was empty, which is the hurt-or-benched case the docstring above says
    should score 0 — so the code contradicted its own contract. None is
    reserved for a FAILED LOOKUP; a successful lookup with no relevant games
    returns a real 0.0. (Fixed 2026-08-27.)
    """
    group = "hitting" if bucket == "H" else "pitching"
    key = (int(mlbam), start.year, group)
    if key not in gamelog_cache:
        gamelog_cache[key] = _fetch_gamelog(int(mlbam), start.year, group)
    log = gamelog_cache[key]
    if log is None:
        return None, 0          # the fetch failed — nothing to grade against
    games = _games_in_window(log, start, end)
    if bucket == "H":
        rel = games
        total = sum(_SCORING.score_hitter_game(g) for g in rel)
        n = sum(g.get("plateAppearances", 0) for g in rel)
    elif bucket == "SP":
        rel = [g for g in games if g.get("gamesStarted", 0) == 1]
        total = sum(_SCORING.score_pitcher_start(g) for g in rel)
        n = len(rel)
    else:
        rel = [g for g in games if g.get("gamesStarted", 0) == 0]
        total = sum(_SCORING.score_pitcher_relief(g) for g in rel)
        n = len(rel)
    if not rel:
        # Fetched successfully; he simply did not appear in the window. That
        # is a real zero and part of what was chosen — not missing data.
        return 0.0, 0
    return float(total), int(n)


def _rejected_mlbam(cf: dict):
    """The rejected candidate's MLBAM id, resolving from the NAME when the id
    is absent (issue #54, step 2).

    A counterfactual written without `rejected_mlbam` used to skip the lookup
    entirely, so the pair could never close — a permanently unpairable record
    that looks identical to one still waiting for its window. Of the
    counterfactuals on disk at 2026-08-28, 3 of 10 lacked the id while 2 of
    those 3 carried a perfectly resolvable name.

    Resolution goes through the collision-safe resolvers (don't-do #10), which
    refuse to guess on an ambiguous name rather than silently grabbing the
    wrong same-name player — a wrong rejected leg would grade the DECISION
    wrong, not just report a missing number. An unresolvable name returns None
    and the pair settles UNSETTLEABLE, which is the honest outcome.
    """
    rid = cf.get("rejected_mlbam")
    if rid:
        return rid
    name = cf.get("rejected_name")
    if not name:
        return None
    bucket = (cf.get("rejected_bucket") or "").upper()
    try:
        from plv_clone.utils.name_match import (
            resolve_batter_id, resolve_pitcher_id,
        )
        if bucket == "H":
            return resolve_batter_id(name)
        if bucket in {"SP", "RP"}:
            return resolve_pitcher_id(name, role=bucket)
        # Unknown bucket: try the hitter table, then the pitcher tables.
        return resolve_batter_id(name) or resolve_pitcher_id(name)
    except Exception:
        return None


def _settle_counterfactual_one(rec: DecisionRecord, today: date,
                               gamelog_cache: dict) -> DecisionRecord:
    """Paired settlement for a v3 executed record. No-op for anything else.

    Runs ALONGSIDE the residual settlement, not instead of it: one asks whether
    the projection was right, the other whether the choice was. Reuses the same
    gamelog cache so the extra player costs at most one more API call.
    """
    from plv_clone.decisions.counterfactual import (
        settle_counterfactual, window_for, is_ripe)

    if not _CF_is_pairable(rec) or rec.counterfactual_settlement:
        return rec
    if not is_ripe(rec, today=today):
        return rec
    win = window_for(rec)
    if win is None:
        return rec
    start, end = win
    cf = rec.counterfactual or {}

    chosen_total, chosen_n = (None, 0)
    if rec.mlbam_id:
        chosen_total, chosen_n = _totals_in_window(
            int(rec.mlbam_id), rec.bucket, start, end, gamelog_cache)

    rej_total, rej_n = (None, 0)
    rej_id = _rejected_mlbam(cf)
    if rej_id:
        rej_total, rej_n = _totals_in_window(
            int(rej_id), cf.get("rejected_bucket") or rec.bucket,
            start, end, gamelog_cache)

    return settle_counterfactual(
        rec, today=today, chosen_total_fp=chosen_total,
        rejected_total_fp=rej_total,
        n_events_chosen=chosen_n, n_events_rejected=rej_n)


def _merge_paired_into_mirror(
    prior: Optional[DecisionRecord], rec: DecisionRecord
) -> DecisionRecord:
    """The record to persist after a paired settlement lands on `rec`.

    Merge INTO any existing mirror so a prior residual `settlement` is never
    clobbered by the paired write; with no mirror, `rec` (source record +
    paired block) is the mirror.
    """
    if prior is None:
        return rec
    return replace(
        prior,
        counterfactual_settlement=rec.counterfactual_settlement,
        settled_at=prior.settled_at or rec.settled_at,
    )


def _settle_prediction_one(rec: DecisionRecord, today: date,
                           gamelog_cache: dict) -> DecisionRecord:
    """Resolve a v4 falsifiable claim. No-op for anything else.

    A third, independent question alongside residual and paired settlement:
    not "was the projection right" or "was the choice right", but "was the
    stated claim right". Gated on the claim's OWN horizon, not the bucket
    settlement window, because the horizon was part of what was promised.
    """
    from plv_clone.decisions.prediction import is_ripe, settle_prediction

    pred = getattr(rec, "prediction", None)
    if not pred or rec.prediction_settlement:
        return rec
    if not is_ripe(pred, today):
        return rec
    if not rec.mlbam_id:
        return replace(rec, prediction_settlement={
            "status": "UNSETTLEABLE", "settled_on": today.isoformat(),
            "note": "record carries no mlbam id"})

    start = date.fromisoformat(rec.snapshot_date)
    end = date.fromisoformat(pred["horizon_end"])
    realized, n = _totals_in_window(rec.mlbam_id, rec.bucket, start, end,
                                    gamelog_cache)
    # A player who never appeared scored zero; that settles, it does not excuse.
    # _totals_in_window signals "no games" and "no data" identically, so an
    # empty window is read as 0.0 rather than left unsettleable.
    realized = 0.0 if realized is None else realized

    comp = None
    if pred.get("metric") == "fp_margin_vs":
        vs_id = pred.get("vs_mlbam")
        if vs_id:
            vs_bucket = pred.get("vs_bucket") or rec.bucket
            comp, _ = _totals_in_window(int(vs_id), vs_bucket, start, end,
                                        gamelog_cache)
            comp = 0.0 if comp is None else comp

    out = settle_prediction(pred, realized=realized, comparator_realized=comp,
                            n_events=n, today=today)
    return replace(rec, prediction_settlement=out,
                   settled_at=rec.settled_at or today.isoformat())


def _merge_prediction_into_mirror(
    prior: Optional[DecisionRecord], rec: DecisionRecord
) -> DecisionRecord:
    """Persist a prediction grade without clobbering other settlement blocks."""
    if prior is None:
        return rec
    return replace(
        prior,
        prediction=prior.prediction or rec.prediction,
        prediction_settlement=rec.prediction_settlement,
        settled_at=prior.settled_at or rec.settled_at,
    )


def _settle_one(
    rec: DecisionRecord, today: date, gamelog_cache: dict
) -> tuple[DecisionRecord, str]:
    """Try to settle one ripe record. Returns (record, status).

    status in {SETTLED, PENDING_EVENTS, PENDING_NO_ACTUAL, PENDING_NO_ID}.
    The caller has already confirmed _ripe(rec, today).
    """
    if rec.mlbam_id is None:
        return rec, "PENDING_NO_ID"

    snap = date.fromisoformat(rec.snapshot_date)
    window = SETTLEMENT_WINDOWS[rec.bucket]
    window_end = snap + timedelta(days=window["days"])
    group = "hitting" if rec.bucket == "H" else "pitching"

    cache_key = (int(rec.mlbam_id), snap.year, group)
    if cache_key not in gamelog_cache:
        gamelog_cache[cache_key] = _fetch_gamelog(int(rec.mlbam_id), snap.year, group)
    games = gamelog_cache[cache_key] or []   # None (fetch failed) -> no data

    if rec.bucket == "H":
        actuals = _hitter_actuals(games, snap, window_end)
    elif rec.bucket == "SP":
        actuals = _sp_actuals(games, snap, window_end)
    else:  # RP
        actuals = _rp_actuals(games, snap, window_end)

    if actuals is None:
        return rec, "PENDING_NO_ACTUAL"

    n_events, actual = actuals
    settled = settle_decision(
        rec, today=today, actual_fp_per_unit=actual, n_events=n_events
    )
    if settled.settlement is None:
        # Time gate passed but settle_decision declined — almost always the
        # event-count gate (n_events < min_events) or a missing proj_per.
        # Gate on `settlement`, not `settled_at`: a paired (counterfactual)
        # settlement pre-sets settled_at, and that must never be mistaken for
        # a residual settlement.
        return settled, "PENDING_EVENTS"
    return settled, "SETTLED"


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

_CLASS_ORDER = [
    "BUY_HIT", "BUY_MISS", "FADE_HIT", "FADE_MISS",
    "HOLD_NEUTRAL", "CAUTION_NEUTRAL", "MIXED_NEUTRAL",
]


def _build_scorecard(
    settled: list[DecisionRecord],
    pending_count: int,
    ripe_pending_count: int,
    today: date,
) -> tuple[list[dict], str]:
    """Return (csv_rows, markdown_text)."""
    # Per-classification counts.
    class_counts: dict[str, int] = defaultdict(int)
    # Per-bucket directional hit-rate (BUY/FADE only; neutrals excluded).
    bucket_dir: dict[str, dict[str, int]] = defaultdict(lambda: {"hit": 0, "total": 0})
    for r in settled:
        cls = (r.settlement or {}).get("classification")
        if not cls:
            continue
        class_counts[cls] += 1
        if cls in ("BUY_HIT", "BUY_MISS", "FADE_HIT", "FADE_MISS"):
            bucket_dir[r.bucket]["total"] += 1
            if cls.endswith("_HIT"):
                bucket_dir[r.bucket]["hit"] += 1

    # CSV rows: one per classification bucket + the pending lines.
    csv_rows: list[dict] = []
    for cls in _CLASS_ORDER:
        if class_counts.get(cls, 0):
            csv_rows.append({"metric": "classification",
                             "key": cls,
                             "value": class_counts[cls]})
    # Any classification not in the canonical order (future-proof).
    for cls, n in sorted(class_counts.items()):
        if cls not in _CLASS_ORDER:
            csv_rows.append({"metric": "classification", "key": cls, "value": n})
    for bkt in ("H", "SP", "RP"):
        d = bucket_dir.get(bkt)
        if d and d["total"]:
            rate = d["hit"] / d["total"]
            csv_rows.append({"metric": "hit_rate_by_bucket",
                             "key": bkt,
                             "value": f"{d['hit']}/{d['total']} ({rate:.0%})"})
    csv_rows.append({"metric": "pending", "key": "total_pending",
                     "value": pending_count})
    csv_rows.append({"metric": "pending", "key": "ripe_but_pending_events",
                     "value": ripe_pending_count})
    csv_rows.append({"metric": "summary", "key": "settled_total",
                     "value": len(settled)})

    # Markdown.
    total_dir = sum(d["total"] for d in bucket_dir.values())
    total_hit = sum(d["hit"] for d in bucket_dir.values())
    lines = [
        f"# Decision Scorecard — {today.isoformat()}",
        "",
        f"- Settled records: **{len(settled)}**",
        f"- Pending (window not elapsed or too few events): **{pending_count}**",
        f"  - of which RIPE (time elapsed) but waiting on events/actuals: "
        f"**{ripe_pending_count}**",
        "",
        "## Classifications",
        "",
        "| classification | count |",
        "|---|---|",
    ]
    if class_counts:
        for cls in _CLASS_ORDER:
            if class_counts.get(cls, 0):
                lines.append(f"| {cls} | {class_counts[cls]} |")
        for cls, n in sorted(class_counts.items()):
            if cls not in _CLASS_ORDER:
                lines.append(f"| {cls} | {n} |")
    else:
        lines.append("| _(none settled yet)_ | 0 |")
    lines += [
        "",
        "## Directional hit-rate by bucket (BUY/FADE only)",
        "",
        "| bucket | hits | total | rate |",
        "|---|---|---|---|",
    ]
    if total_dir:
        for bkt in ("H", "SP", "RP"):
            d = bucket_dir.get(bkt)
            if d and d["total"]:
                lines.append(
                    f"| {bkt} | {d['hit']} | {d['total']} | "
                    f"{d['hit'] / d['total']:.0%} |"
                )
        lines.append(
            f"| **ALL** | {total_hit} | {total_dir} | "
            f"{total_hit / total_dir:.0%} |"
        )
    else:
        lines.append("| _(no directional verdicts settled yet)_ | 0 | 0 | — |")
    lines.append("")
    return csv_rows, "\n".join(lines)


def _write_scorecard(
    csv_rows: list[dict], md_text: str, today: date,
    *, root: Path = DEFAULT_DECISIONS_ROOT,
) -> tuple[Path, Path]:
    out_dir = root
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"scorecard_{today.isoformat()}.csv"
    md_path = out_dir / f"scorecard_{today.isoformat()}.md"

    # CSV (atomic, no pandas dependency for a 3-column file).
    header = "metric,key,value"
    body = "\n".join(
        f"{r['metric']},{r['key']},{r['value']}" for r in csv_rows
    )
    tmp_csv = csv_path.with_suffix(".csv.tmp")
    tmp_csv.write_text(header + "\n" + body + "\n", encoding="utf-8")
    os.replace(tmp_csv, csv_path)

    tmp_md = md_path.with_suffix(".md.tmp")
    tmp_md.write_text(md_text, encoding="utf-8")
    os.replace(tmp_md, md_path)
    return csv_path, md_path


# ---------------------------------------------------------------------------
# Driver entry point
# ---------------------------------------------------------------------------


def run(*, today: date, root: Path = DEFAULT_DECISIONS_ROOT) -> dict:
    """Settle all ripe records, persist settlements, emit scorecard.

    Returns a summary dict (for tests + callers).
    """
    records = _load_source_records(root)
    settled_out: list[DecisionRecord] = []
    pending = 0
    ripe_pending = 0  # time-elapsed but waiting on events/actuals/id
    not_ripe = 0
    newly_settled = 0
    reused_settled = 0
    gamelog_cache: dict = {}

    paired_settled = 0
    prediction_settled = 0
    ungradeable_marked = 0

    for rec in records:
        # Existing settled mirror (if any), loaded FIRST so both the paired
        # step and the residual idempotency gate can consult it.
        prior = _load_existing_settlement(root, rec)

        # 0. Paired (counterfactual) settlement runs on v3 executed records and is
        #    INDEPENDENT of the residual path below — one grades the projection,
        #    the other grades the choice. Sharing gamelog_cache means the extra
        #    player costs at most one additional API call.
        #    Durable skip-gate: source JSONs are never mutated, so a grade
        #    persisted on an earlier run lives only in the mirror — adopt it
        #    instead of re-fetching game logs to recompute it every night.
        if (prior is not None and prior.counterfactual_settlement
                and not rec.counterfactual_settlement):
            # Self-heal (issue #54 verify pass): an ungradeable terminal is
            # PROVISIONAL against a repaired source record. If a late
            # reconcile (failed night, 30-day tx window) has since stamped
            # executed_at or attached a rejected_name, the record is now
            # genuinely pairable — skip adopting the ungradeable block so the
            # pairable branch below grades it for real and overwrites the
            # mirror. Graded/lookup-failure blocks are still adopted as-is.
            _prior_blk = prior.counterfactual_settlement
            if not (_prior_blk.get('ungradeable') and _CF_is_pairable(rec)):
                rec = replace(
                    rec,
                    counterfactual_settlement=_prior_blk,
                    settled_at=rec.settled_at or prior.settled_at,
                )
        if _CF_is_pairable(rec) and not rec.counterfactual_settlement:
            try:
                rec2 = _settle_counterfactual_one(rec, today, gamelog_cache)
                if rec2.counterfactual_settlement:
                    rec = rec2
                    paired_settled += 1
                    # Persist the paired grade NOW, independent of whether the
                    # residual path below can ever settle (it cannot for a
                    # name-only record) — otherwise the grade is recomputed and
                    # the game log re-fetched every night (audit C9).
                    mirror = _merge_paired_into_mirror(prior, rec)
                    _atomic_write_json(_settled_path(root, rec), asdict(mirror))
                    prior = mirror
            except Exception as exc:
                print(f'  WARN paired settlement failed for {rec.decision_id}: '
                      f'{type(exc).__name__}: {exc}')

        # 0.25 Terminal ungradeable marking (issue #54's structural half): an
        #      executed record that is NOT pairable can never be graded — no
        #      surface was attached, no same-bucket rival existed, or the move
        #      never got an execution stamp. Without a terminal block those
        #      records look "awaiting window" forever and are re-walked
        #      nightly. mark_ungradeable is a no-op inside the attribution
        #      horizon (reconcile can still retro-attach a surface), so a
        #      fresh move is never foreclosed. No network on this path.
        if (_CF_is_executed(rec) and not _CF_is_pairable(rec)
                and not rec.counterfactual_settlement):
            rec4 = _CF_mark_ungradeable(rec, today=today)
            if rec4.counterfactual_settlement:
                rec = rec4
                ungradeable_marked += 1
                mirror = _merge_paired_into_mirror(prior, rec)
                _atomic_write_json(_settled_path(root, rec), asdict(mirror))
                prior = mirror

        # 0.5 Prediction (v4) settlement — the third independent question:
        #     was the stated CLAIM right? Gated on the claim's own horizon,
        #     and persisted immediately for the same reason as the paired
        #     block: the source JSON is never mutated, so an unpersisted
        #     grade would be recomputed (and re-fetched) every night.
        if (prior is not None and getattr(prior, 'prediction_settlement', None)
                and not rec.prediction_settlement):
            rec = replace(rec,
                          prediction_settlement=prior.prediction_settlement,
                          settled_at=rec.settled_at or prior.settled_at)
        if getattr(rec, 'prediction', None) and not rec.prediction_settlement:
            try:
                rec3 = _settle_prediction_one(rec, today, gamelog_cache)
                if rec3.prediction_settlement:
                    rec = rec3
                    prediction_settled += 1
                    mirror = _merge_prediction_into_mirror(prior, rec)
                    _atomic_write_json(_settled_path(root, rec), asdict(mirror))
                    prior = mirror
            except Exception as exc:
                print(f'  WARN prediction settlement failed for '
                      f'{rec.decision_id}: {type(exc).__name__}: {exc}')

        # 1. Idempotency: reuse an existing RESIDUAL settlement if present.
        #    A paired-only mirror (settlement=None) must NOT short-circuit —
        #    the residual question is still open and is retried nightly, and
        #    counting it here would inflate the classified total.
        if prior is not None and prior.settlement is not None:
            settled_out.append(prior)
            reused_settled += 1
            continue

        # 2. Unknown bucket / 2020 / not ripe yet -> pending, no network.
        if not _ripe(rec, today):
            pending += 1
            not_ripe += 1
            continue

        # 3. Ripe: pull actuals and try to settle.
        settled, status = _settle_one(rec, today, gamelog_cache)
        if status == "SETTLED":
            _atomic_write_json(_settled_path(root, settled), asdict(settled))
            settled_out.append(settled)
            newly_settled += 1
        else:
            pending += 1
            ripe_pending += 1

    csv_rows, md_text = _build_scorecard(
        settled_out, pending, ripe_pending, today
    )
    csv_path, md_path = _write_scorecard(csv_rows, md_text, today, root=root)

    summary = {
        "total_records": len(records),
        "settled_total": len(settled_out),
        "newly_settled": newly_settled,
        "reused_settled": reused_settled,
        "paired_settled": paired_settled,
        "prediction_settled": prediction_settled,
        "ungradeable_marked": ungradeable_marked,
        "pending": pending,
        "ripe_but_pending": ripe_pending,
        "not_ripe": not_ripe,
        "scorecard_csv": str(csv_path),
        "scorecard_md": str(md_path),
    }
    print(
        f"  settled {len(settled_out)} ({newly_settled} new, "
        f"{reused_settled} reused) | "
        f"paired {paired_settled} new | "
        f"ungradeable {ungradeable_marked} marked | "
        f"predictions {prediction_settled} new | "
        f"pending {pending} ({not_ripe} not-ripe, "
        f"{ripe_pending} ripe-waiting-events)"
    )
    print(f"  RIPE this run: {newly_settled + ripe_pending} | "
          f"NOT-RIPE (window not elapsed): {not_ripe}")
    print(f"  scorecard -> {csv_path}")
    print(f"            -> {md_path}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--today",
        default=date.today().isoformat(),
        help="ISO date treated as 'today' for settlement-window math.",
    )
    ap.add_argument("--root", default=str(DEFAULT_DECISIONS_ROOT),
                    help="Decisions root (default: data/research/decisions).")
    args = ap.parse_args()
    today = datetime.fromisoformat(args.today).date()
    run(today=today, root=Path(args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
