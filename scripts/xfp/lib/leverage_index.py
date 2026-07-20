"""leverage_index.py — empirical Leverage Index table from local statcast PBP.

LI(state) = E[|ΔWP(batting team)| over the next PA from this state], normalized so
the league-average PA has LI = 1.0 — Tango's definition, estimated empirically from
our own 2018–2023 (ex-2020) statcast play-by-play rather than embedding a published
table. The table is FROZEN on those years and applied to all seasons (state-level
population structure, no player information → leakage-safe for validation).

State key: (inning capped at 9, topbot, outs, base_code 0–7, score diff clipped ±5,
from the batting team's perspective). Sparse states fall back to the coarse key
(inning_c, topbot, diff_c), then to 1.0.

Cache: data/research/xfp_cache/li_table_empirical.parquet (delete to rebuild).

Built 2026-07-19 for the gmli_todate validation campaign (Wave 1B).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "research" / "xfp_cache"
TABLE_PATH = CACHE / "li_table_empirical.parquet"
TABLE_YEARS = (2018, 2019, 2021, 2022, 2023)
MIN_STATE_N = 200

STATE_COLS = ["inning_c", "is_top", "outs", "base_code", "diff_c"]
_PA_COLS = [
    "game_pk", "at_bat_number", "inning", "inning_topbot", "outs_when_up",
    "on_1b", "on_2b", "on_3b", "bat_score", "fld_score",
    "post_home_score", "post_away_score", "home_score", "away_score",
]


def _pa_states(year: int) -> pd.DataFrame:
    """One row per PA: state at PA start + batting-team win outcome."""
    sc = pd.read_parquet(CACHE / f"statcast_{year}.parquet", columns=_PA_COLS)
    sc = sc.dropna(subset=["game_pk", "at_bat_number", "inning"]).copy()
    # first pitch row of each PA carries the PA-start state
    pa = sc.sort_index().groupby(["game_pk", "at_bat_number"], observed=True).first().reset_index()

    pa["inning_c"] = pa["inning"].clip(upper=9).astype(int)
    pa["is_top"] = (pa["inning_topbot"] == "Top").astype(int)
    pa["outs"] = pa["outs_when_up"].fillna(0).astype(int).clip(0, 2)
    pa["base_code"] = (
        pa["on_1b"].notna().astype(int)
        + 2 * pa["on_2b"].notna().astype(int)
        + 4 * pa["on_3b"].notna().astype(int)
    )
    pa["diff_c"] = (pa["bat_score"] - pa["fld_score"]).clip(-5, 5).astype(int)

    # final score → batting-team win
    last = (
        sc.sort_values("at_bat_number").groupby("game_pk", observed=True)
        [["post_home_score", "post_away_score"]].last().reset_index()
    )
    last["home_win"] = (last["post_home_score"] > last["post_away_score"]).astype(int)
    pa = pa.merge(last[["game_pk", "home_win"]], on="game_pk", how="left")
    pa["bat_win"] = np.where(pa["is_top"] == 1, 1 - pa["home_win"], pa["home_win"])
    return pa.sort_values(["game_pk", "at_bat_number"]).reset_index(drop=True)


def build_li_table(years: tuple[int, ...] = TABLE_YEARS, force: bool = False) -> pd.DataFrame:
    if TABLE_PATH.exists() and not force:
        return pd.read_parquet(TABLE_PATH)

    frames = [_pa_states(y) for y in years]
    pa = pd.concat(frames, ignore_index=True)

    # WP(state) from the batting team's perspective
    wp = pa.groupby(STATE_COLS, observed=True)["bat_win"].agg(wp="mean", n="size").reset_index()
    coarse = pa.groupby(["inning_c", "is_top", "diff_c"], observed=True)["bat_win"].mean().rename("wp_coarse")
    wp = wp.merge(coarse.reset_index(), on=["inning_c", "is_top", "diff_c"], how="left")
    wp["wp_use"] = np.where(wp["n"] >= MIN_STATE_N, wp["wp"], wp["wp_coarse"])
    wp_map = wp.set_index(STATE_COLS)["wp_use"]

    # per-PA |ΔWP| for the CURRENT batting team
    pa["wp_now"] = wp_map.reindex(pd.MultiIndex.from_frame(pa[STATE_COLS])).values
    nxt = pa.groupby("game_pk", observed=True)[STATE_COLS + ["wp_now"]].shift(-1)
    same_half = nxt["is_top"] == pa["is_top"]
    wp_next_for_batter = np.where(same_half, nxt["wp_now"], 1.0 - nxt["wp_now"])
    # game-ending PA: outcome is the realized win
    wp_next_for_batter = np.where(nxt["wp_now"].isna(), pa["bat_win"].astype(float), wp_next_for_batter)
    pa["abs_dwp"] = (pd.Series(wp_next_for_batter, index=pa.index) - pa["wp_now"]).abs()

    li = pa.groupby(STATE_COLS, observed=True)["abs_dwp"].agg(mean_dwp="mean", n="size").reset_index()
    global_mean = pa["abs_dwp"].mean()
    li["li"] = li["mean_dwp"] / global_mean
    li_coarse = pa.groupby(["inning_c", "is_top", "diff_c"], observed=True)["abs_dwp"].mean() / global_mean
    li = li.merge(li_coarse.rename("li_coarse").reset_index(), on=["inning_c", "is_top", "diff_c"], how="left")
    li["li_use"] = np.where(li["n"] >= MIN_STATE_N, li["li"], li["li_coarse"])

    out = li[STATE_COLS + ["li_use", "n"]].rename(columns={"li_use": "li"})
    out.to_parquet(TABLE_PATH, index=False)
    return out


def li_lookup(states: pd.DataFrame, table: pd.DataFrame | None = None) -> pd.Series:
    """Vectorized LI for a frame with STATE_COLS; fallback coarse → 1.0."""
    t = table if table is not None else build_li_table()
    fine = t.set_index(STATE_COLS)["li"]
    coarse = t.groupby(["inning_c", "is_top", "diff_c"], observed=True)["li"].mean()
    vals = fine.reindex(pd.MultiIndex.from_frame(states[STATE_COLS])).to_numpy(copy=True)
    miss = pd.isna(vals)
    if miss.any():
        ck = pd.MultiIndex.from_frame(states.loc[miss, ["inning_c", "is_top", "diff_c"]])
        vals[miss] = coarse.reindex(ck).fillna(1.0).to_numpy()
    return pd.Series(vals, index=states.index, name="li")
