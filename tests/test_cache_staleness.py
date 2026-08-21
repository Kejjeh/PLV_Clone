"""Issue #40 — shared current-season staleness rule."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

import datetime as dt
import tempfile
from lib.cache_staleness import current_season_stale

THIS_YEAR = dt.date.today().year


def test_missing_cache_is_stale_not_a_crash():
    with tempfile.TemporaryDirectory() as d:
        assert current_season_stale(Path(d) / 'nope.csv', [THIS_YEAR]) is True


def test_completed_seasons_never_go_stale():
    with tempfile.TemporaryDirectory() as d:
        assert current_season_stale(Path(d) / 'nope.csv', [THIS_YEAR - 1]) is False


def test_fresh_current_season_cache_is_not_stale():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'cache.csv'
        f.write_text('x')
        assert current_season_stale(f, [THIS_YEAR]) is False


def test_both_pullers_share_the_one_rule():
    import pull_fg_rp_leverage as fg
    import pull_bref_rp_ir as br
    assert fg._current_season_stale is current_season_stale
    assert br._current_season_stale is current_season_stale
