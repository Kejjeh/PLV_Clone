"""triangulate_links.py — profiles deep-link map for the triangulate dashboard.

Split verbatim from build_triangulate_dashboard.py (2026-07-19 audit item 11);
the dashboard re-exports these names for external callers.
"""
from __future__ import annotations

import sys

from plv_clone.paths import ROOT


def _warn(section, exc):
    print(f"WARN build_triangulate_dashboard.{section}: {exc}", file=sys.stderr)


# name -> (role, mlbam) map for profiles deep-links (2026-07-18 cross-links).
# rh3/rp3 CSVs carry "Last, First" names; convert + normalize. (name, team)
# key first, then unique-name fallback; ambiguous names get no link.
def _load_profile_id_map():
    import unicodedata as _ud, re as _re
    import pandas as _pd

    def _n(s):
        s = _ud.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
        return _re.sub(r'[^a-z ]', '', s.lower()).strip()

    def _flip(nm):
        if ',' in str(nm):
            last, _, first = str(nm).partition(',')
            return f'{first.strip()} {last.strip()}'
        return str(nm)

    by_nt, by_n = {}, {}
    for path, idc, role in ((ROOT / 'data/outputs/xfp_rh3_projections.csv', 'batter', 'hitter'),
                            (ROOT / 'data/outputs/xfp_rp3_projections.csv', 'pitcher', 'sp')):
        try:
            df = _pd.read_csv(path, usecols=[idc, 'player_name', 'team'] if role == 'hitter'
                              else [idc, 'player_name'])
        except Exception as e:
            _warn('profile_id_map', e)
            continue
        for _, r in df.iterrows():
            nm = _n(_flip(r['player_name']))
            pid = r[idc]
            if _pd.isna(pid):
                continue
            pid = int(pid)
            tm = _n(r['team']) if 'team' in df.columns and _pd.notna(r.get('team')) else ''
            by_nt[(nm, tm)] = (role, pid)
            if nm in by_n and by_n[nm][1] != pid:
                by_n[nm] = None  # ambiguous — no link
            else:
                by_n.setdefault(nm, (role, pid))
    return by_nt, by_n, _n


_PROFILE_IDS = None


def _profile_link(c):
    global _PROFILE_IDS
    if _PROFILE_IDS is None:
        _PROFILE_IDS = _load_profile_id_map()
    by_nt, by_n, _n = _PROFILE_IDS
    nm = _n(c.get('name'))
    tm = _n(c.get('team') or '')
    hit = by_nt.get((nm, tm)) or by_n.get(nm)
    if not hit:
        return ''
    role, pid = hit
    return (f'<a class="xlink" href="player_profiles.html?player={pid}&tab=boom" '
            f'title="Full profile (game-by-game archive)">full profile →</a>')
