"""live_monitor.py must show the correct opponent for the 8 aliased MLB
teams (ARI/OAK/CHW/WSN/KCR/TBR/SFG/SDP) — issue #20.

The old inline check `team in (g['away_team'], TEAM_ALIASES.get(team))`
compares team against its OWN alias (e.g. 'ARI' == TEAM_ALIASES['ARI'] ==
'AZ'), which is never true by construction — so an aliased team playing
away always fell through to the `else` branch and showed its own team as
the opponent.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import live_monitor as m  # noqa: E402


def test_aliased_team_away_shows_real_opponent():
    """Diamondbacks (team='ARI') on the road at Houston: MLB schedule
    returns away_team='AZ' (Stats API spelling), home_team='HOU'."""
    g = {'away_team': 'AZ', 'home_team': 'HOU'}
    assert m._resolve_opponent('ARI', g) == 'HOU'


def test_aliased_team_home_shows_real_opponent():
    g = {'away_team': 'HOU', 'home_team': 'AZ'}
    assert m._resolve_opponent('ARI', g) == 'HOU'


def test_non_aliased_team_unaffected():
    g = {'away_team': 'NYY', 'home_team': 'BOS'}
    assert m._resolve_opponent('NYY', g) == 'BOS'
    assert m._resolve_opponent('BOS', g) == 'NYY'


def test_all_eight_aliased_teams_away():
    for espn_code, api_code in m.TEAM_ALIASES.items():
        g = {'away_team': api_code, 'home_team': 'XXX'}
        assert m._resolve_opponent(espn_code, g) == 'XXX', espn_code
