"""closer_rank.py must use exact normalized-name matching, not last-name +
first-3-char substring matching — issue #15.

The module's own header comment documents the canonical rule
(plv_clone.utils.name_match.safe_name_key) and cites a real past incident
(Ryan O'Hearn's apostrophe mis-key) as the reason never to re-derive name
matching locally. The closer-quartet lookup violated that rule; the FA-scan
section in the same file already followed it correctly.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import closer_rank  # noqa: E402


def _reliever_row(name, season=2024, **kw):
    base = dict(name=name, season=season, ip=60.0, tbf_api=250, k=70, bb=20,
                er=20, h=45, sv=5, hld=10, swstr=40, pitches=900, woba_v_sum=60.0)
    base.update(kw)
    return base


def test_no_cross_collision_on_shared_last_name_and_first_prefix(monkeypatch, capsys):
    """A decoy reliever sharing Ryan Helsley's last name AND the first-3-char
    prefix ('Rya') of his first name must not contaminate his career line —
    the exact failure mode the old substring-matching code was exposed to."""
    rel = pd.DataFrame([
        _reliever_row('Ryan Helsley'),
        _reliever_row('Ryanne Helsley', ip=999.0, k=9999),  # decoy: same last name + 'Rya' prefix
        _reliever_row('Pete Fairbanks'),
        _reliever_row('Daniel Palencia'),
        _reliever_row('Jhoan Duran'),
    ])
    rprs2 = pd.DataFrame([
        dict(name_api='Ryan Helsley', role_lag1='closer', sv_lag1=10, hld_lag1=0,
             xfp_ros=80.0, xfp_full_year=150.0, fp_actual_2026=70.0),
        dict(name_api='Ryanne Helsley', role_lag1='setup', sv_lag1=0, hld_lag1=20,
             xfp_ros=9999.0, xfp_full_year=9999.0, fp_actual_2026=9999.0),
        dict(name_api='Pete Fairbanks', role_lag1='closer', sv_lag1=5, hld_lag1=0,
             xfp_ros=60.0, xfp_full_year=120.0, fp_actual_2026=50.0),
        dict(name_api='Daniel Palencia', role_lag1='closer', sv_lag1=3, hld_lag1=2,
             xfp_ros=55.0, xfp_full_year=100.0, fp_actual_2026=40.0),
        dict(name_api='Jhoan Duran', role_lag1='closer', sv_lag1=20, hld_lag1=0,
             xfp_ros=90.0, xfp_full_year=180.0, fp_actual_2026=85.0),
    ])

    monkeypatch.setattr(closer_rank.pd, 'read_csv', lambda *a, **k: rel)
    monkeypatch.setattr(closer_rank.PROJECTIONS, 'rprs2', lambda: rprs2)
    monkeypatch.setattr(closer_rank, 'league', None, raising=False)

    class _FakeLeagueState:
        def _get_league(self):
            class _L:
                teams = []
                def free_agents(self, size=2000):
                    return []
            return _L()

    monkeypatch.setattr(closer_rank, 'LeagueState', _FakeLeagueState, raising=False)
    import plv_clone.league_state as _ls_mod
    monkeypatch.setattr(_ls_mod, 'LeagueState', _FakeLeagueState)

    closer_rank.main()
    out = capsys.readouterr().out
    # career_summary SUMS matched rows — if the decoy leaks in, Ryan
    # Helsley's IP prints as 60+999=1059 instead of his real 60 (a
    # deterministic tell regardless of row order, unlike the rprs2 side's
    # .iloc[0] pick which can accidentally look right depending on order).
    career_lines = [ln for ln in out.splitlines() if ln.strip().startswith('Ryan Helsley')]
    assert career_lines, "Ryan Helsley line missing from output entirely"
    career_line = career_lines[0]  # first occurrence = the CAREER section
    assert '1059' not in career_line, f"decoy IP leaked into Ryan Helsley's line: {career_line!r}"
    assert ' 60 ' in career_line, f"Ryan Helsley's real IP=60 missing: {career_line!r}"
