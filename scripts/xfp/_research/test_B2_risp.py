"""
Test B2 — RISP / leverage check (confirmation).
Compute (RISP xwoba) minus (overall xwoba) per batter-year. Test YoY stability.
"""

from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

ROOT = "c:/Users/Joshua/plv_clone"
STATCAST_GLOB = f"{ROOT}/data/research/xfp_cache/statcast_*.parquet"
OUT = f"{ROOT}/scripts/xfp/_research/test_B2_results.json"


def main():
    paths = sorted(glob.glob(STATCAST_GLOB))
    paths = [p for p in paths if "bak" not in p.lower()]
    out = []
    for path in paths:
        norm_p = path.replace("\\", "/")
        year_str = norm_p.split("statcast_")[1].split(".")[0]
        try:
            year = int(year_str)
        except ValueError:
            continue
        if year < 2018:
            continue
        print(f"  reading {year}...")
        cols = ["batter", "on_2b", "on_3b", "woba_denom", "estimated_woba_using_speedangle"]
        d = ds.dataset(path).to_table(columns=cols).to_pandas()
        d = d[d["woba_denom"] == 1].copy()
        d["risp"] = d["on_2b"].notna() | d["on_3b"].notna()
        # Overall
        all_agg = d.groupby("batter").agg(pa=("woba_denom", "count"),
                                          xwoba=("estimated_woba_using_speedangle", "mean")).reset_index()
        risp_agg = d[d["risp"]].groupby("batter").agg(pa_risp=("woba_denom", "count"),
                                                      xwoba_risp=("estimated_woba_using_speedangle", "mean")).reset_index()
        m = all_agg.merge(risp_agg, on="batter", how="inner")
        m["year"] = year
        out.append(m)
    big = pd.concat(out, ignore_index=True)
    # Require at least 60 RISP PA
    big = big[(big["pa_risp"] >= 60) & (big["pa"] >= 200)].copy()
    big["clutch"] = big["xwoba_risp"] - big["xwoba"]

    # YoY
    p = big[["batter", "year", "clutch"]].dropna()
    p2 = p.copy()
    p2["year"] = p2["year"] - 1
    p2 = p2.rename(columns={"clutch": "clutch_next"})
    merged = p.merge(p2, on=["batter", "year"], how="inner")
    r = float(merged["clutch"].corr(merged["clutch_next"])) if len(merged) >= 30 else None
    print(f"RISP-overall xwoba 'clutch' YoY r = {r}, n_pairs = {len(merged)}")

    results = {
        "n_panel": int(len(big)),
        "yoy_clutch_r": r,
        "n_pairs": int(len(merged)),
        "mean_clutch": float(big["clutch"].mean()),
        "std_clutch": float(big["clutch"].std()),
    }
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
