"""rolling_splits — shared in-progress snapshot-day selection for the rolling builders.

Hitters / pitchers / relievers all build per-(player, split_day) rolling snapshots at
weekly cutoffs. For an IN-PROGRESS season the last weekly cutoff often sits a few days
BEFORE the latest data; if no current ("today") snapshot is emitted, that last weekly
split has a non-empty `after` window, is built as a TRAINING row, and its target
inner-join silently drops every player whose last game WAS the cutoff date — truncating
the projection pool (the 2026-06-22 Vlad/Judge rh3 dropout 433->257).

One correct implementation, shared by all three builders, so the bug can't reappear in
just one of them. Pure + unit-tested (tests/test_rolling_splits.py).
"""
from __future__ import annotations

import pandas as pd


def select_inprogress_splits(base_splits, season_start, max_data_date, today):
    """Choose split_days for an in-progress season. Returns (splits_to_use, elapsed_days).

    splits_to_use = the elapsed weekly cutoffs (cutoff <= max_data_date) PLUS a current
    "in-progress" snapshot (labeled elapsed_days) appended WHENEVER data extends past the
    last weekly cutoff — so that snapshot's `after` window is empty and it captures every
    active player instead of the last weekly split becoming a truncating training row.
    """
    elapsed_days = int((pd.Timestamp(today) - pd.Timestamp(season_start)).days)
    ss = pd.Timestamp(season_start)
    mdd = pd.Timestamp(max_data_date)
    splits = [s for s in base_splits if ss + pd.Timedelta(days=s) <= mdd]
    last_cut = ss + pd.Timedelta(days=max(splits, default=0))
    if (not splits) or (last_cut < mdd):
        splits = list(splits) + [elapsed_days]
    return splits, elapsed_days
