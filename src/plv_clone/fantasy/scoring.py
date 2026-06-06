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
    hd:     float = 2.0    # Holds (BrownU HLD×2; see data/models/league_scoring.json)

    @classmethod
    def load(cls, path: str | Path) -> "LeagueScoring":
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))


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
