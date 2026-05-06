"""
xfp_h9_pipeline.py — H9 cohort decomposition by position group.

Compendium §10.5 lists confounders to control for, including position.
H9 tests two architectures:

  H9a: Add primary_position as one-hot categorical feature to H2 pool.
  H9b: Train separate H2 models per position group; evaluate per-cohort,
       then aggregate to overall cross-year r.

Position groups (per typical fantasy convention):
  - C   (catchers — distinct profile, lower offensive bar)
  - IF  (1B/2B/3B/SS combined)
  - OF  (LF/CF/RF combined)
  - DH  (designated hitter — power-skewed)

Decision gate: H9 ships if cross_year_r ≥ H2 + 0.01 AND |power_bias_hi| ≤ 1.0.
"""
from __future__ import annotations
import sys
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'

sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_h_eval import (
    cross_year_evaluate, score_fn, fmt_result,
    TRAIN_MIN_PA, EVAL_MIN_PA, TRANSITIONS, power_bias_hi, team_context_bias,
)

H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]


def load_with_positions() -> pd.DataFrame:
    """Substrate + primary_position from MLB Stats API (cached per-year via
    player_positions_{year}.json — we already have these for the position map)."""
    df = pd.read_csv(SUBSTRATE)
    pos_df_rows = []
    import json
    for yr in sorted(df['year'].unique()):
        path = ROOT / 'data' / 'models' / f'player_positions_{int(yr)}.json'
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            if not data:
                continue
            for r in data:
                pos_df_rows.append({
                    'batter': int(r['player_id']),
                    'year': int(yr),
                    'primary_position': r.get('primary_position'),
                })
        except Exception:
            continue
    if pos_df_rows:
        pos = pd.DataFrame(pos_df_rows)
        df = df.merge(pos, on=['batter', 'year'], how='left')
    else:
        df['primary_position'] = None

    # Group: C / IF / OF / DH / OTHER
    def group(p):
        if p is None or pd.isna(p):
            return None
        if p == 'C':
            return 'C'
        if p in {'1B', '2B', '3B', 'SS'}:
            return 'IF'
        if p in {'LF', 'CF', 'RF', 'OF'}:
            return 'OF'
        if p == 'DH':
            return 'DH'
        return None
    df['pos_group'] = df['primary_position'].apply(group)
    return df


def evaluate_per_cohort(df: pd.DataFrame, feats: list[str]):
    """For each pos_group, train H2 model on prior years restricted to that
    group; evaluate on test years restricted to same group. Aggregate.

    Train: years < yr_test, year != 2020, pa ≥ 200, pos_group == group, feats present.
    Test:  year == yr_test, pa ≥ 300, pos_group == group, feats present.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    groups = ['C', 'IF', 'OF', 'DH']
    per_group_results = {}
    all_preds, all_acts, all_res = [], [], []

    for grp in groups:
        df_grp = df[df['pos_group'] == grp].copy()
        preds_grp, acts_grp, res_grp = [], [], []
        for yr_train, yr_test in TRANSITIONS:
            train_pool = df_grp[
                (df_grp['year'] < yr_test) & (df_grp['year'] != 2020)
                & (df_grp['pa'] >= TRAIN_MIN_PA)
            ].dropna(subset=feats + ['fp_per_pa_actual'])
            if len(train_pool) < 30:
                continue
            test_year = df_grp[(df_grp['year'] == yr_test) & (df_grp['pa'] >= EVAL_MIN_PA)]
            train_year = df_grp[(df_grp['year'] == yr_train) & (df_grp['pa'] >= TRAIN_MIN_PA)]
            shared = set(train_year['batter']) & set(test_year['batter'])
            train_year = train_year[train_year['batter'].isin(shared)]
            test_year  = test_year [test_year ['batter'].isin(shared)].copy()
            test_meta = test_year[['batter','fp_per_pa_actual','hr_per_pa','team']].rename(
                columns={'hr_per_pa':'_hr','team':'_team','fp_per_pa_actual':'_fp'})
            merged = test_meta.merge(train_year[['batter'] + feats], on='batter') \
                              .dropna(subset=feats + ['_fp'])
            if len(merged) < 5:
                continue
            pipe = Pipeline([('sc', StandardScaler()),
                              ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train_pool[feats].values, train_pool['fp_per_pa_actual'].values)
            merged['pred'] = pipe.predict(merged[feats].values)
            merged['transition'] = f'{yr_train}->{yr_test}'
            preds_grp.extend(merged['pred'].tolist())
            acts_grp.extend(merged['_fp'].tolist())
            res_grp.append(merged)

        if not res_grp:
            per_group_results[grp] = {'r': np.nan, 'n': 0}
            continue
        rs = pd.concat(res_grp, ignore_index=True)
        rs['resid'] = rs['pred'] - rs['_fp']
        r = float(np.corrcoef(preds_grp, acts_grp)[0, 1]) if len(preds_grp) > 1 else np.nan
        per_group_results[grp] = {
            'r': round(r, 4),
            'rmse': round(float(np.sqrt(np.mean(rs['resid']**2))), 4),
            'mae': round(float(np.mean(rs['resid'].abs())), 4),
            'n': len(rs),
            'n_train_avg': len(train_pool),
        }
        # also build the rs to compute power_bias / team_bias on the merged frame
        rs = rs.rename(columns={'_hr': '_hr_per_pa_test', '_team': '_team_test', '_fp': '_fp_per_pa_actual_test'})
        per_group_results[grp]['power_bias_hi'] = power_bias_hi(rs)
        per_group_results[grp]['team_context_bias'] = team_context_bias(rs)
        all_preds.extend(preds_grp)
        all_acts.extend(acts_grp)
        all_res.append(rs)

    overall_r = float(np.corrcoef(all_preds, all_acts)[0, 1]) if len(all_preds) > 1 else np.nan
    rs_all = pd.concat(all_res, ignore_index=True)
    rs_all['resid'] = rs_all['pred'] - rs_all['_fp_per_pa_actual_test']
    overall = {
        'r': round(overall_r, 4),
        'power_bias_hi': power_bias_hi(rs_all),
        'team_context_bias': team_context_bias(rs_all),
        'rmse': round(float(np.sqrt(np.mean(rs_all['resid']**2))), 4),
        'mae': round(float(np.mean(rs_all['resid'].abs())), 4),
        'n': len(rs_all),
    }
    return per_group_results, overall


def main():
    df = load_with_positions()
    print(f'=== H9 — cohort decomposition === substrate {len(df)} rows')
    print('Position group coverage:')
    print(df['pos_group'].value_counts(dropna=False).to_string())
    print()

    # Reference H2 unified
    print('--- Reference: H2 unified Ridge ---')
    h2 = cross_year_evaluate(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']), H2_FEATS, 'H2')
    s_h2 = score_fn(h2['r'], h2['power_bias_hi'])
    print(f'  {fmt_result(h2)}\n')

    # H9a: position one-hot encoded as feature
    print('--- H9a: H2 + position one-hot ---')
    df_oh = df.copy()
    pos_cols = []
    for g in ['IF', 'OF', 'C', 'DH']:
        col = f'pos_{g}'
        df_oh[col] = (df_oh['pos_group'] == g).astype(float)
        pos_cols.append(col)
    h9a_pool = H2_FEATS + pos_cols
    h9a = cross_year_evaluate(df_oh.dropna(subset=h9a_pool + ['fp_per_pa_actual']), h9a_pool, 'H9a')
    s_h9a = score_fn(h9a['r'], h9a['power_bias_hi'])
    print(f'  {fmt_result(h9a)}')
    print(f'  Δ vs H2: r {h9a["r"]-h2["r"]:+.4f}, score {s_h9a-s_h2:+.4f}\n')

    # H9b: train separate model per cohort
    print('--- H9b: Per-cohort separate Ridge ---')
    per_grp, overall = evaluate_per_cohort(df, H2_FEATS)
    print(f'  Per-group cross-year r:')
    for g, r in per_grp.items():
        if pd.isna(r.get('r')):
            print(f'    {g}: insufficient data')
        else:
            print(f'    {g}: r={r["r"]:.4f}  pwr_bias={r.get("power_bias_hi", 0):+.3f}  '
                  f'team_bias={r.get("team_context_bias", 0):+.3f}  '
                  f'mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'\n  Overall (aggregated across cohorts):')
    print(f'    r={overall["r"]:.4f}  pwr_bias={overall["power_bias_hi"]:+.3f}  '
          f'team_bias={overall["team_context_bias"]:+.3f}  mae={overall["mae"]:.4f}  n={overall["n"]}')
    s_h9b = score_fn(overall['r'], overall['power_bias_hi'])
    print(f'    score={s_h9b:.4f}  Δ vs H2: r {overall["r"]-h2["r"]:+.4f}, score {s_h9b-s_h2:+.4f}\n')

    print('=== Summary ===')
    print(f'  H2 unified:           r={h2["r"]:.4f}  score={s_h2:.4f}')
    print(f'  H9a (+ position OH):  r={h9a["r"]:.4f}  score={s_h9a:.4f}  Δ={s_h9a-s_h2:+.4f}')
    print(f'  H9b (per-cohort):     r={overall["r"]:.4f}  score={s_h9b:.4f}  Δ={s_h9b-s_h2:+.4f}')

    print('\n=== Decision gate ===')
    target_r = h2['r'] + 0.01
    for label, r, s in [('H9a', h9a['r'], s_h9a), ('H9b', overall['r'], s_h9b)]:
        passes_r = r >= target_r
        passes_s = s > s_h2
        print(f'  {label}:  r {r:.4f} ≥ {target_r:.4f}? {"PASS" if passes_r else "FAIL"}  |  score > H2? {"PASS" if passes_s else "FAIL"}')


if __name__ == '__main__':
    main()
