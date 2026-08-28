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


def _box(starts_by_pid, n_games=36, team_id=1):
    """Synthetic boxscore frame: one team, n_games, starts at given indices."""
    rows = []
    for i in range(n_games):
        rows.append(dict(game_pk=1000 + i, game_date=pd.Timestamp('2026-04-01') + pd.Timedelta(days=i),
                         mlbam_id=999, team_id=team_id, gs=0))
        for pid, idxs in starts_by_pid.items():
            if i in idxs:
                rows.append(dict(game_pk=1000 + i, game_date=pd.Timestamp('2026-04-01') + pd.Timedelta(days=i),
                                 mlbam_id=pid, team_id=team_id, gs=1))
    return pd.DataFrame(rows)


def _sp_row(**kw):
    base = dict(proj_ros_gs_per_teamgame=0.16, naive_pace=0.19, is_on_il_at_split=0)
    base.update(kw)
    return base


def test_sp_turn_map_counts_team_games_and_excludes_absences():
    """The turn is measured in TEAM GAMES; an IL-sized gap is an absence, not
    a turn, so it must not inflate the median."""
    tm = vs.sp_turn_map(_box({1: [0, 5, 10, 30, 35],      # 5,5 then a 20-game absence
                              2: [0, 6, 12, 18, 24]}))    # honest six-man turn
    assert tm.loc[1, 'median_turn'] == 5.0
    assert tm.loc[1, 'n_turns'] == 3          # 5, 5, 5 — the 20 is dropped
    assert tm.loc[1, 'absence_games'] == 20
    assert tm.loc[2, 'median_turn'] == 6.0


def test_sp_six_man_turn_reads_role():
    """A stretched turn IS the role — six-man/piggyback is not a health fade."""
    tm = vs.sp_turn_map(_box({2: [0, 6, 12, 18, 24]}))
    d = vs.decompose_sp_volume(_sp_row(), tm.loc[2])
    assert d['fade_kind'] == 'ROLE'
    assert d['in_role'] == pytest.approx(1 / 6, abs=1e-4)


def test_sp_full_turn_below_pace_reads_availability():
    tm = vs.sp_turn_map(_box({1: [0, 5, 10, 15, 20, 25, 30, 35]}))
    d = vs.decompose_sp_volume(_sp_row(), tm.loc[1])
    assert d['fade_kind'] == 'AVAILABILITY'
    assert d['in_role'] == pytest.approx(0.20, abs=1e-4)
    assert d['availability'] < 1.0


def test_sp_full_turn_but_no_longer_starting_reads_role():
    """Full turn historically, healthy, but hasn't taken a turn in weeks —
    that is a rotation removal, not an availability discount."""
    tm = vs.sp_turn_map(_box({1: [0, 5, 10, 15]}, n_games=36))
    d = vs.decompose_sp_volume(_sp_row(is_on_il_at_split=0), tm.loc[1])
    assert tm.loc[1, 'games_since_last_start'] > vs.SP_ABSENCE_GAP
    assert d['fade_kind'] == 'ROLE'
    # ...but the same shape WITH an IL flag is availability, not a demotion
    assert vs.decompose_sp_volume(_sp_row(is_on_il_at_split=1),
                                  tm.loc[1])['fade_kind'] == 'AVAILABILITY'


def test_sp_thin_sample_is_unclear_not_guessed():
    tm = vs.sp_turn_map(_box({1: [0, 5]}))
    d = vs.decompose_sp_volume(_sp_row(), tm.loc[1])
    assert d['fade_kind'] == 'UNCLEAR'
    assert d['median_turn'] != d['median_turn']       # NaN — not asserted


def test_sp_no_turn_data_falls_back_to_pace():
    d = vs.decompose_sp_volume(_sp_row(), None)
    assert d['fade_kind'] == 'UNCLEAR'
    assert d['in_role'] == pytest.approx(0.19)


def test_live_glasnow_six_man_canonical():
    """2026-08-29 canonical: LAD runs a six-man, so Glasnow's in-role start
    rate is ~1.0/wk, NOT the 1.19 league default. Skips if he leaves the
    sample or the boxscore cache is absent."""
    try:
        box = pd.read_parquet('data/research/xfp_cache/boxscore_pitchers.parquet')
    except Exception:
        pytest.skip('boxscore cache unavailable')
    tm = vs.sp_turn_map(box)
    if 607192 not in tm.index:
        pytest.skip('Glasnow not in boxscore sample')
    assert tm.loc[607192, 'median_turn'] >= 6.0
    assert tm.loc[607192, 'absence_games'] > 50      # the long IL absence


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
