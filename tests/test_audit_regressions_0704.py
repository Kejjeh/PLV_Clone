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


# Concern 3 (refresh step order) used to be pinned here by `src.index(marker)` —
# byte offsets into refresh_dashboards.py's source TEXT. That cannot fail on the
# regression it exists to catch (audit 2026-08-01 item 40): measured on a mutated
# copy in which the live_blend producer is no longer issued at all, all three
# assertions still evaluate True, because the marker strings survive in the
# source regardless of whether the step runs.
#
# Replaced by ordering assertions over the command sequence main() ACTUALLY
# issues (recorder in place of `run`):
#   tests/test_testqual_refresh_steps.py
#     ::test_live_blend_is_built_before_matchup_consumes_it
#     ::test_boom_stack_producers_run_before_triangulate
#
# When refresh_dashboards.main() grows the declarative (label, command, timeout,
# gating) step list the audit proposed, those assertions move onto that structure
# and the recorder goes away.
