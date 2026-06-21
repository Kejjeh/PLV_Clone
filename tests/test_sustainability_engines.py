"""Regression guards for the sustainability engines after the C1+C3 skills refactor.

Pins the two issues the adversarial-verify workflow surfaced (2026-06-21):
  1. C3's lib import must resolve when the engine is imported via the PACKAGE path
     (league_wide_full_audit does `from scripts.xfp.hitter_sustainability import ...`
     with only ROOT+src on sys.path) — not just as a direct script.
  2. The join_key None/'' guard must not let an empty/None query token resolve to an
     orphaned null-name projection row.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))


def test_package_path_import_resolves():
    """Engine must import via the package path with scripts/xfp NOT on sys.path
    (the league_wide_full_audit context that C3 originally broke)."""
    code = (
        "import sys, os;"
        "sys.path.insert(0, os.getcwd());"
        "sys.path.insert(0, os.path.join(os.getcwd(), 'src'));"
        "from scripts.xfp.hitter_sustainability import classify;"
        "from scripts.xfp.pitcher_sustainability import load_rp3_map;"
        "print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                       capture_output=True, text=True)
    assert r.returncode == 0, f"package-path import crashed:\n{r.stderr}"
    assert "ok" in r.stdout


def test_null_or_empty_query_does_not_resolve():
    """An empty / whitespace query key must not hit an orphaned null-name row."""
    from pitcher_sustainability import load_rp3_map
    from hitter_sustainability import load_rh3_map
    rp = load_rp3_map()
    rh = load_rh3_map()
    assert rp.get("") is None and rp.get("nan") is None
    assert rh.get("") is None and rh.get("nan") is None
