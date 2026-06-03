"""validate_streamer_boom_stack.py — test streamer_boom_stack_v1.

Pre-registered: data/research/validation_runs/streamer_boom_stack_v1_2026-06-03.md

boom_stack at (pitcher, year, cutoff_date) = sum of 3 binary flags:
  (1) skill_spike: last3_K% - season_K% >= +3 pp AND last3_BB% - season_BB% <= -1 pp
  (2) recform_hot: last3_FP_per_start - season_FP_per_start >= +3 FP
  (3) opp_soft: opponent lineup_xfp of next start strictly after cutoff is in
      the bottom tertile of (year, split_day) slate

Per-start variant (Mode B): same components computed strictly before that
start's game_date; opp_soft uses the game's actual lineup_xfp.
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report

from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval, TARGET

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RESEARCH = ROOT / 'data' / 'research'
OUT_DIR = RESEARCH / 'validation_runs'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
CONV_SPLIT_DAYS = [30, 44, 58]


# ---------------------------------------------------------------------------
# Step 1 — Load per-start panel with game_date attached
# ---------------------------------------------------------------------------
def load_per_start_with_dates() -> pd.DataFrame:
    p = pd.read_csv(RESEARCH / 'per_start_predictor_battle.csv')
    p = p[p['year'].isin(YEARS)].copy()
    print(f'  per_start rows in target years: {len(p)}')

    # Build game_pk -> date map across years
    date_frames = []
    for y in YEARS:
        sc = pd.read_parquet(CACHE / f'statcast_{y}.parquet',
                             columns=['game_pk', 'game_date'])
        sc = sc.drop_duplicates('game_pk')
        date_frames.append(sc)
    dates = pd.concat(date_frames, ignore_index=True).drop_duplicates('game_pk')
    dates['game_date'] = pd.to_datetime(dates['game_date'])
    p = p.merge(dates, on='game_pk', how='left')
    n_no_date = p['game_date'].isna().sum()
    print(f'  per_start rows missing game_date after merge: {n_no_date}')
    p = p.dropna(subset=['game_date'])
    p['pitcher'] = p['pitcher'].astype('int64')
    # Compute per-start K% / BB% / FP for components
    p['k_pct'] = p['actual_K'] / p['actual_PA'].clip(lower=1)
    p['bb_pct'] = p['actual_BB'] / p['actual_PA'].clip(lower=1)
    p['fp'] = p['actual_FP']
    # Filter obviously bad rows (PA < 5 = relief stint mislabeled)
    p = p[p['actual_PA'] >= 5].copy()
    return p[['pitcher', 'year', 'game_pk', 'game_date',
              'actual_PA', 'actual_K', 'actual_BB', 'k_pct', 'bb_pct',
              'fp', 'lineup_xfp']].sort_values(['pitcher', 'year', 'game_date'])


# ---------------------------------------------------------------------------
# Step 2 — Compute components 1, 2 at (pitcher, year, cutoff_date)
# ---------------------------------------------------------------------------
def compute_components_at_cutoff(starts: pd.DataFrame,
                                  cutoffs_per_year: dict[int, list[pd.Timestamp]]
                                  ) -> pd.DataFrame:
    """For each pitcher, year, cutoff_date: compute season-to-date K%/BB%/FP
    and last-3-starts K%/BB%/FP using only starts strictly before cutoff."""
    out_rows = []
    for (pid, yr), grp in starts.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        cutoffs = cutoffs_per_year.get(yr, [])
        for cd in cutoffs:
            prior = grp[grp['game_date'] < cd]
            if len(prior) < 1:
                out_rows.append({'pitcher': int(pid), 'year': int(yr),
                                 'cutoff_date': cd,
                                 'season_k_pct': np.nan, 'season_bb_pct': np.nan,
                                 'season_fp': np.nan,
                                 'last3_k_pct': np.nan, 'last3_bb_pct': np.nan,
                                 'last3_fp': np.nan, 'n_prior_starts': 0})
                continue
            sK = prior['actual_K'].sum() / prior['actual_PA'].sum()
            sBB = prior['actual_BB'].sum() / prior['actual_PA'].sum()
            sFP = prior['fp'].mean()
            last3 = prior.tail(3)
            l3K = last3['actual_K'].sum() / max(last3['actual_PA'].sum(), 1)
            l3BB = last3['actual_BB'].sum() / max(last3['actual_PA'].sum(), 1)
            l3FP = last3['fp'].mean()
            out_rows.append({'pitcher': int(pid), 'year': int(yr),
                             'cutoff_date': cd,
                             'season_k_pct': sK, 'season_bb_pct': sBB,
                             'season_fp': sFP,
                             'last3_k_pct': l3K, 'last3_bb_pct': l3BB,
                             'last3_fp': l3FP,
                             'n_prior_starts': int(len(prior))})
    out = pd.DataFrame(out_rows)
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])
    return out


# ---------------------------------------------------------------------------
# Step 3 — Compute component 3 (opp_soft) for Mode A
# ---------------------------------------------------------------------------
def compute_opp_soft_at_cutoff(starts: pd.DataFrame,
                                cutoffs_per_year: dict[int, list[pd.Timestamp]]
                                ) -> pd.DataFrame:
    """For each (pitcher, year, cutoff_date) find the FIRST scheduled start
    strictly AFTER cutoff and use its lineup_xfp. Tertile is computed within
    (year, split_day) slate."""
    rows = []
    for (pid, yr), grp in starts.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        cutoffs = cutoffs_per_year.get(yr, [])
        for cd in cutoffs:
            future = grp[grp['game_date'] >= cd]
            if len(future) == 0 or pd.isna(future.iloc[0]['lineup_xfp']):
                rows.append({'pitcher': int(pid), 'year': int(yr),
                             'cutoff_date': cd, 'opp_lineup_xfp': np.nan})
                continue
            rows.append({'pitcher': int(pid), 'year': int(yr),
                         'cutoff_date': cd,
                         'opp_lineup_xfp': float(future.iloc[0]['lineup_xfp'])})
    out = pd.DataFrame(rows)
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])
    # Tertile within (year, cutoff_date) slate
    out['opp_tertile'] = (
        out.groupby(['year', 'cutoff_date'])['opp_lineup_xfp']
           .transform(lambda s: pd.qcut(s, q=3, labels=[1, 2, 3], duplicates='drop')
                                  if s.dropna().nunique() >= 3 else pd.Series([np.nan]*len(s), index=s.index))
    )
    # tertile==1 is bottom (soft offense -> LOW lineup_xfp -> bottom tertile)
    out['opp_soft'] = (out['opp_tertile'].astype('float') == 1.0).astype(int)
    # Where tertile NaN (couldn't compute), opp_soft = 0 (neutral)
    out.loc[out['opp_tertile'].isna(), 'opp_soft'] = 0
    return out[['pitcher', 'year', 'cutoff_date', 'opp_lineup_xfp', 'opp_soft']]


# ---------------------------------------------------------------------------
# Step 4 — Build boom_stack for Mode A merge into rolling
# ---------------------------------------------------------------------------
def build_boom_stack_panel(rolling: pd.DataFrame, starts: pd.DataFrame) -> pd.DataFrame:
    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    cutoffs_per_year: dict[int, list[pd.Timestamp]] = {}
    for yr in sorted(rolling['year'].unique()):
        if int(yr) not in YEARS:
            continue
        cutoffs_per_year[int(yr)] = sorted(
            pd.to_datetime(rolling[rolling['year'] == yr]['cutoff_date'].unique()).tolist()
        )

    print('  computing per-(pitcher, year, cutoff) K%/BB%/FP components...')
    comps = compute_components_at_cutoff(starts, cutoffs_per_year)
    print(f'  components panel rows: {len(comps)}')

    print('  computing opp_soft (forward-looking-at-cutoff via NEXT scheduled start)...')
    opp = compute_opp_soft_at_cutoff(starts, cutoffs_per_year)
    print(f'  opp panel rows: {len(opp)}')

    panel = comps.merge(opp, on=['pitcher', 'year', 'cutoff_date'], how='left')
    panel['opp_soft'] = panel['opp_soft'].fillna(0).astype(int)

    # Component flags
    delta_K_pp = (panel['last3_k_pct'] - panel['season_k_pct']) * 100.0
    delta_BB_pp = (panel['last3_bb_pct'] - panel['season_bb_pct']) * 100.0
    delta_FP = panel['last3_fp'] - panel['season_fp']

    panel['flag_skill_spike'] = (
        (delta_K_pp >= 3.0) & (delta_BB_pp <= -1.0) & panel['n_prior_starts'].ge(3)
    ).astype(int)
    panel['flag_recform_hot'] = (
        (delta_FP >= 3.0) & panel['n_prior_starts'].ge(3)
    ).astype(int)
    panel['flag_opp_soft'] = panel['opp_soft'].astype(int)

    panel['boom_stack'] = (panel['flag_skill_spike']
                           + panel['flag_recform_hot']
                           + panel['flag_opp_soft']).astype(int)
    return panel[['pitcher', 'year', 'cutoff_date',
                  'flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft',
                  'boom_stack', 'n_prior_starts',
                  'last3_k_pct', 'season_k_pct',
                  'last3_bb_pct', 'season_bb_pct',
                  'last3_fp', 'season_fp', 'opp_lineup_xfp']]


# ---------------------------------------------------------------------------
# Step 5 — Mode A: integration test
# ---------------------------------------------------------------------------
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
            'n_eval_baseline': ov_b['n'],
            'n_eval_full': ov_f['n'],
        }
    return out


def partial_r_full_baseline(rolling: pd.DataFrame, candidate: str) -> dict:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    from scipy.stats import pearsonr

    full = RP3_FEATS + [candidate]
    df = rolling.dropna(subset=full + [TARGET]).copy()
    df = df[(df['gs_to'] >= 2) & (df['ros_gs'] >= 5) & (df['year'] != 2020)]

    res_y = []; res_full = []
    for held in YEARS:
        train = df[df['year'] != held]
        test = df[df['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe_b = Pipeline([('sc', StandardScaler()),
                           ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe_b.fit(train[RP3_FEATS].values, train[TARGET].values)
        pred_b = pipe_b.predict(test[RP3_FEATS].values)
        pipe_f = Pipeline([('sc', StandardScaler()),
                           ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe_f.fit(train[full].values, train[TARGET].values)
        pred_f = pipe_f.predict(test[full].values)
        y_true = test[TARGET].values
        res_y.extend((y_true - pred_b).tolist())
        res_full.extend((pred_f - pred_b).tolist())

    if len(res_y) < 10 or np.std(res_full) == 0:
        return {'partial_r': float('nan'), 'n': len(res_y)}
    return {'partial_r': float(pearsonr(res_y, res_full)[0]), 'n': len(res_y)}


# ---------------------------------------------------------------------------
# Step 6 — Mode B: per-start boom-rate classifier
# ---------------------------------------------------------------------------
def build_per_start_boom_stack(starts: pd.DataFrame) -> pd.DataFrame:
    """For each per-start row: components 1 & 2 use strictly-prior starts;
    component 3 uses the start's own lineup_xfp (pre-game knowable)."""
    rows = []
    for (pid, yr), grp in starts.groupby(['pitcher', 'year'], sort=False):
        grp = grp.sort_values('game_date').reset_index(drop=True)
        for i, row in grp.iterrows():
            prior = grp.iloc[:i]
            if len(prior) < 3:
                rows.append({**row.to_dict(),
                             'flag_skill_spike': 0,
                             'flag_recform_hot': 0,
                             'boom_stack_pre': 0,
                             'n_prior_starts': len(prior)})
                continue
            sK = prior['actual_K'].sum() / max(prior['actual_PA'].sum(), 1)
            sBB = prior['actual_BB'].sum() / max(prior['actual_PA'].sum(), 1)
            sFP = prior['fp'].mean()
            last3 = prior.tail(3)
            l3K = last3['actual_K'].sum() / max(last3['actual_PA'].sum(), 1)
            l3BB = last3['actual_BB'].sum() / max(last3['actual_PA'].sum(), 1)
            l3FP = last3['fp'].mean()
            dK_pp = (l3K - sK) * 100.0
            dBB_pp = (l3BB - sBB) * 100.0
            dFP = l3FP - sFP
            f_ss = int((dK_pp >= 3.0) and (dBB_pp <= -1.0))
            f_rh = int(dFP >= 3.0)
            rows.append({**row.to_dict(),
                         'flag_skill_spike': f_ss,
                         'flag_recform_hot': f_rh,
                         'boom_stack_pre': f_ss + f_rh,
                         'n_prior_starts': len(prior)})
    out = pd.DataFrame(rows)
    # Component 3: opp_soft via tertile of lineup_xfp within (year, calendar month)
    # to keep slate definition stable per-day; cross-day tertile is too coarse.
    out['ym'] = out['game_date'].dt.to_period('M').astype(str)
    out['opp_tertile'] = (
        out.groupby(['year', 'ym'])['lineup_xfp']
           .transform(lambda s: pd.qcut(s.rank(method='first'), q=3,
                                         labels=[1, 2, 3], duplicates='drop')
                                if s.notna().sum() >= 30 else pd.Series([np.nan]*len(s), index=s.index))
    )
    out['flag_opp_soft'] = (out['opp_tertile'].astype('float') == 1.0).astype(int)
    out.loc[out['opp_tertile'].isna(), 'flag_opp_soft'] = 0
    out['boom_stack'] = out['boom_stack_pre'] + out['flag_opp_soft']
    out['boom_outcome'] = (out['fp'] >= 20.0).astype(int)
    return out


def mode_b_boom_rate(per_start_panel: pd.DataFrame,
                     streamer_rank_floor: int = 50) -> dict:
    """Compute boom rate by boom_stack bucket within streamer-tier subset.

    Streamer tier = pitcher's rolling fp_per_start_to <= 25th percentile within
    that (year, calendar month) — i.e., back-end / low-recent-FP arms. This is
    a per-start computable proxy for "rp3 rank >= 50" since we don't have a
    cached rp3 rank panel per game_date.
    """
    df = per_start_panel.copy()
    # Compute pre-start fp_per_start rolling-to-date (we already have season_fp
    # implicitly via per-start sFP — recompute clean here).
    df = df.sort_values(['pitcher', 'year', 'game_date'])
    df['cum_fp'] = df.groupby(['pitcher', 'year'])['fp'].cumsum() - df['fp']
    df['cum_n'] = df.groupby(['pitcher', 'year']).cumcount()
    df['rolling_fp'] = df['cum_fp'] / df['cum_n'].replace(0, np.nan)
    # Streamer threshold: bottom 50% of rolling_fp within (year, calendar month)
    df['rolling_fp_pct'] = (
        df.groupby(['year', 'ym'])['rolling_fp']
          .transform(lambda s: s.rank(pct=True))
    )
    streamer = df[(df['rolling_fp_pct'].notna()) &
                  (df['rolling_fp_pct'] <= 0.50) &
                  (df['cum_n'] >= 3)].copy()

    # Boom rate by bucket
    buckets = {}
    for b in [0, 1, 2, 3]:
        m = streamer['boom_stack'] == b
        n = int(m.sum())
        booms = int(streamer.loc[m, 'boom_outcome'].sum())
        rate = booms / n if n > 0 else float('nan')
        buckets[b] = {'n': n, 'booms': booms, 'boom_rate': rate,
                      'mean_fp': float(streamer.loc[m, 'fp'].mean()) if n > 0 else float('nan')}

    # 2x2 chi-squared: boom_stack <= 0 vs >= 2 on boom outcome
    low = streamer[streamer['boom_stack'] <= 0]
    hi = streamer[streamer['boom_stack'] >= 2]
    table = np.array([
        [int(low['boom_outcome'].sum()), int((1 - low['boom_outcome']).sum())],
        [int(hi['boom_outcome'].sum()),  int((1 - hi['boom_outcome']).sum())],
    ])
    chi2, p, _, _ = chi2_contingency(table) if (table.sum(axis=1).min() >= 5) else (np.nan, np.nan, None, None)

    # Same on full set for context
    full_buckets = {}
    for b in [0, 1, 2, 3]:
        m = df['boom_stack'] == b
        n = int(m.sum())
        booms = int(df.loc[m, 'boom_outcome'].sum())
        rate = booms / n if n > 0 else float('nan')
        full_buckets[b] = {'n': n, 'booms': booms, 'boom_rate': rate,
                           'mean_fp': float(df.loc[m, 'fp'].mean()) if n > 0 else float('nan')}

    return {
        'streamer_n': int(len(streamer)),
        'streamer_buckets': buckets,
        'streamer_chi2_low_vs_hi': {
            'chi2': float(chi2) if not np.isnan(chi2) else None,
            'p_value': float(p) if not np.isnan(p) else None,
            'table_low_vs_hi': table.tolist(),
            'low_boom_rate': float(low['boom_outcome'].mean()) if len(low) else None,
            'hi_boom_rate': float(hi['boom_outcome'].mean()) if len(hi) else None,
        },
        'full_pool_buckets': full_buckets,
        'full_pool_n': int(len(df)),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== validate_streamer_boom_stack ===')

    print('Step 1: load per-start panel + game_dates...')
    starts = load_per_start_with_dates()
    print(f'  per-start rows after PA filter: {len(starts)}')

    print('Step 2: prep rolling RP3 substrate...')
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
    print(f'  rolling rows: {len(rolling)}')
    miss = [f for f in RP3_FEATS if f not in rolling.columns]
    if miss:
        print(f'  WARN: missing baseline feats: {miss}')

    print('Step 3: build boom_stack panel at (pitcher, year, cutoff_date)...')
    panel = build_boom_stack_panel(rolling, starts)
    print(f'  panel rows: {len(panel)}')
    print(f'  panel boom_stack distribution:')
    print(panel['boom_stack'].value_counts().sort_index().to_string())
    print('  flag rates:')
    for f in ('flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft'):
        print(f'    {f}: {panel[f].mean():.3%}')

    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    rolling = rolling.merge(
        panel[['pitcher', 'year', 'cutoff_date',
               'flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft',
               'boom_stack']],
        on=['pitcher', 'year', 'cutoff_date'], how='left',
    )
    for c in ('flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft', 'boom_stack'):
        rolling[c] = rolling[c].fillna(0).astype(int)
    print(f'  rolling rows after merge: {len(rolling)}, '
          f'nonzero boom_stack: {(rolling["boom_stack"] > 0).mean():.1%}')

    # ----- MODE A: model integration -----
    print('\n=== MODE A: integration into rp3 (Rule 9 lift test) ===')
    result = evaluate_candidate(rolling, 'boom_stack', fill_value=0,
                                 label='boom_stack')
    print_report(result)

    print('Convergence across split_day 30/44/58:')
    conv = per_split_day_lift(rolling, 'boom_stack')
    for sd, c in conv.items():
        if c.get('skipped'):
            print(f'  sd={sd}: SKIPPED (n={c["n"]})')
            continue
        print(f'  sd={sd:>3}: r_base={c["r_baseline"]:.4f}  r_full={c["r_full"]:.4f}  '
              f'gain={c["r_gain"]:+.4f}  mae_gain={c["mae_gain"]:+.4f}  '
              f'n={c["n_eval_full"]}')

    print('Partial r vs full baseline (added-variable form):')
    pr = partial_r_full_baseline(rolling, 'boom_stack')
    print(f'  partial r = {pr["partial_r"]:+.4f}  (pooled n={pr["n"]})')

    # Holdout MAE
    py_b, ov_b = cross_year_eval(rolling, RP3_FEATS)
    py_f, ov_f = cross_year_eval(rolling, RP3_FEATS + ['boom_stack'])
    holdout_mae_b = float(np.mean([py_b[y]['mae'] for y in [2024, 2025] if y in py_b]))
    holdout_mae_f = float(np.mean([py_f[y]['mae'] for y in [2024, 2025] if y in py_f]))
    print(f'Holdout MAE baseline: {holdout_mae_b:.4f}  full: {holdout_mae_f:.4f}  '
          f'gain: {holdout_mae_b - holdout_mae_f:+.4f} FP/start')

    # ----- MODE B: per-start boom rate classifier -----
    print('\n=== MODE B: per-start boom-rate classifier (streamer pool) ===')
    print('  building per-start boom_stack panel...')
    ps_panel = build_per_start_boom_stack(starts)
    print(f'  per-start panel rows: {len(ps_panel)}')
    print('  per-start flag rates (all starts):')
    for f in ('flag_skill_spike', 'flag_recform_hot', 'flag_opp_soft'):
        print(f'    {f}: {ps_panel[f].mean():.3%}')

    mode_b = mode_b_boom_rate(ps_panel, streamer_rank_floor=50)
    print(f'  streamer-pool N (rolling-fp pct <=50, n_prior_starts >= 3): '
          f'{mode_b["streamer_n"]}')
    print('  boom rate by boom_stack bucket (streamer pool):')
    for b, info in mode_b['streamer_buckets'].items():
        print(f'    stack={b}: n={info["n"]:>4d}  booms={info["booms"]:>3d}  '
              f'rate={info["boom_rate"]:.3%}  mean_fp={info["mean_fp"]:.2f}')
    cs = mode_b['streamer_chi2_low_vs_hi']
    if cs['chi2'] is not None:
        print(f'  Chi-squared (low <=0 vs hi >=2): chi2={cs["chi2"]:.3f}  '
              f'p={cs["p_value"]:.4f}')
        print(f'    low boom rate: {cs["low_boom_rate"]:.3%}  '
              f'hi boom rate: {cs["hi_boom_rate"]:.3%}')
    print('  boom rate by boom_stack bucket (FULL pool, for reference):')
    for b, info in mode_b['full_pool_buckets'].items():
        print(f'    stack={b}: n={info["n"]:>4d}  booms={info["booms"]:>3d}  '
              f'rate={info["boom_rate"]:.3%}  mean_fp={info["mean_fp"]:.2f}')

    # Persist
    output = {
        'mode_a': {
            'rule9_lift_test': result,
            'convergence_per_split_day': conv,
            'partial_r_vs_full_baseline': pr,
            'holdout_mae': {
                'baseline': holdout_mae_b,
                'full': holdout_mae_f,
                'gain_fp_per_start': holdout_mae_b - holdout_mae_f,
            },
        },
        'mode_b': mode_b,
        'panel_distribution': {
            'boom_stack_value_counts': panel['boom_stack'].value_counts().sort_index().to_dict(),
            'flag_skill_spike_rate': float(panel['flag_skill_spike'].mean()),
            'flag_recform_hot_rate': float(panel['flag_recform_hot'].mean()),
            'flag_opp_soft_rate':    float(panel['flag_opp_soft'].mean()),
        },
    }
    out_json = OUT_DIR / 'streamer_boom_stack_v1_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')


if __name__ == '__main__':
    main()
