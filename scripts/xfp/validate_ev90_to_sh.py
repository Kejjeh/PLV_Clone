# Pre-registered: data/research/validation_runs/ev90_to_sh_2026-07-19.md
"""ev90_to_sh as an rh3 candidate — as-of 90th-pct exit velo, k=40 shrinkage.

Accelerated replacement for the recent_signal_tournament "re-run ~Aug" deferral:
full cross-year test against the complete RH3_FEATS baseline instead of waiting
for more 2026 anchors. Sibling candidate hardhit_season HALTED at Rule 9
(hard_hit_pct_to_sh + barrel_pct_to_sh already in RH3_FEATS) → single cell.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _validate_rh3_v3_helper as H  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
K_SHRINK = 40.0

SEASON_STARTS = {
    2018: "2018-03-29", 2019: "2019-03-20", 2020: "2020-07-23",
    2021: "2021-04-01", 2022: "2022-04-07", 2023: "2023-03-30",
    2024: "2024-03-28", 2025: "2025-03-27", 2026: "2026-03-26",
}


def build_ev90_frame(grid: pd.DataFrame) -> pd.DataFrame:
    """grid: unique (year, split_day) pairs needed. Returns (batter, year, split_day, ev90_to_sh)."""
    out = []
    for year, splits in grid.groupby("year")["split_day"]:
        start = pd.Timestamp(SEASON_STARTS[int(year)])
        path = CACHE / f"statcast_{int(year)}.parquet"
        if not path.exists():
            continue
        sc = pd.read_parquet(path, columns=["batter", "game_date", "launch_speed", "type"])
        sc = sc[(sc["type"] == "X") & sc["launch_speed"].notna() & sc["batter"].notna()].copy()
        sc["game_date"] = pd.to_datetime(sc["game_date"])
        sc["launch_speed"] = sc["launch_speed"].astype(float)
        for split_day in sorted(splits.unique()):
            cutoff = start + pd.Timedelta(days=int(split_day))
            before = sc[sc["game_date"] <= cutoff]
            if before.empty:
                continue
            pop = before["launch_speed"].quantile(0.9)
            g = before.groupby("batter")["launch_speed"].agg(
                ev90_raw=lambda s: s.quantile(0.9), n_bbe="size"
            ).reset_index()
            g["ev90_to_sh"] = (g["n_bbe"] * g["ev90_raw"] + K_SHRINK * pop) / (g["n_bbe"] + K_SHRINK)
            g["year"] = int(year)
            g["split_day"] = int(split_day)
            g["_pop"] = pop
            out.append(g[["batter", "year", "split_day", "ev90_to_sh", "_pop"]])
        print(f"  ev90 built for {int(year)} ({splits.nunique()} splits)", flush=True)
    return pd.concat(out, ignore_index=True)


def main() -> None:
    print("=== /validate-feature: ev90_to_sh (rh3 candidate, accelerated 2026-07-19) ===")
    orig_loader = H.load_and_prep_rh3_inputs

    def patched_loader():
        rolling = orig_loader()
        grid = rolling[["year", "split_day"]].drop_duplicates()
        ev = build_ev90_frame(grid)
        merged = rolling.merge(
            ev[["batter", "year", "split_day", "ev90_to_sh"]],
            on=["batter", "year", "split_day"], how="left",
        )
        # zero-BBE / unmatched rows -> as-of population mean for that (year, split_day)
        pops = ev.drop_duplicates(["year", "split_day"]).set_index(["year", "split_day"])["_pop"]
        key = list(zip(merged["year"], merged["split_day"]))
        merged["ev90_to_sh"] = merged["ev90_to_sh"].fillna(pd.Series(pops.reindex(key).values, index=merged.index))
        return merged

    H.load_and_prep_rh3_inputs = patched_loader

    result = H.run_candidate_eval(
        candidate="ev90_to_sh",
        expected_sign="+",
        pre_reg_path=ROOT / "data" / "research" / "validation_runs" / "ev90_to_sh_2026-07-19.md",
    )

    print("\n=== VERDICT SUMMARY ===")
    print(f"  baseline cross_year_r:     {result['baseline_r']:.4f}")
    print(f"  extended cross_year_r:     {result['candidate_r']:.4f}")
    print(f"  Dr (extended - baseline):  {result['delta_r']:+.4f}")
    print(f"  Per-year positives:        {result['positives']}/7")
    print(f"  Holdout (2024-25) positives: {result['holdout_positives']}/{result['holdout_total']}")
    print(f"  Coef sign sanity:          {'OK' if result['sign_ok'] else 'WRONG'}")

    if result["delta_r"] >= 0.005 and result["positives"] >= 5 and result["sign_ok"]:
        verdict = "PASS"
    elif 0.0 < result["delta_r"] < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
