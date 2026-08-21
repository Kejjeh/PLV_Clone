"""Issue #34 — atomic CSV writes."""
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from lib.atomic_io import atomic_to_csv


def test_write_replaces_and_leaves_no_tmp():
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / 'out.csv'
        dest.write_text('old')
        atomic_to_csv(pd.DataFrame({'a': [1, 2]}), dest)
        assert pd.read_csv(dest)['a'].tolist() == [1, 2]
        assert not list(Path(d).glob('*.tmp'))


def test_live_read_artifacts_use_atomic_writes():
    for f in ('build_xwoba_l225.py', 'build_sp_rp_stuff_windows.py'):
        src = (ROOT / 'scripts' / 'xfp' / f).read_text(encoding='utf-8')
        assert 'atomic_to_csv' in src, f
        # the LATEST pointer (live-read) must not use a bare to_csv
        assert 'x.to_csv(OUT / "' not in src, f
