"""Compute per-team aggregate scores from triangulate results and rank the league."""
import pandas as pd, sys, io
if sys.platform == 'win32' and sys.stdout is sys.__stdout__:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

df = pd.read_csv('data/research/triangulate_universe/all_teams_results.csv')
df = df.rename(columns={'category': 'team'})

# Verdict scoring (signed contribution per player)
def verdict_pts(v):
    v = str(v)
    if 'STRONG HOLD' in v: return 5
    if v.startswith('BUY'):
        if 'archetype breakout' in v: return 4
        if 'process upgrade' in v: return 3
        if 'under-the-radar' in v: return 3
        if 'model anchored' in v: return 3
        if 'outcomes only' in v: return 2
        return 3
    # 4th-lens HOLD overrides — positive but weaker than BUY (verdict was upgraded
    # from FADE/CAUTION; player is held with confidence but not a buy target)
    if v.startswith('HOLD'): return 1
    if v.startswith('FADE'): return -3
    if v.startswith('CAUTION'): return -1
    return 0  # MIXED, etc.

df['vpts'] = df['verdict'].apply(verdict_pts)

# Per-team aggregate
def is_trending_up(t): return str(t) == 'TRENDING_UP'
def is_trending_dn(t): return str(t) == 'TRENDING_DOWN'

agg = df.groupby('team').agg(
    n=('player_name','count'),
    n_strong=('verdict', lambda s: s.str.contains('STRONG HOLD', na=False).sum()),
    n_buy=('verdict', lambda s: s.str.startswith('BUY', na=False).sum()),
    n_fade=('verdict', lambda s: s.str.startswith('FADE', na=False).sum()),
    n_caution=('verdict', lambda s: s.str.startswith('CAUTION', na=False).sum()),
    n_mixed=('verdict', lambda s: (s == 'MIXED — see profile').sum()),
    n_up=('arche_traj', lambda s: s.apply(is_trending_up).sum()),
    n_dn=('arche_traj', lambda s: s.apply(is_trending_dn).sum()),
    arche_avg=('arche_overall', 'mean'),
    arche_top5_avg=('arche_overall', lambda s: s.nlargest(5).mean()),
    vpts_total=('vpts', 'sum'),
).round(2)

# Composite score: verdict points (weighted heavily) + avg archetype OVERALL
# Normalize both, blend 60/40 verdict vs archetype
import numpy as np
agg['composite'] = (
    0.5 * (agg['vpts_total'] - agg['vpts_total'].mean()) / agg['vpts_total'].std() +
    0.3 * (agg['arche_avg'] - agg['arche_avg'].mean()) / agg['arche_avg'].std() +
    0.2 * (agg['arche_top5_avg'] - agg['arche_top5_avg'].mean()) / agg['arche_top5_avg'].std()
).round(2)

agg = agg.sort_values('composite', ascending=False)
agg.insert(0, 'rank', range(1, len(agg)+1))

agg.to_csv('data/research/triangulate_universe/team_ranking.csv')
print("\n=== LEAGUE POWER RANKING (composite of verdicts + archetype quality) ===\n")
print(agg.to_string())

# Per-team top contributors + drags
print("\n\n=== PER-TEAM HIGHLIGHTS ===")
for team in agg.index:
    sub = df[df['team']==team].sort_values('vpts', ascending=False)
    print(f"\n--- {team} (rank #{agg.loc[team,'rank']}, composite {agg.loc[team,'composite']:+.2f}) ---")
    top = sub.head(3)[['player_name','bucket','verdict','arche_overall','arche_traj']]
    bot = sub[sub['vpts']<0][['player_name','bucket','verdict','arche_overall','arche_traj']].head(3)
    print("TOP-3 contributors:")
    for _,r in top.iterrows():
        print(f"  {r['player_name']:25s} {r['bucket']:3s} | {r['verdict']:35s} arche={r['arche_overall']}/{r['arche_traj']}")
    if len(bot):
        print("Biggest drags:")
        for _,r in bot.iterrows():
            print(f"  {r['player_name']:25s} {r['bucket']:3s} | {r['verdict']:35s} arche={r['arche_overall']}/{r['arche_traj']}")
