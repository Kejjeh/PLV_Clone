"""validate_rp_stuff_early_masked.py — EARLY-SEASON-MASKED as-of Stuff+
variants vs production rprs2 (RP model), full split_day framing.

Pre-registered: data/research/validation_runs/rp_stuff_early_masked_2026-07-10.md
(the documented future path from the multisplit REJECT in
rp_stuff_plus_asof_multisplit_2026-07-09.md — early/mid bands were +0.0083 /
+0.0038 but the late band flipped sign and dragged the pooled lift under
the gate).

Two pre-registered cells (Bonferroni 2), both built from
centered = stuff_plus_asof - 100 (league-average neutral point):

  M1  stuff_early       = centered * I[split_day <= 100]        (hard mask)
  M2  stuff_early_decay = centered * max(0, (140-split_day)/140) (control:
      linear decay — tests whether the hard 100 cutoff was cherry-picked)

Attach logic (window -> split_day mapping, RP-filtered FG join) is copied
VERBATIM from validate_rp_stuff_plus_asof_multisplit.py per the prereg.
Imputation deviates (declared): unjoined rows get centered = 0.0 so the
imputed value is mask-invariant (w * 0 = 0 for every weight).

Elevated bar (the <=100 cutoff is a DATA-DERIVED hyperparameter, chosen
from yesterday's band table): per cell —
  (1) pooled lift >= +0.005
  (2) per-year signs >= 4/5
  (3) holdout 2024 AND 2025 BOTH individually positive
  (4) role-change subset lift >= 0
  (5) early <=60 band lift >= +0.005
  (6) late >100 band: M1 mechanical ~0 (report only); M2 >= -0.0005
Family rule: production-license PASS requires BOTH cells to pass.

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

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
FG = ROOT / "data" / "research" / "fg_asof"

FG_YEARS = [2021, 2022, 2023, 2024, 2025]
WINDOW_ENDS = ["05-01", "06-01", "06-15", "07-01", "08-01", "09-01"]
HOLDOUT = [2024, 2025]
GATE = 0.005
RAW = "stuff_plus_asof"
BANDS = [("early <=60", 0, 60), ("mid 61-100", 61, 100), ("late >100", 101, 10_000)]

CELLS = [
    # (name, late-band gate floor or None for report-only mechanical check)
    ("stuff_early", None),
    ("stuff_early_decay", -0.0005),
]


# --------------------------------------------------------------------------
# Attach logic — VERBATIM from validate_rp_stuff_plus_asof_multisplit.py
# --------------------------------------------------------------------------
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


def attach_stuff_asof(rolling: pd.DataFrame) -> pd.DataFrame:
    """Window assignment + join, verbatim multisplit flow (mapping printed)."""
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
                fg = load_fg_rp(y, mmdd).rename(columns={"stuff_plus": RAW})
                fg["year"] = y
                fg["split_day"] = int(r.split_day)
                frames.append(fg)
    mapping = pd.DataFrame(mapping_rows)
    print(mapping.to_string(index=False))

    fgall = pd.concat(frames, ignore_index=True)
    fgall = fgall.drop_duplicates(subset=["pitcher", "year", "split_day"])
    return rolling.merge(fgall, on=["pitcher", "year", "split_day"], how="left")


def main() -> int:
    rolling = pd.read_csv(ROLLING_CSV)
    rolling["pitcher"] = rolling["pitcher"].astype(int)
    rolling["cutoff_dt"] = pd.to_datetime(rolling["cutoff_date"])

    df = attach_stuff_asof(rolling)

    # ---- Step 2.5 coverage re-print (BEFORE imputation and any eval) -------
    print("\n--- Step 2.5 coverage re-print (years 2021-2025, g_to >= EVAL_G_MIN, "
          "pre-dropna population) ---")
    pop_mask = df["year"].isin(FG_YEARS) & (df["g_to"] >= EVAL_G_MIN)
    pop = df[pop_mask]
    for y in FG_YEARS:
        sub = pop[pop.year == y]
        n = len(sub)
        nj = int(sub[RAW].notna().sum())
        print(f"  {y}: rows={n:>5}  stuff+ joined={nj:>5}  join_rate={nj/max(n,1):.1%}")
    for label, lo, hi in BANDS:
        sub = pop[(pop.split_day >= lo) & (pop.split_day <= hi)]
        n = len(sub)
        nj = int(sub[RAW].notna().sum())
        print(f"  band {label:<12}: rows={n:>5}  joined={nj:>5}  join_rate={nj/max(n,1):.1%}")
    tot = len(pop); totj = int(pop[RAW].notna().sum())
    print(f"  TOTAL: rows={tot}  joined={totj}  join_rate={totj/max(tot,1):.1%}  "
          f"imputation_rate={1 - totj/max(tot,1):.1%}")

    # ---- candidate construction (pre-registered) ----------------------------
    eval_df = df[df["year"].isin(FG_YEARS)].copy()
    n_imp = int(eval_df[RAW].isna().sum())
    centered = (eval_df[RAW] - 100.0).fillna(0.0)  # neutral-point imputation
    print(f"\nCentered at 100 (league-average neutral point); "
          f"imputed {n_imp} unjoined rows with centered = 0.0 "
          f"(mask-invariant; declared deviation from the multisplit "
          f"observed-mean imputation)")

    sd = eval_df["split_day"]
    eval_df["stuff_early"] = centered * (sd <= 100).astype(float)
    eval_df["stuff_early_decay"] = centered * np.maximum(0.0, (140.0 - sd) / 140.0)

    rc_mask = role_change_mask(eval_df)

    # ---- baseline: FULL production FEATS_RPRS2 (once, shared by both cells) --
    print("\n--- BASELINE (FULL FEATS_RPRS2, 27 feats, all split_days) ---")
    py_base, overall_base, det_base = cross_year_eval(eval_df, FEATS_RPRS2)
    for y, m in sorted(py_base.items()):
        print(f"  {y}: r={m['r']:.4f}  mae={m['mae']:.2f}  n={m['n']}")
    print(f"  Overall: r={overall_base['r']}  n={overall_base['n']}")
    rc_base = _masked_overall(det_base, rc_mask)

    cell_pass = {}
    for cand, late_floor in CELLS:
        print(f"\n{'='*72}\n=== CELL: {cand} ===\n{'='*72}")
        py_full, overall_full, det_full = cross_year_eval(eval_df, FEATS_RPRS2 + [cand])
        for y, m in sorted(py_full.items()):
            print(f"  {y}: r={m['r']:.4f}  mae={m['mae']:.2f}  n={m['n']}")
        print(f"  Overall: r={overall_full['r']}  n={overall_full['n']}")

        # sample alignment (imputation means candidate NaNs remove zero rows)
        assert overall_base["n"] == overall_full["n"], (
            f"sample drift: baseline n={overall_base['n']} vs full n={overall_full['n']}")

        score = rule9_lift(py_base, py_full,
                           r_base=overall_base["r"], r_full=overall_full["r"],
                           holdout_years=tuple(HOLDOUT))

        rc_full = _masked_overall(det_full, rc_mask)
        rc_lift = (round(rc_full["r"] - rc_base["r"], 4)
                   if pd.notna(rc_full["r"]) and pd.notna(rc_base["r"]) else None)

        band_rows = []
        for label, lo, hi in BANDS:
            m = eval_df["split_day"].between(lo, hi)
            b = _masked_overall(det_base, m)
            f = _masked_overall(det_full, m)
            lift = (round(f["r"] - b["r"], 4)
                    if pd.notna(f["r"]) and pd.notna(b["r"]) else None)
            band_rows.append({"band": label, "n": b["n"],
                              "r_base": b["r"], "r_full": f["r"], "lift": lift})

        print("\n--- GATES (elevated bar) ---")
        g1 = score["lift"] >= GATE
        print(f"  (1) pooled lift:   {score['lift']:+.4f}   (gate >= +{GATE})   "
              f"{'PASS' if g1 else 'FAIL'}")
        print(f"      per-year lift: {score['per_year_lift']}")
        g2 = score["sign_match_years"] >= 4 and score["n_total_years"] == 5
        print(f"  (2) sign consistency: {score['sign_match_years']}/{score['n_total_years']}"
              f"   (gate >= 4/5)   {'PASS' if g2 else 'FAIL'}")
        ho24 = score["per_year_lift"].get(2024)
        ho25 = score["per_year_lift"].get(2025)
        g3 = ho24 is not None and ho25 is not None and ho24 > 0 and ho25 > 0
        print(f"  (3) holdout BOTH positive: 2024 {ho24:+.4f} / 2025 {ho25:+.4f}"
              f"   (gate: each > 0)   {'PASS' if g3 else 'FAIL'}"
              f"   [mean {score['holdout_lift']:+.4f}]")
        g4 = rc_lift is not None and rc_lift >= 0.0
        print(f"  (4) role-change subset (n={rc_base['n']}): "
              f"r {rc_base['r']} -> {rc_full['r']}  lift {rc_lift:+.4f}   "
              f"(gate >= 0)   {'PASS' if g4 else 'FAIL'}")
        early = band_rows[0]
        g5 = early["lift"] is not None and early["lift"] >= GATE
        print(f"  (5) early-band persistence (<=60, n={early['n']}): "
              f"lift {early['lift']:+.4f}   (gate >= +{GATE})   "
              f"{'PASS' if g5 else 'FAIL'}")
        late = band_rows[2]
        if late_floor is None:
            g6 = True
            print(f"  (6) late-band mechanical check (>100, n={late['n']}): "
                  f"lift {late['lift']:+.4f}   (report only — ~0 by construction; "
                  f"nonzero = ridge spillover through the shared fit)")
        else:
            g6 = late["lift"] is not None and late["lift"] >= late_floor
            print(f"  (6) late-band (>100, n={late['n']}): lift {late['lift']:+.4f}   "
                  f"(gate >= {late_floor})   {'PASS' if g6 else 'FAIL'}")
        print(f"      full band table:")
        for row in band_rows:
            print(f"        {row['band']:<12} n={row['n']:>6}  "
                  f"r {row['r_base']} -> {row['r_full']}  lift {row['lift']:+.4f}")

        # ---- diagnostics (context only, not gates) --------------------------
        print("\n--- DIAGNOSTICS (context only) ---")
        s = eval_df.dropna(subset=FEATS_RPRS2 + [cand, TARGET])
        s = s[s["g_to"] >= EVAL_G_MIN]
        r_raw, p_raw = pearsonr(s[cand], s[TARGET])
        print(f"  raw r({cand}, {TARGET}) = {r_raw:+.4f} (p={p_raw:.2g}, n={len(s)})")
        Z = s[FEATS_RPRS2].values
        rx = s[cand].values - LinearRegression().fit(Z, s[cand]).predict(Z)
        ry = s[TARGET].values - LinearRegression().fit(Z, s[TARGET]).predict(Z)
        r_part, p_part = pearsonr(rx, ry)
        print(f"  partial r over ALL 27 FEATS_RPRS2 = {r_part:+.4f} (p={p_part:.2g})")
        for label, lo, hi in BANDS:
            m = s["split_day"].between(lo, hi).values
            if m.sum() > 100:
                rp_, pp_ = pearsonr(rx[m], ry[m])
                print(f"    partial r {label:<12}: {rp_:+.4f} (p={pp_:.2g}, n={m.sum()})")

        ok = g1 and g2 and g3 and g4 and g5 and g6
        cell_pass[cand] = ok
        print(f"\nCELL VERDICT ({cand}): {'PASS' if ok else 'FAIL'}")

    # ---- family verdict (pre-registered anti-cherry-pick rule) --------------
    print(f"\n{'='*72}\n=== FAMILY VERDICT (Bonferroni 2; BOTH cells must pass) ===")
    m1, m2 = cell_pass["stuff_early"], cell_pass["stuff_early_decay"]
    if m1 and m2:
        fam = "PASS — robust to functional form"
    elif m1 and not m2:
        fam = ("REJECTED (SUSPECT) — only the hard mask passed; the "
               "data-derived <=100 cutoff carried the result")
    else:
        fam = "REJECTED — M1 failed"
    print(f"  M1 stuff_early:       {'PASS' if m1 else 'FAIL'}")
    print(f"  M2 stuff_early_decay: {'PASS' if m2 else 'FAIL'}")
    print(f"  FAMILY: {fam}")
    return 0 if (m1 and m2) else 1


if __name__ == "__main__":
    sys.exit(main())
