"""Build next-year (T+1) FP prediction model using sub-domain ratings."""
import pandas as pd
import numpy as np

h = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\hitter_ratings_master.csv')
s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\sp_ratings_master.csv')


def fit(X, y, names):
    X_ = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
    yhat = X_ @ beta
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return dict(zip(['_intercept'] + list(names), beta)), r2


# === HITTERS: Predict T+1 fp_per_pa from year T sub-domains ===
HITTER_FEATS = ['Z_CONTACT', 'O_CONTACT', 'K_AVOIDANCE', 'CONTACT_QUALITY', 'SPRAY_PROFILE',
                'RAW_POWER', 'LAUNCH_OPTIM', 'DAMAGE_PROD',
                'PATIENCE', 'AGGRESSION',
                'SPEED_TOOL', 'SB_CONVERSION', 'age']

# Build training data: each batter's year T row + their year T+1 fp_per_pa
h_sorted = h.sort_values(['batter', 'year']).reset_index(drop=True)
h_sorted['fp_t1'] = h_sorted.groupby('batter')['fp_per_pa'].shift(-1)
h_sorted['year_t1'] = h_sorted.groupby('batter')['year'].shift(-1)
# Only use rows where T+1 is the immediately following year
train = h_sorted[(h_sorted['year_t1'] == h_sorted['year'] + 1) &
                 (h_sorted['data_tier'] == 'FULL') &
                 (h_sorted['fp_t1'].notna())].copy()
print(f'Hitter T+1 training rows: {len(train)}')

X = train[HITTER_FEATS].values
y = train['fp_t1'].values
betas_h, r2_h = fit(X, y, HITTER_FEATS)
print(f'\n=== HITTER T+1 prediction (FP_per_pa next year) ===')
print(f'  R² = {r2_h:.4f}')
for k, v in sorted(betas_h.items(), key=lambda x: -abs(x[1])):
    print(f'  beta_{k:18s} = {v:+.5f}')

# Compare: predicting CURRENT-year FP (baseline)
y_now = train['fp_per_pa'].values
betas_curr, r2_curr = fit(X, y_now, HITTER_FEATS)
print(f'\n  Compared with current-year FP regression: R² = {r2_curr:.4f}')
print(f'  T+1 prediction R² loss vs current: {r2_curr - r2_h:.4f}')

# Validate via out-of-sample holdout (last year as test)
train2 = train[train['year'] < train['year'].max()].copy()
test = train[train['year'] == train['year'].max()].copy()
if len(test) > 50:
    X_tr, y_tr = train2[HITTER_FEATS].values, train2['fp_t1'].values
    betas_tr, _ = fit(X_tr, y_tr, HITTER_FEATS)
    X_te = np.column_stack([np.ones(len(test))] + [test[c].values for c in HITTER_FEATS])
    coef = np.array([betas_tr['_intercept']] + [betas_tr[c] for c in HITTER_FEATS])
    y_pred = X_te @ coef
    y_true = test['fp_t1'].values
    mae = np.abs(y_pred - y_true).mean()
    rmse = np.sqrt(((y_pred - y_true)**2).mean())
    print(f'\n  Holdout (year={int(test["year"].iloc[0])}, n={len(test)}): MAE={mae:.4f}, RMSE={rmse:.4f}')

# === SPs: Predict T+1 fp_per_start from year T sub-domains ===
SP_FEATS = ['SWING_MISS', 'CALLED_STRIKE', 'DAMAGE_SUPP', 'GB_TENDENCY', 'WALK_AVOID', 'velo_rating', 'age']

s_sorted = s.sort_values(['pitcher', 'year']).reset_index(drop=True)
s_sorted['fp_t1'] = s_sorted.groupby('pitcher')['fp_per_start'].shift(-1)
s_sorted['year_t1'] = s_sorted.groupby('pitcher')['year'].shift(-1)
train_s = s_sorted[(s_sorted['year_t1'] == s_sorted['year'] + 1) &
                   (s_sorted['data_tier'] == 'FULL') &
                   (s_sorted['fp_t1'].notna())].copy()
print(f'\nSP T+1 training rows: {len(train_s)}')

X_s = train_s[SP_FEATS].values
y_s = train_s['fp_t1'].values
betas_s, r2_s = fit(X_s, y_s, SP_FEATS)
print(f'\n=== SP T+1 prediction (FP_per_start next year) ===')
print(f'  R² = {r2_s:.4f}')
for k, v in sorted(betas_s.items(), key=lambda x: -abs(x[1])):
    print(f'  beta_{k:18s} = {v:+.5f}')

y_now_s = train_s['fp_per_start'].values
betas_curr_s, r2_curr_s = fit(X_s, y_now_s, SP_FEATS)
print(f'\n  Current-year SP regression: R² = {r2_curr_s:.4f}')
print(f'  T+1 R² loss vs current: {r2_curr_s - r2_s:.4f}')

# Round weights to ship-ready form
print()
print('=== Recommended T+1 model coefficients (FULL pool, all years) ===')
print('Hitters:')
print(f'  intercept = {betas_h["_intercept"]:.5f}')
for f in HITTER_FEATS:
    print(f'  beta_{f:18s} = {betas_h[f]:+.5f}')
print('SPs:')
print(f'  intercept = {betas_s["_intercept"]:.5f}')
for f in SP_FEATS:
    print(f'  beta_{f:18s} = {betas_s[f]:+.5f}')
