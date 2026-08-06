# -*- coding: utf-8 -*-
"""Locks the validated retention constants and the double-shrink guard."""
import pytest

from scripts.xfp.lib import late_season_volume as lsv


def test_retention_constants_match_the_validated_study():
    # 2018-2025 statcast, Aug-5 anchor, holdout 2024-25. Changing these
    # requires re-running the study, not a judgement call.
    assert lsv.retention('H') == pytest.approx(0.865)
    assert lsv.retention('SP') == pytest.approx(0.829)


def test_retention_is_case_insensitive_and_rejects_unknown_sides():
    assert lsv.retention('h') == lsv.retention('H')
    with pytest.raises(ValueError):
        lsv.retention('RP')


def test_hitters_retain_more_than_starters():
    assert lsv.retention('H') > lsv.retention('SP')


def test_volume_from_to_date_shrinks():
    assert lsv.volume_from_to_date(4.0, 'H') == pytest.approx(4.0 * 0.865)
    assert lsv.volume_from_to_date(0.20, 'SP') == pytest.approx(0.20 * 0.829)


def test_sp_model_is_flagged_optimistic_not_silently_patched():
    # the SP volume model shrinks less than history supports; the module
    # exposes the gap rather than correcting the model behind the caller's back
    assert lsv.SP_MODEL_OPTIMISM > 1.0
    assert lsv.SP_MODEL_RETENTION > lsv.SP_RETENTION


def test_double_shrink_guard():
    to_date = 4.0
    calibrated = to_date * lsv.HITTER_MODEL_RETENTION       # correct, once
    twice = calibrated * lsv.HITTER_RETENTION               # the bug
    assert not lsv.is_double_shrunk(calibrated, to_date, 'H')
    assert lsv.is_double_shrunk(twice, to_date, 'H')


def test_double_shrink_guard_handles_zero_denominator():
    assert lsv.is_double_shrunk(0.0, 0.0, 'H') is False
