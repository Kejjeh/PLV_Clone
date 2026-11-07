"""load_projections' mlbam-keyed rp3 map must be keyed by rp3's OWN ids.

Defect (found 2026-09-18): ``rp3_by_mlbam`` was assembled by walking the
2015-2025 SP Statcast cache (``sp_multiyr_2015_2025.csv``), de-duplicating it
by NAME and joining each cached name back onto the name-keyed ``rp3_map``.
Two consequences, both silent:

1. Every SP whose id is absent from that frozen cache (current-season
   debutants — 16 of 376 rp3 rows on the 2026-08-31 artifact) had NO mlbam
   entry, so the hitter branch's opposing-SP factor fell back to the team
   pit_index whenever one of them was the probable, and the
   KNOWN_PITCHER_COLLISIONS branch (which reads ``rp3_by_mlbam`` precisely to
   be collision-safe) found nothing and fell through to the name key.
2. For a same-name pair the name-dedup kept ONE cached id and attached the
   OTHER pitcher's rp3 row to it — the exact wrong-row join the collision
   branch exists to prevent.

rp3 carries the ``pitcher`` (mlbam) column on every row; the map is now built
from that, so it is exact by construction and needs no second cache.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as bmd

from plv_clone import projections as proj_mod


@pytest.fixture
def synthetic_outputs(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    cache = tmp_path / "cache"
    out.mkdir(); cache.mkdir()
    pd.DataFrame({
        "rank": [1, 2, 3, 4],
        "pitcher": [663531, 671106, 999001, 500000],
        "player_name": ["Allen, Logan", "Allen, Logan", "New Debutant", "Old Vet"],
        "xfp_rp3_per_start": [5.0, 12.0, 9.5, 8.0],
        "xfp_rp3_per_start_sched": [5.0, 12.0, 9.5, 8.0],
        "xfp_rp3_sigma": [5.5, 5.5, 5.5, 5.5],
        "data_quality_tag": ["marcel_il", "data_driven_full", "data_driven_thin",
                             "data_driven_full"],
    }).to_csv(out / proj_mod.RP3_NAME, index=False)
    pd.DataFrame({
        "rank": [1], "batter": [100], "player_name": ["Some Hitter"], "team": ["NYY"],
        "xfp_rh3_per_pa": [0.5], "xfp_rh3_per_game": [2.0], "xfp_rh3_sigma": [3.0],
    }).to_csv(out / proj_mod.RH3_NAME, index=False)
    pd.DataFrame({
        "rank": [1], "pitcher": [200], "name_api": ["Some Reliever"],
        "xfp_ros": [10.0], "xfp_full_year": [20.0], "role_lag1": ["closer"],
        "xfp_p25": [5.0], "xfp_p75": [15.0],
    }).to_csv(out / proj_mod.RPRS2_NAME, index=False)
    # The frozen SP cache knows only ONE Logan Allen and none of the debutant.
    pd.DataFrame({"pitcher": [663531, 500000],
                  "player_name": ["Allen, Logan", "Old Vet"]}
                 ).to_csv(cache / "sp_multiyr_2015_2025.csv", index=False)
    pd.DataFrame({"team": ["NYY"], "bat_index": [1.0], "pit_index": [1.0]}
                 ).to_csv(cache / "team_strength_2026.csv", index=False)
    monkeypatch.setattr(proj_mod, "PROJECTIONS", proj_mod.ProjectionStore(out))
    monkeypatch.setattr(bmd, "CACHE", cache)
    return out


def test_every_rp3_row_is_reachable_by_its_own_mlbam(synthetic_outputs):
    _, _, rp3_by_mlbam, _, _ = bmd.load_projections()
    assert 999001 in rp3_by_mlbam, "current-season debutant absent from the id map"
    assert rp3_by_mlbam[999001]["per_start"] == pytest.approx(9.5)
    assert rp3_by_mlbam[500000]["per_start"] == pytest.approx(8.0)


def test_same_name_pitchers_keep_their_own_rows(synthetic_outputs):
    _, _, rp3_by_mlbam, _, _ = bmd.load_projections()
    assert rp3_by_mlbam[671106]["per_start"] == pytest.approx(12.0)
    assert rp3_by_mlbam[663531]["per_start"] == pytest.approx(5.0)


def test_id_map_does_not_depend_on_the_frozen_sp_cache(synthetic_outputs):
    (bmd.CACHE / "sp_multiyr_2015_2025.csv").unlink()
    _, _, rp3_by_mlbam, _, _ = bmd.load_projections()
    assert set(rp3_by_mlbam) == {663531, 671106, 999001, 500000}
