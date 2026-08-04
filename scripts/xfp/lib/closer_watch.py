"""closer_watch — detect ninth-inning ROLE CHANGE, and know when you can't.

WHY THIS EXISTS
On 2026-08-03 the Dodgers' closer job changed hands (Roberts: "When Diaz
returns, it will be in the closer role") and no surface in this repo noticed,
because the only evidence a box score carries is who recorded saves — and LA
had generated ZERO save opportunities in the five days since. Reasoning from
usage, I concluded twice that the role had NOT changed. Both times the data was
silent, not negative.

So the core rule here: a watched arm with no team save chances since the last
check is reported as **NO_CHANCES**, never as "role intact". Absence of a save
is only informative when there was a save to take.

SIGNALS (per watched pitcher, since the previous run)
  HOLDS_ROLE   he recorded >=1 save in the window
  ROLE_LOST    a TEAMMATE recorded a save in the window and he did not
  NO_CHANCES   his club had no save opportunities -> NOTHING IS KNOWN
  NOT_PITCHING no appearances at all in the window (possible IL / usage change)

A save opportunity is a win by 1-3 runs, the same definition used by the RP RoS
work; it is derived from final scores because the box store has no blown-save
column.
"""
from __future__ import annotations

import pandas as pd

HOLDS_ROLE = 'HOLDS_ROLE'
ROLE_LOST = 'ROLE_LOST'
NO_CHANCES = 'NO_CHANCES'
NOT_PITCHING = 'NOT_PITCHING'
JUST_ARRIVED = 'JUST_ARRIVED'


def classify(*, saves_self: int, saves_teammates: int, team_chances: int,
             appearances: int, games_with_team=None) -> tuple:
    """-> (signal, note). Pure; the whole point of the module.

    Order matters. NO_CHANCES is checked BEFORE anything that could be read as
    negative evidence, because a quiet week on a club that never led by three
    tells you nothing about who closes.
    """
    if games_with_team is not None and games_with_team <= 0:
        return JUST_ARRIVED, ('no appearances yet for this club '
                              '(traded/recalled) - role status UNKNOWN')
    if team_chances <= 0:
        return NO_CHANCES, ('club had no save opportunities in the window — '
                            'role status UNKNOWN, not confirmed')
    if saves_self > 0:
        # A save can be earned on a lead the FINAL margin does not show
        # (closer enters up 3, his side adds one). Measured 2026-08-03:
        # 61 computed chances vs 55 actual saves league-wide is sound in
        # aggregate, but 3 of 30 clubs showed saves > chances in one week.
        # Never print an impossible ratio.
        if saves_self > team_chances:
            return HOLDS_ROLE, (f'recorded {saves_self} save(s); the '
                                'derived chance count is a final-margin '
                                'proxy and undercounts here')
        return HOLDS_ROLE, f'recorded {saves_self} save(s) of {team_chances} chance(s)'
    if saves_teammates > 0:
        return ROLE_LOST, (f'{saves_teammates} save(s) went to a teammate over '
                           f'{team_chances} chance(s) and he took none')
    if appearances == 0:
        return NOT_PITCHING, 'no appearances at all in the window'
    return NO_CHANCES, (f'{team_chances} chance(s) existed but produced no save '
                        '(blown/extra-inning) — inconclusive')


def save_opportunities(scores: pd.DataFrame) -> pd.DataFrame:
    """Final scores -> per-team save-opportunity flags.

    `scores` needs columns team, date, margin (team score minus opponent).
    A save opportunity is a win by 1-3 runs.
    """
    if scores is None or not len(scores):
        return pd.DataFrame(columns=['team', 'date', 'save_opp'])
    d = scores.copy()
    d['save_opp'] = (d['margin'] > 0) & (d['margin'] <= 3)
    return d[['team', 'date', 'save_opp']]


def build_watch(*, watchlist: dict, saves: pd.DataFrame,
                chances: dict, appearances: dict,
                games_with_team=None) -> pd.DataFrame:
    """One row per watched arm.

    watchlist    {player_key: {'name':.., 'team':.., 'expect':'CLOSER'|'SETUP'}}
    saves        rows of (player_key, team, n) over the window
    chances      {team: n_save_opportunities}
    appearances  {player_key: n_appearances}
    """
    cols = ['player', 'team', 'expect', 'signal', 'note', 'saves_self',
            'saves_teammates', 'team_chances', 'appearances', 'actionable']
    if not watchlist:
        return pd.DataFrame(columns=cols)
    sv = (saves.groupby(['player_key'])['n'].sum().to_dict()
          if saves is not None and len(saves) else {})
    team_sv = (saves.groupby(['team'])['n'].sum().to_dict()
               if saves is not None and len(saves) else {})
    out = []
    for k, meta in watchlist.items():
        team = meta.get('team')
        mine = int(sv.get(k, 0))
        tm = max(int(team_sv.get(team, 0)) - mine, 0)
        ch = int(chances.get(team, 0))
        ap = int(appearances.get(k, 0))
        gwt = (games_with_team or {}).get(k) if games_with_team else None
        sig, note = classify(saves_self=mine, saves_teammates=tm,
                             team_chances=ch, appearances=ap,
                             games_with_team=gwt)
        # Only a signal that CONTRADICTS the expected role needs a human.
        expect = (meta.get('expect') or '').upper()
        actionable = ((expect == 'CLOSER' and sig in (ROLE_LOST, NOT_PITCHING))
                      or (expect == 'SETUP' and sig == HOLDS_ROLE))
        out.append(dict(player=meta.get('name', k), team=team, expect=expect,
                        signal=sig, note=note, saves_self=mine,
                        saves_teammates=tm, team_chances=ch, appearances=ap,
                        actionable=actionable))
    order = {ROLE_LOST: 0, HOLDS_ROLE: 1, NOT_PITCHING: 2, NO_CHANCES: 3,
             JUST_ARRIVED: 4}
    return (pd.DataFrame(out)
            .assign(_o=lambda d: d['signal'].map(order))
            .sort_values(['actionable', '_o'], ascending=[False, True])
            .drop(columns='_o').reset_index(drop=True))
