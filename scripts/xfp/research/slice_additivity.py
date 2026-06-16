"""Do the two winning slices (attack_angle, fast_swing%) stack ADDITIVELY on top
of bat speed, or double-count? 5-fold CV R2 predicting RoS xwOBACON @35d cutoff,
pooled 2024+25. Models nested: box+prior -> +bat_speed -> +attack_angle -> +fast_swing.
"""
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import cross_val_score
from scipy.stats import pearsonr

C = Path('data/research/xfp_cache')
PA = {'single','double','triple','home_run','strikeout','strikeout_double_play','walk','intent_walk',
      'hit_by_pitch','field_out','force_out','grounded_into_double_play','double_play','triple_play',
      'fielders_choice','fielders_choice_out','field_error','sac_fly','sac_fly_double_play','sac_bunt','catcher_interf'}
K = {'strikeout','strikeout_double_play'}

def prior_woba(y):
    df = pd.read_parquet(C/f'statcast_{y}.parquet', columns=['batter','events','woba_value','woba_denom'])
    pa = df[df.events.isin(PA)]; g = pa.groupby('batter').agg(wd=('woba_denom',lambda s:s.fillna(0).sum()),
        wv=('woba_value',lambda s:s.fillna(0).sum()), n=('events','size'))
    return (g.wv/g.wd)[g.n>=100]
PRIOR={2024:prior_woba(2023),2025:prior_woba(2024)}

def feats(y, cd=35):
    df = pd.read_parquet(C/f'statcast_{y}.parquet', columns=['game_date','batter','bat_speed','attack_angle',
        'events','type','launch_speed','woba_value','woba_denom','estimated_woba_using_speedangle'])
    df.game_date = pd.to_datetime(df.game_date); start = df.game_date.min(); cut = start + pd.Timedelta(days=cd)
    sw = df[df.bat_speed.notna()&(df.bat_speed>10)]; e_sw = sw[(sw.game_date>=start)&(sw.game_date<cut)]
    g = e_sw.groupby('batter')
    f = pd.DataFrame({'bat_speed':g.bat_speed.mean(),'attack_angle':g.attack_angle.mean(),
                      'fast_swing':g.bat_speed.apply(lambda s:(s>=75).mean()),'n_sw':g.bat_speed.size()})
    ed = df[(df.game_date>=start)&(df.game_date<cut)]; epa = ed[ed.events.isin(PA)]
    f['e_woba']=epa.groupby('batter').apply(lambda x:x.woba_value.fillna(0).sum()/max(x.woba_denom.fillna(0).sum(),1))
    f['e_k']=epa.groupby('batter').apply(lambda x:x.events.isin(K).mean()); f['e_pa']=epa.groupby('batter').size()
    eb=ed[ed.type=='X']; f['e_hardhit']=(eb.launch_speed>=95).groupby(eb.batter).mean()
    rb=df[df.game_date>=cut]; f['ros_xwobacon']=rb[rb.type=='X'].groupby('batter').estimated_woba_using_speedangle.mean()
    f['ros_pa']=rb[rb.events.isin(PA)].groupby('batter').size(); f['prior_woba']=PRIOR[y]
    return f[(f.n_sw>=20)&(f.e_pa>=15)&(f.ros_pa>=100)]

D = pd.concat([feats(y) for y in [2024,2025]], ignore_index=True).dropna(
    subset=['bat_speed','attack_angle','fast_swing','e_woba','e_hardhit','e_k','prior_woba','ros_xwobacon'])
y = D['ros_xwobacon'].values
def cvr2(cols):
    m = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    return cross_val_score(m, D[cols].values, y, cv=5, scoring='r2').mean()

base = ['e_woba','e_hardhit','e_k','prior_woba']
print(f"n={len(D)}  5-fold CV R2 predicting RoS xwOBACON @35d\n")
steps = [('box+prior', base),
         ('+ bat_speed', base+['bat_speed']),
         ('+ attack_angle', base+['bat_speed','attack_angle']),
         ('+ fast_swing (3-axis)', base+['bat_speed','attack_angle','fast_swing'])]
prev=None
for name, cols in steps:
    r2=cvr2(cols); d=f"  (Δ {r2-prev:+.4f})" if prev is not None else ""
    print(f"  {name:<24} CV R2={r2:+.4f}{d}"); prev=r2

# are the two winners redundant with each other? partial of each given the other + bat_speed + box + prior
def resid(v,X):
    X1=np.column_stack([np.ones(len(v))]+[X[c].values for c in X.columns]); b,*_=np.linalg.lstsq(X1,v.values,rcond=None); return v.values-X1@b
print("\n  cross-redundancy (partial r vs RoS, controlling for the OTHER winner + bat_speed + box + prior):")
for c, other in [('attack_angle','fast_swing'),('fast_swing','attack_angle')]:
    ctrl=base+['bat_speed',other]; pr=pearsonr(resid(D[c],D[ctrl]),resid(D['ros_xwobacon'],D[ctrl]))[0]
    print(f"    {c:<14} partial r = {pr:+.3f}")
