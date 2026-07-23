"""build_inhouse_stuff.py — in-house Stuff+ fallback (FG-scale calibrated).

WHY (2026-07-20): the FG Stuff+ scrape is Cloudflare-gated and silently froze
for 6 days — every stuff-lens consumer (sp_stuff_model -> boards / floor /
extra_lenses) was reading a 7/14 snapshot. We already compute two in-house
stuff-quality metrics NIGHTLY from our own Statcast substrate:

  1. archetype STUFF (20-80, build_sp_archetypes step 2.6) — head-to-head
     validated vs FG Stuff+ 2026-06-06: predictively EQUAL on forward RoS
     FP/start (clean partial r 0.291 vs FG 0.298), registered verdict
     **FALLBACK-ONLY** (outcome-derived + loses sub-gs6 rookies). This
     builder IMPLEMENTS that registered fallback verdict — it is not a new
     signal promotion (Rule 9 not triggered; FG stays primary when fresh).
  2. PLV (pl_plv_model, r~0.85 vs Pitcher List's published PLV;
     pitcher_plv_targets_2026.csv, nightly) — fills the rookie gap
     (pitch-count-gated, not gs-gated).

METHOD: quantile-map each source onto the FG stuff_plus scale using the
latest FG snapshot as the calibration anchor (rank-based -> monotone, exact
FG scale). Compose: arch where available (gs>=6 universe), else PLV
(pitches>=200). Emit per-row `stuff_source` provenance.

Output: data/research/fg_asof/stuff_inhouse_2026.csv
Consumer: sp_stuff_model.load_2026() overrides stuff_plus from this file
ONLY when the FG snapshot is stale (>2d) — loud provenance line when active.

Run: nightly refresh (after archetypes 2.6 + PLV boards) or ad-hoc:
    python -X utf8 scripts/xfp/build_inhouse_stuff.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FG_CSV = ROOT / 'data' / 'research' / 'fg_asof' / 'fg_pit_2026_current.csv'
ARCH_CSV = ROOT / 'data' / 'research' / 'sp_ratings_master.csv'
PLV_CSV = ROOT / 'data' / 'outputs' / 'pitcher_plv_targets_2026.csv'
OUT_CSV = ROOT / 'data' / 'research' / 'fg_asof' / 'stuff_inhouse_2026.csv'

SEASON = 2026
PLV_MIN_PITCHES = 200
MIN_OVERLAP = 40          # refuse to calibrate a source on fewer anchor pairs


def quantile_map(src: pd.Series, anchor_src: pd.Series, anchor_dst: pd.Series) -> pd.Series:
    """Map src values onto anchor_dst's scale by rank position within
    anchor_src (monotone; ties averaged by interp). All inputs numeric."""
    a_src = np.sort(anchor_src.dropna().values.astype(float))
    a_dst = np.sort(anchor_dst.dropna().values.astype(float))
    if len(a_src) < 2 or len(a_dst) < 2:
        return pd.Series(np.nan, index=src.index)
    # percentile of each src value within the anchor-src distribution
    pct = np.searchsorted(a_src, src.values.astype(float), side='right') / len(a_src)
    pct = np.clip(pct, 0.0, 1.0)
    dst_q = np.quantile(a_dst, pct)
    return pd.Series(np.round(dst_q, 1), index=src.index)


def main() -> int:
    if not FG_CSV.exists():
        print('FAIL: no FG snapshot to calibrate against '
              f'({FG_CSV.name} missing)')
        return 1
    fg = pd.read_csv(FG_CSV)
    fg['stuff_plus'] = pd.to_numeric(fg['stuff_plus'], errors='coerce')
    fg = fg.dropna(subset=['mlb_id', 'stuff_plus'])
    fg['mlb_id'] = fg['mlb_id'].astype(int)
    import os
    from datetime import datetime
    fg_age = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(FG_CSV))).days
    print(f'FG calibration anchor: {len(fg)} pitchers with stuff_plus '
          f'(snapshot age {fg_age}d)')

    # ---- source 1: archetype STUFF (current season) --------------------
    arch = pd.read_csv(ARCH_CSV, usecols=['year', 'pitcher', 'player_name', 'gs', 'STUFF'])
    arch = arch[arch['year'] == SEASON].dropna(subset=['STUFF']).copy()
    arch['pitcher'] = arch['pitcher'].astype(int)

    # ---- source 2: PLV per-pitcher (nightly board) ---------------------
    plv = pd.read_csv(PLV_CSV, usecols=['pitcher', 'player_name', 'pitches', 'plv'])
    plv = plv[plv['pitches'] >= PLV_MIN_PITCHES].dropna(subset=['plv']).copy()
    plv['pitcher'] = plv['pitcher'].astype(int)

    # ---- calibrate each onto the FG stuff_plus scale -------------------
    rows_out = {}
    for name, df, val_col in (('arch', arch, 'STUFF'), ('plv', plv, 'plv')):
        j = df.merge(fg[['mlb_id', 'stuff_plus']], left_on='pitcher',
                     right_on='mlb_id', how='inner')
        if len(j) < MIN_OVERLAP:
            print(f'  {name}: only {len(j)} anchor pairs (<{MIN_OVERLAP}) — SKIPPED')
            continue
        pear = float(np.corrcoef(j[val_col], j['stuff_plus'])[0, 1])
        spear = float(pd.Series(j[val_col]).corr(pd.Series(j['stuff_plus']),
                                                 method='spearman'))
        mapped = quantile_map(df[val_col], j[val_col], j['stuff_plus'])
        rows_out[name] = df.assign(stuff_mapped=mapped.values)
        print(f'  {name}: n={len(df)} (anchor overlap {len(j)}) — vs FG '
              f'stuff_plus: pearson {pear:+.3f}, spearman {spear:+.3f}')

    if 'arch' not in rows_out and 'plv' not in rows_out:
        print('FAIL: no source calibrated')
        return 1

    # ---- compose: arch primary (the validated fallback), plv fills gaps
    out = {}
    if 'plv' in rows_out:
        for _, r in rows_out['plv'].iterrows():
            out[int(r['pitcher'])] = {
                'mlb_id': int(r['pitcher']), 'player_name': r['player_name'],
                'stuff_plus_inhouse': r['stuff_mapped'], 'stuff_source': 'plv',
                'plv': r['plv'], 'arch_stuff_2080': np.nan,
            }
    if 'arch' in rows_out:
        for _, r in rows_out['arch'].iterrows():
            pid = int(r['pitcher'])
            prev = out.get(pid, {})
            out[pid] = {
                'mlb_id': pid, 'player_name': r['player_name'],
                'stuff_plus_inhouse': r['stuff_mapped'], 'stuff_source': 'arch',
                'plv': prev.get('plv', np.nan), 'arch_stuff_2080': r['STUFF'],
            }
    res = pd.DataFrame(out.values()).sort_values('stuff_plus_inhouse',
                                                 ascending=False)
    n_arch = int((res['stuff_source'] == 'arch').sum())
    n_plv = int((res['stuff_source'] == 'plv').sum())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_CSV, index=False)
    print(f'OK {len(res)} pitchers -> {OUT_CSV.name}  '
          f'(arch={n_arch}, plv-fill={n_plv})')
    # visibility: who does PLV rescue that arch misses (the rookie gap)?
    fills = res[res['stuff_source'] == 'plv'].head(12)
    if len(fills):
        print('PLV-only coverage (arch gs-gate misses these):')
        for _, r in fills.iterrows():
            print(f"  {r['player_name']:<24} inhouse={r['stuff_plus_inhouse']:.0f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
