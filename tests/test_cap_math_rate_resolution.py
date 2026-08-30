"""Regression tests for issue #61: an SP whose rate can't be resolved was
silently projected at 0.0 FP, which sorts him LAST in cap_excess_starts and so
makes him the first start benched — a wrong answer pointing in the worst
possible direction, with nothing to distinguish it from a real zero.

The first half of the fix (2026-08-27): accept an MLBAM-keyed rp3
(RosterPitcher carries the id; the lookup used to ignore it — CLAUDE.md
don't-do #10), and flag the filler zero via SPStart.rate_resolved /
unresolved_starts().

The second half (decided 2026-08-28): an unresolved start must not carry its
filler into BENCH-RANKING at all. impute_unresolved_fps() ranks it at the
MEDIAN of the same week's resolved starts — neutral: never benched purely for
being unknown (the Eury Pérez name-match miss read an elite arm as the week's
worst start), never auto-started either — and every consumer surfaces it
loudly (UNRESOLVED_IMPUTE_NOTE). cap_excess_starts stays pure and ranks what
it is given, so the check lives at each consumer's fp-list build site; the
discovery test at the bottom walks every call site to hold that (don't-do #18).
"""
import ast
from datetime import date
from pathlib import Path

import pytest

from plv_clone.cap_math import (
    UNRESOLVED_IMPUTE_NOTE,
    RosterPitcher,
    WeekProbables,
    cap_excess_starts,
    impute_unresolved_fps,
    unresolved_starts,
    weekly_sp_projection,
)

MON = date(2026, 4, 6)
SUN = date(2026, 4, 12)

REAL = RosterPitcher(name="Real Arm", mlbam_id=111, injury_status="ACTIVE", position="SP")
GHOST = RosterPitcher(name="Ghost", mlbam_id=222, injury_status="ACTIVE", position="SP")

PROBABLES = WeekProbables(
    starts={(111, date(2026, 4, 7)): "NYY", (222, date(2026, 4, 8)): "BOS"}
)


def _project(rp3):
    return weekly_sp_projection(
        roster=[REAL, GHOST],
        week_start=MON,
        week_end=SUN,
        rp3=rp3,
        probables=PROBABLES,
    )


@pytest.mark.parametrize(
    "rp3",
    [
        pytest.param({"Real Arm": 14.0}, id="name-keyed"),
        pytest.param({111: 14.0}, id="mlbam-keyed"),
    ],
)
def test_both_key_forms_resolve_and_an_unmatched_arm_is_flagged(rp3):
    """Name- and MLBAM-keyed rp3 dicts both work, and the miss is visible."""
    starts = _project(rp3)
    by_name = {s.pitcher_name: s for s in starts}

    assert by_name["Real Arm"].projected_fp == pytest.approx(14.0)
    assert by_name["Real Arm"].rate_resolved is True

    # The filler zero survives (callers depending on a float still get one)...
    assert by_name["Ghost"].projected_fp == 0.0
    # ...but is no longer indistinguishable from a genuine zero projection.
    assert by_name["Ghost"].rate_resolved is False
    assert [s.pitcher_name for s in unresolved_starts(starts)] == ["Ghost"]


def test_a_genuine_zero_is_not_reported_as_unresolved():
    """A pitcher actually projected at 0.0 is resolved — that IS his number."""
    starts = _project({"Real Arm": 14.0, "Ghost": 0.0})
    by_name = {s.pitcher_name: s for s in starts}

    assert by_name["Ghost"].projected_fp == 0.0
    assert by_name["Ghost"].rate_resolved is True
    assert unresolved_starts(starts) == []


def test_mlbam_wins_over_a_colliding_name():
    """Identity beats name when rp3 carries both (CLAUDE.md don't-do #10)."""
    starts = _project({111: 14.0, "Real Arm": 99.0, 222: 5.0})
    by_name = {s.pitcher_name: s for s in starts}
    assert by_name["Real Arm"].projected_fp == pytest.approx(14.0)
    assert by_name["Ghost"].projected_fp == pytest.approx(5.0)
    assert unresolved_starts(starts) == []


# ── impute_unresolved_fps: the decided bench-ranking fix (2026-08-28) ─────────


def test_imputation_replaces_the_filler_with_the_resolved_median():
    fps = [18.0, 14.0, 6.0, 0.0]
    resolved = [True, True, True, False]
    ranked, imputed_at = impute_unresolved_fps(fps, resolved)
    assert imputed_at == pytest.approx(14.0)          # median of 18/14/6
    assert ranked == [18.0, 14.0, 6.0, 14.0]
    assert fps == [18.0, 14.0, 6.0, 0.0]              # input not mutated


def test_an_unresolved_start_is_never_benched_purely_for_being_unresolved():
    """THE pin. Four starts, cap 3: an unresolved filler-0.0 start plus a
    resolved start BELOW the week median. Raw ranking benches the unresolved
    (the Eury Pérez failure — an unknown elite arm reads as the week's worst
    start); the decided ranking benches the genuinely-lowest RESOLVED start."""
    fps = [0.0, 18.0, 14.0, 6.0]          # index 0 = the unresolved filler
    resolved = [False, True, True, True]

    # the bug being pinned: fed raw, the filler sorts last and is benched
    assert cap_excess_starts(fps, cap=3) == {0}

    ranked, imputed_at = impute_unresolved_fps(fps, resolved)
    excess = cap_excess_starts(ranked, cap=3)
    assert 0 not in excess                # never benched for being unknown
    assert excess == {3}                  # the resolved 6.0 start sits out
    assert imputed_at == pytest.approx(14.0)


def test_neutral_placement_can_still_be_benched_on_merit():
    """Median imputation is neutral, not a free START: when `cap` resolved
    starts genuinely rank at-or-above the median, the unresolved start sits
    out — benched on merit, not for being unknown."""
    fps = [24.0, 22.0, 20.0, 10.0, 2.0, 0.0]   # index 5 unresolved
    resolved = [True] * 5 + [False]
    ranked, imputed_at = impute_unresolved_fps(fps, resolved)
    assert imputed_at == pytest.approx(20.0)   # median of the five resolved
    # top-3 by fp, stable ties: 24, 22, then the RESOLVED 20 (earlier index)
    assert cap_excess_starts(ranked, cap=3) == {3, 4, 5}


def test_imputation_edge_cases():
    # nothing unresolved -> unchanged, nothing imputed
    assert impute_unresolved_fps([5.0, 3.0], [True, True]) == ([5.0, 3.0], None)
    # EVERY start unresolved -> no median to anchor on: unchanged, None (the
    # caller falls back on its own, still loudly)
    assert impute_unresolved_fps([0.0, 0.0], [False, False]) == ([0.0, 0.0], None)
    # empty week
    assert impute_unresolved_fps([], []) == ([], None)
    # parallel-list contract
    with pytest.raises(ValueError):
        impute_unresolved_fps([1.0], [True, False])


# ── consumer: build_matchup_dashboard.apply_sp_cap ────────────────────────────


def test_apply_sp_cap_ranks_an_unresolved_start_at_the_week_median(capsys):
    """The matchup dashboard's cap must not auto-bench a rate_unresolved start
    (its fp is the conservative FALLBACK filler), and must say so loudly."""
    bmd = pytest.importorskip("scripts.xfp.build_matchup_dashboard")

    def one_sp(fp, unresolved=False):
        b = {'type': 'start', 'fp': fp}
        if unresolved:
            b['rate_unresolved'] = True
        return {'fp': fp, 'sigma2': 30.25, 'breakdown': [b]}

    proj = {
        'Ace': one_sp(18.0),
        'Mid': one_sp(14.0),
        'Low': one_sp(9.0),
        # fp is the conservative FALLBACK filler (8.0) — the lowest of the
        # week, so pre-fix the cap auto-benched this unknown arm. Ranked at
        # the resolved median (14.0) he stays in and Low sits out instead.
        'Eury Pérez': one_sp(8.0, unresolved=True),
    }
    removed = bmd.apply_sp_cap(proj, cap=3)

    # The resolved 9.0 start is the one benched — not the unresolved arm.
    assert proj['Low']['breakdown'][0].get('fp_capped') is True
    assert not proj['Eury Pérez']['breakdown'][0].get('fp_capped')
    assert removed == pytest.approx(9.0)
    # The projected mean keeps the conservative fallback (ranking-only imputation).
    assert proj['Eury Pérez']['fp'] == pytest.approx(8.0)

    out = capsys.readouterr().out
    assert UNRESOLVED_IMPUTE_NOTE in out
    assert 'Eury Pérez' in out


# ── discovery guard: every cap_excess_starts call site handles resolution ─────


def test_every_cap_excess_starts_call_site_handles_rate_resolution():
    """cap_excess_starts stays pure; the decided fix lives at each consumer's
    fp-list build site. DISCOVER the consumers instead of naming them
    (don't-do #18): any module under scripts/ that CALLS cap_excess_starts
    must reference impute_unresolved_fps in the same file — otherwise it is
    feeding raw fillers to the ranking and re-opening issue #61."""
    root = Path(__file__).resolve().parent.parent
    call_sites, offenders = [], []
    for path in sorted((root / 'scripts').rglob('*.py')):
        src = path.read_text(encoding='utf-8')
        if 'cap_excess_starts' not in src:
            continue
        tree = ast.parse(src, filename=str(path))
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and (
                (isinstance(n.func, ast.Name) and n.func.id == 'cap_excess_starts')
                or (isinstance(n.func, ast.Attribute)
                    and n.func.attr == 'cap_excess_starts'))
        ]
        if not calls:
            continue          # an import/re-export with no call site
        rel = str(path.relative_to(root))
        call_sites.append(rel)
        if 'impute_unresolved_fps' not in src:
            offenders.append(rel)
    # sanity on the discovery itself: the two known consumers must be found,
    # or every assertion below is vacuous
    assert len(call_sites) >= 2, f"discovery broke — found only {call_sites}"
    assert not offenders, (
        f"{offenders} call cap_excess_starts without an impute_unresolved_fps "
        f"rate-resolution step — unresolved starts will be auto-benched "
        f"(issue #61). Build the ranking list via "
        f"cap_math.impute_unresolved_fps and surface "
        f"UNRESOLVED_IMPUTE_NOTE in the output."
    )
