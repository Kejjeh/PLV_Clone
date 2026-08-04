"""Closer-watch: the failure this pins is CONFUSING SILENCE FOR EVIDENCE.

On 2026-08-03 the Dodgers' ninth-inning job changed hands on the manager's word
while the box score showed nothing, because LA had generated zero save
opportunities in five days. Reasoning from usage produced the confident and
wrong conclusion that the role had not moved — twice.

Every test below exists to keep that specific mistake out of the surface.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.xfp.lib.closer_watch import (  # noqa: E402
    HOLDS_ROLE, JUST_ARRIVED, NOT_PITCHING, NO_CHANCES, ROLE_LOST,
    build_watch, classify,
    save_opportunities,
)


# ── the core rule ──────────────────────────────────────────────────────────
def test_no_team_chances_is_UNKNOWN_never_role_intact():
    """THE bug. Zero save opportunities says nothing about who closes."""
    sig, note = classify(saves_self=0, saves_teammates=0, team_chances=0,
                         appearances=4)
    assert sig == NO_CHANCES
    assert 'UNKNOWN' in note or 'unknown' in note.lower()


def test_no_chances_wins_even_when_he_never_pitched():
    """A closer who did not appear on a club with no leads is still unknown —
    the ordering must not report NOT_PITCHING and imply a demotion."""
    sig, _ = classify(saves_self=0, saves_teammates=0, team_chances=0,
                      appearances=0)
    assert sig == NO_CHANCES


def test_teammate_taking_the_save_is_the_real_signal():
    sig, note = classify(saves_self=0, saves_teammates=2, team_chances=3,
                         appearances=5)
    assert sig == ROLE_LOST
    assert '2' in note


def test_recording_a_save_confirms_the_role():
    sig, _ = classify(saves_self=1, saves_teammates=0, team_chances=2,
                      appearances=6)
    assert sig == HOLDS_ROLE


def test_chances_existed_but_nobody_saved_is_inconclusive():
    """Blown saves and extra-inning wins burn a chance without a save. That is
    not evidence against the incumbent."""
    sig, note = classify(saves_self=0, saves_teammates=0, team_chances=2,
                         appearances=3)
    assert sig == NO_CHANCES
    assert 'inconclusive' in note


def test_not_pitching_only_when_chances_existed():
    sig, _ = classify(saves_self=0, saves_teammates=0, team_chances=2,
                      appearances=0)
    assert sig == NOT_PITCHING


# ── save opportunity derivation ────────────────────────────────────────────
def test_save_opportunity_is_a_win_by_one_to_three():
    d = pd.DataFrame([
        dict(team='LAD', date='2026-07-30', margin=4),    # blowout win
        dict(team='LAD', date='2026-07-29', margin=2),    # save spot
        dict(team='LAD', date='2026-08-01', margin=-1),   # loss
        dict(team='LAD', date='2026-07-17', margin=1),    # save spot
    ])
    out = save_opportunities(d)
    assert list(out['save_opp']) == [False, True, False, True]


def test_save_opportunities_handles_empty():
    assert save_opportunities(pd.DataFrame()).empty


# ── the assembled board ────────────────────────────────────────────────────
def _saves(rows):
    return pd.DataFrame(rows, columns=['player_key', 'team', 'n'])


def test_dodgers_scenario_reports_unknown_not_intact():
    """The live 2026-08-03 state: Scott and Diaz both quiet because LA had no
    save chances. Neither may be reported as holding or losing the job."""
    wl = {'tanner scott': dict(name='Tanner Scott', team='LAD', expect='SETUP'),
          'edwin diaz': dict(name='Edwin Diaz', team='LAD', expect='CLOSER')}
    out = build_watch(watchlist=wl, saves=_saves([]), chances={'LAD': 0},
                      appearances={'tanner scott': 2, 'edwin diaz': 1})
    assert set(out['signal']) == {NO_CHANCES}
    assert not out['actionable'].any()


def test_setup_man_recording_a_save_is_ACTIONABLE():
    """Scott saving a game while Diaz is the presumed closer is exactly the
    event worth waking someone for."""
    wl = {'tanner scott': dict(name='Tanner Scott', team='LAD', expect='SETUP')}
    out = build_watch(watchlist=wl,
                      saves=_saves([('tanner scott', 'LAD', 1)]),
                      chances={'LAD': 2}, appearances={'tanner scott': 3})
    assert out.iloc[0]['signal'] == HOLDS_ROLE
    assert bool(out.iloc[0]['actionable']) is True


def test_closer_losing_a_save_to_a_teammate_is_ACTIONABLE():
    wl = {'luke weaver': dict(name='Luke Weaver', team='PIT', expect='CLOSER')}
    out = build_watch(watchlist=wl,
                      saves=_saves([('gregory soto', 'PIT', 2)]),
                      chances={'PIT': 2}, appearances={'luke weaver': 3})
    r = out.iloc[0]
    assert r['signal'] == ROLE_LOST
    assert r['saves_teammates'] == 2 and r['saves_self'] == 0
    assert bool(r['actionable']) is True


def test_closer_doing_his_job_is_not_actionable():
    wl = {'luke weaver': dict(name='Luke Weaver', team='PIT', expect='CLOSER')}
    out = build_watch(watchlist=wl,
                      saves=_saves([('luke weaver', 'PIT', 2)]),
                      chances={'PIT': 2}, appearances={'luke weaver': 4})
    assert out.iloc[0]['signal'] == HOLDS_ROLE
    assert bool(out.iloc[0]['actionable']) is False


def test_actionable_rows_sort_to_the_top():
    wl = {'a': dict(name='Quiet Guy', team='X', expect='CLOSER'),
          'b': dict(name='Lost It', team='Y', expect='CLOSER')}
    out = build_watch(watchlist=wl, saves=_saves([('other', 'Y', 1)]),
                      chances={'X': 0, 'Y': 1},
                      appearances={'a': 3, 'b': 3})
    assert out.iloc[0]['player'] == 'Lost It'


def test_teammate_saves_exclude_the_watched_arm():
    """A club's total saves minus his own must not double-count him."""
    wl = {'luke weaver': dict(name='Luke Weaver', team='PIT', expect='CLOSER')}
    out = build_watch(watchlist=wl,
                      saves=_saves([('luke weaver', 'PIT', 2)]),
                      chances={'PIT': 3}, appearances={'luke weaver': 5})
    assert out.iloc[0]['saves_teammates'] == 0


def test_empty_watchlist_is_empty_frame_not_error():
    assert build_watch(watchlist={}, saves=_saves([]), chances={},
                       appearances={}).empty


# ── mid-window TRADES ──────────────────────────────────────────────────────
def test_traded_arm_is_not_judged_on_his_old_clubs_games():
    """CAUGHT LIVE 2026-08-03. Weaver and Hoffman changed teams that day. The
    first cut compared saves they recorded for their OLD club against their NEW
    club's save chances and reported ROLE_LOST for both; Bednar came out at
    "4 saves of 3 chances", which is impossible and proved the join was wrong.

    A player with no appearances yet for the team he is being watched on has
    produced no evidence about that role.
    """
    sig, note = classify(saves_self=0, saves_teammates=1, team_chances=2,
                         appearances=0, games_with_team=0)
    assert sig == JUST_ARRIVED
    assert 'no appearances yet' in note.lower() or 'arrived' in note.lower()


def test_traded_arm_is_never_actionable():
    wl = {'luke weaver': dict(name='Luke Weaver', team='PIT', expect='CLOSER')}
    out = build_watch(watchlist=wl, saves=_saves([('gregory soto', 'PIT', 1)]),
                      chances={'PIT': 2}, appearances={'luke weaver': 0},
                      games_with_team={'luke weaver': 0})
    assert out.iloc[0]['signal'] == JUST_ARRIVED
    assert bool(out.iloc[0]['actionable']) is False


def test_once_he_pitches_for_the_new_club_the_watch_resumes():
    wl = {'luke weaver': dict(name='Luke Weaver', team='PIT', expect='CLOSER')}
    out = build_watch(watchlist=wl, saves=_saves([('gregory soto', 'PIT', 2)]),
                      chances={'PIT': 2}, appearances={'luke weaver': 3},
                      games_with_team={'luke weaver': 3})
    assert out.iloc[0]['signal'] == ROLE_LOST
    assert bool(out.iloc[0]['actionable']) is True


def test_saves_exceeding_chances_never_prints_an_impossible_ratio():
    """CAUGHT LIVE: Bednar showed "4 saves of 3 chances". A save can be earned
    on a lead the final margin does not reveal, so the derived chance count is
    a proxy that undercounts for some clubs. The row must not read as nonsense.
    """
    sig, note = classify(saves_self=4, saves_teammates=0, team_chances=3,
                         appearances=4)
    assert sig == HOLDS_ROLE
    assert 'of 3 chance' not in note
    assert 'proxy' in note or 'undercount' in note
