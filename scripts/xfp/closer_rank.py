"""closer_rank.py — Ligers' 4 closers ranked + FA closer scan.

Ranks Fairbanks / Palencia / Helsley / Duran by:
  - career skill (K%, K-BB%, swstr%, xwOBA, ERA)
  - rprs2 RoS projection
  - role context (closer-of-record vs temp)

Then scans FA pool for any closer-quality RP not on a Ligers roster.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd

from plv_clone.projections import PROJECTIONS
from plv_clone.paths import ROOT, CACHE, OUTPUTS as OUT
sys.path.insert(0, str(ROOT))


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z]+', '', s)


def career_summary(df):
    """Weighted career line."""
    if df.empty: return {}
    total_ip = df['ip'].sum()
    total_tbf = df['tbf_api'].sum()
    total_k = df['k'].sum()
    total_bb = df['bb'].sum()
    total_er = df['er'].sum()
    total_h = df['h'].sum()
    return {
        'seasons': len(df),
        'IP': total_ip,
        'SV': df['sv'].sum(),
        'HLD': df['hld'].sum(),
        'ERA': total_er * 9 / total_ip if total_ip else 0,
        'WHIP': (total_h + total_bb) / total_ip if total_ip else 0,
        'K%': total_k / total_tbf * 100 if total_tbf else 0,
        'BB%': total_bb / total_tbf * 100 if total_tbf else 0,
        'KBB%': (total_k - total_bb) / total_tbf * 100 if total_tbf else 0,
        'swstr%': (df['swstr'].sum() / df['pitches'].sum() * 100) if df['pitches'].sum() else 0,
        'xwOBA': (df['woba_v_sum'].sum() / df['tbf_api'].sum()) if df['tbf_api'].sum() else 0,
    }


def main():
    rel = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')
    rprs2 = PROJECTIONS.rprs2()

    targets = ['Pete Fairbanks', 'Daniel Palencia', 'Ryan Helsley', 'Jhoan Duran']
    targets_recent = {}

    print(f'{"="*80}')
    print(f'{"LIGERS CLOSER QUARTET — CAREER + RECENT FORM":^80s}')
    print(f'{"="*80}\n')

    rows = []
    for name in targets:
        first, last = name.split(maxsplit=1)
        sub = rel[rel['name'].str.contains(last, case=False, na=False)]
        # Sometimes more than one match for shared last names
        sub = sub[sub['name'].str.contains(first[:3], case=False, na=False)]
        if sub.empty:
            print(f'{name}: not found in relievers_multiyr')
            continue
        career = career_summary(sub)
        recent = career_summary(sub[sub['season'] >= 2023])
        # rprs2 row
        rp_row = rprs2[rprs2['name_api'].str.contains(last, case=False, na=False)]
        rp_row = rp_row[rp_row['name_api'].str.contains(first[:3], case=False, na=False)]
        proj = rp_row.iloc[0].to_dict() if not rp_row.empty else {}

        rows.append({
            'name': name,
            **{'car_' + k: v for k, v in career.items()},
            **{'rec_' + k: v for k, v in recent.items()},
            'rprs2_role_lag1': proj.get('role_lag1', '?'),
            'rprs2_sv_lag1': proj.get('sv_lag1', 0),
            'rprs2_hld_lag1': proj.get('hld_lag1', 0),
            'rprs2_xfp_ros': proj.get('xfp_ros', 0),
            'rprs2_xfp_full': proj.get('xfp_full_year', 0),
            'rprs2_fp_actual_2026': proj.get('fp_actual_2026', 0),
        })

    print(f'{"PITCHER":<18s} {"Sn":>3s} {"IP":>4s} {"SV":>4s} {"K%":>6s} {"KBB%":>6s} '
          f'{"xwOBA":>6s} {"ERA":>5s}')
    print(f'  --- CAREER ---')
    for r in rows:
        print(f'  {r["name"]:<18s} {r.get("car_seasons", 0):>3d} '
              f'{r.get("car_IP", 0):>4.0f} {r.get("car_SV", 0):>4.0f} '
              f'{r.get("car_K%", 0):>5.1f}% {r.get("car_KBB%", 0):>5.1f}% '
              f'{r.get("car_xwOBA", 0):>6.3f} {r.get("car_ERA", 0):>5.2f}')

    print(f'\n  --- 2023-2026 RECENT FORM ---')
    for r in rows:
        print(f'  {r["name"]:<18s} {r.get("rec_seasons", 0):>3d} '
              f'{r.get("rec_IP", 0):>4.0f} {r.get("rec_SV", 0):>4.0f} '
              f'{r.get("rec_K%", 0):>5.1f}% {r.get("rec_KBB%", 0):>5.1f}% '
              f'{r.get("rec_xwOBA", 0):>6.3f} {r.get("rec_ERA", 0):>5.2f}')

    print(f'\n  --- rprs2 (validated RP role/save model) ---')
    print(f'  {"PITCHER":<18s} {"role":<8s} {"SV25":>5s} {"HLD25":>6s} {"xfp_ros":>9s} {"xfp_full":>9s} {"YTD":>6s}')
    for r in rows:
        print(f'  {r["name"]:<18s} {str(r["rprs2_role_lag1"]):<8s} '
              f'{r["rprs2_sv_lag1"]:>5.0f} {r["rprs2_hld_lag1"]:>6.0f} '
              f'{r["rprs2_xfp_ros"]:>9.1f} {r["rprs2_xfp_full"]:>9.1f} '
              f'{r["rprs2_fp_actual_2026"]:>6.1f}')

    # Rank by projected RoS (rprs2_xfp_ros)
    print(f'\n  --- RANKED BY rprs2 xfp_ros ---')
    rows_sorted = sorted(rows, key=lambda r: -r["rprs2_xfp_ros"])
    for i, r in enumerate(rows_sorted, 1):
        print(f'  #{i}  {r["name"]:<18s}  xfp_ros={r["rprs2_xfp_ros"]:.1f}  '
              f'(career K-BB% {r.get("car_KBB%", 0):.1f}, recent {r.get("rec_KBB%", 0):.1f})')

    # =====================
    # FA closer scan
    # =====================
    print(f'\n{"="*80}')
    print(f'{"FA POOL — TOP CLOSER/RP-ELIGIBLE ARMS":^80s}')
    print(f'{"="*80}\n')

    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(_norm(p.name))

    fas = league.free_agents(size=2000)
    rprs2_lkup = rprs2.set_index('name_api').to_dict('index')

    fa_rows = []
    for fa in fas:
        nk = _norm(fa.name)
        if nk in rostered: continue
        pos = getattr(fa, 'position', '')
        if pos != 'RP': continue
        # rprs2 match
        match = None
        for n in rprs2_lkup:
            if _norm(n) == nk:
                match = rprs2_lkup[n]
                break
        if match is None: continue
        if match.get('xfp_ros', 0) < 100: continue  # filter to actually-projecting RPs
        fa_rows.append({
            'name': fa.name,
            'team': getattr(fa, 'proTeam', '?'),
            'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
            'role_lag1': match.get('role_lag1', '?'),
            'sv_lag1': match.get('sv_lag1', 0),
            'hld_lag1': match.get('hld_lag1', 0),
            'sv_2026': match.get('sv_2026', 0),
            'xfp_ros': match.get('xfp_ros', 0),
            'fp_actual_2026': match.get('fp_actual_2026', 0),
        })
    fa_rows.sort(key=lambda r: -r['xfp_ros'])

    print(f'  {"NAME":<22s} {"TEAM":<5s} {"%OWN":>5s} {"ROLE25":<8s} {"SV25":>5s} '
          f'{"SV26":>5s} {"xfp_ros":>9s} {"YTD":>6s}')
    for r in fa_rows[:15]:
        role = str(r["role_lag1"]) if pd.notna(r["role_lag1"]) else '?'
        print(f'  {r["name"]:<22s} {r["team"]:<5s} {r["pct_owned"]:>4.0f}% '
              f'{role:<8s} {r["sv_lag1"]:>5.0f} {r["sv_2026"]:>5.0f} '
              f'{r["xfp_ros"]:>9.1f} {r["fp_actual_2026"]:>6.1f}')

    # Compare top FA to Ligers' bottom-ranked closer
    if rows and fa_rows:
        worst_liger = rows_sorted[-1]
        best_fa = fa_rows[0]
        print(f'\n  --- COMPARISON ---')
        print(f'  Ligers worst closer ({worst_liger["name"]}): rprs2_xfp_ros = {worst_liger["rprs2_xfp_ros"]:.1f}')
        print(f'  Top available FA ({best_fa["name"]}): rprs2_xfp_ros = {best_fa["xfp_ros"]:.1f}')
        gap = best_fa["xfp_ros"] - worst_liger["rprs2_xfp_ros"]
        if gap > 0:
            print(f'  → FA is +{gap:.1f} better (consider swap)')
        else:
            print(f'  → Ligers worst is +{-gap:.1f} better (hold all four)')


if __name__ == '__main__':
    main()
