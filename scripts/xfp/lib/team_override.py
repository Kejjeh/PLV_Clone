"""team_override — repoint a projection row at the club the player is on NOW.

WHY THIS EXISTS
The models derive `team` from historical Statcast, which is by construction
where a player USED to be. After the 2026 deadline that left **85 players**
carrying stale clubs across rh3 and the volume models — José Soriano read LAA
in xfp_sp_volume_projections.csv while starting for Toronto.

Team is not a cosmetic column. Park factors, schedule joins, opponent context,
bullpen and closer lenses all key on it, so a stale code is quietly wrong in a
dozen places rather than loudly wrong in one.

Two rules the API enforces:

1. **Absence is not a trade.** A 40-man pull does not contain every projected
   player (minors, released, 60-day IL). A player missing from the map keeps
   whatever team he had; blanking him would break lookups that work today.
2. **Never write a code the model vocabulary cannot resolve.** Stale gives the
   wrong park; unknown gives no park at all. Codes outside MODEL_TEAM_CODES
   are dropped at load time and counted, not written.

The override is an IMPROVEMENT, never a dependency: a missing map file yields
an empty map and every call becomes a no-op, so a fresh clone still runs.

Rule 13: this corrects an identity field. It does not touch any projection.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

# The vocabulary every projection CSV and the park tables already speak.
# Verified 2026-08-03: statsapi's `abbreviation` matches this set exactly for
# all 30 clubs, so no translation layer is needed — but a code outside it is
# refused rather than written.
MODEL_TEAM_CODES = frozenset({
    'ATH', 'ATL', 'AZ', 'BAL', 'BOS', 'CHC', 'CIN', 'CLE', 'COL', 'CWS',
    'DET', 'HOU', 'KC', 'LAA', 'LAD', 'MIA', 'MIL', 'MIN', 'NYM', 'NYY',
    'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL', 'TB', 'TEX', 'TOR', 'WSH',
})

DEFAULT_MAP = Path('data/reference/current_teams.json')
STALE_AFTER_DAYS = 3


@dataclass(frozen=True)
class TeamMap:
    teams: dict = field(default_factory=dict)      # mlbam(int) -> model code
    as_of: Optional[datetime.date] = None
    rejected: int = 0                              # codes outside the vocabulary
    source: str = ''

    @property
    def empty(self) -> bool:
        return not self.teams

    def staleness_days(self, today: Optional[datetime.date] = None) -> Optional[int]:
        if self.as_of is None:
            return None
        return ((today or datetime.date.today()) - self.as_of).days

    def is_stale(self, today: Optional[datetime.date] = None) -> bool:
        d = self.staleness_days(today)
        return d is not None and d > STALE_AFTER_DAYS

    def label(self, today: Optional[datetime.date] = None) -> str:
        if self.empty:
            return 'team override: NO MAP (no-op) — run build_current_teams.py'
        d = self.staleness_days(today)
        age = 'age unknown' if d is None else f'{d}d old'
        flag = ' ⚠ STALE' if self.is_stale(today) else ''
        rej = f', {self.rejected} code(s) refused' if self.rejected else ''
        return f'team override: {len(self.teams)} players, {age}{flag}{rej}'


def load_map(path=DEFAULT_MAP) -> TeamMap:
    """Read the map. A missing/unreadable file yields an EMPTY map, not an error."""
    p = Path(path)
    if not p.exists():
        return TeamMap()
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return TeamMap()
    players = raw.get('players') or {}
    teams, rejected = {}, 0
    for k, v in players.items():
        code = str((v or {}).get('abbr') or '').upper()
        if code not in MODEL_TEAM_CODES:
            rejected += 1
            continue
        try:
            teams[int(k)] = code
        except (TypeError, ValueError):
            rejected += 1
    as_of = None
    if raw.get('as_of'):
        try:
            as_of = datetime.date.fromisoformat(str(raw['as_of']))
        except ValueError:
            pass
    return TeamMap(teams=teams, as_of=as_of, rejected=rejected,
                   source=str(raw.get('source') or ''))


def apply_team_override(df: pd.DataFrame, tmap: TeamMap, *,
                        mlbam_col: str = 'mlbam', team_col: str = 'team'):
    """-> (df, n_changed, n_unknown). Returns a COPY; never mutates the input.

    Raises KeyError when *mlbam_col* is absent, rather than quietly doing
    nothing — a renamed id column would otherwise make this a permanent no-op,
    which is exactly how the SP volume join sat dead while matching 0 of 29.
    """
    if mlbam_col not in df.columns:
        raise KeyError(
            f'{mlbam_col!r} not in frame (have: {list(df.columns)[:8]}...). '
            f'Pass the right mlbam column; a silent no-op is not an option.')
    out = df.copy()
    if tmap.empty or team_col not in out.columns:
        return out, 0, 0
    ids = pd.to_numeric(out[mlbam_col], errors='coerce')
    mapped = ids.map(tmap.teams)
    known = mapped.notna()
    changed = known & (mapped != out[team_col])
    out.loc[changed, team_col] = mapped[changed]
    return out, int(changed.sum()), int((~known).sum())


__all__ = ['MODEL_TEAM_CODES', 'DEFAULT_MAP', 'STALE_AFTER_DAYS', 'TeamMap',
           'load_map', 'apply_team_override']
