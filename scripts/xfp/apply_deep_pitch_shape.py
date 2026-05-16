"""apply_deep_pitch_shape.py — apply deep model coefficients to 2026 pitchers.

Uses the validated L1 + 5 winners model to compute FP/start adjustments
for Sheehan, Strider, Rodón, etc. — actual numbers for the swap math.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

from scripts.xfp.validate_pitch_shape_deep import (
    load_year, compute_pitcher_features, YEARS)

# Coefficients from deep sweep (only the FP-impact terms; intercept and
# prior_fp are absorbed into base projection)
COEFS = {
    'd_velo_all':         +0.53118,
    'd_ext_all':          +1.22011,
    'd_ivb_all':          -0.11676,
    'd_release_x_std':    -5.18708,
    'd_whiff_per_swing':  +0.26466,
    'd_spin_fb':          +0.00455,
    'd_whiff_fb':         -0.06686,
    'd_whiff_br':         +0.00698,
}

SP_REMAINING_STARTS = 24


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def main():
    targets = ['Emmet Sheehan', 'Spencer Strider', 'Carlos Rodon',
                'Kyle Bradish', 'Eury Perez', 'Tyler Glasnow',
                'Sonny Gray', 'Framber Valdez', 'Max Fried',
                'Robbie Ray', 'Freddy Peralta', 'Logan Henderson',
                'Connor Prielipp']

    # Load 2026 + 2023-2025 baseline
    print('Loading data...')
    feats_2026 = compute_pitcher_features(load_year(2026))
    feats_baseline = pd.concat([compute_pitcher_features(load_year(y))
                                  for y in [2023, 2024, 2025]], ignore_index=True)

    # Pitcher id lookup
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    sp_lookup = sp[['pitcher', 'player_name']].drop_duplicates('player_name')
    sp_lookup['nk'] = sp_lookup['player_name'].map(_norm)
    id_by_nk = dict(zip(sp_lookup['nk'], sp_lookup['pitcher']))

    # Weighted baseline by n_pitches
    baseline_grp = feats_baseline.groupby('pitcher').apply(
        lambda g: pd.Series({
            'velo_all': (g['velo_all'] * g['n_pitches']).sum() / g['n_pitches'].sum() if g['n_pitches'].sum() else np.nan,
            'ext_all':  (g['ext_all']  * g['n_pitches']).sum() / g['n_pitches'].sum() if g['n_pitches'].sum() else np.nan,
            'ivb_all':  (g['ivb_all']  * g['n_pitches']).sum() / g['n_pitches'].sum() if g['n_pitches'].sum() else np.nan,
            'release_x_std':    g['release_x_std'].mean(),
            'whiff_per_swing':  g['whiff_per_swing'].mean(),
            'spin_fb':          g['spin_fb'].mean(),
            'whiff_fb':         g['whiff_fb'].mean(),
            'whiff_br':         g['whiff_br'].mean(),
        }),
        include_groups=False,
    ).reset_index()
    baseline_by_pid = {int(r['pitcher']): r for _, r in baseline_grp.iterrows()}
    cur_by_pid = {int(r['pitcher']): r for _, r in feats_2026.iterrows()}

    print(f'\n{"PITCHER":<22s} {"d_velo":>7s} {"d_ext":>7s} {"d_xstd":>8s} '
          f'{"d_whif":>7s} {"d_spinFB":>9s} {"d_whifFB":>9s} {"FP/GS":>8s} {"RoS":>7s}')

    rp3 = pd.read_csv(OUT / 'xfp_rp3_projections_il_fixed.csv'
                        if (OUT / 'xfp_rp3_projections_il_fixed.csv').exists()
                        else OUT / 'xfp_rp3_projections.csv')
    rp3['nk'] = rp3['player_name'].map(_norm)
    proj_lookup = {r['nk']: r for _, r in rp3.iterrows()}

    rows = []
    for name in targets:
        nk = _norm(name)
        pid = id_by_nk.get(nk)
        if pid is None: continue
        cur = cur_by_pid.get(int(pid))
        car = baseline_by_pid.get(int(pid))
        if cur is None or car is None:
            print(f'  {name:<22s} no data')
            continue
        deltas = {}
        for col in ['velo_all', 'ext_all', 'ivb_all', 'release_x_std',
                    'whiff_per_swing', 'spin_fb', 'whiff_fb', 'whiff_br']:
            cv, bv = cur.get(col), car.get(col)
            if pd.notna(cv) and pd.notna(bv):
                deltas[f'd_{col}'] = cv - bv
            else:
                deltas[f'd_{col}'] = 0.0

        fp_adj = sum(COEFS[k] * deltas[k] for k in COEFS)
        ros_adj = fp_adj * SP_REMAINING_STARTS

        # Get current rp3 projection (post-IL-fix)
        proj = proj_lookup.get(nk)
        per_start = proj.get('xfp_rp3_per_start_sched') or proj.get('xfp_rp3_per_start') if proj is not None else 0
        gs_rem = proj.get('gs_rem_fixed', SP_REMAINING_STARTS) if proj is not None else SP_REMAINING_STARTS
        cur_ros = per_start * gs_rem if proj is not None else 0
        adj_ros = cur_ros + ros_adj

        print(f'  {name:<22s} {deltas["d_velo_all"]:>+7.2f} {deltas["d_ext_all"]:>+7.2f} '
              f'{deltas["d_release_x_std"]:>+8.2f} {deltas["d_whiff_per_swing"]:>+7.2f} '
              f'{deltas["d_spin_fb"]:>+9.0f} {deltas["d_whiff_fb"]:>+9.2f} '
              f'{fp_adj:>+8.2f} {ros_adj:>+7.1f}')
        rows.append({'name': name, 'fp_adj': fp_adj, 'ros_adj': ros_adj,
                      'cur_ros': cur_ros, 'adj_ros': adj_ros, **deltas})

    pd.DataFrame(rows).to_csv(OUT / 'deep_pitch_shape_2026_adjustments.csv', index=False)
    print(f'\nwrote deep_pitch_shape_2026_adjustments.csv')


if __name__ == '__main__':
    main()
