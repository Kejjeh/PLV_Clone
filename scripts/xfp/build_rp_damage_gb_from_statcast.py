"""
build_rp_damage_gb_from_statcast.py — derive RP-season batted-ball aggregates
from raw statcast parquet files.

For each (pitcher, year) in the qualifying RP cohort (from relievers_multiyr_2018_2026.csv),
aggregate all BIP (bb_type non-null) the pitcher allowed in that year and compute:

  gb_pct       — ground_ball / (gb+fb+ld+pu)
  barrel_pct   — launch_speed_angle == 6 / BIP
  hard_hit_pct — (launch_speed >= 95) / BIP
  xwobacon     — mean(estimated_woba_using_speedangle) over BIP

NOTE on RP-PA identification: rather than per-PA role inference (expensive and
imprecise), we aggregate ALL pitcher-year BIP and then join to the qualifying
RP cohort from relievers_multiyr (G>=20, TBF>=50, role tagged as RP). For
pitchers who were SP and RP in the same year (rare), the BIP count is the
full-year total, which slightly contaminates pure-RP rate stats. The audit
shows the swing-and-miss / GB rate signature dominates the contamination
for almost all relievers since most relief BIP are >>50% of their year-total
BIP. This matches the simpler-proxy approach the audit suggested.

Output: data/research/xfp_cache/rp_damage_gb_2018_2026.csv
  columns: pitcher, year, n_bip, gb_pct, barrel_pct, hard_hit_pct, xwobacon

BIP floor: n_bip >= 30 (validation cohort threshold from RP_SUBDOMAIN_VALIDATION.md).
"""
from __future__ import annotations
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
RP_MULTIYR = REPO / 'data/research/xfp_cache/relievers_multiyr_2018_2026.csv'
STATCAST_DIR = REPO / 'data/research/xfp_cache'
OUT_CSV = REPO / 'data/research/xfp_cache/rp_damage_gb_2018_2026.csv'

YEARS = list(range(2017, 2027))
G_FLOOR = 20
TBF_FLOOR = 50
BIP_FLOOR = 30


def main():
    print('Loading qualifying RP cohort from relievers_multiyr_2018_2026.csv...', flush=True)
    rp = pd.read_csv(RP_MULTIYR)
    rp_co = rp[(rp['g'] >= G_FLOOR) & (rp['tbf_api'] >= TBF_FLOOR)][['pitcher', 'year']].copy()
    rp_co = rp_co.drop_duplicates()
    qualifying_n = len(rp_co)
    print(f'  qualifying RP-seasons (G>={G_FLOOR}, TBF>={TBF_FLOOR}): {qualifying_n}', flush=True)
    print(f'  per-year: {rp_co.groupby("year").size().to_dict()}', flush=True)

    all_rows = []
    cols = ['pitcher', 'bb_type', 'launch_speed', 'launch_angle',
            'launch_speed_angle', 'estimated_woba_using_speedangle']

    for yr in YEARS:
        pq_path = STATCAST_DIR / f'statcast_{yr}.parquet'
        if not pq_path.exists():
            print(f'  {yr}: MISSING {pq_path}', flush=True)
            continue
        sc = pd.read_parquet(pq_path, columns=cols)
        # BIP only: bb_type non-null
        bip = sc[sc['bb_type'].notna() & (sc['bb_type'] != '')].copy()
        bip['is_gb'] = (bip['bb_type'] == 'ground_ball').astype(int)
        bip['is_fb'] = (bip['bb_type'] == 'fly_ball').astype(int)
        bip['is_ld'] = (bip['bb_type'] == 'line_drive').astype(int)
        bip['is_pu'] = (bip['bb_type'] == 'popup').astype(int)
        bip['is_barrel'] = (bip['launch_speed_angle'].fillna(0) == 6).astype(int)
        bip['is_hardhit'] = (bip['launch_speed'].fillna(0) >= 95).astype(int)

        agg = bip.groupby('pitcher').agg(
            n_bip=('bb_type', 'size'),
            gb_n=('is_gb', 'sum'),
            fb_n=('is_fb', 'sum'),
            ld_n=('is_ld', 'sum'),
            pu_n=('is_pu', 'sum'),
            barrel_n=('is_barrel', 'sum'),
            hardhit_n=('is_hardhit', 'sum'),
            xwoba_sum=('estimated_woba_using_speedangle', 'sum'),
            xwoba_n=('estimated_woba_using_speedangle', lambda x: x.notna().sum()),
        ).reset_index()
        denom_bbtype = (agg['gb_n'] + agg['fb_n'] + agg['ld_n'] + agg['pu_n']).replace(0, np.nan)
        agg['gb_pct'] = agg['gb_n'] / denom_bbtype
        agg['barrel_pct'] = agg['barrel_n'] / agg['n_bip'].replace(0, np.nan)
        agg['hard_hit_pct'] = agg['hardhit_n'] / agg['n_bip'].replace(0, np.nan)
        agg['xwobacon'] = agg['xwoba_sum'] / agg['xwoba_n'].replace(0, np.nan)
        agg['year'] = yr
        out = agg[['pitcher', 'year', 'n_bip', 'gb_pct', 'barrel_pct',
                   'hard_hit_pct', 'xwobacon']].copy()
        all_rows.append(out)
        print(f'  {yr}: {len(out)} pitchers w/ BIP; ' +
              f'after floor n_bip>={BIP_FLOOR}: {(out["n_bip"] >= BIP_FLOOR).sum()}', flush=True)

    full = pd.concat(all_rows, ignore_index=True)
    # Apply BIP floor
    full = full[full['n_bip'] >= BIP_FLOOR].copy()

    # Join coverage check vs qualifying RP cohort
    joined = rp_co.merge(full, on=['pitcher', 'year'], how='inner')
    join_cov = len(joined) / qualifying_n
    print(f'\n[join] qualifying RP-seasons matched in statcast-derived: {len(joined)} / {qualifying_n} ({join_cov:.1%})', flush=True)
    per_year_join = joined.groupby('year').size().to_dict()
    per_year_qual = rp_co.groupby('year').size().to_dict()
    print('[join] per-year join coverage:', flush=True)
    for y in YEARS:
        q = per_year_qual.get(y, 0)
        j = per_year_join.get(y, 0)
        if q > 0:
            print(f'   {y}: {j} / {q} ({j/q:.1%})', flush=True)

    # Write output (full statcast-derived table, all pitcher-years meeting BIP floor)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    full.to_csv(OUT_CSV, index=False)
    print(f'\n[write] {OUT_CSV}  rows={len(full)}', flush=True)
    print(f'   year coverage: {sorted(full["year"].unique().tolist())}', flush=True)
    print(f'   mean BIP per RP-year (joined cohort): {joined["n_bip"].mean():.1f}', flush=True)
    print(f'   median BIP per RP-year (joined cohort): {joined["n_bip"].median():.1f}', flush=True)

    # Spot-check known sinkerballers
    name_map = pd.read_csv(RP_MULTIYR, usecols=['pitcher', 'name', 'year'])
    spot_names = ['Devin Williams', 'Aroldis Chapman', 'Clay Holmes', 'Trevor Megill']
    print('\n[spot-check] known sinkerballers / strikeout RPs (recent year):', flush=True)
    for nm in spot_names:
        matches = name_map[name_map['name'] == nm]
        if matches.empty:
            print(f'   {nm}: not found in relievers_multiyr', flush=True)
            continue
        pid = matches['pitcher'].iloc[0]
        recent = joined[(joined['pitcher'] == pid) & (joined['year'] >= 2023)].sort_values('year')
        for _, r in recent.iterrows():
            print(f'   {nm:25s} {int(r["year"])}: n_bip={int(r["n_bip"]):3d}  '
                  f'gb_pct={r["gb_pct"]:.3f}  barrel_pct={r["barrel_pct"]:.3f}  '
                  f'hard_hit_pct={r["hard_hit_pct"]:.3f}  xwobacon={r["xwobacon"]:.3f}', flush=True)


if __name__ == '__main__':
    main()
