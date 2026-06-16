"""LIVE 2026 BAT-SPEED TRENDING BOARD (Part C — the application).

Applies the validated early bat-speed detector to current 2026 data: who is
mechanically up/down vs their established baseline, with the outcome read as
confirmation. Bat speed is fully stabilized by now (2026 regulars have 200+
swings vs the 20-swing stabilization point). Display/context only.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
C = ROOT / 'data' / 'research' / 'xfp_cache'
PA_EVENTS = {'single','double','triple','home_run','strikeout','strikeout_double_play',
             'walk','intent_walk','hit_by_pitch','field_out','force_out',
             'grounded_into_double_play','double_play','triple_play','fielders_choice',
             'fielders_choice_out','field_error','sac_fly','sac_fly_double_play',
             'sac_bunt','catcher_interf'}
COLS = ['batter','events','type','launch_speed','woba_value','woba_denom',
        'estimated_woba_using_speedangle','bat_speed']

def season(y, min_sw):
    df = pd.read_parquet(C / f'statcast_{y}.parquet', columns=COLS)
    rows = {}
    for bid, sub in df.groupby('batter'):
        sw = sub[sub['bat_speed'].notna() & (sub['bat_speed'] > 10)]
        bip = sub[sub['type'] == 'X']
        if len(sw) < min_sw:
            continue
        rows[bid] = dict(bat_speed=sw['bat_speed'].mean(), n_sw=len(sw),
                         xwobacon=bip['estimated_woba_using_speedangle'].mean() if len(bip) else np.nan)
    return pd.DataFrame(rows).T

cur = season(2026, 80)          # current (stabilized: 80+ swings)
base25 = season(2025, 200)
base24 = season(2024, 200)
base = base25.copy()
base.loc[base.index.difference(base25.index)] = base24  # 2025 primary
# fill missing-from-2025 with 2024
miss = cur.index.difference(base25.index).intersection(base24.index)
base = pd.concat([base25, base24.loc[miss]])

names = (pd.read_csv(C / 'hitters_multiyr_2015_2026.csv', usecols=['batter','player_name','year'])
         .query('year>=2025').drop_duplicates('batter').set_index('batter')['player_name'])

out = cur.join(base[['bat_speed','xwobacon']], rsuffix='_base', how='inner')
out['d_bat_speed'] = out['bat_speed'] - out['bat_speed_base']
out['d_xwobacon'] = out['xwobacon'] - out['xwobacon_base']
out['name'] = [names.get(i, str(i)) for i in out.index]
# population SD of YoY bat-speed change for z-scoring
sd = out['d_bat_speed'].std()
out['z'] = out['d_bat_speed'] / sd
print(f"n hitters with 2026(>=80 sw) + baseline: {len(out)}   bat-speed Δ SD={sd:.2f} mph\n")

def show(title, df):
    print(f"=== {title} ===")
    print(f"  {'hitter':<22}{'2026 bs':>8}{'base bs':>8}{'Δ mph':>7}{'z':>6}{'ΔxwOBAcon':>11}")
    for _, r in df.iterrows():
        print(f"  {r['name'][:21]:<22}{r['bat_speed']:>8.1f}{r['bat_speed_base']:>8.1f}"
              f"{r['d_bat_speed']:>+7.2f}{r['z']:>+6.1f}{r['d_xwobacon']:>+11.3f}")

show("TOP RISERS — bat speed up vs baseline (mechanical breakout watch)",
     out.sort_values('d_bat_speed', ascending=False).head(15))
print()
show("TOP DECLINERS — bat speed down vs baseline (physical decline watch)",
     out.sort_values('d_bat_speed').head(15))

# how often does a bat-speed move agree in direction with the xwOBACON move?
v = out.dropna(subset=['d_xwobacon'])
agree = ((v['d_bat_speed'] > 0) == (v['d_xwobacon'] > 0)).mean()
print(f"\nDirectional agreement (Δbat_speed vs ΔxwOBACON, 2026 so far): {100*agree:.0f}%  (n={len(v)})")
out.sort_values('d_bat_speed').to_csv(ROOT/'data'/'research'/'bat_speed_trending_2026.csv')
print("saved -> data/research/bat_speed_trending_2026.csv")
