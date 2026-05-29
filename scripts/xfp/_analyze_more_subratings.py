"""Derive empirical weights for the next round of sub-domain decompositions."""
import pandas as pd
import numpy as np
from pathlib import Path

# Hitters
src = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\xfp_cache\hitters_multiyr_2015_2026.csv')
h = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\hitter_ratings_master.csv')

# Derive o_contact_pct from raw counts: o_contact = contact - z_contact; o_contact_pct = o_contact / o_swing
src['o_contact'] = (src['contact'] - src['z_contact']).clip(lower=0)
src['o_contact_pct'] = (src['o_contact'] / src['o_swing'].clip(lower=1)).clip(0, 1)

# Merge into master by (batter, year)
src_keep = src[['batter','year','z_contact_pct','o_contact_pct']].copy()
hm = h.drop(columns=[c for c in ['z_contact_pct'] if c in h.columns]).merge(src_keep, on=['batter','year'], how='left')


def rate_within_year(df, col, invert=False):
    out = pd.Series(np.nan, index=df.index)
    for yr, idx in df.groupby('year').groups.items():
        s = df.loc[idx, col]
        mu, sd = s.mean(), s.std()
        if sd == 0 or pd.isna(sd):
            out.loc[idx] = 50
        else:
            z = (s - mu) / sd
            if invert: z = -z
            out.loc[idx] = (50 + 10*z).clip(20, 80)
    return out


hm['r_ZContact'] = rate_within_year(hm, 'z_contact_pct')
hm['r_OContact'] = rate_within_year(hm, 'o_contact_pct')


def yoy(df, col, idkey='batter'):
    pivot = df.pivot_table(index=idkey, columns='year', values=col)
    yrs = sorted(df['year'].unique())
    rs = []
    for i in range(len(yrs)-1):
        a, b = yrs[i], yrs[i+1]
        if a not in pivot or b not in pivot: continue
        pair = pivot[[a, b]].dropna()
        if len(pair) < 30: continue
        rs.append(pair.corr().iloc[0, 1])
    return np.mean(rs) if rs else None


print('=== YoY stability of new contact splits ===')
print(f'  r_ZContact   YoY r = {yoy(hm, "r_ZContact"):.3f}')
print(f'  r_OContact   YoY r = {yoy(hm, "r_OContact"):.3f}')
print(f'  correlation(Z, O) = {hm[["r_ZContact","r_OContact"]].corr().iloc[0,1]:.3f}')
print(f'  correlation(Z, r_K) = {hm[["r_ZContact","r_K"]].corr().iloc[0,1]:.3f}')
print(f'  correlation(O, r_K) = {hm[["r_OContact","r_K"]].corr().iloc[0,1]:.3f}')

# Empirical weights for new CONTACT decomposition
# Z_CONTACT (r_ZContact), O_CONTACT (r_OContact), K_AVOID (r_K), QUALITY (r_xCON), SPRAY (r_SprayEnt)
hf = hm[hm['data_tier'] == 'FULL'].dropna(subset=['r_ZContact','r_OContact','r_K','r_xCON','r_SprayEnt']).copy()

def fit(X, y):
    X_ = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
    yhat = X_ @ beta
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return beta[1:], r2


def wts(b, names):
    t = sum(abs(b))
    return {n: abs(bi) / t for n, bi in zip(names, b)}


y_h = hf['fp_per_pa'].values

# Build sub-domain raw composites for new CONTACT (5 sub-domains)
hf['Z_CONTACT_raw']       = hf['r_ZContact']
hf['O_CONTACT_raw']       = hf['r_OContact']
hf['K_AVOID_raw']         = hf['r_K']
hf['CONTACT_QUALITY_raw'] = hf['r_xCON']
hf['SPRAY_PROFILE_raw']   = hf['r_SprayEnt']
b, r2 = fit(hf[['Z_CONTACT_raw','O_CONTACT_raw','K_AVOID_raw','CONTACT_QUALITY_raw','SPRAY_PROFILE_raw']].values, y_h)
w = wts(b, ['Z_CONTACT','O_CONTACT','K_AVOID','CONTACT_QUALITY','SPRAY_PROFILE'])
print(f'\nCONTACT with 5 sub-domains -> fp_per_pa  (R^2={r2:.4f}):')
for k, v in w.items():
    print(f'  {k:18s} = {v:.3f}')

# Item 1: RAW_POWER + EV90 vs LAUNCH (sweet spot + pull-fb only)
# These ratings already exist in master
hf2 = hf.copy()
# RAW_POWER_new = mean(r_HardHit, r_Barrel, r_EV90)
hf2['RAW_POWER_new_raw']    = hf2[['r_HardHit','r_Barrel','r_EV90']].mean(axis=1)
hf2['LAUNCH_OPTIM_new_raw'] = hf2[['r_SweetSpot','r_PullFB']].mean(axis=1)
hf2['DAMAGE_PROD_raw']      = hf2[['r_ISO','r_HRrate']].mean(axis=1)

b, r2 = fit(hf2[['RAW_POWER_new_raw','LAUNCH_OPTIM_new_raw','DAMAGE_PROD_raw']].values, y_h)
w = wts(b, ['RAW_POWER_new','LAUNCH_OPTIM_new','DAMAGE_PROD'])
print(f'\nPOWER with EV90 moved to RAW (R^2={r2:.4f}):')
for k, v in w.items():
    print(f'  {k:18s} = {v:.3f}')

# === SPs — split DAMAGE_SUPP ===
s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\sp_ratings_master.csv')
sf = s[s['data_tier'] == 'FULL'].copy()

sf['HR_SUPP_raw']      = sf[['r_HRrate','r_Barrel']].mean(axis=1)
sf['BIP_QUALITY_raw']  = sf[['r_HardHit','r_xCON']].mean(axis=1)
sf['GB_TENDENCY_raw']  = sf['r_GB']

y_s = sf['fp_per_start'].values
b, r2 = fit(sf[['HR_SUPP_raw','BIP_QUALITY_raw','GB_TENDENCY_raw']].values, y_s)
w = wts(b, ['HR_SUPP','BIP_QUALITY','GB_TENDENCY'])
print(f'\nSP MOVEMENT with DAMAGE_SUPP split into HR_SUPP + BIP_QUALITY (R^2={r2:.4f}):')
for k, v in w.items():
    print(f'  {k:18s} = {v:.3f}')

# Correlation between HR_SUPP and BIP_QUALITY
print(f'  correlation(HR_SUPP_raw, BIP_QUALITY_raw) = {sf[["HR_SUPP_raw","BIP_QUALITY_raw"]].corr().iloc[0,1]:.3f}')
