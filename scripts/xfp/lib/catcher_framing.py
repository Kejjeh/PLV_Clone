"""catcher_framing — standalone display tag for SP triangulate cards.

Validated 2026-06-03 (data/research/validation_runs/catcher_framing_boom_modifier.md):
  - Q5 vs Q1 raw boom-rate gap: +4.6 pp
  - Within-pitcher paired test (n=208 pitchers, t=2.40, p=0.017): +3.06 pp REAL
  - Marginal lift inside boom_stack=0 cell: +3.5 pp; inside boom_stack=1: +7.4 pp
  - 6/7 years positive (2018, 2019, 2021-2025)
  - Verdict: SHIP_AS_DISPLAY_TAG (NOT a 5th boom_stack component — would
    double-count downstream catcher-receiving effects already absorbed by
    drift_swstr / c_plus_swstr features in rp3 v2).

This module derives, on the fly from `statcast_2026.parquet`:
  1. Per-catcher 2026 framing_runs_per_100 using the same shadow-zone formula
     as build_catcher_framing.py / analyze_catcher_framing_boom.py.
  2. Per-team modal 2026 catcher (most-pitches catcher when that team is on
     defense). Used as a v1 baseline — does not consult the daily lineup.
  3. 2026 quintile assignment within catchers with >=200 shadow pitches
     (`_MIN_SHADOW_PITCHES`, lower than the 300-pitch full-season floor from
     the source methodology; originally relaxed because the 2026 season was
     young). Doc/code drift fixed 2026-07-29 — the code had been filtering at
     100. Revisit whether the full 300 floor should be restored now that the
     season is mature.

Public API: `compute_catcher_framing(pitcher_team: str) -> dict`.

Schema additive only — boom_stack engine is NOT touched.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

# Minimum shadow pitches for a catcher to receive a framing quintile. Named so
# the docstring and the filter can never drift apart again (they did: doc said
# 200, code filtered 100 — fixed 2026-07-29). Methodological floor, not one of
# the measured stabilization minimums.
_MIN_SHADOW_PITCHES = 200

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_STATCAST_2026 = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'statcast_2026.parquet')

# 2026 in-season quintile floor — looser than the 300-pitch full-season threshold.
_QUINTILE_SHADOW_PITCH_FLOOR = 200

# Hand-maintained MLBAM id -> display name for the leaderboard catchers (top5/bot5
# and a handful of mid-tier names that show up in roster decisions). The shadow-
# zone derivation gives us mlbam ids only; this map saves us a pybaseball call
# at import-time. If a team's modal catcher is missing from the map, we fall
# back to "MLBAM <id>" so the tag still renders.
_CATCHER_NAME_OVERRIDES: dict[int, str] = {
    693307: "Dillon Dingler",
    686452: "Drew Millas",
    669224: "Austin Wells",
    592663: "J.T. Realmuto",
    686780: "Pedro Pagés",
    668939: "Adley Rutschman",
    696100: "Hunter Goodman",
    663886: "Tyler Stephenson",
    669127: "Shea Langeliers",
    681351: "Logan O'Hoppe",
    641555: "J.C. Escarra",
    682626: "Francisco Álvarez",
    672515: "Gabriel Moreno",
    665966: "Connor Wong",
    608348: "Yan Gomes",
    666310: "Bo Naylor",
    700337: "Edgar Quero",
    543877: "Yainer Diaz",
    521692: "Salvador Perez",
    669257: "Will Smith",
    689414: "Nick Fortes",
    661388: "William Contreras",
    680777: "Ryan Jeffers",
    682626: "Francisco Álvarez",
    680779: "Henry Davis",
    666023: "Luis Campusano",
    663728: "Cal Raleigh",
    672275: "Patrick Bailey",
    663743: "René Pinto",
    643376: "Jonah Heim",
    678218: "Alejandro Kirk",
    660688: "Keibert Ruiz",
    686948: "Sean Murphy",
    686452: "Drew Millas",
}


# ---------------------------------------------------------------------------
# Shadow-zone framing (replicates analyze_catcher_framing_boom.shadow_zone_framing)
# ---------------------------------------------------------------------------
def _shadow_zone_framing_2026() -> pd.DataFrame:
    """Compute per-catcher 2026 framing_runs_per_100 from statcast_2026.parquet.

    Returns columns: catcher_mlbam, shadow_pitches, framing_runs_per_100.
    """
    if not os.path.exists(_STATCAST_2026):
        return pd.DataFrame(columns=['catcher_mlbam', 'shadow_pitches', 'framing_runs_per_100'])
    df = pd.read_parquet(
        _STATCAST_2026,
        columns=['fielder_2', 'description', 'plate_x', 'plate_z', 'sz_top', 'sz_bot'],
    )
    df = df[df['description'].isin({'called_strike', 'ball', 'blocked_ball'})].copy()
    if df.empty:
        return pd.DataFrame(columns=['catcher_mlbam', 'shadow_pitches', 'framing_runs_per_100'])
    px = df['plate_x'].abs()
    pz = df['plate_z']
    sz_top = df['sz_top']
    sz_bot = df['sz_bot']
    in_zone = (px <= 0.83) & (pz <= sz_top) & (pz >= sz_bot)
    shadow_x = (px > 0.83) & (px <= 1.0) & (pz <= sz_top + 0.2) & (pz >= sz_bot - 0.2)
    shadow_z_top = (px <= 1.0) & (pz > sz_top) & (pz <= sz_top + 0.2)
    shadow_z_bot = (px <= 1.0) & (pz < sz_bot) & (pz >= sz_bot - 0.2)
    df['shadow'] = (shadow_x | shadow_z_top | shadow_z_bot) & ~in_zone
    df['called_strike'] = (df['description'] == 'called_strike').astype(int)
    sh = df[df['shadow']].copy()
    if sh.empty:
        return pd.DataFrame(columns=['catcher_mlbam', 'shadow_pitches', 'framing_runs_per_100'])
    lg = sh['called_strike'].mean()
    g = sh.groupby('fielder_2').agg(
        shadow_pitches=('shadow', 'size'),
        shadow_called_strikes=('called_strike', 'sum'),
    ).reset_index()
    # Align to the documented floor. The module docstring has always said 200
    # shadow pitches; the code filtered at 100 — a silent drift that made the
    # framing quintiles more permissive than the documented methodology (and
    # than the 300-pitch full-season floor it was deliberately relaxed from).
    # The docstring's justification for relaxing ("the 2026 season is ~2 mo
    # old") has since expired, so if anything this should climb back toward
    # 300; 200 restores doc/code agreement without a second unreviewed change.
    # NOTE: framing is NOT in the 2026-07-29 stabilization study's metric set
    # (that covered hitter rate metrics + SP/RP stuff/command), so this floor is
    # methodological, not measured — it does not belong in stabilization.py.
    g = g[g['shadow_pitches'] >= _MIN_SHADOW_PITCHES].copy()
    g['framing_rate'] = g['shadow_called_strikes'] / g['shadow_pitches']
    # 0.13 runs per called strike, per 100 shadow pitches (Sports Info Solutions)
    g['framing_runs_per_100'] = (g['framing_rate'] - lg) * 0.13 * 100
    g = g.rename(columns={'fielder_2': 'catcher_mlbam'})
    return g[['catcher_mlbam', 'shadow_pitches', 'framing_runs_per_100']]


# ---------------------------------------------------------------------------
# Team -> modal 2026 catcher
# ---------------------------------------------------------------------------
def _modal_catcher_per_team() -> dict[str, int]:
    """team_abbr -> modal catcher mlbam id (most pitches received in 2026
    when that team was on defense).
    """
    if not os.path.exists(_STATCAST_2026):
        return {}
    sc = pd.read_parquet(
        _STATCAST_2026,
        columns=['home_team', 'away_team', 'inning_topbot', 'fielder_2'],
    )
    sc = sc[sc['fielder_2'].notna()].copy()
    # Defensive team = home_team when 'Top' of inning (away batting),
    # away_team when 'Bot' of inning.
    sc['def_team'] = sc['home_team'].where(sc['inning_topbot'] == 'Top', sc['away_team'])
    modal = (
        sc.groupby(['def_team', 'fielder_2']).size()
          .reset_index(name='n')
          .sort_values(['def_team', 'n'], ascending=[True, False])
          .drop_duplicates('def_team')
    )
    return {str(t): int(c) for t, c in zip(modal['def_team'], modal['fielder_2'])}


# ---------------------------------------------------------------------------
# Combined framing table: team -> {catcher, csaa, quintile, name}
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_framing_table() -> dict[str, dict]:
    """Build per-team modal-catcher framing snapshot for 2026.

    Returns: team_abbr -> {
        'modal_catcher_mlbam': int,
        'modal_catcher_name':  str,
        'csaa_runs':           float,         # framing_runs_per_100
        'shadow_pitches':      int,
        'framing_quintile':    int | None,    # 1..5, None if shadow_n < floor
    }
    """
    fr = _shadow_zone_framing_2026()
    team_to_catcher = _modal_catcher_per_team()
    if fr.empty or not team_to_catcher:
        return {}

    # 2026 quintile cuts only on catchers above the in-season floor.
    fr_q = fr[fr['shadow_pitches'] >= _QUINTILE_SHADOW_PITCH_FLOOR].copy()
    if len(fr_q) >= 5:
        # Ties broken by .rank(method='first') so qcut never raises.
        fr_q['framing_quintile'] = pd.qcut(
            fr_q['framing_runs_per_100'].rank(method='first'),
            5,
            labels=[1, 2, 3, 4, 5],
        ).astype(int)
    else:
        fr_q['framing_quintile'] = np.nan

    fr_idx = fr.set_index('catcher_mlbam')
    quint_idx = fr_q.set_index('catcher_mlbam')['framing_quintile'].to_dict()

    out: dict[str, dict] = {}
    for team, mlbam in team_to_catcher.items():
        if mlbam not in fr_idx.index:
            continue
        row = fr_idx.loc[mlbam]
        out[team] = {
            'modal_catcher_mlbam': int(mlbam),
            'modal_catcher_name': _CATCHER_NAME_OVERRIDES.get(int(mlbam), f"MLBAM {int(mlbam)}"),
            'csaa_runs': float(row['framing_runs_per_100']),
            'shadow_pitches': int(row['shadow_pitches']),
            'framing_quintile': int(quint_idx[mlbam]) if mlbam in quint_idx else None,
        }
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_catcher_framing(pitcher_team: Optional[str]) -> dict:
    """Return the catcher-framing display-tag payload for a pitcher's team.

    Args:
        pitcher_team: 3-letter MLB team abbreviation (e.g. 'NYY', 'LAA').

    Returns:
        {
          'is_elite_framer':     bool,     # True iff modal catcher quintile == 5
          'is_framing_tax':      bool,     # True iff modal catcher quintile == 1
          'modal_catcher_name':  str | None,
          'csaa_runs':           float | None,
          'framing_quintile':    int | None,
        }
    """
    out = {
        'is_elite_framer': False,
        'is_framing_tax': False,
        'modal_catcher_name': None,
        'csaa_runs': None,
        'framing_quintile': None,
    }
    if not pitcher_team or not isinstance(pitcher_team, str):
        return out
    try:
        table = _load_framing_table()
    except Exception:
        return out
    rec = table.get(pitcher_team)
    if rec is None:
        return out
    q = rec.get('framing_quintile')
    out['modal_catcher_name'] = rec.get('modal_catcher_name')
    out['csaa_runs'] = rec.get('csaa_runs')
    out['framing_quintile'] = q
    if q == 5:
        out['is_elite_framer'] = True
    elif q == 1:
        out['is_framing_tax'] = True
    return out
