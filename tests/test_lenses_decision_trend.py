"""Behavioral spec for the swing-decision tracker (`/decision-trend`).

Audit items T19 + T45 (backlog group "lenses", 2026-08-01).

T19 — MEASUREMENT HONESTY. `run_decision_trend.py` gated its chase% / z-swing%
render on an inline `iz < 15 or oz < 15`, copied out of the INNER sanity guard
of `decision_window_study.py` while that study's three OUTER inclusion filters
(MIN_FWD_PITCH 150 / MIN_BASE_PITCH 300 / per-window `max(40, 3*w)`) were
dropped. `src/plv_clone/stabilization.py` — the threshold owner — records the
measured forward-r crossing for both metrics at **150** denominator units.
A 40-out-of-zone-pitch window is therefore descriptive, never decision-grade,
and the board must SAY so instead of printing an "APPROACH SHIFT" verdict off it.

T45 — the tracker resolved both data inputs by bare relative path (so it threw
`FileNotFoundError` from any cwd but the repo root) and built its default board
from a hand-maintained `live_rosters_*.parquet` glob with no producer script,
silently accepting a two-week-old snapshot.

Fixtures are synthetic pitch frames in `tmp_path` with the module's own path
constants monkeypatched — the established pattern in
`tests/test_no_silent_zero_inputs.py` / `tests/test_rp_band_crps_internals.py`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

rdt = importlib.import_module("run_decision_trend")

TODAY = pd.Timestamp("2026-07-30")
BASE_DAY = TODAY - pd.Timedelta(days=30)

_SWING = "swinging_strike"
_TAKE = "ball"


def _pitches(batter, day, *, n_ooz, chase_pct, n_iz, zswing_pct):
    """Synthetic pitch rows with exactly the requested chase / z-swing rates."""
    rows = []
    n_ooz_sw = round(n_ooz * chase_pct / 100)
    for i in range(n_ooz):
        rows.append(dict(batter=batter, game_date=day, zone=11,
                         description=_SWING if i < n_ooz_sw else _TAKE))
    n_iz_sw = round(n_iz * zswing_pct / 100)
    for i in range(n_iz):
        rows.append(dict(batter=batter, game_date=day, zone=5,
                         description=_SWING if i < n_iz_sw else _TAKE))
    return rows


SHORT_ID, FULL_ID = 100, 200
SHORT_NAME, FULL_NAME = "Short Sample", "Full Sample"


def _two_hitter_panel() -> pd.DataFrame:
    """Two hitters with the SAME −15pp chase move; only the sample size differs.

    `Short Sample` clears the old inline 15/15 guard but carries 40 out-of-zone
    pitches — well under the registered 150. `Full Sample` carries 200.
    """
    rows = []
    rows += _pitches(SHORT_ID, BASE_DAY, n_ooz=200, chase_pct=30, n_iz=200, zswing_pct=60)
    rows += _pitches(SHORT_ID, TODAY, n_ooz=40, chase_pct=15, n_iz=40, zswing_pct=60)
    rows += _pitches(FULL_ID, BASE_DAY, n_ooz=400, chase_pct=30, n_iz=400, zswing_pct=60)
    rows += _pitches(FULL_ID, TODAY, n_ooz=200, chase_pct=15, n_iz=200, zswing_pct=60)
    return pd.DataFrame(rows)


@pytest.fixture()
def board(tmp_path, monkeypatch, capsys):
    """Run the tracker over a synthetic panel and hand back its printed board."""
    def _run(panel: pd.DataFrame, names: str, ids: dict | None = None) -> str:
        pq = tmp_path / "statcast_synth.parquet"
        panel.to_parquet(pq)
        ids = ids if ids is not None else {SHORT_NAME: SHORT_ID, FULL_NAME: FULL_ID}
        monkeypatch.setattr(rdt, "STATCAST", str(pq))
        monkeypatch.setattr(
            "plv_clone.utils.name_match.resolve_batter_id",
            lambda name, **kw: ids.get(name),
        )
        # No test may reach the MLB people/search fallback.
        monkeypatch.setattr(rdt, "_mlb_search", lambda name: None)
        monkeypatch.chdir(tmp_path)          # no repo-relative reads may leak in
        monkeypatch.setattr(sys, "argv", ["run_decision_trend.py", "--names", names])
        rc = rdt.main()
        assert rc == 0
        return capsys.readouterr().out
    return _run


def _line(out: str, name: str) -> str:
    hits = [ln for ln in out.splitlines() if ln.startswith(name)]
    assert hits, f"no board line for {name!r} in:\n{out}"
    return hits[0]


def test_undersized_decision_window_is_marked_and_carries_no_verdict(board):
    """A window below the registered stabilization minimum never earns a verdict.

    Both hitters moved chase% by the same −15pp. The one measured over 200
    out-of-zone pitches gets the APPROACH SHIFT read; the one measured over 40
    gets a below-minimum marker and no read at all — the number is descriptive,
    and the board says so.
    """
    out = board(_two_hitter_panel(), f"{SHORT_NAME},{FULL_NAME}")

    full = _line(out, FULL_NAME)
    assert "APPROACH SHIFT" in full
    assert "*" not in full, f"a sufficient sample must not be marked short: {full!r}"

    short = _line(out, SHORT_NAME)
    for verdict in ("APPROACH SHIFT", "drifting", "stable"):
        assert verdict not in short, (
            f"a 40-out-of-zone-pitch window must not publish a {verdict!r} verdict: {short!r}"
        )
    assert "sample short" in short
    assert "*" in short, f"undersized numbers must carry the below-minimum mark: {short!r}"

    # The footer names the owner's measured minimums, not a hand-picked number.
    assert "150 ooz_pitches" in out
    assert "150 iz_pitches" in out


THIN_BASE_NAME = "Thin Baseline"


def test_a_thin_baseline_blocks_the_verdict_even_when_the_window_is_decision_grade(
        board, monkeypatch):
    """Both legs of the comparison must be measurable, not just the window.

    Every Δchase / Δgap on this board is `window − baseline`, so a fat window
    measured against a 40-pitch baseline is exactly as unpublishable as a thin
    window. The window's own rate still renders unmarked (it IS measured); the
    DELTAS carry the marker and the row earns no verdict.

    This is the half the 2026-07-18 study guarded with MIN_BASE_PITCH=300 and
    `run_decision_trend.py` dropped.
    """
    rows = []
    rows += _pitches(300, BASE_DAY, n_ooz=20, chase_pct=30, n_iz=20, zswing_pct=60)
    rows += _pitches(300, TODAY, n_ooz=200, chase_pct=15, n_iz=200, zswing_pct=60)
    out = board(pd.DataFrame(rows), THIN_BASE_NAME, ids={THIN_BASE_NAME: 300})

    line = _line(out, THIN_BASE_NAME)
    for verdict in ("APPROACH SHIFT", "drifting", "stable"):
        assert verdict not in line, (
            f"a 40-pitch baseline must not publish a {verdict!r} verdict: {line!r}"
        )
    assert "sample short" in line
    assert "-15.0" + rdt.SHORT_MARK in line, f"the delta must be marked: {line!r}"
    assert "60.0" + rdt.SHORT_MARK not in line, (
        f"the window's own z-swing IS measured and must render unmarked: {line!r}"
    )


# ── T45 — the tracker must not depend on the process's working directory ─────

def _fake_repo(tmp_path, panel: pd.DataFrame) -> Path:
    """A minimal repo tree carrying only the statcast panel the tracker reads."""
    from plv_clone.league_config import SEASON_YEAR
    repo = tmp_path / "repo"
    cache = repo / "data" / "research" / "xfp_cache"
    cache.mkdir(parents=True)
    panel.to_parquet(cache / f"statcast_{SEASON_YEAR}.parquet")
    return repo


def _with_root(repo: Path):
    """Point the shared paths module at *repo* and re-import the tracker."""
    import plv_clone.paths as paths
    original = paths.ROOT
    paths.ROOT = repo
    try:
        yield importlib.reload(rdt)
    finally:
        paths.ROOT = original
        importlib.reload(rdt)


@pytest.fixture()
def tracker_rooted_at():
    """Factory: `tracker_rooted_at(repo)` -> the tracker module bound to *repo*."""
    gens = []

    def _make(repo: Path):
        g = _with_root(repo)
        gens.append(g)
        return next(g)

    yield _make
    for g in gens:
        next(g, None)


def test_the_tracker_reads_its_panel_from_a_foreign_working_directory(
        tmp_path, monkeypatch, capsys, tracker_rooted_at):
    """Launching from anywhere but the repo root must still find the data.

    The tracker resolved `data/research/xfp_cache/statcast_2026.parquet` and the
    roster glob as bare relative paths, so `python <abs path>/run_decision_trend.py`
    from any other directory died on FileNotFoundError before printing a row.
    """
    repo = _fake_repo(tmp_path, _two_hitter_panel())
    mod = tracker_rooted_at(repo)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(
        "plv_clone.utils.name_match.resolve_batter_id",
        lambda name, **kw: {SHORT_NAME: SHORT_ID, FULL_NAME: FULL_ID}.get(name),
    )
    monkeypatch.setattr(mod, "_mlb_search", lambda name: None)
    monkeypatch.setattr(sys, "argv", ["run_decision_trend.py", "--names", FULL_NAME])

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "APPROACH SHIFT" in _line(out, FULL_NAME)


def _roster_file(repo: Path, datestamp: str) -> Path:
    """Write a one-hitter `live_rosters_<datestamp>.parquet` into *repo*."""
    from plv_clone.league_config import MY_TEAM_NAME
    p = repo / "data" / "research" / f"live_rosters_{datestamp}.parquet"
    pd.DataFrame([dict(player_name=FULL_NAME, position="OF",
                       pro_team="NYY", team_name=MY_TEAM_NAME)]).to_parquet(p)
    return p


def _run_default_board(mod, monkeypatch):
    monkeypatch.setattr(
        "plv_clone.utils.name_match.resolve_batter_id",
        lambda name, **kw: {FULL_NAME: FULL_ID}.get(name),
    )
    monkeypatch.setattr(mod, "_mlb_search", lambda name: None)
    monkeypatch.setattr(sys, "argv", ["run_decision_trend.py"])
    return mod.main()


def test_a_stale_roster_snapshot_refuses_to_build_the_default_board(
        tmp_path, monkeypatch, capsys, tracker_rooted_at):
    """The default board's roster store is hand-maintained and has no producer.

    Nothing in the repo writes `live_rosters_*.parquet` — the newest one on disk
    was two weeks old when this was filed — so the tracker was silently profiling
    a fortnight-old roster. Past the stated bound it must refuse and say how old
    the snapshot is, not quietly build.
    """
    repo = _fake_repo(tmp_path, _two_hitter_panel())
    _roster_file(repo, "2020-01-01")
    mod = tracker_rooted_at(repo)

    rc = _run_default_board(mod, monkeypatch)
    cap = capsys.readouterr()
    msg = cap.out + cap.err

    assert rc != 0, f"a 2020 roster snapshot must not produce a 2026 board:\n{msg}"
    assert "live_rosters_2020-01-01.parquet" in msg
    assert "days old" in msg


def test_a_fresh_roster_snapshot_still_builds_the_default_board(
        tmp_path, monkeypatch, capsys, tracker_rooted_at):
    """The freshness bound must gate staleness, not the feature."""
    from datetime import date
    repo = _fake_repo(tmp_path, _two_hitter_panel())
    _roster_file(repo, date.today().isoformat())
    mod = tracker_rooted_at(repo)

    assert _run_default_board(mod, monkeypatch) == 0
    assert "APPROACH SHIFT" in _line(capsys.readouterr().out, FULL_NAME)


def _nightly_store(repo: Path, datestamp: str) -> Path:
    """Write a one-hitter matchup_rosters_history.parquet (the store the
    nightly step 0.5 ACTUALLY produces) into *repo*."""
    from plv_clone.league_config import MY_TEAM_NAME
    p = repo / "data" / "research" / "matchup_rosters_history.parquet"
    pd.DataFrame([dict(snapshot_date=datestamp, team_name=MY_TEAM_NAME,
                       player_name=FULL_NAME, position="OF",
                       pro_team="NYY")]).to_parquet(p)
    return p


def test_default_board_reads_the_nightly_roster_store(
        tmp_path, monkeypatch, capsys, tracker_rooted_at):
    """Review 2026-08-01: the freshness bound as first shipped KILLED the
    skill's documented default invocation — the tracker read only the orphaned
    hand-maintained live_rosters_* store (last written 07-16) while the
    nightly refresh writes rosters to matchup_rosters_history.parquet every
    day (step 0.5). The default board must consume the store that actually
    has a producer; the legacy file is a fallback, not the primary."""
    from datetime import date
    repo = _fake_repo(tmp_path, _two_hitter_panel())
    _nightly_store(repo, date.today().isoformat())     # fresh, nightly-produced
    # NO live_rosters_* file at all — the orphaned store is absent
    mod = tracker_rooted_at(repo)

    rc = _run_default_board(mod, monkeypatch)
    msg = capsys.readouterr()
    assert rc == 0, (
        "a fresh nightly roster store must build the default board" +
        chr(10) + msg.out + msg.err)
    assert "APPROACH SHIFT" in _line(msg.out, FULL_NAME)


def test_unparseable_snapshot_datestamp_is_not_treated_as_fresh(
        tmp_path, monkeypatch, capsys, tracker_rooted_at):
    """age=None means UNKNOWN, and unknown staleness must refuse the default
    board exactly like measured staleness — treating it as fresh silently
    reopens the stale-roster hole the bound exists for."""
    repo = _fake_repo(tmp_path, _two_hitter_panel())
    p = repo / "data" / "research" / "live_rosters_undated.parquet"
    from plv_clone.league_config import MY_TEAM_NAME
    pd.DataFrame([dict(player_name=FULL_NAME, position="OF",
                       pro_team="NYY", team_name=MY_TEAM_NAME)]).to_parquet(p)
    mod = tracker_rooted_at(repo)

    rc = _run_default_board(mod, monkeypatch)
    msg = capsys.readouterr()
    assert rc != 0, (
        "an undatable roster snapshot must not be treated as fresh" +
        chr(10) + msg.out + msg.err)
    assert "unknown" in (msg.out + msg.err).lower()
