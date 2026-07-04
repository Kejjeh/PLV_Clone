"""Regression locks for the 2026-07-04 full-audit fix classes.

1. Team-abbreviation maps: every map value must be an MLB StatsAPI canonical
   abbr, direction ESPN->MLB (the live_monitor map was INVERTED and missing
   ARI — D-backs/A's/White Sox silently vanished from live totals).
2. Publish list: every tracked xfp-model/docs page must be in the refresh's
   publish constants (triangulate.html was stale on Pages for 6 days).
3. Refresh step order: producers must appear before their consumers in the
   refresh source (blend/boom producers ran AFTER matchup/triangulate for
   weeks — dashboards showed yesterday's numbers).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

MLB_CANON = {
    "AZ", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL", "CWS", "DET", "HOU",
    "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "ATH", "PHI", "PIT",
    "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH",
}


def _extract_map(path: str, name: str) -> dict:
    src = (_ROOT / path).read_text(encoding="utf-8")
    m = re.search(rf"{name}\s*=\s*\{{(.*?)\}}", src, re.S)
    assert m, f"{name} not found in {path}"
    pairs = re.findall(r"'([A-Z]{2,3})'\s*:\s*'([A-Z]{2,3})'", m.group(1))
    assert pairs, f"{name} parsed empty"
    return dict(pairs)


def test_live_monitor_aliases_espn_to_mlb():
    m = _extract_map("scripts/xfp/live_monitor.py", "TEAM_ALIASES")
    assert set(m.values()) <= MLB_CANON, f"non-canonical values: {set(m.values()) - MLB_CANON}"
    assert m.get("ARI") == "AZ", "ARI missing/wrong — the vanishing-Diamondbacks bug"
    assert m.get("OAK") == "ATH", "direction must be ESPN->MLB (OAK->ATH)"
    assert m.get("CHW") == "CWS"
    # no chains: no value may itself be a non-identity key
    for v in m.values():
        assert m.get(v, v) == v, f"alias chain via {v}"


def test_hitter_boom_stack_map_targets_canon():
    m = _extract_map("scripts/xfp/lib/hitter_boom_stack.py", "_TEAM_ABBR_MAP")
    assert set(m.values()) <= MLB_CANON
    assert m.get("ATH") == "ATH" and m.get("OAK") == "ATH", \
        "2026 StatsAPI uses ATH — the backwards ATH->OAK bug"


def test_matchup_ingest_map_targets_canon():
    m = _extract_map("scripts/xfp/build_matchup_dashboard.py", "_E2M")
    assert set(m.values()) <= MLB_CANON
    assert m.get("ARI") == "AZ" and m.get("OAK") == "ATH"


def test_publish_pages_cover_tracked_docs():
    """Every page tracked in xfp-model/docs must be in the publish constants —
    a new dashboard must fail here rather than silently never publishing."""
    import refresh_dashboards as R
    published = set(R.PUBLISH_PAGES_CORE) | set(R.PUBLISH_PAGES_PROFILES)
    docs = _ROOT / "xfp-model" / "docs"
    if not docs.exists():
        import pytest
        pytest.skip("xfp-model sibling not present")
    tracked = {f"docs/{p.name}" for p in docs.glob("*.html")} | \
              {f"docs/{p.name}" for p in docs.glob("*.js")}
    missing = tracked - published
    assert not missing, (f"tracked docs pages missing from PUBLISH_PAGES: {missing} "
                         "— add to the constant or delete the page")


def test_refresh_producers_before_consumers():
    src = (_ROOT / "scripts/xfp/refresh_dashboards.py").read_text(encoding="utf-8")

    def idx(marker):
        assert marker in src, f"step marker gone: {marker}"
        return src.index(marker)

    # producers (moved 2026-07-04, commit a8ce49c) before consumers — match the
    # RUN COMMANDS, not bare filenames (comments mention builders earlier).
    assert idx("scripts/xfp/build_live_blend_xfp.py") < \
           idx("run('4. Build matchup.html"), \
        "live_blend must build before matchup consumes it"
    assert idx("scripts/xfp/stream_the_stack.py") < \
           idx("scripts/xfp/build_triangulate_dashboard"), \
        "stream_the_stack (boom producer) must run before triangulate"
    assert idx("scripts/xfp/build_hitter_boom_stack_daily.py") < \
           idx("scripts/xfp/build_triangulate_dashboard"), \
        "hitter boom producer must run before triangulate"
