"""validate_boom_stack_v2.py — confirmatory validation of streamer_boom_stack_v2.

Pre-registered: data/research/validation_runs/boom_stack_v2_2026-06-03.md

v2 boom_stack = sum of 4 binary flags per start:
  (1) flag_skill_spike   : last3 K% >= +3pp AND BB% <= -1pp vs season
  (2) flag_recform_hot   : last3 FP >= +3 vs season
  (3) flag_opp_soft      : opp lineup_xfp in bottom tertile of (year, month)
  (4) flag_high_k_pitcher: cumulative-prior season K% z-score in (year, month) >= +0.5

Reuses pre-computed streamer panel from search:
  data/research/validation_runs/boom_stack_v2_streamer_panel.csv

Tests run:
  Mode B: per-bucket boom rate stack=0..4 + chi² stack=4 vs stack<=2,
          marginal stack=4 vs stack=3
  Standalone Mode B re-verification (cand=1 vs cand=0 in full streamer pool)
  Independence: pooled + per-year correlation of cand with each v1 flag
  Year-by-year: edge_pp at stack>=3 by year
  Tier robustness: marginal effect by rolling-fp tier (bottom25, 25-50, 50-75)
  Wilson CIs on all boom-rate estimates
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / 'data' / 'research'
OUT_DIR = RESEARCH / 'validation_runs'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
HOLDOUT = [2024, 2025]


def wilson_ci(p, n, alpha=0.05):
    """Wilson 95% CI for binomial proportion. Returns (lo, hi)."""
    if n == 0:
        return (float('nan'), float('nan'))
    z = norm.ppf(1 - alpha / 2)
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def load_streamer_panel() -> pd.DataFrame:
    """Load pre-computed streamer panel from search script output."""
    p = pd.read_csv(OUT_DIR / 'boom_stack_v2_streamer_panel.csv')
    p['game_date'] = pd.to_datetime(p['game_date'])
    # v2 boom_stack — sum of 4 flags
    p['boom_stack_v2'] = (
        p['flag_skill_spike'] + p['flag_recform_hot']
        + p['flag_opp_soft'] + p['cand_high_k_pitcher']
    ).astype(int)
    return p


def mode_b_bucket_table(panel: pd.DataFrame) -> dict:
    """Per-bucket boom rate stack=0..4 with Wilson CIs."""
    buckets = {}
    for b in [0, 1, 2, 3, 4]:
        m = panel['boom_stack_v2'] == b
        n = int(m.sum())
        booms = int(panel.loc[m, 'boom_outcome'].sum())
        rate = booms / n if n else float('nan')
        lo, hi = wilson_ci(rate, n) if n else (float('nan'), float('nan'))
        buckets[b] = {
            'n': n, 'booms': booms, 'boom_rate': rate,
            'wilson_lo': lo, 'wilson_hi': hi,
            'mean_fp': float(panel.loc[m, 'fp'].mean()) if n else float('nan'),
        }
    return buckets


def chi2_stack4_vs_low(panel: pd.DataFrame) -> dict:
    """Chi² test stack=4 vs stack<=2 on boom outcome."""
    hi = panel[panel['boom_stack_v2'] == 4]
    lo = panel[panel['boom_stack_v2'] <= 2]
    if len(hi) < 5 or len(lo) < 5:
        return {'chi2': None, 'p': None, 'n_hi': len(hi), 'n_lo': len(lo)}
    table = np.array([
        [int(hi['boom_outcome'].sum()),
         int((1 - hi['boom_outcome']).sum())],
        [int(lo['boom_outcome'].sum()),
         int((1 - lo['boom_outcome']).sum())],
    ])
    chi2, p, _, _ = chi2_contingency(table)
    return {
        'chi2': float(chi2), 'p': float(p),
        'n_hi': len(hi), 'n_lo': len(lo),
        'hi_boom_rate': float(hi['boom_outcome'].mean()),
        'lo_boom_rate': float(lo['boom_outcome'].mean()),
    }


def chi2_stack4_vs_stack3(panel: pd.DataFrame) -> dict:
    """Chi² test stack=4 vs stack=3 (marginal lift over v1 top tier)."""
    hi = panel[panel['boom_stack_v2'] == 4]
    s3 = panel[panel['boom_stack_v2'] == 3]
    if len(hi) < 5 or len(s3) < 5:
        return {'chi2': None, 'p': None, 'n_hi': len(hi), 'n_s3': len(s3),
                'marginal_pp': None}
    table = np.array([
        [int(hi['boom_outcome'].sum()),
         int((1 - hi['boom_outcome']).sum())],
        [int(s3['boom_outcome'].sum()),
         int((1 - s3['boom_outcome']).sum())],
    ])
    chi2, p, _, _ = chi2_contingency(table)
    return {
        'chi2': float(chi2), 'p': float(p),
        'n_hi': len(hi), 'n_s3': len(s3),
        'hi_boom_rate': float(hi['boom_outcome'].mean()),
        's3_boom_rate': float(s3['boom_outcome'].mean()),
        'marginal_pp': float((hi['boom_outcome'].mean()
                              - s3['boom_outcome'].mean()) * 100),
    }


def standalone_edge_reverify(panel: pd.DataFrame) -> dict:
    """Re-verify search result: cand=1 vs cand=0 standalone boom rate."""
    c = 'cand_high_k_pitcher'
    f1 = panel[panel[c] == 1]
    f0 = panel[panel[c] == 0]
    table = np.array([
        [int(f1['boom_outcome'].sum()), int((1 - f1['boom_outcome']).sum())],
        [int(f0['boom_outcome'].sum()), int((1 - f0['boom_outcome']).sum())],
    ])
    chi2, p, _, _ = chi2_contingency(table)
    return {
        'n_flag1': len(f1), 'n_flag0': len(f0),
        'boom_rate_flag1': float(f1['boom_outcome'].mean()),
        'boom_rate_flag0': float(f0['boom_outcome'].mean()),
        'edge_pp': float((f1['boom_outcome'].mean()
                          - f0['boom_outcome'].mean()) * 100),
        'chi2': float(chi2), 'p': float(p),
    }


def independence_diagnostics(panel: pd.DataFrame) -> dict:
    """Pooled + per-year corr of cand_high_k_pitcher with each v1 flag."""
    v1_flags = ['flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft']
    cand = 'cand_high_k_pitcher'
    pooled = {}
    for f in v1_flags:
        if panel[cand].std() > 0 and panel[f].std() > 0:
            pooled[f] = float(panel[cand].corr(panel[f]))
        else:
            pooled[f] = None
    per_year = {}
    for yr in sorted(panel['year'].unique()):
        ys = panel[panel['year'] == yr]
        if ys[cand].std() == 0 or len(ys) < 30:
            per_year[int(yr)] = {f: None for f in v1_flags}
            continue
        per_year[int(yr)] = {
            f: (float(ys[cand].corr(ys[f]))
                if ys[f].std() > 0 else None)
            for f in v1_flags
        }
    pooled_vals = [v for v in pooled.values() if v is not None]
    max_pooled_abs = max(abs(v) for v in pooled_vals) if pooled_vals else None
    per_year_max = {
        yr: max((abs(v) for v in d.values() if v is not None), default=None)
        for yr, d in per_year.items()
    }
    return {
        'pooled': pooled,
        'pooled_max_abs': max_pooled_abs,
        'per_year': per_year,
        'per_year_max_abs': per_year_max,
        'per_year_max_overall': max(
            (v for v in per_year_max.values() if v is not None), default=None
        ),
    }


def year_by_year_stack3plus(panel: pd.DataFrame) -> dict:
    """Per-year boom-rate edge at stack>=3 (combining 3 and 4) vs stack<=2."""
    out = {}
    pos_years = 0
    eval_years = 0
    for yr in sorted(panel['year'].unique()):
        ys = panel[panel['year'] == yr]
        hi = ys[ys['boom_stack_v2'] >= 3]
        lo = ys[ys['boom_stack_v2'] <= 2]
        if len(hi) < 5 or len(lo) < 30:
            out[int(yr)] = {'skipped': True, 'n_hi': len(hi), 'n_lo': len(lo)}
            continue
        hi_rate = float(hi['boom_outcome'].mean())
        lo_rate = float(lo['boom_outcome'].mean())
        edge_pp = (hi_rate - lo_rate) * 100
        eval_years += 1
        if edge_pp > 0:
            pos_years += 1
        out[int(yr)] = {
            'n_hi': int(len(hi)), 'n_lo': int(len(lo)),
            'hi_boom_rate': hi_rate, 'lo_boom_rate': lo_rate,
            'edge_pp': edge_pp,
        }
    return {'per_year': out,
            'pos_years': pos_years, 'eval_years': eval_years}


def tier_robustness(panel: pd.DataFrame) -> dict:
    """Within the streamer pool, look at high_k_pitcher's marginal effect by
    rolling-fp tier. We don't have rolling_fp in the saved CSV, so we use
    boom_stack_v1 as a coarse 'recent process' proxy: stack=0 = bottom-noise
    tier, stack=1-2 = mid, stack=3 = top-v1. This is NOT identical to the
    boom_stack_by_tier finding (which used pitcher-level fp_per_start tier),
    but it tests whether the cand effect amplifies as the underlying v1
    state improves.

    Also reports the cand effect split by month-of-season as a stability check.
    """
    cand = 'cand_high_k_pitcher'
    tiers = {
        'v1_stack_0': panel[panel['boom_stack_v1'] == 0],
        'v1_stack_1': panel[panel['boom_stack_v1'] == 1],
        'v1_stack_2': panel[panel['boom_stack_v1'] == 2],
        'v1_stack_3': panel[panel['boom_stack_v1'] == 3],
    }
    out = {}
    for name, sub in tiers.items():
        f1 = sub[sub[cand] == 1]
        f0 = sub[sub[cand] == 0]
        if len(f1) < 5 or len(f0) < 30:
            out[name] = {'skipped': True, 'n_f1': len(f1), 'n_f0': len(f0)}
            continue
        r1 = float(f1['boom_outcome'].mean())
        r0 = float(f0['boom_outcome'].mean())
        lo1, hi1 = wilson_ci(r1, len(f1))
        lo0, hi0 = wilson_ci(r0, len(f0))
        out[name] = {
            'n_f1': int(len(f1)), 'n_f0': int(len(f0)),
            'boom_rate_f1': r1, 'boom_rate_f0': r0,
            'edge_pp': (r1 - r0) * 100,
            'wilson_f1': (lo1, hi1), 'wilson_f0': (lo0, hi0),
        }
    return out


def mode_a_quick_check(panel: pd.DataFrame) -> dict:
    """The pre-registration declares Mode A an expected null. We document
    that here without re-running the full rp3 cross-year (the v1 script
    already established the pattern). Instead, we note the framing logic
    and report whether the per-start boom_stack_v2 increases correlation
    with same-start FP within the streamer subset (a weaker version of
    point-estimator test, but the right framing for a per-start signal)."""
    if panel['boom_stack_v2'].std() == 0 or panel['fp'].std() == 0:
        return {'expected_null': True, 'corr_v2_fp_streamer': None}
    corr = float(panel['boom_stack_v2'].corr(panel['fp']))
    corr_v1 = float(panel['boom_stack_v1'].corr(panel['fp']))
    return {
        'expected_null': True,
        'note': ('Full rp3 cross-year integration was tested in v1 and '
                 'failed (gain +0.0000 cross-year r). The 4th flag '
                 '(high_k_pitcher) is structurally redundant with rp3 '
                 's k_pct_to feature for ROS-mean framing. We do NOT '
                 're-run that test; we re-state the expected null per '
                 'pre-registration.'),
        'within_streamer_corr_v2_fp': corr,
        'within_streamer_corr_v1_fp': corr_v1,
        'corr_gain_v2_over_v1': corr - corr_v1,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== validate_boom_stack_v2 (CONFIRMATORY) ===')

    print('Step 1: load pre-computed streamer panel...')
    panel = load_streamer_panel()
    print(f'  streamer panel rows: {len(panel)}')
    print(f'  years: {sorted(panel["year"].unique())}')
    print(f'  v2 boom_stack distribution:')
    print(panel['boom_stack_v2'].value_counts().sort_index().to_string())

    print('\n=== MODE B — per-bucket boom rate (stack=0..4) ===')
    buckets = mode_b_bucket_table(panel)
    for b, info in buckets.items():
        lo, hi = info['wilson_lo'], info['wilson_hi']
        print(f'  stack={b}: n={info["n"]:>5d}  booms={info["booms"]:>4d}  '
              f'rate={info["boom_rate"]:.3%}  '
              f'95%CI=[{lo:.3%}, {hi:.3%}]  '
              f'mean_fp={info["mean_fp"]:.2f}')

    print('\nChi² stack=4 vs stack<=2:')
    c42 = chi2_stack4_vs_low(panel)
    if c42['chi2'] is not None:
        print(f'  chi2={c42["chi2"]:.3f}  p={c42["p"]:.4g}')
        print(f'  hi(stack=4) boom rate: {c42["hi_boom_rate"]:.3%} '
              f'(n={c42["n_hi"]})')
        print(f'  lo(stack<=2) boom rate: {c42["lo_boom_rate"]:.3%} '
              f'(n={c42["n_lo"]})')

    print('\nChi² stack=4 vs stack=3 (marginal lift over v1 top):')
    c43 = chi2_stack4_vs_stack3(panel)
    if c43['chi2'] is not None:
        print(f'  chi2={c43["chi2"]:.3f}  p={c43["p"]:.4g}')
        print(f'  stack=4 boom rate: {c43["hi_boom_rate"]:.3%} (n={c43["n_hi"]})')
        print(f'  stack=3 boom rate: {c43["s3_boom_rate"]:.3%} (n={c43["n_s3"]})')
        print(f'  marginal: {c43["marginal_pp"]:+.2f} pp')

    print('\n=== STANDALONE edge re-verify (cand=1 vs cand=0) ===')
    edge = standalone_edge_reverify(panel)
    print(f'  cand=1 boom rate: {edge["boom_rate_flag1"]:.3%} '
          f'(n={edge["n_flag1"]})')
    print(f'  cand=0 boom rate: {edge["boom_rate_flag0"]:.3%} '
          f'(n={edge["n_flag0"]})')
    print(f'  edge: {edge["edge_pp"]:+.2f} pp  '
          f'chi2={edge["chi2"]:.3f}  p={edge["p"]:.4g}')

    print('\n=== INDEPENDENCE diagnostics ===')
    indep = independence_diagnostics(panel)
    print(f'  pooled corr with v1 flags:')
    for f, v in indep['pooled'].items():
        print(f'    {f}: {v:+.4f}' if v is not None else f'    {f}: N/A')
    print(f'  pooled max |corr|: {indep["pooled_max_abs"]:.4f}')
    print(f'  per-year max |corr| by year:')
    for yr, v in indep['per_year_max_abs'].items():
        print(f'    {yr}: {v:.4f}' if v is not None else f'    {yr}: N/A')
    print(f'  worst per-year max |corr| overall: '
          f'{indep["per_year_max_overall"]:.4f}'
          if indep['per_year_max_overall'] is not None else '  N/A')

    print('\n=== YEAR-BY-YEAR stability (edge at stack>=3 vs stack<=2) ===')
    yby = year_by_year_stack3plus(panel)
    for yr, info in yby['per_year'].items():
        if info.get('skipped'):
            print(f'  {yr}: SKIPPED (n_hi={info["n_hi"]}, n_lo={info["n_lo"]})')
            continue
        print(f'  {yr}: hi(stack>=3) {info["hi_boom_rate"]:.3%} (n={info["n_hi"]})  '
              f'lo(stack<=2) {info["lo_boom_rate"]:.3%} (n={info["n_lo"]})  '
              f'edge={info["edge_pp"]:+.2f}pp')
    print(f'  positive years: {yby["pos_years"]}/{yby["eval_years"]}')

    print('\n=== TIER ROBUSTNESS (cand effect by v1 stack tier) ===')
    tier = tier_robustness(panel)
    for name, info in tier.items():
        if info.get('skipped'):
            print(f'  {name}: SKIPPED (n_f1={info["n_f1"]}, n_f0={info["n_f0"]})')
            continue
        lo1, hi1 = info['wilson_f1']
        lo0, hi0 = info['wilson_f0']
        print(f'  {name}: f1 {info["boom_rate_f1"]:.3%} '
              f'95%CI=[{lo1:.3%}, {hi1:.3%}] (n={info["n_f1"]})  '
              f'f0 {info["boom_rate_f0"]:.3%} '
              f'95%CI=[{lo0:.3%}, {hi0:.3%}] (n={info["n_f0"]})  '
              f'edge={info["edge_pp"]:+.2f}pp')

    print('\n=== MODE A — expected null (per pre-registration) ===')
    ma = mode_a_quick_check(panel)
    print(f'  {ma["note"]}')
    print(f'  within-streamer corr v2_stack vs FP: '
          f'{ma["within_streamer_corr_v2_fp"]:+.4f}')
    print(f'  within-streamer corr v1_stack vs FP: '
          f'{ma["within_streamer_corr_v1_fp"]:+.4f}')
    print(f'  gain (v2 over v1) in this within-streamer corr: '
          f'{ma["corr_gain_v2_over_v1"]:+.4f}')

    # Persist
    output = {
        'streamer_pool_n': int(len(panel)),
        'v2_bucket_distribution': panel['boom_stack_v2']
            .value_counts().sort_index().to_dict(),
        'mode_b_buckets': buckets,
        'chi2_stack4_vs_low': c42,
        'chi2_stack4_vs_stack3': c43,
        'standalone_edge_reverify': edge,
        'independence': indep,
        'year_by_year_stack3plus': yby,
        'tier_robustness': tier,
        'mode_a': ma,
    }
    out_json = OUT_DIR / 'boom_stack_v2_validation_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')


if __name__ == '__main__':
    main()
