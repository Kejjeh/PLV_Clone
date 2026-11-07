"""run_roster_audit: DAY_TO_DAY is not OUT, and a missing return date is '?'.

Defects (found 2026-09-18): (1) the healthy-SP count and the drop pools
filtered on ``~injured`` — ESPN sets ``injured`` for DAY_TO_DAY too, so a DTD
starter with a probable vanished from the cap math and the drop candidates
(don't-do #2, il_states.py). (2) ``int(days_until_return)`` on the NaN that
league_state emits when ESPN has no returnDate raised and killed the report.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from run_roster_audit import fmt_days, out_mask


def _roster():
    return pd.DataFrame([
        {"player_name": "Healthy SP", "lineup_slot": "P", "injured": False, "injury_status": "ACTIVE"},
        {"player_name": "DTD SP", "lineup_slot": "P", "injured": True, "injury_status": "DAY_TO_DAY"},
        {"player_name": "IL SP", "lineup_slot": "IL", "injured": True, "injury_status": "FIFTEEN_DAY_DL"},
        {"player_name": "Bench IL-status", "lineup_slot": "BE", "injured": True, "injury_status": "TEN_DAY_DL"},
        {"player_name": "Concussion", "lineup_slot": "BE", "injured": True, "injury_status": "SEVEN_DAY_DL"},
    ])


def test_day_to_day_is_not_out():
    m = out_mask(_roster())
    assert list(m) == [False, False, True, True, True]


def test_fmt_days_handles_missing():
    assert fmt_days(float("nan")) == "?"
    assert fmt_days(None) == "?"
    assert fmt_days(12.0) == "12"
    assert fmt_days(pd.NA) == "?"
