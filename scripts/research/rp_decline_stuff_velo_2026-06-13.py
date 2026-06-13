"""
RP decline signal backtest: does velo (level or decline) beat whiff/K-level
for predicting a reliever's rest-of-season FP decline?

Leakage discipline:
 - as-of-split features ONLY (_to columns are cumulative-to-split; avg_velo_to level)
 - prior-year velo joined from rp_archetype_career_panel (completed prior season -> safe)
 - target = RoS FP per appearance = (fp_year_total - cum_fp_to_date) / (remaining appearances)
 - base = to-date FP per appearance (and a role-aware base); incremental partial-r over base
 - player-clustered GroupKFold (no reliever in train+test)
 - cluster bootstrap CIs; convergence-curve leakage check across split-days
"""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score

RNG = np.random.default_rng(13)

df = pd.read_csv('data/research/xfp_cache/rolling_relievers_2018_2026.csv')

# ---- reconstruct cumulative FP to-date from cumulative counting stats ----
df['cum_fp_skill'] = (df.k_to + df.ip_to*3.3 - df.h_to - 2*df.er_to - df.bb_to - df.hbp_to)
df['cum_fp_role']  = df['cum_fp_skill'] + 5*df.sv_to + 2*df.hld_to

# ---- RoS target. fp_year_total = full-season FP-with-role. ----
df['ros_fp_total'] = df['fp_year_total'] - df['cum_fp_role']
# estimate remaining appearances: scale g_to by remaining-season fraction of the split window.
# split_day is day-of-season; relievers appear ~ proportional to days. Use season ~186 days.
SEASON_DAYS = 186.0
df['frac_done'] = (df['split_day'] / SEASON_DAYS).clip(0.05, 0.97)
df['g_rest_est'] = df['g_to'] * (1 - df['frac_done']) / df['frac_done']
# keep rows with a meaningful remaining sample
df = df[(df.g_to >= 8) & (df.g_rest_est >= 5) & (df.tbf_to >= 30)].copy()
df['ros_fp_per_app'] = df['ros_fp_total'] / df['g_rest_est']
# to-date FP per appearance (the BASE rate)
df['fp_per_app_to'] = df['cum_fp_role'] / df['g_to']
df['fp_skill_per_app_to'] = df['cum_fp_skill'] / df['g_to']

# winsorize target to tame the per-app ratio tail
lo, hi = df['ros_fp_per_app'].quantile([0.01, 0.99])
df['ros_fp_per_app'] = df['ros_fp_per_app'].clip(lo, hi)

# ---- join prior-year velo + stuff ratings from archetype panel (leakage-safe) ----
arch = pd.read_parquet('data/research/rp_archetype_career_panel.parquet')
prior = arch[['pitcher','year','avg_velo','swstr_pct','k_pct','VELO','STUFF','OVERALL','OVERALL_slope_3yr']].copy()
prior = prior.rename(columns={c: c+'_py' for c in ['avg_velo','swstr_pct','k_pct','VELO','STUFF','OVERALL','OVERALL_slope_3yr']})
prior['join_year'] = prior['year'] + 1
prior = prior.drop(columns='year')
df = df.merge(prior, left_on=['pitcher','year'], right_on=['pitcher','join_year'], how='left')

# ---- engineer signals (all as-of-split / prior-completed-season) ----
# percentile WITHIN split_day (cross-sectional, leakage-safe: uses only other pitchers' as-of data)
def pct_within_split(col):
    return df.groupby('split_day')[col].rank(pct=True)

df['swstr_lvl_pct']  = pct_within_split('swstr_pct_to')
df['k_lvl_pct']      = pct_within_split('k_pct_to')
df['csw_lvl_pct']    = pct_within_split('c_plus_swstr_to')
df['velo_lvl_pct']   = pct_within_split('avg_velo_to')
df['bb_lvl_pct']     = pct_within_split('bb_pct_to')
df['xwoba_lvl_pct']  = pct_within_split('xwoba_per_pa_to')  # lower better

# velo DECLINE: YoY (to-date velo vs prior full-season velo)
df['velo_yoy']       = df['avg_velo_to'] - df['avg_velo_py']
# k/swstr YoY for symmetric comparison
df['swstr_yoy']      = df['swstr_pct_to'] - df['swstr_pct_py']
df['k_yoy']          = df['k_pct_to'] - df['k_pct_py']
# recent-window-vs-to-date: fp_skill_to is a RECENT rolling-window FP; gap vs cumulative = recency delta
df['fp_recent_vs_todate'] = df['fp_skill_to'] - df['fp_skill_per_app_to']  # recent window minus season-rate
# level-vs-FP gap: high stuff but low to-date FP (buy-low) vs low stuff high FP (sell)
df['swstr_minus_fp_pct'] = df['swstr_lvl_pct'] - pct_within_split('fp_per_app_to')
# archetype VELO/STUFF slope (prior-season trajectory)
df['velo_slope_py']  = df['OVERALL_slope_3yr_py']

base_feats = ['fp_per_app_to', 'fp_skill_per_app_to']  # Rule-9 base: to-date FP rate
# add role/leverage base controls so stuff isn't just proxying role
base_feats += ['sv_per_g_to', 'hld_per_g_to', 'role_closer_lag1', 'role_setup_lag1']

signals = {
    'swstr_LEVEL_pct'   : 'swstr_lvl_pct',
    'k_LEVEL_pct'       : 'k_lvl_pct',
    'csw_LEVEL_pct'     : 'csw_lvl_pct',
    'velo_LEVEL_pct'    : 'velo_lvl_pct',
    'velo_DECLINE_yoy'  : 'velo_yoy',
    'swstr_DECLINE_yoy' : 'swstr_yoy',
    'k_DECLINE_yoy'     : 'k_yoy',
    'fp_recent_vs_todate': 'fp_recent_vs_todate',
    'swstr_minus_fp_gap': 'swstr_minus_fp_pct',
    'bb_LEVEL_pct'      : 'bb_lvl_pct',
    'xwoba_LEVEL_pct'   : 'xwoba_lvl_pct',
    'archetype_OVERALL_slope_py': 'velo_slope_py',
}

TARGET = 'ros_fp_per_app'

def incremental_partial_r(feat_col, n_boot=400):
    """OOS incremental partial-r of feat over base, player-clustered GroupKFold.
    Returns partial_r (corr of OOS residuals) + cluster-bootstrap CI + n."""
    d = df.dropna(subset=base_feats + [feat_col, TARGET]).copy()
    if len(d) < 200:
        return dict(n=len(d), partial_r=np.nan, lo=np.nan, hi=np.nan, dr2=np.nan)
    X_base = d[base_feats].values
    X_full = d[base_feats + [feat_col]].values
    y = d[TARGET].values
    groups = d['pitcher'].values
    gkf = GroupKFold(n_splits=5)
    resid_base = np.full(len(d), np.nan)
    pred_full  = np.full(len(d), np.nan)
    pred_base  = np.full(len(d), np.nan)
    feat_oos   = np.full(len(d), np.nan)
    for tr, te in gkf.split(X_full, y, groups):
        mb = LinearRegression().fit(X_base[tr], y[tr])
        mf = LinearRegression().fit(X_full[tr], y[tr])
        pred_base[te] = mb.predict(X_base[te])
        pred_full[te] = mf.predict(X_full[te])
        # partial: residualize feat on base (train), apply to test
        fm = LinearRegression().fit(X_base[tr], d[feat_col].values[tr])
        feat_oos[te] = d[feat_col].values[te] - fm.predict(X_base[te])
        resid_base[te] = y[te] - mb.predict(X_base[te])
    # partial-r = corr(resid_base, feat_residual_oos)
    pr = np.corrcoef(resid_base, feat_oos)[0,1]
    # ΔR2 OOS
    ss = ((y - y.mean())**2).sum()
    r2b = 1 - ((y - pred_base)**2).sum()/ss
    r2f = 1 - ((y - pred_full)**2).sum()/ss
    dr2 = r2f - r2b
    # cluster bootstrap on partial-r
    pids = d['pitcher'].unique()
    boots = []
    idx_by_p = {p: np.where(groups==p)[0] for p in pids}
    for _ in range(n_boot):
        samp = RNG.choice(pids, size=len(pids), replace=True)
        ii = np.concatenate([idx_by_p[p] for p in samp])
        a, b = resid_base[ii], feat_oos[ii]
        if np.std(b) > 1e-9:
            boots.append(np.corrcoef(a, b)[0,1])
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan)
    return dict(n=len(d), partial_r=pr, lo=lo, hi=hi, dr2=dr2)

# ---- material-decline flag AUC ----
# define "material decline": RoS FP/app falls >= 1.5 below to-date FP/app
df['decline_flag'] = ((df['fp_per_app_to'] - df['ros_fp_per_app']) >= 1.5).astype(int)

def decline_auc(feat_col):
    d = df.dropna(subset=base_feats + [feat_col, 'decline_flag']).copy()
    if d['decline_flag'].nunique() < 2 or len(d) < 200:
        return dict(n=len(d), auc=np.nan, auc_incr=np.nan)
    y = d['decline_flag'].values
    groups = d['pitcher'].values
    Xb = d[base_feats].values
    Xf = d[base_feats + [feat_col]].values
    gkf = GroupKFold(5)
    pb = np.full(len(d), np.nan); pf = np.full(len(d), np.nan)
    for tr, te in gkf.split(Xf, y, groups):
        from sklearn.preprocessing import StandardScaler
        sc = StandardScaler().fit(Xb[tr]);
        mb = LogisticRegression(max_iter=1000).fit(sc.transform(Xb[tr]), y[tr])
        pb[te] = mb.predict_proba(sc.transform(Xb[te]))[:,1]
        scf = StandardScaler().fit(Xf[tr])
        mf = LogisticRegression(max_iter=1000).fit(scf.transform(Xf[tr]), y[tr])
        pf[te] = mf.predict_proba(scf.transform(Xf[te]))[:,1]
    return dict(n=len(d), base_rate=y.mean(),
                auc=roc_auc_score(y, pf), auc_base=roc_auc_score(y, pb),
                auc_incr=roc_auc_score(y, pf)-roc_auc_score(y, pb))

print(f'panel rows after filters: {len(df)}  unique RPs: {df.pitcher.nunique()}')
print(f'target ros_fp_per_app mean={df[TARGET].mean():.2f} sd={df[TARGET].std():.2f}')
print(f'decline_flag base rate: {df.decline_flag.mean():.3f}')
print(f'velo_yoy coverage (non-null): {df.velo_yoy.notna().mean():.2f}')
print()

rows = []
for name, col in signals.items():
    pr = incremental_partial_r(col)
    au = decline_auc(col)
    rows.append(dict(signal=name, n=pr['n'], partial_r=pr['partial_r'],
                     ci_lo=pr['lo'], ci_hi=pr['hi'], dR2=pr['dr2'],
                     decline_auc_incr=au.get('auc_incr', np.nan),
                     decline_auc=au.get('auc', np.nan)))
res = pd.DataFrame(rows).sort_values('partial_r', key=lambda s: s.abs(), ascending=False)
pd.set_option('display.width', 200, 'display.max_columns', 20)
print(res.to_string(index=False, float_format=lambda x: f'{x:+.4f}'))

# ---- convergence-curve leakage check: partial-r by split-day bucket ----
print('\n=== Convergence / leakage check: top signals partial-r by split-day bucket ===')
df['sd_bucket'] = pd.cut(df.split_day, [0,60,100,140,200], labels=['early','mid','late','v.late'])
for col, nm in [('velo_lvl_pct','velo_LEVEL'),('swstr_lvl_pct','swstr_LEVEL'),('k_lvl_pct','k_LEVEL'),('velo_yoy','velo_DECLINE_yoy')]:
    line = []
    for bk in ['early','mid','late','v.late']:
        sub = df[df.sd_bucket==bk].dropna(subset=base_feats+[col,TARGET])
        if len(sub) < 80:
            line.append(f'{bk}:n/a'); continue
        # quick OOS partial via single GroupKFold
        from sklearn.linear_model import LinearRegression as LR
        y=sub[TARGET].values; g=sub.pitcher.values
        Xb=sub[base_feats].values; f=sub[col].values
        gkf=GroupKFold(min(5, sub.pitcher.nunique()))
        rb=np.full(len(sub),np.nan); fo=np.full(len(sub),np.nan)
        for tr,te in gkf.split(Xb,y,g):
            mb=LR().fit(Xb[tr],y[tr]); rb[te]=y[te]-mb.predict(Xb[te])
            fm=LR().fit(Xb[tr],f[tr]); fo[te]=f[te]-fm.predict(Xb[te])
        pr=np.corrcoef(rb,fo)[0,1]
        line.append(f'{bk}:{pr:+.3f}(n{len(sub)})')
    print(f'  {nm:18s} ' + '  '.join(line))

# save table
res.to_csv('data/research/validation_runs/rp_decline_stuff_velo_table.csv', index=False)
print('\nsaved table -> data/research/validation_runs/rp_decline_stuff_velo_table.csv')
