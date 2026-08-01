"""Lock the matchup page's playoff section to the ONE validated engine (C12).

Defect being pinned: ``render_playoff_simulation`` ran its own ad-hoc Monte
Carlo with a hardcoded ``playoff_threshold = 12`` minus an assumed 4 prior
wins over ``max(20 - current_period, 0)`` remaining periods — arithmetically
EXACTLY 0.0% all season once the remaining schedule cannot reach 8 more wins.
House principle (the four-rh3-assemblies lesson): the section must REPORT
``season_sim.json`` (run_season_sim.py, the validated engine), stamped with
the payload's age, and refuse to render a number when the payload is missing
or stale — never print a dead 0.0%.

Same seam style as tests/test_no_silent_zero_inputs.py: monkeypatch the
module-level path constant to a synthetic payload in tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as bmd  # noqa: E402


def _payload(**over):
    base = {
        "generated": "2026-07-30",
        "period": 17,
        "sims": 5000,
        "josh": {"team": "New York Ligers",
                 "p_playoffs": 0.9768, "p_title": 0.1408},
    }
    base.update(over)
    return base


def _with_payload(monkeypatch, tmp_path, payload):
    p = tmp_path / "season_sim.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(bmd, "SEASON_SIM_JSON", p)
    return p


def test_playoff_figure_is_season_sims_number_stamped_with_its_as_of_date(
        monkeypatch, tmp_path):
    _with_payload(monkeypatch, tmp_path, _payload())
    html = bmd.render_playoff_simulation(current_period=17)
    assert "97.7" in html, html          # josh.p_playoffs = 0.9768
    assert "14.1" in html, html          # josh.p_title = 0.1408
    assert "2026-07-30" in html, html    # the payload's own as-of stamp
    assert "0.0%" not in html, html


def test_hard_stale_payload_refuses_to_render_a_number(monkeypatch, tmp_path):
    """3+ periods behind the live matchup (lib/title_equity's HARD-STALE bar)
    the number is from another era of the standings — refuse, loudly, instead
    of laundering it as current."""
    _with_payload(monkeypatch, tmp_path,
                  _payload(period=14, generated="2026-06-28"))
    html = bmd.render_playoff_simulation(current_period=17)
    assert "unavailable" in html, html
    assert "stale" in html, html
    assert "97.7" not in html, html


def test_missing_season_sim_payload_renders_unavailable_not_a_dead_zero(
        monkeypatch, tmp_path):
    monkeypatch.setattr(bmd, "SEASON_SIM_JSON", tmp_path / "absent.json")
    html = bmd.render_playoff_simulation(current_period=17)
    assert "unavailable" in html, html
    assert "run_season_sim.py" in html, html
    assert "0.0%" not in html, html
