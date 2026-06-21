"""Start-anchored SP archetype snapshots (Option A).

SPs pitch on an event cadence (~1 start / 5 days), so a calendar-weekly snapshot
grid produces redundant no-start weeks and collapses double-start weeks. This
module re-anchors SP snapshots on actual starts with an event-weighted trailing
last-N-starts window. Display/context only (Rule 13); isolated from the shared
rolling cache and the projection models.
"""
from __future__ import annotations


def _ratio(num, den):
    if num is None or not den:
        return None
    return num / den


def rates_from_counts(c):
    """Derive event-weighted rate metrics from windowed COUNT sums.

    Each rate is num/den over the window (so a heavy start dominates a light one
    correctly) — never a mean of per-start rates. Returns None for any metric
    whose denominator is absent/zero, so callers can skip missing components.
    """
    tbf = c.get("tbf", 0)
    pit = c.get("pitches", 0)
    bbe = c.get("bbe", 0)
    return {
        "k_pct":         _ratio(c.get("k"), tbf),
        "bb_pct":        _ratio(c.get("bb"), tbf),
        "hr_per_bf":     _ratio(c.get("hr"), tbf),
        "swstr_pct":     _ratio(c.get("swstr"), pit),
        "c_plus_swstr":  _ratio(c.get("csw"), pit),
        "avg_velo":      _ratio(c.get("fb_velo_sum"), c.get("fb_n")),
        "barrel_pct":    _ratio(c.get("barrels"), bbe),
        "hard_hit_pct":  _ratio(c.get("hard_hits"), bbe),
        "gb_pct":        _ratio(c.get("gb"), bbe),
        "xwoba_contact": _ratio(c.get("xwoba_sum"), bbe),
    }


_SWSTR = {"swinging_strike", "swinging_strike_blocked", "foul_tip"}
_K = {"strikeout", "strikeout_double_play"}


def starts_from_statcast(df, min_tbf=8):
    """Per-start raw COUNT dicts for one pitcher, from their statcast rows.

    Groups by ``game_date`` (one start per date) and emits the count fields
    ``rates_from_counts`` consumes. Filters relief cameos via ``min_tbf``.
    ``df`` must be a single pitcher's rows with the standard statcast columns.
    Returns a chronologically-sorted list of start dicts.
    """
    out = []
    for gd, g in sorted(df.groupby("game_date")):
        pa = g[g["events"].notna() & (g["events"] != "")]
        tbf = len(pa)
        if tbf < min_tbf:
            continue
        bip = g[g["launch_speed"].notna()]
        bbe = len(bip)
        fb = g[g["pitch_type"].isin(["FF", "SI"])]["release_speed"].dropna()
        out.append({
            "date": str(gd)[:10],
            "tbf": tbf,
            "bb": int((pa["events"] == "walk").sum()),
            "k": int(pa["events"].isin(_K).sum()),
            "hr": int((pa["events"] == "home_run").sum()),
            "pitches": len(g),
            "swstr": int(g["description"].isin(_SWSTR).sum()),
            "csw": int(g["description"].isin(_SWSTR | {"called_strike"}).sum()),
            "fb_velo_sum": float(fb.sum()),
            "fb_n": int(fb.shape[0]),
            "bbe": bbe,
            "barrels": int((bip["launch_speed_angle"] == 6).sum()) if bbe else 0,
            "hard_hits": int((bip["launch_speed"] >= 95).sum()) if bbe else 0,
            "gb": int((bip["bb_type"] == "ground_ball").sum()) if bbe else 0,
            "xwoba_sum": float(bip["estimated_woba_using_speedangle"].fillna(0).sum()) if bbe else 0.0,
        })
    return out


def trailing_start_windows(starts, window=10, min_starts=3):
    """One windowed entry per start, from the ``min_starts``-th start onward.

    Args:
        starts: chronologically-sorted list of per-start dicts. Each must carry
            a ``date`` plus raw COUNT fields (tbf, bb, k, pitches, ...).
        window: trailing number of starts to aggregate (event-weighted).
        min_starts: suppress entries until this many starts have accumulated.

    Returns:
        list of dicts, each with ``date``, ``start_no`` (1-based).
    """
    out = []
    for i, s in enumerate(starts):
        start_no = i + 1
        if start_no < min_starts:
            continue
        win = starts[max(0, i - window + 1): i + 1]
        row = {"date": s["date"], "start_no": start_no, "n_starts": len(win)}
        for key in s:
            if key == "date":
                continue
            row[key] = sum(w.get(key, 0) for w in win)
        out.append(row)
    return out
