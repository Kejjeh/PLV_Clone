"""The live position source that severed the ADR-0009 master_hitter edge.

Three things are pinned here:

1. `load_position_frame` honors its column contract and its fallback ladder
   (cache -> live build -> legacy master CSV -> empty-with-columns), because
   every hitter surface left-merges its result and a silently-wrong shape
   degrades positions to blank with no error (the failure mode ADR-0009
   documented).
2. The cache written by `build_position_map` round-trips through the loader
   with `player_id`->`batter` / `player_name_pos`->`batter_name` renames and
   ''-primary normalized to null (the legacy master carried NaN there, and
   the UTIL replacement bucket + match-rate guard key on notna()).
3. The edge STAYS severed: no active consumer may read master_hitter_{year}
   again. xfp_h_eval.py is exempt — it reads the frozen 2023/2024 vintages
   for its V0 research baseline, not the live-season file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from plv_clone.data import player_positions as pp

ROOT = Path(__file__).resolve().parent.parent


def _write_cache(cache_dir: Path, year: int, records: list[dict]) -> Path:
    path = cache_dir / f"player_positions_{year}.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


CACHE_RECORDS = [
    {"player_id": 660271, "player_name_pos": "Shohei Ohtani",
     "primary_position": "DH", "all_positions_seen": "DH",
     "fantasy_positions": "DH", "fantasy_positions_display": "DH",
     "is_multi_position": False, "position_count": 1},
    {"player_id": 999901, "player_name_pos": "Callup Kid",
     "primary_position": "", "all_positions_seen": "",
     "fantasy_positions": "", "fantasy_positions_display": "",
     "is_multi_position": False, "position_count": 0},
]


def test_loader_reads_cache_and_honors_contract(tmp_path):
    _write_cache(tmp_path, 2026, CACHE_RECORDS)
    frame = pp.load_position_frame(2026, cache_dir=tmp_path)
    assert list(frame.columns) == pp.POSITION_FRAME_COLS
    row = frame.set_index("batter").loc[660271]
    assert row["batter_name"] == "Shohei Ohtani"
    assert row["primary_position"] == "DH"


def test_loader_normalizes_empty_primary_to_null(tmp_path):
    _write_cache(tmp_path, 2026, CACHE_RECORDS)
    frame = pp.load_position_frame(2026, cache_dir=tmp_path)
    unresolved = frame.set_index("batter").loc[999901, "primary_position"]
    assert pd.isna(unresolved)


def test_loader_falls_back_to_legacy_master_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "fetch_primary_positions", lambda year: {})
    monkeypatch.setattr(pp, "fetch_fielding_stats", lambda year: pd.DataFrame())
    legacy = tmp_path / "master_hitter_2026.csv"
    pd.DataFrame([{
        "batter": 12345, "batter_name": "Legacy Guy",
        "primary_position": "SS", "fantasy_positions": "SS",
        "fantasy_positions_display": "SS",
    }]).to_csv(legacy, index=False)
    frame = pp.load_position_frame(
        2026, cache_dir=tmp_path / "empty", legacy_master=legacy)
    assert frame.set_index("batter").loc[12345, "primary_position"] == "SS"


def test_loader_returns_empty_contract_frame_when_nothing_available(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "fetch_primary_positions", lambda year: {})
    monkeypatch.setattr(pp, "fetch_fielding_stats", lambda year: pd.DataFrame())
    frame = pp.load_position_frame(
        2026, cache_dir=tmp_path, legacy_master=tmp_path / "missing.csv")
    assert frame.empty
    assert list(frame.columns) == pp.POSITION_FRAME_COLS


def test_match_rate_guard_reports_and_warns(capsys):
    df = pd.DataFrame({"primary_position": ["SS", None, None, None]})
    rate = pp.report_position_match_rate(df, source="test map")
    out = capsys.readouterr().out
    assert rate == pytest.approx(0.25)
    assert "test map position match rate: 25%" in out
    assert "WARNING" in out


@pytest.mark.parametrize("rel_path", [
    "src/plv_clone/models/xfp/rh3.py",
    "src/plv_clone/models/xfp/rh3_april.py",
    "scripts/xfp/xfp_h2_lock.py",
    "scripts/xfp/xfp_volume_pipeline.py",
])
def test_master_hitter_edge_stays_severed(rel_path):
    """Ratchet: the active consumers must never re-grow a master_hitter read.

    (load_position_frame's own legacy fallback is the ONE sanctioned mention,
    and it lives in player_positions.py, not in these files.)
    """
    text = (ROOT / rel_path).read_text(encoding="utf-8")
    assert "master_hitter" not in text, (
        f"{rel_path} mentions master_hitter again — positions come from "
        "player_positions.load_position_frame (ADR-0009 addendum 2026-09-01); "
        "the dormant chain must not be re-wired into the active layer."
    )
