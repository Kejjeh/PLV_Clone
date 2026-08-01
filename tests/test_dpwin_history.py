"""Tests for lib/dpwin_history — the durable Delta-P(win) surface (C2).

This store is the counterfactual record the decision ledger settles against, so
its idempotency contract is load-bearing: a retried run that duplicated rows
would double-count every alternative and corrupt regret accounting downstream.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

H = pytest.importorskip("scripts.xfp.lib.dpwin_history")


def _state():
    return {
        "mu": {"my_score": 91.1, "opp_score": 120.7},
        "period": 17, "days_remaining": 5, "cap_remaining_mine": 7,
    }


def _moves():
    return [
        {"move_type": "add", "add": {"name": "Streamer A", "mlbam": 111, "bucket": "SP"},
         "start_date": "2026-08-01", "dpwin": 0.021, "pwin": 0.312, "mc_se": 0.003,
         "candidate_source": "advice:fa_streamer"},
        {"move_type": "bench_start", "drop": {"name": "Wobbly", "mlbam": 222, "bucket": "SP"},
         "start_date": "2026-08-02", "dpwin": 0.004, "pwin": 0.295, "mc_se": 0.003,
         "candidate_source": "advice:sp_bench"},
        {"move_type": "sit_hitter", "drop": {"name": "Cold Bat", "mlbam": 333, "bucket": "H"},
         "dpwin": -0.011, "pwin": 0.280, "mc_se": 0.003,
         "candidate_source": "advice:hitter_sit"},
    ]


def _rows(run_id="2026-07-29T120000_7"):
    return H.build_rows(run_id=run_id, state=_state(), regime="TRAILING",
                        base_pwin=0.291, sims=20000, seed=7, moves=_moves(),
                        generated_at=datetime(2026, 7, 29, 12, 0, 0))


# ── schema + shaping ─────────────────────────────────────────────────────────

def test_build_rows_emits_the_declared_schema():
    df = _rows()
    assert list(df.columns) == H.COLUMNS
    assert len(df) == 3


def test_run_context_is_identical_across_rows():
    df = _rows()
    for c in ("run_id", "base_pwin", "period", "regime", "sims", "seed",
              "engine_version", "snapshot_date"):
        assert df[c].nunique() == 1, c


def test_rank_is_assigned_by_descending_dpwin():
    df = _rows().sort_values("rank_in_run")
    assert list(df["add_name"].fillna(df["drop_name"])) == [
        "Streamer A", "Wobbly", "Cold Bat"]


def test_negative_dpwin_candidates_are_kept():
    """The REJECTED surface is the counterfactual — filtering to positive-only
    would destroy the thing the ledger needs."""
    df = _rows()
    assert (df["dpwin"] < 0).any()


def test_engine_version_is_stamped():
    """A future engine change must not silently mix incomparable dpwin values in
    one panel; the 2026-07-29 variance fix moved P(win) by up to ~3pp."""
    assert _rows()["engine_version"].iloc[0] == H.ENGINE_VERSION


def test_unknown_move_type_raises():
    with pytest.raises(ValueError, match="unknown move_type"):
        H.build_rows(run_id="r", state=_state(), regime="CLOSE", base_pwin=0.5,
                     sims=10, seed=1,
                     moves=[{"move_type": "teleport", "dpwin": 0.1}])


def test_missing_mlbam_becomes_zero_not_nan():
    """NaN != NaN in drop_duplicates, so a NaN in the dedup key would silently
    defeat idempotency and let a re-run double every add row."""
    df = H.build_rows(run_id="r", state=_state(), regime="CLOSE", base_pwin=0.5,
                      sims=10, seed=1,
                      moves=[{"move_type": "add",
                              "add": {"name": "No Id", "bucket": "H"},
                              "dpwin": 0.01}])
    assert df["add_mlbam"].iloc[0] == 0
    assert df["drop_mlbam"].iloc[0] == 0


def test_make_run_id_embeds_time_and_seed():
    rid = H.make_run_id(datetime(2026, 7, 29, 14, 30, 5), seed=42)
    assert rid == "2026-07-29T143005_42"


# ── idempotent upsert ────────────────────────────────────────────────────────

def test_append_then_reappend_same_run_replaces_not_duplicates(tmp_path):
    p = tmp_path / "dpwin.parquet"
    r1 = H.append(_rows(), path=p)
    assert r1 == {"added": 3, "replaced": 0, "evicted": 0, "total": 3}
    r2 = H.append(_rows(), path=p)
    assert r2["total"] == 3, "a retried run must not inflate the panel"
    assert r2["added"] == 0
    assert len(pd.read_parquet(p)) == 3


def test_a_second_distinct_run_appends(tmp_path):
    p = tmp_path / "dpwin.parquet"
    H.append(_rows("2026-07-29T120000_7"), path=p)
    H.append(_rows("2026-07-29T180000_7"), path=p)
    df = pd.read_parquet(p)
    assert len(df) == 6
    assert df["run_id"].nunique() == 2


def test_same_pitcher_two_start_dates_are_distinct_rows(tmp_path):
    """A two-start week is two candidates; start_date is in the key for exactly
    this reason."""
    p = tmp_path / "dpwin.parquet"
    moves = [
        {"move_type": "add", "add": {"name": "Two Start", "mlbam": 999, "bucket": "SP"},
         "start_date": "2026-08-01", "dpwin": 0.02},
        {"move_type": "add", "add": {"name": "Two Start", "mlbam": 999, "bucket": "SP"},
         "start_date": "2026-08-04", "dpwin": 0.03},
    ]
    df = H.build_rows(run_id="r1", state=_state(), regime="CLOSE", base_pwin=0.5,
                      sims=10, seed=1, moves=moves)
    H.append(df, path=p)
    assert len(pd.read_parquet(p)) == 2


def test_updated_dpwin_for_same_key_overwrites(tmp_path):
    p = tmp_path / "dpwin.parquet"
    H.append(_rows(), path=p)
    bumped = _rows()
    bumped.loc[bumped["add_mlbam"] == 111, "dpwin"] = 0.099
    H.append(bumped, path=p)
    df = pd.read_parquet(p)
    assert len(df) == 3
    assert df.loc[df["add_mlbam"] == 111, "dpwin"].iloc[0] == pytest.approx(0.099)


def test_append_empty_is_a_noop(tmp_path):
    p = tmp_path / "dpwin.parquet"
    assert H.append(pd.DataFrame(), path=p)["total"] == 0
    assert not p.exists()


def test_append_leaves_no_temp_file(tmp_path):
    p = tmp_path / "dpwin.parquet"
    H.append(_rows(), path=p)
    assert list(tmp_path.glob("*.parquet")) == [p]


def test_corrupt_panel_raises_rather_than_silently_starting_fresh(tmp_path):
    """House rule: no silent data loss. Quietly rewriting a corrupt panel would
    destroy the counterfactual record the ledger depends on."""
    p = tmp_path / "dpwin.parquet"
    p.write_bytes(b"not a parquet file")
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        H.append(_rows(), path=p)


def test_append_rejects_rows_missing_key_columns(tmp_path):
    p = tmp_path / "dpwin.parquet"
    bad = _rows().drop(columns=["start_date"])
    with pytest.raises(ValueError, match="missing key columns"):
        H.append(bad, path=p)


def test_append_reports_evictions_honestly(tmp_path, capsys):
    """Spec 3 (2026-08-01): replacing rows via the same key counts as
    ``replaced``; distinct evaluated rows collapsing onto one key within a
    single append are counted as ``evicted`` and reported LOUDLY — the panel
    never silently shrinks. (The old ``added = max(total - before, 0)``
    arithmetic reported a 54-row loss as zero.)"""
    p = tmp_path / "dpwin.parquet"

    # an intentional upsert is REPLACED, with zero evictions
    H.append(_rows(), path=p)
    res = H.append(_rows(), path=p)
    assert res["replaced"] == 3
    assert res["evicted"] == 0

    # two rows carrying the SAME idempotency key in one batch: one is evicted,
    # the count says so, and a loud line is printed
    one = [{"move_type": "add", "add": {"name": "Dup Guy", "mlbam": 777,
                                        "bucket": "H"}, "dpwin": 0.01}]
    batch = pd.concat([
        H.build_rows(run_id="rdup", state=_state(), regime="CLOSE",
                     base_pwin=0.5, sims=10, seed=1, moves=one),
        H.build_rows(run_id="rdup", state=_state(), regime="CLOSE",
                     base_pwin=0.5, sims=10, seed=1, moves=one),
    ], ignore_index=True)
    capsys.readouterr()
    res2 = H.append(batch, path=p)
    assert res2["evicted"] == 1
    assert res2["added"] == 1
    out = capsys.readouterr().out.lower()
    assert "evict" in out, "an eviction must be reported loudly, never silently"


def test_two_distinct_unresolved_id_adds_sharing_a_drop_both_survive(tmp_path):
    """C2 (2026-08-01): the panel preserves EVERY evaluated candidate.

    Two DISTINCT adds whose mlbam never resolved (None -> sentinel 0) paired
    with the same drop used to collapse onto one dedup key, and
    drop_duplicates(keep='last') silently evicted one — three consecutive live
    runs each lost 54+ evaluated candidates this way. The evicted rows are the
    counterfactual surface the ledger settles against."""
    p = tmp_path / "dpwin.parquet"
    moves = [
        {"move_type": "swap", "add": {"name": "Ghost A", "bucket": "H"},
         "drop": {"name": "Weak Bat", "mlbam": 555, "bucket": "H"},
         "dpwin": 0.011},
        {"move_type": "swap", "add": {"name": "Ghost B", "bucket": "H"},
         "drop": {"name": "Weak Bat", "mlbam": 555, "bucket": "H"},
         "dpwin": 0.022},
    ]
    df = H.build_rows(run_id="r1", state=_state(), regime="CLOSE", base_pwin=0.5,
                      sims=10, seed=1, moves=moves)
    H.append(df, path=p)
    got = pd.read_parquet(p)
    assert len(got) == 2, "stored row count must equal the number evaluated"
    assert set(got["add_name"]) == {"Ghost A", "Ghost B"}, (
        "both unresolved-id adds must be readable back")


# ── read helpers ─────────────────────────────────────────────────────────────

def test_load_on_missing_file_returns_typed_empty_frame(tmp_path):
    df = H.load(tmp_path / "absent.parquet")
    assert df.empty and list(df.columns) == H.COLUMNS


def test_latest_run_for_picks_the_most_recent_at_or_before(tmp_path):
    p = tmp_path / "dpwin.parquet"
    for d, t in (("2026-07-27", 9), ("2026-07-29", 12), ("2026-07-30", 15)):
        rows = H.build_rows(run_id=f"{d}T{t:02d}0000_7", state=_state(),
                            regime="CLOSE", base_pwin=0.5, sims=10, seed=7,
                            moves=_moves(),
                            generated_at=datetime.fromisoformat(f"{d}T{t:02d}:00:00"))
        H.append(rows, path=p)
    assert H.latest_run_for("2026-07-29", path=p) == "2026-07-29T120000_7"
    assert H.latest_run_for("2026-07-26", path=p) is None


def test_log_run_returns_the_run_id_and_writes(tmp_path):
    p = tmp_path / "dpwin.parquet"
    rid = H.log_run(state=_state(), regime="TRAILING", base_pwin=0.291,
                    sims=100, seed=7, moves=_moves(), path=p, verbose=False)
    assert rid and len(pd.read_parquet(p)) == 3
    assert pd.read_parquet(p)["run_id"].iloc[0] == rid


# ── the regression this workstream introduced ────────────────────────────────

def test_leverage_runner_logs_history_and_uses_draw_keys():
    """Two things this file must keep true of the runner:

    1. it writes the surface (otherwise the ledger has nothing to settle);
    2. it passes DRAW KEYS to zero_hitters, not names. When D moved to
       mlbam-keys during the C1 extraction, the advice family still passed a
       name — which matched nothing, so every dpwin_if_benched silently read
       0.00pp and reported every hitter as free to bench. assemble() now raises
       on a non-key, and this pins the call site too.
    """
    src = (ROOT / "scripts" / "xfp" / "run_matchup_leverage.py").read_text(encoding="utf-8")
    assert "dpwin_history.log_run(" in src
    assert "zero_hitters={_draw_key(h)}" in src
    assert "zero_hitters={h['name']}" not in src


def test_assemble_raises_on_a_name_passed_as_a_draw_key():
    """The guard itself — a silent no-op here is a wrong answer that looks like
    a legitimate 'benching him costs nothing'."""
    import numpy as np
    E = pytest.importorskip("scripts.xfp.lib.leverage_engine")
    D = {"n_sims": 50, "seed": 1, "cand": {},
         "my_h": {"id:1": {"name": "Guy A", "mlbam": 1, "arr": np.full(50, 10.0)}},
         "opp_h": {}, "my_rp": {}, "opp_rp": {}, "my_sp": [], "opp_sp": []}
    st = {"mu": {"my_score": 0.0, "opp_score": 0.0},
          "cap_remaining_mine": 10, "cap_remaining_opp": 10}
    with pytest.raises(KeyError, match="not draw keys"):
        E.assemble(st, D, zero_hitters={"Guy A"})
    my, _ = E.assemble(st, D, zero_hitters={"id:1"})
    assert my[0] == 0.0


def test_legacy_parquet_without_key_columns_migrates_on_append(tmp_path):
    """Review round 2 (2026-07-30): a panel written BEFORE the identity-key
    fix has no add_key/drop_key columns. Appending to it must (a) derive keys
    for the legacy rows from their stored (name, mlbam) legs so the same
    logical rows are REPLACED, never duplicated, and (b) leave the merged
    panel fully keyed. NOTE on red-first: the migration branch shipped inside
    Spec 2's minimal fix; this test was written after, and its red was
    produced by mutation (removing the _ensure_key_cols(old) call duplicates
    every legacy row and fails the count assertion) — disclosed per the
    established precedent."""
    p = tmp_path / "dpwin_history.parquet"
    new = _rows()
    legacy = new.drop(columns=["add_key", "drop_key"])
    legacy.to_parquet(p, index=False)

    res = H.append(_rows(), path=p)
    got = H.load(p)
    assert len(got) == 3, "legacy rows must be replaced via derived keys, not duplicated"
    assert res["replaced"] == 3 and res["added"] == 0
    assert "add_key" in got.columns and "drop_key" in got.columns
    assert got["add_key"].notna().all()
