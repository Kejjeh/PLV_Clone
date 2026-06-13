"""
SP in-season STUFF-DECAY -> RoS FP decline backtest (leakage-safe).

Signals (velo + whiff/K + Stuff+ slope ONLY; contact/damage/age out of scope):
  As-of each (pitcher, split_day) using cumulative `_to` vs recent `_last21`
  and vs prior-year final baseline (sp_multiyr.csv).

Targets:
  (a) ros_fp_per_start                         (RoS level)
  (b) decline = ros_fp_per_start - fp_per_start_to   (RoS minus to-date)
  (c) binary material_decline = decline < -2.0

Method: player-clustered GroupKFold (no pitcher in train+test),
  partial r controlling for base (fp_per_start_to) [Rule 9],
  AUC for binary, cluster bootstrap CIs, convergence-curve leakage check.
"""
import numpy as np, pandas as pd
from scipy import stats
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

np.random.seed(13)
PANEL = 'data/research/xfp_cache/rolling_pitchers_2018_2026.csv'
MULTI = 'data/research/xfp_cache/sp_multiyr.csv'

df = pd.read_csv(PANEL)
m = pd.read_csv(MULTI)

# prior-year final baselines per pitcher: velo, swstr, k%, extension
m_prev = m[['pitcher','year','avg_velo','swstr_pct','k_pct','bb_pct','c_plus_swstr','avg_ext']].copy()
m_prev['year'] = m_prev['year'] + 1  # join as prior year onto current
m_prev = m_prev.rename(columns={
    'avg_velo':'py_velo','swstr_pct':'py_swstr','k_pct':'py_k','bb_pct':'py_bb',
    'c_plus_swstr':'py_csw','avg_ext':'py_ext'})
df = df.merge(m_prev, on=['pitcher','year'], how='left')

# --- engineer leakage-safe signals (all from as-of-split data only) ---
# Recent-window vs season-to-date deltas (decay = negative is bad)
df['d_velo_recent']  = df['avg_velo_last21']  - df['avg_velo_to']
df['d_swstr_recent'] = df['swstr_pct_last21'] - df['swstr_pct_to']
df['d_csw_recent']   = df['c_plus_swstr_last21'] - df['c_plus_swstr_to']
df['d_k_recent']     = df['k_pct_last21']     - df['k_pct_to']
df['d_fp_recent']    = df['fp_per_start_last21'] - df['fp_per_start_to']

# within-season velo z (recent vs to-date, scaled by cross-pop sd of to-date)
for col,z in [('avg_velo_to','velo_z_pop'),('swstr_pct_to','swstr_z_pop'),('k_pct_to','k_z_pop')]:
    df[z] = (df[col]-df[col].mean())/df[col].std()

# Prior-year deltas (season-to-date vs last year final) — true YoY decay
df['d_velo_yoy']  = df['avg_velo_to']  - df['py_velo']
df['d_swstr_yoy'] = df['swstr_pct_to'] - df['py_swstr']
df['d_k_yoy']     = df['k_pct_to']     - df['py_k']
df['d_csw_yoy']   = df['c_plus_swstr_to'] - df['py_csw']
# recent-window vs prior-year (sharpest early decay signal)
df['d_velo_recent_yoy']  = df['avg_velo_last21']  - df['py_velo']
df['d_swstr_recent_yoy'] = df['swstr_pct_last21'] - df['py_swstr']
df['d_k_recent_yoy']     = df['k_pct_last21']     - df['py_k']

# Level signals (low recent = decline risk)
df['velo_recent']  = df['avg_velo_last21']
df['swstr_recent'] = df['swstr_pct_last21']
df['k_recent']     = df['k_pct_last21']

SIGNALS = [
    'd_velo_recent','d_swstr_recent','d_csw_recent','d_k_recent',
    'd_velo_yoy','d_swstr_yoy','d_k_yoy','d_csw_yoy',
    'd_velo_recent_yoy','d_swstr_recent_yoy','d_k_recent_yoy',
    'velo_recent','swstr_recent','k_recent',
    'velo_z_pop','swstr_z_pop','k_z_pop',
    'd_fp_recent',  # recent-FP-vs-todate: a non-stuff control benchmark
]
SIGNAL_DESC = {
 'd_velo_recent':'FB velo L21 vs season-to-date',
 'd_swstr_recent':'SwStr% L21 vs to-date',
 'd_csw_recent':'CSW% L21 vs to-date',
 'd_k_recent':'K% L21 vs to-date',
 'd_velo_yoy':'FB velo to-date vs prior-yr',
 'd_swstr_yoy':'SwStr% to-date vs prior-yr',
 'd_k_yoy':'K% to-date vs prior-yr',
 'd_csw_yoy':'CSW% to-date vs prior-yr',
 'd_velo_recent_yoy':'FB velo L21 vs prior-yr',
 'd_swstr_recent_yoy':'SwStr% L21 vs prior-yr',
 'd_k_recent_yoy':'K% L21 vs prior-yr',
 'velo_recent':'FB velo L21 level',
 'swstr_recent':'SwStr% L21 level',
 'k_recent':'K% L21 level',
 'velo_z_pop':'velo z (pop)',
 'swstr_z_pop':'SwStr% z (pop)',
 'k_z_pop':'K% z (pop)',
 'd_fp_recent':'[CTRL] recent FP/start vs to-date',
}

BASE = 'fp_per_start_to'
df['decline'] = df['ros_fp_per_start'] - df[BASE]
df['material_decline'] = (df['decline'] < -2.0).astype(int)

# require valid base + recent window + at least 3 future starts for a stable target
df = df[df['ros_gs'] >= 3].copy()

def partial_r(d, sig, target, base):
    """partial corr of sig vs target controlling for base. cluster-bootstrap CI on pitcher."""
    sub = d[[sig,target,base,'pitcher']].dropna()
    if len(sub) < 200: return None
    def presid(a,b):
        b1 = np.c_[np.ones(len(b)),b]
        coef,_,_,_ = np.linalg.lstsq(b1,a,rcond=None)
        return a - b1@coef
    rx = presid(sub[sig].values, sub[[base]].values)
    ry = presid(sub[target].values, sub[[base]].values)
    r = np.corrcoef(rx,ry)[0,1]
    # raw corr too
    raw = np.corrcoef(sub[sig], sub[target])[0,1]
    # cluster bootstrap
    pids = sub['pitcher'].values
    uniq = np.unique(pids)
    boot=[]
    for _ in range(400):
        samp = np.random.choice(uniq, len(uniq), replace=True)
        idx = np.concatenate([np.where(pids==p)[0] for p in samp])
        ss = sub.iloc[idx]
        rxx = presid(ss[sig].values, ss[[base]].values)
        ryy = presid(ss[target].values, ss[[base]].values)
        boot.append(np.corrcoef(rxx,ryy)[0,1])
    lo,hi = np.percentile(boot,[2.5,97.5])
    return dict(n=len(sub), raw=raw, partial=r, lo=lo, hi=hi)

def grouped_auc(d, sig):
    """incremental AUC: GroupKFold logistic, base-only vs base+signal. returns mean test AUC of base+sig and delta over base."""
    from sklearn.metrics import roc_auc_score
    sub = d[[sig,BASE,'material_decline','pitcher']].dropna()
    if sub.material_decline.nunique()<2 or len(sub)<500: return None
    X = sub[[BASE,sig]].values; Xb = sub[[BASE]].values
    y = sub.material_decline.values; g = sub.pitcher.values
    gkf = GroupKFold(n_splits=5)
    a_full=[]; a_base=[]
    for tr,te in gkf.split(X,y,g):
        sc=StandardScaler().fit(X[tr])
        lr=LogisticRegression(max_iter=500).fit(sc.transform(X[tr]),y[tr])
        a_full.append(roc_auc_score(y[te], lr.predict_proba(sc.transform(X[te]))[:,1]))
        scb=StandardScaler().fit(Xb[tr])
        lrb=LogisticRegression(max_iter=500).fit(scb.transform(Xb[tr]),y[tr])
        a_base.append(roc_auc_score(y[te], lrb.predict_proba(scb.transform(Xb[te]))[:,1]))
    return dict(auc_full=np.mean(a_full), auc_base=np.mean(a_base),
                d_auc=np.mean(a_full)-np.mean(a_base), n=len(sub),
                pos=int(y.sum()))

print('=== panel after filters ===', df.shape, 'material_decline rate', round(df.material_decline.mean(),3))
print('prior-yr velo coverage', df.py_velo.notna().mean().round(3))

rows=[]
for s in SIGNALS:
    pr_dec = partial_r(df, s, 'decline', BASE)
    pr_ros = partial_r(df, s, 'ros_fp_per_start', BASE)
    au = grouped_auc(df, s)
    rows.append(dict(signal=s, desc=SIGNAL_DESC[s],
        n=pr_dec['n'] if pr_dec else 0,
        partial_decline=pr_dec['partial'] if pr_dec else np.nan,
        pd_lo=pr_dec['lo'] if pr_dec else np.nan,
        pd_hi=pr_dec['hi'] if pr_dec else np.nan,
        raw_decline=pr_dec['raw'] if pr_dec else np.nan,
        partial_ros=pr_ros['partial'] if pr_ros else np.nan,
        auc_full=au['auc_full'] if au else np.nan,
        d_auc=au['d_auc'] if au else np.nan,
        ))
res = pd.DataFrame(rows)
res['abs_pd']=res.partial_decline.abs()
res=res.sort_values('abs_pd', ascending=False)
pd.set_option('display.width',200); pd.set_option('display.max_columns',20)
print(res[['signal','desc','n','partial_decline','pd_lo','pd_hi','partial_ros','auc_full','d_auc']].round(4).to_string(index=False))

# --- convergence check: partial r by split_day band ---
print('\n=== CONVERGENCE CHECK (partial_decline by split_day; near-identical = leakage flag) ===')
top = res.head(6).signal.tolist()
for s in top:
    line=[s.ljust(20)]
    for band,(lo,hi) in [('30',(28,32)),('44',(42,46)),('58',(56,60)),('100',(97,103)),('149',(146,152))]:
        sub=df[(df.split_day>=lo)&(df.split_day<=hi)]
        pr=partial_r(sub, s, 'decline', BASE)
        line.append(f'{band}:{pr["partial"]:+.3f}(n{pr["n"]})' if pr else f'{band}:NA')
    print('  '.join(line))

res.to_csv('data/research/validation_runs/_sp_decline_signals_table.csv', index=False)
print('\nsaved table')
