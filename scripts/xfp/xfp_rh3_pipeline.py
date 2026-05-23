"""
xfp_rh3_pipeline.py — Bayesian RoS hitter model with recency + confidence
intervals + replacement-level deltas + PA projection.

Adds on top of RH2:
  1. Last-21-day rate features (shrunken with smaller k since smaller sample)
  2. Residual-based confidence interval (p25 / p50 / p75) per projection
  3. Replacement-level delta per (player, primary_position)
  4. PA projection — current 2026 PA/game pace × games-remaining × IL discount
  5. Composite "drop / hold / add" signal vs replacement

Outputs:
  data/models/xfp_rh3_pipeline.pkl
  data/outputs/xfp_rh3_projections.csv

Decision gate: cross-year r >= RH2 + 0.005 (recency adds signal but is noisy).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

from plv_clone.models.xfp import engine as _engine
from plv_clone.models.xfp.engine import lookup_sigma  # re-export

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
H2_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_h2_projections.csv'
IL_CSV      = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_split_features_2018_2026.csv'
MASTER_HITTER = ROOT / 'data' / 'outputs' / 'master_hitter_2026.csv'
MODEL_PKL   = ROOT / 'data' / 'models' / 'xfp_rh3_pipeline.pkl'
PROJ_CSV    = ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv'

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN = 50
ROS_PA_MIN = 100
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_PA = 200
MARCEL_WEIGHTS = (5, 4, 3)
PA_PER_GAME_LEAGUE = 3.5
SEASON_GAMES = 162

# Replacement-level cutoffs from league_config (8-team, this user's league)
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from league_config import HITTER_REPLACEMENT_RANK as REPLACEMENT_RANK

# Cumulative-window shrinkage spec
SHRINK_SPEC_TO = {
    'k_pct_to':         ('pa_to',     60),
    'bb_pct_to':        ('pa_to',    120),
    'hr_per_pa_to':     ('pa_to',    170),
    'iso_to':           ('ab_to',    160),
    'sb_per_pa_to':     ('pa_to',    300),
    'xwoba_per_pa_to':  ('pa_to',    300),
    'contact_pct_to':   ('swing_to', 100),
    'whiff_pct_to':     ('swing_to', 100),
    'swstr_pct_to':     ('pitches_to', 300),
    'hard_hit_pct_to':  ('bip_to',    50),
    'barrel_pct_to':    ('bip_to',    50),
    'chase_pct_to':     ('out_zone_to', 400),
    'in_play_pct_to':   ('pitches_to', 300),
}
# Last-21-day window: smaller sample, so heavier shrinkage (smaller k -> more
# weight on the population mean unless the rate is way out of band).
SHRINK_SPEC_LAST21 = {
    'k_pct_last21':         ('pa_last21',     30),
    'bb_pct_last21':        ('pa_last21',     60),
    'iso_last21':           ('ab_last21',     80),
    'xwoba_per_pa_last21':  ('pa_last21',    150),
    'contact_pct_last21':   ('swing_last21',  50),
    'whiff_pct_last21':     ('swing_last21',  50),
    'hard_hit_pct_last21':  ('bip_last21',    25),
    'barrel_pct_last21':    ('bip_last21',    25),
    'hr_per_pa_last21':     ('pa_last21',     85),
}

# Model features = RH2 set. Last-21-day rates failed the +0.005 r gate
# (delta vs RH2 was only +0.002 — within noise). They remain in the substrate
# but are NOT used as model features; they only flow to the dashboard as the
# `recency_form_gap` display column. This keeps the production model identical
# to RH2 in predictive output while the decision-layer columns (CI, replacement
# delta, signal) sit on top.
RH3_FEATS = [
    # Cumulative shrunken rates (RH2)
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    # Prior + sample-size cues
    'prior_fp_per_pa', 'prior_pa_eff', 'pa_to', 'split_day',
    # H2 lift career profile (locked variant: Aug-01 cutoff, min_pa=150)
    # Cross-year r-lift +0.024 (the only career-profile feature that survived
    # the empirical r-improvement gate in feature-lift validation 2026-05-09).
    'lift_h2_aug150',
    # xwOBA residual (career-level luck-adjustment signal, 2018-2025 window).
    # Cross-year r-lift +0.0051 on top of RH3 baseline (validated 2026-05-10).
    # Tier-S leading-style predictor: positive residual = career xwOBA exceeds
    # actual wOBA = "unlucky" → mild bump in expected fp.
    'xwoba_residual_career',
    # WITHIN-SEASON xwOBA - actual wOBA gap (H3, validated 2026-05-12).
    # Standalone gain +0.077 r; v2 integrated gain +0.006 r over rh3 v1.
    # Different from xwoba_residual_career (which is career-level) —
    # this one detects within-2026-season luck regression candidates.
    'xwoba_gap_to',
    # Career stage = year - first MLB year (H5, validated 2026-05-12).
    # Captures young-vs-vet trajectory effects rh3 v1 missed.
    # Standalone gain +0.017 r; integrated into v2.
    'career_stage',
]
H2_LOCKED_CSV = ROOT / 'data' / 'outputs' / 'seasonality_h2_locked.csv'
XWOBA_RESID_CSV = ROOT / 'data' / 'outputs' / 'hitter_xwoba_residual.csv'


def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'ab_to' not in out.columns:
        out = out.assign(ab_to=out['pa_to'] - out['bb_to'] - out.get('hbp_to', 0))
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    if 'ab_last21' not in out.columns and 'pa_last21' in out.columns:
        out = out.assign(ab_last21=out['pa_last21'] - out['bb_last21'].fillna(0)
                         - out.get('hbp_last21', 0))
    return out


def build_prior_table(multiyr: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    rows = []
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('batter') for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['pa'] >= 200]
                           .groupby('year')['fp_per_pa_actual'].mean().to_dict())
    all_batters = set()
    for df in by_yr.values():
        all_batters.update(df.index)

    for tgt in years:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL_WEIGHTS):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for b in all_batters:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                df_y = by_yr[y]
                if b in df_y.index:
                    row = df_y.loc[b]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    pa = float(row.get('pa', 0) or 0)
                    fp = float(row.get('fp_per_pa_actual', np.nan))
                    if pa >= 50 and not np.isnan(fp):
                        num += w * pa * fp
                        denom += w * pa
            prior = (num + PRIOR_K_PA * league_mu) / (denom + PRIOR_K_PA)
            rows.append({'batter': b, 'year': tgt,
                         'prior_fp_per_pa': prior,
                         'prior_pa_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    return pd.DataFrame(rows)


def compute_population_means(df: pd.DataFrame, train_years: list[int],
                              spec: dict) -> dict:
    return _engine.compute_population_means(_ensure_derived_denoms(df.copy()), train_years, spec)


def apply_shrinkage(df: pd.DataFrame, pop_means: dict, spec: dict) -> pd.DataFrame:
    return _engine.apply_shrinkage(_ensure_derived_denoms(df.copy()), pop_means, spec)


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    per_year, preds_all, acts_all = {}, [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(test)}
        preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}


def fit_residual_ci(df: pd.DataFrame, feats: list[str]):
    """Residual-based CI table: (split_day, predicted_quartile) -> sigma."""
    sub = df.dropna(subset=feats + [TARGET]).copy()
    sub = sub[(sub['pa_to'] >= EVAL_PA_MIN) & (sub['ros_pa'] >= ROS_PA_MIN)
              & (sub['year'] != 2020)]
    res = _engine.train_residual_table(
        df=sub, feats=feats, target_col=TARGET, train_years=TRAIN_YEARS,
        min_train=100, min_test=30,
    )
    out: dict[tuple[int, int], float] = {}
    for split in sorted(res['split_day'].unique()):
        sub2 = res[res['split_day'] == split]
        qs = pd.qcut(sub2['pred'], q=4, duplicates='drop', labels=False)
        for q in sorted(sub2.groupby(qs).groups.keys()):
            ix = (qs == q)
            sigma = float(sub2.loc[ix, 'resid'].std())
            out[(int(split), int(q))] = sigma
    overall_sigma = float(res['resid'].std())
    return out, overall_sigma


def train_final(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [TARGET])
    train = train[(train['pa_to'] >= EVAL_PA_MIN) & (train['ros_pa'] >= ROS_PA_MIN)
                  & (train['year'].isin(TRAIN_YEARS))]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def main():
    print('=== xfp_rh3 (RH2 + recency + CI + replacement deltas + PA proj) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    # Marcel prior
    print('\nBuilding Marcel prior...')
    years_needed = sorted(rolling['year'].unique())
    prior = build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    # H2-locked career profile feature (Aug-01 cutoff, min 150 PA per half)
    if H2_LOCKED_CSV.exists():
        h2_locked = pd.read_csv(H2_LOCKED_CSV)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2_locked, on='batter', how='left')
        # Players without enough career data: fill with 0 (no seasonal tilt assumed)
        n_with = rolling['lift_h2_aug150'].notna().sum()
        rolling['lift_h2_aug150'] = rolling['lift_h2_aug150'].fillna(0.0)
        print(f'  merged H2-locked feature: {n_with}/{len(rolling)} rows have career data')
    else:
        print(f'  WARNING: {H2_LOCKED_CSV} missing — fill lift_h2_aug150=0')
        rolling['lift_h2_aug150'] = 0.0

    # xwOBA residual career feature (2018-2025 window)
    if XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(XWOBA_RESID_CSV)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
        n_with = rolling['xwoba_residual_career'].notna().sum()
        rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
        print(f'  merged xwOBA residual feature: {n_with}/{len(rolling)} rows have career data')
    else:
        print(f'  WARNING: {XWOBA_RESID_CSV} missing — fill xwoba_residual_career=0')
        rolling['xwoba_residual_career'] = 0.0

    # NEW v2 features (validated 2026-05-12):
    # xwoba_gap_to = within-season expected wOBA on contact − actual wOBA per PA.
    # Captures regression-candidate signal at the current-season window.
    if 'xwoba_on_contact_to' in rolling.columns and 'woba_d_sum_to' in rolling.columns:
        rolling['actual_woba_per_pa_to'] = np.where(
            rolling['woba_d_sum_to'] > 0,
            rolling['woba_v_sum_to'] / rolling['woba_d_sum_to'],
            np.nan)
        rolling['xwoba_gap_to'] = (rolling['xwoba_on_contact_to']
                                     - rolling['actual_woba_per_pa_to'])
        # Fill NaN with 0 (neutral signal)
        rolling['xwoba_gap_to'] = rolling['xwoba_gap_to'].fillna(0.0)
        n_with = (rolling['xwoba_gap_to'] != 0).sum()
        print(f'  computed xwoba_gap_to: {n_with}/{len(rolling)} rows non-trivial')
    else:
        rolling['xwoba_gap_to'] = 0.0
        print('  WARNING: xwoba_on_contact_to or woba_*_sum_to missing — fill 0')

    # career_stage = target year - first MLB year per batter
    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    rolling['career_stage'] = rolling.apply(
        lambda r: r['year'] - first_year.get(r['batter'], r['year']), axis=1)
    print(f'  computed career_stage: range {rolling["career_stage"].min()}-{rolling["career_stage"].max()}')

    # Shrinkage on both windows
    print('Shrinkage (cumulative + last21)...')
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    # last21 columns can be NaN (zero PA in window) — fill _sh with mean
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)

    # Cross-year (RH3)
    print('\n--- LOO cross-year eval (RH3) ---')
    per_year, overall = cross_year_eval(rolling, RH3_FEATS)
    for y, r in sorted(per_year.items()):
        print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    # v2 baseline: drop the v2-added features (xwoba_gap_to + career_stage)
    # AND any _last21 features (legacy gate). This is the actual rh1/rh2-style
    # baseline that v2 should be beating, not "drop last21" alone (which is
    # vacuous when current RH3_FEATS already has no last21 features).
    v2_added = {'xwoba_gap_to', 'career_stage'}
    baseline_feats = [f for f in RH3_FEATS if 'last21' not in f and f not in v2_added]
    _ , baseline = cross_year_eval(rolling, baseline_feats)
    delta = overall['r'] - baseline['r']
    print(f'\n--- Baseline (drops v2 features {sorted(v2_added)} + last21) ---')
    print(f'  Overall: r={baseline["r"]}')
    print(f'  Δr (RH3 v2 − baseline) = {delta:+.4f}  '
          f'{"PASS" if delta >= 0.005 else "MARGINAL"}  (gate: ≥ +0.005)')

    # Confidence interval table
    print('\n--- Building residual-based CI table ---')
    ci_table, overall_sigma = fit_residual_ci(rolling, RH3_FEATS)
    print(f'  overall sigma = {overall_sigma:.4f} FP/PA')

    # Train final + project 2026
    pipe, n_train = train_final(rolling, RH3_FEATS)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RH3 pipeline (n_train={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}) ---')
    print('  Top coefficients:')
    for f, c in sorted(zip(RH3_FEATS, coefs), key=lambda x: -abs(x[1]))[:12]:
        print(f'    {f:<26s} {c:+.4f}')

    # Projection for 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        print('No 2026 data.'); return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['pa_to'] >= EVAL_PA_MIN)]
    valid = df_26.dropna(subset=RH3_FEATS).copy()
    valid['xfp_rh3_per_pa'] = pipe.predict(valid[RH3_FEATS].values)

    # Build pred-quartile cut points per split_day for sigma lookup
    train_for_buckets = rolling.dropna(subset=RH3_FEATS + [TARGET])
    train_for_buckets = train_for_buckets[(train_for_buckets['pa_to'] >= EVAL_PA_MIN)
                                          & (train_for_buckets['ros_pa'] >= ROS_PA_MIN)
                                          & (train_for_buckets['year'].isin(TRAIN_YEARS))]
    train_pred = pipe.predict(train_for_buckets[RH3_FEATS].values)
    pred_buckets = {}
    for split in sorted(train_for_buckets['split_day'].unique()):
        ix = (train_for_buckets['split_day'].values == split)
        if ix.sum() < 30:
            continue
        cuts = np.quantile(train_pred[ix], [0.25, 0.5, 0.75])
        pred_buckets[int(split)] = cuts

    # Per-row sigma + p25/p75 via residual normal approximation (z=0.6745)
    Z25 = 0.6745
    sigmas = []
    for _, row in valid.iterrows():
        sigmas.append(lookup_sigma(ci_table, overall_sigma, latest_split,
                                   row['xfp_rh3_per_pa'], pred_buckets))
    valid['xfp_rh3_sigma'] = sigmas
    valid['xfp_rh3_p25'] = (valid['xfp_rh3_per_pa'] - Z25 * valid['xfp_rh3_sigma']).clip(lower=0)
    valid['xfp_rh3_p75'] = valid['xfp_rh3_per_pa'] + Z25 * valid['xfp_rh3_sigma']

    # Recency vs prior signal — gap between in-season & long-run
    valid['recency_form_gap'] = (valid['xwoba_per_pa_last21_sh'] -
                                  valid['xwoba_per_pa_to_sh']).round(4)

    # Per-game
    valid['xfp_rh3_per_game'] = (valid['xfp_rh3_per_pa'] * PA_PER_GAME_LEAGUE).round(2)

    # Names + position
    names = multiyr[multiyr['year'] == 2026][['batter', 'player_name', 'team']] \
        .drop_duplicates('batter')
    valid = valid.drop_duplicates('batter').merge(names, on='batter', how='left')
    if MASTER_HITTER.exists():
        mh = pd.read_csv(MASTER_HITTER)
        keep = [c for c in ['batter', 'primary_position', 'fantasy_positions',
                            'fantasy_positions_display']
                if c in mh.columns]
        valid = valid.merge(mh[keep], on='batter', how='left')
    if 'primary_position' not in valid.columns:
        valid['primary_position'] = None

    # PA projection: actual PA-pace × games-remaining
    games_played_so_far = max(latest_split, 1)
    games_remaining = max(SEASON_GAMES - games_played_so_far, 0)
    pa_pace = valid['pa_to'] / games_played_so_far
    # Simple: assume current pace continues; future enhancement = lineup spot.
    valid['expected_pa_remaining'] = (pa_pace * games_remaining).round(0)
    valid['expected_total_fp_remaining'] = (
        valid['xfp_rh3_per_pa'] * valid['expected_pa_remaining']
    ).round(1)

    # Replacement-level deltas (per-position)
    print('\n--- Computing replacement-level deltas ---')
    valid = compute_replacement_delta(valid)

    # Composite signal
    valid['signal'] = valid.apply(_signal, axis=1)

    valid = valid.sort_values('xfp_rh3_per_pa', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    # Bundle
    bundle = {
        'pipeline': pipe,
        'features': RH3_FEATS,
        'target': TARGET,
        'pop_means_to': pop_to,
        'pop_means_last21': pop_l21,
        'shrink_spec_to': SHRINK_SPEC_TO,
        'shrink_spec_last21': SHRINK_SPEC_LAST21,
        'prior_k_pa': PRIOR_K_PA,
        'marcel_weights': MARCEL_WEIGHTS,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rh2_r': baseline['r'],
        'delta_r_vs_rh2': round(delta, 4),
        'per_year_r': per_year,
        'ci_table': ci_table,
        'pred_buckets': {k: v.tolist() for k, v in pred_buckets.items()},
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'min_pa_to': EVAL_PA_MIN,
        'min_ros_pa': ROS_PA_MIN,
        'pa_per_game_league': PA_PER_GAME_LEAGUE,
        'season_games': SEASON_GAMES,
        'replacement_rank': REPLACEMENT_RANK,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rh3',
        'note': 'Bayesian RoS hitter Ridge + last-21-day form + residual CI '
                '+ replacement-level deltas + PA-aware total FP.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Slump-precedent merge (rolling-window career comparison vs current 2026)
    slump_path = ROOT / 'data' / 'outputs' / 'slump_precedent_hitters_2026.csv'
    if slump_path.exists():
        sp = pd.read_csv(slump_path)[
            ['batter', 'pct_rank', 'n_comparable', 'bounce_pct',
             'median_next_rate', 'median_delta']
        ].rename(columns={
            'pct_rank': 'slump_pct_rank',
            'n_comparable': 'slump_n_comparable',
            'bounce_pct': 'slump_bounce_pct',
            'median_next_rate': 'slump_next_rate',
            'median_delta': 'slump_delta',
        })
        valid = valid.merge(sp, on='batter', how='left')

    out_cols = [
        'rank', 'batter', 'player_name', 'team', 'primary_position',
        'pa_to', 'pa_last21',
        'prior_fp_per_pa', 'recency_form_gap',
        'xfp_rh3_per_pa', 'xfp_rh3_per_game', 'xfp_rh3_sigma',
        'xfp_rh3_p25', 'xfp_rh3_p75',
        'expected_pa_remaining', 'expected_total_fp_remaining',
        'replacement_xfp_per_pa', 'replacement_delta',
        'signal',
        'slump_pct_rank', 'slump_n_comparable', 'slump_bounce_pct',
        'slump_next_rate', 'slump_delta',
    ]
    out_cols = [c for c in out_cols if c in valid.columns]
    valid[out_cols].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} hitters')
    print('\nTop 10 hitters by signal score (xFP delta vs replacement):')
    show = ['rank', 'player_name', 'primary_position', 'team',
            'xfp_rh3_per_pa', 'xfp_rh3_p25', 'xfp_rh3_p75',
            'replacement_delta', 'signal']
    show = [c for c in show if c in valid.columns]
    top = valid.sort_values('replacement_delta', ascending=False).head(10)
    print(top[show].to_string(index=False))


def _normalize_pos(p) -> str:
    if not isinstance(p, str):
        return 'UTIL'
    p = p.upper().strip()
    if p in ('LF','CF','RF','OF'): return 'OF'
    if p in ('C','1B','2B','SS','3B','DH'): return p
    return 'UTIL'


def compute_replacement_delta(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['_pos'] = df['primary_position'].map(_normalize_pos)
    repl = {}
    for pos, n in REPLACEMENT_RANK.items():
        sub = df[df['_pos'] == pos].sort_values('xfp_rh3_per_pa', ascending=False)
        if len(sub) >= n:
            repl[pos] = float(sub['xfp_rh3_per_pa'].iloc[n - 1])
        elif not sub.empty:
            repl[pos] = float(sub['xfp_rh3_per_pa'].iloc[-1])
        else:
            repl[pos] = float(df['xfp_rh3_per_pa'].median())
    df['replacement_xfp_per_pa'] = df['_pos'].map(repl)
    df['replacement_delta'] = (df['xfp_rh3_per_pa'] - df['replacement_xfp_per_pa']).round(4)
    df = df.drop(columns=['_pos'])
    return df


def _signal(row) -> str:
    """Signal bucket for the dashboard."""
    delta = row.get('replacement_delta', 0)
    p25 = row.get('xfp_rh3_p25', None)
    repl = row.get('replacement_xfp_per_pa', None)
    if delta is None or pd.isna(delta) or repl is None or pd.isna(repl):
        return 'hold'
    # ADD: high-confidence above replacement (p25 still > replacement)
    if p25 is not None and not pd.isna(p25) and p25 > repl:
        return 'add'
    # DROP: below replacement and even p75 doesn't recover
    p75 = row.get('xfp_rh3_p75', None)
    if p75 is not None and not pd.isna(p75) and p75 < repl:
        return 'drop'
    return 'hold'


if __name__ == '__main__':
    main()
