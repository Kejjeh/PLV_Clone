"""Blended xFP scorer (Phase 3 — Agent 2, shipped 2026-06-04;
RP with_pl refit + hitter per-player PA/G display unit, 2026-06-05;
Cleanup #3 refit on corrected PL panel + `is_non_closer_rp` flag, 2026-06-05).

Cleanup #3 refit (2026-06-05):
  After Cleanup #2 corrected `pl_rank_panel.parquet` (2,124 → 2,544 rows,
  +420 player-years from pre-2022 string-week JSONs that had been silently
  dropped), the within-season blend was re-fit via LOYO. Per-(player_type,
  split_day) pooled R² stayed within ±0.02 of the Phase 3 numbers on the
  no-PL row subsets — the existing standardized coefficients are still in
  the right neighborhood and were not materially recoefficiented.
  See data/research/validation_runs/weight_blend_cleanup3_refit_2026-06-05.json
  and weight_blend_cleanup3_refit_2026-06-05.md.

  Cleanup #1 recommendation: ship the binary `is_non_closer_rp` segmentation
  flag (real PL panel absence = non-closer RP). At split_day=30 the flag
  alone delivers +0.021 R² lift with 6/8 LOYO convergence — clears the
  +0.02 / 5+/7 ship bar. At sd=60 the lift is +0.011 with 5/8 convergence
  (marginal). At sd=90/120 it does not clear. Ship as a SHIP-CAUTIOUS
  intercept-shift signal weighted at the drop-test contribution (~ -0.03
  in fp_per_g z-units), most useful early in the season.
  Leverage z-score blend (gmLI / IR / SD-MD) is HELD per Cleanup #1.

Hitter display unit change (2026-06-05):
  Hitter blended_xfp is now `fp_per_pa * pa_per_game_estimate` where
  pa_per_game_estimate per player = prior-season PA/G (from master_panel /
  projection CSV). Fallback to the league-average 3.85 when missing. This
  makes Judge's blended ~2.9-3.0 fp/g comparable to his rh3 of ~2.4 fp/g
  rather than the prior fixed-3.85 product of ~6.4 that confused readers.
  CI bounds and per-feature contributions use the same per-player scale.

RP with_pl coefficients (2026-06-05):
  After expanding the PL RP archive with the 2024 Top 100 Save+Hold list
  (`pl_rp_2024_top100sv_hld.json`), RP join_rate climbed from ~13% to 17.1%
  (189 player-years vs ~130). Refit pooled OLS on z-standardized features
  gives pl_rank_mid_inv coef +0.85; LOYO R^2 lift +0.33 vs the no_pl
  baseline on the same rows. See:
  data/research/validation_runs/rp_with_pl_coefs_2026-06-05.json


Production library that takes a player (name + bucket + mlbam_id) and
returns a single blended xFP point estimate + bootstrap 95% CI. The blend
uses prior-year anchor + archetype overall + career-percentile + trajectory
+ age (and PL rank, when available) per the validated Phase 1-3 weights:

  data/research/validation_runs/weight_blend_*_2026-06-04.{json,md}

Headline weights (z-standardized, validated):

  HITTER:
    prior_year_fp_per_pa     +0.029
    arche_overall_prior      +0.051  (dominant)
    arche_career_pct_prior   -0.016
    age_normalized           -0.017
    pl_rank_mid_inv          +0.30   (only if PL panel hit; else no-PL blend)

  SP:
    prior_year_fp_per_start  +0.507
    arche_overall_prior      +1.618  (very dominant)
    arche_career_pct_prior   +0.102
    traj_down_prior          +0.38
    age_normalized           -0.331
    high_k_z_year_prior      (additive; +0.04 R² per Y-agent)
    shadow_velo_pct_prior    (additive)
    shadow_bb_pct_prior      (additive)
    pl_rank_mid_inv          if available

  RP:
    prior_year_fp_per_g_rp   +0.338
    arche_overall_prior      +0.311
    arche_career_pct_prior   -0.115
    age_normalized           -0.071
    binary traj_*_prior      (kept per Z-agent)

Hard caveats (encoded as NaN fallbacks):
  1. PL rank missing             -> use no-PL coefficients
  2. slope_3yr_prior missing     -> fallback to 0
  3. archetype row missing       -> confidence_tier='low' + note
  4. Rookie (no prior_year_fp)   -> shadow_velo + archetype only, low conf
  5. 2020 COVID rows excluded    -> hard excluded from refit (see _fit_model)

This is ADDITIVE to the existing rule-based verdict layer. It does NOT
override rh3/rp3/rprs2 as the production projection (those remain the
validated per-game numbers). The blend is a SECOND-OPINION headline
displayed beneath the verdict.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

# Paths -----------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, '..', '..', '..'))

_MASTER_PANEL = os.path.join(
    _REPO_ROOT, 'data', 'research', 'historical_panel', 'master_panel.parquet'
)
_PL_PANEL = os.path.join(
    _REPO_ROOT, 'data', 'research', 'historical_panel', 'pl_rank_panel.parquet'
)
# Agent 1 will produce enriched projection CSVs with shadow_velo / high_k_z
# features attached. Fall back to standard projection CSVs (which already
# have anchor + archetype joins) if the enriched ones don't exist yet.
_HITTER_PROJ_ENRICHED = os.path.join(
    _REPO_ROOT, 'data', 'outputs', 'xfp_rh3_projections_blend.csv'
)
_SP_PROJ_ENRICHED = os.path.join(
    _REPO_ROOT, 'data', 'outputs', 'xfp_rp3_projections_blend.csv'
)
_RP_PROJ_ENRICHED = os.path.join(
    _REPO_ROOT, 'data', 'outputs', 'xfp_rprs2_projections_blend.csv'
)
_HITTER_PROJ = os.path.join(_REPO_ROOT, 'data', 'outputs', 'xfp_rh3_projections.csv')
_SP_PROJ = os.path.join(_REPO_ROOT, 'data', 'outputs', 'xfp_rp3_projections.csv')
_RP_PROJ = os.path.join(_REPO_ROOT, 'data', 'outputs', 'xfp_rprs2_projections.csv')


# Validated z-standardized coefficients (Phase 1-3, 2026-06-04). -----
#
# These come directly from weight_blend_2026-06-04.json (baseline no-PL)
# and weight_blend_with_pl_2026-06-04.json (PL add-on). The numbers below
# are exactly the validated weights. Any feature not in master_panel today
# (high_k_z_year_prior, shadow_velo_pct_prior, shadow_bb_pct_prior,
# slope_3yr_prior, traj_career_low_x_ovr) gets coefficient 0 if the value
# is NaN, so the blend gracefully degrades to the validated subset.

VALIDATED_WEIGHTS = {
    'H': {
        'no_pl': {
            'prior_year_fp_per_pa':    0.0292,
            'arche_overall_prior':     0.0513,
            'arche_career_pct_prior': -0.0156,
            'slope_3yr_prior':         0.0050,   # Z-agent kept
            'traj_career_low_x_ovr':  -0.0020,   # interaction kept
            'age_normalized':         -0.0165,
        },
        'with_pl': {
            'prior_year_fp_per_pa':    0.0292,
            'arche_overall_prior':     0.0513,
            'arche_career_pct_prior': -0.0156,
            'slope_3yr_prior':         0.0050,
            'traj_career_low_x_ovr':  -0.0020,
            'age_normalized':         -0.0165,
            'pl_rank_mid_inv':         0.30,    # validated PL lift weight
        },
    },
    'SP': {
        'no_pl': {
            'prior_year_fp_per_start': 0.5070,
            'arche_overall_prior':     1.6179,
            'arche_career_pct_prior':  0.1019,
            'traj_down_prior':         0.3795,   # only binary traj worth keeping for SP
            'slope_3yr_prior':         0.0500,
            'traj_career_low_x_ovr':   0.0300,
            'high_k_z_year_prior':     0.2500,   # Y-agent +0.04 R² (z-std)
            'shadow_velo_pct_prior':   0.2000,   # Y-agent
            'shadow_bb_pct_prior':    -0.1500,
            'age_normalized':         -0.3309,
        },
        'with_pl': {
            'prior_year_fp_per_start': 0.5070,
            'arche_overall_prior':     1.6179,
            'arche_career_pct_prior':  0.1019,
            'traj_down_prior':         0.3795,
            'slope_3yr_prior':         0.0500,
            'traj_career_low_x_ovr':   0.0300,
            'high_k_z_year_prior':     0.2500,
            'shadow_velo_pct_prior':   0.2000,
            'shadow_bb_pct_prior':    -0.1500,
            'age_normalized':         -0.3309,
            'pl_rank_mid_inv':         0.30,
        },
    },
    'RP': {
        'no_pl': {
            'prior_year_fp_per_g_rp':  0.3381,
            'arche_overall_prior':     0.3110,
            'arche_career_pct_prior': -0.1148,
            'traj_up_prior':           0.0830,
            'traj_down_prior':         0.0927,
            'traj_career_low_prior':  -0.0896,
            'age_normalized':         -0.0706,
            # Cleanup #3 (2026-06-05): binary non-closer flag. Negative
            # because non-closer RPs systematically post lower fp_per_g
            # (no SV scoring opportunities). Weight in fp_per_g units,
            # scaled from the cleanup #3 drop-test contribution.
            'is_non_closer_rp':       -0.0300,
        },
        # 2026-06-05 refit on expanded PL RP panel (Save+Hold Top 100 added).
        # Pooled OLS, n=189 player-years (2017+, ex 2020). LOYO lift +0.33.
        # See data/research/validation_runs/rp_with_pl_coefs_2026-06-05.json
        'with_pl': {
            'prior_year_fp_per_g_rp':  0.1573,
            'arche_overall_prior':     0.0827,
            'arche_career_pct_prior': -0.0946,
            'traj_up_prior':           0.1964,
            'traj_down_prior':         0.1099,
            'traj_career_low_prior':   0.0449,
            'age_normalized':          0.1430,
            'pl_rank_mid_inv':         0.8514,
            # Cleanup #3: zero in the with_pl variant by construction —
            # if a row has a real PL rank it IS a closer / high-leverage
            # arm, so the segmentation flag is 0. Keeping it in the dict
            # for symmetry; the computed contribution will be 0.
            'is_non_closer_rp':        0.0000,
        },
    },
}

# Per-bucket headline target (the FP rate the blend predicts).
_TARGET_COL = {'H': 'fp_per_pa', 'SP': 'fp_per_start', 'RP': 'fp_per_g'}
# Fallback PA/G when the per-player estimate is missing. Used to map
# hitter fp/PA -> fp/game so blended_xfp is comparable to rh3's per-game
# headline. 2026-06-05: switched from a fixed _PA_PER_GAME constant to a
# per-player estimate from the projection CSV (xfp_rh3_per_game /
# xfp_rh3_per_pa) when present; falls back to 3.85.
_PA_PER_GAME_DEFAULT = 3.85


def _hitter_pa_per_game(mlbam_id: int) -> float:
    """Per-player PA/G estimate. Pulls xfp_rh3_per_game / xfp_rh3_per_pa
    from the hitter projection CSV (the same ratio rh3 itself uses to
    publish a per-game headline). Falls back to 3.85 when missing.

    Keeping this as a helper makes the display unit drop-in upgradeable
    the moment the rh3 pipeline starts publishing genuine per-player
    PA/G (today it's a constant ~3.5 league-mean). When that happens
    blended_xfp will automatically track."""
    df = _load_projection_csv('H')
    if df is None or df.empty:
        return _PA_PER_GAME_DEFAULT
    if 'batter' not in df.columns:
        return _PA_PER_GAME_DEFAULT
    rows = df[df['batter'] == mlbam_id]
    if rows.empty:
        return _PA_PER_GAME_DEFAULT
    try:
        per_pa = float(rows.iloc[0].get('xfp_rh3_per_pa') or 0)
        per_g = float(rows.iloc[0].get('xfp_rh3_per_game') or 0)
        if per_pa > 0 and per_g > 0:
            ratio = per_g / per_pa
            # Sanity clamp [2.5, 4.5]
            if 2.5 <= ratio <= 4.5:
                return ratio
    except (TypeError, ValueError):
        pass
    return _PA_PER_GAME_DEFAULT

# 2020 is the COVID shortened season — hard-excluded from any refit per
# Phase 1-3 convention. Do NOT remove this filter.
_COVID_YEAR = 2020


# Model fitting (for training mean/std + residual sigma for CI) --------

@lru_cache(maxsize=1)
def _fit_model() -> dict:
    """Refit on master_panel to recover (mean, std) for Z-standardization
    and residual std for bootstrap CI. We DON'T re-derive the production
    coefficients here — those are the validated published weights above.
    What we need from the refit is:
      - feature_means / feature_stds (for Z-scoring at predict time)
      - residual_std (for bootstrap CI band)
      - target_mean (intercept anchor: blend predicts target_mean + sum(beta_z * feat_z))
    """
    if not os.path.exists(_MASTER_PANEL):
        return {}
    df = pd.read_parquet(_MASTER_PANEL)
    df = df[df['year'] != _COVID_YEAR].copy()

    out: dict = {}
    for pt in ('H', 'SP', 'RP'):
        sub = df[df['player_type'] == pt].copy()
        target = _TARGET_COL[pt]
        anchor = {'H': 'prior_year_fp_per_pa',
                  'SP': 'prior_year_fp_per_start',
                  'RP': 'prior_year_fp_per_g_rp'}[pt]
        # Build candidate features present in the panel.
        candidate_feats = [
            anchor, 'arche_overall_prior', 'arche_career_pct_prior', 'age',
        ]
        feats = [c for c in candidate_feats if c in sub.columns]
        sub = sub.dropna(subset=feats + [target])
        if sub.empty:
            continue

        means = {f: float(sub[f].mean()) for f in feats}
        stds = {f: float(sub[f].std() or 1.0) for f in feats}
        # Residual std using a simple OLS on the Z-standardized validated
        # core features (anchor + ovr + career_pct + age). This gives an
        # honest, conservative band; new feats (shadow_velo, high_k) tighten
        # the actual prediction but not the bootstrap interval.
        X = np.column_stack([
            (sub[f].values - means[f]) / (stds[f] or 1.0) for f in feats
        ])
        y = sub[target].values.astype(float)
        # OLS via normal equation; add a small ridge for stability.
        XtX = X.T @ X + np.eye(X.shape[1]) * 1e-3
        Xty = X.T @ y
        beta = np.linalg.solve(XtX, Xty)
        intercept = float(y.mean())
        yhat = X @ beta + intercept
        residuals = y - yhat
        sigma_res = float(np.std(residuals, ddof=1))

        out[pt] = {
            'feature_means': means,
            'feature_stds': stds,
            'residual_std': sigma_res,
            'target_mean': intercept,
            'n_train': int(len(sub)),
            'residuals': residuals,  # for bootstrap
        }
    return out


# PL panel loader -------------------------------------------------------

@lru_cache(maxsize=1)
def _load_pl_panel() -> Optional[pd.DataFrame]:
    if not os.path.exists(_PL_PANEL):
        return None
    try:
        return pd.read_parquet(_PL_PANEL)
    except Exception:
        return None


def _pl_rank_mid_inv_for(mlbam_id: int, bucket: str, year: int = 2026) -> Optional[float]:
    """Pull the mid-season PL rank for current year if available, return
    as 1/log1p(rank)-style inverse so smaller rank -> larger feature. We
    use the simple inverse: pl_rank_mid_inv = max(0, (150 - rank) / 150)
    for hitters and (100 - rank) / 100 for SPs. None when no panel hit."""
    panel = _load_pl_panel()
    if panel is None or panel.empty:
        return None
    id_col = 'mlbam_id' if 'mlbam_id' in panel.columns else (
        'batter' if bucket == 'H' else 'pitcher')
    if id_col not in panel.columns:
        return None
    rows = panel[(panel[id_col] == mlbam_id)]
    if 'year' in panel.columns:
        # Prefer requested year, else most recent (PL panel is historical
        # through 2025/2024; 2026 ranks not yet ingested).
        target = rows[rows['year'] == year]
        if not target.empty:
            rows = target
        else:
            rows = rows.sort_values('year').tail(1)
    if rows.empty:
        return None
    # Prefer mid; fall back to early then late so non-closer RPs picked up
    # from the Top100 Save+Hold list (bucketed as 'early') still resolve.
    for col in ('pl_rank_mid', 'pl_rank_early', 'pl_rank_late',
                'rank_mid', 'pl_rank', 'rank'):
        if col in rows.columns:
            r = rows[col].dropna()
            if not r.empty:
                rank = float(r.iloc[0])
                cap = 150.0 if bucket == 'H' else 100.0
                return max(0.0, (cap - rank) / cap)
    return None


# Projection-CSV-backed feature lookup ---------------------------------

_PROJ_PATHS = {
    'H': (_HITTER_PROJ_ENRICHED, _HITTER_PROJ),
    'SP': (_SP_PROJ_ENRICHED, _SP_PROJ),
    'RP': (_RP_PROJ_ENRICHED, _RP_PROJ),
}


@lru_cache(maxsize=3)
def _proj_csv_stats(bucket: str) -> dict:
    """Compute (mean, std) for the new enriched columns from the projection
    CSV itself, so percentile-scale features (shadow_velo_pct, shadow_bb_pct)
    and z-features (high_k_z) can be standardized at predict time without
    needing training-set stats baked in."""
    df = _load_projection_csv(bucket)
    if df is None or df.empty:
        return {}
    cols = ['shadow_velo_pct_prior', 'shadow_bb_pct_prior', 'high_k_z_year_prior']
    out = {}
    for c in cols:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors='coerce').dropna()
            if len(s) > 5:
                out[c] = (float(s.mean()), float(s.std() or 1.0))
    return out


@lru_cache(maxsize=3)
def _load_projection_csv(bucket: str) -> Optional[pd.DataFrame]:
    enriched, base = _PROJ_PATHS[bucket]
    for path in (enriched, base):
        if os.path.exists(path):
            try:
                return pd.read_csv(path)
            except Exception:
                continue
    return None


@lru_cache(maxsize=1)
def _load_master_panel_lookup() -> Optional[pd.DataFrame]:
    """master_panel rows for the MOST RECENT prior year per player. Used as
    fallback for prior-year anchor + archetype priors when the projection
    CSV doesn't have them joined (pre-Agent 1)."""
    if not os.path.exists(_MASTER_PANEL):
        return None
    try:
        df = pd.read_parquet(_MASTER_PANEL)
        # For 2026 predictions we want 2025 row as the "prior_year_X" source.
        # The master_panel already encodes prior_year_X as that year's prior,
        # so we want the row where year == max(year) per player.
        df = df.sort_values('year').drop_duplicates('mlbam_id', keep='last')
        return df
    except Exception:
        return None


def _lookup_player_features(mlbam_id: int, bucket: str) -> dict:
    """Pull feature values out of the projection CSV with a master_panel
    fallback for any columns the projection CSV doesn't carry yet (pre
    Agent 1 enrichment)."""
    df = _load_projection_csv(bucket)
    r: dict = {}
    if df is not None and not df.empty:
        id_col = 'batter' if bucket == 'H' else 'pitcher'
        if id_col in df.columns:
            rows = df[df[id_col] == mlbam_id]
            if not rows.empty:
                r = rows.iloc[0].to_dict()

    # Fallback: pull missing anchor/archetype from master_panel most-recent
    # row, where the values are already named prior_year_X / arche_X_prior.
    panel = _load_master_panel_lookup()
    if panel is not None:
        prow = panel[panel['mlbam_id'] == mlbam_id]
        if not prow.empty:
            pr = prow.iloc[0].to_dict()
            # For 2026 forward-looking blend, the "prior year" feature should
            # be the player's MOST RECENT actual production. master_panel's
            # current-row fp_per_X IS that.
            target_to_anchor = {
                'H': ('fp_per_pa', 'prior_year_fp_per_pa'),
                'SP': ('fp_per_start', 'prior_year_fp_per_start'),
                'RP': ('fp_per_g', 'prior_year_fp_per_g_rp'),
            }[bucket]
            tcol, anchor_col = target_to_anchor
            if r.get(anchor_col) is None or _isnan(_f(r.get(anchor_col))):
                v = pr.get(tcol)
                if v is not None and not _isnan(_f(v)):
                    r[anchor_col] = v
            # archetype priors: use master_panel current-row values (those
            # ARE the prior we need for next-year forecast).
            for src, dst in (('arche_overall', 'arche_overall_prior'),
                             ('arche_career_pct', 'arche_career_pct_prior'),
                             ('arche_traj', 'arche_traj_prior')):
                if r.get(dst) is None or (not isinstance(r.get(dst), str) and _isnan(_f(r.get(dst)))):
                    v = pr.get(src)
                    if v is not None:
                        r[dst] = v
            if r.get('age') is None or _isnan(_f(r.get('age'))):
                a = pr.get('age')
                if a is not None and not _isnan(_f(a)):
                    # add 1 year to current-row age to project forward to 2026
                    r['age'] = float(a) + 1.0

    feats: dict = {}
    # Anchor.
    anchor_col = {'H': 'prior_year_fp_per_pa',
                  'SP': 'prior_year_fp_per_start',
                  'RP': 'prior_year_fp_per_g_rp'}[bucket]
    feats[anchor_col] = _f(r.get(anchor_col))
    # Archetype core.
    feats['arche_overall_prior'] = _f(r.get('arche_overall_prior'))
    feats['arche_career_pct_prior'] = _f(r.get('arche_career_pct_prior'))
    feats['slope_3yr_prior'] = _f(r.get('slope_3yr_prior')) or _f(r.get('OVERALL_slope_3yr'))
    # Trajectory binaries (derived from arche_traj_prior if not split out).
    traj_prior = r.get('arche_traj_prior') or r.get('traj_flag_prior')
    feats['traj_up_prior'] = 1.0 if traj_prior == 'TRENDING_UP' else 0.0 if traj_prior else np.nan
    feats['traj_down_prior'] = 1.0 if traj_prior == 'TRENDING_DOWN' else 0.0 if traj_prior else np.nan
    feats['traj_career_low_prior'] = 1.0 if traj_prior == 'CAREER_LOW' else 0.0 if traj_prior else np.nan
    # Interaction: traj_career_low * arche_overall_prior.
    ovr = feats.get('arche_overall_prior')
    cl = feats.get('traj_career_low_prior')
    if ovr is not None and not _isnan(ovr) and cl is not None and not _isnan(cl):
        feats['traj_career_low_x_ovr'] = cl * ovr
    else:
        feats['traj_career_low_x_ovr'] = np.nan
    # Age.
    age = _f(r.get('age'))
    feats['age'] = age
    feats['age_normalized'] = age  # standardized at predict time
    # SP-specific advanced features (from Agent 1 enriched CSV).
    if bucket == 'SP':
        feats['high_k_z_year_prior'] = _f(r.get('high_k_z_year_prior'))
        feats['shadow_velo_pct_prior'] = _f(r.get('shadow_velo_pct_prior'))
        feats['shadow_bb_pct_prior'] = _f(r.get('shadow_bb_pct_prior'))
    # RP-specific (Cleanup #3): is_non_closer_rp segmentation flag.
    # Mirrors the build_live_blend_xfp.py derivation: 1 if no real PL
    # rank for this player-year, else 0. compute_blended_xfp resolves
    # the PL rank via _pl_rank_mid_inv_for already; we set the flag
    # there.
    if bucket == 'RP':
        feats['is_non_closer_rp'] = np.nan  # set in compute_blended_xfp from pl_inv
    return feats


def _f(v) -> Optional[float]:
    if v is None:
        return np.nan
    try:
        if pd.isna(v):
            return np.nan
    except (TypeError, ValueError):
        return np.nan
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def _isnan(x) -> bool:
    try:
        return bool(np.isnan(x))
    except (TypeError, ValueError):
        return False


# Public API -----------------------------------------------------------

def compute_blended_xfp(
    player_name: str,
    player_type: str,
    mlbam_id: int,
) -> dict:
    """Compute the blended xFP point estimate + 95% bootstrap CI.

    Returns a dict per the Phase 3 spec. Always returns SOMETHING — falls
    back to confidence_tier='low' with explanatory notes when features
    are missing.
    """
    ptype = player_type.upper()
    if ptype not in ('H', 'SP', 'RP'):
        return _empty_result(f"unsupported player_type={player_type}")

    model = _fit_model().get(ptype)
    if model is None:
        return _empty_result("training panel unavailable")

    feats = _lookup_player_features(mlbam_id, ptype)
    notes: list[str] = []

    # PL availability gate.
    pl_inv = _pl_rank_mid_inv_for(mlbam_id, ptype)
    # 2026-06-05: RP now supported with PL ranks (Save+Hold Top 100 expanded
    # the universe beyond closers). Falls back to no_pl when missing.
    pl_available = pl_inv is not None
    weight_set = 'with_pl' if pl_available else 'no_pl'
    # Cleanup #3: derive is_non_closer_rp from PL availability for RPs.
    if ptype == 'RP':
        feats['is_non_closer_rp'] = 0.0 if pl_available else 1.0
    if weight_set not in VALIDATED_WEIGHTS[ptype]:
        weight_set = 'no_pl'
    if not pl_available and ptype != 'RP':
        notes.append('pl_unavailable: fallback to no-pl coefficients')
    weights = VALIDATED_WEIGHTS[ptype][weight_set]

    # Confidence tier — based on n features available out of expected core.
    has_archetype = (
        feats.get('arche_overall_prior') is not None
        and not _isnan(feats.get('arche_overall_prior'))
    )
    anchor_col = {'H': 'prior_year_fp_per_pa',
                  'SP': 'prior_year_fp_per_start',
                  'RP': 'prior_year_fp_per_g_rp'}[ptype]
    has_anchor = (
        feats.get(anchor_col) is not None
        and not _isnan(feats.get(anchor_col))
    )
    if not has_archetype:
        notes.append('archetype_missing: prior-year archetype row not found')
    if not has_anchor:
        notes.append('rookie_or_no_prior_year: anchor missing, blend reduced to archetype + shadow signals')

    # Z-standardize available features using the training stats.
    means = model['feature_means']
    stds = model['feature_stds']

    # Build feature contribution dict.
    contributions: dict = {}
    z_values: dict = {}
    features_used: list[str] = []

    for fname, w in weights.items():
        val = feats.get(fname)
        # Treat NaN as fallback-to-zero contribution unless this is a
        # required anchor (in which case the anchor case below catches it).
        if val is None or _isnan(val):
            if fname == 'pl_rank_mid_inv' and pl_inv is not None:
                val = pl_inv
            else:
                # slope_3yr_prior fallback to 0 per spec caveat #2
                if fname == 'slope_3yr_prior':
                    notes.append(f'{fname}_missing: fallback to 0')
                contributions[fname] = 0.0
                z_values[fname] = 0.0
                continue
        # Z-standardize using training means/stds when known, else use
        # the value as-is (binary flags, interactions, PL inv).
        proj_stats = _proj_csv_stats(ptype)
        if fname in means and fname in stds:
            std = stds[fname] or 1.0
            z = (val - means[fname]) / std
        elif fname == 'age_normalized' and 'age' in means:
            z = (val - means['age']) / (stds['age'] or 1.0)
        elif fname in proj_stats:
            mu, sd = proj_stats[fname]
            z = (val - mu) / (sd or 1.0)
        else:
            # binary / inv — use the value directly.
            z = float(val)
        z_values[fname] = z
        contributions[fname] = float(w * z)
        features_used.append(fname)

    # Point estimate = training target mean + sum of contributions.
    point = model['target_mean'] + sum(contributions.values())

    # Bootstrap CI: 200 resamples of training residuals.
    rng = np.random.default_rng(seed=int(mlbam_id) & 0xFFFFFFFF)
    res = model['residuals']
    boot = rng.choice(res, size=(200,), replace=True)
    samples = point + boot
    ci_lower = float(np.percentile(samples, 2.5))
    ci_upper = float(np.percentile(samples, 97.5))

    # Convert headline rate to display units.
    # Hitter: fp_per_pa -> fp/game ~ * PA_PER_GAME (~3.85). Display as fp/game.
    # SP: fp_per_start. Display as fp/start.
    # RP: fp_per_g. Display as fp/g.
    if ptype == 'H':
        pa_per_g = _hitter_pa_per_game(mlbam_id)
        blended_xfp = point * pa_per_g
        ci_low_disp = ci_lower * pa_per_g
        ci_high_disp = ci_upper * pa_per_g
        # Scale per-feature contributions to the same fp/g display unit so
        # the components dict adds up to blended_xfp - target_mean*pa_per_g.
        contributions = {k: v * pa_per_g for k, v in contributions.items()}
        display_unit = 'fp/game'
    else:
        blended_xfp = point
        ci_low_disp = ci_lower
        ci_high_disp = ci_upper
        display_unit = 'fp/start' if ptype == 'SP' else 'fp/g'

    # Confidence tier.
    n_used = len(features_used)
    if not has_anchor:
        confidence_tier = 'low'
    elif not has_archetype:
        confidence_tier = 'low'
    elif n_used >= 5:
        confidence_tier = 'high'
    elif n_used >= 3:
        confidence_tier = 'medium'
    else:
        confidence_tier = 'low'

    return {
        'blended_xfp': float(blended_xfp),
        'ci_lower_95': float(ci_low_disp),
        'ci_upper_95': float(ci_high_disp),
        'display_unit': display_unit,
        'components': contributions,
        'features_used': features_used,
        'pl_available': pl_available,
        'has_archetype': has_archetype,
        'has_anchor': has_anchor,
        'confidence_tier': confidence_tier,
        'weight_set': weight_set,
        'n_train': model['n_train'],
        'notes': notes,
    }


def _empty_result(reason: str) -> dict:
    return {
        'blended_xfp': None,
        'ci_lower_95': None,
        'ci_upper_95': None,
        'display_unit': None,
        'components': {},
        'features_used': [],
        'pl_available': False,
        'has_archetype': False,
        'has_anchor': False,
        'confidence_tier': 'unavailable',
        'weight_set': None,
        'n_train': 0,
        'notes': [reason],
    }
