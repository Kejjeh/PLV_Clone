"""
pitcher_role.py — detect whether a pitcher is functioning as SP or RP.

ESPN's .position tag can be stale or wrong for players with dual
eligibility (canonical: Detmers 2026 — position='RP' in ESPN, but has
'SP' in eligible_slots and gamesStarted=6. He's a starter; should be
evaluated with rp3, not rprs2).

Use detect_pitcher_role() instead of `p.position == 'SP'` anywhere
that needs to bucket pitchers into the correct model.

Role detection priority:
  1. If eligible_slots contains SP but not RP  → 'SP'  (no API call)
  2. If eligible_slots contains RP but not SP  → 'RP'  (no API call)
  3. Both SP+RP eligible                       → MLB Stats API gamesStarted
     • gamesStarted / gamesPlayed >= 0.4      → 'SP'
     • else                                   → 'RP'
  4. Neither in eligible_slots                 → fall back to .position tag
"""
from __future__ import annotations

import ast
import requests
from functools import lru_cache


# ── internal helpers ──────────────────────────────────────────────────────────

def _elig_set(player_or_row) -> set[str]:
    """Extract eligible slots as a set of strings from ESPN player obj or df row."""
    elig = getattr(player_or_row, 'eligibleSlots', None)
    if elig is None:
        if hasattr(player_or_row, 'get'):
            elig = player_or_row.get('eligible_slots', [])
        else:
            elig = []
    if isinstance(elig, str):
        try:
            elig = ast.literal_eval(elig)
        except Exception:
            elig = []
    return set(elig) if elig else set()


@lru_cache(maxsize=512)
def _role_from_mlb_stats(mlbam_id: int, season: int = 2026) -> str:
    """Return 'SP' or 'RP' based on actual gamesStarted this season (cached)."""
    try:
        url = (
            f'https://statsapi.mlb.com/api/v1/people/{mlbam_id}/stats'
            f'?stats=season&season={season}&group=pitching&sportId=1'
        )
        data = requests.get(url, timeout=8).json()
        splits = data.get('stats', [{}])[0].get('splits', [])
        if not splits:
            return 'SP'
        stat = splits[0]['stat']
        gs = int(stat.get('gamesStarted', 0))
        gp = max(int(stat.get('gamesPlayed', 1)), 1)
        return 'SP' if gs / gp >= 0.4 else 'RP'
    except Exception:
        return 'SP'  # default: assume starter if API unavailable


def _position_tag(player_or_row) -> str:
    """Read the raw ESPN position string from player obj or df row."""
    pos = getattr(player_or_row, 'position', None)
    if pos is None and hasattr(player_or_row, 'get'):
        pos = player_or_row.get('position', '')
    return (pos or '').upper()


# ── public API ────────────────────────────────────────────────────────────────

def detect_pitcher_role(
    player_or_row,
    mlbam_id: int | None = None,
    season: int = 2026,
) -> str:
    """
    Return 'SP' or 'RP' for a pitcher.

    Args:
        player_or_row: ESPN player object (has .eligibleSlots, .position, .playerId)
                       OR a pandas Series / dict row with 'eligible_slots', 'position',
                       'player_id' columns.
        mlbam_id:      MLBAM pitcher ID — pass explicitly when known (avoids name lookup).
                       If None, tries player_or_row.playerId then row['player_id'].
        season:        Season year for MLB Stats API lookup (default 2026).
    """
    elig = _elig_set(player_or_row)
    has_sp = 'SP' in elig
    has_rp = 'RP' in elig

    if has_sp and not has_rp:
        return 'SP'
    if has_rp and not has_sp:
        return 'RP'
    if has_sp and has_rp:
        # Dual-eligible: resolve via MLB Stats API using MLBAM ID only.
        # Never use player_id from the ESPN row — that's ESPN's internal ID,
        # not MLBAM, and will silently map to the wrong player.
        pid = mlbam_id
        if pid is None:
            # ESPN player objects have .playerId which is also ESPN's ID,
            # not MLBAM. Don't use it — caller must supply mlbam_id explicitly
            # (via build_role_lookup which reads it from rp3/rprs2 projections).
            pass
        if pid:
            return _role_from_mlb_stats(int(pid), season)
        # No MLBAM ID available — fall back to ESPN position tag
        return _position_tag(player_or_row) or 'SP'

    # No pitcher eligibility detected in slots — use position tag
    return _position_tag(player_or_row) or 'SP'


def build_role_lookup(
    roster_df,
    rp3_df=None,
    rprs2_df=None,
) -> dict[str, str]:
    """
    Build a {player_name: 'SP'|'RP'} lookup for an entire pitcher roster.

    Merges MLBAM IDs from both rp3_df ('player_name' + 'pitcher' columns)
    and rprs2_df ('name_api' + 'pitcher' columns) so dual-eligible pitchers
    like Latz (in rprs2 only) and Detmers (in rp3 only) are all resolved
    correctly via MLB Stats API gamesStarted, not ESPN's stale position tag.

    Both DataFrames use 'pitcher' as their MLBAM ID column.
    """
    import unicodedata

    def _norm(s: str) -> str:
        return (
            unicodedata.normalize('NFKD', str(s))
            .encode('ascii', 'ignore')
            .decode()
            .lower()
            .strip()
        )

    def _norm_both(name: str, d: dict, pid: int) -> None:
        """Store MLBAM ID under both the raw norm and a 'First Last' canonical form."""
        nk = _norm(name)
        d[nk] = pid
        # rp3 uses "Last, First" — also store as "First Last" so roster names match
        if ',' in name:
            parts = name.split(',', 1)
            canonical = _norm(parts[1].strip() + ' ' + parts[0].strip())
            d[canonical] = pid

    mlbam_by_norm: dict[str, int] = {}

    if rp3_df is not None:
        for _, row in rp3_df.iterrows():
            pid = row.get('pitcher')
            name = row.get('player_name', '')
            if pid and name:
                _norm_both(name, mlbam_by_norm, int(pid))

    if rprs2_df is not None:
        for _, row in rprs2_df.iterrows():
            pid = row.get('pitcher')
            name = row.get('name_api', '')
            if pid and name:
                nk = _norm(name)
                if nk not in mlbam_by_norm:  # rp3 takes precedence if both present
                    mlbam_by_norm[nk] = int(pid)

    result: dict[str, str] = {}
    for _, row in roster_df.iterrows():
        name = row.get('player_name', '')
        nk = _norm(name)
        mlbam = mlbam_by_norm.get(nk)
        result[name] = detect_pitcher_role(row, mlbam_id=mlbam)

    return result
