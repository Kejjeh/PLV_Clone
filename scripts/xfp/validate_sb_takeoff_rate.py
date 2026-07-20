# Pre-registered: data/research/validation_runs/sb_takeoff_rate_2026-07-19.md
"""sb_takeoff_rate (rh3, Wave 3A) — opportunity-normalized steal propensity.

Runner-level takeoff rate from statcast pitch-level base-state transitions
(no MLB-API PBP pull needed). Single declared cell vs full RH3_FEATS.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_sb_takeoff_rate.py [--sanity-only]
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
K_SHRINK = 15.0

SEASON_STARTS = {
    2018: "2018-03-29", 2019: "2019-03-20", 2020: "2020-07-23",
    2021: "2021-04-01", 2022: "2022-04-07", 2023: "2023-03-30",
    2024: "2024-03-28", 2025: "2025-03-27", 2026: "2026-03-26",
}


def runner_events(year: int) -> pd.DataFrame:
    """One row per steal OPPORTUNITY: (runner, game_date, go 0/1)."""
    sc = pd.read_parquet(
        CACHE / f"statcast_{year}.parquet",
        columns=["game_pk", "at_bat_number", "pitch_number", "game_date",
                 "on_1b", "on_2b", "on_3b", "events"],
    )
    sc = sc.dropna(subset=["game_pk", "at_bat_number", "pitch_number"]).copy()
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    sc = sc.sort_values(["game_pk", "at_bat_number", "pitch_number"])

    grp = sc.groupby(["game_pk", "at_bat_number"], observed=True)
    # NOTE: GroupBy.first()/.last() skip NaN per-column (would backfill a mid-PA
    # steal arrival into the PA-start state) — use true first/last ROWS instead.
    key = ["game_pk", "at_bat_number"]
    first = (sc.drop_duplicates(subset=key, keep="first")
             .set_index(key)[["on_1b", "on_2b", "game_date"]])
    npitch = grp.size().rename("n_pitch")
    last = (sc.drop_duplicates(subset=key, keep="last")
            .set_index(key)[["on_1b", "on_2b", "on_3b"]].add_suffix("_last"))
    cs = grp["events"].apply(lambda s: s.eq("caught_stealing_2b").any()).rename("cs2")

    pa = first.join([npitch, last, cs])
    opp = pa[pa["on_1b"].notna() & pa["on_2b"].isna()].copy()
    r = opp["on_1b"]

    # advanced: runner appears on 2B/3B at any later pitch → detect via per-PA sets
    adv2 = grp["on_2b"].agg(lambda s: set(s.dropna())).rename("set2")
    adv3 = grp["on_3b"].agg(lambda s: set(s.dropna())).rename("set3")
    opp = opp.join([adv2, adv3])
    advanced = [
        (rr in s2 or rr in s3)
        for rr, s2, s3 in zip(r, opp["set2"], opp["set3"])
    ]
    vanished = (
        (opp["n_pitch"] >= 2)
        & opp["on_1b_last"].ne(r).fillna(True)
        & opp["on_2b_last"].ne(r).fillna(True)
        & opp["on_3b_last"].ne(r).fillna(True)
    )
    go = pd.Series(advanced, index=opp.index) | vanished.fillna(False) | opp["cs2"].fillna(False)
    opp["go"] = go.astype(bool).astype(int)
    out = opp.reset_index()[["on_1b", "game_date", "go"]].rename(columns={"on_1b": "batter"})
    out["batter"] = out["batter"].astype("int64")
    return out


def sanity() -> None:
    ev = runner_events(2024)
    print(f"[sanity] 2024 opportunities: {len(ev)}, league takeoff rate: {ev['go'].mean():.3f}")
    g = ev.groupby("batter")["go"].agg(rate="mean", n="size")
    g = g[g["n"] >= 60].sort_values("rate", ascending=False)
    names = pd.read_parquet(CACHE / "boxscore_hitters.parquet", columns=["mlbam_id", "player_name"])
    nm = names.drop_duplicates("mlbam_id").set_index("mlbam_id")["player_name"]
    print("[sanity] top-8 takeoff 2024:", [(nm.get(b, b), f"{r:.2f}") for b, r in g["rate"].head(8).items()])
    print("[sanity] bottom-8:", [(nm.get(b, b), f"{r:.2f}") for b, r in g["rate"].tail(8).items()])


def main() -> None:
    print("=== /validate-feature: sb_takeoff_rate (rh3, Wave 3A) ===")
    sanity()
    if "--sanity-only" in sys.argv:
        return

    orig_loader = H.load_and_prep_rh3_inputs

    def patched_loader():
        rolling = orig_loader()
        grid = rolling[["year", "split_day"]].drop_duplicates()
        out = []
        for year, splits in grid.groupby("year")["split_day"]:
            yr = int(year)
            if not (CACHE / f"statcast_{yr}.parquet").exists():
                continue
            ev = runner_events(yr)
            start = pd.Timestamp(SEASON_STARTS[yr])
            for split_day in sorted(splits.unique()):
                b = ev[ev["game_date"] <= start + pd.Timedelta(days=int(split_day))]
                if b.empty:
                    continue
                pop = b["go"].mean()
                g = b.groupby("batter")["go"].agg(raw="mean", n="size").reset_index()
                g["sb_takeoff_rate_to_sh"] = (g["n"] * g["raw"] + K_SHRINK * pop) / (g["n"] + K_SHRINK)
                g["year"], g["split_day"], g["_pop"] = yr, int(split_day), pop
                out.append(g[["batter", "year", "split_day", "sb_takeoff_rate_to_sh", "_pop"]])
            print(f"  takeoff built {yr}", flush=True)
        tk = pd.concat(out, ignore_index=True)
        merged = rolling.merge(tk[["batter", "year", "split_day", "sb_takeoff_rate_to_sh"]],
                               on=["batter", "year", "split_day"], how="left")
        pops = tk.drop_duplicates(["year", "split_day"]).set_index(["year", "split_day"])["_pop"]
        key = list(zip(merged["year"], merged["split_day"]))
        merged["sb_takeoff_rate_to_sh"] = merged["sb_takeoff_rate_to_sh"].fillna(
            pd.Series(pops.reindex(key).values, index=merged.index))
        return merged

    H.load_and_prep_rh3_inputs = patched_loader
    result = H.run_candidate_eval(
        candidate="sb_takeoff_rate_to_sh", expected_sign="+",
        pre_reg_path=ROOT / "data" / "research" / "validation_runs" / "sb_takeoff_rate_2026-07-19.md",
    )
    print("\n--- SUMMARY ---")
    print(f"  Dr: {result['delta_r']:+.4f}  per-year +: {result['positives']}/7  "
          f"holdout +: {result['holdout_positives']}/{result['holdout_total']}  "
          f"sign: {'OK' if result['sign_ok'] else 'WRONG'}")


if __name__ == "__main__":
    main()
