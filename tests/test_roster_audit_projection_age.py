"""run_roster_audit's projection-age line must never launder a stale
projection as fresh.

Defect (found 2026-09-18): the report computed each projection CSV's age in
days from its mtime and then printed the literal suffix ``— fresh.`` no matter
what the ages were — a 40-day-old rp3 read ``rp3 40d — fresh.`` The number was
right and the verdict was wrong, which is the worst kind of label: a reader
skims the verdict. The label is now derived from the ages by a pure helper.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from run_roster_audit import PROJECTION_MAX_AGE_DAYS, projection_age_note


def test_all_within_threshold_reads_fresh():
    note = projection_age_note({"rh3": 0, "rp3": 1, "rprs2": 0})
    assert "fresh" in note
    assert "STALE" not in note


def test_one_stale_projection_is_named_and_flagged():
    ages = {"rh3": 0, "rp3": PROJECTION_MAX_AGE_DAYS + 38, "rprs2": 0}
    note = projection_age_note(ages)
    assert "STALE" in note, note
    assert "rp3" in note.split("STALE", 1)[1], note   # the stale one is named
    assert "— fresh" not in note


def test_threshold_boundary_is_inclusive_of_max_age():
    ok = projection_age_note({"rh3": PROJECTION_MAX_AGE_DAYS})
    bad = projection_age_note({"rh3": PROJECTION_MAX_AGE_DAYS + 1})
    assert "STALE" not in ok
    assert "STALE" in bad


def test_missing_age_is_reported_as_missing_not_fresh():
    note = projection_age_note({"rh3": 0, "rp3": None})
    assert "MISSING" in note and "rp3" in note
    assert "— fresh" not in note
