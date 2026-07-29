"""Tests for the model-scorecard drift sentinels (added 2026-07-29).

These sentinels exist because the Max Muncy collision gate rotted SILENTLY —
`resolve_batter_id` went from "refuses to guess" to "returns the wrong player"
and nothing alerted. A sentinel that only ever passes is worthless, so the
load-bearing tests here INJECT the drift and assert the check FAILS.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))


@pytest.fixture(scope="module")
def msc():
    """Load build_model_scorecard as a module (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location(
        "build_model_scorecard", ROOT / "scripts" / "xfp" / "build_model_scorecard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(mod, fn, name):
    """Run one check in isolation and return its emitted rows."""
    mod.ROWS.clear()
    mod._run_check(name, fn)
    return list(mod.ROWS)


def _statuses(rows):
    return {r["status"] for r in rows}


# ── collision_team_reachability ───────────────────────────────────────────────

def test_reachability_passes_on_current_tables(msc):
    """Today's KNOWN_COLLISIONS must all be reachable — regression guard."""
    if not msc.ROSTER_HISTORY_PARQUET.exists():
        pytest.skip("roster history parquet unavailable")
    rows = _rows(msc, msc.check_collision_team_reachability,
                 "collision_team_reachability")
    assert rows and _statuses(rows) <= {"PASS", "SKIP"}, rows


def test_reachability_FAILS_on_injected_dead_team_code(msc, monkeypatch):
    """THE test: an unreachable team hint must FAIL, loudly.

    This reproduces the 2026-07-29 root cause — a collision entry keyed to a
    team code no live ESPN spelling can reach, which makes the team filter
    select zero candidates and the resolver fall through.
    """
    if not msc.ROSTER_HISTORY_PARQUET.exists():
        pytest.skip("roster history parquet unavailable")
    from plv_clone.utils import name_match

    poisoned = dict(name_match.KNOWN_COLLISIONS)
    poisoned["Fake Player"] = [
        ("MONTREAL", "3B", 111111),   # no live ESPN code canonicalizes to this
        ("LAD", "SS", 222222),
    ]
    monkeypatch.setattr(name_match, "KNOWN_COLLISIONS", poisoned)

    rows = _rows(msc, msc.check_collision_team_reachability,
                 "collision_team_reachability")
    assert "FAIL" in _statuses(rows), rows
    note = rows[0]["note"]
    assert "DEAD" in note and "MONTREAL" in note
    assert "WRONG player" in note, "the note must say what breaks, not just that it broke"


def test_reachability_also_covers_the_pitcher_table(msc, monkeypatch):
    if not msc.ROSTER_HISTORY_PARQUET.exists():
        pytest.skip("roster history parquet unavailable")
    from plv_clone.utils import name_match

    poisoned = dict(name_match.KNOWN_PITCHER_COLLISIONS)
    poisoned["Fake Arm"] = [("EXPOS", "SP", 333333)]
    monkeypatch.setattr(name_match, "KNOWN_PITCHER_COLLISIONS", poisoned)
    rows = _rows(msc, msc.check_collision_team_reachability,
                 "collision_team_reachability")
    assert "FAIL" in _statuses(rows)
    assert "EXPOS" in rows[0]["note"]


def test_espn_vocabulary_is_the_live_one_not_statcast_codes(msc):
    """The check must compare against ESPN spellings ('Oak'), which is the
    vocabulary that actually reaches the resolver — not Statcast's 'ATH'."""
    if not msc.ROSTER_HISTORY_PARQUET.exists():
        pytest.skip("roster history parquet unavailable")
    codes = msc._live_espn_team_codes()
    assert len(codes) >= 25, f"expected ~30 clubs, got {len(codes)}"
    # 'Oak' is the exact spelling that broke the gate.
    assert any(c.upper() == "OAK" for c in codes), sorted(codes)


# ── collision_smoke ──────────────────────────────────────────────────────────

def test_smoke_passes_on_current_resolvers(msc):
    rows = _rows(msc, msc.check_collision_smoke, "collision_smoke")
    assert rows and rows[0]["status"] == "PASS", rows


def test_smoke_FAILS_when_a_resolver_returns_the_wrong_player(msc, monkeypatch):
    """If resolve_batter_id starts guessing again, this must go red."""
    from plv_clone.utils import name_match

    monkeypatch.setattr(name_match, "resolve_batter_id",
                        lambda *a, **k: 571970)  # always the LAD Muncy = the bug
    rows = _rows(msc, msc.check_collision_smoke, "collision_smoke")
    assert rows[0]["status"] == "FAIL", rows
    assert "BROKEN" in rows[0]["note"]


def test_smoke_FAILS_when_a_should_refuse_case_resolves(msc, monkeypatch):
    """Silently resolving an ambiguous name is the original sin — catch it."""
    from plv_clone.utils import name_match

    real = name_match.resolve_pitcher_id

    def always_answers(name, **kw):
        # never refuse — the exact regression we must detect
        got = real(name, **kw)
        return 671106 if got is None else got

    monkeypatch.setattr(name_match, "resolve_pitcher_id", always_answers)
    rows = _rows(msc, msc.check_collision_smoke, "collision_smoke")
    assert rows[0]["status"] == "FAIL", rows


# ── fa_join_coverage ─────────────────────────────────────────────────────────

def test_fa_join_coverage_runs_and_reports_all_three_buckets(msc):
    rows = _rows(msc, msc.check_fa_join_coverage, "fa_join_coverage")
    segs = {r["segment"] for r in rows}
    assert {"H", "SP", "RP"} <= segs, segs
    assert _statuses(rows) <= {"PASS", "WARN", "FAIL", "SKIP"}


def test_fa_join_coverage_FAILS_when_the_join_collapses(msc, monkeypatch, tmp_path):
    """A normalizer/schema drift shows up as coverage collapsing. Simulate it by
    pointing the snapshot at ids that exist in no projection CSV."""
    fake_dir = tmp_path / "fa_snapshots"
    fake_dir.mkdir()
    for b in ("H", "SP", "RP"):
        pd.DataFrame({"mlbam_id": [9_000_001, 9_000_002, 9_000_003]}).to_parquet(
            fake_dir / f"fa_pool_{b}_latest.parquet")
    monkeypatch.setattr(msc, "FA_SNAPSHOT_DIR", fake_dir)
    # no history -> absolute floors apply (0.70 WARN / 0.40 FAIL)
    monkeypatch.setattr(msc, "SCORECARD_HISTORY", tmp_path / "nope.csv")

    rows = _rows(msc, msc.check_fa_join_coverage, "fa_join_coverage")
    assert rows, "expected rows"
    assert all(r["status"] == "FAIL" for r in rows if r["status"] != "SKIP"), rows
    assert all(r["value"] == 0.0 for r in rows if r["status"] == "FAIL")


def test_fa_join_coverage_skips_cleanly_when_snapshot_missing(msc, monkeypatch, tmp_path):
    monkeypatch.setattr(msc, "FA_SNAPSHOT_DIR", tmp_path / "absent")
    rows = _rows(msc, msc.check_fa_join_coverage, "fa_join_coverage")
    assert rows and all(r["status"] == "SKIP" for r in rows), rows


# ── registry wiring + crash-safety contract ──────────────────────────────────

def test_sentinels_are_registered_in_run_data_health():
    src = (ROOT / "scripts" / "xfp" / "build_model_scorecard.py").read_text(encoding="utf-8")
    body = src.split("def run_data_health()", 1)[1]
    for name in ("collision_team_reachability", "collision_smoke", "fa_join_coverage"):
        assert f"_run_check('{name}'" in body, f"{name} not registered"


def test_a_crashing_sentinel_degrades_to_SKIP_not_an_exception(msc):
    """_run_check's contract: a broken check can never take down the scorecard."""
    def boom():
        raise RuntimeError("synthetic")

    rows = _rows(msc, boom, "synthetic_check")
    assert rows and rows[0]["status"] == "SKIP"
    assert "synthetic" in rows[0]["note"]
