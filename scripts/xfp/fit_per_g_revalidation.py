"""Phase 3 — per-G re-validation + ros_layered vs rprs2 comparison.

1. Re-fit a clean per-G ridge on the rolling RP substrate (LOYO 2018-2025 ex-2020),
   target = `fp_per_g` joined from master_panel. Features mirror blend_score.py
   RP no_pl entry.
2. Re-fit rprs2-style full-season ridge on FEATS_RPRS2, target = `fp_year_total`.
3. Layered ros = per_g_pred × E[G]_pred (from e_of_g_preds_2026-06-06.parquet).
4. Compare MAE / R² / role-bias for ros_layered vs rprs2_full.

NO PRODUCTION WIRING.
"""
from __future__ import annotations
from pathlib import Path
import sys, io, json
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

ROOT = Path(__file__).resolve().parents[2]
ROLLING = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_relievers_2018_2026.csv'
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'
EG_PREDS = ROOT / 'data' / 'research' / 'validation_runs' / 'e_of_g_preds_2026-06-06.parquet'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
# Mid-season snapshot for honest RoS comparison. Default 72 (~mid-June).
# Late snapshots (184/191) collapse rprs2 to a trivial cumulative extrapolation.
import os
SPLIT_DAY = int(os.environ.get('PHASE3_SPLIT_DAY', '72'))

# Per-G feature set (mirrors RP no_pl blend, drops PL-rank dependents)
PERG_FEATS = ['prior_year_fp_per_g_rp', 'arche_overall_prior', 'age',
              'role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1']

# RPRS2-style full-season features (per rprs2.py)
RPRS2_FEATS = [
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to',
    'xwoba_per_pa_to', 'avg_velo_to',
    'g_to', 'ip_to', 'fp_skill_to',
    'role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1',
    'sv_lag1', 'hld_lag1', 'g_lag1', 'ip_lag1',
    'fp_per_g_lag1', 'fp_lag1',
    'gf_pct_to', 'sv_per_g_to', 'hld_per_g_to', 'sv_plus_hld_to',
    'fp_with_role_to', 'sv_per_g_lag1', 'hld_per_g_lag1',
    'split_day',
]


def build_per_yr_snapshot():
    """One row per (pitcher, year) using late-season snapshot from rolling."""
    roll = pd.read_csv(ROLLING)
    # Pick the snapshot closest to SPLIT_DAY per (pitcher, year) — fixed cutoff
    # so rprs2's in-season cumulative features represent ~mid-June pace, not
    # near-final season totals.
    roll['split_dist'] = (roll['split_day'] - SPLIT_DAY).abs()
    roll = roll.sort_values(['pitcher', 'year', 'split_dist'])
    roll = roll.groupby(['pitcher', 'year'], as_index=False).head(1).drop(columns=['split_dist']).copy()
    print(f'(snapshot split_day≈{SPLIT_DAY}, actual distribution: {roll.split_day.value_counts().head(3).to_dict()})')
    panel = pd.read_parquet(PANEL)
    rp = panel[panel.player_type == 'RP'][
        ['mlbam_id', 'year', 'g', 'fp_per_g', 'fp_total',
         'age', 'arche_overall_prior',
         'prior_year_g_rp', 'prior_year_fp_per_g_rp']
    ].rename(columns={'mlbam_id': 'pitcher'})
    df = roll.merge(rp, on=['pitcher', 'year'], how='inner')
    df = df[df.year.isin(YEARS)]
    df = df[df.g >= 5]
    return df


def loyo_ridge(df, feats, target):
    rows_preds, rows_acts, rows_ids = [], [], []
    per_year = {}
    for held in YEARS:
        tr = df[df.year != held].copy()
        te = df[df.year == held].copy()
        if len(tr) < 80 or len(te) < 30:
            continue
        for f in feats:
            if f not in tr.columns:
                tr[f] = 0.0; te[f] = 0.0
            mu = tr[f].mean()
            tr[f] = tr[f].fillna(mu); te[f] = te[f].fillna(mu)
        tr = tr.dropna(subset=[target])
        te = te.dropna(subset=[target])
        if len(tr) < 80 or len(te) < 30:
            continue
        sc = StandardScaler().fit(tr[feats].values)
        m = RidgeCV(alphas=np.logspace(-1, 4, 40), cv=5).fit(
            sc.transform(tr[feats].values), tr[target].values)
        p = m.predict(sc.transform(te[feats].values))
        ss = np.sum((te[target].values - te[target].values.mean()) ** 2)
        r2 = 1 - np.sum((te[target].values - p) ** 2) / ss if ss > 0 else np.nan
        mae = float(np.mean(np.abs(p - te[target].values)))
        per_year[held] = {'r2': round(float(r2), 4), 'mae': round(mae, 2), 'n': len(te)}
        rows_preds.extend(p.tolist())
        rows_acts.extend(te[target].tolist())
        rows_ids.extend(list(zip(te['pitcher'].tolist(), te['year'].tolist())))
    preds = np.array(rows_preds); acts = np.array(rows_acts)
    ss = np.sum((acts - acts.mean()) ** 2)
    r2_overall = 1 - np.sum((acts - preds) ** 2) / ss
    mae_overall = float(np.mean(np.abs(preds - acts)))
    return {
        'r2': round(float(r2_overall), 4),
        'mae': round(mae_overall, 2),
        'n': len(preds),
        'per_year': per_year,
        'preds_df': pd.DataFrame({'pitcher': [i[0] for i in rows_ids],
                                  'year': [i[1] for i in rows_ids],
                                  'pred': preds, 'act': acts}),
    }


def bootstrap_diff(acts, p1, p2, n_boot=200, seed=42, metric='mae'):
    rng = np.random.default_rng(seed)
    diffs = []
    n = len(acts)
    for _ in range(n_boot):
        ix = rng.integers(0, n, n)
        a, b1, b2 = acts[ix], p1[ix], p2[ix]
        if metric == 'mae':
            d = np.mean(np.abs(b1 - a)) - np.mean(np.abs(b2 - a))  # positive = p2 better
        else:
            ss = np.sum((a - a.mean()) ** 2)
            r2_1 = 1 - np.sum((a - b1) ** 2) / ss
            r2_2 = 1 - np.sum((a - b2) ** 2) / ss
            d = r2_2 - r2_1
        diffs.append(d)
    diffs = np.array(diffs)
    return float(diffs.mean()), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def main():
    print('=== Phase 3 per-G re-validation + ros_layered vs rprs2 ===\n')
    df = build_per_yr_snapshot()
    print(f'rows: {len(df)}  years: {sorted(df.year.unique())}')

    print('\n--- LAYER 1: per-G ridge (target = fp_per_g) ---')
    perg = loyo_ridge(df, PERG_FEATS, 'fp_per_g')
    print(f'  R²={perg["r2"]} MAE={perg["mae"]} n={perg["n"]}')
    for y, m in sorted(perg['per_year'].items()):
        print(f'    {y}: R²={m["r2"]:.4f} MAE={m["mae"]:.2f} n={m["n"]}')

    print('\n--- LAYER 1b: rprs2-style full-season ridge (target = fp_year_total) ---')
    # Use 'fp_year_total' from rolling, but make sure it matches master_panel fp_total
    # (fp_year_total in rolling IS the season total). Check alignment.
    df['fp_year_total_from_panel'] = df['fp_total']
    rprs2 = loyo_ridge(df, RPRS2_FEATS, 'fp_year_total_from_panel')
    print(f'  R²={rprs2["r2"]} MAE={rprs2["mae"]} n={rprs2["n"]}')
    for y, m in sorted(rprs2['per_year'].items()):
        print(f'    {y}: R²={m["r2"]:.4f} MAE={m["mae"]:.2f} n={m["n"]}')

    print('\n--- LAYER 2: load E[G] preds + build ros_layered ---')
    eg = pd.read_parquet(EG_PREDS)
    print(f'  E[G] preds: {len(eg)} rows')
    eg_df = eg[['pitcher', 'year', 'eg_pred', 'g']].rename(columns={'g': 'g_act'})

    perg_df = perg['preds_df'].rename(columns={'pred': 'pg_pred', 'act': 'pg_act'})
    rprs2_df = rprs2['preds_df'].rename(columns={'pred': 'rprs2_pred', 'act': 'fp_total_act'})

    # Merge — same set of (pitcher, year)
    merged = perg_df.merge(eg_df, on=['pitcher', 'year'], how='inner')
    merged = merged.merge(rprs2_df, on=['pitcher', 'year'], how='inner')
    # role for bias analysis
    merged = merged.merge(df[['pitcher', 'year', 'role_lag1']],
                          on=['pitcher', 'year'], how='left')
    merged['ros_layered'] = merged['pg_pred'] * merged['eg_pred']

    print(f'  Merged eval set: n={len(merged)}')
    acts = merged['fp_total_act'].values
    rprs2_pred = merged['rprs2_pred'].values
    layered_pred = merged['ros_layered'].values

    ss = np.sum((acts - acts.mean()) ** 2)
    r2_rprs2 = 1 - np.sum((acts - rprs2_pred) ** 2) / ss
    r2_layered = 1 - np.sum((acts - layered_pred) ** 2) / ss
    mae_rprs2 = float(np.mean(np.abs(acts - rprs2_pred)))
    mae_layered = float(np.mean(np.abs(acts - layered_pred)))

    print('\n--- HEAD-TO-HEAD vs actual fp_total ---')
    print(f'  rprs2_pred:    R²={r2_rprs2:.4f}  MAE={mae_rprs2:.2f}')
    print(f'  ros_layered:   R²={r2_layered:.4f}  MAE={mae_layered:.2f}')
    print(f'  ΔR² (layered − rprs2): {r2_layered - r2_rprs2:+.4f}')
    print(f'  ΔMAE (layered − rprs2): {mae_layered - mae_rprs2:+.2f} (negative = layered better)')

    # Bootstrap CIs
    mae_mean, mae_lo, mae_hi = bootstrap_diff(acts, layered_pred, rprs2_pred, metric='mae')
    r2_mean, r2_lo, r2_hi = bootstrap_diff(acts, rprs2_pred, layered_pred, metric='r2')
    print(f'  Bootstrap MAE diff (rprs2 − layered): mean={mae_mean:+.2f} CI95=[{mae_lo:+.2f}, {mae_hi:+.2f}]')
    print(f'    (positive = rprs2 has higher MAE = layered wins)')
    print(f'  Bootstrap R² diff (layered − rprs2):  mean={r2_mean:+.4f} CI95=[{r2_lo:+.4f}, {r2_hi:+.4f}]')

    print('\n--- ROLE BIAS (mean residual = pred − act, by role_lag1) ---')
    merged['resid_rprs2'] = rprs2_pred - acts
    merged['resid_layered'] = layered_pred - acts
    role_bias = merged.groupby('role_lag1').agg(
        n=('pitcher', 'count'),
        rprs2_resid=('resid_rprs2', 'mean'),
        layered_resid=('resid_layered', 'mean'),
        rprs2_mae=('resid_rprs2', lambda x: np.mean(np.abs(x))),
        layered_mae=('resid_layered', lambda x: np.mean(np.abs(x))),
    ).round(2)
    print(role_bias.to_string())

    # Save results
    summary = {
        'per_g_r2': perg['r2'], 'per_g_mae': perg['mae'], 'per_g_n': perg['n'],
        'rprs2_r2': rprs2['r2'], 'rprs2_mae': rprs2['mae'], 'rprs2_n': rprs2['n'],
        'eg_n': len(eg),
        'merged_n': len(merged),
        'rprs2_pred_r2': round(float(r2_rprs2), 4),
        'rprs2_pred_mae': round(mae_rprs2, 2),
        'layered_r2': round(float(r2_layered), 4),
        'layered_mae': round(mae_layered, 2),
        'delta_r2': round(float(r2_layered - r2_rprs2), 4),
        'delta_mae': round(float(mae_layered - mae_rprs2), 2),
        'bootstrap_mae_diff_rprs2_minus_layered': {
            'mean': round(mae_mean, 3), 'ci95_lo': round(mae_lo, 3), 'ci95_hi': round(mae_hi, 3),
        },
        'bootstrap_r2_diff_layered_minus_rprs2': {
            'mean': round(r2_mean, 4), 'ci95_lo': round(r2_lo, 4), 'ci95_hi': round(r2_hi, 4),
        },
        'role_bias': role_bias.to_dict(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / 'phase3_layered_comparison_2026-06-06.json'
    tmp = out_json.with_suffix('.tmp.json')
    tmp.write_text(json.dumps(summary, indent=2, default=str))
    tmp.replace(out_json)
    print(f'\nWrote {out_json}')

    return summary


if __name__ == '__main__':
    main()
