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


__all__ = [
    "fuzzy_match_name",
    "merge_with_model",
    "resolve_batter_id",
    "KNOWN_COLLISIONS",
]
