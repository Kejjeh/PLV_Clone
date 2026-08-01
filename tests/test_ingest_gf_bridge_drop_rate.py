"""gf-bridge mapping-drop tripwire — behavioral spec.

The bridge counts pitches it failed to MAP and warns past a 20% rate, because a
Savant game-feed schema drift would silently drop the whole provisional day. The
rate must be measured against pitches ATTEMPTED, not pitches appended: a repair
run (`--start` over dates the canonical pull has already finalized) maps every
pitch fine and appends none, and must not be reported as a total mapping failure.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
import build_statcast_gf_bridge as bridge  # noqa: E402


CANON_DATE = "2026-06-22"
PK = 824261
N_MAPPABLE = 10
N_UNMAPPABLE = 2


def _canonical_frame():
    """Statcast rows already finalized by the canonical pull for PK/CANON_DATE."""
    rows = []
    for i in range(1, N_MAPPABLE + 1):
        rows.append({
            "game_pk": PK,
            "game_date": CANON_DATE,
            "at_bat_number": i,
            "pitch_number": 1,
            "launch_speed": 95.0 + i,
            "launch_angle": 15.0,
            "estimated_woba_using_speedangle": 0.5,
            "source": None,
        })
    return pd.DataFrame(rows)


def _gf_payload():
    """One game's /gf feed: N_MAPPABLE pitches that map, N_UNMAPPABLE that don't."""
    pitches = [{"ab_number": i, "pitch_number": 1, "ok": True}
               for i in range(1, N_MAPPABLE + 1)]
    pitches += [{"ab_number": 900 + j, "pitch_number": 1, "ok": False}
                for j in range(N_UNMAPPABLE)]
    return {
        "game_date": CANON_DATE,
        "home_team_data": {"abbreviation": "DET"},
        "away_team_data": {"abbreviation": "NYY"},
        "team_home": pitches,
        "team_away": [],
    }


def _install_bridge_stubs(monkeypatch, tmp_path):
    statcast = tmp_path / "statcast_2026.parquet"
    _canonical_frame().to_parquet(statcast, index=False)
    monkeypatch.setattr(bridge, "STATCAST", statcast)
    monkeypatch.setattr(bridge, "game_pks_for_date", lambda d: [PK])
    monkeypatch.setattr(bridge, "_get", lambda url, params=None, retries=3: _gf_payload())

    def _fake_map(p, meta, lookup=None, is_terminal=False):
        if not p.get("ok"):
            raise ValueError("gf schema drift")
        return {"game_pk": meta["game_pk"],
                "at_bat_number": p["ab_number"],
                "pitch_number": p["pitch_number"],
                "source": "gf_provisional"}

    monkeypatch.setattr(bridge, "map_gf_pitch", _fake_map)
    monkeypatch.setattr(sys, "argv",
                        ["build_statcast_gf_bridge.py",
                         "--start", CANON_DATE, "--through", CANON_DATE])
    return statcast


def test_repair_run_over_canonical_dates_reports_attempted_denominator(
        monkeypatch, tmp_path, capsys):
    """A re-run over already-canonical dates reports drops against pitches
    attempted, so a healthy feed is not reported as a total mapping failure."""
    _install_bridge_stubs(monkeypatch, tmp_path)

    bridge.main()

    out = capsys.readouterr().out
    drop_lines = [ln for ln in out.splitlines() if "gf pitch-mapping drops" in ln]
    assert drop_lines, f"bridge printed no drop report:\n{out}"
    assert f"{N_UNMAPPABLE}/{N_MAPPABLE + N_UNMAPPABLE}" in drop_lines[0], drop_lines[0]
    assert "WARNING" not in out, (
        "healthy repair run fired the schema-drift warning:\n" + out)


def test_real_schema_drift_still_warns(monkeypatch, tmp_path, capsys):
    """The tripwire still fires when the feed genuinely stops mapping."""
    _install_bridge_stubs(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "map_gf_pitch",
                        lambda p, meta, lookup=None, is_terminal=False:
                        (_ for _ in ()).throw(ValueError("gf schema drift")))

    bridge.main()

    out = capsys.readouterr().out
    assert "WARNING" in out and "schema drift" in out, out
