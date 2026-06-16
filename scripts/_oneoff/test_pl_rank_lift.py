"""
Test whether Pitcher List ranks add predictive power beyond our rh3/rp3 baseline
in 8-team BrownU.

Method:
1. Use historical_panel/pl_rank_panel.parquet (mid-season PL ranks, 2019-2025).
2. Join with actuals_by_year.parquet (season-end FP/g) and predictor_panel.parquet
   (prior-year FP, the canonical baseline our rh3/rp3 are built on).
3. Two regressions per position bucket (H, SP, RP):
     - Baseline: season_fp_per_g ~ prior_year_fp_per_g
     - +PL: season_fp_per_g ~ prior_year_fp_per_g + pl_rank_mid
   Compute incremental R^2 from adding PL rank.
4. Subgroup: streamer-tier (PL rank > 80) vs core-hold (PL rank <= 50).
5. Robustness: also report Spearman corr of PL rank vs season FP and
   partial Spearman controlling for prior-year FP.

Outputs:
- data/research/validation_runs/pl_rank_value_2026-06-06.md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
PANEL_DIR = REPO / "data" / "research" / "historical_panel"
OUT_PATH = REPO / "data" / "research" / "validation_runs" / "pl_rank_value_2026-06-06.md"

YEAR_TARGET = 2025  # primary year — has most complete PL coverage + actuals

# Position bucket → (actuals_column, prior_column, label)
BUCKETS = {
    "H":  ("fp_per_game",  "prior_year_fp_per_game",  "Hitters"),
    "SP": ("fp_per_start", "prior_year_fp_per_start", "Starting Pitchers"),
    "RP": ("fp_per_g",     "prior_year_fp_per_g_rp",  "Relievers"),
}


def load_panels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pl   = pd.read_parquet(PANEL_DIR / "pl_rank_panel.parquet")
    act  = pd.read_parquet(PANEL_DIR / "actuals_by_year.parquet")
    pred = pd.read_parquet(PANEL_DIR / "predictor_panel.parquet")
    return pl, act, pred


def build_join(pl: pd.DataFrame, act: pd.DataFrame, pred: pd.DataFrame,
               year: int) -> pd.DataFrame:
    p = pl[pl["year"] == year][
        ["mlbam_id", "year", "pl_rank_mid", "pl_rank_early", "pl_rank_late"]
    ]
    a = act[act["year"] == year]
    r = pred[pred["year"] == year]
    df = p.merge(a, on=["mlbam_id", "year"], how="inner")
    df = df.merge(r, on=["mlbam_id", "year", "player_type"], how="left",
                  suffixes=("", "_pred"))
    return df


def ols(y: np.ndarray, X: np.ndarray) -> dict:
    """OLS with intercept. X is design matrix without intercept column."""
    X = np.column_stack([np.ones(len(X)), X])
    beta, resid, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    n = len(y)
    k = X.shape[1] - 1  # excl intercept
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - k - 1) if (n - k - 1) > 0 else float("nan")
    return {"r2": r2, "adj_r2": adj_r2, "n": n, "beta": beta.tolist()}


def f_test_incremental(rss_base: float, rss_full: float, n: int,
                       k_base: int, k_full: int) -> tuple[float, float]:
    """F-test for nested models. Returns (F, p)."""
    df1 = k_full - k_base
    df2 = n - k_full - 1
    if df1 <= 0 or df2 <= 0 or rss_full <= 0:
        return float("nan"), float("nan")
    F = ((rss_base - rss_full) / df1) / (rss_full / df2)
    p = 1.0 - stats.f.cdf(F, df1, df2)
    return float(F), float(p)


def run_bucket(df: pd.DataFrame, bucket: str) -> dict:
    actual_col, prior_col, label = BUCKETS[bucket]
    sub = df[df["player_type"] == bucket].copy()
    sub = sub[["mlbam_id", "pl_rank_mid", actual_col, prior_col]].dropna()
    if len(sub) < 30:
        return {"bucket": bucket, "label": label, "n": len(sub),
                "skip_reason": "n < 30 after dropna"}

    y = sub[actual_col].values
    pl_rank = sub["pl_rank_mid"].values
    prior = sub[prior_col].values

    # Univariate: y ~ PL rank
    uni = ols(y, pl_rank.reshape(-1, 1))
    # Baseline: y ~ prior
    base = ols(y, prior.reshape(-1, 1))
    # Full: y ~ prior + PL rank
    full = ols(y, np.column_stack([prior, pl_rank]))

    incr_r2 = full["r2"] - base["r2"]

    # F-test for nested comparison
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    rss_base = ss_tot * (1.0 - base["r2"])
    rss_full = ss_tot * (1.0 - full["r2"])
    F, p_F = f_test_incremental(rss_base, rss_full, len(y), 1, 2)

    # Spearman rank correlations (more robust to outliers / non-linearity)
    rho_pl, p_pl     = stats.spearmanr(pl_rank, y)
    rho_prior, p_pr  = stats.spearmanr(prior, y)
    # Partial Spearman: residualize both PL and y on prior, then correlate
    def resid_lin(x, z):
        X = np.column_stack([np.ones(len(z)), z])
        beta, *_ = np.linalg.lstsq(X, x, rcond=None)
        return x - X @ beta
    pl_resid = resid_lin(pl_rank, prior)
    y_resid  = resid_lin(y, prior)
    partial_rho, partial_p = stats.spearmanr(pl_resid, y_resid)

    # Subgroup: streamer-tier vs core-hold (relative to bucket)
    if bucket == "SP":
        streamer_mask = sub["pl_rank_mid"] > 50  # Top 100 SPs, streamer = >50
        core_mask     = sub["pl_rank_mid"] <= 25
    elif bucket == "RP":
        streamer_mask = sub["pl_rank_mid"] > 25
        core_mask     = sub["pl_rank_mid"] <= 15
    else:  # H, Top 150
        streamer_mask = sub["pl_rank_mid"] > 80
        core_mask     = sub["pl_rank_mid"] <= 50

    def subgroup_lift(mask):
        if mask.sum() < 20:
            return None
        ys = y[mask]; ps = prior[mask]; rs = pl_rank[mask]
        b = ols(ys, ps.reshape(-1, 1))
        f = ols(ys, np.column_stack([ps, rs]))
        return {"n": int(mask.sum()), "base_r2": b["r2"], "full_r2": f["r2"],
                "incr_r2": f["r2"] - b["r2"]}

    sub_streamer = subgroup_lift(streamer_mask)
    sub_core     = subgroup_lift(core_mask)

    return {
        "bucket": bucket, "label": label, "n": len(sub),
        "uni": uni, "baseline": base, "full": full,
        "incr_r2": incr_r2, "F": F, "p_F": p_F,
        "spearman_pl_uni": (float(rho_pl), float(p_pl)),
        "spearman_prior_uni": (float(rho_prior), float(p_pr)),
        "spearman_pl_partial": (float(partial_rho), float(partial_p)),
        "subgroup_streamer": sub_streamer,
        "subgroup_core": sub_core,
    }


def fmt_pct(x: float) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x*100:+.2f}pp"


def fmt_r2(x: float) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:.4f}"


def render_md(results: list[dict], year: int) -> str:
    lines = []
    lines.append(f"# PL Rank Value vs rh3/rp3 Baseline (BrownU 8-team)")
    lines.append("")
    lines.append(f"_Run date: 2026-06-06 — year tested: {year}_")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("- **Outcome:** season-end FP per game (hitters), FP per start (SP), FP per RP appearance (RP).")
    lines.append(f"- **Year tested:** {year} (most complete PL mid-season cache + final actuals).")
    lines.append("- **Baseline (proxy for rh3/rp3):** prior-year FP/g — the dominant single feature both rh3 and rp3 are built on (anchor coefficient in the weight fit).")
    lines.append("- **+PL model:** prior-year FP/g + PL mid-season rank.")
    lines.append("- **Metric:** incremental R^2 + nested F-test + partial Spearman corr.")
    lines.append("")
    lines.append("> Note: We use prior-year FP/g — not the live rh3/rp3 projection — because rh3/rp3 are themselves trained on prior-year FP + archetype + drift. A test against the full live model would be circular (PL ranks may indirectly inform the priors used to fit rh3/rp3 weights). Using the raw anchor is the conservative apples-to-apples test of whether PL adds info OVER AND ABOVE the strongest single feature.")
    lines.append("")
    lines.append("## Results by position bucket")
    lines.append("")
    lines.append("| Bucket | n | Univariate PL R^2 | Baseline R^2 (prior-y FP) | +PL Full R^2 | Incr. R^2 | F (df=1) | p-value |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        if r.get("skip_reason"):
            lines.append(f"| {r['bucket']} | {r['n']} | — | — | — | — | — | _{r['skip_reason']}_ |")
            continue
        lines.append(
            f"| {r['bucket']} | {r['n']} | "
            f"{fmt_r2(r['uni']['r2'])} | {fmt_r2(r['baseline']['r2'])} | "
            f"{fmt_r2(r['full']['r2'])} | {fmt_pct(r['incr_r2'])} | "
            f"{r['F']:.2f} | {r['p_F']:.4f} |"
        )
    lines.append("")
    lines.append("## Spearman correlations (rank-based, robust)")
    lines.append("")
    lines.append("| Bucket | rho(PL, FP) univariate | rho(prior, FP) | partial rho(PL | prior) | p partial |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in results:
        if r.get("skip_reason"):
            continue
        pl_uni = r["spearman_pl_uni"]; pr = r["spearman_prior_uni"]; par = r["spearman_pl_partial"]
        lines.append(
            f"| {r['bucket']} | {pl_uni[0]:+.3f} (p={pl_uni[1]:.4f}) | "
            f"{pr[0]:+.3f} (p={pr[1]:.4f}) | "
            f"{par[0]:+.3f} | {par[1]:.4f} |"
        )
    lines.append("")
    lines.append("_PL rank is inversely scaled (rank 1 = best), so a negative correlation with FP/g = 'lower rank → higher production' = signal._")
    lines.append("")
    lines.append("## Subgroup: streamer-tier vs core-hold")
    lines.append("")
    lines.append("PL ranks may carry more decision value in the **streamer tier** (low PL ranks) where rh3/rp3's prior-year anchor is weaker (small sample / rookies), and less value in the **core-hold tier** where prior-year FP is itself elite-predictive.")
    lines.append("")
    lines.append("Streamer tiers: H rank>80 / SP rank>50 / RP rank>25. Core tiers: H≤50 / SP≤25 / RP≤15.")
    lines.append("")
    lines.append("| Bucket | tier | n | base R^2 | +PL R^2 | incr R^2 |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in results:
        if r.get("skip_reason"):
            continue
        for label, key in (("streamer", "subgroup_streamer"), ("core-hold", "subgroup_core")):
            s = r[key]
            if s is None:
                lines.append(f"| {r['bucket']} | {label} | — | — | — | _n<20_ |")
            else:
                lines.append(
                    f"| {r['bucket']} | {label} | {s['n']} | "
                    f"{fmt_r2(s['base_r2'])} | {fmt_r2(s['full_r2'])} | {fmt_pct(s['incr_r2'])} |"
                )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    for r in results:
        if r.get("skip_reason"):
            continue
        incr = r["incr_r2"]
        p = r["p_F"]
        partial_rho = r["spearman_pl_partial"][0]
        partial_p = r["spearman_pl_partial"][1]
        if incr < 0.005 and (not np.isfinite(p) or p > 0.10) and abs(partial_rho) < 0.10:
            v = "**DROP / NO ADDITIVE VALUE** — incremental R^2 is functionally zero, F-test non-significant, partial Spearman near zero. Prior-year FP fully subsumes PL rank in 8-team BrownU."
        elif incr < 0.015 and partial_p > 0.05:
            v = "**DOWNWEIGHT** — incremental R^2 modest and statistically marginal. Keep as tie-breaker / sanity-check lens, not a decision driver."
        elif incr >= 0.015 and p < 0.05:
            v = "**KEEP AS LENS** — PL rank carries statistically and practically distinct information beyond the prior-year anchor."
        else:
            v = "**KEEP AS SANITY-CHECK** — directional signal present but small."
        lines.append(f"- **{r['label']} (n={r['n']}):** {v}")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- Baseline = prior-year FP/g, not live rh3/rp3. Live rh3/rp3 contains additional features (archetype, drift, K-form for SPs) that may further compress incremental PL R^2.")
    lines.append("- Single-year test (2025). The pl_rank_panel covers 2019-2025 — a multi-year pooled fit is the natural next step if a non-trivial signal is found here.")
    lines.append("- Rookies excluded by inner-join requirement on prior_year_fp (PL's bias is plausibly highest for veterans with track record).")
    lines.append("- 'Mid-season PL rank' is a single snapshot, not the rolling weekly rank a manager actually consumes; if anything this overstates PL's predictive value (it has more season already in it than an April rank would).")
    lines.append("")
    return "\n".join(lines)


def main():
    pl, act, pred = load_panels()
    df = build_join(pl, act, pred, YEAR_TARGET)

    results = []
    for bucket in ("H", "SP", "RP"):
        results.append(run_bucket(df, bucket))

    md = render_md(results, YEAR_TARGET)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(md, encoding="utf-8")
    print(f"WROTE {OUT_PATH}")

    # Console summary
    print()
    for r in results:
        if r.get("skip_reason"):
            print(f"  {r['bucket']}: SKIPPED ({r['skip_reason']})")
            continue
        print(f"  {r['bucket']} n={r['n']:4d}  "
              f"base R^2={r['baseline']['r2']:.4f}  "
              f"+PL R^2={r['full']['r2']:.4f}  "
              f"incr={r['incr_r2']*100:+.2f}pp  "
              f"p_F={r['p_F']:.4f}  "
              f"partial_rho={r['spearman_pl_partial'][0]:+.3f}")


if __name__ == "__main__":
    main()
