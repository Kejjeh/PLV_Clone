"""fit_closer_il_bundle_validation.py

Joint validation of the 3-feature closer-IL sibling bundle as a candidate
addition to FEATS_RPRS2 under the 9-rule multi-test protocol.

Bundle:
  - is_team_prior_closer
  - prior_closer_returned_recently
  - prior_closer_days_since_return

Outputs:
  data/research/validation_runs/closer_il_bundle_validation_2026-06-06.md
  data/research/validation_runs/closer_il_bundle_validation_2026-06-06.json

Mirrors the LOYO RidgeCV harness used in fit_prior_closer_on_il_validation.py
to keep the baseline honest (Rule 9).
"""
from __future__ import annotations
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_relievers_2018_2026.csv'
OUT_MD   = ROOT / 'data' / 'research' / 'validation_runs' / 'closer_il_bundle_validation_2026-06-06.md'
OUT_JSON = ROOT / 'data' / 'research' / 'validation_runs' / 'closer_il_bundle_validation_2026-06-06.json'

TARGET = 'fp_year_total'
EVAL_G_MIN = 5
TRAIN_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]
BUNDLE = ['is_team_prior_closer', 'prior_closer_returned_recently', 'prior_closer_days_since_return']
SINGLE = 'is_team_prior_closer'
RNG_SEED = 20260606
N_BOOT = 200

BASE_FEATS = [
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
    'xwoba_per_pa_to', 'avg_velo_to', 'zone_pct_to', 'o_swing_pct_to',
    'g_to', 'ip_to', 'fp_skill_to',
    'role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1',
    'sv_lag1', 'hld_lag1', 'g_lag1', 'ip_lag1',
    'fp_per_g_lag1', 'fp_lag1',
    'split_day',
]
NEW_FEATS = [
    'gf_pct_to', 'sv_per_g_to', 'hld_per_g_to', 'sv_plus_hld_to',
    'fp_with_role_to', 'sv_per_g_lag1', 'hld_per_g_lag1',
]
FEATS_RPRS2 = BASE_FEATS + NEW_FEATS


def _fit_loyo(df: pd.DataFrame, feats: list[str], common_mask_feats: list[str]) -> dict:
    """Fit LOYO; require non-null over `common_mask_feats` so all model variants
    are evaluated on the SAME rows (alignment for bootstrap)."""
    df = df.dropna(subset=common_mask_feats + [TARGET]).copy()
    df = df[df['year'].isin(TRAIN_YEARS) & (df['g_to'] >= EVAL_G_MIN)]
    per_year, preds_all, acts_all, year_all = {}, [], [], []
    for held in TRAIN_YEARS:
        tr = df[df['year'] != held]
        te = df[df['year'] == held]
        if len(tr) < 100 or len(te) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(tr[feats].values, tr[TARGET].values)
        preds = pipe.predict(te[feats].values)
        acts = te[TARGET].values
        r = float(np.corrcoef(preds, acts)[0, 1])
        per_year[held] = {'r': round(r, 4), 'r2': round(r * r, 4),
                          'mae': round(float(np.mean(np.abs(preds - acts))), 2),
                          'n': int(len(te))}
        preds_all.extend(preds.tolist())
        acts_all.extend(acts.tolist())
        year_all.extend([held] * len(te))
    preds_arr = np.array(preds_all); acts_arr = np.array(acts_all)
    pooled_r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
    return {
        'per_year': per_year,
        'pooled_r': round(pooled_r, 4),
        'pooled_r2': round(pooled_r * pooled_r, 4),
        'pooled_mae': round(float(np.mean(np.abs(preds_arr - acts_arr))), 2),
        'n': int(len(preds_arr)),
        'preds': preds_arr,
        'acts': acts_arr,
        'years': np.array(year_all),
    }


def _bootstrap_delta_r2(preds_a: np.ndarray, preds_b: np.ndarray,
                        acts: np.ndarray, n_boot: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = len(acts)
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        ra = np.corrcoef(preds_a[idx], acts[idx])[0, 1]
        rb = np.corrcoef(preds_b[idx], acts[idx])[0, 1]
        deltas[i] = (rb * rb) - (ra * ra)
    lo = float(np.quantile(deltas, 0.025))
    hi = float(np.quantile(deltas, 0.975))
    point = float(np.mean(deltas))
    frac_le_zero = float(np.mean(deltas <= 0))
    p = 2 * min(frac_le_zero, 1 - frac_le_zero)
    return {'delta_r2_mean': round(point, 5),
            'ci_lo': round(lo, 5), 'ci_hi': round(hi, 5),
            'p_two_sided': round(p, 4), 'n_boot': n_boot}


def main():
    df = pd.read_csv(ROLLING_CSV)
    print(f'Loaded substrate: {len(df):,} rows')
    for f in BUNDLE:
        print(f'  {f}: coverage={df[f].notna().mean():.4f}  '
              f'pos_rate={(df[f]==1).mean() if df[f].dtype != float or set(df[f].dropna().unique()) <= {0,1,0.0,1.0} else float("nan"):.4f}')

    bundle_feats = FEATS_RPRS2 + BUNDLE
    single_feats = FEATS_RPRS2 + [SINGLE]
    # Common mask: require all 3 bundle features present so all 3 fits use SAME rows
    common = FEATS_RPRS2 + BUNDLE

    print('\nFitting baseline (FEATS_RPRS2, 28 features)...')
    base = _fit_loyo(df, FEATS_RPRS2, common)
    print(f'  pooled r={base["pooled_r"]:.4f} r2={base["pooled_r2"]:.4f} '
          f'mae={base["pooled_mae"]:.2f} n={base["n"]:,}')

    print('\nFitting +single is_team_prior_closer (29 features)...')
    single = _fit_loyo(df, single_feats, common)
    print(f'  pooled r={single["pooled_r"]:.4f} r2={single["pooled_r2"]:.4f} '
          f'mae={single["pooled_mae"]:.2f} n={single["n"]:,}')

    print('\nFitting +bundle (31 features)...')
    bundle = _fit_loyo(df, bundle_feats, common)
    print(f'  pooled r={bundle["pooled_r"]:.4f} r2={bundle["pooled_r2"]:.4f} '
          f'mae={bundle["pooled_mae"]:.2f} n={bundle["n"]:,}')

    assert base['n'] == single['n'] == bundle['n'], 'Sample size mismatch'
    assert np.array_equal(base['acts'], bundle['acts']), 'Actuals misaligned'

    print('\nPer-year convergence (Δr, bundle − baseline):')
    conv = {}
    pos = 0; evaluated = 0
    for yr in TRAIN_YEARS:
        if yr in base['per_year'] and yr in bundle['per_year']:
            db = base['per_year'][yr]['r']
            dc = bundle['per_year'][yr]['r']
            delta = round(dc - db, 4)
            conv[yr] = {'baseline_r': db, 'bundle_r': dc, 'delta_r': delta}
            sign = '+' if delta > 0 else ('0' if delta == 0 else '-')
            print(f'  {yr}: base_r={db:.4f}  bundle_r={dc:.4f}  Δ={delta:+.4f}  [{sign}]')
            evaluated += 1
            if delta > 0: pos += 1
    print(f'  positive folds: {pos}/{evaluated}')

    print(f'\nBootstrap 95% CI on Δr² bundle vs baseline ({N_BOOT} resamples)...')
    boot = _bootstrap_delta_r2(base['preds'], bundle['preds'], base['acts'],
                               N_BOOT, RNG_SEED)
    pooled_delta_r2 = round(bundle['pooled_r2'] - base['pooled_r2'], 5)
    print(f'  pooled Δr² = {pooled_delta_r2:+.5f}')
    print(f'  bootstrap Δr² = {boot["delta_r2_mean"]:+.5f}  '
          f'[{boot["ci_lo"]:+.5f}, {boot["ci_hi"]:+.5f}]')
    print(f'  two-sided p (joint test) = {boot["p_two_sided"]:.4f}')

    # Drop test: refit bundle without each feature
    print('\nDrop test: removing each feature individually from bundle...')
    drop_tests = {}
    for f in BUNDLE:
        feats_minus = [x for x in bundle_feats if x != f]
        fit_minus = _fit_loyo(df, feats_minus, common)
        delta = round(bundle['pooled_r2'] - fit_minus['pooled_r2'], 5)
        drop_tests[f] = {
            'pooled_r2_without': fit_minus['pooled_r2'],
            'incremental_r2': delta,
        }
        print(f"  drop {f:38s} → bundle_r²={bundle['pooled_r2']:.4f}  "
              f"without={fit_minus['pooled_r2']:.4f}  incremental Δr²={delta:+.5f}")

    # Verdict
    pass_lift = pooled_delta_r2 >= 0.01
    pass_conv = pos >= 5
    pass_p    = boot['p_two_sided'] < 0.0056
    passes    = sum([pass_lift, pass_conv, pass_p])
    if passes == 3:
        verdict = 'PROMOTE'
    elif passes == 0:
        verdict = 'REJECT'
    else:
        verdict = 'HOLD'

    print(f'\nGate check:')
    print(f'  pooled Δr² ≥ +0.01:        {pass_lift}  ({pooled_delta_r2:+.5f})')
    print(f'  convergence ≥ 5/{evaluated} folds:  {pass_conv}  ({pos}/{evaluated})')
    print(f'  joint p < 0.0056:          {pass_p}  ({boot["p_two_sided"]:.4f})')
    print(f'\nVERDICT: {verdict}')

    # Canonical RP scoring
    print('\nFitting final models on full TRAIN_YEARS for canonical scoring...')
    df_fit = df.dropna(subset=bundle_feats + [TARGET]).copy()
    df_fit = df_fit[df_fit['year'].isin(TRAIN_YEARS) & (df_fit['g_to'] >= EVAL_G_MIN)]
    pipe_base = Pipeline([('sc', StandardScaler()),
                          ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe_base.fit(df_fit[FEATS_RPRS2].values, df_fit[TARGET].values)
    pipe_bundle = Pipeline([('sc', StandardScaler()),
                            ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe_bundle.fit(df_fit[bundle_feats].values, df_fit[TARGET].values)

    df26 = df[(df['year'] == 2026)].copy()
    df26 = df26.sort_values('split_day').groupby('pitcher', as_index=False).tail(1)
    name_csv = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'
    canonical_names = ['Helsley', 'Duran', 'Fairbanks', 'Tanner Scott', 'Morejón', 'Morejon', 'Palencia']
    name_map = {}
    if name_csv.exists():
        n = pd.read_csv(name_csv)
        name_col = 'name_api' if 'name_api' in n.columns else ('name' if 'name' in n.columns else ('player' if 'player' in n.columns else None))
        id_col = 'pitcher' if 'pitcher' in n.columns else ('mlbam' if 'mlbam' in n.columns else None)
        if name_col and id_col:
            for _, r in n.iterrows():
                try:
                    name_map[int(r[id_col])] = str(r[name_col])
                except Exception:
                    pass

    canonical_rows = []
    for _, r in df26.iterrows():
        if any(pd.isna(r[f]) for f in bundle_feats):
            continue
        nm = name_map.get(int(r['pitcher']), '')
        if not any(c.lower() in nm.lower() for c in canonical_names):
            continue
        base_pred = float(pipe_base.predict([[r[f] for f in FEATS_RPRS2]])[0])
        bundle_pred = float(pipe_bundle.predict([[r[f] for f in bundle_feats]])[0])
        canonical_rows.append({
            'name': nm, 'pitcher': int(r['pitcher']), 'team': r.get('team_abbr', ''),
            'split_day': int(r['split_day']),
            'is_team_prior_closer': int(r['is_team_prior_closer']),
            'prior_closer_returned_recently': int(r['prior_closer_returned_recently']),
            'prior_closer_days_since_return': float(r['prior_closer_days_since_return']),
            'ros_baseline': round(base_pred, 2),
            'ros_bundle': round(bundle_pred, 2),
            'delta': round(bundle_pred - base_pred, 2),
        })

    print('\nCanonical RP deltas:')
    if not canonical_rows:
        print('  (no canonical RPs matched — test uninformative for current roster)')
    for c in canonical_rows:
        print(f"  {c['name']:24s} team={c['team']:4s} "
              f"PC={c['is_team_prior_closer']} RR={c['prior_closer_returned_recently']} "
              f"DSR={c['prior_closer_days_since_return']:6.1f}  "
              f"base={c['ros_baseline']:6.2f} bundle={c['ros_bundle']:6.2f} "
              f"Δ={c['delta']:+.2f}")

    out = {
        'date': '2026-06-06',
        'test': 'closer_il_bundle_joint',
        'bundle_features': BUNDLE,
        'n_total_rows': int(len(df)),
        'n_eval': int(base['n']),
        'coverage': {f: round(float(df[f].notna().mean()), 4) for f in BUNDLE},
        'baseline': {
            'feats_n': len(FEATS_RPRS2),
            'pooled_r': base['pooled_r'], 'pooled_r2': base['pooled_r2'],
            'pooled_mae': base['pooled_mae'],
            'per_year': base['per_year'],
        },
        'single_is_team_prior_closer': {
            'feats_n': len(single_feats),
            'pooled_r': single['pooled_r'], 'pooled_r2': single['pooled_r2'],
            'pooled_mae': single['pooled_mae'],
            'pooled_delta_r2_vs_base': round(single['pooled_r2'] - base['pooled_r2'], 5),
            'per_year': single['per_year'],
        },
        'bundle': {
            'feats_n': len(bundle_feats),
            'pooled_r': bundle['pooled_r'], 'pooled_r2': bundle['pooled_r2'],
            'pooled_mae': bundle['pooled_mae'],
            'per_year': bundle['per_year'],
        },
        'convergence': {'positive_folds': pos, 'evaluated_folds': evaluated,
                        'per_year': conv},
        'lift': {
            'pooled_delta_r2': pooled_delta_r2,
            'pooled_delta_mae': round(bundle['pooled_mae'] - base['pooled_mae'], 2),
            'bootstrap': boot,
        },
        'drop_tests': drop_tests,
        'gate': {
            'pass_lift_ge_0.01': bool(pass_lift),
            'pass_conv_ge_5': bool(pass_conv),
            'pass_joint_p_lt_0.0056': bool(pass_p),
            'gates_passed': int(passes),
        },
        'verdict': verdict,
        'canonical_rps': canonical_rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print(f'\nWrote {OUT_JSON}')
    return out


if __name__ == '__main__':
    main()
