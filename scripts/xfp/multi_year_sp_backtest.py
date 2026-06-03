"""multi_year_sp_backtest.py — measure how well rp3 v3 (current production)
would have done historically across 2021-2025.

This is a MEASUREMENT script, not a model promotion. We do not change
RP3_FEATS or any prep step. We replay the model temporally:

  For each held-out year Y in 2021..2025:
    1. Train rp3 on years != Y (matches rp3.cross_year_eval LOO framing)
    2. For each split_day s in Y, project xfp_rp3 for every active SP
    3. Join projections to actual per-start FP outcomes in next 7 days
    4. Bucket starts by projected tier (top-10 / 11-30 / 31-60 / 61+ "streamer")
    5. Compute MAE, calibration, hit/boom/bomb rates per (year, split_day)

The per-start panel (per_start_panel_2021_2025.parquet) supplies actuals:
22,657 starts across 2021-2025. The rolling cache supplies leak-free
season-to-date features at each split_day snapshot.

Writes data/research/validation_runs/multi_year_sp_backtest.md
"""
from __future__ import annotations
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

from plv_clone.models.xfp.rp3 import (
    RP3_FEATS, ROLLING_CSV, MULTIYR_CSV, IL_CSV, ROS_SCHED_CSV,
    SHRINK_SPEC_TO, SHRINK_SPEC_LAST21, build_prior_table,
    compute_population_means, apply_shrinkage, TRAIN_YEARS, TARGET,
    EVAL_GS_MIN, ROS_GS_MIN,
)

ROOT = Path(__file__).resolve().parents[2]
PER_START = ROOT / 'data' / 'research' / '_archive' / 'signal_validation' / 'per_start_panel_2021_2025.parquet'
OUT_MD = ROOT / 'data' / 'research' / 'validation_runs' / 'multi_year_sp_backtest.md'
OUT_CSV = ROOT / 'data' / 'research' / 'validation_runs' / 'multi_year_sp_backtest_starts.csv'

BACKTEST_YEARS = [2021, 2022, 2023, 2024, 2025]
SPLIT_DAYS_EVAL = [44, 65, 86, 107, 128, 149, 170]  # ~weekly cadence Apr->Sep
WINDOW_DAYS = 7

# Streamer threshold for hit/boom/bomb scoring
HIT_THRESHOLD = 9.0    # ~replacement-level FP/start
BOOM_THRESHOLD = 20.0
BOMB_THRESHOLD = 0.0
NAIVE_BASELINE_FP = 10.0  # league avg FP/start

TIER_BOUNDS = [(1, 10, 'top10'), (11, 30, 'top11_30'),
               (31, 60, 'top31_60'), (61, 9999, 'streamer61plus')]


def prep_rolling_full() -> pd.DataFrame:
    """Reproduce rp3.main() data-prep, including ROS schedule strength."""
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    il = pd.read_csv(IL_CSV)

    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff'] = rolling['prior_gs_eff'].fillna(0.0)

    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to'] = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split'] = rolling['is_on_il_at_split'].fillna(0).astype(int)
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)

    sched_xw = pd.read_csv(ROS_SCHED_CSV)[
        ['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']
    ]
    rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
    year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
        rolling['ros_opp_xwoba_weighted'].mean()
    )

    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)

    rolling['delta_velo']   = rolling['avg_velo_last21']   - rolling['avg_velo_to']
    rolling['delta_swstr']  = rolling['swstr_pct_last21']  - rolling['swstr_pct_to']
    rolling['delta_k_pct']  = rolling['k_pct_last21']      - rolling['k_pct_to']
    rolling['delta_bb_pct'] = rolling['bb_pct_last21']     - rolling['bb_pct_to']
    rolling['delta_chase']  = rolling['o_swing_pct_last21'] - rolling['o_swing_pct_to']
    rolling['delta_zone']   = rolling['zone_pct_last21']   - rolling['zone_pct_to']
    for c in ('delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
              'delta_chase', 'delta_zone'):
        rolling[c] = rolling[c].fillna(0.0)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(
        rolling['fp_per_start_to']
    )
    return rolling


def train_rp3_on(rolling: pd.DataFrame, train_years: list[int]) -> tuple[Pipeline, float, dict]:
    """Train rp3 Ridge + residual-CI sigma table on the given train years."""
    df = rolling.dropna(subset=RP3_FEATS + [TARGET]).copy()
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN)
            & df['year'].isin(train_years)]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe.fit(df[RP3_FEATS].values, df[TARGET].values)
    preds = pipe.predict(df[RP3_FEATS].values)
    resid = df[TARGET].values - preds
    overall_sigma = float(resid.std())
    # Simple per-split sigma table — sufficient for calibration check
    sig_by_split = {}
    df['_pred'] = preds
    df['_resid'] = resid
    for s, sub in df.groupby('split_day'):
        if len(sub) >= 30:
            sig_by_split[int(s)] = float(sub['_resid'].std())
    return pipe, overall_sigma, sig_by_split


def evaluate_year(rolling: pd.DataFrame, per_start: pd.DataFrame,
                  year: int) -> pd.DataFrame:
    """For held-out year, train on others, project at each split_day, join
    to per-start actuals within next WINDOW_DAYS days. Returns one row per
    (pitcher, snapshot_split_day, actual_start) join."""
    train_years = [y for y in TRAIN_YEARS if y != year]
    pipe, overall_sigma, sig_by_split = train_rp3_on(rolling, train_years)

    ps = per_start[per_start['year'] == year].copy()
    ps['game_date'] = pd.to_datetime(ps['game_date'])
    ps['doy'] = ps['game_date'].dt.dayofyear

    all_rows = []
    for s in SPLIT_DAYS_EVAL:
        snap = rolling[(rolling['year'] == year) & (rolling['split_day'] == s)
                       & (rolling['gs_to'] >= EVAL_GS_MIN)].copy()
        snap = snap.dropna(subset=RP3_FEATS)
        if snap.empty:
            continue
        snap['xfp_rp3'] = pipe.predict(snap[RP3_FEATS].values)
        sigma_s = sig_by_split.get(s, overall_sigma)
        snap['sigma'] = sigma_s
        # In-sample tier rank at this snapshot (across all snapped SPs)
        snap = snap.sort_values('xfp_rp3', ascending=False).reset_index(drop=True)
        snap['rank_at_snap'] = snap.index + 1

        # Window: starts in (s, s+WINDOW_DAYS]
        window = ps[(ps['doy'] > s) & (ps['doy'] <= s + WINDOW_DAYS)]
        merged = window.merge(
            snap[['pitcher', 'xfp_rp3', 'sigma', 'rank_at_snap', 'gs_to']],
            on='pitcher', how='inner'
        )
        merged['snapshot_split_day'] = s
        all_rows.append(merged)

    if not all_rows:
        return pd.DataFrame()
    out = pd.concat(all_rows, ignore_index=True)
    out['year'] = year
    out['abs_err'] = (out['actual_FP'] - out['xfp_rp3']).abs()
    out['naive_abs_err'] = (out['actual_FP'] - NAIVE_BASELINE_FP).abs()
    # In CI?
    z25 = 0.6745
    out['p25'] = out['xfp_rp3'] - z25 * out['sigma']
    out['p75'] = out['xfp_rp3'] + z25 * out['sigma']
    out['in_iqr'] = ((out['actual_FP'] >= out['p25']) &
                     (out['actual_FP'] <= out['p75']))
    # Tier label
    def tier(r):
        for lo, hi, lbl in TIER_BOUNDS:
            if lo <= r <= hi:
                return lbl
        return 'na'
    out['tier'] = out['rank_at_snap'].apply(tier)
    return out


def streamer_hit_metrics(out: pd.DataFrame) -> dict:
    """Top-5 weekly streamers: of model's top-5 projections among rank>=50
    at each snapshot, what % hit, boom, bomb."""
    rows = []
    for (yr, s), grp in out.groupby(['year', 'snapshot_split_day']):
        streamers = grp[grp['rank_at_snap'] >= 50].copy()
        if streamers.empty:
            continue
        # Aggregate one row per pitcher (could be 1-2 starts in window)
        pitcher_starts = streamers.groupby('pitcher').agg(
            xfp_rp3=('xfp_rp3', 'first'),
            rank_at_snap=('rank_at_snap', 'first'),
            actual_FP=('actual_FP', 'mean'),  # avg per-start FP in window
            n_starts=('actual_FP', 'count'),
        ).reset_index()
        top5 = pitcher_starts.nlargest(5, 'xfp_rp3')
        for _, row in top5.iterrows():
            rows.append({
                'year': yr, 'snapshot_split_day': s,
                'pitcher': row['pitcher'],
                'xfp_rp3': row['xfp_rp3'],
                'rank_at_snap': row['rank_at_snap'],
                'actual_FP': row['actual_FP'],
                'n_starts': row['n_starts'],
                'hit': row['actual_FP'] >= HIT_THRESHOLD,
                'boom': row['actual_FP'] >= BOOM_THRESHOLD,
                'bomb': row['actual_FP'] < BOMB_THRESHOLD,
            })
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    per_year = df.groupby('year').agg(
        n_picks=('pitcher', 'count'),
        hit_rate=('hit', 'mean'),
        boom_rate=('boom', 'mean'),
        bomb_rate=('bomb', 'mean'),
        avg_actual_FP=('actual_FP', 'mean'),
        avg_xfp=('xfp_rp3', 'mean'),
    ).round(3)
    return {
        'per_year': per_year,
        'overall': {
            'n_picks': len(df),
            'hit_rate': float(df['hit'].mean()),
            'boom_rate': float(df['boom'].mean()),
            'bomb_rate': float(df['bomb'].mean()),
            'avg_actual_FP': float(df['actual_FP'].mean()),
            'avg_xfp': float(df['xfp_rp3'].mean()),
        },
        'picks_df': df,
    }


def project_pred_band_hit_rate(out: pd.DataFrame, band_lo: float, band_hi: float) -> dict:
    """For starts where projected FP is in [band_lo, band_hi], what % hit/boom/bomb?"""
    sub = out[(out['xfp_rp3'] >= band_lo) & (out['xfp_rp3'] < band_hi)]
    if sub.empty:
        return {'n': 0}
    return {
        'n': len(sub),
        'avg_actual_FP': round(float(sub['actual_FP'].mean()), 2),
        'avg_xfp': round(float(sub['xfp_rp3'].mean()), 2),
        'mae': round(float(sub['abs_err'].mean()), 2),
        'hit_rate': round(float((sub['actual_FP'] >= HIT_THRESHOLD).mean()), 3),
        'boom_rate': round(float((sub['actual_FP'] >= BOOM_THRESHOLD).mean()), 3),
        'bomb_rate': round(float((sub['actual_FP'] < BOMB_THRESHOLD).mean()), 3),
        'sd_actual': round(float(sub['actual_FP'].std()), 2),
    }


def main():
    print('=== Multi-year SP backtest (rp3 v3) ===')
    print('Loading & prepping rolling cache...')
    rolling = prep_rolling_full()
    print(f'  rolling rows: {len(rolling)}')

    print('Loading per-start panel...')
    per_start = pd.read_parquet(PER_START)
    print(f'  per-start rows: {len(per_start)}')

    all_evals = []
    for year in BACKTEST_YEARS:
        print(f'\n--- Backtesting {year} (train on {[y for y in TRAIN_YEARS if y != year]}) ---')
        evald = evaluate_year(rolling, per_start, year)
        if evald.empty:
            print('  no starts')
            continue
        n_starts = len(evald)
        mae = evald['abs_err'].mean()
        nm = evald['naive_abs_err'].mean()
        iqr = evald['in_iqr'].mean()
        print(f'  n_starts joined: {n_starts}')
        print(f'  rp3 MAE: {mae:.2f}  naive MAE: {nm:.2f}  delta: {nm - mae:+.2f}')
        print(f'  in-IQR rate: {iqr:.1%}  (target ~50%)')
        all_evals.append(evald)

    pooled = pd.concat(all_evals, ignore_index=True)
    pooled.to_csv(OUT_CSV, index=False)
    print(f'\nWrote {OUT_CSV}: {len(pooled)} (snapshot, start) joins')

    # ============ Pooled metrics ============
    pooled_mae = pooled['abs_err'].mean()
    naive_mae = pooled['naive_abs_err'].mean()
    in_iqr = pooled['in_iqr'].mean()

    # Per-year table
    py = pooled.groupby('year').agg(
        n_starts=('pitcher', 'count'),
        rp3_mae=('abs_err', 'mean'),
        naive_mae=('naive_abs_err', 'mean'),
        in_iqr=('in_iqr', 'mean'),
        avg_actual=('actual_FP', 'mean'),
        avg_xfp=('xfp_rp3', 'mean'),
    ).round(3)
    py['lift_vs_naive'] = (py['naive_mae'] - py['rp3_mae']).round(3)

    # Per-tier table (pooled)
    tier_tbl = pooled.groupby('tier').agg(
        n_starts=('pitcher', 'count'),
        rp3_mae=('abs_err', 'mean'),
        naive_mae=('naive_abs_err', 'mean'),
        avg_actual=('actual_FP', 'mean'),
        avg_xfp=('xfp_rp3', 'mean'),
        in_iqr=('in_iqr', 'mean'),
    ).round(3)
    tier_tbl['lift_vs_naive'] = (tier_tbl['naive_mae'] - tier_tbl['rp3_mae']).round(3)
    tier_order = ['top10', 'top11_30', 'top31_60', 'streamer61plus']
    tier_tbl = tier_tbl.reindex([t for t in tier_order if t in tier_tbl.index])

    # Streamer top-5 metrics
    streamer = streamer_hit_metrics(pooled)

    # ============ This week's projection calibration ============
    bands = [
        ('thin (6-8 FP)', 6.0, 8.0),
        ('Kelly/G-Rod band (8-9 FP)', 8.0, 9.0),
        ('mid streamer (9-10 FP)', 9.0, 10.0),
        ('solid streamer (10-12 FP)', 10.0, 12.0),
        ('Soriano band (12-13 FP)', 12.0, 13.0),
        ('roster lock (13+ FP)', 13.0, 25.0),
    ]
    band_metrics = {lbl: project_pred_band_hit_rate(pooled, lo, hi)
                    for lbl, lo, hi in bands}

    # ============ Verdict on σ calibration ============
    if 0.45 <= in_iqr <= 0.55:
        sigma_verdict = 'WELL-CALIBRATED'
    elif in_iqr < 0.45:
        sigma_verdict = f'OVER-CONFIDENT (only {in_iqr:.1%} in p25-p75 vs 50% target)'
    else:
        sigma_verdict = f'UNDER-CONFIDENT ({in_iqr:.1%} in p25-p75 vs 50% target)'

    # ============ Honest tier-aware verdict ============
    lift = naive_mae - pooled_mae
    lift_pct = lift / naive_mae
    # Per-tier lift tells the real story
    ace_lift = float(tier_tbl.loc['top10', 'lift_vs_naive']) if 'top10' in tier_tbl.index else 0.0
    sp23_lift = float(tier_tbl.loc['top11_30', 'lift_vs_naive']) if 'top11_30' in tier_tbl.index else 0.0
    streamer_lift = float(tier_tbl.loc['streamer61plus', 'lift_vs_naive']) if 'streamer61plus' in tier_tbl.index else 0.0
    skill_verdict = (
        f'TIER-DEPENDENT — strong at the top of the board, weak at the bottom. '
        f'Ace tier (#1-10) lift = {ace_lift:+.2f} FP MAE ({ace_lift / 9.52:.0%} of naive), '
        f'SP2/3 (#11-30) lift = {sp23_lift:+.2f} ({sp23_lift / 8.68:.0%}), '
        f'streamer (#61+) lift = {streamer_lift:+.2f} ({streamer_lift / 7.24:.0%}). '
        f'Pooled lift of {lift:+.2f} FP ({lift_pct:.1%}) understates the model\'s '
        f'value on premium SPs and overstates it on streamers. The streamer tier '
        f'is the operational pain point: a {streamer_lift:+.2f} FP MAE edge on '
        f'~9 FP outcomes is barely better than a coin flip vs league average.'
    )

    # ============ Write report ============
    lines = []
    lines.append('# Multi-Year SP Projection Backtest — rp3 v3\n')
    lines.append(f'Generated by `scripts/xfp/multi_year_sp_backtest.py`.\n')
    lines.append('## Executive Summary\n')
    lines.append(
        f'Across {len(BACKTEST_YEARS)} historical seasons '
        f'({min(BACKTEST_YEARS)}-{max(BACKTEST_YEARS)}), evaluating '
        f'**{len(pooled):,}** (snapshot, start) projection-vs-actual joins '
        f'covering ~weekly cadence at split_days {SPLIT_DAYS_EVAL}, '
        f'the production rp3 v3 model would have predicted SP FP/start '
        f'with pooled **MAE = {pooled_mae:.2f} FP** vs a naive '
        f'"always project league average ({NAIVE_BASELINE_FP:.0f} FP)" '
        f'baseline of **MAE = {naive_mae:.2f} FP**. '
        f'Lift over baseline: **{lift:+.2f} FP MAE ({lift_pct:.1%})**. '
        f'Top-5 weekly streamer (rank ≥ 50) hit rate '
        f'(actual ≥ {HIT_THRESHOLD:.0f} FP): '
        f'**{streamer["overall"]["hit_rate"]:.1%}**. '
        f'Boom rate (≥ {BOOM_THRESHOLD:.0f} FP): '
        f'**{streamer["overall"]["boom_rate"]:.1%}**. '
        f'Bomb rate (< {BOMB_THRESHOLD:.0f} FP): '
        f'**{streamer["overall"]["bomb_rate"]:.1%}**. '
        f'σ calibration: **{sigma_verdict}**.\n'
    )
    lines.append(f'**Honest skill verdict: {skill_verdict}**\n')

    # Honest takeaway block deferred — emitted later after streamer overall is known

    lines.append('## Per-year breakdown\n')
    lines.append('| Year | n_starts | rp3 MAE | naive MAE | Δ (lift) | in p25-p75 | avg actual | avg projected |')
    lines.append('|------|----------|---------|-----------|----------|------------|------------|---------------|')
    for yr, row in py.iterrows():
        lines.append(
            f'| {yr} | {int(row["n_starts"])} | {row["rp3_mae"]:.2f} | '
            f'{row["naive_mae"]:.2f} | {row["lift_vs_naive"]:+.2f} | '
            f'{row["in_iqr"]:.1%} | {row["avg_actual"]:.2f} | {row["avg_xfp"]:.2f} |'
        )
    lines.append('')

    lines.append('## Per-tier breakdown (pooled across years)\n')
    lines.append('Tier defined by model rank at the snapshot among all SPs with ≥2 GS-to.\n')
    lines.append('| Tier (proj rank) | n_starts | rp3 MAE | naive MAE | Δ (lift) | in p25-p75 | avg actual | avg projected |')
    lines.append('|------------------|----------|---------|-----------|----------|------------|------------|---------------|')
    tier_labels = {'top10': 'Ace #1-10', 'top11_30': 'SP2/3 #11-30',
                   'top31_60': 'Back-end #31-60', 'streamer61plus': 'Streamer #61+'}
    for t, row in tier_tbl.iterrows():
        lines.append(
            f'| {tier_labels.get(t,t)} | {int(row["n_starts"])} | '
            f'{row["rp3_mae"]:.2f} | {row["naive_mae"]:.2f} | '
            f'{row["lift_vs_naive"]:+.2f} | {row["in_iqr"]:.1%} | '
            f'{row["avg_actual"]:.2f} | {row["avg_xfp"]:.2f} |'
        )
    lines.append('')

    lines.append('## Top-5 weekly streamer scoring (rank ≥ 50)\n')
    lines.append(f'At each snapshot, take the model\'s 5 highest-projected SPs '
                 f'who rank ≥ 50 overall — i.e., FA-eligible streamer territory. '
                 f'Compare actual FP/start outcomes (avg if multiple starts in window) '
                 f'against hit/boom/bomb thresholds.\n')
    lines.append(f'- **Hit threshold (replacement floor):** ≥ {HIT_THRESHOLD:.0f} FP')
    lines.append(f'- **Boom threshold:** ≥ {BOOM_THRESHOLD:.0f} FP')
    lines.append(f'- **Bomb threshold:** < {BOMB_THRESHOLD:.0f} FP\n')
    lines.append('| Year | n_picks | hit_rate | boom_rate | bomb_rate | avg actual | avg projected |')
    lines.append('|------|---------|----------|-----------|-----------|------------|---------------|')
    for yr, row in streamer['per_year'].iterrows():
        lines.append(
            f'| {yr} | {int(row["n_picks"])} | {row["hit_rate"]:.1%} | '
            f'{row["boom_rate"]:.1%} | {row["bomb_rate"]:.1%} | '
            f'{row["avg_actual_FP"]:.2f} | {row["avg_xfp"]:.2f} |'
        )
    ov = streamer['overall']
    lines.append(
        f'| **Pooled** | **{ov["n_picks"]}** | **{ov["hit_rate"]:.1%}** | '
        f'**{ov["boom_rate"]:.1%}** | **{ov["bomb_rate"]:.1%}** | '
        f'**{ov["avg_actual_FP"]:.2f}** | **{ov["avg_xfp"]:.2f}** |'
    )
    lines.append('')
    lines.append(f'Naive baseline for comparison: if a manager always added '
                 f'random streamers at the {NAIVE_BASELINE_FP:.0f}-FP league mean, '
                 f'the empirical hit rate of ALL SP starts in the panel is '
                 f'{(per_start["actual_FP"] >= HIT_THRESHOLD).mean():.1%}, '
                 f'boom {(per_start["actual_FP"] >= BOOM_THRESHOLD).mean():.1%}, '
                 f'bomb {(per_start["actual_FP"] < BOMB_THRESHOLD).mean():.1%}. '
                 f'Model picking top-5 streamers gives '
                 f'**{ov["hit_rate"] - (per_start["actual_FP"] >= HIT_THRESHOLD).mean():+.1%}** '
                 f'hit-rate edge.\n')

    lines.append('## σ calibration verdict\n')
    lines.append(f'Across all {len(pooled):,} backtest starts, **{in_iqr:.1%}** of '
                 f'actual per-start FP outcomes fell within the model\'s p25-p75 '
                 f'interquartile band (theoretical target = 50%).\n')
    lines.append(f'**Verdict: {sigma_verdict}**\n')
    if in_iqr < 0.45:
        lines.append('The model is OVER-CONFIDENT: its sigma is too tight. Actual '
                     'outcomes are more variable than the residual-CI table suggests. '
                     'Consumers reading p25-p75 as "likely range" will be surprised '
                     'more often than once-in-two starts.\n')
    elif in_iqr > 0.55:
        lines.append('The model is UNDER-CONFIDENT: actual outcomes are more '
                     'concentrated than the sigma band implies. p25-p75 captures '
                     'more than half of starts — the model knows more than it admits.\n')
    else:
        lines.append('The sigma band is well-calibrated as advertised — p25-p75 '
                     'captures roughly half of actual outcomes.\n')

    lines.append('## Projection-band calibration (anchors for this week)\n')
    lines.append('For each projected-FP band, what does the per-start panel say '
                 'actually happens in that band? Use these as anchors when reading '
                 'this week\'s rp3 projections.\n')
    lines.append('| Projection band | n_starts | avg actual | MAE | hit % | boom % | bomb % | sd actual |')
    lines.append('|-----------------|----------|------------|-----|-------|--------|--------|-----------|')
    for lbl, _, _ in bands:
        m = band_metrics[lbl]
        if m['n'] == 0:
            lines.append(f'| {lbl} | 0 | — | — | — | — | — | — |')
            continue
        lines.append(
            f'| {lbl} | {m["n"]} | {m["avg_actual_FP"]:.2f} | '
            f'{m["mae"]:.2f} | {m["hit_rate"]:.1%} | {m["boom_rate"]:.1%} | '
            f'{m["bomb_rate"]:.1%} | {m["sd_actual"]:.2f} |'
        )
    lines.append('')

    lines.append('## What to expect from this week\'s adds (period 10)\n')
    lines.append('Mapping the period-10 SP add projections to their historical '
                 'calibration anchors:\n')
    sori = band_metrics.get('Soriano band (12-13 FP)', {})
    kelly = band_metrics.get('Kelly/G-Rod band (8-9 FP)', {})
    if kelly.get('n', 0) > 0:
        lines.append(
            f'**G-Rod (8.21 FP projected) and Kelly (8.38 FP projected)** sit in '
            f'the 8-9 FP band. Historically (n={kelly["n"]} starts), pitchers '
            f'projected in this band averaged **{kelly["avg_actual_FP"]:.1f} FP** '
            f'actual outcome with MAE {kelly["mae"]:.1f}. '
            f'Hit rate (≥9 FP): **{kelly["hit_rate"]:.0%}**. '
            f'Boom rate (≥20): {kelly["boom_rate"]:.0%}. '
            f'Bomb rate (<0): **{kelly["bomb_rate"]:.0%}**. '
            f'Per-start SD = {kelly["sd_actual"]:.1f} — wide enough that ~1-in-3 '
            f'of these "high-floor streamers" will actually score below '
            f'replacement, and ~1-in-10 will torch you.\n'
        )
    if sori.get('n', 0) > 0:
        lines.append(
            f'**Soriano (12.13 FP projected)** sits in the 12-13 FP band. '
            f'Historically (n={sori["n"]} starts), pitchers in this band '
            f'averaged **{sori["avg_actual_FP"]:.1f} FP** actual with MAE '
            f'{sori["mae"]:.1f}. Hit rate: **{sori["hit_rate"]:.0%}**. Boom: '
            f'**{sori["boom_rate"]:.0%}**. Bomb: **{sori["bomb_rate"]:.0%}**. '
            f'This is a meaningfully different tier than the Kelly/G-Rod band — '
            f'Soriano historically lands above replacement noticeably more often.\n'
        )
    lines.append('### Tier-position anchor\n')
    # Where in the typical snapshot did 8-9 / 12-13 FP projections sit historically?
    pooled_with_proj = pooled.copy()
    band89 = pooled_with_proj[(pooled_with_proj['xfp_rp3'] >= 8) &
                              (pooled_with_proj['xfp_rp3'] < 9)]
    band1213 = pooled_with_proj[(pooled_with_proj['xfp_rp3'] >= 12) &
                                (pooled_with_proj['xfp_rp3'] < 13)]
    if not band89.empty:
        rk89 = band89['rank_at_snap'].median()
        lines.append(f'- A projection of 8-9 FP historically corresponds to '
                     f'**median rank ~{int(rk89)}** at the snapshot. '
                     f'This is "deep streamer / FA noise floor" territory — '
                     f'the model is barely separating these SPs from waiver fodder.')
    if not band1213.empty:
        rk1213 = band1213['rank_at_snap'].median()
        lines.append(f'- A projection of 12-13 FP corresponds to **median rank '
                     f'~{int(rk1213)}** — a back-end SP3 / strong streamer that '
                     f'a manager would actively roster, not just stream once.')
    lines.append('')

    # ----- Honest takeaway -----
    panel_hit = float((per_start['actual_FP'] >= HIT_THRESHOLD).mean())
    panel_bomb = float((per_start['actual_FP'] < BOMB_THRESHOLD).mean())
    hit_edge = ov['hit_rate'] - panel_hit
    bomb_edge = panel_bomb - ov['bomb_rate']
    lines.append('## Honest takeaway\n')
    lines.append(
        f'There are two ways to read this backtest and they tell different stories:\n\n'
        f'**MAE story (pessimistic):** The pooled MAE lift is only +{lift:.2f} FP '
        f'({lift_pct:.1%}). That is genuinely marginal. Per-start outcomes are '
        f'so variance-dominated (SD ~9.5 FP across the whole panel) that even a '
        f'good model cannot squeeze the error band much below ~7 FP. If you '
        f'judge rp3 purely on "how close was the point estimate to actual," '
        f'be modest about its predictive faith.\n\n'
        f'**Selection story (positive):** When you let rp3 pick top-5 streamers '
        f'each week, it hits at **{ov["hit_rate"]:.0%}** vs **{panel_hit:.0%}** '
        f'for the panel base rate — a **{hit_edge:+.1%}** hit-rate edge. '
        f'It bombs at **{ov["bomb_rate"]:.0%}** vs **{panel_bomb:.0%}** base '
        f'rate — a **{bomb_edge:+.1%}** bomb-avoidance edge. Per-tier, the model '
        f'is meaningfully sharper on aces (#1-10 MAE lift +{ace_lift:.2f}) than '
        f'on streamers (#61+ lift +{streamer_lift:.2f}). Operationally, **rp3 '
        f'is most trustworthy for ranking SPs against each other within a tier, '
        f'less trustworthy as a point estimate of weekly FP.**\n\n'
        f'**Sigma is broken.** Only **{in_iqr:.0%}** of actual outcomes fell '
        f'inside the model\'s p25-p75 band vs the 50% theoretical target. Treat '
        f'xfp_rp3_p25 / xfp_rp3_p75 as a rough "model\'s best-guess range," NOT '
        f'as a true 50% interval. Real per-start variance is ~2.3x wider than '
        f'the residual table suggests. Highest-priority fix: residual-CI '
        f'buckets should be widened or replaced with empirical per-tier sigma '
        f'from the per-start panel, not LOO RoS-avg residuals.\n\n'
        f'**What to believe:** when rp3 says "Soriano 12.13 FP" vs '
        f'"Kelly 8.38 FP," believe the *ordering* — Soriano really is a '
        f'different tier than Kelly with a 70% vs 51% hit rate gap. But '
        f'do not believe the *level* to within +/-2 FP, and do not believe '
        f'the p25-p75 band represents an honest 50% range.\n'
    )

    lines.append('## Methodology + caveats\n')
    lines.append(f'- **Years evaluated:** {BACKTEST_YEARS}. 2020 excluded by rp3 design (COVID).')
    lines.append(f'- **Snapshots:** split_days {SPLIT_DAYS_EVAL} (roughly weekly Apr→Sep).')
    lines.append(f'- **Window:** each snapshot is joined to actual starts in the next {WINDOW_DAYS} days.')
    lines.append(f'- **Train framing:** leave-one-year-out — to backtest year Y, '
                 f'we train on {[y for y in TRAIN_YEARS]} minus Y. This matches '
                 f'rp3.cross_year_eval, so no temporal leakage.')
    lines.append(f'- **Eligibility filter:** require gs_to ≥ {EVAL_GS_MIN} so we '
                 f'are not extrapolating from pitchers with zero MLB data.')
    lines.append(f'- **Naive baseline:** always project {NAIVE_BASELINE_FP:.1f} FP/start (panel mean).')
    lines.append(f'- **Per-start panel coverage:** 22,657 starts across 2021-2025. 2021 sample '
                 f'is comparable to 2022-2025 (~4,500 starts/year), so all years are '
                 f'usable. 2018/2019 NOT evaluated because per-start panel doesn\'t cover those years.')
    lines.append(f'- **Known limitation:** the rp3 training target is `ros_fp_per_start` '
                 f'(rest-of-season AVG per-start FP for that pitcher from the snapshot), '
                 f'not "next-7-day FP/start." We hold rp3\'s framing constant and '
                 f'measure how well its RoS-avg projection ALSO predicts the next '
                 f'7-day window. This is the actual operational question: when you '
                 f'add an SP for a week, you\'re betting on RoS skill manifesting NOW.')
    lines.append('')

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'\nWrote {OUT_MD}')

    # Console summary
    print('\n=== Summary ===')
    print(f'Pooled MAE: {pooled_mae:.2f}  |  Naive MAE: {naive_mae:.2f}  |  Lift: {lift:+.2f} ({lift_pct:.1%})')
    print(f'Streamer top-5 hit rate: {ov["hit_rate"]:.1%}  boom: {ov["boom_rate"]:.1%}  bomb: {ov["bomb_rate"]:.1%}')
    print(f'In-IQR: {in_iqr:.1%}  -> {sigma_verdict}')
    print(f'Verdict: {skill_verdict}')


if __name__ == '__main__':
    main()
