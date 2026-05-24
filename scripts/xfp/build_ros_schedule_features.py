"""build_ros_schedule_features.py

Builds per-(pitcher, year, split_day) schedule-weighted opponent quality
and park exposure for rp3 v3 validation candidates.

Outputs: data/research/xfp_cache/ros_schedule_features_2018_2026.csv
  columns: pitcher, year, split_day, ros_opp_xwoba_weighted,
           ros_park_pf_HR_weighted, n_ros_games

Per (pitcher, year, split_day):
  1. Resolve pitcher's primary team that year from pitcher_primary_team
     cache.
  2. From per-year statcast, derive that team's game log (game_pk,
     game_date, home_team, away_team).
  3. Filter to games with game_date > cutoff_date for the split_day (RoS).
  4. For each RoS game determine: opp_team, venue_team (home_team).
  5. Look up opp_team season xwOBA (from same statcast year aggregated
     by batting team) and venue pf_HR (from park_factors_2018_2026.csv).
  6. Equal-weight mean across RoS games -> feature.

Notes
-----
* Opponent xwOBA is *full-season* (mild look-ahead). For a validation
  signal this is fine — same proxy used for all rows in the same year;
  the signal carries cross-pitcher variation in *schedule mix*, not
  in-season opp form. v2 could switch to to-date opp xwOBA.
* Pitchers with no RoS games (end-of-year IL) get NaN; downstream
  validation fills with 1.00 / season mean.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
ROLLING_CSV = CACHE / "rolling_pitchers_2018_2026.csv"
PITCHER_TEAM_CSV = CACHE / "pitcher_primary_team_2018_2026.csv"
PARK_CSV = CACHE / "park_factors_2018_2026.csv"
OUT_CSV = CACHE / "ros_schedule_features_2018_2026.csv"

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]


def build_team_game_log(sc: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_pk, team) with date, opp, venue_team."""
    games = (
        sc[["game_pk", "game_date", "home_team", "away_team"]]
        .drop_duplicates("game_pk")
        .reset_index(drop=True)
    )
    home = games.rename(columns={"home_team": "team", "away_team": "opp"})
    home["venue_team"] = home["team"]
    away = games.rename(columns={"away_team": "team", "home_team": "opp"})
    away["venue_team"] = away["opp"]
    return pd.concat([home, away], ignore_index=True)[
        ["game_pk", "game_date", "team", "opp", "venue_team"]
    ]


def build_team_season_xwoba(sc: pd.DataFrame) -> pd.DataFrame:
    """Per-team batting xwOBA across the full season (sum num / sum denom)."""
    bat_team = np.where(sc["inning_topbot"] == "Top", sc["away_team"], sc["home_team"])
    df = pd.DataFrame({
        "team": bat_team,
        "x_num": sc["estimated_woba_using_speedangle"].astype("Float64"),
        "x_denom": sc["woba_denom"].astype("Int64"),
    })
    df = df.dropna(subset=["x_num", "x_denom"])
    df = df[df["x_denom"] > 0]
    agg = df.groupby("team").agg(
        x_num_sum=("x_num", "sum"),
        x_denom_sum=("x_denom", "sum"),
    ).reset_index()
    agg["team_xwoba"] = agg["x_num_sum"] / agg["x_denom_sum"]
    return agg[["team", "team_xwoba"]]


def normalize_team(t: str) -> str:
    """Park-factors CSV uses 'AZ', 'ATH'. Statcast also uses AZ/ATH. Map any
    legacy abbrs if needed."""
    if t is None:
        return t
    return {"OAK": "ATH"}.get(t, t)


def main() -> None:
    rolling = pd.read_csv(
        ROLLING_CSV, usecols=["pitcher", "year", "split_day", "cutoff_date"]
    )
    rolling = rolling.drop_duplicates(["pitcher", "year", "split_day"])
    pt = pd.read_csv(PITCHER_TEAM_CSV)
    park = pd.read_csv(PARK_CSV)[["year", "team_abbr", "pf_HR"]].rename(
        columns={"team_abbr": "venue_team"}
    )

    out_rows = []
    for yr in YEARS:
        sc_path = CACHE / f"statcast_{yr}.parquet"
        if not sc_path.exists():
            print(f"  [{yr}] no statcast parquet, skip")
            continue
        sc = pd.read_parquet(
            sc_path,
            columns=[
                "game_pk", "game_date", "home_team", "away_team",
                "inning_topbot", "estimated_woba_using_speedangle", "woba_denom",
            ],
        )
        sc["home_team"] = sc["home_team"].map(normalize_team)
        sc["away_team"] = sc["away_team"].map(normalize_team)

        game_log = build_team_game_log(sc)
        game_log["team"] = game_log["team"].map(normalize_team)
        game_log["opp"] = game_log["opp"].map(normalize_team)
        game_log["venue_team"] = game_log["venue_team"].map(normalize_team)

        team_x = build_team_season_xwoba(sc)
        team_x["team"] = team_x["team"].map(normalize_team)
        opp_x = team_x.rename(columns={"team": "opp", "team_xwoba": "opp_xwoba"})

        pf_yr = park[park["year"] == yr][["venue_team", "pf_HR"]]
        # Some years missing in park (e.g. 2026 partial) — neutral fill on join later

        game_log = game_log.merge(opp_x, on="opp", how="left")
        game_log = game_log.merge(pf_yr, on="venue_team", how="left")

        # pitcher-team this year
        pt_yr = pt[pt["year"] == yr][["pitcher", "pitcher_team"]].rename(
            columns={"pitcher_team": "team"}
        )
        pt_yr["team"] = pt_yr["team"].map(normalize_team)
        roll_yr = rolling[rolling["year"] == yr].merge(pt_yr, on="pitcher", how="left")

        n_no_team = roll_yr["team"].isna().sum()
        if n_no_team:
            print(f"  [{yr}] {n_no_team} rolling rows lack pitcher_team — get NaN feats")

        # For each split_day cutoff_date, aggregate team's RoS games
        for split_day, sub in roll_yr.groupby("split_day"):
            cutoff = sub["cutoff_date"].iloc[0]
            ros = game_log[game_log["game_date"] > cutoff]
            agg = ros.groupby("team").agg(
                ros_opp_xwoba_weighted=("opp_xwoba", "mean"),
                ros_park_pf_HR_weighted=("pf_HR", "mean"),
                n_ros_games=("game_pk", "count"),
            ).reset_index()
            merged = sub.merge(agg, on="team", how="left")
            out_rows.append(
                merged[[
                    "pitcher", "year", "split_day",
                    "ros_opp_xwoba_weighted", "ros_park_pf_HR_weighted",
                    "n_ros_games",
                ]]
            )
            print(f"  [{yr} sd={split_day}] cutoff={cutoff} "
                  f"teams_with_ros={len(agg)} pitcher_rows={len(merged)}")

    out = pd.concat(out_rows, ignore_index=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}: {len(out)} rows")
    print(out.describe())


if __name__ == "__main__":
    main()
