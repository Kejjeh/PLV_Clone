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
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(r'c:\Users\Joshua\plv_clone')
RES = REPO / 'data/research'
CACHE = REPO / 'data/research/xfp_cache'
OUT_LOCAL = REPO / 'data/outputs/player_profiles.html'
OUT_PUB = REPO / 'xfp-model/docs/player_profiles.html'

H_MASTER = RES / 'hitter_ratings_master.csv'
S_MASTER = RES / 'sp_ratings_master.csv'
H_DEFS   = RES / 'hitter_archetype_definitions.json'
S_DEFS   = RES / 'sp_archetype_definitions.json'
H_BOUND  = RES / 'hitter_boundary_validation.json'
S_BOUND  = RES / 'sp_boundary_validation.json'

H_ROLLING = CACHE / 'rolling_hitters_2018_2026.csv'
S_ROLLING = CACHE / 'rolling_pitchers_2018_2026.csv'
H_SRC     = CACHE / 'hitters_multiyr_2015_2026.csv'
S_SRC     = CACHE / 'sp_multiyr_2015_2025.csv'

# Whitelisted columns — drives payload size.
H_COLS = [
    'batter', 'year', 'player_name', 'team', 'pa', 'fp_per_pa', 'data_tier',
    'OVERALL', 'CONTACT', 'POWER', 'DISCIPLINE', 'SB',
    'BAT_TO_BALL', 'CONTACT_QUALITY', 'RAW_POWER', 'DAMAGE_PROD',
    'PATIENCE', 'AGGRESSION', 'SPEED_TOOL', 'SB_CONVERSION',
    'babip_career', 'babip_delta', 'babip_luck_flag',
    'archetype', 'contact_subtype', 'power_subtype', 'discipline_subtype',
    'sb_tier', 'spray_archetype',
    'age', 'age_tier', 'boundary_tier', 'rank_in_year',
    'r_Contact', 'r_K', 'r_BABIP', 'r_xCON',
    'r_Barrel', 'r_HardHit', 'r_ISO', 'r_HRrate', 'r_PullFB',
    'r_BB', 'r_Chase', 'r_ZSwing',
    'r_SBrate', 'r_Sprint',
]
S_COLS = [
    'pitcher', 'year', 'player_name', 'gs', 'tbf', 'fp_per_start', 'data_tier',
    'OVERALL', 'STUFF', 'MOVEMENT', 'CONTROL',
    'SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID',
    'archetype', 'stuff_subtype',
    'velo_rating', 'velo_tier', 'pitch_archetype', 'primary_group',
    'age', 'age_tier', 'boundary_tier', 'rank_in_year',
    'r_K', 'r_SwStr', 'r_CSW',
    'r_HRrate', 'r_Barrel', 'r_HardHit', 'r_GB', 'r_xCON',
    'r_BB',
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
    for p in [H_MASTER, S_MASTER, H_DEFS, S_DEFS, H_BOUND, S_BOUND]:
        if not p.exists():
            _fail(f'missing input: {p}')

    h = pd.read_csv(H_MASTER)
    s = pd.read_csv(S_MASTER)

    miss_h = [c for c in H_COLS if c not in h.columns]
    miss_s = [c for c in S_COLS if c not in s.columns]
    if miss_h: _fail(f'hitter master missing cols: {miss_h}')
    if miss_s: _fail(f'sp master missing cols: {miss_s}')

    if h.duplicated(['batter', 'year']).any():
        n = int(h.duplicated(['batter', 'year']).sum())
        _fail(f'hitter master has {n} duplicate (batter, year) rows')
    if s.duplicated(['pitcher', 'year']).any():
        n = int(s.duplicated(['pitcher', 'year']).sum())
        _fail(f'sp master has {n} duplicate (pitcher, year) rows')

    for c in ['CONTACT', 'POWER', 'DISCIPLINE', 'SB', 'OVERALL', 'rank_in_year',
              'BAT_TO_BALL', 'CONTACT_QUALITY', 'RAW_POWER', 'DAMAGE_PROD',
              'PATIENCE', 'AGGRESSION', 'SPEED_TOOL', 'SB_CONVERSION']:
        n = int(h[c].isna().sum())
        if n: _fail(f'hitter master {c} has {n} null rows')
    for c in ['STUFF', 'MOVEMENT', 'CONTROL', 'OVERALL', 'rank_in_year',
              'SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID']:
        n = int(s[c].isna().sum())
        if n: _fail(f'sp master {c} has {n} null rows')

    # Definitions and boundary JSONs load + have expected shape
    for p in [H_DEFS, S_DEFS]:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict) or not d:
            _fail(f'archetype defs malformed: {p}')
    for p in [H_BOUND, S_BOUND]:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        for k in ['EDGE', 'NEAR_EDGE', 'SOLID']:
            if k not in d:
                _fail(f'boundary validation missing {k} in {p}')

    return h, s


def build_hitter_records(h: pd.DataFrame):
    df = h[H_COLS].copy()
    # Replace pandas NaN with None for clean JSON
    df['fp_per_pa'] = df['fp_per_pa'].round(3)
    for c in ['age', 'rank_in_year']:
        df[c] = df[c].astype('Int64')
    for c in ['CONTACT', 'POWER', 'DISCIPLINE', 'SB', 'OVERALL',
              'BAT_TO_BALL', 'CONTACT_QUALITY', 'RAW_POWER', 'DAMAGE_PROD',
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
              'SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID']:
        df[c] = df[c].astype('Int64')
    return json.loads(df.to_json(orient='records'))


def _bucket(v):
    if pd.isna(v): return None
    if v >= 60: return 'PLUS'
    if v >= 40: return 'AVG'
    return 'MINUS'


def _rate(val, mu, sd, invert=False):
    if pd.isna(val) or pd.isna(mu) or pd.isna(sd) or sd == 0:
        return None
    z = (val - mu) / sd
    if invert: z = -z
    return int(round(min(max(50 + 10 * z, 20), 80)))


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
        cell = _bucket(CONTACT) + '/' + _bucket(POWER) + '/' + _bucket(DISCIPLINE)

        info = name_lookup.get(int(row['batter']), {'player_name': None, 'team': None})
        # Weighted Overall — same coefficients as the master CSV builder.
        OVERALL = int(round(CONTACT * 0.65 + POWER * 0.30 + DISCIPLINE * 0.05))
        out.append({
            'batter': int(row['batter']),
            'player_name': info.get('player_name'),
            'team': info.get('team'),
            'year': yr,
            'date': row['cutoff_date'].strftime('%Y-%m-%d'),
            'pa_to': int(row['pa_to']),
            'OVERALL': OVERALL,
            'CONTACT': CONTACT, 'POWER': POWER, 'DISCIPLINE': DISCIPLINE, 'SB': SB,
            'cell': cell,
        })
    print(f'  hitter snapshots: {len(out)} rows ({len(set((o["batter"], o["year"]) for o in out))} player-years)', flush=True)
    return out


def build_sp_snapshots():
    """Per-(pitcher, year, snapshot_date) STUFF + MOVEMENT + CONTROL + Velo ratings.

    Uses the extended SP rolling cache that now carries barrel%, hard_hit%,
    gb%, xwoba_on_contact. Archetype label is recomputed per-snapshot from
    blended STUFF/MOVEMENT/CONTROL ratings.
    """
    if not S_ROLLING.exists() or not S_SRC.exists():
        print('  ⚠ SP rolling/source not found — skipping snapshot build')
        return []
    r = pd.read_csv(S_ROLLING)
    src = pd.read_csv(S_SRC)
    r['cutoff_date'] = pd.to_datetime(r['cutoff_date'])
    name_lookup = (src.sort_values('year').groupby('pitcher')
                   .agg({'player_name': 'last'}).to_dict('index'))

    src['hr_per_bf'] = src['hr'] / src['tbf'].clip(lower=1)
    BASELINE_COLS = ['k_pct', 'swstr_pct', 'c_plus_swstr', 'bb_pct', 'avg_velo',
                     'hr_per_bf', 'barrel_pct', 'hard_hit_pct', 'gb_pct', 'xwoba_contact']
    baselines = {}
    for yr, grp in src.groupby('year'):
        baselines[int(yr)] = {}
        for c in BASELINE_COLS:
            if c not in grp.columns: continue
            baselines[int(yr)][c] = (grp[c].mean(), grp[c].std())

    r = r[r['gs_to'] >= 3].copy()
    r['hr_per_bf_to'] = r['hr_to'] / r['tbf_to'].clip(lower=1)
    if not len(r): return []

    # Load archetype definitions to assign label per snapshot
    with open(S_DEFS, encoding='utf-8') as f:
        sdefs = json.load(f)

    out = []
    for _, row in r.iterrows():
        yr = int(row['year'])
        baseline_yr = yr - 1 if (yr - 1) in baselines else yr
        if baseline_yr not in baselines:
            continue
        b = baselines[baseline_yr]

        rK   = _rate(row['k_pct_to'],         *b['k_pct'])
        rSW  = _rate(row['swstr_pct_to'],     *b['swstr_pct'])
        rCSW = _rate(row['c_plus_swstr_to'],  *b['c_plus_swstr'])
        rBB  = _rate(row['bb_pct_to'],        *b['bb_pct'], invert=True)
        rV   = _rate(row['avg_velo_to'],      *b['avg_velo'])

        # MOVEMENT components (rolling cache extended 2026-05-28). The hr_per_bf
        # baseline in the source uses 'hr_per_bf'; the others use the same names.
        rHR  = _rate(row['hr_per_bf_to'],     *b['hr_per_bf'], invert=True) if 'hr_per_bf' in b else None
        rBR  = _rate(row['barrel_pct_to'],    *b['barrel_pct'], invert=True) if 'barrel_pct' in b else None
        rHH  = _rate(row['hard_hit_pct_to'],  *b['hard_hit_pct'], invert=True) if 'hard_hit_pct' in b else None
        rGB  = _rate(row['gb_pct_to'],        *b['gb_pct']) if 'gb_pct' in b else None
        rXC  = _rate(row['xwoba_on_contact_to'], *b['xwoba_contact'], invert=True) if 'xwoba_contact' in b else None

        s_vals = [v for v in [rK, rSW, rCSW] if v is not None]
        m_vals = [v for v in [rHR, rBR, rHH, rGB, rXC] if v is not None]
        if not (s_vals and m_vals and rBB is not None):
            continue
        STUFF    = int(round(sum(s_vals) / len(s_vals)))
        MOVEMENT = int(round(sum(m_vals) / len(m_vals)))
        CONTROL  = rBB

        def _b(v):
            if v >= 60: return 'PLUS'
            if v >= 40: return 'AVG'
            return 'MINUS'
        cell = f'{_b(STUFF)}/{_b(MOVEMENT)}/{_b(CONTROL)}'
        arch = sdefs.get(cell, {}).get('label', 'UNKNOWN')

        info = name_lookup.get(int(row['pitcher']), {'player_name': None})
        nm = info.get('player_name')
        if isinstance(nm, str) and ',' in nm:
            a, c = nm.split(',', 1)
            nm = f'{c.strip()} {a.strip()}'
        # Weighted Overall — same coefficients as the master CSV builder.
        OVERALL = int(round(STUFF * 0.50 + MOVEMENT * 0.35 + CONTROL * 0.15))
        out.append({
            'pitcher': int(row['pitcher']),
            'player_name': nm,
            'year': yr,
            'date': row['cutoff_date'].strftime('%Y-%m-%d'),
            'gs_to': int(row['gs_to']),
            'OVERALL': OVERALL,
            'STUFF': STUFF, 'MOVEMENT': MOVEMENT, 'CONTROL': CONTROL,
            'velo_rating': rV if rV is not None else 50,
            'cell': cell, 'archetype': arch,
        })
    print(f'  SP snapshots: {len(out)} rows ({len(set((o["pitcher"], o["year"]) for o in out))} pitcher-years)', flush=True)
    return out


def build_payload():
    h, s = assert_schema()

    with open(H_DEFS, encoding='utf-8') as f:
        h_defs = json.load(f)
    with open(S_DEFS, encoding='utf-8') as f:
        s_defs = json.load(f)
    with open(H_BOUND, encoding='utf-8') as f:
        h_bound = json.load(f)
    with open(S_BOUND, encoding='utf-8') as f:
        s_bound = json.load(f)

    years = sorted(set(h['year'].unique().tolist() + s['year'].unique().tolist()))
    current_year = int(max(years))

    print('Computing intra-season snapshots...', flush=True)
    hitter_snapshots = build_hitter_snapshots()
    sp_snapshots = build_sp_snapshots()

    return {
        'last_refresh': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'years': [int(y) for y in years],
        'current_year': current_year,
        'hitter_archetype_defs': h_defs,
        'sp_archetype_defs': s_defs,
        'hitter_boundary': h_bound,
        'sp_boundary': s_bound,
        'hitters': build_hitter_records(h),
        'sps': build_sp_records(s),
        'hitter_snapshots': hitter_snapshots,
        'sp_snapshots': sp_snapshots,
    }


# ── HTML assembly ────────────────────────────────────────────────────────────
# Phases B (template/CSS), C (Plotly + r-in-JS), D (search/modal/tables) live
# in sibling files imported below. Keeping them split eases iteration.
from _player_profiles_template import render_page  # noqa: E402


def main():
    print('Building Player Profiles dashboard...', flush=True)
    payload = build_payload()
    print(f'  payload: {len(payload["hitters"])} hitter-years, '
          f'{len(payload["sps"])} SP-years, years '
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
