"""
Hitter fantasy-point projection layer.

Translates Process+, Decision+, Contact+, Power+, and pitch-surface stats
into expected per-PA fantasy-point rates, calibrated from historical data.

Rate models (calibrated via linear regression on 2023-2024 data):
  BB/PA   ~ chase_pct + decision_plus
  K/PA    ~ whiff_pct + chase_pct
  TB/PA   ~ in_play_pct + xwoba_actual + power_plus

Derived (empirical multipliers, not fit by regression):
  H/PA    = xwoba_actual * 0.85 - 0.015   (xwOBA -> BA proxy)
  R/PA    = 0.37 * (H/PA + BB/PA + HBP/PA)
  RBI/PA  = 0.24 * TB/PA + 0.06 * (H/PA + BB/PA + HBP/PA)
  HBP/PA  = league average constant
  SB/PA   = shrinkage estimate from actual events + league average prior
            Formula: (observed_sb/pa * pa + league_avg * 150) / (pa + 150)
            Requires sb_per_pa_raw column in input DataFrame (added by build_fantasy_exports).
            Falls back to league average (0.020) when column is absent.

Outputs:
  core_fp_per_pa : TB + BB + K + HBP + SB  (skill-driven; preferred ranking)
  full_fp_per_pa : R + TB + RBI + BB + K + HBP + SB  (context-inflated; companion view)
  fp_per_pa      : alias for full_fp_per_pa (backward compat)

See docs/fantasy_points_methodology.md for full accuracy notes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.utils.logging import get_logger
from .scoring import LeagueScoring, hitter_fp_per_pa, hitter_core_fp_per_pa

logger = get_logger(__name__)

_CALIB_FILE = "hitter_fantasy_calibration.json"
_SB_SHRINK_PA = 150.0   # prior weight for SB shrinkage toward league average

# ── Event sets ────────────────────────────────────────────────────────────────

_K_EVENTS  = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
_H_EVENTS  = {"single", "double", "triple", "home_run"}
_TB_MAP    = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
_SB_EVENTS = {"stolen_base_2b", "stolen_base_3b", "stolen_base_home"}
_NON_PA    = {
    "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "wild_pitch", "passed_ball", "balk",
}

# ── League averages (2023-2024 MLB) used as pre-calibration defaults ──────────

_LEAGUE_AVG: dict[str, float] = {
    "bb_rate":  0.085,
    "k_rate":   0.228,
    "tb_rate":  0.365,
    "hbp_rate": 0.009,
    "h_rate":   0.248,
    "r_rate":   0.105,
    "rbi_rate": 0.095,
    "sb_rate":  0.020,
}


# ── Calibration ───────────────────────────────────────────────────────────────

def calibrate(
    processed_dir: Path,
    outputs_dir: Path,
    models_dir: Path,
    calibration_years: list[int] | None = None,
) -> dict:
    """Fit hitter rate models from historical pitch data and save coefficients.

    Reads process_plus_scores parquets + master_hitter CSVs for each
    calibration year. Computes actual rates from events, joins with model
    scores, fits linear regressions, and saves to models_dir.

    Returns the calibration dict (same as what's saved to JSON).
    """
    from sklearn.linear_model import LinearRegression
    from plv_clone.utils.io import read_parquet

    years = calibration_years or [2023, 2024]
    logger.info("Calibrating hitter fantasy model on years=%s", years)

    records = []
    for yr in years:
        pp_dir = processed_dir / f"process_plus_scores/year={yr}"
        mh_path = outputs_dir / f"master_hitter_{yr}.csv"
        if not pp_dir.exists() or not mh_path.exists():
            logger.warning("Skipping year=%d: missing processed scores or master_hitter.", yr)
            continue

        pp_df = read_parquet(pp_dir)
        mh_df = pd.read_csv(mh_path)

        actual = _compute_hitter_actuals(pp_df)
        merged = mh_df.merge(actual, on="batter", how="inner")
        merged["year"] = yr
        records.append(merged)
        logger.info("  year=%d: %d hitters with both scores and actuals", yr, len(merged))

    if not records:
        logger.warning("No calibration data found. Using default coefficients.")
        return _default_calibration()

    df = pd.concat(records, ignore_index=True)
    df = df[df["pa"] >= 50].dropna(subset=[
        "chase_pct", "decision_plus", "whiff_pct", "contact_plus",
        "xwoba_actual", "power_plus",
        "bb_rate", "k_rate", "tb_rate",
    ])
    logger.info("Calibration dataset: %d hitter-seasons", len(df))

    calib = {"calibration_years": years, "n_samples": len(df), "league_averages": _LEAGUE_AVG}

    # ── Fit: BB/PA ~ chase_pct + decision_plus ───────────────────────────
    calib["bb_model"] = _fit_linear(
        df,
        features=["chase_pct", "decision_plus"],
        target="bb_rate",
        label="BB/PA",
    )

    # ── Fit: K/PA ~ whiff_pct + chase_pct ────────────────────────────────
    calib["k_model"] = _fit_linear(
        df,
        features=["whiff_pct", "chase_pct"],
        target="k_rate",
        label="K/PA",
    )

    # ── Fit: TB/PA ~ in_play_pct + xwoba_actual + power_plus ─────────────
    # in_play_pct is needed because TB/PA = contact_rate × quality_of_contact
    calib["tb_model"] = _fit_linear(
        df,
        features=["in_play_pct", "xwoba_actual", "power_plus"],
        target="tb_rate",
        label="TB/PA",
    )

    path = models_dir / _CALIB_FILE
    models_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(calib, indent=2))
    logger.info("Hitter calibration saved to %s (n=%d)", path, len(df))
    return calib


def load_calibration(models_dir: Path) -> dict:
    path = models_dir / _CALIB_FILE
    if path.exists():
        return json.loads(path.read_text())
    logger.info("No hitter calibration found — using defaults.")
    return _default_calibration()


# ── Projection ────────────────────────────────────────────────────────────────

def project(
    master_hitter: pd.DataFrame,
    scoring: LeagueScoring,
    coefs: dict | None = None,
    pa_per_game: float = 3.5,
) -> pd.DataFrame:
    """Add expected fantasy rate and FP columns to master_hitter.

    Parameters
    ----------
    master_hitter : DataFrame from master_hitter_YYYY.csv.
                    If it contains a ``sb_per_pa_raw`` column (added by
                    build_fantasy_exports.run()), that is used for the
                    shrinkage-based SB estimate. Otherwise falls back to
                    league average.
    scoring       : LeagueScoring with your league's weights
    coefs         : Calibration dict from calibrate() or load_calibration()
    pa_per_game   : Playing-time assumption (default 3.5 PA/game for starters)

    Added columns:
      est_bb_rate, est_k_rate, est_tb_rate,
      est_hbp_rate, est_h_rate, est_r_rate, est_rbi_rate, est_sb_rate,
      core_fp_per_pa  (TB + BB + K + HBP + SB — skill-driven),
      full_fp_per_pa  (R + TB + RBI + BB + K + HBP + SB — full context),
      fp_per_pa       (alias for full_fp_per_pa, backward compat),
      fp_per_game     (full_fp_per_pa × pa_per_game)
    """
    c = coefs or load_calibration(Path("."))  # caller should pass proper path
    df = master_hitter.copy()

    # ── Estimated rates ───────────────────────────────────────────────────
    df["est_bb_rate"]  = _apply_model(df, c["bb_model"])
    df["est_k_rate"]   = _apply_model(df, c["k_model"])
    df["est_tb_rate"]  = _apply_model(df, c["tb_model"])
    df["est_hbp_rate"] = c["league_averages"].get("hbp_rate", 0.009)

    # H proxy: xwOBA -> batting average (empirical linear)
    if "xwoba_actual" in df.columns:
        df["est_h_rate"] = (df["xwoba_actual"] * 0.85 - 0.015).clip(lower=0.100, upper=0.450)
    else:
        df["est_h_rate"] = c["league_averages"].get("h_rate", 0.248)

    # R and RBI: empirical multipliers on OBP proxy and TB
    obp_proxy = (df["est_h_rate"] + df["est_bb_rate"] + df["est_hbp_rate"]).clip(lower=0.15)
    df["est_r_rate"]   = (0.37 * obp_proxy).round(4)
    df["est_rbi_rate"] = (0.24 * df["est_tb_rate"] + 0.06 * obp_proxy).round(4)

    # Clip rates to realistic ranges
    df["est_bb_rate"]  = df["est_bb_rate"].clip(lower=0.010, upper=0.250)
    df["est_k_rate"]   = df["est_k_rate"].clip(lower=0.030, upper=0.450)
    df["est_tb_rate"]  = df["est_tb_rate"].clip(lower=0.100, upper=0.700)

    # ── SB proxy: shrinkage toward league average ─────────────────────────
    # Formula: (observed_rate * pa + league_avg * SHRINK_PA) / (pa + SHRINK_PA)
    # At low PA the estimate stays near league avg; at high PA it tracks actual.
    league_sb = c["league_averages"].get("sb_rate", 0.020)
    if "sb_per_pa_raw" in df.columns:
        sb_raw = df["sb_per_pa_raw"].fillna(league_sb)
        pa_col = df["pa"].clip(lower=0) if "pa" in df.columns else pd.Series(0.0, index=df.index)
        df["est_sb_rate"] = (
            (sb_raw * pa_col + league_sb * _SB_SHRINK_PA)
            / (pa_col + _SB_SHRINK_PA)
        ).clip(lower=0.0, upper=0.30).round(4)
    else:
        df["est_sb_rate"] = league_sb

    # ── Core FP (skill-driven: TB, BB, K, HBP, SB) ───────────────────────
    df["core_fp_per_pa"] = df.apply(
        lambda r: hitter_core_fp_per_pa(
            tb_per_pa=r["est_tb_rate"],
            bb_per_pa=r["est_bb_rate"],
            k_per_pa=r["est_k_rate"],
            hbp_per_pa=r["est_hbp_rate"],
            sb_per_pa=r["est_sb_rate"],
            scoring=scoring,
        ),
        axis=1,
    ).round(4)

    # ── Full FP (includes context-dependent R and RBI) ────────────────────
    df["full_fp_per_pa"] = df.apply(
        lambda r: hitter_fp_per_pa(
            r_per_pa=r["est_r_rate"],
            tb_per_pa=r["est_tb_rate"],
            rbi_per_pa=r["est_rbi_rate"],
            bb_per_pa=r["est_bb_rate"],
            k_per_pa=r["est_k_rate"],
            hbp_per_pa=r["est_hbp_rate"],
            sb_per_pa=r["est_sb_rate"],
            scoring=scoring,
        ),
        axis=1,
    ).round(4)

    # Backward-compat alias
    df["fp_per_pa"]   = df["full_fp_per_pa"]
    df["fp_per_game"] = (df["full_fp_per_pa"] * pa_per_game).round(3)

    return df


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_hitter_actuals(pp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-batter actual rate stats from pitch-level events."""
    events = pp_df.dropna(subset=["events"]).copy()
    events = events[events["events"].astype(str).str.strip() != ""]

    # SB: count before filtering to PA events
    sb = (
        events[events["events"].isin(_SB_EVENTS)]
        .groupby("batter").size()
        .rename("sb")
    )

    pa = events[~events["events"].isin(_NON_PA)].copy()
    # Use events strings for PA-level outcomes (pitch-level flags like is_walk
    # capture the individual pitch, not the PA terminal outcome)
    pa["is_bb"]  = pa["events"].isin({"walk", "intent_walk"})
    pa["is_k"]   = pa["events"].isin(_K_EVENTS)
    pa["is_hbp"] = pa["events"] == "hit_by_pitch"
    pa["is_hit"] = pa["events"].isin(_H_EVENTS)
    pa["tb"]     = pa["events"].map(_TB_MAP).fillna(0)

    stats = pa.groupby("batter").agg(
        pa_actual=("batter", "count"),
        bb=("is_bb", "sum"),
        k=("is_k", "sum"),
        hbp=("is_hbp", "sum"),
        h=("is_hit", "sum"),
        tb=("tb", "sum"),
    ).reset_index()

    stats = stats.merge(sb, on="batter", how="left").fillna({"sb": 0})

    denom = stats["pa_actual"].clip(lower=1)
    for col in ("bb", "k", "hbp", "h", "tb", "sb"):
        stats[f"{col}_rate"] = (stats[col] / denom).round(5)

    return stats


def _fit_linear(df: pd.DataFrame, features: list[str], target: str, label: str) -> dict:
    """Fit a linear regression and return a serialisable coefficient dict."""
    from sklearn.linear_model import LinearRegression

    X = df[features].values
    y = df[target].values
    mask = ~(np.isnan(X).any(axis=1) | np.isnan(y))
    X, y = X[mask], y[mask]

    model = LinearRegression().fit(X, y)
    y_pred = model.predict(X)
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    logger.info("  %s model: R²=%.3f  coefs=%s  intercept=%.5f",
                label, r2, dict(zip(features, model.coef_.tolist())), model.intercept_)

    return {
        "features":  features,
        "coefs":     model.coef_.tolist(),
        "intercept": float(model.intercept_),
        "r2":        round(r2, 4),
    }


def _apply_model(df: pd.DataFrame, model_dict: dict) -> pd.Series:
    """Apply stored linear model coefficients to a DataFrame."""
    features  = model_dict["features"]
    coefs     = model_dict["coefs"]
    intercept = model_dict["intercept"]

    result = pd.Series(intercept, index=df.index, dtype=float)
    for feat, coef in zip(features, coefs):
        if feat in df.columns:
            result += coef * df[feat].fillna(df[feat].median())
    return result


def _default_calibration() -> dict:
    """Hard-coded fallback calibration using empirically derived defaults."""
    avg = _LEAGUE_AVG
    return {
        "calibration_years": [],
        "n_samples": 0,
        "league_averages": avg,
        # BB: negative chase, positive decision+
        "bb_model": {
            "features":  ["chase_pct", "decision_plus"],
            "coefs":     [-0.18, 0.003],
            "intercept": avg["bb_rate"] + 0.18 * 0.290 - 0.003 * 100,
            "r2": None,
        },
        # K: positive whiff (per-pitch), positive chase
        "k_model": {
            "features":  ["whiff_pct", "chase_pct"],
            "coefs":     [1.55, 0.45],
            "intercept": avg["k_rate"] - 1.55 * 0.124 - 0.45 * 0.290,
            "r2": None,
        },
        # TB: in_play rate drives volume, xwOBA × power+ drive quality
        "tb_model": {
            "features":  ["in_play_pct", "xwoba_actual", "power_plus"],
            "coefs":     [1.20, 0.60, 0.006],
            "intercept": avg["tb_rate"] - 1.20 * 0.265 - 0.60 * 0.313 - 0.006 * 100,
            "r2": None,
        },
    }
