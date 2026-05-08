"""milb_carryover_screen.py — which MiLB pitcher stats predict next-year MLB?

For every (pitcher, year, level) row in the MiLB substrate, look up that
pitcher's MLB performance in year T+1.  Compute correlation between candidate
MiLB stats and MLB outcomes (SP fp_per_start_actual, RP fp_per_g).

Output: data/research/milb_carryover_pitchers.csv
  feature, level, target, n, cor, recommendation

Decision rule: features with |cor| >= 0.10 enter MT2's feature pool.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'research' / 'milb_carryover_pitchers.csv'

MILB = pd.read_csv(CACHE / 'milb_pitchers_2015_2026.csv')
SP = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv').rename(columns={'year': 'season'})
RP = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')

CANDIDATE_FEATURES = [
    'k_pct', 'bb_pct', 'k_minus_bb_pct',
    'hr_per_9', 'h_per_9', 'er_per_9', 'ip_per_g',
    'era', 'whip',
    'battersFaced', 'inningsPitched', 'gamesStarted', 'gamesPitched',
]

# Roll up MiLB to one row per (pitcher, season, level) with weighted rates.
# (Each json row is already (pitcher, season, team) but in some cases a player
# moved teams within a level — collapse those.)
def consolidate_milb(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ['battersFaced', 'strikeOuts', 'baseOnBalls', 'homeRuns',
              'hits', 'earnedRuns', 'gamesPitched', 'gamesStarted', 'ip']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    grp = df.groupby(['pitcher', 'season', 'level'], as_index=False).agg(
        battersFaced=('battersFaced', 'sum'),
        strikeOuts=('strikeOuts', 'sum'),
        baseOnBalls=('baseOnBalls', 'sum'),
        homeRuns=('homeRuns', 'sum'),
        hits=('hits', 'sum'),
        earnedRuns=('earnedRuns', 'sum'),
        gamesPitched=('gamesPitched', 'sum'),
        gamesStarted=('gamesStarted', 'sum'),
        ip=('ip', 'sum'),
        name=('name', 'first'),
    )
    bf = grp['battersFaced'].replace(0, np.nan)
    ip = grp['ip'].replace(0, np.nan)
    g = grp['gamesPitched'].replace(0, np.nan)
    grp['k_pct'] = grp['strikeOuts'] / bf
    grp['bb_pct'] = grp['baseOnBalls'] / bf
    grp['k_minus_bb_pct'] = grp['k_pct'] - grp['bb_pct']
    grp['hr_per_9'] = grp['homeRuns'] * 9 / ip
    grp['h_per_9'] = grp['hits'] * 9 / ip
    grp['er_per_9'] = grp['earnedRuns'] * 9 / ip
    grp['ip_per_g'] = grp['ip'] / g
    grp['era'] = grp['earnedRuns'] * 9 / ip
    grp['whip'] = (grp['baseOnBalls'] + grp['hits']) / ip
    grp['inningsPitched'] = grp['ip']
    return grp


milb = consolidate_milb(MILB)
print(f'MiLB consolidated: {len(milb)} (pitcher, season, level) rows')

# Build year T+1 MLB targets
sp_next = SP[['pitcher', 'season', 'gs', 'ip_per_start', 'fp_per_start_actual']].copy()
sp_next.columns = ['pitcher', 'next_season', 'mlb_gs', 'mlb_ip_per_start', 'mlb_fp_per_start']
sp_next = sp_next[sp_next['mlb_gs'] >= 5]

rp_next = RP[['pitcher', 'season', 'g', 'ip', 'fp', 'fp_per_g', 'fp_per_ip', 'role']].copy()
rp_next.columns = ['pitcher', 'next_season', 'mlb_g', 'mlb_ip', 'mlb_fp_total',
                    'mlb_fp_per_g', 'mlb_fp_per_ip', 'mlb_role']
rp_next = rp_next[rp_next['mlb_g'] >= 20]

milb['next_season'] = milb['season'] + 1

joined_sp = milb.merge(sp_next, on=['pitcher', 'next_season'], how='inner')
joined_rp = milb.merge(rp_next, on=['pitcher', 'next_season'], how='inner')

print(f'MiLB->MLB SP transitions: {len(joined_sp)}')
print(f'MiLB->MLB RP transitions: {len(joined_rp)}')


def correlate(df: pd.DataFrame, target: str, level: str | None,
              min_milb_bf: int = 50) -> list[dict]:
    sub = df.copy()
    if level is not None:
        sub = sub[sub['level'] == level]
    sub = sub[sub['battersFaced'] >= min_milb_bf]
    if len(sub) < 30:
        return []
    out = []
    for f in CANDIDATE_FEATURES:
        x = pd.to_numeric(sub[f], errors='coerce')
        y = pd.to_numeric(sub[target], errors='coerce')
        m = x.notna() & y.notna()
        if m.sum() < 30:
            continue
        cor = float(np.corrcoef(x[m], y[m])[0, 1])
        out.append({
            'feature': f,
            'level': level or 'BOTH',
            'target': target,
            'n': int(m.sum()),
            'cor': round(cor, 3),
            'recommendation': 'KEEP' if abs(cor) >= 0.10 else 'DROP',
            'min_milb_bf': min_milb_bf,
        })
    return out


rows: list[dict] = []
for level in ('AAA', 'AA', None):
    rows += correlate(joined_sp, 'mlb_fp_per_start', level, min_milb_bf=50)
    rows += correlate(joined_rp, 'mlb_fp_per_g', level, min_milb_bf=50)

# Higher sample threshold pass — more reliable but smaller n
for level in ('AAA', 'AA', None):
    rows += correlate(joined_sp, 'mlb_fp_per_start', level, min_milb_bf=120)
    rows += correlate(joined_rp, 'mlb_fp_per_g', level, min_milb_bf=120)

out = pd.DataFrame(rows).sort_values(['target', 'level', 'min_milb_bf', 'feature'])
out.to_csv(OUT, index=False)
print(f'\nWrote {OUT} ({len(out)} rows)')

print('\n--- SP target (MLB fp_per_start), min_milb_bf=120, by level ---')
sub = out[(out['target'] == 'mlb_fp_per_start') & (out['min_milb_bf'] == 120)]
print(sub[['feature', 'level', 'n', 'cor', 'recommendation']].to_string(index=False))

print('\n--- RP target (MLB fp_per_g), min_milb_bf=120, by level ---')
sub = out[(out['target'] == 'mlb_fp_per_g') & (out['min_milb_bf'] == 120)]
print(sub[['feature', 'level', 'n', 'cor', 'recommendation']].to_string(index=False))

print('\n--- Features kept by ANY (level, target, sample) cell ---')
keep = out[out['recommendation'] == 'KEEP']['feature'].value_counts()
print(keep.to_string())
