"""validate_six_pack.py — cross-year r-lift on all candidate features.

Runs LOO cross-year validation (rh3 / rp3 style) on each candidate hitter
and pitcher feature. Reports baseline r, individual feature lift, and
top combinations.

Hitter candidates (joined by batter):
  - lift_h2_aug150          (already in production — locked baseline)
  - xwoba_residual_career   (item 5)
  - bb_protect_lift          (item 7)
  - career_year              (item 11)
  - age_residual_27          (item 14)

Pitcher candidates (joined by pitcher / pitcher×year):
  - tto3_minus_tto1          (item 6)
  - bullpen_fp_per_ip        (item 3 — joined by team×year)
  - age_residual_28          (item 14)
  - career_year              (item 11)

Excluded from cross-year (in-season decision-support only):
  - sp_velocity_trend (item 4): rolling-recent vs career, not stable cross-year
  - pitch_arsenal_matchup (item 2): pairwise feature, can't be univariate
  - projection_ensemble (item 15): 2026-specific, no historical projections
  - week_schedule_tilt: depends on next-7-days schedule, in-season only

Output: data/research/six_pack_validation.csv
"""
from __future__ import annotations
import sys
import itertools
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))

from scripts.xfp import xfp_rh3_pipeline as rh3mod
from scripts.xfp import xfp_rp3_pipeline as rp3mod

OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'


# =============================================================================
# HITTER VALIDATION
# =============================================================================

def build_hitter_rolling() -> pd.DataFrame:
    """Replicate rh3.main()'s rolling DataFrame build, sans projection."""
    rolling = pd.read_csv(rh3mod.ROLLING_CSV)
    rolling = rh3mod._ensure_derived_denoms(rolling)

    # Marcel prior
    multiyr = pd.read_csv(rh3mod.MULTIYR_CSV)
    years_needed = sorted(rolling['year'].unique())
    prior = rh3mod.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff'] = rolling['prior_pa_eff'].fillna(0.0)

    # H2 locked feature
    if rh3mod.H2_LOCKED_CSV.exists():
        h2 = pd.read_csv(rh3mod.H2_LOCKED_CSV)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2, on='batter', how='left')
        rolling['lift_h2_aug150'] = rolling['lift_h2_aug150'].fillna(0.0)
    else:
        rolling['lift_h2_aug150'] = 0.0

    # xwOBA residual career (production feature added 2026-05-10)
    if hasattr(rh3mod, 'XWOBA_RESID_CSV') and rh3mod.XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(rh3mod.XWOBA_RESID_CSV)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
        rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
    else:
        rolling['xwoba_residual_career'] = 0.0

    # Shrinkage
    pop_to = rh3mod.compute_population_means(rolling, rh3mod.TRAIN_YEARS, rh3mod.SHRINK_SPEC_TO)
    pop_l21 = rh3mod.compute_population_means(rolling, rh3mod.TRAIN_YEARS, rh3mod.SHRINK_SPEC_LAST21)
    rolling = rh3mod.apply_shrinkage(rolling, pop_to, rh3mod.SHRINK_SPEC_TO)
    rolling = rh3mod.apply_shrinkage(rolling, pop_l21, rh3mod.SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in rh3mod.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(rh3mod.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)
    return rolling


def attach_hitter_candidates(rolling: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Merge candidate features. Returns (rolling, candidate_col_names)."""
    candidates = []

    # 5: xwOBA residual (career-level)
    p = OUT / 'hitter_xwoba_residual.csv'
    if p.exists():
        xw = pd.read_csv(p)[['batter', 'xwoba_residual_career', 'ev90_career', 'barrel_pct_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
        rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
        rolling['ev90_career'] = rolling['ev90_career'].fillna(rolling['ev90_career'].median())
        rolling['barrel_pct_career'] = rolling['barrel_pct_career'].fillna(rolling['barrel_pct_career'].median())
        candidates += ['xwoba_residual_career', 'ev90_career', 'barrel_pct_career']

    # 7: protection effect (career-level)
    p = OUT / 'lineup_protection.csv'
    if p.exists():
        lp = pd.read_csv(p)
        if 'bb_protect_lift' in lp.columns:
            lp = lp[['batter', 'bb_protect_lift']].drop_duplicates('batter')
            rolling = rolling.merge(lp, on='batter', how='left')
            rolling['bb_protect_lift'] = rolling['bb_protect_lift'].fillna(0.0)
            candidates += ['bb_protect_lift']

    # 11 + 14: age + career year (per batter per year)
    p = OUT / 'hitter_age_career.csv'
    if p.exists():
        age = pd.read_csv(p)[['batter', 'year', 'age', 'age_residual_27', 'career_year']]
        rolling = rolling.merge(age, on=['batter', 'year'], how='left')
        rolling['age'] = rolling['age'].fillna(rolling['age'].median())
        rolling['age_residual_27'] = rolling['age_residual_27'].fillna(rolling['age_residual_27'].median())
        rolling['career_year'] = rolling['career_year'].fillna(rolling['career_year'].median())
        candidates += ['age', 'age_residual_27', 'career_year']

    # 1: Strength of Schedule (per batter per year)
    p = OUT / 'hitter_sos.csv'
    if p.exists():
        sos = pd.read_csv(p)[['batter', 'year', 'sos_opp_sp_fp_per_start']]
        rolling = rolling.merge(sos, on=['batter', 'year'], how='left')
        rolling['sos_opp_sp_fp_per_start'] = rolling['sos_opp_sp_fp_per_start'].fillna(
            rolling['sos_opp_sp_fp_per_start'].median())
        candidates += ['sos_opp_sp_fp_per_start']

    # NEW: leading-indicator residuals (year-to-date + last-21-day)
    # Year-to-date: xwoba_per_pa_to - actual_woba_per_pa_to
    if 'xwoba_per_pa_to' in rolling.columns and 'woba_v_sum_to' in rolling.columns:
        actual_woba_pa = rolling['woba_v_sum_to'] / rolling['pa_to'].replace(0, np.nan)
        rolling['xwoba_residual_to'] = rolling['xwoba_per_pa_to'] - actual_woba_pa
        rolling['xwoba_residual_to'] = rolling['xwoba_residual_to'].fillna(0.0)
        candidates += ['xwoba_residual_to']

    # Last 21 days
    if 'xwoba_per_pa_last21' in rolling.columns and 'woba_v_sum_last21' in rolling.columns:
        pa21 = rolling.get('pa_last21', pd.Series(0, index=rolling.index)).replace(0, np.nan)
        actual_woba_pa21 = rolling['woba_v_sum_last21'] / pa21
        rolling['xwoba_residual_last21'] = rolling['xwoba_per_pa_last21'] - actual_woba_pa21
        # Backfill: when no last21 data, use 0 (no residual signal)
        rolling['xwoba_residual_last21'] = rolling['xwoba_residual_last21'].fillna(0.0)
        candidates += ['xwoba_residual_last21']

    return rolling, candidates


def eval_hitter_features(rolling: pd.DataFrame, feats: list[str]) -> float:
    _, overall = rh3mod.cross_year_eval(rolling, feats)
    return overall.get('r', np.nan)


# =============================================================================
# PITCHER VALIDATION
# =============================================================================

def build_pitcher_rolling() -> pd.DataFrame:
    """Replicate rp3.main()'s rolling DataFrame build."""
    rolling = pd.read_csv(rp3mod.ROLLING_CSV) if hasattr(rp3mod, 'ROLLING_CSV') else None
    if rolling is None:
        # Fallback: search for cache
        rolling = pd.read_csv(ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_pitchers_2018_2026.csv')
    rolling = rp3mod._ensure_derived_denoms(rolling)

    # Marcel prior
    multiyr = pd.read_csv(rp3mod.MULTIYR_CSV)
    years_needed = sorted(rolling['year'].unique())
    prior = rp3mod.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff'] = rolling['prior_gs_eff'].fillna(0.0)

    # IL features (load from cache if exists)
    il_cache = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_split_features_2018_2026.csv'
    if il_cache.exists():
        il = pd.read_csv(il_cache)
        on_cols = [c for c in ['pitcher', 'year', 'split_day'] if c in il.columns]
        if on_cols:
            rolling = rolling.merge(il, on=on_cols, how='left')
    for c in ['is_on_il_at_split', 'days_since_il_return_imp', 'il_stints_to']:
        if c not in rolling.columns:
            rolling[c] = 0
        else:
            rolling[c] = rolling[c].fillna(0)

    # Shrinkage
    pop_to = rp3mod.compute_population_means(rolling, rp3mod.TRAIN_YEARS, rp3mod.SHRINK_SPEC_TO)
    pop_l21 = rp3mod.compute_population_means(rolling, rp3mod.TRAIN_YEARS, rp3mod.SHRINK_SPEC_LAST21)
    rolling = rp3mod.apply_shrinkage(rolling, pop_to, rp3mod.SHRINK_SPEC_TO)
    rolling = rp3mod.apply_shrinkage(rolling, pop_l21, rp3mod.SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in rp3mod.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(rp3mod.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    return rolling


def attach_pitcher_candidates(rolling: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    candidates = []

    # 6: TTO penalty (career-level)
    p = OUT / 'sp_lineup_pass.csv'
    if p.exists():
        tto = pd.read_csv(p)
        if 'tto3_minus_tto1' in tto.columns:
            tto = tto[['pitcher', 'tto3_minus_tto1']].drop_duplicates('pitcher')
            rolling = rolling.merge(tto, on='pitcher', how='left')
            rolling['tto3_minus_tto1'] = rolling['tto3_minus_tto1'].fillna(0.0)
            candidates += ['tto3_minus_tto1']

    # 11+14: age + career year
    p = OUT / 'sp_age_career.csv'
    if p.exists():
        age = pd.read_csv(p)[['pitcher', 'year', 'age', 'age_residual_28', 'career_year']]
        rolling = rolling.merge(age, on=['pitcher', 'year'], how='left')
        rolling['age'] = rolling['age'].fillna(rolling['age'].median())
        rolling['age_residual_28'] = rolling['age_residual_28'].fillna(rolling['age_residual_28'].median())
        rolling['career_year'] = rolling['career_year'].fillna(rolling['career_year'].median())
        candidates += ['age', 'age_residual_28', 'career_year']

    # 3: bullpen quality (per-team-per-year)
    bp = OUT / 'bullpen_quality.csv'
    if bp.exists():
        bullpen = pd.read_csv(bp)[['team', 'year', 'bullpen_fp_per_ip']]
        # rolling has team_abbr, not team — let's check
        team_col = 'team_abbr' if 'team_abbr' in rolling.columns else 'team'
        if team_col in rolling.columns:
            rolling = rolling.merge(
                bullpen.rename(columns={'team': team_col}),
                on=[team_col, 'year'], how='left')
            rolling['bullpen_fp_per_ip'] = rolling['bullpen_fp_per_ip'].fillna(rolling['bullpen_fp_per_ip'].median())
            candidates += ['bullpen_fp_per_ip']

    # 1: SoS (per pitcher per year)
    p = OUT / 'pitcher_sos.csv'
    if p.exists():
        sos = pd.read_csv(p)[['pitcher', 'year', 'sos_opp_bat_fp_per_pa']]
        rolling = rolling.merge(sos, on=['pitcher', 'year'], how='left')
        rolling['sos_opp_bat_fp_per_pa'] = rolling['sos_opp_bat_fp_per_pa'].fillna(
            rolling['sos_opp_bat_fp_per_pa'].median())
        candidates += ['sos_opp_bat_fp_per_pa']

    return rolling, candidates


def eval_pitcher_features(rolling: pd.DataFrame, feats: list[str]) -> float:
    _, overall = rp3mod.cross_year_eval(rolling, feats)
    return overall.get('r', np.nan)


# =============================================================================
# MAIN
# =============================================================================

def run_subset_search(rolling, base_feats, candidates, eval_fn, label):
    """For each subset of candidates (of size 1..len), eval r and return DataFrame."""
    base_r = eval_fn(rolling, base_feats)
    print(f'  {label} BASELINE r = {base_r:.5f}  (features: {len(base_feats)})')
    rows = []
    rows.append({'subset': 'BASELINE', 'n_candidates_added': 0, 'r': base_r, 'delta_r': 0.0})

    # Individual lift
    indiv = {}
    for c in candidates:
        r = eval_fn(rolling, base_feats + [c])
        delta = r - base_r
        indiv[c] = delta
        rows.append({'subset': c, 'n_candidates_added': 1, 'r': r, 'delta_r': delta})
        flag = 'PASS' if delta >= 0.005 else ('marginal' if delta > 0 else 'NEG')
        print(f'    +{c:<26s} r={r:.5f} DeltaR={delta:+.5f}  {flag}')

    # Combinations (all 2^N if N small, else only positive-individual subset)
    if len(candidates) <= 5:
        all_combos = []
        for k in range(2, len(candidates) + 1):
            all_combos.extend(itertools.combinations(candidates, k))
    else:
        positive = [c for c, d in indiv.items() if d > 0]
        print(f'    {len(positive)}/{len(candidates)} positive — combo search restricted to those')
        all_combos = []
        for k in range(2, len(positive) + 1):
            all_combos.extend(itertools.combinations(positive, k))

    print(f'  Evaluating {len(all_combos)} combinations...')
    for combo in all_combos:
        feats = base_feats + list(combo)
        r = eval_fn(rolling, feats)
        delta = r - base_r
        rows.append({'subset': '+'.join(combo),
                     'n_candidates_added': len(combo), 'r': r, 'delta_r': delta})

    return pd.DataFrame(rows), base_r, indiv


def main():
    RES.mkdir(parents=True, exist_ok=True)
    print('=' * 80)
    print('CROSS-YEAR R-LIFT VALIDATION')
    print('=' * 80)

    # ── Hitters ────────────────────────────────────────────────────────────────
    print('\n[1/2] Building hitter rolling substrate...')
    hit_rolling = build_hitter_rolling()
    print(f'  rolling shape: {hit_rolling.shape}')
    hit_rolling, hit_cands = attach_hitter_candidates(hit_rolling)
    print(f'  candidates: {hit_cands}')

    print('\n[Hitter] cross-year r-lift on top of current production RH3 (incl. lift_h2_aug150):')
    hit_table, hit_base_r, hit_indiv = run_subset_search(
        hit_rolling, rh3mod.RH3_FEATS, hit_cands, eval_hitter_features, 'HITTER')

    hit_table['side'] = 'hitter'
    hit_table.to_csv(RES / 'six_pack_validation_hitters.csv', index=False)

    # ── Pitchers ───────────────────────────────────────────────────────────────
    print('\n[2/2] Building pitcher rolling substrate...')
    try:
        pit_rolling = build_pitcher_rolling()
        print(f'  rolling shape: {pit_rolling.shape}')
        pit_rolling, pit_cands = attach_pitcher_candidates(pit_rolling)
        print(f'  candidates: {pit_cands}')

        print('\n[Pitcher] cross-year r-lift on top of current production RP3:')
        pit_table, pit_base_r, pit_indiv = run_subset_search(
            pit_rolling, rp3mod.RP3_FEATS, pit_cands, eval_pitcher_features, 'PITCHER')

        pit_table['side'] = 'pitcher'
        pit_table.to_csv(RES / 'six_pack_validation_pitchers.csv', index=False)

        combined = pd.concat([hit_table, pit_table], ignore_index=True)
    except Exception as exc:
        print(f'  Pitcher validation failed: {exc}')
        import traceback; traceback.print_exc()
        combined = hit_table

    combined.to_csv(RES / 'six_pack_validation.csv', index=False)

    print('\n' + '=' * 80)
    print('SUMMARY — TOP 5 LIFTS BY SIDE')
    print('=' * 80)
    for side in ['hitter', 'pitcher']:
        sub = combined[combined['side'] == side].sort_values('delta_r', ascending=False)
        print(f'\n{side.upper()} (baseline r={sub.iloc[0]["r"]:.5f}):')
        print(sub.head(5)[['subset', 'n_candidates_added', 'r', 'delta_r']].to_string(index=False))

    print('\n=== Final ship recommendation (Δr ≥ +0.005) ===')
    keepers = combined[combined['delta_r'] >= 0.005]
    print(keepers[['side', 'subset', 'n_candidates_added', 'r', 'delta_r']].to_string(index=False))


if __name__ == '__main__':
    main()
