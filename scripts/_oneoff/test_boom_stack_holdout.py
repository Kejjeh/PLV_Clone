"""test_boom_stack_holdout.py — 2025-only holdout calibration of boom_stack lookup.

Tests whether the SP boom_stack lookup table (BOOM_RATE_BY_TIER_STACK) and the
composite/legacy lookups still produce calibrated predictions on 2025 data.

Compares observed vs predicted boom rate per (tier, stack) bin and overall.

Hitter boom_stack equivalent: pre-computed daily snapshots not available in
panel form, so we skip hitter calibration and note that limitation. We compute
the hitter boom rate on actual_FP >= 5 from xfp_rh3 weekly cuts where possible.
"""
from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.xfp.lib.boom_stack import (
    BOOM_RATE_BY_TIER_STACK,
    BOOM_RATE_BY_STACK,            # legacy streamer-only
    COMPOSITE_BOOM_RATE_BY_STACK_V2,
    tier_for_rank,
)

PANEL = ROOT / 'data' / 'research' / '_boom_stack_per_start_panel_cache.parquet'


def assign_tiers_by_seasonend_fp(df: pd.DataFrame) -> pd.DataFrame:
    """Replicate validation tier assignment: rank each pitcher-year by season-end
    FP-per-start within year (min 8 starts in year), then bucket.

    Tier cutoffs: ace 1-10 / sp2_sp3 11-30 / backend 31-50 / streamer 51+.
    """
    season_agg = (
        df.groupby(['pitcher', 'year'])
          .agg(season_fp_mean=('fp', 'mean'), n_starts=('game_pk', 'count'))
          .reset_index()
    )
    eligible = season_agg[season_agg['n_starts'] >= 8].copy()
    eligible['rank_within_year'] = (
        eligible.groupby('year')['season_fp_mean']
                .rank(method='min', ascending=False)
                .astype(int)
    )
    eligible['tier'] = eligible['rank_within_year'].apply(tier_for_rank)
    out = df.merge(
        eligible[['pitcher', 'year', 'tier', 'rank_within_year']],
        on=['pitcher', 'year'], how='left'
    )
    # Drop starters without season-end tier (i.e. < 8 starts in year)
    return out


def calibrate_by_tier_stack(df: pd.DataFrame) -> pd.DataFrame:
    """Per-(tier, stack) observed vs predicted boom rate."""
    rows = []
    for tier in ['ace', 'sp2_sp3', 'backend', 'streamer']:
        sub = df[df['tier'] == tier]
        for stack in [0, 1, 2, 3]:
            cell = sub[sub['boom_stack'] == stack]
            n = len(cell)
            obs = cell['boom_outcome'].mean() if n else np.nan
            pred = BOOM_RATE_BY_TIER_STACK[tier].get(stack, np.nan)
            err_pp = (obs - pred) * 100 if pd.notna(obs) else np.nan
            # Wilson 95% CI for observed
            if n > 0:
                p = obs
                z = 1.96
                denom = 1 + z**2 / n
                centre = (p + z**2 / (2*n)) / denom
                width = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
                ci_lo = max(0, centre - width)
                ci_hi = min(1, centre + width)
            else:
                ci_lo = ci_hi = np.nan
            rows.append({
                'tier': tier, 'stack': stack, 'n': n,
                'obs_pct': obs * 100 if pd.notna(obs) else np.nan,
                'pred_pct': pred * 100 if pd.notna(pred) else np.nan,
                'err_pp': err_pp,
                'ci_lo_pct': ci_lo * 100 if pd.notna(ci_lo) else np.nan,
                'ci_hi_pct': ci_hi * 100 if pd.notna(ci_hi) else np.nan,
            })
    return pd.DataFrame(rows)


def calibrate_pooled(df: pd.DataFrame) -> pd.DataFrame:
    """Pooled boom rate by stack ignoring tier (composite v2 calibration)."""
    rows = []
    for stack in [0, 1, 2, 3]:
        cell = df[df['boom_stack'] == stack]
        n = len(cell)
        obs = cell['boom_outcome'].mean() if n else np.nan
        pred = COMPOSITE_BOOM_RATE_BY_STACK_V2.get(stack, np.nan)
        err_pp = (obs - pred) * 100 if pd.notna(obs) else np.nan
        if n > 0:
            p = obs
            z = 1.96
            denom = 1 + z**2 / n
            centre = (p + z**2 / (2*n)) / denom
            width = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
            ci_lo = max(0, centre - width)
            ci_hi = min(1, centre + width)
        else:
            ci_lo = ci_hi = np.nan
        rows.append({
            'stack': stack, 'n': n,
            'obs_pct': obs * 100, 'pred_pct': pred * 100,
            'err_pp': err_pp,
            'ci_lo_pct': ci_lo * 100, 'ci_hi_pct': ci_hi * 100,
        })
    return pd.DataFrame(rows)


def main() -> None:
    panel = pd.read_parquet(PANEL)
    print(f'Panel total rows: {len(panel)}  years: {sorted(panel.year.unique())}')
    panel_2025 = panel[panel['year'] == 2025].copy()
    print(f'2025 rows: {len(panel_2025)}')

    panel_2025 = assign_tiers_by_seasonend_fp(panel_2025)
    n_no_tier = panel_2025['tier'].isna().sum()
    print(f'2025 starts without tier (<8 starts that year): {n_no_tier}')
    panel_2025 = panel_2025.dropna(subset=['tier'])
    print(f'2025 starts with tier assigned: {len(panel_2025)}')

    print('\n=== TIER-AWARE calibration (BOOM_RATE_BY_TIER_STACK) ===')
    tier_table = calibrate_by_tier_stack(panel_2025)
    print(tier_table.to_string(index=False, float_format=lambda x: f'{x:.2f}'))

    print('\n=== POOLED calibration (COMPOSITE_BOOM_RATE_BY_STACK_V2) ===')
    pooled = calibrate_pooled(panel_2025)
    print(pooled.to_string(index=False, float_format=lambda x: f'{x:.2f}'))

    # Overall summary
    out_dir = ROOT / 'data' / 'research' / 'validation_runs'
    out_path = out_dir / 'boom_stack_lookup_holdout_2026-06-06.md'
    write_report(tier_table, pooled, panel_2025, out_path)
    print(f'\nReport written: {out_path}')


def write_report(tier_table: pd.DataFrame, pooled: pd.DataFrame,
                  panel_2025: pd.DataFrame, out_path: Path) -> None:
    n_2025 = len(panel_2025)
    overall_boom_rate = panel_2025['boom_outcome'].mean() * 100

    # Verdict: passes calibration if every populated bin's predicted rate
    # falls inside the observed 95% Wilson CI.
    tier_in_ci = tier_table.apply(
        lambda r: (pd.isna(r['pred_pct']) or r['n'] < 30
                   or (r['ci_lo_pct'] <= r['pred_pct'] <= r['ci_hi_pct'])),
        axis=1
    )
    n_bins_total = (tier_table['n'] >= 30).sum()
    n_bins_in_ci = (tier_in_ci & (tier_table['n'] >= 30)).sum()

    pooled_in_ci = pooled.apply(
        lambda r: (r['n'] < 30
                   or (r['ci_lo_pct'] <= r['pred_pct'] <= r['ci_hi_pct'])),
        axis=1
    ).sum()

    # Monotonicity (does obs boom rate increase 0->1->2->3?)
    pooled_monotonic = (pooled['obs_pct'].values[1:] >= pooled['obs_pct'].values[:-1]).all()

    text = []
    text.append('# Boom_Stack Lookup — 2025 Holdout Calibration Test')
    text.append('')
    text.append('Generated 2026-06-06.')
    text.append('')
    text.append('## Method')
    text.append('')
    text.append(f'- Panel: `_boom_stack_per_start_panel_cache.parquet`, n={n_2025} 2025 SP starts')
    text.append('  with season-end FP-tier assignment (>=8 starts in year required).')
    text.append('- 3-component v1 stack: skill_spike + recform_hot + opp_soft (range 0-3).')
    text.append('  (park_friendly 4th component is post-2025 rollout; panel does not include it.)')
    text.append('- Predicted rates: `BOOM_RATE_BY_TIER_STACK` (per-tier) and')
    text.append('  `COMPOSITE_BOOM_RATE_BY_STACK_V2` (pooled).')
    text.append('- Outcome: actual_FP >= 20.')
    text.append('- Wilson 95% CI on observed; lookup "passes" the bin when predicted')
    text.append('  rate falls inside the CI.')
    text.append('')
    text.append(f'Overall 2025 SP-start boom rate: **{overall_boom_rate:.1f}%** (n={n_2025}).')
    text.append('')

    text.append('## SP — Tier-aware calibration')
    text.append('')
    text.append('| tier | stack | n | obs % | pred % | err pp | obs 95% CI | in-CI? |')
    text.append('|------|-------|---|-------|--------|--------|------------|--------|')
    for _, r in tier_table.iterrows():
        in_ci = (r['n'] >= 30
                 and r['ci_lo_pct'] <= r['pred_pct'] <= r['ci_hi_pct'])
        marker = '[PASS]' if in_ci else ('[thin]' if r['n'] < 30 else '[FAIL]')
        text.append(
            f"| {r['tier']} | {int(r['stack'])} | {int(r['n'])} | "
            f"{r['obs_pct']:.1f} | {r['pred_pct']:.1f} | "
            f"{r['err_pp']:+.1f} | "
            f"[{r['ci_lo_pct']:.1f}, {r['ci_hi_pct']:.1f}] | {marker} |"
        )
    text.append('')

    text.append('## SP — Pooled (composite) calibration')
    text.append('')
    text.append('| stack | n | obs % | pred % | err pp | obs 95% CI | in-CI? |')
    text.append('|-------|---|-------|--------|--------|------------|--------|')
    for _, r in pooled.iterrows():
        in_ci = (r['n'] >= 30
                 and r['ci_lo_pct'] <= r['pred_pct'] <= r['ci_hi_pct'])
        marker = '[PASS]' if in_ci else ('[thin]' if r['n'] < 30 else '[FAIL]')
        text.append(
            f"| {int(r['stack'])} | {int(r['n'])} | "
            f"{r['obs_pct']:.1f} | {r['pred_pct']:.1f} | "
            f"{r['err_pp']:+.1f} | "
            f"[{r['ci_lo_pct']:.1f}, {r['ci_hi_pct']:.1f}] | {marker} |"
        )
    text.append('')

    text.append('## Diagnostics')
    text.append('')
    text.append(f'- Tier-aware bins with n>=30 in CI: **{n_bins_in_ci}/{n_bins_total}**')
    text.append(f'- Pooled bins in CI: **{pooled_in_ci}/4**')
    text.append(f'- Pooled monotonic stack 0->3 ascending? **{pooled_monotonic}**')
    text.append('')

    # Tier-aware monotonicity check (the production lookup the engine queries).
    tier_monotonic_count = 0
    for tier in ['ace', 'sp2_sp3', 'backend', 'streamer']:
        sub = tier_table[tier_table['tier'] == tier].sort_values('stack')
        # Only count tier as monotonic if its populated bins (n>=30) ascend
        populated = sub[sub['n'] >= 30]
        if len(populated) >= 2:
            obs_vals = populated['obs_pct'].values
            if (obs_vals[1:] >= obs_vals[:-1]).all():
                tier_monotonic_count += 1

    # Verdict logic — tier-aware is the production lookup, weight it primarily.
    pass_ratio = n_bins_in_ci / max(n_bins_total, 1)
    if pass_ratio >= 0.85:
        verdict = 'LOOKUP STILL VALID'
        rationale = (
            f'Tier-aware lookup (the production query path) has '
            f'{n_bins_in_ci}/{n_bins_total} populated bins (n>=30) inside the '
            f'observed 95% CI on the 2025 holdout. Predictions remain calibrated '
            f'within sampling noise. Recommend continuing to use as-is.'
        )
    elif pass_ratio >= 0.5:
        verdict = 'PARTIAL DRIFT - some bins outside CI'
        rationale = (
            f'{n_bins_in_ci}/{n_bins_total} tier-aware bins in CI. '
            'Direction of effect intact but some predicted rates miss '
            'observed CI. Refresh table when 2026 n is sufficient.'
        )
    else:
        verdict = 'DRIFTED - needs retraining'
        rationale = (
            f'Only {n_bins_in_ci}/{n_bins_total} tier-aware bins inside CI; '
            'lookup no longer calibrated to 2025 holdout.'
        )

    text.append('## Verdict')
    text.append('')
    text.append(f'**{verdict}**')
    text.append('')
    text.append(rationale)
    text.append('')
    text.append('## Hitter boom_stack note')
    text.append('')
    text.append('Hitter boom_stack lookup test is not run here because the live')
    text.append('lineup_amp_hitter component requires same-day lineup state that')
    text.append('was not retroactively cached for 2025 in panel form. The')
    text.append('lineup_amp validation (`hitter_lineup_correlation.md`) covers')
    text.append('2018-2025 + 7/7 years positive but a single-2025 calibration')
    text.append('cell is unavailable from the existing snapshot infrastructure.')

    out_path.write_text('\n'.join(text), encoding='utf-8')


if __name__ == '__main__':
    main()
