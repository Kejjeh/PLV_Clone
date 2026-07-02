"""Characterization tests for hitter_sustainability.load_hitter_rows.

load_hitter_rows is the per-player row selector the breakout-sustainability /
hitter-sustainability engine calls once per name inside main()'s cohort loop.
It normalizes player_name into a `_nk` join key and returns {year: row} for the
requested hitter (with a "Last, First" fallback).

These tests pin the OBSERVABLE behavior (which rows come back, keyed by year;
correct resolution of DIFFERENT names against the SAME frame; empty on miss)
so a performance refactor that stops recomputing the deterministic `_nk`
column on every call is provably output-identical. They test the public
contract, not how `_nk` is computed, so they survive that refactor.
"""
import pandas as pd

from scripts.xfp.hitter_sustainability import load_hitter_rows


def _frame() -> pd.DataFrame:
    """Two players across multiple years, plus a 'Last, First'-stored name."""
    return pd.DataFrame({
        "player_name": ["Aaron Judge", "Aaron Judge", "Mookie Betts", "Ohtani, Shohei"],
        "year":        [2025,          2026,          2026,           2024],
        "pa":          [600,           300,           320,            550],
    })


def test_returns_rows_keyed_by_year():
    rows = load_hitter_rows(_frame(), "Aaron Judge")
    assert set(rows) == {2025, 2026}
    assert int(rows[2025]["pa"]) == 600
    assert int(rows[2026]["pa"]) == 300


def test_not_found_returns_empty():
    assert load_hitter_rows(_frame(), "Nonexistent Player") == {}


def test_last_first_fallback_branch():
    """Stored as 'Ohtani, Shohei'; queried as 'Shohei Ohtani' → alt-name branch."""
    rows = load_hitter_rows(_frame(), "Shohei Ohtani")
    assert set(rows) == {2024}
    assert int(rows[2024]["pa"]) == 550


def test_resolves_different_names_against_same_frame():
    """The load-once optimization must keep resolving DIFFERENT queries correctly
    on the SAME frame across successive calls (this is main()'s cohort loop)."""
    h = _frame()
    rj = load_hitter_rows(h, "Aaron Judge")
    rb = load_hitter_rows(h, "Mookie Betts")
    assert set(rj) == {2025, 2026}
    assert set(rb) == {2026}
    assert int(rb[2026]["pa"]) == 320


def test_idempotent_across_repeated_calls():
    h = _frame()
    r1 = load_hitter_rows(h, "Aaron Judge")
    r2 = load_hitter_rows(h, "Aaron Judge")
    assert set(r1) == set(r2) == {2025, 2026}
    assert int(r1[2026]["pa"]) == int(r2[2026]["pa"]) == 300


# ── staleness_score: sources recent per-game FP from the boxscore store ──
# (store-first / live-fallback via boom_bust._fp_series — no per-player live
# gameLog HTTP call once refresh_boxscores has run). We monkeypatch the shared
# two-tier series so these lock the score MATH and the data seam, not the network.
import pytest


def test_staleness_sources_recent_fp_from_boxscore_store(monkeypatch):
    import scripts.xfp.lib.boom_bust as bb
    monkeypatch.setattr(bb, "_fp_series",
                        lambda mlbam, bucket, season=2026: [8.0] * 6)
    from scripts.xfp.hitter_sustainability import staleness_score
    out = staleness_score(mlbam=12345, rh3_per_game=6.0, rh3_sigma=1.0, last_n_games=15)
    assert out is not None
    assert out["n_sampled"] == 6
    assert out["recent_mean"] == pytest.approx(8.0)
    # sigma_per_game = rh3_sigma * PA_PER_GAME_LEAGUE(3.5); score=(8-6)/3.5
    assert out["score"] == pytest.approx((8.0 - 6.0) / (1.0 * 3.5))


def test_staleness_takes_only_last_n_games(monkeypatch):
    import scripts.xfp.lib.boom_bust as bb
    # 20-game series ascending; last 5 = [15,16,17,18,19] mean 17.0
    monkeypatch.setattr(bb, "_fp_series",
                        lambda *a, **k: [float(i) for i in range(20)])
    from scripts.xfp.hitter_sustainability import staleness_score
    out = staleness_score(12345, rh3_per_game=10.0, rh3_sigma=2.0, last_n_games=5)
    assert out["n_sampled"] == 5
    assert out["recent_mean"] == pytest.approx(17.0)


def test_staleness_none_when_too_few_games(monkeypatch):
    import scripts.xfp.lib.boom_bust as bb
    monkeypatch.setattr(bb, "_fp_series", lambda *a, **k: [8.0, 8.0])  # <5
    from scripts.xfp.hitter_sustainability import staleness_score
    assert staleness_score(12345, 6.0, 1.0) is None


def test_staleness_none_guards():
    from scripts.xfp.hitter_sustainability import staleness_score
    assert staleness_score(None, 6.0, 1.0) is None      # no mlbam
    assert staleness_score(123, None, 1.0) is None       # no rh3
    assert staleness_score(123, 6.0, 0.0) is None        # sigma <= 0
