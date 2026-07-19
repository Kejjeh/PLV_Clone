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


def rate_pillars(components, weights=None):
    """Fold already-rated 20-80 component ratings into ONE pillar rating.

    The per-pillar fold the snapshot builders all repeat: drop None components,
    take the (optionally weighted) mean of survivors, round to int. Returns None
    when nothing survives — the caller's "skip this row / fall back" gate.

    ``weights`` defaults to 1.0 each (plain mean); a weighted call (e.g. RP
    BATTED_BALL) and a plain call are the SAME code path (uniform weights == plain
    mean), which is the point of the consolidation. Rounding is ``int(round(...))``
    to match the builders' historical output exactly.
    """
    if weights is None:
        pairs = [(c, 1.0) for c in components if c is not None]
    else:
        pairs = [(c, w) for c, w in zip(components, weights) if c is not None]
    wsum = sum(w for _, w in pairs)
    if not pairs or wsum == 0:
        return None
    return int(round(sum(c * w for c, w in pairs) / wsum))


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


def trajectory_metrics(group):
    """Per-player 3-year OVERALL slope + career percentile (item 20/D3 hoist).

    Applied per id-group on a frame holding ``year`` / ``OVERALL``. Extracted
    verbatim from the identical ``_trajectory_metrics`` closures in the SP and
    hitter builders.
    """
    g = group.sort_values('year').reset_index(drop=True)
    g['OVERALL_slope_3yr'] = np.nan
    g['OVERALL_career_pct'] = np.nan
    for i in range(len(g)):
        # Slope from last 3 (or fewer) seasons up to and including current
        window = g.iloc[max(0, i-2):i+1]
        if len(window) >= 2 and window['year'].max() - window['year'].min() >= 1:
            slope = np.polyfit(window['year'].values, window['OVERALL'].values, 1)[0]
            g.loc[g.index[i], 'OVERALL_slope_3yr'] = slope
        # Career percentile: where current overall sits in player's history (inclusive)
        career = g.iloc[:i+1]['OVERALL']
        g.loc[g.index[i], 'OVERALL_career_pct'] = (career < g.loc[g.index[i], 'OVERALL']).sum() / len(career)
    return g


def traj_flag(row):
    """TRENDING_UP / TRENDING_DOWN / CAREER_HIGH / CAREER_LOW / STABLE from the
    trajectory metrics (item 20/D3 hoist — verbatim ``_traj_flag``)."""
    s = row['OVERALL_slope_3yr']
    p = row['OVERALL_career_pct']
    if pd.notna(s) and s >= 3.0: return 'TRENDING_UP'
    if pd.notna(s) and s <= -3.0: return 'TRENDING_DOWN'
    if pd.notna(p) and p >= 0.90: return 'CAREER_HIGH'
    if pd.notna(p) and p <= 0.10: return 'CAREER_LOW'
    return 'STABLE'


def attach_trajectory(qual, *, id_col: str):
    """Attach OVERALL_slope_3yr / OVERALL_career_pct / traj_flag to the panel.

    The scaffolding around :func:`trajectory_metrics` / :func:`traj_flag` that
    the SP and hitter builders duplicated verbatim (modulo the id column):
    sort, per-player apply, rounding, and the merge back (preserving row order).
    """
    qual_sorted = qual.sort_values([id_col, 'year'])[[id_col, 'year', 'OVERALL']].copy()
    qual_sorted = qual_sorted.groupby(id_col, group_keys=False)[[id_col, 'year', 'OVERALL']].apply(trajectory_metrics)
    qual_sorted['OVERALL_slope_3yr'] = qual_sorted['OVERALL_slope_3yr'].round(2)
    qual_sorted['OVERALL_career_pct'] = qual_sorted['OVERALL_career_pct'].round(3)
    qual_sorted['traj_flag'] = qual_sorted.apply(traj_flag, axis=1)

    # Merge back into qual (preserve row order)
    return qual.merge(
        qual_sorted[[id_col, 'year', 'OVERALL_slope_3yr', 'OVERALL_career_pct', 'traj_flag']],
        on=[id_col, 'year'], how='left'
    )


def build_career_panel(qual, *, id_col: str, fp_col: str):
    """Attach T+1 / T+2 outcomes for comp matching (item 20/D3 hoist).

    Near-identical across the SP and hitter builders modulo the id/fp columns.
    The "Last, First" -> "First Last" display flip reuses the canonical
    ``bucket_dispatch._flip_lastfirst`` (guarded so non-str values — e.g. NaN
    player names — pass through unchanged, matching the builders' historical
    ``isinstance(s, str)`` check rather than _flip_lastfirst's ``str(s)``).
    """
    from .bucket_dispatch import _flip_lastfirst  # lazy: keeps toolkit import light

    careers = qual.sort_values([id_col, 'year']).reset_index(drop=True)
    careers['next_fp']   = careers.groupby(id_col)[fp_col].shift(-1)
    careers['next_arch'] = careers.groupby(id_col)['archetype'].shift(-1)
    careers['next_year'] = careers.groupby(id_col)['year'].shift(-1)
    careers['t2_fp']     = careers.groupby(id_col)[fp_col].shift(-2)
    careers['t2_year']   = careers.groupby(id_col)['year'].shift(-2)

    # Pretty display name
    careers['name'] = careers['player_name'].apply(
        lambda s: _flip_lastfirst(s) if isinstance(s, str) else s
    )
    return careers


def compute_boundary_validation(qual, *, id_col: str):
    """EDGE / NEAR_EDGE / SOLID T+1 archetype-retention stats (item 20/D3 hoist).

    The boundary-tier validation block duplicated verbatim (modulo the id
    column) in both builders' ``main()``. Feeds ``*_boundary_validation.json``.
    """
    careers = qual.sort_values([id_col, 'year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby(id_col)['archetype'].shift(-1)
    careers['next_year'] = careers.groupby(id_col)['year'].shift(-1)
    current = int(qual['year'].max())
    trans = careers[(careers['next_year'] == careers['year'] + 1) &
                    (careers['next_year'] != current)].copy()
    trans['stayed'] = (trans['archetype'] == trans['next_arch']).astype(int)
    boundary_stats = {}
    for tier in ['EDGE', 'NEAR_EDGE', 'SOLID']:
        sub = trans[trans['boundary_tier'] == tier]
        if len(sub) >= 10:
            boundary_stats[tier] = {
                'n_transitions': int(len(sub)),
                'retention_pct': round(100 * float(sub['stayed'].mean()), 1),
            }
    return boundary_stats


def compute_stickiness(qual, *, id_col: str, fp_col: str, ndigits: int,
                       guard_empty: bool = False):
    """YoY archetype retention + per-age-tier breakdown (item 14 hoist).

    Extracted verbatim-equivalent from the three archetype builders, which
    differed only in the id column (``batter``/``pitcher``), the FP column
    (``fp_per_pa``/``fp_per_start``/``fp_per_g``), the FP rounding (hitter 3dp,
    SP/RP 2dp), and whether an empty next-arch subset yields ``None`` (RP) vs
    ``NaN`` (H/SP) — all captured by the four parameters. Writes the
    ``*_archetype_stickiness.json`` tables (NOT the ratings master, so it does
    not touch the frozen Blended-xFP prior). Equivalence pinned by
    tests/test_archetype_engine.py against reference copies of all three.
    """
    careers = qual.sort_values([id_col, 'year']).reset_index(drop=True)
    careers['next_arch'] = careers.groupby(id_col)['archetype'].shift(-1)
    careers['next_year'] = careers.groupby(id_col)['year'].shift(-1)
    careers['next_fp'] = careers.groupby(id_col)[fp_col].shift(-1)
    careers['year_gap'] = careers['next_year'] - careers['year']
    current_year = int(qual['year'].max())
    trans = careers[(careers['year_gap'] == 1) & (careers['next_year'] != current_year)]

    def _fp(sub, mask):
        if guard_empty and not mask.any():
            return None
        return round(float(sub[mask]['next_fp'].mean()), ndigits)

    out = {}
    for arch in qual['archetype'].unique():
        sub = trans[trans['archetype'] == arch]
        if len(sub) < 8:
            continue
        n_total = len(sub)
        n_stick = int((sub['next_arch'] == arch).sum())
        top_to = sub['next_arch'].value_counts().head(3).to_dict()
        entry = {
            'n_total_transitions': n_total,
            'n_stayed': n_stick,
            'retention_pct': round(100 * n_stick / n_total, 1),
            'top_destinations': [[k, int(v), round(100 * v / n_total, 1)] for k, v in top_to.items()],
            'fp_if_stayed': _fp(sub, sub['next_arch'] == arch),
            'fp_if_left': _fp(sub, sub['next_arch'] != arch),
            'by_age_tier': {},
        }
        for tier in ['PRE_PEAK', 'PEAK', 'POST_PEAK']:
            sub_t = sub[sub['age_tier'] == tier]
            if len(sub_t) < 5:
                continue
            ret = float((sub_t['next_arch'] == arch).mean())
            entry['by_age_tier'][tier] = {
                'n': int(len(sub_t)),
                'retention_pct': round(100 * ret, 1),
            }
        out[arch] = entry
    return out
