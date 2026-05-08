"""league_config.py — single source of truth for the user's league configuration.

Captured from ESPN league settings (2026-05-06):

Roster slots per team:
  C  : 1     1B : 1     2B : 1     3B : 1     SS : 1
  MI : 1 (2B/SS eligibility)
  CI : 1 (1B/3B eligibility)
  UTIL: 1 (any hitter)
  OF : 5
  P  : 9 (any pitcher — flex SP/RP)
  BE : 4 (any position bench)
  IL : 3
  Total roster size: 26 / 22 starters

League size: 8 teams.

Scoring (ESPN standard for this league):
  Hitting: R(+1), TB(+1), RBI(+1), BB(+1), K(-1), HBP(+1), SB(+1)
  Pitching: IP(+3.3), H(-1), ER(-2), BB(-1), HBP(-1), K(+1), SV(+5), HD(+3)

Replacement-level cutoffs (rank past which a player is on the FA pool):
  These drive replacement_delta calculations across RH3/RP3/RP-RS2 + dashboard.

  Calibration: in an 8-team league with multi-position eligibility, ~12-16
  hitters per non-OF position are owned across rosters (1 starter × 8 +
  spillover from MI/CI/UTIL/bench). OF runs deeper (5 starter slots × 8 = 40
  + bench). Pitchers are 9 flex × 8 = 72 owned, split roughly 60/40 SP/RP.
"""
from __future__ import annotations

LEAGUE_SIZE = 8
ROSTER_SIZE = 26
STARTERS = 22

# Hitter replacement-level rank by position
# (rank past which a player is plausibly on the waiver wire)
HITTER_REPLACEMENT_RANK = {
    'C':    10,   # 8 starters + ~2 from bench/UTIL
    '1B':   12,   # 8 + spillover from CI/UTIL/bench
    '2B':   12,   # 8 + spillover from MI/UTIL/bench
    '3B':   12,   # 8 + spillover from CI/UTIL/bench
    'SS':   12,   # 8 + spillover from MI/UTIL/bench
    'OF':   45,   # 5 × 8 = 40 + ~5 spillover from UTIL/bench
    'DH':   16,   # via UTIL slot — top hitters claim this
    'UTIL': 16,
}

# Pitcher replacement-level rank
# 9 P slots × 8 teams = 72 pitchers owned, typical split:
#   ~50% SP starters (45 SPs) + ~30% RP starters (~25 RPs) + ~20% bench
SP_REPLACEMENT_RANK = 45
RP_REPLACEMENT_RANK = 30  # closers + top setup men

# ESPN scoring weights (used by FP formulas in build scripts)
HITTER_FP_WEIGHTS = {
    'R': 1, 'TB': 1, 'RBI': 1, 'BB': 1, 'K': -1, 'HBP': 1, 'SB': 1,
}
PITCHER_FP_WEIGHTS = {
    'IP': 3.3, 'H': -1, 'ER': -2, 'BB': -1, 'HBP': -1, 'K': 1, 'SV': 5, 'HD': 3,
}
PA_PER_GAME_LEAGUE = 3.5  # league avg, used for PA → game scaling
SEASON_GAMES = 162
