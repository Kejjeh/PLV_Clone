"""
build_player_profiles_dashboard.py — Player Profiles dashboard.

Reads:
  data/research/hitter_ratings_master.csv       (after Fix A: includes `batter`)
  data/research/sp_ratings_master.csv           (after Fix A: includes `pitcher`)
  data/research/hitter_archetype_definitions.json
  data/research/sp_archetype_definitions.json
  data/research/hitter_boundary_validation.json
  data/research/sp_boundary_validation.json

Writes:
  data/outputs/player_profiles.html        (local build, tracked)
  xfp-model/docs/player_profiles.html      (published mirror)

Tabs: Home / Hitters / Pitchers. Year-mode selector: Single Year / All Years /
2025+2026 Blend. 12 Plotly quadrant scatters (6 hitter, 6 SP) with Pearson r
computed in JS from the active filter. Player career-arc modal triggered by
search, leaderboard, scatter point, or archetype-table row click.

Schema assertions fail-fast before HTML emission. Refresh wiring is fail-closed.
"""
from __future__ import annotations
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT as REPO  # single source for repo paths
from lib.archetype_engine import rate_value, label_for_cell  # shared 20-80 seam
RES = REPO / 'data/research'
CACHE = REPO / 'data/research/xfp_cache'
OUT_LOCAL = REPO / 'data/outputs/player_profiles.html'
OUT_PUB = REPO / 'xfp-model/docs/player_profiles.html'

H_MASTER = RES / 'hitter_ratings_master.csv'
S_MASTER = RES / 'sp_ratings_master.csv'
R_MASTER = RES / 'rp_ratings_master.csv'
H_DEFS   = RES / 'hitter_archetype_definitions.json'
S_DEFS   = RES / 'sp_archetype_definitions.json'
R_DEFS   = RES / 'rp_archetype_definitions.json'
H_BOUND  = RES / 'hitter_boundary_validation.json'
S_BOUND  = RES / 'sp_boundary_validation.json'
R_BOUND  = RES / 'rp_boundary_validation.json'

H_ROLLING = CACHE / 'rolling_hitters_2018_2026.csv'
S_ROLLING = CACHE / 'rolling_pitchers_2018_2026.csv'
R_ROLLING = CACHE / 'rolling_relievers_2018_2026.csv'
H_SRC     = CACHE / 'hitters_multiyr_2015_2026.csv'
S_SRC     = CACHE / 'sp_multiyr_2015_2025.csv'
R_SRC     = CACHE / 'relievers_multiyr_2018_2026.csv'

# Validated production-model projections — joined onto CURRENT-YEAR rows only so
# the quadrant can plot a player's model rank (rh3/rp3/rprs2) against their actual
# FP performance or archetype ratings. rh3 also supplies primary_position, the
# POS-filter fallback for FA hitters (eligible_positions only covers rostered).
RH3_PROJ   = REPO / 'data/outputs/xfp_rh3_projections.csv'
RP3_PROJ   = REPO / 'data/outputs/xfp_rp3_projections.csv'
RPRS2_PROJ = REPO / 'data/outputs/xfp_rprs2_projections.csv'

# Whitelisted columns — drives payload size.
H_COLS = [
    'batter', 'year', 'player_name', 'team', 'pa', 'fp_per_pa', 't1_fp_projection', 't2_fp_projection',
    # Lineup-spot context (structural-leverage signal, gmLI analog).
    # Display-only — never enters the rated domains.
    'mean_lineup_spot', 'top5_share', 'lineup_role_tier', 'lineup_spot_entropy',
    'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag', 'data_tier',
    'OVERALL', 'CONTACT', 'POWER', 'DISCIPLINE', 'SB',
    'Z_CONTACT', 'O_CONTACT', 'K_AVOIDANCE', 'CONTACT_QUALITY', 'SPRAY_PROFILE',
    'RAW_POWER', 'LAUNCH_OPTIM', 'DAMAGE_PROD',
    'PATIENCE', 'AGGRESSION', 'SPEED_TOOL', 'SB_CONVERSION',
    'babip_career', 'babip_delta', 'babip_luck_flag',
    'archetype', 'contact_subtype', 'power_subtype', 'discipline_subtype',
    'sb_tier', 'spray_archetype',
    'age', 'age_tier', 'boundary_tier', 'rank_in_year',
    'r_Contact', 'r_K', 'r_BABIP', 'r_xCON',
    'r_Barrel', 'r_HardHit', 'r_ISO', 'r_HRrate', 'r_HRrate_parkadj', 'hr_parkadj_delta', 'pf_HR', 'r_PullFB',
    'r_BB', 'r_Chase', 'r_ZSwing',
    'r_SBrate', 'r_Sprint',
]
S_COLS = [
    'pitcher', 'year', 'player_name', 'gs', 'tbf', 'fp_per_start',
    't1_fp_projection', 't2_fp_projection',
    'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag', 'data_tier',
    'OVERALL', 'STUFF', 'MOVEMENT', 'CONTROL',
    'SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID', 'STRIKE_THROWING',
    'archetype', 'stuff_subtype',
    'velo_rating', 'velo_tier', 'pitch_archetype', 'primary_group',
    'age', 'age_tier', 'boundary_tier', 'rank_in_year',
    'r_K', 'r_SwStr', 'r_CSW',
    'r_HRrate', 'r_Barrel', 'r_HardHit', 'r_GB', 'r_xCON',
    'r_BB',
]

# RP master CSV columns. Different schema from SP:
#  - usage cols: g/sv/hld/ip_per_appearance instead of gs/tbf
#  - 3 main domains: STUFF / CONTROL / BATTED_BALL (vs SP's STUFF/MOVEMENT/CONTROL)
#  - 6 sub-domains: SWING_MISS, CALLED_STRIKE, WALK_AVOID, VELO, GB_TENDENCY, BULK_IP
#    (vs SP's SWING_MISS, CALLED_STRIKE, DAMAGE_SUPP, GB_TENDENCY, WALK_AVOID, velo_rating)
#  - tags: CLOSER / HIGH_LEVERAGE / MULTI_INNING_BULK / OBVIOUS_PLATOON_GUY
R_COLS = [
    'pitcher', 'year', 'player_name', 'team_abbr', 'g', 'gs', 'tbf', 'sv', 'hld',
    'ip_per_appearance', 'fp_per_g', 't1_fp_projection', 't2_fp_projection',
    'data_tier',
    'OVERALL', 'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag',
    'STUFF', 'CONTROL', 'BATTED_BALL',
    'SWING_MISS', 'CALLED_STRIKE', 'VELO', 'WALK_AVOID', 'GB_TENDENCY', 'BULK_IP',
    'archetype', 'stuff_subtype', 'cell', 'velo_tier',
    'age', 'age_tier', 'boundary_tier', 'rank_in_year',
    'CLOSER', 'HIGH_LEVERAGE', 'MULTI_INNING_BULK', 'OBVIOUS_PLATOON_GUY',
    'leverage_tier', 'FIREMAN', 'ir', 'inherited_stranded_pct',
    'r_K',
]



def _fail(msg: str):
    print(f'  ERR  {msg}', flush=True)
    sys.exit(1)


def pretty_sp_name(s):
    """`Skubal, Tarik` -> `Tarik Skubal`. Pass through otherwise."""
    if isinstance(s, str) and ',' in s:
        a, b = s.split(',', 1)
        return f'{b.strip()} {a.strip()}'
    return s


def assert_schema():
    for p in [H_MASTER, S_MASTER, R_MASTER,
              H_DEFS, S_DEFS, R_DEFS, H_BOUND, S_BOUND, R_BOUND]:
        if not p.exists():
            _fail(f'missing input: {p}')

    h = pd.read_csv(H_MASTER)
    s = pd.read_csv(S_MASTER)
    rp = pd.read_csv(R_MASTER)

    miss_h = [c for c in H_COLS if c not in h.columns]
    miss_s = [c for c in S_COLS if c not in s.columns]
    miss_r = [c for c in R_COLS if c not in rp.columns]
    if miss_h: _fail(f'hitter master missing cols: {miss_h}')
    if miss_s: _fail(f'sp master missing cols: {miss_s}')
    if miss_r: _fail(f'rp master missing cols: {miss_r}')

    if h.duplicated(['batter', 'year']).any():
        n = int(h.duplicated(['batter', 'year']).sum())
        _fail(f'hitter master has {n} duplicate (batter, year) rows')
    if s.duplicated(['pitcher', 'year']).any():
        n = int(s.duplicated(['pitcher', 'year']).sum())
        _fail(f'sp master has {n} duplicate (pitcher, year) rows')
    if rp.duplicated(['pitcher', 'year']).any():
        n = int(rp.duplicated(['pitcher', 'year']).sum())
        _fail(f'rp master has {n} duplicate (pitcher, year) rows')

    for c in ['CONTACT', 'POWER', 'DISCIPLINE', 'SB', 'OVERALL', 'rank_in_year',
              'Z_CONTACT', 'O_CONTACT', 'K_AVOIDANCE', 'CONTACT_QUALITY', 'SPRAY_PROFILE',
              'RAW_POWER', 'LAUNCH_OPTIM', 'DAMAGE_PROD',
              'PATIENCE', 'AGGRESSION', 'SPEED_TOOL', 'SB_CONVERSION']:
        n = int(h[c].isna().sum())
        if n: _fail(f'hitter master {c} has {n} null rows')
    for c in ['STUFF', 'MOVEMENT', 'CONTROL', 'OVERALL', 'rank_in_year',
              'SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID',
              'STRIKE_THROWING']:
        n = int(s[c].isna().sum())
        if n: _fail(f'sp master {c} has {n} null rows')
    for c in ['STUFF', 'CONTROL', 'BATTED_BALL', 'OVERALL',
              'SWING_MISS', 'CALLED_STRIKE', 'VELO', 'WALK_AVOID',
              'GB_TENDENCY', 'BULK_IP']:
        n = int(rp[c].isna().sum())
        if n: _fail(f'rp master {c} has {n} null rows')

    # Definitions and boundary JSONs load + have expected shape
    for p in [H_DEFS, S_DEFS, R_DEFS]:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict) or not d:
            _fail(f'archetype defs malformed: {p}')
    for p in [H_BOUND, S_BOUND, R_BOUND]:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        for k in ['EDGE', 'NEAR_EDGE', 'SOLID']:
            if k not in d:
                _fail(f'boundary validation missing {k} in {p}')

    return h, s, rp


def build_hitter_records(h: pd.DataFrame):
    df = h[H_COLS].copy()
    # Replace pandas NaN with None for clean JSON
    df['fp_per_pa'] = df['fp_per_pa'].round(3)
    for c in ['age', 'rank_in_year']:
        df[c] = df[c].astype('Int64')
    for c in ['CONTACT', 'POWER', 'DISCIPLINE', 'SB', 'OVERALL',
              'Z_CONTACT', 'O_CONTACT', 'K_AVOIDANCE', 'CONTACT_QUALITY', 'SPRAY_PROFILE',
              'RAW_POWER', 'LAUNCH_OPTIM', 'DAMAGE_PROD',
              'PATIENCE', 'AGGRESSION', 'SPEED_TOOL', 'SB_CONVERSION']:
        df[c] = df[c].astype(int)
    # Component r_* are ints in source; preserve.
    return json.loads(df.to_json(orient='records'))


def build_sp_records(s: pd.DataFrame):
    df = s[S_COLS].copy()
    df['player_name'] = df['player_name'].apply(pretty_sp_name)
    df['fp_per_start'] = df['fp_per_start'].round(2)
    for c in ['age', 'rank_in_year']:
        df[c] = df[c].astype('Int64')
    for c in ['STUFF', 'MOVEMENT', 'CONTROL', 'velo_rating', 'OVERALL',
              'SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID',
              'STRIKE_THROWING']:
        df[c] = df[c].astype('Int64')
    recs = json.loads(df.to_json(orient='records'))
    for r in recs:
        r['role'] = 'SP'
    return recs


def build_rp_records(rp: pd.DataFrame):
    """Map RP master rows to record shape, with role='RP' tag plus the RP-native
    BATTED_BALL / BULK_IP / VELO sub-domain fields and CLOSER / HIGH_LEVERAGE /
    MULTI_INNING_BULK / PLATOON role chips.

    The SP-shaped schema bridges (gs ← g, fp_per_start ← fp_per_g, MOVEMENT
    ← BATTED_BALL, velo_rating ← VELO) were removed 2026-05-30 — the Pitchers
    tab is now split into role-native SP and RP tabs, and the modal reads RP
    fields directly off `role === 'RP'` branches. The native fields below
    (BATTED_BALL / VELO / g / fp_per_g) are the only pitcher-rate keys an RP
    record carries.
    """
    df = rp[R_COLS].copy()
    df['player_name'] = df['player_name'].apply(pretty_sp_name)
    df['fp_per_g'] = df['fp_per_g'].round(2)

    for c in ['age', 'rank_in_year', 'g', 'gs', 'tbf', 'sv', 'hld']:
        df[c] = df[c].astype('Int64')
    for c in ['STUFF', 'CONTROL', 'BATTED_BALL', 'OVERALL',
              'SWING_MISS', 'CALLED_STRIKE', 'VELO', 'WALK_AVOID',
              'GB_TENDENCY', 'BULK_IP']:
        df[c] = df[c].astype('Int64')

    df['team'] = df['team_abbr']

    # RP-specific fields the SP path doesn't have — null them so column lookups
    # don't NaN-out the table cells.
    df['DAMAGE_SUPP'] = None
    df['STRIKE_THROWING'] = None
    df['pitch_archetype'] = None
    df['primary_group'] = None
    df['r_SwStr'] = None
    df['r_CSW'] = None
    df['r_HRrate'] = None
    df['r_Barrel'] = None
    df['r_HardHit'] = None
    df['r_GB'] = None
    df['r_xCON'] = None
    df['r_BB'] = None

    # Cast tag bools to plain python bool so JSON serializes cleanly.
    for c in ['CLOSER', 'HIGH_LEVERAGE', 'MULTI_INNING_BULK', 'OBVIOUS_PLATOON_GUY', 'FIREMAN']:
        if c in df.columns:
            df[c] = df[c].fillna(False).astype(bool)

    recs = json.loads(df.to_json(orient='records'))
    for r in recs:
        r['role'] = 'RP'
        # Compact tag list for chip rendering in the modal.
        tags = []
        if r.get('CLOSER'):            tags.append('CLOSER')
        if r.get('FIREMAN'):           tags.append('FIREMAN')
        if r.get('HIGH_LEVERAGE'):     tags.append('HIGH_LEVERAGE')
        if r.get('MULTI_INNING_BULK'): tags.append('MULTI_INNING_BULK')
        if r.get('OBVIOUS_PLATOON_GUY'): tags.append('PLATOON')
        r['rp_tags'] = tags
    return recs


# 20-80 scalar rating lives once in lib/archetype_engine (C2, 2026-06-21); cell +
# archetype label come from label_for_cell (C3). _rate keeps the legacy name the
# builders' call sites already use.
_rate = rate_value


def build_hitter_snapshots():
    """Per-(batter, year, snapshot_date) C/P/D/SB ratings using rolling cache.

    Each snapshot rates using the PRIOR-year full-season mean/SD as baseline so
    units stay consistent across snapshot dates. Rookies / players without a
    prior year fall back to the snapshot-year baseline.
    """
    if not H_ROLLING.exists() or not H_SRC.exists():
        print('  ⚠ hitter rolling/source not found — skipping snapshot build')
        return []
    r = pd.read_csv(H_ROLLING)
    src = pd.read_csv(H_SRC)
    r['cutoff_date'] = pd.to_datetime(r['cutoff_date'])

    # Derive BABIP and z_swing_pct from raw counts
    r['babip_to'] = ((r['h_to'] - r['hr_to']) /
                     (r['ab_to'] - r['k_to'] - r['hr_to']).clip(lower=1)).clip(0, 1)
    # source for player_name + team lookups
    name_lookup = (src.sort_values('year').groupby('batter')
                   .agg({'player_name': 'last', 'team': 'last'}).to_dict('index'))
    with open(H_DEFS, encoding='utf-8') as f:
        hdefs = json.load(f)

    # Build per-year baselines (mean/sd of full-season rates) for stable rating units
    src['babip'] = ((src['h'] - src['hr']) /
                    (src['ab'] - src['k'] - src['hr']).clip(lower=1)).clip(0, 1)
    BASELINE_COLS = ['contact_pct', 'k_pct', 'babip', 'xwoba_on_contact',
                     'barrel_pct', 'hard_hit_pct', 'iso', 'hr_per_pa',
                     'bb_pct', 'chase_pct', 'sb_per_pa']
    baselines = {}
    for yr, grp in src.groupby('year'):
        baselines[int(yr)] = {c: (grp[c].mean(), grp[c].std()) for c in BASELINE_COLS}

    # 50 PA floor for snapshot rating — rolling cache already filters early-season noise
    r = r[r['pa_to'] >= 50].copy()
    if not len(r): return []

    out = []
    for _, row in r.iterrows():
        yr = int(row['year'])
        baseline_yr = yr - 1 if (yr - 1) in baselines else yr
        if baseline_yr not in baselines:
            continue
        b = baselines[baseline_yr]

        rC = _rate(row['contact_pct_to'],      *b['contact_pct'])
        rK = _rate(row['k_pct_to'],            *b['k_pct'], invert=True)
        rB = _rate(row['babip_to'],            *b['babip'])
        rX = _rate(row['xwoba_on_contact_to'], *b['xwoba_on_contact'])
        rBR= _rate(row['barrel_pct_to'],       *b['barrel_pct'])
        rHH= _rate(row['hard_hit_pct_to'],     *b['hard_hit_pct'])
        rI = _rate(row['iso_to'],              *b['iso'])
        rHR= _rate(row['hr_per_pa_to'],        *b['hr_per_pa'])
        rBB= _rate(row['bb_pct_to'],           *b['bb_pct'])
        rCH= _rate(row['chase_pct_to'],        *b['chase_pct'], invert=True)
        rSB= _rate(row['sb_per_pa_to'],        *b['sb_per_pa'])

        c_vals = [v for v in [rC, rK, rB, rX] if v is not None]
        p_vals = [v for v in [rBR, rHH, rI, rHR] if v is not None]
        d_vals = [v for v in [rBB, rCH] if v is not None]
        if not (c_vals and p_vals and d_vals):
            continue
        CONTACT    = int(round(sum(c_vals) / len(c_vals)))
        POWER      = int(round(sum(p_vals) / len(p_vals)))
        DISCIPLINE = int(round(sum(d_vals) / len(d_vals)))
        SB = rSB if rSB is not None else 50
        cell, arch = label_for_cell([CONTACT, POWER, DISCIPLINE], hdefs)

        info = name_lookup.get(int(row['batter']), {'player_name': None, 'team': None})
        # Weighted Overall — same coefficients as the master CSV builder.
        OVERALL = int(round(CONTACT * 0.55 + POWER * 0.35 + DISCIPLINE * 0.10))
        out.append({
            'batter': int(row['batter']),
            'player_name': info.get('player_name'),
            'team': info.get('team'),
            'year': yr,
            'date': row['cutoff_date'].strftime('%Y-%m-%d'),
            'pa_to': int(row['pa_to']),
            'OVERALL': OVERALL,
            'CONTACT': CONTACT, 'POWER': POWER, 'DISCIPLINE': DISCIPLINE, 'SB': SB,
            'cell': cell, 'archetype': arch,
        })
    print(f'  hitter snapshots: {len(out)} rows ({len(set((o["batter"], o["year"]) for o in out))} player-years)', flush=True)
    return out


def build_sp_start_snapshots(years=(2024, 2025, 2026), window=10, min_starts=3):
    """START-ANCHORED SP snapshots (Option A) — same schema as build_sp_snapshots
    but cadenced per START with an event-weighted trailing last-N-starts window,
    computed directly from statcast (isolated from the shared rolling cache).

    SPs pitch on an event cadence, so this replaces the calendar-weekly grid for
    the intra-season SP chart. Display-only (Rule 13). Hitters stay weekly.
    """
    from lib.sp_start_snapshots import (
        starts_from_statcast, trailing_start_windows, rates_from_counts)
    if not S_SRC.exists():
        print('  ⚠ SP source not found — skipping start-anchored snapshots'); return []
    src = pd.read_csv(S_SRC)
    src['hr_per_bf'] = src['hr'] / src['tbf'].clip(lower=1)
    name_lookup = (src.sort_values('year').groupby('pitcher')
                   .agg({'player_name': 'last'}).to_dict('index'))
    BASELINE_COLS = ['k_pct', 'swstr_pct', 'c_plus_swstr', 'bb_pct', 'avg_velo',
                     'hr_per_bf', 'barrel_pct', 'hard_hit_pct', 'gb_pct', 'xwoba_contact']
    baselines = {}
    for yr, grp in src.groupby('year'):
        baselines[int(yr)] = {c: (grp[c].mean(), grp[c].std())
                              for c in BASELINE_COLS if c in grp.columns}
    with open(S_DEFS, encoding='utf-8') as f:
        sdefs = json.load(f)
    SC_COLS = ['pitcher', 'game_date', 'pitch_type', 'release_speed', 'description',
               'events', 'launch_speed', 'launch_speed_angle', 'bb_type',
               'estimated_woba_using_speedangle']

    out = []
    for yr in years:
        p = CACHE / f'statcast_{yr}.parquet'
        if not p.exists():
            continue
        b = baselines.get(yr - 1) or baselines.get(yr)
        if not b:
            continue
        sc = pd.read_parquet(p, columns=[c for c in SC_COLS])
        for pid, g in sc.groupby('pitcher'):
            starts = starts_from_statcast(g)
            for w in trailing_start_windows(starts, window=window, min_starts=min_starts):
                rt = rates_from_counts(w)
                def R(key, invert=False):
                    v = rt.get(key)
                    return _rate(v, *b[key], invert=invert) if (v is not None and key in b) else None
                rK, rSW, rCSW = R('k_pct'), R('swstr_pct'), R('c_plus_swstr')
                rBB = R('bb_pct', invert=True)
                rV = R('avg_velo')
                move = [R('hr_per_bf', True), R('barrel_pct', True), R('hard_hit_pct', True),
                        R('gb_pct'), R('xwoba_contact', True)]
                s_vals = [v for v in [rK, rSW, rCSW] if v is not None]
                m_vals = [v for v in move if v is not None]
                if not (s_vals and m_vals and rBB is not None):
                    continue
                STUFF = int(round(sum(s_vals) / len(s_vals)))
                MOVEMENT = int(round(sum(m_vals) / len(m_vals)))
                CONTROL = rBB
                cell, arch = label_for_cell([STUFF, MOVEMENT, CONTROL], sdefs)
                nm = (name_lookup.get(int(pid), {}) or {}).get('player_name')
                if isinstance(nm, str) and ',' in nm:
                    a, c = nm.split(',', 1); nm = f'{c.strip()} {a.strip()}'
                out.append({
                    'pitcher': int(pid), 'player_name': nm, 'year': yr,
                    'date': w['date'], 'start_no': w['start_no'], 'gs_to': w['start_no'],
                    'OVERALL': int(round(STUFF * 0.50 + MOVEMENT * 0.35 + CONTROL * 0.15)),
                    'STUFF': STUFF, 'MOVEMENT': MOVEMENT, 'CONTROL': CONTROL,
                    'velo_rating': rV if rV is not None else 50,
                    'cell': cell, 'archetype': arch,
                })
    print(f'  SP start-anchored snapshots: {len(out)} rows '
          f'({len(set((o["pitcher"], o["year"]) for o in out))} pitcher-years)', flush=True)
    return out


def build_rp_snapshots():
    """Per-(pitcher, year, snapshot_date) STUFF / CONTROL / BATTED_BALL ratings
    for relievers — same shape as build_sp_snapshots() so the JS template can
    drive the In-season trajectory + Snapshot-movers views uniformly.

    Maps the columns the rolling-relievers cache carries onto the RP 3-domain
    structure:
      STUFF        ← SWING_MISS (swstr_pct) + CALLED_STRIKE (c_plus_swstr)
      CONTROL      ← WALK_AVOID (bb_pct, inverted) + VELO (avg_velo)
      BATTED_BALL  ← weighted blend of gb_pct (positive) + barrel_pct (inv)
                     + hard_hit_pct (inv) + xwoba_on_contact (inv). Mirrors
                     the SP snapshot decomposition (2026-05-29 extension);
                     the per-cutoff BIP rates were added to the rolling
                     reliever cache in build_rolling_relievers.py.

    BATTED_BALL blend weights (chosen 2026-05-29):
      gb_pct           0.40   ← dominant share, mirrors archetype master
                                where GB_TENDENCY carries 0.50 of BATTED_BALL
      xwoba_on_contact 0.20   ← best single damage-suppression summary
      barrel_pct       0.25   ← inverted; high-leverage damage tail
      hard_hit_pct     0.15   ← inverted; broad contact-quality floor
    Baselines for the four new metrics come from rp_ratings_master.csv (the
    only RP CSV that carries gb_pct / barrel_pct / hard_hit_pct / xwobacon
    aligned to the archetype master). swstr/csw/bb/velo/xwoba_per_pa baselines
    continue to come from relievers_multiyr.

    Archetype label is recomputed per snapshot from the rolling S/C/BB triplet.
    """
    if not R_ROLLING.exists() or not R_SRC.exists():
        print('  ⚠ RP rolling/source not found — skipping RP snapshot build')
        return []
    r = pd.read_csv(R_ROLLING)
    src = pd.read_csv(R_SRC)
    r['cutoff_date'] = pd.to_datetime(r['cutoff_date'])
    name_lookup = (src.sort_values('year').groupby('pitcher')
                   .agg({'name': 'last'}).to_dict('index'))

    BASELINE_COLS = ['swstr_pct', 'c_plus_swstr', 'bb_pct', 'avg_velo', 'xwoba_per_pa']
    baselines = {}
    for yr, grp in src.groupby('year'):
        baselines[int(yr)] = {}
        for c in BASELINE_COLS:
            if c not in grp.columns:
                continue
            baselines[int(yr)][c] = (grp[c].mean(), grp[c].std())

    # Pull BIP-rate baselines from rp_ratings_master (per-year mean/SD of
    # gb_pct / barrel_pct / hard_hit_pct / xwobacon over the qualified RP
    # cohort the archetype master labels). Falls back gracefully if missing.
    # IMPORTANT unit alignment: rp_ratings_master stores gb_pct / barrel_pct /
    # hard_hit_pct as PERCENTAGES (0-100). The rolling cache stores them as
    # FRACTIONS (0-1). Divide the percentage cols by 100 before computing
    # baselines so the z-score is on the same scale as the rolling _to value.
    # xwobacon is already a fraction in both sources.
    BIP_BASELINE_COLS = ['gb_pct', 'barrel_pct', 'hard_hit_pct', 'xwobacon']
    BIP_PCT_COLS = {'gb_pct', 'barrel_pct', 'hard_hit_pct'}
    if R_MASTER.exists():
        rmaster = pd.read_csv(R_MASTER, usecols=lambda c: c in (['year'] + BIP_BASELINE_COLS))
        for yr, grp in rmaster.groupby('year'):
            baselines.setdefault(int(yr), {})
            for c in BIP_BASELINE_COLS:
                if c not in grp.columns:
                    continue
                vals = pd.to_numeric(grp[c], errors='coerce').dropna()
                if c in BIP_PCT_COLS:
                    vals = vals / 100.0
                if len(vals) >= 5:
                    baselines[int(yr)][c] = (vals.mean(), vals.std())

    # RP eligibility floor — same MIN_G_TO=5 the model uses; matches the
    # rolling cache filter so we don't double-restrict here.
    r = r[r['g_to'] >= 5].copy()
    if not len(r):
        return []

    # Load RP archetype defs to assign label per snapshot
    with open(R_DEFS, encoding='utf-8') as f:
        rdefs = json.load(f)

    # BATTED_BALL blend weights — see docstring. Re-normalized over available
    # components per-row so that early-season nulls don't collapse the rating.
    BB_BLEND = {
        'gb_pct':           ('gb_pct_to',           0.40, False),
        'xwoba_on_contact': ('xwoba_on_contact_to', 0.20, True),
        'barrel_pct':       ('barrel_pct_to',       0.25, True),
        'hard_hit_pct':     ('hard_hit_pct_to',     0.15, True),
    }

    out = []
    for _, row in r.iterrows():
        yr = int(row['year'])
        baseline_yr = yr - 1 if (yr - 1) in baselines else yr
        if baseline_yr not in baselines:
            continue
        b = baselines[baseline_yr]
        if not all(k in b for k in BASELINE_COLS):
            continue

        rSW  = _rate(row['swstr_pct_to'],     *b['swstr_pct'])
        rCSW = _rate(row['c_plus_swstr_to'],  *b['c_plus_swstr'])
        rBB  = _rate(row['bb_pct_to'],        *b['bb_pct'], invert=True)
        rV   = _rate(row['avg_velo_to'],      *b['avg_velo'])

        # BATTED_BALL components — each rated 20-80 against prior-year RP
        # cohort baseline, then blended via BB_BLEND weights. Components
        # whose baseline or current value is missing are skipped and the
        # remaining weights re-normalized so partial coverage still rates.
        bb_components = []
        for baseline_key, (rolling_col, weight, invert) in BB_BLEND.items():
            if baseline_key not in b:
                continue
            if rolling_col not in row.index:
                continue
            mu, sd = b[baseline_key]
            rated = _rate(row[rolling_col], mu, sd, invert=invert)
            if rated is None:
                continue
            bb_components.append((rated, weight))

        s_vals = [v for v in [rSW, rCSW] if v is not None]
        c_vals = [v for v in [rBB, rV] if v is not None]
        if not (s_vals and c_vals and bb_components):
            continue
        STUFF       = int(round(sum(s_vals) / len(s_vals)))
        CONTROL     = int(round(sum(c_vals) / len(c_vals)))
        # Weighted mean of BATTED_BALL components, weights re-normalized
        # over whatever components were available.
        bb_w_sum = sum(w for _, w in bb_components)
        BATTED_BALL = int(round(
            sum(v * w for v, w in bb_components) / bb_w_sum
        )) if bb_w_sum > 0 else 50

        cell, arch = label_for_cell([STUFF, CONTROL, BATTED_BALL], rdefs)

        info = name_lookup.get(int(row['pitcher']), {'name': None})
        nm = info.get('name')
        if isinstance(nm, str) and ',' in nm:
            a, c = nm.split(',', 1)
            nm = f'{c.strip()} {a.strip()}'

        # Weighted Overall — mirrors OVERALL_W in build_rp_archetypes.py
        # (STUFF 0.55 / CONTROL 0.30 / BATTED_BALL 0.15) so the snapshot
        # rating aligns with the master CSV's archetype label.
        OVERALL = int(round(STUFF * 0.55 + CONTROL * 0.30 + BATTED_BALL * 0.15))

        # Bridge fields so the JS template's SP path can read MOVEMENT/velo_rating
        # uniformly off RP snapshot rows (mirror of build_rp_records bridges).
        out.append({
            'pitcher': int(row['pitcher']),
            'player_name': nm,
            'year': yr,
            'date': row['cutoff_date'].strftime('%Y-%m-%d'),
            'gs_to': int(row['g_to']),  # g count — SP-shaped path reads gs_to
            'OVERALL': OVERALL,
            'STUFF': STUFF, 'CONTROL': CONTROL, 'BATTED_BALL': BATTED_BALL,
            'MOVEMENT': BATTED_BALL,    # bridge alias so SP code path works
            'velo_rating': rV if rV is not None else 50,
            'cell': cell, 'archetype': arch,
            'role': 'RP',
        })
    print(f'  RP snapshots: {len(out)} rows ({len(set((o["pitcher"], o["year"]) for o in out))} reliever-years)', flush=True)
    return out


# ── ESPN roster-status + eligibility ─────────────────────────────────────────
MY_TEAM_NAME = 'New York Ligers'
# ESPN exposes slot strings like 'C','1B','2B','3B','SS','LF','CF','RF','OF',
# 'DH','SP','RP'. We collapse the corner-outfield strings into 'OF' for filters.
_OUTFIELD_SLOTS = {'OF', 'LF', 'CF', 'RF'}


def _norm_name(n: str) -> str:
    if not isinstance(n, str):
        return ''
    s = unicodedata.normalize('NFKD', n)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]", '', s.lower())
    return s


def _normalize_eligible_positions(slots) -> list[str]:
    """ESPN eligibleSlots -> deduped list of fantasy-relevant positions.

    Keeps C/1B/2B/3B/SS/DH/SP/RP as-is; collapses LF/CF/RF/OF into a single
    'OF'. Drops bench / IL / utility-only slots that aren't positions.
    """
    if not slots:
        return []
    keep = {'C', '1B', '2B', '3B', 'SS', 'DH', 'SP', 'RP'}
    out = []
    seen = set()
    for s in slots:
        if not isinstance(s, str):
            continue
        s = s.strip().upper()
        if s in _OUTFIELD_SLOTS:
            pos = 'OF'
        elif s in keep:
            pos = s
        else:
            continue
        if pos in seen:
            continue
        seen.add(pos)
        out.append(pos)
    return out


def fetch_espn_roster_map() -> dict:
    """Pull every rostered player from ESPN once.

    Returns dict keyed by normalized name with values:
      {'team_name': str, 'is_mine': bool, 'eligible_positions': list[str]}

    Fails CLOSED but soft: on any error, returns {} so every current-year row
    falls through to 'fa' (the safer default for a public dashboard than
    misleadingly tagging everyone as 'mine'/'taken').
    """
    try:
        sys.path.insert(0, str(REPO))
        from app.espn_connector import _get_league  # type: ignore
        league = _get_league()
    except Exception as e:
        print(f'  ESPN unavailable — roster_status will fall back to "fa": {e}',
              flush=True)
        return {}

    out: dict = {}
    try:
        for team in league.teams:
            tname = getattr(team, 'team_name', '') or ''
            is_mine = ('ligers' in tname.lower())
            for player in team.roster:
                name = getattr(player, 'name', '') or ''
                key = _norm_name(name)
                if not key:
                    continue
                slots = getattr(player, 'eligibleSlots', []) or []
                out[key] = {
                    'team_name': tname,
                    'is_mine': is_mine,
                    'eligible_positions': _normalize_eligible_positions(slots),
                }
    except Exception as e:
        print(f'  ESPN team-walk failed mid-pull — partial roster map: {e}',
              flush=True)
    print(f'  ESPN roster map: {len(out)} rostered players', flush=True)
    return out


def annotate_current_year_rows(records: list[dict], current_year: int,
                                roster_map: dict, role: str) -> None:
    """In-place: add roster_status + eligible_positions to current-year rows.

    Non-current-year rows get roster_status=None (the UI hides the chip group
    for those modes). For pitcher rows we also default eligible_positions to
    ['SP'] when ESPN has no entry — the SP master is SP-only by construction.
    """
    n_mine = n_taken = n_fa = 0
    for r in records:
        if r.get('year') != current_year:
            r['roster_status'] = None
            r['eligible_positions'] = []
            continue
        key = _norm_name(r.get('player_name') or '')
        hit = roster_map.get(key)
        # Role-implied fallback when ESPN has no entry: SP→['SP'], RP→['RP'].
        implied = ['SP'] if role == 'sp' else (['RP'] if role == 'rp' else [])
        if hit is None:
            r['roster_status'] = 'fa'
            r['eligible_positions'] = implied
            n_fa += 1
        else:
            if hit['is_mine']:
                r['roster_status'] = 'mine'; n_mine += 1
            else:
                r['roster_status'] = 'taken'; n_taken += 1
            r['eligible_positions'] = hit['eligible_positions'] or implied
    print(f'  {role}: mine={n_mine} taken={n_taken} fa={n_fa} '
          f'(current_year={current_year})', flush=True)


def load_hitter_boom_stack_payload() -> dict:
    """Load the most recent hitter_boom_stack JSON and reshape into a
    per-batter_id map for the Boom/Bust/Variance modal tab (hitter side).

    Mirrors `load_boom_stack_payload` (SP). Falls back gracefully when no
    batch file is found — the tab still renders with the prior placeholder.
    """
    OUT = REPO / 'data/outputs'
    files = sorted(OUT.glob('hitter_boom_stack_*.json'))
    if not files:
        return {'meta': {'available': False, 'reason': 'no hitter_boom_stack JSON found'},
                'by_batter': {}}
    latest = files[-1]
    try:
        with open(latest, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {'meta': {'available': False, 'reason': f'parse error: {e}'},
                'by_batter': {}}

    by_bid: dict[str, dict] = {}
    for c in data.get('candidates', []):
        bid = c.get('batter_id')
        if bid is None:
            continue
        # If a batter appears across multiple games (today + tomorrow), keep
        # the earlier-date entry — that's "today's" view for the profile.
        key = str(int(bid))
        if key in by_bid:
            if c.get('game_date', '') < by_bid[key].get('game_date', ''):
                by_bid[key] = c
        else:
            by_bid[key] = c

    meta = {
        'available': True,
        'source_file': latest.name,
        'window_start': data.get('summary', {}).get('window_start'),
        'window_end': data.get('summary', {}).get('window_end'),
        'n_candidates': len(by_bid),
    }
    return {'meta': meta, 'by_batter': by_bid}


def load_boom_stack_payload() -> dict:
    """Load boom_stack records for the Boom / Bust / Variance modal tab.

    Merges two sources, with window-active records winning on conflict:
      1. sp_boom_stack_full_pool_<date>.json — full ~300-SP universe with
         season-only tags (HIGH-K, catcher framing, IL return). Lower
         precedence; populates the modal for any SP not in the live window.
      2. stream_the_stack_<date>.json — rolling 3-day window of confirmed
         probable starters. Higher precedence — these are the
         highest-confidence per-start projections.

    Falls back gracefully when neither file exists.
    """
    OUT = REPO / 'data/outputs'

    by_pid: dict[str, dict] = {}
    full_pool_meta: dict = {}

    # 1) Full-pool layer (lower precedence).
    fp_files = sorted(OUT.glob('sp_boom_stack_full_pool_*.json'))
    if fp_files:
        latest_fp = fp_files[-1]
        try:
            with open(latest_fp, encoding='utf-8') as f:
                fp_data = json.load(f)
            for c in fp_data.get('candidates', []):
                pid = c.get('pitcher_id')
                if pid is None:
                    continue
                by_pid[str(int(pid))] = c
            full_pool_meta = {
                'full_pool_source_file': latest_fp.name,
                'full_pool_n_candidates': len(fp_data.get('candidates', [])),
                'full_pool_n_with_upcoming_start':
                    fp_data.get('summary', {}).get('n_with_upcoming_start'),
                'full_pool_n_season_only':
                    fp_data.get('summary', {}).get('n_season_only'),
            }
        except Exception as e:
            full_pool_meta = {'full_pool_error': f'parse error: {e}'}

    # 2) Stream_the_stack overlay (higher precedence — overwrites full-pool rows).
    stream_meta: dict = {}
    files = sorted(OUT.glob('stream_the_stack_*.json'))
    if files:
        latest = files[-1]
        try:
            with open(latest, encoding='utf-8') as f:
                data = json.load(f)
            for c in data.get('candidates', []):
                pid = c.get('pitcher_id')
                if pid is None:
                    continue
                c = dict(c)
                # Window-active rows are inherently "has upcoming start" —
                # set the flag so the renderer doesn't show a season-only
                # placeholder for an SP that IS pitching this window.
                c.setdefault('has_upcoming_start', True)
                by_pid[str(int(pid))] = c
            stream_meta = {
                'source_file': latest.name,
                'window_start': data.get('summary', {}).get('window_start'),
                'window_end': data.get('summary', {}).get('window_end'),
                'n_stream_candidates': len(data.get('candidates', [])),
            }
        except Exception as e:
            stream_meta = {'stream_error': f'parse error: {e}'}

    if not by_pid:
        return {
            'meta': {'available': False,
                     'reason': 'no stream_the_stack or full_pool JSON found'},
            'by_pitcher': {},
        }

    meta = {
        'available': True,
        'n_candidates': len(by_pid),
        # Calibrated 50% interval global alpha for SPs — see
        # data/research/validation_runs/calibration_summary*.md
        'sp_interval_alpha': 2.41,
        **stream_meta,
        **full_pool_meta,
    }
    return {'meta': meta, 'by_pitcher': by_pid}


def _proj_value_map(df, id_col: str, val_col: str) -> dict:
    """id(int) -> rounded model value from a projection DataFrame (loaded via the
    ProjectionStore). Fail-soft: returns {} on any error / missing columns so a
    stale or absent projection can never break the dashboard build."""
    try:
        if df is None or df.empty or id_col not in df.columns or val_col not in df.columns:
            return {}
        d = df[[id_col, val_col]].dropna(subset=[id_col, val_col])
        return {int(r[id_col]): round(float(r[val_col]), 3) for _, r in d.iterrows()}
    except Exception as e:
        print(f'  model proj value map failed ({val_col}): {e}', flush=True)
        return {}


def _rh3_primary_pos_map() -> dict:
    """batter(int) -> MLB primary_position string (POS-filter fallback for FAs)."""
    try:
        from plv_clone.projections import PROJECTIONS
        d = PROJECTIONS.rh3()
        if d.empty or 'primary_position' not in d.columns or 'batter' not in d.columns:
            return {}
        d = d[['batter', 'primary_position']].dropna(subset=['batter', 'primary_position'])
        return {int(r['batter']): str(r['primary_position']) for _, r in d.iterrows()}
    except Exception as e:
        print(f'  rh3 primary_position map failed: {e}', flush=True)
        return {}


def annotate_model_axis(records: list[dict], id_key: str, vmap: dict, out_key: str,
                        current_year: int, pos_map: dict | None = None) -> None:
    """In-place: add out_key (model value) to current-year rows; optionally also
    primary_position. Non-current-year rows get None so all-years/blend modes
    simply omit the point (Number.isFinite filter) rather than mis-scale."""
    n = 0
    for r in records:
        cur = r.get('year') == current_year
        rid = r.get(id_key)
        r[out_key] = (vmap.get(int(rid)) if (cur and rid is not None) else None)
        if r[out_key] is not None:
            n += 1
        if pos_map is not None:
            r['primary_position'] = (pos_map.get(int(rid)) if (cur and rid is not None) else None)
    print(f'  {out_key}: annotated {n} current-year rows', flush=True)


def build_payload():
    h, s, rp = assert_schema()

    with open(H_DEFS, encoding='utf-8') as f:
        h_defs = json.load(f)
    with open(S_DEFS, encoding='utf-8') as f:
        s_defs = json.load(f)
    with open(R_DEFS, encoding='utf-8') as f:
        r_defs = json.load(f)
    with open(H_BOUND, encoding='utf-8') as f:
        h_bound = json.load(f)
    with open(S_BOUND, encoding='utf-8') as f:
        s_bound = json.load(f)
    with open(R_BOUND, encoding='utf-8') as f:
        r_bound = json.load(f)

    years = sorted(set(h['year'].unique().tolist()
                       + s['year'].unique().tolist()
                       + rp['year'].unique().tolist()))
    current_year = int(max(years))

    print('Computing intra-season snapshots...', flush=True)
    hitter_snapshots = build_hitter_snapshots()
    sp_snapshots = build_sp_start_snapshots()  # Option A: per-start cadence (was weekly build_sp_snapshots)
    rp_snapshots = build_rp_snapshots()

    hitter_records = build_hitter_records(h)
    sp_records = build_sp_records(s)
    rp_records = build_rp_records(rp)

    print('Fetching ESPN roster map (once)...', flush=True)
    roster_map = fetch_espn_roster_map()
    annotate_current_year_rows(hitter_records, current_year, roster_map, 'hitter')
    annotate_current_year_rows(sp_records,     current_year, roster_map, 'sp')
    annotate_current_year_rows(rp_records,     current_year, roster_map, 'rp')

    print('Joining validated-model projections (rh3/rp3/rprs2) for quadrant axes...', flush=True)
    from plv_clone.projections import PROJECTIONS
    annotate_model_axis(hitter_records, 'batter', _proj_value_map(PROJECTIONS.rh3(), 'batter', 'xfp_rh3_per_game'),
                        'rh3', current_year, pos_map=_rh3_primary_pos_map())
    annotate_model_axis(sp_records, 'pitcher', _proj_value_map(PROJECTIONS.rp3(), 'pitcher', 'xfp_rp3_per_start'),
                        'rp3', current_year)
    annotate_model_axis(rp_records, 'pitcher', _proj_value_map(PROJECTIONS.rprs2(), 'pitcher', 'xfp_ros'),
                        'rprs2', current_year)

    print('Loading boom/bust/variance payload (stream_the_stack)...', flush=True)
    boom_payload = load_boom_stack_payload()
    bm = boom_payload['meta']
    print(f'  boom_stack: available={bm.get("available")} '
          f'n_pitchers={len(boom_payload["by_pitcher"])} '
          f'source={bm.get("source_file")}', flush=True)

    print('Loading hitter boom/bust/variance payload (hitter_boom_stack)...', flush=True)
    boom_hitter_payload = load_hitter_boom_stack_payload()
    bhm = boom_hitter_payload['meta']
    print(f'  hitter boom_stack: available={bhm.get("available")} '
          f'n_batters={len(boom_hitter_payload["by_batter"])} '
          f'source={bhm.get("source_file")}', flush=True)

    rp_count = sum(1 for r in rp_records if r.get('year') == current_year)
    rp_available = rp_count >= 25
    print(f'  RP-archetype current-year records: {rp_count} '
          f'(RP filter {"ENABLED" if rp_available else "disabled — need >=25"})',
          flush=True)

    return {
        'last_refresh': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'years': [int(y) for y in years],
        'current_year': current_year,
        'hitter_archetype_defs': h_defs,
        'sp_archetype_defs': s_defs,
        'rp_archetype_defs': r_defs,
        'hitter_boundary': h_bound,
        'sp_boundary': s_bound,
        'rp_boundary': r_bound,
        'hitters': hitter_records,
        'sps': sp_records,
        'rps': rp_records,
        'hitter_snapshots': hitter_snapshots,
        'sp_snapshots': sp_snapshots,
        'rp_snapshots': rp_snapshots,
        'rp_available': bool(rp_available),
        'my_team_name': MY_TEAM_NAME,
        # Per-pitcher boom/bust/variance — keyed by str(pitcher_id).
        'boom_pitcher': boom_payload,
        # Per-batter boom/bust/variance — keyed by str(batter_id). Populated
        # by `scripts/xfp/build_hitter_boom_stack_daily.py` (step 4.7 of
        # refresh_dashboards.py). Falls back to placeholder when missing.
        'boom_hitter': boom_hitter_payload,
    }


# ── HTML assembly ────────────────────────────────────────────────────────────
# Phases B (template/CSS), C (Plotly + r-in-JS), D (search/modal/tables) live
# in sibling files imported below. Keeping them split eases iteration.
from _player_profiles_template import render_page  # noqa: E402


def main():
    print('Building Player Profiles dashboard...', flush=True)
    payload = build_payload()
    print(f'  payload: {len(payload["hitters"])} hitter-years, '
          f'{len(payload["sps"])} SP-years, '
          f'{len(payload.get("rps", []))} RP-years, years '
          f'{payload["years"][0]}-{payload["years"][-1]}', flush=True)

    html = render_page(payload)

    OUT_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    OUT_LOCAL.write_text(html, encoding='utf-8')
    print(f'  wrote {OUT_LOCAL}  ({len(html):,} bytes)', flush=True)

    if OUT_PUB.parent.exists():
        shutil.copy2(OUT_LOCAL, OUT_PUB)
        sz = OUT_PUB.stat().st_size
        if sz < 50_000:
            _fail(f'published file unexpectedly small: {sz} bytes')
        print(f'  mirrored to {OUT_PUB}  ({sz:,} bytes)', flush=True)
    else:
        print(f'  ⚠ xfp-model/docs not found at {OUT_PUB.parent} — skipped mirror',
              flush=True)

    print('Done.', flush=True)


if __name__ == '__main__':
    main()
