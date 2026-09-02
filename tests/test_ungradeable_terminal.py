"""Issue #54's structural half: never-pairable records get a TERMINAL mark.

The 2026-08-28 census found 3,091 of 3,101 executed records could never be
paired-graded (no dpwin surface attached / no same-bucket rival / no
execution stamp), yet carried no terminal state — indistinguishable from
records merely awaiting their window, re-walked nightly forever.

Pinned here:
  1. the reason taxonomy is exhaustive against is_pairable's definition;
  2. the attribution horizon: a record young enough for reconcile to still
     retro-attach a surface is NEVER marked (no foreclosure);
  3. the block shape: UNSETTLEABLE classification, ungradeable=True,
     settled_at set, and NO fp_gained — so summarize()/dpwin_resolution()
     skip it and §7-§9 are unchanged;
  4. driver integration: settle_decisions.run() writes the mirror once,
     reuses it on the second run, and touches no network on this path;
  5. the horizon constant stays in sync with reconcile_decisions.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src", ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import settle_decisions as SD  # noqa: E402
from plv_clone.decisions import counterfactual as CF  # noqa: E402
from plv_clone.decisions.logger import DecisionRecord, is_pairable  # noqa: E402

SNAP = "2026-07-01"
TODAY = date(2026, 8, 1)


def _record(**over) -> DecisionRecord:
    base = dict(
        decision_id=f"{SNAP}_test_guy_H_001",
        snapshot_date=SNAP,
        player_name="Test Guy",
        mlbam_id=111,
        bucket="H",
        verdict_top="add",
        reason_tag="test",
        confidence="high",
        inputs={},
        action="add",
        executed_at=f"{SNAP}T10:00:00",
        counterfactual=None,
    )
    base.update(over)
    return DecisionRecord(**base)


# ── 1. reason taxonomy ────────────────────────────────────────────────────

def test_reason_no_surface():
    assert CF.ungradeable_reason(_record(counterfactual=None)) == "no_surface_attached"


def test_reason_no_alternative():
    rec = _record(counterfactual={"rejected_name": None, "source_run_id": "r1"})
    assert CF.ungradeable_reason(rec) == "no_alternative_recorded"


def test_reason_no_execution_timestamp():
    rec = _record(executed_at=None,
                  counterfactual={"rejected_name": "Other Guy"})
    assert CF.ungradeable_reason(rec) == "no_execution_timestamp"


def test_pairable_record_has_no_reason():
    rec = _record(counterfactual={"rejected_name": "Other Guy"})
    assert is_pairable(rec)
    assert CF.ungradeable_reason(rec) is None
    assert CF.mark_ungradeable(rec, today=TODAY) is rec


# ── 2. attribution horizon — no foreclosure of recoverable records ────────

def test_fresh_record_is_not_marked():
    rec = _record(snapshot_date=TODAY.isoformat())
    assert CF.mark_ungradeable(rec, today=TODAY) is rec
    edge = _record(snapshot_date="2026-07-30")  # exactly HORIZON days old
    assert CF.mark_ungradeable(edge, today=TODAY) is edge


def test_old_record_is_marked():
    marked = CF.mark_ungradeable(_record(), today=TODAY)
    blk = marked.counterfactual_settlement
    assert blk["classification"] == CF.UNSETTLEABLE
    assert blk["ungradeable"] is True
    assert blk["reason"] == "no_surface_attached"
    assert "fp_gained" not in blk
    assert marked.settled_at


def test_existing_settlement_never_overwritten():
    rec = _record(counterfactual_settlement={"classification": "RIGHT_CALL",
                                             "fp_gained": 5.0})
    assert CF.mark_ungradeable(rec, today=TODAY) is rec


def test_unparseable_snapshot_date_is_left_alone():
    rec = _record(snapshot_date="not-a-date")
    assert CF.mark_ungradeable(rec, today=TODAY) is rec


# ── 3. reporting invisibility ─────────────────────────────────────────────

def test_summarize_and_resolution_skip_ungradeable_blocks():
    graded = _record(counterfactual={"rejected_name": "O", "dpwin_gap": 0.02},
                     counterfactual_settlement={
                         "classification": CF.RIGHT_CALL, "fp_gained": 8.0})
    marked = CF.mark_ungradeable(_record(), today=TODAY)
    summ = CF.summarize([graded, marked])
    assert summ["n_settled"] == 1
    res = CF.dpwin_resolution([graded, marked])
    assert res["n"] if res.get("n") else res["status"] == "EARLY_READ"


# ── 4. driver integration ─────────────────────────────────────────────────

def _write_source(root: Path, rec: DecisionRecord) -> Path:
    from dataclasses import asdict
    d = root / rec.snapshot_date
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{rec.decision_id}.json"
    p.write_text(json.dumps(asdict(rec), default=str), encoding="utf-8")
    return p


def test_run_marks_persists_and_reuses(tmp_path, monkeypatch):
    # The RESIDUAL path may legitimately fetch for a ripe record; serve it a
    # failed-lookup None. The ungradeable MARKING itself must not depend on
    # any of these calls succeeding.
    calls = []
    monkeypatch.setattr(
        SD, "_fetch_gamelog", lambda *a, **k: (calls.append(a), None)[1])

    _write_source(tmp_path, _record())
    fresh = _record(decision_id=f"{TODAY}_fresh_guy_H_001",
                    snapshot_date=TODAY.isoformat(), player_name="Fresh Guy")
    _write_source(tmp_path, fresh)

    s1 = SD.run(today=TODAY, root=tmp_path)
    assert s1["ungradeable_marked"] == 1

    mirror = tmp_path / "settled" / SNAP / f"{SNAP}_test_guy_H_001.json"
    assert mirror.exists()
    payload = json.loads(mirror.read_text(encoding="utf-8"))
    blk = payload["counterfactual_settlement"]
    assert blk["classification"] == CF.UNSETTLEABLE
    assert blk["ungradeable"] is True
    assert payload["settled_at"]

    # the fresh record was NOT foreclosed
    assert not (tmp_path / "settled" / TODAY.isoformat()
                / f"{TODAY}_fresh_guy_H_001.json").exists()

    # second run adopts the mirror instead of re-marking
    s2 = SD.run(today=TODAY, root=tmp_path)
    assert s2["ungradeable_marked"] == 0


def test_late_reconcile_repair_self_heals_the_terminal_mark(tmp_path, monkeypatch):
    """A record marked ungradeable, then repaired by a lagging reconcile
    (executed_at stamped / rejected_name attached after the horizon), must
    settle for REAL on the next run — the mirror's provisional block is not
    adopted onto a now-pairable record (verify pass 2026-09-01)."""
    def _games(mlbam_id, season, group):
        # 2 games inside the July window; chosen (111) outscores rejected (222)
        base = {"plateAppearances": 4, "runs": 1, "totalBases": 2, "rbi": 1,
                "baseOnBalls": 1, "hitByPitch": 0, "stolenBases": 0,
                "strikeOuts": 1}
        pts = 2 if int(mlbam_id) == 111 else 1
        return [dict(base, date=f"2026-07-0{d}", runs=pts) for d in (2, 3)]
    monkeypatch.setattr(SD, "_fetch_gamelog", _games)

    # Run 1: no-surface record gets terminally marked.
    _write_source(tmp_path, _record(executed_at=None, counterfactual=None))
    s1 = SD.run(today=TODAY, root=tmp_path)
    assert s1["ungradeable_marked"] == 1
    mirror = tmp_path / "settled" / SNAP / f"{SNAP}_test_guy_H_001.json"
    assert json.loads(mirror.read_text(encoding="utf-8"))[
        "counterfactual_settlement"]["ungradeable"] is True

    # Late reconcile repairs the SOURCE record: stamps execution + rival.
    _write_source(tmp_path, _record(
        executed_at=f"{SNAP}T10:00:00",
        counterfactual={"rejected_name": "Other Guy", "rejected_mlbam": 222,
                        "rejected_bucket": "H", "dpwin_gap": 0.01}))

    # Run 2: the provisional block is NOT adopted; the record grades for real.
    s2 = SD.run(today=TODAY, root=tmp_path)
    assert s2["ungradeable_marked"] == 0
    assert s2["paired_settled"] == 1
    blk = json.loads(mirror.read_text(encoding="utf-8"))[
        "counterfactual_settlement"]
    assert not blk.get("ungradeable")
    assert "fp_gained" in blk


# ── 5. constant sync ──────────────────────────────────────────────────────

def test_horizon_matches_reconcile_attribution_days():
    import reconcile_decisions as RD
    assert CF.ATTRIBUTION_HORIZON_DAYS == RD.ATTRIBUTION_DAYS, (
        "counterfactual.ATTRIBUTION_HORIZON_DAYS mirrors "
        "reconcile_decisions.ATTRIBUTION_DAYS; they drifted apart."
    )
