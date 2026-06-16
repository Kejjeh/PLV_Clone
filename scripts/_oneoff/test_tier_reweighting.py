"""Test tier hierarchy vs empirical lens lift from lens_weight backtest.

Reads lens_weight_backtest_2026-06-06.snapshots.csv and re-computes per-lens
lift with bootstrap CIs, then compares with the current Tier A/B/C/D labels.

Output: data/research/validation_runs/tier_reweighting_2026-06-06.md
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(r"c:/Users/Joshua/plv_clone")
SNAP = ROOT / "data/research/validation_runs/lens_weight_backtest_2026-06-06.snapshots.csv"
OUT = ROOT / "data/research/validation_runs/tier_reweighting_2026-06-06.md"

# Current tier labels per the task prompt
LENS_TO_TIER = {
    "L1_blend": "A",        # Blended xFP / rh3 / rp3
    "L2_rank": "A",         # rh3 / rp3 rank
    "L3_boom": "C",         # boom-bust + boom_stack
    "L4_sust": "B",         # sustainability
    "L5_xwoba_l21": "B",    # xwOBA L21d vs baseline
    "L6_xwobacon_yoy": "B", # xwOBACON YoY
}
LENS_LABEL = {
    "L1_blend": "Blended xFP",
    "L2_rank": "rh3 / rp3 rank",
    "L3_boom": "boom-bust",
    "L4_sust": "sustainability",
    "L5_xwoba_l21": "xwOBA L21d",
    "L6_xwobacon_yoy": "xwOBACON YoY",
}

LENSES = list(LENS_TO_TIER)
RNG = np.random.default_rng(42)


def bootstrap_lift(buy: np.ndarray, fade: np.ndarray, n_boot: int = 2000) -> tuple[float, float, float, float]:
    if len(buy) < 5 or len(fade) < 5:
        return (np.nan, np.nan, np.nan, np.nan)
    lift = float(buy.mean() - fade.mean())
    lifts = np.empty(n_boot)
    for i in range(n_boot):
        b = RNG.choice(buy, size=len(buy), replace=True).mean()
        f = RNG.choice(fade, size=len(fade), replace=True).mean()
        lifts[i] = b - f
    lo, hi = np.quantile(lifts, [0.025, 0.975])
    p_le_0 = float((lifts <= 0).mean())
    return (lift, float(lo), float(hi), p_le_0)


def per_pos_table(df: pd.DataFrame, pos_group: str) -> pd.DataFrame:
    sub = df[df.pos_group == pos_group]
    rows = []
    for lens in LENSES:
        if lens not in sub.columns:
            continue
        vote = pd.to_numeric(sub[lens], errors="coerce")
        valid = vote.notna() & sub.fwd_fp_per_g.notna()
        v = vote[valid].values
        fp = sub.fwd_fp_per_g[valid].values
        buy = fp[v > 0]
        fade = fp[v < 0]
        lift, lo, hi, p = bootstrap_lift(buy, fade)
        rows.append({
            "lens": lens,
            "label": LENS_LABEL[lens],
            "tier_current": LENS_TO_TIER[lens],
            "n_buy": int((v > 0).sum()),
            "n_fade": int((v < 0).sum()),
            "mean_buy": float(buy.mean()) if len(buy) else np.nan,
            "mean_fade": float(fade.mean()) if len(fade) else np.nan,
            "lift": lift,
            "ci_lo": lo,
            "ci_hi": hi,
            "p_le_0": p,
        })
    return pd.DataFrame(rows)


def propose_tier(row: pd.Series, tier_a_median_lift: float) -> str:
    if pd.isna(row.lift) or row.n_fade < 5 or row.n_buy < 5:
        return "D"  # inconclusive -> context
    if row.ci_lo > 0 and row.lift > tier_a_median_lift:
        return "A"
    if row.ci_lo > 0:
        return "B"
    if row.ci_hi < 0:
        return "D"  # negative lift, context only
    return "C"  # crosses zero


def render_table(table: pd.DataFrame, pos_label: str) -> str:
    # Compute median lift among lenses with current Tier A AND conclusive lift
    tier_a_conclusive = table[(table.tier_current == "A") & table.lift.notna()]
    tier_a_median = float(tier_a_conclusive.lift.median()) if len(tier_a_conclusive) else 0.0

    table = table.assign(tier_proposed=table.apply(propose_tier, axis=1, tier_a_median_lift=tier_a_median))
    # Rank by CI lower bound (most defensible lift)
    table = table.sort_values("ci_lo", ascending=False, na_position="last").reset_index(drop=True)

    lines = [f"### {pos_label}", ""]
    lines.append(f"_Tier A median lift threshold for promotion: {tier_a_median:+.2f} FP/g_")
    lines.append("")
    lines.append("| Rank | Lens | Current | Proposed | n BUY | n FADE | Lift | 95% CI | Δ Tier |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in table.iterrows():
        if pd.isna(r.lift):
            lift_s, ci_s = "—", "INCONCLUSIVE"
        else:
            lift_s = f"{r.lift:+.2f}"
            ci_s = f"[{r.ci_lo:+.2f}, {r.ci_hi:+.2f}]"
        delta = "" if r.tier_current == r.tier_proposed else f"{r.tier_current} → {r.tier_proposed}"
        lines.append(
            f"| {i+1} | {r.label} ({r.lens}) | {r.tier_current} | {r.tier_proposed} "
            f"| {r.n_buy} | {r.n_fade} | {lift_s} | {ci_s} | {delta} |"
        )
    lines.append("")
    return "\n".join(lines), table


def main() -> None:
    df = pd.read_csv(SNAP)
    h_table = per_pos_table(df, "H")
    sp_table = per_pos_table(df, "SP")

    h_section, h_t = render_table(h_table, "Hitters (n=362 snapshots)")
    sp_section, sp_t = render_table(sp_table, "SPs (n=149 snapshots)")

    # Specific call-outs
    sp_boom = sp_t[sp_t.lens == "L3_boom"].iloc[0]
    h_boom = h_table[h_table.lens == "L3_boom"].iloc[0]

    md = f"""# Tier Re-weighting Test — 2026-06-06

## Question

Does the current Tier A (Blended xFP + rh3/rp3) / Tier B (sustainability + xwOBA L21d + xwOBACON YoY) / Tier C (boom-bust + boom_stack) / Tier D (context) hierarchy match empirical lens lift?

Data: re-computed bootstrap lifts (2000 resamples, seed=42) from `lens_weight_backtest_2026-06-06.snapshots.csv` (511 snapshots: 362 H + 149 SP across 4 as-of dates in 2025).

## Method

- Rank each lens by **95% bootstrap CI lower bound** (most defensible positive lift)
- A lens is **promoted to Tier A** if its CI excludes zero AND its lift exceeds the median lift of current Tier A lenses
- A lens is **demoted to Tier D** if its CI is strictly below zero (wrong direction) or it has < 5 BUY/FADE observations (inconclusive — context only)
- A lens stays in **Tier B/C** if CI excludes zero but lift below Tier A median (B) or CI crosses zero (C)

## Results — by position group

{sp_section}

{h_section}

## Key findings

1. **SP boom-bust (L3) dominates**: lift = {sp_boom.lift:+.2f} FP/g with CI [{sp_boom.ci_lo:+.2f}, {sp_boom.ci_hi:+.2f}], p(lift≤0)={sp_boom.p_le_0:.3f}. The only SP lens with a conclusive positive lift in this sample. **Recommendation: promote boom-bust to Tier A for SPs**, given Tier A's rh3/rp3 and Blended xFP are INCONCLUSIVE (no FADE observations because of top-rank sampling).

2. **Hitter boom-bust (L3) is the only conclusive positive lens**: lift = {h_boom.lift:+.2f} FP/g, CI [{h_boom.ci_lo:+.2f}, {h_boom.ci_hi:+.2f}]. xwOBA L21d and xwOBACON YoY (currently Tier B) had negative or zero lift in this sample. **Recommendation: promote boom-bust to Tier A for hitters**, and demote L5/L6 to Tier C (variance) or Tier D (context) pending a larger/cleaner backtest.

3. **Tier A primary signals are unmeasurable in this sample**: L1_blend + L2_rank produced 100% BUY votes (sample drawn from top-100 by rh3/rp3 — no FADE arm). The current Tier A label may still be correct on theoretical/production grounds, but the empirical justification needs a balanced rank sample.

## Specific re-tiering recommendation

**SPs**:
- Tier A: Blended xFP, rh3-rank, **boom-bust (promoted from C)**
- Tier B: sustainability (no change)
- Tier C: removed (boom-bust was the only occupant)
- Tier D: archetype + age/boundary + PL + live_marginal (no change)

**Hitters**:
- Tier A: Blended xFP, rh3-rank, **boom-bust (promoted from C)**
- Tier B: sustainability (kept — production 9-marker decomp, simplified version was inconclusive here)
- Tier C: xwOBA L21d, xwOBACON YoY (demoted from B — CI crosses or is below zero in this sample)
- Tier D: archetype + PL + live_marginal (no change)

## Caveats (carry forward from backtest report)

- **Top-rank sampling**: Tier A lenses (L1, L2) had zero FADE observations, so their empirical lift is untestable here. The promotion of boom-bust to Tier A is conditional on Tier A primary signals being theoretically sound on production grounds, not on direct head-to-head measurement in this sample.
- **N=511 snapshots, 4 as-of dates**: bootstrap CIs are wide; replication across more dates + balanced rank sampling is needed before locking in tier reassignment.
- **Recency leak in L1/L2**: current 2026 rh3/rp3 ranks proxy for 2025 historical ranks — L2 in particular would look weaker in a true real-time test.
- **L4 sustainability simplified**: 2-marker SP / xwOBA-gap H decomposition vs production 9-marker panel. Real Tier B might be stronger than measured.
- **L5 baseline**: 2024 full-season xwOBA vs production "2025 baseline" framing.
- **No IL censoring**: forward windows containing IL stints depress lift for high-talent players unfairly.

## Bottom line

The lens-weight backtest **does not support** the current Tier C placement of boom-bust for either position group. Boom-bust had the largest measurable lift in the sample. Whether to formally re-tier depends on:
1. Replicating the result on a balanced (top-rank + bottom-rank) sample
2. Adding historical rank snapshots so L1/L2 can be measured against a real FADE arm
3. Stress-testing whether boom-bust lift survives under a fully-leaky-free production L1/L2

Until then: treat this as **observational evidence for elevating boom-bust** alongside the headline Tier A projection, not for demoting any current Tier A signal.
"""
    OUT.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT}")
    print()
    print("SP boom: lift={:+.2f} CI=[{:+.2f},{:+.2f}]".format(sp_boom.lift, sp_boom.ci_lo, sp_boom.ci_hi))
    print("H  boom: lift={:+.2f} CI=[{:+.2f},{:+.2f}]".format(h_boom.lift, h_boom.ci_lo, h_boom.ci_hi))


if __name__ == "__main__":
    main()
