"""FA-pool snapshot tracking hygiene (audit T46).

Spec: dated per-run FA-pool snapshots are disk-only build artifacts and must
be git-ignored, while the three `fa_pool_{H,SP,RP}_latest.parquet` pointers
stay TRACKED -- every production consumer (blend_score, trade_target_scan,
build_model_scorecard, session_context, run_positional_board) resolves the
`_latest` pointer, and a fresh clone needs them because they are ESPN-derived
inputs, not regenerable offline.

These assert on the ignore RULES only (`--no-index`), so they are independent
of whether the already-tracked dated blobs have been `git rm --cached`ed yet.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT_DIR = "data/research/fa_snapshots"

DATED_SNAPSHOTS = [
    f"{SNAPSHOT_DIR}/fa_pool_H_2026-06-06-0253.parquet",
    f"{SNAPSHOT_DIR}/fa_pool_SP_2026-07-31-1210.parquet",
    f"{SNAPSHOT_DIR}/fa_pool_RP_2026-08-01-0900.parquet",
]

LATEST_POINTERS = [
    f"{SNAPSHOT_DIR}/fa_pool_H_latest.parquet",
    f"{SNAPSHOT_DIR}/fa_pool_SP_latest.parquet",
    f"{SNAPSHOT_DIR}/fa_pool_RP_latest.parquet",
]


def _is_ignored(relpath: str) -> bool:
    """True when git's ignore rules match `relpath`, index state aside."""
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", relpath],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        pytest.fail(
            f"git check-ignore failed for {relpath!r} "
            f"(rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.returncode == 0


@pytest.mark.parametrize("relpath", DATED_SNAPSHOTS)
def test_dated_fa_pool_snapshots_are_git_ignored(relpath: str) -> None:
    assert _is_ignored(relpath), (
        f"{relpath} is not ignored -- dated FA-pool snapshots accumulate "
        "unboundedly and violate CLAUDE.md's no-parquet-in-git rule"
    )


@pytest.mark.parametrize("relpath", LATEST_POINTERS)
def test_latest_fa_pool_pointers_are_not_ignored(relpath: str) -> None:
    assert not _is_ignored(relpath), (
        f"{relpath} is ignored -- the _latest pointers are the ONLY thing "
        "production consumers read and must stay tracked for a fresh clone"
    )


def test_no_dated_fa_snapshot_is_tracked_in_git():
    """T46's actual spec (review 2026-08-01): the ignore RULE alone proves
    nothing — gitignore does not untrack. A fresh clone must contain no dated
    per-run copies, only the three *_latest pointers, so the TRACKED set is
    what this asserts."""
    import subprocess
    out = subprocess.run(
        ["git", "ls-files", "data/research/fa_snapshots/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60)
    tracked = [l for l in out.stdout.splitlines() if l.strip()]
    dated = [t for t in tracked if "_latest" not in t]
    assert not dated, (
        f"{len(dated)} dated FA-pool snapshot(s) still tracked (first: "
        f"{dated[:3]}) — run git rm --cached on them; the ignore rule alone "
        f"does not untrack")
    assert len(tracked) == 3, f"expected exactly the 3 _latest pointers, got {tracked}"
