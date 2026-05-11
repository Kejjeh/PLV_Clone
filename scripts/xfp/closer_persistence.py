"""closer_persistence.py — does the early-season save leader stay the closer?

For each (MLB team, year), find:
  A. Top saver through ~midseason (split_day=60, roughly June 1)
  B. Top saver in late season (split_day=120, roughly mid-August)

  Match rate = % of team-years where A == B.

This tells us: if I see a non-Ligers MLB team where a specific RP is
hoarding saves through midseason, what's the probability THEY are the
closer of record in September? If high (>70%), early-season SV leader
is a reliable predictor of playoff-window closer. If low, closer roles
churn and we should track current usage closely.

Bonus: identify the actionable "rising closer" pattern — pitcher who
gained ground in the second half vs first half (e.g., took over a job).

Output: data/research/closer_persistence.csv + console findings
"""
from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

MIDSEASON_SPLIT = 60   # roughly day 60 of the season (early June)
LATE_SPLIT = 120       # roughly day 120 (mid-August)
MIN_SAVES_TO_QUALIFY = 4  # team needs ≥4 saves at the snapshot to be meaningful


def main():
    rel = pd.read_csv(CACHE / 'rolling_relievers_2018_2026.csv')
    # Restrict to years with both midseason + late snapshots available
    mid = rel[rel['split_day'] == MIDSEASON_SPLIT].copy()
    late = rel[rel['split_day'] == LATE_SPLIT].copy()
    print(f'Midseason snapshots: {len(mid)}, Late snapshots: {len(late)}')

    # For each (team_abbr, year), top saver per snapshot
    def top_saver(df):
        df = df[df['sv_to'].fillna(0) >= MIN_SAVES_TO_QUALIFY]
        if df.empty: return None
        idx = df['sv_to'].idxmax()
        row = df.loc[idx]
        return {'pitcher': int(row['pitcher']),
                'sv': int(row['sv_to']),
                'fp_per_g': float(row.get('fp_per_g_lag1', 0) or 0)}

    rows = []
    for (team, year), mid_grp in mid.groupby(['team_abbr', 'year']):
        if pd.isna(team): continue
        mid_top = top_saver(mid_grp)
        if mid_top is None: continue
        late_grp = late[(late['team_abbr'] == team) & (late['year'] == year)]
        late_top = top_saver(late_grp)
        if late_top is None: continue
        rows.append({
            'team': team, 'year': year,
            'mid_pitcher': mid_top['pitcher'],
            'mid_sv': mid_top['sv'],
            'late_pitcher': late_top['pitcher'],
            'late_sv': late_top['sv'],
            'same_closer': mid_top['pitcher'] == late_top['pitcher'],
        })
    df = pd.DataFrame(rows)
    print(f'\nTotal team-year comparisons: {len(df)}')

    persistence_rate = df['same_closer'].mean()
    print(f'\n=== HEADLINE ===')
    print(f'Closer persistence rate (mid → late season): {persistence_rate*100:.1f}%')
    print(f'  Across {len(df)} team-years, midseason save leader was '
          f'STILL late-season save leader in {persistence_rate*100:.1f}% of cases.')

    # Per-year breakdown
    print(f'\n=== Per-year persistence ===')
    yr_summary = df.groupby('year').agg(
        n=('team', 'count'),
        persistence=('same_closer', 'mean')).reset_index()
    for _, r in yr_summary.iterrows():
        print(f'  {int(r["year"])}: {r["persistence"]*100:>5.1f}%  (n={int(r["n"])})')

    # Examples where closer CHANGED (the interesting cases)
    changed = df[~df['same_closer']]
    print(f'\n=== {len(changed)} examples where closer CHANGED midseason → late ===')

    # Attach names for readability
    name_map = pd.read_csv(CACHE / 'mlb_player_id_name.csv') if (CACHE / 'mlb_player_id_name.csv').exists() else None
    if name_map is not None:
        name_lookup = dict(zip(name_map['mlb_id'].astype(int), name_map['name']))
        changed = changed.copy()
        changed['mid_name'] = changed['mid_pitcher'].map(lambda p: name_lookup.get(int(p), str(p)))
        changed['late_name'] = changed['late_pitcher'].map(lambda p: name_lookup.get(int(p), str(p)))

    print(f'{"YEAR":>4s} {"TEAM":<5s} {"MID CLOSER":<25s} {"LATE CLOSER":<25s} {"MID_SV":>7s} {"LATE_SV":>7s}')
    for _, r in changed.head(30).iterrows():
        mn = r.get('mid_name', str(r['mid_pitcher']))
        ln = r.get('late_name', str(r['late_pitcher']))
        print(f'  {int(r["year"]):>4d} {r["team"]:<5s} {mn:<25s} {ln:<25s} '
              f'{int(r["mid_sv"]):>7d} {int(r["late_sv"]):>7d}')

    df.to_csv(RES / 'closer_persistence.csv', index=False)
    print(f'\nwrote {RES / "closer_persistence.csv"}')

    # Current 2026 midseason leaders (predict late-season closers)
    cur = mid[mid['year'] == 2026].copy()
    cur = cur[cur['sv_to'].fillna(0) >= MIN_SAVES_TO_QUALIFY]
    if cur.empty:
        # If split_day=60 not in 2026 yet, try the latest available split
        recent_2026 = rel[rel['year'] == 2026]
        if not recent_2026.empty:
            latest = recent_2026['split_day'].max()
            print(f'\n2026 only has split_day up to {latest}, using that for projection')
            cur = recent_2026[recent_2026['split_day'] == latest]
            cur = cur[cur['sv_to'].fillna(0) >= MIN_SAVES_TO_QUALIFY]

    if not cur.empty and name_map is not None:
        # Top saver per team in 2026
        top26 = cur.sort_values('sv_to', ascending=False).drop_duplicates('team_abbr')
        top26['name'] = top26['pitcher'].map(lambda p: name_lookup.get(int(p), str(p)))
        print(f'\n=== 2026 current team save leaders (projected late-season closers '
              f'at {persistence_rate*100:.0f}% confidence) ===')
        for _, r in top26.sort_values('sv_to', ascending=False).iterrows():
            print(f'  {r["team_abbr"]:<5s} {r["name"]:<25s} SV={int(r["sv_to"])}')


if __name__ == '__main__':
    main()
