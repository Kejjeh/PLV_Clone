"""validate_era_normalization.py — pre-registered 4-cell era-normalization test.

Pre-registration: data/research/validation_runs/era_normalization_2026-07-10.md
(LOCKED before this script first ran). Cells, Bonferroni family of 4:

  E1 (rh3) league_fp_env_to    : leave-self-out PA-weighted league mean core FP/PA
                                 to-date at (year, split_day). Expected +.
  E2 (rp3) league_sp_fp_env_to : leave-self-out GS-weighted league mean FP/start
                                 to-date at (year, split_day). Expected +.
  E3 (rh3) prior_env_gap       : env_year_H(T-1, full year) - league_fp_env_to(T).
                                 Expected -.
  E4 (rp3) prior_env_gap_sp    : env_year_SP(T-1, full year) - league_sp_fp_env_to(T).
                                 Expected -.

Gates per cell: pooled lift >= +0.005 vs FULL production baseline; per-year signs
>= 5/7; holdout 2024 AND 2025 both positive; coefficient sign as declared;
split_day-band convergence non-negative in >= 3/4 bands.

Usage:
  python scripts/xfp/validate_era_normalization.py --part env   (env tables only)
  python scripts/xfp/validate_era_normalization.py --part rh3   (E1 + E3)
  python scripts/xfp/validate_era_normalization.py --part rp3   (E2 + E4)
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

HITTER_MULTIYR = ROOT / "data" / "research" / "xfp_cache" / "hitters_multiyr_2015_2026.csv"
SP_MULTIYR = ROOT / "data" / "research" / "xfp_cache" / "sp_multiyr_2015_2025.csv"

BANDS = [(0, 60), (61, 105), (106, 150), (151, 999)]
HOLDOUT = (2024, 2025)
GATE = 0.005


# ---------------------------------------------------------------- env layers
def hitter_env_year_table() -> dict[int, float]:
    """Full-year league env: PA-weighted core FP/PA over ALL batter rows."""
    hm = pd.read_csv(HITTER_MULTIYR, usecols=["year", "pa", "core_fp_total"])
    g = hm.groupby("year")
    env = (g["core_fp_total"].sum() / g["pa"].sum()).to_dict()
    return {int(k): float(v) for k, v in env.items()}


def sp_env_year_table() -> dict[int, float]:
    """Full-year league env: GS-weighted FP/start over sp_multiyr rows (gs>=1)."""
    sm = pd.read_csv(SP_MULTIYR, usecols=["year", "gs", "fp_total"])
    sm = sm[sm["gs"] >= 1]
    g = sm.groupby("year")
    env = (g["fp_total"].sum() / g["gs"].sum()).to_dict()
    return {int(k): float(v) for k, v in env.items()}


def add_hitter_env(rolling: pd.DataFrame) -> pd.DataFrame:
    """E1 league_fp_env_to (leave-self-out) + E3 prior_env_gap."""
    df = rolling.copy()
    elig = (df["pa_to"] >= 50) & df["fp_total_to"].notna() & df["pa_to"].notna()
    sub = df.loc[elig, ["year", "split_day", "fp_total_to", "pa_to"]]
    agg = (sub.groupby(["year", "split_day"])
              .agg(sum_fp=("fp_total_to", "sum"), sum_pa=("pa_to", "sum"),
                   n_elig=("pa_to", "size"))
              .reset_index())
    df = df.merge(agg, on=["year", "split_day"], how="left")
    own_fp = np.where(elig, df["fp_total_to"].fillna(0.0), 0.0)
    own_pa = np.where(elig, df["pa_to"].fillna(0.0), 0.0)
    denom = df["sum_pa"] - own_pa
    df["league_fp_env_to"] = np.where(denom > 0, (df["sum_fp"] - own_fp) / denom, np.nan)
    n_nan = int(df["league_fp_env_to"].isna().sum())
    print(f"  league_fp_env_to: NaN rows = {n_nan} / {len(df)}")
    env_year = hitter_env_year_table()
    df["prior_env_gap"] = df["year"].map(lambda y: env_year.get(int(y) - 1, np.nan)) \
        - df["league_fp_env_to"]
    df = df.drop(columns=["sum_fp", "sum_pa", "n_elig"])
    return df


def add_sp_env(rolling: pd.DataFrame) -> pd.DataFrame:
    """E2 league_sp_fp_env_to (leave-self-out, GS-weighted) + E4 prior_env_gap_sp."""
    df = rolling.copy()
    elig = (df["gs_to"] >= 2) & df["fp_per_start_to"].notna() & df["gs_to"].notna()
    sub = df.loc[elig, ["year", "split_day", "fp_per_start_to", "gs_to"]].copy()
    sub["fp_x_gs"] = sub["fp_per_start_to"] * sub["gs_to"]
    agg = (sub.groupby(["year", "split_day"])
              .agg(sum_fpgs=("fp_x_gs", "sum"), sum_gs=("gs_to", "sum"),
                   n_elig=("gs_to", "size"))
              .reset_index())
    df = df.merge(agg, on=["year", "split_day"], how="left")
    own_fpgs = np.where(elig, (df["fp_per_start_to"] * df["gs_to"]).fillna(0.0), 0.0)
    own_gs = np.where(elig, df["gs_to"].fillna(0.0), 0.0)
    denom = df["sum_gs"] - own_gs
    df["league_sp_fp_env_to"] = np.where(denom > 0, (df["sum_fpgs"] - own_fpgs) / denom,
                                         np.nan)
    n_nan = int(df["league_sp_fp_env_to"].isna().sum())
    print(f"  league_sp_fp_env_to: NaN rows = {n_nan} / {len(df)}")
    env_year = sp_env_year_table()
    df["prior_env_gap_sp"] = df["year"].map(lambda y: env_year.get(int(y) - 1, np.nan)) \
        - df["league_sp_fp_env_to"]
    df = df.drop(columns=["sum_fpgs", "sum_gs", "n_elig"])
    return df


# ---------------------------------------------------------------- reporting
def _per_year_deltas(base_py: dict, ext_py: dict) -> list[tuple[int, float]]:
    return [(y, ext_py[y]["r"] - base_py[y]["r"])
            for y in sorted(set(base_py) & set(ext_py))]


def report_cell(name: str, expected_sign: str, base_ov: dict, ext_ov: dict,
                base_py: dict, ext_py: dict, coef: float,
                band_deltas: dict[str, float]) -> dict:
    lift = ext_ov["r"] - base_ov["r"]
    deltas = _per_year_deltas(base_py, ext_py)
    pos = sum(1 for _, d in deltas if d > 0)
    ho = {y: d for y, d in deltas if y in HOLDOUT}
    ho_pass = all(v > 0 for v in ho.values()) and len(ho) == 2
    sign_ok = (expected_sign == "+" and coef > 0) or (expected_sign == "-" and coef < 0)
    bands_nonneg = sum(1 for v in band_deltas.values() if v >= 0)
    conv_pass = bands_nonneg >= 3

    print(f"\n===== CELL {name} (expected coef {expected_sign}) =====")
    print(f"  baseline r = {base_ov['r']:.4f} (n={base_ov['n']})")
    print(f"  +cand    r = {ext_ov['r']:.4f} (n={ext_ov['n']})")
    print(f"  LIFT = {lift:+.4f}   (gate >= +{GATE})")
    print("  per-year deltas:")
    for y, d in deltas:
        print(f"    {y}: {d:+.4f} {'(+)' if d > 0 else '(-)' if d < 0 else '(0)'}")
    print(f"  sign consistency: {pos}/{len(deltas)} (need >=5/7)")
    print(f"  holdout 2024={ho.get(2024, float('nan')):+.4f} "
          f"2025={ho.get(2025, float('nan')):+.4f} -> {'PASS' if ho_pass else 'FAIL'}")
    print(f"  final coef = {coef:+.6f} expected {expected_sign} -> "
          f"{'OK' if sign_ok else 'WRONG SIGN'}")
    print("  split_day-band convergence (pooled cross-year delta-r):")
    for b, v in band_deltas.items():
        print(f"    {b}: {v:+.4f}")
    print(f"  bands non-negative: {bands_nonneg}/4 (need >=3)")

    gates = {"lift": lift >= GATE, "signs": pos >= 5, "holdout": ho_pass,
             "coef": sign_ok, "convergence": conv_pass}
    if all(gates.values()):
        verdict = "PASS"
    elif gates["signs"] and gates["holdout"] and gates["coef"] and lift > 0:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"  GATES: {gates}")
    print(f"  VERDICT: {verdict}")
    return {"cell": name, "lift": round(lift, 4), "signs": f"{pos}/{len(deltas)}",
            "holdout_2024": round(ho.get(2024, np.nan), 4),
            "holdout_2025": round(ho.get(2025, np.nan), 4),
            "coef": round(coef, 6), "bands": band_deltas, "verdict": verdict,
            "base_r": base_ov["r"], "ext_r": ext_ov["r"], "per_year": deltas}


# ---------------------------------------------------------------- rh3 part
def run_rh3() -> list[dict]:
    from plv_clone.models.xfp import rh3
    from scripts.xfp._validate_rh3_v3_helper import load_and_prep_rh3_inputs, _cye

    print("=== rh3 part: E1 league_fp_env_to, E3 prior_env_gap ===")
    rolling = load_and_prep_rh3_inputs()
    rolling = add_hitter_env(rolling)
    for c in ("league_fp_env_to", "prior_env_gap"):
        print(f"  {c}: NaN={int(rolling[c].isna().sum())} "
              f"std(all rows)={float(rolling[c].std()):.5f}")
    # descriptive: env at a mid-season split per year
    mid = (rolling[rolling["split_day"] == 90]
           .groupby("year")["league_fp_env_to"].mean())
    print("  to-date env at split_day 90 by year:")
    print(mid.round(4).to_string())

    feats_base = list(rh3.RH3_FEATS)
    base_py, base_ov = _cye(rolling, feats_base)

    results = []
    cells = [("E1 rh3 league_fp_env_to", "league_fp_env_to", "+"),
             ("E3 rh3 prior_env_gap", "prior_env_gap", "-")]
    ext_out = {}
    for label, cand, sign in cells:
        ext_py, ext_ov = _cye(rolling, feats_base + [cand])
        pipe, _ = rh3.train_final(rolling, feats_base + [cand])
        coef = dict(zip(feats_base + [cand], pipe.named_steps["r"].coef_))[cand]
        ext_out[cand] = (label, sign, ext_py, ext_ov, coef)

    # convergence bands: baseline + each candidate per band
    band_deltas: dict[str, dict[str, float]] = {c: {} for _, c, _ in cells}
    for lo, hi in BANDS:
        sub = rolling[(rolling["split_day"] >= lo) & (rolling["split_day"] <= hi)]
        bname = f"sd {lo}-{hi}"
        try:
            _, bo = _cye(sub, feats_base)
            for _, cand, _s in cells:
                _, eo = _cye(sub, feats_base + [cand])
                band_deltas[cand][bname] = round(eo["r"] - bo["r"], 4)
        except Exception as e:  # pragma: no cover
            print(f"  band {bname}: eval failed - {e}")

    for _, cand, _s in cells:
        label, sign, ext_py, ext_ov, coef = ext_out[cand]
        results.append(report_cell(label, sign, base_ov, ext_ov, base_py, ext_py,
                                   coef, band_deltas[cand]))
    return results


# ---------------------------------------------------------------- rp3 part
def run_rp3() -> list[dict]:
    from plv_clone.models.xfp import rp3
    from scripts.xfp._rp3_validation_harness import prep_rolling, _cye
    from plv_clone.models.xfp.rp3 import RP3_FEATS

    print("=== rp3 part: E2 league_sp_fp_env_to, E4 prior_env_gap_sp ===")
    rolling = prep_rolling()
    rolling = add_sp_env(rolling)
    for c in ("league_sp_fp_env_to", "prior_env_gap_sp"):
        print(f"  {c}: NaN={int(rolling[c].isna().sum())} "
              f"std(all rows)={float(rolling[c].std()):.4f}")
    mid = (rolling[rolling["split_day"] == 90]
           .groupby("year")["league_sp_fp_env_to"].mean())
    print("  to-date env at split_day 90 by year:")
    print(mid.round(3).to_string())

    feats_base = list(RP3_FEATS)
    base_py, base_ov = _cye(rolling, feats_base)

    results = []
    cells = [("E2 rp3 league_sp_fp_env_to", "league_sp_fp_env_to", "+"),
             ("E4 rp3 prior_env_gap_sp", "prior_env_gap_sp", "-")]
    ext_out = {}
    for label, cand, sign in cells:
        ext_py, ext_ov = _cye(rolling, feats_base + [cand])
        pipe, _ = rp3.train_final(rolling, feats_base + [cand])
        coef = dict(zip(feats_base + [cand], pipe.named_steps["r"].coef_))[cand]
        ext_out[cand] = (label, sign, ext_py, ext_ov, coef)

    band_deltas: dict[str, dict[str, float]] = {c: {} for _, c, _ in cells}
    for lo, hi in BANDS:
        sub = rolling[(rolling["split_day"] >= lo) & (rolling["split_day"] <= hi)]
        bname = f"sd {lo}-{hi}"
        try:
            _, bo = _cye(sub, feats_base)
            for _, cand, _s in cells:
                _, eo = _cye(sub, feats_base + [cand])
                band_deltas[cand][bname] = round(eo["r"] - bo["r"], 4)
        except Exception as e:  # pragma: no cover
            print(f"  band {bname}: eval failed - {e}")

    for _, cand, _s in cells:
        label, sign, ext_py, ext_ov, coef = ext_out[cand]
        results.append(report_cell(label, sign, base_ov, ext_ov, base_py, ext_py,
                                   coef, band_deltas[cand]))
    return results


def print_env_tables() -> None:
    print("League env by FULL year (hitter: PA-weighted core FP/PA; SP: GS-weighted FP/start):")
    eh = hitter_env_year_table()
    es = sp_env_year_table()
    print(f"  {'year':<6}{'hitter_core_fp_per_pa':<24}{'sp_fp_per_start':<16}")
    for y in sorted(set(eh) | set(es)):
        print(f"  {y:<6}{eh.get(y, float('nan')):<24.4f}{es.get(y, float('nan')):<16.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["env", "rh3", "rp3"], required=True)
    args = ap.parse_args()
    print_env_tables()
    if args.part == "env":
        return
    results = run_rh3() if args.part == "rh3" else run_rp3()
    print("\n########## FINAL SUMMARY ##########")
    for r in results:
        print(f"{r['cell']}: lift={r['lift']:+.4f} signs={r['signs']} "
              f"ho24={r['holdout_2024']:+.4f} ho25={r['holdout_2025']:+.4f} "
              f"coef={r['coef']:+.6f} bands={r['bands']} -> {r['verdict']}")


if __name__ == "__main__":
    main()
