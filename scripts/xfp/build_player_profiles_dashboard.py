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

import pandas as pd

REPO = Path(r'c:\Users\Joshua\plv_clone')
RES = REPO / 'data/research'
OUT_LOCAL = REPO / 'data/outputs/player_profiles.html'
OUT_PUB = REPO / 'xfp-model/docs/player_profiles.html'

H_MASTER = RES / 'hitter_ratings_master.csv'
S_MASTER = RES / 'sp_ratings_master.csv'
H_DEFS   = RES / 'hitter_archetype_definitions.json'
S_DEFS   = RES / 'sp_archetype_definitions.json'
H_BOUND  = RES / 'hitter_boundary_validation.json'
S_BOUND  = RES / 'sp_boundary_validation.json'

# Whitelisted columns — drives payload size.
H_COLS = [
    'batter', 'year', 'player_name', 'team', 'pa', 'fp_per_pa', 'data_tier',
    'CONTACT', 'POWER', 'DISCIPLINE', 'SB',
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
    'STUFF', 'MOVEMENT', 'CONTROL',
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

    for c in ['CONTACT', 'POWER', 'DISCIPLINE', 'SB', 'rank_in_year']:
        n = int(h[c].isna().sum())
        if n: _fail(f'hitter master {c} has {n} null rows')
    for c in ['STUFF', 'MOVEMENT', 'CONTROL', 'rank_in_year']:
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
    for c in ['CONTACT', 'POWER', 'DISCIPLINE', 'SB']:
        df[c] = df[c].astype(int)
    # Component r_* are ints in source; preserve.
    return json.loads(df.to_json(orient='records'))


def build_sp_records(s: pd.DataFrame):
    df = s[S_COLS].copy()
    df['player_name'] = df['player_name'].apply(pretty_sp_name)
    df['fp_per_start'] = df['fp_per_start'].round(2)
    for c in ['age', 'rank_in_year']:
        df[c] = df[c].astype('Int64')
    for c in ['STUFF', 'MOVEMENT', 'CONTROL', 'velo_rating']:
        df[c] = df[c].astype('Int64')
    return json.loads(df.to_json(orient='records'))


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
