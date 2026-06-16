"""EARLY-SEASON RoS PREDICTION (Part B — confirmation of the bat-speed edge).

Hypothesis (from Part A stabilization): early in a season, bat speed is reliable
while outcome rates are noise, so early bat speed should forecast rest-of-season
production AND add value over the (still-noisy) early rate stats. The edge should
be largest at the smallest cutoff and fade as the rates catch up.

Cohorts with Opening-Day bat tracking: 2024, 2025 (2 cohorts — exploratory,
display-grade, NOT a 5/7 validation). Everything computed from the raw parquet
with an exact game_date split (no leaderboard date-param ambiguity).
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[3]
C = ROOT / 'data' / 'research' / 'xfp_cache'
PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play',
             'sac_bunt','catcher_interf'}
K_EVENTS = {'strikeout','strikeout_double_play'}
COLS = ['game_date','batter','events','type','launch_speed','woba_value','woba_denom',
        'estimated_woba_using_speedangle','bat_speed','swing_length','attack_angle']

def load(y):
    df = pd.read_parquet(C / f'statcast_{y}.parquet', columns=COLS)
    df['game_date'] = pd.to_datetime(df['game_date'])
    return df

def wstats(sub):
    sw = sub[sub['bat_speed'].notna() & (sub['bat_speed'] > 10)]
    pa = sub[sub['events'].isin(PA_EVENTS)]
    bip = sub[sub['type'] == 'X']
    npa = len(pa); nbip = len(bip)
    wd = pa['woba_denom'].fillna(0).sum()
    return dict(
        n_sw=len(sw),
        bat_speed=sw['bat_speed'].mean(),
        swing_length=sw['swing_length'].mean(),
        attack_angle=sw['attack_angle'].mean(),
        n_pa=npa,
        woba=(pa['woba_value'].fillna(0).sum() / wd) if wd > 0 else np.nan,
        k_pct=(pa['events'].isin(K_EVENTS).sum() / npa) if npa else np.nan,
        n_bip=nbip,
        hard_hit=((bip['launch_speed'] >= 95).mean()) if nbip else np.nan,
        xwobacon=bip['estimated_woba_using_speedangle'].mean() if nbip else np.nan,
    )

def per_batter(df, mask):
    out = {}
    for bid, sub in df[mask].groupby('batter'):
        out[bid] = wstats(sub)
    return pd.DataFrame(out).T

def prior_full(y):
    df = load(y)
    rows = {}
    for bid, sub in df.groupby('batter'):
        sw = sub[sub['bat_speed'].notna() & (sub['bat_speed'] > 10)]
        pa = sub[sub['events'].isin(PA_EVENTS)]
        wd = pa['woba_denom'].fillna(0).sum()
        rows[bid] = dict(prior_woba=(pa['woba_value'].fillna(0).sum()/wd) if wd>0 else np.nan,
                         prior_bat_speed=sw['bat_speed'].mean() if len(sw) else np.nan,
                         prior_pa=len(pa))
    p = pd.DataFrame(rows).T
    return p[p['prior_pa'] >= 100]

def resid(y, X):
    X1 = np.column_stack([np.ones(len(y))] + [X[c].values for c in X.columns])
    beta, *_ = np.linalg.lstsq(X1, y.values, rcond=None)
    return y.values - X1 @ beta

CUTOFFS = [21, 35, 49, 70]
COHORTS = {2024: 2023, 2025: 2024}
panels = {y: load(y) for y in COHORTS}
priors = {py: prior_full(py) for py in COHORTS.values()}

def build(y, cut_days):
    df = panels[y]; start = df['game_date'].min(); cut = start + pd.Timedelta(days=cut_days)
    early = per_batter(df, (df['game_date'] >= start) & (df['game_date'] < cut)).add_prefix('e_')
    ros = per_batter(df, df['game_date'] >= cut)[['woba','xwobacon','n_pa']].add_prefix('r_')
    m = early.join(ros, how='inner').join(priors[COHORTS[y]], how='left')
    m = m[(m['e_n_sw'] >= 20) & (m['e_n_pa'] >= 15) & (m['r_n_pa'] >= 100)]
    return m.astype(float)

print("=== Part B: early signal -> RoS, by cutoff (pooled 2024+2025) ===")
print("\n(1) RAW r of each EARLY signal with RoS xwOBACON  [shows which signal is")
print("    trustworthy early; bat speed should lead while rates are still noisy]")
sig = ['bat_speed','woba','hard_hit','k_pct','xwobacon']
hdr = f"  {'cutoff':<8}{'n':>5}" + ''.join(f"{s:>11}" for s in sig)
print(hdr)
pooled = {}
for cd in CUTOFFS:
    parts = [build(y, cd) for y in COHORTS]
    M = pd.concat(parts, ignore_index=True); pooled[cd] = M
    row = f"  {str(cd)+'d':<8}{len(M):>5}"
    for s in sig:
        r = pearsonr(M['e_'+s], M['r_xwobacon'])[0]
        row += f"{r:>+11.3f}"
    print(row)

print("\n(2) PARTIAL r of early bat_speed with RoS, controlling for early rate")
print("    stats + prior-year wOBA  [does bat speed ADD beyond the noisy rates?]")
print(f"  {'cutoff':<8}{'n':>5}{'->RoS xwOBACON':>18}{'->RoS wOBA':>14}{'per-yr signs':>16}")
ctrl = ['e_woba','e_hard_hit','e_k_pct','prior_woba']
for cd in CUTOFFS:
    M = pooled[cd].dropna(subset=ctrl+['e_bat_speed','r_xwobacon','r_woba'])
    pr_x = pearsonr(resid(M['e_bat_speed'], M[ctrl]), resid(M['r_xwobacon'], M[ctrl]))[0]
    pr_w = pearsonr(resid(M['e_bat_speed'], M[ctrl]), resid(M['r_woba'], M[ctrl]))[0]
    signs = []
    for y in COHORTS:
        My = build(y, cd).dropna(subset=ctrl+['e_bat_speed','r_xwobacon'])
        if len(My) > 25:
            prc = pearsonr(resid(My['e_bat_speed'], My[ctrl]), resid(My['r_xwobacon'], My[ctrl]))[0]
            signs.append('+' if prc > 0 else '-')
    print(f"  {str(cd)+'d':<8}{len(M):>5}{pr_x:>+18.3f}{pr_w:>+14.3f}{''.join(signs):>16}")

print("\n(3) DELTA-vs-prior 'getting better/worse' read: does (early bat_speed -")
print("    prior-yr bat_speed) forecast (RoS xwOBACON - prior wOBA)?  2025 clean;")
print("    2024 prior=2023 is 2nd-half-only bat speed (caveated).")
print(f"  {'cohort':<10}{'cutoff':<8}{'n':>5}{'r(Δbs, ΔRoS)':>16}")
for y in COHORTS:
    for cd in [35, 49]:
        M = build(y, cd)
        M = M.dropna(subset=['e_bat_speed','prior_bat_speed','r_xwobacon','prior_woba'])
        M['dbs'] = M['e_bat_speed'] - M['prior_bat_speed']
        M['dros'] = M['r_xwobacon'] - M['prior_woba']
        if len(M) > 25:
            r = pearsonr(M['dbs'], M['dros'])[0]
            tag = '' if y == 2025 else ' (2023 prior=2H only)'
            print(f"  {y:<10}{str(cd)+'d':<8}{len(M):>5}{r:>+16.3f}{tag}")
