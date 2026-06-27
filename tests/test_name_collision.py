"""Regression tests for same-last-name player collisions in skill lookups.

Canonical case (2026-06-26): a diagnostic matched pitchers by last-name substring
("Warren") and conflated Will Warren (mlbam 701542, NYY, STARTER) with Austin
Warren (mlbam 681810, NY Mets, RELIEVER), so Austin's relief games corrupted Will's
profile. The fix removed last-name `str.contains` from skill engines in favor of
normalized full-name / mlbam-keyed lookups (resolve_pitcher_id / resolve_batter_id).

These tests lock in:
  1. the fix PATTERN (normalized full-name match does not cross-leak), and
  2. the canonical resolver distinguishes the two Warrens, and
  3. the boom-bust engine filters by mlbam, never by name.
"""
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))


def _nm(s):
    """The collision-safe normalizer the fixed skill engines use (full name,
    accent-stripped, 'Last, First' flipped)."""
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()
    if "," in s:
        a, b = s.split(",", 1)
        s = f"{b.strip()} {a.strip()}"
    return " ".join(s.replace(".", "").split())


def test_lastname_substring_was_the_bug():
    """Documents the OLD bug: a surname substring matches BOTH Warrens."""
    df = pd.DataFrame({"player_name": ["Warren, Will", "Warren, Austin", "Garcia, Luis"]})
    leaked = df[df["player_name"].str.lower().str.contains("warren", na=False)]
    assert len(leaked) == 2  # the cross-person leak we removed


def test_fullname_match_does_not_cross_leak():
    """The FIX: normalized full-name match resolves to exactly one Warren."""
    df = pd.DataFrame({"player_name": ["Warren, Will", "Warren, Austin"],
                       "pitcher": [701542, 681810]})
    m = df[df["player_name"].apply(_nm) == _nm("Will Warren")]
    assert len(m) == 1
    assert int(m.iloc[0]["pitcher"]) == 701542
    m2 = df[df["player_name"].apply(_nm) == _nm("Austin Warren")]
    assert int(m2.iloc[0]["pitcher"]) == 681810


def test_resolve_pitcher_id_distinguishes_warrens():
    """The canonical resolver (the recommended path) keeps the Warrens separate."""
    from plv_clone.utils.name_match import resolve_pitcher_id
    cache = ROOT / "data" / "research" / "xfp_cache"
    spm_p, rpm_p = cache / "sp_multiyr.csv", cache / "relievers_multiyr_2018_2026.csv"
    if not (spm_p.exists() and rpm_p.exists()):
        pytest.skip("multiyr frames unavailable")
    spm, rpm = pd.read_csv(spm_p), pd.read_csv(rpm_p)
    assert resolve_pitcher_id("Will Warren", team="NYY", role="SP",
                              sp_multiyr=spm, rp_multiyr=rpm) == 701542
    assert resolve_pitcher_id("Austin Warren", team="NYM", role="RP",
                              sp_multiyr=spm, rp_multiyr=rpm) == 681810


def test_boom_bust_engine_keys_by_mlbam():
    """The /boom-bust-history engine must filter the boxscore store by mlbam id,
    never by player_name — so a same-name player can never leak into a profile."""
    src = (ROOT / "scripts" / "xfp" / "lib" / "boom_bust.py").read_text(encoding="utf-8")
    assert 'df["mlbam_id"] == int(mlbam)' in src
    assert "people/{mlbam}" in src or "people/" in src
    # and it must NOT filter the box by player_name substring
    assert "player_name'].str.contains" not in src
    assert 'player_name"].str.contains' not in src
