"""Season-drift and dead-parameter specs from the 2026-08-01 volume audit group.

(File name follows the `tests/test_volume_*.py` convention this audit track was
allocated; the items themselves are the group's drift/hygiene backlog — T43
rh3_april's hardcoded projection year, T49 the archetype builders' unread
`current_year` parameter.)

Both defects are latent rather than live: they are no-ops on today's substrate
and only bite on the calendar roll. That is exactly why they need pinning —
nothing else in the suite would notice them until an April 2027 run silently
projected nobody.
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

from plv_clone.models.xfp import rh3_april  # noqa: E402


# --------------------------------------------------- rh3_april season drift (T43)
def test_april_model_projects_the_newest_season_in_its_substrate():
    """The April hitter model follows the calendar, not a literal.

    Its three siblings (rh3, rp3, rprs2) were migrated to
    `proj_year = int(rolling['year'].max())`; rh3_april was the holdout. Because
    the model is out of framing for ~11 months a year and is not in the nightly
    chain, a stale literal would not surface until the first April run of the
    next season — and then as a silent 'no April-substrate data' skip, not an
    error.
    """
    substrate = pd.DataFrame({"year": [2025, 2026, 2027, 2027], "split_day": [20, 20, 12, 20]})
    assert rh3_april.projection_year(substrate) == 2027

    older = pd.DataFrame({"year": [2024, 2025], "split_day": [20, 20]})
    assert rh3_april.projection_year(older) == 2025


def test_april_model_embeds_no_hardcoded_season():
    """No season literal survives anywhere in the module's executable code.

    Structural rather than end-to-end by design: rh3_april.main() is a full
    train-and-project run over the real hitter substrate, so the cheap guard
    that a future edit cannot reintroduce the literal is an AST scan. Declared
    year CONSTANTS (TRAIN_YEARS) and the 2020-exclusion rule are legitimate and
    stay allowed.
    """
    tree = ast.parse(Path(inspect.getfile(rh3_april)).read_text(encoding="utf-8"))
    literals = sorted({
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int) and not isinstance(node.value, bool)
        and node.value >= 2021 and node.lineno > 100   # past the constants block
    })
    assert literals == [], (
        f"hardcoded season literal(s) at line(s) {literals} — use "
        "projection_year(rolling) so the model follows the substrate")


# ------------------------------------ archetype builder dead parameter (T49)
def _declared_but_unread_params(func) -> list[str]:
    """Parameter names the function declares but never reads in its body."""
    src = textwrap.dedent(inspect.getsource(func))
    fn = ast.parse(src).body[0]
    declared = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
    read = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
            and isinstance(n.ctx, ast.Load)}
    return [a for a in declared if a not in read]


def test_sp_archetype_panel_builder_declares_no_parameter_it_never_reads():
    """The ratings-panel signature must not promise scoping it does not do.

    `build_ratings_panel(current_year=2026)` read like a year filter and was
    never referenced: the body applies a GS floor, drops 2020, and computes the
    20-80 ratings WITHIN year via groupby('year') across the whole 2015-current
    panel — there is no year ceiling by design. A caller trusting the parameter
    would silently get the full panel back, and the default was one more season
    literal to rot. Threading it in would be a behavior change to the emitted
    ratings, not a cleanup, so the signature is what gives.
    """
    import build_sp_archetypes as sp_arch

    assert _declared_but_unread_params(sp_arch.build_ratings_panel) == []
