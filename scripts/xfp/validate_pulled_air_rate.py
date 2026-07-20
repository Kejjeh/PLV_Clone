# Pre-registered: data/research/validation_runs/pulled_air_rate_2026-07-19.md
"""pulled_air_rate as an rh3 candidate — as-of pulled-air-ball share, k=40 shrinkage.

Deep-research campaign Wave 1A (ledger: registry 2026-07-19). Two pre-declared cells:
  1A-1 pulled_air_rate_to_sh (main effect)
  1A-2 pulled_air_x_midpow (interaction with middle hard_hit_pct_to_sh tercile)
Exploits xwOBA's direction-blindness: no RH3_FEATS feature sees spray angle.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_pulled_air_rate.py [--sanity-only]
"""
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
AIR_LA_MIN = 10.0
PULL_SPRAY_MAX = -15.0  # handedness-adjusted degrees; more negative = more pulled

SEASON_STARTS = {
    2018: "2018-03-29", 2019: "2019-03-20", 2020: "2020-07-23",
    2021: "2021-04-01", 2022: "2022-04-07", 2023: "2023-03-30",
    2024: "2024-03-28", 2025: "2025-03-27", 2026: "2026-03-26",
}


def load_bbe(year: int) -> pd.DataFrame:
    sc = pd.read_parquet(
        CACHE / f"statcast_{year}.parquet",
        columns=["batter", "game_date", "type", "launch_angle", "hc_x", "hc_y", "stand"],
    )
    sc = sc[(sc["type"] == "X") & sc["hc_x"].notna() & sc["hc_y"].notna() & sc["batter"].notna()].copy()
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    # Spray angle: 0 = up the middle; negative = toward LF line (pull for RHB).
    phi = np.degrees(np.arctan2(sc["hc_x"].astype(float) - 125.42, 198.27 - sc["hc_y"].astype(float)))
    # Handedness-adjust so NEGATIVE = pull side for everyone.
    sc["adj_spray"] = np.where(sc["stand"] == "R", -phi, phi)
    # NOTE sign: for RHB pull is LF (phi < 0) -> adj = -phi > 0... flip so pulled is negative:
    sc["adj_spray"] = -sc["adj_spray"]
    la = sc["launch_angle"].astype(float)
    sc["is_pulled_air"] = ((la >= AIR_LA_MIN) & (sc["adj_spray"] <= PULL_SPRAY_MAX)).astype(int)
    return sc[["batter", "game_date", "is_pulled_air"]]


def build_frame(grid: pd.DataFrame) -> pd.DataFrame:
    out = []
    for year, splits in grid.groupby("year")["split_day"]:
        start = pd.Timestamp(SEASON_STARTS[int(year)])
        path = CACHE / f"statcast_{int(year)}.parquet"
        if not path.exists():
            continue
        bbe = load_bbe(int(year))
        for split_day in sorted(splits.unique()):
            cutoff = start + pd.Timedelta(days=int(split_day))
            before = bbe[bbe["game_date"] <= cutoff]
            if before.empty:
                continue
            pop = before["is_pulled_air"].mean()
            g = before.groupby("batter")["is_pulled_air"].agg(raw="mean", n_bbe="size").reset_index()
            g["pulled_air_rate_to_sh"] = (g["n_bbe"] * g["raw"] + K_SHRINK * pop) / (g["n_bbe"] + K_SHRINK)
            g["year"] = int(year)
            g["split_day"] = int(split_day)
            g["_pop"] = pop
            out.append(g[["batter", "year", "split_day", "pulled_air_rate_to_sh", "_pop"]])
        print(f"  pulled_air built for {int(year)} ({splits.nunique()} splits)", flush=True)
    return pd.concat(out, ignore_index=True)


def sanity_check() -> None:
    """2024 full-season: league share + known-profile ordering."""
    bbe = load_bbe(2024)
    league = bbe["is_pulled_air"].mean()
    print(f"[sanity] 2024 league pulled-air share of BBE: {league:.3f} (published ~0.175)")
    g = bbe.groupby("batter")["is_pulled_air"].agg(rate="mean", n="size")
    g = g[g["n"] >= 200].sort_values("rate", ascending=False)
    names = pd.read_parquet(CACHE / "boxscore_hitters.parquet", columns=["mlbam_id", "player_name"])
    nm = names.drop_duplicates("mlbam_id").set_index("mlbam_id")["player_name"]
    top = [(nm.get(b, str(b)), f"{r:.3f}") for b, r in g["rate"].head(8).items()]
    bot = [(nm.get(b, str(b)), f"{r:.3f}") for b, r in g["rate"].tail(8).items()]
    print("[sanity] top-8 pulled-air 2024 (expect Paredes-type pull-power names):", top)
    print("[sanity] bottom-8 (expect slap/oppo profiles):", bot)


def main() -> None:
    print("=== /validate-feature: pulled_air_rate (rh3, Wave 1A, 2 cells) ===")
    sanity_check()
    if "--sanity-only" in sys.argv:
        return

    orig_loader = H.load_and_prep_rh3_inputs

    def patched_loader():
        rolling = orig_loader()
        grid = rolling[["year", "split_day"]].drop_duplicates()
        pa = build_frame(grid)
        merged = rolling.merge(
            pa[["batter", "year", "split_day", "pulled_air_rate_to_sh"]],
            on=["batter", "year", "split_day"], how="left",
        )
        pops = pa.drop_duplicates(["year", "split_day"]).set_index(["year", "split_day"])["_pop"]
        key = list(zip(merged["year"], merged["split_day"]))
        merged["pulled_air_rate_to_sh"] = merged["pulled_air_rate_to_sh"].fillna(
            pd.Series(pops.reindex(key).values, index=merged.index)
        )
        # Cell 1A-2: interaction with middle hard_hit tercile (within year, split_day)
        def midpow_flag(df):
            t = df["hard_hit_pct_to_sh"].rank(pct=True)
            return ((t >= 1 / 3) & (t < 2 / 3)).astype(float)
        merged["_midpow"] = (
            merged.groupby(["year", "split_day"], group_keys=False)
            .apply(midpow_flag, include_groups=False)
        )
        merged["pulled_air_x_midpow"] = merged["pulled_air_rate_to_sh"] * merged["_midpow"]
        return merged

    H.load_and_prep_rh3_inputs = patched_loader

    prereg = ROOT / "data" / "research" / "validation_runs" / "pulled_air_rate_2026-07-19.md"
    for cell, cand in [("1A-1", "pulled_air_rate_to_sh"), ("1A-2", "pulled_air_x_midpow")]:
        print(f"\n{'='*70}\n=== CELL {cell}: {cand} ===\n{'='*70}")
        result = H.run_candidate_eval(candidate=cand, expected_sign="+", pre_reg_path=prereg)
        print(f"\n--- CELL {cell} SUMMARY ---")
        print(f"  baseline r: {result['baseline_r']:.4f}  extended r: {result['candidate_r']:.4f}")
        print(f"  Dr: {result['delta_r']:+.4f}  per-year +: {result['positives']}/7  "
              f"holdout +: {result['holdout_positives']}/{result['holdout_total']}  "
              f"sign: {'OK' if result['sign_ok'] else 'WRONG'}")


if __name__ == "__main__":
    main()
