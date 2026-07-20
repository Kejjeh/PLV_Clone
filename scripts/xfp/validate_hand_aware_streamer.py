# Pre-registered: see data/research/validation_runs/hand_aware_streamer_2026-07-19.md
"""Validate opp_xwoba_vs_hand_asof (hand-matched opponent strength) for per-start SP FP.

Candidate: opposing team's as-of xwOBA accumulated only vs pitchers of the
starter's hand. Controls (Rule 9 per-start baseline): pitcher's own cumulative
fp_proxy per start + opponent's as-of overall (hand-blind) xwOBA.
Outcome: fp_proxy of the start (per_start_fp_proxy substrate).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from build_recform_hot_retroactive import per_start_fp_proxy  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
HOLDOUT_YEARS = [2024, 2025]
MIN_TEAM_PA_HAND = 150
MIN_TEAM_PA_OVERALL = 300
MIN_PRIOR_STARTS = 3


def build_year(year: int) -> pd.DataFrame:
    cols = [
        "game_pk", "game_date", "pitcher", "p_throws", "inning", "inning_topbot",
        "at_bat_number", "home_team", "away_team", "events",
        "woba_value", "woba_denom", "estimated_woba_using_speedangle",
    ]
    sc = pd.read_parquet(CACHE / f"statcast_{year}.parquet", columns=cols)
    sc = sc.dropna(subset=["game_pk", "game_date", "pitcher"]).copy()
    sc["game_date"] = pd.to_datetime(sc["game_date"])

    # batting team of each half-inning
    sc["bat_team"] = np.where(sc["inning_topbot"] == "Top", sc["away_team"], sc["home_team"])

    # ── starters: pitcher of the first at-bat of each game half ──────────
    first = (
        sc[sc["inning"] == 1]
        .sort_values("at_bat_number")
        .groupby(["game_pk", "inning_topbot"], observed=True)
        .first()
        .reset_index()[["game_pk", "inning_topbot", "game_date", "pitcher", "p_throws", "bat_team"]]
        .rename(columns={"pitcher": "starter", "p_throws": "starter_hand", "bat_team": "opp_team"})
    )

    # ── team as-of xwOBA, by hand and overall (strictly before game date) ─
    pa = sc[sc["woba_denom"] == 1].copy()
    pa["xw"] = pa["estimated_woba_using_speedangle"].fillna(pa["woba_value"])

    def asof_table(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        day = df.groupby(keys + ["game_date"], observed=True)["xw"].agg(["sum", "count"]).reset_index()
        day = day.sort_values("game_date")
        day[["cum_sum", "cum_n"]] = (
            day.groupby(keys, observed=True)[["sum", "count"]].cumsum()
            - day[["sum", "count"]].values
        )
        day["asof_xwoba"] = day["cum_sum"] / day["cum_n"].replace(0, np.nan)
        return day[keys + ["game_date", "asof_xwoba", "cum_n"]]

    by_hand = asof_table(pa, ["bat_team", "p_throws"])
    overall = asof_table(pa, ["bat_team"])

    starts = first.merge(
        by_hand.rename(columns={"bat_team": "opp_team", "p_throws": "starter_hand",
                                "asof_xwoba": "opp_xwoba_vs_hand_asof", "cum_n": "pa_hand"}),
        on=["opp_team", "starter_hand", "game_date"], how="left",
    ).merge(
        overall.rename(columns={"bat_team": "opp_team",
                                "asof_xwoba": "opp_xwoba_overall_asof", "cum_n": "pa_overall"}),
        on=["opp_team", "game_date"], how="left",
    )

    # ── outcome + pitcher as-of quality from the canonical substrate ─────
    fp = per_start_fp_proxy(year)
    fp = fp.sort_values(["pitcher", "game_date"]).copy()
    grp = fp.groupby("pitcher", observed=True)
    fp["prior_starts"] = grp.cumcount()
    fp["fp_proxy_per_start_to"] = (
        grp["fp_proxy"].cumsum() - fp["fp_proxy"]
    ) / fp["prior_starts"].replace(0, np.nan)

    out = starts.merge(
        fp[["pitcher", "game_pk", "fp_proxy", "prior_starts", "fp_proxy_per_start_to"]],
        left_on=["starter", "game_pk"], right_on=["pitcher", "game_pk"], how="inner",
    )
    out["year"] = year
    out = out[
        (out["prior_starts"] >= MIN_PRIOR_STARTS)
        & (out["pa_hand"] >= MIN_TEAM_PA_HAND)
        & (out["pa_overall"] >= MIN_TEAM_PA_OVERALL)
    ].dropna(subset=["fp_proxy", "fp_proxy_per_start_to",
                     "opp_xwoba_vs_hand_asof", "opp_xwoba_overall_asof"])
    return out[["year", "game_date", "starter", "starter_hand", "opp_team", "fp_proxy",
                "fp_proxy_per_start_to", "opp_xwoba_vs_hand_asof", "opp_xwoba_overall_asof"]]


def partial_r(df: pd.DataFrame) -> tuple[float, float, int]:
    """Partial r of candidate vs outcome, controlling for the Rule 9 baseline."""
    X = df[["fp_proxy_per_start_to", "opp_xwoba_overall_asof"]].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(X)), X])
    y = df["fp_proxy"].to_numpy(dtype=float)
    c = df["opp_xwoba_vs_hand_asof"].to_numpy(dtype=float)
    ry = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    rc = c - X @ np.linalg.lstsq(X, c, rcond=None)[0]
    r, p = pearsonr(rc, ry)
    return r, p, len(df)


def main() -> None:
    frames = {}
    for yr in TRAIN_YEARS + HOLDOUT_YEARS:
        frames[yr] = build_year(yr)
        print(f"{yr}: {len(frames[yr])} qualified starts")

    train = pd.concat([frames[y] for y in TRAIN_YEARS], ignore_index=True)
    hold = pd.concat([frames[y] for y in HOLDOUT_YEARS], ignore_index=True)

    print("\n== Gate (a): pooled partial r, training years ==")
    r, p, n = partial_r(train)
    print(f"pooled partial r = {r:+.4f} (p={p:.2e}, n={n})")

    print("\n== Gate (b): per-year sign consistency ==")
    for yr in TRAIN_YEARS + HOLDOUT_YEARS:
        ry, py, ny = partial_r(frames[yr])
        tag = "HOLDOUT" if yr in HOLDOUT_YEARS else "train"
        print(f"{yr} ({tag}): partial r = {ry:+.4f} (p={py:.3f}, n={ny})")

    print("\n== Gate (c): pooled holdout ==")
    rh, ph, nh = partial_r(hold)
    print(f"holdout pooled partial r = {rh:+.4f} (p={ph:.2e}, n={nh})")

    print("\n== Rule 8 framing slices (training pooled, by season third) ==")
    m = train["game_date"].dt.month
    for label, mask in [("Apr-May", m <= 5), ("Jun-Jul", (m >= 6) & (m <= 7)), ("Aug-Sep", m >= 8)]:
        rs, ps, ns = partial_r(train[mask])
        print(f"{label}: partial r = {rs:+.4f} (p={ps:.3f}, n={ns})")

    print("\n== Context: raw (no-control) correlations, training pooled ==")
    for col in ["opp_xwoba_vs_hand_asof", "opp_xwoba_overall_asof", "fp_proxy_per_start_to"]:
        rr, _ = pearsonr(train[col].to_numpy(dtype=float), train["fp_proxy"].to_numpy(dtype=float))
        print(f"corr(fp_proxy, {col}) = {rr:+.4f}")


if __name__ == "__main__":
    main()
