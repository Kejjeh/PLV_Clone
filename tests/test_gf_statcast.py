"""Tests for the Savant /gf -> statcast schema mapper (lib/gf_statcast)."""
import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.gf_statcast import (
    statcast_description, statcast_event, pitch_type_value, bb_type_from_angle,
    woba_components, build_xwoba_lookup, xwoba_from_speedangle, map_gf_pitch,
)


def test_description_and_event_mapping():
    assert statcast_description("In play, out(s)") == "hit_into_play"
    assert statcast_description("Swinging Strike") == "swinging_strike"
    assert statcast_description("Called Strike") == "called_strike"
    assert statcast_description("Ball") == "ball"
    assert statcast_event("Flyout") == "field_out"
    assert statcast_event("Home Run") == "home_run"
    assert statcast_event("Walk") == "walk"
    assert statcast_event("") is None


def test_type_value():
    assert pitch_type_value("ball", None) == "B"
    assert pitch_type_value("called_strike", None) == "S"
    assert pitch_type_value("swinging_strike", None) == "S"
    assert pitch_type_value("hit_into_play", "field_out") == "X"


def test_bb_type_bins():
    assert bb_type_from_angle(2) == "ground_ball"
    assert bb_type_from_angle(15) == "line_drive"
    assert bb_type_from_angle(30) == "fly_ball"
    assert bb_type_from_angle(60) == "popup"
    assert bb_type_from_angle(None) is None


def test_woba_components():
    assert woba_components("home_run") == (2.00, 1)
    assert woba_components("walk") == (0.69, 1)
    assert woba_components("strikeout") == (0.0, 1)          # out: value 0, denom 1
    assert woba_components("field_out") == (0.0, 1)
    assert woba_components("intent_walk") == (0.0, 0)        # IBB excluded from BOTH num & denom
    assert woba_components("sac_bunt") == (0.0, 0)
    assert woba_components(None) == (None, None)             # non-terminal pitch


def test_xwoba_lookup_recovers_high_value_for_barrels():
    # a tiny history: hard line drives -> high xwOBA, weak grounders -> low
    hist = pd.DataFrame({
        "launch_speed": [104, 103, 105, 70, 72, 68],
        "launch_angle": [25, 24, 26, -5, 0, -10],
        "estimated_woba_using_speedangle": [1.9, 1.8, 2.0, 0.10, 0.12, 0.08],
    })
    lk = build_xwoba_lookup(hist)
    hot = xwoba_from_speedangle(104, 25, lk)
    cold = xwoba_from_speedangle(70, -5, lk)
    assert hot > 1.5 and cold < 0.3
    # unseen (EV,LA) falls back to nearest / global mean, not a crash
    assert xwoba_from_speedangle(99, 12, lk) is not None
    assert xwoba_from_speedangle(None, None, lk) is None


def _gf_row(**kw):
    base = dict(ab_number=12, pitch_number=5, batter=665487, pitcher=680694,
                catcher=1, pitcher_name="Kyle Bradish", inning=6, half_inning="top",
                stand="R", p_throws="R", pre_balls=1, pre_strikes=2, outs=1,
                pitch_type="FF", pitch_name="4-Seam Fastball", start_speed=95.2,
                end_speed=87.1, spin_rate=2300, extension=6.5, pfxX=5.0, pfxZ=12.0,
                plate_x=0.1, plate_z=2.5, zone=5, sz_top=3.4, sz_bot=1.6,
                pitcher_time_thru_order=2)
    base.update(kw)
    return base


GAME = dict(game_pk=824261, game_date="2026-06-22", game_year=2026,
            home_team="DET", away_team="NYY", game_type="R")


def test_map_gf_pitch_home_run():
    lk = build_xwoba_lookup(pd.DataFrame({
        "launch_speed": [106], "launch_angle": [28],
        "estimated_woba_using_speedangle": [2.0]}))
    r = map_gf_pitch(_gf_row(description="In play, run(s)", events="Home Run",
                             launch_speed=106, launch_angle=28, hit_distance=430,
                             is_barrel=1, des="homers"), GAME, lk)
    assert r["events"] == "home_run" and r["type"] == "X"
    assert r["description"] == "hit_into_play"
    assert r["release_speed"] == 95.2 and r["release_spin_rate"] == 2300
    assert r["inning_topbot"] == "Top"
    assert r["woba_value"] == 2.00 and r["woba_denom"] == 1
    assert r["launch_speed_angle"] == 6            # barrel
    assert r["bb_type"] == "fly_ball"
    assert r["estimated_woba_using_speedangle"] is not None
    assert r["game_pk"] == 824261 and r["at_bat_number"] == 12
    assert r["source"] == "gf_provisional"


def test_map_gf_pitch_non_terminal_strike_has_no_woba():
    r = map_gf_pitch(_gf_row(description="Swinging Strike", events=""), GAME)
    assert r["type"] == "S" and r["events"] is None
    assert r["woba_value"] is None and r["woba_denom"] is None
    assert r["estimated_woba_using_speedangle"] is None   # not a batted ball
    assert r["bat_speed"] is None  # no batSpeed in this row
