"""Cadence- AND ET-time-aware PL cache staleness — a ranking is stale only once its
NEXT edition has ACTUALLY published (SP Mon, closers ~Tue, hitters ~Wed, all ~7 PM ET;
streamers rolling). At Tue 4 AM only Monday's SP list is new; the rest land that evening."""
import sys
from pathlib import Path
from datetime import date, datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.pl_cache import (
    _cache_is_stale, _latest_published_edition, PL_PUBLISH_CADENCE, _ET,
)

TUE_4AM = datetime(2026, 6, 23, 4, 0, tzinfo=_ET)    # Tue, before evening articles
TUE_8PM = datetime(2026, 6, 23, 20, 0, tzinfo=_ET)   # Tue, after ~7 PM articles


def test_at_tue_4am_only_monday_sp_is_new():
    # SP (Mon) edition 6/22 is out by Tue 4 AM -> a 6/19 cache is stale
    assert _cache_is_stale("pl_sps_top100.json", date(2026, 6, 19), TUE_4AM)[0] is True
    # closers (Tue ~7 PM) have NOT dropped yet at 4 AM -> 6/19 cache still current
    assert _cache_is_stale("pl_closers.json", date(2026, 6, 19), TUE_4AM)[0] is False
    # hitters (Wed) also not yet -> current
    assert _cache_is_stale("pl_hitters_top150.json", date(2026, 6, 19), TUE_4AM)[0] is False


def test_tuesday_closers_go_stale_after_7pm_et():
    # same 6/19 cache, but now it's Tue 8 PM -> the Tue closer edition has published
    assert _cache_is_stale("pl_closers.json", date(2026, 6, 19), TUE_8PM)[0] is True
    # SP still stale (Monday's been out since yesterday)
    assert _cache_is_stale("pl_sps_top100.json", date(2026, 6, 19), TUE_8PM)[0] is True


def test_fresh_after_pulling_this_cycle():
    # pulled Mon 6/22 -> SP current at Tue 4 AM
    assert _cache_is_stale("pl_sps_top100.json", date(2026, 6, 22), TUE_4AM)[0] is False


def test_publish_hour_boundary():
    # the latest live Tuesday edition flips at ~7 PM ET on Tuesday
    assert _latest_published_edition(TUE_4AM, 1) == date(2026, 6, 16)   # prior Tue
    assert _latest_published_edition(TUE_8PM, 1) == date(2026, 6, 23)   # today's, now out
    assert _latest_published_edition(TUE_4AM, 0) == date(2026, 6, 22)   # Monday already out


def test_streamers_rolling_two_day():
    assert _cache_is_stale("pl_sp_streamers_latest.json", date(2026, 6, 22), TUE_4AM)[0] is False
    assert _cache_is_stale("pl_sp_streamers_latest.json", date(2026, 6, 20), TUE_4AM)[0] is True


def test_every_pl_cache_has_a_cadence():
    for f in ("pl_sps_top100.json", "pl_hitters_top150.json", "pl_closers.json",
              "pl_sp_streamers_latest.json"):
        assert f in PL_PUBLISH_CADENCE
