"""
Per-lens reliability (calibration) diagrams for the 8 synthesis lenses.

For each lens, compute a verdict in {-1, -0.5, 0, +0.5, +1} based on the
lens's signal vs the population, then look at mean forward-30d FP/g
(`target` column) in each verdict bin. A calibrated lens is monotonic
increasing (BUY -> highest forward FP). A miscalibrated lens is flat,
inverted, or U-shaped.

Lens -> column proxy (snapshot has projections + recent form + priors):
  L1 Blended xFP / rank          -> pred_k80 (validated shrunk talent estimate, 80-PA cohort prior)
  L2 boom-bust L21/L8            -> l21_avg (recent form, last-21d running average)
  L3 sustainability proxy        -> |l21_avg - l42_avg|  (closer to 0 = more consistent)
  L4 prior-year baseline         -> prior_avg
  L5 xwOBA L21 vs prior baseline -> l21_avg - prior_avg  (hitters)
  L6 xwOBACON YoY direction      -> prior_avg - prior2_avg  (hitters; positive = improving YoY)
  L7 archetype/age decline       -> -1 * (prior2_avg - prior_avg)  proxy for downtrend = decline risk
  L8 model rank vs replacement   -> pred_k80 - cohort_replacement_median
"""

import numpy as np
import pandas as pd
from pathlib import Path

OUT_PATH = Path("data/research/validation_runs/per_lens_reliability_2026-06-06.md")
H_PATH = Path("data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet")
SP_PATH = Path("data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet")

VERDICT_BINS = [-1, -0.5, 0, 0.5, 1]
VERDICT_LABELS = ["FADE", "FADE-LITE", "HOLD", "BUY-LITE", "BUY"]


def to_verdict(signal: pd.Series) -> pd.Series:
    """Map a signal series to {-1, -0.5, 0, +0.5, +1} verdicts using
    population quintile cuts. Highest 20% -> BUY (+1), next 20% -> BUY-LITE
    (+0.5), middle 20% -> HOLD (0), next 20% -> FADE-LITE (-0.5),
    bottom 20% -> FADE (-1)."""
    s = signal.copy()
    out = pd.Series(index=s.index, dtype=float)
    valid = s.notna()
    if valid.sum() < 5:
        return out
    q = s[valid].quantile([0.2, 0.4, 0.6, 0.8]).tolist()
    def assign(v):
        if pd.isna(v):
            return np.nan
        if v <= q[0]:
            return -1.0
        if v <= q[1]:
            return -0.5
        if v <= q[2]:
            return 0.0
        if v <= q[3]:
            return 0.5
        return 1.0
    out = s.apply(assign)
    return out


def reliability_table(df: pd.DataFrame, verdict: pd.Series, target: pd.Series) -> pd.DataFrame:
    """For each verdict bin, return mean target FP, std, n, and 95% CI."""
    rows = []
    for v in VERDICT_BINS:
        mask = (verdict == v) & target.notna()
        n = int(mask.sum())
        if n == 0:
            rows.append({"verdict": v, "n": 0, "mean": np.nan,
                         "std": np.nan, "ci_lo": np.nan, "ci_hi": np.nan})
            continue
        m = target[mask].mean()
        s = target[mask].std(ddof=1) if n > 1 else 0.0
        se = s / np.sqrt(n) if n > 1 else 0.0
        rows.append({"verdict": v, "n": n, "mean": m, "std": s,
                     "ci_lo": m - 1.96 * se, "ci_hi": m + 1.96 * se})
    return pd.DataFrame(rows)


def classify_calibration(tbl: pd.DataFrame) -> str:
    """Classify monotonicity. CALIBRATED = strictly monotonic increasing.
    INVERTED = strictly monotonic decreasing. U-SHAPED = min in middle.
    FLAT = max - min < 5% of overall mean. Otherwise MIXED."""
    means = tbl["mean"].dropna().tolist()
    if len(means) < 3:
        return "INSUFFICIENT_DATA"
    overall = np.mean(means)
    spread = max(means) - min(means)
    if overall != 0 and spread / abs(overall) < 0.05:
        return "FLAT"
    diffs = np.diff(means)
    if all(d > 0 for d in diffs):
        return "CALIBRATED"
    if all(d < 0 for d in diffs):
        return "INVERTED"
    # detect U-shape: min in middle position
    mn_idx = np.argmin(means)
    mx_idx = np.argmax(means)
    if 0 < mn_idx < len(means) - 1:
        return "U-SHAPED"
    if 0 < mx_idx < len(means) - 1:
        return "INVERTED-U"
    # weak monotonic (most diffs same sign)
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    if pos > neg:
        return "WEAK-CALIBRATED"
    if neg > pos:
        return "WEAK-INVERTED"
    return "MIXED"


def lens_signals_hitter(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Build the 8 lens signals for hitters."""
    return {
        "L1 Blended-xFP / rh3-rank":   df["pred_k80"],
        "L2 boom-bust L21/L8":         df["l21_avg"],
        "L3 sustainability proxy":     -(df["l21_avg"] - df["l42_avg"]).abs(),
        "L4 prior-year baseline":      df["prior_avg"],
        "L5 xwOBA L21 vs prior":       df["l21_avg"] - df["prior_avg"],
        "L6 xwOBACON YoY direction":   df["prior_avg"] - df["prior2_avg"],
        "L7 archetype/age decline":    -(df["prior2_avg"] - df["prior_avg"]),
        "L8 model rank vs replacement":df["pred_k80"] - df["pred_k80"].median(),
    }


def lens_signals_sp(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Build the 8 lens signals for SPs. L5/L6 (xwOBA-specific) marked N/A."""
    return {
        "L1 Blended-xFP / rp3-rank":   df["pred_k80"],
        "L2 boom-bust L21/L8":         df["l21_avg"],
        "L3 sustainability proxy":     -(df["l21_avg"] - df["l42_avg"]).abs(),
        "L4 prior-year baseline":      df["prior_avg"],
        "L5 xwOBA L21 vs prior":       df["l21_avg"] - df["prior_avg"],   # SP analog: recent vs prior
        "L6 xwOBACON YoY direction":   df["prior_avg"] - df["prior2_avg"],  # SP YoY direction
        "L7 archetype/age decline":    -(df["prior2_avg"] - df["prior_avg"]),
        "L8 model rank vs replacement":df["pred_k80"] - df["pred_k80"].median(),
    }


def ascii_diagram(tbl: pd.DataFrame, target_mean: float) -> str:
    """Render an ASCII bar chart of bin mean vs population mean."""
    lines = []
    means = tbl["mean"].tolist()
    if not any(pd.notna(m) for m in means):
        return "    (insufficient data)"
    valid_means = [m for m in means if pd.notna(m)]
    lo = min(valid_means)
    hi = max(valid_means)
    span = max(hi - lo, 1e-9)
    for v, m, n in zip(tbl["verdict"], tbl["mean"], tbl["n"]):
        if pd.isna(m):
            bar = "(no data)"
        else:
            width = int(round(30 * (m - lo) / span))
            bar = "#" * max(width, 1)
        label = VERDICT_LABELS[VERDICT_BINS.index(v)]
        lines.append(f"    {label:>10s} ({v:+.1f}): {bar:30s}  mean={m:6.3f}  n={n}")
    lines.append(f"    {'pop mean':>10s}        : {'.' * 30}  mean={target_mean:6.3f}")
    return "\n".join(lines)


def fmt_table(tbl: pd.DataFrame) -> str:
    """Render reliability table as markdown."""
    rows = ["| verdict | n | mean FP | 95% CI |", "|---|---|---|---|"]
    for _, row in tbl.iterrows():
        label = VERDICT_LABELS[VERDICT_BINS.index(row["verdict"])]
        if row["n"] == 0:
            rows.append(f"| {label} ({row['verdict']:+.1f}) | 0 | -- | -- |")
        else:
            rows.append(
                f"| {label} ({row['verdict']:+.1f}) | {int(row['n'])} | "
                f"{row['mean']:.3f} | [{row['ci_lo']:.3f}, {row['ci_hi']:.3f}] |"
            )
    return "\n".join(rows)


def run_group(df: pd.DataFrame, group_name: str, signals_fn) -> str:
    """Run all 8 lenses for a group, return markdown section."""
    pop_mean = df["target"].mean()
    pop_std = df["target"].std()
    md = [f"## {group_name}",
          f"",
          f"- n_snapshots = {len(df)}",
          f"- forward target mean = {pop_mean:.3f} +/- {pop_std:.3f}",
          f"- tiers = {df['tier'].value_counts().to_dict()}",
          f""]
    signals = signals_fn(df)
    verdicts = {}
    for lens, sig in signals.items():
        verdicts[lens] = to_verdict(sig)
    for lens, verdict in verdicts.items():
        tbl = reliability_table(df, verdict, df["target"])
        verdict_label = classify_calibration(tbl)
        md.append(f"### {lens}")
        md.append("")
        md.append(f"**Verdict: {verdict_label}**")
        md.append("")
        md.append(fmt_table(tbl))
        md.append("")
        md.append("```")
        md.append(ascii_diagram(tbl, pop_mean))
        md.append("```")
        md.append("")
    return "\n".join(md)


def main():
    h = pd.read_parquet(H_PATH)
    sp = pd.read_parquet(SP_PATH)

    lines = ["# Per-lens reliability (calibration) diagrams",
             "",
             "Generated 2026-06-06.",
             "",
             "## Method",
             "",
             "For each lens, the per-snapshot lens signal is mapped to a verdict in "
             "{-1, -0.5, 0, +0.5, +1} via population quintile cuts. "
             "Mean forward FP (`target`) is computed per verdict bin with 95% CIs. "
             "A CALIBRATED lens is strictly monotonic increasing. "
             "INVERTED = strictly decreasing. "
             "U-SHAPED / INVERTED-U = extremum in middle. "
             "FLAT = max-min spread < 5% of pooled mean.",
             "",
             "**Caveat (top-rank sampling):** The snapshot is restricted to top-150 "
             "hitters and top-100 SPs by season-FP. This compresses the lower verdict "
             "bins (the FADEs are still above-average players population-wide) and "
             "narrows the BUY-to-FADE spread relative to a full-population calibration. "
             "Top-rank sampling tends to FLATTEN signals; rank-based lenses (L1, L8) "
             "are most affected because the top-k cutoff is itself the signal.",
             ""]
    lines.append(run_group(h, "Hitters", lens_signals_hitter))
    lines.append("---")
    lines.append("")
    lines.append(run_group(sp, "Starting Pitchers", lens_signals_sp))

    # Summary table at the end
    h_summary = []
    sp_summary = []
    for lens, sig in lens_signals_hitter(h).items():
        v = to_verdict(sig)
        tbl = reliability_table(h, v, h["target"])
        h_summary.append((lens, classify_calibration(tbl),
                           tbl["mean"].max() - tbl["mean"].min()))
    for lens, sig in lens_signals_sp(sp).items():
        v = to_verdict(sig)
        tbl = reliability_table(sp, v, sp["target"])
        sp_summary.append((lens, classify_calibration(tbl),
                            tbl["mean"].max() - tbl["mean"].min()))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Lens | Hitters | SP |")
    lines.append("|---|---|---|")
    for (h_lens, h_cls, h_spread), (sp_lens, sp_cls, sp_spread) in zip(h_summary, sp_summary):
        lines.append(f"| {h_lens} | {h_cls} (spread {h_spread:.2f}) | {sp_cls} (spread {sp_spread:.2f}) |")
    lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print()
    print("Summary:")
    for (lens, cls, spread) in h_summary:
        print(f"  H  {lens:36s} -> {cls:18s} spread={spread:.3f}")
    print()
    for (lens, cls, spread) in sp_summary:
        print(f"  SP {lens:36s} -> {cls:18s} spread={spread:.3f}")


if __name__ == "__main__":
    main()
