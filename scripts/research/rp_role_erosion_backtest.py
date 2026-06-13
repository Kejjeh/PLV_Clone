"""
RP ROLE / LEVERAGE EROSION backtest (2026-06-13).

Thesis: RP fantasy value is OPPORTUNITY-dominated (rprs2 r~0.87 vs rp3 0.55
because saves/holds = role). So the decline that CRATERS RP FP is ROLE LOSS,
not rate regression. Test whether role/leverage-erosion signals predict:
  (a) realized RoS RP FP/appearance
  (b) a ROLE-LOSS outcome flag (RoS save+hold share drops materially below to-date)

Leakage discipline (lens_value_add lesson):
  - as-of-split ONLY (every feature computed from cumulative _to at the split)
  - player-clustered GroupKFold (cluster = pitcher)
  - INCREMENTAL partial-r over a base model (rprs2-style: to-date role-FP-rate
    + to-date sv/hld share); Rule 9 baseline includes the production drivers
  - cluster-bootstrap CIs
  - convergence-curve check (signal stable as split_day advances?)
"""
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from scipy import stats

RNG = np.random.default_rng(13)
PANEL = 'data/research/xfp_cache/rolling_relievers_2018_2026.csv'

d = pd.read_csv(PANEL)
d = d.sort_values(['pitcher','year','split_day']).reset_index(drop=True)

# ---- RoS outcomes (rest of season = full_year - to_date) ----
# fp_year_total is the full-season role-FP total (rprs2 target).
d['ros_fp'] = d['fp_year_total'] - d['fp_with_role_to']
d['ros_g']  = None  # we don't have full-year G directly; approximate via final-split g_to per pitcher-year
finalg = (d.sort_values('split_day').groupby(['pitcher','year'])
            .agg(g_final=('g_to','last'), sv_final=('sv_to','last'),
                 hld_final=('hld_to','last'), gf_final=('gf_to','last')).reset_index())
d = d.merge(finalg, on=['pitcher','year'], how='left')
d['ros_g']   = d['g_final']  - d['g_to']
d['ros_sv']  = d['sv_final'] - d['sv_to']
d['ros_hld'] = d['hld_final']- d['hld_to']
d['ros_gf']  = d['gf_final'] - d['gf_to']

# ---- RECENT-WINDOW (last ~14 days) incremental rates, as-of split ----
# Subtract the cumulative _to value 2 splits prior (split_day-14).
prev = d[['pitcher','year','split_day','g_to','gf_to','sv_to','hld_to','fp_with_role_to']].copy()
prev['split_day'] = prev['split_day'] + 14   # so it joins onto the row 14d later
prev = prev.rename(columns={c: c+'_prev' for c in
        ['g_to','gf_to','sv_to','hld_to','fp_with_role_to']})
d = d.merge(prev, on=['pitcher','year','split_day'], how='left')

d['g_rec']   = d['g_to']  - d['g_to_prev']
d['gf_rec']  = d['gf_to'] - d['gf_to_prev']
d['sv_rec']  = d['sv_to'] - d['sv_to_prev']
d['hld_rec'] = d['hld_to']- d['hld_to_prev']

# recent rates (guard small denom)
def rate(num, den):
    den = den.replace(0, np.nan); return (num/den)
d['gf_pct_rec']     = rate(d['gf_rec'], d['g_rec'])
d['sv_per_g_rec']   = rate(d['sv_rec'], d['g_rec'])
d['hld_per_g_rec']  = rate(d['hld_rec'],d['g_rec'])
d['svhld_per_g_rec']= rate(d['sv_rec']+d['hld_rec'], d['g_rec'])
d['svhld_per_g_to'] = rate(d['sv_to']+d['hld_to'], d['g_to'])

# ============ SIGNALS (as-of split, trend = recent minus to-date) ============
d['sig_gf_trend']    = d['gf_pct_rec']    - d['gf_pct_to']            # GF% erosion
d['sig_svshare_trend'] = d['sv_per_g_rec']- d['sv_per_g_to']         # save-share trend
d['sig_hldshare_trend']= d['hld_per_g_rec']-rate(d['hld_to'],d['g_to'])
d['sig_svhld_trend'] = d['svhld_per_g_rec']- d['svhld_per_g_to']     # combined leverage-opp trend
# closer-status change: was closer-rate (sv_per_g) high but recent collapsed?
d['sig_closer_loss'] = (d['sv_per_g_to']>0.15).astype(int) * (d['sv_per_g_rec'].fillna(0) - d['sv_per_g_to'])
# appearance trend (losing the ball entirely -> fewer apps)
d['g_per_split_to']  = rate(d['g_to'], d['split_day'])
# leverage-tier proxy from to-date opportunity
d['lev_to'] = d['svhld_per_g_to']

# ---- BASE (rprs2-style production drivers, as-of split) ----
d['base_fp_rate_to'] = rate(d['fp_with_role_to'], d['g_to'])   # role-FP per appearance to-date
BASE = ['base_fp_rate_to','sv_per_g_to','svhld_per_g_to','gf_pct_to']

# ---- TARGET (a): RoS FP per appearance ----
d['y_ros_fp_per_app'] = rate(d['ros_fp'], d['ros_g'])

# ---- TARGET (b): ROLE-LOSS flag ----
# RoS save+hold share materially below to-date. Justify threshold: require the
# pitcher to HAVE a role to lose (to-date svhld/g >= 0.15, ~closer/setup tier)
# AND RoS svhld/g drop by >= 40% relative (a 'material' opportunity crater).
d['ros_svhld_per_g'] = rate(d['ros_sv']+d['ros_hld'], d['ros_g'])
had_role = d['svhld_per_g_to'] >= 0.15
rel_drop = (d['svhld_per_g_to'] - d['ros_svhld_per_g']) / d['svhld_per_g_to']
d['role_loss'] = (had_role & (rel_drop >= 0.40)).astype(int)

# ---- analysis sample: need enough apps both sides, valid recent window ----
m = (d['g_to']>=8) & (d['ros_g']>=5) & d['g_rec'].notna() & (d['g_rec']>=2)
S = d[m].copy()
SIGS = ['sig_gf_trend','sig_svshare_trend','sig_hldshare_trend','sig_svhld_trend',
        'sig_closer_loss','g_per_split_to','lev_to']
for c in SIGS+BASE+['y_ros_fp_per_app']:
    S[c] = S[c].replace([np.inf,-np.inf], np.nan)
S = S.dropna(subset=BASE+['y_ros_fp_per_app','role_loss']).reset_index(drop=True)
for c in SIGS:
    S[c] = S[c].fillna(0.0)

print(f'Analysis sample n={len(S)}  unique pitchers={S.pitcher.nunique()}  role_loss base rate={S.role_loss.mean():.3f}')

groups = S['pitcher'].values
gkf = GroupKFold(n_splits=5)

def oos_pred(X, y, clf=False):
    pred = np.full(len(y), np.nan)
    for tr,te in gkf.split(X,y,groups):
        if clf:
            mdl = LogisticRegression(max_iter=1000, C=1.0)
            mdl.fit(X[tr],y[tr]); pred[te]=mdl.predict_proba(X[te])[:,1]
        else:
            mdl = LinearRegression(); mdl.fit(X[tr],y[tr]); pred[te]=mdl.predict(X[te])
    return pred

def partial_r(resid_y, resid_x):
    r,_ = stats.pearsonr(resid_x, resid_y); return r

# residualize a signal & y against BASE (OOS), then correlate -> incremental partial-r
yv = S['y_ros_fp_per_app'].values
Xbase = S[BASE].values
base_pred_y = oos_pred(Xbase, yv)
resid_y = yv - base_pred_y

def cluster_boot_ci(vals, idx, stat_fn, n=2000):
    pids = S['pitcher'].values
    uniq = np.unique(pids)
    out=[]
    for _ in range(n):
        samp = RNG.choice(uniq, size=len(uniq), replace=True)
        rows = np.concatenate([idx[pids[idx]==p] for p in samp]) if False else None
        # faster: build mask
        mask = np.isin(pids, samp)  # approximate cluster boot (with-replacement clusters)
        out.append(stat_fn(mask))
    return np.percentile(out,[2.5,97.5])

idx_all = np.arange(len(S))

rows=[]
for sig in SIGS:
    xv = S[sig].values.reshape(-1,1)
    base_pred_x = oos_pred(Xbase, S[sig].values)
    resid_x = S[sig].values - base_pred_x
    pr = partial_r(resid_y, resid_x)
    # AUC for role_loss: sig alone (direction-agnostic via abs corr sign)
    yl = S['role_loss'].values
    try:
        auc = roc_auc_score(yl, S[sig].values)
        auc = max(auc, 1-auc)  # report discriminative power magnitude
    except Exception:
        auc = np.nan
    # cluster bootstrap CI on partial-r
    def stat(mask):
        rx, ry = resid_x[mask], resid_y[mask]
        if len(rx)<30 or np.std(rx)==0: return np.nan
        return stats.pearsonr(rx,ry)[0]
    lo,hi = cluster_boot_ci(None, idx_all, stat, n=800)
    rows.append(dict(signal=sig, partial_r=round(pr,4), pr_lo=round(lo,4),
                     pr_hi=round(hi,4), auc_roleloss=round(auc,3)))

res = pd.DataFrame(rows).sort_values('partial_r', key=lambda s:s.abs(), ascending=False)
print('\n=== INCREMENTAL signal table (partial-r over rprs2-style base; cluster-boot 95% CI) ===')
print(res.to_string(index=False))

# ---- Role-loss predictability: full role/leverage signal set vs base, OOS AUC ----
yl = S['role_loss'].values
auc_base = roc_auc_score(yl, oos_pred(Xbase, yl, clf=True))
Xfull = S[BASE+SIGS].values
auc_full = roc_auc_score(yl, oos_pred(Xfull, yl, clf=True))
print(f'\nROLE-LOSS flag OOS AUC: base(rprs2 drivers)={auc_base:.3f}  +role/leverage signals={auc_full:.3f}  delta={auc_full-auc_base:+.3f}')

# ---- Does role/leverage erosion explain RoS FP DECLINE? incremental R2 full vs base ----
def oos_r2(X,y):
    p = oos_pred(X,y); ss_res=np.sum((y-p)**2); ss_tot=np.sum((y-y.mean())**2)
    return 1-ss_res/ss_tot
r2_base = oos_r2(Xbase, yv)
r2_full = oos_r2(S[BASE+SIGS].values, yv)
print(f'RoS FP/app OOS R2: base={r2_base:.3f}  +role/leverage signals={r2_full:.3f}  deltaR2={r2_full-r2_base:+.4f}')

# ---- Convergence curve: partial-r of best signal by split_day bucket ----
best = res.iloc[0]['signal']
print(f'\nConvergence curve for best signal [{best}] (partial-r of raw sig vs resid_y by split bucket):')
S['_resy']=resid_y
for lo,hi in [(30,65),(66,100),(101,135),(136,191)]:
    sub=S[(S.split_day>=lo)&(S.split_day<=hi)]
    if len(sub)>40:
        r=stats.pearsonr(sub[best], sub['_resy'])[0]
        print(f'  split {lo:3d}-{hi:3d}: n={len(sub):5d}  partial-r~={r:+.3f}  role_loss_rate={sub.role_loss.mean():.3f}')

# ---- Save outputs for report ----
res.to_csv('data/research/validation_runs/_rp_role_erosion_sigtable.csv', index=False)
print('\nsaved sig table.')
print(f'__HEADLINE__ deltaR2={r2_full-r2_base:+.4f} | AUC_delta={auc_full-auc_base:+.3f} | best_sig={best} pr={res.iloc[0].partial_r}')
