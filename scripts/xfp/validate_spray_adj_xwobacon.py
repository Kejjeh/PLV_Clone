# Pre-registered: data/research/validation_runs/spray_adj_xwobacon_2026-07-19.md
"""spray_adj_xwobacon (rh3, Wave 2A — conditional cell, triggered by 1A-1 result)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _validate_rh3_v3_helper as H  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
K_SHRINK = 40.0
LOOKUP_YEARS = (2018, 2019, 2021, 2022, 2023)

SEASON_STARTS = {
    2018: "2018-03-29", 2019: "2019-03-20", 2020: "2020-07-23",
    2021: "2021-04-01", 2022: "2022-04-07", 2023: "2023-03-30",
    2024: "2024-03-28", 2025: "2025-03-27", 2026: "2026-03-26",
}


def load_bbe(year: int) -> pd.DataFrame:
    sc = pd.read_parquet(
        CACHE / f"statcast_{year}.parquet",
        columns=["batter", "game_date", "type", "launch_angle", "launch_speed",
                 "hc_x", "hc_y", "stand", "woba_value"],
    )
    sc = sc[(sc["type"] == "X") & sc["hc_x"].notna() & sc["hc_y"].notna()
            & sc["launch_speed"].notna() & sc["batter"].notna()].copy()
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    phi = np.degrees(np.arctan2(sc["hc_x"].astype(float) - 125.42, 198.27 - sc["hc_y"].astype(float)))
    adj = np.where(sc["stand"] == "R", phi, -phi)  # negative = pull (verified Wave 1A)
    sc["spray_bin"] = pd.cut(pd.Series(adj, index=sc.index), [-90, -30, -15, 0, 15, 30, 90], labels=False)
    la = sc["launch_angle"].astype(float)
    sc["la_band"] = np.where(la < 10, 0, np.where(la < 25, 1, 2))
    return sc


def build_lookup() -> tuple[pd.Series, list[float]]:
    frames = [load_bbe(y) for y in LOOKUP_YEARS]
    pool = pd.concat(frames, ignore_index=True)
    ev_cuts = pool["launch_speed"].quantile([1 / 3, 2 / 3]).tolist()
    pool["ev_band"] = np.digitize(pool["launch_speed"], ev_cuts)
    lut = pool.groupby(["spray_bin", "la_band", "ev_band"], observed=True)["woba_value"].mean()
    return lut, ev_cuts


def main() -> None:
    print("=== /validate-feature: spray_adj_xwobacon (rh3, Wave 2A) ===")
    lut, ev_cuts = build_lookup()
    print(f"  lookup: {len(lut)} cells; ev cuts {[round(c,1) for c in ev_cuts]}")

    orig_loader = H.load_and_prep_rh3_inputs

    def patched_loader():
        rolling = orig_loader()
        grid = rolling[["year", "split_day"]].drop_duplicates()
        out = []
        for year, splits in grid.groupby("year")["split_day"]:
            yr = int(year)
            if not (CACHE / f"statcast_{yr}.parquet").exists():
                continue
            bbe = load_bbe(yr)
            bbe["ev_band"] = np.digitize(bbe["launch_speed"], ev_cuts)
            key = pd.MultiIndex.from_frame(bbe[["spray_bin", "la_band", "ev_band"]])
            bbe["exp_val"] = lut.reindex(key).fillna(lut.mean()).values
            start = pd.Timestamp(SEASON_STARTS[yr])
            for split_day in sorted(splits.unique()):
                before = bbe[bbe["game_date"] <= start + pd.Timedelta(days=int(split_day))]
                if before.empty:
                    continue
                pop = before["exp_val"].mean()
                g = before.groupby("batter")["exp_val"].agg(raw="mean", n="size").reset_index()
                g["spray_adj_xwobacon"] = (g["n"] * g["raw"] + K_SHRINK * pop) / (g["n"] + K_SHRINK)
                g["year"], g["split_day"], g["_pop"] = yr, int(split_day), pop
                out.append(g[["batter", "year", "split_day", "spray_adj_xwobacon", "_pop"]])
            print(f"  built {yr}", flush=True)
        sa = pd.concat(out, ignore_index=True)
        merged = rolling.merge(sa[["batter", "year", "split_day", "spray_adj_xwobacon"]],
                               on=["batter", "year", "split_day"], how="left")
        pops = sa.drop_duplicates(["year", "split_day"]).set_index(["year", "split_day"])["_pop"]
        key = list(zip(merged["year"], merged["split_day"]))
        merged["spray_adj_xwobacon"] = merged["spray_adj_xwobacon"].fillna(
            pd.Series(pops.reindex(key).values, index=merged.index))
        return merged

    H.load_and_prep_rh3_inputs = patched_loader
    result = H.run_candidate_eval(
        candidate="spray_adj_xwobacon", expected_sign="+",
        pre_reg_path=ROOT / "data" / "research" / "validation_runs" / "spray_adj_xwobacon_2026-07-19.md",
    )
    print("\n--- SUMMARY ---")
    print(f"  Dr: {result['delta_r']:+.4f}  per-year +: {result['positives']}/7  "
          f"holdout +: {result['holdout_positives']}/{result['holdout_total']}  "
          f"sign: {'OK' if result['sign_ok'] else 'WRONG'}")


if __name__ == "__main__":
    main()
