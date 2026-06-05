"""fit_weight_blend_live_tags.py — Add retroactive HIGH-K-ARM + shadow-scout
features to the SP weight blend and measure R² lift vs Phase-2 baseline.

Inputs:
  data/research/historical_panel/master_panel.parquet
  data/research/historical_panel/sp_live_tags_retroactive.parquet

Output:
  printed report; markdown writer is in the parent task.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'
TAGS = ROOT / 'data' / 'research' / 'historical_panel' / 'sp_live_tags_retroactive.parquet'

# Phase-2 SP baseline feature set (from fit_weight_blend.py)
BASE_FEATS = [
    'prior_year_fp_per_start', 'arche_overall_prior', 'arche_career_pct_prior',
    'traj_up_prior', 'traj_down_prior', 'traj_career_low_prior', 'age_normalized',
]

NEW_FEATS = {
    'high_k_only': ['high_k_z_year_prior'],
    'shadow_only': ['shadow_velo_pct_prior', 'shadow_k_pct_prior',
                    'shadow_bb_pct_prior', 'shadow_whiff_pct_prior', 'shadow_csw_pct_prior'],
    'combined': ['high_k_z_year_prior', 'shadow_velo_pct_prior', 'shadow_k_pct_prior',
                 'shadow_bb_pct_prior', 'shadow_whiff_pct_prior', 'shadow_csw_pct_prior'],
}


def build_sp_panel():
    panel = pd.read_parquet(PANEL)
    tags = pd.read_parquet(TAGS)
    sp = panel[panel['player_type'] == 'SP'].copy()
    sp = sp[sp['fp_per_start'].notna() & sp['prior_year_fp_per_start'].notna() &
            sp['arche_overall_prior'].notna() & (~sp['covid_short'])]
    sp['traj_up_prior'] = (sp['arche_traj_prior'] == 'TRENDING_UP').astype(int)
    sp['traj_down_prior'] = (sp['arche_traj_prior'] == 'TRENDING_DOWN').astype(int)
    sp['traj_career_low_prior'] = (sp['arche_traj_prior'] == 'CAREER_LOW').astype(int)
    sp['age_normalized'] = (sp['age'] - 28) / 5

    # Join tags as PRIOR-YEAR (no leakage: tag at year-1 predicting year)
    tag_cols = ['high_k_z_year', 'shadow_velo_pct', 'shadow_k_pct',
                'shadow_bb_pct', 'shadow_whiff_pct', 'shadow_csw_pct', 'n_pitches']
    tags_prior = tags[['mlbam_id', 'year'] + tag_cols].copy()
    tags_prior['year'] = tags_prior['year'] + 1  # shift to "prior year"
    rename = {c: c + '_prior' for c in tag_cols}
    tags_prior = tags_prior.rename(columns=rename)
    sp = sp.merge(tags_prior, on=['mlbam_id', 'year'], how='left')
    return sp


def fit_loyo(sub, features, y_col='fp_per_start'):
    years = sorted(sub['year'].unique())
    preds, actual, fold = [], [], []
    for held in years:
        train = sub[sub['year'] != held]
        test = sub[sub['year'] == held]
        if len(test) < 5:
            continue
        mu = train[features].mean()
        sd = train[features].std().replace(0, 1)
        Xtr = ((train[features] - mu) / sd).values
        Xte = ((test[features] - mu) / sd).values
        reg = LinearRegression().fit(Xtr, train[y_col].values)
        p = reg.predict(Xte)
        # anchor baseline (prior fp_per_start only)
        a_reg = LinearRegression().fit(train[[features[0]]].values, train[y_col].values)
        a_pred = a_reg.predict(test[[features[0]]].values)
        r2b = r2_score(test[y_col].values, p)
        r2a = r2_score(test[y_col].values, a_pred)
        fold.append({'year': held, 'n': len(test), 'r2_blend': r2b, 'r2_anchor': r2a, 'lift': r2b - r2a})
        preds.extend(p.tolist()); actual.extend(test[y_col].tolist())
    return np.array(preds), np.array(actual), fold


def drop_test(sub, features, y_col='fp_per_start'):
    full = LinearRegression().fit(sub[features], sub[y_col]).score(sub[features], sub[y_col])
    out = {}
    for f in features:
        reduced = [x for x in features if x != f]
        r = LinearRegression().fit(sub[reduced], sub[y_col]).score(sub[reduced], sub[y_col])
        out[f] = round(full - r, 5)
    return out, full


def run(sp, feats, label):
    sub = sp.dropna(subset=feats + ['fp_per_start']).copy()
    # Shadow features require pitcher had >=200 pitches the prior year
    if 'n_pitches_prior' in sub.columns:
        if any('shadow' in f for f in feats):
            sub = sub[sub['n_pitches_prior'] >= 200]
    preds, actual, fold = fit_loyo(sub, feats)
    pooled = r2_score(actual, preds)
    # anchor pooled
    a_reg = LinearRegression().fit(sub[[feats[0]]].values, sub['fp_per_start'].values)
    a_p = a_reg.predict(sub[[feats[0]]].values)
    pooled_anchor = r2_score(sub['fp_per_start'].values, a_p)
    contrib, full_r2 = drop_test(sub, feats)
    pos = sum(1 for f in fold if f['lift'] > 0)
    return {
        'label': label, 'n': len(sub), 'features': feats,
        'pooled_r2_blend': round(pooled, 4),
        'pooled_r2_anchor': round(pooled_anchor, 4),
        'pooled_lift': round(pooled - pooled_anchor, 4),
        'convergence': f'{pos}/{len(fold)}',
        'fold_lifts': [(f['year'], round(f['lift'], 4)) for f in fold],
        'drop_contrib': contrib,
        'full_in_sample_r2': round(full_r2, 4),
    }


def main():
    sp = build_sp_panel()
    print(f'SP panel rows: {len(sp):,}')
    print(f'  with tag join (any shadow non-null): {sp["shadow_velo_pct_prior"].notna().sum():,}')
    print(f'  with high_k_z_year_prior non-null: {sp["high_k_z_year_prior"].notna().sum():,}')

    results = {}
    # Baseline (Phase 2) — full panel
    results['baseline_phase2'] = run(sp, BASE_FEATS, 'baseline_phase2')
    # Baseline on the high_k subset (apples-to-apples)
    sp_hk = sp[sp['high_k_z_year_prior'].notna()].copy()
    results['baseline_hk_subset'] = run(sp_hk, BASE_FEATS, 'baseline_hk_subset')
    # Baseline on the shadow subset
    sp_sh = sp[sp['shadow_velo_pct_prior'].notna() & (sp['n_pitches_prior'] >= 200)].copy()
    results['baseline_shadow_subset'] = run(sp_sh, BASE_FEATS, 'baseline_shadow_subset')
    # +high_k
    results['plus_high_k'] = run(sp, BASE_FEATS + NEW_FEATS['high_k_only'], 'plus_high_k')
    # +shadow
    results['plus_shadow'] = run(sp, BASE_FEATS + NEW_FEATS['shadow_only'], 'plus_shadow')
    # +combined
    results['plus_combined'] = run(sp, BASE_FEATS + NEW_FEATS['combined'], 'plus_combined')

    # Shadow rookie/small-sample subgroup: prior n_pitches in (200, 2000)
    sp_small = sp[(sp['n_pitches_prior'] >= 200) & (sp['n_pitches_prior'] < 2000)].copy()
    results['rookie_baseline'] = run(sp_small, BASE_FEATS, 'rookie_baseline')
    results['rookie_plus_shadow'] = run(sp_small, BASE_FEATS + NEW_FEATS['shadow_only'], 'rookie_plus_shadow')
    results['rookie_plus_high_k'] = run(sp_small, BASE_FEATS + NEW_FEATS['high_k_only'], 'rookie_plus_high_k')

    for k, v in results.items():
        print(f'\n=== {k} ===')
        print(f'  n={v["n"]}  pooled R² blend={v["pooled_r2_blend"]}  anchor={v["pooled_r2_anchor"]}  lift={v["pooled_lift"]:+}')
        print(f'  convergence: {v["convergence"]}')
        print(f'  fold_lifts: {v["fold_lifts"]}')
        print(f'  drop contributions (top 5):')
        for f, c in sorted(v['drop_contrib'].items(), key=lambda x: -x[1])[:8]:
            print(f'    {f:35s}  {c:+.5f}')

    out = ROOT / 'data' / 'research' / 'validation_runs' / 'weight_blend_live_tags_2026-06-04.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as fp:
        json.dump(results, fp, indent=2, default=str)
    print(f'\nWrote {out}')


if __name__ == '__main__':
    main()
