# Pre-registered: see data/research/validation_runs/stuff_asof_thin_gs_2026-07-11.md
"""Validate the stuff x thin-gs interaction as an rp3 candidate.

Family (Bonferroni 2, declared pre-run):
  M1 = stuff_asof_c * I[gs_to <= 8]         (hard mask)
  M2 = stuff_asof_c * max(0,(12-gs_to)/12)  (decay control)

stuff_asof is a leakage-safe, split-day-aligned reconstruction of the archetype
STUFF grade from the rolling substrate's own AS-OF columns. Level is NOT tested
(redundant); only the thin-gs interaction. Baseline = full 24-feature RP3_FEATS.
"""
from __future__ import annotations
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

import sys
from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report


def build_stuff_asof(df: pd.DataFrame) -> pd.DataFrame:
    """stuff_asof = within-(year, split_day) rank-pctl of 0.65*swstr + 0.35*CSW,
    centered at 0.5. Uses ONLY as-of columns -> no leakage."""
    out = df.copy()
    out["_stuff_raw"] = 0.65 * out["swstr_pct_to"] + 0.35 * out["c_plus_swstr_to"]
    out["stuff_asof"] = (
        out.groupby(["year", "split_day"])["_stuff_raw"]
        .rank(pct=True)
    )
    out["stuff_asof_c"] = out["stuff_asof"].fillna(0.5) - 0.5
    # M1 hard mask, M2 decay control
    out["stuff_asof_thin_M1"] = out["stuff_asof_c"] * (out["gs_to"] <= 8).astype(float)
    out["stuff_asof_thin_M2"] = out["stuff_asof_c"] * np.clip((12 - out["gs_to"]) / 12.0, 0, None)
    return out


def main() -> None:
    rolling = prep_rolling()
    rolling = build_stuff_asof(rolling)

    # Diagnostic: how many thin-gs rows carry the signal
    n_thin = int((rolling["gs_to"] <= 8).sum())
    print(f"substrate n={len(rolling)}  thin-gs (<=8) rows={n_thin} "
          f"({100*n_thin/len(rolling):.1f}%)")

    results = {}
    for col in ["stuff_asof_thin_M1", "stuff_asof_thin_M2"]:
        res = evaluate_candidate(rolling, col, fill_value=0.0, label=col)
        print_report(res, gate=0.005)
        results[col] = res

    # Family verdict (both must clear the gate)
    m1, m2 = results["stuff_asof_thin_M1"], results["stuff_asof_thin_M2"]
    print("\n" + "=" * 60)
    print("FAMILY VERDICT (both cells must pass, Bonferroni 2):")
    def _cell(r):
        return (r["lift"] >= 0.005 and r["sign_match_years"] >= 5
                and (r["holdout_lift"] or 0) > 0)
    print(f"  M1 pass={_cell(m1)}  lift={m1['lift']:+.4f} signs={m1['sign_match_years']}/{m1['n_total_years']} ho={m1['holdout_lift']:+.4f}")
    print(f"  M2 pass={_cell(m2)}  lift={m2['lift']:+.4f} signs={m2['sign_match_years']}/{m2['n_total_years']} ho={m2['holdout_lift']:+.4f}")
    verdict = "PASS" if (_cell(m1) and _cell(m2)) else (
        "MARGINAL" if (m1["lift"] > 0 and m2["lift"] > 0) else "REJECTED")
    print(f"  => FAMILY: {verdict}")


if __name__ == "__main__":
    main()
