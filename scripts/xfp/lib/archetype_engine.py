"""archetype_engine — shared 20-80 scouting toolkit for the archetype builders.

The hitter / SP / RP archetype builders (`build_hitter_archetypes.py`,
`build_sp_archetypes.py`, `build_rp_archetypes.py`) each owned byte-identical
copies of these pure helpers. They live here once; each builder composes them.

A *toolkit*, not an orchestrator (same posture as `models/xfp/engine.py` per
ADR-0001): the per-position builders keep their own component lists, domain
weights, ARCHETYPES dicts, and pipeline. Only the position-agnostic scouting
math is shared. `age_tier` is parametrized because hitters and pitchers peak at
different ages — the one helper that genuinely varied.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rating_20_80(series, grouper, invert: bool = False):
    """20-80 scouting scale: 50=mean, 10pts=1 SD, capped [20,80], within-year.

    ``grouper`` is a (Series)GroupBy on the same frame as ``series`` (typically
    grouped by year) so ratings are scaled within each season's population.
    """
    mu = grouper.transform('mean')
    sd = grouper.transform('std').replace(0, np.nan)
    z = (series - mu) / sd
    if invert:
        z = -z
    return (50 + 10 * z).clip(20, 80)


def rate_value(val, mu, sd, invert: bool = False):
    """Scalar sibling of :func:`rating_20_80` — rate one value against a
    PRE-COMPUTED baseline (mu, sd), returning an int on the 20-80 scale.

    Snapshot builders rate a single row against a prior-season baseline (they
    have no in-frame population to group), so they need the scalar form. Same
    rule as ``rating_20_80`` (50 = mean, 10 pts = 1 SD, clipped [20,80]); the
    only difference is mu/sd are supplied rather than derived from a grouper.
    Returns None when any input is missing or sd is zero (undefined rating).
    """
    if pd.isna(val) or pd.isna(mu) or pd.isna(sd) or sd == 0:
        return None
    z = (val - mu) / sd
    if invert:
        z = -z
    return int(round(min(max(50 + 10 * z, 20), 80)))


def label_for_cell(ratings, defs):
    """Map an ordered list of pillar ratings to ``(cell, archetype_label)``.

    ``ratings`` are the role's pillar 20-80 ratings in matrix order (e.g.
    hitter CONTACT/POWER/DISCIPLINE, SP STUFF/MOVEMENT/CONTROL). ``defs`` is the
    role's archetype-definitions dict (cell-string -> {'label': ...}). The
    40/60 bucket cuts are the matrix's own definition, so they live here with
    the labels rather than re-inlined per builder. Unknown cell -> 'UNKNOWN'.
    """
    cell = '/'.join(bucket(r) for r in ratings)
    return cell, defs.get(cell, {}).get('label', 'UNKNOWN')


def bucket(rating) -> str:
    """PLUS (>=60) / AVG (>=40) / MINUS — the coarse 20-80 bucket."""
    if rating >= 60:
        return 'PLUS'
    if rating >= 40:
        return 'AVG'
    return 'MINUS'


def boundary_distance(rating) -> int:
    """Min distance to either archetype-bucket threshold (40 or 60).
    Higher = further from a label flip."""
    return int(min(abs(rating - 40), abs(rating - 60)))


def boundary_tier_label(d) -> str:
    """Tier label from boundary distance: EDGE (<=2) / NEAR_EDGE (<=5) / SOLID.

    Validated 2026-05-28: SOLID-tier ratings have ~66% T+1 archetype retention
    vs ~35% for EDGE-tier — the label is advisory near a boundary, durable when
    SOLID.
    """
    if d <= 2:
        return 'EDGE'
    if d <= 5:
        return 'NEAR_EDGE'
    return 'SOLID'


def age_tier(age, *, pre_max: int, peak_max: int):
    """PRE_PEAK / PEAK / POST_PEAK from age, with position-specific windows.

    Hitters peak ~1 year earlier than SPs, so the builders pass different
    ``pre_max`` / ``peak_max`` (hitters 25/30, SPs 26/31). Returns None for an
    unknown age.
    """
    if pd.isna(age):
        return None
    if age <= pre_max:
        return 'PRE_PEAK'
    if age <= peak_max:
        return 'PEAK'
    return 'POST_PEAK'
