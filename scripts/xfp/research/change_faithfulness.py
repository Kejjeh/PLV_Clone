"""CHANGE-FAITHFULNESS TEST (display/context signal validation, not a ranker).

Question: when a player's bat-tracking metric MOVES year-over-year, does their
real performance move WITH it? r(delta_metric, delta_outcome) pooled across the
3 available YoY cohorts (2023->24, 24->25, 25->26), with per-cohort sign
consistency. A metric whose CHANGE co-moves with a real performance CHANGE is a
faithful "getting better / worse" detector even though it can't be a forward ranker.

Roles: hitter (batter bat-tracking), SP (induced), RP (induced).
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / 'data' / 'research'
CACHE = RES / 'xfp_cache'

BT = pd.read_csv(RES / 'bat_tracking_all_2023_2026.csv')
TM = pd.read_csv(RES / 'swing_timing_miss_dist_2023_2026.csv')
BT['mlbam_id'] = pd.to_numeric(BT['mlbam_id'], errors='coerce')
TM['mlbam_id'] = pd.to_numeric(TM['mlbam_id'], errors='coerce')

def wide_bat(ptype):
    """One row per (id, year): merge bat_tracking + attack_angle + timing sources."""
    b = BT[(BT['player_type'] == ptype)].copy()
    bt = b[b['source'].str.startswith('bat_tracking')]
    aa = b[b['source'].str.startswith('attack_angle')]
    # swords rate
    if 'swords' in bt.columns and 'competitive_swings' in bt.columns:
        bt = bt.assign(swords_rate=bt['swords'] / bt['competitive_swings'].replace(0, np.nan))
    btcols = ['mlbam_id','year','avg_bat_speed','hard_swing_rate','squared_up_per_swing',
              'blast_per_swing','swing_length','swords_rate','whiff_per_swing','batter_run_value']
    aacols = ['mlbam_id','year','attack_angle','swing_tilt','ideal_attack_angle_rate','attack_direction']
    bt = bt[[c for c in btcols if c in bt.columns]].groupby(['mlbam_id','year'], as_index=False).mean()
    aa = aa[[c for c in aacols if c in aa.columns]].groupby(['mlbam_id','year'], as_index=False).mean()
    w = bt.merge(aa, on=['mlbam_id','year'], how='outer')
    # timing
    t = TM[TM['player_type'] == ptype].copy()
    tcols = ['mlbam_id','year','whiff_rate','miss_distance','perfect_percent','flawed_percent',
             'late_percent','early_percent','tied_up_percent','lined_up_percent']
    t = t[[c for c in tcols if c in t.columns]].groupby(['mlbam_id','year'], as_index=False).mean()
    w = w.merge(t, on=['mlbam_id','year'], how='outer')
    return w

def yoy_deltas(wide, idcol='mlbam_id'):
    """Stack 3 cohorts: for each id present in (y, y+1), delta = val(y+1)-val(y)."""
    out = []
    for y in [2023, 2024, 2025]:
        a = wide[wide['year'] == y].set_index(idcol)
        b = wide[wide['year'] == y + 1].set_index(idcol)
        common = a.index.intersection(b.index)
        common = common[~common.duplicated()]
        a, b = a.loc[common], b.loc[common]
        d = (b - a)
        d['cohort'] = f'{y}->{y+1}'
        d[idcol] = common
        out.append(d.reset_index(drop=True))
    return pd.concat(out, ignore_index=True)

def faithfulness(metric_wide, outcome_wide, metrics, outcomes, idcol, label):
    dm = yoy_deltas(metric_wide, idcol)
    do = yoy_deltas(outcome_wide, idcol)
    merged = dm.merge(do, on=[idcol, 'cohort'], suffixes=('_m', '_o'))
    print(f"\n{'='*78}\n{label}  (pooled delta-pairs available: {len(merged)})\n{'='*78}")
    for O in outcomes:
        oc = O + '_o' if O + '_o' in merged.columns else O
        if oc not in merged.columns:
            continue
        rows = []
        for M in metrics:
            mc = M + '_m' if M + '_m' in merged.columns else M
            if mc not in merged.columns:
                continue
            sub = merged[[mc, oc, 'cohort']].dropna()
            if len(sub) < 40:
                continue
            r, p = pearsonr(sub[mc], sub[oc])
            # per-cohort signs
            signs = []
            for c, g in sub.groupby('cohort'):
                if len(g) >= 20:
                    rc = pearsonr(g[mc], g[oc])[0]
                    signs.append('+' if rc > 0 else '-')
            consist = signs.count('+' if r > 0 else '-')
            rows.append((M, r, p, len(sub), f"{consist}/{len(signs)}", ''.join(signs)))
        rows.sort(key=lambda x: -abs(x[1]))
        print(f"\n  Δoutcome = Δ{O}:")
        print(f"    {'metric':<26}{'r(Δ,Δ)':>9}{'p':>10}{'n':>6}  cohort-consist")
        for M, r, p, n, cc, sg in rows:
            star = '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else ''))
            print(f"    Δ{M:<25}{r:>+9.3f}{p:>10.1e}{n:>6}  {cc} [{sg}] {star}")

# ---------- HITTERS ----------
HIT = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
HIT = HIT[HIT['year'] >= 2023].copy()
HIT['mlbam_id'] = pd.to_numeric(HIT['batter'], errors='coerce')
hit_metrics = ['avg_bat_speed','hard_swing_rate','squared_up_per_swing','blast_per_swing',
               'swing_length','swords_rate','whiff_per_swing','attack_angle','swing_tilt',
               'ideal_attack_angle_rate','whiff_rate','miss_distance','perfect_percent',
               'late_percent','early_percent','tied_up_percent','lined_up_percent']
hit_out = ['fp_per_pa_actual','xwoba_per_pa','k_pct','barrel_pct','iso','hard_hit_pct','ev90']
faithfulness(wide_bat('batter'), HIT[['mlbam_id','year']+[c for c in hit_out if c in HIT.columns]],
             hit_metrics, hit_out, 'mlbam_id', 'HITTERS — Δmechanic vs Δoutcome')

# ---------- SP (induced) ----------
SP = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
SP = SP[SP['year'] >= 2023].copy()
SP['mlbam_id'] = pd.to_numeric(SP['pitcher'], errors='coerce')
sp_out = ['fp_per_start_actual','xwoba_contact','k_pct','bb_pct','barrel_pct','hard_hit_pct']
pit_metrics = ['avg_bat_speed','hard_swing_rate','squared_up_per_swing','blast_per_swing',
               'swing_length','swords_rate','whiff_per_swing','attack_angle',
               'ideal_attack_angle_rate','whiff_rate','miss_distance','perfect_percent',
               'late_percent','tied_up_percent','lined_up_percent']
sp_ids = set(SP['mlbam_id'].dropna().astype(int))
faithfulness(wide_bat('pitcher'), SP[['mlbam_id','year']+[c for c in sp_out if c in SP.columns]],
             pit_metrics, sp_out, 'mlbam_id', 'SP (induced) — Δmechanic-allowed vs Δoutcome')

# ---------- RP (induced) ----------
RPD = pd.read_csv(CACHE / 'rp_damage_gb_2018_2026.csv')
RPD = RPD[RPD['year'] >= 2023].copy()
RPD['mlbam_id'] = pd.to_numeric(RPD['pitcher'], errors='coerce')
# RP-pure: in rp_damage_gb but NOT an SP (gs>=8 universe)
RPD = RPD[~RPD['mlbam_id'].isin(sp_ids)]
rp_out = ['xwobacon','barrel_pct','hard_hit_pct']
faithfulness(wide_bat('pitcher'), RPD[['mlbam_id','year']+[c for c in rp_out if c in RPD.columns]],
             pit_metrics, rp_out, 'mlbam_id', 'RP (induced) — Δmechanic-allowed vs Δoutcome')
