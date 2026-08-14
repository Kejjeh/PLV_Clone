"""
Fantasy league scoring configuration and fantasy-point calculators.

The LeagueScoring dataclass holds per-event point weights and is the
single source of truth for all FP calculations. Edit league_scoring.json
to change weights without touching code.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


def _parse_ip(raw) -> float:
    """MLB gameLog inningsPitched parser.

    MLB API returns inningsPitched as a string with .0/.1/.2 partial-inning
    notation: '5.0' = 5.000, '5.1' = 5 + 1/3, '5.2' = 5 + 2/3.

    Accepts:  '5.2', '5.0', '0.0', '1.0', 5.0 (float), 0 (int), None, ''.
    Raises:   ValueError on unparseable string with malformed decimal.
    Returns:  float innings (e.g. '5.2' -> 5.6667).
    """
    if raw is None or raw == '':
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if '.' not in s:
        return float(s)
    whole, frac = s.split('.', 1)
    whole_i = int(whole)
    frac_i = int(frac)
    if frac_i == 0:
        return float(whole_i)
    if frac_i == 1:
        return whole_i + 1 / 3
    if frac_i == 2:
        return whole_i + 2 / 3
    raise ValueError(
        f"_parse_ip: unexpected partial-inning notation {raw!r} (frac={frac_i})"
    )


@dataclass
class LeagueScoring:
    """Per-event fantasy-point weights for one league."""

    # ── Batting ───────────────────────────────────────────────────────────
    r:       float = 1.0    # Runs scored
    tb:      float = 1.0    # Total bases
    rbi:     float = 1.0    # Runs batted in
    bb_bat:  float = 1.0    # Walks (batting)
    k_bat:   float = -1.0   # Strikeouts (batting)
    hbp_bat: float = 1.0    # Hit by pitch (batting)
    sb:      float = 1.0    # Stolen bases

    # ── Pitching ──────────────────────────────────────────────────────────
    ip:     float = 3.3    # Innings pitched (per IP)
    h_pit:  float = -1.0   # Hits allowed
    er:     float = -2.0   # Earned runs
    bb_pit: float = -1.0   # Walks issued
    hb_pit: float = -1.0   # Hit batters
    k_pit:  float = 1.0    # Strikeouts (pitching)
    sv:     float = 5.0    # Saves
    hd:     float = 3.0    # Holds (BrownU HLD×3, ESPN statId 60; see data/models/league_scoring.json)

    @classmethod
    def load(cls, path: str | Path) -> "LeagueScoring":
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    # ── Game-level scoring API (PR 5 sub-action 1) ────────────────────────
    def score_hitter_game(self, stats: dict) -> float:
        """MLB gameLog -> BrownU FP for a hitter game.

        Keys: runs, totalBases, rbi, baseOnBalls, hitByPitch, stolenBases,
        strikeOuts.
        """
        return (
            self.r        * stats['runs']
            + self.tb     * stats['totalBases']
            + self.rbi    * stats['rbi']
            + self.bb_bat * stats['baseOnBalls']
            + self.hbp_bat * stats['hitByPitch']
            + self.sb     * stats['stolenBases']
            + self.k_bat  * stats['strikeOuts']
        )

    def _score_pitcher_base_game(self, stats: dict) -> float:
        """PRIVATE. Shared K/IP/H/ER/BB/HBP scoring used by starts and relief.

        Does NOT add SV/HLD. Called by both score_pitcher_start and
        score_pitcher_relief. Naming intentionally avoids 'start' so relief
        callers aren't semantically coupled to a starting-pitcher abstraction.
        """
        ip = _parse_ip(stats['inningsPitched'])
        return (
            self.k_pit    * stats['strikeOuts']
            + self.ip     * ip
            + self.h_pit  * stats['hits']
            + self.er     * stats['earnedRuns']
            + self.bb_pit * stats['baseOnBalls']
            + self.hb_pit * stats['hitByPitch']
        )

    def score_pitcher_start(self, stats: dict) -> float:
        """MLB gameLog -> BrownU FP for a start.

        Filter caller: stats['gamesStarted']==1. SV/HLD are not added
        (starters do not accumulate these in BrownU scoring).
        """
        return self._score_pitcher_base_game(stats)

    def score_pitcher_relief(self, stats: dict) -> float:
        """MLB gameLog -> BrownU FP for a relief appearance.

        Filter caller: stats['gamesStarted']==0. Adds self.sv*saves +
        self.hd*holds on top of shared base scoring. Does NOT call
        score_pitcher_start.
        """
        base = self._score_pitcher_base_game(stats)
        return base + self.sv * stats['saves'] + self.hd * stats['holds']

    def score_player_game(
        self,
        player_type: Literal['H', 'SP', 'RP'],
        stats: dict,
    ) -> float:
        """Dispatcher: 'H' -> hitter, 'SP' -> start, 'RP' -> relief."""
        if player_type == 'H':
            return self.score_hitter_game(stats)
        if player_type == 'SP':
            return self.score_pitcher_start(stats)
        if player_type == 'RP':
            return self.score_pitcher_relief(stats)
        raise ValueError(
            f"score_player_game: unknown player_type {player_type!r} "
            "(expected 'H', 'SP', or 'RP')"
        )


def hitter_fp_per_pa(
    r_per_pa: float,
    tb_per_pa: float,
    rbi_per_pa: float,
    bb_per_pa: float,
    k_per_pa: float,
    hbp_per_pa: float,
    sb_per_pa: float,
    scoring: LeagueScoring,
) -> float:
    """Expected fantasy points per plate appearance (full: includes R and RBI)."""
    return (
        scoring.r      * r_per_pa
        + scoring.tb      * tb_per_pa
        + scoring.rbi     * rbi_per_pa
        + scoring.bb_bat  * bb_per_pa
        + scoring.k_bat   * k_per_pa
        + scoring.hbp_bat * hbp_per_pa
        + scoring.sb      * sb_per_pa
    )


def hitter_core_fp_per_pa(
    tb_per_pa: float,
    bb_per_pa: float,
    k_per_pa: float,
    hbp_per_pa: float,
    sb_per_pa: float,
    scoring: LeagueScoring,
) -> float:
    """Core skill FP/PA: TB, BB, K, HBP, SB only. Excludes context-dependent R and RBI."""
    return (
        scoring.tb      * tb_per_pa
        + scoring.bb_bat  * bb_per_pa
        + scoring.k_bat   * k_per_pa
        + scoring.hbp_bat * hbp_per_pa
        + scoring.sb      * sb_per_pa
    )


def pitcher_fp_per_ip(
    h_per_ip: float,
    er_per_ip: float,
    bb_per_ip: float,
    hb_per_ip: float,
    k_per_ip: float,
    scoring: LeagueScoring,
) -> float:
    """Expected fantasy points per inning pitched (excludes SV/HD)."""
    return (
        scoring.ip
        + scoring.h_pit  * h_per_ip
        + scoring.er     * er_per_ip
        + scoring.bb_pit * bb_per_ip
        + scoring.hb_pit * hb_per_ip
        + scoring.k_pit  * k_per_ip
    )


# ── Totals-based convenience calculators ──────────────────────────────────────
# These take SUMMED COUNTING TOTALS (not rates) and return total FP. They are
# the seam for the ~35 scripts that inline-derive the BrownU formula from
# accumulated stat totals. Default scoring is the module-level DEFAULT instance,
# whose weights match the BrownU constants documented in CLAUDE.md.

DEFAULT = LeagueScoring()


def pitcher_fp(
    k: float,
    ip: float,
    h: float,
    er: float,
    bb: float,
    hbp: float,
    sv: float = 0.0,
    hld: float = 0.0,
    scoring: LeagueScoring = DEFAULT,
) -> float:
    """Total pitcher FP from counting totals.

    BrownU default: K + IP*3.3 - H - 2*ER - BB - HBP + 5*SV + 2*HLD.
    `ip` is expected already in decimal innings (use _parse_ip on raw
    '5.2'-style MLB strings first). SV/HLD default to 0 for starters.
    """
    return (
        scoring.k_pit    * k
        + scoring.ip     * ip
        + scoring.h_pit  * h
        + scoring.er     * er
        + scoring.bb_pit * bb
        + scoring.hb_pit * hbp
        + scoring.sv     * sv
        + scoring.hd     * hld
    )


def hitter_fp(
    r: float,
    tb: float,
    rbi: float,
    bb: float,
    hbp: float,
    sb: float,
    k: float,
    scoring: LeagueScoring = DEFAULT,
) -> float:
    """Total hitter FP from counting totals.

    BrownU default: R + TB + RBI + BB + HBP + SB - K.
    """
    return (
        scoring.r        * r
        + scoring.tb     * tb
        + scoring.rbi    * rbi
        + scoring.bb_bat * bb
        + scoring.hbp_bat * hbp
        + scoring.sb     * sb
        + scoring.k_bat  * k
    )
