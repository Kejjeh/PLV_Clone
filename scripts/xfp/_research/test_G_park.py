"""TEST G — Park factor adjustment for HR rate.

1) Adjust hr_per_pa by dividing by team_hr_factor (pf_HR).
2) Re-rate within year: r_HRrate_parkadj = within-year rank of adjusted hr_per_pa scaled to 20-80.
3) Refit hitter current-year FP regression and T+1 FP regression with park-adjusted vs raw HR rating.
4) Special test: team-movers (year T -> year T+1 different team) — does park-adjusted predict T+1 FP better?

We use sub-domain ratings + age + r_HRrate (raw OR park-adjusted) as feature set.
Sub-domain ratings already include DAMAGE_PROD which is HR-dependent — we leave them as-is
and only swap r_HRrate. This isolates the park signal in a single feature.

Park data starts 2018; we filter to year >= 2019 (so we have year and year-1 park records).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    HIT_SUBS, build_horizon_panel, load_hitters,
)
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
PARK = Path(__file__).resolve().parents[3] / "data" / "research" / "xfp_cache" / "park_factors_2018_2026.csv"


def within_year_rank_2080(series: pd.Series) -> pd.Series:
    """Rank to percentile then 20-80 scaled (mean 50, sd 10 assumes uniform)."""
    # Use percentile rank -> z via normal inverse to be consistent with prod style
    from scipy.stats import norm
    p = series.rank(pct=True, method="average").clip(0.001, 0.999)
    z = norm.ppf(p)
    return (50 + 10 * z).clip(20, 80)


def load_panel_with_park():
    h = load_hitters()
    park = pd.read_csv(PARK)
    park = park[["year", "team_abbr", "pf_HR", "pf_wOBA"]].rename(columns={"team_abbr": "team"})
    h = h.merge(park, on=["year", "team"], how="left")
    h["pf_HR"] = h["pf_HR"].fillna(1.0)
    # Adjust hr_per_pa (skill-pure: what would HR rate be in a neutral park)
    h["hr_per_pa_parkadj"] = h["hr_per_pa"] / h["pf_HR"]
    # Re-rate within year
    h["r_HRrate_parkadj"] = h.groupby("year")["hr_per_pa_parkadj"].transform(within_year_rank_2080)
    return h


def fit_and_score(df, feats, y_col, test_year):
    df = df.dropna(subset=feats + [y_col])
    df = df[df["data_tier"] == "FULL"]
    train = df[df["year"] <= test_year - 1]
    test = df[df["year"] == test_year]
    if len(train) < 50 or len(test) < 10:
        return None
    m = LinearRegression().fit(train[feats], train[y_col])
    yp = m.predict(test[feats])
    return {
        "r2": float(r2_score(test[y_col], yp)),
        "mae": float(mean_absolute_error(test[y_col], yp)),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
    }


def add_prev_team(df):
    df = df.sort_values(["batter", "year"]).copy()
    df["prev_team"] = df.groupby("batter")["team"].shift(1)
    df["team_changed_from_prev"] = (df["prev_team"].notna()) & (df["prev_team"] != df["team"])
    return df


def main():
    h = load_panel_with_park()
    h = build_horizon_panel(h, id_col="batter", y_col="fp_per_pa", horizons=(1,))
    h = add_prev_team(h)

    # filter to years with park coverage on year T+1 also, so 2018 onward
    h_pf = h[h["year"] >= 2018].copy()

    feats_raw     = HIT_SUBS + ["age", "r_HRrate"]
    feats_parkadj = HIT_SUBS + ["age", "r_HRrate_parkadj"]

    # CURRENT-YEAR FP regression: test on 2024
    cy = {
        "test_year": 2024,
        "raw": fit_and_score(h_pf, feats_raw, "fp_per_pa", 2024),
        "parkadj": fit_and_score(h_pf, feats_parkadj, "fp_per_pa", 2024),
    }
    if cy["raw"] and cy["parkadj"]:
        cy["delta_r2"] = cy["parkadj"]["r2"] - cy["raw"]["r2"]

    # T+1 FP regression: test on 2024 (predicts 2025)
    t1 = {
        "test_year": 2024,
        "raw": fit_and_score(h_pf, feats_raw, "fp_t1", 2024),
        "parkadj": fit_and_score(h_pf, feats_parkadj, "fp_t1", 2024),
    }
    if t1["raw"] and t1["parkadj"]:
        t1["delta_r2"] = t1["parkadj"]["r2"] - t1["raw"]["r2"]

    # TEAM MOVERS subset: players who changed teams between year T-1 -> T
    # Train on all, but evaluate ONLY on team-changers in test year
    def fit_train_then_eval_movers(feats, y_col, test_year):
        df = h_pf.dropna(subset=feats + [y_col])
        df = df[df["data_tier"] == "FULL"]
        train = df[df["year"] <= test_year - 1]
        test = df[(df["year"] == test_year) & (df["team_changed_from_prev"])]
        if len(train) < 50 or len(test) < 5:
            return None
        m = LinearRegression().fit(train[feats], train[y_col])
        yp = m.predict(test[feats])
        return {
            "r2": float(r2_score(test[y_col], yp)),
            "mae": float(mean_absolute_error(test[y_col], yp)),
            "n_train": int(len(train)),
            "n_test_movers": int(len(test)),
        }

    movers = {
        "test_year_T+1_via_2024": {
            "raw":     fit_train_then_eval_movers(feats_raw,     "fp_t1", 2024),
            "parkadj": fit_train_then_eval_movers(feats_parkadj, "fp_t1", 2024),
        },
        "test_year_currentY_2024": {
            "raw":     fit_train_then_eval_movers(feats_raw,     "fp_per_pa", 2024),
            "parkadj": fit_train_then_eval_movers(feats_parkadj, "fp_per_pa", 2024),
        },
    }

    # SPOT-CHECK: Rockies hitters (high pf_HR) — raw rating should be inflated, park-adj lower
    spot = []
    rockies_recent = h_pf[(h_pf["team"] == "COL") & (h_pf["year"] >= 2019) & (h_pf["data_tier"] == "FULL")]
    for _, row in rockies_recent.iterrows():
        spot.append({
            "player": row["player_name"], "year": int(row["year"]), "team": row["team"],
            "pf_HR": float(row["pf_HR"]),
            "hr_per_pa": float(row["hr_per_pa"]),
            "r_HRrate_raw": float(row["r_HRrate"]),
            "r_HRrate_parkadj": float(row["r_HRrate_parkadj"]),
            "delta": float(row["r_HRrate_parkadj"] - row["r_HRrate"]),
        })
    # Sort by largest negative delta (most "inflated" raw ratings)
    spot.sort(key=lambda d: d["delta"])
    spot_rockies_topdrop = spot[:10]

    out = {
        "current_year": cy,
        "t1": t1,
        "team_movers": movers,
        "spot_check_rockies_top_park_adj_drops": spot_rockies_topdrop,
        "n_rows_with_park": int(h_pf["pf_HR"].notna().sum()),
    }
    with open(OUT / "test_G_results.json", "w") as f:
        json.dump(out, f, indent=2, default=float)

    print(json.dumps({
        "cy_raw_r2": cy["raw"]["r2"] if cy["raw"] else None,
        "cy_parkadj_r2": cy["parkadj"]["r2"] if cy["parkadj"] else None,
        "cy_delta": cy.get("delta_r2"),
        "t1_raw_r2": t1["raw"]["r2"] if t1["raw"] else None,
        "t1_parkadj_r2": t1["parkadj"]["r2"] if t1["parkadj"] else None,
        "t1_delta": t1.get("delta_r2"),
        "movers_t1_raw":     movers["test_year_T+1_via_2024"]["raw"],
        "movers_t1_parkadj": movers["test_year_T+1_via_2024"]["parkadj"],
        "rockies_spot": spot_rockies_topdrop[:5],
    }, indent=2))


if __name__ == "__main__":
    main()
