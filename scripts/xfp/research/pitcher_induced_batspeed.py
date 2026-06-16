"""SP/RP INDUCED BAT-SPEED build (#2). Pitcher analog of the hitter detector.

induced_bat_speed = mean bat speed of swings faced. Confounded by opponent
quality, so the headline metric is opponent-adjusted SUPPRESSION:
  supp = mean over faced swings of (swing_bat_speed - that batter's season baseline).
supp < 0 => pitcher makes hitters swing slower than they normally do (stuff up).

Tests: (A) stabilization (split-half by faced swings) vs outcome stabilization;
(B) change-faithfulness Δsupp vs Δ(xwOBA-allowed, K%) with orthogonality control,
split SP vs RP. All from raw parquet. 2023 bat speed is 2H-only (noted).
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import pearsonr

rng = np.random.default_rng(20260616)
ROOT = Path(__file__).resolve().parents[3]
C = ROOT / 'data' / 'research' / 'xfp_cache'
PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play','sac_bunt','catcher_interf'}
K_EVENTS = {'strikeout','strikeout_double_play'}
COLS = ['pitcher','batter','events','type','launch_speed','woba_value','woba_denom','bat_speed']

# SP set (gs>=8) per year from sp_multiyr
spm = pd.read_csv(C / 'sp_multiyr_2015_2025.csv', usecols=['pitcher','year','gs'])
SP_SET = set(zip(spm[spm['gs'] >= 8]['pitcher'], spm[spm['gs'] >= 8]['year']))

def build_year(y):
    df = pd.read_parquet(C / f'statcast_{y}.parquet', columns=COLS)
    df['year'] = y
    sw = df[df['bat_speed'].notna() & (df['bat_speed'] > 10)].copy()
    # batter baseline (>=50 swings) for opponent adjustment
    bcnt = sw.groupby('batter')['bat_speed'].transform('size')
    base = sw.groupby('batter')['bat_speed'].mean()
    sw['baseline'] = sw['batter'].map(base)
    sw['supp'] = sw['bat_speed'] - sw['baseline']
    # pitcher induced (per pitcher-season)
    ind = sw.groupby('pitcher').agg(n_fsw=('bat_speed','size'),
                                    ind_bs=('bat_speed','mean'),
                                    ind_supp=('supp','mean'))
    # pitcher outcomes
    pa = df[df['events'].isin(PA_EVENTS)]
    o = pa.groupby('pitcher').agg(n_pa=('events','size'),
                                  wd=('woba_denom', lambda s: s.fillna(0).sum()),
                                  wv=('woba_value', lambda s: s.fillna(0).sum()),
                                  k=('events', lambda s: s.isin(K_EVENTS).sum()))
    o['xwoba_allow'] = o['wv'] / o['wd']; o['k_pct'] = o['k'] / o['n_pa']
    bip = df[df['type'] == 'X']
    o['barrel_allow'] = bip.groupby('pitcher')['launch_speed'].apply(lambda s: (s >= 95).mean())
    m = ind.join(o[['n_pa','xwoba_allow','k_pct','barrel_allow']], how='inner').reset_index()
    m['year'] = y
    m['role'] = ['SP' if (p, y) in SP_SET else 'RP' for p in m['pitcher']]
    # keep per-swing supp arrays for stabilization
    return m, sw[['pitcher','supp']]

years = [2024, 2025]   # clean full-season bat speed
mats, swarrs = [], []
for y in years:
    m, s = build_year(y)
    mats.append(m); s['psn'] = s['pitcher'].astype(str) + '_' + str(y); swarrs.append(s)
MAT = pd.concat(mats, ignore_index=True)
SWALL = pd.concat(swarrs, ignore_index=True)
print(f"pitcher-seasons (2024-25): {len(MAT)}  SP={sum(MAT.role=='SP')} RP={sum(MAT.role=='RP')}")
print(f"  median faced-swings: SP={MAT[MAT.role=='SP'].n_fsw.median():.0f}  RP={MAT[MAT.role=='RP'].n_fsw.median():.0f}")

# ---- (A) stabilization: induced supp (swing grain) vs xwoba_allow (PA grain) ----
def reliability(vbp, n, n_splits=25):
    elig = {k: v for k, v in vbp.items() if len(v) >= 2*n}
    if len(elig) < 25: return np.nan
    rs = []
    for _ in range(n_splits):
        a, b = [], []
        for v in elig.values():
            idx = rng.permutation(len(v)); a.append(v[idx[:n]].mean()); b.append(v[idx[n:2*n]].mean())
        rs.append(np.corrcoef(a, b)[0, 1])
    return float(np.mean(rs))
supp_by = {k: v.values for k, v in SWALL.groupby('psn')['supp']}
print("\n(A) INDUCED-SUPP stabilization (split-half by faced swings):")
NS = [20, 30, 50, 75, 100, 150, 200, 300, 500]
print("  n faced-swings: " + ''.join(f'{n:>6}' for n in NS))
print("  induced_supp r: " + ''.join((f'{reliability(supp_by,n):>6.2f}') for n in NS))

# ---- (B) faithfulness Δsupp vs Δoutcome, split SP/RP, with orthogonality ----
def yoy(df, key, cols):
    a = df[df.year == 2024].set_index(key); b = df[df.year == 2025].set_index(key)
    common = a.index.intersection(b.index)
    d = (b.loc[common, cols] - a.loc[common, cols]); d[key] = common
    return d.reset_index(drop=True)

def resid(y, X):
    X1 = np.column_stack([np.ones(len(y))] + [X[c].values for c in X.columns])
    beta, *_ = np.linalg.lstsq(X1, y.values, rcond=None); return y.values - X1 @ beta

print("\n(B) CHANGE-FAITHFULNESS  Δind_supp vs Δoutcome (2024->2025; +=they move together)")
for role in ['SP', 'RP']:
    sub = MAT[(MAT.role == role) & (MAT.n_fsw >= (300 if role == 'SP' else 80)) & (MAT.n_pa >= (200 if role == 'SP' else 60))]
    d = yoy(sub, 'pitcher', ['ind_supp', 'ind_bs', 'xwoba_allow', 'k_pct', 'barrel_allow']).dropna()
    if len(d) < 25:
        print(f"  {role}: n={len(d)} too small"); continue
    print(f"  --- {role} (n={len(d)} pitchers w/ both yrs) ---")
    for out in ['xwoba_allow', 'k_pct', 'barrel_allow']:
        r = pearsonr(d['ind_supp'], d[out])[0]
        # orthogonality: does supp add beyond Δk_pct + Δbarrel?
        ctrl = [c for c in ['k_pct', 'barrel_allow'] if c != out]
        pr = pearsonr(resid(d['ind_supp'], d[ctrl]), resid(d[out], d[ctrl]))[0]
        print(f"    Δind_supp vs Δ{out:<13} raw r={r:+.3f}   partial(|Δ{ctrl})={pr:+.3f}")
