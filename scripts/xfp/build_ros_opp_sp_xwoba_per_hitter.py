"""build_ros_opp_sp_xwoba_per_hitter.py

Builds per-(batter, year, split_day) RoS-schedule-weighted opposing-SP-quality
feature for the rh3 v3 candidate `ros_opp_sp_xwoba_weighted`.

Outputs: data/research/xfp_cache/ros_opp_sp_xwoba_per_hitter.csv
  columns: batter, year, split_day, ros_opp_sp_xwoba_weighted, n_ros_games

Per (batter, year, split_day):
  1. Resolve batter's primary team that year via max-PA team in
     hitters_multiyr_2015_2026.csv.
  2. Derive team game log from per-year statcast parquet (game_pk, date,
     home/away).
  3. Filter to games with game_date > split_day cutoff (RoS).
  4. For each RoS game, look up opp team's avg-SP xwOBA-allowed for that
     year (tbf-weighted across all SPs primarily rostered on opp_team
     with gs >= 5 that year).
  5. Equal-weight mean across RoS games (proxy for 4 PA per game; under
     the avg-SP-per-team approximation each game contributes equally).

Notes
-----
* SP-quality proxy is full-season (mild look-ahead), same as the rp3
  schedule feature. Carries cross-batter variation in schedule mix.
* Statcast parquets are large and gitignored — they live in the main
  repo's xfp_cache. We read from MAIN_CACHE for parquets and write to
  the worktree's CACHE.
* No handedness adjustment in v1 — team-aggregate SP quality only.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
# Statcast parquets are gitignored — live in the main repo's cache only.
from plv_clone.paths import CACHE as MAIN_CACHE

ROLLING_CSV = CACHE / "rolling_hitters_2018_2026.csv"
MULTIYR_CSV = CACHE / "hitters_multiyr_2015_2026.csv"
SP_MULTIYR_CSV = CACHE / "sp_multiyr_2015_2025.csv"
PITCHER_TEAM_CSV = CACHE / "pitcher_primary_team_2018_2026.csv"
OUT_CSV = CACHE / "ros_opp_sp_xwoba_per_hitter.csv"

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
MIN_GS_FOR_SP = 5  # gs threshold to count a pitcher as a starter that year


def normalize_team(t):
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return t
    return {"OAK": "ATH"}.get(t, t)


def build_team_avg_sp_xwoba_per_year() -> pd.DataFrame:
    """Per (team, year) tbf-weighted avg SP xwOBA-allowed.

    Restricts to pitchers with gs >= MIN_GS_FOR_SP that year, joined to
    their primary team via pitcher_primary_team_2018_2026.csv.
    """
    sp = pd.read_csv(
        SP_MULTIYR_CSV,
        usecols=["pitcher", "year", "woba_v_sum", "woba_d_sum", "gs", "tbf"],
    )
    sp = sp[(sp["gs"] >= MIN_GS_FOR_SP) & (sp["woba_d_sum"] > 0)]
    pt = pd.read_csv(PITCHER_TEAM_CSV)
    pt["pitcher_team"] = pt["pitcher_team"].map(normalize_team)
    m = sp.merge(pt, on=["pitcher", "year"], how="inner")
    agg = (
        m.groupby(["pitcher_team", "year"])
        .agg(num=("woba_v_sum", "sum"), denom=("woba_d_sum", "sum"),
             n_sps=("pitcher", "nunique"))
        .reset_index()
        .rename(columns={"pitcher_team": "team"})
    )
    agg["team_avg_sp_xwoba"] = agg["num"] / agg["denom"]
    return agg[["team", "year", "team_avg_sp_xwoba", "n_sps"]]


def build_team_game_log_year(yr: int) -> pd.DataFrame:
    sc_path = MAIN_CACHE / f"statcast_{yr}.parquet"
    if not sc_path.exists():
        print(f"  [{yr}] no statcast parquet at {sc_path}, skip")
        return pd.DataFrame()
    sc = pd.read_parquet(
        sc_path, columns=["game_pk", "game_date", "home_team", "away_team"]
    )
    sc["home_team"] = sc["home_team"].map(normalize_team)
    sc["away_team"] = sc["away_team"].map(normalize_team)
    games = sc.drop_duplicates("game_pk").reset_index(drop=True)
    home = games.rename(columns={"home_team": "team", "away_team": "opp"})
    away = games.rename(columns={"away_team": "team", "home_team": "opp"})
    out = pd.concat(
        [home[["game_pk", "game_date", "team", "opp"]],
         away[["game_pk", "game_date", "team", "opp"]]],
        ignore_index=True,
    )
    return out


def build_batter_primary_team() -> pd.DataFrame:
    """Per (batter, year) → primary team (max-PA team that year)."""
    h = pd.read_csv(MULTIYR_CSV, usecols=["batter", "year", "team", "pa"])
    h["team"] = h["team"].map(normalize_team)
    h = h.dropna(subset=["team"])
    h = h.sort_values(["batter", "year", "pa"], ascending=[True, True, False])
    pt = h.drop_duplicates(["batter", "year"], keep="first")[
        ["batter", "year", "team"]
    ].rename(columns={"team": "batter_team"})
    return pt


def main() -> None:
    print("=== build_ros_opp_sp_xwoba_per_hitter ===")

    rolling = pd.read_csv(
        ROLLING_CSV, usecols=["batter", "year", "split_day", "cutoff_date"]
    )
    rolling = rolling.drop_duplicates(["batter", "year", "split_day"])
    print(f"  rolling rows: {len(rolling)}")

    bt = build_batter_primary_team()
    print(f"  batter-team rows: {len(bt)}")

    team_sp = build_team_avg_sp_xwoba_per_year()
    print(f"  team-SP-xwoba rows: {len(team_sp)}  "
          f"years={sorted(team_sp.year.unique())}")
    print(team_sp.groupby("year")["team_avg_sp_xwoba"].describe()[
        ["mean", "min", "max"]
    ])

    out_rows = []
    for yr in YEARS:
        game_log = build_team_game_log_year(yr)
        if game_log.empty:
            continue
        # join opp team's avg SP xwOBA for this year
        ts_yr = team_sp[team_sp["year"] == yr][["team", "team_avg_sp_xwoba"]]
        ts_yr = ts_yr.rename(columns={"team": "opp", "team_avg_sp_xwoba": "opp_sp_xwoba"})
        gl = game_log.merge(ts_yr, on="opp", how="left")

        # batter team this year
        bt_yr = bt[bt["year"] == yr][["batter", "batter_team"]]
        roll_yr = rolling[rolling["year"] == yr].merge(bt_yr, on="batter", how="left")
        n_no_team = roll_yr["batter_team"].isna().sum()
        if n_no_team:
            print(f"  [{yr}] {n_no_team} rolling rows lack batter_team")

        for split_day, sub in roll_yr.groupby("split_day"):
            cutoff = sub["cutoff_date"].iloc[0]
            ros = gl[gl["game_date"] > cutoff]
            agg = (
                ros.groupby("team")
                .agg(
                    ros_opp_sp_xwoba_weighted=("opp_sp_xwoba", "mean"),
                    n_ros_games=("game_pk", "count"),
                )
                .reset_index()
                .rename(columns={"team": "batter_team"})
            )
            merged = sub.merge(agg, on="batter_team", how="left")
            # `sub` came from a groupby on split_day so `split_day` may have
            # been consumed as the grouping key — re-add if missing.
            if "split_day" not in merged.columns:
                merged["split_day"] = split_day
            if "year" not in merged.columns:
                merged["year"] = yr
            out_rows.append(
                merged[[
                    "batter", "year", "split_day",
                    "ros_opp_sp_xwoba_weighted", "n_ros_games",
                ]]
            )
            print(f"  [{yr} sd={split_day}] cutoff={cutoff} "
                  f"teams_with_ros={len(agg)} batter_rows={len(merged)}")

    out = pd.concat(out_rows, ignore_index=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}: {len(out)} rows")
    print(out["ros_opp_sp_xwoba_weighted"].describe())
    miss = out["ros_opp_sp_xwoba_weighted"].isna().sum()
    print(f"  NaN: {miss} ({miss / max(len(out), 1):.1%})")


if __name__ == "__main__":
    main()
