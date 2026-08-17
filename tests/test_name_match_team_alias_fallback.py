"""General (non-KNOWN_COLLISIONS) fallback team-hint canonicalization — issue #12.

`_pick_collision_candidate` (the KNOWN_COLLISIONS/KNOWN_PITCHER_COLLISIONS gate)
canonicalizes team codes through `team_key()` so ESPN's "Oak" and the model
CSVs' "ATH" are one equivalence class — fixed 2026-07-29 after the Max Muncy
incident. `resolve_batter_id`'s general fallback (for any name NOT in
KNOWN_COLLISIONS) and `resolve_pitcher_id._try_rp` never got that fix: they
compare team codes with a raw `.str.upper()`, so a team-alias mismatch
silently degrades a resolvable player to `None` instead of disambiguating.

These tests exercise that general fallback path directly (a synthetic
multiyr frame passed via the `multiyr=`/`rp_multiyr=` parameter, per the
existing pattern in this test suite — no CSV/network I/O).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id  # noqa: E402


def test_general_fallback_batter_team_hint_resolves_via_espn_alias():
    """'Jordan Test' collides across two teams in the cache (LAD, ATH) and is
    NOT in KNOWN_COLLISIONS. Passing team='Oak' (ESPN's live spelling) must
    resolve the Athletics row via team_key(), not silently no-op the filter
    and then refuse on the resulting multi-id ambiguity."""
    multiyr = pd.DataFrame([
        dict(batter=111, player_name="Jordan Test", team="LAD", year=2026),
        dict(batter=222, player_name="Jordan Test", team="ATH", year=2026),
    ])
    assert resolve_batter_id("Jordan Test", team="Oak", multiyr=multiyr) == 222
    assert resolve_batter_id("Jordan Test", team="ATH", multiyr=multiyr) == 222
    assert resolve_batter_id("Jordan Test", team="LAD", multiyr=multiyr) == 111
    # No team hint at all still correctly refuses (genuinely ambiguous).
    assert resolve_batter_id("Jordan Test", multiyr=multiyr) is None


def test_general_fallback_rp_team_hint_resolves_via_espn_alias():
    """Same fix, RP side: resolve_pitcher_id._try_rp's team_abbr compare."""
    rp_multiyr = pd.DataFrame([
        dict(pitcher=333, name="Casey Sample", team_abbr="LAD", year=2026),
        dict(pitcher=444, name="Casey Sample", team_abbr="ATH", year=2026),
    ])
    sp_multiyr = pd.DataFrame([dict(pitcher=999, player_name="Nobody, Else", year=2026)])
    assert resolve_pitcher_id("Casey Sample", team="Oak", role="RP",
                              rp_multiyr=rp_multiyr, sp_multiyr=sp_multiyr) == 444
    assert resolve_pitcher_id("Casey Sample", team="ATH", role="RP",
                              rp_multiyr=rp_multiyr, sp_multiyr=sp_multiyr) == 444
    assert resolve_pitcher_id("Casey Sample", team="LAD", role="RP",
                              rp_multiyr=rp_multiyr, sp_multiyr=sp_multiyr) == 333
