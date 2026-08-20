"""Issue #28 — one canonical IL-state definition, consumed everywhere.

The SEVEN_DAY_DL (concussion IL) omission survived because ~14 modules each
kept a private hand-typed IL tuple. These tests pin every known gate to the
canonical sets in plv_clone.il_states so membership can never drift again.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / 'scripts' / 'xfp', ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plv_clone import il_states as canon


def test_canonical_sets_cover_concussion_il():
    assert 'SEVEN_DAY_DL' in canon.IL_STATES_STRICT
    assert 'IL7' in canon.IL_STATES_STRICT
    assert 'DAY_TO_DAY' not in canon.IL_STATES_STRICT
    assert canon.IL_STATES_WITH_DTD == canon.IL_STATES_STRICT | {'DAY_TO_DAY'}
    assert canon.LONG_IL_STATES < canon.IL_STATES_STRICT


def test_partial_credit_has_concussion_entry_and_safe_default():
    # 7-day IL is the shortest stint, so its credit must be >= the 10-day's.
    assert canon.partial_credit('SEVEN_DAY_DL') >= canon.partial_credit('TEN_DAY_DL')
    # An unknown/future ESPN state must NEVER mean full credit.
    assert canon.partial_credit('SOME_FUTURE_STATE') == 0.0


def test_consumers_import_the_canonical_sets():
    from lib import injury_status
    import build_matchup_dashboard as bmd
    import monte_carlo
    import fix_il_flag_from_espn
    import fa_move_planner_v2
    from lib import triangulate_core, triangulate_cards, rehab_watchlist
    from plv_clone import cap_math
    import build_il_stash_boards
    import build_playoff_board

    assert injury_status._IL_STATES == canon.IL_STATES_STRICT
    assert bmd.IL_INJURY_STATES == canon.IL_STATES_WITH_DTD
    assert bmd._IL_PARTIAL_CREDIT is canon.IL_PARTIAL_CREDIT
    for s in (monte_carlo.IL_STATES, fix_il_flag_from_espn.IL_STATUSES,
              fa_move_planner_v2.IL_STATUSES, triangulate_cards._IL_STATES,
              cap_math.IL_STATUSES, build_il_stash_boards.IL_STATES,
              build_playoff_board.IL_STATES):
        assert 'SEVEN_DAY_DL' in s, s
    assert 'SEVEN_DAY_DL' in rehab_watchlist.REAL_IL_STATES
    assert 'SEVEN_DAY_DL' in triangulate_core.__dict__.get('IL_CAVEAT_STATES', canon.IL_STATES_STRICT)


def test_matchup_is_il_player_semantics_preserved():
    """Gotcha #7: BE slot stays active; only IL slot/status zeroes a player."""
    from types import SimpleNamespace
    import build_matchup_dashboard as bmd
    concussed_be = SimpleNamespace(injuryStatus='SEVEN_DAY_DL', lineup_slot='BE')
    healthy_be = SimpleNamespace(injuryStatus='ACTIVE', lineup_slot='BE')
    assert bmd.is_il_player(concussed_be) is True
    assert bmd.is_il_player(healthy_be) is False
