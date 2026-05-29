"""Lock in the final coefficients for the 3 ship items.

1. SP T+1 with SWING_MISS × WALK_AVOID interaction
2. SP T+2 projection model
3. Park-adjusted HR rate computation
"""
import pandas as pd
import numpy as np

s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\sp_ratings_master.csv')
sf = s[s['data_tier'] == 'FULL'].copy()

s_sorted = sf.sort_values(['pitcher', 'year']).reset_index(drop=True)
s_sorted['fp_t1'] = s_sorted.groupby('pitcher')['fp_per_start'].shift(-1)
s_sorted['fp_t2'] = s_sorted.groupby('pitcher')['fp_per_start'].shift(-2)
s_sorted['year_t1'] = s_sorted.groupby('pitcher')['year'].shift(-1)
s_sorted['year_t2'] = s_sorted.groupby('pitcher')['year'].shift(-2)


def fit(X, y, names):
    X_ = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
    yhat = X_ @ beta
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return dict(zip(['_intercept'] + names, beta)), r2


# === T+1 with SWING_MISS × WALK_AVOID interaction ===
train_t1 = s_sorted[(s_sorted['year_t1'] == s_sorted['year'] + 1) &
                     (s_sorted['fp_t1'].notna())].copy()
print(f'T+1 training rows: {len(train_t1)}')
train_t1['SwM_x_WA'] = train_t1['SWING_MISS'] * train_t1['WALK_AVOID']

feats = ['SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID',
          'velo_rating', 'age', 'SwM_x_WA']
betas, r2 = fit(train_t1[feats].values, train_t1['fp_t1'].values, feats)
print(f'\n=== SP T+1 with interaction (R² = {r2:.4f}) ===')
for k, v in betas.items():
    print(f'  {k:18s} = {v:+.6f}')

# === T+2 model ===
train_t2 = s_sorted[(s_sorted['year_t2'] == s_sorted['year'] + 2) &
                     (s_sorted['fp_t2'].notna())].copy()
print(f'\nT+2 training rows: {len(train_t2)}')

feats_t2 = ['SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID',
             'velo_rating', 'age']
betas_t2, r2_t2 = fit(train_t2[feats_t2].values, train_t2['fp_t2'].values, feats_t2)
print(f'\n=== SP T+2 (R² = {r2_t2:.4f}) ===')
for k, v in betas_t2.items():
    print(f'  {k:18s} = {v:+.6f}')

# === Park factor — load + sanity-check ===
import os
pf_path = r'c:\Users\Joshua\plv_clone\data\research\xfp_cache\park_factors_2018_2026.csv'
if os.path.exists(pf_path):
    pf = pd.read_csv(pf_path)
    print(f'\n=== Park factors ===')
    print(f'  rows: {len(pf)}')
    print(f'  cols: {list(pf.columns)[:10]}')
    print(pf.head(3).to_string())
