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
  2. If eligible_slots contains RP but not SP  → 'RP' UNLESS the name appears
     in the rp3 SP-model output — ESPN's slot grants LAG a mid-season RP→SP
     conversion (canonical: Griffin Jax 2026 post-trade — RP-only slots for
     weeks while starting for TB, so cap math ignored his real starts).
     rp3 membership = strong evidence of real starts → decide on
     gamesStarted like the dual path. True relievers are never in rp3, so
     they short-circuit to 'RP' with no API call, exactly as before.
  3. Both SP+RP eligible                       → MLB Stats API gamesStarted
     • gamesStarted / gamesPlayed >= 0.4      → 'SP'
     • else, if gamesStarted >= 1             → recent game log breaks the tie
     • else                                   → 'RP'
  4. Neither in eligible_slots                 → fall back to .position tag

The season-cumulative ratio in (3) is blind to an IN-SEASON role change —
early relief appearances stay in the denominator all year (issue #11,
canonical: Ian Seymour 2026, 8 GS / 37 G = 0.216 cumulative while taking a
regular 5-day rotation turn, several of those turns logged GS=0 as bulk
behind an opener). The recency window fixes that; see
`_recent_role_from_gamelog`.
"""
from __future__ import annotations

import ast
import sys as _sys
import requests
from functools import lru_cache
from plv_clone.league_config import SEASON_YEAR  # single source of truth for the season


def _warn(section, exc):
    print(f"WARN pitcher_role.{section}: {exc}", file=_sys.stderr)


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
        except Exception as e:
            _warn('elig_parse', e)
            elig = []
    return set(elig) if elig else set()


_RECENT_WINDOW = 6          # outings inspected by the recency test
_RECENT_SP_MIN = 3          # start-equivalents in that window to call it 'SP'
_BULK_PITCHES = 60          # opener-bulk outing: pitch count ...
_BULK_IP = 3.0              # ... and innings, both required


def _ip_to_float(ip) -> float:
    """MLB's innings string ('5.1' = 5 and 1/3) -> float. Never raises."""
    try:
        whole, _, outs = str(ip).partition('.')
        return int(whole or 0) + (int(outs or 0) / 3.0)
    except Exception:
        return 0.0


@lru_cache(maxsize=512)
def _recent_role_from_gamelog(mlbam_id: int, season: int = SEASON_YEAR) -> str | None:
    """Role from the LAST ``_RECENT_WINDOW`` outings, or None if undecidable.

    The season-cumulative ratio cannot see an in-season role change: April
    relief appearances sit in the denominator all year. This reads the actual
    recent usage instead.

    A "start-equivalent" is ``GS=1`` OR a bulk outing behind an opener
    (>= _BULK_PITCHES pitches AND >= _BULK_IP innings). The bulk clause is
    load-bearing for Rays-style staffs, where a rotation regular can log
    ``GS=0`` on a 90-pitch, 6-inning outing.

    Returns None (caller falls back to the cumulative test) when the log is
    unavailable or too short to read.
    """
    try:
        url = (
            f'https://statsapi.mlb.com/api/v1/people/{mlbam_id}/stats'
            f'?stats=gameLog&season={season}&group=pitching&sportId=1'
        )
        data = requests.get(url, timeout=8).json()
        splits = data.get('stats', [{}])[0].get('splits', [])
        if len(splits) < _RECENT_SP_MIN:
            return None
        recent = splits[-_RECENT_WINDOW:]
        equiv = 0
        for sp in recent:
            stat = sp.get('stat', {})
            if int(stat.get('gamesStarted', 0) or 0) >= 1:
                equiv += 1
            elif (int(stat.get('numberOfPitches', 0) or 0) >= _BULK_PITCHES
                    and _ip_to_float(stat.get('inningsPitched')) >= _BULK_IP):
                equiv += 1
        return 'SP' if equiv >= _RECENT_SP_MIN else 'RP'
    except Exception as e:
        _warn(f'recent_role_from_gamelog({mlbam_id})', e)
        return None


@lru_cache(maxsize=512)
def _role_from_mlb_stats(mlbam_id: int, season: int = SEASON_YEAR) -> str:
    """Return 'SP' or 'RP' based on actual gamesStarted this season (cached).

    Cumulative ratio first; where it says 'RP' but the pitcher has made at
    least one start, the recent game log breaks the tie (issue #11 — Seymour
    2026: 8 GS / 37 G = 0.216 cumulative, but 4 of his last 6 outings were
    starts on a 5-day turn). A pitcher with zero starts is never ambiguous,
    so true relievers still cost exactly one API call.
    """
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
        if gs / gp >= 0.4:
            return 'SP'
        if gs >= 1:
            recent = _recent_role_from_gamelog(mlbam_id, season)
            if recent is not None:
                return recent
        return 'RP'
    except Exception as e:
        _warn(f'role_from_mlb_stats({mlbam_id})', e)
        return 'SP'  # default: assume starter if API unavailable


def _position_tag(player_or_row) -> str:
    """Read the raw ESPN position string from player obj or df row."""
    pos = getattr(player_or_row, 'position', None)
    if pos is None and hasattr(player_or_row, 'get'):
        pos = player_or_row.get('position', '')
    return (pos or '').upper()


def _name_of(player_or_row) -> str:
    """Player name from an ESPN player object or a df row.

    A pandas Series' ``.name`` attribute is its INDEX label (often an int), NOT
    the player's name — so for dict/Series rows read the 'player_name'/'name'
    COLUMN first (via ``.get``), and only fall back to the ``.name`` attribute for
    ESPN player objects, where ``.name`` IS the player name. The final isinstance
    guard means a stray non-string (e.g. an int index) can never reach ``.strip``.
    """
    if hasattr(player_or_row, 'get'):  # dict / pandas Series
        nm = player_or_row.get('player_name') or player_or_row.get('name')
        if nm is not None:
            return str(nm).strip()
    nm = getattr(player_or_row, 'name', None)  # ESPN player object
    return nm.strip() if isinstance(nm, str) else ''


def _team_of(player_or_row):
    """Pro-team abbreviation hint (for collision-safe resolution), or None."""
    for attr in ('proTeam', 'pro_team'):
        v = getattr(player_or_row, attr, None)
        if v:
            return str(v).upper()
    if hasattr(player_or_row, 'get'):
        for k in ('pro_team', 'team', 'team_abbr', 'proTeam'):
            v = player_or_row.get(k)
            if v:
                return str(v).upper()
    return None


@lru_cache(maxsize=1024)
def _resolve_pitcher_mlbam(name: str, team: str | None) -> int | None:
    """Best-effort name -> MLBAM id for role detection. Collision-safe CSV
    caches first (KNOWN_PITCHER_COLLISIONS), MLB Stats API as fallback. Cached
    per (name, team). This is what lets ``detect_pitcher_role`` own resolution
    so callers never have to pass an id."""
    if not name:
        return None
    try:
        from plv_clone.utils.name_match import resolve_pitcher_id
        pid = resolve_pitcher_id(name, team=team)
        if pid:
            return int(pid)
    except Exception as e:
        _warn(f'resolve_pitcher_id({name})', e)
    try:
        from plv_clone.mlb_stats import resolve_mlbam
        pid = resolve_mlbam([name]).get(name)
        return int(pid) if pid else None
    except Exception as e:
        _warn(f'resolve_mlbam({name})', e)
        return None


@lru_cache(maxsize=1)
def _rp3_name_keys() -> frozenset:
    """Safe-keyed player names present in the rp3 SP-model output.

    Membership = the SP pipeline has real starts for this name, regardless of
    what ESPN's slot list says. Used to escalate an RP-only-eligible pitcher
    to the gamesStarted check when ESPN lags a conversion (Jax 2026). Degrades
    to an empty set (→ pre-fix behavior) if the CSV or normalizer is missing.
    """
    try:
        import pandas as pd
        from plv_clone.utils.name_match import safe_name_key
        try:
            from plv_clone.paths import ROOT as _ROOT
            path = _ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'
        except Exception:
            path = 'data/outputs/xfp_rp3_projections.csv'
        names = pd.read_csv(path, usecols=['player_name'])['player_name'].dropna()
        return frozenset(safe_name_key(n) for n in names)
    except Exception as e:
        _warn('rp3_name_keys', e)
        return frozenset()


def _decide_by_starts(player_or_row, mlbam_id, season, gs_lookup, id_resolver,
                      fallback: str) -> str:
    """Shared endgame: resolve an id if needed, decide on real gamesStarted;
    `fallback` when resolution is exhausted."""
    pid = mlbam_id
    if pid is None:
        resolver = id_resolver or _resolve_pitcher_mlbam
        pid = resolver(_name_of(player_or_row), _team_of(player_or_row))
    if pid:
        gs = gs_lookup or _role_from_mlb_stats
        return gs(int(pid), season)
    return fallback


# ── public API ────────────────────────────────────────────────────────────────

def detect_pitcher_role(
    player_or_row,
    mlbam_id: int | None = None,
    season: int = SEASON_YEAR,
    *,
    gs_lookup=None,
    id_resolver=None,
    rp3_keys=None,
    check_recent_starts: bool = False,
) -> str:
    """
    Return 'SP' or 'RP' for a pitcher.

    The module OWNS resolution: callers do not need to pass an id. For a
    dual-eligible pitcher (SP and RP both in ``eligible_slots``, e.g. Detmers —
    ESPN ``.position`` says 'RP' but he's starting) the role is decided on real
    ``gamesStarted``, and the MLBAM id needed for that is resolved here from the
    player's name. The stale ESPN ``.position`` tag is only a last resort when
    resolution is exhausted, so a caller can no longer get a silent wrong answer
    by forgetting to pass ``mlbam_id``.

    Args:
        player_or_row: ESPN player object (has .eligibleSlots, .position, .name)
                       OR a pandas Series / dict row with 'eligible_slots',
                       'position', 'player_name' columns.
        mlbam_id:      MLBAM pitcher ID — an optional optimisation. When omitted,
                       the dual-eligible path resolves it internally.
        season:        Season year for the gamesStarted lookup (default 2026).

    Keyword-only seams (for tests — production leaves them None):
        gs_lookup:   (mlbam_id, season) -> 'SP'|'RP'. Defaults to the live MLB
                     Stats API gamesStarted source. Inject an in-memory adapter
                     to test the dual-eligible path without the network.
        id_resolver: (name, team) -> int|None. Defaults to the collision-safe
                     CSV+API resolver. Inject to test without CSV/API.
        rp3_keys:    set of safe-keyed names in the rp3 SP model. Defaults to
                     the cached CSV loader. Inject to test the RP-only
                     conversion escalation offline.

    check_recent_starts (issue #16): the RP-only escalation below only
        fires for names already in rp3, which requires >= EVAL_GS_MIN (2)
        real starts logged — so a pitcher's FIRST 1-2 starts after an
        RP->SP conversion still fall through to a blind 'RP', reproducing
        the exact Griffin Jax failure mode the rp3-membership check exists
        to close, just for a shorter window. Pass True to also escalate an
        RP-only-eligible pitcher NOT (yet) in rp3 to a real gamesStarted
        check via _decide_by_starts — this costs one extra API call per
        such pitcher (cached per process), so only set it for a BOUNDED
        pitcher set (a ~29-man roster, not a 2000-player FA-pool scan)
        where SP-cap accounting correctness matters more than call volume.
        Default False preserves the original zero-extra-cost behavior for
        FA-pool-wide scans, where a true reliever is by far the common case.
    """
    elig = _elig_set(player_or_row)
    has_sp = 'SP' in elig
    has_rp = 'RP' in elig

    if has_sp and not has_rp:
        return 'SP'
    if has_rp and not has_sp:
        # ESPN slot grants LAG a mid-season RP→SP conversion (canonical:
        # Griffin Jax 2026 post-trade — RP-only slots for weeks while starting
        # for TB, so cap math ignored his real starts). If the SP model (rp3)
        # knows this name, it has real starts: decide on gamesStarted like the
        # dual path. True relievers are never in rp3 → short-circuit 'RP'
        # with no API call, exactly as before.
        keys = rp3_keys if rp3_keys is not None else _rp3_name_keys()
        try:
            from plv_clone.utils.name_match import safe_name_key
            in_rp3 = safe_name_key(_name_of(player_or_row)) in keys
        except Exception as e:
            _warn('rp3_membership', e)
            in_rp3 = False
        if in_rp3 or check_recent_starts:
            return _decide_by_starts(player_or_row, mlbam_id, season,
                                     gs_lookup, id_resolver, fallback='RP')
        return 'RP'
    if has_sp and has_rp:
        # Dual-eligible: decide on real starts. Use a caller-supplied id if
        # given, otherwise resolve it ourselves — never silently fall back to
        # the stale ESPN .position tag while a real read is obtainable.
        # Resolution exhausted → tag is the documented last resort.
        return _decide_by_starts(player_or_row, mlbam_id, season,
                                 gs_lookup, id_resolver,
                                 fallback=_position_tag(player_or_row) or 'SP')

    # No pitcher eligibility detected in slots — common for SLOTLESS roster
    # frames (get_all_teams() carries no eligible_slots column, gotcha #3).
    # Absence of slot data is absence of EVIDENCE, not evidence of 'RP': the
    # bare ESPN tag here is exactly the Detmers mislabel this module exists to
    # defeat (caught live 2026-07-20 — a slotless get_all_teams row returned
    # 'RP' for a 20-of-20-starts Detmers, bypassing every safety net below the
    # slot checks). Mirror the RP-only branch: an RP tag is trusted only for
    # names the SP model doesn't know; rp3 membership escalates to real
    # gamesStarted. SP tags short-circuit (the mislabel risk runs RP->SP, not
    # the reverse), and true relievers still cost no API call.
    tag = _position_tag(player_or_row)
    if tag != 'RP':
        return tag or 'SP'
    keys = rp3_keys if rp3_keys is not None else _rp3_name_keys()
    try:
        from plv_clone.utils.name_match import safe_name_key
        in_rp3 = safe_name_key(_name_of(player_or_row)) in keys
    except Exception as e:
        _warn('rp3_membership_slotless', e)
        in_rp3 = False
    if in_rp3 or check_recent_starts:
        return _decide_by_starts(player_or_row, mlbam_id, season,
                                 gs_lookup, id_resolver, fallback='RP')
    return 'RP'


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
    # Name join key — OWNER: name_match.safe_name_key. `_rp3_name_keys` above
    # already uses it, so this function was the only place in the module still
    # hand-rolling one. The old local body was NFKD-ascii-lower-strip: it kept
    # apostrophes and periods, so an rp3 "O'Hearn, Ryan" and an ESPN roster
    # "Ryan O’Hearn" (curly U+2019) normalized differently and the role lookup
    # fell through to ESPN's stale position tag. safe_name_key collapses both
    # apostrophe forms, C.J./CJ and hyphens. Both sides of the join below use it.
    from plv_clone.utils.name_match import safe_name_key as _norm

    def _norm_both(name: str, d: dict, pid: int) -> None:
        """Store the MLBAM ID under the canonical key.

        safe_name_key already rewrites "Last, First" -> "first last", so the
        explicit flip this used to do is now a no-op that lands on the same key
        (kept only so an rp3 spelling change can't silently drop the alias).
        """
        nk = _norm(name)
        d[nk] = pid
        if ',' in name:
            parts = name.split(',', 1)
            d[_norm(parts[1].strip() + ' ' + parts[0].strip())] = pid

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


_PITCHER_TAGS = frozenset({"SP", "RP", "P"})


def roster_buckets(roster_df, role_lookup: dict[str, str]) -> dict[str, list]:
    """Split a roster into {'H', 'SP', 'RP'} by ROLE TRUTH, dropping nobody.

    The board-level companion to ``build_role_lookup``. A row is a pitcher iff
    its ESPN position tag is one of SP/RP/P — the tag is reliable for "is this a
    pitcher at all" — but WHICH pitcher bucket it lands in comes from
    ``role_lookup``, never from the tag. Detmers (tag 'RP', 23 starts) is the
    canonical case; a caller that branched on the tag dropped him silently and
    under-counted rotation starts against the period cap.

    Exists as a pure function so the classification is testable without a live
    ESPN pull. Every input row appears in exactly one output bucket.
    """
    out: dict[str, list] = {"H": [], "SP": [], "RP": []}
    for _, row in roster_df.iterrows():
        name = row["player_name"]
        if str(row.get("position")) in _PITCHER_TAGS:
            out[role_lookup.get(name, "RP")].append(name)
        else:
            out["H"].append(name)
    return out
