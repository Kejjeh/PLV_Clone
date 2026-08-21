"""Issue #44 — dated-snapshot retention prune."""
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from lib.retention import prune_dated_snapshots


def test_prunes_old_keeps_recent_latest_and_undated():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        old = d / 'closer_leaders_2026-05-01.csv'
        recent = d / 'closer_leaders_2026-08-15.csv'
        latest = d / 'closer_leaders_latest.csv'
        undated = d / 'closer_leaders.csv'
        other = d / 'xfp_rprs2_projections.csv'   # not a snapshot family
        for f in (old, recent, latest, undated, other):
            f.write_text('x')
        deleted = prune_dated_snapshots(d, keep_days=30, today=date(2026, 8, 20))
        assert [p.name for p in deleted] == ['closer_leaders_2026-05-01.csv']
        assert recent.exists() and latest.exists() and undated.exists() and other.exists()


def test_wired_into_refresh():
    src = (ROOT / 'scripts' / 'xfp' / 'refresh_dashboards.py').read_text(encoding='utf-8')
    assert 'prune_dated_snapshots' in src
