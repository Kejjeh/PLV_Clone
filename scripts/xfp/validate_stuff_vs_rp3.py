"""validate_stuff_vs_rp3.py — Rule-9 INTEGRATION test of FanGraphs Stuff+ vs production rp3.

Pre-registered: data/research/validation_runs/stuff_vs_rp3_2026-06-06.md

Question answered: does adding Stuff+ to the FULL production RP3_FEATS list improve
the rest-of-season SP FP/start projection, or is its signal already captured?

Baseline = the EXACT live RP3_FEATS (Rule 9). Framing = in-season -> RoS (Rule 8):
features as-of ~June 6, predict FP/start over the rest of the season.

Headline:
  cross_year_r(RP3_FEATS)  vs  cross_year_r(RP3_FEATS + stuff_plus)
  + partial r of stuff_plus vs RoS after controlling for ALL RP3_FEATS
  + collinearity of stuff_plus against each RP3_FEAT (explains redundancy)
  + same battery for the archetype STUFF grade (prior-year, leakage-safe)

DO NOT commit.
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, attach_prior_year_feature  # noqa: E402

from plv_clone.models.xfp.rp3 import (  # noqa: E402
    RP3_FEATS, cross_year_eval, TARGET, EVAL_GS_MIN, ROS_GS_MIN,
)

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"
SP_RATINGS = ROOT / "data" / "research" / "sp_ratings_master.csv"

# FG Stuff+ in the fg_asof _pre pulls only exists 2021+. The rolling substrate
# also has 2018/2019 but no as-of-June-6 Stuff+ for those years.
FG_YEARS = [2021, 2022, 2023, 2024, 2025]
HOLDOUT = [2024, 2025]
GATE = 0.005


def june6_split_day(rolling: pd.DataFrame) -> dict[int, int]:
    """For each FG year, the split_day whose cutoff_date is nearest June 6."""
    out = {}
    sub = rolling[["year", "split_day", "cutoff_date"]].drop_duplicates().copy()
    sub["cutoff_date"] = pd.to_datetime(sub["cutoff_date"])
    for y in FG_YEARS:
        s = sub[sub.year == y].copy()
        if s.empty:
            continue
        s["d"] = (s["cutoff_date"] - pd.Timestamp(f"{y}-06-06")).abs()
        out[y] = int(s.nsmallest(1, "d").split_day.iloc[0])
    return out


def attach_stuff_plus(rolling: pd.DataFrame, sd_map: dict[int, int]) -> pd.DataFrame:
    """Join as-of-June-6 FG Stuff+ (+ companion FG metrics for diagnostics)
    onto the June-6-aligned rolling rows, key mlb_id==pitcher."""
    frames = []
    for y, sd in sd_map.items():
        fg = pd.read_csv(FG / f"fg_pit_{y}_pre.csv")
        fg = fg.rename(columns={"mlb_id": "pitcher"})
        keep = ["pitcher", "stuff_plus", "location_plus", "pitching_plus"]
        keep = [c for c in keep if c in fg.columns]
        fg = fg[keep].dropna(subset=["pitcher"]).copy()
        fg["pitcher"] = fg["pitcher"].astype(int)
        fg["year"] = y
        fg["split_day"] = sd
        frames.append(fg)
    fgall = pd.concat(frames, ignore_index=True)
    r = rolling.copy()
    r["pitcher"] = r["pitcher"].astype(int)
    return r.merge(fgall, on=["pitcher", "year", "split_day"], how="left")


def eval_pop(df: pd.DataFrame, feats: list[str]):
    """Run production cross_year_eval but only over FG_YEARS (so the LOO test
    years match the population where the candidate exists)."""
    # cross_year_eval iterates TRAIN_YEARS internally; restrict df to FG_YEARS
    # so held-out years are FG-covered and the comparison is apples-to-apples.
    sub = df[df["year"].isin(FG_YEARS)].copy()
    return cross_year_eval(sub, feats)


def partial_r(df: pd.DataFrame, x: str, y: str, controls: list[str]):
    cols = [x, y] + controls
    s = df[cols].dropna()
    if len(s) < 30:
        return np.nan, np.nan, len(s)
    Z = s[controls].values
    rx = s[x].values - LinearRegression().fit(Z, s[x]).predict(Z)
    ry = s[y].values - LinearRegression().fit(Z, s[y]).predict(Z)
    r, p = pearsonr(rx, ry)
    return r, p, len(s)


def run_candidate(pop: pd.DataFrame, col: str, label: str):
    print("\n" + "=" * 78)
    print(f"CANDIDATE: {label}  (column `{col}`)")
    print("=" * 78)

    nn = pop[col].notna().sum()
    print(f"  non-null: {nn}/{len(pop)} ({100*nn/len(pop):.1f}%)")

    # Restrict to rows where candidate is present so baseline & full are on the
    # IDENTICAL population (true Rule-9 apples-to-apples).
    sub = pop[pop[col].notna()].copy()

    feats = [f for f in RP3_FEATS if f in sub.columns]
    missing = [f for f in RP3_FEATS if f not in sub.columns]
    if missing:
        print(f"  [Rule-9 caveat] {len(missing)} RP3_FEAT absent from substrate, "
              f"excluded from baseline: {missing}")
        print(f"  (baseline = {len(feats)}/{len(RP3_FEATS)} production feats; the "
              f"excluded ones are opponent/schedule, orthogonal to stuff)")

    py_base, ov_base = eval_pop(sub, feats)
    py_full, ov_full = eval_pop(sub, feats + [col])
    lift = ov_full["r"] - ov_base["r"]

    print(f"\n  Baseline (RP3_FEATS, {len(RP3_FEATS)} feats):   r={ov_base['r']:.4f}  n={ov_base['n']}")
    print(f"  Full     (+{col}, {len(RP3_FEATS)+1} feats):  r={ov_full['r']:.4f}  n={ov_full['n']}")
    print(f"  >>> LIFT = {lift:+.4f}   (PASS bar >= +{GATE:.3f})")

    print("\n  Per-year LOO lift (full - baseline):")
    pos = 0
    n_yr = 0
    for yr in sorted(py_full.keys()):
        if yr in py_base:
            d = py_full[yr]["r"] - py_base[yr]["r"]
            n_yr += 1
            if d > 0:
                pos += 1
            print(f"    {yr}: base={py_base[yr]['r']:+.4f}  full={py_full[yr]['r']:+.4f}  d={d:+.4f}  n={py_full[yr]['n']}")
    print(f"  Sign consistency: {pos}/{n_yr} years positive (bar 4-of-5)")

    ho_full = [py_full[y]["r"] for y in HOLDOUT if y in py_full]
    ho_base = [py_base[y]["r"] for y in HOLDOUT if y in py_base]
    ho_lift = float(np.mean(ho_full) - np.mean(ho_base)) if ho_full and ho_base else None
    if ho_lift is not None:
        print(f"  Holdout (2024-25) avg lift: {ho_lift:+.4f}")

    # Partial r vs RoS after controlling for ALL RP3_FEATS (orthogonal signal)
    pr, pp, pn = partial_r(sub, col, TARGET, feats)
    print(f"\n  Partial r of {col} vs {TARGET} | ALL RP3_FEATS: {pr:+.4f} (p={pp:.4f}, n={pn})")
    print("    (this is the orthogonal signal that survives the full baseline)")

    # raw r for reference
    rr = pearsonr(*sub[[col, TARGET]].dropna().values.T)[0]
    print(f"  Raw r of {col} vs {TARGET} (no controls): {rr:+.4f}")

    return dict(lift=lift, r_base=ov_base["r"], r_full=ov_full["r"],
                pos=pos, n_yr=n_yr, ho_lift=ho_lift, partial=pr, partial_p=pp,
                raw=rr, n=ov_full["n"])


def collinearity(pop: pd.DataFrame, col: str):
    print("\n" + "-" * 78)
    print(f"COLLINEARITY: |corr({col}, RP3_FEAT)| — what absorbs it")
    print("-" * 78)
    feats = [f for f in RP3_FEATS if f in pop.columns]
    s = pop[[col] + feats].dropna()
    rows = []
    for f in feats:
        if s[f].std() == 0:
            continue
        r = pearsonr(s[col], s[f])[0]
        rows.append((f, r))
    rows.sort(key=lambda t: -abs(t[1]))
    for f, r in rows[:12]:
        print(f"    {f:<28s} r={r:+.3f}")


def main():
    print("=== validate_stuff_vs_rp3: Rule-9 integration test of FG Stuff+ vs rp3 ===")
    print("Framing: in-season (as-of ~June 6) -> rest-of-season FP/start (Rule 8)")

    rolling = prep_rolling()
    print(f"\nrolling substrate rows: {len(rolling)}")

    sd_map = june6_split_day(rolling)
    print("June-6-aligned split_day per year:")
    for y, sd in sd_map.items():
        cd = rolling[(rolling.year == y) & (rolling.split_day == sd)]["cutoff_date"].iloc[0]
        print(f"  {y}: split_day={sd}  cutoff={cd}")

    # Filter rolling to the June-6-aligned (year, split_day) rows only, so the
    # whole test runs on the in-season slice that matches the Stuff+ as-of date.
    masks = [(rolling.year == y) & (rolling.split_day == sd) for y, sd in sd_map.items()]
    pop = rolling[np.logical_or.reduce(masks)].copy()
    # Apply the same eval-eligibility filters cross_year_eval uses so the
    # candidate-present population is the production-eligible one.
    pop = pop[(pop["gs_to"] >= EVAL_GS_MIN) & (pop["ros_gs"] >= ROS_GS_MIN)]
    print(f"\nJune-6 in-season population (eval-eligible): {len(pop)} pitcher-years")

    # --- attach candidate 1: FG Stuff+ (as-of June 6) ---
    pop = attach_stuff_plus(pop, sd_map)

    # --- attach candidate 2: archetype STUFF grade, prior-year (leakage-safe) ---
    pop = attach_prior_year_feature(
        pop, str(SP_RATINGS), source_col="STUFF", new_col="arche_stuff_prior", min_gs=5
    )

    # ---------- RUN ----------
    res_fg = run_candidate(pop, "stuff_plus", "FanGraphs Stuff+ (as-of June 6)")
    collinearity(pop, "stuff_plus")

    res_arch = run_candidate(pop, "arche_stuff_prior", "Archetype STUFF grade (prior-year 20-80)")
    collinearity(pop, "arche_stuff_prior")

    # ---------- VERDICT ----------
    print("\n" + "#" * 78)
    print("VERDICT")
    print("#" * 78)
    for nm, r in [("FG Stuff+", res_fg), ("Archetype STUFF (prior-yr)", res_arch)]:
        if r["lift"] >= GATE:
            v = "PASS"
        elif r["lift"] > 0:
            v = "MARGINAL"
        else:
            v = "REJECTED"
        print(f"  {nm:<28s} lift={r['lift']:+.4f}  partial_r|baseline={r['partial']:+.4f}  "
              f"signs={r['pos']}/{r['n_yr']}  -> {v}")
    print(f"\n  (PASS bar +{GATE:.3f}; partial_r|baseline = orthogonal signal surviving full RP3_FEATS)")


if __name__ == "__main__":
    main()
