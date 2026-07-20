# Pre-registered: data/research/validation_runs/teammate_context_2026-07-19.md
"""teammate_context (rh3, Wave 2B): rbi_context / r_context lineup-spillover cells."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _validate_rh3_v3_helper as H  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
K_WOBA, K_ISO = 60.0, 60.0
AHEAD, BEHIND = 2, 3

SEASON_STARTS = {
    2018: "2018-03-29", 2019: "2019-03-20", 2020: "2020-07-23",
    2021: "2021-04-01", 2022: "2022-04-07", 2023: "2023-03-30",
    2024: "2024-03-28", 2025: "2025-03-27", 2026: "2026-03-26",
}

ISO_W = {"single": 0.0, "double": 1.0, "triple": 2.0, "home_run": 3.0}


def load_year(year: int):
    """Return (pa_frame for rates, lineup frame with team)."""
    sc = pd.read_parquet(
        CACHE / f"statcast_{year}.parquet",
        columns=["batter", "game_pk", "game_date", "events", "woba_value", "woba_denom",
                 "inning_topbot", "home_team", "away_team"],
    )
    sc = sc[sc["batter"].notna()].copy()
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    pa = sc[sc["woba_denom"] == 1].copy()
    ev = pa["events"].astype(str)
    pa["iso_num"] = ev.map(ISO_W).fillna(np.nan)  # NaN for non-AB-hit events handled below
    # AB flag: PA minus BB/HBP/sac (approx; consistent across players)
    pa["is_ab"] = (~ev.isin(["walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf"])).astype(int)
    pa["iso_num"] = pa["iso_num"].fillna(0.0) * pa["is_ab"]

    team = np.where(sc["inning_topbot"] == "Top", sc["away_team"], sc["home_team"])
    bteam = sc.assign(team=team).drop_duplicates(["game_pk", "batter"])[["game_pk", "batter", "team"]]

    lu = pd.read_parquet(
        CACHE / f"hitter_lineup_appearances_{year}.parquet",
        columns=["game_pk", "batter", "lineup_spot", "started_game", "game_date"],
    )
    lu = lu[(lu["started_game"] == True) & lu["lineup_spot"].between(1, 9)].copy()  # noqa: E712
    lu["game_date"] = pd.to_datetime(lu["game_date"])
    lu = lu.merge(bteam, on=["game_pk", "batter"], how="left").dropna(subset=["team"])
    return pa, lu


def asof_rates(pa: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    b = pa[pa["game_date"] <= cutoff]
    if b.empty:
        return pd.DataFrame(columns=["batter", "woba_sh", "iso_sh"])
    pop_w = b["woba_value"].mean()
    ab = b[b["is_ab"] == 1]
    pop_i = ab["iso_num"].mean()
    g = b.groupby("batter").agg(w_sum=("woba_value", "sum"), n_pa=("woba_value", "size")).reset_index()
    gi = ab.groupby("batter").agg(i_sum=("iso_num", "sum"), n_ab=("iso_num", "size")).reset_index()
    g = g.merge(gi, on="batter", how="left").fillna({"i_sum": 0.0, "n_ab": 0.0})
    g["woba_sh"] = (g["w_sum"] + K_WOBA * pop_w) / (g["n_pa"] + K_WOBA)
    g["iso_sh"] = (g["i_sum"] + K_ISO * pop_i) / (g["n_ab"] + K_ISO)
    return g[["batter", "woba_sh", "iso_sh"]]


def build_context(grid: pd.DataFrame) -> pd.DataFrame:
    out = []
    for year, splits in grid.groupby("year")["split_day"]:
        yr = int(year)
        if not (CACHE / f"statcast_{yr}.parquet").exists():
            continue
        try:
            pa, lu = load_year(yr)
        except FileNotFoundError:
            continue
        start = pd.Timestamp(SEASON_STARTS[yr])
        # neighbor map per (game, team): spot -> batter
        wide = lu.pivot_table(index=["game_pk", "team", "game_date"], columns="lineup_spot",
                              values="batter", aggfunc="first")
        for split_day in sorted(splits.unique()):
            cutoff = start + pd.Timedelta(days=int(split_day))
            w = wide[wide.index.get_level_values("game_date") <= cutoff]
            if w.empty:
                continue
            rates = asof_rates(pa, cutoff).set_index("batter")
            rows = []
            for spot in range(1, 10):
                if spot not in w.columns:
                    continue
                ahead = [(spot - 1 - k) % 9 + 1 for k in range(AHEAD)]
                behind = [(spot - 1 + k + 1) % 9 + 1 for k in range(BEHIND)]
                sub = pd.DataFrame({"batter": w[spot]})
                sub["rbi_context"] = np.nanmean(
                    [w[a].map(rates["woba_sh"]).to_numpy(dtype=float) for a in ahead if a in w.columns], axis=0)
                sub["r_context"] = np.nanmean(
                    [w[b].map(rates["iso_sh"]).to_numpy(dtype=float) for b in behind if b in w.columns], axis=0)
                rows.append(sub.dropna(subset=["batter"]))
            allrows = pd.concat(rows, ignore_index=True)
            g = allrows.groupby("batter")[["rbi_context", "r_context"]].mean().reset_index()
            g["year"], g["split_day"] = yr, int(split_day)
            out.append(g)
        print(f"  context built {yr}", flush=True)
    return pd.concat(out, ignore_index=True)


def main() -> None:
    print("=== /validate-feature: teammate_context (rh3, Wave 2B, 2 cells) ===")
    orig_loader = H.load_and_prep_rh3_inputs

    def patched_loader():
        rolling = orig_loader()
        grid = rolling[["year", "split_day"]].drop_duplicates()
        ctx = build_context(grid)
        merged = rolling.merge(ctx, on=["batter", "year", "split_day"], how="left")
        for c in ("rbi_context", "r_context"):
            n_miss = merged[c].isna().sum()
            print(f"  {c}: match {1 - n_miss/len(merged):.1%}; mean-imputing {n_miss}")
            merged[c] = merged[c].fillna(merged[c].mean())
        return merged

    H.load_and_prep_rh3_inputs = patched_loader
    prereg = ROOT / "data" / "research" / "validation_runs" / "teammate_context_2026-07-19.md"
    for cell, cand in [("2B-1", "rbi_context"), ("2B-2", "r_context")]:
        print(f"\n{'='*70}\n=== CELL {cell}: {cand} ===\n{'='*70}")
        result = H.run_candidate_eval(candidate=cand, expected_sign="+", pre_reg_path=prereg)
        print(f"\n--- CELL {cell} SUMMARY ---")
        print(f"  Dr: {result['delta_r']:+.4f}  per-year +: {result['positives']}/7  "
              f"holdout +: {result['holdout_positives']}/{result['holdout_total']}  "
              f"sign: {'OK' if result['sign_ok'] else 'WRONG'}")


if __name__ == "__main__":
    main()
