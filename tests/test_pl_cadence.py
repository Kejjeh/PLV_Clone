"""Cadence-aware PL cache staleness — a ranking is stale only once its NEXT edition
has actually published (SP Mon, closers ~Tue, hitters ~Wed, streamers rolling)."""
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from lib.pl_cache import _cache_is_stale, _last_weekday_on_or_before, PL_PUBLISH_CADENCE

TUE = date(2026, 6, 23)   # a Tuesday; this week's Mon = 6/22


def test_sp_stale_once_mondays_edition_is_out():
    # fetched Fri 6/19 -> the Mon 6/22 SP edition has since dropped -> stale
    stale, _ = _cache_is_stale("pl_sps_top100.json", date(2026, 6, 19), TUE)
    assert stale
    # fetched on/after this week's Monday -> current
    stale2, _ = _cache_is_stale("pl_sps_top100.json", date(2026, 6, 22), TUE)
    assert not stale2


def test_closers_tuesday_cadence():
    # closers publish ~Tue; on Tue 6/23 a 6/19 cache is stale (6/23 edition out)
    stale, _ = _cache_is_stale("pl_closers.json", date(2026, 6, 19), TUE)
    assert stale


def test_streamers_rolling_two_day():
    assert _cache_is_stale("pl_sp_streamers_latest.json", date(2026, 6, 22), TUE)[0] is False
    assert _cache_is_stale("pl_sp_streamers_latest.json", date(2026, 6, 20), TUE)[0] is True  # 3d


def test_unknown_file_falls_back_to_rolling_week():
    # not in cadence map -> rolling 7d
    assert _cache_is_stale("mystery.json", date(2026, 6, 1), TUE)[0] is True
    assert _cache_is_stale("mystery.json", date(2026, 6, 20), TUE)[0] is False


def test_last_weekday_helper():
    assert _last_weekday_on_or_before(TUE, 0) == date(2026, 6, 22)   # Monday
    assert _last_weekday_on_or_before(TUE, 1) == date(2026, 6, 23)   # Tuesday (today)
    assert _last_weekday_on_or_before(TUE, 2) == date(2026, 6, 17)   # prior Wednesday


def test_every_pl_cache_has_a_cadence():
    for f in ("pl_sps_top100.json", "pl_hitters_top150.json", "pl_closers.json",
              "pl_sp_streamers_latest.json"):
        assert f in PL_PUBLISH_CADENCE
