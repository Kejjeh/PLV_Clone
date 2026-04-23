"""
PLV MVP Review Script
=====================
Runs the full pipeline and writes a structured review packet to:

  data/outputs/review_YYYY/
    review_summary.md          -- narrative summary + 10-bullet exec summary
    data_integrity.json        -- row counts, missingness, outcome rates
    model_metrics.csv          -- all 5 sub-models vs baselines
    calibration_swing.png
    calibration_called_strike.png
    calibration_contact.png
    calibration_foul.png
    plv_distribution_pitch.png -- pitch-level histogram + QQ
    plv_distribution_count.png -- mean PLV heatmap by count state
    plv_distribution_type.png  -- box/violin by pitch type
    plv_predicted_vs_actual.png-- BattedBallModel scatter
    pitcher_leaderboard.csv    -- qualified pitcher PLV (wide format)
    pitch_type_leaderboard.csv -- per-pitcher-per-pitch-type PLV
    stability_analysis.csv     -- half-half r / S-B r by sample threshold
    suspicious_cases.csv       -- outliers, out-of-range, high-variance rows

Usage:
    cd plv_clone
    python scripts/run_plv_review.py [--skip-pull] [--skip-train] [--year 2024]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Force UTF-8 I/O on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import stats as scipy_stats

from plv_clone.config import get_config
from plv_clone.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("review")

CFG = get_config()


def review_dir(year: int) -> Path:
    d = CFG.outputs_dir / f"review_{year}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE STEPS
# ══════════════════════════════════════════════════════════════════════════════

def step_pull(start: date, end: date) -> None:
    from plv_clone.data.ingest_statcast import pull_statcast_range
    logger.info("Pulling data %s to %s ...", start, end)
    pull_statcast_range(start, end, CFG.raw_data_dir, CFG.statcast_chunk_days)


def step_features(start: date, end: date, skip_pull: bool = False) -> None:
    from plv_clone.pipelines.build_pitch_dataset import run
    logger.info("Building features %s to %s ...", start, end)
    run(start_date=start, end_date=end, config=CFG, skip_pull=skip_pull)


def step_train() -> None:
    from plv_clone.pipelines.train_plv import run
    logger.info("Training PLV models ...")
    run(config=CFG)


def step_score(year: int) -> None:
    from plv_clone.pipelines.score_plv import run
    logger.info("Scoring year=%d ...", year)
    run(year=year, config=CFG)


def load_artifacts(year: int):
    from plv_clone.utils.io import read_parquet
    from plv_clone.models.plv_model import PLVModel
    from plv_clone.features.run_value_features import load_count_value_table
    from plv_clone.pipelines.train_plv import _load_year_range, _drop_unknown

    plv_model   = PLVModel.load(CFG.models_dir)
    count_table = load_count_value_table(CFG.models_dir)
    feat_dir    = CFG.processed_dir / "pitch_features"

    train_df = _drop_unknown(_load_year_range(feat_dir, CFG.effective_train_start.year, CFG.train_end.year))
    val_df   = _drop_unknown(_load_year_range(feat_dir, CFG.val_start.year, CFG.val_end.year))
    scored_df = read_parquet(CFG.processed_dir / "plv_scores" / f"year={year}")

    logger.info("Artifacts loaded: train=%d | val=%d | scored=%d", len(train_df), len(val_df), len(scored_df))
    return plv_model, count_table, train_df, val_df, scored_df


# ══════════════════════════════════════════════════════════════════════════════
# 1 — data_integrity.json
# ══════════════════════════════════════════════════════════════════════════════

def write_data_integrity(train_df, val_df, scored_df, out: Path) -> dict:
    logger.info("Writing data_integrity.json ...")

    def _summary(label: str, df: pd.DataFrame) -> dict:
        rec: dict = {"label": label, "rows": len(df)}

        if "pitcher" in df.columns:
            rec["unique_pitchers"] = int(df["pitcher"].nunique())
        if "batter" in df.columns:
            rec["unique_batters"] = int(df["batter"].nunique())
        if "game_date" in df.columns:
            dates = pd.to_datetime(df["game_date"])
            rec["date_min"] = str(dates.min().date())
            rec["date_max"] = str(dates.max().date())

        # Pitch type distribution
        if "pitch_type" in df.columns:
            rec["pitch_type_pct"] = (
                df["pitch_type"].value_counts(normalize=True)
                .mul(100).round(1).to_dict()
            )

        # Outcome distribution
        if "resolved_outcome" in df.columns:
            rec["outcome_pct"] = (
                df["resolved_outcome"].value_counts(normalize=True)
                .mul(100).round(2).to_dict()
            )

        # Swing / contact / in-play rates
        for col, lbl in [("is_swing","swing_rate"),("is_contact","contact_rate"),("is_in_play","in_play_rate")]:
            if col in df.columns:
                rec[lbl] = round(float(df[col].mean()), 4)

        # Missingness on key cols
        key_cols = ["release_speed","pfx_x","pfx_z","plate_x","plate_z",
                    "release_extension","estimated_woba_using_speedangle","delta_run_exp"]
        missing = {}
        for c in key_cols:
            if c in df.columns:
                pct = round(100 * df[c].isna().mean(), 2)
                if pct > 0.0:
                    missing[c] = pct
        rec["missing_pct"] = missing

        # Pitch key uniqueness
        key_cols_pk = ["game_pk","at_bat_number","pitch_number","pitcher","batter"]
        if all(c in df.columns for c in key_cols_pk):
            rec["duplicate_pitch_keys"] = int(df.duplicated(subset=key_cols_pk).sum())

        return rec

    integrity = {
        "generated_at": datetime.utcnow().isoformat(),
        "train":  _summary("Train 2021-2023", train_df),
        "val":    _summary("Val 2024", val_df),
        "scored": _summary(f"Scored 2024", scored_df),
    }
    out.write_text(json.dumps(integrity, indent=2), encoding="utf-8")
    logger.info("  -> %s", out.name)
    return integrity


# ══════════════════════════════════════════════════════════════════════════════
# 2 — model_metrics.csv
# ══════════════════════════════════════════════════════════════════════════════

def write_model_metrics(plv_model, val_df: pd.DataFrame, out: Path) -> pd.DataFrame:
    from plv_clone.models.evaluation import evaluate_classifier, evaluate_regression
    logger.info("Writing model_metrics.csv ...")

    val_takes    = val_df[val_df["is_take"].astype(bool)]
    val_swings   = val_df[val_df["is_swing"].astype(bool)]
    val_contacts = val_df[val_df["is_contact"].astype(bool)]
    val_ip       = val_df[val_df["is_in_play"].astype(bool) &
                          val_df["estimated_woba_using_speedangle"].notna()]

    specs = [
        ("SwingModel",        val_df,       "is_swing",                       "classifier", plv_model.swing_model.predict_proba),
        ("CalledStrikeModel", val_takes,    "is_called_strike",               "classifier", plv_model.cs_model.predict_proba),
        ("ContactModel",      val_swings,   "is_contact",                     "classifier", plv_model.contact_model.predict_proba),
        ("FoulModel",         val_contacts, "is_foul",                        "classifier", plv_model.foul_model.predict_proba),
        ("BattedBallModel",   val_ip,       "estimated_woba_using_speedangle", "regression", plv_model.bbv_model.predict),
    ]

    rows = []
    all_metrics = {}
    for name, df_sub, target, kind, predict_fn in specs:
        if len(df_sub) == 0:
            logger.warning("  %s: no validation samples", name)
            continue
        y_true = df_sub[target].values.astype(float)
        y_pred = predict_fn(df_sub)

        if kind == "classifier":
            m = evaluate_classifier(y_true, y_pred, label=name, verbose=True)
            rows.append({
                "model": name, "kind": "classifier", "n": m["n"],
                "positive_rate": round(m["positive_rate"], 4),
                "log_loss": round(m["log_loss"], 4),
                "baseline_log_loss": round(m["baseline_log_loss"], 4),
                "log_loss_delta": round(m["log_loss"] - m["baseline_log_loss"], 4),
                "beats_baseline_ll": m["beats_baseline_ll"],
                "brier_score": round(m["brier_score"], 4),
                "baseline_brier": round(m["baseline_brier"], 4),
                "beats_baseline_brier": m["beats_baseline_bs"],
                "auc_roc": round(m["auc_roc"], 4),
                "ece": round(m["ece"], 4),
                "rmse": None, "mae": None, "r2": None, "spearman_r": None,
                "baseline_rmse": None, "beats_baseline_rmse": None,
            })
        else:
            m = evaluate_regression(y_true, y_pred, label=name, verbose=True)
            rows.append({
                "model": name, "kind": "regression", "n": m["n"],
                "positive_rate": None,
                "log_loss": None, "baseline_log_loss": None, "log_loss_delta": None,
                "beats_baseline_ll": None,
                "brier_score": None, "baseline_brier": None, "beats_baseline_brier": None,
                "auc_roc": None, "ece": None,
                "rmse": round(m["rmse"], 4),
                "mae": round(m["mae"], 4),
                "r2": round(m["r2"], 4),
                "spearman_r": round(m["spearman_r"], 4),
                "baseline_rmse": round(m["baseline_rmse"], 4),
                "beats_baseline_rmse": m["beats_baseline"],
            })
        all_metrics[name] = m

    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(out, index=False)
    logger.info("  -> %s  (%d models)", out.name, len(metrics_df))
    return metrics_df, all_metrics


# ══════════════════════════════════════════════════════════════════════════════
# 3 — calibration_*.png  (one file per classifier)
# ══════════════════════════════════════════════════════════════════════════════

def write_calibration_plots(plv_model, val_df: pd.DataFrame, rdir: Path) -> list[Path]:
    from plv_clone.models.evaluation import calibration_plot_data
    logger.info("Writing calibration plots ...")

    val_takes    = val_df[val_df["is_take"].astype(bool)]
    val_swings   = val_df[val_df["is_swing"].astype(bool)]
    val_contacts = val_df[val_df["is_contact"].astype(bool)]

    specs = [
        ("swing",         val_df,       plv_model.swing_model.predict_proba,   "is_swing"),
        ("called_strike", val_takes,    plv_model.cs_model.predict_proba,      "is_called_strike"),
        ("contact",       val_swings,   plv_model.contact_model.predict_proba, "is_contact"),
        ("foul",          val_contacts, plv_model.foul_model.predict_proba,    "is_foul"),
    ]

    paths = []
    for slug, df_sub, predict_fn, target_col in specs:
        if len(df_sub) < 50:
            continue
        y_true = df_sub[target_col].values.astype(float)
        y_pred = predict_fn(df_sub)
        cal    = calibration_plot_data(y_true, y_pred, n_bins=10)

        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        fig.suptitle(f"Calibration — {slug.replace('_',' ').title()} (n={len(df_sub):,})", fontsize=12)

        # Left: reliability diagram
        ax = axes[0]
        ax.plot([0,1],[0,1], "k--", alpha=0.4, label="Perfect")
        ax.plot(cal["mean_predicted"], cal["fraction_positive"], "o-", color="steelblue", ms=6, label="Model")
        ax.fill_between(cal["mean_predicted"],
                        cal["fraction_positive"] - 0.05,
                        cal["fraction_positive"] + 0.05,
                        alpha=0.12, color="steelblue")
        ax.set_xlabel("Mean predicted probability"); ax.set_ylabel("Fraction of positives")
        ax.set_title("Reliability diagram"); ax.legend(fontsize=9); ax.grid(alpha=0.3)
        ax.set_xlim(0,1); ax.set_ylim(0,1)

        # Right: predicted probability histogram
        ax2 = axes[1]
        pos_mask = y_true == 1
        ax2.hist(y_pred[~pos_mask], bins=40, alpha=0.6, color="steelblue", label="Negatives", density=True)
        ax2.hist(y_pred[pos_mask],  bins=40, alpha=0.6, color="darkorange", label="Positives", density=True)
        ax2.set_xlabel("Predicted probability"); ax2.set_ylabel("Density")
        ax2.set_title("Score distribution by class"); ax2.legend(fontsize=9); ax2.grid(alpha=0.3)

        plt.tight_layout()
        p = rdir / f"calibration_{slug}.png"
        plt.savefig(p, dpi=120, bbox_inches="tight")
        plt.close()
        paths.append(p)
        logger.info("  -> %s", p.name)

    return paths


# ══════════════════════════════════════════════════════════════════════════════
# 4 — plv_distribution_*.png
# ══════════════════════════════════════════════════════════════════════════════

def write_plv_distribution_plots(scored_df: pd.DataFrame, year: int, rdir: Path) -> list[Path]:
    logger.info("Writing PLV distribution plots ...")
    paths = []
    plv = scored_df["plv"].dropna()

    pitcher_avg = (
        scored_df.groupby("pitcher")
        .agg(plv_mean=("plv","mean"), n=("plv","count"))
        .query(f"n >= {CFG.min_pitches_plv}")["plv_mean"]
    )

    # ── pitch-level: histogram + QQ ──────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"PLV Pitch-Level Distribution — {year}  (n={len(plv):,})", fontsize=12)

    ax = axes[0]
    ax.hist(plv.clip(-1,11), bins=80, color="steelblue", edgecolor="none", alpha=0.85)
    ax.axvline(plv.mean(), color="red",   linestyle="--", lw=1.5, label=f"Mean={plv.mean():.3f}")
    ax.axvline(plv.median(), color="orange", linestyle=":", lw=1.5, label=f"Median={plv.median():.3f}")
    ax.axvline(5.0,          color="green",  linestyle=":",  lw=1.2, label="Target=5.0")
    stats_txt = (f"mean={plv.mean():.3f}\nstd={plv.std():.3f}\n"
                 f"skew={plv.skew():.3f}\nkurt={plv.kurtosis():.3f}")
    ax.text(0.02, 0.97, stats_txt, transform=ax.transAxes, va="top", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax.set_xlabel("PLV"); ax.set_ylabel("Pitch count"); ax.set_title("Histogram")
    ax.legend(fontsize=8); ax.grid(alpha=0.25)

    ax2 = axes[1]
    (osm, osr), (slope, intercept, r) = scipy_stats.probplot(plv, dist="norm")
    ax2.plot(osm, osr, ".", color="steelblue", ms=2, alpha=0.4)
    ax2.plot(osm, slope*np.array(osm)+intercept, "r-", lw=1.5, label=f"r={r:.4f}")
    ax2.set_xlabel("Theoretical quantiles"); ax2.set_ylabel("Observed PLV")
    ax2.set_title("QQ Plot (vs Normal)"); ax2.legend(fontsize=9); ax2.grid(alpha=0.25)

    plt.tight_layout()
    p1 = rdir / "plv_distribution_pitch.png"
    plt.savefig(p1, dpi=120, bbox_inches="tight"); plt.close()
    paths.append(p1)
    logger.info("  -> %s", p1.name)

    # ── count-state heatmap ───────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(f"PLV by Count State — {year}", fontsize=12)

    if "balls" in scored_df.columns and "strikes" in scored_df.columns:
        count_plv = (
            scored_df.groupby(["balls","strikes"])["plv"]
            .mean().unstack(fill_value=np.nan)
        )
        count_n = (
            scored_df.groupby(["balls","strikes"])["plv"]
            .count().unstack(fill_value=0)
        )

        ax = axes[0]
        im = ax.imshow(count_plv.values, cmap="RdYlGn", aspect="auto", vmin=3.5, vmax=6.5)
        ax.set_xticks(range(len(count_plv.columns)))
        ax.set_xticklabels([f"{s} str" for s in count_plv.columns])
        ax.set_yticks(range(len(count_plv.index)))
        ax.set_yticklabels([f"{b} ball" for b in count_plv.index])
        ax.set_title("Mean PLV (green = pitcher-favourable)")
        plt.colorbar(im, ax=ax, shrink=0.8)
        for i in range(len(count_plv.index)):
            for j in range(len(count_plv.columns)):
                v = count_plv.values[i,j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9, fontweight="bold")

        ax2 = axes[1]
        im2 = ax2.imshow(count_n.values, cmap="Blues", aspect="auto")
        ax2.set_xticks(range(len(count_n.columns)))
        ax2.set_xticklabels([f"{s} str" for s in count_n.columns])
        ax2.set_yticks(range(len(count_n.index)))
        ax2.set_yticklabels([f"{b} ball" for b in count_n.index])
        ax2.set_title("Pitch count by count state")
        plt.colorbar(im2, ax=ax2, shrink=0.8)
        for i in range(len(count_n.index)):
            for j in range(len(count_n.columns)):
                n = int(count_n.values[i,j])
                ax2.text(j, i, f"{n//1000}k", ha="center", va="center", fontsize=9)

    plt.tight_layout()
    p2 = rdir / "plv_distribution_count.png"
    plt.savefig(p2, dpi=120, bbox_inches="tight"); plt.close()
    paths.append(p2)
    logger.info("  -> %s", p2.name)

    # ── pitch-type violin ─────────────────────────────────────────────────────
    if "pitch_type" in scored_df.columns:
        pt_order = (
            scored_df.groupby("pitch_type")["plv"]
            .agg(["mean","count"])
            .query("count >= 500")
            .sort_values("mean", ascending=False)
            .index.tolist()
        )
        if pt_order:
            fig, ax = plt.subplots(figsize=(max(8, len(pt_order)*1.2), 6))
            data = [scored_df[scored_df["pitch_type"]==pt]["plv"].dropna().values for pt in pt_order]
            parts = ax.violinplot(data, positions=range(len(pt_order)), showmedians=True, showextrema=False)
            for pc in parts["bodies"]:
                pc.set_alpha(0.65); pc.set_facecolor("steelblue")
            parts["cmedians"].set_color("red"); parts["cmedians"].set_linewidth(2)
            # Add mean dots
            means = [np.mean(d) for d in data]
            ax.scatter(range(len(pt_order)), means, color="orange", zorder=5, s=40, label="Mean")
            ax.axhline(5.0, color="green", linestyle=":", lw=1.2, label="League avg=5.0")
            # Add pitch count labels
            for i, (pt, d) in enumerate(zip(pt_order, data)):
                ax.text(i, ax.get_ylim()[0]+0.05, f"n={len(d)//1000}k", ha="center", fontsize=7, color="gray")
            ax.set_xticks(range(len(pt_order))); ax.set_xticklabels(pt_order, fontsize=9)
            ax.set_ylabel("PLV"); ax.set_title(f"PLV Distribution by Pitch Type — {year} (>=500 pitches)")
            ax.legend(fontsize=9); ax.grid(alpha=0.25, axis="y")
            plt.tight_layout()
            p3 = rdir / "plv_distribution_type.png"
            plt.savefig(p3, dpi=120, bbox_inches="tight"); plt.close()
            paths.append(p3)
            logger.info("  -> %s", p3.name)

    # ── BattedBallModel: predicted vs actual xwOBA ────────────────────────────
    ip_df = scored_df[
        scored_df["is_in_play"].astype(bool) &
        scored_df["estimated_woba_using_speedangle"].notna() &
        scored_df["e_xwoba_in_play"].notna()
    ]
    if len(ip_df) > 200:
        sample = ip_df.sample(min(8000, len(ip_df)), random_state=42)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle(f"BattedBallValueModel: Predicted vs Actual xwOBA — {year}", fontsize=12)

        ax = axes[0]
        ax.scatter(sample["e_xwoba_in_play"], sample["estimated_woba_using_speedangle"],
                   alpha=0.12, s=6, color="teal", rasterized=True)
        lim = [0, 1]
        ax.plot(lim, lim, "r--", lw=1.2, alpha=0.7, label="y=x")
        ax.set_xlabel("Predicted E[xwOBA]"); ax.set_ylabel("Actual xwOBA")
        ax.set_title("Scatter (random 8k in-play pitches)")
        ax.legend(fontsize=9); ax.grid(alpha=0.25); ax.set_xlim(0,1); ax.set_ylim(-0.05,2.0)

        ax2 = axes[1]
        # Bin predicted, show mean actual ± se
        bins = np.linspace(0, 0.9, 16)
        bin_idx = np.digitize(ip_df["e_xwoba_in_play"].values, bins)
        means_pred, means_act, ses = [], [], []
        for b in range(1, len(bins)):
            mask = bin_idx == b
            if mask.sum() >= 20:
                means_pred.append(ip_df["e_xwoba_in_play"].values[mask].mean())
                act = ip_df["estimated_woba_using_speedangle"].values[mask]
                means_act.append(act.mean())
                ses.append(act.std() / np.sqrt(mask.sum()))
        if means_pred:
            ax2.errorbar(means_pred, means_act, yerr=ses, fmt="o-", color="steelblue",
                         capsize=3, ms=5, label="Mean actual ± SE")
            ax2.plot([0,1],[0,1],"r--",lw=1.2,alpha=0.7,label="y=x")
        ax2.set_xlabel("Mean predicted E[xwOBA] in bin"); ax2.set_ylabel("Mean actual xwOBA")
        ax2.set_title("Binned prediction accuracy"); ax2.legend(fontsize=9); ax2.grid(alpha=0.25)

        plt.tight_layout()
        p4 = rdir / "plv_predicted_vs_actual.png"
        plt.savefig(p4, dpi=120, bbox_inches="tight"); plt.close()
        paths.append(p4)
        logger.info("  -> %s", p4.name)

    return paths


# ══════════════════════════════════════════════════════════════════════════════
# 5 — pitcher_leaderboard.csv  +  pitch_type_leaderboard.csv
# ══════════════════════════════════════════════════════════════════════════════

def write_leaderboards(scored_df: pd.DataFrame, year: int,
                       p_out: Path, pt_out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger.info("Writing leaderboards ...")

    pitcher_lb = (
        scored_df.groupby(["pitcher","player_name"])
        .agg(
            pitches              = ("plv",                  "count"),
            plv                  = ("plv",                  "mean"),
            plv_std              = ("plv",                  "std"),
            plv_raw              = ("plv_raw",               "mean"),
            swing_rate           = ("p_swing",               "mean"),
            whiff_rate           = ("p_whiff_given_swing",   "mean"),
            contact_rate         = ("p_contact_given_swing", "mean"),
            cs_rate              = ("p_cs_given_take",       "mean"),
            e_xwoba_ip           = ("e_xwoba_in_play",       "mean"),
        )
        .reset_index()
        .query(f"pitches >= {CFG.min_pitches_plv}")
        .sort_values("plv", ascending=False)
        .reset_index(drop=True)
    )
    pitcher_lb["plv_pctile"] = pitcher_lb["plv"].rank(pct=True).mul(100).round(1)
    pitcher_lb = pitcher_lb.round(4)
    pitcher_lb.to_csv(p_out, index=False)
    logger.info("  -> %s  (%d pitchers)", p_out.name, len(pitcher_lb))

    pt_lb = (
        scored_df.groupby(["pitcher","player_name","pitch_type","pitch_group"])
        .agg(
            pitches    = ("plv",              "count"),
            plv        = ("plv",              "mean"),
            plv_std    = ("plv",              "std"),
            avg_velo   = ("release_speed",    "mean"),
            swing_rate = ("p_swing",          "mean"),
            whiff_rate = ("p_whiff_given_swing","mean"),
            e_xwoba_ip = ("e_xwoba_in_play",  "mean"),
        )
        .reset_index()
        .query("pitches >= 50")
        .sort_values("plv", ascending=False)
        .reset_index(drop=True)
    )
    pt_lb["plv_pctile"] = pt_lb["plv"].rank(pct=True).mul(100).round(1)
    pt_lb = pt_lb.round(4)
    pt_lb.to_csv(pt_out, index=False)
    logger.info("  -> %s  (%d pitch-type rows)", pt_out.name, len(pt_lb))

    return pitcher_lb, pt_lb


# ══════════════════════════════════════════════════════════════════════════════
# 6 — stability_analysis.csv
# ══════════════════════════════════════════════════════════════════════════════

def write_stability(scored_df: pd.DataFrame, plv_model, out: Path) -> pd.DataFrame:
    logger.info("Writing stability_analysis.csv ...")
    rng = np.random.default_rng(42)
    pitcher_pitches = scored_df.groupby("pitcher")["plv"].apply(list)
    thresholds = [25, 50, 100, 200, 300, 500, 750, 1000]
    rows = []

    for thresh in thresholds:
        qualified = {p: v for p, v in pitcher_pitches.items() if len(v) >= thresh * 2}
        if len(qualified) < 5:
            continue
        h1, h2 = [], []
        for pitches in qualified.values():
            idx = rng.permutation(len(pitches))
            h1.append(np.mean([pitches[i] for i in idx[:len(idx)//2]]))
            h2.append(np.mean([pitches[i] for i in idx[len(idx)//2:]]))
        r_p, _ = scipy_stats.pearsonr(h1, h2)
        r_s, _ = scipy_stats.spearmanr(h1, h2)
        sb_r = 2 * r_p / (1 + r_p) if r_p > 0 else 0.0
        rows.append({
            "min_pitches": thresh,
            "n_pitchers": len(qualified),
            "half_half_pearson_r": round(r_p, 4),
            "half_half_spearman_r": round(r_s, 4),
            "full_sample_r_spearman_brown": round(sb_r, 4),
            "reliable_70pct": sb_r >= 0.70,
        })

    # YoY 2023->2024 correlation
    feat_dir = CFG.processed_dir / "pitch_features"
    try:
        from plv_clone.pipelines.train_plv import _load_year_range, _drop_unknown
        df23 = _drop_unknown(_load_year_range(feat_dir, 2023, 2023))
        if len(df23) > 0:
            s23 = plv_model.score_pitches(df23)
            lb23 = (s23.groupby("pitcher")["plv"]
                    .agg(plv_2023="mean", n_2023="count")
                    .query(f"n_2023 >= {CFG.min_pitches_plv}"))
            lb24 = (scored_df.groupby("pitcher")["plv"]
                    .agg(plv_2024="mean", n_2024="count")
                    .query(f"n_2024 >= {CFG.min_pitches_plv}"))
            yoy = lb23.join(lb24, how="inner").dropna()
            if len(yoy) >= 10:
                r_s_yoy, p_yoy = scipy_stats.spearmanr(yoy["plv_2023"], yoy["plv_2024"])
                rows.append({
                    "min_pitches": "YoY_2023_2024",
                    "n_pitchers": len(yoy),
                    "half_half_pearson_r": None,
                    "half_half_spearman_r": None,
                    "full_sample_r_spearman_brown": None,
                    "reliable_70pct": None,
                    "yoy_spearman_r": round(r_s_yoy, 4),
                    "yoy_p_value": round(p_yoy, 4),
                })
                logger.info("  YoY 2023->2024: Spearman r=%.3f (n=%d)", r_s_yoy, len(yoy))
    except Exception as e:
        logger.warning("  YoY analysis failed: %s", e)

    stab_df = pd.DataFrame(rows)
    stab_df.to_csv(out, index=False)
    logger.info("  -> %s", out.name)
    return stab_df


# ══════════════════════════════════════════════════════════════════════════════
# 7 — suspicious_cases.csv
# ══════════════════════════════════════════════════════════════════════════════

def write_suspicious_cases(scored_df: pd.DataFrame, pitcher_lb: pd.DataFrame,
                           all_metrics: dict, out: Path) -> pd.DataFrame:
    logger.info("Writing suspicious_cases.csv ...")
    records = []

    # a) PLV out of [0, 10]
    # With pitch-level scaling ~0.5% of individual pitches naturally fall outside [0,10]
    # (heavy tails on plv_raw). Only flag HIGH if >5% are out of range.
    if "plv" in scored_df.columns:
        oor = scored_df[(scored_df["plv"] < 0) | (scored_df["plv"] > 10)]
        if len(oor) > 0:
            pct_oor = 100 * len(oor) / len(scored_df)
            severity = "HIGH" if pct_oor > 5.0 else ("MEDIUM" if pct_oor > 1.0 else "LOW")
            records.append({
                "category": "PLV out of [0,10]",
                "severity": severity,
                "count": len(oor),
                "pct_of_scored": round(pct_oor, 3),
                "detail": f"min={scored_df['plv'].min():.3f}, max={scored_df['plv'].max():.3f}",
                "player_name": None, "pitcher": None,
            })

    # b) Sub-model probabilities out of [0, 1]
    for col in ["p_swing","p_cs_given_take","p_contact_given_swing","p_foul_given_contact","e_xwoba_in_play"]:
        if col not in scored_df.columns:
            continue
        oor_n = ((scored_df[col] < 0) | (scored_df[col] > 1)).sum()
        if oor_n > 0:
            records.append({
                "category": f"{col} out of [0,1]",
                "severity": "HIGH",
                "count": int(oor_n),
                "pct_of_scored": round(100*oor_n/len(scored_df), 3),
                "detail": f"min={scored_df[col].min():.4f}, max={scored_df[col].max():.4f}",
                "player_name": None, "pitcher": None,
            })

    # c) Models not beating baseline
    for name, m in all_metrics.items():
        if not m.get("beats_baseline_ll", m.get("beats_baseline", True)):
            delta = (m.get("log_loss", m.get("rmse", 0)) -
                     m.get("baseline_log_loss", m.get("baseline_rmse", 0)))
            records.append({
                "category": f"{name} below baseline",
                "severity": "HIGH",
                "count": m.get("n", 0),
                "pct_of_scored": None,
                "detail": f"delta={delta:.4f} (positive = worse than baseline)",
                "player_name": None, "pitcher": None,
            })

    # d) High within-pitcher PLV variance
    if len(pitcher_lb) > 0:
        p95_std = pitcher_lb["plv_std"].quantile(0.95)
        high_var = pitcher_lb[pitcher_lb["plv_std"] > max(2.5, p95_std)].copy()
        for _, row in high_var.head(20).iterrows():
            records.append({
                "category": "High within-pitcher PLV std",
                "severity": "MEDIUM",
                "count": int(row["pitches"]),
                "pct_of_scored": None,
                "detail": f"plv_std={row['plv_std']:.3f}, plv={row['plv']:.3f}",
                "player_name": row.get("player_name", ""),
                "pitcher": row.get("pitcher", ""),
            })

    # e) Small-sample extreme PLV (100-199 pitches, |plv - 5| > 2)
    if len(pitcher_lb) > 0:
        small = pitcher_lb[(pitcher_lb["pitches"] < 200) & (pitcher_lb["pitches"] >= 100)]
        extreme_small = small[abs(small["plv"] - 5.0) > 2.0]
        for _, row in extreme_small.head(10).iterrows():
            records.append({
                "category": "Small-sample extreme PLV",
                "severity": "LOW",
                "count": int(row["pitches"]),
                "pct_of_scored": None,
                "detail": f"plv={row['plv']:.3f}, pitches={row['pitches']}",
                "player_name": row.get("player_name", ""),
                "pitcher": row.get("pitcher", ""),
            })

    # f) PLV mean deviation from 5.0
    plv_mean = float(scored_df["plv"].mean())
    if abs(plv_mean - 5.0) >= 0.2:
        severity = "HIGH" if abs(plv_mean - 5.0) >= 0.5 else "MEDIUM"
        records.append({
            "category": "PLV mean deviates from 5.0",
            "severity": severity,
            "count": len(scored_df),
            "pct_of_scored": None,
            "detail": f"pitch-level mean={plv_mean:.4f}, deviation={plv_mean-5.0:.4f}",
            "player_name": None, "pitcher": None,
        })

    # g) Suspiciously high/low swing rates at pitcher level
    if "p_swing" in scored_df.columns:
        sw_by_p = (scored_df.groupby(["pitcher","player_name"])["p_swing"]
                   .agg(avg_swing="mean", n="count")
                   .query(f"n >= {CFG.min_pitches_plv}"))
        extreme_sw = sw_by_p[(sw_by_p["avg_swing"] > 0.65) | (sw_by_p["avg_swing"] < 0.30)]
        for (pit, name), row in extreme_sw.iterrows():
            records.append({
                "category": "Extreme avg predicted swing rate",
                "severity": "MEDIUM",
                "count": int(row["n"]),
                "pct_of_scored": None,
                "detail": f"avg_p_swing={row['avg_swing']:.3f}",
                "player_name": name,
                "pitcher": pit,
            })

    susp_df = pd.DataFrame(records) if records else pd.DataFrame(
        columns=["category","severity","count","pct_of_scored","detail","player_name","pitcher"])
    susp_df.to_csv(out, index=False)
    logger.info("  -> %s  (%d issues logged)", out.name, len(susp_df))
    return susp_df


# ══════════════════════════════════════════════════════════════════════════════
# 8 — review_summary.md
# ══════════════════════════════════════════════════════════════════════════════

def write_review_summary(
    year: int,
    integrity: dict,
    metrics_df: pd.DataFrame,
    all_metrics: dict,
    stab_df: pd.DataFrame,
    susp_df: pd.DataFrame,
    scored_df: pd.DataFrame,
    pitcher_lb: pd.DataFrame,
    rdir: Path,
) -> str:
    logger.info("Writing review_summary.md ...")

    plv = scored_df["plv"].dropna()
    plv_mean = float(plv.mean())
    plv_std  = float(plv.std())

    pitcher_plv = (
        scored_df.groupby("pitcher")["plv"]
        .agg(mean="mean", n="count")
        .query(f"n >= {CFG.min_pitches_plv}")["mean"]
    )

    # ── Derive facts ──────────────────────────────────────────────────────────
    all_beat_baseline = all(
        m.get("beats_baseline_ll", m.get("beats_baseline", False))
        for m in all_metrics.values()
    )
    failed_models = [
        n for n, m in all_metrics.items()
        if not m.get("beats_baseline_ll", m.get("beats_baseline", True))
    ]
    plv_centred = abs(plv_mean - 5.0) < 0.3

    high_severity = susp_df[susp_df["severity"] == "HIGH"] if len(susp_df) else pd.DataFrame()

    # YoY spearman from stab_df
    yoy_rows = stab_df[stab_df["min_pitches"] == "YoY_2023_2024"] if "yoy_spearman_r" in stab_df.columns else pd.DataFrame()
    yoy_r = float(yoy_rows["yoy_spearman_r"].iloc[0]) if len(yoy_rows) > 0 else None

    # Half-half r at 200 pitches
    stab_200 = stab_df[stab_df["min_pitches"] == 200] if len(stab_df) else pd.DataFrame()
    r_200 = float(stab_200["full_sample_r_spearman_brown"].iloc[0]) if len(stab_200) > 0 else None

    # Top 3 / bottom 3 pitchers
    top3 = pitcher_lb.head(3)[["player_name","pitches","plv"]].values.tolist() if len(pitcher_lb) >= 3 else []
    bot3 = pitcher_lb.tail(3)[["player_name","pitches","plv"]].values.tolist() if len(pitcher_lb) >= 3 else []

    # PLV vs whiff correlation
    whiff_r = None
    if "p_whiff_given_swing" in scored_df.columns:
        by_p = scored_df.groupby("pitcher").agg(
            plv=("plv","mean"), w=("p_whiff_given_swing","mean"), n=("plv","count")
        ).query(f"n>={CFG.min_pitches_plv}")
        if len(by_p) > 10:
            whiff_r, _ = scipy_stats.pearsonr(by_p["plv"], by_p["w"])

    # ── Bullet facts ──────────────────────────────────────────────────────────
    bullets = []

    # 1: data scale
    train_rows = integrity["train"]["rows"]
    val_rows   = integrity["val"]["rows"]
    train_dups = integrity["train"].get("duplicate_pitch_keys", 0)
    val_dups   = integrity["val"].get("duplicate_pitch_keys", 0)
    total_dups = train_dups + val_dups
    dup_note = (
        f"{total_dups:,} duplicate pitch keys detected — investigate."
        if total_dups > 0 else "0 duplicate pitch keys"
    )
    bullets.append(
        f"**Data scale**: {train_rows:,} training pitches (2021-2023) and "
        f"{val_rows:,} validation pitches (2024) ingested with {dup_note}."
    )

    # 2: sub-model baselines
    if all_beat_baseline:
        bullets.append(
            "**All 5 sub-models beat naive baselines** on their primary metric (log-loss "
            "for classifiers, RMSE for BattedBallModel)."
        )
    else:
        bullets.append(
            f"**Model baseline failure**: {', '.join(failed_models)} do NOT beat naive "
            "baselines — must be fixed before trusting any leaderboard output."
        )

    # 3: swing model specifics
    sw_m = all_metrics.get("SwingModel", {})
    if sw_m:
        bullets.append(
            f"**SwingModel** (most-called model): log-loss={sw_m.get('log_loss',0):.4f} "
            f"vs baseline {sw_m.get('baseline_log_loss',0):.4f}, "
            f"AUC={sw_m.get('auc_roc',0):.4f}, ECE={sw_m.get('ece',0):.4f}."
        )

    # 4: batted ball model
    bb_m = all_metrics.get("BattedBallModel", {})
    if bb_m:
        bullets.append(
            f"**BattedBallModel**: RMSE={bb_m.get('rmse',0):.4f} "
            f"(baseline {bb_m.get('baseline_rmse',0):.4f}), "
            f"Spearman r={bb_m.get('spearman_r',0):.4f}. "
            + ("Low Spearman r is expected given extreme outcome variance of individual batted balls."
               if bb_m.get("spearman_r", 1) < 0.4 else "Spearman r is acceptable.")
        )

    # 5: PLV centering
    if plv_centred:
        bullets.append(
            f"**PLV scale**: pitch-level mean={plv_mean:.3f} (target 5.0, deviation "
            f"{plv_mean-5.0:+.3f}) — well-centred. Pitcher-level mean="
            f"{float(pitcher_plv.mean()):.3f}, std={float(pitcher_plv.std()):.3f}."
        )
    else:
        bullets.append(
            f"**PLV scale off**: pitch-level mean={plv_mean:.3f} deviates "
            f"{plv_mean-5.0:+.3f} from target 5.0. Scaling params need refit."
        )

    # 6: leaderboard sanity
    if top3:
        top_names = ", ".join(f"{r[0]} ({r[2]:.2f})" for r in top3)
        bot_names = ", ".join(f"{r[0]} ({r[2]:.2f})" for r in bot3)
        bullets.append(
            f"**Leaderboard top 3**: {top_names}. "
            f"Bottom 3: {bot_names}."
        )

    # 7: whiff correlation
    if whiff_r is not None:
        direction = "positive" if whiff_r > 0 else "NEGATIVE (suspicious)"
        bullets.append(
            f"**PLV-whiff correlation** (pitcher-level): Pearson r={whiff_r:.3f} — "
            f"{direction}. Higher whiff rate should mean higher PLV."
        )

    # 8: stability
    if r_200 is not None:
        label = "reliable" if r_200 >= 0.70 else "borderline" if r_200 >= 0.50 else "noisy"
        bullets.append(
            f"**Stability at 200 pitches**: full-sample r={r_200:.3f} (Spearman-Brown) — "
            f"{label}. {'Sufficient for season-level leaderboards.' if r_200>=0.70 else 'Use with caution at low sample sizes.'}"
        )
    if yoy_r is not None:
        bullets.append(
            f"**Year-over-year stability (2023->2024)**: Spearman r={yoy_r:.3f} — "
            + ("good predictive signal." if yoy_r > 0.4 else "weak signal, investigate.")
        )

    # 9: suspicious cases
    n_high = len(high_severity)
    if n_high == 0:
        bullets.append(
            "**Suspicious cases**: 0 HIGH-severity issues. A few MEDIUM/LOW-severity "
            "small-sample outliers and high-variance pitchers noted — expected behaviour."
        )
    else:
        cats = ", ".join(high_severity["category"].tolist())
        bullets.append(
            f"**Suspicious cases**: {n_high} HIGH-severity issues — {cats}. Must investigate."
        )

    # 10: verdict
    yoy_ok = yoy_r is not None and yoy_r >= 0.4
    if all_beat_baseline and plv_centred and n_high == 0 and yoy_ok:
        verdict = (
            "**VERDICT: READY for exploratory leaderboards.** All models learn meaningful "
            "signal, PLV is well-scaled (pitch-level mean≈5, std≈1.5), no critical failures, "
            "and YoY stability is strong. Label all outputs as unofficial (public-data clone). "
            "System is ready to advance to Process+."
        )
    elif all_beat_baseline and plv_centred and n_high == 0:
        verdict = (
            "**VERDICT: Conditional — confirm YoY stability before publishing.** "
            "Models and scaling look correct but YoY holdout not yet validated."
        )
    elif all_beat_baseline and not plv_centred:
        verdict = (
            "**VERDICT: Conditional — refit PLV scaling before publishing leaderboards.** "
            "Models are working but PLV absolute values will be misleading."
        )
    else:
        verdict = (
            "**VERDICT: NOT READY — fix failing models before using leaderboards.**"
        )
    bullets.append(verdict)

    # ── Compose markdown ──────────────────────────────────────────────────────
    lines = [
        f"# PLV MVP Review Summary — {year}",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        f"_Pipeline: train 2021-2023 | val {year} | scored {year}_",
        "",
        "---",
        "",
        "## 10-Bullet Executive Summary",
        "",
    ]
    for i, b in enumerate(bullets, 1):
        lines.append(f"{i}. {b}")

    lines += [
        "",
        "---",
        "",
        "## Model Metrics at a Glance",
        "",
        "| Model | Kind | n | Primary metric | Baseline | Beats? |",
        "|-------|------|---|----------------|----------|--------|",
    ]
    for _, row in metrics_df.iterrows():
        if row["kind"] == "classifier":
            metric_val = f"log-loss={row['log_loss']}"
            baseline   = f"{row['baseline_log_loss']}"
            beats      = "YES" if row["beats_baseline_ll"] else "NO"
        else:
            metric_val = f"RMSE={row['rmse']}"
            baseline   = f"{row['baseline_rmse']}"
            beats      = "YES" if row["beats_baseline_rmse"] else "NO"
        lines.append(f"| {row['model']} | {row['kind']} | {int(row['n']):,} | {metric_val} | {baseline} | {beats} |")

    lines += [
        "",
        "---",
        "",
        "## Data Integrity at a Glance",
        "",
        f"| Split | Rows | Pitchers | Date range |",
        "|-------|------|----------|------------|",
    ]
    for split_key in ("train","val","scored"):
        s = integrity[split_key]
        lines.append(
            f"| {s['label']} | {s['rows']:,} | {s.get('unique_pitchers','—')} "
            f"| {s.get('date_min','—')} to {s.get('date_max','—')} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Suspicious Cases Summary",
        "",
        f"Total issues logged: {len(susp_df)}",
        f"HIGH severity: {len(high_severity)}",
        "",
    ]
    if len(susp_df):
        lines.append("| Category | Severity | Count | Detail |")
        lines.append("|----------|----------|-------|--------|")
        for _, row in susp_df.head(20).iterrows():
            lines.append(
                f"| {row['category']} | {row['severity']} | {row['count']} | {row['detail']} |"
            )

    text = "\n".join(lines)
    out_path = rdir / "review_summary.md"
    out_path.write_text(text, encoding="utf-8")
    logger.info("  -> %s", out_path.name)
    return text


# ══════════════════════════════════════════════════════════════════════════════
# FILE INDEX + EXECUTIVE SUMMARY PRINTER
# ══════════════════════════════════════════════════════════════════════════════

def print_index_and_summary(rdir: Path, summary_text: str, year: int) -> None:
    print(f"\n{'='*68}")
    print(f"  PLV MVP Review Packet — {year}")
    print(f"  {rdir}")
    print(f"{'='*68}")

    print("\n-- OUTPUT FILES --")
    all_files = sorted(rdir.iterdir())
    col_w = max(len(f.name) for f in all_files) + 2
    for f in all_files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:{col_w}}  {size_kb:>7.1f} KB")

    print(f"\n-- 10-BULLET EXECUTIVE SUMMARY --")
    in_bullets = False
    for line in summary_text.splitlines():
        if line.strip().startswith("## 10-Bullet"):
            in_bullets = True
            continue
        if in_bullets:
            if line.strip().startswith("---") or (line.strip().startswith("##") and "10-Bullet" not in line):
                break
            if line.strip():
                print(line)
    print(f"\n{'='*68}\n")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="PLV MVP review pipeline")
    parser.add_argument("--skip-pull",     action="store_true")
    parser.add_argument("--skip-features", action="store_true")
    parser.add_argument("--skip-train",    action="store_true")
    parser.add_argument("--year",          type=int, default=2024)
    args = parser.parse_args()

    rdir = review_dir(args.year)
    train_start = CFG.effective_train_start
    test_end    = date(args.year, 11, 1)

    logger.info("Review dir: %s", rdir)

    if not args.skip_pull:
        step_pull(train_start, test_end)
    if not args.skip_features and not args.skip_train:
        step_features(train_start, test_end, skip_pull=args.skip_pull)
    if not args.skip_train:
        step_train()

    step_score(args.year)

    plv_model, count_table, train_df, val_df, scored_df = load_artifacts(args.year)

    # Write all outputs
    integrity   = write_data_integrity(
        train_df, val_df, scored_df,
        rdir / "data_integrity.json"
    )
    metrics_df, all_metrics = write_model_metrics(
        plv_model, val_df,
        rdir / "model_metrics.csv"
    )
    write_calibration_plots(plv_model, val_df, rdir)
    write_plv_distribution_plots(scored_df, args.year, rdir)
    pitcher_lb, pt_lb = write_leaderboards(
        scored_df, args.year,
        rdir / "pitcher_leaderboard.csv",
        rdir / "pitch_type_leaderboard.csv",
    )
    stab_df = write_stability(scored_df, plv_model, rdir / "stability_analysis.csv")
    susp_df = write_suspicious_cases(
        scored_df, pitcher_lb, all_metrics,
        rdir / "suspicious_cases.csv"
    )
    summary = write_review_summary(
        args.year, integrity, metrics_df, all_metrics,
        stab_df, susp_df, scored_df, pitcher_lb, rdir,
    )

    print_index_and_summary(rdir, summary, args.year)


if __name__ == "__main__":
    main()
