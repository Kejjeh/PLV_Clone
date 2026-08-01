"""Behavioral tests for the RP forward-volume pipeline.

Audit 2026-08-01 (backlog T41 / T18). The RP pipeline carried local forks of
four helpers that were hoisted into `lib.volume_model` in the 2026-07-19
consolidation, and the forks had drifted:

  * its `attach_team_games` fork never gained the unmapped-team visibility
    guard, so a desynced team map degrades to the league mean in silence —
    while the hitter and SP builds announce it;
  * its `cross_year_eval` fork carried the same train-year leak as the lib
    (T18): LOO folds trained on every season in the substrate minus the held
    one, including the in-progress season the shipped model never fits on.

These specs are written against the pipeline's public functions on synthetic
frames — no statcast parquet, no projection CSV, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

import xfp_rp_volume_pipeline as rp  # noqa: E402


def _team_games(year: int, teams: dict[str, int]) -> pd.DataFrame:
    rows = []
    for team, n in teams.items():
        for i in range(n):
            rows.append({"year": year, "team": team,
                         "game_date": pd.Timestamp(f"{year}-04-01") + pd.Timedelta(days=i)})
    return pd.DataFrame(rows)


# ------------------------------------------------ unmapped-team report (T41)
def test_rp_build_reports_the_unmapped_team_share_like_the_hitter_and_sp_builds(capsys):
    """A reliever whose team never appears in the schedule takes the league-mean
    fallback — and the RP build says so, exactly as the other two volume builds
    do. Silence here means a stale team map moves every reliever's projected
    appearance rate with nothing on stdout to show for it.
    """
    rolling = pd.DataFrame({
        "pitcher": [1, 2, 3, 4],
        "year": 2024,
        "cutoff_date": "2024-05-01",
        "split_day": 30,
        "team_abbr": ["NYY", "NYY", "AZ", "AZ"],   # 'AZ' absent from the schedule
    })
    tg = _team_games(2024, {"NYY": 100, "BOS": 120})

    out = rp.attach_team_games(rolling, tg)

    assert out["team_games_to"].notna().all()      # values unchanged
    printed = capsys.readouterr().out
    assert "attach_team_games" in printed, (
        "the RP build applied the league-mean fallback silently; printed=%r" % printed)
    assert "50.0%" in printed, printed


def test_rp_attach_team_games_leaves_one_row_per_reliever_snapshot():
    """The team attach is a lookup on the substrate's own column — no fan-out."""
    rolling = pd.DataFrame({
        "pitcher": [1, 2, 3],
        "year": 2024,
        "cutoff_date": "2024-05-01",
        "split_day": 30,
        "team_abbr": ["NYY", "NYY", "BOS"],
    })
    out = rp.attach_team_games(rolling, _team_games(2024, {"NYY": 100, "BOS": 120}))
    assert len(out) == 3
    assert out["team_games_to"].tolist() == [31.0, 31.0, 31.0]
    assert out["team_games_remaining"].tolist() == [69.0, 69.0, 89.0]
    assert "team" in out.columns and "team_abbr" not in out.columns


# ---------------------------------------- LOO train-year isolation, RP (T18)
def _rp_substrate(years, *, seed=3, n_per_cell=40, sign=1.0):
    """Minimal synthetic reliever substrate that clears `rp.eligible`."""
    rng = np.random.default_rng(seed)
    rows = []
    for yr in years:
        for split_day in (30, 90):
            n = n_per_cell
            anchor = rng.uniform(0.05, 0.45, size=n)
            frame = pd.DataFrame({
                "pitcher": np.arange(n) + 1000 * yr + split_day,
                "year": yr,
                "split_day": float(split_day),
                "g_to": rng.uniform(10, 60, size=n),
                "team_games_to": 80.0,
                "team_games_remaining": 80.0,
                "g_per_teamgame_to": anchor,
                rp.TARGET: np.clip(sign * (anchor - 0.25) + 0.25
                                   + rng.normal(scale=0.02, size=n), 0.0, 0.55),
            })
            for col in rp.RP_VOLUME_FEATS:
                if col not in frame.columns:
                    frame[col] = rng.normal(size=n)
            frame["split_day"] = float(split_day)
            rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def test_rp_loo_folds_never_fit_on_a_season_outside_the_training_years(monkeypatch):
    """The RP gate must score the model the RP pipeline actually ships.

    `main()` fits the final model on TRAIN_YEARS only. If the LOO folds train on
    the whole substrate minus the held year, the pre-registered gate measures a
    different model — and for RP the leak is wider than the in-progress season:
    TRAIN_YEARS excludes 2018 as well, so 2018 rows leak into every fold too.
    """
    train_years = [2021, 2022, 2023]
    monkeypatch.setattr(rp, "TRAIN_YEARS", train_years)

    declared = _rp_substrate(train_years)
    outside = _rp_substrate([2018, 2026], seed=99, sign=-1.0)

    clean, clean_pooled, _ = rp.cross_year_eval(declared)
    with_extra, extra_pooled, _ = rp.cross_year_eval(
        pd.concat([declared, outside], ignore_index=True))

    assert set(with_extra) == set(clean) == set(train_years)
    assert with_extra[2022] == clean[2022], (
        "the 2022 RP fold moved because seasons outside TRAIN_YEARS entered its "
        f"training frame: {with_extra[2022]} vs {clean[2022]}")
    assert extra_pooled == clean_pooled, (
        f"pooled RP gate is not reproducible: {extra_pooled} vs {clean_pooled}")
