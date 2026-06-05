"""Analyze whether trajectory tags are redundant with OVR archetype scoring.

Steps:
  1. Correlation: traj indicators vs OVR (per player_type)
  2. Continuous slope_3yr vs binary traj tags in blend
  3. Interaction terms traj × OVR
  4. Simplified model: prior_fp + OVR + slope_3yr + age
  5. Report
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'
RATINGS = {
    'H':  (ROOT / 'data' / 'research' / 'hitter_ratings_master.csv', 'batter'),
    'SP': (ROOT / 'data' / 'research' / 'sp_ratings_master.csv', 'pitcher'),
    'RP': (ROOT / 'data' / 'research' / 'rp_ratings_master.csv', 'pitcher'),
}

CFG = {
    'H':  ('fp_per_pa',    'prior_year_fp_per_pa'),
    'SP': ('fp_per_start', 'prior_year_fp_per_start'),
    'RP': ('fp_per_g',     'prior_year_fp_per_g_rp'),
}


def load_with_slope(panel, ptype):
    path, idcol = RATINGS[ptype]
    r = pd.read_csv(path, usecols=[idcol, 'year', 'OVERALL_slope_3yr'])
    # Build *prior-year* slope: join on (mlbam_id, year-1)
    r = r.rename(columns={idcol: 'mlbam_id', 'OVERALL_slope_3yr': 'slope_3yr_prior'})
    r['year'] = r['year'] + 1  # shift so it joins as prior-year slope
    sub = panel[panel['player_type'] == ptype].merge(r, on=['mlbam_id', 'year'], how='left')
    return sub


def build(sub, ptype):
    y_col, anchor = CFG[ptype]
    sub = sub[sub[y_col].notna() & sub[anchor].notna() & sub['arche_overall_prior'].notna()].copy()
    if ptype == 'RP':
        sub = sub[(sub['year'] >= 2017) & (~sub['covid_short'])]
    else:
        sub = sub[~sub['covid_short']]
    sub['traj_up'] = (sub['arche_traj_prior'] == 'TRENDING_UP').astype(int)
    sub['traj_down'] = (sub['arche_traj_prior'] == 'TRENDING_DOWN').astype(int)
    sub['traj_career_low'] = (sub['arche_traj_prior'] == 'CAREER_LOW').astype(int)
    sub['age_n'] = (sub['age'] - 28) / 5
    return sub, y_col, anchor


def r2_of(sub, feats, y_col):
    s = sub.dropna(subset=feats + [y_col])
    if len(s) < 50: return None, 0
    X = s[feats].values; y = s[y_col].values
    reg = LinearRegression().fit(X, y)
    return r2_score(y, reg.predict(X)), len(s)


def per_year_stability(sub, feats, y_col, baseline_feats):
    """Per-year lift of full feats over baseline."""
    lifts = {}
    for yr in sorted(sub['year'].unique()):
        s = sub[sub['year'] == yr].dropna(subset=feats + [y_col])
        if len(s) < 30: continue
        train = sub[sub['year'] != yr].dropna(subset=feats + [y_col])
        if len(train) < 100: continue
        rf = LinearRegression().fit(train[feats], train[y_col])
        rb = LinearRegression().fit(train[baseline_feats], train[y_col])
        lf = r2_score(s[y_col], rf.predict(s[feats]))
        lb = r2_score(s[y_col], rb.predict(s[baseline_feats]))
        lifts[yr] = round(lf - lb, 4)
    return lifts


def analyze(panel, ptype):
    sub = load_with_slope(panel, ptype)
    sub, y_col, anchor = build(sub, ptype)
    out = {'ptype': ptype, 'n_total': len(sub)}

    # === Step 1: Correlations
    cor_cols = ['arche_overall_prior', 'traj_up', 'traj_down', 'traj_career_low', 'slope_3yr_prior']
    out['correlations'] = sub[cor_cols].corr().round(3).to_dict()

    # === Step 2: R² comparison
    base = [anchor, 'arche_overall_prior', 'arche_career_pct_prior', 'age_n']
    binary = base + ['traj_up', 'traj_down', 'traj_career_low']
    slope = base + ['slope_3yr_prior']
    none  = base
    all_ = base + ['traj_up', 'traj_down', 'traj_career_low', 'slope_3yr_prior']

    r2 = {}
    for name, fs in [('anchor_only', [anchor]),
                     ('no_traj', none),
                     ('binary_traj', binary),
                     ('continuous_slope', slope),
                     ('both', all_)]:
        v, n = r2_of(sub, fs, y_col)
        r2[name] = {'r2': round(v, 4) if v is not None else None, 'n': n}
    out['r2_in_sample'] = r2

    # === Step 3: Interactions
    s2 = sub.dropna(subset=base + ['traj_up','traj_down','traj_career_low','arche_overall_prior']).copy()
    s2['ovr_z'] = (s2['arche_overall_prior'] - s2['arche_overall_prior'].mean()) / s2['arche_overall_prior'].std()
    s2['traj_up_x_ovr'] = s2['traj_up'] * s2['ovr_z']
    s2['traj_down_x_ovr'] = s2['traj_down'] * s2['ovr_z']
    s2['traj_cl_x_ovr'] = s2['traj_career_low'] * s2['ovr_z']
    inter_feats = binary + ['traj_up_x_ovr','traj_down_x_ovr','traj_cl_x_ovr']
    v, n = r2_of(s2, inter_feats, y_col)
    out['r2_in_sample']['binary_plus_interactions'] = {'r2': round(v, 4) if v else None, 'n': n}

    # Per-feature contribution within interaction model
    full_r2 = LinearRegression().fit(s2[inter_feats], s2[y_col]).score(s2[inter_feats], s2[y_col])
    contrib = {}
    for f in ['traj_up','traj_down','traj_career_low','traj_up_x_ovr','traj_down_x_ovr','traj_cl_x_ovr']:
        red = [x for x in inter_feats if x != f]
        r = LinearRegression().fit(s2[red], s2[y_col]).score(s2[red], s2[y_col])
        contrib[f] = round(full_r2 - r, 5)
    out['interaction_contributions'] = contrib

    # === Step 4: stability of binary traj across years (lift over no_traj)
    out['per_year_lift_binary_over_no_traj'] = per_year_stability(sub.dropna(subset=binary+[y_col]), binary, y_col, none)
    out['per_year_lift_slope_over_no_traj'] = per_year_stability(sub.dropna(subset=slope+[y_col]), slope, y_col, none)

    # Drop-test each binary traj tag individually (within the binary model)
    s3 = sub.dropna(subset=binary+[y_col])
    full = LinearRegression().fit(s3[binary], s3[y_col]).score(s3[binary], s3[y_col])
    drop = {}
    for f in ['traj_up','traj_down','traj_career_low']:
        red = [x for x in binary if x != f]
        r = LinearRegression().fit(s3[red], s3[y_col]).score(s3[red], s3[y_col])
        drop[f] = round(full - r, 5)
    out['binary_drop_tests'] = drop

    return out


def main():
    panel = pd.read_parquet(PANEL)
    results = {}
    for p in ['H','SP','RP']:
        print(f'\n=== {p} ===')
        results[p] = analyze(panel, p)
        r = results[p]
        print(f'n={r["n_total"]}')
        print('R² in-sample:')
        for k,v in r['r2_in_sample'].items():
            print(f'  {k:30s} r2={v["r2"]}  n={v["n"]}')
        print('Binary drop tests:', r['binary_drop_tests'])
        print('Interaction contributions:', r['interaction_contributions'])
        print('Per-year lift binary over no_traj:', r['per_year_lift_binary_over_no_traj'])
        print('Per-year lift slope over no_traj:', r['per_year_lift_slope_over_no_traj'])
        print('Correlations (OVR row):', {k:v.get('arche_overall_prior') for k,v in r['correlations'].items()})

    import json
    out = ROOT / 'data' / 'research' / 'validation_runs' / 'weight_blend_traj_analysis_2026-06-04.json'
    with open(out,'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'\nWrote {out}')


if __name__ == '__main__':
    main()
