"""projection_ensemble.py — combine our model with public projections.

Pulls public projection systems from FanGraphs (we already have a fetcher in
scripts/fetch_fangraphs.py for current-season-to-date stats; FanGraphs also
publishes ZiPS/Steamer/ATC RoS as CSVs at the same domain). For now this
module reads any *_projections_2026.csv files dropped into data/research/
and ensembles them with our rh3/rp3 outputs.

Drop locations expected:
  data/research/external_projections/zips_hitters_2026.csv
  data/research/external_projections/zips_pitchers_2026.csv
  data/research/external_projections/steamer_hitters_2026.csv
  data/research/external_projections/steamer_pitchers_2026.csv
  data/research/external_projections/atc_hitters_2026.csv
  data/research/external_projections/atc_pitchers_2026.csv

The script tolerates missing files; ensembles whichever it finds. Maps each
external system to a per-PA fp estimate using their AVG/HR/BB/K columns,
then averages across systems and blends with rh3.

Output:
  data/outputs/projection_ensemble_hitters.csv
  data/outputs/projection_ensemble_pitchers.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np
import re

from plv_clone.paths import ROOT
from plv_clone.fantasy.scoring import pitcher_fp
EXT = ROOT / 'data' / 'research' / 'external_projections'
OUT = ROOT / 'data' / 'outputs'




def hitter_fp_per_pa(row) -> float:
    """Convert a projection row's slash line into expected core_fp per PA.

    core_fp = TB + BB + HBP - K. Expected per PA:
      = AVG*(SLG/AVG)*AB/PA + BB/PA + HBP/PA - K/PA  [TB ≈ SLG*AB]
    Most projection systems publish PA, AB, H, 2B, 3B, HR, BB, HBP, SO.
    """
    pa = row.get('PA') or row.get('pa')
    if not pa or pa <= 0:
        return np.nan
    h = row.get('H', 0)
    d2 = row.get('2B', 0)
    d3 = row.get('3B', 0)
    hr = row.get('HR', 0)
    bb = row.get('BB', 0)
    hbp = row.get('HBP', 0)
    so = row.get('SO', row.get('K', 0))
    singles = h - d2 - d3 - hr
    tb = singles + 2 * d2 + 3 * d3 + 4 * hr
    return float((tb + bb + hbp - so) / pa)


def pitcher_fp_per_g(row) -> float:
    """Approx pitcher FP/game. Our SP fp = K + IP*3.3 - H - 2*ER - BB - HBP.

    Projections give per-season totals; divide by GS or G.
    """
    g = row.get('GS') or row.get('G') or 0
    if not g:
        return np.nan
    ip = row.get('IP', 0)
    k = row.get('SO', row.get('K', 0))
    h = row.get('H', 0)
    er = row.get('ER', 0)
    bb = row.get('BB', 0)
    hbp = row.get('HBP', 0)
    fp = pitcher_fp(k=k, ip=ip, h=h, er=er, bb=bb, hbp=hbp)
    return float(fp / g)


def load_external(kind: str) -> pd.DataFrame:
    """kind = 'hitters' or 'pitchers'. Returns long DataFrame with mlb_id, system, value."""
    if not EXT.exists():
        return pd.DataFrame()
    rows = []
    for path in sorted(EXT.glob(f'*_{kind}_*.csv')):
        system = path.stem.split('_')[0]
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f'  skip {path.name}: {e}')
            continue
        if 'xMLBAMID' not in df.columns:
            print(f'  skip {path.name}: no xMLBAMID')
            continue
        df['mlb_id'] = pd.to_numeric(df['xMLBAMID'], errors='coerce')
        df = df[df['mlb_id'].notna()].copy()
        df['mlb_id'] = df['mlb_id'].astype(int)
        if kind == 'hitters':
            df['proj_fp_per_pa'] = df.apply(hitter_fp_per_pa, axis=1)
            df = df[df['proj_fp_per_pa'].notna()]
            for _, r in df.iterrows():
                rows.append({'mlb_id': int(r['mlb_id']), 'system': system,
                             'fp_per_pa': r['proj_fp_per_pa'], 'pa': r.get('PA', 0)})
        else:
            df['proj_fp_per_g'] = df.apply(pitcher_fp_per_g, axis=1)
            df = df[df['proj_fp_per_g'].notna()]
            for _, r in df.iterrows():
                rows.append({'mlb_id': int(r['mlb_id']), 'system': system,
                             'fp_per_g': r['proj_fp_per_g'],
                             'gs': r.get('GS', r.get('G', 0))})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    EXT.mkdir(parents=True, exist_ok=True)

    # Hitters — join on mlb_id (rh3 'batter' col == MLBAM player_id)
    rh = PROJECTIONS.rh3()
    rh['mlb_id'] = rh['batter'].astype(int)
    h_ext = load_external('hitters')
    if not h_ext.empty:
        h_pivot = h_ext.pivot_table(index='mlb_id', columns='system', values='fp_per_pa', aggfunc='mean')
        h_pivot = h_pivot.reset_index()
        h_pivot['ext_n_systems'] = h_pivot.drop(columns='mlb_id').notna().sum(axis=1)
        h_pivot['ext_mean_fp_per_pa'] = h_pivot.drop(columns=['mlb_id', 'ext_n_systems']).mean(axis=1)
        rh_full = rh.merge(h_pivot, on='mlb_id', how='left')
        # Ensemble: 60% rh3 + 40% ext (only when ext available)
        rh_full['ensemble_fp_per_pa'] = np.where(
            rh_full['ext_mean_fp_per_pa'].notna(),
            0.6 * rh_full['xfp_rh3_per_pa'] + 0.4 * rh_full['ext_mean_fp_per_pa'],
            rh_full['xfp_rh3_per_pa']
        )
        rh_full['ensemble_fp_per_game'] = rh_full['ensemble_fp_per_pa'] * (rh_full['xfp_rh3_per_game'] / rh_full['xfp_rh3_per_pa'].replace(0, np.nan))
        f1 = OUT / 'projection_ensemble_hitters.csv'
        rh_full.to_csv(f1, index=False)
        print(f'  wrote {f1} ({len(rh_full)} hitters, {h_pivot["ext_n_systems"].sum():.0f} ext rows)')
    else:
        print(f'  no external hitter projections in {EXT}')
        print(f'  drop CSVs there with columns: Name, PA, AB, H, 2B, 3B, HR, BB, HBP, SO')
        # Still write a pass-through ensemble = rh3
        rh['ext_n_systems'] = 0
        rh['ensemble_fp_per_pa'] = rh['xfp_rh3_per_pa']
        rh['ensemble_fp_per_game'] = rh['xfp_rh3_per_game']
        rh.to_csv(OUT / 'projection_ensemble_hitters.csv', index=False)

    # Pitchers
    rp = PROJECTIONS.rp3()
    rp['mlb_id'] = rp['pitcher'].astype(int)
    p_ext = load_external('pitchers')
    if not p_ext.empty:
        p_pivot = p_ext.pivot_table(index='mlb_id', columns='system', values='fp_per_g', aggfunc='mean')
        p_pivot = p_pivot.reset_index()
        p_pivot['ext_n_systems'] = p_pivot.drop(columns='mlb_id').notna().sum(axis=1)
        p_pivot['ext_mean_fp_per_g'] = p_pivot.drop(columns=['mlb_id', 'ext_n_systems']).mean(axis=1)
        rp_full = rp.merge(p_pivot, on='mlb_id', how='left')
        rp_full['ensemble_fp_per_start'] = np.where(
            rp_full['ext_mean_fp_per_g'].notna(),
            0.6 * rp_full['xfp_rp3_per_start'] + 0.4 * rp_full['ext_mean_fp_per_g'],
            rp_full['xfp_rp3_per_start']
        )
        f2 = OUT / 'projection_ensemble_pitchers.csv'
        rp_full.to_csv(f2, index=False)
        print(f'  wrote {f2} ({len(rp_full)} pitchers, {p_pivot["ext_n_systems"].sum():.0f} ext rows)')
    else:
        print(f'  no external pitcher projections in {EXT}')
        rp['ext_n_systems'] = 0
        rp['ensemble_fp_per_start'] = rp['xfp_rp3_per_start']
        rp.to_csv(OUT / 'projection_ensemble_pitchers.csv', index=False)


if __name__ == '__main__':
    main()
