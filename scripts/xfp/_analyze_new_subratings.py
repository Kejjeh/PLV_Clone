"""One-off analysis: derive empirical weights for the new sub-domain additions."""
import pandas as pd
import numpy as np
from pathlib import Path

src_h = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\xfp_cache\hitters_multiyr_2015_2026.csv')
h = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\hitter_ratings_master.csv')
src_h_keep = src_h[['batter','year','sweet_spot_pct','ev90','pull_fb_pct',
                    'pull_pct','cent_pct','oppo_pct','hbp_pct']].copy()
# Master CSV stores these as percentage form (e.g., 7.2 not 0.072); drop to avoid collision
master_drop = [c for c in ['pull_fb_pct','hbp_pct','pull_pct','cent_pct','oppo_pct','sweet_spot_pct','ev90'] if c in h.columns]
h_clean = h.drop(columns=master_drop)
hm = h_clean.merge(src_h_keep, on=['batter','year'], how='left')


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


def spray_entropy(row):
    pulls = [row.get('pull_pct'), row.get('cent_pct'), row.get('oppo_pct')]
    pulls = [p for p in pulls if pd.notna(p) and p > 0]
    if not pulls: return np.nan
    s = sum(pulls)
    if s == 0: return np.nan
    pp = [p/s for p in pulls]
    return -sum(p * np.log(p) for p in pp)


hm['spray_entropy'] = hm.apply(spray_entropy, axis=1)
hm['r_SweetSpot'] = rate_within_year(hm, 'sweet_spot_pct')
hm['r_EV90']      = rate_within_year(hm, 'ev90')
hm['r_PullFB_new']= rate_within_year(hm, 'pull_fb_pct')
hm['r_SprayEnt']  = rate_within_year(hm, 'spray_entropy')
hm['r_HBP']       = rate_within_year(hm, 'hbp_pct')


def yoy(df, col, idkey=None):
    if idkey is None:
        idkey = 'batter' if 'batter' in df.columns else 'pitcher'
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


print('=== YoY stability of NEW hitter sub-ratings ===')
for c in ['r_SweetSpot','r_EV90','r_PullFB_new','r_SprayEnt','r_HBP']:
    y = yoy(hm, c)
    print(f'  {c:14s} YoY r = {y:.3f}' if y else f'  {c:14s} no pairs')


def fit(X, y):
    X_ = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
    yhat = X_ @ beta
    r2 = 1 - ((y-yhat)**2).sum() / ((y-y.mean())**2).sum()
    return beta[1:], r2


def w(b):
    t = sum(abs(b))
    return [abs(bi)/t for bi in b]


hf = hm[hm['data_tier']=='FULL'].copy()
keep_cols = ['r_HardHit','r_Barrel','r_SweetSpot','r_EV90','r_PullFB_new','r_ISO','r_HRrate',
             'r_Contact','r_K','r_xCON','r_SprayEnt','r_BB','r_Chase','r_HBP','r_ZSwing']
hf2 = hf.dropna(subset=keep_cols).copy()
print(f'\nFULL hitter rows after dropna on new sub-ratings: {len(hf2)}')

y_h = hf2['fp_per_pa'].values

hf2['RAW_POWER_raw']      = hf2[['r_HardHit','r_Barrel']].mean(axis=1)
hf2['LAUNCH_OPTIM_raw']   = hf2[['r_SweetSpot','r_EV90','r_PullFB_new']].mean(axis=1)
hf2['DAMAGE_PROD_raw']    = hf2[['r_ISO','r_HRrate']].mean(axis=1)
hf2['BAT_TO_BALL_raw']    = hf2[['r_Contact','r_K']].mean(axis=1)
hf2['CONTACT_QUALITY_raw']= hf2['r_xCON']
hf2['SPRAY_PROFILE_raw']  = hf2['r_SprayEnt']
hf2['PATIENCE_raw']       = hf2[['r_BB','r_Chase','r_HBP']].mean(axis=1)
hf2['AGGRESSION_raw']     = hf2['r_ZSwing']

b, r2 = fit(hf2[['RAW_POWER_raw','LAUNCH_OPTIM_raw','DAMAGE_PROD_raw']].values, y_h)
W = w(b); print(f'\nPOWER sub-weights: RAW={W[0]:.2f}  LAUNCH={W[1]:.2f}  PROD={W[2]:.2f}  (sub-R^2={r2:.3f})')

b, r2 = fit(hf2[['BAT_TO_BALL_raw','CONTACT_QUALITY_raw','SPRAY_PROFILE_raw']].values, y_h)
W = w(b); print(f'CONTACT sub-weights: B2B={W[0]:.2f}  QUALITY={W[1]:.2f}  SPRAY={W[2]:.2f}  (sub-R^2={r2:.3f})')

b, r2 = fit(hf2[['PATIENCE_raw','AGGRESSION_raw']].values, y_h)
W = w(b); print(f'DISCIPLINE sub-weights (HBP in PATIENCE): PATIENCE={W[0]:.2f}  AGGRESSION={W[1]:.2f}  (sub-R^2={r2:.3f})')

# Overall — refit with new compositions
hf2['CONTACT_new']    = hf2[['r_Contact','r_K','r_xCON','r_SprayEnt']].mean(axis=1)
hf2['POWER_new']      = hf2[['r_HardHit','r_Barrel','r_SweetSpot','r_EV90','r_PullFB_new','r_ISO','r_HRrate']].mean(axis=1)
hf2['DISCIPLINE_new'] = hf2[['r_BB','r_Chase','r_HBP','r_ZSwing']].mean(axis=1)
b, r2 = fit(hf2[['CONTACT_new','POWER_new','DISCIPLINE_new']].values, y_h)
W = w(b)
print(f'\nNEW OVERALL weights: C={W[0]:.3f}  P={W[1]:.3f}  D={W[2]:.3f}  R^2={r2:.4f}')

# --- SPs ---
print()
print('='*60)
src_s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\xfp_cache\sp_multiyr_2015_2025.csv')
s = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\research\sp_ratings_master.csv')
src_s_keep = src_s[['pitcher','year','avg_pfxz']].copy()
sm = s.merge(src_s_keep, on=['pitcher','year'], how='left')
sm['r_PitchShape'] = rate_within_year(sm, 'avg_pfxz')
sf = sm[sm['data_tier']=='FULL'].dropna(subset=['r_PitchShape','r_SwStr','r_K','r_CSW']).copy()
print(f'FULL SP rows with pitch shape: {len(sf)}')

y_s = sf['fp_per_start'].values
b, r2 = fit(sf[['r_SwStr','r_K','r_CSW','r_PitchShape']].values, y_s)
print(f'STUFF + PITCH_SHAPE betas: {[round(bb, 4) for bb in b]}')
print(f'  (r_SwStr, r_K, r_CSW, r_PitchShape)   R^2={r2:.3f}')

print(f'\nYoY r_PitchShape stability: {yoy(sm, "r_PitchShape"):.3f}')

# Check arsenal entropy availability
arsenal_path = Path(r'c:\Users\Joshua\plv_clone\data\research\sp_archetype_career_panel.parquet')
if arsenal_path.exists():
    panel = pd.read_parquet(arsenal_path)
    if 'arsenal_entropy' in panel.columns:
        print(f'\narsenal_entropy in career_panel: yes')
        print(f'  coverage: {panel["arsenal_entropy"].notna().mean()*100:.0f}% overall')
        print(f'  by year:')
        for yr, g in panel.groupby('year'):
            n = g["arsenal_entropy"].notna().sum()
            print(f'    {yr}: {n}/{len(g)} ({n/len(g)*100:.0f}%)')
        # Merge and fit
        ae = panel[['pitcher','year','arsenal_entropy']].copy()
        sm2 = sf.merge(ae, on=['pitcher','year'], how='left')
        sm2['r_Arsenal'] = rate_within_year(sm2, 'arsenal_entropy')
        sf2 = sm2.dropna(subset=['r_Arsenal']).copy()
        print(f'\nFULL SP rows with arsenal_entropy: {len(sf2)}')
        if len(sf2) > 100:
            b, r2 = fit(sf2[['r_SwStr','r_K','r_CSW','r_PitchShape','r_Arsenal']].values,
                        sf2['fp_per_start'].values)
            print(f'  betas: {[round(bb, 4) for bb in b]}')
            print(f'  R^2: {r2:.3f}')
            print(f'  arsenal_entropy YoY r: {yoy(sm2, "r_Arsenal"):.3f}')
