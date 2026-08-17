"""trade_simulator.py must credit RP fantasy points for SV/HLD, not
silently compute them with the SP-shaped zero-credit formula — issue #22.

Statcast pitch-level events carry no save/hold flag (game-state-derived,
not per-pitch), so this prorates the pitcher's season SV/HLD totals
(relievers_multiyr) by the fraction of his season appearances inside the
simulated window — the same proration approach the module already uses
for SB (per its own docstring).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import trade_simulator as m  # noqa: E402


def test_estimate_rp_sv_hld_prorates_by_appearance_share(monkeypatch, tmp_path):
    rel = pd.DataFrame([
        dict(pitcher=42, season=2024, g=60, sv=30, hld=0),
    ])
    rel_path = tmp_path / "relievers_multiyr_2018_2026.csv"
    rel.to_csv(rel_path, index=False)
    monkeypatch.setattr(m, "CACHE", tmp_path)

    sv, hld = m._estimate_rp_sv_hld(42, 2024, games_in_window=30)
    assert sv == pytest.approx(15.0)  # half the season's appearances -> half the saves
    assert hld == 0.0


def test_estimate_rp_sv_hld_caps_share_at_one(monkeypatch, tmp_path):
    """More window games than the season total (shouldn't happen, but
    don't let a data mismatch produce an inflated SV estimate)."""
    rel = pd.DataFrame([dict(pitcher=42, season=2024, g=10, sv=5, hld=0)])
    rel_path = tmp_path / "relievers_multiyr_2018_2026.csv"
    rel.to_csv(rel_path, index=False)
    monkeypatch.setattr(m, "CACHE", tmp_path)

    sv, hld = m._estimate_rp_sv_hld(42, 2024, games_in_window=99)
    assert sv == pytest.approx(5.0)


def test_estimate_rp_sv_hld_unknown_pitcher_returns_zero(monkeypatch, tmp_path):
    rel = pd.DataFrame([dict(pitcher=1, season=2024, g=10, sv=5, hld=0)])
    rel_path = tmp_path / "relievers_multiyr_2018_2026.csv"
    rel.to_csv(rel_path, index=False)
    monkeypatch.setattr(m, "CACHE", tmp_path)

    sv, hld = m._estimate_rp_sv_hld(999999, 2024, games_in_window=10)
    assert (sv, hld) == (0.0, 0.0)


def test_pitcher_fp_in_window_credits_rp_saves(monkeypatch, tmp_path):
    """End-to-end: an RP's simulated FP must be HIGHER than the same box
    line would score for an SP (zero SV/HLD credit) once he has real
    saves in the window."""
    year = 2024
    statcast = pd.DataFrame([
        dict(game_date=f"{year}-06-0{d}", game_pk=d, pitcher=42,
             events="strikeout", bat_score=0, post_bat_score=0, inning=9)
        for d in range(1, 4)
    ])
    (tmp_path / f"statcast_{year}.parquet").write_bytes(b"")  # existence check only
    monkeypatch.setattr(m, "CACHE", tmp_path)
    monkeypatch.setattr(m.pd, "read_parquet", lambda *a, **k: statcast)

    rel = pd.DataFrame([dict(pitcher=42, season=year, g=3, sv=3, hld=0)])
    (tmp_path / "relievers_multiyr_2018_2026.csv").write_text(rel.to_csv(index=False))

    start, end = pd.Timestamp(f"{year}-06-01"), pd.Timestamp(f"{year}-06-03")
    rp_result = m.pitcher_fp_in_window(42, start, end, role="rp")
    sp_result = m.pitcher_fp_in_window(42, start, end, role="sp")
    assert rp_result["fp"] > sp_result["fp"]
