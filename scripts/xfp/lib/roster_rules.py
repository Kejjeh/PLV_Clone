"""roster_rules — BrownU legality for a proposed roster change.

The optimizer searches thousands of add/drop permutations, so legality has to be
a cheap pure function over roster composition, kept separate from the P(win)
scoring. ``delta_pwin`` deliberately scores ILLEGAL scenarios too (it is useful
to know what dropping a whole bucket would be worth); this module is what stops
an illegal one from being RECOMMENDED.

The rules encoded here are league constants, not preferences, with one exception
that is a standing owner rule and is marked as such.

  * 29 roster spots = 13 active hitters + 9 active pitchers + 4 bench + 3 IL.
  * BE counts as ACTIVE for scoring (gotcha #7 — Josh manages the lineup daily,
    so every healthy bench player gets activated before lock). A swap therefore
    does not need to land in a specific slot; it needs the roster to stay
    fillable.
  * **4 true RPs is a FLOOR, not a target** (standing owner rule, 2026-07-18):
    never propose an RP drop to absorb an SP return or free a spot. An RP may
    only be dropped for an RP. This is the one rule here that is a preference
    rather than a league constraint, and it is enforced anyway because violating
    it produces advice Josh will not take.
  * Positional coverage: you cannot drop the last player able to fill a required
    slot (the catcher case is the one that actually bites).
  * SP starts are capped per PERIOD, not per week, and the cap is period-aware
    (10 standard / 16 the 2026 ASG block / 20 a two-week playoff round). The cap
    is enforced inside the Monte Carlo (``_sp_side_total``) rather than here,
    because whether an added start scores depends on how many earlier starts
    actually occur in that trial. What this module checks is the cheap
    precondition: an SP add is pointless when zero cap remains.
"""
from __future__ import annotations

from typing import Iterable, Optional

# League roster spec (reference_league_rules.md)
ACTIVE_HITTERS = 13
ACTIVE_PITCHERS = 9
BENCH = 4
IL_SLOTS = 3
ROSTER_TOTAL = ACTIVE_HITTERS + ACTIVE_PITCHERS + BENCH + IL_SLOTS   # 29

# Standing owner rule (2026-07-18): a FLOOR, never a target.
RP_FLOOR = 4

# Slots that must be fillable. UTIL/BE/IL are deliberately absent — they are
# flex membership, not a position that needs covering.
REQUIRED_SLOTS = ('C', '1B', '2B', '3B', 'SS', 'OF')


class IllegalMove(ValueError):
    """A proposed change violates a roster rule."""


def _counts(roster: Iterable[dict]) -> dict:
    """Bucket counts over NON-IL players (IL'd players occupy no active slot)."""
    act = [p for p in roster if not p.get('on_il')]
    return {
        'H': sum(1 for p in act if p['bucket'] == 'H'),
        'SP': sum(1 for p in act if p['bucket'] == 'SP'),
        'RP': sum(1 for p in act if p['bucket'] == 'RP'),
        'total_active': len(act),
        'total': sum(1 for _ in roster),
    }


def _covers(roster: Iterable[dict], slot: str) -> int:
    """How many non-IL players can fill *slot*."""
    n = 0
    for p in roster:
        if p.get('on_il'):
            continue
        elig = p.get('eligible') or set()
        if slot in elig or p.get('espn_pos') == slot:
            n += 1
        elif slot == 'OF' and (p.get('espn_pos') in ('LF', 'CF', 'RF')
                               or {'LF', 'CF', 'RF'} & set(elig)):
            n += 1
    return n


def apply_swap(roster: list[dict], *, add: Optional[dict] = None,
               drop: Optional[dict] = None) -> list[dict]:
    """Return the roster after a swap. Pure — does not mutate the input."""
    out = [p for p in roster
           if not (drop and _same_player(p, drop))]
    if drop and len(out) == len(roster):
        raise IllegalMove(f"drop target {drop.get('name')!r} is not on the roster")
    if add:
        out = out + [{
            'name': add.get('name'), 'mlbam': add.get('mlbam'),
            'bucket': add.get('bucket'), 'espn_pos': add.get('espn_pos'),
            'slot': None, 'eligible': set(add.get('eligible') or ()),
            'on_il': False, 'injury_status': add.get('injury_status', ''),
        }]
    return out


def _same_player(a: dict, b: dict) -> bool:
    if a.get('mlbam') and b.get('mlbam'):
        return int(a['mlbam']) == int(b['mlbam'])
    return (a.get('name') or '').lower() == (b.get('name') or '').lower()


#: public alias — the optimizer's undo-suppression and pair-legality checks
#: legitimately need player identity; keep them off the private name
same_player = _same_player


def lineup_capacity_problem(*, n_hitters_after: int, hitter_games_after: float,
                            days_remaining: int) -> Optional[str]:
    """Flag an add whose games CANNOT actually be played.

    This guards a real limitation of the Monte-Carlo engine. ``_classify`` counts
    every non-IL player at their team's full remaining game count, because BE
    counts as active for Josh (gotcha #7 — he rotates the bench in daily). That
    is a good approximation while total desired hitter-games fit inside the
    available lineup slots. It stops being one the moment they don't:

        available hitter-game slots = ACTIVE_HITTERS x days_remaining

    Carrying a 14th hitter is perfectly legal — that is what the bench is for —
    but he cannot play every day, and the engine has no notion of a daily lineup,
    so it would credit games that are physically unplayable. An optimizer
    actively searching for adds will find and exploit exactly that gap: in the
    first live run, adding a 14th hitter over 4 remaining days wanted 56
    hitter-games against 52 slots, and the ~4 unplayable games were worth about
    the entire claimed edge.

    Returns a reason string when the add over-subscribes the lineup, else None.
    """
    if days_remaining is None or days_remaining <= 0:
        return None
    slots = ACTIVE_HITTERS * int(days_remaining)
    if hitter_games_after <= slots:
        return None
    over = hitter_games_after - slots
    return (f"{n_hitters_after} hitters want {hitter_games_after:.0f} games but only "
            f"{slots} lineup slots exist ({ACTIVE_HITTERS} x {days_remaining}d) — "
            f"{over:.0f} games could not be played, and the engine would credit "
            f"them anyway")


def check_swap(roster: list[dict], *, add: Optional[dict] = None,
               drop: Optional[dict] = None,
               cap_remaining: Optional[int] = None,
               hitter_games: Optional[dict] = None,
               days_remaining: Optional[int] = None) -> list[str]:
    """Return a list of rule violations (empty list == legal).

    Returning reasons rather than a bare bool is deliberate: the optimizer
    reports WHY a tempting move was excluded, which is most of the value when the
    answer is "you cannot do the obvious thing".
    """
    problems: list[str] = []

    if add is None and drop is None:
        return problems

    if drop is not None and not any(_same_player(p, drop) for p in roster):
        return [f"{drop.get('name')!r} is not on the roster"]

    if drop is not None and drop.get('on_il'):
        # Not a rule violation, but a real trap: dropping an IL'd stash frees an
        # IL slot, not an active one, so it does not solve an active-roster crunch.
        problems.append(
            f"{drop.get('name')} is on IL — dropping frees an IL slot, not an "
            f"active one")

    after = apply_swap(roster, add=add, drop=drop)
    before_c, after_c = _counts(roster), _counts(after)

    # roster size
    if after_c['total'] > ROSTER_TOTAL:
        problems.append(
            f"roster would hold {after_c['total']} > {ROSTER_TOTAL} players "
            f"(an add needs a matching drop)")

    # 4-RP floor, and the RP-for-RP rule
    if after_c['RP'] < RP_FLOOR:
        problems.append(
            f"RP count would fall to {after_c['RP']} < floor {RP_FLOOR} "
            f"(standing rule 2026-07-18: 4 true RPs is a FLOOR, never a target)")
    if (drop is not None and drop.get('bucket') == 'RP'
            and before_c['RP'] <= RP_FLOOR
            and (add is None or add.get('bucket') != 'RP')):
        problems.append(
            f"at the RP floor an RP may only be dropped for another RP — "
            f"{drop.get('name')} out for a {add.get('bucket') if add else 'nothing'} "
            f"is exactly the move the standing rule forbids")

    # active-bucket sufficiency: enough bodies to fill the required active slots
    if after_c['H'] < ACTIVE_HITTERS:
        problems.append(
            f"only {after_c['H']} healthy hitters for {ACTIVE_HITTERS} active "
            f"hitter slots")
    if after_c['SP'] + after_c['RP'] < ACTIVE_PITCHERS:
        problems.append(
            f"only {after_c['SP'] + after_c['RP']} healthy pitchers for "
            f"{ACTIVE_PITCHERS} active pitcher slots")

    # positional coverage — the catcher case is the one that actually bites
    if drop is not None and drop.get('bucket') == 'H':
        for slot in REQUIRED_SLOTS:
            if _covers(roster, slot) > 0 and _covers(after, slot) == 0:
                problems.append(
                    f"dropping {drop.get('name')} leaves nobody eligible at {slot}")

    # SP add with no cap left cannot score
    if (add is not None and add.get('bucket') == 'SP'
            and cap_remaining is not None and cap_remaining <= 0):
        problems.append(
            "no SP starts remain under the period cap, so an added start cannot "
            "score this period")

    # lineup capacity: would the added hitter's games actually be playable?
    if (add is not None and add.get('bucket') == 'H'
            and hitter_games is not None and days_remaining):
        games = 0.0
        for p in after:
            if p.get('bucket') != 'H' or p.get('on_il'):
                continue
            key = p.get('mlbam') or p.get('name')
            g = hitter_games.get(key)
            if g is None:
                g = hitter_games.get(p.get('name'))
            games += float(g if g is not None else days_remaining)
        why = lineup_capacity_problem(
            n_hitters_after=after_c['H'], hitter_games_after=games,
            days_remaining=int(days_remaining))
        if why:
            problems.append(why)

    return problems


def is_legal(roster: list[dict], **kw) -> bool:
    return not check_swap(roster, **kw)


__all__ = [
    'ACTIVE_HITTERS', 'ACTIVE_PITCHERS', 'BENCH', 'IL_SLOTS', 'ROSTER_TOTAL',
    'RP_FLOOR', 'REQUIRED_SLOTS', 'IllegalMove',
    'apply_swap', 'check_swap', 'is_legal',
]
