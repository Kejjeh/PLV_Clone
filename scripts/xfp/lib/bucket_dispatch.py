"""Bucket dispatch + name resolution for the triangulate engine."""
from __future__ import annotations
import sys, unicodedata

ARCHETYPE_PANELS = {
    'H':  'data/research/hitter_archetype_career_panel.parquet',
    'SP': 'data/research/sp_archetype_career_panel.parquet',
    'RP': 'data/research/rp_archetype_career_panel.parquet',
}
PROJECTIONS = {
    'H':  'data/outputs/xfp_rh3_projections.csv',
    'SP': 'data/outputs/xfp_rp3_projections.csv',
    'RP': 'data/outputs/xfp_rprs2_projections.csv',
}


# _norm routed to the name_match owner (item 10, 2026-07-04). cached_data imports
# THIS _norm to build the projection `_key` column and resolve_player() looks it
# up with the same helper — one shared source, so the swap is self-consistent on
# both sides. join_key is order-independent (makes SP _flip_lastfirst redundant
# but harmless) and punctuation-robust.
from plv_clone.utils.name_match import (  # noqa: E402
    join_key as _norm,
    KNOWN_COLLISIONS,
    KNOWN_PITCHER_COLLISIONS,
    _pick_collision_candidate,
    team_key,
)


def _flip_lastfirst(s: str) -> str:
    if ',' in str(s):
        a, b = s.split(',', 1)
        return f"{b.strip()} {a.strip()}"
    return str(s)


def fa_sp_mlbam_ids(fa_pool, *, sp_multiyr=None, rp_multiyr=None) -> set[int]:
    """Resolve an ESPN FA-pool frame to the set of FA **SP** mlbam ids.

    Rule 10 (audit C7, 2026-07-30): FA membership is decided by mlbam id,
    never by name-string matching — build_sp_alerts' old last-name +
    first-initial fallback let a ROSTERED pitcher be alerted as a free agent
    whenever a genuine FA shared his surname and first initial. Each FA name
    goes through the collision-safe ``resolve_pitcher_id`` (team-hinted,
    role='SP'); a name that cannot be resolved is SKIPPED with a one-line
    stderr breadcrumb and treated as NOT-FA — losing an alert beats
    inventing one.

    Args:
        fa_pool: DataFrame in the ``LeagueState.available_fa()`` shape —
            ``player_name``, ``position``, optionally ``pro_team``.
        sp_multiyr / rp_multiyr: preloaded resolver caches. Pass them when
            resolving many names (``resolve_pitcher_id`` re-reads its default
            CSVs per call otherwise).
    """
    from plv_clone.utils.name_match import resolve_pitcher_id

    ids: set[int] = set()
    for _, p in fa_pool.iterrows():
        if str(p.get('position', '') or '') not in ('SP', 'P'):
            continue
        nm = p.get('player_name')
        team = p.get('pro_team')
        if not (isinstance(team, str) and team.strip()):
            team = None
        pid = resolve_pitcher_id(str(nm), team=team, role='SP',
                                 sp_multiyr=sp_multiyr, rp_multiyr=rp_multiyr)
        if pid is None:
            print(f"  [fa-id] SKIP: FA SP {nm!r} did not resolve to an mlbam "
                  f"id — treated as NOT-FA (no alert)", file=sys.stderr)
            continue
        ids.add(int(pid))
    return ids


def _bucket_order(hint: str | None) -> list[str]:
    return ([hint] + [b for b in ('H', 'SP', 'RP') if b != hint]
            if hint else ['H', 'SP', 'RP'])


def _find_by_id(mlbam: int, name: str, hint: str | None) -> dict | None:
    """Locate a collision-gate-resolved mlbam id in the projection pools
    (then the archetype panels) and build the standard resolve_player dict.

    An id lookup is unambiguous by construction, so no multi-match handling
    is needed. If the id is in no pool, returns None with a breadcrumb —
    falling back to a NAME join here would reopen the wrong-player door.
    """
    from .cached_data import _load_projection, _load_archetype

    for bucket in _bucket_order(hint):
        df = _load_projection(bucket)
        id_col = 'batter' if bucket == 'H' else 'pitcher'
        name_col = 'player_name' if bucket in ('H', 'SP') else 'name_api'
        m = df[df[id_col] == mlbam]
        if not m.empty:
            r = m.iloc[0]
            disp = r[name_col]
            if bucket == 'SP':
                disp = _flip_lastfirst(disp)
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': disp,
                'team': r.get('team', ''),
                'position': r.get('primary_position', '') if bucket == 'H' else bucket,
            }
    for bucket in ('H', 'SP', 'RP'):
        p = _load_archetype(bucket)
        if p is None:
            continue
        id_col = 'batter' if bucket == 'H' else 'pitcher'
        if id_col not in p.columns:
            continue
        m = p[p[id_col] == mlbam]
        if not m.empty:
            name_col = 'player_name' if 'player_name' in p.columns else 'name'
            r = m.sort_values('year').iloc[-1]
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': r[name_col],
                'team': r.get('team', ''),
                'position': bucket,
            }
    print(f"NOTE: \"{name}\" collision-resolved to mlbam {mlbam}, but that id "
          f"is in no projection/archetype pool — returning None", file=sys.stderr)
    return None


def _disambiguate_rows(m, id_col: str, bucket: str,
                       team: str | None, position: str | None):
    """Reduce a multi-player name-key match to one player via caller hints.

    Mirrors the `_pick_collision_candidate` precedence: team (canonicalized
    through team_key) is authoritative when supplied — it never falls through
    to position; position applies only when no team was given and only for
    hitters (for pitchers the bucket already encodes the role). Returns a
    frame whose rows are all one player, or None (refuse to guess).
    """
    if team is not None and str(team).strip():
        if 'team' not in m.columns:
            return None
        hits = m[m['team'].apply(team_key) == team_key(team)]
        if not hits.empty and hits[id_col].nunique() == 1:
            return hits
        return None
    if position is not None and str(position).strip() and bucket == 'H' \
            and 'primary_position' in m.columns:
        hits = m[m['primary_position'].astype(str).str.upper()
                 == str(position).upper().strip()]
        if not hits.empty and hits[id_col].nunique() == 1:
            return hits
    return None


def resolve_player(name: str, hint: str | None = None, *,
                   team: str | None = None,
                   position: str | None = None) -> dict | None:
    """Return {'id', 'bucket', 'display_name', 'team', 'position'} or None.

    Rule-10 contract (audit C4, 2026-07-30; ambiguity semantics tightened by
    review round 2 the same day): a name matching more than one distinct
    player id in a pool is REFUSED (None + loud stderr) unless the optional
    `team=` / `position=` disambiguator selects exactly one player — never
    resolved to the first row. A KNOWN-collision name whose twin is in no
    pool is pool-UNIQUE and resolves hintlessly with a visibility breadcrumb
    (refusing broke hintless /triangulate for Will Smith-class names); a
    SUPPLIED hint that selects nothing still refuses (contradiction, not a
    missing hint). Team accepts any ESPN/Statcast spelling (team_key
    canonicalizes, e.g. 'Oak' == 'ATH'). For pitchers, pass the role
    ('SP'/'RP') as `position`. Unambiguous names resolve exactly as before.
    """
    # Import here to avoid a circular at module-import time.
    from .cached_data import _load_projection, _load_archetype

    # ── Collision gate FIRST (before any name-key join). Team is
    # authoritative, position/role second. A colliding name with no selecting
    # hint does NOT refuse outright: refusal is decided by ambiguity IN THE
    # POOLS below — a collision-table name whose twin has no projection/panel
    # row anywhere (Will Smith, Jacob Wilson, Luis García Jr.) is pool-unique
    # and must keep resolving hintlessly, or the whole triangulate surface
    # breaks for real players (found by adversarial review round 2,
    # 2026-07-30). The single-candidate path prints a breadcrumb so the
    # collision risk stays visible; the both-pooled case (Muncy) still
    # refuses via the multi-match gate below, same contract as
    # resolve_batter_id.
    collision_watch = False
    for table in (KNOWN_COLLISIONS, KNOWN_PITCHER_COLLISIONS):
        if name in table:
            forced = _pick_collision_candidate(table[name], team=team,
                                               hint=position)
            if forced is not None:
                return _find_by_id(int(forced), name, hint)
            if team is not None or position is not None:
                # a hint was SUPPLIED but selects nothing — that is a real
                # contradiction, not a missing hint; refuse loudly
                print(f"REFUSE: \"{name}\" is a known name collision "
                      f"({len(table[name])} candidates) and team={team!r} / "
                      f"position={position!r} does not select exactly one — "
                      f"returning None", file=sys.stderr)
                return None
            collision_watch = True

    key = _norm(name)
    for bucket in _bucket_order(hint):
        df = _load_projection(bucket)
        if bucket == 'H':
            id_col, name_col = 'batter', 'player_name'
        elif bucket == 'SP':
            id_col, name_col = 'pitcher', 'player_name'
        else:
            id_col, name_col = 'pitcher', 'name_api'
        m = df[df['_key'] == key]
        if not m.empty:
            if len(m) > 1 and m[id_col].nunique() > 1:
                narrowed = _disambiguate_rows(m, id_col, bucket, team, position)
                if narrowed is None:
                    print(f"REFUSE MULTI-MATCH: \"{name}\" matches "
                          f"{m[id_col].nunique()} distinct players in the {bucket} "
                          f"pool and team={team!r} / position={position!r} does "
                          f"not select exactly one — returning None",
                          file=sys.stderr)
                    return None
                m = narrowed
            r = m.iloc[0]
            disp = r[name_col]
            if bucket == 'SP':
                disp = _flip_lastfirst(disp)
            if collision_watch:
                print(f"NOTE: \"{name}\" is a known name collision, but only "
                      f"ONE candidate is in the pools — resolved to "
                      f"{r.get('team', '?')} (mlbam {int(r[id_col])}). Pass "
                      f"team= if you meant the other player.", file=sys.stderr)
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': disp,
                'team': r.get('team', ''),
                'position': r.get('primary_position', '') if bucket == 'H' else bucket,
            }
    # Fallback: archetype panels
    for bucket in ('H', 'SP', 'RP'):
        p = _load_archetype(bucket)
        if p is None:
            continue
        name_col = 'player_name' if 'player_name' in p.columns else 'name'
        id_col = 'batter' if bucket == 'H' else 'pitcher'
        m = p[p['_key'] == key]
        if not m.empty:
            if id_col in m.columns and m[id_col].nunique() > 1:
                print(f"REFUSE MULTI-MATCH: \"{name}\" matches "
                      f"{m[id_col].nunique()} distinct players in the {bucket} "
                      f"archetype panel — returning None", file=sys.stderr)
                return None
            r = m.sort_values('year').iloc[-1]
            if collision_watch:
                print(f"NOTE: \"{name}\" is a known name collision, but only "
                      f"ONE candidate is in the panels — resolved to "
                      f"{r.get('team', '?')} (mlbam {int(r[id_col])}). Pass "
                      f"team= if you meant the other player.", file=sys.stderr)
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': r[name_col],
                'team': r.get('team', ''),
                'position': bucket,
            }
    return None
