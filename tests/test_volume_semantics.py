"""Role vs availability decomposition — lib.volume_semantics owns it.

The volume model's projection is a health-discounted EXPECTATION (in-role
usage x availability). Reading it as in-lineup volume produced a wrong daily
sit on 2026-08-29 (LAD Muncy: proj 2.72 read as "worst bat" while his
when-active usage was ~3.7 PA/g at 92% started — the discount priced his
2024-25 missed time, not his role). These tests pin the decomposition
contract and the ROLE/AVAILABILITY fader classification.
"""
from __future__ import annotations

import pandas as pd
import pytest

vs = pytest.importorskip("scripts.xfp.lib.volume_semantics")


def _row(**kw):
    base = dict(proj_ros_pa_per_teamgame=2.7, naive_pace=3.4,
                started_pct_to=0.90, pa_per_started_game_to=4.0,
                pa_last21=65, pa_per_teamgame_to=3.4)
    base.update(kw)
    return base


def test_availability_fader_muncy_shape():
    """Everyday role (90% started, recent pace intact), proj well below pace
    -> the fade is an availability discount, and in_role sits near the real
    when-active usage, NOT the discounted projection."""
    d = vs.decompose_hitter_volume(_row())
    assert d["fade_kind"] == "AVAILABILITY"
    assert d["in_role"] == pytest.approx(3.6, abs=0.1)
    assert d["availability"] < 0.8


def test_role_fader_peters_shape():
    """Part-time role (low started_pct) -> the fade is a ROLE signal."""
    d = vs.decompose_hitter_volume(_row(started_pct_to=0.55,
                                        pa_per_started_game_to=3.8,
                                        pa_last21=40, pa_per_teamgame_to=2.8,
                                        proj_ros_pa_per_teamgame=2.2,
                                        naive_pace=3.0))
    assert d["fade_kind"] == "ROLE"


def test_recent_collapse_reads_role_even_when_started_pct_lags():
    """started_pct is season-cumulative and lags a benching; a collapsed
    recent pace must flip the read to ROLE."""
    d = vs.decompose_hitter_volume(_row(pa_last21=25))
    assert d["fade_kind"] == "ROLE"


def test_no_fader_gap_no_kind():
    d = vs.decompose_hitter_volume(_row(proj_ros_pa_per_teamgame=3.5))
    assert d["fade_kind"] == ""


def test_live_muncy_canonical():
    """The 2026-08-29 canonical, pinned against the live CSV (skips if the
    row disappears; re-point the canonical if LAD-Muncy leaves the sample)."""
    vol = pd.read_csv("data/outputs/xfp_volume_projections.csv")
    row = vol[vol.mlbam_id == 571970]
    if not len(row):
        pytest.skip("LAD Muncy not in current volume sample")
    d = vs.decompose_hitter_volume(row.iloc[0])
    assert d["fade_kind"] == "AVAILABILITY"
    assert d["in_role"] > d["proj"]
