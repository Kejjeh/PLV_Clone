"""Player-name normalization + fuzzy-match utilities.

Extracted from `app/espn_connector.py` so `league_state` and any other
consumer can depend on the matching logic without pulling in ESPN auth.
The source-of-truth functions are duplicated (not deleted) in
`app/espn_connector.py` until the Step 4 migration consolidates callers.
"""
from __future__ import annotations

import difflib
import unicodedata
from typing import Optional

import pandas as pd


def _normalize(name: str) -> str:
    """Lowercase, strip accents, drop common suffixes, and rewrite
    'Last, First' → 'First Last' for fuzzy matching."""
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"
    for suffix in [" jr.", " jr", " ii", " iii", " iv", " sr.", " sr"]:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name.lower().strip()


def join_key(name) -> str:
    """Order-independent normalization for use as a *dict join key*.

    Lowercases, strips accents, then joins the sorted alphabetic tokens with no
    separator: ``"Kyle Schwarber"`` and ``"Schwarber, Kyle"`` both → ``"kyleschwarber"``.

    Distinct in purpose from :func:`_normalize` (which preserves token order and
    strips suffixes for *fuzzy display matching*).  ``join_key`` exists to match
    two dicts whose names may differ in order/format — it sacrifices readability
    and anagram-safety for robustness.  This is the canonical home for the
    ``_norm`` helper duplicated across the scripts layer.
    """
    import re
    if name is None or (isinstance(name, float) and name != name):  # None / NaN
        return ""
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return "".join(sorted(re.findall(r"[a-z]+", s)))


def fuzzy_match_name(
    espn_name: str,
    model_names: list[str],
    cutoff: float = 0.78,
) -> Optional[str]:
    """Return best fuzzy match from `model_names` for an ESPN player name,
    or None if no candidate meets `cutoff`."""
    norm_espn = _normalize(espn_name)
    norm_model = {_normalize(n): n for n in model_names}
    matches = difflib.get_close_matches(
        norm_espn, list(norm_model.keys()), n=1, cutoff=cutoff
    )
    if matches:
        return norm_model[matches[0]]
    return None


def merge_with_model(
    espn_df: pd.DataFrame,
    model_df: pd.DataFrame,
    model_name_col: str = "player_name",
    cutoff: float = 0.78,
) -> pd.DataFrame:
    """Left-join an ESPN player list onto `model_df` by fuzzy name match.

    Adds a `model_name` column with the matched name (or NaN if no match
    cleared `cutoff`) and returns only the matched rows joined to the
    model frame.
    """
    model_names = model_df[model_name_col].tolist()
    espn_df = espn_df.copy()
    espn_df["model_name"] = espn_df["player_name"].apply(
        lambda n: fuzzy_match_name(n, model_names, cutoff=cutoff)
    )
    matched = espn_df.dropna(subset=["model_name"])
    merged = matched.merge(
        model_df,
        left_on="model_name",
        right_on=model_name_col,
        how="left",
        suffixes=("_espn", ""),
    )
    return merged


# ── Collision-safe exact-name join (Rule 10) ─────────────────────────────
# `fuzzy_match_name` must NEVER be used to JOIN a player list onto a stats/
# projection frame: a 0.78 difflib cutoff lets "Hayden Alvarez" inherit
# "Yordan Alvarez"'s row and invents "Bryce Mayer" from "Bryce Miller"
# (roster-audit FA board, 2026-07-19). These helpers are the join-safe
# replacement: exact normalized full-name match, team tie-break, and a
# refuse-to-guess None on anything ambiguous.

TEAM_CODE_ALIASES: dict[str, str] = {
    # ESPN / FanGraphs spellings → the Statcast codes the model CSVs carry.
    "ARI": "AZ", "CHW": "CWS", "WSN": "WSH", "OAK": "ATH",
    "SDP": "SD", "SFG": "SF", "TBR": "TB", "KCR": "KC",
}


def team_key(team) -> str:
    """Canonicalize a team abbreviation across ESPN / Statcast / FanGraphs."""
    t = str(team or "").upper().strip()
    return TEAM_CODE_ALIASES.get(t, t)


def safe_name_key(name) -> str:
    """Exact-join key: :func:`_normalize` plus punctuation collapse so
    "C.J. Abrams" / "CJ Abrams" and curly-vs-straight apostrophes converge."""
    s = _normalize(name)
    for ch in (".", "'", "’"):
        s = s.replace(ch, "")
    return " ".join(s.replace("-", " ").split())


def build_safe_name_index(names, teams=None) -> dict[str, list]:
    """Build ``{safe_name_key: [(label, team_key|None), ...]}`` for
    :func:`safe_lookup`.

    ``names`` may be a pandas Series (lookups return its index labels — hand
    the label to ``df.loc``) or any iterable (labels are list positions).
    ``teams`` optionally aligns 1:1 with ``names`` and enables team
    tie-breaking for true same-name collisions (Max Muncy LAD vs ATH).
    """
    if hasattr(names, "index") and hasattr(names, "tolist"):
        labels, vals = list(names.index), names.tolist()
    else:
        vals = list(names)
        labels = list(range(len(vals)))
    if teams is None:
        tkeys = [None] * len(vals)
    else:
        traw = teams.tolist() if hasattr(teams, "tolist") else list(teams)
        # `t == t` filters NaN floats from pandas columns.
        tkeys = [team_key(t) if (t is not None and t == t and str(t).strip())
                 else None for t in traw]
    idx: dict[str, list] = {}
    for lbl, n, tk in zip(labels, vals, tkeys):
        k = safe_name_key(n)
        if k:
            idx.setdefault(k, []).append((lbl, tk))
    return idx


def safe_lookup(name, index: dict[str, list], *, team=None):
    """Collision-safe replacement for :func:`fuzzy_match_name` in JOIN
    contexts. Exact normalized full-name match only — no distance metric, so
    a surname-similar prospect can never inherit a star's row.

    Returns the single matching label from :func:`build_safe_name_index`.
    On a same-name collision, ``team`` breaks the tie; if the match is still
    absent or ambiguous, returns None — the caller must skip the row, never
    guess (see ``memory/feedback_player_name_collisions.md``).
    """
    cands = index.get(safe_name_key(name))
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][0]
    if team is not None:
        tk = team_key(team)
        hits = [lbl for lbl, t in cands if t == tk]
        if len(hits) == 1:
            return hits[0]
    return None


# Known name collisions in the player universe. Each entry maps a colliding
# name to a list of (team, position, mlbam_id) tuples so the resolver can pick
# the right player using roster metadata. See
# `memory/feedback_player_name_collisions.md` for the canonical list — keep
# this dict in sync with that memory file.
KNOWN_COLLISIONS: dict[str, list[tuple[str, str, int]]] = {
    "Max Muncy": [
        ("LAD", "3B", 571970),  # established veteran
        ("ATH", "SS", 691777),  # 2024+ Oakland callup
    ],
    # Added 2026-06-05 from PL-archive name-resolution audit.
    # Will Smith: LAD catcher (669257) vs SF/ATL LHP-turned-position-classified
    # 519293 in batter cache (legacy rows). All PL hitter-article references
    # 2020-2025 are the LAD catcher; default to LAD.
    "Will Smith": [
        ("LAD", "C", 669257),
        ("SF", "P", 519293),
    ],
    # Jacob Wilson: HOU 2021 cup-of-coffee (607111) vs ATH 2024+ rookie SS (805779).
    # PL article references are the ATH shortstop.
    "Jacob Wilson": [
        ("ATH", "SS", 805779),
        ("HOU", "IF", 607111),
    ],
    # Luis García family: PHI legacy IF 472610, HOU 2021 fringe 677651,
    # WSH 2B (Jr.) 671277. PL hitter-article references 2022+ are
    # consistently the Washington 2B regardless of "Jr." suffix presence.
    "Luis Garcia": [
        ("WSH", "2B", 671277),
        ("HOU", "IF", 677651),
        ("PHI", "IF", 472610),
    ],
    "Luis García": [
        ("WSH", "2B", 671277),
        ("HOU", "IF", 677651),
        ("PHI", "IF", 472610),
    ],
    "Luis García Jr.": [
        ("WSH", "2B", 671277),
        ("HOU", "IF", 677651),
        ("PHI", "IF", 472610),
    ],
}

# Pitcher-side equivalent. Same shape as KNOWN_COLLISIONS:
# name -> [(team_abbr, role_hint, mlbam_id), ...]. role_hint is 'SP'/'RP'/'P'
# when the two players have distinct roles; team is the primary disambiguator.
# Keep in sync with `memory/feedback_player_name_collisions.md`.
KNOWN_PITCHER_COLLISIONS: dict[str, list[tuple[str, str, int]]] = {
    # Two Logan Allens, both LHP — team is the only reliable disambiguator.
    #   663531: SD/CLE veteran, last MLB innings 2021
    #   671106: CLE current rotation LHP (2023+)
    "Logan Allen": [
        ("CLE", "SP", 671106),
        ("SD", "SP", 663531),
    ],
    # Also surface the cache's "Last, First" spelling so callers using that
    # form (Statcast multiyr cache) hit the same disambiguation gate.
    "Allen, Logan": [
        ("CLE", "SP", 671106),
        ("SD", "SP", 663531),
    ],
    # José Soriano (LAA SP, 667755). NOT a true two-player collision — this is an
    # accent-drift RESOLUTION FORCE. resolve_pitcher_id does an accent-SENSITIVE
    # exact string match, so the accent-free spellings "Jose Soriano" /
    # "Soriano, Jose" never matched the cache's "Soriano, José" and returned None.
    # That silent None caused wrong-ID fallbacks in ad-hoc analysis scripts
    # (2026-06-21: a hardcoded fallback grabbed the WRONG pitcher's game log).
    # Forcing the unaccented spellings here makes team/role-hinted resolution
    # return the right id; the accented spelling still resolves via the cache
    # path (it is a different dict key, so this entry does not shadow it).
    # (There is also a George Soriano RP, 666277 — distinct full name, so no key
    # collision, but it is why a bare "Soriano" must never be guessed.)
    "Jose Soriano": [
        ("LAA", "SP", 667755),
    ],
    "Soriano, Jose": [
        ("LAA", "SP", 667755),
    ],
}


# Pitcher-side ALIASES (NOT collisions). One canonical pitcher with
# multiple spellings across data sources: PL articles use a nickname or
# different transliteration than the Statcast / cache "formal" spelling.
# Resolves alias_spelling -> canonical_spelling. Callers look up the
# canonical spelling in their existing name -> mlbam map.
#
# Centralized 2026-06-06 from local dict in
# scripts/xfp/build_pl_rank_panel.py:85 so other consumers (live_monitor,
# audit_pl_name_resolution, future PL ingest scripts) read one source.
#
# Add entries here when a name-resolution audit surfaces a new mismatch.
# Keep in sync with `memory/feedback_player_name_collisions.md` (collisions
# only) — this map is for canonical-spelling drift, not ambiguous IDs.
KNOWN_PITCHER_ALIASES: dict[str, str] = {
    "Mike Soroka": "Michael Soroka",
    "Hyun-Jin Ryu": "Hyun Jin Ryu",
    "Matt Boyd": "Matthew Boyd",
    "Louie Varland": "Louis Varland",
}


def canonical_pitcher_spelling(name: str) -> str:
    """Return the canonical (Statcast cache) spelling for a pitcher name.

    Looks up the input in ``KNOWN_PITCHER_ALIASES``. If the name is not an
    alias, returns it unchanged. Callers then look up the result in their
    existing name -> mlbam map.

    Example:
        >>> canonical_pitcher_spelling("Mike Soroka")
        'Michael Soroka'
        >>> canonical_pitcher_spelling("Tarik Skubal")
        'Tarik Skubal'
    """
    return KNOWN_PITCHER_ALIASES.get(name, name)


def classify_pitcher_bucket(
    mlbam_id: int,
    *,
    rp3_path: str = "data/outputs/xfp_rp3_projections.csv",
    rprs2_path: str = "data/outputs/xfp_rprs2_projections.csv",
) -> Optional[str]:
    """Classify a pitcher_id as 'SP' or 'RP' by consulting the production
    projection CSVs.

    Lookup order:
      1. If mlbam_id appears in xfp_rp3_projections.csv (SP model output),
         return 'SP'.
      2. Else if in xfp_rprs2_projections.csv (RP model output), return 'RP'.
      3. Else return None.

    A pitcher rostered in BOTH cohorts (rare: mid-season SP-to-RP move) is
    classified as 'SP' since the rp3 entry is the source of truth for any
    pitcher who has started recent games.

    Notes:
      - This is the CANONICAL classifier for downstream consumers that need
        to route a pitcher to the correct projection model.
      - Reads only the rank/pitcher columns (cheap; cached at module level).
      - Returns None for unrostered or unprojected pitchers — caller must
        decide the fallback.
    """
    import pandas as _pd
    import os as _os

    cache_key = (rp3_path, rprs2_path)
    cache = classify_pitcher_bucket.__dict__.setdefault("_cache", {})
    sig = (
        _os.path.getmtime(rp3_path) if _os.path.exists(rp3_path) else None,
        _os.path.getmtime(rprs2_path) if _os.path.exists(rprs2_path) else None,
    )
    cached = cache.get(cache_key)
    if cached is not None and cached["sig"] == sig:
        rp3_ids = cached["rp3_ids"]
        rprs2_ids = cached["rprs2_ids"]
    else:
        rp3_ids = (
            set(_pd.read_csv(rp3_path, usecols=["pitcher"])["pitcher"].astype(int))
            if _os.path.exists(rp3_path)
            else set()
        )
        rprs2_ids = (
            set(_pd.read_csv(rprs2_path, usecols=["pitcher"])["pitcher"].astype(int))
            if _os.path.exists(rprs2_path)
            else set()
        )
        cache[cache_key] = {"sig": sig, "rp3_ids": rp3_ids, "rprs2_ids": rprs2_ids}

    mid = int(mlbam_id)
    if mid in rp3_ids:
        return "SP"
    if mid in rprs2_ids:
        return "RP"
    return None


def resolve_batter_id(
    name: str,
    *,
    team: Optional[str] = None,
    position: Optional[str] = None,
    multiyr: Optional[pd.DataFrame] = None,
    multiyr_path: str = "data/research/xfp_cache/hitters_multiyr_2015_2026.csv",
) -> Optional[int]:
    """Resolve a player name to their MLBAM batter ID, disambiguating
    known collisions using ``team`` / ``position`` hints.

    Args:
        name: Player name as it appears in ESPN / model outputs (e.g.
            "Max Muncy"). Accent / suffix normalization is applied so
            "José Ramírez" and "Jose Ramirez" both resolve.
        team: ESPN/MLB team abbreviation (e.g. "LAD") — required when
            ``name`` is in ``KNOWN_COLLISIONS``.
        position: Position abbreviation (e.g. "3B") — second-line tie
            breaker if ``team`` is ambiguous.
        multiyr: Optional pre-loaded multiyr cache to avoid re-reading
            the CSV per call. If None, reads from ``multiyr_path``.
        multiyr_path: Path to the hitters_multiyr cache.

    Returns:
        MLBAM batter ID (int), or None if the name doesn't resolve. For
        a colliding name with no ``team``/``position`` hint, returns
        None (caller must disambiguate) rather than silently picking the
        wrong player.
    """
    # Fast-path the collision list first — these are the historic footguns.
    if name in KNOWN_COLLISIONS:
        candidates = KNOWN_COLLISIONS[name]
        if team is not None:
            for cand_team, cand_pos, mlbam in candidates:
                if cand_team.upper() == team.upper():
                    return mlbam
        if position is not None:
            for cand_team, cand_pos, mlbam in candidates:
                if cand_pos.upper() == position.upper():
                    return mlbam
        # Refuse to silently guess.
        return None

    if multiyr is None:
        multiyr = pd.read_csv(multiyr_path)

    # Prefer the most recent year's row for stable team/position info.
    sub = multiyr[multiyr["player_name"] == name]
    if sub.empty:
        return None
    if team is not None and "team" in sub.columns:
        team_sub = sub[sub["team"].str.upper() == team.upper()]
        if not team_sub.empty:
            sub = team_sub
    # Return the most recent batter ID for the (filtered) rows.
    if "year" in sub.columns:
        sub = sub.sort_values("year", ascending=False)
    return int(sub.iloc[0]["batter"])


def resolve_pitcher_id(
    name: str,
    *,
    team: Optional[str] = None,
    role: Optional[str] = None,
    sp_multiyr: Optional[pd.DataFrame] = None,
    rp_multiyr: Optional[pd.DataFrame] = None,
    sp_path: str = "data/research/xfp_cache/sp_multiyr_2015_2025.csv",
    rp_path: str = "data/research/xfp_cache/relievers_multiyr_2018_2026.csv",
) -> Optional[int]:
    """Resolve a pitcher name to their MLBAM pitcher ID, disambiguating
    known collisions using ``team`` / ``role`` hints.

    Mirrors :func:`resolve_batter_id`. The pitcher caches use two distinct
    name spellings:

      - ``sp_multiyr_2015_2025.csv`` column ``player_name`` is "Last, First"
      - ``relievers_multiyr_2018_2026.csv`` column ``name`` is "First Last"

    Both spellings are checked. ``KNOWN_PITCHER_COLLISIONS`` is consulted
    first; if the name collides and no ``team`` hint is provided, returns
    None rather than silently picking the wrong player.

    Args:
        name: Pitcher name (either "Last, First" or "First Last" works).
        team: MLB team abbreviation — required for known collisions.
        role: 'SP' or 'RP' — restricts which cache is checked first and
            used as a second-line tie-breaker.
        sp_multiyr / rp_multiyr: Pre-loaded caches to avoid CSV re-reads.
        sp_path / rp_path: Cache paths.

    Returns:
        MLBAM pitcher ID (int), or None if unresolved.
    """
    # Collision gate first — for both spellings.
    if name in KNOWN_PITCHER_COLLISIONS:
        candidates = KNOWN_PITCHER_COLLISIONS[name]
        if team is not None:
            for cand_team, cand_role, mlbam in candidates:
                if cand_team.upper() == team.upper():
                    return mlbam
        if role is not None:
            for cand_team, cand_role, mlbam in candidates:
                if cand_role.upper() == role.upper():
                    return mlbam
        return None

    # "First Last" -> "Last, First" alternate form for the SP cache.
    alt_name = None
    if "," not in name and " " in name:
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            alt_name = f"{parts[1]}, {parts[0]}"
    elif "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            alt_name = f"{parts[1]} {parts[0]}"

    def _try_sp() -> Optional[int]:
        nonlocal sp_multiyr
        if sp_multiyr is None:
            try:
                sp_multiyr = pd.read_csv(sp_path)
            except FileNotFoundError:
                return None
        for n in (name, alt_name):
            if n is None:
                continue
            sub = sp_multiyr[sp_multiyr["player_name"] == n]
            if not sub.empty:
                if "year" in sub.columns:
                    sub = sub.sort_values("year", ascending=False)
                # Multiple distinct IDs for the same name = unresolved
                # collision the caller should have hit via KNOWN_PITCHER_COLLISIONS.
                ids = sub["pitcher"].unique()
                if len(ids) > 1:
                    return None
                return int(sub.iloc[0]["pitcher"])
        return None

    def _try_rp() -> Optional[int]:
        nonlocal rp_multiyr
        if rp_multiyr is None:
            try:
                rp_multiyr = pd.read_csv(rp_path)
            except FileNotFoundError:
                return None
        for n in (name, alt_name):
            if n is None:
                continue
            sub = rp_multiyr[rp_multiyr["name"] == n]
            if not sub.empty:
                if team is not None and "team_abbr" in sub.columns:
                    team_sub = sub[sub["team_abbr"].astype(str).str.upper() == team.upper()]
                    if not team_sub.empty:
                        sub = team_sub
                if "year" in sub.columns:
                    sub = sub.sort_values("year", ascending=False)
                ids = sub["pitcher"].unique()
                if len(ids) > 1:
                    return None
                return int(sub.iloc[0]["pitcher"])
        return None

    # Role hint orders which cache we check first.
    if role and role.upper() == "RP":
        return _try_rp() or _try_sp()
    if role and role.upper() == "SP":
        return _try_sp() or _try_rp()
    return _try_sp() or _try_rp()


def resolve_id(
    name: str,
    *,
    kind: str,
    team: Optional[str] = None,
    position: Optional[str] = None,
    role: Optional[str] = None,
) -> Optional[int]:
    """Unified, collision-safe name → MLBAM resolution — the single seam every
    caller should reach for.

    Routes to :func:`resolve_batter_id` or :func:`resolve_pitcher_id` by
    ``kind``. Both consult the KNOWN_COLLISIONS tables and **safe-fail to None**
    on an ambiguous collision rather than guessing, so a caller can't grab the
    wrong same-name player (the Max Muncy LAD-vs-ATH footgun).

    Args:
        name: Player name as it appears in ESPN / model outputs.
        kind: 'batter'/'hitter'/'H' or 'pitcher'/'SP'/'RP'/'P'.
        team: Team abbreviation — required to disambiguate a colliding name.
        position: Hitter position hint (second-line tie-breaker).
        role: Pitcher role hint ('SP'/'RP') — orders which cache is checked.
    """
    k = (kind or "").strip().lower()
    if k in ("batter", "hitter", "h"):
        return resolve_batter_id(name, team=team, position=position)
    if k in ("pitcher", "sp", "rp", "p"):
        r = role or (kind.upper() if k in ("sp", "rp") else None)
        return resolve_pitcher_id(name, team=team, role=r)
    raise ValueError(
        f"resolve_id: unknown kind {kind!r} (expected batter/hitter or pitcher/SP/RP)"
    )


# ── Pre-resolved name → batter-ID cache lookup ──────────────────────────

_CACHE_DF: Optional[pd.DataFrame] = None
_CACHE_PATH: Optional[str] = None
_DEFAULT_CACHE_PATH = "data/research/xfp_cache/name_resolution_2026.csv"


def _load_cache(cache_path: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Lazy-load the name-resolution cache (module-level memo).

    Returns None if the cache file doesn't exist — callers fall back to
    ``resolve_batter_id``.
    """
    global _CACHE_DF, _CACHE_PATH
    path = cache_path or _DEFAULT_CACHE_PATH
    if _CACHE_DF is not None and _CACHE_PATH == path:
        return _CACHE_DF
    import os
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    _CACHE_DF = df
    _CACHE_PATH = path
    return df


def lookup_batter_id_cached(
    name: str,
    *,
    team: Optional[str] = None,
    position: Optional[str] = None,
    cache_path: Optional[str] = None,
    cache_df: Optional[pd.DataFrame] = None,
) -> Optional[int]:
    """Look up a batter MLBAM ID from the pre-resolved name cache.

    Lookup order:
      1. Exact ``(player_name, team)`` match in the cache (if ``team`` given).
      2. Exact ``player_name`` match if unique (one row in the cache).
      3. Fall back to ``resolve_batter_id(name, team=..., position=...)``.

    Args:
        name: Player name (ESPN-or-Statcast spelling).
        team: Optional team abbreviation — required for known collisions.
        position: Optional position — second-line collision tie-breaker.
        cache_path: Override the default cache CSV path. ``None`` uses
            ``data/research/xfp_cache/name_resolution_2026.csv``.
        cache_df: Pre-loaded cache DataFrame (skips the lazy-load).

    Returns:
        MLBAM batter ID (int) or None if unresolved.
    """
    df = cache_df if cache_df is not None else _load_cache(cache_path)
    if df is not None and not df.empty and "player_name" in df.columns:
        sub = df[df["player_name"] == name]
        if sub.empty:
            # Accent-insensitive fallback: compare normalized forms.
            target = _normalize(name)
            if "_norm_name" not in df.columns:
                df = df.copy()
                df["_norm_name"] = df["player_name"].apply(_normalize)
            sub = df[df["_norm_name"] == target]
        if not sub.empty:
            if team is not None and "team" in sub.columns:
                team_sub = sub[sub["team"].astype(str).str.upper() == team.upper()]
                if not team_sub.empty:
                    sub = team_sub
            # Take the first resolved row.
            resolved = sub[sub["batter_mlbam"].notna()]
            if not resolved.empty:
                try:
                    return int(resolved.iloc[0]["batter_mlbam"])
                except (TypeError, ValueError):
                    pass
    # Cache miss → fall through to live resolver. Don't crash if the
    # multiyr cache isn't present in the working tree.
    try:
        return resolve_batter_id(name, team=team, position=position)
    except FileNotFoundError:
        return None


def _reset_cache_for_tests() -> None:
    """Test-only helper to clear the module-level cache memo."""
    global _CACHE_DF, _CACHE_PATH
    _CACHE_DF = None
    _CACHE_PATH = None


__all__ = [
    "fuzzy_match_name",
    "merge_with_model",
    "safe_name_key",
    "build_safe_name_index",
    "safe_lookup",
    "team_key",
    "TEAM_CODE_ALIASES",
    "resolve_batter_id",
    "resolve_pitcher_id",
    "lookup_batter_id_cached",
    "KNOWN_COLLISIONS",
    "KNOWN_PITCHER_COLLISIONS",
    "KNOWN_PITCHER_ALIASES",
    "canonical_pitcher_spelling",
    "classify_pitcher_bucket",
]
