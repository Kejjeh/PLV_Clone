# -*- coding: utf-8 -*-
"""Amendment A: fantasy-roster dilution of same-club correlation + direct
realized-vs-modeled fantasy-team-day SD. Read-only. Pre-registered before run."""
import itertools

import numpy as np
import pandas as pd

ROSTERS = 'data/research/matchup_rosters_history.parquet'
BOX = 'data/research/xfp_cache/boxscore_hitters.parquet'
SIGMA_DAILY = 3.2502          # the sigma memo's truth-SD constant (flat fallback, labelled)
MIN_SHARED = 10
SEED = 20260801

ro = pd.read_parquet(ROSTERS)
print('roster store: %d rows, %s..%s, %d teams' % (
    len(ro), ro['snapshot_date'].min(), ro['snapshot_date'].max(),
    ro['team_id'].nunique()))

# active hitters only: exclude pitchers and IL slots (BE counts active per house rule)
act = ro[(~ro['position'].isin(['SP', 'RP', 'P']))
         & (~ro['lineup_slot'].astype(str).str.upper().isin(['IL', 'IR']))].copy()
act['snapshot_date'] = pd.to_datetime(act['snapshot_date']).dt.date
act = act.dropna(subset=['mlbam_id'])
act['mlbam_id'] = act['mlbam_id'].astype(int)

box = pd.read_parquet(BOX)
box['game_date'] = pd.to_datetime(box['game_date']).dt.date
day_fp = (box.groupby(['mlbam_id', 'game_date'], as_index=False)
             .agg(fp=('fp_h', 'sum'), club=('team_id', 'first')))

# join: roster-day x player daily FP (played that day)
m = act.merge(day_fp, left_on=['mlbam_id', 'snapshot_date'],
              right_on=['mlbam_id', 'game_date'], how='inner')
print('roster-day player rows with a game: %d over %d roster-days' % (
    len(m), m.groupby(['team_id', 'snapshot_date']).ngroups))

# ── A1: pairwise correlation within fantasy rosters ─────────────────────────
pair_rows = []
for tid, g in m.groupby('team_id'):
    wide = g.pivot_table(index='snapshot_date', columns='mlbam_id',
                         values='fp', aggfunc='sum')
    club_of = g.groupby('mlbam_id')['club'].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) else None)
    for a, b in itertools.combinations(wide.columns, 2):
        sub = wide[[a, b]].dropna()
        if len(sub) < MIN_SHARED:
            continue
        va, vb = sub[a].values, sub[b].values
        if va.std() == 0 or vb.std() == 0:
            continue
        r = float(np.corrcoef(va, vb)[0, 1])
        same_club = club_of.get(a) == club_of.get(b)
        pair_rows.append((tid, a, b, len(sub), r, bool(same_club)))

pairs = pd.DataFrame(pair_rows,
                     columns=['tid', 'a', 'b', 'n', 'r', 'same_club'])
w = pairs['n'].values.astype(float)
rho_f = float(np.average(pairs['r'].values, weights=w))
rng = np.random.default_rng(SEED)
idx = np.arange(len(pairs))
boots = np.array([np.average(pairs['r'].values[t], weights=w[t])
                  for t in (rng.choice(idx, len(idx), True)
                            for _ in range(2000))])
lo, hi = np.percentile(boots, [2.5, 97.5])
sc = pairs[pairs['same_club']]
cc = pairs[~pairs['same_club']]
print()
print('A1: fantasy pairs=%d (same-club %d / cross-club %d)'
      % (len(pairs), len(sc), len(cc)))
print('    rho_fantasy = %+.4f  [%+.4f, %+.4f]' % (rho_f, lo, hi))
if len(sc):
    print('    same-club subset  = %+.4f (n=%d)'
          % (np.average(sc['r'], weights=sc['n']), len(sc)))
print('    cross-club subset = %+.4f (n=%d)'
      % (np.average(cc['r'], weights=cc['n']), len(cc)))
per_rd = m.groupby(['team_id', 'snapshot_date'])['club'].agg(
    lambda s: sum(v * (v - 1) / 2 for v in s.value_counts().values))
print('    same-club pairs per roster-day: mean %.2f' % per_rd.mean())

# ── A2: realized vs modeled team-day SD ─────────────────────────────────────
td = (m.groupby(['team_id', 'snapshot_date'])
        .agg(total=('fp', 'sum'), k=('fp', 'size')).reset_index())
td['modeled_sd'] = np.sqrt(td['k']) * SIGMA_DAILY
td['centered'] = td['total'] - td.groupby('team_id')['total'].transform('mean')
raw_ratio = float(td['centered'].std(ddof=1) / td['modeled_sd'].mean())
td['day_demeaned'] = td['centered'] - td.groupby('snapshot_date')['centered'].transform('mean')
dd_ratio = float(td['day_demeaned'].std(ddof=1) / td['modeled_sd'].mean())
print()
print('A2: %d team-days | mean k=%.1f | modeled per-day SD (flat %.4f/player): %.2f FP'
      % (len(td), td['k'].mean(), SIGMA_DAILY, td['modeled_sd'].mean()))
print('    realized/modeled ratio  raw (team-demeaned): %.3f' % raw_ratio)
print('    realized/modeled ratio  day+team demeaned:   %.3f' % dd_ratio)
per_team = (td.groupby('team_id')
              .apply(lambda g: g['centered'].std(ddof=1) / g['modeled_sd'].mean(),
                     include_groups=False))
print('    per-team raw ratios: %s'
      % np.array2string(per_team.values, precision=2))
