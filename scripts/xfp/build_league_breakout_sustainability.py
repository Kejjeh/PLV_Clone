"""
League-wide breakout sustainability ranking.

Implements /league-breakout-sustainability skill. Pulls all 8 team rosters
+ FA pool, applies 5-axis sustainability scorecard, outputs tiered ranking.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import sys
import os
import unicodedata
from datetime import date

pd.set_option('display.width', 260)
pd.set_option('display.max_columns', 40)

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
from app.espn_connector import (
    get_all_teams,
    get_free_agents,
)
from plv_clone.league_state import LeagueState

MULTIYR = 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv'
HITTER_POSITIONS = {'C','1B','2B','3B','SS','OF','DH','MI','CI','LF','CF','RF','UTIL'}

# ---------------------------------------------------------------------------
# Name resolution
# ---------------------------------------------------------------------------

def fold(s):
    if pd.isna(s): return ''
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower().strip()


def build_name_resolver(df):
    """Build a name → batter_id lookup. Returns (resolver_fn, n_collisions)."""
    df = df.copy()
    df['__name_fold'] = df['player_name'].apply(fold)
    # most-recent-year row per (name_fold, batter) pair — keep all distinct batter IDs
    name_batters = (df.sort_values('year', ascending=False)
                    .drop_duplicates(['__name_fold', 'batter'])
                    [['__name_fold', 'batter']]
                    .groupby('__name_fold')['batter'].apply(list).to_dict())
    n_coll = sum(1 for v in name_batters.values() if len(v) > 1)
    def resolve(name):
        v = name_batters.get(fold(name))
        if v is None: return None
        return v[0]  # caller should handle collisions explicitly if known
    return resolve, n_coll, name_batters


# ---------------------------------------------------------------------------
# Pool assembly
# ---------------------------------------------------------------------------

def pull_pools():
    print("Pulling MY_ROSTER...")
    mine = LeagueState().my_roster_with_injuries()
    mine_hit = mine[mine['position'].isin(HITTER_POSITIONS)].copy()
    mine_hit['source'] = 'MY_ROSTER'
    mine_hit['team_name'] = 'Ligers'
    mine_hit['percent_owned'] = 100.0

    print("Pulling all 8 team rosters...")
    all_teams = get_all_teams()
    print(f"  all_teams shape: {all_teams.shape}  cols: {list(all_teams.columns)[:12]}...")
    all_hit = all_teams[all_teams['position'].isin(HITTER_POSITIONS)].copy()
    my_ids = set(mine_hit['player_id'].tolist())
    other_hit = all_hit[~all_hit['player_id'].isin(my_ids)].copy()
    other_hit['source'] = 'OTHER:' + other_hit['team_name'].astype(str)
    other_hit['injured'] = other_hit.get('injured', False)
    other_hit['percent_owned'] = 100.0

    print("Pulling FA pool (size=2000)...")
    fa = get_free_agents(size=2000)
    fa_hit = fa[fa['position'].isin(HITTER_POSITIONS)].copy()
    # FA pool doesn't have player_id — dedupe by (name, position) against rostered names
    rostered_names = set(
        all_hit['player_name'].fillna('').str.strip().str.lower().tolist()
    )
    fa_hit = fa_hit[~fa_hit['player_name'].fillna('').str.strip().str.lower().isin(rostered_names)].copy()
    fa_hit['player_id'] = None
    fa_hit['source'] = 'FA'
    fa_hit['team_name'] = None
    fa_hit['injured'] = False

    keep_cols = ['player_name', 'player_id', 'position', 'source', 'team_name',
                 'injured', 'percent_owned']
    pool = pd.concat([
        mine_hit[keep_cols],
        other_hit[keep_cols],
        fa_hit[keep_cols],
    ], ignore_index=True)
    print(f"  total pool: {len(pool)}  (MY={len(mine_hit)}, OTHER={len(other_hit)}, FA={len(fa_hit)})")
    return pool


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def score_candidate(pid, pool_row, df):
    sub = df[df['batter'] == pid].sort_values('year')
    if sub.empty:
        return None
    has_25 = (sub['year'] == 2025).any()
    has_26 = (sub['year'] == 2026).any()
    if not has_26:
        return None
    r26 = sub[sub['year'] == 2026].iloc[0]
    pa26 = int(r26['pa']) if pd.notna(r26['pa']) else 0
    if pa26 < 80:
        return None

    pks = sub[sub['pa'] >= 250]
    peak_xc = float(pks['xwoba_on_contact'].max()) if len(pks) else float(sub['xwoba_on_contact'].max())

    if not has_25:
        # No baseline — tag rookie debut
        return {
            'name': pool_row['player_name'], 'pos': pool_row['position'],
            'source': pool_row['source'], 'team': pool_row.get('team_name'),
            'own': round(float(pool_row.get('percent_owned') or 0.0), 1),
            'inj': bool(pool_row.get('injured', False)),
            'pa26': pa26,
            'xw26': round(float(r26['xwoba_per_pa']), 3),
            'xc26': round(float(r26['xwoba_on_contact']), 3),
            'd_xw': None, 'd_xc': None,
            'shrunk_gap': None,
            'pow_axes': None, 'proc_axes': None,
            'career_best': None, 'distinguish': None,
            'score': None, 'tier': 'ROOKIE_DEBUT', 'sub_tag': '',
            'peak_xc': round(peak_xc, 3), 'mlb_yrs': int(sub['year'].nunique()),
        }

    r25 = sub[sub['year'] == 2025].iloc[0]

    def f(row, col):
        v = row.get(col)
        return float(v) if pd.notna(v) else np.nan

    xw25, xc25 = f(r25, 'xwoba_per_pa'), f(r25, 'xwoba_on_contact')
    hh25, ev25 = f(r25, 'hard_hit_pct'), f(r25, 'ev90')
    k25, w25, ch25 = f(r25, 'k_pct'), f(r25, 'whiff_pct'), f(r25, 'chase_pct')

    xw26, xc26 = f(r26, 'xwoba_per_pa'), f(r26, 'xwoba_on_contact')
    hh26, ev26 = f(r26, 'hard_hit_pct'), f(r26, 'ev90')
    k26, w26, ch26 = f(r26, 'k_pct'), f(r26, 'whiff_pct'), f(r26, 'chase_pct')

    # Axis 1: Bayesian-shrunk gap
    k_prior = 150.0
    baseline = xw25 if not np.isnan(xw25) else (peak_xc * 0.78)
    shrunk_xw = (pa26 * xw26 + k_prior * baseline) / (pa26 + k_prior)
    shrunk_gap = shrunk_xw - baseline
    axis1 = shrunk_gap >= 0.020

    # Axis 2: process axes improved
    proc_axes = sum([
        (not np.isnan(w25)) and (w26 < w25 - 0.005),
        (not np.isnan(ch25)) and (ch26 < ch25 - 0.005),
        (not np.isnan(k25)) and (k26 < k25 - 0.005),
    ])
    axis2 = proc_axes >= 2

    # Axis 3: power axes improved
    pow_axes = sum([
        (not np.isnan(ev25)) and (ev26 > ev25 + 0.3),
        (not np.isnan(hh25)) and (hh26 > hh25 + 0.01),
        (not np.isnan(xc25)) and (xc26 > xc25 + 0.01),
    ])
    axis3 = pow_axes >= 2

    # Axis 4: CI distinguishability
    se = 0.39 / np.sqrt(pa26)
    ci_lo, ci_hi = xw26 - 1.96 * se, xw26 + 1.96 * se
    distinguish = (not np.isnan(xw25)) and (xw25 < ci_lo or xw25 > ci_hi)
    axis4 = distinguish

    # Axis 5: within 5pt of career-best xwOBACON
    career_best = (xc26 >= peak_xc - 0.005)
    axis5 = career_best

    score = int(axis1) + int(axis2) + int(axis3) + int(axis4) + int(axis5)

    # Tier
    if shrunk_gap < -0.020 and (not np.isnan(xw25)) and (xw26 < xw25 - 0.020):
        tier = 'DECLINE'
    elif score >= 4:
        tier = 'SUSTAINABLE'
    elif score == 3:
        tier = 'NARROW'
    elif score == 2:
        tier = 'MIXED'
    elif score == 1:
        tier = 'HOT_STREAK'
    else:
        tier = 'HOT_STREAK_DEEP'

    sub_tag = ''
    if pow_axes >= 2 and proc_axes == 0:
        sub_tag = '[POWER-ONLY]'
    elif proc_axes >= 2 and pow_axes == 0:
        sub_tag = '[DISCIPLINE-ONLY]'

    return {
        'name': pool_row['player_name'], 'pos': pool_row['position'],
        'source': pool_row['source'], 'team': pool_row.get('team_name'),
        'own': round(float(pool_row.get('percent_owned') or 0.0), 1),
        'inj': bool(pool_row.get('injured', False)),
        'pa26': pa26,
        'xw26': round(xw26, 3), 'xc26': round(xc26, 3),
        'd_xw': round(xw26 - xw25, 3) if not np.isnan(xw25) else None,
        'd_xc': round(xc26 - xc25, 3) if not np.isnan(xc25) else None,
        'shrunk_gap': round(shrunk_gap, 3),
        'pow_axes': pow_axes, 'proc_axes': proc_axes,
        'career_best': career_best, 'distinguish': distinguish,
        'score': score, 'tier': tier, 'sub_tag': sub_tag,
        'peak_xc': round(peak_xc, 3), 'mlb_yrs': int(sub['year'].nunique()),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== League-wide breakout sustainability scan ===\n")

    df = pd.read_csv(MULTIYR)
    resolve, n_coll, _ = build_name_resolver(df)
    print(f"Name resolver built ({n_coll} same-name collisions in source data — first ID used; check resolve_batter_id for explicit cases)")

    pool = pull_pools()
    pool['mlbam'] = pool['player_name'].apply(resolve)
    matched = pool[pool['mlbam'].notna()].copy()
    unmatched = pool[pool['mlbam'].isna()]
    print(f"\nMatched MLBAM: {len(matched)}   Unmatched: {len(unmatched)}")
    if len(unmatched):
        print(f"  unmatched sample: {unmatched['player_name'].head(10).tolist()}")

    print("\nScoring each candidate...")
    rows = []
    for _, p in matched.iterrows():
        out = score_candidate(int(p['mlbam']), p, df)
        if out is not None:
            rows.append(out)
    scored = pd.DataFrame(rows)
    print(f"Scored: {len(scored)}")
    print(f"  By tier: {scored['tier'].value_counts().to_dict()}")

    out_path = f'data/research/league_breakout_sustainability_{date.today()}.csv'
    scored.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")

    # Tiered display
    TIER_ORDER = ['SUSTAINABLE', 'NARROW', 'MIXED', 'HOT_STREAK', 'HOT_STREAK_DEEP', 'DECLINE', 'ROOKIE_DEBUT']
    cols_show = ['name', 'pos', 'source', 'own', 'pa26', 'xw26', 'xc26',
                 'd_xc', 'shrunk_gap', 'pow_axes', 'proc_axes', 'sub_tag', 'inj']

    for tier in TIER_ORDER:
        t = scored[scored['tier'] == tier].copy()
        if t.empty: continue
        t = t.sort_values('xw26', ascending=False)
        print(f"\n{'='*100}")
        print(f"=== TIER: {tier} ({len(t)} hitters) ===")
        print('='*100)
        print(t[cols_show].to_string(index=False))

    # ---- Action callouts ----
    print("\n" + "="*100)
    print("=== ACTION CALLOUTS ===")
    print("="*100)
    print("\nTop FA SUSTAINABLE adds (own% < 50%, sorted by shrunk_gap desc):")
    fa_sus = scored[(scored['tier']=='SUSTAINABLE') & (scored['source']=='FA') & (scored['own']<50)] \
                   .sort_values('shrunk_gap', ascending=False)
    print(fa_sus[['name','pos','own','xw26','xc26','d_xc','shrunk_gap','pow_axes','proc_axes','sub_tag']].head(15).to_string(index=False))

    print("\nTop trade targets (OTHER team rosters, MIXED or HOT_STREAK, may be selling on perceived breakout):")
    targets = scored[scored['source'].str.startswith('OTHER:', na=False)
                     & scored['tier'].isin(['MIXED','HOT_STREAK','HOT_STREAK_DEEP','DECLINE'])] \
                   .sort_values('xw26', ascending=False)
    print(targets[['name','pos','source','xw26','xc26','d_xc','shrunk_gap','tier','sub_tag']].head(15).to_string(index=False))

    print("\nMY_ROSTER drop watch (HOT_STREAK or DECLINE — players you're holding on hope):")
    drops = scored[(scored['source']=='MY_ROSTER')
                   & scored['tier'].isin(['HOT_STREAK','HOT_STREAK_DEEP','DECLINE'])]
    if drops.empty:
        print("  (none — your roster is well-positioned on sustainability)")
    else:
        print(drops[['name','pos','xw26','xc26','d_xc','shrunk_gap','tier','sub_tag','inj']].to_string(index=False))


if __name__ == '__main__':
    main()
