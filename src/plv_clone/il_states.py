"""Canonical ESPN IL-state sets (issue #28).

The SEVEN_DAY_DL (concussion IL) omission of 2026-08 survived because ~14
modules each hand-typed their own IL tuple; a state that appears once a
season never forces the bug. Every "is this player on the IL" gate must
import from here — tests/test_il_states.py pins the known consumers.

Semantics:
- IL_STATES_STRICT  — true IL/out states. Zeroes projections.
- IL_STATES_WITH_DTD — strict + DAY_TO_DAY, for pickup/streamer exclusion
  where "when in doubt, exclude" is the spec. NEVER use for projections:
  a DAY_TO_DAY pitcher with a confirmed probable still pitches (Soriano
  2026), and Josh's bench players are active (gotcha #7).
- LONG_IL_STATES    — definitively-out tier (60-day / IR / OUT).
"""

IL_STATES_STRICT = frozenset({
    'SEVEN_DAY_DL', 'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
    # alternate ESPN spellings seen in the wild (monte_carlo, 2026-05)
    'SEVEN_DAY_IL', 'TEN_DAY_IL', 'FIFTEEN_DAY_IL', 'SIXTY_DAY_IL',
    'INJURY_RESERVE', 'OUT',
    'IL', 'IL7', 'IL10', 'IL15', 'IL60',
})
IL_STATES_WITH_DTD = IL_STATES_STRICT | {'DAY_TO_DAY'}
LONG_IL_STATES = frozenset({'SIXTY_DAY_DL', 'SIXTY_DAY_IL', 'INJURY_RESERVE', 'OUT'})

# Expected-games credit for an IL'd player with NO known return date.
# Shorter mandated stints get more credit; unknown states get ZERO — an
# unknown state must never mean "project as healthy".
IL_PARTIAL_CREDIT = {
    'SEVEN_DAY_DL': 0.25, 'SEVEN_DAY_IL': 0.25,
    'TEN_DAY_DL': 0.20, 'TEN_DAY_IL': 0.20,
    'FIFTEEN_DAY_DL': 0.10, 'FIFTEEN_DAY_IL': 0.10,
    'SIXTY_DAY_DL': 0.0, 'SIXTY_DAY_IL': 0.0,
    'INJURY_RESERVE': 0.0, 'OUT': 0.0,
}


def partial_credit(state: str) -> float:
    return IL_PARTIAL_CREDIT.get(state, 0.0)
