"""Make data-presence gating impossible to ignore (audit 2026-08-01, item 38).

WHY THIS FILE EXISTS
--------------------
A large slice of this suite guards itself with `pytest.skip("<artifact> not
present in this checkout")`. That is the RIGHT design — the artifacts are
rebuilt nightly and most are untracked, so a dev checkout must not go red. But a
skip and a pass print the same green tick, so a CI runner without the caches
reports "all tests passed" while the tests that would have caught a regression
never ran.

MEASURED, this checkout (2026-08-01, re-measured as the audit's other tracks
landed their test files):
  * 158 test files, 38 of which carry a data-presence guard, 72 guard sites.
  * of the artifacts those guards check, the three projection CSVs,
    subseason_variance_bands.csv and batter_rolling_features.csv are git-TRACKED
    (a fresh clone HAS them); the rolling_*_2018_2026.csv substrates, the
    multiyr caches and all 22 data/models/*.pkl are UNTRACKED — they exist only
    after a refresh.
  * a prior measurement under a simulated cacheless checkout observed 37 tests
    skipping (of 1404 collected). That number is the threshold to reason about,
    not the ~250 the finding estimated.

WHAT THIS FILE ADDS
-------------------
`PLV_STRICT_DATA=1` turns "artifacts absent" from a silent skip into a red run.
CI that owns the caches sets it; a dev checkout leaves it unset and keeps the
skips. The census ratchet below then forces any NEW data guard to be an explicit
decision rather than a quiet one.

SCOPE NOTE: the audit's preferred home for this was tests/conftest.py — a
`pytest_report_header` line plus a session-finish "N data-gated tests skipped"
summary and a real `--strict-data` CLI flag. conftest.py is outside this track's
file set, so the env-var gate lives here instead. It is functionally sufficient
for CI (the run goes red) but it reports on ARTIFACTS rather than counting the
skipped tests; the counting half is recorded as deferred.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())

STRICT_ENV = "PLV_STRICT_DATA"

# The artifacts the data-gated tests actually check for. Repo-relative.
# Every one of these is UNTRACKED (verified against `git ls-files`): they exist
# only after `python scripts/xfp/refresh_dashboards.py` has run. The tracked
# artifacts (the three projection CSVs, subseason_variance_bands.csv,
# batter_rolling_features.csv) are deliberately NOT listed — they are present on
# a fresh clone, so gating on them would never fire.
REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "data/research/xfp_cache/rolling_hitters_2018_2026.csv",
    "data/research/xfp_cache/rolling_pitchers_2018_2026.csv",
    "data/research/xfp_cache/rolling_relievers_2018_2026.csv",
    "data/research/xfp_cache/hitters_multiyr_2015_2026.csv",
    "data/research/xfp_cache/sp_multiyr_2015_2025.csv",
    "data/research/xfp_cache/statcast_2026.parquet",
    "data/models/xfp_rh3_pipeline.pkl",
    "data/models/xfp_rp3_pipeline.pkl",
    "data/models/xfp_rprs2_pipeline.pkl",
)


def absent_required_artifacts(root: Path = REPO_ROOT) -> list[str]:
    """Repo-relative paths of every required artifact missing under `root`."""
    return [p for p in REQUIRED_ARTIFACTS if not (root / p).exists()]


def strict_data_enabled() -> bool:
    """True when the caller has declared this run OWNS the built artifacts."""
    return os.environ.get(STRICT_ENV, "").strip().lower() not in ("", "0", "false", "no")


# ── the gate itself ──────────────────────────────────────────────────────────

def test_absent_required_artifacts_names_every_missing_file(tmp_path):
    """A gate that says 'something is missing' is not actionable; it must name
    what to rebuild."""
    assert set(absent_required_artifacts(tmp_path)) == set(REQUIRED_ARTIFACTS), \
        "an empty tree must report every required artifact as absent"

    present = REQUIRED_ARTIFACTS[0]
    p = tmp_path / present
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    assert present not in absent_required_artifacts(tmp_path)
    assert len(absent_required_artifacts(tmp_path)) == len(REQUIRED_ARTIFACTS) - 1


@pytest.mark.parametrize("value,expected", [
    (None, False), ("", False), ("0", False), ("false", False), ("no", False),
    ("1", True), ("true", True), ("yes", True),
])
def test_strict_data_is_opt_in(monkeypatch, value, expected):
    """A dev checkout without the nightly caches must stay green by default;
    only a runner that declares it owns the artifacts turns the gate on."""
    monkeypatch.delenv(STRICT_ENV, raising=False)
    if value is not None:
        monkeypatch.setenv(STRICT_ENV, value)
    assert strict_data_enabled() is expected


def test_a_strict_run_fails_loudly_when_an_artifact_is_absent():
    """THE GATE. With PLV_STRICT_DATA set, an absent artifact is a red run, not
    a green tick over tests that silently never executed.

    Unset (the default), this reports the census and skips — and `-r sxX` in
    addopts is what puts that reason into the summarised CI log.
    """
    absent = absent_required_artifacts()
    if not strict_data_enabled():
        pytest.skip(
            f"{STRICT_ENV} unset; {len(absent)}/{len(REQUIRED_ARTIFACTS)} built "
            f"artifacts absent, so the tests that need them will skip"
            + (f": {absent}" if absent else ""))
    assert not absent, (
        f"{STRICT_ENV} is set but {len(absent)} required artifact(s) are absent, so "
        f"the tests that depend on them SKIPPED rather than ran:\n  "
        + "\n  ".join(absent)
        + "\n\nRun `python scripts/xfp/refresh_dashboards.py` on this runner, or "
          f"unset {STRICT_ENV} and accept that this run did not exercise them.")


# ── the ratchet: a new silent guard must be a deliberate act ─────────────────

_GUARD_RE = re.compile(r"pytest\.skip\(|pytest\.importorskip\(|@pytest\.mark\.skipif")

# Measured 2026-08-01: 38 of 158 test files carry a guard, 72 guard sites. The
# bound is a ratchet, not a target — if a new guard is genuinely warranted, raise
# it in the same commit and say why. It exists so "just skip it" cannot become
# the default way to make a test stop failing.
#
# HEADROOM IS DELIBERATE AND TEMPORARY: the 2026-08-01 audit is landing new test
# files from seven concurrent tracks, so a bound set tight against the census at
# the moment this file was written would go red on a NEIGHBOUR's legitimate new
# guard rather than on a real regression. Re-tighten to census+2 / census+4 once
# the audit's test additions have all landed.
# 2026-08-27, +3 files (50 -> 53): the bug-audit wave converted three HARD
# FAILURES into honest data gates, which is what this ratchet wants to see
# happen deliberately rather than reflexively:
#   test_leverage_index / test_trend_signal_centering — both read gitignored
#     statcast parquets and ERRORED on a fresh checkout, so "no data here"
#     was indistinguishable from "code is broken". That confusion is exactly
#     what let a stale baseline of 8 failures go unexamined for weeks.
#   test_triangulate — skips a verdict lock when the lens stack degraded
#     (new result['degraded_lenses']), because a verdict synthesized without
#     statcast is not evidence about the code.
#   test_hygiene_python_floor / test_lens_health — NEW guard-bearing files,
#     each guarding on interpreter version rather than on data.
# Sites stayed under 100, so only the file bound moved.
#
# 2026-08-27, +1 file (53 -> 54): test_roster_rules_iteration uses a single
# module-level importorskip for scripts.xfp.lib.roster_rules, matching how
# every other lib-layer test reaches that package. It gates on an import, not
# on data, and it guards a legality bug that could silently declare an
# oversized roster legal.
# 2026-08-27, +1 file (54 -> 55): test_inactive_lineup_slots uses one
# module-level importorskip for build_matchup_dashboard (a heavy import), and
# it pins the canonical "bench is an active scoring slot" rule (gotcha #7),
# which had NO test coverage at all while two comments argued against it.
# 2026-08-27, +1 file (55 -> 56): test_leverage_sp_lever_keys uses the same
# module-level importorskip as test_leverage_engine (the engine needs the
# dashboard import chain). It guards the two SP levers of assemble(), which
# silently reported "benching/dropping him costs nothing" on a malformed key.
# 2026-08-27, +1 file (56 -> 57): test_settlement_lookup_failure uses one
# module-level importorskip for settle_decisions (a driver import). It guards
# the fetch-failure vs real-zero distinction in the settlement layer, which
# had been graded as a free win for the chosen player.
# 2026-08-27, +1 file (57 -> 58): test_ip_parsers_agree skips a parser that is
# not importable in a given checkout rather than failing it. It pins the MLB
# partial-inning notation contract across the repo's SIXTEEN independent IP
# parsers, two of which disagreed.
# 2026-08-27, +1 file (58 -> 59): test_refresh_gate_structure importorskips
# pyyaml. It exists BECAUSE the sibling test_refresh_ci_gate skips all nine of
# its tests without PowerShell — on Linux the nightly gate's exit-code
# contract was pinned by nothing. This one checks the same contract statically
# so it holds on every platform.
MAX_GUARDED_FILES = 59
# Sites 100 -> 101 for the same file's single importorskip (2026-08-27). This
# is the first time the SITE bound has moved since it was set; it is the
# tighter of the two and worth keeping that way.
MAX_GUARD_SITES = 104


def _guard_census() -> tuple[int, int, list[str]]:
    guarded, sites = [], 0
    for f in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        n = len(_GUARD_RE.findall(f.read_text(encoding="utf-8")))
        if n:
            guarded.append(f.name)
            sites += n
    return len(guarded), sites, guarded


def test_the_data_gating_census_stays_within_its_declared_bound():
    n_files, n_sites, guarded = _guard_census()
    assert n_files <= MAX_GUARDED_FILES and n_sites <= MAX_GUARD_SITES, (
        f"{n_files} test files now carry a presence/import guard ({n_sites} sites), "
        f"over the declared bound ({MAX_GUARDED_FILES} files / {MAX_GUARD_SITES} "
        f"sites). Every guard is a test that can silently not run. If the new one "
        f"is warranted, raise the bound in the same commit.\nGuarded: {guarded}")


# Margin note (review 2026-08-01): the census sat at EXACTLY the slack bound
# in the deletion direction, so one concurrent track removing one guarded
# file turned this test red for an unrelated author. Keep >=3 files / >=4
# sites of margin on BOTH sides when re-tightening.
MAX_BOUND_SLACK_FILES = 15
MAX_BOUND_SLACK_SITES = 31


def test_the_census_bound_has_not_gone_slack():
    """Keep the ratchet meaningful: a bound far above the real count stops
    ratcheting. The tolerance below is the audit-window headroom described at
    MAX_GUARDED_FILES — shrink both together when re-tightening.

    Note the direction: as neighbouring tracks add guarded files the slack
    SHRINKS, so this test gets safer, not more brittle, while the audit lands.
    """
    n_files, n_sites, _ = _guard_census()
    assert (MAX_GUARDED_FILES - n_files <= MAX_BOUND_SLACK_FILES
            and MAX_GUARD_SITES - n_sites <= MAX_BOUND_SLACK_SITES), (
        f"the guard bound ({MAX_GUARDED_FILES}/{MAX_GUARD_SITES}) has drifted far "
        f"above the actual census ({n_files}/{n_sites}) — tighten it")
