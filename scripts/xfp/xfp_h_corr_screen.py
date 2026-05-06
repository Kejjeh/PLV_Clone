"""
xfp_h_corr_screen.py — cross-year correlation pre-screen for hitter features.

For each candidate feature, computes cor(feat_yearT, fp_per_pa_actual_yearT+1)
per transition, then aggregates across transitions. Features with weak or
inconsistent cross-year signal get flagged for removal from the H2 pool.

Output: data/research/xfp_h_correlation_screen.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
OUT = ROOT / 'data' / 'research' / 'xfp_h_correlation_screen.csv'

TRANSITIONS = [(2018, 2019), (2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025)]
EVAL_MIN_PA = 300

# Candidate H3 pool (compendium-aligned; expanded vs H2)
# Drops: hbp_pct (H2 screen flagged DROP), z_swing_pct (DROP), and explicitly LD%
# (compendium §10.2: Y/Y r ~0.22, mostly noise — never include).
CANDIDATES = [
    # Plate discipline (Statcast pitch-level rates)
    'swing_pct', 'chase_pct', 'contact_pct', 'whiff_pct', 'in_play_pct',
    'zone_pct', 'o_swing_pct', 'z_contact_pct',
    'swstr_pct', 'c_plus_swstr',
    # Contact quality (compendium Tier S/A)
    'xwoba_on_contact', 'xwoba_per_pa',
    'hard_hit_pct', 'barrel_pct',
    'ev90',           # NEW — compendium §3, §10.1: outperforms mean EV
    'sweet_spot_pct', # NEW — compendium Tier A
    'avg_ev',         # kept for comparison; expected to lose to ev90
    # Spray angle (compendium Tier B — drives HR projection via FB-pull)
    'pull_pct', 'cent_pct', 'oppo_pct', 'pull_fb_pct',  # NEW
    # Outcome rate stats (semi-circular but year-stable)
    'k_pct',     # → labelled k_pct_lag1 in the H2 search
    'bb_pct',    # → labelled bb_pct_lag1
    'hr_per_pa', # → labelled hr_per_pa_lag1
    'iso',       # → labelled iso_lag1
    'sb_per_pa', # → labelled sb_per_pa_lag1
    # Speed (Statcast — process not outcome; compendium Y/Y r >0.85)
    'sprint_speed',
]


def screen_one(df: pd.DataFrame, feat: str) -> dict:
    """Per-transition correlation between year-T feature and year-(T+1) fp_per_pa."""
    cors: list[float] = []
    n_each: list[int] = []
    for yr_train, yr_test in TRANSITIONS:
        train_year = df[(df['year'] == yr_train) & (df['pa'] >= EVAL_MIN_PA)]
        test_year  = df[(df['year'] == yr_test)  & (df['pa'] >= EVAL_MIN_PA)]
        shared = set(train_year['batter']) & set(test_year['batter'])
        if not shared:
            continue
        merged = pd.DataFrame({
            'batter': list(shared),
        }).merge(train_year[['batter', feat]], on='batter') \
          .merge(test_year[['batter', 'fp_per_pa_actual']], on='batter')
        merged = merged.dropna(subset=[feat, 'fp_per_pa_actual'])
        if len(merged) < 30:
            continue
        c = float(np.corrcoef(merged[feat], merged['fp_per_pa_actual'])[0, 1])
        if pd.isna(c):
            continue
        cors.append(c)
        n_each.append(len(merged))

    if not cors:
        return {
            'feature': feat, 'n_transitions': 0, 'mean_cor': np.nan,
            'min_cor': np.nan, 'max_cor': np.nan, 'mean_abs_cor': np.nan,
            'sign_flip': False, 'mean_n': 0, 'recommendation': 'no_data',
        }

    mean_c = float(np.mean(cors))
    min_c  = float(min(cors))
    max_c  = float(max(cors))
    mean_abs = float(np.mean([abs(c) for c in cors]))
    sign_flip = bool(min_c < 0 < max_c)

    # Recommendation per the plan:
    # KEEP if |mean_cor| ≥ 0.10
    # DROP if |mean_cor| < 0.05 and sign flips across transitions
    # WATCH otherwise
    if abs(mean_c) >= 0.10:
        rec = 'KEEP'
    elif abs(mean_c) < 0.05 and sign_flip:
        rec = 'DROP'
    else:
        rec = 'WATCH'

    return {
        'feature': feat,
        'n_transitions': len(cors),
        'mean_cor': round(mean_c, 4),
        'min_cor': round(min_c, 4),
        'max_cor': round(max_c, 4),
        'mean_abs_cor': round(mean_abs, 4),
        'sign_flip': sign_flip,
        'mean_n': int(np.mean(n_each)),
        'recommendation': rec,
    }


def main():
    df = pd.read_csv(SUBSTRATE)
    print(f'=== correlation screen — {SUBSTRATE.name}: {len(df)} rows ===')
    print(f'Transitions: {TRANSITIONS}')
    print(f'Eval threshold: ≥ {EVAL_MIN_PA} PA per side\n')

    rows = [screen_one(df, f) for f in CANDIDATES]
    out = pd.DataFrame(rows)
    out = out.sort_values('mean_abs_cor', ascending=False).reset_index(drop=True)

    print(out.to_string(index=False))
    out.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}')

    keep = out[out['recommendation'] == 'KEEP']['feature'].tolist()
    drop = out[out['recommendation'] == 'DROP']['feature'].tolist()
    watch = out[out['recommendation'] == 'WATCH']['feature'].tolist()
    print(f'\nKEEP ({len(keep)}): {keep}')
    print(f'WATCH ({len(watch)}): {watch}')
    print(f'DROP ({len(drop)}): {drop}')


if __name__ == '__main__':
    main()
