"""Audit C5 regression tests for _label_roster_status in
scripts/xfp/build_index_dashboard.py.

The bug (docs/production_audit_2026-07-30.md C5): the league-roster lookup was
a dict keyed by bare normalized name (last-write-wins), so BOTH Max Muncy
mlbIds — the rostered ATH callup and the FA LAD veteran — were labelled with
the roster owner's status on the shipped dashboard. The contract locked here:
ownership is per-(name, team) identity, so each distinct mlbId keeps its own
label and its own projection row.

ESPN is stubbed by monkeypatching plv_clone.league_state.LeagueState (the
function imports it at call time), returning a synthetic all_teams() frame —
no live league call.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.xfp.build_index_dashboard as bid  # noqa: E402


def _stub_league(frame: pd.DataFrame):
    class _StubLeagueState:
        def all_teams(self, *args, **kwargs):
            return frame
    return _StubLeagueState


def test_each_mlbid_keeps_its_own_ownership_label(monkeypatch):
    """Two players share the name 'Max Muncy'; only the Athletics one is on
    the user's ESPN roster. The rostered mlbId is labelled 'mine'; the other
    mlbId stays 'fa' and keeps its own projection values."""
    import plv_clone.league_state as ls
    teams = pd.DataFrame([
        {'player_name': 'Max Muncy', 'pro_team': 'Oak',
         'team_name': 'New York Ligers'},
        {'player_name': 'Kyle Schwarber', 'pro_team': 'Phi',
         'team_name': 'Bash Bros'},
    ])
    monkeypatch.setattr(ls, 'LeagueState', _stub_league(teams))

    records = [
        {'mlbId': 571970, 'name': 'Max Muncy', 'team': 'LAD',
         'roster': 'fa', 'xfpPerPa': 0.42},
        {'mlbId': 691777, 'name': 'Max Muncy', 'team': 'ATH',
         'roster': 'fa', 'xfpPerPa': 0.11},
        {'mlbId': 656941, 'name': 'Kyle Schwarber', 'team': 'PHI',
         'roster': 'fa', 'xfpPerPa': 0.51},
        {'mlbId': 400001, 'name': 'Somebody Else', 'team': 'NYM',
         'roster': 'fa', 'xfpPerPa': 0.20},
    ]
    bid._label_roster_status(records, bid.xfp_name_key,
                             my_team_name='New York Ligers')

    by_id = {r['mlbId']: r for r in records}
    # The rostered Athletics Muncy is mine...
    assert by_id[691777]['roster'] == 'mine'
    # ...and the LAD Muncy is NOT swallowed by the same name key.
    assert by_id[571970]['roster'] == 'fa'
    # Each record keeps its own projection row untouched.
    assert by_id[571970]['xfpPerPa'] == 0.42
    assert by_id[691777]['xfpPerPa'] == 0.11
    # Ordinary single-identity labels still work (incl. ESPN 'Phi' vs
    # Statcast 'PHI' team-code drift).
    assert by_id[656941]['roster'] == 'taken'
    assert by_id[656941]['taken_by_team'] == 'Bash Bros'
    assert by_id[400001]['roster'] == 'fa'


def test_roster_feed_that_collapses_two_players_without_team_tiebreak_raises(monkeypatch):
    """Build-time assertion (audit C5): if two ROSTERED players collapse to
    one name key and no team tiebreak can separate them, labelling must fail
    loudly at build time — every same-key record's label would otherwise be
    a guess."""
    import plv_clone.league_state as ls
    teams = pd.DataFrame([
        {'player_name': 'Max Muncy', 'pro_team': None,
         'team_name': 'New York Ligers'},
        {'player_name': 'Max Muncy', 'pro_team': None,
         'team_name': 'Bash Bros'},
    ])
    monkeypatch.setattr(ls, 'LeagueState', _stub_league(teams))

    records = [{'mlbId': 571970, 'name': 'Max Muncy', 'team': 'LAD',
                'roster': 'fa'}]
    with pytest.raises(ValueError, match='max muncy'):
        bid._label_roster_status(records, bid.xfp_name_key,
                                 my_team_name='New York Ligers')


def test_my_team_merge_matches_by_mlbid_not_collapsed_name_dict():
    """Review round 2 (2026-07-30): the MY_TEAM merge path still joined by a
    bare (last, first) name dict — with two Max Muncy records, last-write-wins
    kept only one, and find_xfp_record('Max Muncy') returned whichever
    survived (the WRONG player when Josh rosters the other). The contract:
    when the ESPN payload row carries an mlbId and the records do too, the
    merge matches BY ID and the name dict never decides."""
    records = [
        {'mlbId': 571970, 'name': 'Max Muncy', 'team': 'LAD', 'xfpPerPa': 0.42},
        {'mlbId': 691777, 'name': 'Max Muncy', 'team': 'ATH', 'xfpPerPa': 0.11},
    ]
    by_key = {bid.plv_name_key(r['name']): r for r in records}   # collapsed!
    by_id = {r['mlbId']: r for r in records}
    # Josh rosters the LAD Muncy (571970) — the name dict kept the ATH one.
    rec = bid.find_xfp_record('Max Muncy', by_key, mlbam=571970, by_id=by_id)
    assert rec is not None and rec['mlbId'] == 571970, (
        'the merge must return the ID-matched record, not the name-dict '
        'survivor')
    # No id supplied and the name is collapsed-ambiguous: name path still
    # answers (legacy behavior for id-less payload rows).
    legacy = bid.find_xfp_record('Max Muncy', by_key)
    assert legacy is not None
