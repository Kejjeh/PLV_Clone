"""scan_hitter_trajectory.py — L21d archetype shift scanner.

For every 2026 hitter with pa_last21 >= 60:
  1. Rate L21d window on 2025 baseline (so the 20-80 scale is interpretable)
  2. Compare bucket-level shifts vs (a) 2025 archetype, (b) 2026 season-to-date archetype
  3. Surface upward / downward / within-year (STD vs L21d) divergences

Used for Mode 2 (scan) of /hitter-archetype with rolling-window data."""
from __future__ import annotations
import pandas as pd, numpy as np, json
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')


def bucket(x):
    if x >= 60: return 'PLUS'
    if x >= 40: return 'AVG'
    return 'MINUS'


def bucket_delta(a, b):
    if pd.isna(a) or pd.isna(b): return None
    order = {'MINUS': 0, 'AVG': 1, 'PLUS': 2}
    return order[bucket(b)] - order[bucket(a)]


def main():
    # 1. Latest 2026 L21d snapshot per batter
    r = pd.read_csv(REPO / 'data/research/xfp_cache/rolling_hitters_2018_2026.csv')
    r = r[r['year'] == 2026].copy()
    r['cutoff_date'] = pd.to_datetime(r['cutoff_date'])
    latest = r.sort_values('cutoff_date').groupby('batter').tail(1).copy()
    print(f'2026 latest snapshots: {len(latest)} batters, cutoff={latest["cutoff_date"].max().date()}')

    latest['babip_last21'] = (
        (latest['h_last21'] - latest['hr_last21']) /
        (latest['ab_last21'] - latest['k_last21'] - latest['hr_last21']).clip(lower=1)
    ).clip(0, 1)

    qual = latest[latest['pa_last21'] >= 60].copy()
    print(f'qualified (pa_last21 >= 60): {len(qual)}')

    # 2. Build 2025 league baseline from the source CSV (raw rates)
    src = pd.read_csv(REPO / 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv')
    s25 = src[src['year'] == 2025].copy()
    s25['babip'] = ((s25['h'] - s25['hr']) / (s25['ab'] - s25['k'] - s25['hr']).clip(lower=1)).clip(0, 1)
    baseline = {}
    for c in ['contact_pct', 'k_pct', 'babip', 'xwoba_on_contact',
              'barrel_pct', 'hard_hit_pct', 'iso', 'hr_per_pa',
              'bb_pct', 'chase_pct']:
        baseline[c] = (s25[c].mean(), s25[c].std())

    def rate(val, key, invert=False):
        mu, sd = baseline[key]
        if sd == 0 or pd.isna(val):
            return 50
        z = (val - mu) / sd
        if invert:
            z = -z
        return int(round(min(max(50 + 10 * z, 20), 80)))

    # 3. Rate L21d using available components
    def rate_row(row):
        rC = rate(row['contact_pct_last21'], 'contact_pct')
        rK = rate(row['k_pct_last21'], 'k_pct', invert=True)
        rB = rate(row['babip_last21'], 'babip')
        rX = rate(row['xwoba_on_contact_last21'], 'xwoba_on_contact')
        rBR = rate(row['barrel_pct_last21'], 'barrel_pct')
        rHH = rate(row['hard_hit_pct_last21'], 'hard_hit_pct')
        rI = rate(row['iso_last21'], 'iso')
        rHR = rate(row['hr_per_pa_last21'], 'hr_per_pa')
        rBB = rate(row['bb_pct_last21'], 'bb_pct')
        rCH = rate(row['chase_pct_last21'], 'chase_pct', invert=True)
        return pd.Series({
            'CONTACT_raw': np.mean([rC, rK, rB, rX]),
            'POWER_raw': np.mean([rBR, rHH, rI, rHR]),
            'DISCIPLINE_raw': np.mean([rBB, rCH]),
        })

    rated = qual.apply(rate_row, axis=1)
    qual = pd.concat([qual.reset_index(drop=True), rated.reset_index(drop=True)], axis=1)

    # 4. Re-rescale composites within the L21d population (match master semantics)
    def rescale(s):
        mu, sd = s.mean(), s.std()
        z = (s - mu) / (sd if sd else 1)
        return (50 + 10 * z).clip(20, 80).round(0).astype(int)
    qual['C_L21'] = rescale(qual['CONTACT_raw'])
    qual['P_L21'] = rescale(qual['POWER_raw'])
    qual['D_L21'] = rescale(qual['DISCIPLINE_raw'])
    qual['cell_L21'] = (qual['C_L21'].apply(bucket) + '/'
                       + qual['P_L21'].apply(bucket) + '/'
                       + qual['D_L21'].apply(bucket))

    # 5. Map cell -> archetype label
    defs = json.load(open(REPO / 'data/research/hitter_archetype_definitions.json'))
    qual['arch_L21'] = qual['cell_L21'].map(lambda x: defs.get(x, {'label': 'UNK'})['label'])

    # 6. Join with master via career panel (which carries batter ID) to get 2026 STD + 2025 baselines
    panel = pd.read_parquet(REPO / 'data/research/hitter_archetype_career_panel.parquet')
    p26 = panel[panel['year'] == 2026][['player_name', 'batter', 'CONTACT', 'POWER', 'DISCIPLINE',
                                          'archetype', 'age_tier', 'boundary_tier', 'fp_per_pa']].rename(
        columns={'CONTACT': 'C_STD', 'POWER': 'P_STD', 'DISCIPLINE': 'D_STD',
                 'archetype': 'arch_STD', 'fp_per_pa': 'fp_pa_STD'})
    p25 = panel[panel['year'] == 2025][['batter', 'CONTACT', 'POWER', 'DISCIPLINE',
                                          'archetype', 'fp_per_pa']].rename(
        columns={'CONTACT': 'C_25', 'POWER': 'P_25', 'DISCIPLINE': 'D_25',
                 'archetype': 'arch_25', 'fp_per_pa': 'fp_pa_25'})
    qual = qual.merge(p26, on='batter', how='left')
    qual = qual.merge(p25, on='batter', how='left')

    qual['dC_25_L21'] = qual.apply(lambda r: bucket_delta(r.get('C_25'), r.get('C_L21')), axis=1)
    qual['dP_25_L21'] = qual.apply(lambda r: bucket_delta(r.get('P_25'), r.get('P_L21')), axis=1)
    qual['dD_25_L21'] = qual.apply(lambda r: bucket_delta(r.get('D_25'), r.get('D_L21')), axis=1)
    qual['net_change'] = (qual['dC_25_L21'].fillna(0) + qual['dP_25_L21'].fillna(0)
                          + qual['dD_25_L21'].fillna(0))

    # 7. Upward shifters
    print()
    print('=' * 100)
    print('UPWARD ARCHETYPE SHIFTERS (L21d 2026 vs 2025) — sorted by net bucket gain')
    print('=' * 100)
    up = qual[(qual['arch_L21'] != qual['arch_25']) & (qual['net_change'] >= 1)
              & (qual['arch_25'].notna())].sort_values('net_change', ascending=False)
    for _, x in up.head(30).iterrows():
        bumps = []
        if x['dC_25_L21'] and x['dC_25_L21'] > 0: bumps.append('C+')
        if x['dP_25_L21'] and x['dP_25_L21'] > 0: bumps.append('P+')
        if x['dD_25_L21'] and x['dD_25_L21'] > 0: bumps.append('D+')
        age = x.get('age_tier') or '?'
        print(f'  {x.player_name:25s} {age:9s} PA21={int(x.pa_last21):3d}  '
              f'25: C={int(x.C_25)} P={int(x.P_25)} D={int(x.D_25)} ({x.arch_25:14s})  '
              f'-> L21d: C={int(x.C_L21)} P={int(x.P_L21)} D={int(x.D_L21)} ({x.arch_L21:14s}) [{" ".join(bumps)}]')

    # 8. Downward shifters
    print()
    print('=' * 100)
    print('DOWNWARD ARCHETYPE SHIFTERS (L21d 2026 vs 2025) — sorted by net bucket loss')
    print('=' * 100)
    down = qual[(qual['arch_L21'] != qual['arch_25']) & (qual['net_change'] <= -1)
                & (qual['arch_25'].notna())].sort_values('net_change')
    for _, x in down.head(30).iterrows():
        drops = []
        if x['dC_25_L21'] and x['dC_25_L21'] < 0: drops.append('C-')
        if x['dP_25_L21'] and x['dP_25_L21'] < 0: drops.append('P-')
        if x['dD_25_L21'] and x['dD_25_L21'] < 0: drops.append('D-')
        age = x.get('age_tier') or '?'
        print(f'  {x.player_name:25s} {age:9s} PA21={int(x.pa_last21):3d}  '
              f'25: C={int(x.C_25)} P={int(x.P_25)} D={int(x.D_25)} ({x.arch_25:14s})  '
              f'-> L21d: C={int(x.C_L21)} P={int(x.P_L21)} D={int(x.D_L21)} ({x.arch_L21:14s}) [{" ".join(drops)}]')

    # 9. STD-vs-L21d divergence (within 2026)
    print()
    print('=' * 100)
    print('STD-vs-L21d DIVERGENCE — 2026 season-to-date archetype != current L21d archetype')
    print('=' * 100)
    div = qual[(qual['arch_STD'].notna()) & (qual['arch_L21'] != qual['arch_STD'])].copy()
    div['std_l21_shift'] = div.apply(
        lambda r: (bucket_delta(r.get('C_STD'), r.get('C_L21')) or 0)
                 + (bucket_delta(r.get('P_STD'), r.get('P_L21')) or 0)
                 + (bucket_delta(r.get('D_STD'), r.get('D_L21')) or 0), axis=1)
    div = div.sort_values('std_l21_shift', ascending=False)
    print(f'  {len(div)} STD-vs-L21d divergences')
    for _, x in div.head(20).iterrows():
        direction = '↑' if x.std_l21_shift > 0 else '↓'
        print(f'  {direction}{abs(int(x.std_l21_shift))} {x.player_name:25s} '
              f'STD: C={int(x.C_STD)} P={int(x.P_STD)} D={int(x.D_STD)} ({x.arch_STD:14s})  '
              f'-> L21d: C={int(x.C_L21)} P={int(x.P_L21)} D={int(x.D_L21)} ({x.arch_L21})')

    qual.to_csv(REPO / 'data/research/hitter_trajectory_scan_2026.csv', index=False)
    print()
    print('wrote data/research/hitter_trajectory_scan_2026.csv')


if __name__ == '__main__':
    main()
