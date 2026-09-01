"""smoke.py — fast offline sanity check. Run after ANY change.

    python scripts/ci/smoke.py

Two stages, both offline (no ESPN/MLB/Statcast calls):
  1. Import the load-bearing single-source modules (catches syntax errors,
     broken imports, and validated-signals registry drift at import time).
  2. A pytest subset selected by GLOB (discovery, not enumeration — see
     don't-do #18): repo hygiene meta-tests, contract pins, and pure-math
     tests. Target < 60s. The full suite is still
     `python scripts/ci/run_summary.py -- python -m pytest`.

Exit 0 = safe to proceed. Nonzero = a contract you touched broke; read the
pytest output above the summary line.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"

# Light, dependency-cheap modules whose import-time asserts are themselves
# guards (validated_signals refuses unregistered FEATS entries).
IMPORTS = [
    "plv_clone.paths",
    "plv_clone.cap_math",
    "plv_clone.league_config",
    "plv_clone.models.xfp.validated_signals",
]

# Glob patterns, so newly added hygiene/contract tests join the smoke set on
# the day they are written.
PATTERNS = [
    "test_claude_md_budget.py",
    "test_skills_registered.py",
    "test_hygiene_*.py",
    "test_cap_math*.py",
    "test_scoring.py",
    "test_paths.py",
    "test_schedule_fetch_contract.py",
    "test_validated_signals.py",
    "test_sp_fp_formula_copies.py",
    "test_no_hardcoded_scoring_weights.py",
    "test_league_scoring.py",
]


def main() -> int:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

    print("[smoke 1/2] importing load-bearing modules...", flush=True)
    code = (
        "import importlib,sys\n"
        f"mods = {IMPORTS!r}\n"
        "for m in mods:\n"
        "    importlib.import_module(m)\n"
        "print('imports OK:', len(mods))\n"
    )
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                       cwd=REPO, env=env)
    if r.returncode != 0:
        print("[smoke] FAIL at import stage", flush=True)
        return r.returncode

    files = sorted({p for pat in PATTERNS for p in TESTS.glob(pat)})
    # Anti-vacuity: a glob typo must not silently shrink the smoke set.
    if len(files) < 8:
        print(f"[smoke] FAIL: only {len(files)} smoke test files matched — "
              f"expected >= 8. Fix PATTERNS in scripts/ci/smoke.py.")
        return 2

    print(f"[smoke 2/2] pytest on {len(files)} contract/hygiene files...",
          flush=True)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--no-cov", *map(str, files)],
        cwd=REPO, env=env)
    print(f"[smoke] {'PASS' if r.returncode == 0 else 'FAIL'}", flush=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
