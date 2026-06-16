"""Drop-one-lens ablation.

Synthesize the 8 merge-protocol lens votes from snapshot fields, build an
equal-weighted ensemble that predicts forward FP, then ablate each lens in
turn and measure ΔMAE.

Proxies used (snapshot has no native rh3/rp3 columns):
    L1 Blended xFP / rh3 rank decile  -> pred_k150 decile within (year, tier)
    L2 boom-bust L21/L8 actuals       -> l21_avg sign vs cohort median
    L3 sustainability bucket proxy    -> sign(l21_avg - l42_avg)
    L4 prior-year baseline            -> sign(prior_avg - cohort_median(prior))
    L5 xwOBA L21 vs prior-year gap    -> sign(l21_avg - prior_avg)
    L6 xwOBACON YoY                   -> sign(prior_avg - prior2_avg)
    L7 archetype age tier             -> tier (top50 = +1, else 0)
    L8 model rank decile              -> pred_k300 decile within (year, tier)

Vote scale: +1 BUY / 0 HOLD / -1 FADE.
Ensemble prediction = cohort_mean(target) + slope * sum(votes)
where slope is fit on the training half by simple OLS.

NOT committed (scripts/_oneoff/ is gitignored).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(r"c:/Users/Joshua/plv_clone")
H_SNAP = REPO / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet"
SP_SNAP = REPO / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet"
OUT_MD = REPO / "data/research/validation_runs/drop_one_lens_ablation_2026-06-06.md"

RNG = np.random.default_rng(20260606)
N_BOOT = 500


def _trinary_from_cohort(series: pd.Series, by: pd.Series, lo: float = 0.33, hi: float = 0.67) -> pd.Series:
    """Convert continuous signal -> -1/0/+1 by cohort percentile."""
    out = pd.Series(0, index=series.index, dtype=float)
    for _, idx in by.groupby(by, dropna=False).groups.items():
        vals = series.loc[idx]
        if vals.notna().sum() < 5:
            continue
        q_lo = vals.quantile(lo)
        q_hi = vals.quantile(hi)
        out.loc[idx] = np.where(vals >= q_hi, 1.0, np.where(vals <= q_lo, -1.0, 0.0))
        out.loc[vals.index[vals.isna()]] = 0.0
    return out


def _trinary_from_diff(series: pd.Series, eps: float = 0.05) -> pd.Series:
    """Convert a delta into trinary using ± eps band around 0."""
    out = pd.Series(0.0, index=series.index)
    out.loc[series > eps] = 1.0
    out.loc[series < -eps] = -1.0
    out.loc[series.isna()] = 0.0
    return out


def build_lenses(df: pd.DataFrame, is_hitter: bool) -> pd.DataFrame:
    """Add L1..L8 columns of -1/0/+1 votes."""
    out = df.copy()
    cohort_key = out["year"].astype(str) + "_" + out["tier"].astype(str)

    # L1 Blended xFP / rh3 rank decile -> use pred_k150 (long shrinkage, talent-anchored)
    out["L1"] = _trinary_from_cohort(out["pred_k150"], cohort_key)

    # L2 boom-bust L21/L8 actuals -> recent average vs cohort median
    out["L2"] = _trinary_from_cohort(out["l21_avg"], cohort_key)

    # L3 sustainability bucket proxy -> short-window vs medium-window
    # If L21 >> L42, "running hot" (-1 = REGRESS); if L21 << L42, "BUY-LOW" (+1)
    # Use inverse sign so the lens is contrarian to outcome
    delta = out["l21_avg"] - out["l42_avg"]
    out["L3"] = _trinary_from_diff(-delta, eps=0.10)

    # L4 prior-year baseline -> sign vs cohort median of prior
    out["L4"] = _trinary_from_cohort(out["prior_avg"], cohort_key)

    # L5 xwOBA L21 vs prior-year gap (hitters)
    # If L21 ahead of prior baseline => BUY; behind => FADE
    gap = out["l21_avg"] - out["prior_avg"]
    out["L5"] = _trinary_from_diff(gap, eps=0.10)

    # L6 xwOBACON YoY -> prior vs prior2 trajectory
    yoy = out["prior_avg"] - out["prior2_avg"]
    out["L6"] = _trinary_from_diff(yoy, eps=0.10)

    # L7 archetype age tier -> top50 = peak/established (+1), else 0
    out["L7"] = np.where(out["tier"] == "top50", 1.0, 0.0)

    # L8 model rank decile -> use pred_k300 (heavy shrinkage, archetype-equivalent)
    out["L8"] = _trinary_from_cohort(out["pred_k300"], cohort_key)

    # NaN safety
    for L in [f"L{i}" for i in range(1, 9)]:
        out[L] = out[L].fillna(0.0)
    return out


def fit_and_score(train: pd.DataFrame, test: pd.DataFrame, active_lenses: list[str]) -> float:
    """Fit cohort_mean + slope*sum_votes on TRAIN, return MAE on TEST."""
    # cohort mean of target by (year, tier) from train
    cohort_means = train.groupby(["year", "tier"])["target"].mean()

    train_anchor = train.set_index(["year", "tier"]).index.map(cohort_means)
    test_anchor = test.set_index(["year", "tier"]).index.map(cohort_means)
    # Fall back to global mean if cohort unseen
    global_mean = train["target"].mean()
    train_anchor = pd.Series(train_anchor, index=train.index).fillna(global_mean)
    test_anchor = pd.Series(test_anchor, index=test.index).fillna(global_mean)

    train_sum = train[active_lenses].sum(axis=1)
    test_sum = test[active_lenses].sum(axis=1)

    # Fit slope by simple OLS on residual = target - anchor against vote_sum
    resid = train["target"].values - train_anchor.values
    x = train_sum.values
    if np.std(x) > 1e-9:
        slope = np.cov(x, resid, bias=True)[0, 1] / np.var(x)
    else:
        slope = 0.0

    pred = test_anchor.values + slope * test_sum.values
    mae = float(np.mean(np.abs(test["target"].values - pred)))
    return mae


def bootstrap_mae_delta(df: pd.DataFrame, baseline_lenses: list[str], dropped: str, n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """Bootstrap (mean delta, ci_lo, ci_hi) for ΔMAE = MAE_drop - MAE_baseline."""
    deltas = []
    n = len(df)
    idx_all = np.arange(n)
    for _ in range(n_boot):
        boot_idx = RNG.choice(idx_all, size=n, replace=True)
        boot = df.iloc[boot_idx].reset_index(drop=True)
        # 50/50 train/test split
        cut = n // 2
        train = boot.iloc[:cut]
        test = boot.iloc[cut:]
        mae_base = fit_and_score(train, test, baseline_lenses)
        mae_drop = fit_and_score(train, test, [L for L in baseline_lenses if L != dropped])
        deltas.append(mae_drop - mae_base)
    deltas = np.array(deltas)
    return float(deltas.mean()), float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def run_ablation(df: pd.DataFrame, label: str, is_hitter: bool) -> dict:
    lenses_all = [f"L{i}" for i in range(1, 9)]
    # Baseline MAE on single split for headline
    np.random.seed(42)
    df_shuffled = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
    cut = len(df_shuffled) // 2
    train = df_shuffled.iloc[:cut]
    test = df_shuffled.iloc[cut:]

    mae_base = fit_and_score(train, test, lenses_all)
    results = {}
    for L in lenses_all:
        mae_drop = fit_and_score(train, test, [x for x in lenses_all if x != L])
        delta_point = mae_drop - mae_base
        # bootstrap CI
        boot_mean, ci_lo, ci_hi = bootstrap_mae_delta(df_shuffled, lenses_all, L, n_boot=N_BOOT)
        results[L] = {
            "mae_drop": mae_drop,
            "delta_point": delta_point,
            "boot_mean": boot_mean,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
        }
    return {"label": label, "n": len(df), "mae_base": mae_base, "lenses": results}


def render_markdown(h_res: dict, sp_res: dict) -> str:
    lens_names = {
        "L1": "Blended xFP / rh3 rank decile (pred_k150)",
        "L2": "Boom-bust L21 actuals (l21_avg)",
        "L3": "Sustainability bucket proxy (-(L21-L42))",
        "L4": "Prior-year baseline (prior_avg)",
        "L5": "L21 vs prior-year gap",
        "L6": "xwOBACON YoY (prior - prior2)",
        "L7": "Archetype age tier (top50 vs other)",
        "L8": "Model rank decile (pred_k300)",
    }

    def _sec(res: dict, label: str) -> str:
        lines = [f"### {label} — n={res['n']}", f"Baseline MAE (all 8 lenses) = **{res['mae_base']:.4f}** FP/g\n"]
        lines.append("| Lens | Description | MAE w/o lens | ΔMAE (point) | ΔMAE bootstrap mean | 95% CI |")
        lines.append("|---|---|---|---|---|---|")
        sorted_lenses = sorted(res["lenses"].items(), key=lambda kv: -kv[1]["boot_mean"])
        for L, r in sorted_lenses:
            lines.append(
                f"| {L} | {lens_names[L]} | {r['mae_drop']:.4f} | {r['delta_point']:+.4f} | "
                f"{r['boot_mean']:+.4f} | [{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}] |"
            )
        lines.append("")
        # critical vs dead weight verdict
        sig_critical = [L for L, r in res["lenses"].items() if r["ci_lo"] > 0]
        sig_dead = [L for L, r in res["lenses"].items() if r["ci_hi"] < 0 or (abs(r["boot_mean"]) < 0.001 and r["ci_lo"] < 0 < r["ci_hi"])]
        ambiguous = [L for L in res["lenses"] if L not in sig_critical and L not in sig_dead]
        lines.append(f"- **Critical (CI excludes 0, drop HURTS MAE):** {', '.join(sig_critical) if sig_critical else '(none)'}")
        lines.append(f"- **Dead weight (CI < 0 or ≈ 0):** {', '.join(sig_dead) if sig_dead else '(none)'}")
        lines.append(f"- **Ambiguous:** {', '.join(ambiguous) if ambiguous else '(none)'}")
        lines.append("")
        return "\n".join(lines)

    parts = [
        "# Drop-one-lens ablation — 2026-06-06\n",
        "Goal: Identify which of the 8 synthesis lenses carry signal vs which are dead weight, ",
        "by ablating each in turn from an equal-weighted ensemble that predicts forward FP/g.\n",
        "## Method\n",
        "- Snapshot frames at `data/research/validation_runs/shrinkage_*_snap_2026-06-06.parquet`.",
        "- 8 lenses synthesized as -1/0/+1 votes (see header of `scripts/_oneoff/test_drop_one_lens.py` for proxies).",
        "- Ensemble: `pred = cohort_mean(target by year×tier) + slope * sum(votes)`. Slope fit via OLS on train half.",
        "- 50/50 train/test split (seed=42) for headline MAE; bootstrap (B=500) for ΔMAE CI.",
        "- ΔMAE > 0 ⇒ lens carries signal (dropping it raises error). ΔMAE ≤ 0 ⇒ dead weight or noise.\n",
        "## Results\n",
        _sec(h_res, "HITTER sample"),
        _sec(sp_res, "SP sample"),
        "## Combined verdict & recommendation\n",
    ]

    # Build combined recommendation
    def _verdict(res: dict) -> tuple[list, list]:
        keep = [L for L, r in res["lenses"].items() if r["boot_mean"] > 0.001 and r["ci_lo"] > -0.0005]
        drop = [L for L, r in res["lenses"].items() if r["ci_hi"] < 0 or (r["boot_mean"] < 0 and r["ci_hi"] < 0.0005)]
        return keep, drop

    h_keep, h_drop = _verdict(h_res)
    sp_keep, sp_drop = _verdict(sp_res)
    parts.append(f"- **Hitters — keep:** {', '.join(h_keep) or '(none above threshold)'}")
    parts.append(f"- **Hitters — drop:** {', '.join(h_drop) or '(none clearly negative)'}")
    parts.append(f"- **SPs — keep:** {', '.join(sp_keep) or '(none above threshold)'}")
    parts.append(f"- **SPs — drop:** {', '.join(sp_drop) or '(none clearly negative)'}")
    parts.append("")
    parts.append("Caveats: lens votes are PROXIES synthesized from snapshot fields, not the real triangulate ")
    parts.append("merge-protocol cards. Real lens votes come from the live skill stack and are not in the ")
    parts.append("snapshot. This analysis is best read as an information-content scan over the underlying ")
    parts.append("signal sources, not a final say on the protocol UI. Bootstrap uses sampled-with-replacement ")
    parts.append("blocks; sample sizes (H n=1498, SP n=550) are modest so CIs are wide.")
    parts.append("")
    return "\n".join(parts)


def main() -> None:
    h = pd.read_parquet(H_SNAP)
    sp = pd.read_parquet(SP_SNAP)

    h_lensed = build_lenses(h, is_hitter=True)
    sp_lensed = build_lenses(sp, is_hitter=False)

    h_res = run_ablation(h_lensed, "HITTER", is_hitter=True)
    sp_res = run_ablation(sp_lensed, "SP", is_hitter=False)

    md = render_markdown(h_res, sp_res)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"WROTE {OUT_MD}")
    # also print summary (ascii only — cp1252 console safe)
    print("\nHITTER baseline MAE:", round(h_res["mae_base"], 4))
    for L, r in sorted(h_res["lenses"].items(), key=lambda kv: -kv[1]["boot_mean"]):
        print(f"  {L}: dMAE={r['boot_mean']:+.4f} CI=[{r['ci_lo']:+.4f},{r['ci_hi']:+.4f}]")
    print("\nSP baseline MAE:", round(sp_res["mae_base"], 4))
    for L, r in sorted(sp_res["lenses"].items(), key=lambda kv: -kv[1]["boot_mean"]):
        print(f"  {L}: dMAE={r['boot_mean']:+.4f} CI=[{r['ci_lo']:+.4f},{r['ci_hi']:+.4f}]")


if __name__ == "__main__":
    main()
