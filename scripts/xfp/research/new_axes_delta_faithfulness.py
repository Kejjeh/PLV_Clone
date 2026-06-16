"""Confirm the two new axes work as CHANGE signals (Δ vs baseline), the framing
/trending uses — and resolve attack-angle's optimum (is linear Δ ok, or model
distance-from-productive-band?). Δ = season(t+1) - season(t), vs ΔxwOBACON.
"""
import numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import pearsonr
C = Path('data/research/xfp_cache')

def season(y, min_sw):
    df = pd.read_parquet(C/f'statcast_{y}.parquet',
                         columns=['batter','type','launch_speed','estimated_woba_using_speedangle','bat_speed','attack_angle'])
    sw = df[df.bat_speed.notna()&(df.bat_speed>10)]
    g = sw.groupby('batter')
    t = pd.DataFrame({'bat_speed':g.bat_speed.mean(),'attack_angle':g.attack_angle.mean(),
                      'fast_swing':g.bat_speed.apply(lambda s:(s>=75).mean()),'n':g.bat_speed.size()})
    bip = df[df.type=='X']; t['xwobacon']=bip.groupby('batter').estimated_woba_using_speedangle.mean()
    return t[t.n>=min_sw]

S = {y:season(y, 150 if y<2026 else 80) for y in [2024,2025,2026]}

# population-optimal attack angle: binned mean xwOBACON across all player-seasons
allps = pd.concat([S[y] for y in S], ignore_index=True)
allps['aa_bin'] = (allps.attack_angle/2).round()*2
opt = allps.groupby('aa_bin').xwobacon.mean()
opt = opt[allps.groupby('aa_bin').size() >= 20]
aa_star = opt.idxmax()
print(f"population-optimal attack angle ~ {aa_star:.0f}deg (binned-max xwOBACON); "
      f"productive band {opt[opt>=opt.max()-0.01].index.min():.0f}-{opt[opt>=opt.max()-0.01].index.max():.0f}deg\n")

def delta(ya, yb):
    a, b = S[ya].align(S[yb], join='inner', axis=0)
    d = pd.DataFrame(index=a.index)
    for c in ['bat_speed','attack_angle','fast_swing','xwobacon']:
        d['d_'+c] = b[c]-a[c]
    d['d_aa_toward'] = (b.attack_angle-aa_star).abs() - (a.attack_angle-aa_star).abs()  # neg = moved toward optimum
    return d

print(f"{'cohort':<12}{'metric':<22}{'r(Δ,ΔxwOBACON)':>16}{'n':>6}")
for ya,yb,tag in [(2024,2025,''),(2025,2026,' (2026 partial)')]:
    d = delta(ya,yb).dropna()
    for c in ['d_bat_speed','d_attack_angle','d_fast_swing','d_aa_toward']:
        r = pearsonr(d[c], d['d_xwobacon'])[0]
        print(f"  {str(ya)+'->'+str(yb):<10}{c:<22}{r:>+16.3f}{len(d):>6}{tag if c=='d_bat_speed' else ''}")
    print()
