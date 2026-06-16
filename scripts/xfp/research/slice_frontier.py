"""SLICE FRONTIER SWEEP — which bat-tracking slice best identifies breakout/decline?

Each candidate scored on the TWO axes that matter (everything else is a fishing
expedition):
  (A) STABILIZATION — split-half n for r>=0.70 (does it keep the early-season edge?)
  (B) INCREMENTAL EARLY-SEASON RoS LIFT — partial r with RoS xwOBACON controlling
      for [early bat_speed + early box-score + prior] (does it beat PLAIN bat speed?)
  + 2-cohort (2024/25) sign consistency; ~11 candidates => Bonferroni bar p<0.0045.

Slices: 1 premium-velo bat speed | 2 swing-grain contact (squared-up, hardhit/swing)
        | 3 intent/top-end (p90 bat speed, fast-swing rate) | 4 contact-depth timing
        | 5 swing-path (attack angle mean, consistency, ideal rate).
All from raw parquet, exact game_date split. DISPLAY/CONTEXT only.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import pearsonr

rng = np.random.default_rng(20260616)
C = Path('data/research/xfp_cache')
PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play','sac_bunt','catcher_interf'}
K_EVENTS = {'strikeout','strikeout_double_play'}
COLS = ['game_date','batter','pitch_type','release_speed','type','launch_speed','woba_value',
        'woba_denom','estimated_woba_using_speedangle','bat_speed','attack_angle',
        'intercept_ball_minus_batter_pos_y_inches','events']

def load(y):
    df = pd.read_parquet(C / f'statcast_{y}.parquet', columns=COLS)
    df['game_date'] = pd.to_datetime(df['game_date'])
    sw = df[df['bat_speed'].notna() & (df['bat_speed'] > 10)].copy()
    sw['hi_velo'] = sw['release_speed'] >= 95
    evmax = 1.23 * sw['bat_speed'] + 0.23 * sw['release_speed']
    sw['su'] = (sw['launch_speed'].notna() & ((sw['launch_speed'] / evmax) >= 0.80)).astype(float)
    sw['hh_sw'] = (sw['launch_speed'] >= 95).fillna(False).astype(float)
    sw['fast'] = (sw['bat_speed'] >= 75).astype(float)
    sw['iy'] = sw['intercept_ball_minus_batter_pos_y_inches']
    sw['aa'] = sw['attack_angle']
    sw['ideal'] = ((sw['aa'] >= 5) & (sw['aa'] <= 20)).astype(float)
    return df, sw

DAT = {y: load(y) for y in [2024, 2025]}

# ---------------- (A) STABILIZATION ----------------
# metric -> (column, aggregator, swing-subset filter)
MEAN = lambda a: a.mean()
P90 = lambda a: np.percentile(a, 90)
STD = lambda a: a.std()
STAB = {
    'bat_speed (ref)':       ('bat_speed', MEAN, None),
    'bs_hivelo (slice1)':    ('bat_speed', MEAN, 'hi_velo'),
    'squared_up/sw (slice2)':('su', MEAN, None),
    'hardhit/sw (slice2)':   ('hh_sw', MEAN, None),
    'bs_p90 (slice3)':       ('bat_speed', P90, None),
    'fast_swing% (slice3)':  ('fast', MEAN, None),
    'intercept_y (slice4)':  ('iy', MEAN, None),
    'attack_angle (slice5)': ('aa', MEAN, None),
    'attack_angle_sd(sl5)':  ('aa', STD, None),
    'ideal_aa% (slice5)':    ('ideal', MEAN, None),
}
def arrays(col, filt):
    out = {}
    for y in [2024, 2025]:
        sw = DAT[y][1]
        s = sw[sw[filt]] if filt else sw
        for bid, v in s.groupby('batter')[col]:
            out[f'{bid}_{y}'] = v.dropna().values
    return out
def reliability(vbp, n, aggfn, n_splits=20):
    elig = {k: v for k, v in vbp.items() if len(v) >= 2 * n}
    if len(elig) < 25: return np.nan
    rs = []
    for _ in range(n_splits):
        a, b = [], []
        for v in elig.values():
            idx = rng.permutation(len(v)); a.append(aggfn(v[idx[:n]])); b.append(aggfn(v[idx[n:2*n]]))
        rs.append(np.corrcoef(a, b)[0, 1])
    return float(np.mean(rs))
NS = [20, 30, 50, 75, 100, 150, 200, 300]
print("(A) STABILIZATION — split-half r by # swings (pooled 2024+25)")
print(f"  {'metric':<24}" + ''.join(f'{n:>6}' for n in NS) + '   stab@0.70')
stab_pt = {}
for label, (col, agg, filt) in STAB.items():
    vbp = arrays(col, filt)
    row = [reliability(vbp, n, agg) for n in NS]
    pt = next((NS[i] for i, r in enumerate(row) if not np.isnan(r) and r >= 0.70), None)
    stab_pt[label] = pt
    print(f"  {label:<24}" + ''.join(('  n/a ' if np.isnan(r) else f'{r:>6.2f}') for r in row)
          + f"   {('>='+str(pt)) if pt else '>300'}")

# ---------------- (B) INCREMENTAL EARLY-SEASON RoS LIFT ----------------
def prior_woba(y):
    df = pd.read_parquet(C / f'statcast_{y}.parquet', columns=['batter','events','woba_value','woba_denom'])
    pa = df[df['events'].isin(PA_EVENTS)]
    g = pa.groupby('batter').agg(wd=('woba_denom', lambda s: s.fillna(0).sum()),
                                 wv=('woba_value', lambda s: s.fillna(0).sum()), n=('events','size'))
    return (g['wv'] / g['wd'])[g['n'] >= 100]
PRIOR = {2024: prior_woba(2023), 2025: prior_woba(2024)}

def win_feats(y, cut_days):
    df, sw = DAT[y]; start = df['game_date'].min(); cut = start + pd.Timedelta(days=cut_days)
    e_sw = sw[(sw['game_date'] >= start) & (sw['game_date'] < cut)]
    g = e_sw.groupby('batter')
    f = pd.DataFrame({
        'bat_speed': g['bat_speed'].mean(),
        'bs_hivelo': e_sw[e_sw['hi_velo']].groupby('batter')['bat_speed'].mean(),
        'squared_up': g['su'].mean(), 'hardhit_sw': g['hh_sw'].mean(),
        'bs_p90': g['bat_speed'].quantile(0.90), 'fast_swing': g['fast'].mean(),
        'intercept_y': g['iy'].mean(), 'attack_angle': g['aa'].mean(),
        'attack_angle_sd': g['aa'].std(), 'ideal_aa': g['ideal'].mean(),
        'n_sw': g['bat_speed'].size(),
    })
    ed = df[(df['game_date'] >= start) & (df['game_date'] < cut)]
    epa = ed[ed['events'].isin(PA_EVENTS)]
    f['e_woba'] = epa.groupby('batter').apply(lambda x: x['woba_value'].fillna(0).sum() / max(x['woba_denom'].fillna(0).sum(), 1))
    f['e_k'] = epa.groupby('batter').apply(lambda x: x['events'].isin(K_EVENTS).mean())
    f['e_pa'] = epa.groupby('batter').size()
    ebip = ed[ed['type'] == 'X']
    f['e_hardhit'] = (ebip['launch_speed'] >= 95).groupby(ebip['batter']).mean()
    # RoS outcome
    rd = df[df['game_date'] >= cut]; rbip = rd[rd['type'] == 'X']
    f['ros_xwobacon'] = rbip.groupby('batter')['estimated_woba_using_speedangle'].mean()
    f['ros_pa'] = rd[rd['events'].isin(PA_EVENTS)].groupby('batter').size()
    f['prior_woba'] = PRIOR[y]
    return f[(f['n_sw'] >= 20) & (f['e_pa'] >= 15) & (f['ros_pa'] >= 100)]

def resid(yv, X):
    X1 = np.column_stack([np.ones(len(yv))] + [X[c].values for c in X.columns])
    beta, *_ = np.linalg.lstsq(X1, yv.values, rcond=None); return yv.values - X1 @ beta

CANDS = ['bat_speed','bs_hivelo','squared_up','hardhit_sw','bs_p90','fast_swing',
         'intercept_y','attack_angle','attack_angle_sd','ideal_aa']
CTRL = ['e_woba','e_hardhit','e_k','prior_woba']      # + early bat_speed for slices
for cd in [21, 35]:
    pooled = pd.concat([win_feats(y, cd).assign(yr=y) for y in [2024, 2025]], ignore_index=True)
    print(f"\n(B) INCREMENTAL RoS-xwOBACON LIFT @ cutoff {cd}d  (n={len(pooled)} pooled)")
    print(f"  {'candidate':<18}{'raw r':>8}{'partial*':>10}{'per-yr':>8}   (*ctrl: box+prior"
          f"{' (+bat_speed for slices)' if True else ''})")
    for c in CANDS:
        ctrl = CTRL + ([] if c == 'bat_speed' else ['bat_speed'])
        sub = pooled.dropna(subset=[c, 'ros_xwobacon'] + ctrl)
        if len(sub) < 40:
            print(f"  {c:<18}{'(n<40)':>8}"); continue
        raw = pearsonr(sub[c], sub['ros_xwobacon'])[0]
        pr = pearsonr(resid(sub[c], sub[ctrl]), resid(sub['ros_xwobacon'], sub[ctrl]))[0]
        signs = []
        for y in [2024, 2025]:
            sy = win_feats(y, cd).dropna(subset=[c, 'ros_xwobacon'] + ctrl)
            if len(sy) > 25:
                signs.append('+' if pearsonr(resid(sy[c], sy[ctrl]), resid(sy['ros_xwobacon'], sy[ctrl]))[0] > 0 else '-')
        tag = f" stab{stab_pt.get([k for k in stab_pt if k.startswith(c.split('_')[0])][0] if False else '',None)}"
        print(f"  {c:<18}{raw:>+8.3f}{pr:>+10.3f}{''.join(signs):>8}")
