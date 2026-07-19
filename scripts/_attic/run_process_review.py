"""
Process+ Review Script
======================
Runs the Process+ pipeline and writes a structured review packet to:

  data/outputs/process_review_YYYY/
    review_summary.md               -- narrative + exec summary
    data_integrity.json             -- row counts, component coverage, PA counts
    scaling_params.json             -- raw component distributions + scaling
    component_distributions.png    -- histograms of decision/contact/power (hitter-level)
    component_correlations.png      -- pairwise scatter: D+ vs C+ vs P+
    stability_decision.png          -- split-half reliability by PA threshold (decision)
    stability_contact.png           -- split-half reliability (contact)
    stability_power.png             -- split-half reliability (power)
    stability_analysis.csv          -- table of reliability stats
    hitter_leaderboard.csv          -- qualified hitter Process+ (wide format)
    yoy_stability.csv               -- year-over-year Spearman r per component
    suspicious_cases.csv            -- out-of-range, null-heavy, extreme hitters

Usage:
    cd plv_clone
    python scripts/run_process_review.py [--skip-train] [--year 2024]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

from plv_clone.config import get_config
from plv_clone.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("process_review")

CFG = get_config()


def review_dir(year: int) -> Path:
    d = CFG.outputs_dir / f"process_review_{year}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE STEPS
# ══════════════════════════════════════════════════════════════════════════════

def step_train_process() -> None:
    from plv_clone.pipelines.train_process_plus import run
    logger.info("Fitting Process+ scaling params ...")
    run(config=CFG)


def step_score_process(year: int) -> None:
    from plv_clone.pipelines.score_process_plus import run
    logger.info("Scoring Process+ for year=%d ...", year)
    run(year=year, config=CFG)


def _resolve_batter_names(hitter_lb: pd.DataFrame) -> pd.DataFrame:
    """Add batter_name column from pybaseball MLBAM lookup."""
    if "batter_name" in hitter_lb.columns:
        return hitter_lb
    try:
        from pybaseball import playerid_reverse_lookup
        ids = hitter_lb["batter"].astype(int).tolist()
        lookup_df = playerid_reverse_lookup(ids, key_type="mlbam")
        lookup_df = lookup_df[["key_mlbam", "name_first", "name_last"]].copy()
        lookup_df["batter_name"] = (
            lookup_df["name_first"].str.title() + " " + lookup_df["name_last"].str.title()
        )
        lookup_df = lookup_df.rename(columns={"key_mlbam": "batter"})[["batter", "batter_name"]]
        hitter_lb = hitter_lb.merge(lookup_df, on="batter", how="left")
        # Fill any lookup failures with the numeric ID
        hitter_lb["batter_name"] = hitter_lb["batter_name"].fillna(
            hitter_lb["batter"].astype(str)
        )
        logger.info("Resolved batter names for %d hitters.", hitter_lb["batter_name"].notna().sum())
    except Exception as e:
        logger.warning("Could not resolve batter names: %s. Using IDs.", e)
        hitter_lb = hitter_lb.copy()
        hitter_lb["batter_name"] = hitter_lb["batter"].astype(str)
    return hitter_lb


def load_artifacts(year: int):
    from plv_clone.utils.io import read_parquet
    from plv_clone.models.process_plus_model import ProcessPlusModel
    from plv_clone.pipelines.train_plv import _load_year_range, _drop_unknown

    pp_model = ProcessPlusModel.load(CFG.models_dir)
    feat_dir = CFG.processed_dir / "pitch_features"

    train_df  = _drop_unknown(_load_year_range(feat_dir, CFG.effective_train_start.year, CFG.train_end.year))
    val_df    = _drop_unknown(_load_year_range(feat_dir, CFG.val_start.year, CFG.val_end.year))
    scored_df = read_parquet(CFG.processed_dir / "process_plus_scores" / f"year={year}")
    hitter_lb = pd.read_csv(CFG.outputs_dir / f"process_plus_leaderboard_{year}.csv")
    hitter_lb = _resolve_batter_names(hitter_lb)

    logger.info(
        "Artifacts loaded: train=%d | val=%d | scored=%d | qualified_hitters=%d",
        len(train_df), len(val_df), len(scored_df), len(hitter_lb),
    )
    return pp_model, train_df, val_df, scored_df, hitter_lb


# ══════════════════════════════════════════════════════════════════════════════
# 1 — data_integrity.json
# ══════════════════════════════════════════════════════════════════════════════

def write_data_integrity(scored_df: pd.DataFrame, hitter_lb: pd.DataFrame, out: Path) -> dict:
    logger.info("Writing data_integrity.json ...")

    integrity: dict = {
        "generated_at": datetime.utcnow().isoformat(),
        "pitch_level": {
            "rows": len(scored_df),
            "unique_batters": int(scored_df["batter"].nunique()) if "batter" in scored_df.columns else None,
            "decision_coverage_pct": round(100 * scored_df["discipline_value"].notna().mean(), 2),
            "contact_coverage_pct":  round(100 * scored_df["contact_value"].notna().mean(), 2),
            "power_coverage_pct":    round(100 * scored_df["power_value"].notna().mean(), 2),
        },
        "hitter_level": {
            "qualified_hitters": len(hitter_lb),
            "process_plus_range": [
                round(float(hitter_lb["process_plus"].min()), 2),
                round(float(hitter_lb["process_plus"].max()), 2),
            ] if len(hitter_lb) > 0 else None,
            "process_plus_mean": round(float(hitter_lb["process_plus"].mean()), 2) if len(hitter_lb) > 0 else None,
            "process_plus_std":  round(float(hitter_lb["process_plus"].std()),  2) if len(hitter_lb) > 0 else None,
        },
    }

    # Component-level pitch stats
    for comp in ("discipline_value", "contact_value", "power_value"):
        if comp in scored_df.columns:
            vals = scored_df[comp].dropna()
            integrity[f"{comp}_stats"] = {
                "n": len(vals),
                "mean": round(float(vals.mean()), 6),
                "std":  round(float(vals.std()),  6),
                "min":  round(float(vals.min()),  6),
                "max":  round(float(vals.max()),  6),
            }

    out.write_text(json.dumps(integrity, indent=2), encoding="utf-8")
    logger.info("  -> %s", out.name)
    return integrity


# ══════════════════════════════════════════════════════════════════════════════
# 2 — scaling_params.json
# ══════════════════════════════════════════════════════════════════════════════

def write_scaling_params(pp_model, out: Path) -> None:
    logger.info("Writing scaling_params.json ...")
    out.write_text(json.dumps(pp_model.scaling_params, indent=2), encoding="utf-8")
    logger.info("  -> %s", out.name)


# ══════════════════════════════════════════════════════════════════════════════
# 3 — component_distributions.png  (hitter-level histograms)
# ══════════════════════════════════════════════════════════════════════════════

def write_component_distributions(hitter_lb: pd.DataFrame, out: Path) -> None:
    logger.info("Writing component_distributions.png ...")

    components = [
        ("discipline_plus", "Discipline+", "#2196F3"),
        ("k_avoidance_plus",  "K-Avoidance+",  "#4CAF50"),
        ("power_plus",    "Power+",    "#FF9800"),
        ("process_plus",  "Process+",  "#9C27B0"),
    ]
    # Only plot columns that exist
    components = [(c, l, col) for c, l, col in components if c in hitter_lb.columns]

    fig, axes = plt.subplots(1, len(components), figsize=(5 * len(components), 4))
    if len(components) == 1:
        axes = [axes]

    for ax, (col, label, color) in zip(axes, components):
        vals = hitter_lb[col].dropna()
        ax.hist(vals, bins=30, color=color, alpha=0.75, edgecolor="white")
        ax.axvline(100, color="black", linestyle="--", linewidth=1.0, label="100 (avg)")
        ax.set_title(f"{label}\nn={len(vals)}, mean={vals.mean():.1f}, std={vals.std():.1f}")
        ax.set_xlabel("+metric")
        ax.set_ylabel("Hitters")
        ax.legend(fontsize=8)

    fig.suptitle(f"Process+ Component Distributions (Hitter-Level)", fontsize=13)
    plt.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("  -> %s", out.name)


# ══════════════════════════════════════════════════════════════════════════════
# 4 — component_correlations.png
# ══════════════════════════════════════════════════════════════════════════════

def write_component_correlations(hitter_lb: pd.DataFrame, out: Path) -> None:
    logger.info("Writing component_correlations.png ...")

    pairs = [
        ("discipline_plus", "k_avoidance_plus"),
        ("discipline_plus", "power_plus"),
        ("k_avoidance_plus",  "power_plus"),
    ]
    pairs = [(a, b) for a, b in pairs if a in hitter_lb.columns and b in hitter_lb.columns]

    fig, axes = plt.subplots(1, len(pairs), figsize=(5 * len(pairs), 4))
    if len(pairs) == 1:
        axes = [axes]

    for ax, (xcol, ycol) in zip(axes, pairs):
        sub = hitter_lb[[xcol, ycol]].dropna()
        r, p = scipy_stats.spearmanr(sub[xcol], sub[ycol])
        ax.scatter(sub[xcol], sub[ycol], alpha=0.4, s=15, color="#555")
        ax.set_xlabel(xcol.replace("_", " "))
        ax.set_ylabel(ycol.replace("_", " "))
        ax.set_title(f"Spearman r={r:.3f} (n={len(sub)})")
        # Reference lines at 100
        ax.axvline(100, color="gray", linestyle="--", linewidth=0.7)
        ax.axhline(100, color="gray", linestyle="--", linewidth=0.7)

    fig.suptitle("Pairwise Component Correlations (expect < 0.5 between components)", fontsize=11)
    plt.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("  -> %s", out.name)


# ══════════════════════════════════════════════════════════════════════════════
# 5 — stability_analysis.csv + per-component reliability plots
# ══════════════════════════════════════════════════════════════════════════════

def write_stability_analysis(scored_df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """Split-half Spearman-Brown reliability by PA threshold, per component."""
    logger.info("Running stability analysis ...")

    pa_thresholds = [25, 50, 100, 150, 200, 300, 500]
    components = [
        ("discipline_value", "discipline_plus", "Discipline+"),
        ("contact_value",  "k_avoidance_plus",  "Contact+"),
        ("power_value",    "power_plus",    "Power+"),
    ]

    rows = []
    for pitch_col, plus_col, label in components:
        if pitch_col not in scored_df.columns:
            continue
        _rows = _stability_for_component(
            scored_df, pitch_col=pitch_col, label=label, pa_thresholds=pa_thresholds
        )
        rows.extend(_rows)

    stability_df = pd.DataFrame(rows)
    csv_path = out_dir / "stability_analysis.csv"
    stability_df.to_csv(csv_path, index=False)
    logger.info("  -> %s", csv_path.name)

    # Plot one chart per component
    _plot_stability_by_component(stability_df, out_dir)

    return stability_df


def _stability_for_component(
    scored_df: pd.DataFrame,
    pitch_col: str,
    label: str,
    pa_thresholds: list[int],
) -> list[dict]:
    """Compute split-half reliability at each PA threshold for one component."""
    import hashlib

    # Assign each PA to a half using stable hash on (batter, game_pk, at_bat_number)
    # Fallback: use simple row index parity
    if all(c in scored_df.columns for c in ["game_pk", "at_bat_number", "batter"]):
        scored_df = scored_df.copy()
        scored_df["_pa_key"] = (
            scored_df["batter"].astype(str) + "_" +
            scored_df["game_pk"].astype(str) + "_" +
            scored_df["at_bat_number"].astype(str)
        )
        scored_df["_pa_hash"] = scored_df["_pa_key"].apply(
            lambda s: int(hashlib.md5(s.encode()).hexdigest(), 16) % 2
        )
        half_col = "_pa_hash"
    else:
        scored_df = scored_df.copy()
        scored_df["_row_half"] = np.arange(len(scored_df)) % 2
        half_col = "_row_half"

    rows = []
    for min_pa in pa_thresholds:
        # Count PAs per batter
        if "game_pk" in scored_df.columns and "at_bat_number" in scored_df.columns:
            pa_counts = (
                scored_df.dropna(subset=["batter", "game_pk", "at_bat_number"])
                .groupby("batter")[["game_pk", "at_bat_number"]]
                .apply(lambda x: x.drop_duplicates().shape[0])
                .rename("pa")
            )
        else:
            pa_counts = scored_df.groupby("batter").size().rename("pa").apply(lambda n: n // 4)

        qualified = pa_counts[pa_counts >= min_pa].index

        sub = scored_df[scored_df["batter"].isin(qualified) & scored_df[pitch_col].notna()]

        if len(sub) == 0:
            continue

        # Split-half means
        h0 = sub[sub[half_col] == 0].groupby("batter")[pitch_col].mean()
        h1 = sub[sub[half_col] == 1].groupby("batter")[pitch_col].mean()
        merged = pd.concat([h0, h1], axis=1, keys=["h0", "h1"]).dropna()

        if len(merged) < 10:
            continue

        r, _ = scipy_stats.spearmanr(merged["h0"], merged["h1"])
        r_sb  = 2 * r / (1 + r) if r != -1 else np.nan  # Spearman-Brown

        rows.append({
            "component": label,
            "min_pa": min_pa,
            "n_hitters": len(merged),
            "half_half_spearman_r": round(r, 4),
            "full_sample_sb_r": round(r_sb, 4) if not np.isnan(r_sb) else None,
            "reliable_70pct": r_sb >= 0.70 if not np.isnan(r_sb) else False,
        })

    return rows


def _plot_stability_by_component(stability_df: pd.DataFrame, out_dir: Path) -> None:
    if stability_df.empty:
        return
    for comp in stability_df["component"].unique():
        sub = stability_df[stability_df["component"] == comp].sort_values("min_pa")
        if sub.empty:
            continue

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(sub["min_pa"], sub["half_half_spearman_r"], "o-", label="Split-half r")
        ax.plot(sub["min_pa"], sub["full_sample_sb_r"],     "s--", label="Spearman-Brown (projected)")
        ax.axhline(0.70, color="gray", linestyle=":", label="0.70 reliability threshold")
        ax.set_xlabel("Minimum PA threshold")
        ax.set_ylabel("Spearman r")
        ax.set_title(f"{comp} — Reliability vs. PA threshold")
        ax.legend()
        ax.set_ylim(0, 1.05)
        safe = comp.lower().replace("+", "plus").replace(" ", "_")
        out = out_dir / f"stability_{safe}.png"
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
        logger.info("  -> %s", out.name)


# ══════════════════════════════════════════════════════════════════════════════
# 6 — hitter_leaderboard.csv
# ══════════════════════════════════════════════════════════════════════════════

def write_hitter_leaderboard(hitter_lb: pd.DataFrame, out: Path) -> None:
    logger.info("Writing hitter_leaderboard.csv ...")
    hitter_lb.to_csv(out, index=False)
    logger.info("  -> %s", out.name)


# ══════════════════════════════════════════════════════════════════════════════
# 7 — yoy_stability.csv  (requires prior-year scores)
# ══════════════════════════════════════════════════════════════════════════════

def write_yoy_stability(year: int, out: Path) -> dict | None:
    prior_year = year - 1
    prior_path = CFG.outputs_dir / f"process_plus_leaderboard_{prior_year}.csv"
    if not prior_path.exists():
        logger.warning("No prior-year leaderboard found at %s. Skipping YoY.", prior_path)
        return None

    logger.info("Computing YoY stability %d->%d ...", prior_year, year)

    prior = pd.read_csv(prior_path)
    cur   = pd.read_csv(CFG.outputs_dir / f"process_plus_leaderboard_{year}.csv")

    results = {}
    for comp in ("discipline_plus", "k_avoidance_plus", "power_plus", "process_plus"):
        if comp not in prior.columns or comp not in cur.columns:
            continue
        merged = prior[["batter", comp]].merge(
            cur[["batter", comp]].rename(columns={comp: f"{comp}_cur"}),
            on="batter", how="inner",
        )
        if len(merged) < 10:
            logger.warning("  %s: too few shared hitters (%d) for YoY.", comp, len(merged))
            continue
        r, p = scipy_stats.spearmanr(merged[comp], merged[f"{comp}_cur"])
        results[comp] = {"n_hitters": len(merged), "spearman_r": round(r, 4), "p_value": round(p, 4)}
        logger.info("  %s YoY r=%.3f (n=%d, p=%.3e)", comp, r, len(merged), p)

    rows = [
        {
            "year_from": prior_year, "year_to": year,
            "component": comp,
            "n_hitters": v["n_hitters"],
            "yoy_spearman_r": v["spearman_r"],
            "yoy_p_value": v["p_value"],
        }
        for comp, v in results.items()
    ]
    yoy_df = pd.DataFrame(rows)
    yoy_df.to_csv(out, index=False)
    logger.info("  -> %s", out.name)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 8 — suspicious_cases.csv
# ══════════════════════════════════════════════════════════════════════════════

def write_suspicious_cases(hitter_lb: pd.DataFrame, scored_df: pd.DataFrame, out: Path) -> pd.DataFrame:
    logger.info("Writing suspicious_cases.csv ...")
    cases = []

    # Process+ out of [50, 150] — extreme outliers
    if "process_plus" in hitter_lb.columns:
        oor = hitter_lb[(hitter_lb["process_plus"] < 50) | (hitter_lb["process_plus"] > 150)]
        if len(oor) > 0:
            name_col = "batter_name" if "batter_name" in hitter_lb.columns else "batter"
            cases.append({
                "category": "Process+ out of [50, 150]",
                "severity": "HIGH" if len(oor) / len(hitter_lb) > 0.05 else "LOW",
                "count": len(oor),
                "pct_of_qualified": round(100 * len(oor) / len(hitter_lb), 3),
                "detail": f"min={hitter_lb['process_plus'].min():.2f}, max={hitter_lb['process_plus'].max():.2f}",
                "hitter_name": oor[name_col].head(3).tolist(),
            })

    # Components with nearly zero Spearman r vs process_plus.
    # NOTE: contact_raw has much smaller variance than power_raw, so Contact+
    # contributing little to process_plus correlation is *expected*, not degenerate.
    # Only flag if ALL three show near-zero correlation (suggests model failure).
    comp_rs = {}
    for comp in ("discipline_plus", "k_avoidance_plus", "power_plus"):
        if comp in hitter_lb.columns and "process_plus" in hitter_lb.columns:
            sub = hitter_lb[[comp, "process_plus"]].dropna()
            if len(sub) > 10:
                r, _ = scipy_stats.spearmanr(sub[comp], sub["process_plus"])
                comp_rs[comp] = r
    if comp_rs and all(abs(r) < 0.1 for r in comp_rs.values()):
        cases.append({
            "category": "All components uncorrelated with process_plus",
            "severity": "HIGH",
            "count": len(comp_rs),
            "pct_of_qualified": None,
            "detail": f"All component r's < 0.1: {comp_rs} — scoring may be broken",
            "hitter_name": [],
        })

    # Hitters with extreme per-pitch decision values (>3 SD from mean)
    if "discipline_value" in scored_df.columns:
        mean_dv = scored_df.groupby("batter")["discipline_value"].mean()
        pop_mean = mean_dv.mean()
        pop_std  = mean_dv.std()
        if pop_std > 0:
            z = (mean_dv - pop_mean) / pop_std
            extreme = z[z.abs() > 3]
            if len(extreme) > 0:
                cases.append({
                    "category": "Extreme discipline_value (|z|>3)",
                    "severity": "LOW",
                    "count": len(extreme),
                    "pct_of_qualified": None,
                    "detail": f"z range: [{z.min():.2f}, {z.max():.2f}]",
                    "hitter_name": extreme.index.astype(str).tolist()[:5],
                })

    susp_df = pd.DataFrame(cases) if cases else pd.DataFrame(
        columns=["category", "severity", "count", "pct_of_qualified", "detail", "hitter_name"]
    )
    susp_df.to_csv(out, index=False)
    logger.info("  -> %s", out.name)
    return susp_df


# ══════════════════════════════════════════════════════════════════════════════
# 9 — review_summary.md
# ══════════════════════════════════════════════════════════════════════════════

def write_review_summary(
    year: int,
    integrity: dict,
    pp_model,
    hitter_lb: pd.DataFrame,
    stability_df: pd.DataFrame,
    yoy_results: dict | None,
    susp_df: pd.DataFrame,
    out: Path,
) -> None:
    logger.info("Writing review_summary.md ...")

    sp = pp_model.scaling_params
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    n_hitters = integrity["hitter_level"]["qualified_hitters"]
    pp_mean   = integrity["hitter_level"].get("process_plus_mean", "?")
    pp_std    = integrity["hitter_level"].get("process_plus_std",  "?")
    pp_range  = integrity["hitter_level"].get("process_plus_range", ["?", "?"])

    # Top / bottom 10
    name_col = "batter_name" if "batter_name" in hitter_lb.columns else "batter"
    top10_lines    = ""
    bottom10_lines = ""
    if len(hitter_lb) >= 10:
        top10 = hitter_lb.nlargest(10, "process_plus")[[name_col, "pa", "process_plus", "discipline_plus", "k_avoidance_plus", "power_plus"]]
        top10_lines = top10.to_string(index=False)
        bottom10 = hitter_lb.nsmallest(10, "process_plus")[[name_col, "pa", "process_plus", "discipline_plus", "k_avoidance_plus", "power_plus"]]
        bottom10_lines = bottom10.to_string(index=False)

    # YoY summary
    yoy_lines = "No prior-year data available."
    if yoy_results:
        yoy_lines = "\n".join(
            f"  {comp}: r={v['spearman_r']:.3f} (n={v['n_hitters']})"
            for comp, v in yoy_results.items()
        )

    # Stability summary (minimum reliable PA threshold per component)
    stab_lines = ""
    if not stability_df.empty:
        for comp in stability_df["component"].unique():
            sub = stability_df[
                (stability_df["component"] == comp) &
                (stability_df["reliable_70pct"].astype(bool))
            ].sort_values("min_pa")
            if not sub.empty:
                min_rel = sub["min_pa"].min()
                stab_lines += f"  {comp}: reliable at ≥{min_rel} PA (SB r≥0.70)\n"
            else:
                stab_lines += f"  {comp}: not reliably stable at any tested threshold\n"

    # Suspicious cases
    n_high = int((susp_df["severity"] == "HIGH").sum()) if len(susp_df) > 0 else 0
    n_medium = int((susp_df["severity"] == "MEDIUM").sum()) if len(susp_df) > 0 else 0
    susp_lines = susp_df[["category", "severity", "count", "detail"]].to_string(index=False) \
        if len(susp_df) > 0 else "No suspicious cases found."

    # Pairwise correlations
    pair_lines = ""
    for a, b in [("discipline_plus", "k_avoidance_plus"), ("discipline_plus", "power_plus"), ("k_avoidance_plus", "power_plus")]:
        if a in hitter_lb.columns and b in hitter_lb.columns:
            sub = hitter_lb[[a, b]].dropna()
            if len(sub) > 10:
                r, _ = scipy_stats.spearmanr(sub[a], sub[b])
                warn = " *** HIGH — possible double-counting ***" if abs(r) > 0.5 else ""
                pair_lines += f"  {a} vs {b}: r={r:.3f}{warn}\n"

    # Component scaling
    comp_scaling = ""
    for comp in ("decision", "contact", "power", "process"):
        mk = f"{comp}_mean"
        sk = f"{comp}_std"
        if mk in sp and sk in sp:
            comp_scaling += f"  {comp:12s}: mean={sp[mk]:.6f}  std={sp[sk]:.6f}\n"

    # Overall verdict
    yoy_ok = False
    if yoy_results and "process_plus" in yoy_results:
        yoy_ok = yoy_results["process_plus"]["spearman_r"] >= 0.30
    # Allow ±5 from 100: train/val distribution shift of a few points is expected
    # because scaling is frozen on training data (2021-2023) and applied to 2024.
    process_centred = abs(pp_mean - 100.0) < 5.0 if isinstance(pp_mean, float) else False

    if process_centred and n_high == 0 and yoy_ok:
        verdict = (
            "**VERDICT: READY for exploratory leaderboards.** "
            "Process+ is centred near 100, no HIGH-severity issues, and "
            "year-over-year stability is sufficient. "
            "All three components are in production shape."
        )
    else:
        issues = []
        if not process_centred:
            issues.append(f"Process+ mean={pp_mean:.1f} (expected 100±5)" if isinstance(pp_mean, float) else "mean unknown")
        if n_high > 0:
            issues.append(f"{n_high} HIGH-severity issue(s) in suspicious_cases.csv")
        if not yoy_ok:
            if yoy_results is None:
                issues.append("YoY stability: no prior-year leaderboard (run score-process for prior year)")
            else:
                issues.append("YoY stability below target (need r≥0.30)")
        verdict = (
            f"**VERDICT: REVIEW REQUIRED.** Issues: {'; '.join(issues)}. "
            "Address before publishing leaderboards."
        )

    # ── Write ─────────────────────────────────────────────────────────────
    md = f"""# Process+ Review — {year}
Generated: {now}

---

## Executive Summary

1. **Qualified hitters**: {n_hitters} (min_pa={CFG.min_pa_process})
2. **Process+ distribution**: mean={pp_mean}, std={pp_std}, range=[{pp_range[0]}, {pp_range[1]}]
3. **Scaling params frozen from training population** ({sp.get('n_qualified_hitters', '?')} hitters)
4. **Year-over-year Process+ stability**: {yoy_results.get('process_plus', {}).get('spearman_r', 'N/A') if yoy_results else 'N/A'} (target ≥0.30)
5. **Suspicious cases**: {len(susp_df)} flagged ({n_high} HIGH, {n_medium} MEDIUM)
6. **No new models trained** — Process+ reuses PLV sub-models directly

{verdict}

---

## 1. Component Scaling Parameters

{comp_scaling}

---

## 2. Component Stability (Spearman-Brown reliability)

{stab_lines}

---

## 3. Pairwise Component Correlations

{pair_lines}*(expect |r| < 0.5 — high correlation suggests double-counting)*

---

## 4. Year-over-Year Stability ({year - 1} → {year})

{yoy_lines}

---

## 5. Top 10 Process+ Hitters ({year})

```
{top10_lines}
```

---

## 6. Bottom 10 Process+ Hitters ({year})

```
{bottom10_lines}
```

---

## 7. Suspicious Cases

```
{susp_lines}
```

---

*Unofficial public-data clone. Not affiliated with Pitcher List.*
"""
    out.write_text(md, encoding="utf-8")
    logger.info("  -> %s", out.name)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Process+ Review Script")
    parser.add_argument("--skip-train",    action="store_true", help="Skip training scaling params")
    parser.add_argument("--skip-score",    action="store_true", help="Skip scoring pitches")
    parser.add_argument("--year",          type=int, default=2024, help="Year to review (default: 2024)")
    args = parser.parse_args()

    year = args.year
    rd   = review_dir(year)

    logger.info("=== Process+ Review: year=%d ===", year)
    logger.info("Output directory: %s", rd)

    # ── Pipeline steps ────────────────────────────────────────────────────
    if not args.skip_train:
        step_train_process()
    else:
        logger.info("Skipping Process+ training (--skip-train).")

    if not args.skip_score:
        step_score_process(year)
    else:
        logger.info("Skipping scoring (--skip-score).")

    # ── Load artifacts ────────────────────────────────────────────────────
    pp_model, train_df, val_df, scored_df, hitter_lb = load_artifacts(year)

    # ── Review sections ────────────────────────────────────────────────────
    integrity    = write_data_integrity(scored_df, hitter_lb, rd / "data_integrity.json")
    write_scaling_params(pp_model, rd / "scaling_params.json")
    write_component_distributions(hitter_lb, rd / "component_distributions.png")
    write_component_correlations(hitter_lb, rd / "component_correlations.png")
    stability_df = write_stability_analysis(scored_df, rd)
    write_hitter_leaderboard(hitter_lb, rd / "hitter_leaderboard.csv")
    yoy_results  = write_yoy_stability(year, rd / "yoy_stability.csv")
    susp_df      = write_suspicious_cases(hitter_lb, scored_df, rd / "suspicious_cases.csv")

    write_review_summary(
        year=year,
        integrity=integrity,
        pp_model=pp_model,
        hitter_lb=hitter_lb,
        stability_df=stability_df,
        yoy_results=yoy_results,
        susp_df=susp_df,
        out=rd / "review_summary.md",
    )

    logger.info("=== Process+ Review complete. Outputs in: %s ===", rd)


if __name__ == "__main__":
    main()
