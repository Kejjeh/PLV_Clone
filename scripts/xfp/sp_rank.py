"""sp_rank.py — Ligers SP staff ranked + FA SP scan.

Career skill + recent form + rp3 projection. Mirrors closer_rank.py.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd
from plv_clone.projections import PROJECTIONS

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'


# Name join key — OWNER: plv_clone.utils.name_match.join_key (order-independent,
# so "Fried, Max" == "Max Fried"). NEVER re-derive locally: 127 local copies
# drifted apart and mis-keyed Ryan O'Hearn's curly apostrophe (2026-07-28).
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


SP_REMAINING_STARTS = 24  # dynamic empirical value, see opponent_lineup_overlap.py


def career_summary(df):
    if df.empty: return {}
    tbf = df['tbf'].sum()
    pitches = df['pitches'].sum()
    swstr = df['swstr'].sum()
    k = df['k'].sum()
    bb = df['bb'].sum()
    return {
        'seasons': len(df),
        'GS': df['gs'].sum(),
        'IP/GS': (df['ip_per_start'] * df['gs']).sum() / df['gs'].sum() if df['gs'].sum() else 0,
        'K%': k / tbf * 100 if tbf else 0,
        'BB%': bb / tbf * 100 if tbf else 0,
        'KBB%': (k - bb) / tbf * 100 if tbf else 0,
        'swstr%': swstr / pitches * 100 if pitches else 0,
        'xwOBA_pa': df['woba_v_sum'].sum() / df['woba_d_sum'].sum() if df['woba_d_sum'].sum() else 0,
        'FP/GS': df['fp_total'].sum() / df['gs'].sum() if df['gs'].sum() else 0,
    }


def main():
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    rp3 = PROJECTIONS.rp3()

    ligers_sps = [
        'Max Fried', 'Freddy Peralta', 'Carlos Rodon', 'Jose Soriano',
        'Parker Messick', 'Will Warren', 'Kyle Bradish',
        'Framber Valdez', 'Tyler Glasnow', 'Hunter Greene',
    ]

    # Normalize lookup once
    sp['_nk'] = sp['player_name'].map(_norm)
    rp3['_nk'] = rp3['player_name'].map(_norm)

    def find_in_sp(name):
        nk = _norm(name)
        return sp[sp['_nk'] == nk]

    def find_in_rp3(name):
        nk = _norm(name)
        return rp3[rp3['_nk'] == nk]

    rows = []
    print(f'{"="*90}')
    print(f'  LIGERS SP STAFF — career + recent form + rp3 projection')
    print(f'{"="*90}\n')

    for name in ligers_sps:
        sub = find_in_sp(name)
        if sub.empty:
            print(f'  {name}: NOT in sp_multiyr')
            continue
        career = career_summary(sub)
        recent = career_summary(sub[sub['year'] >= 2023])
        proj = find_in_rp3(name)
        rprow = proj.iloc[0].to_dict() if not proj.empty else {}
        per_g = rprow.get('xfp_rp3_per_start_sched') or rprow.get('xfp_rp3_per_start', 0)
        # IL'd SPs: subtract expected missed starts (rough, IL-injuryStatus aware)
        starts_rem = SP_REMAINING_STARTS
        if rprow.get('is_on_il_at_split', 0) == 1:
            starts_rem = max(0, SP_REMAINING_STARTS - 4)  # ~4 missed starts on IL
        ros = per_g * starts_rem
        rows.append({
            'name': name,
            **{'car_'+k: v for k, v in career.items()},
            **{'rec_'+k: v for k, v in recent.items()},
            'rp3_ros': ros,
            'rp3_per_g': per_g,
            'rp3_sig': rprow.get('signal', '?'),
            'rp3_starts_remaining': starts_rem,
            'is_on_il': bool(rprow.get('is_on_il_at_split', 0)),
        })

    print(f'  {"PITCHER":<18s} {"Sn":>3s} {"GS":>4s} {"IP/GS":>6s} {"K%":>6s} '
          f'{"KBB%":>6s} {"xwOBA":>6s} {"FP/GS":>6s}')
    print(f'  --- CAREER ---')
    for r in rows:
        print(f'  {r["name"]:<18s} {r.get("car_seasons",0):>3d} '
              f'{r.get("car_GS",0):>4.0f} {r.get("car_IP/GS",0):>6.2f} '
              f'{r.get("car_K%",0):>5.1f}% {r.get("car_KBB%",0):>5.1f}% '
              f'{r.get("car_xwOBA_pa",0):>6.3f} {r.get("car_FP/GS",0):>6.2f}')

    print(f'\n  --- 2023-2026 RECENT FORM ---')
    for r in rows:
        print(f'  {r["name"]:<18s} {r.get("rec_seasons",0):>3d} '
              f'{r.get("rec_GS",0):>4.0f} {r.get("rec_IP/GS",0):>6.2f} '
              f'{r.get("rec_K%",0):>5.1f}% {r.get("rec_KBB%",0):>5.1f}% '
              f'{r.get("rec_xwOBA_pa",0):>6.3f} {r.get("rec_FP/GS",0):>6.2f}')

    print(f'\n  --- rp3 projection ---')
    print(f'  {"PITCHER":<18s} {"per_GS":>7s} {"GS_rem":>7s} {"RoS":>7s}  signal')
    for r in rows:
        print(f'  {r["name"]:<18s} {r["rp3_per_g"]:>7.2f} '
              f'{r["rp3_starts_remaining"]:>7.0f} {r["rp3_ros"]:>7.1f}  {r["rp3_sig"]}')

    rows_sorted = sorted(rows, key=lambda x: -x['rp3_ros'])
    print(f'\n  --- RANKED BY rp3 RoS ---')
    for i, r in enumerate(rows_sorted, 1):
        print(f'  #{i}  {r["name"]:<18s} RoS={r["rp3_ros"]:>6.1f} '
              f'(career K-BB% {r.get("car_KBB%",0):.1f}, recent {r.get("rec_KBB%",0):.1f}, FP/GS {r["rp3_per_g"]:.2f})')

    # ============ FA SP SCAN ============
    print(f'\n{"="*90}')
    print(f'  FA POOL — TOP SP-eligible arms')
    print(f'{"="*90}\n')

    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(_norm(p.name))

    fas = league.free_agents(size=2000)
    fa_rows = []
    for fa in fas:
        nk = _norm(fa.name)
        if nk in rostered: continue
        pos = getattr(fa, 'position', '')
        if pos != 'SP': continue
        m = rp3[rp3['_nk'] == nk]
        if m.empty: continue
        r = m.iloc[0]
        per_g = r.get('xfp_rp3_per_start_sched') or r.get('xfp_rp3_per_start', 0)
        starts_rem = SP_REMAINING_STARTS
        if r.get('is_on_il_at_split', 0) == 1:
            starts_rem = max(0, SP_REMAINING_STARTS - 4)
        ros = per_g * starts_rem
        if ros < 100: continue
        fa_rows.append({
            'name': fa.name,
            'team': getattr(fa, 'proTeam', '?'),
            'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
            'per_g': per_g,
            'gs_rem': starts_rem,
            'ros': ros,
            'signal': r.get('signal', '?'),
        })
    fa_rows.sort(key=lambda x: -x['ros'])

    print(f'  {"NAME":<22s} {"TEAM":<5s} {"%OWN":>5s} {"per_GS":>7s} {"GS_r":>5s} {"RoS":>7s}  signal')
    for r in fa_rows[:15]:
        print(f'  {r["name"]:<22s} {r["team"]:<5s} {r["pct_owned"]:>4.0f}% '
              f'{r["per_g"]:>7.2f} {r["gs_rem"]:>5.0f} {r["ros"]:>7.1f}  {r["signal"]}')

    if rows and fa_rows:
        worst_liger = rows_sorted[-1]
        best_fa = fa_rows[0]
        gap = best_fa['ros'] - worst_liger['rp3_ros']
        print(f'\n  --- COMPARISON ---')
        print(f'  Ligers worst active SP ({worst_liger["name"]}): rp3 RoS = {worst_liger["rp3_ros"]:.1f}')
        print(f'  Top available FA SP ({best_fa["name"]}): rp3 RoS = {best_fa["ros"]:.1f}')
        if gap > 0:
            print(f'  → FA is +{gap:.1f} better')
        else:
            print(f'  → Ligers worst is +{-gap:.1f} better')


if __name__ == '__main__':
    main()
