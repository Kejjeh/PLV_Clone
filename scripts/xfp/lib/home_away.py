"""home_away — home/road split lens.

Derived purely from statcast inning_topbot (NO team join needed): a HITTER bats
at home in the 'Bot' half; a PITCHER pitches at home in the 'Top' half. xwOBA is
built with the same construction as expected_stats; the split math reuses the
tested splits.platoon_split core (home↔L / away↔R relabel). Context-only
(CLAUDE.md #13) — park/home-away was validate-tested and NOT promoted as a
ranker, so this is display/context only.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT
from .splits import platoon_split
from .expected_stats import _xwoba_woba

CACHE = ROOT / "data" / "research" / "xfp_cache"
_COLS = ["batter", "pitcher", "events", "inning_topbot",
         "woba_value", "woba_denom", "estimated_woba_using_speedangle"]
_DOM = {"L": "HOME", "R": "AWAY", None: None}


def home_away_split(home: dict, away: dict, *, pa_floor: int = 50) -> dict:
    """home/away each {pa, value} → relabeled platoon_split (HOME↔L, AWAY↔R)."""
    r = platoon_split(home, away, pa_floor=pa_floor)
    return {
        "rate_home": r["rate_vs_L"], "rate_away": r["rate_vs_R"], "combined": r["combined"],
        "pa_home": r["pa_vs_L"], "pa_away": r["pa_vs_R"],
        "lift_home_pct": r["lift_vs_L_pct"], "lift_away_pct": r["lift_vs_R_pct"],
        "sample_ok_home": r["sample_ok_L"], "sample_ok_away": r["sample_ok_R"],
        "dominant_side": _DOM[r["dominant_side"]],
    }


def _side_value(df: pd.DataFrame) -> dict:
    xw, _wo, denom = _xwoba_woba(df)
    return {"pa": denom, "value": (xw * denom) if xw is not None else 0}


def hitter_home_away(batter_id: int, statcast_df: pd.DataFrame | None = None,
                     pa_floor: int = 50) -> dict | None:
    if statcast_df is None:
        p = CACHE / "statcast_2026.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS)
    d = statcast_df[(statcast_df["batter"] == batter_id)
                    & statcast_df["events"].notna() & (statcast_df["events"] != "")]
    if d.empty:
        return None
    return home_away_split(_side_value(d[d["inning_topbot"] == "Bot"]),   # bats at home
                           _side_value(d[d["inning_topbot"] == "Top"]),   # road
                           pa_floor=pa_floor)


def sp_home_away(pitcher_id: int, statcast_df: pd.DataFrame | None = None,
                 pa_floor: int = 40) -> dict | None:
    if statcast_df is None:
        p = CACHE / "statcast_2026.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS)
    d = statcast_df[(statcast_df["pitcher"] == pitcher_id)
                    & statcast_df["events"].notna() & (statcast_df["events"] != "")]
    if d.empty:
        return None
    return home_away_split(_side_value(d[d["inning_topbot"] == "Top"]),   # pitches at home
                           _side_value(d[d["inning_topbot"] == "Bot"]),   # road
                           pa_floor=pa_floor)
