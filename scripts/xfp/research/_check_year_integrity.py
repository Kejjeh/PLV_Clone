"""CRITICAL integrity check: is the 'year' param real, or did Savant ignore it
and return duplicated data? Statcast bat-tracking launched 2024, so 2023 rows
are suspect. Test: for players in BOTH 2023 and 2024, are their metric values
identical (=> mislabeled duplicate) or different (=> real distinct years)?"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / 'data' / 'research'

def check(path, key_cols, metrics, label):
    print(f"\n{'='*70}\n{label}  ({path})")
    df = pd.read_csv(RES / path)
    # restrict to hitters if player_type exists
    if 'player_type' in df.columns:
        df = df[df['player_type'].astype(str).str.lower().str.startswith('bat')]
    years = sorted(df['year'].unique())
    print(f"  years: {years}")
    # pairwise: for consecutive years, how many players overlap & how many have IDENTICAL metric vector
    for i in range(len(years)-1):
        ya, yb = years[i], years[i+1]
        a = df[df['year']==ya].set_index('mlbam_id')
        b = df[df['year']==yb].set_index('mlbam_id')
        common = a.index.intersection(b.index)
        common = common[~common.duplicated()]
        a2, b2 = a.loc[common], b.loc[common]
        # avoid dup-index explosions
        a2 = a2[~a2.index.duplicated()]; b2 = b2[~b2.index.duplicated()]
        common = a2.index.intersection(b2.index)
        a2, b2 = a2.loc[common], b2.loc[common]
        m = [c for c in metrics if c in a2.columns and c in b2.columns]
        if not m or len(common)==0:
            print(f"  {ya}->{yb}: no common/metrics")
            continue
        # row-identical across ALL metrics?
        diff = (a2[m].fillna(-999).values - b2[m].fillna(-999).values)
        identical_rows = (np.abs(diff).sum(axis=1) < 1e-9).sum()
        # correlation of one headline metric across the two years
        hm = m[0]
        valid = a2[hm].notna() & b2[hm].notna()
        r = np.corrcoef(a2[hm][valid], b2[hm][valid])[0,1] if valid.sum()>2 else np.nan
        print(f"  {ya}->{yb}: n_common={len(common)}  identical_rows(all metrics)={identical_rows} "
              f"({100*identical_rows/len(common):.1f}%)  r[{hm}]={r:.3f}")
        # show a sample player's values both years
        if len(common):
            pid = common[0]
            print(f"     sample id={pid}: {ya} {hm}={a2.loc[pid,hm]:.4f} | {yb} {hm}={b2.loc[pid,hm]:.4f}")

check('bat_tracking_all_2023_2026.csv', ['mlbam_id'],
      ['avg_bat_speed','blast_per_swing','swing_length','swords','hard_swing_rate'],
      'BAT-TRACKING MAIN')

check('swing_timing_miss_dist_2023_2026.csv', ['mlbam_id'],
      ['whiff_rate','miss_distance','perfect_percent','lined_up_percent'],
      'SWING TIMING + MISS DIST')
