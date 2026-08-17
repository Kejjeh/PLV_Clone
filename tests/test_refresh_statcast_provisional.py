"""refresh_xfp_statcast.py must compute its pull window and gap-repair
scan from CANONICAL rows only, not rows tagged source='gf_provisional' —
issue #17. Mirrors build_statcast_gf_bridge.py's own canon_max pattern
(`sc[sc["source"] != "gf_provisional"]`).

Without this, once a provisional row lands for a date, both the tail-pull
window (last_date pushed forward past it) and the gap-repair scan (its
game_pks already "have"-covered by the provisional rows) stop ever
re-fetching that date as canonical data — it can get stuck provisional
permanently.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from refresh_xfp_statcast import canonical_max_date, canonical_games  # noqa: E402


def _frame():
    return pd.DataFrame([
        # Aug 1: canonical, fully present.
        dict(game_pk=1, game_date="2026-08-01", source="statcast"),
        dict(game_pk=2, game_date="2026-08-01", source="statcast"),
        # Aug 2: ONLY a provisional row — no canonical data yet.
        dict(game_pk=3, game_date="2026-08-02", source="gf_provisional"),
    ])


def test_canonical_max_date_ignores_provisional_rows():
    df = _frame()
    df["game_date"] = pd.to_datetime(df["game_date"])
    assert str(canonical_max_date(df)) == "2026-08-01"


def test_canonical_games_excludes_provisional_game_pks():
    df = _frame()
    df["game_date"] = pd.to_datetime(df["game_date"])
    games = canonical_games(df)
    assert set(games["game_pk"]) == {1, 2}


def test_missing_source_column_treats_everything_as_canonical():
    """Older caches / other years may not have a source column at all —
    must not crash, and must not treat every row as provisional."""
    df = pd.DataFrame([
        dict(game_pk=1, game_date="2026-08-01"),
        dict(game_pk=2, game_date="2026-08-02"),
    ])
    df["game_date"] = pd.to_datetime(df["game_date"])
    assert str(canonical_max_date(df)) == "2026-08-02"
    assert set(canonical_games(df)["game_pk"]) == {1, 2}
