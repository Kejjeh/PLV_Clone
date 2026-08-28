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

#: started_pct at/above which the current role reads "everyday".
EVERYDAY_STARTED_PCT = 0.85
#: recent pace within this fraction of season pace reads "role intact".
RECENT_PACE_OK = 0.85


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
