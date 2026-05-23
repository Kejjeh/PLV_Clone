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


__all__ = ["fuzzy_match_name", "merge_with_model"]
