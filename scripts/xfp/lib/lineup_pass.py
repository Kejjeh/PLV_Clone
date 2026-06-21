"""lineup_pass — times-through-order (TTO) decay lens.

A starter's core_fp/PA on the 3rd time through the order vs the 1st: the
within-start durability complement to sp_floor's per-start bust model. The data
(data/outputs/sp_lineup_pass.csv) existed but was orphaned in legacy dashboards;
this surfaces it on the SP card.

NOTE: rates are pitcher-side core_fp/PA = K − (TB+BB+HBP) — NEGATIVE numbers,
lower = worse, NOT the rh3/rp3 FP scale. The CSV is a career-static snapshot
(rebuilt by hand via sp_lineup_pass.py, not the daily refresh). Context-only
(CLAUDE.md #13): TTO informs bench-priority/durability, it never moves rp3.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT

LINEUP_PASS = ROOT / "data" / "outputs" / "sp_lineup_pass.csv"


def tto_decay(tto1_rate, tto3_rate, tto3_pa, *, pa_floor: int = 100,
              penalty_threshold: float = -0.05) -> dict:
    """Pure: 3rd-time-through decay from 1st/3rd-pass rates + 3rd-pass PA.

    penalty = tto3_rate − tto1_rate (negative = worse the 3rd time through).
    tier: STEEP_DECAY (<= 2×threshold) / DECAY (<= threshold) /
          DURABLE (>= −threshold) / AVERAGE (in between). None-safe.
    """
    if tto1_rate is None or tto3_rate is None or tto3_pa is None:
        return {"tto1_rate": tto1_rate, "tto3_rate": tto3_rate,
                "tto3_pa": tto3_pa, "penalty": None,
                "tier": "UNKNOWN", "sample_ok": False}
    penalty = tto3_rate - tto1_rate
    if penalty <= 2 * penalty_threshold:
        tier = "STEEP_DECAY"
    elif penalty <= penalty_threshold:
        tier = "DECAY"
    elif penalty >= -penalty_threshold:
        tier = "DURABLE"
    else:
        tier = "AVERAGE"
    return {"tto1_rate": tto1_rate, "tto3_rate": tto3_rate, "tto3_pa": tto3_pa,
            "penalty": penalty, "tier": tier, "sample_ok": tto3_pa >= pa_floor}


def _f(v):
    return float(v) if v is not None and pd.notna(v) else None


def sp_lineup_pass(pitcher_id: int, lp_df: pd.DataFrame | None = None,
                   pa_floor: int = 100) -> dict | None:
    """TTO decay for one SP from the lineup-pass CSV (career-static snapshot)."""
    if lp_df is None:
        if not LINEUP_PASS.exists():
            return None
        lp_df = pd.read_csv(LINEUP_PASS)
    row = lp_df[lp_df["pitcher"] == pitcher_id]
    if row.empty:
        return None
    r = row.iloc[0]
    return tto_decay(_f(r.get("tto1_rate")), _f(r.get("tto3_rate")),
                     _f(r.get("tto3_pa")), pa_floor=pa_floor)
