"""Guard against the repo-root path-drift bug class.

On 2026-07-19 (commit b42b561) 96 scripts were archived one directory deeper
without updating their hardcoded ``ROOT = Path(__file__).resolve().parents[N]``.
``ROOT`` silently began resolving to ``<repo>/scripts``, so baseline data files
failed ``.exists()`` and were replaced with ``0.0`` constants — a Rule 9 baseline
degraded without a single error message. Measured cost on rh3: cross-year r
0.6418 -> 0.6050 (-0.0368) against a +0.005 promotion gate.

The bug is fully machine-detectable, so it should never recur. See
``docs/rh3_harness_root_bug_2026-07-28.md``.

Two tests:
  1. every hardcoded ``parents[N]`` repo-root anchor still resolves to the repo root
  2. the preferred marker-based form actually finds the root from any depth
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())

SKIP_DIRS = {".git", "node_modules", ".cache", ".venv", "venv", "__pycache__",
             "xfp-model", "build",
             # agent worktrees are full checkouts whose parents[N] anchors
             # correctly resolve to the WORKTREE root, not this repo's — the
             # scan must never descend into them (found when a leftover T48
             # worktree produced 265 false anchors, 2026-08-01)
             ".claude"}

# Variable names that denote the repository root by convention.
ROOTISH_NAMES = {"ROOT", "_ROOT", "REPO_ROOT", "_REPO_ROOT", "PROJECT_ROOT", "pre_reg_path"}

# Anchors that deliberately point somewhere OTHER than the repo root.
# (path, variable) -> what it is actually anchored to, for the failure message.
INTENTIONAL_NON_ROOT = {
    ("scripts/xfp/lib/rating_arc.py", "_XFP"): "scripts/xfp (added to sys.path)",
}

ASSIGN_RE = re.compile(
    r"^[ \t]*(?P<var>[A-Za-z_]\w*)\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[(?P<n>\d+)\]\s*$",
    re.M,
)


def _python_files() -> list[Path]:
    return [
        f
        for f in REPO_ROOT.rglob("*.py")
        if not (SKIP_DIRS & set(f.parts)) and f != Path(__file__)
    ]


def _anchors() -> list[tuple[Path, str, int]]:
    """Every `VAR = Path(__file__).resolve().parents[N]` in the repo."""
    found = []
    for f in _python_files():
        try:
            src = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "parents[" not in src:
            continue
        for m in ASSIGN_RE.finditer(src):
            found.append((f, m.group("var"), int(m.group("n"))))
    return found


def test_hardcoded_parents_anchors_resolve_to_repo_root():
    """A `parents[N]` repo-root anchor must actually land on the repo root.

    If this fails, a file moved and its hardcoded depth did not follow. Fix by
    switching that line to the marker-based form::

        ROOT = next(p for p in Path(__file__).resolve().parents
                    if (p / "pyproject.toml").is_file())

    which survives any future move. If the anchor intentionally points somewhere
    else, add it to INTENTIONAL_NON_ROOT above.
    """
    anchors = _anchors()
    assert anchors, "found no parents[N] anchors at all — the detection regex is probably broken"

    broken = []
    for f, var, n in anchors:
        rel = f.relative_to(REPO_ROOT).as_posix()
        if (rel, var) in INTENTIONAL_NON_ROOT:
            continue
        if var not in ROOTISH_NAMES and not re.search(
            rf"\b{re.escape(var)}\s*/\s*['\"](data|src|scripts|app|docs|tests)['\"]",
            f.read_text(encoding="utf-8"),
        ):
            continue  # not a repo-root anchor
        resolved = f.parents[n] if n < len(f.parents) else None
        if resolved != REPO_ROOT:
            broken.append(f"  {rel}\n      {var} = parents[{n}] -> {resolved}")

    assert not broken, (
        "repo-root anchors that no longer resolve to the repo root "
        f"({len(broken)}):\n" + "\n".join(broken)
    )


def test_intentional_non_root_anchors_are_still_accurate():
    """Keep the allowlist honest: entries must exist and still be non-root.

    Without this, a stale allowlist entry would mask a real regression.
    """
    for (rel, var), description in INTENTIONAL_NON_ROOT.items():
        f = REPO_ROOT / rel
        assert f.is_file(), f"stale allowlist entry: {rel} no longer exists — remove it"
        src = f.read_text(encoding="utf-8")
        m = re.search(
            rf"^[ \t]*{re.escape(var)}\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]\s*$",
            src,
            re.M,
        )
        assert m, f"stale allowlist entry: {rel} no longer defines {var} that way — remove it"
        resolved = f.parents[int(m.group(1))]
        assert resolved != REPO_ROOT, (
            f"{rel}:{var} now resolves to the repo root ({description} no longer applies) "
            "— drop it from INTENTIONAL_NON_ROOT so it is covered by the main test"
        )


# ── absolute machine paths (audit 2026-08-01, item 47) ───────────────────────
#
# ASSIGN_RE above only sees the `parents[N]` form. The OTHER way a module pins
# itself to one machine is a string literal — `ROOT = 'c:/Users/Joshua/plv_clone'`
# — which the parents[N] guard cannot see at all. Same bug class (a checkout
# anywhere else silently resolves to a path that does not exist, and the
# .exists() fallbacks turn that into 0.0 constants rather than an error), caught
# by a different detector.
#
# This is a RATCHET, not a cleanup: the existing offenders are named below so
# the guard is green today and any NEW one is red. Work the list down by
# switching each file to the marker form documented in this module's docstring.

ABS_LITERAL_RE = re.compile(r"""['"](?:[A-Za-z]:[\\/]|/Users/|/home/)""")

# Trees whose modules must be portable. Deliberately excludes the dead/one-off
# trees (also .gitignore'd out of the CodeGraph index) — they are not run.
SCANNED_TREES = ("scripts/xfp", "src/plv_clone")
EXCLUDED_SUBTREES = {"research", "_research", "archive", "_attic", "_oneoff", "_adhoc"}


def _scanned_modules(root: Path | None = None) -> list[Path]:
    root = root or REPO_ROOT
    out = []
    for tree in SCANNED_TREES:
        for f in (root / tree).rglob("*.py"):
            if EXCLUDED_SUBTREES & set(f.parts) or SKIP_DIRS & set(f.parts):
                continue
            out.append(f)
    return sorted(out)


def absolute_path_literals(files) -> dict[str, int]:
    """{repo-relative path: count} for every module embedding an absolute path."""
    hits: dict[str, int] = {}
    for f in files:
        try:
            src = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n = len(ABS_LITERAL_RE.findall(src))
        if n:
            hits[f.relative_to(REPO_ROOT).as_posix()] = n
    return hits


# Measured 2026-08-01 with the detector above: 46 modules, 48 literals. Almost
# every one is the same `ROOT = Path('c:/Users/Joshua/plv_clone')`; the two
# exceptions are `scripts/xfp/mc_signal_a_bootstrap.py` (two r-string data paths)
# and `scripts/xfp/run_whats_new.py` (an Obsidian vault path OUTSIDE the repo).
# `src/plv_clone/paths.py` is a detector false positive — its only match is the
# docstring line quoting the bad pattern it exists to replace.
#
# SHRINK THIS LIST, never grow it. These are converted in small batches (change
# ROOT, re-run the owning test file) precisely because a wrong root resolution in
# a model-adjacent script reproduces the 2026-07-19 b42b561 bug this module
# guards: rh3 cross-year r 0.6418 -> 0.6050 with no error message.
ABSOLUTE_PATH_LITERAL_ALLOWLIST: frozenset[str] = frozenset({
    "scripts/xfp/_ad_hoc_elly_langford_swap.py",
    "scripts/xfp/_harrison_meyer_scan.py",
    "scripts/xfp/analyze_catcher_framing_boom.py",
    "scripts/xfp/analyze_traj_redundancy.py",
    "scripts/xfp/apply_deep_pitch_shape.py",
    "scripts/xfp/audit_model_ceiling.py",
    "scripts/xfp/audit_pl_name_resolution.py",
    "scripts/xfp/build_historical_panel.py",
    "scripts/xfp/build_live_tags_retroactive.py",
    "scripts/xfp/build_recform_hot_retroactive.py",
    "scripts/xfp/check_xwoba_gap_symmetry.py",
    "scripts/xfp/closer_persistence.py",
    "scripts/xfp/compare_erceg_fairbanks.py",
    "scripts/xfp/compare_pl_top100_sp.py",
    "scripts/xfp/compare_pl_top150_hitters.py",
    "scripts/xfp/compare_pl_top50.py",
    "scripts/xfp/compare_to_pitcherlist.py",
    "scripts/xfp/drift_integration_backtest.py",
    "scripts/xfp/fit_rp_with_pl_coefs.py",
    "scripts/xfp/fit_weight_blend.py",
    "scripts/xfp/fit_weight_blend_cleanup3.py",
    "scripts/xfp/fit_weight_blend_live_tags.py",
    "scripts/xfp/fit_weight_blend_recform.py",
    "scripts/xfp/fit_weight_blend_rp_proxy.py",
    "scripts/xfp/fit_weight_blend_with_pl.py",
    "scripts/xfp/fit_weight_blend_within_season.py",
    "scripts/xfp/hitter_xwoba_residual.py",
    "scripts/xfp/lose_faith_threshold.py",
    "scripts/xfp/mc_signal_a_bootstrap.py",
    "scripts/xfp/missed_breakout_scan.py",
    "scripts/xfp/per_start_predictor_battle.py",
    "scripts/xfp/playoff_peak_analysis.py",
    "scripts/xfp/preseason_only_benchmark.py",
    "scripts/xfp/recalibrate_sp_rolling_window.py",
    "scripts/xfp/run_whats_new.py",
    "scripts/xfp/starts_per_week_analysis.py",
    "scripts/xfp/temp_player_profile.py",
    "scripts/xfp/validate_drift_v5_fixes.py",
    "scripts/xfp/validate_pitch_shape_convergence.py",
    "scripts/xfp/validate_pitch_shape_deep.py",
    "scripts/xfp/validate_pitch_shape_early_warning.py",
    "scripts/xfp/validate_rolling_trend.py",
    "scripts/xfp/validate_six_pack.py",
    "scripts/xfp/validate_sustainability.py",
    "scripts/xfp/verify_top2_picks.py",
    "src/plv_clone/paths.py",
})

# Literal count at the same measurement. The per-file allowlist catches a NEW
# file; this catches a new literal inside an already-listed one.
ABSOLUTE_PATH_LITERAL_BASELINE = 48


def test_no_module_outside_the_allowlist_embeds_an_absolute_machine_path():
    """A module that hardcodes `c:/Users/...` only works on one machine.

    Fix by resolving the root instead::

        ROOT = next(p for p in Path(__file__).resolve().parents
                    if (p / "pyproject.toml").is_file())
    """
    hits = absolute_path_literals(_scanned_modules())
    new = {k: v for k, v in hits.items() if k not in ABSOLUTE_PATH_LITERAL_ALLOWLIST}
    assert not new, (
        f"{len(new)} module(s) embed an absolute machine path:\n"
        + "\n".join(f"  {k}  ({v} literal(s))" for k, v in sorted(new.items()))
        + "\n\nResolve the root through the marker walk-up instead of hardcoding it."
    )


def test_the_absolute_path_ratchet_only_moves_down():
    """The allowlist is per-FILE, so it would not notice a second literal added
    to a file already on it. The total does."""
    total = sum(absolute_path_literals(_scanned_modules()).values())
    assert total <= ABSOLUTE_PATH_LITERAL_BASELINE, (
        f"{total} absolute-path literals, above the {ABSOLUTE_PATH_LITERAL_BASELINE} "
        "recorded 2026-08-01 — a new one was added inside an allowlisted file")


def test_the_absolute_path_allowlist_names_only_files_that_exist():
    """A stale entry silently exempts nothing, but it also hides that the file is
    gone; keep the list a true inventory."""
    missing = [rel for rel in ABSOLUTE_PATH_LITERAL_ALLOWLIST
               if not (REPO_ROOT / rel).is_file()]
    assert not missing, f"stale allowlist entries (file gone) — remove them: {missing}"


def test_the_absolute_path_detector_fires_on_a_hardcoded_root_only(tmp_path):
    """Anti-vacuity proof, on a synthetic tree.

    The guards this replaces (audit items 39/40) were green against the exact
    regression they existed to catch. This one is shown to separate a hardcoded
    root from the marker walk-up before it is trusted repo-wide.
    """
    bad = tmp_path / "hardcoded.py"
    bad.write_text("ROOT = Path('c:/Users/Joshua/plv_clone')\n", encoding="utf-8")
    bad_posix = tmp_path / "posix_hardcoded.py"
    bad_posix.write_text('DATA = "/Users/joshua/plv_clone/data"\n', encoding="utf-8")
    good = tmp_path / "portable.py"
    good.write_text(
        "ROOT = next(p for p in Path(__file__).resolve().parents\n"
        "            if (p / 'pyproject.toml').is_file())\n"
        "DATA = ROOT / 'data' / 'outputs'\n",
        encoding="utf-8",
    )

    flagged = {f.name for f in (bad, bad_posix, good)
               if ABS_LITERAL_RE.search(f.read_text(encoding="utf-8"))}
    assert flagged == {"hardcoded.py", "posix_hardcoded.py"}, (
        f"detector does not separate hardcoded roots from the marker form: {flagged}")


@pytest.mark.parametrize(
    "start",
    [
        "scripts/xfp/research",
        "scripts/xfp/_attic",
        "scripts/xfp/archive",
        "src/plv_clone/models/xfp",
        "tests",
    ],
)
def test_marker_walkup_finds_root_from_any_depth(start):
    """The recommended marker form must work from every tree it is used in."""
    d = REPO_ROOT / start
    if not d.exists():
        pytest.skip(f"{start} not present")
    probe = d / "_probe.py"  # need not exist; parents[] is purely lexical
    found = next(p for p in probe.resolve().parents if (p / "pyproject.toml").is_file())
    assert found == REPO_ROOT
