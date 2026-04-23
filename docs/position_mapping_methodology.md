# Player Position Mapping Methodology

## Overview

Position data is fetched from the MLB Stats API and joined to all hitter exports
on stable MLBAM player IDs. Positions are derived from actual fielding games
started (GS) in the season, not roster listings, so eligibility reflects observed
playing-time patterns rather than nominal designations.

Results are cached to `data/models/player_positions_{year}.json`. Delete the
cache file to force a refresh from the API.

---

## Data Sources

| Data | Endpoint | Used for |
|------|----------|---------|
| Primary position | `/api/v1/sports/1/players?season={year}` | Single canonical position per player |
| Fielding GS/GP | `/api/v1/stats?stats=season&group=fielding&season={year}&playerPool=ALL` | Eligibility determination |

---

## Eligibility Rule

**Default: 10 games started (GS) at a position.**

This matches the ESPN and Yahoo fantasy platform standard. Configurable via
`PositionConfig.min_games_for_eligibility`.

```python
@dataclass
class PositionConfig:
    min_games_for_eligibility: int = 10  # GS at position
    use_games_started: bool = True        # GS vs GP
    include_dh: bool = True
    outfield_merge: bool = True           # LF/CF/RF → OF
    exclude_pitchers: bool = True
```

---

## Position Normalization

| Raw API value | Normalized | Notes |
|---------------|-----------|-------|
| LF, CF, RF    | OF        | Outfield positions merged |
| C, 1B, 2B, 3B, SS | Same | Passed through directly |
| DH            | DH        | Included by default |
| P, SP, RP     | (excluded) | Pitcher positions excluded from hitter eligibility |
| PH, PR, others | (excluded) | Non-fielding designations ignored |

---

## Output Fields

Every hitter in `master_hitter_{year}.csv` carries these columns:

| Column | Type | Description |
|--------|------|-------------|
| `primary_position` | str | Best single position: normalized API primary, or highest-GS position if primary is pitcher |
| `all_positions_seen` | str (pipe-delimited) | All raw positions with GS > 0, e.g. `"LF\|CF"` |
| `fantasy_positions` | str (pipe-delimited) | Normalized positions passing eligibility, e.g. `"OF"` |
| `fantasy_positions_display` | str (comma-separated) | Human-readable version, e.g. `"OF"` or `"1B, OF"` |
| `is_multi_position` | bool | True if player qualifies at 2+ fantasy positions |
| `position_count` | int | Number of qualifying fantasy positions |

Position columns are sorted in canonical order: C, 1B, 2B, 3B, SS, OF, DH.

---

## Multi-Position Tracking

A player is `is_multi_position = True` when they have ≥ 10 GS at two or more distinct
fantasy positions in the same season. Examples:

- Pete Alonso with 10+ GS at 1B and OF → `fantasy_positions = "1B|OF"`, `is_multi_position = True`
- A catcher who DH'd 10+ times → `fantasy_positions = "C|DH"`, `is_multi_position = True`

Multi-position eligibility is a significant fantasy asset (roster flexibility).
The `is_multi_position` column enables filtering in all hitter views.

---

## Primary Position Logic

1. Use the API primary position, normalized (LF/CF/RF → OF).
2. If the API says the player is a pitcher (P/SP/RP) but they have qualifying hitter
   positions, prefer the first qualifying hitter position.
3. If no primary is resolvable, fall back to the position with the most GS in the season.

---

## Dashboard Integration

Position multiselect filters appear in:
- **Hitters** tab (Leaderboard)
- **Hitter Fantasy** tab
- **Target Boards** tab (hitter boards only)

Player View shows `fantasy_positions_display` in the player header.

---

## Pitchers

Pitchers receive `primary_position = "P"` uniformly. The SP/RP role distinction
is handled separately by the PLV role inference pipeline (`pitcher_role` column
in pitcher exports), not by the position mapping layer.

---

## Caching and Refresh

Position data is cached per year to `data/models/player_positions_{year}.json`.

- Re-run `plv build-exports {year}` to refresh (will use cache if present)
- Delete `player_positions_{year}.json` to force API re-fetch
- Cache should be refreshed at least once mid-season as rosters shift

---

## Known Limitations

- **Early season**: GS counts are low for all players. The 10-GS threshold may
  disqualify true multi-position players until they accumulate enough appearances.
  Use 5 GS for early-season analysis by setting `min_games_for_eligibility=5`.
- **DH-only**: Pure designated hitters who never field appear only as DH in
  `fantasy_positions`. If your league doesn't have a DH slot, set `include_dh=False`.
- **Position switches mid-season**: If a player moves positions during the year,
  they may qualify at multiple positions or have split GS totals. The API returns
  per-position season-total stats, so both positions will be captured correctly.
- **Unresolved players**: Hitters not in the MLB Stats API fielding data (very rare —
  typically one-game callups with no fielding appearances) will have null position
  fields. These are logged as warnings during export.
