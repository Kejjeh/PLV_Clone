"""
Pitcher fantasy-point projection layer.

Translates PLV, whiff%, cs%, xwOBA-model, and contact% into expected
per-IP fantasy-point rates, calibrated from historical pitch data.

Rate models (calibrated via linear regression on 2023-2024 data):
  K/IP    ~ plv + whiff_pct
  BB/IP   ~ plv + cs_pct
  H/IP    ~ plv + contact_pct + xwoba_model
  ER/IP   ~ plv + xwoba_model   (target = FIP/9 from actual pitch events)

Derived:
  HBP/IP  = league average constant (~0.033)

Role classification:
  SP if avg pitches per game appearance > 50, else RP.
  fp_per_start  = fp_per_ip * ip_per_start  (SP only)
  fp_per_app    = fp_per_ip * ip_per_app    (RP only)

SV/HD are NOT included in fp_per_ip or fp_per_start/fp_per_app.
They are reported separately as sv_upside and hd_upside with role notes.
See docs/fantasy_points_methodology.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.utils.logging import get_logger
from .scoring import LeagueScoring, pitcher_fp_per_ip

logger = get_logger(__name__)

_CALIB_FILE = "pitcher_fantasy_calibration.json"

# ── Event sets ────────────────────────────────────────────────────────────────

_H_EVENTS = {"single", "double", "triple", "home_run"}
_NON_PA   = {
    "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "wild_pitch", "passed_ball", "balk",
}
_PITCHES_PER_IP = 15.0   # MLB avg ~15 pitches per IP; used for IP estimation
_FIP_CONSTANT   = 3.17   # 2023-2024 average FIP constant

# ── League averages (2023-2024 MLB, per IP) ───────────────────────────────────

_LEAGUE_AVG: dict[str, float] = {
    "k_per_ip":   0.944,   # K/9 ≈ 8.5 → K/IP = 8.5/9
    "bb_per_ip":  0.333,   # BB/9 ≈ 3.0
    "h_per_ip":   0.944,   # H/9 ≈ 8.5
    "er_per_ip":  0.467,   # ERA ≈ 4.20 → ER/IP
    "hb_per_ip":  0.033,   # HBP/9 ≈ 0.3
    "ip_per_start": 5.5,
    "ip_per_app":   1.0,
}


# ── Calibration ───────────────────────────────────────────────────────────────

def calibrate(
    processed_dir: Path,
    outputs_dir: Path,
    models_dir: Path,
    calibration_years: list[int] | None = None,
) -> dict:
    """Fit pitcher rate models from historical PLV pitch data.

    Reads plv_scores parquets + master_pitcher CSVs. Computes K, BB, H, HBP,
    HR counts from events, estimates IP from pitch count (pitches/15), builds
    FIP-based ER/IP as the calibration target, then fits linear regressions.
    """
    from plv_clone.utils.io import read_parquet

    years = calibration_years or [2023, 2024]
    logger.info("Calibrating pitcher fantasy model on years=%s", years)

    records = []
    for yr in years:
        plv_dir = processed_dir / f"plv_scores/year={yr}"
        mp_path = outputs_dir / f"master_pitcher_{yr}.csv"
        if not plv_dir.exists() or not mp_path.exists():
            logger.warning("Skipping year=%d: missing plv_scores or master_pitcher.", yr)
            continue

        plv_df = read_parquet(plv_dir)
        mp_df  = pd.read_csv(mp_path)

        actual = _compute_pitcher_actuals(plv_df)
        merged = mp_df.merge(actual, on="pitcher", how="inner")
        merged["year"] = yr
        records.append(merged)
        logger.info("  year=%d: %d pitchers with both scores and actuals", yr, len(merged))

    if not records:
        logger.warning("No calibration data found. Using default coefficients.")
        return _default_calibration()

    df = pd.concat(records, ignore_index=True)
    df = df[df["ip_est"] >= 10].dropna(subset=[
        "plv", "whiff_pct", "cs_pct", "xwoba_model", "contact_pct",
        "k_per_ip", "bb_per_ip", "h_per_ip", "er_per_ip",
    ])
    logger.info("Calibration dataset: %d pitcher-seasons", len(df))

    calib = {"calibration_years": years, "n_samples": len(df), "league_averages": _LEAGUE_AVG}

    calib["k_model"]  = _fit_linear(df, ["plv", "whiff_pct"], "k_per_ip",  "K/IP")
    calib["bb_model"] = _fit_linear(df, ["plv", "cs_pct"],    "bb_per_ip", "BB/IP")
    calib["h_model"]  = _fit_linear(df, ["plv", "contact_pct", "xwoba_model"], "h_per_ip", "H/IP")
    calib["er_model"] = _fit_linear(df, ["plv", "xwoba_model"], "er_per_ip", "ER/IP")

    path = models_dir / _CALIB_FILE
    models_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(calib, indent=2))
    logger.info("Pitcher calibration saved to %s (n=%d)", path, len(df))
    return calib


def load_calibration(models_dir: Path) -> dict:
    path = models_dir / _CALIB_FILE
    if path.exists():
        return json.loads(path.read_text())
    logger.info("No pitcher calibration found — using defaults.")
    return _default_calibration()


# ── Projection ────────────────────────────────────────────────────────────────

def project(
    master_pitcher: pd.DataFrame,
    rolling_plv: pd.DataFrame | None,
    scoring: LeagueScoring,
    coefs: dict | None = None,
    ip_per_start: float = 5.5,
    ip_per_app: float = 1.0,
    role_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add expected fantasy rate and FP columns to master_pitcher.

    Added columns:
      est_k_per_ip, est_bb_per_ip, est_h_per_ip, est_er_per_ip, est_hb_per_ip,
      fp_per_ip, fp_per_start (SP), fp_per_app (RP),
      pitcher_role, sv_upside, hd_upside
    """
    c = coefs or _default_calibration()
    df = master_pitcher.copy()

    # ── Role classification ───────────────────────────────────────────────
    if role_df is not None and "pitcher" in role_df.columns:
        df = df.merge(role_df[["pitcher", "pitcher_role", "avg_pitches_per_game"]],
                      on="pitcher", how="left")
    if "pitcher_role" not in df.columns:
        df["pitcher_role"] = "SP"   # default if no role info; caller should supply role_df

    # ── Rolling PLV blend (weight 30% recent if available) ───────────────
    if rolling_plv is not None and not rolling_plv.empty and "plv" in rolling_plv.columns:
        latest_roll = (
            rolling_plv.sort_values("date")
            .groupby("pitcher")["plv"]
            .last()
            .rename("rolling_plv_30d")
            .reset_index()
        )
        df = df.merge(latest_roll, on="pitcher", how="left")
        # Blend: 70% season PLV, 30% rolling (if rolling is available)
        df["plv_blended"] = df["plv"].copy()
        has_roll = df["rolling_plv_30d"].notna()
        df.loc[has_roll, "plv_blended"] = (
            0.70 * df.loc[has_roll, "plv"] + 0.30 * df.loc[has_roll, "rolling_plv_30d"]
        )
    else:
        df["plv_blended"] = df["plv"]

    # Use blended PLV for projection
    plv_orig = df["plv"].copy()
    df["plv"] = df["plv_blended"]

    # ── Estimated rates ───────────────────────────────────────────────────
    df["est_k_per_ip"]  = _apply_model(df, c["k_model"]).clip(lower=0.2, upper=2.0)
    df["est_bb_per_ip"] = _apply_model(df, c["bb_model"]).clip(lower=0.1, upper=1.5)
    df["est_h_per_ip"]  = _apply_model(df, c["h_model"]).clip(lower=0.3, upper=2.0)
    df["est_er_per_ip"] = _apply_model(df, c["er_model"]).clip(lower=0.1, upper=1.2)
    df["est_hb_per_ip"] = c["league_averages"].get("hb_per_ip", 0.033)

    # Restore original PLV
    df["plv"] = plv_orig

    # ── Fantasy points per IP (no SV/HD) ─────────────────────────────────
    df["fp_per_ip"] = df.apply(
        lambda r: pitcher_fp_per_ip(
            h_per_ip=r["est_h_per_ip"],
            er_per_ip=r["est_er_per_ip"],
            bb_per_ip=r["est_bb_per_ip"],
            hb_per_ip=r["est_hb_per_ip"],
            k_per_ip=r["est_k_per_ip"],
            scoring=scoring,
        ),
        axis=1,
    ).round(4)

    # ── Per-start / per-app based on role ─────────────────────────────────
    df["fp_per_start"] = np.where(
        df["pitcher_role"] == "SP",
        (df["fp_per_ip"] * ip_per_start).round(2),
        np.nan,
    )
    df["fp_per_app"] = np.where(
        df["pitcher_role"] == "RP",
        (df["fp_per_ip"] * ip_per_app).round(2),
        np.nan,
    )

    # ── SV / HD upside notes ──────────────────────────────────────────────
    # These are role-sensitive and very noisy. Reported as multipliers only.
    # Closer (RP with high-leverage usage): ~0.15 SV/app → +0.75 FP/app
    # Setup/hold (RP): ~0.25 HD/app → +0.75 FP/app
    # We flag RP pitchers; user applies their own role knowledge.
    df["sv_upside"]  = np.where(df["pitcher_role"] == "RP",
                                 f"+{scoring.sv:.0f}/save (role-dependent)", "")
    df["hd_upside"]  = np.where(df["pitcher_role"] == "RP",
                                 f"+{scoring.hd:.0f}/hold (role-dependent)", "")

    return df


# ── Role inference ─────────────────────────────────────────────────────────────

def infer_roles(plv_df: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame with pitcher_role ('SP'/'RP') and avg_pitches_per_game.

    Classification: avg pitches per game appearance > 50 → SP, else RP.
    """
    per_game = (
        plv_df.groupby(["pitcher", "game_pk"])
        .size()
        .reset_index(name="pitches_in_game")
    )
    avg_per_game = (
        per_game.groupby("pitcher")["pitches_in_game"]
        .mean()
        .reset_index(name="avg_pitches_per_game")
    )
    avg_per_game["pitcher_role"] = np.where(
        avg_per_game["avg_pitches_per_game"] > 50, "SP", "RP"
    )
    return avg_per_game


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_pitcher_actuals(plv_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-pitcher actual rate stats from pitch-level events.

    IP is estimated as pitches / 15 (empirical MLB average).
    ER/IP is estimated via FIP formula from K, BB, HBP, HR counts.
    """
    events = plv_df.dropna(subset=["events"]).copy()
    events = events[events["events"].astype(str).str.strip() != ""]

    pa = events[~events["events"].isin(_NON_PA)].copy()
    # Use events strings for PA-level outcomes (pitch-level flags are unreliable
    # for terminal walk/K classification in the PA-filtered dataset)
    _K_EVENTS_P = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
    pa["is_k"]   = pa["events"].isin(_K_EVENTS_P)
    pa["is_bb"]  = pa["events"].isin({"walk", "intent_walk"})
    pa["is_hbp"] = pa["events"] == "hit_by_pitch"
    pa["is_h"]   = pa["events"].isin(_H_EVENTS)
    pa["is_hr"]  = pa["events"] == "home_run"

    stats = pa.groupby("pitcher").agg(
        pitches_pa=("pitcher", "count"),
        k=("is_k", "sum"),
        bb=("is_bb", "sum"),
        hbp=("is_hbp", "sum"),
        h=("is_h", "sum"),
        hr=("is_hr", "sum"),
    ).reset_index()

    # Total pitches (including balls/strikes, not just PA outcomes)
    pitch_totals = plv_df.groupby("pitcher").size().reset_index(name="pitches_total")
    stats = stats.merge(pitch_totals, on="pitcher", how="left")

    stats["ip_est"] = stats["pitches_total"] / _PITCHES_PER_IP

    ip = stats["ip_est"].clip(lower=0.1)
    stats["k_per_ip"]  = stats["k"]   / ip
    stats["bb_per_ip"] = stats["bb"]  / ip
    stats["h_per_ip"]  = stats["h"]   / ip
    stats["hb_per_ip"] = stats["hbp"] / ip
    stats["hr_per_ip"] = stats["hr"]  / ip

    # FIP-based ER estimate
    stats["fip"] = (
        13 * stats["hr_per_ip"]
        + 3 * (stats["bb_per_ip"] + stats["hb_per_ip"])
        - 2 * stats["k_per_ip"]
        + _FIP_CONSTANT
    )
    stats["er_per_ip"] = (stats["fip"] / 9).clip(lower=0.05, upper=1.5)

    return stats


def _fit_linear(df: pd.DataFrame, features: list[str], target: str, label: str) -> dict:
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
    features  = model_dict["features"]
    coefs     = model_dict["coefs"]
    intercept = model_dict["intercept"]

    result = pd.Series(intercept, index=df.index, dtype=float)
    for feat, coef in zip(features, coefs):
        if feat in df.columns:
            result += coef * df[feat].fillna(df[feat].median())
    return result


def _default_calibration() -> dict:
    avg = _LEAGUE_AVG
    return {
        "calibration_years": [],
        "n_samples": 0,
        "league_averages": avg,
        # K/IP: higher PLV -> more Ks, higher whiff -> more Ks
        "k_model": {
            "features":  ["plv", "whiff_pct"],
            "coefs":     [0.15, 3.50],
            "intercept": avg["k_per_ip"] - 0.15 * 5.0 - 3.50 * 0.275,
            "r2": None,
        },
        # BB/IP: higher PLV -> fewer BBs, higher cs% -> fewer BBs
        "bb_model": {
            "features":  ["plv", "cs_pct"],
            "coefs":     [-0.08, -2.20],
            "intercept": avg["bb_per_ip"] + 0.08 * 5.0 + 2.20 * 0.31,
            "r2": None,
        },
        # H/IP: higher PLV -> fewer H, lower contact% -> fewer H
        "h_model": {
            "features":  ["plv", "contact_pct", "xwoba_model"],
            "coefs":     [-0.12, 1.80, 2.50],
            "intercept": avg["h_per_ip"] + 0.12 * 5.0 - 1.80 * 0.326 - 2.50 * 0.313,
            "r2": None,
        },
        # ER/IP: higher PLV -> fewer ER, lower xwoba -> fewer ER
        "er_model": {
            "features":  ["plv", "xwoba_model"],
            "coefs":     [-0.06, 2.20],
            "intercept": avg["er_per_ip"] + 0.06 * 5.0 - 2.20 * 0.313,
            "r2": None,
        },
    }
