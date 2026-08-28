"""ROSTER TRENDING BOARD (#1) — who on MY team / the FA pool is physically
getting better or worse RIGHT NOW. Role-appropriate fast-stabilizing signal:
  HITTERS  -> bat speed (validated early-warning detector, hitter-only)
  PITCHERS -> fastball velocity (already validated + in rp3; the pitcher analog,
              since induced bat speed was rejected for pitchers)
2026-to-date vs prior-year baseline, z-scored. Display/context only.
"""
import sys; sys.path.insert(0, str(ROOT))  # repo root, NOT cwd (issue #72)
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
C = ROOT / 'data' / 'research' / 'xfp_cache'
PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play','sac_bunt','catcher_interf'}

# ---- pitcher FB-velo trend (2026 vs 2025) ----
def velo_year(y, min_fb):
    df = pd.read_parquet(C / f'statcast_{y}.parquet',
                         columns=['pitcher','pitch_type','release_speed','type','events','woba_value','woba_denom'])
    fb = df[df['pitch_type'].isin(['FF','SI'])]
    v = fb.groupby('pitcher').agg(velo=('release_speed','mean'), n_fb=('release_speed','size'))
    v = v[v['n_fb'] >= min_fb]
    pa = df[df['events'].isin(PA_EVENTS)]
    o = pa.groupby('pitcher').agg(wd=('woba_denom', lambda s: s.fillna(0).sum()),
                                  wv=('woba_value', lambda s: s.fillna(0).sum()))
    v['xwoba_allow'] = (o['wv'] / o['wd'])
    return v
cur_p, base_p = velo_year(2026, 50), velo_year(2025, 100)
velo = cur_p.join(base_p[['velo','xwoba_allow']], rsuffix='_base', how='inner')
velo['d_velo'] = velo['velo'] - velo['velo_base']
velo['d_xwoba_allow'] = velo['xwoba_allow'] - velo['xwoba_allow_base']
velo['z'] = velo['d_velo'] / velo['d_velo'].std()
VELO = velo.to_dict('index')          # mlbam -> {...}

# ---- hitter bat-speed trend (already built) ----
bs = pd.read_csv(ROOT / 'data' / 'research' / 'bat_speed_trending_2026.csv', index_col=0)
BS = bs.to_dict('index')              # mlbam -> {...}

# ---- ESPN roster + ownership + FAs ----
from app.espn_connector import get_my_roster, get_all_teams, get_free_agents
from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
HIT = pd.read_csv(C / 'hitters_multiyr_2015_2026.csv')
SPM = pd.read_csv(C / 'sp_multiyr_2015_2025.csv')
try:
    RPM = pd.read_csv(C / 'relievers_multiyr_2018_2026.csv')
except Exception:
    RPM = None

def is_pitcher(pos): return str(pos).upper() in {'SP','RP','P'}

def rid(name, pos, team):
    try:
        if is_pitcher(pos):
            return resolve_pitcher_id(name, team=team, role=('SP' if str(pos).upper()=='SP' else 'RP'),
                                      sp_multiyr=SPM, rp_multiyr=RPM)
        return resolve_batter_id(name, team=team, position=pos, multiyr=HIT)
    except Exception:
        return None

mine = get_my_roster()
print(f"My roster: {len(mine)}\n")

def fmt_h(name, d):
    return (f"  {name[:22]:<23}{d['bat_speed']:>6.1f}{d['bat_speed_base']:>7.1f}"
            f"{d['d_bat_speed']:>+7.2f}{d['z']:>+6.1f}{d['d_xwobacon']:>+11.3f}")
def fmt_p(name, d):
    return (f"  {name[:22]:<23}{d['velo']:>6.1f}{d['velo_base']:>7.1f}"
            f"{d['d_velo']:>+7.2f}{d['z']:>+6.1f}{d['d_xwoba_allow']:>+12.3f}")

# my hitters / pitchers
rows_h, rows_p, unres = [], [], []
for _, r in mine.iterrows():
    pid = rid(r['player_name'], r['position'], r.get('pro_team'))
    if pid is None:
        unres.append(f"{r['player_name']} ({r['position']})"); continue
    if is_pitcher(r['position']) and pid in VELO:
        rows_p.append((r['player_name'], VELO[pid]))
    elif (not is_pitcher(r['position'])) and pid in BS:
        rows_h.append((r['player_name'], BS[pid]))
    else:
        unres.append(f"{r['player_name']} ({r['position']}) [no 2026 sample]")

print("=== MY HITTERS — bat-speed trend (2026 vs '25 baseline) ===")
print(f"  {'hitter':<23}{'now':>6}{'base':>7}{'Δmph':>7}{'z':>6}{'ΔxwOBAcon':>11}")
for n, d in sorted(rows_h, key=lambda x: -x[1]['d_bat_speed']):
    print(fmt_h(n, d))
print("\n=== MY PITCHERS — FB velo trend (2026 vs '25 baseline) ===")
print(f"  {'pitcher':<23}{'now':>6}{'base':>7}{'Δmph':>7}{'z':>6}{'ΔxwOBAallow':>12}")
for n, d in sorted(rows_p, key=lambda x: -x[1]['d_velo']):
    print(fmt_p(n, d))
if unres:
    print(f"\n  (no trend read: {', '.join(unres)})")

# ---- FA risers (breakout-watch adds) ----
fa = get_free_agents(size=2000)
fa_h, fa_p = [], []
for _, r in fa.iterrows():
    pid = rid(r['player_name'], r['position'], r.get('pro_team'))
    if pid is None: continue
    if is_pitcher(r['position']) and pid in VELO and VELO[pid].get('n_fb',0) >= 80:
        fa_p.append((r['player_name'], VELO[pid]))
    elif (not is_pitcher(r['position'])) and pid in BS and BS[pid].get('n_sw',0) >= 120:
        fa_h.append((r['player_name'], BS[pid]))

print("\n=== TOP FA HITTER RISERS — bat speed up (breakout watch) ===")
print(f"  {'hitter':<23}{'now':>6}{'base':>7}{'Δmph':>7}{'z':>6}{'ΔxwOBAcon':>11}")
for n, d in sorted(fa_h, key=lambda x: -x[1]['d_bat_speed'])[:12]:
    print(fmt_h(n, d))
print("\n=== TOP FA SP/RP RISERS — FB velo up (stuff-up watch) ===")
print(f"  {'pitcher':<23}{'now':>6}{'base':>7}{'Δmph':>7}{'z':>6}{'ΔxwOBAallow':>12}")
for n, d in sorted(fa_p, key=lambda x: -x[1]['d_velo'])[:12]:
    print(fmt_p(n, d))
