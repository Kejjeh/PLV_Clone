"""fit_weight_blend_within_season.py — Phase 3: within-season ROS prediction.

For each (player_type, split_day), fit a weighted blend of `_to` features +
same-year archetype OVR/traj/career_pct against the rest-of-season FP outcome.
LOO-CV across years. Compare against anchor baseline (prior-year FP).

Outputs:
  data/research/validation_runs/weight_blend_within_season_2026-06-04.json
  data/research/validation_runs/weight_blend_within_season_2026-06-04.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'
OUT_DIR.mkdir(parents=True, exist_ok=True)

SPLIT_DAYS = [30, 60, 90, 120]
# Rolling cache has stride 7 starting at 30: 30, 37, 44, 51, 58, 65...
# Map to nearest available: 30->30, 60->58, 90->93, 120->121
SPLIT_DAY_MAP = {30: 30, 60: 58, 90: 93, 120: 121}

# Per-type config
CFG = {
    'SP': {
        'file': 'rolling_pitchers_2018_2026.csv',
        'arch_file': 'sp_ratings_master.csv',
        'id_col': 'pitcher',
        'features_to': ['k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'avg_velo_to', 'barrel_pct_to',
                        'hard_hit_pct_to', 'gb_pct_to', 'fp_per_start_to'],
        'features_recent': ['k_pct_last21', 'fp_per_start_last21', 'xwoba_per_pa_last21'],
        'ros_col': 'ros_fp_per_start',
        'sample_col': 'gs_to',
        'sample_min': 3,
    },
    'H': {
        'file': 'rolling_hitters_2018_2026.csv',
        'arch_file': 'hitter_ratings_master.csv',
        'id_col': 'batter',
        'features_to': ['k_pct_to', 'bb_pct_to', 'iso_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'hard_hit_pct_to', 'barrel_pct_to',
                        'contact_pct_to', 'chase_pct_to', 'core_fp_per_pa_to'],
        'features_recent': ['core_fp_per_pa_last21', 'xwoba_per_pa_last21', 'k_pct_last21'],
        'ros_col': 'ros_full_fp_per_pa',
        'sample_col': 'pa_to',
        'sample_min': 50,
    },
    'RP': {
        'file': 'rolling_relievers_2018_2026.csv',
        'arch_file': 'rp_ratings_master.csv',
        'id_col': 'pitcher',
        'features_to': ['k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'avg_velo_to', 'barrel_pct_to',
                        'hard_hit_pct_to', 'sv_per_g_to', 'hld_per_g_to'],
        'features_recent': [],  # no last21 cols indexed cleanly for RP outcome
        'ros_col': None,         # derived
        'sample_col': 'g_to',
        'sample_min': 8,
    },
}


def load_panel(ptype, target_split_day):
    cfg = CFG[ptype]
    df = pd.read_csv(CACHE / cfg['file'])
    avail = SPLIT_DAY_MAP[target_split_day]
    df = df[df['split_day'] == avail].copy()

    # Build ROS target
    if cfg['ros_col'] is not None:
        df['_ros'] = df[cfg['ros_col']]
    else:
        # RP: derive ros_fp_per_g from fp_year_total - fp_with_role_to over remaining games
        # We don't have ros_g directly; use ros_fp_total as outcome (per-season residual FP)
        df['_ros_fp_total'] = df['fp_year_total'] - df['fp_with_role_to']
        df['_ros'] = df['_ros_fp_total']  # absolute ROS FP for RP

    # Filter by sample size at cutoff
    df = df[df[cfg['sample_col']] >= cfg['sample_min']]

    # Drop nulls in ROS
    df = df[df['_ros'].notna()]

    # Join archetype (same-year OVR observable mid-season)
    arch = pd.read_csv(CACHE.parent / cfg['arch_file'])
    arch_keep = arch[['year', cfg['id_col'], 'OVERALL', 'OVERALL_career_pct',
                      'traj_flag', 'age']].rename(columns={
        'OVERALL': 'arche_ovr', 'OVERALL_career_pct': 'arche_career_pct',
        'traj_flag': 'arche_traj'
    })
    df = df.merge(arch_keep, on=['year', cfg['id_col']], how='left')

    # Anchor: prior-year FP proxy.
    if ptype == 'RP':
        df['_anchor'] = df['fp_per_g_lag1']
    else:
        # build prior-year fp by player from each player-year's max split_day snapshot
        anchor_src = pd.read_csv(CACHE / cfg['file'])
        anchor_col = 'fp_per_start_to' if ptype == 'SP' else 'core_fp_per_pa_to'
        # pick max split per (year, id)
        idx = anchor_src.groupby(['year', cfg['id_col']])['split_day'].idxmax()
        anchor_src = anchor_src.loc[idx, ['year', cfg['id_col'], anchor_col]].rename(
            columns={anchor_col: '_anchor_curr'})
        anchor_src['year'] = anchor_src['year'] + 1  # lag1
        df = df.merge(anchor_src, on=['year', cfg['id_col']], how='left')
        df['_anchor'] = df['_anchor_curr']

    # Traj indicators
    df['traj_up'] = (df['arche_traj'] == 'TRENDING_UP').astype(int)
    df['traj_down'] = (df['arche_traj'] == 'TRENDING_DOWN').astype(int)
    df['age_norm'] = (df['age'].fillna(28) - 28) / 5

    # Final feature set
    features = (cfg['features_to'] + cfg['features_recent']
                + ['arche_ovr', 'arche_career_pct', 'traj_up', 'traj_down', 'age_norm'])
    # Drop features not present
    features = [f for f in features if f in df.columns]

    df = df.dropna(subset=features + ['_ros', '_anchor'])
    return df, features


def fit_loyo(sub, features, anchor='_anchor', y='_ros'):
    years = sorted(sub['year'].unique())
    fold_results = []
    all_pred_blend, all_pred_anchor, all_actual = [], [], []

    for held in years:
        train = sub[sub['year'] != held]
        test = sub[sub['year'] == held]
        if len(test) < 100 or len(train) < 200:
            continue

        means = train[features].mean()
        stds = train[features].std().replace(0, 1)
        Xtr = ((train[features] - means) / stds).values
        Xte = ((test[features] - means) / stds).values
        ytr = train[y].values
        yte = test[y].values

        blend = LinearRegression().fit(Xtr, ytr)
        pred_b = blend.predict(Xte)

        anc_train = train[[anchor]].values
        anc_test = test[[anchor]].values
        anc_reg = LinearRegression().fit(anc_train, ytr)
        pred_a = anc_reg.predict(anc_test)

        r2_b = r2_score(yte, pred_b)
        r2_a = r2_score(yte, pred_a)

        fold_results.append({
            'held_year': int(held), 'n_test': len(test),
            'r2_blend': round(r2_b, 4), 'r2_anchor': round(r2_a, 4),
            'lift': round(r2_b - r2_a, 4),
        })
        all_pred_blend.extend(pred_b.tolist())
        all_pred_anchor.extend(pred_a.tolist())
        all_actual.extend(yte.tolist())

    if not fold_results:
        return None
    pooled_r2_blend = r2_score(all_actual, all_pred_blend)
    pooled_r2_anchor = r2_score(all_actual, all_pred_anchor)
    return {
        'folds': fold_results,
        'pooled_r2_blend': round(pooled_r2_blend, 4),
        'pooled_r2_anchor': round(pooled_r2_anchor, 4),
        'pooled_lift': round(pooled_r2_blend - pooled_r2_anchor, 4),
        'convergence': f"{sum(1 for f in fold_results if f['lift']>0)}/{len(fold_results)}",
    }


def drop_test(sub, features, y='_ros'):
    X = sub[features].values
    yv = sub[y].values
    full_r2 = LinearRegression().fit(X, yv).score(X, yv)
    contrib = {}
    for f in features:
        red = [c for c in features if c != f]
        r2 = LinearRegression().fit(sub[red].values, yv).score(sub[red].values, yv)
        contrib[f] = round(full_r2 - r2, 4)
    return contrib


def main():
    all_results = {}
    for ptype in ['SP', 'H', 'RP']:
        print(f'\n=== {ptype} ===')
        all_results[ptype] = {}
        for sd in SPLIT_DAYS:
            print(f'  split_day={sd} (mapped to {SPLIT_DAY_MAP[sd]})')
            try:
                sub, features = load_panel(ptype, sd)
            except Exception as e:
                print(f'    ERROR loading: {e}')
                continue
            print(f'    n={len(sub):,}  features={len(features)}')
            if len(sub) < 300:
                print('    SKIP (n too low)')
                all_results[ptype][sd] = {'n': len(sub), 'skip': 'low_n'}
                continue

            r = fit_loyo(sub, features)
            if r is None:
                all_results[ptype][sd] = {'n': len(sub), 'skip': 'no_folds'}
                continue
            contrib = drop_test(sub, features)
            top5 = dict(sorted(contrib.items(), key=lambda x: -x[1])[:5])
            print(f'    pooled R² blend={r["pooled_r2_blend"]:.4f}  anchor={r["pooled_r2_anchor"]:.4f}  lift={r["pooled_lift"]:+.4f}')
            print(f'    convergence={r["convergence"]}')
            print(f'    top features: {top5}')
            all_results[ptype][sd] = {
                'n': len(sub), 'features': features, **r,
                'top5_contrib': top5, 'all_contrib': contrib,
            }

    out_json = OUT_DIR / 'weight_blend_within_season_2026-06-04.json'
    with open(out_json, 'w') as fp:
        json.dump(all_results, fp, indent=2, default=str)
    print(f'\nWrote {out_json}')
    return all_results


if __name__ == '__main__':
    main()
