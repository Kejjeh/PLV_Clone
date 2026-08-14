"""playoff_calendar — period-conditional xFP (built TDD 2026-08-12).

Playoff periods are CALENDAR WINDOWS, not a RoS blob: 21 (1wk, cap 10),
22 and 23 (2wk, cap 20). A player's value in a round = his rate x the games
he is actually available for IN THAT WINDOW, and an SP's = the starts the
rotation calendar actually hands him, capped at the roster level.

Windows and caps are CONSUMED from the existing seams (resolve_period_meta,
sp_cap_for_period) at integration time — this module never re-derives them.
Pure functions over explicit dates; no IO.
"""
from __future__ import annotations

from datetime import date


ROTATION_LEN = 5  # team games per rotation turn (matches lib.availability)

# Calibration of the lattice to the repo's validated empirical rate
# (audit 2026-08-14). A clean 1-in-5 lattice over a ~6.3-game week implies 1.26
# starts per SP per week; CLAUDE.md's validated figure is 1.19. The ~6% gap is
# everything the clean lattice omits — skipped turns on off-day-heavy weeks,
# six-man stretches, spot bullpen games, short IL blips that never register as a
# stint.
#
# The lattice is kept for PLACEMENT (a start lands on a real date; period
# assignment needs that) and corrected for COUNTS. Uncorrected, the bias runs in
# the worst direction available: it inflates projected starts against a HARD
# league cap, turning "10.6 vs cap 10, spill 0.6" out of what is really 10.0 —
# a phantom decision.
TEAM_GAMES_PER_WEEK = 6.3
EMPIRICAL_STARTS_PER_WEEK = 1.19        # CLAUDE.md league constant
ROTATION_EFFICIENCY = EMPIRICAL_STARTS_PER_WEEK / (TEAM_GAMES_PER_WEEK / ROTATION_LEN)


def cap_absorbed_fp(arms: list[tuple[float, float]], *, cap: float) -> float:
    """Roster-level period SP FP under the start cap.

    `arms` = (fp_per_start, expected_starts) per SP. Starts past the cap score
    zero (league rule), and a rational manager burns cap on the BEST starts —
    so consume capacity greedily from the highest fp_per_start down, allowing
    fractional expected starts.
    """
    room = float(cap)
    total = 0.0
    for fp_per_start, starts in sorted(arms, key=lambda a: -a[0]):
        take = min(starts, room)
        total += fp_per_start * take
        room -= take
        if room <= 0:
            break
    return total


def cap_status(arms: list[tuple[float, float]], *, cap: float,
               tol: float = 1e-9) -> dict:
    """Is the period SP cap actually binding, and what does the spill cost?

    -> {'starts', 'cap', 'room', 'binding', 'raw', 'absorbed', 'lost_fp'}

    Decided on STARTS vs the cap — the quantity the league rule is written in —
    not on a float comparison of two FP totals. The board previously labelled a
    period BINDING whenever `raw > absorbed`; the greedy fill accumulates in a
    different order than the raw sum, so at exactly-the-cap the two differ in
    the last bit and 9.4 starts against a cap of 10 printed BINDING. That
    inverts the week's streaming advice: BINDING says "your next start scores
    zero", slack says "you have room to spend".
    """
    starts = float(sum(s for _, s in arms))
    raw = float(sum(r * s for r, s in arms))
    absorbed = cap_absorbed_fp(arms, cap=cap)
    over = starts - float(cap)
    binding = over > tol
    return {'starts': starts, 'cap': float(cap),
            'room': 0.0 if binding else max(0.0, -over),
            'binding': binding, 'raw': raw, 'absorbed': absorbed,
            'lost_fp': max(0.0, raw - absorbed) if binding else 0.0}


def sp_starts_in_window(*, team_dates: list[date], last_start_date: date,
                        window: tuple[date, date],
                        rotation_len: int = ROTATION_LEN) -> int:
    """Count this SP's projected starts inside [window_start, window_end].

    Rotation cycle: he starts every `rotation_len`-th TEAM game after his
    last start — off-days shift real dates, which is exactly why start counts
    must come from the team calendar, not from weeks x 1.19.

    PRECONDITION: `team_dates` must STRADDLE `last_start_date`. Phase — where
    in the rotation this pitcher currently sits — is carried entirely by how
    many team games have elapsed since he last threw. If the schedule begins
    after his last start there is nothing to count, the filter below becomes a
    no-op, and every pitcher on the team silently collapses onto the same
    lattice. That shipped on 2026-08-14 (all 8 active SPs got an identical
    7.0-start allocation), so it now raises instead of guessing.
    """
    if team_dates and min(team_dates) > last_start_date:
        raise ValueError(
            f"team_dates must straddle last_start_date to carry rotation "
            f"phase: schedule starts {min(team_dates)} but last start was "
            f"{last_start_date}. Widen the schedule pull backwards.")
    after = sorted(d for d in team_dates if d > last_start_date)
    start_dates = after[rotation_len - 1::rotation_len]
    lo, hi = window
    return sum(1 for d in start_dates if lo <= d <= hi)


def expected_starts_in_window(*, team_dates: list[date], last_start_date: date,
                              window: tuple[date, date],
                              rotation_len: int = ROTATION_LEN) -> float:
    """`sp_starts_in_window` corrected to the empirical starts-per-week rate.

    Use this wherever a start COUNT is being compared to something — the period
    SP cap, an opponent's rotation, a streaming budget. Use the raw
    `sp_starts_in_window` only when you need the integer PLACEMENT of turns.
    """
    raw = sp_starts_in_window(team_dates=team_dates,
                              last_start_date=last_start_date,
                              window=window, rotation_len=rotation_len)
    return raw * ROTATION_EFFICIENCY


def hitter_period_xfp(*, rate_fp_per_pa: float, pa_per_teamgame: float,
                      team_dates_in_window: list[date],
                      return_date: date | None = None) -> float:
    """Expected FP for one hitter in one period window, availability-aware."""
    games = [d for d in team_dates_in_window
             if return_date is None or d >= return_date]
    return rate_fp_per_pa * pa_per_teamgame * len(games)
