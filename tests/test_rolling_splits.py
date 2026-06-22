"""Regression test for the in-progress split selection in build_rolling_hitters.

The 2026-06-22 bug: when statcast data landed 1-4 days past the last weekly cutoff,
no current ("in-progress", after.empty) snapshot was emitted, so the last weekly
split became a truncating TRAINING row whose target inner-join dropped every player
who didn't play on the post-cutoff day — collapsing the rh3 projection pool from 433
to 257 and silently dropping active stars (Vlad) and any one-day-rested player.
"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from build_rolling_hitters import select_inprogress_splits

SS = pd.Timestamp("2026-03-26")          # season start
WEEKLY = list(range(30, 201, 7))         # ...79, 86, 93 (86 -> 6/20)


def test_current_snapshot_emitted_when_data_past_last_weekly_cutoff():
    # Data through 6/21 = 1 day past the 6/20 (split 86) cutoff. The last weekly
    # split would be a truncating training row -> we MUST append a current snapshot.
    max_data = pd.Timestamp("2026-06-21")
    today = pd.Timestamp("2026-06-22")
    splits, elapsed = select_inprogress_splits(WEEKLY, SS, max_data, today)
    assert 86 in splits                       # 6/20 weekly cutoff present
    assert 93 not in splits                   # 6/27 hasn't elapsed
    assert elapsed in splits                  # current in-progress snapshot appended
    assert elapsed == 88 and max(splits) == 88


def test_no_extra_snapshot_when_data_lands_on_weekly_boundary():
    # Data exactly through 6/20 (= split 86 cutoff): that weekly split is itself
    # after.empty (no truncation), so no extra current snapshot is needed.
    max_data = pd.Timestamp("2026-06-20")
    today = pd.Timestamp("2026-06-21")
    splits, elapsed = select_inprogress_splits(WEEKLY, SS, max_data, today)
    assert max(splits) == 86                  # last weekly cutoff, no append
    assert elapsed not in splits or elapsed == 86


def test_empty_when_no_cutoffs_elapsed_still_emits_current():
    # Very early season: no weekly cutoff elapsed yet, but there IS data -> emit a
    # current snapshot so the pool isn't empty.
    max_data = pd.Timestamp("2026-04-01")
    today = pd.Timestamp("2026-04-02")
    splits, elapsed = select_inprogress_splits(WEEKLY, SS, max_data, today)
    assert splits == [elapsed]
