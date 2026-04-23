"""
Shared pytest fixtures for PLV Clone tests.

Provides a small synthetic pitch DataFrame that covers all outcome types
and is valid for testing ingestion, cleaning, feature engineering,
and scoring logic without requiring real Statcast data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


N_PITCHES = 200
RNG = np.random.default_rng(42)


def _make_synthetic_pitches(n: int = N_PITCHES, seed: int = 42) -> pd.DataFrame:
    """Create a minimal synthetic pitch DataFrame with all required fields."""
    rng = np.random.default_rng(seed)

    # Pitch keys
    game_pks = rng.integers(700000, 700010, size=n)
    at_bat_numbers = rng.integers(1, 10, size=n)
    pitch_numbers = rng.integers(1, 6, size=n)
    pitchers = rng.choice([100, 101, 102, 103, 104], size=n)
    batters = rng.choice([200, 201, 202, 203, 204, 205, 206, 207], size=n)

    # Unique pitch keys — increment pitch_number to ensure uniqueness
    keys = set()
    rows = []
    idx = 0
    for i in range(n):
        pk = (int(game_pks[i]), int(at_bat_numbers[i]), int(pitch_numbers[i]),
              int(pitchers[i]), int(batters[i]))
        while pk in keys:
            pitch_numbers[i] = (pitch_numbers[i] % 10) + 1
            pk = (int(game_pks[i]), int(at_bat_numbers[i]), int(pitch_numbers[i]),
                  int(pitchers[i]), int(batters[i]))
            idx += 1
            if idx > 1000:
                break
        keys.add(pk)
        rows.append(pk)

    game_pks_u, ab_u, pn_u, pit_u, bat_u = zip(*rows)

    # Descriptions covering all outcome types
    descriptions = rng.choice(
        [
            "ball", "called_strike",
            "swinging_strike", "swinging_strike_blocked",
            "foul", "foul_tip",
            "hit_into_play", "hit_into_play_no_out", "hit_into_play_score",
        ],
        size=n,
        p=[0.22, 0.18, 0.10, 0.02, 0.15, 0.03, 0.15, 0.08, 0.07],
    )

    # Pitch types
    pitch_types = rng.choice(
        ["FF", "SI", "SL", "CU", "CH", "FS"],
        size=n,
        p=[0.35, 0.20, 0.20, 0.10, 0.10, 0.05],
    )

    # Count states
    balls = rng.integers(0, 4, size=n)
    strikes = rng.integers(0, 3, size=n)

    # Handedness
    p_throws = rng.choice(["R", "L"], size=n, p=[0.75, 0.25])
    stand = rng.choice(["R", "L"], size=n, p=[0.60, 0.40])

    # Physical pitch characteristics
    release_speed = rng.normal(92, 5, size=n).clip(70, 105)
    pfx_x = rng.normal(0, 8, size=n)
    pfx_z = rng.normal(6, 8, size=n)
    plate_x = rng.normal(0, 1, size=n).clip(-2, 2)
    plate_z = rng.normal(2.5, 0.7, size=n).clip(0.5, 4.5)
    release_pos_x = rng.normal(-1.5, 0.5, size=n)
    release_pos_z = rng.normal(5.8, 0.3, size=n)
    release_extension = rng.normal(6.2, 0.5, size=n).clip(4, 8)
    zone = rng.choice(list(range(1, 10)) + list(range(11, 15)), size=n)

    # Launch metrics (null for non-in-play)
    in_play_mask = np.isin(descriptions, ["hit_into_play", "hit_into_play_no_out", "hit_into_play_score"])
    launch_speed = np.where(in_play_mask, rng.normal(90, 15, size=n).clip(0, 120), np.nan)
    launch_angle = np.where(in_play_mask, rng.normal(15, 25, size=n).clip(-90, 90), np.nan)
    xwoba = np.where(
        in_play_mask,
        rng.beta(1.5, 4, size=n),  # roughly 0–1, right-skewed
        np.nan,
    )

    # Run value
    delta_run_exp = rng.normal(0, 0.05, size=n)

    # wOBA fields
    woba_value = np.where(in_play_mask, rng.beta(1.5, 4, size=n), np.nan)
    woba_denom = np.where(in_play_mask, 1.0, np.nan)

    events_map = {
        "hit_into_play": "field_out",
        "hit_into_play_no_out": "single",
        "hit_into_play_score": "home_run",
        "ball": None,
        "called_strike": None,
        "swinging_strike": None,
        "swinging_strike_blocked": None,
        "foul": None,
        "foul_tip": None,
    }
    events = [events_map.get(d) for d in descriptions]

    # Dates
    from datetime import date, timedelta
    start_date = date(2023, 4, 1)
    game_dates = [str(start_date + timedelta(days=int(rng.integers(0, 180)))) for _ in range(n)]

    return pd.DataFrame({
        "game_date": game_dates,
        "game_pk": list(game_pks_u),
        "at_bat_number": list(ab_u),
        "pitch_number": list(pn_u),
        "pitcher": list(pit_u),
        "batter": list(bat_u),
        "player_name": [f"Pitcher{p}" for p in pit_u],
        "pitch_type": pitch_types,
        "release_speed": release_speed,
        "release_pos_x": release_pos_x,
        "release_pos_z": release_pos_z,
        "pfx_x": pfx_x,
        "pfx_z": pfx_z,
        "plate_x": plate_x,
        "plate_z": plate_z,
        "release_extension": release_extension,
        "balls": balls,
        "strikes": strikes,
        "p_throws": p_throws,
        "stand": stand,
        "zone": zone,
        "description": descriptions,
        "events": events,
        "launch_speed": launch_speed,
        "launch_angle": launch_angle,
        "estimated_woba_using_speedangle": xwoba,
        "delta_run_exp": delta_run_exp,
        "woba_value": woba_value,
        "woba_denom": woba_denom,
        "on_1b": rng.choice([True, False], size=n, p=[0.3, 0.7]),
        "on_2b": rng.choice([True, False], size=n, p=[0.2, 0.8]),
        "on_3b": rng.choice([True, False], size=n, p=[0.1, 0.9]),
        "outs_when_up": rng.integers(0, 3, size=n),
        "inning": rng.integers(1, 10, size=n),
    })


@pytest.fixture(scope="session")
def raw_df() -> pd.DataFrame:
    """Raw synthetic Statcast DataFrame (pre-cleaning)."""
    return _make_synthetic_pitches(N_PITCHES, seed=42)


@pytest.fixture(scope="session")
def clean_df(raw_df) -> pd.DataFrame:
    """Cleaned version of the synthetic DataFrame."""
    from plv_clone.data.clean_statcast import clean_statcast
    return clean_statcast(raw_df)


@pytest.fixture(scope="session")
def feature_df(clean_df) -> pd.DataFrame:
    """Feature-engineered version of the cleaned DataFrame."""
    from plv_clone.features.pitch_features import build_pitch_features
    from plv_clone.features.context_features import build_context_features
    return build_context_features(build_pitch_features(clean_df))
