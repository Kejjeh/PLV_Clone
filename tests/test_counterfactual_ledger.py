"""Tests for the counterfactual decision ledger (C5 + C6).

Three components, one contract: record what was chosen AND what was passed on,
then grade the CHOICE rather than the projection.

  logger.py v3            executed-move records + the counterfactual block
  counterfactual.py       realized(chosen) - realized(rejected), pure
  reconcile_decisions.py  joins ESPN transactions to the dpwin surface

The load-bearing property is that v1/v2 records — 131 days of them — keep
parsing. A schema change that orphaned the existing ledger would destroy the
history the whole apparatus exists to accumulate.
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

from plv_clone.decisions.logger import (  # noqa: E402
    DecisionRecord, build_executed_record, build_decision_id, log_decision,
    is_executed_record, is_pairable, VALID_ACTIONS, _norm_name,
)
from plv_clone.decisions import counterfactual as CF  # noqa: E402


# ── v3 schema: backward compatibility is the whole game ──────────────────────

def test_v1_payload_still_parses():
    """131 days of records must survive the schema bump."""
    v1 = {"decision_id": "2026-03-01_max_muncy_H_001", "snapshot_date": "2026-03-01",
          "player_name": "Max Muncy", "mlbam_id": 571970, "bucket": "H",
          "verdict_top": "BUY", "reason_tag": None, "confidence": 0.6,
          "inputs": {"pl_rank": 40}}
    r = DecisionRecord(**v1)
    assert r.record_schema == 2       # legacy default
    assert r.action is None           # -> a verdict record, not an executed move
    assert not is_executed_record(r)


def test_v2_payload_still_parses():
    v2 = {"decision_id": "x", "snapshot_date": "2026-07-10", "player_name": "A",
          "mlbam_id": 1, "bucket": "SP", "verdict_top": "HOLD",
          "reason_tag": None, "confidence": None,
          "inputs": {"proj_per": 11.2, "proj_units": "fp_per_start",
                     "inputs_schema": 2},
          "settled_at": None, "settlement": None}
    r = DecisionRecord(**v2)
    assert r.counterfactual is None and r.counterfactual_settlement is None


def test_v3_roundtrips_through_json():
    r = build_executed_record(
        snapshot_date="2026-07-30", player_name="Joc Pederson", mlbam_id=592626,
        bucket="H", action="swap", executed_at="2026-07-30T09:15:00",
        rejected={"name": "Ryan Jeffers", "mlbam": 680777, "bucket": "H"},
        dpwin_chosen=0.0875, dpwin_rejected=0.0872, source_run_id="r1")
    from dataclasses import asdict
    back = DecisionRecord(**json.loads(json.dumps(asdict(r), default=str)))
    assert back.record_schema == 3 and back.action == "swap"
    assert back.counterfactual["rejected_name"] == "Ryan Jeffers"


def test_dpwin_gap_is_derived_not_passed():
    """Deriving it means it can never disagree with its own components."""
    r = build_executed_record(
        snapshot_date="2026-07-30", player_name="A", mlbam_id=1, bucket="H",
        action="add", dpwin_chosen=0.0875, dpwin_rejected=0.0800)
    assert r.counterfactual["dpwin_gap"] == pytest.approx(0.0075, abs=1e-9)


def test_invalid_action_raises():
    with pytest.raises(ValueError, match="not in"):
        build_executed_record(snapshot_date="2026-07-30", player_name="A",
                              mlbam_id=1, bucket="H", action="teleport")


def test_every_valid_action_is_accepted():
    for a in sorted(VALID_ACTIONS):
        r = build_executed_record(snapshot_date="2026-07-30", player_name="A",
                                  mlbam_id=1, bucket="H", action=a)
        assert r.action == a and r.verdict_top == a.upper()


def test_pairable_requires_both_execution_and_an_alternative():
    base = dict(snapshot_date="2026-07-30", player_name="A", mlbam_id=1,
                bucket="H", action="add")
    assert not is_pairable(build_executed_record(**base))
    assert not is_pairable(build_executed_record(
        **base, rejected={"name": "B", "mlbam": 2, "bucket": "H"}))   # no exec
    assert not is_pairable(build_executed_record(
        **base, executed_at="2026-07-30T09:00:00"))                   # no alt
    assert is_pairable(build_executed_record(
        **base, executed_at="2026-07-30T09:00:00",
        rejected={"name": "B", "mlbam": 2, "bucket": "H"}))


def test_decision_ids_are_unchanged_by_v3():
    """_norm_name builds FILESYSTEM ids, not join keys. Rewriting it would orphan
    every existing record — it must stay underscore-joined."""
    assert _norm_name("Max Muncy") == "max_muncy"
    assert build_decision_id("2026-07-30", "Max Muncy", "H") == \
        "2026-07-30_max_muncy_H_001"


def test_v3_record_writes_and_reads_from_disk(tmp_path):
    r = build_executed_record(
        snapshot_date="2026-07-30", player_name="Joc Pederson", mlbam_id=592626,
        bucket="H", action="swap", executed_at="2026-07-30T09:15:00",
        rejected={"name": "Ryan Jeffers", "mlbam": 680777, "bucket": "H"})
    p = log_decision(r, root=tmp_path)
    assert p.exists()
    back = DecisionRecord(**json.loads(p.read_text(encoding="utf-8")))
    assert back.action == "swap"


# ── paired settlement: grading the CHOICE ────────────────────────────────────

def _rec(bucket="H", executed="2026-07-01T12:00:00"):
    return build_executed_record(
        snapshot_date="2026-07-01", player_name="Chosen", mlbam_id=1,
        bucket=bucket, action="swap", executed_at=executed,
        rejected={"name": "Passed", "mlbam": 2, "bucket": bucket},
        dpwin_chosen=0.05, dpwin_rejected=0.03)


def test_window_is_common_to_both_sides():
    r = _rec("H")
    start, end = CF.window_for(r)
    assert start == date(2026, 7, 1)
    assert (end - start).days == 21          # H window
    assert (CF.window_for(_rec("SP"))[1] - date(2026, 7, 1)).days == 35


def test_not_ripe_before_the_window_closes():
    r = _rec("H")
    assert not CF.is_ripe(r, today=date(2026, 7, 20))
    assert CF.is_ripe(r, today=date(2026, 7, 22))


def test_early_settlement_is_refused_not_approximated():
    """Grading early favours whichever side happened to play first."""
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 10),
                                   chosen_total_fp=50, rejected_total_fp=10)
    assert out.counterfactual_settlement is None


def test_right_call_when_chosen_clearly_outproduces():
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=60.0, rejected_total_fp=30.0,
                                   n_events_chosen=80, n_events_rejected=70)
    blk = out.counterfactual_settlement
    assert blk["fp_gained"] == pytest.approx(30.0)
    assert blk["classification"] == CF.RIGHT_CALL


def test_wrong_call_when_the_alternative_wins():
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=20.0, rejected_total_fp=45.0,
                                   n_events_chosen=80, n_events_rejected=70)
    assert out.counterfactual_settlement["classification"] == CF.WRONG_CALL


def test_wash_inside_the_threshold_band():
    """Ordinary noise must not be graded as skill."""
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=40.0, rejected_total_fp=35.0,
                                   n_events_chosen=80, n_events_rejected=70)
    assert out.counterfactual_settlement["classification"] == CF.WASH


def test_a_rejected_player_who_never_played_scores_zero_not_missing():
    """THE design decision: playing time is part of what you chose. If the
    alternative got hurt or benched, that is the decision paying off — not a
    missing value to discard.

    UNCHANGED as a rule; only how "never played" reaches here changed.
    It used to arrive as ``None``, which ALSO meant "the gamelog lookup
    failed" — so a decision with no data behind it was graded a RIGHT_CALL
    with the full fp_gained. `_totals_in_window` now returns a real 0.0 for a
    successful lookup with no games in the window, and reserves None for a
    failed fetch (2026-08-27). The behaviour this test pins is identical."""
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=35.0, rejected_total_fp=0.0,
                                   n_events_chosen=80, n_events_rejected=0)
    blk = out.counterfactual_settlement
    assert blk["rejected_total_fp"] == 0.0
    assert blk["rejected_never_played"] is True
    assert blk["fp_gained"] == pytest.approx(35.0)
    assert blk["classification"] == CF.RIGHT_CALL


def test_a_failed_rejected_lookup_is_unsettleable_not_a_free_win():
    """The case that used to be indistinguishable from "never played".

    A None on the rejected side means the gamelog fetch failed. Coercing it
    to 0.0 credited the chosen player with the entire fp_gained and graded a
    decision we have no data for as RIGHT_CALL — a bias pointing one way, on
    the side issue #54 established is usually an unrostered FA.
    """
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=35.0, rejected_total_fp=None,
                                   n_events_chosen=80, n_events_rejected=0)
    blk = out.counterfactual_settlement
    assert blk["classification"] == CF.UNSETTLEABLE
    assert blk["lookup_failed_side"] == "rejected"
    assert "fp_gained" not in blk, "a failed lookup must not report a gain"


def test_a_failed_lookup_on_both_sides_names_both():
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=None, rejected_total_fp=None,
                                   n_events_chosen=0, n_events_rejected=0)
    assert out.counterfactual_settlement["lookup_failed_side"] == "both"


def test_a_chosen_player_with_no_events_is_unsettleable_not_wrong():
    """"he did not play" must not be confused with "the alternative won"."""
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=None, rejected_total_fp=20.0,
                                   n_events_chosen=0, n_events_rejected=60)
    blk = out.counterfactual_settlement
    assert blk["classification"] == CF.UNSETTLEABLE
    assert blk["low_sample"] is True
    assert "fp_gained" not in blk


def test_low_sample_flags_but_does_not_gate():
    out = CF.settle_counterfactual(_rec("H"), today=date(2026, 7, 25),
                                   chosen_total_fp=12.0, rejected_total_fp=2.0,
                                   n_events_chosen=5, n_events_rejected=4)
    blk = out.counterfactual_settlement
    assert blk["low_sample"] is True
    assert blk["fp_gained"] == pytest.approx(10.0)     # still scored


def test_unpairable_record_is_left_untouched():
    r = build_executed_record(snapshot_date="2026-07-01", player_name="A",
                              mlbam_id=1, bucket="H", action="add")
    out = CF.settle_counterfactual(r, today=date(2026, 8, 30),
                                   chosen_total_fp=99, rejected_total_fp=1)
    assert out.counterfactual_settlement is None


def test_residual_settlement_and_paired_settlement_coexist():
    """They answer different questions and neither replaces the other."""
    r = _rec("H")
    r = r.__class__(**{**r.__dict__, "settlement": {"classification": "BUY_HIT"}})
    out = CF.settle_counterfactual(r, today=date(2026, 7, 25),
                                   chosen_total_fp=60.0, rejected_total_fp=20.0,
                                   n_events_chosen=80, n_events_rejected=70)
    assert out.settlement["classification"] == "BUY_HIT"
    assert out.counterfactual_settlement["classification"] == CF.RIGHT_CALL


def test_thresholds_scale_with_the_bucket():
    assert CF.classify(9.0, "H") == CF.WASH        # under 10
    assert CF.classify(9.0, "SP") == CF.RIGHT_CALL  # over 8
    assert CF.classify(-6.0, "RP") == CF.WRONG_CALL  # under -5


# ── aggregation + resolution ─────────────────────────────────────────────────

def _settled(bucket, chosen, rejected, gap=0.01):
    r = build_executed_record(
        snapshot_date="2026-07-01", player_name="C", mlbam_id=1, bucket=bucket,
        action="swap", executed_at="2026-07-01T12:00:00",
        rejected={"name": "P", "mlbam": 2, "bucket": bucket},
        dpwin_chosen=gap, dpwin_rejected=0.0)
    return CF.settle_counterfactual(r, today=date(2026, 9, 1),
                                    chosen_total_fp=chosen,
                                    rejected_total_fp=rejected,
                                    n_events_chosen=80, n_events_rejected=80)


def test_summarize_reports_cumulative_fp_versus_the_road_not_taken():
    recs = [_settled("H", 60, 20), _settled("H", 10, 40), _settled("SP", 30, 28)]
    s = CF.summarize(recs)
    assert s["n_settled"] == 3
    assert s["total_fp_gained"] == pytest.approx(40 - 30 + 2)
    assert s["by_bucket"]["H"]["RIGHT_CALL"] == 1
    assert s["by_bucket"]["H"]["WRONG_CALL"] == 1
    assert s["by_bucket"]["SP"]["WASH"] == 1


def test_summarize_ignores_unsettled_records():
    assert CF.summarize([_rec("H")])["n_settled"] == 0


def test_dpwin_resolution_is_an_early_read_below_power():
    out = CF.dpwin_resolution([_settled("H", 60, 20) for _ in range(5)])
    assert out["status"] == "EARLY_READ"
    assert "need 30" in out["note"]


def test_dpwin_resolution_computes_terciles_once_powered():
    recs = [_settled("H", 40 + i, 20, gap=i / 1000) for i in range(36)]
    out = CF.dpwin_resolution(recs)
    assert out["status"] == "OK"
    assert len(out["tercile_win_rates"]) == 3
    assert isinstance(out["monotone"], bool)


# ── reconciler ───────────────────────────────────────────────────────────────

def _tx_ts_ms(hour: int = 9) -> int:
    """Epoch-ms for *hour*:00 today — consistent with a tx dated today.

    find_run compares the run's generated_at against the transaction's REAL
    timestamp (C8: a surface generated later the same day must not explain an
    earlier click), so fixtures must carry a ts_ms that matches the date they
    claim."""
    return int(datetime.combine(date.today(), dtime(hour, 0)).timestamp() * 1000)


def _hist_row(run_id, snapshot, name, mlbam, bucket, dpwin):
    return {
        "run_id": run_id, "generated_at": f"{snapshot}T12:00:00",
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


def test_reconciler_attributes_a_move_and_picks_the_passed_on_alternative(tmp_path):
    """The happy path: an executed add joins the surface that preceded it, and the
    counterfactual is the best candidate Josh did NOT take."""
    import reconcile_decisions as RD

    hist = pd.DataFrame([
        _hist_row("2026-07-29T120000_7", "2026-07-29", "Joc Pederson", 592626, "H", 0.0875),
        _hist_row("2026-07-29T120000_7", "2026-07-29", "Ryan Jeffers", 680777, "H", 0.0872),
        _hist_row("2026-07-29T120000_7", "2026-07-29", "Javier Sanoja", 691594, "H", 0.0750),
    ])
    hp = tmp_path / "dpwin.parquet"
    hist.to_parquet(hp, index=False)

    tx = pd.DataFrame([{
        "date": date.today(), "ts_ms": _tx_ts_ms(9), "team_id": "1",
        "team_name": "New York Ligers", "action_str": "FA ADDED",
        "player_name": "Joc Pederson", "position": "OF", "pro_team": "Tex",
        "espn_player_id": 1, "mlbam_id": None}])
    tp = tmp_path / "tx.parquet"
    tx.to_parquet(tp, index=False)

    # snapshot must sit within the attribution window of today
    hist["snapshot_date"] = (date.today() - timedelta(days=1)).isoformat()
    hist.to_parquet(hp, index=False)

    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     verbose=False)
    assert s["events"] == 1 and s["unattributed"] == 0
    rec = s["records"][0]
    assert rec.action == "add" and rec.record_schema == 3
    assert rec.counterfactual["rejected_name"] == "Ryan Jeffers"   # next best
    assert rec.counterfactual["dpwin_chosen"] == pytest.approx(0.0875)
    assert rec.counterfactual["dpwin_gap"] == pytest.approx(0.0003, abs=1e-6)
    assert rec.reason_tag == "auto_reconciled"


def test_reconciler_never_offers_the_executed_player_as_his_own_alternative(tmp_path):
    import reconcile_decisions as RD
    yday = (date.today() - timedelta(days=1)).isoformat()
    hist = pd.DataFrame([_hist_row("r1", yday, "Only Guy", 111, "H", 0.05)])
    hp = tmp_path / "h.parquet"; hist.to_parquet(hp, index=False)
    assert RD.pick_rejected(pd.read_parquet(hp), "r1", "H", "Only Guy") is None


def test_reconciler_reports_unattributable_moves_rather_than_inventing_a_surface(tmp_path):
    import reconcile_decisions as RD
    hp = tmp_path / "empty.parquet"
    pd.DataFrame(columns=["run_id", "snapshot_date", "add_name", "add_mlbam",
                          "add_bucket", "dpwin", "dtitle_equity_pp"]
                 ).to_parquet(hp, index=False)
    tx = pd.DataFrame([{
        "date": date.today(), "ts_ms": 1785000000001, "team_id": "1",
        "team_name": "New York Ligers", "action_str": "DROPPED",
        "player_name": "Someone", "position": "SP", "pro_team": "LAA",
        "espn_player_id": 2, "mlbam_id": None}])
    tp = tmp_path / "tx.parquet"; tx.to_parquet(tp, index=False)
    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     root=tmp_path / "decisions_root", verbose=False)
    assert s["unattributed"] == 1 and s["records"] == []


def test_reconciler_collapses_same_timestamp_add_drop_into_a_swap():
    import reconcile_decisions as RD
    tx = pd.DataFrame([
        {"date": date.today(), "ts_ms": 999, "kind": "add",
         "player_name": "In", "position": "OF", "mlbam_id": None},
        {"date": date.today(), "ts_ms": 999, "kind": "drop",
         "player_name": "Out", "position": "SP", "mlbam_id": None},
    ])
    ev = RD.collapse_swaps(tx)
    assert len(ev) == 1 and ev[0]["action"] == "swap"
    assert ev[0]["add"]["player_name"] == "In"
    assert ev[0]["drop"]["player_name"] == "Out"


def test_reconciler_warns_on_an_unrecognized_action_rather_than_dropping_it(tmp_path, capsys):
    import reconcile_decisions as RD
    tx = pd.DataFrame([{
        "date": date.today(), "ts_ms": 1, "team_id": "1",
        "team_name": "New York Ligers", "action_str": "TRADED_AWAY",
        "player_name": "X", "position": "OF", "pro_team": "Tex",
        "espn_player_id": 1, "mlbam_id": None}])
    tp = tmp_path / "tx.parquet"; tx.to_parquet(tp, index=False)
    RD.load_my_transactions(days=10, path=tp)
    assert "unrecognized action_str" in capsys.readouterr().out


def test_reconciler_counts_name_only_id_matches(tmp_path):
    """mlbam_id is mostly NaN in the transactions store, so a name join is the
    normal path — but it is where a same-name collision would enter, so it must
    be counted and surfaced."""
    import reconcile_decisions as RD
    yday = (date.today() - timedelta(days=1)).isoformat()
    hist = pd.DataFrame([
        _hist_row("r1", yday, "Chosen Guy", 111, "H", 0.05),
        _hist_row("r1", yday, "Other Guy", 222, "H", 0.04)])
    hp = tmp_path / "h.parquet"; hist.to_parquet(hp, index=False)
    tx = pd.DataFrame([{
        "date": date.today(), "ts_ms": _tx_ts_ms(9), "team_id": "1",
        "team_name": "New York Ligers", "action_str": "FA ADDED",
        "player_name": "Chosen Guy", "position": "OF", "pro_team": "Tex",
        "espn_player_id": 1, "mlbam_id": None}])
    tp = tmp_path / "tx.parquet"; tx.to_parquet(tp, index=False)
    s = RD.reconcile(days=10, dry_run=True, tx_path=tp, hist_path=hp,
                     root=tmp_path / "decisions_root", verbose=False)
    assert s["name_only_matches"] == 1
    assert s["records"][0].inputs["id_source"] == "name_only"
