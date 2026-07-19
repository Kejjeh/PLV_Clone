"""
xfp_rh3 — Bayesian RoS hitter model with recency + confidence
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

ADR-0001: this module owns its own fit_and_project orchestration. The shared
`engine.py` is a toolkit composed at load-bearing steps, not an orchestrator.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

from plv_clone.models.xfp import engine as _engine
from plv_clone.models.xfp.engine import lookup_sigma, lookup_sigma_vec  # re-export
from plv_clone.league_config import HITTER_REPLACEMENT_RANK as REPLACEMENT_RANK
from plv_clone.models.xfp.hitter_sigma_hetero import (
    load_calibration as _load_hetero_calib,
    compute_batter_sigma_factors as _compute_hetero_factors,
)

warnings.filterwarnings('ignore')

# Path anchors: this file lives at src/plv_clone/models/xfp/rh3.py, so parents[4]
# is the repo root (rh3.py → xfp → models → plv_clone → src → repo root).
ROOT = Path(__file__).resolve().parents[4]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
H2_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_h2_projections.csv'
IL_CSV      = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_split_features_2018_2026.csv'
ROS_OPP_SP_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'ros_opp_sp_xwoba_per_hitter.csv'
BX_PRIORS_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'bx_priors_2018_2026.csv'
MASTER_HITTER = ROOT / 'data' / 'outputs' / 'master_hitter_2026.csv'
HITTER_RATINGS_MASTER = ROOT / 'data' / 'research' / 'hitter_ratings_master.csv'
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
    # xwoba_gap_to (within-season xwOBA - actual wOBA per PA) REMOVED
    # 2026-05-23: re-audit verdict MARGINAL (-0.0003 vs full baseline;
    # career_stage carries the v2 joint lift). Promoted Rule 9 to hard
    # assert; this feature couldn't clear the +0.005 gate. Derivation at
    # line ~285 is left intact so retroactive analyses can still compute
    # the column; it just isn't in FEATS anymore.
    # Career stage = year - first MLB year (H5, validated 2026-05-12).
    # Captures young-vs-vet trajectory effects rh3 v1 missed.
    # Standalone gain +0.017 r; integrated into v2.
    'career_stage',
    # RoS opposing-SP schedule strength: per-(batter, year, split_day)
    # equal-weight mean opp_team SP xwOBA-allowed over the batter's
    # primary team's remaining schedule. Validated PASS 2026-05-24
    # (Δr +0.0137 vs full rh3 v2 baseline, 7/7 per-year positives,
    # holdout 2/2). Cache built by
    # scripts/xfp/build_ros_opp_sp_xwoba_per_hitter.py — see
    # data/research/xfp_cache/ros_opp_sp_xwoba_per_hitter.csv. Joined on
    # (batter, year, split_day); NaN filled with per-year mean (mostly
    # end-of-year batters with no remaining games).
    'ros_opp_sp_xwoba_weighted',
    # Box-score-era ensemble prior (bx v0 hitter leg): vintage ridge prediction
    # of year-T fp_per_pa from the player's T-1 box line, trained only on panel
    # years <= T-1 (no train-on-future). Validated PASS 2026-07-10 as cell B1
    # (Δr +0.0088 vs full baseline on the pre-SB cache; pre-flight on the
    # live-SB BUILDER_VERSION-3 cache +0.0076, holdout mean +0.0072, coef
    # +0.026 — PROMOTE per the pre-registered rule; sign consistency 4/7 on
    # the new substrate, disclosed). Cache built by
    # scripts/xfp/build_bx_priors.py — see
    # data/research/xfp_cache/bx_priors_2018_2026.csv. Joined on
    # (batter, year); NaN (rookies / no qualifying T-1 box line) filled with
    # per-year mean. See bx_ensemble_2026-07-10.md +
    # bx_prior_h_promotion_2026-07-10.md.
    'bx_prior_h',
]
H2_LOCKED_CSV = ROOT / 'data' / 'outputs' / 'seasonality_h2_locked.csv'
XWOBA_RESID_CSV = ROOT / 'data' / 'outputs' / 'hitter_xwoba_residual.csv'

# ADR-0003 phase-5 hard assert: every FEATS entry must have a PASS
# validation_runs record. Backfill completed 2026-05-23 (grandfather
# entries for pre-existing features). Wrap to bypass the sklearn-noise
# filter above.
from plv_clone.models.xfp.validated_signals import check_feats_validated as _check_feats_validated
with warnings.catch_warnings():
    warnings.simplefilter("default", UserWarning)
    _check_feats_validated(RH3_FEATS, target="rh3", strict=True)


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


# Bump to force a cold fit when fit-stage LOGIC changes (data/FEATS changes are
# caught automatically by the content hash).
_FIT_FP_VERSION = 1


# eligibility mask shared by the fit stages (hoisted scaffolding, audit D2)
def _fit_filter(d: pd.DataFrame):
    return (d['pa_to'] >= EVAL_PA_MIN) & (d['ros_pa'] >= ROS_PA_MIN) & (d['year'] != 2020)


def _fit_fingerprint(rolling: pd.DataFrame, feats: list[str]) -> str:
    return _engine.fit_fingerprint(
        rolling, feats, target=TARGET, train_years=TRAIN_YEARS,
        extra=(TARGET, EVAL_PA_MIN, ROS_PA_MIN), fp_version=_FIT_FP_VERSION)


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    return _engine.cross_year_eval_ridge(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=_fit_filter, min_train=100, min_test=30)


def fit_residual_ci(df: pd.DataFrame, feats: list[str], resid: pd.DataFrame | None = None):
    """Residual-based CI table: (split_day, predicted_quartile) -> sigma.

    `resid`: the per-row detail frame cross_year_eval already produced — the
    second LOO pass here was fit-for-fit IDENTICAL to it (same filters, same
    alphas, same folds; audit 2026-07-04, 46.2s/day of duplicate fitting).
    Falls back to the old independent pass when not supplied."""
    return _engine.fit_residual_ci_from(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=_fit_filter, min_train=100, min_test=30, resid=resid)


def train_final(df: pd.DataFrame, feats: list[str]):
    return _engine.train_final_ridge(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=lambda d: (d['pa_to'] >= EVAL_PA_MIN) & (d['ros_pa'] >= ROS_PA_MIN))


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
    # vectorized (audit 2026-07-19): identical to the old row-wise apply —
    # unmapped batters fill with their own year (career_stage 0), then int.
    rolling['career_stage'] = (
        rolling['year'] - rolling['batter'].map(first_year).fillna(rolling['year'])
    ).astype(int)
    print(f'  computed career_stage: range {rolling["career_stage"].min()}-{rolling["career_stage"].max()}')

    # RoS opposing-SP schedule strength (validated 2026-05-24, PASS Δr +0.0137).
    # Cache source: scripts/xfp/build_ros_opp_sp_xwoba_per_hitter.py. Merge
    # mirrors the validation harness (attach() in
    # validate_ros_opp_sp_xwoba_weighted.py).
    if ROS_OPP_SP_CSV.exists():
        opp_sp = pd.read_csv(ROS_OPP_SP_CSV)[
            ['batter', 'year', 'split_day', 'ros_opp_sp_xwoba_weighted']
        ]
        rolling = rolling.merge(opp_sp, on=['batter', 'year', 'split_day'], how='left')
        n_missing = int(rolling['ros_opp_sp_xwoba_weighted'].isna().sum())
        # HARD GUARD (audit 2026-07-04): the cache froze at split 58 for ~6 weeks
        # and this fillna silently constant-filled 100% of projection rows —
        # a VALIDATED feature served a year-mean while looking alive. If the
        # majority of CURRENT-SEASON rows are NaN pre-fill, the cache is frozen
        # again: fail loudly (refresh step 1.9 rebuilds it daily).
        _cur_yr = int(rolling['year'].max())
        _cur = rolling[rolling['year'] == _cur_yr]
        _cur_nan = float(_cur['ros_opp_sp_xwoba_weighted'].isna().mean()) if len(_cur) else 0.0
        if _cur_nan > 0.50:
            raise RuntimeError(
                f"ros_opp_sp_xwoba_weighted: {_cur_nan:.0%} of {_cur_yr} rows are NaN pre-fill — "
                "the ros schedule-strength cache looks FROZEN (see "
                "build_ros_schedule caches / refresh step 1.9). Refusing to "
                "silently constant-fill a validated feature.")
        year_means = rolling.groupby('year')['ros_opp_sp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(year_means)
        rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(
            rolling['ros_opp_sp_xwoba_weighted'].mean()
        )
        print(f'  ros_opp_sp_xwoba_weighted missing pre-fill: {n_missing}/{len(rolling)} '
              f'({n_missing / max(len(rolling), 1):.1%}) — filled with year mean')
    else:
        raise FileNotFoundError(
            f'Missing required RoS opp-SP cache: {ROS_OPP_SP_CSV}. '
            'Run scripts/xfp/build_ros_opp_sp_xwoba_per_hitter.py.'
        )

    # Box-score-era ensemble prior (validated 2026-07-10, B1 PASS + pre-flight
    # PROMOTE on the live-SB cache). Cache source: scripts/xfp/build_bx_priors.py.
    # Merge mirrors the validation harness (_merge_bx in validate_bx_ensemble.py):
    # (batter, year) mlbam join, per-year-mean fill.
    if BX_PRIORS_CSV.exists():
        bx = pd.read_csv(BX_PRIORS_CSV)[['mlbam', 'year', 'bx_prior_h']].rename(
            columns={'mlbam': 'batter'})
        rolling = rolling.merge(bx, on=['batter', 'year'], how='left')
        n_missing = int(rolling['bx_prior_h'].isna().sum())
        # HARD GUARD (mirrors ros_opp_sp_xwoba_weighted, audit 2026-07-04): the
        # bx prior is built from COMPLETED T-1 seasons, so ~35-40% NaN (rookies /
        # sub-floor T-1 lines) is the healthy state. If the MAJORITY of
        # current-season rows are NaN pre-fill, the cache is stale/broken (e.g.
        # season rolled over without a build_bx_priors.py rerun) and the fill
        # would silently constant-serve a validated feature: fail loudly.
        _cur_yr = int(rolling['year'].max())
        _cur = rolling[rolling['year'] == _cur_yr]
        _cur_nan = float(_cur['bx_prior_h'].isna().mean()) if len(_cur) else 0.0
        if _cur_nan > 0.50:
            raise RuntimeError(
                f"bx_prior_h: {_cur_nan:.0%} of {_cur_yr} rows are NaN pre-fill — "
                f"the bx priors cache looks STALE (expected ~35-40% NaN). Rerun "
                "scripts/xfp/build_bx_priors.py (refresh step 1.95). Refusing to "
                "silently constant-fill a validated feature.")
        year_means = rolling.groupby('year')['bx_prior_h'].transform('mean')
        rolling['bx_prior_h'] = rolling['bx_prior_h'].fillna(year_means)
        rolling['bx_prior_h'] = rolling['bx_prior_h'].fillna(rolling['bx_prior_h'].mean())
        print(f'  bx_prior_h missing pre-fill: {n_missing}/{len(rolling)} '
              f'({n_missing / max(len(rolling), 1):.1%}) — filled with year mean')
    else:
        raise FileNotFoundError(
            f'Missing required bx priors cache: {BX_PRIORS_CSV}. '
            'Run scripts/xfp/build_bx_priors.py.'
        )

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
    # ── Fingerprint warm-skip (audit 2026-07-04): the entire fit stage is a
    # deterministic function of the immutable train-year slice + FEATS. On a
    # fingerprint match, load the fitted bundle and jump to projection
    # (~34s -> ~2s). The Rule-9 gate re-runs EXACTLY when it is meaningful —
    # whenever the fingerprint (data or features) changes.
    _fp = _fit_fingerprint(rolling, RH3_FEATS)
    _warm = None
    if MODEL_PKL.exists():
        try:
            _b = joblib.load(MODEL_PKL)
            if _b.get('fit_fingerprint') == _fp:
                _warm = _b
        except Exception:
            _warm = None
    if _warm is not None:
        print('\n[warm-fit] fingerprint match — LOO eval / Rule-9 gate / CI / final '
              'fit loaded from bundle (they re-run whenever train data or FEATS change)')
        per_year = _warm['per_year_r']
        overall = {'r': _warm['cross_year_r'], 'mae': _warm['cross_year_mae'], 'n': None}
        baseline = {'r': _warm['baseline_rh2_r']}
        delta = _warm['delta_r_vs_rh2']
        ci_table = _warm['ci_table']
        overall_sigma = _warm['overall_sigma']
        pipe = _warm['pipeline']
        n_train = _warm['n_train']
    else:
        per_year, overall, _resid_full = cross_year_eval(rolling, RH3_FEATS)
        for y, r in sorted(per_year.items()):
            print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
        print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

        # v2 baseline: drop the v2-added features (xwoba_gap_to + career_stage)
        # AND any _last21 features (legacy gate). This is the actual rh1/rh2-style
        # baseline that v2 should be beating, not "drop last21" alone (which is
        # vacuous when current RH3_FEATS already has no last21 features).
        # Rule 9 hard gate: any feature in v2_added must collectively lift the
        # cross-year r by ≥ +0.005 vs a baseline that drops them. 2026-05-23:
        # xwoba_gap_to removed (verdict MARGINAL re-audit), career_stage demoted
        # to baseline (joint lift below gate). v2_added now empty — gate is
        # vacuous until the next claimed lift lands. ADR-0003.
        # 2026-05-24: promoted ros_opp_sp_xwoba_weighted (rh3 v3). Validation
        # data/research/validation_runs/ros_opp_sp_xwoba_weighted_2026-05-24.md
        # showed Δr +0.0137 vs full rh3 v2 baseline, 7/7 per-year positives,
        # holdout 2/2. Rule 9 hard assert now FIRES meaningfully against the
        # full prior-production baseline (RH3_FEATS minus this one feature).
        # 2026-07-10: promoted bx_prior_h (box-score-era ensemble prior, B1
        # PASS + live-SB pre-flight PROMOTE, bx_ensemble_2026-07-10.md). The
        # gate now asserts the JOINT lift of both promoted features vs a
        # baseline that drops them.
        v2_added: set[str] = {"ros_opp_sp_xwoba_weighted", "bx_prior_h"}
        baseline_feats = [f for f in RH3_FEATS if 'last21' not in f and f not in v2_added]
        _ , baseline, _ = cross_year_eval(rolling, baseline_feats)
        delta = overall['r'] - baseline['r']
        print(f'\n--- Baseline (drops v2 features {sorted(v2_added)} + last21) ---')
        print(f'  Overall: r={baseline["r"]}')
        print(f'  Δr (RH3 v2 − baseline) = {delta:+.4f}  (gate: ≥ +0.005)')
        if v2_added and delta < 0.005:
            # RuntimeError, not assert (audit 2026-07-04): assert vanishes under
            # python -O, silently disabling the Rule-9 promotion gate.
            raise RuntimeError(
                f"Rule 9 gate: Δr={delta:+.4f} below +0.005 for v2 features "
                f"{sorted(v2_added)}. Revert or re-validate.")

        # Confidence interval table
        print('\n--- Building residual-based CI table ---')
        ci_table, overall_sigma = fit_residual_ci(rolling, RH3_FEATS, resid=_resid_full)
        print(f'  overall sigma = {overall_sigma:.4f} FP/PA')

        # Train final + project 2026
        pipe, n_train = train_final(rolling, RH3_FEATS)
        coefs = pipe.named_steps['r'].coef_
        print(f'\n--- Final RH3 pipeline (n_train={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}) ---')
        print('  Top coefficients:')
        for f, c in sorted(zip(RH3_FEATS, coefs), key=lambda x: -abs(x[1]))[:12]:
            print(f'    {f:<26s} {c:+.4f}')


    # Projection for 2026
    # projection year = latest season in the substrate (audit R2: the old
    # hardcoded ==2026 would silently no-op on 2027-01-01)
    proj_year = int(rolling['year'].max())
    df_26 = rolling[rolling['year'] == proj_year].copy()
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
    # (vectorized 2026-07-19, audit item 21/W2 — latest_split is constant here;
    # golden A/B verified byte-identical vs the scalar iterrows loop)
    Z25 = 0.6745
    valid['xfp_rh3_sigma_raw'] = lookup_sigma_vec(
        ci_table, overall_sigma, latest_split,
        valid['xfp_rh3_per_pa'].to_numpy(), pred_buckets)
    # Hetero sigma (validated 2026-06-03, SHIP_HETERO_FOR_HITTERS): per-batter
    # multiplicative factor from a ridge over hitter_ratings_master features
    # (POWER, ev90, contact_pct, iso, ...). CV r2=0.5744; pooled coverage
    # preserved (25.10% -> 25.16%); per-batter coverage spread narrows
    # (8.13pp -> 7.57pp). Factor clamped [0.7, 1.5] and mean-re-centered to
    # 1.0 across active rh3 batters so global calibration is preserved.
    # See data/research/validation_runs/hitter_sigma_heteroskedastic_search.md.
    try:
        _hetero_calib = _load_hetero_calib()
        if HITTER_RATINGS_MASTER.exists():
            _ratings_for_sigma = pd.read_csv(HITTER_RATINGS_MASTER, low_memory=False)
            _active_batters = set(valid['batter'].astype(int).tolist())
            _factor_map = _compute_hetero_factors(
                _ratings_for_sigma, _hetero_calib, batter_subset=_active_batters,
            )
            valid['batter_sigma_factor'] = (
                valid['batter'].astype(int).map(_factor_map).fillna(1.0)
            )
            valid['sigma_calibration_method'] = 'hetero_v1'
        else:
            print(f'  WARNING: {HITTER_RATINGS_MASTER} missing — falling back to global sigma')
            valid['batter_sigma_factor'] = 1.0
            valid['sigma_calibration_method'] = 'global_fallback'
    except FileNotFoundError as _e:
        print(f'  WARNING: hetero sigma calibration unavailable ({_e}) — using global sigma')
        valid['batter_sigma_factor'] = 1.0
        valid['sigma_calibration_method'] = 'global_fallback'
    # Audit the re-centering: mean factor across active batters should be ~1.0
    _mean_factor_active = float(valid['batter_sigma_factor'].mean())
    print(f'  hetero sigma: mean batter_sigma_factor across {len(valid)} active '
          f'batters = {_mean_factor_active:.4f} (target 1.000 ± 0.02)')
    if abs(_mean_factor_active - 1.0) > 0.02:
        print(f'  NOTE: factor mean drift {_mean_factor_active - 1.0:+.4f} '
              f'exceeds ±0.02 — global pooled coverage may shift slightly')
    # Carry the raw global sigma for transparency and apply hetero
    valid['xfp_rh3_sigma_global'] = valid['xfp_rh3_sigma_raw']
    valid['xfp_rh3_sigma_hetero'] = valid['xfp_rh3_sigma_raw'] * valid['batter_sigma_factor']
    # Headline sigma column (back-compat) now reflects hetero band
    valid['xfp_rh3_sigma'] = valid['xfp_rh3_sigma_hetero']
    valid['xfp_rh3_p25'] = (valid['xfp_rh3_per_pa'] - Z25 * valid['xfp_rh3_sigma']).clip(lower=0)
    valid['xfp_rh3_p75'] = valid['xfp_rh3_per_pa'] + Z25 * valid['xfp_rh3_sigma']

    # Recency vs prior signal — gap between in-season & long-run
    valid['recency_form_gap'] = (valid['xwoba_per_pa_last21_sh'] -
                                  valid['xwoba_per_pa_to_sh']).round(4)

    # Per-game
    valid['xfp_rh3_per_game'] = (valid['xfp_rh3_per_pa'] * PA_PER_GAME_LEAGUE).round(2)

    # Names + position
    names = multiyr[multiyr['year'] == proj_year][['batter', 'player_name', 'team']] \
        .drop_duplicates('batter')
    valid = valid.drop_duplicates('batter').merge(names, on='batter', how='left')
    if MASTER_HITTER.exists():
        mh = pd.read_csv(MASTER_HITTER)
        keep = [c for c in ['batter', 'primary_position', 'fantasy_positions',
                            'fantasy_positions_display']
                if c in mh.columns]
        valid = valid.merge(mh[keep], on='batter', how='left')
        # Match-rate visibility guard (audit 2026-07-19 R5): a desynced master
        # CSV silently drops primary_position -> everyone collapses to the
        # UTIL replacement bucket and replacement_delta distorts. Values
        # unchanged — surface the match rate so the failure can't hide.
        if 'primary_position' in valid.columns:
            _pos_match = float(valid['primary_position'].notna().mean())
            print(f'  master_hitter position match rate: {_pos_match:.0%}')
            if _pos_match < 0.5:
                print('  !! WARNING: <50% of hitters matched master_hitter — '
                      'replacement buckets are collapsing to UTIL; the master '
                      'CSV is stale or id-desynced')
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

    # Composite signal for the dashboard (vectorized 2026-07-19, audit item
    # 21/W3 — golden A/B verified byte-identical vs the row-wise _signal()):
    #   hold : replacement_delta / replacement level missing
    #   add  : high-confidence above replacement (p25 still > replacement)
    #   drop : below replacement and even p75 doesn't recover
    # NaN comparisons intentionally match row-wise semantics (NaN > x = False).
    _repl = valid['replacement_xfp_per_pa']
    valid['signal'] = np.select(
        [
            valid['replacement_delta'].isna() | _repl.isna(),
            valid['xfp_rh3_p25'].notna() & (valid['xfp_rh3_p25'] > _repl),
            valid['xfp_rh3_p75'].notna() & (valid['xfp_rh3_p75'] < _repl),
        ],
        ['hold', 'add', 'drop'],
        default='hold',
    )

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
        'fit_fingerprint': _fp,
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
        'xfp_rh3_sigma_raw', 'xfp_rh3_sigma_global', 'xfp_rh3_sigma_hetero',
        'batter_sigma_factor', 'sigma_calibration_method',
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


if __name__ == '__main__':
    main()
