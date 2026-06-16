"""
Test whether merge protocol's confidence labels (HIGH >=6, MED 4-5, LOW 2-3, NULL <2)
predict materially better forward FP/game than each other.

NOTE: The shrinkage snapshot parquets don't carry archetype / xwOBA / age columns,
so the 8 lenses are SYNTHESIZED using available proxies. This tests the LABEL
calibration concept, not the exact 8 production lenses.

Proxies used per lens:
- L1 (xFP rank vs replacement): l21_avg vs tier-median (above = BUY, bottom 25% = FADE)
- L2 (boom% L21): pct of L21 games >= boom_threshold (>0.25 = BUY, <0.10 = FADE)
    -- approximated as l21_avg distance above tier mean
- L3 (bust%): l21_avg distance below tier mean (FADE if l21_avg < tier p25)
- L4 (prior-year baseline above replacement): prior_avg vs tier-median
- L5 (sustainability proxy): n_l21 >= median n -> stable -> tilt HOLD/BUY
- L6 (xwOBA L21 above baseline): l21_avg > 1.10 * l42_avg -> BUY
- L7 (YoY direction): prior_avg vs prior2_avg
- L8 (age-based decline): no age column -> use prior2_avg presence as career_length proxy
    (longer career & prior2 > prior -> FADE)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

REPO = Path(r"c:/Users/Joshua/plv_clone")
H_PATH = REPO / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet"
SP_PATH = REPO / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet"
OUT = REPO / "data/research/validation_runs/confidence_label_calibration_2026-06-06.md"

RNG = np.random.default_rng(20260606)


def synthesize_votes(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Synthesize 8 lens votes (+1 BUY, 0 HOLD, -1 FADE) per row."""
    df = df.copy()
    # Compute tier-level medians/percentiles for as_of+tier so the rank is comparable
    tier_grp = df.groupby(["as_of", "tier"])["l21_avg"]
    df["l21_med"] = tier_grp.transform("median")
    df["l21_p25"] = tier_grp.transform(lambda s: s.quantile(0.25))
    df["l21_p75"] = tier_grp.transform(lambda s: s.quantile(0.75))

    prior_grp = df.groupby(["as_of", "tier"])["prior_avg"]
    df["prior_med"] = prior_grp.transform("median")

    n_med = df.groupby("as_of")["n_l21"].transform("median")

    # L1: l21 rank decile vs replacement
    df["L1"] = np.where(df["l21_avg"] > df["l21_med"], 1,
                        np.where(df["l21_avg"] < df["l21_p25"], -1, 0))
    # L2: boom proxy - top quartile of L21 in tier -> BUY
    df["L2"] = np.where(df["l21_avg"] > df["l21_p75"], 1,
                        np.where(df["l21_avg"] < df["l21_p25"] * 0.8, -1, 0))
    # L3: bust proxy - bottom quartile -> FADE
    df["L3"] = np.where(df["l21_avg"] < df["l21_p25"], -1, 0)
    # L4: prior-year above replacement
    df["L4"] = np.where(df["prior_avg"].fillna(df["prior_med"]) > df["prior_med"], 1,
                        np.where(df["prior_avg"].fillna(df["prior_med"]) < df["prior_med"] * 0.8, -1, 0))
    # L5: stability - more L21 samples -> trust positive signal
    df["L5"] = np.where(
        (df["n_l21"] >= n_med) & (df["l21_avg"] > df["l21_med"]), 1,
        np.where((df["n_l21"] < n_med * 0.6), -1, 0)
    )
    # L6: L21 above L42 by 10% -> BUY (recent surge)
    df["L6"] = np.where(df["l21_avg"] > 1.10 * df["l42_avg"], 1,
                        np.where(df["l21_avg"] < 0.85 * df["l42_avg"], -1, 0))
    # L7: YoY direction prior_avg vs prior2_avg
    p1 = df["prior_avg"].fillna(df["prior_med"])
    p2 = df["prior2_avg"].fillna(p1)
    df["L7"] = np.where(p1 > p2 * 1.05, 1,
                        np.where(p1 < p2 * 0.90, -1, 0))
    # L8: "age proxy" - if prior2 exists AND prior2 > prior -> decline -> FADE
    has_p2 = df["prior2_avg"].notna()
    df["L8"] = np.where(has_p2 & (df["prior2_avg"] > df["prior_avg"] * 1.10), -1,
                        np.where(~has_p2, 0, 0))

    lens_cols = [f"L{i}" for i in range(1, 9)]
    buys = (df[lens_cols] == 1).sum(axis=1)
    fades = (df[lens_cols] == -1).sum(axis=1)
    df["buys"] = buys
    df["fades"] = fades
    df["agreement"] = (buys - fades).abs()
    df["net_direction"] = np.sign(buys - fades).astype(int)

    df["confidence"] = pd.cut(
        df["agreement"],
        bins=[-0.5, 1.5, 3.5, 5.5, 8.5],
        labels=["NULL", "LOW", "MED", "HIGH"],
    )
    df["kind"] = kind
    return df


def bootstrap_mean_ci(values: np.ndarray, n_boot: int = 2000, alpha: float = 0.05):
    if len(values) == 0:
        return np.nan, np.nan, np.nan
    boots = RNG.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    lo = np.quantile(boots, alpha / 2)
    hi = np.quantile(boots, 1 - alpha / 2)
    return float(values.mean()), float(lo), float(hi)


def replacement_level(df: pd.DataFrame) -> float:
    """Use the bottom-tier as_of median target as 'replacement'."""
    # 51-150 H and 51-100 SP serve as replacement-level proxy
    if "tier" in df.columns:
        rep_tier = "51-150" if "51-150" in df["tier"].unique() else "51-100"
        rep = df.loc[df["tier"] == rep_tier, "target"]
        if len(rep) > 0:
            return float(rep.median())
    return float(df["target"].median())


def summarize(df: pd.DataFrame, kind: str, rep_level: float) -> pd.DataFrame:
    rows = []
    for label in ["HIGH", "MED", "LOW", "NULL"]:
        sub = df[df["confidence"] == label]
        if len(sub) == 0:
            rows.append({"kind": kind, "confidence": label, "n": 0,
                         "mean_fp": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                         "delta_vs_rep": np.nan})
            continue
        # net_direction-signed FP delta vs replacement:
        # for BUY-net we want target - rep (positive = good call)
        # for FADE-net we want rep - target (positive = good call)
        signed = np.where(sub["net_direction"] >= 0,
                          sub["target"] - rep_level,
                          rep_level - sub["target"])
        m, lo, hi = bootstrap_mean_ci(signed)
        rows.append({"kind": kind, "confidence": label, "n": len(sub),
                     "mean_signed_delta": m, "ci_lo": lo, "ci_hi": hi,
                     "raw_mean_target": float(sub["target"].mean()),
                     "pct_buy_net": float((sub["net_direction"] > 0).mean()),
                     "pct_fade_net": float((sub["net_direction"] < 0).mean())})
    return pd.DataFrame(rows)


def main() -> None:
    h = pd.read_parquet(H_PATH)
    sp = pd.read_parquet(SP_PATH)
    h_v = synthesize_votes(h, "H")
    sp_v = synthesize_votes(sp, "SP")
    h_rep = replacement_level(h)
    sp_rep = replacement_level(sp)

    h_sum = summarize(h_v, "H", h_rep)
    sp_sum = summarize(sp_v, "SP", sp_rep)

    # Distribution table
    def dist(df, kind):
        d = df["confidence"].value_counts().reindex(["HIGH", "MED", "LOW", "NULL"]).fillna(0).astype(int)
        d.name = kind
        return d

    h_dist = dist(h_v, "H")
    sp_dist = dist(sp_v, "SP")
    pooled = h_dist + sp_dist
    pooled.name = "POOLED"

    # Pooled across H+SP — z-score target within group to allow combining
    h_v["target_z"] = (h_v["target"] - h_v["target"].mean()) / h_v["target"].std()
    sp_v["target_z"] = (sp_v["target"] - sp_v["target"].mean()) / sp_v["target"].std()
    pool = pd.concat([h_v[["confidence", "target_z", "net_direction"]],
                       sp_v[["confidence", "target_z", "net_direction"]]], ignore_index=True)
    pool_rows = []
    for label in ["HIGH", "MED", "LOW", "NULL"]:
        sub = pool[pool["confidence"] == label]
        if len(sub) == 0:
            pool_rows.append({"confidence": label, "n": 0, "mean_z": np.nan,
                              "ci_lo": np.nan, "ci_hi": np.nan})
            continue
        signed = np.where(sub["net_direction"] >= 0, sub["target_z"], -sub["target_z"])
        m, lo, hi = bootstrap_mean_ci(np.asarray(signed))
        pool_rows.append({"confidence": label, "n": len(sub), "mean_signed_z": m,
                          "ci_lo": lo, "ci_hi": hi})
    pool_sum = pd.DataFrame(pool_rows)

    # Monotonicity check
    def mono_check(sum_df):
        vals = {row["confidence"]: row.get("mean_signed_delta", row.get("mean_signed_z"))
                for _, row in sum_df.iterrows() if not pd.isna(row.get("mean_signed_delta", row.get("mean_signed_z")))}
        order = [vals.get(l, np.nan) for l in ["HIGH", "MED", "LOW", "NULL"]]
        mono = all(order[i] >= order[i + 1] - 0.05 for i in range(len(order) - 1) if not (np.isnan(order[i]) or np.isnan(order[i + 1])))
        return mono, order

    h_mono, h_order = mono_check(h_sum)
    sp_mono, sp_order = mono_check(sp_sum)
    pool_mono, pool_order = mono_check(pool_sum)

    # CI overlap between HIGH and MED
    def ci_overlap(sum_df):
        d = {row["confidence"]: (row.get("ci_lo"), row.get("ci_hi"))
             for _, row in sum_df.iterrows()}
        hi_lo, hi_hi = d.get("HIGH", (np.nan, np.nan))
        med_lo, med_hi = d.get("MED", (np.nan, np.nan))
        if any(np.isnan(v) for v in [hi_lo, hi_hi, med_lo, med_hi]):
            return "n/a"
        # overlap if HIGH lo < MED hi AND MED lo < HIGH hi
        overlaps = (hi_lo < med_hi) and (med_lo < hi_hi)
        return "OVERLAP" if overlaps else "SEPARATED"

    h_overlap = ci_overlap(h_sum)
    sp_overlap = ci_overlap(sp_sum)
    pool_overlap = ci_overlap(pool_sum)

    # Build report
    lines = []
    lines.append("# Confidence Label Calibration — empirical test")
    lines.append("")
    lines.append("**Date**: 2026-06-06  •  **Inputs**: shrinkage_h_snap_2026-06-06.parquet (1498 H), shrinkage_sp_snap_2026-06-06.parquet (550 SP)")
    lines.append("")
    lines.append("**Question**: Do merge-protocol confidence labels (HIGH >=6 / MED 4-5 / LOW 2-3 / NULL <2) predict materially better forward FP/game?")
    lines.append("")
    lines.append("**Method**: 8 lens votes synthesized from available snapshot proxies (xFP rank, boom/bust quartile, prior baseline, stability, L21 vs L42, YoY direction, career-length decline). Target = forward 30d FP/game. Replacement = bottom-tier median. Signed delta uses net BUY/FADE direction so a correct FADE on a poor performer counts positive.")
    lines.append("")
    lines.append("**Caveat**: production lenses include archetype + xwOBA + age, which the snapshot parquets do not carry. This test validates the LABEL CONCEPT (does agreement count predict outcome quality?) not the exact 8 production lenses.")
    lines.append("")
    lines.append("## 1. Label distribution")
    lines.append("")
    lines.append("| Label | H (n) | SP (n) | Pooled |")
    lines.append("|---|---:|---:|---:|")
    for label in ["HIGH", "MED", "LOW", "NULL"]:
        lines.append(f"| {label} | {int(h_dist[label])} | {int(sp_dist[label])} | {int(pooled[label])} |")
    lines.append(f"| **Total** | **{h_dist.sum()}** | **{sp_dist.sum()}** | **{pooled.sum()}** |")
    lines.append("")
    lines.append("## 2. Hitter — signed FP delta vs replacement")
    lines.append("")
    lines.append(f"Replacement-level (51-150 tier median target): **{h_rep:.3f} FP/g**")
    lines.append("")
    lines.append("| Label | n | mean signed Δ | 95% CI | raw mean target | %BUY net | %FADE net |")
    lines.append("|---|---:|---:|---|---:|---:|---:|")
    for _, r in h_sum.iterrows():
        if r["n"] == 0:
            lines.append(f"| {r['confidence']} | 0 | - | - | - | - | - |")
            continue
        lines.append(f"| {r['confidence']} | {r['n']} | {r['mean_signed_delta']:+.3f} | [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}] | {r['raw_mean_target']:.3f} | {r['pct_buy_net']:.0%} | {r['pct_fade_net']:.0%} |")
    lines.append("")
    lines.append(f"Monotone HIGH > MED > LOW > NULL? **{'YES' if h_mono else 'NO'}** — order: {[f'{v:+.3f}' if not np.isnan(v) else 'NaN' for v in h_order]}")
    lines.append(f"HIGH vs MED 95% CI overlap: **{h_overlap}**")
    lines.append("")
    lines.append("## 3. SP — signed FP delta vs replacement")
    lines.append("")
    lines.append(f"Replacement-level (51-100 tier median target): **{sp_rep:.3f} FP/g**")
    lines.append("")
    lines.append("| Label | n | mean signed Δ | 95% CI | raw mean target | %BUY net | %FADE net |")
    lines.append("|---|---:|---:|---|---:|---:|---:|")
    for _, r in sp_sum.iterrows():
        if r["n"] == 0:
            lines.append(f"| {r['confidence']} | 0 | - | - | - | - | - |")
            continue
        lines.append(f"| {r['confidence']} | {r['n']} | {r['mean_signed_delta']:+.3f} | [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}] | {r['raw_mean_target']:.3f} | {r['pct_buy_net']:.0%} | {r['pct_fade_net']:.0%} |")
    lines.append("")
    lines.append(f"Monotone HIGH > MED > LOW > NULL? **{'YES' if sp_mono else 'NO'}** — order: {[f'{v:+.3f}' if not np.isnan(v) else 'NaN' for v in sp_order]}")
    lines.append(f"HIGH vs MED 95% CI overlap: **{sp_overlap}**")
    lines.append("")
    lines.append("## 4. Pooled (H + SP, z-scored within kind)")
    lines.append("")
    lines.append("| Label | n | mean signed z | 95% CI |")
    lines.append("|---|---:|---:|---|")
    for _, r in pool_sum.iterrows():
        if r["n"] == 0:
            lines.append(f"| {r['confidence']} | 0 | - | - |")
            continue
        lines.append(f"| {r['confidence']} | {r['n']} | {r['mean_signed_z']:+.3f} | [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}] |")
    lines.append("")
    lines.append(f"Monotone HIGH > MED > LOW > NULL? **{'YES' if pool_mono else 'NO'}** — order: {[f'{v:+.3f}' if not np.isnan(v) else 'NaN' for v in pool_order]}")
    lines.append(f"HIGH vs MED 95% CI overlap: **{pool_overlap}**")
    lines.append("")

    # Recommendation
    lines.append("## 5. Recommendation")
    lines.append("")
    h_hi = h_sum[h_sum["confidence"] == "HIGH"]["mean_signed_delta"].iloc[0] if (h_sum["confidence"] == "HIGH").any() else np.nan
    h_med = h_sum[h_sum["confidence"] == "MED"]["mean_signed_delta"].iloc[0] if (h_sum["confidence"] == "MED").any() else np.nan
    sp_hi = sp_sum[sp_sum["confidence"] == "HIGH"]["mean_signed_delta"].iloc[0] if (sp_sum["confidence"] == "HIGH").any() else np.nan
    sp_med = sp_sum[sp_sum["confidence"] == "MED"]["mean_signed_delta"].iloc[0] if (sp_sum["confidence"] == "MED").any() else np.nan

    h_gap = (h_hi - h_med) if not (np.isnan(h_hi) or np.isnan(h_med)) else np.nan
    sp_gap = (sp_hi - sp_med) if not (np.isnan(sp_hi) or np.isnan(sp_med)) else np.nan

    lines.append(f"- HIGH vs MED gap, H: **{h_gap:+.3f} FP/g** (HIGH={h_hi:+.3f}, MED={h_med:+.3f})")
    lines.append(f"- HIGH vs MED gap, SP: **{sp_gap:+.3f} FP/g** (HIGH={sp_hi:+.3f}, MED={sp_med:+.3f})")
    lines.append("")
    if (h_overlap == "OVERLAP" and sp_overlap == "OVERLAP") or (not h_mono and not sp_mono):
        verdict = "FAIL — labels are not calibrated. HIGH does NOT materially beat MED at 95% CI."
    elif (h_overlap == "SEPARATED" and sp_overlap == "SEPARATED" and h_mono and sp_mono):
        verdict = "PASS — labels are calibrated. HIGH > MED > LOW > NULL monotonically with separated CIs."
    else:
        verdict = "MIXED — some monotonicity but HIGH/MED CIs overlap on at least one bucket; labels are weakly calibrated at best."
    lines.append(f"### Verdict: {verdict}")
    lines.append("")
    lines.append("### Cutoff suggestion")
    if "FAIL" in verdict or "MIXED" in verdict:
        # Examine smoother cutoffs: try 7/5/3 and 5/3/2
        # Use the H+SP pool agreement values directly
        all_v = pd.concat([h_v.assign(target_norm=(h_v["target"] - h_v["target"].mean()) / h_v["target"].std()),
                          sp_v.assign(target_norm=(sp_v["target"] - sp_v["target"].mean()) / sp_v["target"].std())], ignore_index=True)
        all_v["signed_z"] = np.where(all_v["net_direction"] >= 0, all_v["target_norm"], -all_v["target_norm"])
        rows = []
        for ag in range(0, 9):
            sub = all_v[all_v["agreement"] == ag]
            if len(sub) < 20:
                continue
            m, lo, hi = bootstrap_mean_ci(sub["signed_z"].values, n_boot=500)
            rows.append((ag, len(sub), m, lo, hi))
        lines.append("")
        lines.append("Per-agreement-count signed z (n>=20 only):")
        lines.append("")
        lines.append("| agreement | n | mean signed z | 95% CI |")
        lines.append("|---:|---:|---:|---|")
        for ag, n, m, lo, hi in rows:
            lines.append(f"| {ag} | {n} | {m:+.3f} | [{lo:+.3f}, {hi:+.3f}] |")
        lines.append("")
        lines.append("Use this table to choose cutoffs that separate strata by at least 0.1 signed-z (~1 FP/g for SP, ~0.1 FP/g for H).")
    else:
        lines.append("Current cutoffs (HIGH >=6, MED 4-5, LOW 2-3) are validated.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print()
    print("=== KEY RESULTS ===")
    print(f"H verdict: HIGH-MED gap {h_gap:+.3f} FP/g, CI overlap: {h_overlap}, monotone: {h_mono}")
    print(f"SP verdict: HIGH-MED gap {sp_gap:+.3f} FP/g, CI overlap: {sp_overlap}, monotone: {sp_mono}")
    print(f"Pool verdict: monotone: {pool_mono}, CI overlap: {pool_overlap}")
    print(f"Overall: {verdict}")


if __name__ == "__main__":
    main()
