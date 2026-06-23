"""gf_statcast — map Baseball Savant per-game feed (/gf) pitches to the statcast schema.

The pitch-level analog of the boxscore bridge: pybaseball.statcast() pulls Savant's
FINALIZED search CSV, which lags ~1-2 days, so the MODELS (rh3/rp3/rprs2, archetypes,
splits, expected-stats) run a day behind. Savant's per-game feed
(baseballsavant.mlb.com/gf?game_pk=) carries the same pitch-level Statcast in real time.
This module maps a /gf pitch row into the statcast_2026 parquet schema so those games can
be appended PROVISIONALLY and the models become same-day current; the daily pybaseball
pull later overwrites them with the canonical, QC'd values.

Pure + unit-tested. The /gf endpoint is undocumented and uses human-readable
descriptions/events ("In play, out(s)", "Flyout") and different field names
(start_speed, hit_speed) — all the translation lives here.

The one field /gf lacks is estimated_woba_using_speedangle (xwOBA-on-contact); it carries
xba only. We reconstruct it from an EV x LA lookup fit on our own Statcast history
(build_xwoba_lookup), and derive actual woba_value/woba_denom from the play event via the
standard wOBA weights.
"""
from __future__ import annotations

import math

# ── wOBA weights (≈ recent-season scale; provisional data, 3-dp precision is fine) ──
# Event -> wOBA value. Outs / errors / strikeouts = 0.
WOBA_VALUE = {
    "walk": 0.69, "hit_by_pitch": 0.72,
    "single": 0.88, "double": 1.25, "triple": 1.58, "home_run": 2.00,
}
# PA-ending events that do NOT count in the wOBA denominator (IBB, sac bunt, CI).
WOBA_DENOM_ZERO = {"intent_walk", "catcher_interf", "sac_bunt"}
# PA-ending events (terminal). Everything else is a non-terminal pitch.
TERMINAL_EVENTS = set(WOBA_VALUE) | WOBA_DENOM_ZERO | {
    "strikeout", "strikeout_double_play", "field_out", "force_out",
    "grounded_into_double_play", "double_play", "field_error", "fielders_choice",
    "fielders_choice_out", "sac_fly", "sac_fly_double_play", "truncated_pa",
}

# ── gf human-readable -> statcast machine values ──
EVENT_MAP = {
    "Single": "single", "Double": "double", "Triple": "triple", "Home Run": "home_run",
    "Walk": "walk", "Intent Walk": "intent_walk", "Hit By Pitch": "hit_by_pitch",
    "Strikeout": "strikeout", "Strikeout Double Play": "strikeout_double_play",
    "Flyout": "field_out", "Lineout": "field_out", "Pop Out": "field_out",
    "Groundout": "field_out", "Grounded Into DP": "grounded_into_double_play",
    "Double Play": "double_play", "Forceout": "force_out", "Field Error": "field_error",
    "Fielders Choice": "fielders_choice", "Fielders Choice Out": "fielders_choice_out",
    "Sac Fly": "sac_fly", "Sac Fly Double Play": "sac_fly_double_play",
    "Sac Bunt": "sac_bunt", "Bunt Groundout": "field_out", "Bunt Pop Out": "field_out",
    "Catcher Interference": "catcher_interf", "Runner Out": "field_out",
}
DESC_MAP = {
    "Ball": "ball", "Ball In Dirt": "blocked_ball", "Blocked Ball": "blocked_ball",
    "Called Strike": "called_strike", "Swinging Strike": "swinging_strike",
    "Swinging Strike (Blocked)": "swinging_strike_blocked", "Foul": "foul",
    "Foul Tip": "foul_tip", "Foul Bunt": "foul_bunt", "Missed Bunt": "missed_bunt",
    "Hit By Pitch": "hit_by_pitch", "Pitchout": "pitchout",
    "In play, no out": "hit_into_play", "In play, out(s)": "hit_into_play",
    "In play, run(s)": "hit_into_play", "Automatic Ball": "automatic_ball",
    "Automatic Strike": "automatic_strike",
}


def _f(v):
    """Parse a gf numeric (handles '', None, '.370', numbers)."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def statcast_description(gf_desc) -> str | None:
    return DESC_MAP.get(str(gf_desc), None)


def statcast_event(gf_event) -> str | None:
    if not gf_event:
        return None
    return EVENT_MAP.get(str(gf_event), None)


def pitch_type_value(desc_machine, event_machine) -> str | None:
    """statcast `type`: B (ball) / S (strike) / X (in play)."""
    if event_machine or desc_machine == "hit_into_play":
        return "X"
    if desc_machine in ("ball", "blocked_ball", "pitchout", "hit_by_pitch",
                        "automatic_ball"):
        return "B"
    if desc_machine in ("called_strike", "swinging_strike", "swinging_strike_blocked",
                        "foul", "foul_tip", "foul_bunt", "missed_bunt",
                        "automatic_strike"):
        return "S"
    return None


def bb_type_from_angle(la) -> str | None:
    """Approximate statcast bb_type from launch angle (LA bins)."""
    la = _f(la)
    if la is None:
        return None
    if la < 10:
        return "ground_ball"
    if la < 25:
        return "line_drive"
    if la < 50:
        return "fly_ball"
    return "popup"


def woba_components(event_machine):
    """(woba_value, woba_denom) for a PA-ending event; (None, None) if non-terminal."""
    if not event_machine or event_machine not in TERMINAL_EVENTS:
        return None, None
    val = WOBA_VALUE.get(event_machine, 0.0)
    denom = 0 if event_machine in WOBA_DENOM_ZERO else 1
    return val, denom


# ── xwOBA-on-contact reconstruction (EV x LA lookup) ──

def build_xwoba_lookup(hist_df, ev_bin=2.0, la_bin=5.0):
    """Fit a {(ev_bucket, la_bucket): mean estimated_woba_using_speedangle} lookup from
    historical Statcast batted balls. Reconstructs Savant's speed-angle xwOBA model
    closely enough for provisional use. hist_df needs launch_speed, launch_angle,
    estimated_woba_using_speedangle."""
    df = hist_df.dropna(subset=["launch_speed", "launch_angle",
                                "estimated_woba_using_speedangle"]).copy()
    df["_ev"] = (df["launch_speed"] / ev_bin).round() * ev_bin
    df["_la"] = (df["launch_angle"] / la_bin).round() * la_bin
    grp = df.groupby(["_ev", "_la"])["estimated_woba_using_speedangle"].mean()
    return {"table": grp.to_dict(), "ev_bin": ev_bin, "la_bin": la_bin,
            "global_mean": float(df["estimated_woba_using_speedangle"].mean())}


def xwoba_from_speedangle(ls, la, lookup):
    """Look up reconstructed xwOBA-on-contact for an (EV, LA); None if no batted ball."""
    ls, la = _f(ls), _f(la)
    if ls is None or la is None or lookup is None:
        return None
    eb, lb = lookup["ev_bin"], lookup["la_bin"]
    key = (round(ls / eb) * eb, round(la / lb) * lb)
    v = lookup["table"].get(key)
    if v is None:  # nearest-neighbour fallback by EV (then global mean)
        cand = [(abs(k[0] - key[0]) + abs(k[1] - key[1]), val)
                for k, val in lookup["table"].items()]
        v = min(cand)[1] if cand else lookup["global_mean"]
    return round(float(v), 3)


def map_gf_pitch(row, game_meta, lookup=None, is_terminal=None) -> dict:
    """Map ONE /gf pitch dict to a statcast-schema row dict (load-bearing columns;
    callers fill the remaining statcast columns with NaN). game_meta supplies
    game-level fields: game_pk, game_date, game_year, home_team, away_team, game_type.

    events/woba_value/woba_denom are populated only on the PA-ENDING pitch. gf attaches
    the PA outcome to EVERY pitch of the PA, so the caller must pass `is_terminal`
    (the last pitch of each at_bat_number); when None it falls back to bool(events),
    which is only correct for an already-isolated terminal pitch (e.g. unit tests).
    """
    desc = statcast_description(row.get("description"))
    ev_raw = row.get("events")
    event = statcast_event(ev_raw)
    if is_terminal is None:
        is_terminal = bool(ev_raw)
    ls = _f(row.get("launch_speed") if row.get("launch_speed") is not None else row.get("hit_speed"))
    la = _f(row.get("launch_angle") if row.get("launch_angle") is not None else row.get("hit_angle"))
    wv, wd = woba_components(event) if is_terminal else (None, None)
    half = str(row.get("half_inning") or "").lower()
    out = {
        # keys / ids
        "game_pk": game_meta.get("game_pk"),
        "at_bat_number": row.get("ab_number"),
        "pitch_number": row.get("pitch_number"),
        "batter": row.get("batter"),
        "pitcher": row.get("pitcher"),
        "fielder_2": row.get("catcher"),
        "player_name": row.get("pitcher_name"),
        # context
        "game_date": game_meta.get("game_date"),
        "game_year": game_meta.get("game_year"),
        "game_type": game_meta.get("game_type", "R"),
        "home_team": game_meta.get("home_team"),
        "away_team": game_meta.get("away_team"),
        "inning": row.get("inning"),
        "inning_topbot": "Top" if half.startswith("top") else ("Bot" if half else None),
        "stand": row.get("stand"),
        "p_throws": row.get("p_throws"),
        "balls": _f(row.get("pre_balls")) if row.get("pre_balls") is not None else _f(row.get("balls")),
        "strikes": _f(row.get("pre_strikes")) if row.get("pre_strikes") is not None else _f(row.get("strikes")),
        "outs_when_up": _f(row.get("outs")),
        "n_thruorder_pitcher": _f(row.get("pitcher_time_thru_order")),
        # pitch shape
        "pitch_type": row.get("pitch_type"),
        "pitch_name": row.get("pitch_name"),
        "release_speed": _f(row.get("start_speed")),
        "effective_speed": _f(row.get("end_speed")),
        "release_spin_rate": _f(row.get("spin_rate")),
        "release_extension": _f(row.get("extension")),
        "pfx_x": _f(row.get("pfxX")), "pfx_z": _f(row.get("pfxZ")),
        "plate_x": _f(row.get("plate_x") if row.get("plate_x") is not None else row.get("px")),
        "plate_z": _f(row.get("plate_z") if row.get("plate_z") is not None else row.get("pz")),
        "zone": _f(row.get("zone")),
        "sz_top": _f(row.get("sz_top")), "sz_bot": _f(row.get("sz_bot")),
        # batted ball
        "launch_speed": ls, "launch_angle": la,
        "hit_distance_sc": _f(row.get("hit_distance")),
        "hc_x": _f(row.get("hc_x")), "hc_y": _f(row.get("hc_y")),
        "bb_type": bb_type_from_angle(la) if (desc == "hit_into_play") else None,
        "launch_speed_angle": (6 if str(row.get("is_barrel")) in ("1", "True", "true") else
                               (2 if ls is not None else None)),
        # bat tracking (gf carries bat speed; attack_angle/swing_length absent -> NaN)
        "bat_speed": _f(row.get("batSpeed")),
        # outcome
        "description": desc, "events": event if is_terminal else None,
        "type": pitch_type_value(desc, event if is_terminal else None),
        "des": row.get("des"),
        # wOBA (terminal only)
        "woba_value": wv, "woba_denom": wd,
        "estimated_woba_using_speedangle": (xwoba_from_speedangle(ls, la, lookup)
                                            if (desc == "hit_into_play") else None),
        "estimated_ba_using_speedangle": _f(str(row.get("xba")).lstrip("0") if row.get("xba") else None),
        # provenance
        "source": "gf_provisional",
    }
    return out
