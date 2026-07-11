"""validate_rp3_stuff_plus_asof_multisplit.py — Rule-9 integration test of
as-of FanGraphs Stuff+ (SP main effect) vs production rp3, at the FULL
split_day range (the actual production framing of RP3_FEATS).

Pre-registered: data/research/validation_runs/
rp3_stuff_plus_asof_multisplit_2026-07-11.md
(the ONE untested cell in the Stuff+ family; adjudicates the June-6
single-split +0.0095 anomaly; family closes on rejection).

Design (locked in the prereg):
  - candidate `stuff_plus_asof_c` = (FG Stuff+ over {Y}-03-01 .. window_end)
    - 100, window_end = LATEST of {05-01, 06-01, 06-15, 07-01, 08-01, 09-01}
    with window_end <= the row's cutoff_date (nearest-without-leakage).
    Attach logic mirrored from validate_rp_stuff_plus_asof_multisplit.py with
    the role filter flipped to STARTERS (gs >= 1 AND gs/g >= 0.4).
  - unjoined rows (early-April cutoffs, missing-from-window pitchers, ALL of
    2018/2019) -> centered = 0.0 (mask-invariant scale-neutral imputation per
    rp_stuff_early_masked_2026-07-10), so baseline and candidate score the
    IDENTICAL population (asserted).
  - baseline  = RP3_FEATS (24 production features) via rp3.cross_year_eval
    on the _rp3_validation_harness.prep_rolling() substrate
  - candidate = RP3_FEATS + ['stuff_plus_asof_c']
  - gates: (1) pooled lift >= +0.005; (2) per-year sign >= 5/7;
           (3) holdout (2024,2025) avg lift > 0;
           (4) Rule-8 split-band convergence — no negative band (4dp) across
               early <=60 / mid 61-100 / late >100;
           (5) full-data linear-probe coef on the candidate > 0.

DO NOT commit model changes from this script. Research read only.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling  # noqa: E402
from lib.rule9 import rule9_lift  # noqa: E402

from plv_clone.models.xfp.rp3 import (  # noqa: E402
    RP3_FEATS, cross_year_eval, TRAIN_YEARS,
)
from plv_clone.paths import ROOT  # noqa: E402

FG = ROOT / "data" / "research" / "fg_asof"

FG_YEARS = [2021, 2022, 2023, 2024, 2025]
WINDOW_ENDS = ["05-01", "06-01", "06-15", "07-01", "08-01", "09-01"]
HOLDOUT = (2024, 2025)
GATE = 0.005
CAND = "stuff_plus_asof_c"
BANDS = [("early <=60", 0, 60), ("mid 61-100", 61, 100), ("late >100", 101, 10_000)]


def load_fg_sp(year: int, mmdd: str) -> pd.DataFrame:
    """One as-of FG window pull, restricted to STARTERS within the window
    (gs >= 1 AND gs/g >= 0.4 — mirrors detect_pitcher_role's 0.4 rule)."""
    fg = pd.read_csv(FG / f"fg_pit_asof_{year}_{mmdd}.csv")
    fg = fg.rename(columns={"mlb_id": "pitcher"})
    fg = fg.dropna(subset=["pitcher"]).copy()
    fg["pitcher"] = fg["pitcher"].astype(int)
    g = pd.to_numeric(fg["g"], errors="coerce")
    gs = pd.to_numeric(fg["gs"], errors="coerce").fillna(0)
    is_sp = (gs >= 1) & ((gs / g.replace(0, np.nan)) >= 0.4)
    out = fg[is_sp.fillna(False)][["pitcher", "stuff_plus"]].copy()
    out["stuff_plus"] = pd.to_numeric(out["stuff_plus"], errors="coerce")
    return out.dropna(subset=["stuff_plus"]).drop_duplicates(subset=["pitcher"])


def _band_r(detail: pd.DataFrame, lo: int, hi: int) -> tuple[float, int]:
    m = detail["split_day"].between(lo, hi)
    sub = detail[m]
    if len(sub) < 10:
        return float("nan"), int(len(sub))
    return float(np.corrcoef(sub["pred"], sub["actual"])[0, 1]), int(len(sub))


def main() -> int:
    rolling = prep_rolling()
    rolling["pitcher"] = rolling["pitcher"].astype(int)
    rolling["cutoff_dt"] = pd.to_datetime(rolling["cutoff_date"])

    # ---- window assignment: latest window_end <= cutoff_date ---------------
    print("--- Window -> split_day mapping (nearest-without-leakage) ---")
    frames = []
    for y in FG_YEARS:
        ends = [pd.Timestamp(f"{y}-{e}") for e in WINDOW_ENDS]
        year_splits = (rolling[rolling.year == y][["split_day", "cutoff_dt"]]
                       .drop_duplicates().sort_values("split_day"))
        n_imputed = 0
        for _, r in year_splits.iterrows():
            eligible = [e for e in ends if e <= r.cutoff_dt]
            if not eligible:
                n_imputed += 1
                continue
            win = max(eligible)
            fg = load_fg_sp(y, win.strftime("%m%d")).rename(
                columns={"stuff_plus": CAND})
            fg["year"] = y
            fg["split_day"] = int(r.split_day)
            frames.append(fg)
        print(f"  {y}: {len(year_splits)} splits, {n_imputed} pre-window (imputed)")

    fgall = pd.concat(frames, ignore_index=True)
    fgall = fgall.drop_duplicates(subset=["pitcher", "year", "split_day"])

    df = rolling.merge(fgall, on=["pitcher", "year", "split_day"], how="left")

    # ---- Step 2.5 coverage (BEFORE imputation and any eval) ----------------
    print("\n--- Step 2.5 coverage (pre-imputation, pre-dropna) ---")
    for y in sorted(TRAIN_YEARS):
        sub = df[df.year == y]
        nj = int(sub[CAND].notna().sum())
        print(f"  {y}: rows={len(sub):>6}  stuff+ joined={nj:>6}  "
              f"join_rate={nj / max(len(sub), 1):.1%}")

    # ---- centering + mask-invariant imputation ------------------------------
    df[CAND] = df[CAND] - 100.0          # scale-defined neutral point
    n_imp = int(df[CAND].isna().sum())
    df[CAND] = df[CAND].fillna(0.0)
    print(f"\nCentered at 100; imputed {n_imp} rows to 0.0 (mask-invariant)")

    # ---- baseline: FULL production RP3_FEATS --------------------------------
    print(f"\n--- BASELINE (RP3_FEATS, {len(RP3_FEATS)} feats) ---")
    py_base, ov_base, det_base = cross_year_eval(df, RP3_FEATS)
    for y, m in sorted(py_base.items()):
        print(f"  {y}: r={m['r']:.4f}  n={m['n']}")
    print(f"  Overall: r={ov_base['r']}  n={ov_base['n']}")

    # ---- candidate -----------------------------------------------------------
    print(f"\n--- CANDIDATE (+ {CAND}) ---")
    py_full, ov_full, det_full = cross_year_eval(df, RP3_FEATS + [CAND])
    for y, m in sorted(py_full.items()):
        print(f"  {y}: r={m['r']:.4f}  n={m['n']}")
    print(f"  Overall: r={ov_full['r']}  n={ov_full['n']}")

    assert ov_base["n"] == ov_full["n"], (
        f"sample drift: baseline n={ov_base['n']} vs full n={ov_full['n']}")

    # ---- gates 1-3 -----------------------------------------------------------
    score = rule9_lift(py_base, py_full, r_base=ov_base["r"],
                       r_full=ov_full["r"], holdout_years=HOLDOUT)

    # ---- gate 4: Rule-8 split-band convergence -------------------------------
    band_rows = []
    for label, lo, hi in BANDS:
        rb, nb = _band_r(det_base, lo, hi)
        rf, nf = _band_r(det_full, lo, hi)
        lift = round(rf - rb, 4) if np.isfinite(rb) and np.isfinite(rf) else None
        band_rows.append({"band": label, "n": nb, "r_base": round(rb, 4),
                          "r_full": round(rf, 4), "lift": lift})

    # ---- gate 5: full-data linear-probe coef sign ----------------------------
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    fit_df = df.dropna(subset=RP3_FEATS + [CAND, "ros_fp_per_start"])
    fit_df = fit_df[(fit_df["year"] != 2020)]
    X = StandardScaler().fit_transform(fit_df[RP3_FEATS + [CAND]].values)
    lr = LinearRegression().fit(X, fit_df["ros_fp_per_start"].values)
    cand_coef = float(lr.coef_[-1])

    # ---- verdict --------------------------------------------------------------
    print("\n--- GATES ---")
    g1 = score["lift"] >= GATE
    print(f"  (1) pooled lift:      {score['lift']:+.4f}  (gate >= +{GATE})  "
          f"{'PASS' if g1 else 'FAIL'}")
    print(f"      per-year lift:    {score['per_year_lift']}")
    g2 = score["sign_match_years"] >= 5
    print(f"  (2) sign consistency: {score['sign_match_years']}/"
          f"{score['n_total_years']}  (gate >= 5/7)  {'PASS' if g2 else 'FAIL'}")
    g3 = (score["holdout_lift"] or 0) > 0
    print(f"  (3) holdout lift:     {score['holdout_lift']:+.4f}  (gate > 0)  "
          f"{'PASS' if g3 else 'FAIL'}")
    neg_bands = [b for b in band_rows if b["lift"] is not None and b["lift"] < 0]
    g4 = not neg_bands
    print(f"  (4) band convergence: {'PASS' if g4 else 'FAIL'}")
    for b in band_rows:
        print(f"      {b['band']:<12} n={b['n']:>6}  r_base={b['r_base']}  "
              f"r_full={b['r_full']}  lift={b['lift']}")
    g5 = cand_coef > 0
    print(f"  (5) probe coef:       {cand_coef:+.5f}  (gate > 0)  "
          f"{'PASS' if g5 else 'FAIL'}")

    verdict = "PASS" if all([g1, g2, g3, g4, g5]) else "REJECTED"
    print(f"\n=== VERDICT: {verdict} ===")
    if verdict == "REJECTED":
        print("Per the pre-registration: the Stuff+-into-rate-models family "
              "(rp3 AND rprs2, all variants) is CLOSED until 2027 rollover.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
