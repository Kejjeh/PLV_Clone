"""Behavioral tests for scripts/xfp/reconcile_decisions.py — ledger-loop honesty.

The reconciler closes the decision-ledger loop: executed ESPN transactions are
joined back to the dpwin surface that motivated them. These tests lock the
three contracts from the 2026-07-30 production audit:

  C3   the bucket comes from the surface / collision-safe resolvers /
       projection-map membership — never from the always-empty transactions
       ``position`` column, and never defaults to 'H'
  C8   a move is graded only against a surface generated BEFORE it
  C11  the nightly pipeline actually runs the reconciler, and an executed
       transaction stamps ``executed_at`` onto a matching open v3 record
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import reconcile_decisions as RD  # noqa: E402


YDAY = (date.today() - timedelta(days=1)).isoformat()


def _ts_ms(day: date, hour: int, minute: int = 0) -> int:
    return int(datetime.combine(day, dtime(hour, minute)).timestamp() * 1000)


def _hist_row(run_id, snapshot, name, mlbam, bucket, dpwin, generated_at=None):
    return {
        "run_id": run_id,
        "generated_at": generated_at or f"{snapshot}T12:00:00",
        "snapshot_date": snapshot, "engine_version": 1, "period": 17,
        "regime": "CLOSE", "base_pwin": 0.42, "my_score": 90.0,
        "opp_score": 100.0, "days_remaining": 4, "cap_remaining_mine": 7,
        "sims": 1000, "seed": 7, "move_type": "add",
        "add_name": name, "add_mlbam": mlbam, "add_bucket": bucket,
        "drop_name": None, "drop_mlbam": 0, "drop_bucket": None,
        "start_date": "", "dpwin": dpwin, "pwin_scenario": 0.45,
        "mc_se": 0.005, "dtitle_pp_per_win": 0.88,
        "dtitle_equity_pp": round(dpwin * 0.88, 4),
        "rank_in_run": 1, "candidate_source": "optimizer:round1",
    }


def _tx_row(name, *, ts_ms, action="FA ADDED", position="", mlbam=None):
    """A transactions_history row as it actually looks live: position is
    EMPTY-STRING (all 410 live rows) and mlbam_id is NaN."""
    return {
        "date": date.today(), "ts_ms": ts_ms, "team_id": "1",
        "team_name": "New York Ligers", "action_str": action,
        "player_name": name, "position": position, "pro_team": "Tex",
        "espn_player_id": 1, "mlbam_id": mlbam,
    }


def _write(tmp_path, hist_rows, tx_rows):
    hp = tmp_path / "dpwin.parquet"
    pd.DataFrame(hist_rows).to_parquet(hp, index=False)
    tp = tmp_path / "tx.parquet"
    pd.DataFrame(tx_rows).to_parquet(tp, index=False)
    return hp, tp


# ── C3: bucket honesty ───────────────────────────────────────────────────────

def test_blank_position_pitcher_add_lands_in_sp_bucket_with_sp_counterfactual(tmp_path):
    """An executed pitcher add whose transactions ``position`` is blank (as it
    is for EVERY live row) lands in the SP bucket via the matched dpwin row,
    draws its rejected alternative from SP candidates, and grades on the
    pitching window — never defaulting to 'H' + a hitter counterfactual."""
    hist = [
        _hist_row("r_yday", YDAY, "Zeb Fakepitcher", 900001, "SP", 0.050),
        _hist_row("r_yday", YDAY, "Alt Spguy", 900002, "SP", 0.040),
        _hist_row("r_yday", YDAY, "Big Hitterman", 900003, "H", 0.090),
    ]
    tx = [_tx_row("Zeb Fakepitcher", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     verbose=False)
    assert s["events"] == 1 and s["unattributed"] == 0
    rec = s["records"][0]
    assert rec.bucket == "SP"
    assert rec.counterfactual["rejected_name"] == "Alt Spguy"
    assert rec.counterfactual["rejected_bucket"] == "SP"
    # "grades on the pitching log": SP routes to the 35d pitching window,
    # not the 21d hitter window.
    from plv_clone.decisions import counterfactual as CF
    start, end = CF.window_for(rec)
    assert (end - start).days == 35


def test_unresolvable_bucket_makes_the_move_unattributable_never_h(tmp_path, monkeypatch):
    """When neither the surface, the collision-safe resolvers, nor the
    projection maps can bucket the player, the move is counted unattributable
    with no record written — a defaulted 'H' would hand a pitcher a hitter
    counterfactual and a hitter game log."""
    for attr in ("RP3_CSV", "RPRS2_CSV", "RH3_CSV"):
        monkeypatch.setattr(RD, attr, tmp_path / f"missing_{attr}.csv",
                            raising=False)
    hist = [_hist_row("r_yday", YDAY, "Big Hitterman", 900003, "H", 0.090)]
    tx = [_tx_row("Total Mysteryperson", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     verbose=False)
    assert s["records"] == []
    assert s["no_bucket"] == 1
    assert s["unattributed"] == 1


def test_off_surface_player_buckets_via_projection_map_membership(tmp_path, monkeypatch):
    """An executed add the surface never scored still gets a bucket when the
    name appears in a projection map: rprs2 membership -> RP, rp3 membership
    (stored 'Last, First') -> SP."""
    monkeypatch.setattr(RD, "RP3_CSV", tmp_path / "rp3.csv", raising=False)
    monkeypatch.setattr(RD, "RPRS2_CSV", tmp_path / "rprs2.csv", raising=False)
    monkeypatch.setattr(RD, "RH3_CSV", tmp_path / "rh3.csv", raising=False)
    pd.DataFrame({"pitcher": [900011], "name_api": ["Relief Fakearm"]}
                 ).to_csv(tmp_path / "rprs2.csv", index=False)
    pd.DataFrame({"pitcher": [900012], "player_name": ["Fakestarter, Zeb"]}
                 ).to_csv(tmp_path / "rp3.csv", index=False)

    hist = [_hist_row("r_yday", YDAY, "Someone Else", 900003, "H", 0.090)]
    tx = [_tx_row("Relief Fakearm", ts_ms=_ts_ms(date.today(), 9)),
          _tx_row("Zeb Fakestarter", ts_ms=_ts_ms(date.today(), 9, 30))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     verbose=False)
    assert s["no_bucket"] == 0
    by_name = {r.player_name: r for r in s["records"]}
    assert by_name["Relief Fakearm"].bucket == "RP"
    assert by_name["Zeb Fakestarter"].bucket == "SP"
    assert by_name["Relief Fakearm"].inputs["bucket_source"] == "projection_map"


# ── C8: no hindsight — the surface must PRE-DATE the move ────────────────────

def test_move_attributes_only_to_a_run_generated_before_it(tmp_path):
    """With runs at 00:30 and 10:42 and a 09:00 transaction, attribution goes
    to the 00:30 run — the 10:42 surface did not exist when Josh clicked."""
    today = date.today().isoformat()
    run_early = f"{today}T003000_7"
    run_late = f"{today}T104200_7"
    hist = []
    for rid, gen_hm in ((run_early, "00:30:00"), (run_late, "10:42:00")):
        hist += [
            _hist_row(rid, today, "Timing Guy", 900021, "H", 0.050,
                      generated_at=f"{today}T{gen_hm}"),
            _hist_row(rid, today, "Alt Guy", 900022, "H", 0.040,
                      generated_at=f"{today}T{gen_hm}"),
        ]
    tx = [_tx_row("Timing Guy", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     verbose=False)
    assert s["unattributed"] == 0
    rec = s["records"][0]
    assert rec.counterfactual["source_run_id"] == run_early


def test_move_is_unattributed_when_every_run_postdates_it(tmp_path):
    """With only the 10:42 run on the books, a 09:00 transaction has no
    surface that existed before it — the honest outcome is unattributed."""
    today = date.today().isoformat()
    hist = [_hist_row(f"{today}T104200_7", today, "Timing Guy", 900021, "H",
                      0.050, generated_at=f"{today}T10:42:00")]
    tx = [_tx_row("Timing Guy", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     verbose=False)
    assert s["records"] == []
    assert s["unattributed"] == 1


# ── C11: the pipeline actually runs the reconciler ───────────────────────────

def test_refresh_pipeline_registers_reconciler_after_persist_transactions():
    """The ledger loop only closes if something schedules the reconciler: it
    must run in refresh_dashboards.py AFTER the transactions persist step
    (same producer/consumer source-order idiom as the other step tests)."""
    src = (ROOT / "scripts" / "xfp" / "refresh_dashboards.py").read_text(
        encoding="utf-8")
    assert "reconcile_decisions.py" in src
    assert src.index("persist_transactions.py") < src.index(
        "reconcile_decisions.py")


def test_reconcile_run_writes_an_executed_record_to_the_decisions_tree(tmp_path):
    """A non-dry run against a synthetic transactions+dpwin fixture lands a
    v3 executed record on disk — what the nightly registration invokes."""
    hist = [
        _hist_row("r_yday", YDAY, "Zeb Fakepitcher", 900001, "SP", 0.050),
        _hist_row("r_yday", YDAY, "Alt Spguy", 900002, "SP", 0.040),
    ]
    tx = [_tx_row("Zeb Fakepitcher", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)
    root = tmp_path / "decisions"

    s = RD.reconcile(days=10, dry_run=False, tx_path=tp, hist_path=hp,
                     root=root, verbose=False)
    assert s["created"] == 1
    files = list(root.rglob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["record_schema"] == 3
    assert payload["action"] == "add"
    assert payload["executed_at"] is not None
    assert payload["counterfactual"]["source_run_id"] == "r_yday"
    assert payload["counterfactual"]["rejected_name"] == "Alt Spguy"


def test_open_v3_record_receives_executed_at_when_its_move_executes(tmp_path):
    """Docstring step 3 made real: an OPEN v3 record (a logged decision with
    no executed_at) matching an executed transaction within the attribution
    window is stamped with the transaction's timestamp — and the reconciler
    does NOT pile a duplicate auto_reconciled record on top of it."""
    from plv_clone.decisions.logger import build_executed_record, log_decision
    root = tmp_path / "decisions"
    open_rec = build_executed_record(
        snapshot_date=YDAY, player_name="Stamp Target", mlbam_id=900031,
        bucket="H", action="add",
        rejected={"name": "Passed Guy", "mlbam": 900032, "bucket": "H"},
        dpwin_chosen=0.05, dpwin_rejected=0.04, source_run_id="r_yday")
    path = log_decision(open_rec, root=root)
    assert json.loads(path.read_text(encoding="utf-8"))["executed_at"] is None

    hist = [_hist_row("r_yday", YDAY, "Stamp Target", 900031, "H", 0.05)]
    tx = [_tx_row("Stamp Target", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=False, tx_path=tp, hist_path=hp,
                     root=root, verbose=False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["executed_at"] is not None
    assert payload["executed_at"].startswith(date.today().isoformat())
    assert s["stamped"] == 1
    assert s["created"] == 0   # the logged decision absorbs the execution


# ── review round 2 (2026-07-30): hermeticity + list-JSON + action-kind ───────

def _open_record(day_dir, fname, name, action="add"):
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / fname).write_text(json.dumps({
        "record_schema": 3, "action": action, "executed_at": None,
        "player_name": name, "mlbam_id": None,
        "snapshot_date": day_dir.name}), encoding="utf-8")


def test_reconcile_with_explicit_root_never_consults_the_live_tree(
        tmp_path, monkeypatch):
    """A reconcile run given its own root must not read the production
    decisions tree: a matching open record in the (simulated) live tree is
    invisible, so attribution proceeds instead of a phantom stamp diverting
    it. This is also what keeps every root-passing test hermetic."""
    import plv_clone.decisions.logger as logger
    live = tmp_path / "live_decisions"
    _open_record(live / YDAY, "x.json", "Zeb Fakepitcher")
    monkeypatch.setattr(logger, "DECISIONS_ROOT", live)

    hist = [
        _hist_row("r_yday", YDAY, "Zeb Fakepitcher", 900001, "SP", 0.050),
        _hist_row("r_yday", YDAY, "Alt Spguy", 900002, "SP", 0.040),
    ]
    tx = [_tx_row("Zeb Fakepitcher", ts_ms=_ts_ms(date.today(), 9))]
    hp, tp = _write(tmp_path, hist, tx)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     root=tmp_path / "my_root", verbose=False)
    assert s["stamped"] == 0, "live-tree records must be invisible"
    assert len(s["records"]) == 1


def test_stamping_survives_a_list_shaped_json_file(tmp_path):
    """The decisions tree also holds scorecard-style files whose top level is
    a LIST — the stamp scan must skip them, not crash the reconciler."""
    root = tmp_path / "root"
    day = root / YDAY
    day.mkdir(parents=True)
    (day / "scorecard.json").write_text(json.dumps([{"whatever": 1}]),
                                        encoding="utf-8")
    _open_record(day, "open.json", "Zeb Fakepitcher")
    when = datetime.combine(date.today(), dtime(9, 0))
    got = RD.stamp_open_records(name="Zeb Fakepitcher", mlbam=None,
                                when=when, root=root, dry_run=True)
    assert [p.name for p in got] == ["open.json"]


def test_stamping_matches_action_kind(tmp_path):
    """An executed ADD must not stamp a logged DROP record for the same
    player: dropping X and adding X are different decisions, and stamping
    the wrong one silently closes it as executed. A logged swap counts as
    either leg."""
    root = tmp_path / "root"
    day = root / YDAY
    _open_record(day, "drop.json", "Zeb Fakepitcher", action="drop")
    _open_record(day, "add.json", "Zeb Fakepitcher", action="add")
    _open_record(day, "swap.json", "Zeb Fakepitcher", action="swap")
    when = datetime.combine(date.today(), dtime(9, 0))
    got = RD.stamp_open_records(name="Zeb Fakepitcher", mlbam=None,
                                when=when, root=root, dry_run=True,
                                action="add")
    assert sorted(p.name for p in got) == ["add.json", "swap.json"]


def test_resolver_leg_buckets_an_off_surface_pitcher_and_refuses_two_way(
        monkeypatch):
    """Leg 2 of the C3 precedence chain, exercised POSITIVELY (the reviewer
    found only negative fall-through coverage): an off-surface name that the
    collision-safe pitcher resolver identifies — and the pitcher CSVs
    classify — buckets to SP/RP; a name resolving as BOTH pitcher and batter
    is two-way ambiguity and refuses (None), never a guess.

    NOTE on red-first: this path already existed when the test was written
    (review round 2); its red was produced by mutation — inverting the
    p_bucket gate makes it fail on both asserts — rather than by a pre-fix
    checkout. Disclosed per the collisions track's precedent."""
    monkeypatch.setattr(RD, "resolve_pitcher_id",
                        lambda name, team=None, **k: 777001)
    monkeypatch.setattr(RD, "resolve_batter_id",
                        lambda name, team=None, **k: None)
    monkeypatch.setattr(RD, "classify_pitcher_bucket",
                        lambda pid, **k: "SP")
    assert RD._bucket_via_resolver("Off Surfaceguy") == "SP"

    # two-way ambiguity: both resolvers answer -> refuse
    monkeypatch.setattr(RD, "resolve_batter_id",
                        lambda name, team=None, **k: 888001)
    assert RD._bucket_via_resolver("Two Wayguy") is None
