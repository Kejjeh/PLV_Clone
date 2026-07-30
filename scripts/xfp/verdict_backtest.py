"""Leakage-safe retrospective backtest of the headline projection + add/hold/drop
signal vs realized forward FP.

Leakage discipline (memory `feedback_convergence_curve_leakage_detector`):
  * Production pkls train ONLY on 2018-2025 (TRAIN_YEARS) — predicting 2026
    split rows is out-of-sample by YEAR. No model-fit leakage.
  * Features are reconstructed exactly as each pipeline's main() builds them,
    using the rolling cache's cumulative-to-split (`*_to`) columns. These are
    leakage-safe: each (player, split_day) row carries only data observed
    through that split's cutoff.
  * The forward target (`ros_full_fp_per_pa` / `ros_fp_per_start` /
    `fp_year_total`-derived) is the realized outcome AFTER the split — the thing
    we are testing the projection against. It is NEVER used as a feature.
  * Replacement level + signal are recomputed PER SPLIT from the projected
    population at that split (exactly as the pipeline does for the latest split),
    so the as-of decision is reconstructable.

For each (player, split_day) we record: projection, signal (add/hold/drop),
realized forward target, settler classification.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# "today" = data freshness cutoff. Models/data run through 2026-06-09.
AS_OF = date(2026, 6, 9)

ROOT = Path(__file__).resolve().parents[2]

import joblib

from plv_clone.models.xfp import rh3 as RH3
from plv_clone.models.xfp import rp3 as RP3
from plv_clone.models.xfp import rprs2 as RPRS2
from plv_clone.decisions.settler import SETTLEMENT_WINDOWS

# Settler windows give us thresholds; classification reproduced inline so we can
# run it vectorized across the panel (settle_decision is per-record).
H_THR = SETTLEMENT_WINDOWS["H"]["threshold"]    # 0.02 FP/PA
SP_THR = SETTLEMENT_WINDOWS["SP"]["threshold"]  # 1.0  FP/start
RP_THR = SETTLEMENT_WINDOWS["RP"]["threshold"]  # 0.5  FP/g
H_MIN_EVENTS = SETTLEMENT_WINDOWS["H"]["min_events"]    # 30 PA
SP_MIN_EVENTS = SETTLEMENT_WINDOWS["SP"]["min_events"]  # 5 starts
RP_MIN_EVENTS = SETTLEMENT_WINDOWS["RP"]["min_events"]  # 10 app


# --------------------------------------------------------------------------- #
# Feature reconstruction — replicate each pipeline's main() feature build.
# --------------------------------------------------------------------------- #
def build_hitter_panel() -> pd.DataFrame:
    """Reconstruct rh3 features on the full rolling-hitter cache."""
    rolling = pd.read_csv(RH3.ROLLING_CSV)
    multiyr = pd.read_csv(RH3.MULTIYR_CSV)

    prior = RH3.build_prior_table(multiyr, sorted(rolling["year"].unique()))
    rolling = rolling.merge(prior, on=["batter", "year"], how="left")
    league_mu = float(multiyr[multiyr["pa"] >= 200]["fp_per_pa_actual"].mean())
    rolling["prior_fp_per_pa"] = rolling["prior_fp_per_pa"].fillna(league_mu)
    rolling["prior_pa_eff"] = rolling["prior_pa_eff"].fillna(0.0)

    if RH3.H2_LOCKED_CSV.exists():
        h2 = pd.read_csv(RH3.H2_LOCKED_CSV)[["batter", "lift_h2_aug150"]]
        rolling = rolling.merge(h2, on="batter", how="left")
        rolling["lift_h2_aug150"] = rolling["lift_h2_aug150"].fillna(0.0)
    else:
        rolling["lift_h2_aug150"] = 0.0

    if RH3.XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(RH3.XWOBA_RESID_CSV)[["batter", "xwoba_residual_career"]]
        rolling = rolling.merge(xw, on="batter", how="left")
        rolling["xwoba_residual_career"] = rolling["xwoba_residual_career"].fillna(0.0)
    else:
        rolling["xwoba_residual_career"] = 0.0

    if "xwoba_on_contact_to" in rolling.columns and "woba_d_sum_to" in rolling.columns:
        rolling["actual_woba_per_pa_to"] = np.where(
            rolling["woba_d_sum_to"] > 0,
            rolling["woba_v_sum_to"] / rolling["woba_d_sum_to"], np.nan)
        rolling["xwoba_gap_to"] = (rolling["xwoba_on_contact_to"]
                                   - rolling["actual_woba_per_pa_to"]).fillna(0.0)
    else:
        rolling["xwoba_gap_to"] = 0.0

    # Box-score-era ensemble prior — promoted into RH3_FEATS 2026-07-10 (B1,
    # bx_prior_h_promotion_2026-07-10.md). This reconstruction was NOT updated
    # at promotion time, so every hitter run of this script raised
    # KeyError: ['bx_prior_h'] from the dropna(subset=feats) below (found
    # 2026-07-29 by the band-CRPS study). Merge mirrors rh3.main() lines 373-397
    # and _merge_bx in validate_bx_ensemble.py: (batter, year) mlbam join,
    # per-year-mean fill, then global-mean fill.
    if RH3.BX_PRIORS_CSV.exists():
        bx = pd.read_csv(RH3.BX_PRIORS_CSV)[["mlbam", "year", "bx_prior_h"]].rename(
            columns={"mlbam": "batter"})
        rolling = rolling.merge(bx, on=["batter", "year"], how="left")
        year_means = rolling.groupby("year")["bx_prior_h"].transform("mean")
        rolling["bx_prior_h"] = rolling["bx_prior_h"].fillna(year_means)
        rolling["bx_prior_h"] = rolling["bx_prior_h"].fillna(rolling["bx_prior_h"].mean())
    else:
        raise FileNotFoundError(
            f"Missing required bx priors cache: {RH3.BX_PRIORS_CSV}. "
            "Run scripts/xfp/build_bx_priors.py (refresh step 1.95).")

    first_year = multiyr.groupby("batter")["year"].min().to_dict()
    rolling["career_stage"] = rolling.apply(
        lambda r: r["year"] - first_year.get(r["batter"], r["year"]), axis=1)

    opp_sp = pd.read_csv(RH3.ROS_OPP_SP_CSV)[
        ["batter", "year", "split_day", "ros_opp_sp_xwoba_weighted"]]
    rolling = rolling.merge(opp_sp, on=["batter", "year", "split_day"], how="left")
    year_means = rolling.groupby("year")["ros_opp_sp_xwoba_weighted"].transform("mean")
    rolling["ros_opp_sp_xwoba_weighted"] = (
        rolling["ros_opp_sp_xwoba_weighted"].fillna(year_means)
        .fillna(rolling["ros_opp_sp_xwoba_weighted"].mean()))

    pop_to = RH3.compute_population_means(rolling, RH3.TRAIN_YEARS, RH3.SHRINK_SPEC_TO)
    pop_l21 = RH3.compute_population_means(rolling, RH3.TRAIN_YEARS, RH3.SHRINK_SPEC_LAST21)
    rolling = RH3.apply_shrinkage(rolling, pop_to, RH3.SHRINK_SPEC_TO)
    rolling = RH3.apply_shrinkage(rolling, pop_l21, RH3.SHRINK_SPEC_LAST21)
    for col in (rate + "_sh" for rate in RH3.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling["year"].isin(RH3.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling["pa_last21"] = rolling["pa_last21"].fillna(0).astype(float)
    return rolling, multiyr


def build_pitcher_panel() -> pd.DataFrame:
    """Reconstruct rp3 features on the full rolling-pitcher cache."""
    rolling = pd.read_csv(RP3.ROLLING_CSV)
    multiyr = pd.read_csv(RP3.MULTIYR_CSV)
    il = pd.read_csv(RP3.IL_CSV)

    prior = RP3.build_prior_table(multiyr, sorted(rolling["year"].unique()))
    rolling = rolling.merge(prior, on=["pitcher", "year"], how="left")
    league_mu = float(multiyr[multiyr["gs"] >= 10]["fp_per_start_actual"].mean())
    rolling["prior_source"] = np.where(rolling["prior_fp_per_start"].notna(), "mlb_lag", None)
    if RP3.MILB_PRIORS_CSV.exists():
        mp = pd.read_csv(RP3.MILB_PRIORS_CSV)[["pitcher", "projected_fp_per_start"]]
        mp = mp.rename(columns={"projected_fp_per_start": "milb_prior_fp"})
        rolling = rolling.merge(mp, on="pitcher", how="left")
        is26 = rolling["year"] == 2026
        nf = is26 & rolling["prior_fp_per_start"].isna()
        hm = nf & rolling["milb_prior_fp"].notna()
        rolling.loc[hm, "prior_fp_per_start"] = rolling.loc[hm, "milb_prior_fp"]
    rolling["prior_fp_per_start"] = rolling["prior_fp_per_start"].fillna(league_mu)
    rolling["prior_gs_eff"] = rolling["prior_gs_eff"].fillna(0.0)

    rolling = rolling.merge(il, on=["pitcher", "year", "split_day"], how="left")
    rolling["il_stints_to"] = rolling["il_stints_to"].fillna(0).astype(int)
    rolling["is_on_il_at_split"] = rolling["is_on_il_at_split"].fillna(0).astype(int)
    max_dsr = float(rolling["days_since_il_return"].max(skipna=True) or 200)
    rolling["days_since_il_return_imp"] = rolling["days_since_il_return"].fillna(max_dsr + 1)

    sched = pd.read_csv(RP3.ROS_SCHED_CSV)[
        ["pitcher", "year", "split_day", "ros_opp_xwoba_weighted"]]
    rolling = rolling.merge(sched, on=["pitcher", "year", "split_day"], how="left")
    ym = rolling.groupby("year")["ros_opp_xwoba_weighted"].transform("mean")
    rolling["ros_opp_xwoba_weighted"] = (
        rolling["ros_opp_xwoba_weighted"].fillna(ym)
        .fillna(rolling["ros_opp_xwoba_weighted"].mean()))

    pop_to = RP3.compute_population_means(rolling, RP3.TRAIN_YEARS, RP3.SHRINK_SPEC_TO)
    pop_l21 = RP3.compute_population_means(rolling, RP3.TRAIN_YEARS, RP3.SHRINK_SPEC_LAST21)
    rolling = RP3.apply_shrinkage(rolling, pop_to, RP3.SHRINK_SPEC_TO)
    rolling = RP3.apply_shrinkage(rolling, pop_l21, RP3.SHRINK_SPEC_LAST21)
    rolling["delta_velo"] = rolling["avg_velo_last21"] - rolling["avg_velo_to"]
    rolling["delta_swstr"] = rolling["swstr_pct_last21"] - rolling["swstr_pct_to"]
    rolling["delta_k_pct"] = rolling["k_pct_last21"] - rolling["k_pct_to"]
    rolling["delta_bb_pct"] = rolling["bb_pct_last21"] - rolling["bb_pct_to"]
    rolling["delta_chase"] = rolling["o_swing_pct_last21"] - rolling["o_swing_pct_to"]
    rolling["delta_zone"] = rolling["zone_pct_last21"] - rolling["zone_pct_to"]
    for c in ("delta_velo", "delta_swstr", "delta_k_pct", "delta_bb_pct",
              "delta_chase", "delta_zone"):
        rolling[c] = rolling[c].fillna(0.0)
    for col in (rate + "_sh" for rate in RP3.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling["year"].isin(RP3.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    return rolling


def build_reliever_panel() -> pd.DataFrame:
    """rprs2 features are already materialized in the rolling reliever cache."""
    return pd.read_csv(RPRS2.ROLLING_CSV)


# --------------------------------------------------------------------------- #
# Per-split prediction + signal derivation (replicates each pipeline exactly).
# --------------------------------------------------------------------------- #
Z25 = 0.6745


def lookup_sigma_vec(ci_table, overall_sigma, split, preds, pred_buckets):
    from plv_clone.models.xfp.engine import lookup_sigma
    return np.array([lookup_sigma(ci_table, overall_sigma, split, p, pred_buckets)
                     for p in preds])


# --------------------------------------------------------------------------- #
# add/hold/drop signal — vectorized, mirroring the CURRENT production path.
#
# History (why this code exists here at all): rh3/rp3 used to expose a row-wise
# `_signal(row)` helper that this script called via `df.apply(..., axis=1)`.
# Commit de9f6e6 ("model vectorization", audit item 21/W3) DELETED both helpers
# and inlined an equivalent `np.select` block into each pipeline's `main()`.
# Nothing re-pointed this script, so `run_hitters()` / `run_pitchers()` have
# raised AttributeError on every invocation since. Found 2026-07-29.
#
# Why a local vectorized reimplementation rather than importing production's:
# after de9f6e6 the production signal is NOT a callable — it is an inline
# `np.select(...)` inside `rh3.main()` / `rp3.main()`, and `main()` retrains the
# model and writes the production CSVs. There is no importable seam to call.
# The right long-term fix is to extract `signal_vec(df)` into rh3/rp3 and have
# both `main()` and this script call it; that edit is out of this change's file
# set, so instead we (a) reproduce the np.select EXACTLY — same predicate order,
# same column names, same NaN semantics — and (b) lock it against drift with
# tests/test_verdict_backtest_hosts.py::test_*_signal_matches_production, which
# replays these functions over the shipped production projection CSVs and
# asserts the emitted signal is byte-identical to the `signal` column the
# pipelines actually wrote. If someone changes the production rule and not this
# one, that test fails.
#
# NEVER add a fallback default for a missing input column: silently defaulting a
# missing band or replacement level to "hold" is exactly the silent-zero class of
# bug that cost -0.0368 cross-year r in the 2026-07-28 ROOT incident. Missing
# input => raise.
# --------------------------------------------------------------------------- #
H_SIGNAL_COLS = ("replacement_delta", "replacement_xfp_per_pa",
                 "xfp_rh3_p25", "xfp_rh3_p75")
SP_SIGNAL_COLS = ("is_on_il_at_split", "replacement_delta",
                  "replacement_xfp_per_start",
                  "xfp_rp3_decision_p25", "xfp_rp3_decision_p75")


def _require_cols(df: pd.DataFrame, cols, who: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(
            f"{who}: missing required signal input column(s) {missing}. "
            f"Present: {sorted(df.columns)[:40]}... "
            "Refusing to emit a signal from an incomplete frame (a defaulted "
            "'hold' would silently corrupt every backtested verdict).")


def hitter_signal_vec(df: pd.DataFrame) -> np.ndarray:
    """rh3 add/hold/drop. Mirrors the np.select block in `rh3.main()`.

    hold : replacement_delta / replacement level missing
    add  : p25 still above replacement (high-confidence above)
    drop : p75 still below replacement (no recovery even at the top of the band)

    NaN comparisons intentionally evaluate False, matching production.
    """
    _require_cols(df, H_SIGNAL_COLS, "hitter_signal_vec")
    repl = df["replacement_xfp_per_pa"]
    p25, p75 = df["xfp_rh3_p25"], df["xfp_rh3_p75"]
    return np.select(
        [
            df["replacement_delta"].isna() | repl.isna(),
            p25.notna() & (p25 > repl),
            p75.notna() & (p75 < repl),
        ],
        ["hold", "add", "drop"],
        default="hold",
    )


def pitcher_signal_vec(df: pd.DataFrame) -> np.ndarray:
    """rp3 il/add/hold/drop. Mirrors the np.select block in `rp3.main()`.

    CRITICAL: the trigger reads the **DECISION** band
    (`xfp_rp3_decision_p25/p75`, built from the RAW LOO sigma), NOT the
    displayed `xfp_rp3_p25/p75` band (raw sigma x alpha_global ~= 2.41). The
    wide display band is coverage-calibrated for an honest CI and is far too
    wide to ever cross the SP-45 replacement level — feeding it to this rule
    makes the signal inert (100% 'hold', found by this very backtest
    2026-06-11, fixed in rp3 by 13bb4a1). Getting this wrong does not error; it
    silently flattens every backtested verdict.
    """
    _require_cols(df, SP_SIGNAL_COLS, "pitcher_signal_vec")
    il = df["is_on_il_at_split"]
    repl = df["replacement_xfp_per_start"]
    p25, p75 = df["xfp_rp3_decision_p25"], df["xfp_rp3_decision_p75"]
    return np.select(
        [
            il.isna() | (il != 0),
            df["replacement_delta"].isna() | repl.isna(),
            p25.notna() & (p25 > repl),
            p75.notna() & (p75 < repl),
        ],
        ["il", "hold", "add", "drop"],
        default="hold",
    )


def run_hitters(rolling, multiyr) -> pd.DataFrame:
    b = joblib.load(RH3.MODEL_PKL)
    pipe, feats = b["pipeline"], b["features"]
    ci_table, overall_sigma = b["ci_table"], b["overall_sigma"]
    pred_buckets = {int(k): np.array(v) for k, v in b["pred_buckets"].items()}

    # position lookup
    mh = pd.read_csv(RH3.MASTER_HITTER) if RH3.MASTER_HITTER.exists() else None
    out_rows = []
    d26 = rolling[rolling["year"] == 2026]
    for split in sorted(d26["split_day"].unique()):
        sub = d26[(d26["split_day"] == split) & (d26["pa_to"] >= RH3.EVAL_PA_MIN)].copy()
        sub = sub.dropna(subset=feats)
        if sub.empty:
            continue
        sub["proj"] = pipe.predict(sub[feats].values)
        sig = lookup_sigma_vec(ci_table, overall_sigma, int(split), sub["proj"].values, pred_buckets)
        sub["sigma"] = sig  # global sigma (hetero factor ~1.0 mean; omitted for OOS panel)
        sub["p25"] = (sub["proj"] - Z25 * sub["sigma"]).clip(lower=0)
        sub["p75"] = sub["proj"] + Z25 * sub["sigma"]
        # position
        if mh is not None:
            sub = sub.merge(mh[["batter", "primary_position"]].drop_duplicates("batter"),
                            on="batter", how="left")
        else:
            sub["primary_position"] = None
        sub["primary_position"] = sub["primary_position"].fillna("UTIL")
        # replacement per position (per split)
        sub = RH3.compute_replacement_delta(sub.rename(columns={"proj": "xfp_rh3_per_pa"}))
        sub = sub.rename(columns={"xfp_rh3_per_pa": "proj"})
        sub["xfp_rh3_p25"] = sub["p25"]
        sub["xfp_rh3_p75"] = sub["p75"]
        sub["signal"] = hitter_signal_vec(sub)
        for _, r in sub.iterrows():
            out_rows.append({
                "bucket": "H", "player": int(r["batter"]), "split_day": int(split),
                "cutoff_date": r.get("cutoff_date"),
                "proj_per": float(r["proj"]), "p25": float(r["p25"]), "p75": float(r["p75"]),
                "replacement": float(r["replacement_xfp_per_pa"]),
                "signal": r["signal"],
                "realized_per": float(r["ros_full_fp_per_pa"]),
                "n_events": float(r["ros_pa"]),
                "eligible": bool(r["ros_pa"] >= RH3.ROS_PA_MIN),
            })
    return pd.DataFrame(out_rows)


def run_pitchers(rolling) -> pd.DataFrame:
    b = joblib.load(RP3.MODEL_PKL)
    pipe, feats = b["pipeline"], b["features"]
    ci_table, overall_sigma = b["ci_table"], b["overall_sigma"]
    pred_buckets = {int(k): np.array(v) for k, v in b["pred_buckets"].items()}
    # sigma calibration alpha
    calib = RP3._load_sigma_calibration()
    alpha = float(calib.get("alpha_global", 1.0))

    out_rows = []
    d26 = rolling[rolling["year"] == 2026]
    for split in sorted(d26["split_day"].unique()):
        sub = d26[(d26["split_day"] == split) & (d26["gs_to"] >= RP3.EVAL_GS_MIN)].copy()
        sub = sub.dropna(subset=feats)
        if sub.empty:
            continue
        sub["proj"] = pipe.predict(sub[feats].values)
        sig = lookup_sigma_vec(ci_table, overall_sigma, int(split), sub["proj"].values, pred_buckets)
        sub["sigma"] = sig * alpha
        sub["xfp_rp3_p25"] = (sub["proj"] - Z25 * sub["sigma"]).clip(lower=0)
        sub["xfp_rp3_p75"] = sub["proj"] + Z25 * sub["sigma"]
        # Decision band: narrow RAW-sigma band (no x2.41), matching rp3.py bugfix
        # 13bb4a1 so the backtest tests the FIXED add/drop signal, not the inert
        # wide display band. _signal() reads xfp_rp3_decision_p25/p75 first.
        sub["xfp_rp3_decision_p25"] = (sub["proj"] - Z25 * sig).clip(lower=0)
        sub["xfp_rp3_decision_p75"] = sub["proj"] + Z25 * sig
        # replacement (global SP-45) per split
        srt = sub.sort_values("proj", ascending=False)
        n = RP3.REPLACEMENT_SP_RANK
        repl = float(srt["proj"].iloc[n - 1]) if len(srt) >= n else float(srt["proj"].median())
        sub["replacement_xfp_per_start"] = round(repl, 3)
        sub["replacement_delta"] = (sub["proj"] - repl).round(3)
        sub["signal"] = pitcher_signal_vec(sub)
        for _, r in sub.iterrows():
            out_rows.append({
                "bucket": "SP", "player": int(r["pitcher"]), "split_day": int(split),
                "cutoff_date": r.get("cutoff_date"),
                "proj_per": float(r["proj"]),
                "p25": float(r["xfp_rp3_p25"]), "p75": float(r["xfp_rp3_p75"]),
                "replacement": float(r["replacement_xfp_per_start"]),
                "signal": r["signal"],
                "realized_per": float(r["ros_fp_per_start"]),
                "n_events": float(r["ros_gs"]),
                "eligible": bool(r["ros_gs"] >= RP3.ROS_GS_MIN) and int(r.get("is_on_il_at_split", 0)) == 0,
            })
    return pd.DataFrame(out_rows)


def run_relievers(rolling) -> pd.DataFrame:
    b = joblib.load(RPRS2.MODEL_PKL)
    pipe, feats = b["pipeline"], b["features"]
    ci_table, overall_sigma = b["ci_table"], b["overall_sigma"]
    pred_buckets = {int(k): np.array(v) for k, v in b["pred_buckets"].items()}

    out_rows = []
    d26 = rolling[rolling["year"] == 2026]
    for split in sorted(d26["split_day"].unique()):
        sub = d26[(d26["split_day"] == split) & (d26["g_to"] >= RPRS2.EVAL_G_MIN)].copy()
        sub = sub.dropna(subset=feats)
        if sub.empty:
            continue
        # model targets full-year total
        sub["proj_full"] = pipe.predict(sub[feats].values).round(1)
        sig = lookup_sigma_vec(ci_table, overall_sigma, int(split), sub["proj_full"].values, pred_buckets)
        sub["xfp_sigma"] = sig
        sub["xfp_p25"] = (sub["proj_full"] - Z25 * sub["xfp_sigma"]).clip(lower=0)
        sub["xfp_p75"] = sub["proj_full"] + Z25 * sub["xfp_sigma"]
        # replacement (RP-30) per split, full-year basis (matches pipeline)
        srt = sub.sort_values("proj_full", ascending=False)
        n = RPRS2.REPLACEMENT_RANK_RP
        repl = float(srt["proj_full"].iloc[n - 1]) if len(srt) >= n else float(srt["proj_full"].median())
        sub["replacement_xfp"] = round(repl, 1)
        sub["replacement_delta"] = (sub["proj_full"] - repl).round(1)

        def signal(r):
            if pd.isna(r["replacement_delta"]) or pd.isna(r["replacement_xfp"]):
                return "hold"
            if pd.notna(r["xfp_p25"]) and r["xfp_p25"] > r["replacement_xfp"]:
                return "add"
            if pd.notna(r["xfp_p75"]) and r["xfp_p75"] < r["replacement_xfp"]:
                return "drop"
            return "hold"
        sub["signal"] = sub.apply(signal, axis=1)
        # realized forward = fp_year_total - fp-to-date (fp_with_role_to is the
        # FP earned through split with SV/HLD bonuses included).
        for _, r in sub.iterrows():
            if pd.isna(r["fp_year_total"]):
                continue
            realized_ros = float(r["fp_year_total"]) - float(r["fp_with_role_to"])
            proj_ros = float(r["proj_full"]) - float(r["fp_with_role_to"])
            out_rows.append({
                "bucket": "RP", "player": int(r["pitcher"]), "split_day": int(split),
                "cutoff_date": r.get("cutoff_date"),
                # full-year basis (native model/signal unit)
                "proj_full": float(r["proj_full"]),
                "realized_full": float(r["fp_year_total"]),
                # RoS basis (forward only)
                "proj_per": proj_ros, "realized_per": realized_ros,
                "replacement": float(r["replacement_xfp"]),
                "signal": r["signal"],
                "n_events": float(r["g_to"]),  # appearances-to-split (proxy; forward g not in cache)
                "eligible": True,
            })
    return pd.DataFrame(out_rows)


# --------------------------------------------------------------------------- #
# Settlement + stats
# --------------------------------------------------------------------------- #
def classify(signal, residual, thr):
    if signal == "add":   # BUY
        return "BUY_HIT" if residual > thr else "BUY_MISS"
    if signal == "drop":  # FADE
        return "FADE_HIT" if residual < -thr else "FADE_MISS"
    return "HOLD_NEUTRAL"


def settle(df, thr, bucket):
    df = df.copy()
    df["residual"] = df["realized_per"] - df["proj_per"]
    df["classification"] = df.apply(lambda r: classify(r["signal"], r["residual"], thr), axis=1)
    return df


def quintile_calibration(df, value_col, real_col):
    d = df.dropna(subset=[value_col, real_col]).copy()
    if len(d) < 10:
        return None
    d["q"] = pd.qcut(d[value_col], 5, labels=False, duplicates="drop")
    g = d.groupby("q").agg(n=("residual", "size"),
                           mean_proj=(value_col, "mean"),
                           mean_real=(real_col, "mean")).reset_index()
    return g


def main():
    print("Building hitter panel...")
    h_roll, h_multi = build_hitter_panel()
    print("Building pitcher panel...")
    p_roll = build_pitcher_panel()
    print("Building reliever panel...")
    r_roll = build_reliever_panel()

    print("Predicting + signal (hitters)...")
    H = run_hitters(h_roll, h_multi)
    print("Predicting + signal (pitchers)...")
    SP = run_pitchers(p_roll)
    print("Predicting + signal (relievers)...")
    RP = run_relievers(r_roll)

    H = settle(H, H_THR, "H")
    SP = settle(SP, SP_THR, "SP")

    # As-of date gate: a decision at split-day cutoff D only settles if the
    # settler window has FULLY elapsed by AS_OF (2026-06-09). This is the honest
    # "could we have scored this decision by now" filter and mirrors
    # settle_decision()'s `today >= snapshot + window_days` clause.
    def window_elapsed(df, window_days):
        cd = pd.to_datetime(df["cutoff_date"]).dt.date
        return cd.map(lambda c: (AS_OF - c).days >= window_days)

    H = H[window_elapsed(H, SETTLEMENT_WINDOWS["H"]["days"])].copy()
    SP = SP[window_elapsed(SP, SETTLEMENT_WINDOWS["SP"]["days"])].copy()

    # restrict to settleable rows (enough forward events)
    H_s = H[H["n_events"] >= H_MIN_EVENTS].copy()
    SP_s = SP[(SP["n_events"] >= SP_MIN_EVENTS) & SP["eligible"]].copy()

    H.to_csv(ROOT / "data/research/validation_runs/_bt_hitters.csv", index=False)
    SP.to_csv(ROOT / "data/research/validation_runs/_bt_pitchers.csv", index=False)
    RP.to_csv(ROOT / "data/research/validation_runs/_bt_relievers.csv", index=False)

    def report(name, df_s, value_col, real_col, thr):
        print(f"\n========== {name} ==========")
        print(f"n total rows: {len(df_s)}")
        print("per split_day n:")
        print(df_s.groupby("split_day").size().to_dict())
        # Spearman overall + per split
        d = df_s.dropna(subset=[value_col, real_col])
        rho, p = spearmanr(d[value_col], d[real_col])
        print(f"Spearman(proj, realized) OVERALL: rho={rho:.3f} (p={p:.2e}, n={len(d)})")
        for split in sorted(d["split_day"].unique()):
            ds = d[d["split_day"] == split]
            if len(ds) >= 10:
                rr, pp = spearmanr(ds[value_col], ds[real_col])
                print(f"   split {split} (cutoff {ds['cutoff_date'].iloc[0]}): rho={rr:.3f} n={len(ds)}")
        # signal tier means
        print("mean realized forward by signal tier:")
        gt = df_s.groupby("signal")[real_col].agg(["mean", "size"])
        print(gt.to_string())
        # BUY/FADE hit rates
        cls = df_s["classification"].value_counts().to_dict()
        print("classification counts:", cls)
        buys = df_s[df_s["signal"] == "add"]
        fades = df_s[df_s["signal"] == "drop"]
        if len(buys):
            bh = (buys["classification"] == "BUY_HIT").mean()
            print(f"BUY n={len(buys)}  BUY_HIT rate={bh:.3f}  mean residual={buys['residual'].mean():+.3f}")
        if len(fades):
            fh = (fades["classification"] == "FADE_HIT").mean()
            print(f"FADE n={len(fades)} FADE_HIT rate={fh:.3f} mean residual={fades['residual'].mean():+.3f}")
        # quintile calibration
        cal = quintile_calibration(df_s, value_col, real_col)
        if cal is not None:
            print("quintile calibration (proj quintile -> mean proj / mean realized):")
            print(cal.to_string(index=False))
        return {"rho": rho, "n": len(d), "tier": gt, "cal": cal, "cls": cls,
                "buy_n": len(buys), "fade_n": len(fades)}

    res = {}
    res["H"] = report("HITTERS (rh3, FP/PA)", H_s, "proj_per", "realized_per", H_THR)
    res["SP"] = report("STARTERS (rp3, FP/start)", SP_s, "proj_per", "realized_per", SP_THR)

    # --- RP: ranking lens ONLY ------------------------------------------------
    # CAVEAT: rprs2 targets full-SEASON FP total and was trained on COMPLETE
    # seasons (2019-2025). For in-progress 2026 the cache's `fp_year_total` is
    # the SEASON-TO-DATE total as of the 6/9 pull (~70 games), NOT a realized
    # full-162 outcome. So we CANNOT settler-classify or calibration-check the RP
    # full-year projection (units mismatch: full-season proj vs partial actual).
    # What IS valid and leakage-safe: the RANK correlation between the full-year
    # projection and season-to-date actuals — a "does the model order RPs
    # correctly" check (better RPs accumulate more FP-to-date). We report that
    # alone and flag the rest as not-reconstructable in-season.
    RP_rank = RP.dropna(subset=["proj_full", "realized_full"]).copy()
    print("\n========== RELIEVERS (rprs2) — RANKING LENS ONLY ==========")
    print("CAVEAT: 2026 fp_year_total is SEASON-TO-DATE (partial), not full-162.")
    print("        Calibration + settler classification NOT reconstructable in-season.")
    rho_rp, p_rp = spearmanr(RP_rank["proj_full"], RP_rank["realized_full"])
    print(f"Spearman(full-year proj, season-to-date actual) OVERALL: "
          f"rho={rho_rp:.3f} (p={p_rp:.2e}, n={len(RP_rank)})")
    for split in sorted(RP_rank["split_day"].unique()):
        ds = RP_rank[RP_rank["split_day"] == split]
        if len(ds) >= 10:
            rr, _ = spearmanr(ds["proj_full"], ds["realized_full"])
            print(f"   split {split} (cutoff {ds['cutoff_date'].iloc[0]}): rho={rr:.3f} n={len(ds)}")
    # Signal-tier mean of season-to-date actual (ordinal check only).
    print("mean season-to-date actual FP by signal tier (ordinal check only):")
    print(RP_rank.groupby("signal")["realized_full"].agg(["mean", "size"]).to_string())
    res["RP"] = {"rho": rho_rp, "n": len(RP_rank)}

    import pickle
    with open(ROOT / "data/research/validation_runs/_bt_results.pkl", "wb") as f:
        pickle.dump({"H": H, "SP": SP, "RP": RP, "H_s": H_s, "SP_s": SP_s,
                     "RP_rank": RP_rank}, f)
    print("\nDone. Panels written to data/research/validation_runs/_bt_*.csv")


if __name__ == "__main__":
    main()
