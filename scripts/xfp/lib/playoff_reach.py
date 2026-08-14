"""playoff_reach — P(you actually play period p), for weighting a RoS sum.

THE PROBLEM THIS FIXES (audit 2026-08-14)
-----------------------------------------
`build_period_xfp_board` summed xfp_p20..xfp_p23 into one `ros_total`. Periods
21/22/23 are playoff ROUNDS. Adding them undiscounted asserts P(reach round 3)
= 1.0, when the sim itself says P(title) = 0.157.

That miscounts more than it looks like. The two 2-week playoff rounds are the
biggest per-period buckets on the board, so undiscounted they dominate the sort
— the board silently ranks "best in the championship round" instead of "most
expected value from here", and credits a player fully for weeks that happen a
quarter of the time. Discounting also changes ADD/DROP logic: it pulls weight
back toward the periods that are certain to be played.

THE MODEL
---------
`season_sim.json` exports P(title), P(playoffs), a seed distribution and the
round structure, but not per-round win probabilities. Those are recoverable
under one stated assumption — a constant per-round win probability `q`:

    P(title) = P(bye) * q^(R-1) + P(no bye) * q^R

The RHS is strictly increasing in q on (0, 1), so bisection finds the unique
root. Then:

    reach(round 1) = P(no bye)
    reach(round k) = P(bye) * q^(k-2) + P(no bye) * q^(k-1),  k >= 2

By construction `reach(final) * q == P(title)`, so the weights can never
silently disagree with the payload that produced them — `reach_probabilities`
asserts exactly that before returning.

WHAT THIS IS NOT
----------------
Constant-q is an approximation. A 3-seed really is likelier to win round 1 than
round 2, and opponent strength is seed-conditional. The registered upgrade is
the joint bracket MC (seeding, byes, opponent-conditional draws) already
deferred in `title_equity.dtitle_for_ros_delta`; this module is the honest
linear read in the meantime, and says so in `status`.

Everything returns None rather than 1.0 when the payload cannot support it.
Defaulting a missing weight to 1.0 IS the bug being fixed — absence of a
probability is not certainty.

Rule 13: this is a display/decision-layer weight. It never touches
rh3/rp3/rprs2.
"""
from __future__ import annotations

from typing import Optional

# Bisection bounds/tolerance for solving the per-round win probability.
_Q_TOL = 1e-12
_Q_ITERS = 200


def _byes(playoff_teams: int, n_rounds: int) -> int:
    """Seeds that skip round 1 in a standard single-elimination bracket.

    A bracket with `n_rounds` rounds seats 2**n_rounds; whoever is missing gets
    a bye. 6 teams / 3 rounds -> 8 - 6 = 2 byes (the 1 and 2 seeds).
    """
    return max(0, 2 ** int(n_rounds) - int(playoff_teams))


def _solve_q(p_title: float, p_bye: float, p_nobye: float, n_rounds: int) -> Optional[float]:
    """Root of P(bye)*q^(R-1) + P(nobye)*q^R = P(title), by bisection."""
    if n_rounds < 1 or (p_bye + p_nobye) <= 0:
        return None

    def f(q: float) -> float:
        return (p_bye * q ** (n_rounds - 1) + p_nobye * q ** n_rounds) - p_title

    lo, hi = 0.0, 1.0
    if f(hi) < 0:
        # P(title) exceeds what winning every round can deliver — the payload is
        # internally inconsistent; refuse rather than clamp to a fake q=1.
        return None
    if f(lo) > 0:
        return None
    for _ in range(_Q_ITERS):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < _Q_TOL:
            break
    return (lo + hi) / 2


def reach_probabilities(payload: dict | None) -> dict:
    """P(play period p) for every period in the season, from a season_sim payload.

    -> {'reach': {period: prob} | None, 'q_per_round', 'p_bye', 'n_rounds',
        'status', 'note'}

    Regular-season periods (<= ``reg_season_end``) map to 1.0. Playoff periods
    map to the round-reach probabilities above. ``reach`` is None whenever the
    payload cannot support the computation.
    """
    out = {'reach': None, 'q_per_round': None, 'p_bye': None,
           'n_rounds': None, 'status': 'unavailable', 'note': ''}
    if not payload:
        out['note'] = 'season_sim.json missing — run /season-sim'
        return out

    josh = payload.get('josh') or {}
    rounds = payload.get('playoff_rounds') or []
    p_title = josh.get('p_title')
    p_playoffs = josh.get('p_playoffs')
    if not rounds:
        out['note'] = 'payload carries no playoff_rounds — cannot locate the rounds'
        return out
    if p_title is None or p_playoffs is None:
        out['note'] = ('payload carries no p_title / p_playoffs — cannot derive '
                       'per-round win probability; re-run /season-sim')
        return out

    round_periods = [int(r[0]) for r in rounds]
    n_rounds = len(round_periods)

    # P(bye) = probability of landing on a seed that skips round 1.
    # seed_dist_miss_then_1toN = [P(miss), P(seed 1), ..., P(seed N)].
    seed_dist = josh.get('seed_dist_miss_then_1toN') or []
    n_byes = _byes(int(payload.get('playoff_teams') or 0), n_rounds)
    if seed_dist and n_byes:
        p_bye = float(sum(seed_dist[1:1 + n_byes]))
    else:
        p_bye = 0.0
    p_bye = min(p_bye, float(p_playoffs))
    p_nobye = float(p_playoffs) - p_bye

    q = _solve_q(float(p_title), p_bye, p_nobye, n_rounds)
    if q is None:
        out['note'] = (f'could not solve a per-round win probability from '
                       f'p_title={p_title} with P(bye)={p_bye:.3f}, '
                       f'P(no bye)={p_nobye:.3f} over {n_rounds} rounds — the '
                       f'payload is internally inconsistent; re-run /season-sim')
        return out

    reach: dict[int, float] = {}
    reg_end = int(payload.get('reg_season_end') or (min(round_periods) - 1))
    for p in range(1, reg_end + 1):
        reach[p] = 1.0
    for k, p in enumerate(sorted(round_periods), start=1):
        if k == 1:
            reach[p] = p_nobye
        else:
            reach[p] = p_bye * q ** (k - 2) + p_nobye * q ** (k - 1)

    # Self-consistency: winning the final round IS the title. If this does not
    # hold, the weights disagree with the payload they came from and must not
    # ship — that is exactly the class of silent divergence this module exists
    # to prevent.
    final = reach[max(round_periods)]
    if abs(final * q - float(p_title)) > 1e-6:
        out['note'] = (f'internal check failed: reach(final)*q={final * q:.6f} != '
                       f'p_title={p_title}; refusing to emit weights')
        return out

    out.update(reach=reach, q_per_round=q, p_bye=p_bye, n_rounds=n_rounds,
               status='constant_q_v1',
               note=(f'constant per-round win probability q={q:.3f} solved from '
                     f'P(title)={p_title:.4f} over {n_rounds} rounds '
                     f'(P(bye)={p_bye:.3f}); an approximation — round-specific '
                     f'and opponent-conditional win rates need the joint '
                     f'bracket MC'))
    return out


def reach_weighted_total(per_period: dict[int, float],
                         reach: dict[int, float] | None) -> Optional[float]:
    """Sum period values weighted by P(the period is played).

    Returns None when ``reach`` is unavailable — a caller must not silently fall
    back to an unweighted sum, because an unweighted sum IS the assertion that
    every playoff round is certain.

    Raises KeyError for a period with no weight: dropping it would understate
    the total and keeping it at 1.0 would overstate it, and neither should
    happen quietly.
    """
    if reach is None:
        return None
    missing = [p for p in per_period if p not in reach]
    if missing:
        raise KeyError(f'no reach probability for period(s) {sorted(missing)}; '
                       f'weights cover {sorted(reach)}')
    return sum(v * reach[p] for p, v in per_period.items())


__all__ = ['reach_probabilities', 'reach_weighted_total']
