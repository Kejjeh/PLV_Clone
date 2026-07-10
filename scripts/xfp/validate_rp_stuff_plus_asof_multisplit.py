"""validate_rp_stuff_plus_asof_multisplit.py — MULTI-SPLIT Rule-9 integration
test of as-of FanGraphs Stuff+ vs production rprs2 (RP model), at the FULL
split_day range (the actual production framing of FEATS_RPRS2).

Pre-registered: data/research/validation_runs/
rp_stuff_plus_asof_multisplit_2026-07-09.md
(confirmatory follow-up to the single-split PASS in
rp_stuff_plus_asof_2026-07-09.md — its deployment caveat #1.)

Design (locked in the prereg):
  - candidate `stuff_plus_asof` = FG Stuff+ over {Y}-03-01 .. window_end,
    where window_end is the LATEST of {05-01, 06-01, 06-15, 07-01, 08-01,
    09-01} with window_end <= the row's cutoff_date (nearest-without-leakage).
    FG rows RP-filtered within the window (gs == 0 OR gs/g < 0.4).
  - unjoined rows (early-April cutoffs + missing-from-window pitchers) are
    mean-imputed with the global mean of OBSERVED values, so baseline and
    candidate score the IDENTICAL population (asserted).
  - population: ALL split_days, years 2021-2025, g_to >= EVAL_G_MIN and
    dropna(27 feats + target) inside the production cross_year_eval.
  - baseline  = FEATS_RPRS2 (27 production features) via rprs2.cross_year_eval
  - candidate = FEATS_RPRS2 + ['stuff_plus_asof']
  - gates: (1) pooled lift >= +0.005; (2) per-year sign 5/5;
           (3) holdout (2024,2025) lift > 0;
           (4) role-change subset lift >= 0;
           (5) Rule-8 split-band convergence — lift within bands
               early <=60 / mid 61-100 / late >100 must have NO negative
               band (4dp), regardless of the pooled number.

DO NOT commit model changes. This script only ADDs a research read.
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
from lib.rule9 import rule9_lift  # noqa: E402

from plv_clone.models.xfp.rprs2 import (  # noqa: E402
    FEATS_RPRS2, cross_year_eval, role_change_mask, _masked_overall,
    ROLLING_CSV, TARGET, EVAL_G_MIN,
)

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"

FG_YEARS = [2021, 2022, 2023, 2024, 2025]
WINDOW_ENDS = ["05-01", "06-01", "06-15", "07-01", "08-01", "09-01"]
HOLDOUT = [2024, 2025]
GATE = 0.005
CAND = "stuff_plus_asof"
BANDS = [("early <=60", 0, 60), ("mid 61-100", 61, 100), ("late >100", 101, 10_000)]


def load_fg_rp(year: int, mmdd: str) -> pd.DataFrame:
    """One as-of FG window pull, restricted to relievers within the window
    (gs == 0 OR gs/g < 0.4), per the prereg (same filter as the 0615 run)."""
    fg = pd.read_csv(FG / f"fg_pit_asof_{year}_{mmdd}.csv")
    fg = fg.rename(columns={"mlb_id": "pitcher"})
    fg = fg.dropna(subset=["pitcher"]).copy()
    fg["pitcher"] = fg["pitcher"].astype(int)
    g = pd.to_numeric(fg["g"], errors="coerce")
    gs = pd.to_numeric(fg["gs"], errors="coerce").fillna(0)
    is_rp = (gs == 0) | ((gs / g.replace(0, np.nan)) < 0.4)
    out = fg[is_rp.fillna(False)][["pitcher", "stuff_plus"]].copy()
    out["stuff_plus"] = pd.to_numeric(out["stuff_plus"], errors="coerce")
    return out.dropna(subset=["stuff_plus"]).drop_duplicates(subset=["pitcher"])


def main() -> int:
    rolling = pd.read_csv(ROLLING_CSV)
    rolling["pitcher"] = rolling["pitcher"].astype(int)
    rolling["cutoff_dt"] = pd.to_datetime(rolling["cutoff_date"])

    # ---- window assignment: latest window_end <= cutoff_date ---------------
    print("--- Window -> split_day mapping (nearest-without-leakage) ---")
    frames = []
    mapping_rows = []
    for y in FG_YEARS:
        ends = [pd.Timestamp(f"{y}-{e}") for e in WINDOW_ENDS]
        year_splits = (rolling[rolling.year == y][["split_day", "cutoff_dt"]]
                       .drop_duplicates().sort_values("split_day"))
        for _, r in year_splits.iterrows():
            eligible = [e for e in ends if e <= r.cutoff_dt]
            win = max(eligible) if eligible else None
            mapping_rows.append({
                "year": y, "split_day": int(r.split_day),
                "cutoff_date": r.cutoff_dt.date().isoformat(),
                "window_end": win.date().isoformat() if win is not None else "IMPUTED",
                "staleness_days": (r.cutoff_dt - win).days if win is not None else None,
            })
            if win is not None:
                mmdd = win.strftime("%m%d")
                fg = load_fg_rp(y, mmdd).rename(columns={"stuff_plus": CAND})
                fg["year"] = y
                fg["split_day"] = int(r.split_day)
                frames.append(fg)
    mapping = pd.DataFrame(mapping_rows)
    print(mapping.to_string(index=False))

    fgall = pd.concat(frames, ignore_index=True)
    fgall = fgall.drop_duplicates(subset=["pitcher", "year", "split_day"])

    df = rolling.merge(fgall, on=["pitcher", "year", "split_day"], how="left")

    # ---- Step 2.5 coverage (BEFORE imputation and any eval) ----------------
    print("\n--- Step 2.5 coverage (years 2021-2025, g_to >= EVAL_G_MIN, "
          "pre-dropna population) ---")
    pop_mask = df["year"].isin(FG_YEARS) & (df["g_to"] >= EVAL_G_MIN)
    pop = df[pop_mask]
    for y in FG_YEARS:
        sub = pop[pop.year == y]
        n = len(sub)
        nj = int(sub[CAND].notna().sum())
        print(f"  {y}: rows={n:>5}  stuff+ joined={nj:>5}  join_rate={nj/max(n,1):.1%}")
    for label, lo, hi in BANDS:
        sub = pop[(pop.split_day >= lo) & (pop.split_day <= hi)]
        n = len(sub)
        nj = int(sub[CAND].notna().sum())
        print(f"  band {label:<12}: rows={n:>5}  joined={nj:>5}  join_rate={nj/max(n,1):.1%}")
    tot = len(pop); totj = int(pop[CAND].notna().sum())
    print(f"  TOTAL: rows={tot}  joined={totj}  join_rate={totj/max(tot,1):.1%}  "
          f"imputation_rate={1 - totj/max(tot,1):.1%}")

    # ---- imputation (global mean of observed values) ------------------------
    eval_df = df[df["year"].isin(FG_YEARS)].copy()
    obs_mean = float(eval_df[CAND].mean())
    n_imp = int(eval_df[CAND].isna().sum())
    eval_df[CAND] = eval_df[CAND].fillna(obs_mean)
    print(f"\nImputed {n_imp} rows with observed mean {obs_mean:.2f}")

    rc_mask = role_change_mask(eval_df)

    # ---- baseline: FULL production FEATS_RPRS2 ------------------------------
    print("\n--- BASELINE (FULL FEATS_RPRS2, 27 feats, all split_days) ---")
    py_base, overall_base, det_base = cross_year_eval(eval_df, FEATS_RPRS2)
    for y, m in sorted(py_base.items()):
        print(f"  {y}: r={m['r']:.4f}  mae={m['mae']:.2f}  n={m['n']}")
    print(f"  Overall: r={overall_base['r']}  n={overall_base['n']}")

    # ---- candidate: + stuff_plus_asof ---------------------------------------
    print(f"\n--- CANDIDATE (FEATS_RPRS2 + {CAND}) ---")
    py_full, overall_full, det_full = cross_year_eval(eval_df, FEATS_RPRS2 + [CAND])
    for y, m in sorted(py_full.items()):
        print(f"  {y}: r={m['r']:.4f}  mae={m['mae']:.2f}  n={m['n']}")
    print(f"  Overall: r={overall_full['r']}  n={overall_full['n']}")

    # sample alignment (imputation means candidate NaNs remove zero rows)
    assert overall_base["n"] == overall_full["n"], (
        f"sample drift: baseline n={overall_base['n']} vs full n={overall_full['n']}")

    # ---- gates 1-3: Rule-9 scoring ------------------------------------------
    score = rule9_lift(py_base, py_full,
                       r_base=overall_base["r"], r_full=overall_full["r"],
                       holdout_years=tuple(HOLDOUT))

    # ---- gate 4: role-change subset (same fits, masked) ----------------------
    rc_base = _masked_overall(det_base, rc_mask)
    rc_full = _masked_overall(det_full, rc_mask)
    rc_lift = (round(rc_full["r"] - rc_base["r"], 4)
               if pd.notna(rc_full["r"]) and pd.notna(rc_base["r"]) else None)

    # ---- gate 5: Rule-8 split-band convergence (same fits, masked) ------------
    band_rows = []
    for label, lo, hi in BANDS:
        m = eval_df["split_day"].between(lo, hi)
        b = _masked_overall(det_base, m)
        f = _masked_overall(det_full, m)
        lift = (round(f["r"] - b["r"], 4)
                if pd.notna(f["r"]) and pd.notna(b["r"]) else None)
        band_rows.append({"band": label, "n": b["n"],
                          "r_base": b["r"], "r_full": f["r"], "lift": lift})

    print("\n--- GATES ---")
    g1 = score["lift"] >= GATE
    print(f"  (1) pooled lift:   {score['lift']:+.4f}   (gate >= +{GATE})   "
          f"{'PASS' if g1 else 'FAIL'}")
    print(f"      per-year lift: {score['per_year_lift']}")
    g2 = score["sign_match_years"] == score["n_total_years"] == 5
    print(f"  (2) sign consistency: {score['sign_match_years']}/{score['n_total_years']}"
          f"   (gate 5/5, zero slack)   {'PASS' if g2 else 'FAIL'}")
    hl = score["holdout_lift"]
    g3 = hl is not None and hl > 0
    print(f"  (3) holdout (2024+2025) lift: {hl:+.4f}   (gate > 0)   "
          f"{'PASS' if g3 else 'FAIL'}")
    g4 = rc_lift is not None and rc_lift >= 0.0
    print(f"  (4) role-change subset (n={rc_base['n']}): "
          f"r {rc_base['r']} -> {rc_full['r']}  lift {rc_lift:+.4f}   "
          f"(gate >= 0)   {'PASS' if g4 else 'FAIL'}")
    print(f"  (5) Rule-8 split-band convergence (gate: no negative band):")
    g5 = True
    for row in band_rows:
        ok = row["lift"] is not None and row["lift"] >= 0.0
        g5 = g5 and ok
        print(f"      {row['band']:<12} n={row['n']:>6}  "
              f"r {row['r_base']} -> {row['r_full']}  lift {row['lift']:+.4f}  "
              f"{'ok' if ok else 'SIGN FLIP'}")
    print(f"      convergence: {'PASS' if g5 else 'FAIL'}")

    # ---- diagnostics (context only, not gates) --------------------------------
    print("\n--- DIAGNOSTICS (context only) ---")
    s = eval_df.dropna(subset=FEATS_RPRS2 + [CAND, TARGET])
    s = s[s["g_to"] >= EVAL_G_MIN]
    r_raw, p_raw = pearsonr(s[CAND], s[TARGET])
    print(f"  raw r({CAND}, {TARGET}) = {r_raw:+.4f} (p={p_raw:.2g}, n={len(s)})")
    Z = s[FEATS_RPRS2].values
    rx = s[CAND].values - LinearRegression().fit(Z, s[CAND]).predict(Z)
    ry = s[TARGET].values - LinearRegression().fit(Z, s[TARGET]).predict(Z)
    r_part, p_part = pearsonr(rx, ry)
    print(f"  partial r over ALL 27 FEATS_RPRS2 = {r_part:+.4f} (p={p_part:.2g})")
    # per-band partial r (does the signal's information vary by season stage?)
    for label, lo, hi in BANDS:
        m = s["split_day"].between(lo, hi).values
        if m.sum() > 100:
            rp_, pp_ = pearsonr(rx[m], ry[m])
            print(f"    partial r {label:<12}: {rp_:+.4f} (p={pp_:.2g}, n={m.sum()})")

    ok = g1 and g2 and g3 and g4 and g5
    print(f"\nVERDICT: {'PASS' if ok else 'REJECTED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
