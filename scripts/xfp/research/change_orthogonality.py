"""Are the bat-tracking CHANGE signals NEW, or do they just mirror box-score stat
changes we already have? Partial correlation: r(Δmechanic, Δoutcome | Δconventional),
via residualization. If partial r stays meaningful after controlling for the
conventional outcome-stat changes, the mechanic is a distinct (often earlier) tell.

Also: a crude LEADING test — does a mechanic change in one YoY transition co-move
with the OUTCOME change in the NEXT transition (mechanic leads by ~a year)?
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / 'data' / 'research'
CACHE = RES / 'xfp_cache'
import importlib.util
spec = importlib.util.spec_from_file_location("cf", ROOT / 'scripts/xfp/research/change_faithfulness.py')

# reuse wide_bat / yoy_deltas by re-importing the module's helpers
BT = pd.read_csv(RES / 'bat_tracking_all_2023_2026.csv')
TM = pd.read_csv(RES / 'swing_timing_miss_dist_2023_2026.csv')
BT['mlbam_id'] = pd.to_numeric(BT['mlbam_id'], errors='coerce')
TM['mlbam_id'] = pd.to_numeric(TM['mlbam_id'], errors='coerce')

def wide_bat(ptype):
    b = BT[BT['player_type'] == ptype].copy()
    bt = b[b['source'].str.startswith('bat_tracking')].copy()
    aa = b[b['source'].str.startswith('attack_angle')].copy()
    if 'swords' in bt.columns and 'competitive_swings' in bt.columns:
        bt['swords_rate'] = bt['swords'] / bt['competitive_swings'].replace(0, np.nan)
    btc = ['mlbam_id','year','avg_bat_speed','hard_swing_rate','squared_up_per_swing','blast_per_swing','swords_rate']
    aac = ['mlbam_id','year','attack_angle','ideal_attack_angle_rate']
    bt = bt[[c for c in btc if c in bt.columns]].groupby(['mlbam_id','year'], as_index=False).mean()
    aa = aa[[c for c in aac if c in aa.columns]].groupby(['mlbam_id','year'], as_index=False).mean()
    w = bt.merge(aa, on=['mlbam_id','year'], how='outer')
    t = TM[TM['player_type'] == ptype]
    tc = ['mlbam_id','year','whiff_rate','perfect_percent','lined_up_percent']
    t = t[[c for c in tc if c in t.columns]].groupby(['mlbam_id','year'], as_index=False).mean()
    return w.merge(t, on=['mlbam_id','year'], how='outer')

def yoy(wide, lo, hi):
    out = []
    for y in range(lo, hi):
        a = wide[wide['year'] == y].set_index('mlbam_id')
        b = wide[wide['year'] == y+1].set_index('mlbam_id')
        common = a.index.intersection(b.index); common = common[~common.duplicated()]
        a, b = a.loc[common], b.loc[common]
        d = (b - a); d['mlbam_id'] = common; d['t'] = y
        out.append(d.reset_index(drop=True))
    return pd.concat(out, ignore_index=True)

def resid(y, X):
    X1 = np.column_stack([np.ones(len(y))] + [X[c].values for c in X.columns])
    beta, *_ = np.linalg.lstsq(X1, y.values, rcond=None)
    return y.values - X1 @ beta

def partial_test(metric_wide, out_wide, idjoin, focus, outcome, controls, label):
    dm = yoy(metric_wide, 2023, 2026)
    do = yoy(out_wide, 2023, 2026)
    m = dm.merge(do, on=['mlbam_id','t'], suffixes=('','_o'))
    print(f"\n{'='*76}\n{label}: Δ{outcome} controlling for {['Δ'+c for c in controls]}\n{'='*76}")
    print(f"  {'mechanic':<24}{'raw r':>9}{'partial r':>11}{'n':>6}  retained")
    for M in focus:
        cols = [M, outcome] + controls
        sub = m[[c for c in cols if c in m.columns]].dropna()
        if M not in sub.columns or outcome not in sub.columns or len(sub) < 40:
            continue
        ctrl = [c for c in controls if c in sub.columns]
        raw = pearsonr(sub[M], sub[outcome])[0]
        rm = resid(sub[M], sub[ctrl]); ro = resid(sub[outcome], sub[ctrl])
        pr = pearsonr(rm, ro)[0]
        ret = f"{100*pr/raw:>5.0f}%" if abs(raw) > 1e-6 else "  n/a"
        print(f"  Δ{M:<23}{raw:>+9.3f}{pr:>+11.3f}{len(sub):>6}  {ret}")

# HITTERS
HIT = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
HIT = HIT[HIT['year'] >= 2023].copy(); HIT['mlbam_id'] = pd.to_numeric(HIT['batter'], errors='coerce')
hout = ['fp_per_pa_actual','xwoba_per_pa','k_pct','barrel_pct','hard_hit_pct','iso']
hw = HIT[['mlbam_id','year']+[c for c in hout if c in HIT.columns]]
focus_h = ['blast_per_swing','avg_bat_speed','attack_angle','whiff_rate','perfect_percent','lined_up_percent','squared_up_per_swing']
partial_test(wide_bat('batter'), hw, 'mlbam_id', focus_h, 'fp_per_pa_actual',
             ['barrel_pct','hard_hit_pct','k_pct'], 'HITTERS — does mechanic-Δ beat conventional contact-Δ?')

# SP
SP = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
SP = SP[SP['year'] >= 2023].copy(); SP['mlbam_id'] = pd.to_numeric(SP['pitcher'], errors='coerce')
sout = ['fp_per_start_actual','xwoba_contact','k_pct','barrel_pct','hard_hit_pct']
sw = SP[['mlbam_id','year']+[c for c in sout if c in SP.columns]]
focus_s = ['whiff_rate','blast_per_swing','squared_up_per_swing','avg_bat_speed','perfect_percent','lined_up_percent']
partial_test(wide_bat('pitcher'), sw, 'mlbam_id', focus_s, 'fp_per_start_actual',
             ['k_pct','barrel_pct','hard_hit_pct'], 'SP (induced) — does mechanic-Δ beat conventional contact-Δ?')

# ---- crude LEADING test (hitters): mechanic Δ in transition t  -> outcome Δ in transition t+1 ----
print(f"\n{'='*76}\nLEADING (hitters): does Δmechanic[t] foreshadow Δfp[t+1]?  (2 cohorts, exploratory)\n{'='*76}")
dm = yoy(wide_bat('batter'), 2023, 2026); do = yoy(hw, 2023, 2026)
do_next = do.copy(); do_next['t'] = do_next['t'] - 1   # shift outcome back so it joins to prior mechanic Δ
lead = dm.merge(do_next[['mlbam_id','t','fp_per_pa_actual']], on=['mlbam_id','t'])
print(f"  {'mechanic Δ[t]':<24}{'r vs Δfp[t+1]':>14}{'n':>6}")
for M in focus_h:
    sub = lead[[M,'fp_per_pa_actual']].dropna()
    if len(sub) < 30:
        print(f"  Δ{M:<23}{'(n<30)':>14}{len(sub):>6}"); continue
    r = pearsonr(sub[M], sub['fp_per_pa_actual'])[0]
    print(f"  Δ{M:<23}{r:>+14.3f}{len(sub):>6}")
