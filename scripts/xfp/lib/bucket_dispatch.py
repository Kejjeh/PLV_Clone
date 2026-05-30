"""Bucket dispatch + name resolution for the triangulate engine."""
from __future__ import annotations
import sys, unicodedata

ARCHETYPE_PANELS = {
    'H':  'data/research/hitter_archetype_career_panel.parquet',
    'SP': 'data/research/sp_archetype_career_panel.parquet',
    'RP': 'data/research/rp_archetype_career_panel.parquet',
}
PROJECTIONS = {
    'H':  'data/outputs/xfp_rh3_projections.csv',
    'SP': 'data/outputs/xfp_rp3_projections.csv',
    'RP': 'data/outputs/xfp_rprs2_projections.csv',
}


def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii').lower().strip()


def _flip_lastfirst(s: str) -> str:
    if ',' in str(s):
        a, b = s.split(',', 1)
        return f"{b.strip()} {a.strip()}"
    return str(s)


def resolve_player(name: str, hint: str | None = None) -> dict | None:
    """Return {'id', 'bucket', 'display_name', 'team', 'position'} or None."""
    # Import here to avoid a circular at module-import time.
    from .cached_data import _load_projection, _load_archetype

    key = _norm(name)
    order = [hint] + [b for b in ('H', 'SP', 'RP') if b != hint] if hint else ['H', 'SP', 'RP']
    for bucket in order:
        if bucket is None:
            continue
        df = _load_projection(bucket)
        if bucket == 'H':
            id_col, name_col = 'batter', 'player_name'
        elif bucket == 'SP':
            id_col, name_col = 'pitcher', 'player_name'
        else:
            id_col, name_col = 'pitcher', 'name_api'
        m = df[df['_key'] == key]
        if not m.empty:
            if len(m) > 1:
                first = m.iloc[0]
                ft = first.get('team', '?')
                fp = first.get('primary_position', bucket) if bucket == 'H' else bucket
                print(f"WARN MULTI-MATCH for \"{name}\" — took {ft} {fp}; ignored {len(m)-1} other(s)", file=sys.stderr)
            r = m.iloc[0]
            disp = r[name_col]
            if bucket == 'SP':
                disp = _flip_lastfirst(disp)
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': disp,
                'team': r.get('team', ''),
                'position': r.get('primary_position', '') if bucket == 'H' else bucket,
            }
    # Fallback: archetype panels
    for bucket in ('H', 'SP', 'RP'):
        p = _load_archetype(bucket)
        if p is None:
            continue
        name_col = 'player_name' if 'player_name' in p.columns else 'name'
        m = p[p['_key'] == key]
        if not m.empty:
            if m[name_col].nunique() > 1:
                print(f"WARN MULTI-MATCH for \"{name}\" in archetype panel — took first; ignored {m[name_col].nunique()-1} other(s)", file=sys.stderr)
            r = m.sort_values('year').iloc[-1]
            id_col = 'batter' if bucket == 'H' else 'pitcher'
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': r[name_col],
                'team': r.get('team', ''),
                'position': bucket,
            }
    return None
