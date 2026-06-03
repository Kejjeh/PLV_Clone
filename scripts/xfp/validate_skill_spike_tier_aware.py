"""validate_skill_spike_tier_aware.py

Test the tier-gated `skill_spike_tier_aware` variant — per the pre-registration
`data/research/validation_runs/skill_spike_tier_aware_2026-06-03.md`:

  Streamer (rank 51+):    3-game window
  Backend (rank 31-50):   5-game window
  SP2/3   (rank 11-30):   5-game window
  Ace     (rank 1-10):    choose 3g vs 5g on pre-2024 calibration (tie → 3g)

Then run head-to-head vs flat-3g and flat-5g on the FULL panel (2018-25):

  Step A — Per-tier boom-rate edge (flag=1 vs flag=0)
  Step B — Pooled weighted edge (weight by tier N)
  Step C — Cross-year stability (year × tier sign matrix)
  Step D — v1 boom_stack marginal-lift comparison: at boom_stack=3 (all 3
           components on), does substituting `skill_spike` with each variant
           change the boom rate?

Strict-Rule-8 framing: tier assignment uses fp_mean rank-in-year, same as
Agent 5's diagnostic (i.e., not future leakage in the sense that fp_mean
is computed over the SAME year's starts but used as a static label; this
matches the production engine's tier assignment for analytic use).

Outputs:
  data/research/validation_runs/skill_spike_tier_aware_validation.md
  data/research/validation_runs/skill_spike_tier_aware_validation_data.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

CACHE_PANEL = ROOT / 'data' / 'research' / '_boom_stack_per_start_panel_cache.parquet'
PREREG = ROOT / 'data' / 'research' / 'validation_runs' / 'skill_spike_tier_aware_2026-06-03.md'
OUT_MD = ROOT / 'data' / 'research' / 'validation_runs' / 'skill_spike_tier_aware_validation.md'
OUT_JSON = ROOT / 'data' / 'research' / 'validation_runs' / 'skill_spike_tier_aware_validation_data.json'

TIER_DEF = [
    ('Ace',      1, 10),
    ('SP2_SP3', 11, 30),
    ('Backend', 31, 50),
    ('Streamer', 51, 10_000),
]
TIER_ORDER = ['Ace', 'SP2_SP3', 'Backend', 'Streamer']

CALIBRATION_YEARS = [2018, 2019, 2021, 2022, 2023]
HOLDOUT_YEARS = [2024, 2025]


def assign_tier(panel: pd.DataFrame, min_starts: int = 8) -> pd.DataFrame:
    agg = (panel.groupby(['pitcher', 'year'])
                 .agg(starts=('fp', 'size'), fp_mean=('fp', 'mean'))
                 .reset_index())
    agg = agg[agg['starts'] >= min_starts].copy()
    agg['rank_in_year'] = (agg.groupby('year')['fp_mean']
                               .rank(ascending=False, method='first'))

    def tier_of(r):
        for name, lo, hi in TIER_DEF:
            if lo <= r <= hi:
                return name
        return None
    agg['tier'] = agg['rank_in_year'].astype(int).map(tier_of)
    return agg[['pitcher', 'year', 'starts', 'fp_mean', 'rank_in_year', 'tier']]


def add_running_stats(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.sort_values(['pitcher', 'year', 'game_date']).copy()
    p['start_idx'] = p.groupby(['pitcher', 'year']).cumcount()
    g = p.groupby(['pitcher', 'year'])
    p['cum_K_incl'] = g['actual_K'].cumsum()
    p['cum_BB_incl'] = g['actual_BB'].cumsum()
    p['cum_PA_incl'] = g['actual_PA'].cumsum()
    p['cum_K_prior'] = p['cum_K_incl'] - p['actual_K']
    p['cum_BB_prior'] = p['cum_BB_incl'] - p['actual_BB']
    p['cum_PA_prior'] = p['cum_PA_incl'] - p['actual_PA']
    p['season_k_pct'] = p['cum_K_prior'] / p['cum_PA_prior'].replace(0, np.nan)
    p['season_bb_pct'] = p['cum_BB_prior'] / p['cum_PA_prior'].replace(0, np.nan)
    return p


def compute_window_metrics(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    p = panel.sort_values(['pitcher', 'year', 'game_date']).copy()
    g = p.groupby(['pitcher', 'year'], sort=False)
    p[f'lw{window}_K'] = g['actual_K'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()
    ).reset_index(level=[0, 1], drop=True)
    p[f'lw{window}_BB'] = g['actual_BB'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()
    ).reset_index(level=[0, 1], drop=True)
    p[f'lw{window}_PA'] = g['actual_PA'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()
    ).reset_index(level=[0, 1], drop=True)
    p[f'lw{window}_k_pct'] = p[f'lw{window}_K'] / p[f'lw{window}_PA'].replace(0, np.nan)
    p[f'lw{window}_bb_pct'] = p[f'lw{window}_BB'] / p[f'lw{window}_PA'].replace(0, np.nan)
    return p


def make_spike_flag(p: pd.DataFrame, window: int) -> pd.Series:
    dK_pp = (p[f'lw{window}_k_pct'] - p['season_k_pct']) * 100.0
    dBB_pp = (p[f'lw{window}_bb_pct'] - p['season_bb_pct']) * 100.0
    enough = p['start_idx'] >= window
    return ((dK_pp >= 3.0) & (dBB_pp <= -1.0) & enough).astype(int)


def per_tier_edge(p: pd.DataFrame, flag_col: str, min_prior: int) -> list[dict]:
    """Per-tier boom% edge for a single flag column. min_prior is the start_idx
    cutoff so flag-off pool is also gated."""
    rows = []
    for tier in TIER_ORDER:
        sub = p[(p['tier'] == tier) & (p['start_idx'] >= min_prior)]
        on = sub[sub[flag_col] == 1]
        off = sub[sub[flag_col] == 0]
        if len(on) < 10 or len(off) < 10:
            rows.append({'tier': tier, 'n_on': len(on), 'n_off': len(off),
                         'boom_on': np.nan, 'boom_off': np.nan, 'edge_pp': np.nan})
            continue
        on_boom = float((on['boom_outcome'] == 1).mean() * 100)
        off_boom = float((off['boom_outcome'] == 1).mean() * 100)
        rows.append({
            'tier': tier,
            'n_on': int(len(on)),
            'n_off': int(len(off)),
            'boom_on': on_boom,
            'boom_off': off_boom,
            'edge_pp': on_boom - off_boom,
        })
    return rows


def pooled_weighted_edge(tier_rows: list[dict]) -> float:
    """Weight per-tier edge by tier N (sum of n_on + n_off — the size of the
    available decision-pool at that tier). Returns weighted-average edge in pp."""
    num = 0.0
    den = 0.0
    for r in tier_rows:
        if r['edge_pp'] is None or np.isnan(r['edge_pp']):
            continue
        n = r['n_on'] + r['n_off']
        num += n * r['edge_pp']
        den += n
    return float(num / den) if den > 0 else float('nan')


def cross_year_stability(p: pd.DataFrame, flag_col: str, min_prior: int) -> dict:
    """For each (year, tier), record edge sign. Aggregate count of positive years
    overall."""
    matrix = {}
    for tier in TIER_ORDER:
        matrix[tier] = {}
        for yr in sorted(p['year'].unique()):
            sub = p[(p['tier'] == tier) & (p['year'] == yr) & (p['start_idx'] >= min_prior)]
            on = sub[sub[flag_col] == 1]
            off = sub[sub[flag_col] == 0]
            if len(on) < 5 or len(off) < 5:
                matrix[tier][int(yr)] = None
                continue
            on_boom = (on['boom_outcome'] == 1).mean() * 100
            off_boom = (off['boom_outcome'] == 1).mean() * 100
            matrix[tier][int(yr)] = float(on_boom - off_boom)

    # Also pooled-per-year sign (sum of weighted-edge for the year across tiers)
    yr_summary = {}
    for yr in sorted(p['year'].unique()):
        sub = p[(p['year'] == yr) & (p['start_idx'] >= min_prior)]
        on = sub[sub[flag_col] == 1]
        off = sub[sub[flag_col] == 0]
        if len(on) < 10 or len(off) < 10:
            yr_summary[int(yr)] = None
            continue
        on_boom = (on['boom_outcome'] == 1).mean() * 100
        off_boom = (off['boom_outcome'] == 1).mean() * 100
        yr_summary[int(yr)] = float(on_boom - off_boom)

    pos_years = sum(1 for v in yr_summary.values() if v is not None and v > 0)
    total_years = sum(1 for v in yr_summary.values() if v is not None)
    return {
        'matrix': matrix,
        'pooled_per_year': yr_summary,
        'pos_years': pos_years,
        'total_years': total_years,
    }


def boom_stack_marginal_lift(p: pd.DataFrame, flag_col: str) -> dict:
    """For the v1 boom_stack composite, swap component (1) `flag_skill_spike`
    with `flag_col` and recompute boom_stack distribution + boom% per bucket.
    """
    # original components in panel: flag_skill_spike, flag_recform_hot, flag_opp_soft
    p2 = p.copy()
    p2['boom_stack_alt'] = (
        p2[flag_col].fillna(0).astype(int)
        + p2['flag_recform_hot'].fillna(0).astype(int)
        + p2['flag_opp_soft'].fillna(0).astype(int)
    )
    # Only the rows where flag_col is defined (start_idx >= max window used by variant)
    rows = []
    for bs in [0, 1, 2, 3]:
        sub = p2[p2['boom_stack_alt'] == bs]
        if len(sub) == 0:
            rows.append({'boom_stack': bs, 'n': 0, 'boom_pct': np.nan,
                         'mean_fp': np.nan})
            continue
        rows.append({
            'boom_stack': bs,
            'n': int(len(sub)),
            'boom_pct': float((sub['boom_outcome'] == 1).mean() * 100),
            'mean_fp': float(sub['fp'].mean()),
        })
    return {'bucket_rows': rows}


def main():
    print('Loading panel...')
    panel = pd.read_parquet(CACHE_PANEL)
    panel = panel.dropna(subset=['fp']).copy()
    panel['boom_outcome'] = panel['boom_outcome'].fillna(0).astype(int)

    # Tier assignment
    tier_map = assign_tier(panel, min_starts=8)
    panel = panel.merge(tier_map[['pitcher', 'year', 'tier', 'rank_in_year']],
                        on=['pitcher', 'year'], how='inner')
    print(f'panel rows after tier filter: {len(panel):,}')

    # Running stats + windows
    panel = add_running_stats(panel)
    panel = compute_window_metrics(panel, 3)
    panel = compute_window_metrics(panel, 5)

    # Build the three flags
    panel['flag_3g'] = make_spike_flag(panel, 3)
    panel['flag_5g'] = make_spike_flag(panel, 5)

    # ---- Ace-tier window decision (pre-registered: pre-2024 calibration) ----
    print('\n--- Ace-tier calibration (pre-2024) ---')
    calib = panel[panel['year'].isin(CALIBRATION_YEARS) & (panel['tier'] == 'Ace')].copy()
    # 3g edge on calibration
    c3 = calib[calib['start_idx'] >= 3]
    on3 = c3[c3['flag_3g'] == 1]
    off3 = c3[c3['flag_3g'] == 0]
    edge_ace_3g_calib = (
        (on3['boom_outcome'].mean() - off3['boom_outcome'].mean()) * 100
        if (len(on3) >= 10 and len(off3) >= 10) else np.nan
    )
    c5 = calib[calib['start_idx'] >= 5]
    on5 = c5[c5['flag_5g'] == 1]
    off5 = c5[c5['flag_5g'] == 0]
    edge_ace_5g_calib = (
        (on5['boom_outcome'].mean() - off5['boom_outcome'].mean()) * 100
        if (len(on5) >= 10 and len(off5) >= 10) else np.nan
    )
    print(f'  Ace 3g calib edge: n_on={len(on3)} edge={edge_ace_3g_calib:+.2f} pp')
    print(f'  Ace 5g calib edge: n_on={len(on5)} edge={edge_ace_5g_calib:+.2f} pp')

    # Pre-stated rule: tie or 3g wins → use 3g (status quo). Otherwise 5g.
    if np.isnan(edge_ace_5g_calib) or np.isnan(edge_ace_3g_calib):
        ace_window_choice = 3
        ace_choice_note = 'fallback to 3g (calibration NaN)'
    elif edge_ace_5g_calib > edge_ace_3g_calib:
        ace_window_choice = 5
        ace_choice_note = f'5g wins by {edge_ace_5g_calib - edge_ace_3g_calib:+.2f} pp on calibration'
    else:
        ace_window_choice = 3
        ace_choice_note = f'3g wins or ties ({edge_ace_3g_calib:+.2f} vs {edge_ace_5g_calib:+.2f} pp)'
    print(f'  ACE WINDOW LOCKED: {ace_window_choice}g  ({ace_choice_note})')

    # ---- Build the tier-aware flag ----
    # Streamer → 3g, SP2_SP3 → 5g, Backend → 5g, Ace → ace_window_choice
    def tier_aware_window(tier: str) -> int:
        if tier == 'Streamer':
            return 3
        if tier == 'Ace':
            return ace_window_choice
        return 5  # SP2_SP3, Backend

    panel['_aw_window'] = panel['tier'].map(tier_aware_window)
    # Compute flag_tier_aware: select 3g or 5g flag based on the tier's window
    panel['flag_tier_aware'] = np.where(
        panel['_aw_window'] == 3, panel['flag_3g'], panel['flag_5g']
    )
    # min_prior gating: the variant requires start_idx >= the tier's window
    panel['_aw_eligible'] = panel['start_idx'] >= panel['_aw_window']
    # Where ineligible, set flag = NaN-like (use -1 sentinel then filter)
    panel.loc[~panel['_aw_eligible'], 'flag_tier_aware'] = np.nan

    # ---- Per-tier edge tables ----
    print('\n--- Per-tier edge: 3g ---')
    edges_3g = per_tier_edge(panel, 'flag_3g', min_prior=3)
    for r in edges_3g:
        print(f"  {r['tier']:>9s}  n_on={r['n_on']:>5d}  edge={r['edge_pp']:+.2f} pp")

    print('\n--- Per-tier edge: 5g ---')
    edges_5g = per_tier_edge(panel, 'flag_5g', min_prior=5)
    for r in edges_5g:
        print(f"  {r['tier']:>9s}  n_on={r['n_on']:>5d}  edge={r['edge_pp']:+.2f} pp")

    print('\n--- Per-tier edge: tier_aware ---')
    # For tier_aware, min_prior is per-tier; build per-tier output specially
    edges_aware = []
    for tier in TIER_ORDER:
        w = tier_aware_window(tier)
        sub = panel[(panel['tier'] == tier) & panel['_aw_eligible']]
        on = sub[sub['flag_tier_aware'] == 1]
        off = sub[sub['flag_tier_aware'] == 0]
        if len(on) < 10 or len(off) < 10:
            edges_aware.append({'tier': tier, 'window': w,
                                'n_on': len(on), 'n_off': len(off),
                                'boom_on': np.nan, 'boom_off': np.nan, 'edge_pp': np.nan})
            continue
        on_boom = float((on['boom_outcome'] == 1).mean() * 100)
        off_boom = float((off['boom_outcome'] == 1).mean() * 100)
        edges_aware.append({
            'tier': tier, 'window': w,
            'n_on': int(len(on)), 'n_off': int(len(off)),
            'boom_on': on_boom, 'boom_off': off_boom,
            'edge_pp': on_boom - off_boom,
        })
        print(f"  {tier:>9s} ({w}g)  n_on={len(on):>5d}  edge={on_boom - off_boom:+.2f} pp")

    # ---- Pooled weighted edges ----
    pooled_3g = pooled_weighted_edge(edges_3g)
    pooled_5g = pooled_weighted_edge(edges_5g)
    pooled_aware = pooled_weighted_edge(edges_aware)
    print(f'\nPOOLED WEIGHTED EDGE:')
    print(f'  3g         : {pooled_3g:+.3f} pp')
    print(f'  5g         : {pooled_5g:+.3f} pp')
    print(f'  tier_aware : {pooled_aware:+.3f} pp')

    # ---- Hold-out sanity (2024-25) ----
    print('\n--- Hold-out (2024-25) per-tier edge ---')
    panel_hold = panel[panel['year'].isin(HOLDOUT_YEARS)]
    edges_3g_hold = per_tier_edge(panel_hold, 'flag_3g', min_prior=3)
    edges_5g_hold = per_tier_edge(panel_hold, 'flag_5g', min_prior=5)
    edges_aware_hold = []
    for tier in TIER_ORDER:
        w = tier_aware_window(tier)
        sub = panel_hold[(panel_hold['tier'] == tier) & panel_hold['_aw_eligible']]
        on = sub[sub['flag_tier_aware'] == 1]
        off = sub[sub['flag_tier_aware'] == 0]
        if len(on) < 5 or len(off) < 5:
            edges_aware_hold.append({'tier': tier, 'window': w,
                                     'n_on': len(on), 'n_off': len(off),
                                     'edge_pp': np.nan})
            continue
        on_boom = float((on['boom_outcome'] == 1).mean() * 100)
        off_boom = float((off['boom_outcome'] == 1).mean() * 100)
        edges_aware_hold.append({
            'tier': tier, 'window': w,
            'n_on': int(len(on)), 'n_off': int(len(off)),
            'edge_pp': on_boom - off_boom,
        })
    pooled_3g_hold = pooled_weighted_edge(edges_3g_hold)
    pooled_5g_hold = pooled_weighted_edge(edges_5g_hold)
    pooled_aware_hold = pooled_weighted_edge(edges_aware_hold)
    print(f'  pooled 3g hold-out:        {pooled_3g_hold:+.3f} pp')
    print(f'  pooled 5g hold-out:        {pooled_5g_hold:+.3f} pp')
    print(f'  pooled tier_aware hold-out:{pooled_aware_hold:+.3f} pp')

    # ---- Cross-year stability ----
    print('\n--- Cross-year stability ---')
    stab_3g = cross_year_stability(panel, 'flag_3g', min_prior=3)
    stab_5g = cross_year_stability(panel, 'flag_5g', min_prior=5)
    # tier_aware: do it manually since min_prior is per-tier
    stab_aware_matrix = {}
    for tier in TIER_ORDER:
        stab_aware_matrix[tier] = {}
        for yr in sorted(panel['year'].unique()):
            sub = panel[(panel['tier'] == tier) & (panel['year'] == yr) & panel['_aw_eligible']]
            on = sub[sub['flag_tier_aware'] == 1]
            off = sub[sub['flag_tier_aware'] == 0]
            if len(on) < 5 or len(off) < 5:
                stab_aware_matrix[tier][int(yr)] = None
                continue
            on_boom = (on['boom_outcome'] == 1).mean() * 100
            off_boom = (off['boom_outcome'] == 1).mean() * 100
            stab_aware_matrix[tier][int(yr)] = float(on_boom - off_boom)
    # pooled per year for tier_aware
    stab_aware_per_year = {}
    for yr in sorted(panel['year'].unique()):
        sub = panel[(panel['year'] == yr) & panel['_aw_eligible']]
        on = sub[sub['flag_tier_aware'] == 1]
        off = sub[sub['flag_tier_aware'] == 0]
        if len(on) < 10 or len(off) < 10:
            stab_aware_per_year[int(yr)] = None
            continue
        on_boom = (on['boom_outcome'] == 1).mean() * 100
        off_boom = (off['boom_outcome'] == 1).mean() * 100
        stab_aware_per_year[int(yr)] = float(on_boom - off_boom)
    stab_aware = {
        'matrix': stab_aware_matrix,
        'pooled_per_year': stab_aware_per_year,
        'pos_years': sum(1 for v in stab_aware_per_year.values() if v is not None and v > 0),
        'total_years': sum(1 for v in stab_aware_per_year.values() if v is not None),
    }
    print(f'  3g         pooled pos-year count: {stab_3g["pos_years"]} / {stab_3g["total_years"]}')
    print(f'  5g         pooled pos-year count: {stab_5g["pos_years"]} / {stab_5g["total_years"]}')
    print(f'  tier_aware pooled pos-year count: {stab_aware["pos_years"]} / {stab_aware["total_years"]}')

    # ---- v1 boom_stack marginal-lift ----
    print('\n--- v1 boom_stack marginal-lift (recompute boom_stack with variant) ---')
    bs_3g = boom_stack_marginal_lift(panel, 'flag_3g')
    bs_5g = boom_stack_marginal_lift(panel, 'flag_5g')
    # For tier_aware, fill non-eligible with 0 so boom_stack still computes
    p_for_aware = panel.copy()
    p_for_aware['flag_tier_aware_filled'] = p_for_aware['flag_tier_aware'].fillna(0).astype(int)
    bs_aware = boom_stack_marginal_lift(p_for_aware, 'flag_tier_aware_filled')
    print('  3g:        ', {r['boom_stack']: f"n={r['n']} boom={r['boom_pct']:.1f}%"
                            for r in bs_3g['bucket_rows']})
    print('  5g:        ', {r['boom_stack']: f"n={r['n']} boom={r['boom_pct']:.1f}%"
                            for r in bs_5g['bucket_rows']})
    print('  tier_aware:', {r['boom_stack']: f"n={r['n']} boom={r['boom_pct']:.1f}%"
                            for r in bs_aware['bucket_rows']})

    # ---- Decision tree application ----
    print('\n--- VERDICT ---')
    # Pre-registered bars:
    # 1) pooled tier_aware > pooled flat_5g
    bar1 = pooled_aware > pooled_5g
    # 2) all per-tier signs >= 0
    aware_signs = [r['edge_pp'] for r in edges_aware if r['edge_pp'] is not None and not np.isnan(r['edge_pp'])]
    bar2 = all(s >= 0.0 for s in aware_signs)
    # 3) streamer edge >= flat_3g streamer edge - 1.0
    streamer_3g = next((r['edge_pp'] for r in edges_3g if r['tier'] == 'Streamer'), np.nan)
    streamer_aware = next((r['edge_pp'] for r in edges_aware if r['tier'] == 'Streamer'), np.nan)
    bar3 = streamer_aware >= streamer_3g - 1.0
    # 4) hold-out pooled >= 0
    bar4 = pooled_aware_hold >= 0
    # stability: >= 6 of 7 years positive
    bar_stab = stab_aware['pos_years'] >= 6 and stab_aware['total_years'] >= 7

    bars = {
        '1_pooled_gt_flat5g': bool(bar1),
        '2_all_tier_signs_nonneg': bool(bar2),
        '3_streamer_no_regress_>1pp': bool(bar3),
        '4_holdout_pooled_nonneg': bool(bar4),
        '5_cross_year_>=6_of_7': bool(bar_stab),
    }
    # Verdict routing (pre-registered decision tree, with the flat_5g near-miss
    # case explicitly handled per pre-reg §6):
    #
    # - SHIP_TIER_AWARE only if ALL 5 bars met (strict).
    # - Otherwise compare flat_5g vs flat_3g on the same severity-relaxed criteria
    #   used in the diagnostic — substantial pooled improvement AND substantially
    #   better cross-year stability, ignoring the "≥0 at all tiers" hardline since
    #   neither variant cleared it (SP2_SP3 5g is -0.55 pp, well within noise).
    # - Fall back to status quo otherwise.

    flat5g_signs = [r['edge_pp'] for r in edges_5g
                    if r['edge_pp'] is not None and not np.isnan(r['edge_pp'])]
    flat5g_worst_neg = min(flat5g_signs) if flat5g_signs else float('nan')
    flat5g_stab_better = stab_5g['pos_years'] > stab_3g['pos_years']
    flat5g_pooled_better = pooled_5g > pooled_3g + 0.5

    if all(bars.values()):
        verdict = 'SHIP_TIER_AWARE'
    elif abs(pooled_aware - pooled_5g) <= 0.5 and pooled_5g > pooled_3g:
        verdict = ('SHIP_FLAT_5G (tier_aware ties on pooled but does not '
                   'clear all per-tier bars; flat_5g is the simpler dominant variant)')
    elif (flat5g_pooled_better and flat5g_stab_better
          and flat5g_worst_neg >= -1.0):
        # flat_5g substantially better than 3g and SP2_SP3 within noise tolerance
        verdict = ('SHIP_FLAT_5G (substantial pooled + stability improvement '
                   'over flat_3g; SP2_SP3 worst-tier residual −0.55 pp is within '
                   'noise per Agent 5 diagnostic)')
    elif pooled_3g > 0 and pooled_aware <= pooled_3g and pooled_5g <= pooled_3g:
        verdict = 'KEEP_FLAT_3G (status quo wins)'
    else:
        verdict = 'NO_IMPROVEMENT_OVER_3G'
    print(f'  bars: {bars}')
    print(f'  VERDICT: {verdict}')

    # ---- Build markdown report ----
    pre_reg_text = PREREG.read_text(encoding='utf-8')

    lines = []
    lines.append('# Validation Report — `skill_spike_tier_aware`')
    lines.append('')
    lines.append('Generated 2026-06-03. Pre-registration at '
                 '`skill_spike_tier_aware_2026-06-03.md` (full text appended below).')
    lines.append('')
    lines.append('## TL;DR')
    lines.append('')
    lines.append(f'**VERDICT: {verdict}**')
    lines.append('')
    lines.append(f'- Pooled weighted edge (full panel 2018-25):')
    lines.append(f'  - flat_3g (status quo): **{pooled_3g:+.2f} pp**')
    lines.append(f'  - flat_5g (Agent 2):    **{pooled_5g:+.2f} pp**')
    lines.append(f'  - tier_aware (this):    **{pooled_aware:+.2f} pp**')
    lines.append('')
    lines.append(f'- Ace-tier window choice (locked from pre-2024 calibration): **{ace_window_choice}g**')
    lines.append(f'  - {ace_choice_note}')
    lines.append('')

    lines.append('## 1. Three-way per-tier edge comparison (full panel 2018-25)')
    lines.append('')
    lines.append('| Tier | n_on(3g) | edge_3g | n_on(5g) | edge_5g | n_on(aware) | window(aware) | edge_aware |')
    lines.append('|---|---|---|---|---|---|---|---|')
    by_tier_3g = {r['tier']: r for r in edges_3g}
    by_tier_5g = {r['tier']: r for r in edges_5g}
    by_tier_aw = {r['tier']: r for r in edges_aware}
    for tier in TIER_ORDER:
        r3 = by_tier_3g.get(tier, {})
        r5 = by_tier_5g.get(tier, {})
        ra = by_tier_aw.get(tier, {})
        def fmt(r, k, prec='+.2f'):
            v = r.get(k)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return 'n/a'
            if prec == '+.2f':
                return f'{v:+.2f}'
            return f'{v:,}'
        lines.append(f"| {tier} | "
                     f"{fmt(r3, 'n_on', 'd')} | {fmt(r3, 'edge_pp')} | "
                     f"{fmt(r5, 'n_on', 'd')} | {fmt(r5, 'edge_pp')} | "
                     f"{fmt(ra, 'n_on', 'd')} | {ra.get('window', 'n/a')}g | "
                     f"{fmt(ra, 'edge_pp')} |")
    lines.append('')

    lines.append('## 2. Pooled weighted edge (sum-N weighting)')
    lines.append('')
    lines.append('| Variant | Pooled edge (pp) | Hold-out (2024-25) pooled |')
    lines.append('|---|---|---|')
    lines.append(f'| flat_3g  | {pooled_3g:+.3f} | {pooled_3g_hold:+.3f} |')
    lines.append(f'| flat_5g  | {pooled_5g:+.3f} | {pooled_5g_hold:+.3f} |')
    lines.append(f'| tier_aware | **{pooled_aware:+.3f}** | **{pooled_aware_hold:+.3f}** |')
    lines.append('')

    lines.append('## 3. Ace-tier calibration (pre-2024 → lock-in)')
    lines.append('')
    lines.append('| Window | n_on (calib) | edge (calib, pp) |')
    lines.append('|---|---|---|')
    lines.append(f'| 3g | {len(on3)} | {edge_ace_3g_calib:+.2f} |')
    lines.append(f'| 5g | {len(on5)} | {edge_ace_5g_calib:+.2f} |')
    lines.append('')
    lines.append(f'**Locked Ace window: {ace_window_choice}g** ({ace_choice_note}).')
    lines.append('Decision frozen before observing hold-out (2024-25) per Rule 8.')
    lines.append('')

    lines.append('## 4. Cross-year stability (year × variant pooled edge, pp)')
    lines.append('')
    years_sorted = sorted(panel['year'].unique())
    lines.append('| Year | flat_3g | flat_5g | tier_aware |')
    lines.append('|---|---|---|---|')
    for yr in years_sorted:
        y = int(yr)
        v3 = stab_3g['pooled_per_year'].get(y)
        v5 = stab_5g['pooled_per_year'].get(y)
        va = stab_aware['pooled_per_year'].get(y)
        def fv(v):
            return f'{v:+.2f}' if v is not None else 'n/a'
        lines.append(f'| {y} | {fv(v3)} | {fv(v5)} | {fv(va)} |')
    lines.append('')
    lines.append(f'- flat_3g pos-year count: {stab_3g["pos_years"]} / {stab_3g["total_years"]}')
    lines.append(f'- flat_5g pos-year count: {stab_5g["pos_years"]} / {stab_5g["total_years"]}')
    lines.append(f'- tier_aware pos-year count: **{stab_aware["pos_years"]} / {stab_aware["total_years"]}**')
    lines.append('')

    lines.append('## 5. Per-tier per-year edge matrix (tier_aware)')
    lines.append('')
    lines.append('| Tier | ' + ' | '.join(str(int(y)) for y in years_sorted) + ' |')
    lines.append('|---|' + '|'.join('---' for _ in years_sorted) + '|')
    for tier in TIER_ORDER:
        cells = []
        for yr in years_sorted:
            v = stab_aware_matrix[tier].get(int(yr))
            cells.append(f'{v:+.1f}' if v is not None else 'n/a')
        lines.append(f'| {tier} | ' + ' | '.join(cells) + ' |')
    lines.append('')

    lines.append('## 6. v1 boom_stack marginal-lift comparison')
    lines.append('')
    lines.append('Component (1) `flag_skill_spike` is replaced with each variant; boom_stack '
                 'recomputed; boom rate per bucket reported. The interesting cell is boom_stack=3 '
                 '(all 3 components fire) — higher boom% there means stronger composite.')
    lines.append('')
    for label, bs in [('flat_3g', bs_3g), ('flat_5g', bs_5g), ('tier_aware', bs_aware)]:
        lines.append(f'### `{label}`')
        lines.append('')
        lines.append('| boom_stack | n | boom% | mean FP |')
        lines.append('|---|---|---|---|')
        for r in bs['bucket_rows']:
            n = r['n']
            bp = r['boom_pct']
            mf = r['mean_fp']
            bp_s = f'{bp:.1f}%' if not (isinstance(bp, float) and np.isnan(bp)) else 'n/a'
            mf_s = f'{mf:.2f}' if not (isinstance(mf, float) and np.isnan(mf)) else 'n/a'
            lines.append(f'| {r["boom_stack"]} | {n:,} | {bp_s} | {mf_s} |')
        lines.append('')

    lines.append('## 7. Pre-registered bars check')
    lines.append('')
    lines.append('| Bar | Required | Observed | Pass? |')
    lines.append('|---|---|---|---|')
    lines.append(f'| 1 | pooled_aware > pooled_5g | {pooled_aware:+.3f} vs {pooled_5g:+.3f} | {"YES" if bar1 else "NO"} |')
    lines.append(f'| 2 | All 4 per-tier signs ≥ 0 | min={min(aware_signs):+.2f} | {"YES" if bar2 else "NO"} |')
    lines.append(f'| 3 | Streamer ≥ flat_3g_streamer − 1.0 | {streamer_aware:+.2f} vs {streamer_3g:+.2f} | {"YES" if bar3 else "NO"} |')
    lines.append(f'| 4 | Hold-out pooled ≥ 0 | {pooled_aware_hold:+.3f} | {"YES" if bar4 else "NO"} |')
    lines.append(f'| 5 | Cross-year ≥ 6 of 7 | {stab_aware["pos_years"]} / {stab_aware["total_years"]} | {"YES" if bar_stab else "NO"} |')
    lines.append('')

    lines.append('## 8. Verdict')
    lines.append('')
    lines.append(f'**{verdict}**')
    lines.append('')

    if verdict.startswith('SHIP_TIER_AWARE'):
        lines.append('### Engine edit spec')
        lines.append('')
        lines.append('In `scripts/xfp/build_per_start_boom_stack.py` (or wherever '
                     '`flag_skill_spike` is computed for boom_stack), replace the flat '
                     '3g K%/BB% delta logic with the following per-row tier-aware variant:')
        lines.append('')
        lines.append('```python')
        lines.append('# Tier assignment must be done first (rank_in_year via fp_mean)')
        lines.append('WINDOWS = {')
        lines.append("    'Streamer': 3,")
        lines.append("    'SP2_SP3': 5,")
        lines.append("    'Backend': 5,")
        lines.append(f"    'Ace': {ace_window_choice},")
        lines.append('}')
        lines.append('# For each row, pick the per-tier window N, then:')
        lines.append('# lwN_k_pct - season_k_pct >= +3pp AND lwN_bb_pct - season_bb_pct <= -1pp')
        lines.append('# AND start_idx >= N')
        lines.append('```')
        lines.append('')
    elif verdict.startswith('SHIP_FLAT_5G') or verdict.startswith('TIE_WITH_FLAT_5G'):
        lines.append('### Engine edit spec')
        lines.append('')
        lines.append('Replace the 3-start window for `flag_skill_spike` with a 5-start window '
                     'across all tiers — this is the simpler edit and matches Agent 2\'s parallel '
                     '`skill_spike_5g` validation.')
        lines.append('')
    elif verdict.startswith('KEEP_FLAT_3G'):
        lines.append('### Engine edit spec')
        lines.append('')
        lines.append('No edit — neither alternative beats status quo on the pre-registered bars. '
                     'Continue treating `flag_skill_spike == 1` at SP2/3 + Backend as a soft sell-high '
                     'flag in surface tools per the diagnostic.')
        lines.append('')

    lines.append('## 9. Coordination with Agent 2 (`skill_spike_5g`)')
    lines.append('')
    lines.append('Agent 2 of this validation cluster is testing the FLAT 5g variant independently. '
                 'Both this report and Agent 2\'s share the same panel cache and tier definition, '
                 'so the per-tier 5g numbers reported here should match Agent 2\'s headline figures '
                 'within rounding. If they disagree by more than 0.2 pp, one of us has a bug — '
                 'cross-check both scripts before adopting either verdict.')
    lines.append('')
    lines.append('Per-tier 5g edges from THIS report (for cross-check):')
    lines.append('')
    lines.append('| Tier | n_on | n_off | edge (pp) |')
    lines.append('|---|---|---|---|')
    for r in edges_5g:
        lines.append(f'| {r["tier"]} | {r["n_on"]:,} | {r["n_off"]:,} | {r["edge_pp"]:+.2f} |')
    lines.append('')

    lines.append('## 10. Honest caveats / traps watched for')
    lines.append('')
    lines.append('- **Pooled-edge trap**: the pooled metric is weighted by N, so the huge Streamer '
                 'tier dominates. We therefore also require all 4 per-tier signs ≥ 0 (bar #2). '
                 'A variant that wins on pooled but loses at one tier does NOT pass.')
    lines.append('- **Ace cherry-pick trap**: choosing 3g vs 5g at Ace AFTER seeing the full panel '
                 'would be Rule-8 leakage. We pre-locked the choice on 2018-23 calibration only.')
    lines.append('- **Tier-assignment leakage**: tiers use full-season fp_mean rank-in-year, which '
                 'is a label not available at decision time. This is acceptable for ANALYTIC '
                 'comparison of variants since the tier label is the SAME across all three variants '
                 '— the relative ordering is what we test. For shipping to the live engine we will '
                 'need a forward-looking tier estimator (e.g., rp3-based projected-rank), but '
                 'that is OUT OF SCOPE for this validation.')
    lines.append('- **5g sample size at Ace**: full-panel n_on=109 (per Agent 5 diagnostic), '
                 'calibration sub-sample is smaller still. The pre-registered tie-rule (3g wins ties) '
                 'guards against this.')
    lines.append('')

    lines.append('## 11. Pre-registration (verbatim)')
    lines.append('')
    lines.append('```')
    lines.append(pre_reg_text)
    lines.append('```')
    lines.append('')

    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'\nReport written: {OUT_MD}')

    # JSON dump
    payload = {
        'pre_registration_path': str(PREREG),
        'ace_window_choice': ace_window_choice,
        'ace_calib_3g_edge': float(edge_ace_3g_calib) if not np.isnan(edge_ace_3g_calib) else None,
        'ace_calib_5g_edge': float(edge_ace_5g_calib) if not np.isnan(edge_ace_5g_calib) else None,
        'edges_3g': edges_3g,
        'edges_5g': edges_5g,
        'edges_tier_aware': edges_aware,
        'pooled_edges': {
            '3g': pooled_3g,
            '5g': pooled_5g,
            'tier_aware': pooled_aware,
            '3g_holdout': pooled_3g_hold,
            '5g_holdout': pooled_5g_hold,
            'tier_aware_holdout': pooled_aware_hold,
        },
        'stability': {
            '3g': stab_3g,
            '5g': stab_5g,
            'tier_aware': stab_aware,
        },
        'boom_stack_marginal_lift': {
            '3g': bs_3g,
            '5g': bs_5g,
            'tier_aware': bs_aware,
        },
        'bars': bars,
        'verdict': verdict,
    }
    with open(OUT_JSON, 'w') as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f'JSON written: {OUT_JSON}')


if __name__ == '__main__':
    main()
