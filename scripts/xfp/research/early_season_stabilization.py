"""EARLY-SEASON STABILIZATION (Part A of the early bat-speed detector).

The early-warning premise: bat speed is reliable in a handful of swings, while
outcome rates (wOBA, hard-hit%, xwOBACON, K%) need months of PA to stabilize.
If true, then early in a season bat speed is a trustworthy "getting better/worse"
read while the box-score rates are still noise.

Method: split-half reliability at sample size n. For each metric, take every
(player, season) with >= 2n events of that metric's grain (swings for bat-speed,
PA for wOBA/K%, BIP for hard-hit/xwOBACON), randomly split into two disjoint
n-event halves, correlate the half-means across players. Sweep n. The n where
reliability crosses ~0.7 is the 'stabilization point'. Pooled over 2024+2025
(seasons with Opening-Day bat tracking); 2026 added for swing metrics only.
"""
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(20260616)
ROOT = Path(__file__).resolve().parents[3]
C = ROOT / 'data' / 'research' / 'xfp_cache'

PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play',
             'sac_bunt','catcher_interf'}
K_EVENTS = {'strikeout','strikeout_double_play'}
COLS = ['batter','bat_speed','swing_length','attack_angle','events','type',
        'launch_speed','woba_value','estimated_woba_using_speedangle']

def load(years):
    frames = []
    for y in years:
        df = pd.read_parquet(C / f'statcast_{y}.parquet', columns=COLS)
        df['psn'] = df['batter'].astype('Int64').astype(str) + '_' + str(y)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)

def per_event(df, grain):
    """Return {player_season: np.array of per-event metric values}."""
    if grain == 'bat_speed':
        s = df[df['bat_speed'].notna() & (df['bat_speed'] > 10)]
        return {k: v.values for k, v in s.groupby('psn')['bat_speed']}
    if grain == 'swing_length':
        s = df[df['swing_length'].notna() & df['bat_speed'].notna()]
        return {k: v.values for k, v in s.groupby('psn')['swing_length']}
    if grain == 'attack_angle':
        s = df[df['attack_angle'].notna() & df['bat_speed'].notna()]
        return {k: v.values for k, v in s.groupby('psn')['attack_angle']}
    if grain in ('woba', 'k'):
        pa = df[df['events'].isin(PA_EVENTS)].copy()
        if grain == 'woba':
            pa['v'] = pa['woba_value'].fillna(0.0)
        else:
            pa['v'] = pa['events'].isin(K_EVENTS).astype(float)
        return {k: v.values for k, v in pa.groupby('psn')['v']}
    if grain in ('hard_hit', 'xwobacon'):
        bip = df[df['type'] == 'X'].copy()
        if grain == 'hard_hit':
            bip = bip[bip['launch_speed'].notna()]
            bip['v'] = (bip['launch_speed'] >= 95).astype(float)
        else:
            bip = bip[bip['estimated_woba_using_speedangle'].notna()]
            bip['v'] = bip['estimated_woba_using_speedangle']
        return {k: v.values for k, v in bip.groupby('psn')['v']}

def reliability(vbp, n, n_splits=30):
    elig = {k: v for k, v in vbp.items() if len(v) >= 2 * n}
    if len(elig) < 30:
        return np.nan, len(elig)
    rs = []
    for _ in range(n_splits):
        a, b = [], []
        for v in elig.values():
            idx = rng.permutation(len(v))
            a.append(v[idx[:n]].mean()); b.append(v[idx[n:2*n]].mean())
        rs.append(np.corrcoef(a, b)[0, 1])
    return float(np.mean(rs)), len(elig)

print("Loading 2024-2025 (PA/BIP/swings) + 2026 (swings)...")
df2 = load([2024, 2025])
df3 = load([2024, 2025, 2026])  # swings only get the extra year

GRAINS = {
    'bat_speed (swing)':      ('bat_speed', df3),
    'swing_length (swing)':   ('swing_length', df3),
    'attack_angle (swing)':   ('attack_angle', df3),
    'hard_hit% (BIP)':        ('hard_hit', df2),
    'xwOBACON (BIP)':         ('xwobacon', df2),
    'wOBA (PA)':              ('woba', df2),
    'K% (PA)':                ('k', df2),
}
NS = [5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 300, 400]

print("\nSPLIT-HALF RELIABILITY by sample size n (events of the metric's grain)")
print(f"{'metric':<22}" + ''.join(f'{n:>6}' for n in NS))
results = {}
for label, (grain, src) in GRAINS.items():
    vbp = per_event(src, grain)
    row = []
    for n in NS:
        r, ne = reliability(vbp, n)
        row.append(r)
    results[label] = row
    print(f"{label:<22}" + ''.join(('  n/a ' if np.isnan(r) else f'{r:>6.2f}') for r in row))

# stabilization point: smallest n with reliability >= 0.70
print("\nStabilization point (smallest n with split-half r >= 0.70):")
for label, row in results.items():
    pt = next((NS[i] for i, r in enumerate(row) if (not np.isnan(r)) and r >= 0.70), None)
    grain = GRAINS[label][0]
    unit = 'swings' if 'swing' in label or grain in ('bat_speed','swing_length','attack_angle') else ('PA' if grain in ('woba','k') else 'BIP')
    print(f"  {label:<22} {'>= '+str(pt)+' '+unit if pt else 'NOT reached by n=400'}")
