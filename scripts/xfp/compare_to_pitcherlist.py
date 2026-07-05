"""compare_to_pitcherlist.py — my v2 model rankings vs Pitcher List 5/12 + 5/11.

Compares:
  • SP: rp3 v2 per-start × SP_REMAINING_STARTS, vs PL Top 100 (Pollack 5/11)
  • RP (saves-only): rprs2 v2 xfp_ros, vs PL Top 50 Closers (Graham 5/12)

Outputs:
  • Side-by-side leaderboard with rank disagreements
  • Top 10 biggest disagreements per side with diagnostic columns
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd

from plv_clone.projections import PROJECTIONS

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

SP_REMAINING_STARTS = 24

PL_CLOSERS = [
    'Mason Miller','Cade Smith','Aroldis Chapman','Jhoan Duran','Devin Williams',
    'Andres Munoz','Bryan Baker','Tanner Scott','Louis Varland','Pete Fairbanks',
    'Raisel Iglesias','David Bednar',"Riley O'Brien",'Paul Sewald','Daniel Palencia',
    'Jacob Latz','Gregory Soto','Abner Uribe','Kenley Jansen','Seranthony Dominguez',
    'Lucas Erceg','Jack Perkins','Caleb Kilian','Ryan Zeferjahn','Rico Garcia',
    'Graham Ashcraft','Gus Varland','Jeff Hoffman','Trevor Megill','Robert Suarez',
    'Bryan King','Kyle Finnegan','Keaton Winn','Sam Bachman','Anthony Nunez',
    'Pierce Johnson','Blake Treinen','Daniel Lynch IV','Mason Montgomery','Tony Santillan',
    'Juan Morillo','Luke Weaver','Alex Vesia','Grant Taylor','Camilo Doval',
    'Joel Peguero','Erik Sabrowski','Dylan Lee','Garrett Cleavinger','Phil Maton',
]

PL_SPS = [
    'Paul Skenes','Cam Schlittler','Chris Sale','Jacob deGrom','Shohei Ohtani',
    'Yoshinobu Yamamoto','Bryan Woo','Jacob Misiorowski','Cristopher Sanchez',
    'Max Fried','Nolan McLean','Chase Burns','Shota Imanaga','Logan Gilbert',
    'Kevin Gausman','Drew Rasmussen','George Kirby','Zack Wheeler','Carlos Rodon',
    'Dylan Cease','Blake Snell','Joe Ryan','Freddy Peralta','Framber Valdez',
    'Jesus Luzardo','Jose Soriano','Braxton Ashcraft','Parker Messick',
    'Shane McClanahan','Michael King','Robbie Ray','Sonny Gray','Gavin Williams',
    'Logan Henderson','Michael Soroka','Will Warren','Ryne Nelson','Kyle Harrison',
    'Emerson Hancock','Ryan Weathers','Landen Roupp','Connelly Early','Nick Lodolo',
    'Davis Martin','Nathan Eovaldi','Connor Prielipp','Payton Tolle','Kris Bubic',
    'Kyle Bradish','Trevor Rogers','Edward Cabrera','Eury Perez','Sandy Alcantara',
    'Emmet Sheehan','Foster Griffin','Spencer Strider','Robby Snelling','Max Meyer',
    'Reid Detmers','MacKenzie Gore','Bryce Miller','Bryce Elder','Noah Schultz',
    'Michael Wacha','Clay Holmes','Randy Vasquez','Christian Scott','Griffin Canning',
    'Merrill Kelly','Ranger Suarez','Seth Lugo','Nick Martinez','Bubba Chandler',
    'Spencer Arrighetti','Trey Yesavage','Chase Dollander','Peter Lambert',
    'Trevor McDonald','Mike Burrows','Andrew Abbott','Joey Cantillo','Justin Wrobleski',
    'Zac Gallen','Mitch Keller','Lucas Giolito','Jack Leiter','Tanner Bibee',
    'Aaron Nola','Dustin May','Jameson Taillon','Brayan Bello','Slade Cecconi',
    'Jack Flaherty','Cade Cavalli','Carmen Mlodzinski','Janson Junk','Walbert Urena',
    'J.T. Ginn','Keider Montero','Stephen Kolek',
]


# _norm was join_key's exact algorithm (NFD-Mn + sorted alpha tokens); routed to
# the name_match owner (item 10, 2026-07-04). Proven byte-identical → pure move.
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


def main():
    # ===================== SPs =====================
    fixed = OUT / 'xfp_rp3_projections_il_fixed.csv'
    src = fixed if fixed.exists() else OUT / 'xfp_rp3_projections.csv'
    print(f'  using {src.name}')
    rp3 = pd.read_csv(src)
    rp3['nk'] = rp3['player_name'].map(_norm)
    rp3['ros'] = rp3['ros_fixed'] if 'ros_fixed' in rp3.columns else rp3.apply(
        lambda r: (r.get('xfp_rp3_per_start_sched') or r.get('xfp_rp3_per_start', 0))
                    * (SP_REMAINING_STARTS - (4 if r.get('is_on_il_at_split', 0) == 1 else 0)),
        axis=1)
    rp3_sorted = rp3.sort_values('ros', ascending=False).reset_index(drop=True)
    rp3_sorted['my_rank'] = rp3_sorted.index + 1

    sp_rows = []
    for i, name in enumerate(PL_SPS, 1):
        nk = _norm(name)
        m = rp3_sorted[rp3_sorted['nk'] == nk]
        if m.empty:
            sp_rows.append({'PL_rank': i, 'name': name, 'my_rank': None,
                              'my_ros': None, 'diff': None})
            continue
        r = m.iloc[0]
        sp_rows.append({
            'PL_rank': i, 'name': name,
            'my_rank': int(r['my_rank']), 'my_ros': round(r['ros'], 1),
            'per_start': round(r.get('xfp_rp3_per_start_sched') or r['xfp_rp3_per_start'], 2),
            'is_il': int(r.get('is_on_il_at_split', 0) or 0),
            'signal': r.get('signal', '?'),
            'diff': i - int(r['my_rank']),
        })
    sp_df = pd.DataFrame(sp_rows)

    print(f'{"="*90}')
    print(f'  SP COMPARISON: my rp3 v2 RoS vs PL Top 100 (Pollack 5/11)')
    print(f'{"="*90}\n')
    print(f'  {"PL#":>4s} {"NAME":<24s} {"MY#":>5s} {"DIFF":>6s} {"per_GS":>7s} {"RoS":>7s} {"IL":>3s} {"sig":<6s}')

    big_disagree_sp_higher_me = []
    big_disagree_sp_lower_me = []
    for _, r in sp_df.iterrows():
        diff_s = f'{int(r["diff"]):+d}' if pd.notna(r["diff"]) else '—'
        my_rank = f'{int(r["my_rank"])}' if pd.notna(r["my_rank"]) else '—'
        per_g = f'{r["per_start"]:.2f}' if pd.notna(r.get("per_start")) else '—'
        ros = f'{r["my_ros"]:.1f}' if pd.notna(r["my_ros"]) else '—'
        il_s = 'IL' if r.get('is_il') == 1 else ''
        sig = str(r.get('signal', '') if pd.notna(r.get('signal')) else '')
        print(f'  {r["PL_rank"]:>4d} {r["name"]:<24s} {my_rank:>5s} {diff_s:>6s} {per_g:>7s} {ros:>7s} {il_s:>3s} {sig:<6s}')
        if pd.notna(r['diff']):
            if r['diff'] >= 15:  # PL has them low, I have them high
                big_disagree_sp_higher_me.append(r)
            elif r['diff'] <= -15:  # PL has them high, I have them low
                big_disagree_sp_lower_me.append(r)

    print(f'\n  --- SPs PL ranks LOW, I rank HIGH (model loves more than PL) ---')
    for r in sorted(big_disagree_sp_higher_me, key=lambda x: -x['diff'])[:15]:
        print(f'    PL#{r["PL_rank"]:>3d} → my#{int(r["my_rank"]):>3d}: {r["name"]:<24s} '
              f'(per_GS {r.get("per_start","?"):.2f}, RoS {r["my_ros"]:.1f})')

    print(f'\n  --- SPs PL ranks HIGH, I rank LOW (PL loves more than model) ---')
    for r in sorted(big_disagree_sp_lower_me, key=lambda x: x['diff'])[:15]:
        print(f'    PL#{r["PL_rank"]:>3d} → my#{int(r["my_rank"]):>3d}: {r["name"]:<24s} '
              f'(per_GS {r.get("per_start","?"):.2f}, RoS {r["my_ros"]:.1f})')

    # ===================== RPs (closers) =====================
    rprs2 = PROJECTIONS.rprs2()
    rprs2['nk'] = rprs2['name_api'].map(_norm)
    rprs2_sorted = rprs2.sort_values('xfp_ros', ascending=False).reset_index(drop=True)
    rprs2_sorted['my_rank'] = rprs2_sorted.index + 1

    rp_rows = []
    for i, name in enumerate(PL_CLOSERS, 1):
        nk = _norm(name)
        m = rprs2_sorted[rprs2_sorted['nk'] == nk]
        if m.empty:
            rp_rows.append({'PL_rank': i, 'name': name, 'my_rank': None,
                              'xfp_ros': None, 'role_lag1': None, 'diff': None})
            continue
        r = m.iloc[0]
        rp_rows.append({
            'PL_rank': i, 'name': name,
            'my_rank': int(r['my_rank']),
            'xfp_ros': round(r['xfp_ros'], 1),
            'role_lag1': r.get('role_lag1', '?'),
            'sv_lag1': r.get('sv_lag1', 0),
            'sv_2026': r.get('sv_2026', 0),
            'ytd': r.get('fp_actual_2026', 0),
            'diff': i - int(r['my_rank']),
        })
    rp_df = pd.DataFrame(rp_rows)

    print(f'\n{"="*90}')
    print(f'  RP COMPARISON: my rprs2 v2 xfp_ros vs PL Top 50 Closers (Graham 5/12)')
    print(f'{"="*90}\n')
    print(f'  {"PL#":>4s} {"NAME":<24s} {"MY#":>5s} {"DIFF":>6s} {"role25":<8s} {"SV25":>5s} {"SV26":>5s} {"RoS":>7s}')

    big_disagree_rp_higher_me = []
    big_disagree_rp_lower_me = []
    for _, r in rp_df.iterrows():
        diff_s = f'{int(r["diff"]):+d}' if pd.notna(r["diff"]) else '—'
        my_rank = f'{int(r["my_rank"])}' if pd.notna(r["my_rank"]) else '—'
        ros = f'{r["xfp_ros"]:.1f}' if pd.notna(r["xfp_ros"]) else '—'
        role = str(r.get('role_lag1', '')) if pd.notna(r.get('role_lag1')) else '?'
        sv25 = f'{int(r["sv_lag1"])}' if pd.notna(r.get('sv_lag1')) else '?'
        sv26 = f'{int(r["sv_2026"])}' if pd.notna(r.get('sv_2026')) else '?'
        print(f'  {r["PL_rank"]:>4d} {r["name"]:<24s} {my_rank:>5s} {diff_s:>6s} {role:<8s} {sv25:>5s} {sv26:>5s} {ros:>7s}')
        if pd.notna(r['diff']):
            if r['diff'] >= 15:
                big_disagree_rp_higher_me.append(r)
            elif r['diff'] <= -15:
                big_disagree_rp_lower_me.append(r)

    print(f'\n  --- CLOSERS PL ranks LOW, I rank HIGH ---')
    for r in sorted(big_disagree_rp_higher_me, key=lambda x: -x['diff'])[:15]:
        print(f'    PL#{r["PL_rank"]:>3d} → my#{int(r["my_rank"]):>3d}: {r["name"]:<24s} '
              f'(SV25 {r.get("sv_lag1",0):.0f}, SV26 {r.get("sv_2026",0):.0f}, role {r.get("role_lag1","?")})')

    print(f'\n  --- CLOSERS PL ranks HIGH, I rank LOW ---')
    for r in sorted(big_disagree_rp_lower_me, key=lambda x: x['diff'])[:15]:
        print(f'    PL#{r["PL_rank"]:>3d} → my#{int(r["my_rank"]):>3d}: {r["name"]:<24s} '
              f'(SV25 {r.get("sv_lag1",0):.0f}, SV26 {r.get("sv_2026",0):.0f}, role {r.get("role_lag1","?")})')

    # Rank correlation
    sp_join = sp_df.dropna(subset=['my_rank']).copy()
    rp_join = rp_df.dropna(subset=['my_rank']).copy()
    if len(sp_join) >= 10:
        rho_sp = sp_join[['PL_rank', 'my_rank']].corr(method='spearman').iloc[0, 1]
        print(f'\n  SP Spearman rank correlation (PL vs my model): {rho_sp:.3f}  (n={len(sp_join)})')
    if len(rp_join) >= 10:
        rho_rp = rp_join[['PL_rank', 'my_rank']].corr(method='spearman').iloc[0, 1]
        print(f'  RP Spearman rank correlation (PL vs my model): {rho_rp:.3f}  (n={len(rp_join)})')

    sp_df.to_csv(OUT / 'sp_vs_pitcherlist.csv', index=False)
    rp_df.to_csv(OUT / 'rp_vs_pitcherlist.csv', index=False)


if __name__ == '__main__':
    main()
