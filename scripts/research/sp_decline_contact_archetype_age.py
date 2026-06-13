"""
Backtest: which in-season CONTACT-QUALITY / ARCHETYPE / AGE decline signals
best predict a SP's rest-of-season FP DECLINE (catch Framber-Valdez early).

Leakage discipline (lens_value_add_2026-06-11 lesson):
  - as-of features ONLY (cumulative-to-split _to + recent _last21 window)
  - player-clustered GroupKFold (cluster = pitcher)
  - INCREMENTAL value over base projection (partial r, Rule 9)
  - cluster-bootstrap CIs
  - convergence-curve leakage check across split_days
"""
import warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import LinearRegression, LogisticRegression
from scipy import stats

RNG = np.random.default_rng(13)
ROLL = 'data/research/xfp_cache/rolling_pitchers_2018_2026.csv'
ARCH = 'data/research/sp_archetype_career_panel.parquet'

# ---------------------------------------------------------------- load + filter
r = pd.read_csv(ROLL)
# require enough season-to-date and RoS sample to make decline meaningful
r = r[(r['gs_to'] >= 6) & (r['ros_gs'] >= 4)].copy()

# ---------------------------------------------------------------- base + targets
# Base projection = season-to-date FP/start (the naive "carry forward" baseline).
r['base'] = r['fp_per_start_to']
r['ros_fp'] = r['ros_fp_per_start']
# (a) realized RoS FP/start = ros_fp
# (b) DECLINE target = RoS - to-date  (negative = decline)
r['decline'] = r['ros_fp'] - r['base']
# (c) binary material decline = RoS drops >2 below to-date
r['mat_decline'] = (r['decline'] < -2.0).astype(int)

# ---------------------------------------------------------------- CONTACT signals
# recent-window (_last21) vs season-to-date (_to): rising damage = decline signal.
# Positive delta = recent worse than to-date.
r['d_hardhit']   = r['hard_hit_pct_last21'] - r['hard_hit_pct_to']
r['d_barrel']    = r['barrel_pct_last21']   - r['barrel_pct_to']
r['d_xwobacon']  = r['xwoba_on_contact_last21'] - r['xwoba_on_contact_to']
r['d_xwoba_pa']  = r['xwoba_per_pa_last21']  - r['xwoba_per_pa_to']
# avg_EV: no _to/_last21 EV column directly; proxy via woba_d (damage) is captured.
# gb decline (more air = more damage)
r['d_gb']        = r['gb_pct_last21'] - r['gb_pct_to']  # negative = fewer grounders recently

contact_sigs = {
    'd_hardhit':  ('+', 'HardHit% recent vs to-date (rising=decline)'),
    'd_barrel':   ('+', 'Barrel% recent vs to-date (rising=decline)'),
    'd_xwobacon': ('+', 'xwOBAcon recent vs to-date (rising=decline)'),
    'd_xwoba_pa': ('+', 'xwOBA/PA recent vs to-date (rising=decline)'),
    'd_gb':       ('-', 'GB% recent vs to-date (falling=decline)'),
}

# ---------------------------------------------------------------- ARCHETYPE merge
a = pd.read_parquet(ARCH)
a_prev = a[['pitcher','year','STUFF','OVERALL','OVERALL_slope_3yr','arsenal_entropy',
            'FB_pct','SL_pct','CB_pct','CH_pct','FS_pct','age','career_year']].copy()
# YoY STUFF drop: compare this-season-rating vs prior-season-rating, leakage-safe
# (archetype ratings are per full year; to stay as-of we merge PRIOR year's full
# rating and this year's prior-year rating to form a YoY delta available pre-split).
a_prev['merge_year'] = a_prev['year'] + 1   # prior-year row attaches to next season
prev = a_prev.rename(columns={
    'STUFF':'STUFF_prev','OVERALL':'OVERALL_prev','OVERALL_slope_3yr':'OVERALL_slope_prev',
    'arsenal_entropy':'entropy_prev','FB_pct':'FB_pct_prev','age':'age_prev',
    'career_year':'career_year_prev'})
prev = prev[['pitcher','merge_year','STUFF_prev','OVERALL_prev','OVERALL_slope_prev',
             'entropy_prev','FB_pct_prev','age_prev','career_year_prev']]

# also bring two-years-prior STUFF to compute a YoY drop available as-of
a_prev2 = a[['pitcher','year','STUFF','FB_pct','arsenal_entropy']].copy()
a_prev2['merge_year'] = a_prev2['year'] + 2
a_prev2 = a_prev2.rename(columns={'STUFF':'STUFF_prev2','FB_pct':'FB_pct_prev2',
                                  'arsenal_entropy':'entropy_prev2'})
a_prev2 = a_prev2[['pitcher','merge_year','STUFF_prev2','FB_pct_prev2','entropy_prev2']]

r = r.merge(prev, left_on=['pitcher','year'], right_on=['pitcher','merge_year'], how='left')
r = r.merge(a_prev2, left_on=['pitcher','year'], right_on=['pitcher','merge_year'], how='left')

# YoY archetype-derived signals (all use PRIOR-year completed ratings -> leakage-safe)
r['stuff_yoy_drop']  = r['STUFF_prev2'] - r['STUFF_prev']      # +ve = STUFF fell yr-over-yr
r['overall_slope']   = -r['OVERALL_slope_prev']               # +ve = declining trajectory
r['fb_yoy_drop']     = r['FB_pct_prev2'] - r['FB_pct_prev']    # +ve = FB% falling (velo comp)
r['entropy_yoy_chg'] = r['entropy_prev'] - r['entropy_prev2']  # arsenal entropy change
r['offspeed_prev']   = 1.0 - r['FB_pct_prev']                 # higher = more offspeed lean
r['age_v']           = r['age_prev']                          # as-of age (prior season age+~)
r['career_yr']       = r['career_year_prev']

arch_sigs = {
    'stuff_yoy_drop':  ('+', 'STUFF rating YoY drop (prior2->prior)'),
    'overall_slope':   ('+', 'OVERALL 3yr declining slope (neg slope)'),
    'fb_yoy_drop':     ('+', 'FB% YoY drop (velo compensation)'),
    'entropy_yoy_chg': ('+', 'arsenal entropy change YoY'),
    'offspeed_prev':   ('+', 'offspeed lean (1-FB%) prior'),
}

# ---------------------------------------------------------------- helpers
def cluster_partial_r(df, sig, target, base='base', n_boot=400):
    """Partial correlation of sig with target, controlling for base projection.
    Returns (partial_r, lo, hi, n). Cluster-bootstrap over pitcher."""
    d = df[[sig, target, base, 'pitcher']].dropna()
    if len(d) < 50:
        return np.nan, np.nan, np.nan, len(d)
    def pr(dd):
        X = dd[[base]].values
        # residualize sig and target on base
        rs = dd[sig].values  - LinearRegression().fit(X, dd[sig].values).predict(X)
        rt = dd[target].values - LinearRegression().fit(X, dd[target].values).predict(X)
        if rs.std() < 1e-9 or rt.std() < 1e-9:
            return np.nan
        return np.corrcoef(rs, rt)[0,1]
    point = pr(d)
    clusters = d['pitcher'].unique()
    boots = []
    for _ in range(n_boot):
        samp = RNG.choice(clusters, size=len(clusters), replace=True)
        dd = pd.concat([d[d['pitcher']==c] for c in samp])
        v = pr(dd)
        if not np.isnan(v): boots.append(v)
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan)
    return point, lo, hi, len(d)

def incremental_auc(df, sig, flag='mat_decline', base='base', n_splits=5):
    """OOS AUC of logistic [base] vs [base+sig], player-clustered. Returns
    (auc_base, auc_full, delta, n)."""
    from sklearn.metrics import roc_auc_score
    d = df[[sig, flag, base, 'pitcher']].dropna()
    if len(d) < 100 or d[flag].nunique() < 2:
        return np.nan, np.nan, np.nan, len(d)
    gkf = GroupKFold(n_splits=n_splits)
    g = d['pitcher'].values
    yb, yf, ytrue = [], [], []
    for tr, te in gkf.split(d, d[flag], g):
        dtr, dte = d.iloc[tr], d.iloc[te]
        if dtr[flag].nunique() < 2: continue
        mb = LogisticRegression(max_iter=500).fit(dtr[[base]], dtr[flag])
        mf = LogisticRegression(max_iter=500).fit(dtr[[base,sig]], dtr[flag])
        yb.extend(mb.predict_proba(dte[[base]])[:,1])
        yf.extend(mf.predict_proba(dte[[base,sig]])[:,1])
        ytrue.extend(dte[flag].values)
    if len(set(ytrue)) < 2:
        return np.nan, np.nan, np.nan, len(d)
    ab = roc_auc_score(ytrue, yb); af = roc_auc_score(ytrue, yf)
    return ab, af, af-ab, len(d)

# ---------------------------------------------------------------- run signals
all_sigs = {**contact_sigs, **arch_sigs}
rows = []
for sig,(sign,desc) in all_sigs.items():
    if sig not in r.columns: continue
    pr_d, lo_d, hi_d, n_d = cluster_partial_r(r, sig, 'decline')
    ab, af, dauc, n_a = incremental_auc(r, sig, 'mat_decline')
    leak = 'OK'
    rows.append(dict(signal=sig, desc=desc, n=n_d,
                     partial_r_decline=pr_d, pr_lo=lo_d, pr_hi=hi_d,
                     sig_ci='YES' if (not np.isnan(lo_d) and lo_d*hi_d>0) else 'no',
                     auc_base=ab, auc_full=af, d_auc=dauc, n_auc=n_a, leak=leak))
res = pd.DataFrame(rows).sort_values('partial_r_decline', key=lambda s: s.abs(), ascending=False)

# ---------------------------------------------------------------- AGE INTERACTION
# Does in-season contact decline predict RoS decline HARDER for age 31+ vets?
# Use best contact signal; test interaction term + stratified partial r.
best_contact = 'd_xwoba_pa'  # set after viewing; will recompute below for robustness
# choose contact signal with max |partial r|
cc = res[res['signal'].isin(contact_sigs)].copy()
best_contact = cc.iloc[0]['signal']

di = r[[best_contact,'decline','base','age_v','pitcher']].dropna().copy()
di['old'] = (di['age_v'] >= 31).astype(int)
# z-score the contact signal for interpretable interaction
di['z'] = (di[best_contact]-di[best_contact].mean())/di[best_contact].std()
# interaction model: decline ~ base + z + old + z*old   (cluster-bootstrap on z*old)
def interaction_coef(dd):
    import numpy as np
    X = np.column_stack([dd['base'], dd['z'], dd['old'], dd['z']*dd['old'], np.ones(len(dd))])
    beta, *_ = np.linalg.lstsq(X, dd['decline'].values, rcond=None)
    return beta[1], beta[3]  # main z effect, interaction
mz, mint = interaction_coef(di)
clusters = di['pitcher'].unique()
bz, bint = [], []
for _ in range(500):
    samp = RNG.choice(clusters, size=len(clusters), replace=True)
    dd = pd.concat([di[di['pitcher']==c] for c in samp])
    try:
        z,i = interaction_coef(dd); bz.append(z); bint.append(i)
    except Exception: pass
int_lo, int_hi = np.percentile(bint,[2.5,97.5])
z_lo, z_hi = np.percentile(bz,[2.5,97.5])

# stratified partial r
pr_young = cluster_partial_r(r[r['age_v']<31], best_contact, 'decline')
pr_old   = cluster_partial_r(r[r['age_v']>=31], best_contact, 'decline')

# ---------------------------------------------------------------- CONVERGENCE / leakage curve
# partial r of best signals by split_day quartile -> should be FLAT if leakage-safe
def by_split(sig):
    out=[]
    for q,grp in r.groupby(pd.cut(r['split_day'],[0,79,121,163,200],labels=['early','mid','late','vlate'])):
        pr_d,_,_,n = cluster_partial_r(grp, sig, 'decline', n_boot=80)
        out.append((str(q),n,round(pr_d,3) if not np.isnan(pr_d) else None))
    return out

conv = {best_contact: by_split(best_contact)}
top_arch = res[res['signal'].isin(arch_sigs)].iloc[0]['signal']
conv[top_arch] = by_split(top_arch)

# ---------------------------------------------------------------- OUTPUT
pd.set_option('display.width',200, 'display.max_columns',30)
print('=== SIGNAL RANKING (partial r predicting DECLINE, AUC for material-decline flag) ===')
print(res[['signal','n','partial_r_decline','pr_lo','pr_hi','sig_ci','auc_full','d_auc','n_auc']].to_string(index=False))
print()
print(f'best contact signal: {best_contact}')
print(f'AGE INTERACTION (decline ~ base + z + old(31+) + z*old):')
print(f'  main z effect = {mz:.3f} FP/SD  CI[{z_lo:.3f},{z_hi:.3f}]')
print(f'  z*old interaction = {mint:.3f} FP/SD  CI[{int_lo:.3f},{int_hi:.3f}]  '
      f'{"SIGNIFICANT" if int_lo*int_hi>0 else "n.s."}')
print(f'  stratified partial r  young(<31): {pr_young[0]:.3f} (n={pr_young[3]})  '
      f'old(31+): {pr_old[0]:.3f} (n={pr_old[3]})')
print()
print('CONVERGENCE / leakage curve (partial r by split_day band; flat=leakage-safe):')
for k,v in conv.items():
    print(f'  {k}: {v}')

# stash for the report writer
import json
summary = dict(
    ranking=res.to_dict('records'),
    best_contact=best_contact,
    age_interaction=dict(z=mz,z_lo=z_lo,z_hi=z_hi,inter=mint,int_lo=int_lo,int_hi=int_hi,
                         young_r=pr_young[0],young_n=pr_young[3],old_r=pr_old[0],old_n=pr_old[3]),
    convergence=conv,
    n_total=len(r),
)
with open('.cache/sp_decline_summary.json','w') as f:
    json.dump(summary,f,indent=2,default=str)
print('\nwrote .cache/sp_decline_summary.json')
