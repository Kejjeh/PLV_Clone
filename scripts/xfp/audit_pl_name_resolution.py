"""Audit PL article name resolution against the multiyr caches.

Loops every pl_*.json in data/research/pl_historical/, attempts to resolve
each name via the same normalized-name maps as build_pl_rank_panel, and
categorizes outcomes: CLEAN, COLLISION_GUARDED, FAIL_NO_MATCH,
AMBIGUOUS_NEW_COLLISION (multiple distinct mlbam_ids share the normalized
name in the cache, but not yet in KNOWN_COLLISIONS).

Outputs:
  - data/research/pl_historical/name_resolution_audit_2026-06-05.md
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import pandas as pd

from plv_clone.utils.name_match import (
    _normalize, KNOWN_COLLISIONS, KNOWN_PITCHER_COLLISIONS,
)

ROOT = Path('c:/Users/Joshua/plv_clone')
PL_DIR = ROOT / 'data' / 'research' / 'pl_historical'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_MD = PL_DIR / 'name_resolution_audit_2026-06-05.md'


def build_full_name_index():
    """Build {norm_name: set(mlbam_id)} per hitter/pitcher, so we can detect
    NEW collisions (norm name with >1 distinct id) instead of silently
    overwriting."""
    hitters = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                          usecols=['batter', 'player_name', 'mlb_name', 'team', 'year'])
    h_full: dict[str, set[int]] = defaultdict(set)
    h_team_map: dict[tuple[str, str], int] = {}
    for _, r in hitters.iterrows():
        for nm in (r.get('player_name'), r.get('mlb_name')):
            n = _normalize(nm) if isinstance(nm, str) else ''
            if n:
                h_full[n].add(int(r['batter']))
                team = str(r.get('team') or '').upper()
                if team:
                    h_team_map[(n, team)] = int(r['batter'])

    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv',
                     usecols=['pitcher', 'player_name'])
    p_full: dict[str, set[int]] = defaultdict(set)
    for _, r in sp.iterrows():
        n = _normalize(r['player_name'])
        if n:
            p_full[n].add(int(r['pitcher']))

    rp = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv',
                     usecols=['pitcher', 'name', 'team_abbr', 'year'])
    p_team_map: dict[tuple[str, str], int] = {}
    for _, r in rp.iterrows():
        n = _normalize(r['name']) if isinstance(r.get('name'), str) else ''
        if n:
            p_full[n].add(int(r['pitcher']))
            team = str(r.get('team_abbr') or '').upper()
            if team:
                p_team_map[(n, team)] = int(r['pitcher'])

    return h_full, p_full, h_team_map, p_team_map


def main():
    h_full, p_full, _, _ = build_full_name_index()

    known_h_collisions = {_normalize(n) for n in KNOWN_COLLISIONS}
    known_p_collisions = {_normalize(n) for n in KNOWN_PITCHER_COLLISIONS}

    stats = {
        'total': 0,
        'clean': 0,
        'collision_guarded': 0,
        'fail_no_match': 0,
        'ambiguous_new_collision': 0,
    }
    per_file = {}
    fail_names: dict[str, list[str]] = defaultdict(list)  # name -> list of files
    new_collision_names: dict[str, set[int]] = {}

    files = sorted(PL_DIR.glob('pl_*.json'))
    for fp in files:
        kind = fp.stem.split('_')[1]
        full_idx = h_full if kind == 'h' else p_full
        known_coll = known_h_collisions if kind == 'h' else known_p_collisions

        d = json.loads(fp.read_text(encoding='utf-8'))
        ranks = d.get('ranks') or {}
        f_total = f_clean = f_guard = f_fail = f_amb = 0
        for name in ranks:
            stats['total'] += 1
            f_total += 1
            n = _normalize(name)
            if n in known_coll:
                stats['collision_guarded'] += 1
                f_guard += 1
                continue
            ids = full_idx.get(n, set())
            if not ids:
                stats['fail_no_match'] += 1
                f_fail += 1
                fail_names[name].append(fp.name)
            elif len(ids) == 1:
                stats['clean'] += 1
                f_clean += 1
            else:
                stats['ambiguous_new_collision'] += 1
                f_amb += 1
                new_collision_names[name] = ids
        per_file[fp.name] = (f_total, f_clean, f_guard, f_fail, f_amb)

    # Write audit report
    lines = []
    lines.append('# PL name-resolution audit — 2026-06-05')
    lines.append('')
    lines.append(f'Files scanned: {len(files)}')
    lines.append(f'Total named players across all articles: {stats["total"]:,}')
    lines.append('')
    lines.append('| Outcome | Count | Pct |')
    lines.append('|---|---:|---:|')
    for k in ('clean', 'collision_guarded', 'fail_no_match', 'ambiguous_new_collision'):
        v = stats[k]
        pct = v / max(stats['total'], 1) * 100
        lines.append(f'| {k} | {v:,} | {pct:.1f}% |')
    lines.append('')
    resolved = stats['clean'] + stats['collision_guarded']
    lines.append(f'**Resolution rate (clean + guarded): {resolved:,}/{stats["total"]:,} = {resolved/max(stats["total"],1)*100:.1f}%**')
    lines.append('')

    # New collisions
    lines.append(f'## Newly-discovered ambiguous names ({len(new_collision_names)})')
    lines.append('')
    lines.append('Names whose normalized form maps to >1 mlbam_id in the multiyr cache, not in KNOWN_COLLISIONS.')
    lines.append('')
    lines.append('| Name | mlbam_ids |')
    lines.append('|---|---|')
    for name, ids in sorted(new_collision_names.items()):
        lines.append(f'| {name} | {sorted(ids)} |')
    lines.append('')

    # Failures
    lines.append(f'## Failed-to-match names ({len(fail_names)} unique)')
    lines.append('')
    lines.append('Top 50 by article count:')
    lines.append('')
    lines.append('| Name | Article count | Sample file |')
    lines.append('|---|---:|---|')
    ranked = sorted(fail_names.items(), key=lambda kv: -len(kv[1]))
    for name, files_in in ranked[:50]:
        lines.append(f'| {name} | {len(files_in)} | {files_in[0]} |')
    lines.append('')

    # Per-file
    lines.append('## Per-file detail')
    lines.append('')
    lines.append('| File | Total | Clean | Guarded | Fail | Ambig |')
    lines.append('|---|---:|---:|---:|---:|---:|')
    for f, (t, c, g, fa, a) in sorted(per_file.items()):
        lines.append(f'| {f} | {t} | {c} | {g} | {fa} | {a} |')

    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'wrote {OUT_MD}')
    print(f'\nresolution rate: {resolved}/{stats["total"]} = {resolved/max(stats["total"],1)*100:.1f}%')
    print(f'new ambiguous collisions: {len(new_collision_names)}')
    print(f'unique failed names: {len(fail_names)}')

    # Also return the new collision dict for downstream processing
    return new_collision_names, fail_names


if __name__ == '__main__':
    main()
