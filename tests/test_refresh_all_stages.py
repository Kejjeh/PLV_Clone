"""Issue #37 — refresh_all stage-graph consistency."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

import refresh_all


def test_pitcher_schedule_is_not_gating():
    """No substrate/model/index stage inside refresh_all reads
    pitcher_schedule_2026.csv, so a transient probables 503 must not abort
    the whole model rebuild (it is refreshed independently at step 2.9)."""
    stage = next(s for s in refresh_all.STAGES if 'schedule' in s[0].lower())
    assert stage[3] is False


def test_summary_never_claims_missing_stages_are_uncounted():
    """A missing non-gating script DOES fail the run (exit 1) by design;
    the summary must not print the opposite."""
    src = (ROOT / 'scripts' / 'xfp' / 'refresh_all.py').read_text(encoding='utf-8')
    assert 'not counted as failures' not in src
