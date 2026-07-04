"""
xfp_h5_pipeline.py — H5 multi-year Marcel-style weighting on H2 features.

Compendium §10.4: "Most-recent-year weight on a 5/4/3/2 sliding scale across
last 4 years, then regress to league-mean by stat-specific k."

For each (batter, year=T), each feature is replaced by:
  marcel(f) = (5*f_T-1 + 4*f_T-2 + 3*f_T-3 + 2*f_T-4) / sum(weights present)

Years where the batter didn't qualify (≥ 100 PA) drop out and weights renormalize.
A batter with only one prior year still gets a value (weight 5, normalized to 1).

Then test:
  H5 = H2 features but using marcel_<feat> instead of single-year features
  H5+H4 = same plus team_run_env_lag1 (combined H4 + H5)

Decision gate vs H2: r ≥ H2 + 0.01 AND |power_bias_hi| ≤ 1.0.
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
from xfp_h_eval import cross_year_evaluate, score_fn, fmt_result, TRAIN_MIN_PA, EVAL_MIN_PA
from xfp_h4_pipeline import add_team_run_env

H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]

# Marcel weights for the 4 most recent years before the target year.
# Compendium suggests 5/4/3/2 (Marcel-style). These are renormalized when
# fewer years of history are available.
MARCEL_WEIGHTS = [5, 4, 3, 2]
HISTORY_MIN_PA = 100  # minimum PA to count a year as "real history"


def add_marcel_features(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Replace each feature in `feats` with a Marcel-weighted version using up
    to 4 years of history. The output column name is `m_<feat>`.

    For target year T, history years are T-1, T-2, T-3, T-4 with weights
    5/4/3/2 (most recent heaviest). Missing years renormalize.
    """
    df = df.copy()
    df = df.sort_values(['batter', 'year']).reset_index(drop=True)
    # Eligibility: only count a year as history if pa ≥ HISTORY_MIN_PA
    elig_mask = df['pa'] >= HISTORY_MIN_PA

    # Build per-(batter, year) lookup so we can pull arbitrary feat values cheaply
    feat_lookup: dict[tuple[int, int], dict] = {}
    for _, r in df[elig_mask][['batter', 'year'] + feats].iterrows():
        key = (int(r['batter']), int(r['year']))
        feat_lookup[key] = {f: r[f] for f in feats}

    new_cols = {f'm_{f}': [] for f in feats}
    for _, r in df.iterrows():
        b = int(r['batter'])
        T = int(r['year'])
        for f in feats:
            num = 0.0
            denom = 0.0
            for offset, w in zip([1, 2, 3, 4], MARCEL_WEIGHTS):
                key = (b, T - offset)
                if key in feat_lookup:
                    val = feat_lookup[key].get(f)
                    if val is not None and not pd.isna(val):
                        num += w * float(val)
                        denom += w
            new_cols[f'm_{f}'].append(num / denom if denom > 0 else np.nan)

    for col, vals in new_cols.items():
        df[col] = vals
    return df


def main():
    df = pd.read_csv(SUBSTRATE)
    print(f'=== H5 — Marcel weighting — substrate {len(df)} rows ===')
    df = add_team_run_env(df)
    df = add_marcel_features(df, H2_FEATS)

    # Coverage check
    sub = df[df['pa'] >= EVAL_MIN_PA]
    m_feats = [f'm_{f}' for f in H2_FEATS]
    cov = sub[m_feats].notna().all(axis=1).sum()
    print(f'Marcel feature coverage on ≥{EVAL_MIN_PA} PA cohort: '
          f'{cov} / {len(sub)} ({cov/max(len(sub),1):.1%})\n')

    # H2 reference
    h2 = cross_year_evaluate(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']),
                              H2_FEATS, label='H2 (lag-1, production)')
    print(f'H2 reference:\n  {fmt_result(h2)}\n')

    # H5 — Marcel-weighted versions of H2
    print('--- H5: Marcel-weighted H2 features ---')
    df_h5 = df.dropna(subset=m_feats + ['fp_per_pa_actual']).copy()
    print(f'  After dropna: {len(df_h5)} rows ({(df_h5["pa"]>=300).sum()} ≥300 PA)')
    res_h5 = cross_year_evaluate(df_h5, m_feats, label='H5 (Marcel)')
    print('  ' + fmt_result(res_h5))
    s_h5 = score_fn(res_h5['r'], res_h5['power_bias_hi'])
    print(f'  vs H2: r {res_h5["r"] - h2["r"]:+.4f}, score {s_h5 - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}\n')

    # H5+H4 combo: Marcel features + team_run_env_lag1
    print('--- H5+H4: Marcel features + team_run_env_lag1 ---')
    combo = m_feats + ['team_run_env_lag1']
    df_combo = df.dropna(subset=combo + ['fp_per_pa_actual']).copy()
    print(f'  After dropna: {len(df_combo)} rows ({(df_combo["pa"]>=300).sum()} ≥300 PA)')
    res_combo = cross_year_evaluate(df_combo, combo, label='H5+H4 (Marcel + team_env)')
    print('  ' + fmt_result(res_combo))
    s_combo = score_fn(res_combo['r'], res_combo['power_bias_hi'])
    print(f'  vs H2: r {res_combo["r"] - h2["r"]:+.4f}, score {s_combo - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}\n')

    # Hybrid: Marcel for stable features (k_pct, bb_pct, hr_per_pa, iso, sprint_speed)
    # and lag-1 for less-stable features (whiff_pct, contact_pct, etc.)
    # Per compendium §10.4: "Skill metrics that age fast (speed, K-rate) deserve heavier
    # recency weights; stickier metrics tolerate longer lookbacks." We test both directions.
    HIGH_STABILITY = ['m_k_pct', 'm_bb_pct', 'm_hr_per_pa', 'm_iso',
                       'm_hard_hit_pct', 'm_sb_per_pa', 'm_sprint_speed']
    LAG1_KEEP = ['whiff_pct', 'contact_pct', 'swstr_pct', 'z_contact_pct',
                  'chase_pct', 'in_play_pct']

    print('--- H5-hybrid: Marcel for high-stability + lag-1 for plate-disc ---')
    hybrid = HIGH_STABILITY + LAG1_KEEP
    df_hyb = df.dropna(subset=hybrid + ['fp_per_pa_actual']).copy()
    print(f'  After dropna: {len(df_hyb)} rows ({(df_hyb["pa"]>=300).sum()} ≥300 PA)')
    res_hyb = cross_year_evaluate(df_hyb, hybrid, label='H5-hybrid')
    print('  ' + fmt_result(res_hyb))
    s_hyb = score_fn(res_hyb['r'], res_hyb['power_bias_hi'])
    print(f'  vs H2: r {res_hyb["r"] - h2["r"]:+.4f}, score {s_hyb - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}\n')

    # H5-hybrid + team_env
    print('--- H5-hybrid + team_run_env_lag1 ---')
    hybrid_env = hybrid + ['team_run_env_lag1']
    df_he = df.dropna(subset=hybrid_env + ['fp_per_pa_actual']).copy()
    print(f'  After dropna: {len(df_he)} rows ({(df_he["pa"]>=300).sum()} ≥300 PA)')
    res_he = cross_year_evaluate(df_he, hybrid_env, label='H5-hybrid + team_env')
    print('  ' + fmt_result(res_he))
    s_he = score_fn(res_he['r'], res_he['power_bias_hi'])
    print(f'  vs H2: r {res_he["r"] - h2["r"]:+.4f}, score {s_he - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}\n')

    # Summary
    print('=== Summary ===')
    print(f'  H2 reference         r={h2["r"]:.4f}  team_bias={h2["team_context_bias"]:+.4f}  score={score_fn(h2["r"], h2["power_bias_hi"]):.4f}')
    print(f'  H5 (Marcel only)     r={res_h5["r"]:.4f}  team_bias={res_h5["team_context_bias"]:+.4f}  score={s_h5:.4f}  Δ={s_h5 - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}')
    print(f'  H5+H4 (Marcel+team)  r={res_combo["r"]:.4f}  team_bias={res_combo["team_context_bias"]:+.4f}  score={s_combo:.4f}  Δ={s_combo - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}')
    print(f'  H5-hybrid            r={res_hyb["r"]:.4f}  team_bias={res_hyb["team_context_bias"]:+.4f}  score={s_hyb:.4f}  Δ={s_hyb - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}')
    print(f'  H5-hybrid + team_env r={res_he["r"]:.4f}  team_bias={res_he["team_context_bias"]:+.4f}  score={s_he:.4f}  Δ={s_he - score_fn(h2["r"], h2["power_bias_hi"]):+.4f}')


if __name__ == '__main__':
    main()
