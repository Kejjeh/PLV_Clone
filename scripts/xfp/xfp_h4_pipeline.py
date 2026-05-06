"""
xfp_h4_pipeline.py — H4 adds team run-environment as a lag-1 feature.

Targets the H2-documented `team_context_bias = -0.039` (model under-projects
high-context teams). The Christian Walker callout (HOU, +0.32 FP/PA above
projection) is the canonical case.

team_run_env_lag1 = mean fp_per_pa_actual in year T-1 for the batter's
year-T team, computed across all qualified (≥ 200 PA) hitters on that team
EXCLUDING the focal batter (so the feature is non-circular at training time).

Decision gate: ships if cross_year_r ≥ H2 + 0.01 AND |power_bias_hi| ≤ 1.0
AND |team_context_bias| improves vs H2's -0.039.
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
    TRAIN_MIN_PA, EVAL_MIN_PA,
)


def add_team_run_env(df: pd.DataFrame) -> pd.DataFrame:
    """Add `team_run_env_lag1` to each row.

    For a (batter, year=T) row with team=X, the feature is:
      mean(fp_per_pa_actual) over hitters on team X in year T-1 with pa ≥ 200,
      excluding the focal batter himself (to keep the feature non-circular).

    Hitters in year T who weren't in any team's year-T-1 cohort get NaN
    (rookies / late-season call-ups / cross-league trades).
    """
    df = df.copy()
    # Build a lookup: for each (year, team), list of (batter, pa, fp_per_pa)
    yt = df[df['pa'] >= 200].dropna(subset=['team', 'fp_per_pa_actual']).copy()

    # PA-weighted team mean fp_per_pa, excluding focal batter
    rows: list[float] = []
    yt_groups = yt.groupby(['year', 'team'])
    # Pre-aggregate per (year, team) for speed
    team_agg = yt_groups.apply(lambda g: pd.Series({
        'pa_sum': g['pa'].sum(),
        'wfp_sum': (g['pa'] * g['fp_per_pa_actual']).sum(),
        'n': len(g),
    })).reset_index()
    team_agg_idx = team_agg.set_index(['year', 'team'])

    # Per-row contribution map for leave-one-out
    yt_idx = yt.set_index(['year', 'team', 'batter'])

    def env_for(row) -> float:
        target_year = row['year']
        team = row.get('team')
        batter = row.get('batter')
        if not isinstance(team, str) or not team:
            return np.nan
        prior_year = target_year - 1
        key = (prior_year, team)
        if key not in team_agg_idx.index:
            return np.nan
        agg = team_agg_idx.loc[key]
        pa_sum = float(agg['pa_sum'])
        wfp_sum = float(agg['wfp_sum'])
        # Subtract focal batter's prior-year contribution if present
        try:
            self_row = yt_idx.loc[(prior_year, team, batter)]
            if isinstance(self_row, pd.DataFrame):
                self_row = self_row.iloc[0]
            self_pa = float(self_row['pa'])
            self_fp = float(self_row['fp_per_pa_actual'])
            pa_sum -= self_pa
            wfp_sum -= self_pa * self_fp
        except KeyError:
            pass
        if pa_sum <= 0:
            return np.nan
        return wfp_sum / pa_sum

    df['team_run_env_lag1'] = df.apply(env_for, axis=1)
    return df


def main():
    df = pd.read_csv(SUBSTRATE)
    print(f'=== H4 — substrate {len(df)} rows ===')
    df = add_team_run_env(df)
    cov = df['team_run_env_lag1'].notna().sum()
    print(f'team_run_env_lag1 coverage: {cov} / {len(df)} ({cov/len(df):.1%})')
    sub = df[df['pa'] >= EVAL_MIN_PA]
    print(f'  ≥{EVAL_MIN_PA} PA cohort: {sub["team_run_env_lag1"].notna().sum()} / {len(sub)}')
    print(f'  Distribution: {sub["team_run_env_lag1"].describe().to_dict()}\n')

    # H2 reference
    H2_FEATS = [
        'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
        'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
        'sprint_speed', 'sb_per_pa',
    ]
    h2 = cross_year_evaluate(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']),
                              H2_FEATS, label='H2 (production)')
    print(f'H2 reference:\n  {fmt_result(h2)}\n')

    # H4 — H2 + team_run_env_lag1
    H4_POOL = H2_FEATS + ['team_run_env_lag1']
    df_pool = df.dropna(subset=H4_POOL + ['fp_per_pa_actual']).copy()
    print(f'After dropna on H4 pool: {len(df_pool)} rows ({(df_pool["pa"]>=300).sum()} ≥300 PA)\n')

    print('--- H4 full pool ---')
    res = cross_year_evaluate(df_pool, H4_POOL, label='H4 (H2 + team_env)')
    print('  ' + fmt_result(res))
    s_full = score_fn(res['r'], res['power_bias_hi'])
    print(f'  vs H2: r {res["r"] - h2["r"]:+.4f}, '
          f'team_bias {res["team_context_bias"] - h2["team_context_bias"]:+.4f}, '
          f'score {s_full - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}\n')

    # Backward elimination on H4 pool
    cur = list(H4_POOL)
    history = [(list(cur), res, s_full)]
    best_score, best_feats, best_res = s_full, list(cur), res
    step = 0
    while len(cur) > 5:
        step += 1
        print(f'Step {step}: try dropping each of {len(cur)}')
        candidates = []
        for f in cur:
            trial = [x for x in cur if x != f]
            r = cross_year_evaluate(df_pool, trial, label=f'-{f}')
            sc = score_fn(r['r'], r['power_bias_hi'])
            candidates.append((f, r, sc))
        candidates.sort(key=lambda x: -x[2])
        f_drop, r_top, sc_top = candidates[0]
        print(f'  Best drop: {f_drop:<22s}  r={r_top["r"]:.4f}  pwr_bias={r_top["power_bias_hi"]:+.3f}  '
              f'team_bias={r_top["team_context_bias"]:+.3f}  score={sc_top:.4f}  (was {best_score:.4f})')
        cur = [x for x in cur if x != f_drop]
        history.append((list(cur), r_top, sc_top))
        if sc_top > best_score + 0.0001:
            best_score = sc_top
            best_feats = list(cur)
            best_res = r_top
            print(f'  ↑ NEW BEST score={best_score:.4f}, feats={len(best_feats)}')
        elif sc_top < best_score - 0.05:
            print('  ↓ score dropped > 0.05 from best; stopping BE')
            break

    print('\n=== H4 winner ===')
    print('  ' + fmt_result(best_res))
    print(f'  Features ({len(best_feats)}): {best_feats}')
    has_team_env = 'team_run_env_lag1' in best_feats
    print(f'  team_run_env_lag1 retained: {has_team_env}')

    print('\n=== Decision gate ===')
    target_r = h2['r'] + 0.01
    print(f'  cross_year_r {best_res["r"]:.4f} ≥ H2 + 0.01 = {target_r:.4f}? '
          f'{"PASS" if best_res["r"] >= target_r else "FAIL"}')
    print(f'  |power_bias_hi| {abs(best_res["power_bias_hi"]):.4f} ≤ 1.0? '
          f'{"PASS" if abs(best_res["power_bias_hi"]) <= 1.0 else "FAIL"}')
    print(f'  team_context_bias {best_res["team_context_bias"]:+.4f} (H2: {h2["team_context_bias"]:+.4f}) '
          f'shrunk? {"PASS" if abs(best_res["team_context_bias"]) < abs(h2["team_context_bias"]) else "FAIL"}')
    print(f'  Score (T=1) {best_score:.4f} > H2 {score_fn(h2["r"], h2["power_bias_hi"]):.4f}? '
          f'{"PASS" if best_score > score_fn(h2["r"], h2["power_bias_hi"]) else "FAIL"}')

    # Persist
    out = []
    for feats, r, sc in history:
        out.append({'n_feats': len(feats), 'features': '|'.join(feats),
                    'r': r['r'], 'power_bias_hi': r['power_bias_hi'],
                    'team_context_bias': r['team_context_bias'],
                    'rmse': r['rmse'], 'mae': r['mae'], 'n': r['n'],
                    'score_T1': sc})
    pd.DataFrame(out).to_csv(ROOT / 'data' / 'research' / 'xfp_h4_be_log.csv', index=False)
    print('\nWrote BE log → data/research/xfp_h4_be_log.csv')
    print(f'\nH4_FEATS = {best_feats}')


if __name__ == '__main__':
    main()
