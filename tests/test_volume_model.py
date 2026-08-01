"""Behavioral tests for `lib.volume_model` — the shared expected-playing-time
engine behind all three forward-volume pipelines (hitter / SP / RP).

Audit 2026-08-01 (backlog T35): this module had NO test file at all, and
neither did any of the three pipelines that consume it. The specs below pin
the behavior the volume layer actually promises:

  * attaching team-games to a roster is a LOOKUP, not a fan-out — one row in,
    one row out;
  * a player whose team cannot be matched to a schedule is REPORTED, not
    silently handed the league mean (this covers the abbreviation-drift case
    the shipped guard missed: `team` present but absent from the schedule map);
  * the per-year statcast cache is transparent — cold and warm runs agree, a
    newer source parquet rebuilds, a corrupt cache rebuilds rather than raising;
  * the LOO cross-year evaluation never fits on a season outside the declared
    training years (backlog T18).

Everything runs on synthetic frames in tmp_path with `volume_model.CACHE`
monkeypatched, so no real parquet is read and the nightly caches in
data/research/xfp_cache/ can never be touched by this file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

from lib import volume_model as vm  # noqa: E402


# --------------------------------------------------------------- fixtures
def _team_games(year: int, teams: dict[str, int]) -> pd.DataFrame:
    """Long (year, team, game_date) frame: `teams` maps team -> n games."""
    rows = []
    for team, n in teams.items():
        for i in range(n):
            rows.append({"year": year,
                         "team": team,
                         "game_date": pd.Timestamp("2024-04-01") + pd.Timedelta(days=i)})
    return pd.DataFrame(rows)


def _rolling(ids, year=2024, cutoff="2024-05-01", id_col="batter") -> pd.DataFrame:
    return pd.DataFrame({
        id_col: list(ids),
        "year": year,
        "cutoff_date": cutoff,
        "split_day": 30,
    })


# ------------------------------------------- unmapped-team visibility (T35)
def test_team_absent_from_schedule_is_reported_not_silently_league_meaned(capsys):
    """A player whose team string never appears in the schedule map takes the
    league-mean fallback — and the build says so.

    The blind spot this pins: the shipped guard measured `team.isna()`, but the
    fallback branch triggers on `(year, team) not in dates_by`, which is
    strictly broader. An abbreviation drift ('AZ' in the roster vs 'ARI' in the
    schedule) is fully mapped by the isna measure and silently league-meaned.
    """
    rolling = _rolling([1, 2, 3, 4])
    team_map = pd.DataFrame({"batter": [1, 2, 3, 4],
                             "year": 2024,
                             "team": ["NYY", "NYY", "AZ", "AZ"]})
    tg = _team_games(2024, {"NYY": 100, "BOS": 120})

    out = vm.attach_team_games(rolling, tg, team_map, "batter")

    # values unchanged: the drifted rows still get the league-mean fallback
    assert out["team_games_to"].notna().all()
    printed = capsys.readouterr().out
    assert "attach_team_games" in printed, (
        "the unmapped share was never reported; printed=%r" % printed)
    assert "50.0%" in printed, (
        "expected the true fallback share (2 of 4 rows), got: %r" % printed)


def test_fully_mapped_roster_reports_nothing(capsys):
    """The guard is a signal, not noise: a clean map prints no warning."""
    rolling = _rolling([1, 2])
    team_map = pd.DataFrame({"batter": [1, 2], "year": 2024, "team": ["NYY", "BOS"]})
    out = vm.attach_team_games(rolling, _team_games(2024, {"NYY": 100, "BOS": 120}),
                               team_map, "batter")
    assert out["team_games_to"].tolist() == [31.0, 31.0]
    assert "attach_team_games" not in capsys.readouterr().out


# ------------------------------------------------ one row in, one row out (T35)
def test_attaching_team_games_leaves_exactly_one_row_per_player():
    """The team join is a lookup, not a fan-out.

    A team map carrying a duplicated (id, year) would silently multiply every
    affected player's rows, inflating both the training frame and the emitted
    projection pool. The row count is the contract.
    """
    rolling = _rolling([1, 2, 3])
    team_map = pd.DataFrame({"batter": [1, 2, 3], "year": 2024,
                             "team": ["NYY", "NYY", "BOS"]})
    out = vm.attach_team_games(rolling, _team_games(2024, {"NYY": 100, "BOS": 120}),
                               team_map, "batter")

    assert len(out) == len(rolling) == 3
    assert sorted(out["batter"].tolist()) == [1, 2, 3]
    # ...and the per-player playing-time estimate is the team's, not a mean
    by_id = dict(zip(out["batter"], out["team_games_to"]))
    assert by_id[1] == by_id[2] == 31.0          # NYY: 31 games on/before 5/1
    assert by_id[3] == 31.0
    rem = dict(zip(out["batter"], out["team_games_remaining"]))
    assert rem[1] == 69.0 and rem[3] == 89.0      # 100-31 vs 120-31


# ------------------------------------------------------ per-year cache (T35)
@pytest.fixture()
def statcast_cache(tmp_path, monkeypatch):
    """A tmp CACHE holding one synthetic statcast_2024.parquet.

    monkeypatching `volume_model.CACHE` is load-bearing: without it a cache
    test would write into data/research/xfp_cache/ and could poison the real
    nightly team_games caches.
    """
    monkeypatch.setattr(vm, "CACHE", tmp_path)
    pd.DataFrame({
        "game_pk": [1, 1, 2, 2, 3],
        "game_date": pd.to_datetime(["2024-04-01", "2024-04-01", "2024-04-02",
                                     "2024-04-02", "2024-04-03"]),
        "home_team": ["NYY", "NYY", "BOS", "BOS", "NYY"],
        "away_team": ["BOS", "BOS", "NYY", "NYY", "TB"],
    }).to_parquet(tmp_path / "statcast_2024.parquet", index=False)
    return tmp_path


def _spy_on_source_reads(monkeypatch):
    """Count how many times the source parquet is actually parsed."""
    calls = []
    real = vm._team_games_year

    def counted(src):
        calls.append(src)
        return real(src)

    monkeypatch.setattr(vm, "_team_games_year", counted)
    return calls


def test_team_games_agree_whether_the_cache_is_cold_or_warm(statcast_cache, monkeypatch):
    """A warm cache is transparent: same playing-time frame, no second parse."""
    calls = _spy_on_source_reads(monkeypatch)

    cold = vm.build_team_games(years=[2024])
    assert len(calls) == 1, "cold run should parse the source exactly once"

    warm = vm.build_team_games(years=[2024])
    assert len(calls) == 1, "warm run re-parsed the source parquet"

    pd.testing.assert_frame_equal(cold, warm)
    # sanity: 3 distinct game_pks -> 6 team-games
    assert len(cold) == 6
    assert set(cold["team"]) == {"NYY", "BOS", "TB"}


def test_a_newer_source_parquet_rebuilds_the_cache(statcast_cache, monkeypatch):
    """When the season's statcast parquet changes, the derived frame follows.

    This is the whole safety story for the in-progress season, which is
    rewritten nightly while the seven historical seasons stay immutable.
    """
    import os

    vm.build_team_games(years=[2024])            # prime the cache
    src = statcast_cache / "statcast_2024.parquet"

    # a fourth game appears, and the source is stamped newer than the cache
    pd.DataFrame({
        "game_pk": [1, 2, 3, 4],
        "game_date": pd.to_datetime(["2024-04-01", "2024-04-02", "2024-04-03",
                                     "2024-04-04"]),
        "home_team": ["NYY", "BOS", "NYY", "TB"],
        "away_team": ["BOS", "NYY", "TB", "NYY"],
    }).to_parquet(src, index=False)
    future = src.stat().st_mtime + 60
    os.utime(src, (future, future))

    calls = _spy_on_source_reads(monkeypatch)
    refreshed = vm.build_team_games(years=[2024])

    assert len(calls) == 1, "a newer source parquet did not invalidate the cache"
    assert len(refreshed) == 8, "the new game never reached the derived frame"


def test_a_corrupt_cache_file_rebuilds_instead_of_failing_the_build(statcast_cache):
    """A truncated cache degrades to a rebuild, not to a crashed nightly."""
    vm.build_team_games(years=[2024])
    (statcast_cache / "team_games_cache_2024.parquet").write_bytes(b"not a parquet")

    recovered = vm.build_team_games(years=[2024])
    assert len(recovered) == 6
    assert set(recovered["team"]) == {"NYY", "BOS", "TB"}


def test_a_cache_that_cannot_be_written_is_announced_not_silently_disabled(
        statcast_cache, capsys, monkeypatch):
    """A permanently unwritable cache degrades loudly.

    The cache write is best-effort by design — the derived frame is returned
    either way, so no nightly should fail over it. But swallowing the error
    without a word means the whole point of the cache (the seven immutable
    seasons are parsed once, ever) can be silently off for months while every
    run re-parses ~2.5 GB of parquet. Visibility only: values are untouched.
    """
    def unwritable(self, *a, **kw):
        raise OSError("read-only file system")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", unwritable)

    out = vm.build_team_games(years=[2024])

    assert len(out) == 6, "the frame must still be returned when the cache fails"
    printed = capsys.readouterr().out
    assert "cache" in printed.lower(), (
        "an unwritable cache was swallowed in silence; printed=%r" % printed)
    assert "2024" in printed, printed


def test_a_season_with_no_statcast_parquet_is_skipped_not_invented(statcast_cache):
    """Missing seasons drop out of the schedule rather than erroring or
    contributing empty rows."""
    out = vm.build_team_games(years=[2023, 2024])
    assert set(out["year"]) == {2024}


# ------------------------------------------ LOO train-year isolation (T18)
def _loo_substrate(years, *, seed=7, n_per_cell=40, sign=1.0):
    """Synthetic (id, year, split_day, x1, x2, naive, y) volume substrate.

    `sign` flips the x1 -> y relationship, which is how an out-of-training
    season is made to visibly poison a fold that should never have seen it.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for yr in years:
        for split_day in (30, 90):
            x1 = rng.normal(size=n_per_cell)
            x2 = rng.normal(size=n_per_cell)
            rows.append(pd.DataFrame({
                "pid": np.arange(n_per_cell) + 1000 * yr + split_day,
                "year": yr,
                "split_day": split_day,
                "x1": x1,
                "x2": x2,
                "naive": x1,
                "y": sign * (2.0 * x1 + 0.5 * x2) + rng.normal(scale=0.3,
                                                               size=n_per_cell),
            }))
    return pd.concat(rows, ignore_index=True)


def _run_loo(df, train_years):
    return vm.cross_year_eval(
        df,
        feats=["x1", "x2"], target="y", naive_col="naive", id_col="pid",
        train_years=list(train_years), pred_clip=(-10.0, 10.0),
        eligible_fn=lambda d: d,
    )


def test_loo_folds_never_fit_on_a_season_outside_the_training_years():
    """The pre-registered LOO gate scores the model the pipeline actually ships.

    The shipped final fit trains on TRAIN_YEARS only. If the LOO folds train on
    *every* season in the substrate minus the held one, the gate is measuring a
    different model — and its fold scores drift every night as the in-progress
    season accumulates rows, so a published validation number can never be
    re-derived. Holding out 2022 must give the same score whether or not an
    in-progress 2026 is sitting in the input.
    """
    train_years = [2021, 2022, 2023]
    declared = _loo_substrate(train_years)
    in_progress = _loo_substrate([2026], seed=11, sign=-1.0)   # not a train year

    clean, clean_pooled, _ = _run_loo(declared, train_years)
    with_extra, extra_pooled, _ = _run_loo(
        pd.concat([declared, in_progress], ignore_index=True), train_years)

    assert set(with_extra) == set(clean) == set(train_years), (
        "an out-of-training season must never become its own LOO fold")
    assert with_extra[2022] == clean[2022], (
        "the 2022 fold moved because rows outside the declared training years "
        f"entered its training frame: {with_extra[2022]} vs {clean[2022]}")
    assert extra_pooled == clean_pooled, (
        f"pooled gate is not reproducible: {extra_pooled} vs {clean_pooled}")


def test_t52_derived_cache_round_trips_identically(tmp_path, monkeypatch):
    """T52 (closed 2026-08-01): the RP pipeline caches DERIVED per-year
    results, never the raw frame — so a cold compute and a warm cache read
    must produce identical team-games and identical (and identically-sorted)
    relief-appearance arrays for a frozen season. The frame-order hazard the
    original deferral feared cannot survive this contract: arrays are sorted
    before the write and re-sorted on load."""
    import numpy as np
    import pandas as pd
    import importlib
    import xfp_rp_volume_pipeline as RPV

    # tiny synthetic season: 2 games, starter + reliever each half-inning
    rows = []
    for pk, d in ((1, "2024-04-01"), (2, "2024-04-02")):
        for topbot in ("Top", "Bot"):
            rows += [
                dict(game_pk=pk, game_date=d, pitcher=100 + pk, inning=1,
                     inning_topbot=topbot, home_team="AAA", away_team="BBB"),
                dict(game_pk=pk, game_date=d, pitcher=500, inning=7,
                     inning_topbot=topbot, home_team="AAA", away_team="BBB"),
            ]
    cache = tmp_path / "xfp_cache"
    cache.mkdir()
    pd.DataFrame(rows).to_parquet(cache / "statcast_2024.parquet", index=False)
    monkeypatch.setattr(RPV, "CACHE", cache)

    cold_tg, cold_rel = RPV.build_schedule_and_relief_apps()
    assert (cache / ".rp_volume_derived" / "tg_2024.parquet").exists(), (
        "a frozen season must write its derived cache")
    warm_tg, warm_rel = RPV.build_schedule_and_relief_apps()

    pd.testing.assert_frame_equal(
        cold_tg.reset_index(drop=True), warm_tg.reset_index(drop=True))
    assert set(cold_rel) == set(warm_rel)
    for k in cold_rel:
        np.testing.assert_array_equal(cold_rel[k], warm_rel[k])
    # the reliever really is the cached appearance, the starters are not
    assert (2024, 500) in warm_rel and len(warm_rel[(2024, 500)]) == 2
