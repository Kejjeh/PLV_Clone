"""Boxscore bridge partial-pull reporting — behavioral spec.

Per-game fetch failures are caught and printed to stderr, but the closing
summary counted successes only, so a run that stored 2 of a date's 3 final games
terminated on a success-shaped line. The bridge must report what it stored
against what it attempted, and name the games it lost.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
import refresh_boxscores as rb  # noqa: E402


GAME_DATE = "2026-06-22"
PKS = [101, 102, 103]
FAILING_PK = 102


def _install_stubs(monkeypatch, tmp_path, failing=(FAILING_PK,)):
    monkeypatch.setattr(rb, "OUT_P", tmp_path / "boxscore_pitchers.parquet")
    monkeypatch.setattr(rb, "OUT_H", tmp_path / "boxscore_hitters.parquet")
    monkeypatch.setattr(rb, "game_pks_for_date", lambda d: list(PKS))

    def _fake_rows(game_pk, game_date):
        if game_pk in failing:
            raise RuntimeError("503 Service Unavailable")
        p = [{"game_pk": game_pk, "game_date": game_date.isoformat(),
              "mlbam_id": 600000 + game_pk, "player_name": f"P{game_pk}",
              "ip": 1.0, "so": 1, "h_allowed": 0, "er": 0, "fp_sp": 4.3}]
        h = [{"game_pk": game_pk, "game_date": game_date.isoformat(),
              "mlbam_id": 700000 + game_pk, "player_name": f"H{game_pk}",
              "fp_h": 3.0}]
        return p, h

    monkeypatch.setattr(rb, "boxscore_rows", _fake_rows)
    monkeypatch.setattr(sys, "argv", ["refresh_boxscores.py", "--date", GAME_DATE])


def test_partial_pull_reports_stored_against_attempted_and_names_failures(
        monkeypatch, tmp_path, capsys):
    """A run that loses a game reports N/M stored, the failure count, and the pk."""
    _install_stubs(monkeypatch, tmp_path)

    rb.main()

    out = capsys.readouterr().out
    done = [ln for ln in out.splitlines() if "games refreshed" in ln]
    assert done, f"no closing summary:\n{out}"
    assert f"{len(PKS) - 1}/{len(PKS)}" in done[0], done[0]
    assert "1 failed" in done[0], done[0]
    assert str(FAILING_PK) in done[0], done[0]


def test_clean_pull_reports_full_completion(monkeypatch, tmp_path, capsys):
    """With every game stored the summary shows the full count and no failures."""
    _install_stubs(monkeypatch, tmp_path, failing=())

    rb.main()

    out = capsys.readouterr().out
    done = [ln for ln in out.splitlines() if "games refreshed" in ln]
    assert done, f"no closing summary:\n{out}"
    assert f"{len(PKS)}/{len(PKS)}" in done[0], done[0]
    assert "failed" not in done[0].lower() or "0 failed" in done[0], done[0]


def test_mass_failure_warns(monkeypatch, tmp_path, capsys):
    """Losing most of a date's games is announced, not just tallied."""
    _install_stubs(monkeypatch, tmp_path, failing=tuple(PKS[:2]))

    rb.main()

    out = capsys.readouterr().out
    assert "WARNING" in out, out


def test_a_routine_single_game_loss_is_reported_but_does_not_cry_wolf(
        monkeypatch, tmp_path, capsys):
    """Review round (2026-08-01): both original fixtures (1-of-3 = 33%,
    2-of-3 = 67%) sit ABOVE the 10% warn threshold, so `> 0.10` could be
    changed to `> 0.0` with every test still green — and the nightly would
    then shout on every routine single-game 503. This pins the band from
    below: a loss rate under the threshold is REPORTED in the summary but
    raises no WARNING."""
    pks = list(range(200, 220))            # 20 games, 1 failure = 5% < 10%
    monkeypatch.setattr(rb, "game_pks_for_date", lambda d: list(pks))
    _install_stubs(monkeypatch, tmp_path, failing=(201,))
    monkeypatch.setattr(rb, "game_pks_for_date", lambda d: list(pks))

    rb.main()

    out = capsys.readouterr().out
    done = [ln for ln in out.splitlines() if "games refreshed" in ln]
    assert done, out
    assert "1 failed" in done[0], done[0]          # still visible
    assert "!! WARNING" not in out, (
        "a 5% loss must not trip the mass-failure warning — the threshold is "
        "what keeps the signal meaningful")
