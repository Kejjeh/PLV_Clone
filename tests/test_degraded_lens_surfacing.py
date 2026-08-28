"""Issue #57: a verdict built on a degraded lens stack must SAY SO.

PR #56 added `result['degraded_lenses']`; nothing displayed it. A caller could
tell a degraded verdict from a sound one, but no caller actually did — which is
the same silent-verdict-change hazard don't-do #12 exists to stop (Bailey Ober
reads CAUTION with statcast_2026.parquet present and MIXED without it).

These tests pin the three seams: one owner of the wording, every result dict
carrying the field (batch path included, not just the live path), and the two
display surfaces plus the decision ledger actually consuming it.
"""
import pytest

lens_health = pytest.importorskip("scripts.xfp.lib.lens_health")
cards = pytest.importorskip("scripts.xfp.lib.triangulate_cards")
core = pytest.importorskip("scripts.xfp.lib.triangulate_core")

DEGRADED = [
    "extra_lenses.trend_lens: FileNotFoundError: statcast_2026.parquet",
    "extra_lenses.floor_adj: ValueError: no rows",
    "boom_stack.tier_lookup: KeyError: 'tier'",
]


# ── the wording has one owner ────────────────────────────────────────────────

def test_a_healthy_build_produces_no_caveat():
    assert lens_health.caveat([]) is None
    assert lens_health.caveat(None) is None


def test_caveat_names_the_lenses_and_counts_them():
    text = lens_health.caveat(DEGRADED)
    assert text is not None
    assert "extra_lenses.trend_lens" in text
    assert "boom_stack.tier_lookup" in text
    # Two failures inside extra_lenses are two named sections but the count
    # must match what's actually named, not the raw entry count.
    assert str(len(lens_health.sections(DEGRADED))) in text


def test_sections_dedupes_repeat_failures_in_one_lens():
    entries = ["a.b: ValueError: x", "a.b: KeyError: y", "c.d: OSError: z"]
    assert lens_health.sections(entries) == ("a.b", "c.d")


# ── every result dict carries the field ──────────────────────────────────────

def _assemble(**over):
    kw = dict(
        player={"display_name": "Test Arm", "bucket": "SP", "id": 1},
        bucket="SP", pl_main=None, pl_main_date=None, pl_stream="—",
        pl_stream_opp=None, pl_stream_date=None, model={}, arche={},
        verdict="HOLD", rationale="r", override_tag=None, verdict_top="HOLD",
        reason_tag=None, confidence=0.5, n_aligned=1, n_avail=2,
        watch_list=[], blend={}, il_status=None,
    )
    kw.update(over)
    return core.assemble_result(**kw)


def test_assemble_result_carries_degraded_lenses():
    """The batch/--cards-out path assembles here too. Before this, the field was
    attached only on the live triangulate_player path, so persisted FA cards
    silently lacked it — exactly the partial-fix shape (issue #69)."""
    assert _assemble(degraded_lenses=DEGRADED)["degraded_lenses"] == DEGRADED


def test_assemble_result_defaults_to_the_live_registry():
    lens_health.reset()
    try:
        lens_health.record("extra_lenses.trend_lens", FileNotFoundError("statcast"))
        result = _assemble()  # no degraded_lenses kwarg
        assert lens_health.sections(result["degraded_lenses"]) == (
            "extra_lenses.trend_lens",
        )
    finally:
        lens_health.reset()


def test_a_healthy_assemble_records_nothing():
    lens_health.reset()
    assert _assemble()["degraded_lenses"] == []


# ── the display surfaces consume it ──────────────────────────────────────────

def _card(**over):
    card = cards.build_card_data(_assemble(**over))
    # vclass is stamped by the dashboard builder, not build_card_data.
    card["vclass"] = cards._verdict_class(card)
    return card


def test_card_data_carries_it_and_card_html_renders_the_banner():
    card = _card(degraded_lenses=DEGRADED)
    assert card["degraded_lenses"] == DEGRADED

    html = cards._card_html(card, 0)
    assert 'class="degraded"' in html, "the banner element is missing"
    assert "degraded lens stack" in html
    # It must precede the verdict, or a reader reaches the verdict first.
    assert html.index('class="degraded"') < html.index('class="verdict"')


def test_a_healthy_card_renders_no_banner():
    html = cards._card_html(_card(), 0)
    assert 'class="degraded"' not in html


def test_the_dashboard_stylesheet_defines_the_banner():
    """A rendered banner with no rule is an invisible caveat."""
    from scripts.xfp.lib import triangulate_dashboard_style as style

    css = "".join(v for v in vars(style).values() if isinstance(v, str))
    assert ".degraded{" in css


def test_the_cli_card_prints_the_caveat():
    run_tri = pytest.importorskip("scripts.xfp.run_triangulate")
    player = {"display_name": "Test Arm", "bucket": "SP", "id": 1}
    model = {"rank": "—", "proj": None, "signal": None}
    out = run_tri.format_card(
        player, None, None, "—", None, model, {}, "HOLD", "rationale",
        degraded_lenses=DEGRADED,
    )
    assert "degraded lens stack" in out
    # Above the rationale: the caveat has to land before the reasoning.
    assert out.index("degraded lens stack") < out.index("rationale")

    clean = run_tri.format_card(
        player, None, None, "—", None, model, {}, "HOLD", "rationale",
    )
    assert "degraded lens stack" not in clean


# ── the ledger records it ────────────────────────────────────────────────────

def test_the_decision_record_carries_the_degradation():
    """Otherwise a verdict logged off a partial stack is settled later as though
    it were a full-stack read, with nothing in the record to say it wasn't."""
    from datetime import date

    from plv_clone.decisions.logger import from_triangulate_result

    record = from_triangulate_result(
        _assemble(degraded_lenses=DEGRADED), snapshot_date=date(2026, 8, 28)
    )
    assert record.inputs["degraded_lenses"] == DEGRADED

    clean = from_triangulate_result(
        _assemble(degraded_lenses=[]), snapshot_date=date(2026, 8, 28)
    )
    assert clean.inputs["degraded_lenses"] == []


# ── the skills that display verdicts carry the instruction ───────────────────

@pytest.mark.parametrize(
    "skill",
    ["triangulate", "player-verdict", "pitcher-compare", "hitter-compare",
     "fa-pickup-deep-dive"],
)
def test_verdict_displaying_skills_require_the_caveat(skill):
    """The code surfaces render it; a skill that synthesizes its own headline
    has to be told to. Issue #57 names these five."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / ".claude" / "skills" / skill / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "degraded_lenses" in text
    assert "lens_health" in text, "must point at the shared wording, not hand-roll it"
