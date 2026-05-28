"""
Cross-pool breakout sustainability scan:
- All hitters on user roster (already covered in prior script)
- All FA hitters in league with PA >= 100 in 2026 and meaningful YoY signal

For each candidate, compute the sustainability scorecard dimensions:
  1. History at this level (career years near current xwOBACON)
  2. Process change (whiff/chase/whiff_pct deltas)
  3. Power change (EV90/hard_hit/barrel deltas)
  4. Stabilization (2026 PA size vs gate)
  5. Age curve (best estimate from first_year)
  6. Sign in fp_per_pa_actual vs xwOBA gap (luck context)
"""
import pandas as pd
import numpy as np
import sys, unicodedata
pd.set_option('display.width', 240)
pd.set_option('display.max_columns', 35)

sys.path.insert(0, 'c:/Users/Joshua/plv_clone')
from app.espn_connector import get_free_agents, get_my_roster_with_injuries

MULTIYR = 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv'
df = pd.read_csv(MULTIYR)

def fold(s):
    if pd.isna(s): return ''
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower().strip()

# Name → (most-recent) batter id lookup
df['__name_fold'] = df['player_name'].apply(fold)
df_recent = df.sort_values('year', ascending=False).drop_duplicates('__name_fold')
name_to_bid = dict(zip(df_recent['__name_fold'], df_recent['batter']))
def resolve(name):
    return name_to_bid.get(fold(name))

# ---- pull FA pool ----
print("Pulling FA pool (size=2000)...")
fa = get_free_agents(size=2000)
HITTER_POS = {'C','1B','2B','3B','SS','OF','DH','MI','CI','LF','CF','RF'}
fa_hit = fa[fa['position'].isin(HITTER_POS)].copy()
fa_hit['mlbam'] = fa_hit['player_name'].apply(resolve)
fa_hit = fa_hit[fa_hit['mlbam'].notna()]
print(f"FA hitters with MLBAM: {len(fa_hit)}")

# ---- pull roster ----
roster = get_my_roster_with_injuries()
hitters_r = roster[roster['position'].isin(HITTER_POS)].copy()
hitters_r['mlbam'] = hitters_r['player_name'].apply(resolve)
hitters_r = hitters_r[hitters_r['mlbam'].notna()]

# Combine into one frame with source flag
fa_hit['source'] = 'FA'
hitters_r['source'] = 'ROSTER'
allp = pd.concat([
    fa_hit[['player_name','position','mlbam','source','percent_owned']].assign(injured=False),
    hitters_r[['player_name','position','mlbam','source','injured']].assign(percent_owned=100.0),
], ignore_index=True)
print(f"\nTotal candidate pool (FA + roster): {len(allp)}")

# ---- get 2025 and 2026 rows for each ----
df_25 = df[df['year']==2025].set_index('batter')
df_26 = df[df['year']==2026].set_index('batter')

def career_summary(pid):
    sub = df[df['batter']==pid].sort_values('year')
    if sub.empty: return None
    # find consecutive recent years to estimate age via first MLB year
    first_year = int(sub['year'].min())
    # peak xwOBACON year (≥250 PA)
    pks = sub[sub['pa']>=250]
    peak = pks.loc[pks['xwoba_on_contact'].idxmax()] if len(pks) else sub.loc[sub['xwoba_on_contact'].idxmax()]
    return {
        'first_year': first_year,
        'mlb_years': int(sub['year'].nunique()),
        'peak_xwobacon': float(peak['xwoba_on_contact']),
        'peak_year': int(peak['year']),
        # recent 3-year band of xwOBACON ≥ 250 PA
        'recent_xwobacon_band': pks.tail(3)['xwoba_on_contact'].agg(['min','max']).to_dict()
            if len(pks)>=2 else None,
    }

# ---- score each candidate ----
rows = []
for _, p in allp.iterrows():
    pid = int(p['mlbam'])
    r25 = df_25.loc[pid] if pid in df_25.index else None
    r26 = df_26.loc[pid] if pid in df_26.index else None
    if r26 is None: continue
    pa26 = int(r26['pa']) if pd.notna(r26['pa']) else 0
    if pa26 < 80: continue  # filter to meaningful sample
    csum = career_summary(pid)
    if csum is None: continue

    xw25 = float(r25['xwoba_per_pa']) if (r25 is not None and pd.notna(r25['xwoba_per_pa'])) else np.nan
    xc25 = float(r25['xwoba_on_contact']) if (r25 is not None and pd.notna(r25['xwoba_on_contact'])) else np.nan
    hh25 = float(r25['hard_hit_pct']) if (r25 is not None and pd.notna(r25['hard_hit_pct'])) else np.nan
    ev25 = float(r25['ev90']) if (r25 is not None and pd.notna(r25['ev90'])) else np.nan
    k25  = float(r25['k_pct']) if (r25 is not None and pd.notna(r25['k_pct'])) else np.nan
    w25  = float(r25['whiff_pct']) if (r25 is not None and pd.notna(r25['whiff_pct'])) else np.nan
    ch25 = float(r25['chase_pct']) if (r25 is not None and pd.notna(r25['chase_pct'])) else np.nan
    bb25 = float(r25['bb_pct']) if (r25 is not None and pd.notna(r25['bb_pct'])) else np.nan

    xw26 = float(r26['xwoba_per_pa'])
    xc26 = float(r26['xwoba_on_contact'])
    hh26 = float(r26['hard_hit_pct'])
    ev26 = float(r26['ev90'])
    k26  = float(r26['k_pct'])
    w26  = float(r26['whiff_pct'])
    ch26 = float(r26['chase_pct'])
    bb26 = float(r26['bb_pct'])

    # 95% CI on xwOBA at PA26 (SE ≈ 0.39/sqrt(PA))
    se = 0.39 / np.sqrt(max(pa26,1))
    ci_lo = xw26 - 1.96*se
    ci_hi = xw26 + 1.96*se
    # Is 2025 baseline OUTSIDE the CI? = statistically distinguishable
    distinguishable = (not np.isnan(xw25)) and (xw25 < ci_lo or xw25 > ci_hi)

    # Bayesian-shrunk xwOBA (k=150)
    k_prior = 150.0
    baseline_xw = xw25 if not np.isnan(xw25) else csum['peak_xwobacon'] * 0.78  # rough fallback
    shrunk_xw = (pa26*xw26 + k_prior*baseline_xw) / (pa26 + k_prior)
    shrunk_gap = shrunk_xw - baseline_xw

    # process score: count of 3 axes where signal IMPROVED (whiff↓, chase↓, K%↓)
    proc_axes = 0
    if not np.isnan(w25) and w26 < w25 - 0.005: proc_axes += 1
    if not np.isnan(ch25) and ch26 < ch25 - 0.005: proc_axes += 1
    if not np.isnan(k25) and k26 < k25 - 0.005: proc_axes += 1

    # power score: count of 3 axes where signal IMPROVED (EV up, hard-hit up, xwOBACON up)
    pow_axes = 0
    if not np.isnan(ev25) and ev26 > ev25 + 0.3: pow_axes += 1
    if not np.isnan(hh25) and hh26 > hh25 + 0.01: pow_axes += 1
    if not np.isnan(xc25) and xc26 > xc25 + 0.01: pow_axes += 1

    # career-best flag
    career_best_xc = xc26 > csum['peak_xwobacon'] - 0.005  # within or above peak

    rows.append({
        'name': p['player_name'],
        'pos': p['position'],
        'src': p['source'],
        'own': round(p['percent_owned'],1) if 'percent_owned' in p else None,
        'inj': p.get('injured', False),
        'pa26': pa26,
        'xw26': round(xw26,3),
        'xc26': round(xc26,3),
        'd_xw': round(xw26-xw25,3) if not np.isnan(xw25) else None,
        'd_xc': round(xc26-xc25,3) if not np.isnan(xc25) else None,
        'shrunk_gap': round(shrunk_gap,3),
        'ci_lo': round(ci_lo,3),
        'distinguish': distinguishable,
        'pow_axes': pow_axes,
        'proc_axes': proc_axes,
        'career_best': career_best_xc,
        'peak_xc': round(csum['peak_xwobacon'],3),
        'peak_yr': csum['peak_year'],
        'mlb_yrs': csum['mlb_years'],
    })

cand = pd.DataFrame(rows)
print(f"\nCandidates with PA26 ≥ 80: {len(cand)}")

# Filter to BREAKOUT candidates: meaningful YoY improvement (d_xc >= +0.030) OR career-best xwOBACON
breakouts = cand[
    ((cand['d_xc'].notna()) & (cand['d_xc'] >= 0.030)) |
    (cand['career_best'] & (cand['xc26'] >= 0.380))
].copy()
breakouts = breakouts.sort_values(['shrunk_gap','xw26'], ascending=[False, False])

print(f"\nBreakout candidates (Δxwobacon ≥ +0.030 OR career-best xwOBACON ≥ .380): {len(breakouts)}")
print(breakouts.to_string(index=False))

# Save
breakouts.to_csv('data/research/breakout_sustainability_scan_2026-05-27.csv', index=False)

# ---- Sustainability scorecard verdicts ----
print("\n" + "="*80)
print("SUSTAINABILITY SCORECARD (auto-verdict)")
print("="*80)

def verdict(row):
    score = 0
    score += 1 if row['shrunk_gap'] >= 0.020 else 0
    score += 1 if row['proc_axes'] >= 2 else 0
    score += 1 if row['pow_axes'] >= 2 else 0
    score += 1 if row['distinguish'] else 0
    score += 1 if row['career_best'] else 0
    if score >= 4: return 'SUSTAINABLE'
    if score == 3: return 'NARROW BREAKOUT'
    if score == 2: return 'MIXED'
    return 'HOT STREAK / FRAGILE'

breakouts['verdict'] = breakouts.apply(verdict, axis=1)
print(breakouts[['name','pos','src','own','pa26','xw26','xc26','d_xc','shrunk_gap',
                 'pow_axes','proc_axes','career_best','distinguish','verdict']].to_string(index=False))
