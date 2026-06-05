"""Derive z-standardized RP coefficients for VALIDATED_WEIGHTS['RP']['with_pl'].

Fits pooled OLS on joined master_panel x pl_rank_panel RP rows (>=2017, ex 2020).
Features mirror VALIDATED_WEIGHTS['RP']['no_pl'] + pl_rank_mid_inv (cap-adjusted to match
blend_score.py's _pl_rank_mid_inv_for transform: max(0, (100-rank)/100)).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'
PL = ROOT / 'data' / 'research' / 'historical_panel' / 'pl_rank_panel.parquet'

panel = pd.read_parquet(PANEL)
pl = pd.read_parquet(PL)

sub = panel[panel['player_type'] == 'RP'].copy()
sub = sub[sub['fp_per_g'].notna() & sub['prior_year_fp_per_g_rp'].notna()
          & sub['arche_overall_prior'].notna()]
sub = sub[(sub['year'] >= 2017) & (~sub['covid_short'])]
sub['traj_up_prior'] = (sub['arche_traj_prior'] == 'TRENDING_UP').astype(int)
sub['traj_down_prior'] = (sub['arche_traj_prior'] == 'TRENDING_DOWN').astype(int)
sub['traj_career_low_prior'] = (sub['arche_traj_prior'] == 'CAREER_LOW').astype(int)
sub['age_normalized'] = (sub['age'] - 28) / 5

m = sub.merge(pl, on=['mlbam_id', 'year'], how='inner')
# Match blend_score.py transform: pl_rank_mid_inv = max(0, (100-rank)/100)
# Use 'pl_rank_mid' col (or fall back to early/late if mid missing per snapshot)
m['pl_rank_use'] = m['pl_rank_mid'].fillna(m['pl_rank_early']).fillna(m['pl_rank_late'])
m['pl_rank_mid_inv'] = (100.0 - m['pl_rank_use'].astype(float)).clip(lower=0) / 100.0
m = m.dropna(subset=['pl_rank_mid_inv'])

feats = ['prior_year_fp_per_g_rp', 'arche_overall_prior', 'arche_career_pct_prior',
         'traj_up_prior', 'traj_down_prior', 'traj_career_low_prior',
         'age_normalized', 'pl_rank_mid_inv']
m = m.dropna(subset=feats + ['fp_per_g'])
print(f'RP rows joined: {len(m)}')

means = m[feats].mean()
stds = m[feats].std().replace(0, 1)
Xz = (m[feats] - means) / stds
y = m['fp_per_g'].values

reg = LinearRegression().fit(Xz, y)
r2 = reg.score(Xz, y)
print(f'pooled R2 = {r2:.4f}')
print('\nz-standardized coefficients (RP with_pl):')
coefs = {}
for f, c in zip(feats, reg.coef_):
    coefs[f] = round(float(c), 4)
    print(f'  {f:35s} {c:+.4f}')
print(f'\nintercept = {reg.intercept_:.4f}')

# LOYO CV for honest lift vs no_pl baseline on SAME rows
base_feats = [f for f in feats if f != 'pl_rank_mid_inv']
years = sorted(m['year'].unique())
preds_b, preds_f, actuals = [], [], []
for h in years:
    tr, te = m[m['year'] != h], m[m['year'] == h]
    if len(tr) < 30 or len(te) < 3:
        continue
    mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
    Xtr_f = ((tr[feats] - mu) / sd).fillna(0).values
    Xte_f = ((te[feats] - mu) / sd).fillna(0).values
    Xtr_b = ((tr[base_feats] - mu[base_feats]) / sd[base_feats]).fillna(0).values
    Xte_b = ((te[base_feats] - mu[base_feats]) / sd[base_feats]).fillna(0).values
    ytr, yte = tr['fp_per_g'].values, te['fp_per_g'].values
    preds_b.extend(LinearRegression().fit(Xtr_b, ytr).predict(Xte_b))
    preds_f.extend(LinearRegression().fit(Xtr_f, ytr).predict(Xte_f))
    actuals.extend(yte)
r2_b = r2_score(actuals, preds_b)
r2_f = r2_score(actuals, preds_f)
print(f'\nLOYO R2 baseline = {r2_b:.4f}  with_pl = {r2_f:.4f}  lift = {r2_f-r2_b:+.4f}')

out = {
    'n': len(m), 'pooled_r2': r2, 'loyo_r2_baseline': r2_b,
    'loyo_r2_with_pl': r2_f, 'loyo_lift': r2_f - r2_b,
    'coefficients': coefs,
}
(ROOT / 'data' / 'research' / 'validation_runs' /
 'rp_with_pl_coefs_2026-06-05.json').write_text(json.dumps(out, indent=2))
print('\nwrote rp_with_pl_coefs_2026-06-05.json')
