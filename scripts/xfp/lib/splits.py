"""splits — platoon (vs L/R) handedness lens.

The audit (2026-06-21) found platoon splits were the #1 missing lens: hitter
handedness data existed (data/outputs/hitter_handedness.csv) but dead-ended in a
legacy path, and the PITCHER vs-LHB/RHB split did not exist at all. This is the
one home for both, plus the pure split-math core.

CONTEXT-ONLY lens (feedback #13): a platoon edge informs daily start/sit and
matchup reads; it NEVER moves the rh3/rp3 headline. Sample-adequacy is surfaced
explicitly so a 20-PA "split" is not mistaken for a real one.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT

OUT = ROOT / "data" / "outputs"
CACHE = ROOT / "data" / "research" / "xfp_cache"
HITTER_HANDEDNESS = OUT / "hitter_handedness.csv"

_K_EVENTS = {"strikeout", "strikeout_double_play"}


def _rate(value, pa):
    return (value / pa) if pa else None


def platoon_split(vs_l: dict, vs_r: dict, *, pa_floor: int = 50) -> dict:
    """Pure platoon read from per-side {pa, value} (value = summed metric, e.g.
    xwOBA*PA). Returns rates, combined rate, lift% vs combined, sample-adequacy
    flags, and the dominant side. A side with 0 PA -> rate None / sample False.
    """
    pa_l, pa_r = vs_l.get("pa", 0) or 0, vs_r.get("pa", 0) or 0
    rate_l, rate_r = _rate(vs_l.get("value", 0), pa_l), _rate(vs_r.get("value", 0), pa_r)
    tot_pa = pa_l + pa_r
    combined = _rate((vs_l.get("value", 0) or 0) + (vs_r.get("value", 0) or 0), tot_pa)

    def lift(rate):
        if rate is None or not combined:
            return None
        return (rate / combined - 1.0) * 100.0

    if rate_l is not None and rate_r is not None:
        dominant = "L" if rate_l > rate_r else "R"
    elif rate_l is not None:
        dominant = "L"
    elif rate_r is not None:
        dominant = "R"
    else:
        dominant = None
    return {
        "rate_vs_L": rate_l, "rate_vs_R": rate_r, "combined": combined,
        "pa_vs_L": pa_l, "pa_vs_R": pa_r,
        "lift_vs_L_pct": lift(rate_l), "lift_vs_R_pct": lift(rate_r),
        "sample_ok_L": pa_l >= pa_floor, "sample_ok_R": pa_r >= pa_floor,
        "dominant_side": dominant,
    }


def hitter_platoon(batter_id: int, hh_df: pd.DataFrame | None = None,
                   pa_floor: int = 50) -> dict | None:
    """Hitter platoon from the prebuilt handedness CSV (xwOBA-rate vs L/R)."""
    if hh_df is None:
        if not HITTER_HANDEDNESS.exists():
            return None
        hh_df = pd.read_csv(HITTER_HANDEDNESS)
    row = hh_df[hh_df["batter"] == batter_id]
    if row.empty:
        return None
    r = row.iloc[0]
    return platoon_split(
        {"pa": float(r.get("pa_vs_L", 0) or 0), "value": float(r.get("rate_vs_L", 0) or 0) * float(r.get("pa_vs_L", 0) or 0)},
        {"pa": float(r.get("pa_vs_R", 0) or 0), "value": float(r.get("rate_R", 0) or 0) * float(r.get("pa_vs_R", 0) or 0)},
        pa_floor=pa_floor,
    )


def sp_platoon(pitcher_id: int, statcast_df: pd.DataFrame | None = None,
               pa_floor: int = 40) -> dict | None:
    """Pitcher platoon (xwOBA-ALLOWED vs LHB/RHB) computed from statcast, grouped
    by batter stand. Lower allowed-rate is better — read dominant_side as the
    handedness the pitcher suppresses LESS (the side to attack)."""
    if statcast_df is None:
        p = CACHE / "statcast_2026.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=["pitcher", "stand", "events",
                                                  "estimated_woba_using_speedangle"])
    d = statcast_df[(statcast_df["pitcher"] == pitcher_id)
                    & statcast_df["events"].notna() & (statcast_df["events"] != "")]
    if d.empty:
        return None

    def side(stand):
        s = d[d["stand"] == stand]
        return {"pa": len(s),
                "value": float(s["estimated_woba_using_speedangle"].fillna(0).sum())}
    return platoon_split(side("L"), side("R"), pa_floor=pa_floor)
