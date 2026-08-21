"""Issue #35 — PL cache follow-ups: RP universe, closers fallback, hitter
edition stamping."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from lib import pl_cache
import build_pl_cache as bpl


def test_rp_universe_tracks_the_parsed_table(monkeypatch):
    """parse_closers now reads the 100-row ranked table; a reliever with
    model_rank 51-100 absent from it is a snub ('UR'), not out-of-scope."""
    fake = {'ranks': {f'Pitcher {i}': i for i in range(1, 101)}, 'fetched': '2026-08-18'}
    monkeypatch.setattr(pl_cache, '_load_pl_cache', lambda fname: fake)
    rk, _ = pl_cache.pl_rank('Nobody Special', 'RP', model_rank=75)
    assert rk == 'UR'


def test_rp_universe_still_bounds_out_of_scope(monkeypatch):
    fake = {'ranks': {f'Pitcher {i}': i for i in range(1, 101)}, 'fetched': '2026-08-18'}
    monkeypatch.setattr(pl_cache, '_load_pl_cache', lambda fname: fake)
    rk, _ = pl_cache.pl_rank('Nobody Special', 'RP', model_rank=250)
    assert rk == '—'


def test_closers_url_candidates_cover_slip_days_and_weeks():
    urls = [u for u, _ in bpl.closers_url_candidates(date(2026, 8, 18))]
    assert len(set(urls)) >= 6  # Tue+Wed across 3 weeks


def test_hitter_edition_stamp_never_launders_a_reserved_week():
    """Re-serving the already-cached week must keep the OLD fetched stamp so
    staleness keeps accruing (the 08-18 'looked current a week behind' bug)."""
    stamp = bpl.hitter_edition_stamp(prev_week=20, prev_fetched='2026-08-12',
                                     resolved_week=20, calendar_wed=date(2026, 8, 19))
    assert str(stamp) == '2026-08-12'
    stamp2 = bpl.hitter_edition_stamp(prev_week=20, prev_fetched='2026-08-12',
                                      resolved_week=21, calendar_wed=date(2026, 8, 19))
    assert str(stamp2) == '2026-08-19'
