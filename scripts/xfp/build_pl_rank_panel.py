"""Build pl_rank_panel.parquet from PL historical JSON archive.

For each PL JSON (season_year, week, ranks{name->rank}, injury_list_ranks{}):
  - resolve player names -> mlbam_id (using cache name maps + KNOWN_COLLISIONS guard)
  - bucket the week into early (W1-2) / mid (W12-14) / late (W20-22)
  - take the earliest snapshot per bucket per (mlbam_id, year)

Outputs one row per (mlbam_id, year) with columns:
  pl_rank_early, pl_rank_mid, pl_rank_late,
  pl_il_rank_early, pl_il_rank_mid, pl_il_rank_late
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from plv_clone.utils.name_match import (
    _normalize, KNOWN_COLLISIONS, KNOWN_PITCHER_COLLISIONS,
)

from plv_clone.paths import ROOT
PL_DIR = ROOT / 'data' / 'research' / 'pl_historical'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'research' / 'historical_panel' / 'pl_rank_panel.parquet'


def _bucket(week: int | None) -> str | None:
    if week is None:
        return None
    if 1 <= week <= 6:
        return 'early'
    if 10 <= week <= 16:
        return 'mid'
    if 18 <= week <= 24:
        return 'late'
    return None


def build_name_maps():
    """Build {normalized_name: mlbam_id} for batters, SPs, RPs.

    Drops any name appearing in KNOWN_COLLISIONS without team context
    (we can't pick safely without team — PL JSON lacks team).
    """
    hitters = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                          usecols=['batter', 'player_name', 'mlb_name'])
    # Prefer player_name (Last, First); fall back to mlb_name (First Last)
    hitters['norm1'] = hitters['player_name'].apply(_normalize)
    hitters['norm2'] = hitters['mlb_name'].fillna('').apply(_normalize)
    h_map = {}
    for _, r in hitters.iterrows():
        for n in (r['norm1'], r['norm2']):
            if n and n not in h_map:
                h_map[n] = int(r['batter'])
    # For each KNOWN_COLLISIONS entry, override the cache map with the
    # FIRST candidate (the preferred resolution for PL articles, which lack
    # team context). Order in name_match.py is curated so the head entry is
    # the player PL articles actually reference (e.g. Will Smith → LAD C,
    # Luis García → WSH 2B, Jacob Wilson → ATH SS). See
    # feedback_player_name_collisions.md 2026-06-05 audit note.
    for cn, cands in KNOWN_COLLISIONS.items():
        if cands:
            h_map[_normalize(cn)] = int(cands[0][2])

    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv',
                     usecols=['pitcher', 'player_name'])
    sp['norm'] = sp['player_name'].apply(_normalize)
    sp_map = dict(zip(sp['norm'], sp['pitcher'].astype(int)))

    rp = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv',
                     usecols=['pitcher', 'name'])
    rp['norm'] = rp['name'].apply(_normalize)
    rp_map = dict(zip(rp['norm'], rp['pitcher'].astype(int)))

    # Merge SP + RP into one pitcher map (SP wins ties — SP cache is older/more canonical)
    p_map = dict(rp_map)
    p_map.update(sp_map)
    for cn in KNOWN_PITCHER_COLLISIONS:
        p_map.pop(_normalize(cn), None)

    # PL-article name-spelling aliases that don't match the Statcast cache's
    # formal first-name spelling. Centralized in
    # src/plv_clone/utils/name_match.py:KNOWN_PITCHER_ALIASES (2026-06-06).
    # Add entries there, not here, so other consumers stay in sync.
    from plv_clone.utils.name_match import KNOWN_PITCHER_ALIASES
    for pl_name, formal in KNOWN_PITCHER_ALIASES.items():
        mid = p_map.get(_normalize(formal))
        if mid is not None:
            p_map[_normalize(pl_name)] = mid

    return h_map, p_map


def parse_pl_file(fp: Path, name_map: dict) -> list[dict]:
    d = json.loads(fp.read_text(encoding='utf-8'))
    year = int(d.get('season_year'))
    week = d.get('week')
    bucket = None
    if isinstance(week, str):
        w = week.lstrip('W')
        if w.isdigit():
            week = int(w)
            bucket = _bucket(week)
        elif week.lower() in ('early', 'mid', 'late'):
            bucket = week.lower()
            week = {'early': 1, 'mid': 13, 'late': 21}[bucket]
    else:
        bucket = _bucket(week)
    if bucket is None:
        return []
    rows = []
    for name, rank in (d.get('ranks') or {}).items():
        mid = name_map.get(_normalize(name))
        if mid is None:
            continue
        rows.append({'mlbam_id': mid, 'year': year, 'bucket': bucket,
                     'week': week, 'rank': rank, 'is_il': False})
    for name, rank in (d.get('injury_list_ranks') or {}).items():
        mid = name_map.get(_normalize(name))
        if mid is None:
            continue
        rows.append({'mlbam_id': mid, 'year': year, 'bucket': bucket,
                     'week': week, 'rank': rank, 'is_il': True})
    return rows


def main():
    h_map, p_map = build_name_maps()
    print(f'name maps: hitters={len(h_map):,} pitchers={len(p_map):,}')

    all_rows = []
    files = sorted(PL_DIR.glob('pl_*.json'))
    miss_log = {}
    for fp in files:
        stem = fp.stem  # pl_h_2024_W13 or pl_sp_2024_W13
        parts = stem.split('_')
        kind = parts[1]  # 'h' or 'sp'
        name_map = h_map if kind == 'h' else p_map

        # count misses (for logging)
        d = json.loads(fp.read_text(encoding='utf-8'))
        total = len(d.get('ranks') or {})
        rows = parse_pl_file(fp, name_map)
        matched = sum(1 for r in rows if not r['is_il'])
        miss_log[fp.name] = (matched, total)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    print(f'\nraw PL rows resolved: {len(df):,}')
    # Coverage summary
    overall_matched = sum(m for m, _ in miss_log.values())
    overall_total = sum(t for _, t in miss_log.values())
    print(f'overall name match rate: {overall_matched}/{overall_total} = '
          f'{overall_matched/max(overall_total,1):.1%}')

    # For each (mlbam_id, year, bucket, is_il), keep the earliest week (best snapshot)
    df = df.sort_values(['mlbam_id', 'year', 'bucket', 'is_il', 'week'])
    df = df.drop_duplicates(['mlbam_id', 'year', 'bucket', 'is_il'], keep='first')

    # Pivot: one row per (mlbam_id, year)
    main_df = df[~df['is_il']].pivot_table(
        index=['mlbam_id', 'year'], columns='bucket', values='rank', aggfunc='first'
    ).rename(columns=lambda c: f'pl_rank_{c}').reset_index()

    il_df = df[df['is_il']].pivot_table(
        index=['mlbam_id', 'year'], columns='bucket', values='rank', aggfunc='first'
    ).rename(columns=lambda c: f'pl_il_rank_{c}').reset_index()

    out = main_df.merge(il_df, on=['mlbam_id', 'year'], how='outer')
    for col in ['pl_rank_early', 'pl_rank_mid', 'pl_rank_late',
                'pl_il_rank_early', 'pl_il_rank_mid', 'pl_il_rank_late']:
        if col not in out.columns:
            out[col] = pd.NA

    for col in ['pl_rank_early', 'pl_rank_mid', 'pl_rank_late',
                'pl_il_rank_early', 'pl_il_rank_mid', 'pl_il_rank_late']:
        out[col] = pd.to_numeric(out[col], errors='coerce')

    print(f'\npanel shape: {out.shape}')
    print('non-null counts per column:')
    print(out.notna().sum())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f'\nwrote {OUT}')


if __name__ == '__main__':
    main()
