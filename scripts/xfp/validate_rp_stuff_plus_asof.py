"""validate_rp_stuff_plus_asof.py — Rule-9 INTEGRATION test of as-of FanGraphs
Stuff+ vs production rprs2 (RP model).

Pre-registered: data/research/validation_runs/rp_stuff_plus_asof_2026-07-09.md

Question: does adding the as-of (season-start .. ~June-15) FG Stuff+ to the FULL
production FEATS_RPRS2 list improve the fp_year_total projection for relievers,
or is its signal already captured?

Design (locked in the prereg):
  - population: rolling_relievers rows at the June-15-aligned split_day per
    year, years 2021-2025 (Stuff+ exists 2021+; 2019 has none; 2020 excluded),
    g_to >= 5, stuff_plus_asof non-null (SAME rows for baseline + candidate).
  - baseline  = FEATS_RPRS2 (27 production features) via rprs2.cross_year_eval
  - candidate = FEATS_RPRS2 + ['stuff_plus_asof']
  - gates: lift >= +0.005, per-year sign 5/5, holdout (2024,2025) lift > 0.

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
    FEATS_RPRS2, cross_year_eval, ROLLING_CSV, TARGET, EVAL_G_MIN,
)

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"

FG_YEARS = [2021, 2022, 2023, 2024, 2025]
HOLDOUT = [2024, 2025]
GATE = 0.005
CAND = "stuff_plus_asof"


def june15_split_day(rolling: pd.DataFrame) -> dict[int, int]:
    """Per FG year, the split_day whose cutoff_date is nearest June 15."""
    out = {}
    sub = rolling[["year", "split_day", "cutoff_date"]].drop_duplicates().copy()
    sub["cutoff_date"] = pd.to_datetime(sub["cutoff_date"])
    for y in FG_YEARS:
        s = sub[sub.year == y].copy()
        if s.empty:
            continue
        s["d"] = (s["cutoff_date"] - pd.Timestamp(f"{y}-06-15")).abs()
        out[y] = int(s.nsmallest(1, "d").split_day.iloc[0])
    return out


def load_fg_rp(year: int) -> pd.DataFrame:
    """As-of-June-15 FG pull, restricted to relievers within the window
    (gs == 0 OR gs/g < 0.4), per the prereg."""
    fg = pd.read_csv(FG / f"fg_pit_asof_{year}_0615.csv")
    fg = fg.rename(columns={"mlb_id": "pitcher"})
    fg = fg.dropna(subset=["pitcher"]).copy()
    fg["pitcher"] = fg["pitcher"].astype(int)
    g = pd.to_numeric(fg["g"], errors="coerce")
    gs = pd.to_numeric(fg["gs"], errors="coerce").fillna(0)
    is_rp = (gs == 0) | ((gs / g.replace(0, np.nan)) < 0.4)
    return fg[is_rp.fillna(False)][
        ["pitcher", "stuff_plus", "location_plus", "pitching_plus"]
    ].copy()


def main() -> int:
    rolling = pd.read_csv(ROLLING_CSV)
    sd_map = june15_split_day(rolling)
    print("June-15-aligned split_days:", sd_map)

    # ---- attach candidate -------------------------------------------------
    frames = []
    for y, sd in sd_map.items():
        fg = load_fg_rp(y)
        fg = fg.rename(columns={"stuff_plus": CAND,
                                "location_plus": "location_plus_asof",
                                "pitching_plus": "pitching_plus_asof"})
        fg["year"] = y
        fg["split_day"] = sd
        frames.append(fg)
    fgall = pd.concat(frames, ignore_index=True)
    fgall = fgall.drop_duplicates(subset=["pitcher", "year", "split_day"])

    df = rolling.copy()
    df["pitcher"] = df["pitcher"].astype(int)
    df = df.merge(fgall, on=["pitcher", "year", "split_day"], how="left")

    # ---- Step 2.5 coverage (before any eval) ------------------------------
    print("\n--- Step 2.5 coverage (June-15 split rows, g_to >= EVAL_G_MIN) ---")
    pop_mask = (
        df["year"].isin(FG_YEARS)
        & df.apply(lambda r: sd_map.get(r["year"]) == r["split_day"], axis=1)
        & (df["g_to"] >= EVAL_G_MIN)
    )
    pop = df[pop_mask].copy()
    for y in FG_YEARS:
        sub = pop[pop.year == y]
        n = len(sub)
        nj = int(sub[CAND].notna().sum())
        nfg = len(fgall[fgall.year == y])
        print(f"  {y} sd={sd_map[y]:>3}: substrate={n:>4}  fg_rp_rows={nfg:>4}  "
              f"stuff+ joined={nj:>4}  join_rate={nj/max(n,1):.1%}")

    # ---- identical-population filter --------------------------------------
    # cross_year_eval dropna's internally over feats+target; pre-drop candidate
    # NaN so baseline and candidate score the SAME rows.
    need = FEATS_RPRS2 + [CAND, TARGET]
    pop = pop.dropna(subset=[c for c in need if c in pop.columns])
    print(f"\nEval population after dropna(feats + {CAND} + target): {len(pop)} rows")
    print(pop.groupby("year").size().to_string())

    # ---- baseline: FULL production FEATS_RPRS2 ----------------------------
    print("\n--- BASELINE (FULL FEATS_RPRS2, 27 feats) ---")
    py_base, overall_base, _ = cross_year_eval(pop, FEATS_RPRS2)
    for y, m in sorted(py_base.items()):
        print(f"  {y}: r={m['r']:.4f}  mae={m['mae']:.2f}  n={m['n']}")
    print(f"  Overall: r={overall_base['r']}  n={overall_base['n']}")

    # ---- candidate: + stuff_plus_asof --------------------------------------
    print(f"\n--- CANDIDATE (FEATS_RPRS2 + {CAND}) ---")
    py_full, overall_full, _ = cross_year_eval(pop, FEATS_RPRS2 + [CAND])
    for y, m in sorted(py_full.items()):
        print(f"  {y}: r={m['r']:.4f}  mae={m['mae']:.2f}  n={m['n']}")
    print(f"  Overall: r={overall_full['r']}  n={overall_full['n']}")

    # ---- Rule-9 scoring -----------------------------------------------------
    score = rule9_lift(py_base, py_full,
                       r_base=overall_base["r"], r_full=overall_full["r"],
                       holdout_years=tuple(HOLDOUT))
    print("\n--- RULE-9 GATES ---")
    print(f"  lift:            {score['lift']:+.4f}   (gate >= +{GATE})   "
          f"{'PASS' if score['lift'] >= GATE else 'FAIL'}")
    print(f"  per-year lift:   {score['per_year_lift']}")
    print(f"  sign consistency: {score['sign_match_years']}/{score['n_total_years']}"
          f"   (gate 5/5)   "
          f"{'PASS' if score['sign_match_years'] == score['n_total_years'] == 5 else 'FAIL'}")
    hl = score["holdout_lift"]
    print(f"  holdout (2024+2025) lift: {hl:+.4f}   (gate > 0)   "
          f"{'PASS' if hl is not None and hl > 0 else 'FAIL'}")

    # ---- diagnostics (context only, not gates) -----------------------------
    print("\n--- DIAGNOSTICS (context only) ---")
    s = pop[[CAND, TARGET] + FEATS_RPRS2].dropna()
    r_raw, p_raw = pearsonr(s[CAND], s[TARGET])
    print(f"  raw r({CAND}, {TARGET}) = {r_raw:+.4f} (p={p_raw:.2g}, n={len(s)})")
    Z = s[FEATS_RPRS2].values
    rx = s[CAND].values - LinearRegression().fit(Z, s[CAND]).predict(Z)
    ry = s[TARGET].values - LinearRegression().fit(Z, s[TARGET]).predict(Z)
    r_part, p_part = pearsonr(rx, ry)
    print(f"  partial r over ALL 27 FEATS_RPRS2 = {r_part:+.4f} (p={p_part:.2g})")
    # top collinearity
    cors = {f: abs(pearsonr(s[CAND], s[f])[0]) for f in FEATS_RPRS2
            if s[f].std() > 0}
    top = sorted(cors.items(), key=lambda kv: -kv[1])[:6]
    print("  top |corr| vs production feats:",
          ", ".join(f"{f}={v:.2f}" for f, v in top))

    ok = (score["lift"] >= GATE
          and score["sign_match_years"] == score["n_total_years"] == 5
          and hl is not None and hl > 0)
    print(f"\nVERDICT: {'PASS' if ok else 'REJECTED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
