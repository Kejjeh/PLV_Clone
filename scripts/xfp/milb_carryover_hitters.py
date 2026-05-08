"""milb_carryover_hitters.py — which MiLB hitter stats predict next-year MLB?

Mirrors milb_carryover_screen.py for hitters. Target: MLB fp_per_pa.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'research' / 'milb_carryover_hitters.csv'

MILB = pd.read_csv(CACHE / 'milb_hitters_2015_2026.csv')
HIT = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')

CANDIDATE_FEATURES = [
    'k_pct', 'bb_pct', 'k_minus_bb_pct',
    'hr_per_pa', 'xbh_per_pa', 'iso',
    'sb_attempts_per_pa', 'plateAppearances', 'gamesPlayed',
    'avg', 'obp', 'slg', 'ops',
]


def consolidate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    sum_fields = ['plateAppearances', 'atBats', 'hits', 'doubles', 'triples',
                  'homeRuns', 'baseOnBalls', 'strikeOuts', 'hitByPitch',
                  'stolenBases', 'caughtStealing', 'gamesPlayed', 'totalBases']
    for c in sum_fields:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    grp = df.groupby(['batter', 'season', 'level'], as_index=False).agg(
        **{c: (c, 'sum') for c in sum_fields}, name=('name', 'first'))
    pa = grp['plateAppearances'].replace(0, np.nan)
    ab = grp['atBats'].replace(0, np.nan)
    grp['k_pct'] = grp['strikeOuts'] / pa
    grp['bb_pct'] = grp['baseOnBalls'] / pa
    grp['k_minus_bb_pct'] = grp['k_pct'] - grp['bb_pct']
    grp['hr_per_pa'] = grp['homeRuns'] / pa
    grp['xbh_per_pa'] = (grp['doubles'] + grp['triples'] + grp['homeRuns']) / pa
    grp['iso'] = (grp['totalBases'] - grp['hits']) / ab
    grp['sb_attempts_per_pa'] = (grp['stolenBases'] + grp['caughtStealing']) / pa
    grp['avg'] = grp['hits'] / ab
    grp['obp'] = (grp['hits'] + grp['baseOnBalls'] + grp['hitByPitch']) / pa
    grp['slg'] = grp['totalBases'] / ab
    grp['ops'] = grp['obp'] + grp['slg']
    return grp


milb = consolidate(MILB)
print(f'MiLB consolidated: {len(milb)} (batter, season, level) rows')

# Hit target table
hit = HIT.copy()
year_col = 'year' if 'year' in hit.columns else 'season'
print(f'  hitters_multiyr cols include: pa={"pa" in hit.columns}, fp_per_pa={"fp_per_pa_actual" in hit.columns}')

hit_next = hit[['batter', year_col, 'pa', 'fp_per_pa_actual']].copy()
hit_next.columns = ['batter', 'next_season', 'mlb_pa', 'mlb_fp_per_pa']
hit_next = hit_next[hit_next['mlb_pa'] >= 100]

milb['next_season'] = milb['season'] + 1
joined = milb.merge(hit_next, on=['batter', 'next_season'], how='inner')
print(f'MiLB->MLB hitter transitions: {len(joined)}')


def correlate(df: pd.DataFrame, level: str | None, min_pa: int) -> list[dict]:
    sub = df.copy()
    if level is not None:
        sub = sub[sub['level'] == level]
    sub = sub[sub['plateAppearances'] >= min_pa]
    if len(sub) < 30:
        return []
    out = []
    for f in CANDIDATE_FEATURES:
        x = pd.to_numeric(sub[f], errors='coerce')
        y = pd.to_numeric(sub['mlb_fp_per_pa'], errors='coerce')
        m = x.notna() & y.notna()
        if m.sum() < 30:
            continue
        cor = float(np.corrcoef(x[m], y[m])[0, 1])
        out.append({
            'feature': f,
            'level': level or 'BOTH',
            'min_milb_pa': min_pa,
            'n': int(m.sum()),
            'cor': round(cor, 3),
            'recommendation': 'KEEP' if abs(cor) >= 0.10 else 'DROP',
        })
    return out


rows = []
for level in ('AAA', 'AA', None):
    for min_pa in (80, 200):
        rows += correlate(joined, level, min_pa)
out = pd.DataFrame(rows).sort_values(['min_milb_pa', 'level', 'feature'])
out.to_csv(OUT, index=False)
print(f'Wrote {OUT} ({len(out)} rows)')

print('\n--- AAA hitter carryover, min_pa=200 ---')
sub = out[(out['level'] == 'AAA') & (out['min_milb_pa'] == 200)]
print(sub[['feature', 'n', 'cor', 'recommendation']].to_string(index=False))

print('\n--- AA hitter carryover, min_pa=200 ---')
sub = out[(out['level'] == 'AA') & (out['min_milb_pa'] == 200)]
print(sub[['feature', 'n', 'cor', 'recommendation']].to_string(index=False))
