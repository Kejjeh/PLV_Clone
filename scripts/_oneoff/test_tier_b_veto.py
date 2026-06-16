"""
Empirical validation of the Tier B veto rule.

Tier A says BUY when prior FP/g > median; FADE when < p25; else HOLD.
Tier B (the "veto") says REGRESS/REAL_DECLINE when:
  - Hitters: xwOBA L21d vs prior-year season baseline gap < -0.060
  - SPs: K% L30d drops > 8pp vs prior-year season baseline

We test whether downgrading Tier A BUY -> HOLD when Tier B vetoes
produces better forward 30d FP outcomes than leaving the BUY alone.

Inputs:
  data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet
  data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet
  data/research/xfp_cache/statcast_2024.parquet
  data/research/xfp_cache/statcast_2025.parquet

Output:
  data/research/validation_runs/tier_b_veto_validation_2026-06-06.md
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("c:/Users/Joshua/plv_clone")
SNAP_H = REPO / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet"
SNAP_SP = REPO / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet"
SC_DIR = REPO / "data/research/xfp_cache"
OUT = REPO / "data/research/validation_runs/tier_b_veto_validation_2026-06-06.md"

H_XWOBA_DROP_THRESH = -0.060  # gap that triggers REAL_DECLINE
SP_K_DROP_THRESH_PP = 8.0     # K% drop > 8pp triggers REGRESS/NOISE
L21_DAYS = 21
L30_DAYS = 30


# ---- helpers ----------------------------------------------------------------

def load_statcast_for(year: int, cols: list[str]) -> pd.DataFrame:
    fp = SC_DIR / f"statcast_{year}.parquet"
    sc = pd.read_parquet(fp, columns=cols)
    if "game_date" in sc.columns:
        sc["game_date"] = pd.to_datetime(sc["game_date"])
    return sc


def compute_prior_season_xwoba(sc_prior: pd.DataFrame) -> pd.Series:
    ev = sc_prior[sc_prior["events"].notna()].copy()
    # Use estimated_woba_using_speedangle for true xwOBA proxy.
    # For PAs without speedangle (Ks, walks) fall back to standard wOBA values.
    # Statcast estimated_woba_using_speedangle is NaN for non-BBE; we replace
    # with rule-based wOBA weights for K/BB/HBP.
    woba_map = {
        "strikeout": 0.0,
        "walk": 0.69,
        "intent_walk": 0.69,
        "hit_by_pitch": 0.72,
    }
    ev["w"] = ev["estimated_woba_using_speedangle"]
    ev.loc[ev["events"].isin(woba_map), "w"] = ev["events"].map(woba_map)
    # drop the PAs where neither field nor speedangle nor map exists
    ev = ev.dropna(subset=["w"])
    return ev.groupby("batter")["w"].mean()


def compute_l21_xwoba_per_player(sc_curr: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """Per-batter xwOBA in the 21d window ending just before as_of."""
    start = as_of - pd.Timedelta(days=L21_DAYS)
    win = sc_curr[(sc_curr["game_date"] >= start) & (sc_curr["game_date"] < as_of)]
    ev = win[win["events"].notna()].copy()
    woba_map = {
        "strikeout": 0.0,
        "walk": 0.69,
        "intent_walk": 0.69,
        "hit_by_pitch": 0.72,
    }
    ev["w"] = ev["estimated_woba_using_speedangle"]
    ev.loc[ev["events"].isin(woba_map), "w"] = ev["events"].map(woba_map)
    ev = ev.dropna(subset=["w"])
    grp = ev.groupby("batter")["w"]
    return grp.agg(["mean", "size"]).rename(columns={"mean": "l21_xwoba", "size": "l21_pa"})


def compute_prior_season_kpct(sc_prior: pd.DataFrame) -> pd.Series:
    ev = sc_prior[sc_prior["events"].notna()]
    grp = ev.groupby("pitcher")["events"]
    k = grp.apply(lambda s: (s == "strikeout").sum())
    n = grp.size()
    return (k / n).rename("prior_kpct")


def compute_l30_kpct_per_pitcher(sc_curr: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    start = as_of - pd.Timedelta(days=L30_DAYS)
    win = sc_curr[(sc_curr["game_date"] >= start) & (sc_curr["game_date"] < as_of)]
    ev = win[win["events"].notna()].copy()
    grp = ev.groupby("pitcher")["events"]
    k = grp.apply(lambda s: (s == "strikeout").sum())
    n = grp.size()
    out = pd.DataFrame({"l30_kpct": (k / n), "l30_pa": n})
    return out


# ---- Tier A verdicts --------------------------------------------------------

def add_tier_a(snap: pd.DataFrame) -> pd.DataFrame:
    """Compute Tier A verdict per (year, progress) bucket using prior_avg."""
    out_parts = []
    for (yr, prog), g in snap.groupby(["year", "progress"]):
        prior = g["prior_avg"].dropna()
        if len(prior) < 10:
            med = prior.median() if len(prior) else np.nan
            p25 = prior.quantile(0.25) if len(prior) else np.nan
        else:
            med = prior.median()
            p25 = prior.quantile(0.25)
        gg = g.copy()
        gg["_med"] = med
        gg["_p25"] = p25
        gg["tier_a"] = np.where(
            gg["prior_avg"].isna(), "UNKNOWN",
            np.where(gg["prior_avg"] > med, "BUY",
                     np.where(gg["prior_avg"] < p25, "FADE", "HOLD"))
        )
        out_parts.append(gg)
    return pd.concat(out_parts, ignore_index=True)


# ---- Tier B for hitters -----------------------------------------------------

def add_tier_b_hitters(snap: pd.DataFrame) -> pd.DataFrame:
    snap = snap.copy()
    snap["as_of"] = pd.to_datetime(snap["as_of"])
    snap["tier_b"] = "OK"
    snap["xwoba_gap"] = np.nan

    # Cache prior-season xwOBA by year.
    prior_cache: dict[int, pd.Series] = {}
    for prior_yr in sorted(set(int(y) - 1 for y in snap["year"].unique())):
        if (SC_DIR / f"statcast_{prior_yr}.parquet").exists():
            sc_p = load_statcast_for(prior_yr, ["batter", "events", "estimated_woba_using_speedangle"])
            prior_cache[prior_yr] = compute_prior_season_xwoba(sc_p)
            del sc_p
    # Single-year iteration: load current year once, compute per-as_of windows.
    for yr in sorted(snap["year"].unique()):
        prior_yr = yr - 1
        if prior_yr not in prior_cache:
            continue
        prior_xwoba = prior_cache[prior_yr]
        try:
            sc_curr = load_statcast_for(yr, ["batter", "events",
                                              "estimated_woba_using_speedangle", "game_date"])
        except FileNotFoundError:
            continue
        ym = snap[snap["year"] == yr]
        for as_of in sorted(ym["as_of"].unique()):
            mask = (snap["year"] == yr) & (snap["as_of"] == as_of)
            l21 = compute_l21_xwoba_per_player(sc_curr, as_of)
            if l21.empty:
                continue
            # join L21 + prior
            sub = snap.loc[mask, ["pid"]].copy()
            sub = sub.merge(l21.rename_axis("pid").reset_index(), on="pid", how="left")
            sub["prior_xwoba"] = sub["pid"].map(prior_xwoba)
            sub["gap"] = sub["l21_xwoba"] - sub["prior_xwoba"]
            # require min PA to trust L21
            sub.loc[sub["l21_pa"] < 40, "gap"] = np.nan
            gap_arr = pd.to_numeric(sub["gap"], errors="coerce").astype(float).to_numpy()
            snap.loc[mask, "xwoba_gap"] = gap_arr
            tier_b = np.where(
                np.isfinite(gap_arr) & (gap_arr < H_XWOBA_DROP_THRESH),
                "REAL_DECLINE", "OK"
            )
            snap.loc[mask, "tier_b"] = tier_b
        del sc_curr
    return snap


# ---- Tier B for SPs ---------------------------------------------------------

def add_tier_b_sps(snap: pd.DataFrame) -> pd.DataFrame:
    snap = snap.copy()
    snap["as_of"] = pd.to_datetime(snap["as_of"])
    snap["tier_b"] = "OK"
    snap["k_drop_pp"] = np.nan

    prior_cache: dict[int, pd.Series] = {}
    for prior_yr in sorted(set(int(y) - 1 for y in snap["year"].unique())):
        if (SC_DIR / f"statcast_{prior_yr}.parquet").exists():
            sc_p = load_statcast_for(prior_yr, ["pitcher", "events"])
            prior_cache[prior_yr] = compute_prior_season_kpct(sc_p)
            del sc_p

    for yr in sorted(snap["year"].unique()):
        prior_yr = yr - 1
        if prior_yr not in prior_cache:
            continue
        prior_k = prior_cache[prior_yr]
        try:
            sc_curr = load_statcast_for(yr, ["pitcher", "events", "game_date"])
        except FileNotFoundError:
            continue
        ym = snap[snap["year"] == yr]
        for as_of in sorted(ym["as_of"].unique()):
            mask = (snap["year"] == yr) & (snap["as_of"] == as_of)
            l30 = compute_l30_kpct_per_pitcher(sc_curr, as_of)
            sub = snap.loc[mask, ["pid"]].copy()
            sub = sub.merge(l30.rename_axis("pid").reset_index(), on="pid", how="left")
            sub["prior_kpct"] = sub["pid"].map(prior_k)
            sub["drop_pp"] = (sub["prior_kpct"] - sub["l30_kpct"]) * 100.0
            sub.loc[sub["l30_pa"] < 50, "drop_pp"] = np.nan
            drop_arr = pd.to_numeric(sub["drop_pp"], errors="coerce").astype(float).to_numpy()
            snap.loc[mask, "k_drop_pp"] = drop_arr
            tier_b = np.where(
                np.isfinite(drop_arr) & (drop_arr > SP_K_DROP_THRESH_PP),
                "REGRESS", "OK"
            )
            snap.loc[mask, "tier_b"] = tier_b
        del sc_curr
    return snap


# ---- veto analysis ----------------------------------------------------------

def combined_relative(h: pd.DataFrame, sp: pd.DataFrame) -> dict:
    """Row-weighted view: rescale target into bucket-median units so H + SP can be pooled."""
    parts = []
    for df, group in ((h, "H"), (sp, "SP")):
        sub = df[(df["tier_a"] == "BUY") & df["target"].notna()].copy()
        if sub.empty:
            continue
        med = sub.groupby(["year", "progress"])["target"].transform("median")
        sub["_fwd_med"] = med
        sub["fwd_hit"] = sub["target"] > sub["_fwd_med"]
        sub["delta_rel"] = (sub["_fwd_med"] - sub["target"]) / sub["_fwd_med"].abs()
        sub["_group"] = group
        parts.append(sub)
    if not parts:
        return {"label": "Combined", "n_buy": 0, "n_conflict": 0}
    sub = pd.concat(parts, ignore_index=True)
    n_buy = len(sub)
    conflicts = sub[sub["tier_b"].isin(["REAL_DECLINE", "REGRESS", "NOISE"])]
    n_conflict = len(conflicts)
    if n_conflict == 0:
        return {"label": "Combined", "n_buy": n_buy, "n_conflict": 0}
    veto_correct = int((~conflicts["fwd_hit"]).sum())
    veto_false = int(conflicts["fwd_hit"].sum())
    pct_correct = 100.0 * veto_correct / n_conflict
    pct_false = 100.0 * veto_false / n_conflict
    return {
        "label": "Combined (relative)",
        "n_buy": n_buy,
        "n_conflict": n_conflict,
        "pct_correct": pct_correct,
        "pct_false": pct_false,
        "veto_correct_n": veto_correct,
        "veto_false_n": veto_false,
        "mean_rel_swing_per_veto": float(conflicts["delta_rel"].mean()),
        "net_rel_swing": float(conflicts["delta_rel"].sum()),
        "net_fp_swing": np.nan,                  # not meaningful pooled
        "mean_fp_swing_per_veto": np.nan,
        "mean_target_veto_cases": np.nan,
        "mean_target_no_veto_cases": np.nan,
        "mean_med_veto_cases": np.nan,
    }


def veto_summary(df: pd.DataFrame, label: str) -> dict:
    """For BUY-by-Tier-A rows, compare outcomes when Tier B vetoes."""
    # Need a target & a per-bucket median to call hit/miss.
    sub = df[df["tier_a"] == "BUY"].copy()
    sub = sub[sub["target"].notna()]
    if sub.empty:
        return {"label": label, "n_buy": 0, "n_conflict": 0}

    # Forward-FP median by (year, progress) — neutral benchmark.
    med = sub.groupby(["year", "progress"])["target"].transform("median")
    sub["_fwd_med"] = med
    sub["fwd_hit"] = sub["target"] > sub["_fwd_med"]  # BUY "would have been right"

    n_buy = len(sub)
    conflicts = sub[sub["tier_b"].isin(["REAL_DECLINE", "REGRESS", "NOISE"])]
    n_conflict = len(conflicts)

    if n_conflict == 0:
        return {
            "label": label, "n_buy": n_buy, "n_conflict": 0,
            "pct_correct": np.nan, "pct_false": np.nan,
            "net_fp_swing": 0.0, "mean_target_veto": np.nan,
            "mean_target_no_veto": float(sub["target"].mean()),
            "veto_correct_n": 0, "veto_false_n": 0,
        }

    # CORRECT veto: Tier B vetoed BUY AND fwd FP was below median (BUY would have whiffed).
    # FALSE  veto: Tier B vetoed BUY AND fwd FP was above median (BUY would have hit).
    veto_correct = (~conflicts["fwd_hit"]).sum()
    veto_false = conflicts["fwd_hit"].sum()
    pct_correct = 100.0 * veto_correct / n_conflict
    pct_false = 100.0 * veto_false / n_conflict

    # Net FP swing: applying veto downgrades BUY -> HOLD. We assume HOLD's
    # outcome distribution = bucket median. So delta per row = median - target.
    # Positive swing means veto SAVED us FP (target was below median, we'd
    # have done worse following BUY).
    delta = conflicts["_fwd_med"] - conflicts["target"]
    net_swing = float(delta.sum())
    mean_swing = float(delta.mean())

    return {
        "label": label,
        "n_buy": n_buy,
        "n_conflict": n_conflict,
        "pct_correct": pct_correct,
        "pct_false": pct_false,
        "veto_correct_n": int(veto_correct),
        "veto_false_n": int(veto_false),
        "net_fp_swing": net_swing,
        "mean_fp_swing_per_veto": mean_swing,
        "mean_target_veto_cases": float(conflicts["target"].mean()),
        "mean_target_no_veto_cases": float(
            sub.loc[~sub.index.isin(conflicts.index), "target"].mean()),
        "mean_med_veto_cases": float(conflicts["_fwd_med"].mean()),
    }


# ---- main -------------------------------------------------------------------

def main() -> None:
    print("Loading snapshots...")
    h = pd.read_parquet(SNAP_H)
    sp = pd.read_parquet(SNAP_SP)

    print(f"H n={len(h)}, SP n={len(sp)}")

    print("Tier A verdicts...")
    h = add_tier_a(h)
    sp = add_tier_a(sp)

    print("Tier B for hitters (xwOBA L21 vs prior season)...")
    h = add_tier_b_hitters(h)

    print("Tier B for SPs (K% L30 vs prior season)...")
    sp = add_tier_b_sps(sp)

    print("\nTier A distribution (H):", h["tier_a"].value_counts().to_dict())
    print("Tier B distribution (H):", h["tier_b"].value_counts().to_dict())
    print("Tier A distribution (SP):", sp["tier_a"].value_counts().to_dict())
    print("Tier B distribution (SP):", sp["tier_b"].value_counts().to_dict())

    h_summary = veto_summary(h, "Hitters")
    sp_summary = veto_summary(sp, "SPs")
    # NOTE: a true "combined" view is meaningless because hitter target
    # (FP/g, ~2-5 scale) and SP target (FP/start, ~10-20 scale) are on
    # different scales. We report a row-weighted-correctness combined
    # bucket using bucket-relative deltas instead of summing raw FP.
    combined = combined_relative(h, sp)

    print("\nH:", h_summary)
    print("\nSP:", sp_summary)
    print("\nCombined (relative):", combined)

    md = render_md(h_summary, sp_summary, combined, h, sp)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md, encoding="utf-8")
    print(f"\nWrote {OUT}")


def fmt(v, p=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{p}f}"
    return str(v)


def render_md(h, sp, comb, h_df, sp_df) -> str:
    lines = []
    lines.append("# Tier B Veto Empirical Validation")
    lines.append("")
    lines.append("**Generated:** 2026-06-06")
    lines.append("")
    lines.append("**Question.** When Tier A (prior-season FP/g percentile rank) says BUY")
    lines.append("but Tier B (xwOBA L21 vs prior-season baseline / SP K% L30 vs prior")
    lines.append("season) screams REAL_DECLINE/REGRESS, the production rule downgrades the")
    lines.append("verdict one step (BUY -> HOLD). Does that veto actually improve hit rate?")
    lines.append("")
    lines.append("**Method.**")
    lines.append("- Snapshot grid: hitters n=" + str(len(h_df)) + ", SPs n=" + str(len(sp_df)) +
                 " from `shrinkage_*_snap_2026-06-06.parquet` (2024 + 2025, monthly as_of).")
    lines.append("- Tier A bucketed by (year, progress): BUY = prior_avg > median, FADE < p25.")
    lines.append("- Tier B hitter: gap = L21 xwOBA - prior-yr xwOBA; veto if gap < " +
                 f"{H_XWOBA_DROP_THRESH:.3f} and L21 PA >= 40.")
    lines.append("- Tier B SP: drop = prior K% - L30 K% (pp); veto if drop > " +
                 f"{SP_K_DROP_THRESH_PP:.0f}pp and L30 PA >= 50.")
    lines.append("- Forward outcome = `target` (next-window FP/g). 'Hit' = target above")
    lines.append("  bucket median; otherwise BUY 'would have whiffed.'")
    lines.append("- Veto CORRECT = vetoed BUY and target was below median. FALSE = vetoed")
    lines.append("  BUY and target was above median. Net FP swing = sum(median - target)")
    lines.append("  across vetoed rows; positive means the veto saved FP.")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Group | N BUY rows | N conflicts | % correct vetoes | % false vetoes | Mean FP swing/veto | Net FP swing |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in (h, sp):
        lines.append(
            f"| {s['label']} | {s.get('n_buy',0)} | {s.get('n_conflict',0)} | "
            f"{fmt(s.get('pct_correct'))}% | {fmt(s.get('pct_false'))}% | "
            f"{fmt(s.get('mean_fp_swing_per_veto'))} | {fmt(s.get('net_fp_swing'))} |"
        )
    # Combined row uses relative swing because FP scales differ.
    lines.append(
        f"| {comb['label']} | {comb.get('n_buy',0)} | {comb.get('n_conflict',0)} | "
        f"{fmt(comb.get('pct_correct'))}% | {fmt(comb.get('pct_false'))}% | "
        f"{fmt(comb.get('mean_rel_swing_per_veto'),3)} (rel) | "
        f"{fmt(comb.get('net_rel_swing'),3)} (rel) |"
    )
    lines.append("")
    lines.append("### Detail per group")
    for s in (h, sp):
        lines.append(f"#### {s['label']}")
        if s.get("n_conflict", 0) == 0:
            lines.append("- No conflicts found.")
            continue
        lines.append(f"- BUY rows: **{s['n_buy']}**, conflict rows: **{s['n_conflict']}**.")
        lines.append(f"- Vetoes that turned out CORRECT (target < median): **{s['veto_correct_n']}** "
                     f"({fmt(s['pct_correct'])}%)")
        lines.append(f"- Vetoes that turned out FALSE   (target >= median): **{s['veto_false_n']}** "
                     f"({fmt(s['pct_false'])}%)")
        lines.append(f"- Mean target FP on vetoed rows: **{fmt(s['mean_target_veto_cases'])}**")
        lines.append(f"- Mean target FP on un-vetoed BUY rows: **{fmt(s['mean_target_no_veto_cases'])}**")
        lines.append(f"- Bucket-median benchmark on vetoed rows: **{fmt(s['mean_med_veto_cases'])}**")
        lines.append(f"- Net FP swing if veto applied: **{fmt(s['net_fp_swing'])} FP** "
                     f"({fmt(s['mean_fp_swing_per_veto'])} per row)")
        lines.append("")
    # Combined relative panel.
    lines.append(f"#### {comb['label']}")
    if comb.get("n_conflict", 0) == 0:
        lines.append("- No conflicts found.")
    else:
        lines.append("- Hitter and SP targets are on different scales (FP/g vs FP/start) so FP")
        lines.append("  swings are not directly summable. The combined row uses bucket-relative")
        lines.append("  swing = `(median - target) / |median|`, pooled across both groups.")
        lines.append(f"- Pooled BUY rows: **{comb['n_buy']}**, conflict rows: **{comb['n_conflict']}**.")
        lines.append(f"- Vetoes CORRECT: **{comb['veto_correct_n']}** ({fmt(comb['pct_correct'])}%)")
        lines.append(f"- Vetoes FALSE:   **{comb['veto_false_n']}** ({fmt(comb['pct_false'])}%)")
        lines.append(f"- Mean relative swing per veto: **{fmt(comb['mean_rel_swing_per_veto'],3)}** "
                     f"(positive = veto saved FP relative to median)")
        lines.append("")
    lines.append("## Recommendation")
    # Per-group recommendation: hitter and SP veto have very different value.
    lines.append("### Hitters")
    lines.append(derive_recommendation(h))
    lines.append("")
    lines.append("### SPs")
    lines.append(derive_recommendation(sp))
    lines.append("")
    lines.append("### Pooled")
    lines.append(derive_recommendation_relative(comb))
    return "\n".join(lines)


def derive_recommendation(s: dict) -> str:
    if s.get("n_conflict", 0) < 10:
        return ("Too few conflict cases (<10) in combined sample to draw a defensible "
                "conclusion. Hold the veto in place but re-test in 4-6 weeks with more "
                "panel data, especially mid-season as_of slices.")
    pct_correct = s.get("pct_correct") or 0
    net = s.get("net_fp_swing") or 0
    per_row = s.get("mean_fp_swing_per_veto") or 0
    if pct_correct >= 55 and per_row > 0.5:
        return (f"**KEEP the Tier B veto.** {fmt(pct_correct)}% of vetoes were correct, "
                f"net FP swing +{fmt(net)} ({fmt(per_row)}/row). The veto reliably "
                "rescues FP that a naive BUY would have lost.")
    if pct_correct >= 50 and per_row >= 0:
        return (f"**KEEP but watch.** Hit rate {fmt(pct_correct)}% (just above coin-flip) "
                f"with net swing +{fmt(net)} FP ({fmt(per_row)}/row). Veto adds marginal "
                "value; consider tightening Tier B thresholds before relying on it.")
    if pct_correct >= 45:
        return (f"**WEAKEN the veto.** Only {fmt(pct_correct)}% correct, net swing "
                f"{fmt(net)} FP. Apply only when Tier B is paired with a second confirming "
                "signal (process metric drift, age >=32, IL-adjacent), not as a standalone "
                "downgrade rule.")
    return (f"**DROP the veto.** Only {fmt(pct_correct)}% of vetoes were correct, net swing "
            f"{fmt(net)} FP ({fmt(per_row)}/row). The downgrade rule is overcautious: it "
            "kills more BUY hits than it rescues. Surface Tier B as display-only context.")


def derive_recommendation_relative(s: dict) -> str:
    if s.get("n_conflict", 0) < 10:
        return ("Too few pooled conflict cases (<10) to draw a defensible conclusion.")
    pct_correct = s.get("pct_correct") or 0
    rel = s.get("mean_rel_swing_per_veto") or 0
    if pct_correct >= 55 and rel > 0.02:
        return (f"Pooled hit rate **{fmt(pct_correct)}%** with mean relative swing "
                f"**+{fmt(rel,3)}** per veto. Veto adds value when averaged over both groups, "
                "but per-group analysis above is more reliable.")
    if pct_correct >= 50:
        return (f"Pooled hit rate **{fmt(pct_correct)}%** with mean relative swing "
                f"**{fmt(rel,3)}** per veto. Veto is at coin-flip; keep only where "
                "per-group evidence supports it (see SP section).")
    return (f"Pooled hit rate **{fmt(pct_correct)}%** with mean relative swing "
            f"**{fmt(rel,3)}** per veto. The veto degrades overall accuracy.")


if __name__ == "__main__":
    main()
