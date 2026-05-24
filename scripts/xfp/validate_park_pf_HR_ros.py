"""Validation script for `park_pf_HR_ros` as a rp3 v3 candidate feature.

Pre-registered: data/research/validation_runs/park_pf_HR_ros_2026-05-24.md.

Hypothesis: A pitcher's home-park HR factor (v1 proxy for RoS park
exposure) adds independent predictive lift on RoS FP/start over the
full RP3_FEATS baseline, with negative coefficient.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_park_pf_HR_ros.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report  # noqa: E402
from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval, train_final  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
PARK_CSV = CACHE / "park_factors_2018_2026.csv"
TEAM_CACHE = CACHE / "pitcher_primary_team_2018_2026.csv"

YEARS = list(range(2018, 2027))


def build_pitcher_team_cache() -> pd.DataFrame:
    """For each (pitcher, year), derive modal team while pitching from statcast.
    Cached to TEAM_CACHE so the parquet scan only runs once.
    """
    if TEAM_CACHE.exists():
        return pd.read_csv(TEAM_CACHE)
    rows = []
    for yr in YEARS:
        path = CACHE / f"statcast_{yr}.parquet"
        if not path.exists():
            continue
        sc = pd.read_parquet(path, columns=["pitcher", "home_team", "away_team", "inning_topbot"])
        sc = sc.dropna(subset=["pitcher"])
        sc["pitcher_team"] = np.where(sc["inning_topbot"] == "Top",
                                      sc["home_team"], sc["away_team"])
        top = sc.groupby("pitcher")["pitcher_team"].agg(
            lambda s: s.mode().iat[0] if len(s.mode()) else None
        ).reset_index()
        top["year"] = yr
        rows.append(top)
        print(f"  [{yr}] {len(top)} pitcher-team rows")
    out = pd.concat(rows, ignore_index=True)[["pitcher", "year", "pitcher_team"]]
    out.to_csv(TEAM_CACHE, index=False)
    print(f"  wrote {TEAM_CACHE}: {len(out)} rows")
    return out


def attach_park_pf(rolling: pd.DataFrame) -> pd.DataFrame:
    pf = pd.read_csv(PARK_CSV)[["year", "team_abbr", "pf_HR"]]
    team = build_pitcher_team_cache().rename(columns={"pitcher_team": "team_abbr"})
    merged = rolling.merge(team, on=["pitcher", "year"], how="left")
    merged = merged.merge(pf, on=["year", "team_abbr"], how="left")
    merged = merged.rename(columns={"pf_HR": "park_pf_HR_ros"})
    n_missing = merged["park_pf_HR_ros"].isna().sum()
    print(f"  park_pf_HR_ros missing after join: {n_missing} / {len(merged)} "
          f"({n_missing / max(len(merged), 1):.1%}) — filled with 1.00")
    merged["park_pf_HR_ros"] = merged["park_pf_HR_ros"].fillna(1.00)
    return merged


def main() -> None:
    print("=== /validate-feature: park_pf_HR_ros (rp3 v3 candidate) ===")
    print("Pre-reg: data/research/validation_runs/park_pf_HR_ros_2026-05-24.md")
    print()
    rolling = prep_rolling()
    rolling = attach_park_pf(rolling)

    result = evaluate_candidate(rolling, "park_pf_HR_ros", fill_value=1.00)
    print_report(result, gate=0.005)

    # Coef sign sanity
    print("\n=== Coefficient sign sanity check (expected -) ===")
    pipe, _ = train_final(rolling, RP3_FEATS + ["park_pf_HR_ros"])
    coefs = dict(zip(RP3_FEATS + ["park_pf_HR_ros"], pipe.named_steps["r"].coef_))
    coef = coefs["park_pf_HR_ros"]
    sign_ok = coef < 0
    print(f"  park_pf_HR_ros: coef={coef:+.4f}  {'OK' if sign_ok else 'WRONG SIGN'}")

    print("\n=== VERDICT SUMMARY ===")
    lift = result["lift"]
    signs = result["sign_match_years"]
    print(f"  Δr (lift):                 {lift:+.4f}")
    print(f"  Per-year positives:        {signs}/{result['n_total_years']}")
    print(f"  Holdout (2024-25) lift:    {result['holdout_lift']}")
    print(f"  Coef sign:                 {'OK' if sign_ok else 'WRONG'}")

    if lift >= 0.005 and signs >= 5 and sign_ok:
        verdict = "PASS"
    elif 0.0 < lift < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
