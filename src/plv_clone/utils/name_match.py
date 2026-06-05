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
}


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
    "resolve_batter_id",
    "resolve_pitcher_id",
    "lookup_batter_id_cached",
    "KNOWN_COLLISIONS",
    "KNOWN_PITCHER_COLLISIONS",
]
