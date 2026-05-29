"""Test new sub-domain candidates empirically."""
import pandas as pd
import numpy as np

src_h = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\xfp_cache\hitters_multiyr_2015_2026.csv')
src_s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\xfp_cache\sp_multiyr_2015_2025.csv')
h = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\hitter_ratings_master.csv')
s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\sp_ratings_master.csv')


def rate_within_year(df, col, invert=False):
    out = pd.Series(np.nan, index=df.index)
    for yr, idx in df.groupby('year').groups.items():
        s = df.loc[idx, col]
        mu, sd = s.mean(), s.std()
        if sd == 0 or pd.isna(sd): out.loc[idx] = 50
        else:
            z = (s - mu) / sd
            if invert: z = -z
            out.loc[idx] = (50 + 10*z).clip(20, 80)
    return out


def fit(X, y):
    X_ = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
    yhat = X_ @ beta
    r2 = 1 - ((y-yhat)**2).sum() / ((y-y.mean())**2).sum()
    return beta[1:], r2


def yoy(df, col, idkey):
    pivot = df.pivot_table(index=idkey, columns='year', values=col)
    yrs = sorted(df['year'].unique())
    rs = []
    for i in range(len(yrs)-1):
        a, b = yrs[i], yrs[i+1]
        if a not in pivot or b not in pivot: continue
        pair = pivot[[a,b]].dropna()
        if len(pair) < 30: continue
        rs.append(pair.corr().iloc[0,1])
    return np.mean(rs) if rs else None


# === HITTER ideas ===

# Add new derived stats
src_h['gap_xbh_per_pa'] = (src_h['b2'] + src_h['b3']) / src_h['pa'].clip(lower=1)
src_h['pitches_per_pa'] = src_h['pitches'] / src_h['pa'].clip(lower=1)

# Merge into master
join_h = src_h[['batter','year','gap_xbh_per_pa','pitches_per_pa']].copy()
hm = h.merge(join_h, on=['batter','year'], how='left')
hm['r_GapPower']    = rate_within_year(hm, 'gap_xbh_per_pa')
hm['r_PitchesPerPA']= rate_within_year(hm, 'pitches_per_pa')

print('=== HITTER new sub-rating candidates ===')
print(f'  r_GapPower (2B+3B / PA)      YoY r = {yoy(hm, "r_GapPower", "batter"):.3f}')
print(f'  r_PitchesPerPA               YoY r = {yoy(hm, "r_PitchesPerPA", "batter"):.3f}')
print(f'  corr(r_GapPower, r_ISO)         = {hm[["r_GapPower","r_ISO"]].corr().iloc[0,1]:.3f}')
print(f'  corr(r_GapPower, r_HRrate)      = {hm[["r_GapPower","r_HRrate"]].corr().iloc[0,1]:.3f}')
print(f'  corr(r_PitchesPerPA, r_BB)      = {hm[["r_PitchesPerPA","r_BB"]].corr().iloc[0,1]:.3f}')
print(f'  corr(r_PitchesPerPA, r_Chase)   = {hm[["r_PitchesPerPA","r_Chase"]].corr().iloc[0,1]:.3f}')

# Test GAP_POWER as separate sub-domain under POWER
hf = hm[hm['data_tier']=='FULL'].dropna(subset=['r_GapPower','r_PitchesPerPA','r_BB','r_Chase','r_HBP','r_ZSwing','r_HRrate','r_ISO','r_Barrel','r_HardHit','r_EV90','r_SweetSpot','r_PullFB']).copy()
y_h = hf['fp_per_pa'].values

# POWER with GAP_POWER added as 4th sub-domain (split DAMAGE_PROD into Gap vs HR)
hf['RAW_POWER_raw']    = hf[['r_HardHit','r_Barrel','r_EV90']].mean(axis=1)
hf['LAUNCH_OPTIM_raw'] = hf[['r_SweetSpot','r_PullFB']].mean(axis=1)
hf['GAP_PROD_raw']     = hf['r_GapPower']
hf['HR_PROD_raw']      = hf['r_HRrate']
hf['ISO_raw']          = hf['r_ISO']  # to test inclusion separately

print()
print('--- Test 1: POWER with Gap separated from HR (vs current Damage = mean(ISO, HR)) ---')
b, r2 = fit(hf[['RAW_POWER_raw','LAUNCH_OPTIM_raw','GAP_PROD_raw','HR_PROD_raw','ISO_raw']].values, y_h)
print(f'  betas: RAW={b[0]:.4f}  LAUNCH={b[1]:.4f}  GAP_PROD={b[2]:.4f}  HR_PROD={b[3]:.4f}  ISO={b[4]:.4f}')
total = sum(abs(bi) for bi in b)
print(f'  weights: RAW={abs(b[0])/total:.3f}  LAUNCH={abs(b[1])/total:.3f}  GAP_PROD={abs(b[2])/total:.3f}  HR_PROD={abs(b[3])/total:.3f}  ISO={abs(b[4])/total:.3f}')
print(f'  R^2 = {r2:.4f}')

# Test PITCHES_PER_PA as candidate sub-domain under DISCIPLINE
hf['PATIENCE_raw']    = hf[['r_BB','r_Chase','r_HBP']].mean(axis=1)
hf['AGGRESSION_raw']  = hf['r_ZSwing']
hf['PITCH_WORK_raw']  = hf['r_PitchesPerPA']

print()
print('--- Test 2: DISCIPLINE with PITCH_WORK added ---')
b, r2 = fit(hf[['PATIENCE_raw','AGGRESSION_raw','PITCH_WORK_raw']].values, y_h)
print(f'  betas: PATIENCE={b[0]:.4f}  AGGRESSION={b[1]:.4f}  PITCH_WORK={b[2]:.4f}')
total = sum(abs(bi) for bi in b)
print(f'  weights: PATIENCE={abs(b[0])/total:.3f}  AGGRESSION={abs(b[1])/total:.3f}  PITCH_WORK={abs(b[2])/total:.3f}')
print(f'  R^2 = {r2:.4f}')

# === SP ideas ===

# Add new derived stats
src_s['zone_pct'] = src_s['in_zone'] / src_s['pitches'].clip(lower=1)
join_s = src_s[['pitcher','year','zone_pct']].copy()
sm = s.merge(join_s, on=['pitcher','year'], how='left')
sm['r_ZonePct'] = rate_within_year(sm, 'zone_pct')

# Try arsenal_entropy via career panel
try:
    panel = pd.read_parquet(r'c:\Users\Joshua\plv_clone\data\research\sp_archetype_career_panel.parquet')
    if 'arsenal_entropy' in panel.columns:
        ae = panel[['pitcher','year','arsenal_entropy']].dropna()
        sm = sm.merge(ae, on=['pitcher','year'], how='left')
        sm['r_Arsenal'] = rate_within_year(sm, 'arsenal_entropy')
        print()
        print(f'arsenal_entropy: in career panel, coverage = {sm["arsenal_entropy"].notna().mean()*100:.0f}% of SP-years')
except Exception as e:
    print(f'arsenal_entropy: error - {e}')

print()
print('=== SP new sub-rating candidates ===')
print(f'  r_ZonePct (in_zone / pitches)   YoY r = {yoy(sm, "r_ZonePct", "pitcher"):.3f}')
if 'r_Arsenal' in sm.columns:
    print(f'  r_Arsenal (pitch entropy)       YoY r = {yoy(sm, "r_Arsenal", "pitcher"):.3f}')
print(f'  corr(r_ZonePct, r_BB)              = {sm[["r_ZonePct","r_BB"]].corr().iloc[0,1]:.3f}')
print(f'  corr(r_ZonePct, r_CSW)             = {sm[["r_ZonePct","r_CSW"]].corr().iloc[0,1]:.3f}')

# Test ZONE_PCT as candidate sub-domain under CONTROL (4th component) or STUFF
sf = sm[sm['data_tier']=='FULL'].dropna(subset=['r_ZonePct','r_SwStr','r_K','r_CSW','r_BB']).copy()
y_s = sf['fp_per_start'].values

print()
print('--- Test 3: ZONE_PCT in CONTROL (currently just WALK_AVOID = r_BB) ---')
b, r2 = fit(sf[['r_BB','r_ZonePct']].values, y_s)
print(f'  betas: WALK_AVOID={b[0]:.4f}  ZONE_PCT={b[1]:.4f}')
total = sum(abs(bi) for bi in b)
print(f'  weights: WALK_AVOID={abs(b[0])/total:.3f}  ZONE_PCT={abs(b[1])/total:.3f}')
print(f'  R^2 = {r2:.4f}')

print()
print('--- Test 4: STUFF + ZONE_PCT (test if zone-throwing predicts FP beyond SwM/CSW) ---')
b, r2 = fit(sf[['r_SwStr','r_K','r_CSW','r_ZonePct']].values, y_s)
print(f'  betas: r_SwStr={b[0]:.4f}  r_K={b[1]:.4f}  r_CSW={b[2]:.4f}  ZONE_PCT={b[3]:.4f}')
total = sum(abs(bi) for bi in b)
print(f'  weights: r_SwStr={abs(b[0])/total:.3f}  r_K={abs(b[1])/total:.3f}  r_CSW={abs(b[2])/total:.3f}  ZONE_PCT={abs(b[3])/total:.3f}')
print(f'  R^2 = {r2:.4f}')

if 'r_Arsenal' in sm.columns:
    sf2 = sm[sm['data_tier']=='FULL'].dropna(subset=['r_Arsenal','r_SwStr','r_K','r_CSW']).copy()
    if len(sf2) > 100:
        print()
        print(f'--- Test 5: STUFF + ARSENAL_DEPTH (n={len(sf2)}) ---')
        b, r2 = fit(sf2[['r_SwStr','r_K','r_CSW','r_Arsenal']].values, sf2['fp_per_start'].values)
        print(f'  betas: r_SwStr={b[0]:.4f}  r_K={b[1]:.4f}  r_CSW={b[2]:.4f}  ARSENAL={b[3]:.4f}')
        total = sum(abs(bi) for bi in b)
        print(f'  weights: r_SwStr={abs(b[0])/total:.3f}  r_K={abs(b[1])/total:.3f}  r_CSW={abs(b[2])/total:.3f}  ARSENAL={abs(b[3])/total:.3f}')
        print(f'  R^2 = {r2:.4f}')
