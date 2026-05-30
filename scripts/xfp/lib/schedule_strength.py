"""Next-14-day SP opponent offensive-strength index.

Source: `data/outputs/xfp_rp3_projections.csv` already carries a
`next2_avg_bat_index` column produced by the rp3 pipeline (mean opponent
offensive index over the SP's next ~2 turns). We piggyback on that so we
don't re-derive opponent strength here.

The index is normalised to a 0-1 scale within the current SP universe,
where 1.0 = facing the strongest offenses (hardest schedule) and 0.0 =
softest. If the source column is missing or empty, every SP gets `None`.
"""
from __future__ import annotations
import os
import pandas as pd

from .bucket_dispatch import PROJECTIONS

_CACHE: dict | None = None


def _build_index() -> dict:
    """Return a dict mapping pitcher_id (int) -> schedule_idx float in [0,1]."""
    path = PROJECTIONS.get('SP')
    if not path or not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    if 'next2_avg_bat_index' not in df.columns or 'pitcher' not in df.columns:
        return {}
    sub = df[['pitcher', 'next2_avg_bat_index']].dropna()
    if sub.empty:
        return {}
    lo = float(sub['next2_avg_bat_index'].min())
    hi = float(sub['next2_avg_bat_index'].max())
    if hi - lo < 1e-9:
        return {int(pid): 0.5 for pid in sub['pitcher']}
    out = {}
    for pid, raw in zip(sub['pitcher'], sub['next2_avg_bat_index']):
        out[int(pid)] = float((raw - lo) / (hi - lo))
    return out


def schedule_idx_for(pitcher_id) -> float | None:
    """Return 0-1 schedule strength for an SP, or None if not available."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _build_index()
    if not _CACHE:
        return None
    try:
        return _CACHE.get(int(pitcher_id))
    except (TypeError, ValueError):
        return None
