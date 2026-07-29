"""
xfp_h3_pipeline.py — H3 backward elimination on a compendium-aligned pool.

Adds to H2's pool: ev90, avg_ev (kept for direct comparison), barrel_pct,
xwoba_per_pa, xwoba_on_contact, c_plus_swstr, o_swing_pct, zone_pct.
Drops (per H1.5 screen + compendium §10.2): pull_*, cent_*, oppo_*,
sweet_spot_pct, hbp_pct, z_swing_pct, ld_pct (never had).

Decision gate: H3 ships if cross_year_r ≥ H2 + 0.01 AND |power_bias_hi| ≤ 1.0.
"""
from __future__ import annotations
import sys
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'

sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_h_eval import (
    cross_year_evaluate, lag_baseline_evaluate, score_fn, fmt_result,
    TRAIN_MIN_PA, EVAL_MIN_PA, TRANSITIONS,
)

# H2 final feature set (the bar to beat)
H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]

# H3 candidate pool — H2 + H1.5 KEEP that survived screen + EV90/avg_ev
# (chase_pct and o_swing_pct are duplicates in our substrate; keep one)
H3_POOL = [
    # Plate discipline
    'swing_pct', 'chase_pct', 'contact_pct', 'whiff_pct', 'in_play_pct',
    'zone_pct', 'z_contact_pct', 'swstr_pct', 'c_plus_swstr',
    # Contact quality
    'xwoba_on_contact', 'xwoba_per_pa',
    'hard_hit_pct', 'barrel_pct',
    'avg_ev', 'ev90',  # both kept; let BE pick
    # Outcome rates (lag-equivalent)
    'k_pct', 'bb_pct', 'hr_per_pa', 'iso', 'sb_per_pa',
    # Speed
    'sprint_speed',
]


def main():
    df = pd.read_csv(SUBSTRATE)
    print(f'=== H3 backward elimination — substrate {len(df)} rows ===')
    print(f'Pool ({len(H3_POOL)} features): {H3_POOL}\n')

    base = lag_baseline_evaluate(df)
    print(f'Reference baselines:')
    print(f'  {fmt_result(base)}')
    h2_ref = cross_year_evaluate(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']),
                                  H2_FEATS, label='H2 (production)')
    print(f'  {fmt_result(h2_ref)}\n')

    df_pool = df.dropna(subset=H3_POOL + ['fp_per_pa_actual']).copy()
    print(f'After dropna on full H3 pool: {len(df_pool)} rows '
          f'({(df_pool["pa"]>=TRAIN_MIN_PA).sum()} ≥{TRAIN_MIN_PA} PA, '
          f'{(df_pool["pa"]>=EVAL_MIN_PA).sum()} ≥{EVAL_MIN_PA} PA)\n')

    # Step 0: full pool
    print('--- Step 0: full H3 pool ---')
    res = cross_year_evaluate(df_pool, H3_POOL, label=f'pool[{len(H3_POOL)}]')
    s = score_fn(res['r'], res['power_bias_hi'])
    print('  ' + fmt_result(res))
    print(f'  vs H2: r {res["r"]-h2_ref["r"]:+.4f}, score {s - score_fn(h2_ref["r"], h2_ref["power_bias_hi"]):+.4f}\n')

    cur = list(H3_POOL)
    history = [(list(cur), res, s)]
    best_score, best_feats, best_res = s, list(cur), res

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
        print(f'  Best drop: {f_drop:<22s}  r={r_top["r"]:.4f}  pwr_bias={r_top["power_bias_hi"]:+.3f}  score={sc_top:.4f}  (was {best_score:.4f})')
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

    print('\n=== H3 backward elimination — winner ===')
    print('  ' + fmt_result(best_res))
    print(f'  Features ({len(best_feats)}): {best_feats}')
    print()
    print('=== Decision gate ===')
    target_r = h2_ref['r'] + 0.01
    print(f'  cross_year_r {best_res["r"]:.4f} ≥ H2 + 0.01 = {target_r:.4f}? {"PASS" if best_res["r"] >= target_r else "FAIL"}')
    print(f'  |power_bias_hi| {abs(best_res["power_bias_hi"]):.4f} ≤ 1.0? {"PASS" if abs(best_res["power_bias_hi"]) <= 1.0 else "FAIL"}')
    print(f'  Score (T=1) {best_score:.4f} > H2 score {score_fn(h2_ref["r"], h2_ref["power_bias_hi"]):.4f}? '
          f'{"PASS" if best_score > score_fn(h2_ref["r"], h2_ref["power_bias_hi"]) else "FAIL"}')

    out = []
    for feats, r, sc in history:
        out.append({'n_feats': len(feats), 'features': '|'.join(feats),
                    'r': r['r'], 'power_bias_hi': r['power_bias_hi'],
                    'team_context_bias': r['team_context_bias'],
                    'rmse': r['rmse'], 'mae': r['mae'],
                    'n': r['n'], 'score_T1': sc})
    pd.DataFrame(out).to_csv(ROOT / 'data' / 'research' / 'xfp_h3_be_log.csv', index=False)
    print('\nWrote BE log → data/research/xfp_h3_be_log.csv')
    print(f'\nH3_FEATS = {best_feats}')


if __name__ == '__main__':
    main()
