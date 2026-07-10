"""build_ros_park_factor.py

Builds per-(player, year, split_day) schedule-weighted rest-of-season
PARK FACTOR for the `ros_park_factor_weighted` candidate feature
(rh3 + rp3, pre-registered 2026-07-09).

Mirrors the schedule machinery of build_ros_opp_sp_xwoba_per_hitter.py
(hitters) and build_ros_schedule_features.py (pitchers):

Per (player, year, split_day):
  1. Resolve player's primary team that year (max-PA team from
     hitters_multiyr for batters; pitcher_primary_team cache for SPs).
  2. Team game log from per-year statcast parquet (game_pk, game_date,
     home_team, away_team); venue = home_team.
  3. Filter to RoS games (game_date > split_day cutoff_date).
  4. Join each RoS venue's LAGGED Savant park factor: for outcome year T
     use the 3-yr-rolling window ENDING T-1 (key_year = T-1) from
     park_factors_savant.csv, falling back to the single-year T-1 value
     for team-years without a full 3-yr window (new parks), then
     neutral 1.00. Rule-8 leakage-safe: nothing from year T enters.
  5. Equal-weight mean across RoS games (each game ~ equal PAs/starts).

Feature scale: Savant index_woba / 100 (1.00 = neutral, >1 hitter-friendly).

Outputs:
  data/research/xfp_cache/ros_park_factor_per_hitter.csv
    (batter, year, split_day, ros_park_factor_weighted, n_ros_games)
  data/research/xfp_cache/ros_park_factor_per_pitcher.csv
    (pitcher, year, split_day, ros_park_factor_weighted, n_ros_games)

All split_days present in the rolling CSVs are covered (30..191 weekly),
years 2018, 2019, 2021-2026 (2020 excluded, matching the harnesses).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
# Statcast parquets are gitignored — live in the main repo's cache.
from plv_clone.paths import CACHE as MAIN_CACHE

ROLLING_HITTERS_CSV = CACHE / "rolling_hitters_2018_2026.csv"
ROLLING_PITCHERS_CSV = CACHE / "rolling_pitchers_2018_2026.csv"
MULTIYR_CSV = CACHE / "hitters_multiyr_2015_2026.csv"
PITCHER_TEAM_CSV = CACHE / "pitcher_primary_team_2018_2026.csv"
PARK_CSV = CACHE / "park_factors_savant.csv"
OUT_HITTER_CSV = CACHE / "ros_park_factor_per_hitter.csv"
OUT_PITCHER_CSV = CACHE / "ros_park_factor_per_pitcher.csv"

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
FEATURE = "ros_park_factor_weighted"


def normalize_team(t):
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return t
    return {"OAK": "ATH"}.get(t, t)


def build_lagged_park_table() -> pd.DataFrame:
    """Per (outcome_year, venue_team) lagged park factor pf.

    outcome_year T -> Savant 3-yr-rolling index_woba ending key_year=T-1,
    single-year T-1 fallback for teams missing the 3-yr window.
    """
    pf = pd.read_csv(PARK_CSV)
    pf = pf.dropna(subset=["team_abbr", "index_woba"])
    rows = []
    for t in YEARS:
        key = t - 1
        r3 = pf[(pf["key_year"] == key) & (pf["n_years_rolling"] == 3)]
        r1 = pf[(pf["key_year"] == key) & (pf["n_years_rolling"] == 1)]
        r3 = r3.set_index("team_abbr")["index_woba"]
        r1 = r1.set_index("team_abbr")["index_woba"]
        teams = sorted(set(r3.index) | set(r1.index))
        for team in teams:
            val = r3.get(team, np.nan)
            src = "rolling3"
            if pd.isna(val):
                val = r1.get(team, np.nan)
                src = "single_year_fallback"
            rows.append({"year": t, "venue_team": team,
                         "pf": val / 100.0, "pf_source": src})
    out = pd.DataFrame(rows)
    n_fb = (out["pf_source"] == "single_year_fallback").sum()
    print(f"  lagged park table: {len(out)} team-years, "
          f"{n_fb} single-year fallbacks")
    return out


def build_team_game_log_year(yr: int) -> pd.DataFrame:
    """One row per (game_pk, team) with game_date, venue_team (= home)."""
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
    home["venue_team"] = home["team"]
    away = games.rename(columns={"away_team": "team", "home_team": "opp"})
    away["venue_team"] = away["opp"]
    return pd.concat(
        [home[["game_pk", "game_date", "team", "venue_team"]],
         away[["game_pk", "game_date", "team", "venue_team"]]],
        ignore_index=True,
    )


def build_batter_primary_team() -> pd.DataFrame:
    h = pd.read_csv(MULTIYR_CSV, usecols=["batter", "year", "team", "pa"])
    h["team"] = h["team"].map(normalize_team)
    h = h.dropna(subset=["team"])
    h = h.sort_values(["batter", "year", "pa"], ascending=[True, True, False])
    return h.drop_duplicates(["batter", "year"], keep="first")[
        ["batter", "year", "team"]
    ].rename(columns={"team": "player_team"})


def build_pitcher_primary_team() -> pd.DataFrame:
    pt = pd.read_csv(PITCHER_TEAM_CSV)
    pt["pitcher_team"] = pt["pitcher_team"].map(normalize_team)
    return pt.rename(columns={"pitcher_team": "player_team"})[
        ["pitcher", "year", "player_team"]
    ]


def build_for(kind: str, rolling_csv: Path, id_col: str,
              team_table: pd.DataFrame, park: pd.DataFrame,
              out_csv: Path) -> None:
    print(f"\n--- building {kind} cache ---")
    rolling = pd.read_csv(
        rolling_csv, usecols=[id_col, "year", "split_day", "cutoff_date"]
    ).drop_duplicates([id_col, "year", "split_day"])
    print(f"  rolling rows: {len(rolling)}")

    out_rows = []
    for yr in YEARS:
        game_log = build_team_game_log_year(yr)
        if game_log.empty:
            continue
        pf_yr = park[park["year"] == yr][["venue_team", "pf"]]
        gl = game_log.merge(pf_yr, on="venue_team", how="left")
        n_pf_nan = gl["pf"].isna().sum()
        if n_pf_nan:
            print(f"  [{yr}] {n_pf_nan}/{len(gl)} game-team rows lack pf "
                  f"(unmatched venue_team) — excluded from means")

        tt_yr = team_table[team_table["year"] == yr][[id_col, "player_team"]] \
            if id_col in team_table.columns else \
            team_table[team_table["year"] == yr]
        roll_yr = rolling[rolling["year"] == yr].merge(
            tt_yr, on=id_col, how="left"
        )
        n_no_team = roll_yr["player_team"].isna().sum()
        if n_no_team:
            print(f"  [{yr}] {n_no_team} rolling rows lack player_team")

        for split_day, sub in roll_yr.groupby("split_day"):
            cutoff = sub["cutoff_date"].iloc[0]
            ros = gl[gl["game_date"] > cutoff]
            agg = (
                ros.groupby("team")
                .agg(**{
                    FEATURE: ("pf", "mean"),
                    "n_ros_games": ("game_pk", "count"),
                })
                .reset_index()
                .rename(columns={"team": "player_team"})
            )
            merged = sub.merge(agg, on="player_team", how="left")
            if "split_day" not in merged.columns:
                merged["split_day"] = split_day
            if "year" not in merged.columns:
                merged["year"] = yr
            out_rows.append(
                merged[[id_col, "year", "split_day", FEATURE, "n_ros_games"]]
            )
        print(f"  [{yr}] done ({roll_yr['split_day'].nunique()} split_days)")

    out = pd.concat(out_rows, ignore_index=True)
    out.to_csv(out_csv, index=False)
    miss = out[FEATURE].isna().sum()
    print(f"  wrote {out_csv}: {len(out)} rows")
    print(f"  {FEATURE}: mean={out[FEATURE].mean():.4f} "
          f"std={out[FEATURE].std():.4f} "
          f"min={out[FEATURE].min():.4f} max={out[FEATURE].max():.4f}")
    print(f"  NaN: {miss} ({miss / max(len(out), 1):.1%}) "
          f"(end-of-year no-RoS-games rows + missing team)")


def main() -> None:
    print("=== build_ros_park_factor ===")
    park = build_lagged_park_table()
    build_for("hitter", ROLLING_HITTERS_CSV, "batter",
              build_batter_primary_team(), park, OUT_HITTER_CSV)
    build_for("pitcher", ROLLING_PITCHERS_CSV, "pitcher",
              build_pitcher_primary_team(), park, OUT_PITCHER_CSV)


if __name__ == "__main__":
    main()
