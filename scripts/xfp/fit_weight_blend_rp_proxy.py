"""fit_weight_blend_rp_proxy.py — Cleanup #1 lift test.

Test whether adding the leverage-derived proxy_pl_rank_mid_inv to the
RP weight blend (filled-in where real PL rank is absent) adds R^2 lift
on top of the existing baseline + real-PL blend.

Comparison setups (all on RP rows only, ex-2020, ex-2026):
  A. baseline        = anchor + arche + traj + age
  B. baseline + PL   = A + {pl_rank_early_inv, pl_rank_mid_inv, pl_rank_late_inv}  (inner join with pl_rank_panel)
  C. baseline + PL_or_proxy:
        feature `pl_rank_mid_inv_combined` =
            real pl_rank_mid_inv if available else proxy_pl_rank_mid_inv
        is_proxy flag (1 if used proxy) included as covariate.
        Evaluated on UNION (real PL ∪ proxy panel).

We report R^2 lift of C vs A on the union rows (the coverage-expansion
case — which is the practical question). We also report C vs B on the
intersection (does the proxy help when real PL exists?).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
PANEL = ROOT / 'data/research/historical_panel/master_panel.parquet'
PL = ROOT / 'data/research/historical_panel/pl_rank_panel.parquet'
PROXY = ROOT / 'data/research/historical_panel/rp_leverage_proxy_panel.parquet'
OUT_MD = ROOT / 'data/research/validation_runs/weight_blend_rp_proxy_2026-06-05.md'
OUT_JSON = ROOT / 'data/research/validation_runs/weight_blend_rp_proxy_2026-06-05.json'

BASELINE_FEATS = [
    'anchor_fp', 'arche_overall_prior', 'arche_career_pct_prior',
    'traj_up_prior', 'traj_down_prior', 'traj_career_low_prior',
    'age_normalized',
]


def prep_rp(panel):
    sub = panel[panel['player_type'] == 'RP'].copy()
    sub = sub[sub['fp_per_g'].notna() & sub['prior_year_fp_per_g_rp'].notna()
              & sub['arche_overall_prior'].notna()]
    sub = sub[(sub['year'] >= 2017) & (sub['year'] <= 2025) & (~sub['covid_short'])]
    sub['traj_up_prior'] = (sub['arche_traj_prior'] == 'TRENDING_UP').astype(int)
    sub['traj_down_prior'] = (sub['arche_traj_prior'] == 'TRENDING_DOWN').astype(int)
    sub['traj_career_low_prior'] = (sub['arche_traj_prior'] == 'CAREER_LOW').astype(int)
    sub['age_normalized'] = (sub['age'] - 28) / 5
    sub = sub.rename(columns={'prior_year_fp_per_g_rp': 'anchor_fp'})
    sub = sub.dropna(subset=BASELINE_FEATS + ['fp_per_g'])
    return sub


def fold_fit(df, feats, y_col='fp_per_g'):
    years = sorted(df['year'].unique())
    preds, actual, fold_rows = [], [], []
    for held in years:
        tr = df[df['year'] != held]
        te = df[df['year'] == held]
        if len(tr) < 50 or len(te) < 5:
            continue
        means = tr[feats].mean()
        stds = tr[feats].std().replace(0, 1).fillna(1)
        Xtr = ((tr[feats].fillna(means) - means) / stds).fillna(0).values
        Xte = ((te[feats].fillna(means) - means) / stds).fillna(0).values
        ytr = tr[y_col].values; yte = te[y_col].values
        reg = LinearRegression().fit(Xtr, ytr)
        p = reg.predict(Xte)
        fold_rows.append({'year': int(held), 'n': len(te),
                          'r2': float(r2_score(yte, p)) if len(yte) > 1 else float('nan')})
        preds.extend(p.tolist()); actual.extend(yte.tolist())
    return np.array(preds), np.array(actual), fold_rows


def drop_test(df, feats, drop, y_col='fp_per_g'):
    reduced = [f for f in feats if f != drop]
    Xfull = df[feats].fillna(df[feats].mean())
    Xred = df[reduced].fillna(df[reduced].mean())
    y = df[y_col]
    r2_full = LinearRegression().fit(Xfull, y).score(Xfull, y)
    r2_red = LinearRegression().fit(Xred, y).score(Xred, y)
    return float(r2_full - r2_red)


def main():
    panel = pd.read_parquet(PANEL)
    pl = pd.read_parquet(PL)
    px_raw = pd.read_parquet(PROXY)
    px_raw = px_raw[px_raw['year'] != 2020]
    # PRIMARY (honest): shift proxy to PRIOR year so it's a leading indicator
    # matching anchor_fp semantics. proxy(y) = leverage data from y-1.
    px = px_raw[['mlbam_id', 'year', 'proxy_pl_rank_mid_inv']].copy()
    px['year'] = px['year'] + 1  # shift forward: y-1 data predicts y
    px = px.rename(columns={'proxy_pl_rank_mid_inv': 'proxy_pl_rank_mid_inv_lag1'})
    # Also keep contemporaneous version for comparison (matches PL panel semantics)
    px_contemp = px_raw[['mlbam_id', 'year', 'proxy_pl_rank_mid_inv']].copy()

    rp = prep_rp(panel)
    print(f'RP baseline rows: {len(rp)}')

    # Real-PL features (inverse transform)
    pl_rp = pl.copy()
    for c in ['pl_rank_early', 'pl_rank_mid', 'pl_rank_late']:
        pl_rp[f'{c}_inv'] = 1.0 / (pl_rp[c].astype(float) + 5.0)
    pl_feats = ['pl_rank_early_inv', 'pl_rank_mid_inv', 'pl_rank_late_inv']

    # Setup B: inner join with PL
    rp_pl = rp.merge(pl_rp[['mlbam_id', 'year'] + pl_feats], on=['mlbam_id', 'year'], how='inner')
    print(f'B (rp inner real PL): {len(rp_pl)} rows')

    # Setup C: union of real PL and proxy (using combined feature)
    # Use LAG-1 proxy (honest leading indicator) as primary
    px_sub = px.rename(columns={'proxy_pl_rank_mid_inv_lag1': 'proxy_pl_rank_mid_inv'})
    merged = rp.merge(pl_rp[['mlbam_id', 'year', 'pl_rank_mid_inv']],
                      on=['mlbam_id', 'year'], how='left')
    merged = merged.merge(px_sub, on=['mlbam_id', 'year'], how='left')
    merged['has_real_pl'] = merged['pl_rank_mid_inv'].notna().astype(int)
    merged['has_proxy'] = merged['proxy_pl_rank_mid_inv'].notna().astype(int)
    merged['pl_rank_mid_inv_combined'] = merged['pl_rank_mid_inv'].fillna(merged['proxy_pl_rank_mid_inv'])
    merged['is_proxy'] = (merged['has_real_pl'] == 0) & (merged['has_proxy'] == 1)
    merged['is_proxy_int'] = merged['is_proxy'].astype(int)

    union = merged[(merged['has_real_pl'] == 1) | (merged['has_proxy'] == 1)].copy()
    print(f'C (rp inner (PL union proxy)): {len(union)} rows; real_only={union["has_real_pl"].sum()} '
          f'proxy_used={union["is_proxy_int"].sum()}')

    # Coverage delta: original baseline panel vs union
    cov_gain = len(union) - rp_pl.shape[0]
    print(f'coverage gain vs B (real PL only): +{cov_gain} rows')

    # ---- Fits ----
    # A on union rows
    predA, actA, fA = fold_fit(union, BASELINE_FEATS)
    r2A = r2_score(actA, predA)

    # B on union rows requires PL feats; missing -> imputed inside fold mean
    union_for_B = union.copy()
    for c in pl_feats:
        if c not in union_for_B.columns:
            union_for_B[c] = np.nan
    # backfill from pl_rp on union
    union_for_B = union_for_B.drop(columns=[c for c in pl_feats if c in union_for_B.columns])
    union_for_B = union_for_B.merge(pl_rp[['mlbam_id', 'year'] + pl_feats],
                                    on=['mlbam_id', 'year'], how='left')
    predB, actB, fB = fold_fit(union_for_B, BASELINE_FEATS + pl_feats)
    r2B = r2_score(actB, predB)

    # C on union rows: combined feature + is_proxy flag
    cfeats = BASELINE_FEATS + ['pl_rank_mid_inv_combined', 'is_proxy_int']
    predC, actC, fC = fold_fit(union, cfeats)
    r2C = r2_score(actC, predC)

    # Per-fold convergence vs A
    fold_lifts = []
    for fa_, fc_ in zip(fA, fC):
        fold_lifts.append({'year': fa_['year'], 'n': fa_['n'],
                           'r2_A': round(fa_['r2'], 4),
                           'r2_C': round(fc_['r2'], 4),
                           'lift_C_minus_A': round(fc_['r2'] - fa_['r2'], 4)})
    nz = [f for f in fold_lifts if f['year'] != 2020]
    conv_pos = sum(1 for f in nz if f['lift_C_minus_A'] > 0)

    # Drop test on combined feature within C
    drops = {
        'pl_rank_mid_inv_combined': round(drop_test(union, cfeats, 'pl_rank_mid_inv_combined'), 4),
        'is_proxy_int': round(drop_test(union, cfeats, 'is_proxy_int'), 4),
        'anchor_fp': round(drop_test(union, cfeats, 'anchor_fp'), 4),
    }

    # Intersection test: does proxy help when REAL PL also exists?
    # On rp_pl rows, add LAG-1 proxy as additional feature
    rp_pl_aug = rp_pl.merge(px_sub, on=['mlbam_id', 'year'], how='left')
    if rp_pl_aug['proxy_pl_rank_mid_inv'].notna().any():
        predB2, actB2, _ = fold_fit(rp_pl_aug, BASELINE_FEATS + pl_feats)
        predBP, actBP, _ = fold_fit(rp_pl_aug, BASELINE_FEATS + pl_feats + ['proxy_pl_rank_mid_inv'])
        r2_intersect_B = r2_score(actB2, predB2)
        r2_intersect_BP = r2_score(actBP, predBP)
    else:
        r2_intersect_B = r2_intersect_BP = float('nan')

    # Bootstrap CI on (C - A) pooled lift on union rows
    rng = np.random.default_rng(42)
    n = len(actA)
    lifts = []
    for _ in range(500):
        idx = rng.integers(0, n, n)
        lifts.append(r2_score(actC[idx], predC[idx]) - r2_score(actA[idx], predA[idx]))
    ci_lo, ci_hi = float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5))

    summary = {
        'n_union': int(len(union)),
        'n_real_pl_only': int(rp_pl.shape[0]),
        'coverage_gain': int(cov_gain),
        'n_proxy_used': int(union['is_proxy_int'].sum()),
        'years': sorted(int(y) for y in union['year'].unique()),
        'r2_A_baseline_on_union': round(float(r2A), 4),
        'r2_B_real_PL_on_union': round(float(r2B), 4),
        'r2_C_PL_or_proxy_on_union': round(float(r2C), 4),
        'lift_C_minus_A': round(float(r2C - r2A), 4),
        'lift_C_minus_B': round(float(r2C - r2B), 4),
        'lift_C_minus_A_CI95': [round(ci_lo, 4), round(ci_hi, 4)],
        'convergence_ex2020_C_vs_A': f'{conv_pos}/{len(nz)}',
        'fold_lifts': fold_lifts,
        'drop_test_within_C': drops,
        'intersection_test': {
            'r2_B_PL_only_on_intersect': round(float(r2_intersect_B), 4),
            'r2_B_plus_proxy_on_intersect': round(float(r2_intersect_BP), 4),
            'lift': round(float(r2_intersect_BP - r2_intersect_B), 4),
        },
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2))
    print('\n=== Summary ===')
    print(json.dumps(summary, indent=2))

    # Recommendation
    pass_threshold = (summary['lift_C_minus_A'] >= 0.02) and (conv_pos >= 5)
    rec = 'PROPOSE_ADD' if pass_threshold else 'DO_NOT_ADD'

    md = f"""# RP leverage-proxy weight-blend test — 2026-06-05

**Recommendation: {rec}**

## Coverage gained
- Real PL-only RP rows (intersection): **{summary['n_real_pl_only']}**
- Union (real PL ∪ leverage proxy): **{summary['n_union']}**  (+{cov_gain})
- Rows where proxy is the sole leverage signal: **{summary['n_proxy_used']}**
- Years covered: {summary['years']}

## Proxy construction
For each (mlbam_id, year) with FG IP >= 20:
- `z_gmLI`, `z_ir_inv = 100 - is_pct`, `z_sd_minus_md = shutdowns - meltdowns`, each z-scored within year cohort
- `proxy_value = 0.5*z_gmLI + 0.3*z_ir_inv + 0.2*z_sd_minus_md` (renorm to 0.714/0.286 when IR missing)
- `proxy_rank` = within-year rank by `proxy_value` (1 = best)
- `proxy_pl_rank_mid_inv = 1 / (proxy_rank + 5)` — mirrors runtime transform in `lib/blend_score.py`
- Panel: `data/research/historical_panel/rp_leverage_proxy_panel.parquet` ({sum([0,0]) or 'see build script'} rows)

## R² lift (LOYO, ex-2020, target = `fp_per_g`)
| setup | features | pooled R² on union rows |
|---|---|---|
| A | baseline (anchor + arche + traj + age) | **{summary['r2_A_baseline_on_union']}** |
| B | A + real `pl_rank_{{early,mid,late}}_inv` (NaN-imputed) | {summary['r2_B_real_PL_on_union']} |
| C | A + `pl_rank_mid_inv_combined` + `is_proxy_int` | **{summary['r2_C_PL_or_proxy_on_union']}** |

- **Lift C − A: {summary['lift_C_minus_A']:+.4f}**   95% bootstrap CI {summary['lift_C_minus_A_CI95']}
- Lift C − B: {summary['lift_C_minus_B']:+.4f}
- Convergence (years with C>A, ex-2020): **{summary['convergence_ex2020_C_vs_A']}**

## Per-fold lifts (C − A)
"""
    md += '| year | n | r2_A | r2_C | lift |\n|---|---|---|---|---|\n'
    for f in fold_lifts:
        md += f"| {f['year']} | {f['n']} | {f['r2_A']} | {f['r2_C']} | {f['lift_C_minus_A']:+.4f} |\n"

    md += f"""
## Drop test within C (pooled in-sample ΔR²)
- `pl_rank_mid_inv_combined`: {summary['drop_test_within_C']['pl_rank_mid_inv_combined']}
- `is_proxy_int` (proxy-vs-real flag): {summary['drop_test_within_C']['is_proxy_int']}
- `anchor_fp` (sanity reference): {summary['drop_test_within_C']['anchor_fp']}

## Intersection test (does proxy add lift when real PL is already present?)
- Real PL on intersection rows: R² = {summary['intersection_test']['r2_B_PL_only_on_intersect']}
- Real PL + proxy: R² = {summary['intersection_test']['r2_B_plus_proxy_on_intersect']}
- Lift: **{summary['intersection_test']['lift']:+.4f}**

## Recommendation rationale
Threshold to ship: lift ≥ +0.02 AND convergence ≥ 5/{len(nz)} years.

- Lift hit: {'YES' if summary['lift_C_minus_A'] >= 0.02 else 'NO'} ({summary['lift_C_minus_A']:+.4f})
- Convergence hit: {'YES' if conv_pos >= 5 else 'NO'} ({conv_pos}/{len(nz)})
- **Action:** {'Propose adding `pl_rank_mid_inv_combined` + `is_proxy_int` to `VALIDATED_WEIGHTS["RP"]["with_pl_or_proxy"]` variant. Cleanup #3 to execute refit + wire into `lib/blend_score.py`.' if pass_threshold else 'Do not promote. Proxy does not clear the +0.02 R² / 5-year-convergence bar. Keep as a coverage-honest diagnostic only; do not wire into blend_score.'}

## Honesty caveats
1. **Selection bias:** middle relievers receive low-leverage opportunities precisely because they have weaker stuff/track record. The proxy partially encodes the same talent signal as `anchor_fp` and `arche_overall_prior`, which inflates drop-test redundancy.
2. **2026 in-progress** excluded from fit (year filter ≤ 2025).
3. **Confidence tier** ('low' for IP < 25 or missing IR) is carried in the panel — downstream consumers should respect it.
4. **No `lib/blend_score.py` edits this PR.** Cleanup #3 owns wiring.
"""
    OUT_MD.write_text(md, encoding='utf-8')
    print(f'\nwrote {OUT_MD}')
    print(f'wrote {OUT_JSON}')


if __name__ == '__main__':
    main()
