"""
xfp_h2_pipeline.py — H2 Ridge model with backward elimination on hitter features.

Mirrors `scripts/xfp/xfp_v8_pipeline.py` for hitters. Starts from the
H1.5-screened candidate pool, runs backward elimination ranked by
score_fn = r * 3 - max(0, |power_bias_hi| - 1.0) * 0.5, and reports the
winning feature set.

Decision gate (per the plan):
    H2 ships if cross_year_r ≥ B_lag + 0.02 AND |power_bias_hi| ≤ 1.0
    (B_lag = naive prior-year FP/PA baseline, established in xfp_h_eval.py)

Both bias metrics are tracked at every step. team_context_bias is reported
but doesn't gate on it.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'

# Re-import the harness from xfp_h_eval
import sys
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_h_eval import (
    cross_year_evaluate,
    lag_baseline_evaluate,
    score_fn,
    fmt_result,
    TRAIN_MIN_PA,
    EVAL_MIN_PA,
    TRANSITIONS,
)

# H2 candidate pool — H1.5 KEEP + sprint_speed + sb_per_pa (both WATCH but plan-required)
# Drop o_swing_pct (duplicate of chase_pct in our substrate).
POOL = [
    'xwoba_per_pa', 'c_plus_swstr', 'avg_ev', 'iso', 'k_pct', 'hr_per_pa',
    'hard_hit_pct', 'contact_pct', 'whiff_pct', 'swstr_pct', 'bb_pct',
    'z_contact_pct', 'xwoba_on_contact', 'barrel_pct', 'zone_pct',
    'chase_pct', 'in_play_pct', 'sprint_speed', 'sb_per_pa',
]


def main():
    df = pd.read_csv(SUBSTRATE)
    print(f'=== H2 backward elimination — substrate {SUBSTRATE.name}: {len(df)} rows ===')
    print(f'Pool ({len(POOL)} features): {POOL}\n')

    # Reference baseline
    base = lag_baseline_evaluate(df)
    print(f'Reference baseline:\n  {fmt_result(base)}\n')
    bar = base['r']

    # Drop rows with any NaN in pool — needed for stable BE comparison
    df_pool = df.dropna(subset=POOL + ['fp_per_pa_actual']).copy()
    print(f'After dropna on pool features: {len(df_pool)} rows')
    print(f'  ≥{TRAIN_MIN_PA} PA: {(df_pool["pa"] >= TRAIN_MIN_PA).sum()}')
    print(f'  ≥{EVAL_MIN_PA} PA: {(df_pool["pa"] >= EVAL_MIN_PA).sum()}\n')

    # Initial fit on full pool
    print('--- Step 0: full pool ---')
    res = cross_year_evaluate(df_pool, POOL, label=f'pool[{len(POOL)}]')
    s = score_fn(res['r'], res['power_bias_hi'])
    print(fmt_result(res))
    print(f'  vs B_lag improvement: {res["r"] - bar:+.4f}\n')

    # Backward elimination: drop the feature whose removal preserves (or improves) score the most
    cur_feats = list(POOL)
    history = [(list(cur_feats), res, s)]
    best_score = s
    best_feats = list(cur_feats)
    best_res = res

    step = 0
    while len(cur_feats) > 3:
        step += 1
        print(f'--- Step {step}: try dropping each of {len(cur_feats)} ---')
        candidates = []
        for f in cur_feats:
            trial = [x for x in cur_feats if x != f]
            r = cross_year_evaluate(df_pool, trial, label=f'drop({f})')
            sc = score_fn(r['r'], r['power_bias_hi'])
            candidates.append((f, r, sc))

        # Sort by score desc — best to drop first
        candidates.sort(key=lambda x: -x[2])
        top = candidates[0]
        f_drop, r_top, sc_top = top
        print(f'  Best drop: {f_drop:<22s}  '
              f'r={r_top["r"]:.4f}  bias={r_top["power_bias_hi"]:+.3f}  score={sc_top:.4f}  '
              f'(was {best_score:.4f})')
        cur_feats = [x for x in cur_feats if x != f_drop]
        history.append((list(cur_feats), r_top, sc_top))

        if sc_top > best_score + 0.0001:
            best_score = sc_top
            best_feats = list(cur_feats)
            best_res = r_top
            print(f'  ↑ NEW BEST score={best_score:.4f}, feats={len(best_feats)}')
        elif sc_top < best_score - 0.05:
            print(f'  ↓ score dropped > 0.05 from best; stopping BE')
            break

    print('\n=== H2 backward elimination — winner ===')
    print(fmt_result(best_res))
    print(f'  Features ({len(best_feats)}): {best_feats}')
    print(f'  vs B_lag (r={bar:.4f}): {best_res["r"] - bar:+.4f}')

    # Decision gate
    target_r = bar + 0.02
    print(f'\nDecision gate:')
    print(f'  cross_year_r {best_res["r"]:.4f} ≥ B_lag + 0.02 = {target_r:.4f}? '
          f'{"PASS" if best_res["r"] >= target_r else "FAIL"}')
    print(f'  |power_bias_hi| {abs(best_res["power_bias_hi"]):.4f} ≤ 1.0? '
          f'{"PASS" if abs(best_res["power_bias_hi"]) <= 1.0 else "FAIL"}')

    # Persist BE history for later inspection
    out = []
    for feats, r, sc in history:
        out.append({
            'n_feats': len(feats),
            'features': '|'.join(feats),
            'r': r['r'],
            'power_bias_hi': r['power_bias_hi'],
            'team_context_bias': r['team_context_bias'],
            'rmse': r['rmse'],
            'mae': r['mae'],
            'n': r['n'],
            'score_T1': sc,
        })
    log_path = ROOT / 'data' / 'research' / 'xfp_h2_be_log.csv'
    pd.DataFrame(out).to_csv(log_path, index=False)
    print(f'\nWrote BE log → {log_path}')
    print(f'\nWinning feature list saved as Python: {best_feats}')


if __name__ == '__main__':
    main()
