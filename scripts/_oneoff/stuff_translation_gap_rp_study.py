"""Stuff Translation Gap — RELIEF PITCHER study (companion to SP study 2026-06-13).

Leakage-safe OOS reliever-week study: among HIGH-Stuff RP, which pre-week
indicators predict POOR forward BrownU fantasy value? Mirrors the SP study's
method/rigor (stuff-proxy cohort, within-cell translation residuals, expanding
OOS dR2 over stuff alone, convergence-curve leakage check).

KEY RP DIFFERENCE: RP fantasy value is role/save-driven (rprs2, not rp3). Saves
worth 5, holds worth 2. So the dominant avoid bucket should be LOW-LEVERAGE-TRUST
(elite stuff, no save/hold path), not skill-translation.

Forward target (derived; leakage-safe): cumulative BrownU RP FP is computed from
the strictly-cumulative count columns (k_to,bb_to,h_to,er_to,outs_to,hbp_to,
sv_to,hld_to). Last split per (pitcher,year) = season totals. Forward FP/game =
(season_fp - fp_to) / (season_g - g_to) over the strictly-post-cutoff appearances.
"""
import pandas as pd, numpy as np
from sklearn.linear_model import LinearRegression

CSV = 'data/research/xfp_cache/rolling_relievers_2018_2026.csv'
df = pd.read_csv(CSV)
df = df.loc[:, ~df.columns.duplicated()]  # sv_per_g_lag1/hld_per_g_lag1 dup'd in header

# ---- BrownU RP FP from cumulative counts: K + IP*3.3 - H - 2ER - BB - HBP + 5SV + 2HLD
def brownu_fp(d):
    ip = d.outs_to / 3.0
    return (d.k_to + ip*3.3 - d.h_to - 2*d.er_to - d.bb_to - d.hbp_to
            + 5*d.sv_to + 2*d.hld_to)
df['fp_to'] = brownu_fp(df)

# season totals = last split per pitcher-year
df = df.sort_values('split_day')
last = df.groupby(['pitcher','year']).tail(1)[['pitcher','year','fp_to','g_to']]
last = last.rename(columns={'fp_to':'season_fp','g_to':'season_g'})
df = df.merge(last, on=['pitcher','year'], how='left')

# forward fp/game over strictly-post-cutoff appearances
df['fwd_g'] = df['season_g'] - df['g_to']
df['fwd_fp'] = df['season_fp'] - df['fp_to']
df['fwd_fp_per_g'] = np.where(df['fwd_g'] > 0, df['fwd_fp']/df['fwd_g'], np.nan)

# ---- RP cohort gate: enough appearances to-date AND forward window
#  reliever-flavored: g_to>=10, fwd_g>=8, exclude SP-heavy (gs_to small)
df = df[(df.gs_to <= 3)]  # true relievers (no/few starts)
df = df[(df.g_to >= 10) & (df.fwd_g >= 8) & df.fwd_fp_per_g.notna()]
# historical years only for target (2026 partial excluded)
df = df[df.year != 2026]
print(f'panel RP-weeks: {len(df)}')

# ---- Stuff measure: within-cell z of velo + swstr (RP stuff-proxy; no movement
#  needed — velo+swstr is the documented fallback). Pure cross-sectional as-of.
def zc(s):
    m, sd = s.mean(), s.std()
    return (s - m) / sd if sd and not np.isnan(sd) else s*0.0

for col, z in [('avg_velo_to','z_velo'),('swstr_pct_to','z_swstr'),
               ('k_pct_to','z_k'),('bb_pct_to','z_bb'),('zone_pct_to','z_zone'),
               ('c_plus_swstr_to','z_csw'),('barrel_pct_to','z_barrel'),
               ('hard_hit_pct_to','z_hardhit'),('xwoba_on_contact_to','z_xwobacon'),
               ('gb_pct_to','z_gb')]:
    df[z] = df.groupby(['year','split_day'])[col].transform(zc)

df['stuff'] = df[['z_velo','z_swstr']].mean(axis=1)
# re-z stuff within cell so it's clean
df['stuff'] = df.groupby(['year','split_day'])['stuff'].transform(zc)

# HIGH-Stuff cohort = top quartile stuff within each as-of cell
df['stuff_q'] = df.groupby(['year','split_day'])['stuff'].transform(
    lambda s: s.rank(pct=True))
hi = df[df.stuff_q >= 0.75].copy()
print(f'HIGH-Stuff RP-weeks: {len(hi)}  fwd_fp/g mean {hi.fwd_fp_per_g.mean():.2f} '
      f'(full panel {df.fwd_fp_per_g.mean():.2f})')

# ---- within-cell translation residuals (sign-oriented: POSITIVE = worse stuff
#  translation / hypothesized worse forward value)
def resid_within_cell(d, ycol, xcol='stuff'):
    out = pd.Series(index=d.index, dtype=float)
    for key, g in d.groupby(['year','split_day']):
        if len(g) < 8: out.loc[g.index] = np.nan; continue
        X = g[[xcol]].values; y = g[ycol].values
        lr = LinearRegression().fit(X, y)
        out.loc[g.index] = y - lr.predict(X)
    return out

# build on the FULL panel cells (more stable cells), then subset to hi
for tgt, name in [('c_plus_swstr_to','rcsw'),('swstr_pct_to','rswstr'),('k_pct_to','rk')]:
    df['res_'+name] = resid_within_cell(df, tgt)
# K-BB translation: residual of (k_pct - bb_pct) on stuff
df['k_minus_bb'] = df['k_pct_to'] - df['bb_pct_to']
df['res_rkbb'] = resid_within_cell(df, 'k_minus_bb')

# re-merge residuals into hi
hi = df[df.stuff_q >= 0.75].copy()

# ============================================================
# BUCKET DEFINITIONS (all as-of, within-cell z; POSITIVE = hypothesized WORSE)
# ============================================================
# (a) walk-volatility: high bb%, low zone% (ball-rate instability proxy)
hi['b_walk'] = hi['z_bb'] - hi['z_zone']
# (b) HR-volatility: barrel + hardhit + low-GB (flyball+damage profile)
hi['b_hr'] = hi['z_barrel'] + hi['z_hardhit'] - hi['z_gb']
# (c) low-leverage-trust: good stuff but NO save/hold path. role_middle + no sv path.
#   higher = worse. use lagged role + lagged save/hold rate.
hi['sv_path'] = hi['sv_per_g_lag1'].fillna(0) + 0.5*hi['hld_per_g_lag1'].fillna(0)
hi['b_lowlev'] = hi['role_middle_lag1'].fillna(0)*1.0 - zc(hi['sv_path'])
# also a pure 'no save path' z
hi['b_nosvpath'] = -zc(hi['sv_path'])
# (d) one-pitch-fragility PROXY: extreme zone-swing reliance / low o_swing (note gap)
hi['b_fragile'] = -hi.groupby(['year','split_day'])['o_swing_pct_to'].transform(zc)
# (e) recent decline PROXY: we have no last21 velo split; use low workload (g_to low
#   within cell = unestablished) + note gap. Use -z(g_to) as workload handle.
hi['b_decline'] = -hi.groupby(['year','split_day'])['g_to'].transform(zc)
# skill-translation buckets (sign: positive=worse translation)
hi['b_nowhiff_csw'] = -hi['res_rcsw']
hi['b_nowhiff_swstr'] = -hi['res_rswstr']
hi['b_nok_kbb'] = -hi['res_rkbb']
hi['b_damage'] = hi['z_barrel'] + hi['z_hardhit'] + hi['z_xwobacon']

BUCKETS = ['b_walk','b_hr','b_lowlev','b_nosvpath','b_fragile','b_decline',
           'b_nowhiff_csw','b_nowhiff_swstr','b_nok_kbb','b_damage']

# z-normalize buckets within cell for fair comparison
for b in BUCKETS:
    hi[b] = hi.groupby(['year','split_day'])[b].transform(zc)

hi = hi.dropna(subset=BUCKETS + ['stuff','fwd_fp_per_g'])
print(f'HIGH-Stuff usable (no NaN): {len(hi)}')

# ============================================================
# EXPANDING-WINDOW OOS: dR2 of each bucket OVER stuff alone
# ============================================================
TEST_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]
def oos_r2(feats):
    yhat, ytrue = [], []
    for ty in TEST_YEARS:
        tr = hi[hi.year < ty]; te = hi[hi.year == ty]
        if len(tr) < 100 or len(te) < 20: continue
        lr = LinearRegression().fit(tr[feats], tr['fwd_fp_per_g'])
        yhat.append(lr.predict(te[feats])); ytrue.append(te['fwd_fp_per_g'].values)
    yhat = np.concatenate(yhat); ytrue = np.concatenate(ytrue)
    ss_res = ((ytrue - yhat)**2).sum()
    ss_tot = ((ytrue - ytrue.mean())**2).sum()
    return 1 - ss_res/ss_tot, len(ytrue)

base_r2, n_oos = oos_r2(['stuff'])
print(f'\\nbase OOS R2 (stuff alone): {base_r2:+.4f}  n_oos={n_oos}')

print('\\n=== per-bucket incremental OOS dR2 over stuff alone ===')
rows = []
for b in BUCKETS:
    r2, _ = oos_r2(['stuff', b])
    dr2 = r2 - base_r2
    # within-cell spearman with forward fp (direction)
    rho = hi[[b,'fwd_fp_per_g']].corr(method='spearman').iloc[0,1]
    rows.append((b, dr2, rho))
    print(f'  {b:18s}  dR2={dr2:+.4f}  spearman(bucket,fwdFP)={rho:+.3f}')

# ============================================================
# ROLE-PATH vs SKILL-TRANSLATION head-to-head (KEY RP TEST)
# ============================================================
print('\\n=== ROLE-PATH vs SKILL-TRANSLATION (key RP test) ===')
role_path = ['b_lowlev']  # role/leverage avoid
skill_path = ['b_nok_kbb','b_nowhiff_csw','b_damage']  # SP-style skill avoids
r2_role,_ = oos_r2(['stuff'] + role_path); print(f'  stuff + role-path  dR2 {r2_role-base_r2:+.4f}')
r2_skill,_ = oos_r2(['stuff'] + skill_path); print(f'  stuff + skill-path dR2 {r2_skill-base_r2:+.4f}')
r2_both,_ = oos_r2(['stuff'] + role_path + skill_path); print(f'  stuff + both       dR2 {r2_both-base_r2:+.4f}')

# Also: does the SAVE PATH (positive lens) just directly predict fwd value?
# regress fwd on stuff + sv_path z
hi['z_svpath'] = hi.groupby(['year','split_day'])['sv_path'].transform(zc).fillna(0)
r2_sv,_ = oos_r2(['stuff','z_svpath']); print(f'  stuff + sv_path(+)  dR2 {r2_sv-base_r2:+.4f}  (positive leverage signal)')

# ============================================================
# CONVERGENCE-CURVE LEAKAGE CHECK (per-split spearman, early vs late)
# ============================================================
print('\\n=== convergence-curve leakage check (per-split spearman early<=79 vs >=135) ===')
def split_rho(b):
    early = hi[hi.split_day <= 79]; late = hi[hi.split_day >= 135]
    re = early[[b,'fwd_fp_per_g']].corr(method='spearman').iloc[0,1]
    rl = late[[b,'fwd_fp_per_g']].corr(method='spearman').iloc[0,1]
    rm = hi[[b,'fwd_fp_per_g']].corr(method='spearman').iloc[0,1]
    return rm, re, rl
for b in BUCKETS:
    rm,re,rl = split_rho(b)
    print(f'  {b:18s} mean {rm:+.3f}  early {re:+.3f}  late {rl:+.3f}')

# ============================================================
# AVOID-RISK COMPOSITE (validating buckets only — decided after seeing dR2)
# ============================================================
print('\\n=== quintile forward FP by candidate composite (low-leverage + damage) ===')
hi['avoid_lowlev'] = hi['b_lowlev']
for comp_name, comp_feats in [('lowlev_only',['b_lowlev']),
                               ('lowlev+damage',['b_lowlev','b_damage']),
                               ('lowlev+kbb+damage',['b_lowlev','b_nok_kbb','b_damage'])]:
    hi['_comp'] = hi[comp_feats].mean(axis=1)
    r2c,_ = oos_r2(['stuff','_comp'])
    q = pd.qcut(hi['_comp'], 5, labels=False, duplicates='drop')
    qm = hi.groupby(q)['fwd_fp_per_g'].mean()
    print(f'  {comp_name:20s} dR2 {r2c-base_r2:+.4f}  Q1 {qm.iloc[0]:.2f} -> Q5 {qm.iloc[-1]:.2f}  '
          f'(Q5-Q1 {qm.iloc[-1]-qm.iloc[0]:+.2f})')

# FG Stuff+ cross-check if joinable
import os, glob
fg = glob.glob('data/research/fg_asof/*')
print('\\nFG asof files:', [os.path.basename(f) for f in fg][:10] if fg else 'NONE')
