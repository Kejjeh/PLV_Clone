"""ligers_six_pack_summary.py — Ligers-roster view across the six new artifacts.

Reads:
  sp_velocity_trend.csv         (item 4)
  hitter_xwoba_residual.csv     (item 5)
  sp_lineup_pass.csv            (item 6)
  batter_pitch_weakness.csv     (item 2 — partial; needs pairwise)
  lineup_protection.csv         (item 7)
  projection_ensemble_*.csv     (item 15)

Emits a single console report focused on Ligers players.
"""
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0, '.')

from plv_clone.paths import ROOT
OUT = ROOT / 'data' / 'outputs'

from plv_clone.league_state import LeagueState
from plv_clone.league_config import MY_TEAM_NAME
ls = LeagueState()
teams = ls.all_teams()
ligers = teams[teams['team_name'] == MY_TEAM_NAME]
hit_names = ligers[~ligers['position'].isin(['SP', 'RP', 'P'])]['player_name'].tolist()
sp_names = ligers[ligers['position'].isin(['SP', 'P'])]['player_name'].tolist()
rp_names = ligers[ligers['position'] == 'RP']['player_name'].tolist()


def name_variants(names):
    """Return both 'First Last' and 'Last, First' forms for matching."""
    out = set(names)
    for n in names:
        if ',' not in n:
            parts = n.rsplit(' ', 1)
            if len(parts) == 2:
                out.add(f'{parts[1]}, {parts[0]}')
        else:
            parts = [p.strip() for p in n.split(',', 1)]
            if len(parts) == 2:
                out.add(f'{parts[1]} {parts[0]}')
    return out


hit_set = name_variants(hit_names)
sp_set = name_variants(sp_names)
rp_set = name_variants(rp_names)

print('=' * 80)
print('LIGERS — SIX-PACK SUMMARY')
print('=' * 80)

def show(df, names_set, name_col='player_name'):
    return df[df[name_col].isin(names_set)] if name_col in df.columns else df

# ── ITEM 4 — Velocity trend (SPs) ────────────────────────────────────────────
print('\n[Item 4] SP velocity trend (DECLINING ≥1.0 mph = injury watch)')
v = pd.read_csv(OUT / 'sp_velocity_trend.csv')
v_l = show(v, sp_set | rp_set)
print(v_l[['player_name', 'starts_n', 'starts_2026', 'career_velo',
            'last5_velo', 'last5_2026_velo', 'velo_drop_mph', 'alert',
            'last_start_date']].to_string(index=False))

# ── ITEM 5 — xwOBA residual (hitters) ────────────────────────────────────────
print('\n[Item 5] Hitter xwOBA residual (positive = unlucky/regression-up)')
x = pd.read_csv(OUT / 'hitter_xwoba_residual.csv')
x_l = show(x, hit_set)
cols5 = ['player_name', 'bbe_latest', 'woba_con_latest', 'xwoba_con_latest',
        'xwoba_residual_latest', 'ev90_latest', 'barrel_pct_latest']
print(x_l[cols5].sort_values('xwoba_residual_latest', ascending=False).to_string(index=False))

# ── ITEM 6 — Time-through-order (SPs) ────────────────────────────────────────
print('\n[Item 6] SP TTO penalty (raw drop in core_fp/PA from 1st to 3rd time)')
t = pd.read_csv(OUT / 'sp_lineup_pass.csv')
t_l = show(t, sp_set)
cols6 = ['player_name', 'total_pa', 'tto1_rate', 'tto2_rate', 'tto3_rate', 'tto3_minus_tto1']
avail = [c for c in cols6 if c in t_l.columns]
print(t_l[avail].sort_values('tto3_minus_tto1').to_string(index=False))

# ── ITEM 7 — Lineup protection (hitters) ─────────────────────────────────────
print('\n[Item 7] Lineup protection (BB% lift from STRONG vs WEAK protector)')
p = pd.read_csv(OUT / 'lineup_protection.csv')
p_l = show(p, hit_set)
cols7 = ['player_name', 'pa_STRONG', 'pa_WEAK', 'bb_pct_STRONG', 'bb_pct_WEAK',
        'bb_protect_lift', 'iso_protect_lift']
avail = [c for c in cols7 if c in p_l.columns]
print(p_l[avail].sort_values('bb_protect_lift', ascending=False, na_position='last').to_string(index=False))

# ── ITEM 15 — Ensemble vs rh3/rp3 ────────────────────────────────────────────
print('\n[Item 15a] Hitter ensemble (rh3 vs rh3 + ATC/Steamer/ZiPS/TheBatX)')
eh = pd.read_csv(OUT / 'projection_ensemble_hitters.csv')
eh_l = show(eh, hit_set)
eh_l = eh_l.copy()
if 'ext_mean_fp_per_pa' in eh_l.columns:
    eh_l['delta_per_pa'] = (eh_l['ensemble_fp_per_pa'] - eh_l['xfp_rh3_per_pa']).round(4)
    cols15h = ['player_name', 'xfp_rh3_per_pa', 'ext_mean_fp_per_pa', 'ensemble_fp_per_pa',
              'delta_per_pa', 'ext_n_systems']
    avail = [c for c in cols15h if c in eh_l.columns]
    print(eh_l[avail].sort_values('delta_per_pa', ascending=False, na_position='last').to_string(index=False))
else:
    print('  (no external sources merged)')

print('\n[Item 15b] Pitcher ensemble (rp3 vs rp3 + ATC/Steamer/ZiPS/TheBatX)')
ep = pd.read_csv(OUT / 'projection_ensemble_pitchers.csv')
ep_l = show(ep, sp_set | rp_set)
ep_l = ep_l.copy()
if 'ext_mean_fp_per_g' in ep_l.columns:
    ep_l['delta_per_start'] = (ep_l['ensemble_fp_per_start'] - ep_l['xfp_rp3_per_start']).round(2)
    cols15p = ['player_name', 'xfp_rp3_per_start', 'ext_mean_fp_per_g', 'ensemble_fp_per_start',
              'delta_per_start', 'ext_n_systems']
    avail = [c for c in cols15p if c in ep_l.columns]
    print(ep_l[avail].sort_values('delta_per_start', ascending=False, na_position='last').to_string(index=False))
else:
    print('  (no external sources merged)')

# ── ITEM 2 — Pitch weakness, hitter side (Ligers) ────────────────────────────
print('\n[Item 2] Ligers hitter weakness profile (whiff% by pitch group)')
b = pd.read_csv(OUT / 'batter_pitch_weakness.csv')
b_l = show(b, hit_set)
piv = b_l.pivot_table(index='player_name', columns='ptg', values='whiff_per_swing', aggfunc='first')
print(piv.round(1).fillna('-').to_string())
