"""Issue #39 — optimizer candidate resolution and projection-drop visibility."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))


def test_name_match_sp_cache_includes_current_season():
    """Tripwire: the audit suspected this cache was frozen at 2015-2025 by
    filename; it is actually refreshed daily. If it EVER truly freezes, every
    current-season debutant SP falls to name-key identity and scores
    realized_fp 0.0 — this test catches that regression."""
    import inspect
    from plv_clone.utils import name_match
    sig = inspect.signature(name_match.resolve_pitcher_id)
    sp_path = sig.parameters['sp_path'].default
    years = pd.read_csv(ROOT / sp_path, usecols=['year'])['year']
    import datetime
    assert years.max() >= datetime.date.today().year


def test_optimizer_falls_back_to_api_resolution():
    src = (ROOT / 'scripts' / 'xfp' / 'run_weekly_optimizer.py').read_text(encoding='utf-8')
    block = src.split('def resolve_candidate_mlbams')[1].split('\ndef ')[0]
    assert '_resolve_mlbam_via_api' in block or '_resolve_pitcher_mlbam' in block


def test_projection_drops_are_loud_and_gated():
    from run_weekly_optimizer import check_projection_drops
    # under threshold: returns silently
    check_projection_drops({'SP': 1}, {'SP': 10})
    # over threshold: refuses to report a silently-emptied bucket as clean
    with pytest.raises(RuntimeError):
        check_projection_drops({'SP': 5}, {'SP': 10})
