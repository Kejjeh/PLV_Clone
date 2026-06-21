"""expected_stats — expected-vs-actual (luck) lens.

The depth audit (2026-06-21) found xwOBA/xwOBACON are computed internally and
drive rh3/sustainability, but are never DISPLAYED as an expected-vs-actual
percentile panel — the canonical "is this real or luck" view. Only the external
/savant-compare WebFetch showed it. This is the one internal home.

xwOBA is built the standard way: estimated_woba_using_speedangle on balls in
play, the actual woba_value on non-BIP outcomes (BB/HBP/K), over woba_denom.
The gap (actual wOBA − xwOBA) sizes regression. CONTEXT-ONLY (feedback #13): it
informs conviction / regression direction, it never moves rh3/rp3.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT

CACHE = ROOT / "data" / "research" / "xfp_cache"


def expected_vs_actual(xwoba, woba, *, pctl=None, luck_threshold: float = 0.020) -> dict:
    """Pure: compare expected (xwoba) to actual (woba).

    gap = woba − xwoba (positive = overperforming / due for negative regression;
    negative = underperforming / bounce due). Returns regression tier + optional
    xwoba percentile. None-safe.
    """
    if xwoba is None or woba is None:
        return {"xwoba": xwoba, "woba": woba, "gap": None,
                "regression": "UNKNOWN", "xwoba_pctl": pctl}
    gap = woba - xwoba
    if gap > luck_threshold:
        reg = "OVERPERFORMING"
    elif gap < -luck_threshold:
        reg = "UNDERPERFORMING"
    else:
        reg = "ALIGNED"
    return {"xwoba": xwoba, "woba": woba, "gap": gap,
            "regression": reg, "xwoba_pctl": pctl}


def _xwoba_woba(df: pd.DataFrame) -> tuple:
    """(xwoba, woba, denom) over a set of PA rows. xwOBA = estimated on BIP +
    actual woba_value on non-BIP, all over woba_denom."""
    pa = df[df["events"].notna() & (df["events"] != "")]
    denom = pa["woba_denom"].fillna(0).sum()
    if denom <= 0:
        return None, None, 0
    bip = pa["estimated_woba_using_speedangle"].notna()
    x_num = (pa.loc[bip, "estimated_woba_using_speedangle"].sum()
             + pa.loc[~bip, "woba_value"].fillna(0).sum())
    woba = pa["woba_value"].fillna(0).sum() / denom
    return x_num / denom, woba, int(denom)


_COLS = ["batter", "pitcher", "events", "woba_value", "woba_denom",
         "estimated_woba_using_speedangle"]


def _population_pctl(values: pd.Series, v: float) -> int | None:
    if v is None or values.empty:
        return None
    return int(round((values < v).mean() * 100))


def hitter_expected(batter_id: int, statcast_df: pd.DataFrame | None = None,
                    pa_floor: int = 50) -> dict | None:
    if statcast_df is None:
        p = CACHE / "statcast_2026.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS)
    d = statcast_df[statcast_df["batter"] == batter_id]
    xw, wo, denom = _xwoba_woba(d)
    if xw is None or denom < pa_floor:
        return None
    return expected_vs_actual(float(round(xw, 3)), float(round(wo, 3)))


def sp_expected(pitcher_id: int, statcast_df: pd.DataFrame | None = None,
                bf_floor: int = 80) -> dict | None:
    """Expected-vs-actual wOBA-ALLOWED for a pitcher (lower xwoba = better)."""
    if statcast_df is None:
        p = CACHE / "statcast_2026.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS)
    d = statcast_df[statcast_df["pitcher"] == pitcher_id]
    xw, wo, denom = _xwoba_woba(d)
    if xw is None or denom < bf_floor:
        return None
    # For pitchers, OVERPERFORMING = allowing LESS than expected (lucky) — flip sign
    r = expected_vs_actual(float(round(xw, 3)), float(round(wo, 3)))
    if r["gap"] is not None:
        r["regression"] = ("OVERPERFORMING" if r["gap"] < -0.020
                           else "UNDERPERFORMING" if r["gap"] > 0.020 else "ALIGNED")
    return r
