"""hitter_rank.py — Ligers position-player staff ranked + FA hitter scan.

Career skill + recent form + rh3 projection. Mirrors sp_rank.py.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'


def _norm(s):
    """Order-independent normalize — handles 'Last, First' == 'First Last'."""
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def career_summary(df):
    if df.empty: return {}
    pa = df['pa'].sum()
    pitches = df['pitches'].sum()
    swings = df['swing'].sum()
    swstr = df['swstr'].sum()
    k = df['k'].sum()
    bb = df['bb'].sum()
    h = df['h'].sum()
    hr = df['hr'].sum()
    tb = df['tb'].sum()
    sb = df['sb'].sum()
    return {
        'seasons': len(df),
        'PA': pa,
        'HR/600': hr / pa * 600 if pa else 0,
        'SB/600': sb / pa * 600 if pa else 0,
        'K%': k / pa * 100 if pa else 0,
        'BB%': bb / pa * 100 if pa else 0,
        'whiff%': swstr / swings * 100 if swings else 0,
        'avg_ev': (df['avg_ev'] * df['bip']).sum() / df['bip'].sum() if df['bip'].sum() else 0,
        'hardhit%': df['hard_hit_n'].sum() / df['bip'].sum() * 100 if df['bip'].sum() else 0,
        'barrel%': df['barrel_n'].sum() / df['bip'].sum() * 100 if df['bip'].sum() else 0,
        'xwOBA': df['woba_v_sum'].sum() / df['woba_d_sum'].sum() if df['woba_d_sum'].sum() else 0,
        'core_fp_per_pa': df['core_fp_total'].sum() / pa if pa else 0,
    }


def main():
    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    h['_nk'] = h['player_name'].map(_norm)
    rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh3['_nk'] = rh3['player_name'].map(_norm)

    ligers_hitters = [
        'Aaron Judge', 'Vladimir Guerrero Jr.', 'Pete Alonso',
        'Elly De La Cruz', 'Bo Bichette', 'Trea Turner',
        'Jordan Walker', 'Corbin Carroll', 'Luis Arraez',
        'Michael Harris II', 'Salvador Perez', 'Wyatt Langford',
        'Brendan Donovan',
    ]

    rows = []
    print(f'{"="*100}')
    print(f'  LIGERS HITTERS — career + recent form + rh3 projection')
    print(f'{"="*100}\n')

    for name in ligers_hitters:
        nk = _norm(name)
        sub = h[h['_nk'] == nk]
        if sub.empty:
            print(f'  {name}: NOT in hitters_multiyr')
            continue
        career = career_summary(sub)
        recent = career_summary(sub[sub['year'] >= 2023])
        proj = rh3[rh3['_nk'] == nk]
        rprow = proj.iloc[0].to_dict() if not proj.empty else {}
        rows.append({
            'name': name,
            **{'car_'+k_: v for k_, v in career.items()},
            **{'rec_'+k_: v for k_, v in recent.items()},
            'rh3_per_pa': rprow.get('xfp_rh3_per_pa', 0),
            'rh3_ros': rprow.get('expected_total_fp_remaining', 0),
            'rh3_sig': rprow.get('signal', '?'),
            'pos': rprow.get('primary_position', '?'),
        })

    # CAREER
    print(f'  {"NAME":<22s} {"PA":>5s} {"K%":>5s} {"BB%":>5s} {"EV":>5s} {"HH%":>5s} '
          f'{"BRL%":>5s} {"HR/600":>7s} {"SB/600":>7s} {"xwOBA":>6s} {"core_fp/PA":>11s}')
    print(f'  --- CAREER ---')
    for r in rows:
        print(f'  {r["name"]:<22s} {r.get("car_PA",0):>5.0f} '
              f'{r.get("car_K%",0):>4.1f}% {r.get("car_BB%",0):>4.1f}% '
              f'{r.get("car_avg_ev",0):>5.1f} {r.get("car_hardhit%",0):>4.1f}% '
              f'{r.get("car_barrel%",0):>4.1f}% {r.get("car_HR/600",0):>7.1f} '
              f'{r.get("car_SB/600",0):>7.1f} {r.get("car_xwOBA",0):>6.3f} '
              f'{r.get("car_core_fp_per_pa",0):>11.4f}')

    print(f'\n  --- 2023-2026 RECENT FORM ---')
    for r in rows:
        print(f'  {r["name"]:<22s} {r.get("rec_PA",0):>5.0f} '
              f'{r.get("rec_K%",0):>4.1f}% {r.get("rec_BB%",0):>4.1f}% '
              f'{r.get("rec_avg_ev",0):>5.1f} {r.get("rec_hardhit%",0):>4.1f}% '
              f'{r.get("rec_barrel%",0):>4.1f}% {r.get("rec_HR/600",0):>7.1f} '
              f'{r.get("rec_SB/600",0):>7.1f} {r.get("rec_xwOBA",0):>6.3f} '
              f'{r.get("rec_core_fp_per_pa",0):>11.4f}')

    rows_sorted = sorted(rows, key=lambda x: -x['rh3_ros'])
    print(f'\n  --- RANKED BY rh3 RoS ---')
    for i, r in enumerate(rows_sorted, 1):
        print(f'  #{i:>2d}  {r["name"]:<22s} pos={r["pos"]:<3s} '
              f'rh3 RoS={r["rh3_ros"]:>6.1f}  '
              f'(per_PA={r["rh3_per_pa"]:.3f}, career xwOBA {r.get("car_xwOBA",0):.3f}, recent {r.get("rec_xwOBA",0):.3f})')

    # =========== FA SCAN ===========
    print(f'\n{"="*100}')
    print(f'  FA POOL — top hitters by validated rh3 RoS')
    print(f'{"="*100}\n')

    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(_norm(p.name))

    fas = league.free_agents(size=500)
    fa_rows = []
    for fa in fas:
        nk = _norm(fa.name)
        if nk in rostered: continue
        # hitter eligibility check
        slots = set(getattr(fa, 'eligibleSlots', []) or [])
        if not (slots & {'C', '1B', '2B', '3B', 'SS', 'OF', 'CF', 'LF', 'RF', 'DH', 'UTIL'}):
            continue
        m = rh3[rh3['_nk'] == nk]
        if m.empty: continue
        r = m.iloc[0]
        ros = r.get('expected_total_fp_remaining', 0)
        if ros < 150: continue
        fa_rows.append({
            'name': fa.name,
            'team': getattr(fa, 'proTeam', '?'),
            'pos': r.get('primary_position', '?'),
            'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
            'slots': sorted(slots & {'C', '1B', '2B', '3B', 'SS', 'OF', 'CF', 'LF', 'RF', 'DH', 'UTIL'}),
            'per_pa': r.get('xfp_rh3_per_pa', 0),
            'ros': ros,
            'signal': r.get('signal', '?'),
        })
    fa_rows.sort(key=lambda x: -x['ros'])

    print(f'  {"NAME":<24s} {"TEAM":<5s} {"POS":<4s} {"%OWN":>5s} {"per_PA":>7s} {"RoS":>7s}  signal  slots')
    for r in fa_rows[:20]:
        print(f'  {r["name"]:<24s} {r["team"]:<5s} {r["pos"]:<4s} '
              f'{r["pct_owned"]:>4.0f}% {r["per_pa"]:>7.3f} {r["ros"]:>7.1f}  '
              f'{r["signal"]:<5s}  {",".join(r["slots"][:5])}')

    if rows and fa_rows:
        worst_liger = rows_sorted[-1]
        best_fa = fa_rows[0]
        gap = best_fa['ros'] - worst_liger['rh3_ros']
        print(f'\n  --- COMPARISON ---')
        print(f'  Ligers worst hitter ({worst_liger["name"]}): rh3 RoS = {worst_liger["rh3_ros"]:.1f}')
        print(f'  Top available FA ({best_fa["name"]}): rh3 RoS = {best_fa["ros"]:.1f}')
        if gap > 0:
            print(f'  → FA is +{gap:.1f} better')


if __name__ == '__main__':
    main()
