"""Sensitivity analysis: lens-weight perturbation -> verdict flip rate.

Tests whether the multi-lens synthesis verdict is stable under small
weight perturbations. If verdicts flip on +-10% weight changes,
the merge protocol is fragile.

Method:
  1. Load shrinkage_h_snap_2026-06-06.parquet (1,498 H snapshots).
  2. Construct 8 BUY/HOLD/FADE lens votes per snapshot using the
     same construction as test_drop_one_lens.py (the canonical
     8-lens synthesis the project already documented).
  3. Baseline: equal weights (0.125 each). Verdict = weighted sum.
       BUY  if sum > +0.5
       HOLD if -0.5 <= sum <= +0.5
       FADE if sum < -0.5
  4. Perturb each lens's weight by +-10%, +-20% (8 * 2 * 2 = 32 runs).
     The other 7 weights are RENORMALISED to keep total mass = 1.0
     (so the perturbation isolates the *relative* weight of one lens).
  5. For each perturbation, recompute verdicts. Count flips vs baseline.
  6. Flag lenses where the +-20% perturbation flips > 5% of verdicts.

Output: data/research/validation_runs/sensitivity_analysis_2026-06-06.md
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(r"c:/Users/Joshua/plv_clone")
H_SNAP = REPO / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet"
OUT_MD = REPO / "data/research/validation_runs/sensitivity_analysis_2026-06-06.md"

LENS_NAMES = {
    "L1": "Blended xFP rank (pred_k150 cohort decile)",
    "L2": "Boom/bust L21 actuals (l21_avg cohort decile)",
    "L3": "Sustainability (sign(L42 - L21))",
    "L4": "Prior-year baseline (prior_avg cohort decile)",
    "L5": "xwOBA L21 vs prior gap (l21_avg - prior_avg)",
    "L6": "xwOBACON YoY (prior_avg - prior2_avg)",
    "L7": "Archetype age tier (top50)",
    "L8": "Model rank decile (pred_k300 cohort decile)",
}
LENSES = list(LENS_NAMES.keys())  # L1..L8

BUY_T = 0.5   # weighted sum > +0.5 -> BUY
FADE_T = -0.5  # weighted sum < -0.5 -> FADE


# ---------------------------- lens construction ----------------------------
def _trinary_from_cohort(series: pd.Series, by: pd.Series, lo: float = 0.33, hi: float = 0.67) -> pd.Series:
    out = pd.Series(0.0, index=series.index)
    for _, idx in by.groupby(by, dropna=False).groups.items():
        vals = series.loc[idx]
        if vals.notna().sum() < 5:
            continue
        q_lo = vals.quantile(lo)
        q_hi = vals.quantile(hi)
        out.loc[idx] = np.where(vals >= q_hi, 1.0, np.where(vals <= q_lo, -1.0, 0.0))
        out.loc[vals.index[vals.isna()]] = 0.0
    return out


def _trinary_from_diff(series: pd.Series, eps: float = 0.10) -> pd.Series:
    out = pd.Series(0.0, index=series.index)
    out.loc[series > eps] = 1.0
    out.loc[series < -eps] = -1.0
    out.loc[series.isna()] = 0.0
    return out


def build_lenses(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cohort_key = out["year"].astype(str) + "_" + out["tier"].astype(str)
    out["L1"] = _trinary_from_cohort(out["pred_k150"], cohort_key)
    out["L2"] = _trinary_from_cohort(out["l21_avg"], cohort_key)
    delta = out["l21_avg"] - out["l42_avg"]
    out["L3"] = _trinary_from_diff(-delta, eps=0.10)
    out["L4"] = _trinary_from_cohort(out["prior_avg"], cohort_key)
    gap = out["l21_avg"] - out["prior_avg"]
    out["L5"] = _trinary_from_diff(gap, eps=0.10)
    yoy = out["prior_avg"] - out["prior2_avg"]
    out["L6"] = _trinary_from_diff(yoy, eps=0.10)
    out["L7"] = np.where(out["tier"] == "top50", 1.0, 0.0)
    out["L8"] = _trinary_from_cohort(out["pred_k300"], cohort_key)
    for L in LENSES:
        out[L] = out[L].fillna(0.0)
    return out


# ---------------------------- verdict computation --------------------------
def verdict_from_weights(votes: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Return Series of 'BUY'/'HOLD'/'FADE' per row."""
    w = np.array([weights[L] for L in LENSES])
    scores = (votes[LENSES].values * w).sum(axis=1)
    verdicts = np.where(scores > BUY_T, "BUY",
                np.where(scores < FADE_T, "FADE", "HOLD"))
    return pd.Series(verdicts, index=votes.index)


def perturb_weights(base_weights: dict[str, float], lens: str, mult: float) -> dict[str, float]:
    """Multiply one lens's weight by mult, then renormalise the others to keep total=1.0."""
    new = dict(base_weights)
    old_w = new[lens]
    new_w = old_w * mult
    new[lens] = new_w
    # Rescale the other 7 so the total sums to 1.0 (preserves total mass; isolates relative shift)
    others = [L for L in LENSES if L != lens]
    other_sum = sum(new[L] for L in others)
    target_other = 1.0 - new_w
    if other_sum > 1e-9 and target_other > 0:
        scale = target_other / other_sum
        for L in others:
            new[L] *= scale
    return new


def flip_table(votes: pd.DataFrame, baseline_verdicts: pd.Series, base_weights: dict[str, float]) -> pd.DataFrame:
    rows = []
    for lens in LENSES:
        for pct in [-0.20, -0.10, +0.10, +0.20]:
            mult = 1.0 + pct
            new_w = perturb_weights(base_weights, lens, mult)
            new_v = verdict_from_weights(votes, new_w)
            flips_total = (new_v != baseline_verdicts).sum()
            n = len(baseline_verdicts)
            pct_flips = 100.0 * flips_total / n

            # Direction breakdown
            buy_to_hold = ((baseline_verdicts == "BUY") & (new_v == "HOLD")).sum()
            buy_to_fade = ((baseline_verdicts == "BUY") & (new_v == "FADE")).sum()
            hold_to_buy = ((baseline_verdicts == "HOLD") & (new_v == "BUY")).sum()
            hold_to_fade = ((baseline_verdicts == "HOLD") & (new_v == "FADE")).sum()
            fade_to_hold = ((baseline_verdicts == "FADE") & (new_v == "HOLD")).sum()
            fade_to_buy = ((baseline_verdicts == "FADE") & (new_v == "BUY")).sum()

            rows.append({
                "lens": lens,
                "delta_pct": pct,
                "new_weight": new_w[lens],
                "n_flips": flips_total,
                "pct_flips": pct_flips,
                "buy_to_hold": buy_to_hold,
                "buy_to_fade": buy_to_fade,
                "hold_to_buy": hold_to_buy,
                "hold_to_fade": hold_to_fade,
                "fade_to_hold": fade_to_hold,
                "fade_to_buy": fade_to_buy,
            })
    return pd.DataFrame(rows)


# ---------------------------- driver ---------------------------------------
def main():
    print(f"[1/5] Loading {H_SNAP.name}...")
    df = pd.read_parquet(H_SNAP)
    print(f"  N = {len(df)} snapshots")

    print("[2/5] Building 8 lens votes...")
    votes = build_lenses(df)
    print("  Lens vote distributions (BUY/HOLD/FADE counts):")
    for L in LENSES:
        c = votes[L].value_counts().reindex([1.0, 0.0, -1.0], fill_value=0)
        print(f"    {L}: BUY={int(c[1.0])}, HOLD={int(c[0.0])}, FADE={int(c[-1.0])}")

    print("[3/5] Baseline verdicts (equal weights 0.125 each)...")
    base_w = {L: 0.125 for L in LENSES}
    base_verdicts = verdict_from_weights(votes, base_w)
    bv = base_verdicts.value_counts()
    print(f"  BUY={int(bv.get('BUY', 0))}, HOLD={int(bv.get('HOLD', 0))}, FADE={int(bv.get('FADE', 0))}")

    print("[4/5] Perturbation sweep (8 lenses x 4 deltas = 32 runs)...")
    res = flip_table(votes, base_verdicts, base_w)

    # Identify SENSITIVE lenses: |+-20%| flips > 5% of verdicts
    sens = (
        res[res["delta_pct"].abs() == 0.20]
        .groupby("lens")["pct_flips"]
        .max()
        .reset_index()
        .rename(columns={"pct_flips": "max_pct_flip_at_20"})
    )
    sens["sensitive"] = sens["max_pct_flip_at_20"] > 5.0
    sens_sorted = sens.sort_values("max_pct_flip_at_20", ascending=False)

    # Stable lenses ranked: lowest max_pct_flip
    stable_sorted = sens.sort_values("max_pct_flip_at_20", ascending=True)

    # Overall verdict
    sens_count = sens["sensitive"].sum()
    n_lens = len(LENSES)
    if sens_count >= 4:
        overall = "FRAGILE"
    elif sens_count >= 1:
        overall = "MIXED"
    else:
        overall = "STABLE"

    print(f"[5/5] Overall: {overall} ({sens_count}/{n_lens} sensitive lenses)")

    # ---------------------------- render markdown -----------------------------
    n = len(base_verdicts)
    bv_buy = int(bv.get("BUY", 0))
    bv_hold = int(bv.get("HOLD", 0))
    bv_fade = int(bv.get("FADE", 0))

    lines = [
        "# Lens-Weight Sensitivity Analysis (2026-06-06)",
        "",
        "## Setup",
        "",
        f"- **Snapshot:** `shrinkage_h_snap_2026-06-06.parquet` ({n:,} hitter rows).",
        f"- **Lenses tested:** 8 (BUY=+1, HOLD=0, FADE=-1) constructed via the canonical project synthesis (mirrors `test_drop_one_lens.py`).",
        f"- **Baseline weights:** equal (0.125 each).",
        f"- **Verdict rule:** sum > +{BUY_T} -> BUY; sum < {FADE_T} -> FADE; otherwise HOLD.",
        f"- **Baseline distribution:** BUY={bv_buy} ({100*bv_buy/n:.1f}%), HOLD={bv_hold} ({100*bv_hold/n:.1f}%), FADE={bv_fade} ({100*bv_fade/n:.1f}%).",
        f"- **Perturbation rule:** scale one lens's weight by 1+delta, renormalise the other 7 so total mass stays = 1.0.",
        "",
        "## Per-lens, per-perturbation flip table",
        "",
        "| Lens | Description | Delta | New weight | Flips | % flipped |",
        "|------|-------------|-------|------------|-------|-----------|",
    ]
    for L in LENSES:
        sub = res[res["lens"] == L].sort_values("delta_pct")
        for _, r in sub.iterrows():
            lines.append(
                f"| {L} | {LENS_NAMES[L]} | {r['delta_pct']:+.0%} | {r['new_weight']:.3f} | {int(r['n_flips'])} | {r['pct_flips']:.2f}% |"
            )

    lines += [
        "",
        "## Sensitivity ranking (by max |+-20%| flip rate)",
        "",
        "### Most sensitive lenses",
        "",
        "| Rank | Lens | Description | Max % flipped at +-20% | Sensitive? |",
        "|------|------|-------------|-----------------------|------------|",
    ]
    for i, (_, r) in enumerate(sens_sorted.iterrows(), 1):
        flag = "YES" if r["sensitive"] else "no"
        lines.append(
            f"| {i} | {r['lens']} | {LENS_NAMES[r['lens']]} | {r['max_pct_flip_at_20']:.2f}% | {flag} |"
        )

    lines += [
        "",
        "### Most stable lenses",
        "",
        "| Rank | Lens | Description | Max % flipped at +-20% |",
        "|------|------|-------------|-----------------------|",
    ]
    for i, (_, r) in enumerate(stable_sorted.iterrows(), 1):
        lines.append(
            f"| {i} | {r['lens']} | {LENS_NAMES[r['lens']]} | {r['max_pct_flip_at_20']:.2f}% |"
        )

    lines += [
        "",
        "## Overall verdict",
        "",
        f"**{overall}** ({int(sens_count)} of {n_lens} lenses exceed the 5% flip threshold at +-20%).",
        "",
    ]
    if overall == "FRAGILE":
        lines.append("More than half the lenses flip > 5% of verdicts on a +-20% weight nudge. The merge protocol is highly sensitive to weight calibration; sloppy or eyeballed weights will produce inconsistent verdicts.")
    elif overall == "MIXED":
        lines.append("Some lenses are sensitive (>5% flip), others are stable. The protocol is robust to most weights but a few lenses need careful calibration.")
    else:
        lines.append("All lenses flip <=5% of verdicts at +-20%. The merge protocol is robust to weight perturbation - the verdict surface is driven by lens *agreement*, not by precise weight values.")

    lines += [
        "",
        "## Recommendation",
        "",
    ]
    sensitive_lenses = sens_sorted[sens_sorted["sensitive"]]
    if len(sensitive_lenses):
        lines.append("Lenses that need careful weight calibration (small wrong move flips many verdicts):")
        for _, r in sensitive_lenses.iterrows():
            lines.append(f"- **{r['lens']}** ({LENS_NAMES[r['lens']]}) - {r['max_pct_flip_at_20']:.2f}% flip rate at +-20%")
    else:
        lines.append("No lenses exceed the 5% flip threshold at +-20%. The verdict surface is consensus-driven; weight precision matters less than lens *coverage* (which lenses are included).")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {OUT_MD}")

    # Headline for caller
    print("\nHEADLINE:")
    print(f"  Overall: {overall}")
    print(f"  Sensitive lenses ({int(sens_count)}/{n_lens}):")
    for _, r in sens_sorted.iterrows():
        flag = "<-- SENSITIVE" if r["sensitive"] else ""
        print(f"    {r['lens']} max flip @ +-20% = {r['max_pct_flip_at_20']:.2f}% {flag}")


if __name__ == "__main__":
    main()
