"""Role vs availability — the ONE owner of volume-projection semantics.

The validated volume model's `proj_ros_pa_per_teamgame` is a health-discounted
EXPECTATION: roughly (in-role usage when active) x (expected availability).
Consumers kept reading it as in-lineup volume, which breaks two decisions:

  * DAILY start/sit: on a day a player is in the lineup, the right volume is
    his in-role usage, NOT the availability-discounted projection. Canonical
    (2026-08-29): LAD Max Muncy — proj 2.72 PA/tg read as "the daily sit,"
    while his when-active usage is ~3.7 PA/g, 92% started, no platoon; the
    0.74 availability factor prices his 2024-25 missed time (73 and 100 games
    played), not a role loss.
  * FADER flags: a proj-below-pace gap can mean a genuine role erosion
    (Tristan Peters) or an availability discount on an intact everyday role
    (Muncy). The first is a lineup signal; the second is an injury-risk
    statement. Displaying both as "FADER" invites the wrong move.

This module decomposes and classifies. Display/decision layer only (Rule 13):
the model's projection itself is untouched and remains the ROS-TOTAL truth.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: started_pct at/above which the current role reads "everyday".
EVERYDAY_STARTED_PCT = 0.85
#: recent pace within this fraction of season pace reads "role intact".
RECENT_PACE_OK = 0.85

#: team-game gap between starts above which the gap is an ABSENCE (IL /
#: option / shutdown), not a rotation turn. A 5-man turn is 5, a 6-man is 6,
#: and one skipped turn is ~10 — so 9 splits "stretched turn" from "he was
#: not there". The ASG break costs no team games, so it does not inflate.
SP_ABSENCE_GAP = 9
#: median turn (team games) at/below which the rotation slot reads "full turn".
SP_NORMAL_TURN = 5.5
#: measured turns required before the turn length is trusted.
SP_MIN_TURNS = 3


def decompose_hitter_volume(row) -> dict:
    """Split a volume-projection row into in-role usage and availability.

    ``row`` is a row (Series/dict) from xfp_volume_projections.csv. Returns
    {'in_role', 'availability', 'proj', 'fade_kind'} where fade_kind is:

      * 'ROLE'         — proj sits below pace because the role itself is
                         eroding (bench/platoon/demotion signal),
      * 'AVAILABILITY' — the when-active role is intact; the discount prices
                         expected missed time (age/injury history),
      * ''             — no fader gap (proj >= naive pace).

    Daily start/sit decisions should use ``in_role``; ROS totals and swap
    math should keep using ``proj``.
    """
    proj = float(row['proj_ros_pa_per_teamgame'])
    pace = float(row['naive_pace'])
    started = float(row.get('started_pct_to') or 0)
    per_started = float(row.get('pa_per_started_game_to') or 0)
    in_role = started * per_started if started and per_started else pace
    availability = float(np.clip(proj / in_role, 0.0, 1.5)) if in_role > 0 else 1.0

    fade_kind = ''
    if proj < pace - 1e-9:
        recent = float(row.get('pa_last21') or 0) / 21.0  # builder's cal-day proxy
        season = float(row.get('pa_per_teamgame_to') or pace)
        role_intact = (started >= EVERYDAY_STARTED_PCT
                       and season > 0 and recent >= RECENT_PACE_OK * season * (19.5 / 21.0))
        fade_kind = 'AVAILABILITY' if role_intact else 'ROLE'
    return dict(in_role=round(in_role, 3), availability=round(availability, 3),
                proj=proj, fade_kind=fade_kind)


def sp_turn_map(box) -> pd.DataFrame:
    """Measure each starter's rotation TURN, in team games, from boxscores.

    ``box`` is the boxscore_pitchers frame (game_pk, game_date, mlbam_id,
    team_id, gs). Team games come from the frame itself — every distinct
    (team_id, game_pk) is one — so a pitcher's gap between starts is counted
    in TEAM GAMES, not calendar days. That is the unit the volume model
    projects in, and it is immune to off-days and the ASG break.

    Gaps above ``SP_ABSENCE_GAP`` are absences, not turns: they are excluded
    from the median (their cost belongs to availability) and reported
    separately. Returns one row per starter indexed by mlbam_id with
    median_turn, n_turns, games_since_last_start, absence_games.
    """
    box = box.copy()
    box['game_date'] = pd.to_datetime(box['game_date'])
    tg = (box[['team_id', 'game_pk', 'game_date']].drop_duplicates()
          .sort_values(['team_id', 'game_date', 'game_pk']))
    tg['tidx'] = tg.groupby('team_id').cumcount()
    last = tg.groupby('team_id')['tidx'].max().rename('team_last_tidx')
    st = (box[box['gs'] == 1]
          .merge(tg, on=['team_id', 'game_pk', 'game_date'], how='left')
          .merge(last, on='team_id', how='left')
          .sort_values(['mlbam_id', 'tidx']))

    rows = []
    for pid, g in st.groupby('mlbam_id'):
        gaps = np.diff(g['tidx'].values)
        gaps = gaps[gaps > 0]
        turns = gaps[gaps <= SP_ABSENCE_GAP]
        rows.append(dict(
            mlbam_id=int(pid),
            median_turn=float(np.median(turns)) if len(turns) else np.nan,
            n_turns=int(len(turns)),
            games_since_last_start=int(g['team_last_tidx'].iloc[-1] - g['tidx'].iloc[-1]),
            absence_games=int(gaps[gaps > SP_ABSENCE_GAP].sum()),
        ))
    return pd.DataFrame(rows).set_index('mlbam_id')


def decompose_sp_volume(row, turn=None) -> dict:
    """Split an SP volume-projection row into in-role turn and availability.

    Same conflation as the hitter side, different mechanism: a starter's
    ``proj_ros_gs_per_teamgame`` below pace can mean the TURN itself is
    stretched (six-man rotation, piggyback, innings limit) or that a full-turn
    starter is expected to miss time. Only the first is a role signal.

    ``row`` comes from xfp_sp_volume_projections.csv; ``turn`` is that
    pitcher's row from :func:`sp_turn_map` (or None when unmeasured). Returns
    {'in_role', 'availability', 'proj', 'fade_kind', 'median_turn'} with
    fade_kind in 'ROLE' / 'AVAILABILITY' / 'UNCLEAR' / ''.

    Weekly start COUNTS for an active arm should use ``in_role``; ROS totals
    and swap math keep using ``proj``, which correctly prices missed time.
    """
    proj = float(row['proj_ros_gs_per_teamgame'])
    pace = float(row['naive_pace'])
    med = float(turn['median_turn']) if turn is not None and pd.notna(
        turn.get('median_turn')) else np.nan
    n_turns = int(turn['n_turns']) if turn is not None else 0
    measured = n_turns >= SP_MIN_TURNS and med == med and med > 0

    in_role = 1.0 / med if measured else pace
    availability = float(np.clip(proj / in_role, 0.0, 1.5)) if in_role > 0 else 1.0

    fade_kind = ''
    if proj < pace - 1e-9:
        if not measured:
            fade_kind = 'UNCLEAR'
        elif med > SP_NORMAL_TURN:
            fade_kind = 'ROLE'          # the turn itself is stretched
        elif (turn is not None
              and float(turn.get('games_since_last_start') or 0) > SP_ABSENCE_GAP
              and not float(row.get('is_on_il_at_split') or 0)):
            fade_kind = 'ROLE'          # full turn, but no longer taking one
        else:
            fade_kind = 'AVAILABILITY'  # full turn when active; missed-time discount
    return dict(in_role=round(in_role, 4), availability=round(availability, 3),
                proj=proj, fade_kind=fade_kind,
                median_turn=med if measured else np.nan)
