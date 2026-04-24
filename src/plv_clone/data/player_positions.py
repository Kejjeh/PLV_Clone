"""
Player position enrichment layer.

Fetches and caches position data from the MLB Stats API for a given season.
Builds per-player fantasy eligibility from fielding games-started data.

Sources:
  Primary positions : MLB Stats API /sports/1/players?season={year}
  Fielding stats    : MLB Stats API /stats?group=fielding&season={year}

Eligibility rule (default): a player qualifies at a position if they have
>= 10 games started (GS) there in the season. Configurable via PositionConfig.

See docs/position_mapping_methodology.md.
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_OUTFIELD_RAW    = {"LF", "CF", "RF"}
_INFIELD_POS     = {"C", "1B", "2B", "3B", "SS"}
_PITCHER_RAW     = {"P", "SP", "RP"}
_VALID_FANTASY   = {"C", "1B", "2B", "3B", "SS", "OF", "DH"}
_POSITION_ORDER  = {"C": 0, "1B": 1, "2B": 2, "3B": 3, "SS": 4, "OF": 5, "DH": 6}


@dataclass
class PositionConfig:
    """Configuration for position eligibility determination.

    Attributes
    ----------
    min_games_for_eligibility : GS (or G) at a position required for fantasy eligibility.
        Default 10 matches standard ESPN/Yahoo eligibility rules.
    use_games_started : If True, use gamesStarted; if False use gamesPlayed.
    include_dh : Whether DH counts as a fantasy position.
    outfield_merge : If True, LF/CF/RF are all mapped to OF.
    exclude_pitchers : If True, pitcher positions (P/SP/RP) are excluded from
        hitter fantasy_positions.
    """
    min_games_for_eligibility: int = 10
    use_games_started: bool = True
    include_dh: bool = True
    outfield_merge: bool = True
    exclude_pitchers: bool = True


def _normalize_position(pos: str, cfg: PositionConfig) -> str | None:
    """Map a raw fielding/position abbreviation to a fantasy position.

    Returns None if the position is not a valid fantasy position (e.g. P, PH, PR).
    """
    if pos in _OUTFIELD_RAW:
        return "OF" if cfg.outfield_merge else pos
    if pos in _INFIELD_POS:
        return pos
    if pos == "DH":
        return "DH" if cfg.include_dh else None
    if pos in _PITCHER_RAW:
        return None
    return None


def _sort_positions(positions: list[str]) -> list[str]:
    """Sort fantasy positions in canonical order: C, 1B, 2B, 3B, SS, OF, DH."""
    return sorted(positions, key=lambda p: _POSITION_ORDER.get(p, 99))


def fetch_primary_positions(year: int) -> dict[int, str]:
    """Return {mlbam_id: primary_position_abbreviation} for all active players in *year*.

    Uses the MLB Stats API /sports/1/players endpoint. Includes pitchers
    (pos='P') and position players alike.
    """
    import requests
    url = f"https://statsapi.mlb.com/api/v1/sports/1/players?season={year}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Primary positions fetch failed (year=%d): %s", year, exc)
        return {}

    result: dict[int, str] = {}
    for p in resp.json().get("people", []):
        pid = p.get("id")
        pos = p.get("primaryPosition", {}).get("abbreviation", "")
        if pid and pos:
            result[int(pid)] = pos
    logger.info("Primary positions loaded: %d players (year=%d)", len(result), year)
    return result


def fetch_fielding_stats(year: int) -> pd.DataFrame:
    """Return per-player per-position fielding stats from the MLB Stats API.

    Columns: player_id (int), player_name (str), position_raw (str),
             games_played (int), games_started (int).
    """
    import requests
    url = (
        f"https://statsapi.mlb.com/api/v1/stats"
        f"?stats=season&group=fielding&season={year}&playerPool=ALL&limit=5000"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Fielding stats fetch failed (year=%d): %s", year, exc)
        return pd.DataFrame()

    splits = resp.json().get("stats", [{}])[0].get("splits", [])
    rows = []
    for s in splits:
        p   = s.get("player", {})
        pid = p.get("id")
        if not pid:
            continue
        stat = s.get("stat", {})
        rows.append({
            "player_id":     int(pid),
            "player_name":   p.get("fullName", ""),
            "position_raw":  s.get("position", {}).get("abbreviation", ""),
            "games_played":  int(stat.get("gamesPlayed",  0) or 0),
            "games_started": int(stat.get("gamesStarted", 0) or 0),
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["player_id", "player_name", "position_raw", "games_played", "games_started"]
    )
    logger.info("Fielding stats loaded: %d rows (year=%d)", len(df), year)
    return df


def build_position_map(
    year: int,
    config: PositionConfig | None = None,
    cache_dir: Path | None = None,
    max_cache_age_days: int | None = None,
) -> pd.DataFrame:
    """Build the complete player position map for *year*.

    Fetches primary positions and fielding games-started from the MLB Stats API,
    applies the eligibility threshold, and returns one row per player with:

    - player_id                : MLBAM ID (int)
    - primary_position         : best single display position (normalized)
    - all_positions_seen       : pipe-delimited raw positions with GS > 0
    - fantasy_positions        : pipe-delimited normalized positions passing eligibility
    - fantasy_positions_display: human-readable comma-separated version
    - is_multi_position        : True if position_count > 1
    - position_count           : number of qualifying fantasy positions

    Results are cached to ``cache_dir/player_positions_{year}.json``.
    Delete that file to force a refresh.
    """
    cfg = config or PositionConfig()

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_path: Path | None = None
    if cache_dir:
        cache_path = cache_dir / f"player_positions_{year}.json"
        if cache_path.exists():
            cache_fresh = True
            if max_cache_age_days is not None:
                age_days = (_time.time() - cache_path.stat().st_mtime) / 86400
                if age_days > max_cache_age_days:
                    cache_fresh = False
                    logger.info(
                        "Position cache is %.1f days old (max %d) — refreshing (year=%d).",
                        age_days, max_cache_age_days, year,
                    )
            if cache_fresh:
                try:
                    df = pd.DataFrame(json.loads(cache_path.read_text()))
                    # Ensure boolean column survives JSON round-trip
                    if "is_multi_position" in df.columns:
                        df["is_multi_position"] = df["is_multi_position"].astype(bool)
                    logger.info(
                        "Position map loaded from cache: %d players (year=%d)", len(df), year
                    )
                    return df
                except Exception as exc:
                    logger.warning("Cache read failed (%s); re-fetching API.", exc)

    # ── Fetch ─────────────────────────────────────────────────────────────────
    primary_pos = fetch_primary_positions(year)
    fielding_df = fetch_fielding_stats(year)

    if fielding_df.empty:
        logger.warning("No fielding stats for year=%d — returning empty position map.", year)
        return pd.DataFrame()

    threshold_col = "games_started" if cfg.use_games_started else "games_played"

    # ── Build per-player rows ─────────────────────────────────────────────────
    rows = []
    for pid, grp in fielding_df.groupby("player_id"):
        name = grp["player_name"].iloc[0]

        # All raw positions with at least one game started
        all_raw_seen = sorted(
            grp.loc[grp["games_started"] > 0, "position_raw"].unique().tolist()
        )

        # Fantasy-eligible positions (threshold, normalized, deduped)
        eligible_raw = grp.loc[
            grp[threshold_col] >= cfg.min_games_for_eligibility, "position_raw"
        ].unique()
        fantasy_set: set[str] = set()
        for pos in eligible_raw:
            mapped = _normalize_position(pos, cfg)
            if mapped and (not cfg.exclude_pitchers or mapped not in _PITCHER_RAW):
                fantasy_set.add(mapped)
        fantasy_sorted = _sort_positions(list(fantasy_set))

        # Primary position: normalize API primary; fall back to top GS position
        raw_primary = primary_pos.get(int(pid), "")
        norm_primary = _normalize_position(raw_primary, cfg) or raw_primary
        # If primary is pitcher but player has hitter positions, prefer the hitter pos
        if raw_primary in _PITCHER_RAW and fantasy_sorted:
            norm_primary = fantasy_sorted[0]
        # If still no primary, use highest-GS position
        if not norm_primary and not grp.empty:
            best = grp.sort_values("games_started", ascending=False).iloc[0]
            norm_primary = _normalize_position(best["position_raw"], cfg) or best["position_raw"]

        rows.append({
            "player_id":                int(pid),
            "player_name_pos":          name,
            "primary_position":         norm_primary,
            "all_positions_seen":       "|".join(all_raw_seen),
            "fantasy_positions":        "|".join(fantasy_sorted),
            "fantasy_positions_display": ", ".join(fantasy_sorted) if fantasy_sorted else "",
            "is_multi_position":        len(fantasy_sorted) > 1,
            "position_count":           len(fantasy_sorted),
        })

    df = pd.DataFrame(rows)
    logger.info(
        "Position map built: %d players, %d multi-position (year=%d)",
        len(df), int(df["is_multi_position"].sum()), year,
    )

    # ── Write cache ───────────────────────────────────────────────────────────
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Convert bool to Python bool for JSON serialisation
        records = df.assign(is_multi_position=df["is_multi_position"].tolist()).to_dict(
            orient="records"
        )
        cache_path.write_text(json.dumps(records, indent=2))
        logger.info("Position map cached -> %s", cache_path)

    return df


def enrich_hitters(
    df: pd.DataFrame,
    position_map: pd.DataFrame,
    id_col: str = "batter",
) -> pd.DataFrame:
    """Merge position fields into a hitter DataFrame on *id_col* (MLBAM ID).

    Players absent from the position map receive null position fields.
    Returns a copy of *df* with position columns added (or overwritten).
    """
    if position_map.empty:
        logger.warning("Position map empty — hitter position enrichment skipped.")
        return df

    pos_cols = [
        "player_id", "primary_position", "all_positions_seen",
        "fantasy_positions", "fantasy_positions_display",
        "is_multi_position", "position_count",
    ]
    available = [c for c in pos_cols if c in position_map.columns]
    merged = df.merge(
        position_map[available].rename(columns={"player_id": id_col}),
        on=id_col,
        how="left",
    )
    n_resolved = merged["primary_position"].notna().sum()
    logger.info(
        "Hitter position enrichment: %d/%d resolved (%.1f%%)",
        n_resolved, len(merged), 100 * n_resolved / max(len(merged), 1),
    )
    return merged


def enrich_pitchers(
    df: pd.DataFrame,
    id_col: str = "pitcher",
) -> pd.DataFrame:
    """Add primary_position = 'P' to a pitcher DataFrame.

    The SP/RP role distinction is handled separately via pitcher_role from
    the PLV scoring pipeline; this just marks pitchers as 'P' for display.
    """
    df = df.copy()
    if "primary_position" not in df.columns:
        df["primary_position"] = "P"
    return df


def validate_positions(
    df: pd.DataFrame,
    id_col: str = "batter",
    threshold: float = 0.10,
    strict: bool = False,
) -> dict:
    """Audit position enrichment quality. Returns a summary dict.

    Checks: null primary_position, empty fantasy_positions, multi-position count.
    Logs warnings; raises ValueError in strict mode if unresolved > threshold.
    """
    n = len(df)
    results: dict = {"total_players": n}

    if "primary_position" in df.columns:
        n_null = int(df["primary_position"].isna().sum())
        results["null_primary_position"] = n_null
        if n_null > 0:
            ids = df.loc[df["primary_position"].isna(), id_col].head(10).tolist()
            logger.warning("Null primary_position: %d/%d — sample IDs: %s", n_null, n, ids)
            if strict and n_null > threshold * n:
                raise ValueError(f"Too many null primary_position: {n_null}/{n}")

    if "fantasy_positions" in df.columns:
        n_empty = int((df["fantasy_positions"].fillna("") == "").sum())
        results["empty_fantasy_positions"] = n_empty
        if n_empty > 0:
            logger.warning("Empty fantasy_positions: %d/%d players.", n_empty, n)

    if "is_multi_position" in df.columns:
        n_multi = int(df["is_multi_position"].fillna(False).sum())
        results["multi_position_count"] = n_multi
        results["multi_position_pct"]   = round(100 * n_multi / max(n, 1), 1)
        logger.info(
            "Multi-position players: %d/%d (%.1f%%)",
            n_multi, n, results["multi_position_pct"],
        )

    return results
