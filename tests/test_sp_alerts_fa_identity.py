"""Audit C7 regression tests: the SP alert board's FA gate is mlbam-id-keyed.

The bug (docs/production_audit_2026-07-30.md C7): build_sp_alerts.py's
`is_fa` fell back to last-name + first-INITIAL matching against the FA-pool
name set, so a ROSTERED pitcher sharing surname+initial with any genuine FA
was alerted as available. The fix: resolve the FA pool to mlbam ids once
(`fa_sp_mlbam_ids`, collision-safe via resolve_pitcher_id) and filter the
statcast frame by pitcher id; an unresolvable FA name is skipped with a
one-line breadcrumb and treated as NOT-FA — losing an alert beats inventing
one.

build_sp_alerts.py itself is a run-at-import script (live ESPN + duckdb), so
the resolution seam lives in scripts/xfp/lib/bucket_dispatch.py and is tested
behaviorally with synthetic frames; the script's wiring is pinned by source
assertion (the tests/test_name_collision.py::test_roster_audit_join_is_not_fuzzy
pattern).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_fa_pool_membership_is_mlbam_keyed_and_refuses_lookalikes(capsys):
    """A genuine FA ('Gerardo Rodriguez') shares surname + first initial with
    a rostered ace ('Grayson Rodriguez'). The FA id set contains only the
    real FA's mlbam id — the rostered pitcher can never be marked FA by
    name-shape similarity — and an unresolvable FA name is skipped with a
    loud breadcrumb instead of being guessed."""
    from scripts.xfp.lib.bucket_dispatch import fa_sp_mlbam_ids

    fa_pool = pd.DataFrame([
        {'player_name': 'Gerardo Rodriguez', 'position': 'SP', 'pro_team': 'Mia'},
        {'player_name': 'Totally Unknown', 'position': 'SP', 'pro_team': None},
        {'player_name': 'Juan Soto', 'position': 'OF', 'pro_team': 'NYM'},
    ])
    # Synthetic SP multiyr cache ("Last, First" spelling, the real schema).
    spm = pd.DataFrame({
        'player_name': ['Rodriguez, Gerardo', 'Rodriguez, Grayson'],
        'pitcher': [900001, 680694],
        'year': [2026, 2026],
    })
    rpm = pd.DataFrame({'name': pd.Series(dtype=str),
                        'pitcher': pd.Series(dtype=int),
                        'year': pd.Series(dtype=int),
                        'team_abbr': pd.Series(dtype=str)})

    ids = fa_sp_mlbam_ids(fa_pool, sp_multiyr=spm, rp_multiyr=rpm)

    assert ids == {900001}
    # The rostered Grayson (same surname, same first initial 'G') is NOT FA.
    assert 680694 not in ids
    # The hitter row was never considered; the unresolvable name left a
    # breadcrumb and no id.
    err = capsys.readouterr().err
    assert 'Totally Unknown' in err
    assert 'NOT-FA' in err


def test_sp_alert_fa_gate_is_id_keyed_not_initial_matched():
    """Lock the wiring (source assertion — the script runs live ESPN at
    import, same pattern as test_roster_audit_join_is_not_fuzzy): the alert
    board filters the statcast frame by the resolved FA mlbam-id set, and the
    surname + first-initial fallback is gone."""
    src = (ROOT / 'scripts' / 'xfp' / 'build_sp_alerts.py').read_text(encoding='utf-8')
    # The id-keyed gate is present and drives the FA row filter.
    assert 'fa_sp_mlbam_ids' in src
    assert 'isin(fa_sp_ids)' in src
    # The name-shape fallback (last name + first initial) is deleted.
    assert 'kp[-1] == last' not in src
    assert 'fa_sp_norm' not in src
