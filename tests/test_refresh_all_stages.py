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


def test_refresh_driver_visibility_contracts():
    """Issue #38 — driver-level visibility invariants, pinned as source
    contracts (the driver has no importable API; these are the load-bearing
    strings whose loss silently regresses the fix)."""
    src = (ROOT / 'scripts' / 'xfp' / 'refresh_dashboards.py').read_text(encoding='utf-8')
    # (A) closing roll-up exists and run() records failures
    assert 'FAILED_STEPS.append' in src and 'FAILED STEPS THIS RUN' in src
    # (B) the rh3 substrate gates the publish
    assert 'ok_rolling = run' in src and 'not ok_rolling' in src
    # (C) calibration idle-gate requires the JSON too
    assert 'calibration_summary.json' in src
    # (D) the weekly plv rebuild is RETIRED (ADR-0009 addendum 2026-09-01):
    #     the tombstone must stay so the step is not silently re-added, and
    #     no run() may issue plv update from the nightly again.
    assert '1.98. RETIRED' in src
    assert "run('1.98" not in src and 'plv_clone.cli update' not in \
        src.split('1.98. RETIRED')[0]
    # (E) per-artifact withholding consults every builder flag
    for flag in ('ok_index', 'ok_matchup', 'ok_tri_page', 'ok_xfp_board'):
        assert f"'{flag}" in src or flag in src.split('_page_ok = {')[1][:400]
    # (F) the PL staleness checkpoint prints BEFORE the publish decision
    assert src.index('7. PL cache freshness') < src.index('if not args.no_push:')
