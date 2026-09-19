"""The three offline scenarios render and DIFFER where they must.

complete: no missing/stale markers anywhere.
stale:    the projection-age line says STALE and names rp3; the playoff card
          refuses the 6-period-old payload.
missing:  the hitter/RP with no projection row carry '⚠ no proj', the SP
          absent from rp3 carries '≈ est', the age line says MISSING, the
          playoff card says unavailable, and the optimizer payload names the
          unscoreable players.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "ci"))

import render_offline_scenarios as R


def _all(tmp_path):
    return {s: R.render(s, tmp_path) for s in ("complete", "stale", "missing")}


def test_complete_has_no_missing_or_stale_markers(tmp_path):
    html = _all(tmp_path)["complete"]
    assert "⚠ no proj" not in html and "≈ est" not in html
    assert "STALE" not in html and "MISSING" not in html
    assert "unavailable" not in html
    assert "unscoreable_drops: <b>none</b>" in html
    assert "— fresh" in html


def test_stale_is_labelled_stale_not_fresh(tmp_path):
    html = _all(tmp_path)["stale"]
    assert "STALE" in html and "rp3 41d" in html
    assert "— fresh" not in html
    assert "periods stale" in html            # playoff card refused the old payload
    assert "97.0%" not in html                # ...and did not print its number


def test_missing_is_named_not_zeroed(tmp_path):
    html = _all(tmp_path)["missing"]
    assert "⚠ no proj" in html
    assert "≈ est" in html
    assert "MISSING: rp3" in html
    assert "season_sim.json missing" in html
    assert "unscoreable_drops: <b>Beta Bat (H), Closer Arm (RP)</b>" in html


def test_il_player_is_zero_without_the_missing_badge(tmp_path):
    html = _all(tmp_path)["complete"]
    row = html.split("Hurt Bat")[1].split("</tr>")[0]
    assert "⚠ no proj" not in row and "+0.0" in row


def test_main_writes_three_files(tmp_path):
    assert R.main(["--out", str(tmp_path / "x")]) == 0
    assert sorted(p.name for p in (tmp_path / "x").iterdir()) == ["complete.html", "missing.html", "stale.html"]
