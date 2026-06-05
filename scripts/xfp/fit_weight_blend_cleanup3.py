"""fit_weight_blend_cleanup3.py — Cleanup #3 refit of within-season blend
on the corrected pl_rank_panel.parquet (2,544 rows, +420 vs prior).

Adds PL features (pl_rank_mid_inv) to all three player types and, for RP only,
an `is_non_closer_rp` binary segmentation flag (1 when no real PL rank). This
captures Cleanup #1's recommendation to ship the segmentation effect while
holding the leverage z-score blend.

Outputs:
  data/research/validation_runs/weight_blend_cleanup3_refit_2026-06-05.json

Constraints:
  - 2020 excluded
  - LOYO across all available years
  - Standardization fit on train only
  - Baseline = current within-season blend (NO PL features) — i.e. the
    Phase 3 numbers we're refitting against
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
HP = ROOT / 'data' / 'research' / 'historical_panel'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'

SPLIT_DAYS = [30, 60, 90, 120]
SPLIT_DAY_MAP = {30: 30, 60: 58, 90: 93, 120: 121}

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
        'sample_col': 'gs_to', 'sample_min': 3,
        'pl_cap': 100.0,
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
        'sample_col': 'pa_to', 'sample_min': 50,
        'pl_cap': 150.0,
    },
    'RP': {
        'file': 'rolling_relievers_2018_2026.csv',
        'arch_file': 'rp_ratings_master.csv',
        'id_col': 'pitcher',
        'features_to': ['k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'avg_velo_to', 'barrel_pct_to',
                        'hard_hit_pct_to', 'sv_per_g_to', 'hld_per_g_to'],
        'features_recent': [],
        'ros_col': None,
        'sample_col': 'g_to', 'sample_min': 8,
        'pl_cap': 100.0,
    },
}


def _load_pl():
    pl = pd.read_parquet(HP / 'pl_rank_panel.parquet')
    # collapse to (mlbam_id, year, pl_rank_mid). Fall back to early/late if mid missing.
    pl['pl_rank'] = pl['pl_rank_mid']
    pl['pl_rank'] = pl['pl_rank'].fillna(pl['pl_rank_early']).fillna(pl['pl_rank_late'])
    return pl[['mlbam_id', 'year', 'pl_rank']].copy()


def load_panel(ptype, target_split_day, pl_panel):
    cfg = CFG[ptype]
    df = pd.read_csv(CACHE / cfg['file'])
    avail = SPLIT_DAY_MAP[target_split_day]
    df = df[df['split_day'] == avail].copy()

    if cfg['ros_col'] is not None:
        df['_ros'] = df[cfg['ros_col']]
    else:
        df['_ros'] = df['fp_year_total'] - df['fp_with_role_to']

    df = df[df[cfg['sample_col']] >= cfg['sample_min']]
    df = df[df['_ros'].notna()]

    arch = pd.read_csv(HP.parent / cfg['arch_file'])
    arch_keep = arch[['year', cfg['id_col'], 'OVERALL', 'OVERALL_career_pct',
                      'traj_flag', 'age']].rename(columns={
        'OVERALL': 'arche_ovr', 'OVERALL_career_pct': 'arche_career_pct',
        'traj_flag': 'arche_traj'})
    df = df.merge(arch_keep, on=['year', cfg['id_col']], how='left')

    df['traj_up'] = (df['arche_traj'] == 'TRENDING_UP').astype(int)
    df['traj_down'] = (df['arche_traj'] == 'TRENDING_DOWN').astype(int)
    df['age_norm'] = (df['age'].fillna(28) - 28) / 5

    # Join PL panel.
    pl_join = pl_panel.rename(columns={'mlbam_id': cfg['id_col']})
    df = df.merge(pl_join, on=['year', cfg['id_col']], how='left')
    cap = cfg['pl_cap']
    df['pl_rank_mid_inv'] = np.where(
        df['pl_rank'].notna(),
        np.clip((cap - df['pl_rank']) / cap, 0, 1),
        np.nan,
    )
    df['has_pl'] = df['pl_rank'].notna().astype(int)
    if ptype == 'RP':
        df['is_non_closer_rp'] = (~df['pl_rank'].notna()).astype(int)

    base_feats = ([f for f in cfg['features_to'] if f in df.columns]
                  + [f for f in cfg['features_recent'] if f in df.columns]
                  + ['arche_ovr', 'arche_career_pct', 'traj_up', 'traj_down', 'age_norm'])
    df = df[df['year'] != 2020].copy()
    return df, base_feats


def fit_loyo(sub, features, y='_ros'):
    sub_use = sub.dropna(subset=features + [y]).copy()
    years = sorted(sub_use['year'].unique())
    folds = []
    pred_all, y_all = [], []
    for held in years:
        train = sub_use[sub_use['year'] != held]
        test = sub_use[sub_use['year'] == held]
        if len(test) < 50 or len(train) < 200:
            continue
        means = train[features].mean()
        stds = train[features].std().replace(0, 1)
        Xtr = ((train[features] - means) / stds).values
        Xte = ((test[features] - means) / stds).values
        ytr = train[y].values
        yte = test[y].values
        reg = LinearRegression().fit(Xtr, ytr)
        pred = reg.predict(Xte)
        folds.append({'year': int(held), 'n': len(test),
                      'r2': float(r2_score(yte, pred))})
        pred_all.extend(pred.tolist())
        y_all.extend(yte.tolist())
    if not folds:
        return None
    pooled = float(r2_score(y_all, pred_all)) if y_all else float('nan')
    # Refit pooled coefficients on full sub (z-standardized) for shipping.
    means = sub_use[features].mean()
    stds = sub_use[features].std().replace(0, 1)
    Xall = ((sub_use[features] - means) / stds).values
    yall = sub_use[y].values
    reg_full = LinearRegression().fit(Xall, yall)
    coefs = {f: float(c) for f, c in zip(features, reg_full.coef_)}
    return {
        'folds': folds, 'pooled_r2': pooled,
        'coefs_zstd': coefs, 'intercept': float(reg_full.intercept_),
        'n_rows': len(sub_use),
        'feature_means': {f: float(means[f]) for f in features},
        'feature_stds': {f: float(stds[f]) for f in features},
    }


def drop_test_one(sub, features, feature_to_drop, y='_ros'):
    sub_use = sub.dropna(subset=features + [y]).copy()
    if len(sub_use) < 100:
        return None
    Xfull = sub_use[features].values
    yv = sub_use[y].values
    full_r2 = LinearRegression().fit(Xfull, yv).score(Xfull, yv)
    red = [c for c in features if c != feature_to_drop]
    red_r2 = LinearRegression().fit(sub_use[red].values, yv).score(sub_use[red].values, yv)
    return {'full_r2': float(full_r2), 'reduced_r2': float(red_r2),
            'drop_contrib': float(full_r2 - red_r2)}


def fold_lift(sub, features_base, features_full, y='_ros'):
    """Per-year LOYO lift of full features vs base features."""
    sub_b = sub.dropna(subset=features_base + [y])
    sub_f = sub.dropna(subset=features_full + [y])
    # use intersection of rows where both feature sets are available
    common = sub_f.copy()
    years = sorted(common['year'].unique())
    folds = []
    pa_b, pa_f, y_all = [], [], []
    for held in years:
        train = common[common['year'] != held]
        test = common[common['year'] == held]
        if len(test) < 50 or len(train) < 200:
            continue
        for label, feats, store in [('base', features_base, pa_b), ('full', features_full, pa_f)]:
            mns = train[feats].mean()
            sds = train[feats].std().replace(0, 1)
            Xtr = ((train[feats] - mns) / sds).values
            Xte = ((test[feats] - mns) / sds).values
            reg = LinearRegression().fit(Xtr, train[y].values)
            pred = reg.predict(Xte)
            store.extend(pred.tolist())
        y_all.extend(test[y].values.tolist())
        # per-fold
        # recompute per-fold r2s
        def _r(feats):
            mns = train[feats].mean(); sds = train[feats].std().replace(0,1)
            Xtr = ((train[feats] - mns) / sds).values
            Xte = ((test[feats] - mns) / sds).values
            reg = LinearRegression().fit(Xtr, train[y].values)
            return float(r2_score(test[y].values, reg.predict(Xte)))
        r_b = _r(features_base); r_f = _r(features_full)
        folds.append({'year': int(held), 'n': len(test), 'r2_base': r_b,
                      'r2_full': r_f, 'lift': r_f - r_b})
    pooled_lift = (r2_score(y_all, pa_f) - r2_score(y_all, pa_b)) if y_all else float('nan')
    convergence = f"{sum(1 for f in folds if f['lift']>0)}/{len(folds)}"
    return {'folds': folds, 'pooled_lift': float(pooled_lift),
            'convergence': convergence}


def main():
    pl = _load_pl()
    print(f'PL panel: {len(pl)} rows after collapse')
    results = {}
    for ptype in ['SP', 'H', 'RP']:
        print(f'\n=== {ptype} ===')
        results[ptype] = {}
        for sd in SPLIT_DAYS:
            sub, base_feats = load_panel(ptype, sd, pl)
            n_total = len(sub)
            n_pl = int(sub['has_pl'].sum())
            print(f' split_day={sd}  n_total={n_total}  has_pl={n_pl}')

            # No-PL: base features only
            res_nopl = fit_loyo(sub, base_feats)

            # With-PL: subset to has_pl==1, add pl_rank_mid_inv
            pl_sub = sub[sub['has_pl'] == 1].copy()
            full_feats_pl = base_feats + ['pl_rank_mid_inv']
            res_pl = fit_loyo(pl_sub, full_feats_pl) if len(pl_sub) >= 300 else None

            entry = {
                'n_total': n_total, 'n_has_pl': n_pl,
                'no_pl': res_nopl, 'with_pl': res_pl,
            }

            if ptype == 'RP':
                # Test is_non_closer_rp added to base on FULL panel (pooled)
                full_feats_rp = base_feats + ['is_non_closer_rp']
                res_rp_seg = fit_loyo(sub, full_feats_rp)
                dt = drop_test_one(sub, full_feats_rp, 'is_non_closer_rp')
                lift_seg = fold_lift(sub, base_feats, full_feats_rp)
                entry['rp_segmentation'] = {
                    'fit': res_rp_seg,
                    'drop_test_is_non_closer_rp': dt,
                    'fold_lift_vs_base': lift_seg,
                }

            results[ptype][sd] = entry

            if res_nopl:
                print(f'   no_pl  pooled R^2={res_nopl["pooled_r2"]:.4f} (n={res_nopl["n_rows"]})')
            if res_pl:
                print(f'   with_pl pooled R^2={res_pl["pooled_r2"]:.4f} (n={res_pl["n_rows"]})')
            if ptype == 'RP' and entry['rp_segmentation']['fit']:
                seg = entry['rp_segmentation']
                print(f'   +is_non_closer_rp pooled R^2={seg["fit"]["pooled_r2"]:.4f}'
                      f'  drop_contrib={seg["drop_test_is_non_closer_rp"]["drop_contrib"]:.4f}'
                      f'  pooled lift={seg["fold_lift_vs_base"]["pooled_lift"]:+.4f}'
                      f'  conv={seg["fold_lift_vs_base"]["convergence"]}')

    out = OUT_DIR / 'weight_blend_cleanup3_refit_2026-06-05.json'
    with open(out, 'w') as fp:
        json.dump(results, fp, indent=2, default=str)
    print(f'\nWrote {out}')
    return results


if __name__ == '__main__':
    main()
