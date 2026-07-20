# Pre-registered: data/research/validation_runs/gmli_todate_2026-07-19.md
"""gmli_todate (3 cells) as rprs2 candidates — Wave 1B of the deep-research campaign.

Entry-LI per relief appearance from the frozen empirical LI table
(lib/leverage_index.py), aggregated as-of each (year, split_day) on the rprs2 grid.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_gmli_todate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from lib.leverage_index import build_li_table, li_lookup, STATE_COLS  # noqa: E402
import _rprs2_validation_harness as RH  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
MIN_APP = 5

SEASON_STARTS = {
    2018: "2018-03-29", 2019: "2019-03-20", 2020: "2020-07-23",
    2021: "2021-04-01", 2022: "2022-04-07", 2023: "2023-03-30",
    2024: "2024-03-28", 2025: "2025-03-27", 2026: "2026-03-26",
}

_COLS = [
    "game_pk", "game_date", "at_bat_number", "pitcher", "inning", "inning_topbot",
    "outs_when_up", "on_1b", "on_2b", "on_3b", "bat_score", "fld_score",
    "home_team", "away_team",
]


def relief_entries(year: int, table: pd.DataFrame) -> pd.DataFrame:
    """One row per RELIEF appearance: (pitcher, team, game_pk, game_date, entry_li)."""
    sc = pd.read_parquet(CACHE / f"statcast_{year}.parquet", columns=_COLS)
    sc = sc.dropna(subset=["game_pk", "pitcher", "at_bat_number"]).copy()
    sc["game_date"] = pd.to_datetime(sc["game_date"])

    # entry = first row for (pitcher, game_pk)
    entry = sc.sort_values("at_bat_number").groupby(["pitcher", "game_pk"], observed=True).first().reset_index()

    # exclude the game's starters (first pitcher of each half in inning 1)
    starters = (
        sc[sc["inning"] == 1].sort_values("at_bat_number")
        .groupby(["game_pk", "inning_topbot"], observed=True)["pitcher"].first().reset_index()
    )
    starter_keys = set(zip(starters["game_pk"], starters["pitcher"]))
    entry = entry[~entry.apply(lambda r: (r["game_pk"], r["pitcher"]) in starter_keys, axis=1)].copy()

    entry["inning_c"] = entry["inning"].clip(upper=9).astype(int)
    entry["is_top"] = (entry["inning_topbot"] == "Top").astype(int)
    entry["outs"] = entry["outs_when_up"].fillna(0).astype(int).clip(0, 2)
    entry["base_code"] = (
        entry["on_1b"].notna().astype(int)
        + 2 * entry["on_2b"].notna().astype(int)
        + 4 * entry["on_3b"].notna().astype(int)
    )
    entry["diff_c"] = (entry["bat_score"] - entry["fld_score"]).clip(-5, 5).astype(int)
    entry["entry_li"] = li_lookup(entry[STATE_COLS].reset_index(drop=True), table).values
    # pitcher's team = fielding side
    entry["team"] = np.where(entry["is_top"] == 1, entry["home_team"], entry["away_team"])
    return entry[["pitcher", "team", "game_pk", "game_date", "entry_li"]]


def build_gmli_frame(grid: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    out = []
    for year, splits in grid.groupby("year")["split_day"]:
        yr = int(year)
        if not (CACHE / f"statcast_{yr}.parquet").exists():
            continue
        ent = relief_entries(yr, table)
        start = pd.Timestamp(SEASON_STARTS[yr])
        for split_day in sorted(splits.unique()):
            cutoff = start + pd.Timedelta(days=int(split_day))
            b = ent[ent["game_date"] <= cutoff]
            if b.empty:
                continue
            g = b.groupby("pitcher").agg(
                gmli_todate=("entry_li", "mean"), n_app=("entry_li", "size"),
                team=("team", "last"),
            ).reset_index()
            g = g[g["n_app"] >= MIN_APP].copy()
            team_mean = b.groupby("team")["entry_li"].mean()  # pooled bullpen mean
            g["gmli_todate_teamrel"] = g["gmli_todate"] - g["team"].map(team_mean)
            g["n_teammates_higher_gmli"] = g.apply(
                lambda r: int((g.loc[g["team"] == r["team"], "gmli_todate"] > r["gmli_todate"]).sum()),
                axis=1,
            )
            g["year"] = yr
            g["split_day"] = int(split_day)
            out.append(g[["pitcher", "year", "split_day", "gmli_todate",
                          "gmli_todate_teamrel", "n_teammates_higher_gmli"]])
        print(f"  gmli built for {yr} ({splits.nunique()} splits)", flush=True)
    return pd.concat(out, ignore_index=True)


def main() -> None:
    print("=== /validate-feature: gmli_todate (rprs2, Wave 1B, 3 cells) ===")
    table = build_li_table()

    rolling = RH.prep_rolling()
    grid = rolling[["year", "split_day"]].drop_duplicates()
    gm = build_gmli_frame(grid, table)

    merged = rolling.merge(gm, on=["pitcher", "year", "split_day"], how="left")
    cells = ["gmli_todate", "gmli_todate_teamrel", "n_teammates_higher_gmli"]
    for c in cells:
        n_miss = merged[c].isna().sum()
        print(f"  {c}: match {1 - n_miss/len(merged):.1%}; mean-imputing {n_miss} rows")
        merged[c] = merged[c].fillna(merged[c].mean())

    # sanity: 2024 top gmli_todate at final split should be closer-class arms
    last24 = gm[(gm.year == 2024) & (gm.split_day == gm[gm.year == 2024].split_day.max())]
    top = last24.nlargest(8, "gmli_todate")[["pitcher", "gmli_todate"]]
    print("[sanity] top-8 gmli_todate 2024 final split (expect closer mlbam ids):")
    print(top.to_string(index=False))

    results = {}
    for c in cells:
        res = RH.evaluate_candidate(merged, c)
        RH.print_report(res)
        results[c] = res

    best = max(results, key=lambda c: results[c]["lift"])
    others = [c for c in cells if c != best and results[c]["lift"] > 0]
    if others:
        print(f"\n=== Redundancy: joint ({best} + rest) vs baseline+{best} ===")
        joint = RH.evaluate_candidate(merged, others, baseline_extra=[best],
                                      label=f"joint|{best}")
        RH.print_report(joint)


if __name__ == "__main__":
    main()
