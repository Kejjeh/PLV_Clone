"""opponent_action_predictor.py --all-teams must never predict the user's
own team as an 'opponent' — issue #21."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import opponent_action_predictor as m  # noqa: E402
from plv_clone.league_config import MY_TEAM_NAME  # noqa: E402


def test_all_teams_excludes_my_team():
    teams = m.resolve_teams_to_predict(all_teams=True, team=None)
    assert MY_TEAM_NAME not in teams
    assert len(teams) == len(m.PROFILES) - 1


def test_all_teams_still_includes_every_real_opponent():
    teams = m.resolve_teams_to_predict(all_teams=True, team=None)
    for t in m.PROFILES:
        if t != MY_TEAM_NAME:
            assert t in teams


def test_explicit_team_still_allowed_even_if_it_is_my_team():
    """An explicit --team "New York Ligers" call is a deliberate ask, not
    the unintended --all-teams default — don't block it."""
    teams = m.resolve_teams_to_predict(all_teams=False, team=MY_TEAM_NAME)
    assert teams == [MY_TEAM_NAME]
