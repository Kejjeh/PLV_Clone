"""diagnose_skill_spike_anti_predictive.py

Diagnose WHY flag_skill_spike (last3_K% delta >= +3pp AND last3_BB% delta <= -1pp)
is anti-predictive of boom at SP2/3 and Backend tiers but positive at Streamer:

  Ace      : +3.1 pp
  SP2/3    : -3.4 pp
  Backend  : -4.1 pp
  Streamer : +2.7 pp

Three hypotheses tested:
  H1 — Regression to mean: established pitchers have stable baselines; spike =
       outlier outcome window that reverts.
  H2 — Sample-size noise: 3-start window too short; lengthen to 5 → sign flips.
  H3 — Context confound: spike-3 driven by softer opponents that don't repeat.

Outputs:
  data/research/validation_runs/skill_spike_anti_predictive_diagnosis.md
  data/research/validation_runs/skill_spike_diagnosis_data.json
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
OUT_MD = ROOT / 'data' / 'research' / 'validation_runs' / 'skill_spike_anti_predictive_diagnosis.md'
OUT_JSON = ROOT / 'data' / 'research' / 'validation_runs' / 'skill_spike_diagnosis_data.json'

TIER_DEF = [
    ('Ace',      1, 10),
    ('SP2_SP3', 11, 30),
    ('Backend', 31, 50),
    ('Streamer', 51, 10_000),
]


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
    """Add running season K%, season FP per start, and last-N K%/FP windows.
    All strictly prior-to-game.
    """
    p = panel.sort_values(['pitcher', 'year', 'game_date']).copy()
    p['start_idx'] = p.groupby(['pitcher', 'year']).cumcount()  # 0-based

    # prior-game cumulative sums for season-to-date
    g = p.groupby(['pitcher', 'year'])
    p['cum_K_incl'] = g['actual_K'].cumsum()
    p['cum_BB_incl'] = g['actual_BB'].cumsum()
    p['cum_PA_incl'] = g['actual_PA'].cumsum()
    p['cum_FP_incl'] = g['fp'].cumsum()

    # prior = inclusive minus current
    p['cum_K_prior'] = p['cum_K_incl'] - p['actual_K']
    p['cum_BB_prior'] = p['cum_BB_incl'] - p['actual_BB']
    p['cum_PA_prior'] = p['cum_PA_incl'] - p['actual_PA']
    p['cum_FP_prior'] = p['cum_FP_incl'] - p['fp']

    p['season_k_pct'] = p['cum_K_prior'] / p['cum_PA_prior'].replace(0, np.nan)
    p['season_bb_pct'] = p['cum_BB_prior'] / p['cum_PA_prior'].replace(0, np.nan)
    p['season_fp_per_start'] = p['cum_FP_prior'] / p['start_idx'].replace(0, np.nan)

    return p


def compute_window_metrics(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    """For each row, compute K%, BB%, FP/start using the last `window` strictly-prior starts."""
    p = panel.copy().sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)

    # Use shift+rolling for strictly-prior
    g = p.groupby(['pitcher', 'year'], sort=False)
    # Shift each metric by 1 so current game excluded, then rolling sum over `window`
    p[f'lw{window}_K'] = g['actual_K'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()).reset_index(level=[0,1], drop=True)
    p[f'lw{window}_BB'] = g['actual_BB'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()).reset_index(level=[0,1], drop=True)
    p[f'lw{window}_PA'] = g['actual_PA'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()).reset_index(level=[0,1], drop=True)
    p[f'lw{window}_FP_sum'] = g['fp'].apply(
        lambda s: s.shift(1).rolling(window, min_periods=window).sum()).reset_index(level=[0,1], drop=True)

    p[f'lw{window}_k_pct'] = p[f'lw{window}_K'] / p[f'lw{window}_PA'].replace(0, np.nan)
    p[f'lw{window}_bb_pct'] = p[f'lw{window}_BB'] / p[f'lw{window}_PA'].replace(0, np.nan)
    p[f'lw{window}_fp_per_start'] = p[f'lw{window}_FP_sum'] / window

    return p


def make_skill_spike_flag(panel: pd.DataFrame, window: int) -> pd.Series:
    """Skill spike at window N: lwN_k_pct - season_k_pct >= +3 pp AND
    lwN_bb_pct - season_bb_pct <= -1 pp, with n_prior_starts >= N+ (use start_idx>=N)."""
    dK_pp = (panel[f'lw{window}_k_pct'] - panel['season_k_pct']) * 100.0
    dBB_pp = (panel[f'lw{window}_bb_pct'] - panel['season_bb_pct']) * 100.0
    enough = panel['start_idx'] >= window
    return ((dK_pp >= 3.0) & (dBB_pp <= -1.0) & enough).astype(int)


def h1_variance_test(panel: pd.DataFrame) -> dict:
    """H1 — within-season per-start K% variance by tier.
    If SP2/3 / Backend pitchers have LOWER within-season K% variance than
    Streamers, then a 3-start spike is a tail event → reverts to lower true talent.
    """
    rows = []
    for tier_name, _, _ in TIER_DEF:
        sub = panel[panel['tier'] == tier_name]
        if len(sub) == 0:
            continue
        # per pitcher-year: variance of per-start k_pct AND mean k_pct
        agg = sub.groupby(['pitcher', 'year']).agg(
            mean_k=('k_pct', 'mean'),
            std_k=('k_pct', 'std'),
            mean_fp=('fp', 'mean'),
            std_fp=('fp', 'std'),
            n_starts=('fp', 'size'),
        ).reset_index()
        agg = agg[agg['n_starts'] >= 8]

        rows.append({
            'tier': tier_name,
            'n_pitcher_years': len(agg),
            'mean_season_k_pct': float(agg['mean_k'].mean()),
            'median_within_season_k_std': float(agg['std_k'].median()),
            'mean_within_season_k_std': float(agg['std_k'].mean()),
            'median_within_season_fp_std': float(agg['std_fp'].median()),
            # CV of K%
            'k_coef_of_variation': float((agg['std_k'] / agg['mean_k']).median()),
        })
    return {'tier_variance_table': rows}


def h2_window_sensitivity(panel: pd.DataFrame) -> dict:
    """H2 — re-run boom-rate analysis with spike windows 3, 5, 7.
    If anti-predictive sign at non-streamer tiers flips at window=5 or 7,
    H2 is supported.
    """
    # Build window=5 and window=7 spike flags in addition to the existing window=3
    p = panel.copy()
    p = compute_window_metrics(p, window=5)
    p = compute_window_metrics(p, window=7)
    p['flag_skill_spike_5g'] = make_skill_spike_flag(p, 5)
    p['flag_skill_spike_7g'] = make_skill_spike_flag(p, 7)
    # boom_outcome is fp >= 20

    results = {}
    for window_key in ['flag_skill_spike', 'flag_skill_spike_5g', 'flag_skill_spike_7g']:
        tier_rows = []
        for tier_name, _, _ in TIER_DEF:
            sub = p[p['tier'] == tier_name]
            # require n_prior_starts >= the window size (already enforced in 5g/7g via start_idx, but
            # for the 3g case panel was filtered upstream)
            if window_key == 'flag_skill_spike':
                ssub = sub[sub['n_prior_starts'] >= 3]
            elif window_key == 'flag_skill_spike_5g':
                ssub = sub[sub['start_idx'] >= 5]
            else:
                ssub = sub[sub['start_idx'] >= 7]
            on = ssub[ssub[window_key] == 1]
            off = ssub[ssub[window_key] == 0]
            if len(on) < 10 or len(off) < 10:
                continue
            on_boom = (on['fp'] >= 20).mean() * 100
            off_boom = (off['fp'] >= 20).mean() * 100
            tier_rows.append({
                'tier': tier_name,
                'window': window_key,
                'n_on': len(on),
                'n_off': len(off),
                'boom_on': on_boom,
                'boom_off': off_boom,
                'edge_pp': on_boom - off_boom,
                'mean_fp_on': float(on['fp'].mean()),
                'mean_fp_off': float(off['fp'].mean()),
                'mean_fp_edge': float(on['fp'].mean() - off['fp'].mean()),
            })
        results[window_key] = tier_rows
    return {'window_sensitivity': results, 'panel_with_windows': p}


def h1b_forward_kpct_reversion(panel_w: pd.DataFrame) -> dict:
    """H1b — direct reversion test.
    For SP2/3 and Backend pitchers with flag_skill_spike == 1 (3g):
    Compare (a) pre-spike season-to-date K%, (b) spike-3 K%, (c) next-3 K%.
    If next-3 K% reverts back toward pre-spike, H1 confirmed.
    """
    p = panel_w.sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)

    # For each row that IS the start AFTER the spike-3 window, we want:
    #   pre-spike season K% (excluding the 3 spike starts)
    #   the 3-start K% in the spike window (lw3_k_pct)
    #   the next-3 starts K% (forward)

    # Compute forward last-3 (i.e., this start + next 2) for K%
    g = p.groupby(['pitcher', 'year'], sort=False)
    # next3 includes this row and next 2 (a forward-looking window starting at this row)
    p['fwd3_K'] = g['actual_K'].apply(
        lambda s: s.rolling(3, min_periods=3).sum().shift(-2)).reset_index(level=[0,1], drop=True)
    p['fwd3_PA'] = g['actual_PA'].apply(
        lambda s: s.rolling(3, min_periods=3).sum().shift(-2)).reset_index(level=[0,1], drop=True)
    p['fwd3_FP_sum'] = g['fp'].apply(
        lambda s: s.rolling(3, min_periods=3).sum().shift(-2)).reset_index(level=[0,1], drop=True)
    p['fwd3_k_pct'] = p['fwd3_K'] / p['fwd3_PA'].replace(0, np.nan)
    p['fwd3_fp_per_start'] = p['fwd3_FP_sum'] / 3

    # The "spike fired" row is the start AFTER the 3-start spike window. So at row i where
    # flag_skill_spike==1, lw3 stats use starts i-3..i-1 (prior). At this row, the "next 3"
    # starts are i, i+1, i+2 (fwd3).

    rows = []
    for tier_name in ['Ace', 'SP2_SP3', 'Backend', 'Streamer']:
        sub = p[(p['tier'] == tier_name) & (p['flag_skill_spike'] == 1)].copy()
        sub = sub.dropna(subset=['fwd3_k_pct', 'season_k_pct'])
        if len(sub) < 20:
            continue
        # We want the "pre-spike" season K% which is the season K% NOT INCLUDING the spike window.
        # Currently season_k_pct uses cum_K_prior which is all prior starts INCLUDING the spike-3.
        # So pre-spike season K% = (cum_K_prior - lw3_K) / (cum_PA_prior - lw3_PA)
        cum_K_pre_spike = sub['cum_K_prior'] - sub['lw3_K']
        cum_PA_pre_spike = sub['cum_PA_prior'] - sub['lw3_PA']
        pre_spike_k = cum_K_pre_spike / cum_PA_pre_spike.replace(0, np.nan)
        sub['pre_spike_k_pct'] = pre_spike_k

        valid = sub.dropna(subset=['pre_spike_k_pct', 'fwd3_k_pct'])
        if len(valid) < 20:
            continue
        rows.append({
            'tier': tier_name,
            'n_spikes_with_forward_window': len(valid),
            'pre_spike_k_pct_mean': float(valid['pre_spike_k_pct'].mean()),
            'spike3_k_pct_mean': float(valid['lw3_k_pct'].mean()),
            'fwd3_k_pct_mean': float(valid['fwd3_k_pct'].mean()),
            'spike_delta_pp': float((valid['lw3_k_pct'] - valid['pre_spike_k_pct']).mean() * 100),
            'fwd_delta_vs_pre_pp': float((valid['fwd3_k_pct'] - valid['pre_spike_k_pct']).mean() * 100),
            'reversion_fraction_of_spike': float(
                ((valid['lw3_k_pct'] - valid['fwd3_k_pct']) /
                 (valid['lw3_k_pct'] - valid['pre_spike_k_pct']).replace(0, np.nan)).median()
            ),
            # Also FP-side
            'fwd3_fp_per_start_mean': float(valid['fwd3_fp_per_start'].mean()),
            'pre_spike_fp_per_start_mean': float(
                ((valid['cum_FP_prior'] - valid['lw3_FP_sum']) / (valid['start_idx'] - 3).replace(0, np.nan)).mean()
            ),
        })
    return {'forward_reversion': rows}


def h3_opp_strength(panel_w: pd.DataFrame) -> dict:
    """H3 — opponent confound test.
    For spike==1 rows: compare the lineup_xfp of the spike-3 starts (the 3 prior
    starts that triggered the spike) vs the pitcher's season-to-date avg lineup_xfp.
    If spike-3 opponents were systematically softer, H3 supported.

    Also: compare lineup_xfp of the CURRENT start (where prediction is made) vs season avg.
    If current start opp == soft, then it would have already triggered opp_soft.
    """
    p = panel_w.sort_values(['pitcher', 'year', 'game_date']).reset_index(drop=True)
    g = p.groupby(['pitcher', 'year'], sort=False)

    # Mean lineup_xfp of last 3 prior starts (strictly prior)
    p['lw3_opp_xfp_mean'] = g['lineup_xfp'].apply(
        lambda s: s.shift(1).rolling(3, min_periods=3).mean()).reset_index(level=[0,1], drop=True)

    # Season-to-date opp xfp (strictly prior)
    p['cum_opp_xfp_incl'] = g['lineup_xfp'].cumsum()
    p['cum_opp_xfp_prior'] = p['cum_opp_xfp_incl'] - p['lineup_xfp']
    p['season_opp_xfp_mean'] = p['cum_opp_xfp_prior'] / p['start_idx'].replace(0, np.nan)

    rows = []
    for tier_name in ['Ace', 'SP2_SP3', 'Backend', 'Streamer']:
        sub_on = p[(p['tier'] == tier_name) & (p['flag_skill_spike'] == 1)].dropna(
            subset=['lw3_opp_xfp_mean', 'season_opp_xfp_mean', 'lineup_xfp'])
        sub_off = p[(p['tier'] == tier_name) & (p['flag_skill_spike'] == 0) & (p['n_prior_starts'] >= 3)].dropna(
            subset=['lw3_opp_xfp_mean', 'season_opp_xfp_mean', 'lineup_xfp'])
        if len(sub_on) < 20 or len(sub_off) < 20:
            continue
        rows.append({
            'tier': tier_name,
            'n_spike': len(sub_on),
            'n_nospike': len(sub_off),
            # Were the 3 spike starts against softer opponents than season avg?
            'spike3_opp_xfp_mean': float(sub_on['lw3_opp_xfp_mean'].mean()),
            'spike_season_opp_xfp_mean': float(sub_on['season_opp_xfp_mean'].mean()),
            'spike_opp_gap_lw3_vs_season': float(
                (sub_on['lw3_opp_xfp_mean'] - sub_on['season_opp_xfp_mean']).mean()),
            # Compare to nospike control
            'nospike_lw3_opp_xfp_mean': float(sub_off['lw3_opp_xfp_mean'].mean()),
            'nospike_season_opp_xfp_mean': float(sub_off['season_opp_xfp_mean'].mean()),
            'nospike_opp_gap_lw3_vs_season': float(
                (sub_off['lw3_opp_xfp_mean'] - sub_off['season_opp_xfp_mean']).mean()),
            # The CURRENT start (predicted) opp xfp
            'spike_current_opp_xfp_mean': float(sub_on['lineup_xfp'].mean()),
            'nospike_current_opp_xfp_mean': float(sub_off['lineup_xfp'].mean()),
        })
    return {'opp_strength': rows}


def main():
    print('Loading cached panel...')
    panel = pd.read_parquet(CACHE_PANEL)
    panel = panel.dropna(subset=['fp']).copy()
    panel['boom_stack'] = panel['boom_stack'].fillna(0).astype(int)

    # Assign tiers
    tier_map = assign_tier(panel, min_starts=8)
    panel = panel.merge(tier_map[['pitcher', 'year', 'tier', 'rank_in_year']],
                        on=['pitcher', 'year'], how='inner')
    print(f'  panel rows after tier filter: {len(panel):,}')
    print('  tier counts:')
    print(panel['tier'].value_counts().to_string())

    # Add running stats for the panel
    panel = add_running_stats(panel)

    # H1 — within-season variance
    print('\n--- H1: within-season K% variance by tier ---')
    h1 = h1_variance_test(panel)
    for r in h1['tier_variance_table']:
        print(f"  {r['tier']:>9s}  n_py={r['n_pitcher_years']:>4d}  "
              f"mean_K={r['mean_season_k_pct']:.3f}  "
              f"med_within_std={r['median_within_season_k_std']:.3f}  "
              f"K_CV={r['k_coef_of_variation']:.3f}")

    # H2 — window sensitivity (requires recomputing 3g, 5g, 7g lw-stats and flags)
    # Also pre-compute lw3 stats for H1b reversion test.
    print('\n--- H2: window sensitivity (3 vs 5 vs 7 start spike windows) ---')
    panel = compute_window_metrics(panel, window=3)
    h2 = h2_window_sensitivity(panel)
    panel_w = h2.pop('panel_with_windows')
    for win_key, rows in h2['window_sensitivity'].items():
        print(f'  [{win_key}]')
        for r in rows:
            print(f"    {r['tier']:>9s}  n_on={r['n_on']:>4d}  "
                  f"boom_on={r['boom_on']:.1f}%  boom_off={r['boom_off']:.1f}%  "
                  f"edge={r['edge_pp']:+.1f} pp  mean_fp_edge={r['mean_fp_edge']:+.2f}")

    # H1b — forward K% reversion (direct test of H1)
    print('\n--- H1b: forward K% reversion after spike ---')
    h1b = h1b_forward_kpct_reversion(panel_w)
    for r in h1b['forward_reversion']:
        print(f"  {r['tier']:>9s}  n={r['n_spikes_with_forward_window']:>4d}  "
              f"pre={r['pre_spike_k_pct_mean']:.3f}  "
              f"spike3={r['spike3_k_pct_mean']:.3f}  "
              f"fwd3={r['fwd3_k_pct_mean']:.3f}  "
              f"fwd_vs_pre={r['fwd_delta_vs_pre_pp']:+.1f} pp")

    # H3 — opp strength confound
    print('\n--- H3: opponent strength gap at spike ---')
    h3 = h3_opp_strength(panel_w)
    for r in h3['opp_strength']:
        print(f"  {r['tier']:>9s}  n_spike={r['n_spike']:>4d}  "
              f"spike_lw3_opp={r['spike3_opp_xfp_mean']:.3f}  "
              f"spike_season_opp={r['spike_season_opp_xfp_mean']:.3f}  "
              f"spike_gap={r['spike_opp_gap_lw3_vs_season']:+.4f}  "
              f"nospike_gap={r['nospike_opp_gap_lw3_vs_season']:+.4f}")

    # ----- Build markdown report -----
    lines = []
    lines.append('# Why is `flag_skill_spike` Anti-Predictive at SP2/3 + Backend?')
    lines.append('')
    lines.append('Generated 2026-06-03. Diagnostic follow-up to `boom_stack_by_tier.md`.')
    lines.append('')
    lines.append('## 0. Finding being explained')
    lines.append('')
    lines.append('From `boom_stack_by_tier.md` Section 3, edge of `flag_skill_spike` on boom% (next start FP ≥ 20):')
    lines.append('')
    lines.append('| Tier | n(spike=1) | boom% on | boom% off | edge (pp) |')
    lines.append('|---|---|---|---|---|')
    lines.append('| Ace | 186 | 46.8% | 43.7% | +3.1 |')
    lines.append('| SP2/3 | 361 | 26.6% | 30.0% | **−3.4** |')
    lines.append('| Backend | 329 | 18.5% | 22.7% | **−4.1** |')
    lines.append('| Streamer | 1,632 | 13.5% | 10.8% | +2.7 |')
    lines.append('')
    lines.append('The signal **flips sign** at the non-streamer tiers and is most anti-predictive at Backend (−4.1 pp).')
    lines.append('')
    lines.append('## 1. H1 — Regression to mean (within-season K% variance by tier)')
    lines.append('')
    lines.append('If established pitchers have stable true K% baselines and lower within-season noise, '
                 'a 3-start spike is more likely to be an outlier outcome window than a real skill change.')
    lines.append('')
    lines.append('| Tier | n pitcher-years | mean season K% | median within-season per-start K% std | K% coef of variation (median) |')
    lines.append('|---|---|---|---|---|')
    for r in h1['tier_variance_table']:
        lines.append(f"| {r['tier']} | {r['n_pitcher_years']:,} | "
                     f"{r['mean_season_k_pct']*100:.1f}% | "
                     f"{r['median_within_season_k_std']*100:.2f} pp | "
                     f"{r['k_coef_of_variation']:.3f} |")
    lines.append('')
    # Interpret H1 — is non-streamer variance lower than streamer?
    var_by_tier = {r['tier']: r['median_within_season_k_std'] for r in h1['tier_variance_table']}
    if 'Streamer' in var_by_tier and 'Backend' in var_by_tier and 'SP2_SP3' in var_by_tier:
        h1_supported = (var_by_tier['Backend'] < var_by_tier['Streamer']) and (var_by_tier['SP2_SP3'] < var_by_tier['Streamer'])
        if h1_supported:
            verdict_h1 = '**H1 evidence: SUPPORTED.** Established tiers (SP2/3, Backend) have *lower* within-season per-start K% std than Streamers, so a 3-start spike is more likely a tail-outcome window that reverts.'
        else:
            verdict_h1 = '**H1 evidence: NOT SUPPORTED.** Within-season K% variance is not systematically lower for non-streamer tiers, so a spike is no more likely to be an outlier here than at Streamer.'
    else:
        verdict_h1 = '**H1 evidence: INCONCLUSIVE.**'
    lines.append(verdict_h1)
    lines.append('')

    lines.append('### H1b — Direct forward-K% reversion after spike (the cleanest H1 test)')
    lines.append('')
    lines.append('For each `flag_skill_spike == 1` row, compute the spike-window K%, '
                 'the pre-spike season K%, and the K% over the NEXT 3 starts. '
                 'If next-3 K% reverts back toward the pre-spike baseline, H1 is confirmed.')
    lines.append('')
    lines.append('| Tier | n | pre-spike K% | spike-3 K% | next-3 K% | next-3 minus pre (pp) |')
    lines.append('|---|---|---|---|---|---|')
    for r in h1b['forward_reversion']:
        lines.append(f"| {r['tier']} | {r['n_spikes_with_forward_window']:,} | "
                     f"{r['pre_spike_k_pct_mean']*100:.1f}% | "
                     f"{r['spike3_k_pct_mean']*100:.1f}% | "
                     f"{r['fwd3_k_pct_mean']*100:.1f}% | "
                     f"{r['fwd_delta_vs_pre_pp']:+.1f} |")
    lines.append('')
    rev_by_tier = {r['tier']: r for r in h1b['forward_reversion']}
    # Interpret: at each tier, how much of the spike reverts?
    if 'SP2_SP3' in rev_by_tier and 'Backend' in rev_by_tier and 'Streamer' in rev_by_tier:
        sp23 = rev_by_tier['SP2_SP3']
        bk = rev_by_tier['Backend']
        st = rev_by_tier['Streamer']
        # spike size at each tier
        spike_size_sp23 = (sp23['spike3_k_pct_mean'] - sp23['pre_spike_k_pct_mean']) * 100
        spike_size_bk = (bk['spike3_k_pct_mean'] - bk['pre_spike_k_pct_mean']) * 100
        spike_size_st = (st['spike3_k_pct_mean'] - st['pre_spike_k_pct_mean']) * 100
        # carry-over: fwd vs pre
        carry_sp23 = sp23['fwd_delta_vs_pre_pp']
        carry_bk = bk['fwd_delta_vs_pre_pp']
        carry_st = st['fwd_delta_vs_pre_pp']
        # reversion = 1 - carry/spike_size
        rev_sp23 = 1 - (carry_sp23 / spike_size_sp23) if spike_size_sp23 != 0 else float('nan')
        rev_bk = 1 - (carry_bk / spike_size_bk) if spike_size_bk != 0 else float('nan')
        rev_st = 1 - (carry_st / spike_size_st) if spike_size_st != 0 else float('nan')
        lines.append('**Reversion fraction** (1 − carry/spike): how much of the spike has reverted in next-3?')
        lines.append('')
        lines.append('| Tier | spike size (pp) | next-3 carry vs pre (pp) | reversion fraction |')
        lines.append('|---|---|---|---|')
        lines.append(f'| SP2/3 | {spike_size_sp23:+.1f} | {carry_sp23:+.1f} | {rev_sp23*100:.0f}% reverted |')
        lines.append(f'| Backend | {spike_size_bk:+.1f} | {carry_bk:+.1f} | {rev_bk*100:.0f}% reverted |')
        lines.append(f'| Streamer | {spike_size_st:+.1f} | {carry_st:+.1f} | {rev_st*100:.0f}% reverted |')
        lines.append('')
        if rev_bk > 0.65 and rev_sp23 > 0.65 and rev_bk > rev_st:
            lines.append('**H1b verdict: STRONGLY SUPPORTED.** At Backend and SP2/3, the K% spike fully or '
                         'almost fully reverts within 3 starts, while at Streamer the spike carries forward more. '
                         'This is the direct mechanism for the anti-predictive sign.')
        elif rev_bk > rev_st and rev_sp23 > rev_st:
            lines.append('**H1b verdict: DIRECTIONALLY SUPPORTED.** Non-streamer tiers revert more than Streamer.')
        else:
            lines.append('**H1b verdict: NOT SUPPORTED.** Reversion does not clearly differ by tier.')
    lines.append('')

    # H2 — window sensitivity
    lines.append('## 2. H2 — Sample-size noise (longer windows)')
    lines.append('')
    lines.append('If the issue is just that 3 starts is too short, a 5- or 7-start spike window should restore the positive sign at non-streamer tiers.')
    lines.append('')
    for win_key, rows in h2['window_sensitivity'].items():
        win_label = {'flag_skill_spike': '3-start window',
                     'flag_skill_spike_5g': '5-start window',
                     'flag_skill_spike_7g': '7-start window'}[win_key]
        lines.append(f'### {win_label}')
        lines.append('')
        lines.append('| Tier | n(on) | n(off) | boom% on | boom% off | edge (pp) | mean FP edge |')
        lines.append('|---|---|---|---|---|---|---|')
        for r in rows:
            lines.append(f"| {r['tier']} | {r['n_on']:,} | {r['n_off']:,} | "
                         f"{r['boom_on']:.1f}% | {r['boom_off']:.1f}% | "
                         f"{r['edge_pp']:+.1f} | {r['mean_fp_edge']:+.2f} |")
        lines.append('')
    # Interpret H2
    win5 = h2['window_sensitivity']['flag_skill_spike_5g']
    win7 = h2['window_sensitivity']['flag_skill_spike_7g']
    by_5 = {r['tier']: r['edge_pp'] for r in win5}
    by_7 = {r['tier']: r['edge_pp'] for r in win7}
    sp23_5 = by_5.get('SP2_SP3', None)
    bk_5 = by_5.get('Backend', None)
    sp23_7 = by_7.get('SP2_SP3', None)
    bk_7 = by_7.get('Backend', None)
    if sp23_5 is not None and bk_5 is not None:
        if (sp23_5 > 0 and bk_5 > 0) or (sp23_7 is not None and bk_7 is not None and sp23_7 > 0 and bk_7 > 0):
            verdict_h2 = '**H2 evidence: SUPPORTED.** Longer windows flip the sign at non-streamer tiers, indicating 3 starts is too short to detect real K% change against an established baseline.'
        elif sp23_5 > -1 and bk_5 > -1:
            verdict_h2 = '**H2 evidence: PARTIALLY SUPPORTED.** Longer windows attenuate the anti-predictive edge but do not flip it positive.'
        else:
            verdict_h2 = '**H2 evidence: NOT SUPPORTED.** The anti-predictive sign persists at 5- and 7-start windows, so this is not a sample-size artifact.'
    else:
        verdict_h2 = '**H2 evidence: INCONCLUSIVE.**'
    lines.append(verdict_h2)
    lines.append('')

    # H3 — opp strength
    lines.append('## 3. H3 — Context confound (opponent strength at the spike)')
    lines.append('')
    lines.append('If the spike-3 starts were against softer opponents than the pitcher faces on average, '
                 'the K% gain was matchup-driven and will not repeat against the next opponent.')
    lines.append('')
    lines.append('`lineup_xfp` is the opponent lineup\'s expected hitter FP — higher = tougher lineup. '
                 'A negative `spike_gap` means the spike-3 opponents were softer than the season baseline.')
    lines.append('')
    lines.append('| Tier | n(spike) | spike-3 opp xfp | season opp xfp | spike gap | nospike gap (control) |')
    lines.append('|---|---|---|---|---|---|')
    for r in h3['opp_strength']:
        lines.append(f"| {r['tier']} | {r['n_spike']:,} | "
                     f"{r['spike3_opp_xfp_mean']:.3f} | "
                     f"{r['spike_season_opp_xfp_mean']:.3f} | "
                     f"{r['spike_opp_gap_lw3_vs_season']:+.4f} | "
                     f"{r['nospike_opp_gap_lw3_vs_season']:+.4f} |")
    lines.append('')
    # Interpret H3: is spike_gap systematically more negative than nospike_gap at non-streamer tiers?
    gap_by = {r['tier']: r for r in h3['opp_strength']}
    if 'Backend' in gap_by and 'SP2_SP3' in gap_by:
        delta_bk = gap_by['Backend']['spike_opp_gap_lw3_vs_season'] - gap_by['Backend']['nospike_opp_gap_lw3_vs_season']
        delta_sp23 = gap_by['SP2_SP3']['spike_opp_gap_lw3_vs_season'] - gap_by['SP2_SP3']['nospike_opp_gap_lw3_vs_season']
        lines.append(f'- Backend: spike-vs-nospike opp gap differential = {delta_bk:+.4f}')
        lines.append(f'- SP2/3:   spike-vs-nospike opp gap differential = {delta_sp23:+.4f}')
        lines.append('')
        if delta_bk < -0.01 and delta_sp23 < -0.01:
            verdict_h3 = '**H3 evidence: SUPPORTED.** Spike-3 windows at non-streamer tiers were systematically against softer opponents than non-spike windows.'
        elif abs(delta_bk) < 0.005 and abs(delta_sp23) < 0.005:
            verdict_h3 = '**H3 evidence: NOT SUPPORTED.** Spike windows were not against systematically different opposition than control.'
        else:
            verdict_h3 = '**H3 evidence: WEAK / MIXED.** Some directional pattern but not a clean confound.'
    else:
        verdict_h3 = '**H3 evidence: INCONCLUSIVE.**'
    lines.append(verdict_h3)
    lines.append('')

    # ----- SYNTHESIS -----
    lines.append('## 4. Synthesis')
    lines.append('')
    lines.append(verdict_h1)
    lines.append('')
    lines.append(verdict_h2)
    lines.append('')
    lines.append(verdict_h3)
    lines.append('')

    # Decide primary mechanism
    primary = []
    if 'NOT SUPPORTED' not in verdict_h1 and 'INCONCLUSIVE' not in verdict_h1:
        primary.append('H1 (regression to mean)')
    if 'NOT SUPPORTED' not in verdict_h2 and 'INCONCLUSIVE' not in verdict_h2:
        primary.append('H2 (sample-size noise)')
    if 'NOT SUPPORTED' not in verdict_h3 and 'INCONCLUSIVE' not in verdict_h3:
        primary.append('H3 (opponent confound)')
    if primary:
        lines.append(f'**Most consistent mechanism(s): {", ".join(primary)}.**')
    else:
        lines.append('**No single hypothesis cleanly explains the finding; further work needed.**')
    lines.append('')

    # ----- ACTIONABLE RECOMMENDATION -----
    lines.append('## 5. Actionable recommendation')
    lines.append('')
    if 'H1 (regression to mean)' in primary:
        lines.append('- **Treat `flag_skill_spike == 1` at SP2/3 or Backend tier as a SELL-HIGH / regression-warning '
                     'flag in `/triangulate` and `/sp-week-plan`** rather than a tailwind. The next-start K% reverts '
                     'and boom rate drops below the tier baseline.')
        lines.append('- For Streamer / Ace tiers, retain the current bullish interpretation.')
    if 'H2 (sample-size noise)' in primary:
        lines.append('- **Build a `skill_spike_5g` or `skill_spike_7g` variant** for non-streamer tiers in the production '
                     'engine and pre-register a `/validate-feature` run on this new flag.')
    if 'H3 (opponent confound)' in primary:
        lines.append('- **Build an `opp_xfp_corrected_k_pct_delta` feature** — residualize the K%-delta against the '
                     'spike-window opponent strength before flagging — and validate against rp3.')
    lines.append('')

    # Candidate features for future validation
    lines.append('### Candidate features for future `/validate-feature` runs')
    lines.append('')
    if 'H2 (sample-size noise)' in primary:
        lines.append('- `skill_spike_5g_nonstreamer`: 5-start K%/BB% spike flag, gated on tier != Streamer.')
        lines.append('- `skill_spike_7g_nonstreamer`: 7-start variant for the same gating.')
    if 'H1 (regression to mean)' in primary:
        lines.append('- `skill_spike_3g_sell_high`: invert the flag at SP2/3 + Backend tiers — i.e., interpret '
                     'spike=1 as a NEGATIVE indicator (regression flag) for those tiers.')
    if 'H3 (opponent confound)' in primary:
        lines.append('- `k_pct_delta_oppcorrected`: (last3 K% − season K%) − β · (last3 opp lineup_xfp − season opp lineup_xfp).')
    lines.append('')

    # ----- Caveats -----
    lines.append('## 6. Caveats')
    lines.append('')
    lines.append('- All windows still require `start_idx >= window` (strictly prior). 5g and 7g samples are smaller, '
                 'especially at the Ace tier.')
    lines.append('- `lineup_xfp` is the *modeled* opponent strength used in the per-start panel; tertile cuts in the '
                 'production engine use a month-by-month slate definition (see `build_per_start_boom_stack`).')
    lines.append('- Forward K% reversion uses the next 3 starts; if a pitcher had only 1-2 remaining starts in the '
                 'season, that spike row is dropped from H1b.')
    lines.append('')
    lines.append('## 7. Data dump')
    lines.append('')
    lines.append(f'Full numeric tables in `{OUT_JSON.name}` alongside this file.')

    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'\nReport written to {OUT_MD}')

    # JSON dump (strip non-serializable)
    payload = {
        'h1_variance_test': h1,
        'h2_window_sensitivity': h2['window_sensitivity'],
        'h1b_forward_reversion': h1b,
        'h3_opp_strength': h3,
    }
    with open(OUT_JSON, 'w') as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f'JSON data written to {OUT_JSON}')


if __name__ == '__main__':
    main()
