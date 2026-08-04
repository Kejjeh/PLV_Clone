"""Optimizer CLI seams: --scratch, --include, and a realized-FP pool leg.

WHY THESE EXIST (all three traced to live failures on 2026-08-01/02)

--scratch  The engine models an UNCONFIRMED start as ~0.80 likely to happen.
           Jose Soriano's 8/1 start was scratched (trade deadline), which Josh
           knew and the model did not. With the phantom start assumed, the SP
           cap read as full, so an added streamer scored ZERO in ~80% of trials
           and Jax priced at -0.32pp. Conditioned on the scratch he priced at
           +7.34pp. A 7.7pp swing driven entirely by state the tool had no way
           to accept.

--include  build_candidates takes the top-N FAs by PROJECTED window FP and
           drops anything with fp <= 0. Griffin Jax resolved to mlbam=None, so
           project_player found no start for him and he scored 0.00 -> he never
           entered the pool at all and the board could not see the best move on
           it. Bo/Grisham likewise could not be forced in for a head-to-head.

--realized The pool's only ranking key was the projection, so a player the
           model underrates cannot be surfaced no matter how much he is
           actually scoring. A second leg ranked on realized production fixes
           the blind spot without displacing the projected leg.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.xfp.run_weekly_optimizer import (  # noqa: E402
    parse_scratch, select_pool,
)


# ── --scratch parsing ──────────────────────────────────────────────────────
def test_parses_one_scratch():
    assert parse_scratch('Jose Soriano:2026-08-02') == [
        ('Jose Soriano', '2026-08-02')]


def test_parses_several_and_tolerates_whitespace():
    got = parse_scratch(' Jose Soriano : 2026-08-02 , Max Fried:2026-08-03 ')
    assert got == [('Jose Soriano', '2026-08-02'),
                   ('Max Fried', '2026-08-03')]


def test_empty_scratch_is_empty_list():
    assert parse_scratch(None) == []
    assert parse_scratch('') == []
    assert parse_scratch('   ') == []


@pytest.mark.parametrize('bad', [
    'Jose Soriano',              # no date
    'Jose Soriano:08-02-2026',   # wrong date order
    'Jose Soriano:2026-13-02',   # impossible month
    ':2026-08-02',               # no name
    'Jose Soriano:notadate',
])
def test_malformed_scratch_RAISES_rather_than_silently_dropping(bad):
    """A silently-ignored scratch is the exact bug this flag exists to fix:
    the run would look successful while the cap math stayed wrong. Loud or
    nothing."""
    with pytest.raises(ValueError):
        parse_scratch(bad)


# ── pool selection ─────────────────────────────────────────────────────────
def _c(name, bucket, fp, realized=0.0):
    return {'name': name, 'bucket': bucket, 'fp': fp, 'realized_fp': realized}


def test_projected_leg_takes_top_n_per_bucket():
    cands = [_c('h%d' % i, 'H', fp=10 - i) for i in range(6)]
    out = select_pool(cands, top_n=3, realized_n=0, include=())
    assert [c['name'] for c in out] == ['h0', 'h1', 'h2']


def test_buckets_are_independent():
    cands = ([_c('h%d' % i, 'H', fp=10 - i) for i in range(4)]
             + [_c('sp%d' % i, 'SP', fp=5 - i) for i in range(4)])
    out = select_pool(cands, top_n=2, realized_n=0, include=())
    assert sorted(c['name'] for c in out) == ['h0', 'h1', 'sp0', 'sp1']


def test_realized_leg_adds_players_the_projection_would_have_missed():
    """The whole point: a hitter the model rates 9th by projection but who is
    actually the top scorer must reach the pool."""
    cands = [_c('proj_star', 'H', fp=10.0, realized=1.0),
             _c('proj_ok', 'H', fp=9.0, realized=2.0),
             _c('underrated', 'H', fp=1.0, realized=99.0)]
    out = select_pool(cands, top_n=1, realized_n=1, include=())
    names = {c['name'] for c in out}
    assert names == {'proj_star', 'underrated'}


def test_the_two_legs_union_without_duplicating():
    cands = [_c('both', 'H', fp=10.0, realized=99.0),
             _c('other', 'H', fp=1.0, realized=1.0)]
    out = select_pool(cands, top_n=1, realized_n=1, include=())
    assert [c['name'] for c in out] == ['both']


def test_include_forces_a_player_outside_both_legs():
    cands = [_c('top', 'H', fp=10.0, realized=10.0),
             _c('Griffin Jax', 'SP', fp=0.0, realized=0.0)]
    out = select_pool(cands, top_n=1, realized_n=1, include=('Griffin Jax',))
    assert 'Griffin Jax' in {c['name'] for c in out}


def test_include_is_accent_and_case_insensitive():
    cands = [_c('José Soriano', 'SP', fp=0.0)]
    out = select_pool(cands, top_n=0, realized_n=0, include=('jose soriano',))
    assert [c['name'] for c in out] == ['José Soriano']


def test_include_marks_the_row_so_the_caller_can_report_it():
    cands = [_c('Griffin Jax', 'SP', fp=0.0)]
    out = select_pool(cands, top_n=0, realized_n=0, include=('Griffin Jax',))
    assert out[0].get('forced_include') is True


def test_unmatched_include_is_reported_not_swallowed():
    """A typo'd --include must not look like a successful run."""
    cands = [_c('top', 'H', fp=10.0)]
    missing = []
    out = select_pool(cands, top_n=1, realized_n=0, include=('Nobody Here',),
                      missing_out=missing)
    assert missing == ['Nobody Here']
    assert [c['name'] for c in out] == ['top']
