"""validate_skill_spike_5g.py — test skill_spike_5g.

Pre-registered: data/research/validation_runs/skill_spike_5g_2026-06-03.md

skill_spike_5g at a per-start row =
  (last5_K% - season_K%) >= +3 pp AND (last5_BB% - season_BB%) <= -1 pp
  AND start_idx >= 5.

Same thresholds as skill_spike_3g, only window length changes from 3 -> 5.

Two-mode validation:
  Mode A: integration into RP3_FEATS (expected null per diagnostic)
  Mode B: per-tier per-start boom-rate edge (the real test — sign cleanup at
          Backend / SP2/3, retention at Streamer)

Also:
  - Year-by-year stability (>= 5/7 positive at Backend + SP2/3 union)
  - Independence with v1 components (3g, recform, opp_soft)
  - Convergence at split_day 30/44/58 (leakage check)
  - 3g vs 5g head-to-head per tier

Outputs:
  data/research/validation_runs/skill_spike_5g_results.json
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, pearsonr

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report

from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval, TARGET

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RESEARCH = ROOT / 'data' / 'research'
OUT_DIR = RESEARCH / 'validation_runs'
PANEL_CACHE = RESEARCH / '_boom_stack_per_start_panel_cache.parquet'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
CONV_SPLIT_DAYS = [30, 44, 58]

TIER_DEF = [
    ('Ace',      1, 10),
    ('SP2_SP3', 11, 30),
    ('Backend', 31, 50),
    ('Streamer', 51, 10_000),
]


# ---------------------------------------------------------------------------
# Tier assignment (same as diagnostic)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Build 5g flag on cached panel
# ---------------------------------------------------------------------------
def add_running_stats(p: pd.DataFrame) -> pd.DataFrame:
    p = p.sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)
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


def compute_window_metrics(p: pd.DataFrame, window: int) -> pd.DataFrame:
    p = p.copy().sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)
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


# ---------------------------------------------------------------------------
# Mode B per-tier
# ---------------------------------------------------------------------------
def per_tier_edges(panel: pd.DataFrame, flag_col: str,
                   min_prior: int) -> list[dict]:
    rows = []
    for tier_name, _, _ in TIER_DEF:
        sub = panel[(panel['tier'] == tier_name) & (panel['start_idx'] >= min_prior)]
        on = sub[sub[flag_col] == 1]
        off = sub[sub[flag_col] == 0]
        if len(on) < 10 or len(off) < 10:
            rows.append({'tier': tier_name, 'window': flag_col,
                         'n_on': len(on), 'n_off': len(off),
                         'boom_on': float('nan'), 'boom_off': float('nan'),
                         'edge_pp': float('nan'), 'mean_fp_edge': float('nan'),
                         'chi2': None, 'p_value': None})
            continue
        on_boom = (on['fp'] >= 20).mean() * 100
        off_boom = (off['fp'] >= 20).mean() * 100
        # chi2 2x2
        table = np.array([
            [int((on['fp'] >= 20).sum()), int((on['fp'] < 20).sum())],
            [int((off['fp'] >= 20).sum()), int((off['fp'] < 20).sum())],
        ])
        chi2, p, _, _ = chi2_contingency(table) if table.sum(axis=1).min() >= 5 else (np.nan, np.nan, None, None)
        rows.append({
            'tier': tier_name,
            'window': flag_col,
            'n_on': int(len(on)),
            'n_off': int(len(off)),
            'boom_on': float(on_boom),
            'boom_off': float(off_boom),
            'edge_pp': float(on_boom - off_boom),
            'mean_fp_on': float(on['fp'].mean()),
            'mean_fp_off': float(off['fp'].mean()),
            'mean_fp_edge': float(on['fp'].mean() - off['fp'].mean()),
            'chi2': float(chi2) if not np.isnan(chi2) else None,
            'p_value': float(p) if not np.isnan(p) else None,
        })
    return rows


def per_year_edge_at_tier_union(panel: pd.DataFrame, flag_col: str,
                                tier_names: list[str], min_prior: int) -> dict:
    out = {}
    sub_all = panel[panel['tier'].isin(tier_names) & (panel['start_idx'] >= min_prior)]
    for yr in YEARS:
        sub = sub_all[sub_all['year'] == yr]
        on = sub[sub[flag_col] == 1]
        off = sub[sub[flag_col] == 0]
        if len(on) < 10 or len(off) < 10:
            out[yr] = {'n_on': int(len(on)), 'n_off': int(len(off)), 'edge_pp': None}
            continue
        on_boom = (on['fp'] >= 20).mean() * 100
        off_boom = (off['fp'] >= 20).mean() * 100
        out[yr] = {
            'n_on': int(len(on)), 'n_off': int(len(off)),
            'boom_on': float(on_boom), 'boom_off': float(off_boom),
            'edge_pp': float(on_boom - off_boom),
        }
    pos = sum(1 for yr, info in out.items() if info.get('edge_pp') is not None and info['edge_pp'] > 0)
    counted = sum(1 for yr, info in out.items() if info.get('edge_pp') is not None)
    return {'per_year': out, 'pos': pos, 'counted': counted}


# ---------------------------------------------------------------------------
# Independence check
# ---------------------------------------------------------------------------
def independence_corr(panel: pd.DataFrame, candidate: str,
                       others: list[str]) -> dict:
    sub = panel[panel['start_idx'] >= 5].copy()
    # Per-year corr
    per_year = {}
    for yr in YEARS:
        ys = sub[sub['year'] == yr]
        if len(ys) < 50:
            continue
        row = {}
        for o in others:
            if o not in ys.columns:
                row[o] = None
                continue
            try:
                r, _ = pearsonr(ys[candidate].astype(float).values, ys[o].astype(float).values)
                row[o] = float(r)
            except Exception:
                row[o] = None
        per_year[yr] = row
    # Pooled
    pooled = {}
    for o in others:
        if o not in sub.columns:
            pooled[o] = None
            continue
        try:
            r, _ = pearsonr(sub[candidate].astype(float).values, sub[o].astype(float).values)
            pooled[o] = float(r)
        except Exception:
            pooled[o] = None
    return {'per_year': per_year, 'pooled': pooled}


# ---------------------------------------------------------------------------
# Mode A: integration into RP3
# ---------------------------------------------------------------------------
def build_5g_panel_for_cutoffs(starts: pd.DataFrame,
                                cutoffs_per_year: dict[int, list[pd.Timestamp]]) -> pd.DataFrame:
    """For each (pitcher, year, cutoff_date), compute flag_skill_spike_5g
    using starts strictly before cutoff. Used for Mode A merge into rolling."""
    out_rows = []
    for (pid, yr), grp in starts.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        cutoffs = cutoffs_per_year.get(yr, [])
        for cd in cutoffs:
            prior = grp[grp['game_date'] < cd]
            if len(prior) < 5:
                out_rows.append({'pitcher': int(pid), 'year': int(yr),
                                 'cutoff_date': cd,
                                 'flag_skill_spike_5g': 0,
                                 'n_prior_starts': int(len(prior))})
                continue
            sK = prior['actual_K'].sum() / max(prior['actual_PA'].sum(), 1)
            sBB = prior['actual_BB'].sum() / max(prior['actual_PA'].sum(), 1)
            last5 = prior.tail(5)
            l5K = last5['actual_K'].sum() / max(last5['actual_PA'].sum(), 1)
            l5BB = last5['actual_BB'].sum() / max(last5['actual_PA'].sum(), 1)
            dK_pp = (l5K - sK) * 100.0
            dBB_pp = (l5BB - sBB) * 100.0
            flag = int((dK_pp >= 3.0) and (dBB_pp <= -1.0))
            out_rows.append({'pitcher': int(pid), 'year': int(yr),
                             'cutoff_date': cd,
                             'flag_skill_spike_5g': flag,
                             'n_prior_starts': int(len(prior))})
    out = pd.DataFrame(out_rows)
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])
    return out


def per_split_day_lift(rolling: pd.DataFrame, candidate: str) -> dict:
    out: dict = {}
    for sd in CONV_SPLIT_DAYS:
        sub = rolling[rolling['split_day'] == sd].copy()
        if len(sub) < 200:
            out[sd] = {'skipped': True, 'n': len(sub)}
            continue
        py_b, ov_b = cross_year_eval(sub, RP3_FEATS)
        py_f, ov_f = cross_year_eval(sub, RP3_FEATS + [candidate])
        per_year_lift = {y: round(py_f[y]['r'] - py_b[y]['r'], 4)
                         for y in py_b if y in py_f}
        out[sd] = {
            'n_total': int(len(sub)),
            'r_baseline': ov_b['r'],
            'r_full': ov_f['r'],
            'r_gain': round(ov_f['r'] - ov_b['r'], 4),
            'mae_baseline': ov_b['mae'],
            'mae_full': ov_f['mae'],
            'mae_gain': round(ov_b['mae'] - ov_f['mae'], 4),
            'per_year_lift': per_year_lift,
        }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== validate_skill_spike_5g ===')

    # ---- Load cached per-start panel (has 3g flag already) ----
    print('Step 1: load cached per-start panel...')
    panel = pd.read_parquet(PANEL_CACHE)
    panel = panel.dropna(subset=['fp']).copy()
    print(f'  per-start panel rows: {len(panel):,}')

    # Assign tier
    tier_map = assign_tier(panel, min_starts=8)
    panel = panel.merge(tier_map[['pitcher', 'year', 'tier', 'rank_in_year']],
                        on=['pitcher', 'year'], how='inner')
    print(f'  panel rows after tier filter: {len(panel):,}')
    print('  tier counts:')
    print(panel['tier'].value_counts().to_string())

    # Add running stats + 5g window + 3g window (verify), flags
    panel = add_running_stats(panel)
    panel = compute_window_metrics(panel, window=3)
    panel = compute_window_metrics(panel, window=5)
    panel['flag_skill_spike_3g'] = make_spike_flag(panel, 3)
    panel['flag_skill_spike_5g'] = make_spike_flag(panel, 5)

    # Verify the recomputed 3g matches the cached one
    n_match = int((panel['flag_skill_spike_3g'] == panel['flag_skill_spike']).sum())
    print(f'  recomputed 3g vs cached: {n_match}/{len(panel)} match')

    # ---- Mode B: per-tier edges, 3g vs 5g ----
    print('\n=== MODE B: per-tier per-start boom-rate (3g vs 5g) ===')

    rows_3g = per_tier_edges(panel, 'flag_skill_spike_3g', min_prior=3)
    rows_5g = per_tier_edges(panel, 'flag_skill_spike_5g', min_prior=5)

    print('\n  [3g — for reference]')
    for r in rows_3g:
        if np.isnan(r['edge_pp']):
            print(f"    {r['tier']:>9s}  n_on={r['n_on']:>4d}  SKIPPED (too small)")
            continue
        print(f"    {r['tier']:>9s}  n_on={r['n_on']:>4d}  "
              f"boom_on={r['boom_on']:.1f}%  boom_off={r['boom_off']:.1f}%  "
              f"edge={r['edge_pp']:+.2f}pp  fp_edge={r['mean_fp_edge']:+.2f}")

    print('\n  [5g — candidate]')
    for r in rows_5g:
        if np.isnan(r['edge_pp']):
            print(f"    {r['tier']:>9s}  n_on={r['n_on']:>4d}  SKIPPED (too small)")
            continue
        print(f"    {r['tier']:>9s}  n_on={r['n_on']:>4d}  "
              f"boom_on={r['boom_on']:.1f}%  boom_off={r['boom_off']:.1f}%  "
              f"edge={r['edge_pp']:+.2f}pp  fp_edge={r['mean_fp_edge']:+.2f}  "
              f"chi2={r['chi2'] if r['chi2'] else 'NA':.3f}  "
              f"p={r['p_value'] if r['p_value'] else float('nan'):.4f}")

    # ---- Year-by-year stability for Backend + SP2/3 union ----
    print('\n=== YEAR-BY-YEAR STABILITY (Backend + SP2/3 union) ===')
    yr_5g_nonstreamer = per_year_edge_at_tier_union(
        panel, 'flag_skill_spike_5g', ['SP2_SP3', 'Backend'], min_prior=5)
    print(f'  5g, non-streamer (SP2/3 + Backend): {yr_5g_nonstreamer["pos"]}/{yr_5g_nonstreamer["counted"]} years positive')
    for yr, info in yr_5g_nonstreamer['per_year'].items():
        if info['edge_pp'] is None:
            print(f'    {yr}: n_on={info["n_on"]:>3d}  SKIPPED')
            continue
        print(f'    {yr}: n_on={info["n_on"]:>3d}  edge={info["edge_pp"]:+.2f}pp')

    yr_5g_streamer = per_year_edge_at_tier_union(
        panel, 'flag_skill_spike_5g', ['Streamer'], min_prior=5)
    print(f'  5g, streamer: {yr_5g_streamer["pos"]}/{yr_5g_streamer["counted"]} years positive')
    for yr, info in yr_5g_streamer['per_year'].items():
        if info['edge_pp'] is None:
            continue
        print(f'    {yr}: n_on={info["n_on"]:>4d}  edge={info["edge_pp"]:+.2f}pp')

    # Also: 3g for context
    yr_3g_nonstreamer = per_year_edge_at_tier_union(
        panel, 'flag_skill_spike_3g', ['SP2_SP3', 'Backend'], min_prior=3)
    yr_3g_streamer = per_year_edge_at_tier_union(
        panel, 'flag_skill_spike_3g', ['Streamer'], min_prior=3)
    print(f'  [3g, non-streamer: {yr_3g_nonstreamer["pos"]}/{yr_3g_nonstreamer["counted"]} positive — for reference]')
    print(f'  [3g, streamer:     {yr_3g_streamer["pos"]}/{yr_3g_streamer["counted"]} positive — for reference]')

    # ---- Independence ----
    print('\n=== INDEPENDENCE (5g vs v1 components) ===')
    indep = independence_corr(panel, 'flag_skill_spike_5g',
                              ['flag_skill_spike_3g', 'flag_recform_hot',
                               'flag_opp_soft'])
    print('  Pooled:')
    for k, v in indep['pooled'].items():
        print(f'    corr(5g, {k}) = {v:+.3f}' if v is not None else f'    corr(5g, {k}) = NA')
    print('  Per-year corr(5g, 3g):')
    for yr, row in indep['per_year'].items():
        v = row.get('flag_skill_spike_3g')
        print(f'    {yr}: {v:+.3f}' if v is not None else f'    {yr}: NA')

    # ---- Mode A: integration into rp3 ----
    print('\n=== MODE A: integration into rp3 (Rule 9 lift test) ===')

    print('  loading rolling substrate...')
    rolling = prep_rolling()
    sched_path = CACHE / 'ros_schedule_features_2018_2026.csv'
    if sched_path.exists() and 'ros_opp_xwoba_weighted' not in rolling.columns:
        sched = pd.read_csv(sched_path)
        rolling = rolling.merge(
            sched[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']],
            on=['pitcher', 'year', 'split_day'], how='left',
        )
        rolling['ros_opp_xwoba_weighted'] = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform(
            lambda s: s.fillna(s.mean()))
    if 'ros_opp_xwoba_weighted' not in rolling.columns:
        rolling['ros_opp_xwoba_weighted'] = 0.0
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    print(f'  rolling rows: {len(rolling):,}')

    # Build 5g flag at (pitcher, year, cutoff_date) using starts strictly before cutoff
    cutoffs_per_year: dict[int, list[pd.Timestamp]] = {}
    for yr in sorted(rolling['year'].unique()):
        if int(yr) not in YEARS:
            continue
        cutoffs_per_year[int(yr)] = sorted(
            pd.to_datetime(rolling[rolling['year'] == yr]['cutoff_date'].unique()).tolist()
        )

    # Use the per-start panel (re-loaded raw, not the tier-merged one) to compute the cutoff-level flag
    raw_starts = pd.read_parquet(PANEL_CACHE).dropna(subset=['fp']).copy()
    raw_starts = raw_starts[['pitcher', 'year', 'game_date',
                              'actual_K', 'actual_BB', 'actual_PA']].copy()

    print('  building 5g flag at (pitcher, year, cutoff_date)...')
    panel_a = build_5g_panel_for_cutoffs(raw_starts, cutoffs_per_year)
    print(f'  cutoff-level rows: {len(panel_a):,}  '
          f'flag_5g fire rate: {panel_a["flag_skill_spike_5g"].mean():.3%}')

    rolling = rolling.merge(
        panel_a[['pitcher', 'year', 'cutoff_date', 'flag_skill_spike_5g']],
        on=['pitcher', 'year', 'cutoff_date'], how='left',
    )
    rolling['flag_skill_spike_5g'] = rolling['flag_skill_spike_5g'].fillna(0).astype(int)
    print(f'  merged rolling: nonzero flag_5g rate = {(rolling["flag_skill_spike_5g"] > 0).mean():.3%}')

    result_a = evaluate_candidate(rolling, 'flag_skill_spike_5g',
                                   fill_value=0, label='flag_skill_spike_5g')
    print_report(result_a)

    print('\nConvergence across split_day 30/44/58:')
    conv = per_split_day_lift(rolling, 'flag_skill_spike_5g')
    for sd, c in conv.items():
        if c.get('skipped'):
            print(f'  sd={sd}: SKIPPED (n={c["n"]})')
            continue
        print(f'  sd={sd:>3}: r_base={c["r_baseline"]:.4f}  r_full={c["r_full"]:.4f}  '
              f'gain={c["r_gain"]:+.4f}  mae_gain={c["mae_gain"]:+.4f}')

    # Holdout MAE
    py_b, ov_b = cross_year_eval(rolling, RP3_FEATS)
    py_f, ov_f = cross_year_eval(rolling, RP3_FEATS + ['flag_skill_spike_5g'])
    holdout_mae_b = float(np.mean([py_b[y]['mae'] for y in [2024, 2025] if y in py_b]))
    holdout_mae_f = float(np.mean([py_f[y]['mae'] for y in [2024, 2025] if y in py_f]))
    print(f'Holdout MAE baseline: {holdout_mae_b:.4f}  full: {holdout_mae_f:.4f}  '
          f'gain: {holdout_mae_b - holdout_mae_f:+.4f} FP/start')

    # ---- Persist ----
    output = {
        'mode_b_per_tier': {
            '3g': rows_3g,
            '5g': rows_5g,
        },
        'year_stability': {
            '5g_nonstreamer': yr_5g_nonstreamer,
            '5g_streamer': yr_5g_streamer,
            '3g_nonstreamer': yr_3g_nonstreamer,
            '3g_streamer': yr_3g_streamer,
        },
        'independence': indep,
        'mode_a': {
            'rule9_lift_test': result_a,
            'convergence_per_split_day': conv,
            'holdout_mae': {
                'baseline': holdout_mae_b,
                'full': holdout_mae_f,
                'gain_fp_per_start': holdout_mae_b - holdout_mae_f,
            },
        },
        'panel_distribution': {
            'flag_5g_rate_per_start_overall': float(panel['flag_skill_spike_5g'].mean()),
            'flag_5g_rate_per_start_eligible': float(
                panel.loc[panel['start_idx'] >= 5, 'flag_skill_spike_5g'].mean()
            ),
            'flag_5g_rate_by_year': {
                int(yr): float(g.loc[g['start_idx'] >= 5, 'flag_skill_spike_5g'].mean())
                for yr, g in panel.groupby('year')
            },
            'recomputed_3g_match_cached': n_match,
        },
    }
    out_json = OUT_DIR / 'skill_spike_5g_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')


if __name__ == '__main__':
    main()
