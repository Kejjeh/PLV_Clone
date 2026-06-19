"""matchup_projection — the deep, pure core of the H2H matchup projection.

This module owns the *adjuster math* that used to live inline in
``scripts/xfp/build_matchup_dashboard.py::project_player`` behind a wall of
module globals (MA0–MA7, momentum, heteroscedastic σ).  The dashboard keeps the
*data assembly* (schedule resolution, role/collision detection, ESPN/MLB I/O);
this module keeps the *computation*: how a base projection + a sequence of
per-event contexts combine into FP, variance, and the breakdown rows the HTML
reads.

Design (ADR-0001 / ADR-0002 shape):
  - No god-config object.  Three composed pure functions — one per role
    (SP / hitter / RP) — over injected data.  Per-event context arrives as
    frozen dataclasses; scalar knobs arrive as a frozen ``MatchupConfig``.
  - Pure over data: no I/O, no module globals, no pandas dependency.  Tested
    with literal contexts — the interface is the test surface.

The breakdown-row dict keys are part of the interface: the dashboard's
``render_*`` functions and ``apply_sp_cap`` read them, so they are reproduced
here verbatim.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# --- adjuster clamp bounds (the magic numbers that were inline) ---------------
# Each clamp expresses "an opponent/platoon factor can only move a projection so
# far."  They live here, next to the combination rule they bound.
_SP_OPP_CLAMP = (0.80, 1.20)        # opposing-offense factor on an SP start
_HIT_OPP_SP_CLAMP = (0.70, 1.30)    # opposing-SP factor on a hitter game
_HIT_OPP_TEAM_CLAMP = (0.85, 1.15)  # fallback team-pitching factor on a hitter game
_PLATOON_CLAMP = (0.85, 1.15)       # platoon (stance vs opp xwOBA) factor


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class MatchupConfig:
    """Scalar knobs shared across the three projection paths.

    Defaults mirror the constants in build_matchup_dashboard.py so a caller can
    omit them and get identical behaviour.
    """
    league_avg_sp_fp_per_start: float = 11.5
    league_avg_xwoba: float = 0.310
    unconfirmed_start_conf: float = 0.80
    default_rp_app_rate: float = 0.35
    # variance fallbacks (used when a per-player σ is unavailable)
    sigma_per_sp_start: float = 5.5
    sigma_per_rp_game: float = 2.5
    sigma_per_hitter_game: float = 3.5
    # heteroscedastic hitter variance
    global_sigma_pa_fp: float = 0.517
    league_pa_per_game: float = 3.5


@dataclass(frozen=True)
class ProjResult:
    """Output of a per-role projection: total FP, scoring units, variance, and
    the per-event breakdown rows the dashboard renders."""
    fp: float
    units: float
    sigma2: float
    breakdown: list[dict] = field(default_factory=list)


# =============================================================================
# SP — projected starts under the cap
# =============================================================================

@dataclass(frozen=True)
class SPStartCtx:
    """One projected SP start.  ``opp_bat_index`` is the opposing offense's bat
    index (higher = tougher); ``confirmed`` distinguishes ESPN-probable starts
    from rotation-gap predictions."""
    date: str
    opp_team: str
    opp_bat_index: Optional[float]
    confirmed: bool = True


def sp_opp_factor(opp_bat_index: Optional[float]) -> float:
    """Opposing-offense factor for an SP start: a strong opposing lineup
    suppresses the start.  ``1/idx`` clamped to ±20%."""
    if not opp_bat_index:
        return 1.0
    return _clamp(1.0 / opp_bat_index, *_SP_OPP_CLAMP)


def project_sp_starts(
    per_start_base: float,
    starts: list[SPStartCtx],
    *,
    recent_factor: float = 1.0,
    calib: float = 1.0,
    momentum: float = 1.0,
    sigma: float,
    cfg: MatchupConfig = MatchupConfig(),
) -> ProjResult:
    """Project a pitcher's in-window starts.

    FP per start = base × opp × recent_form × calibration × confidence × momentum.
    Variance = n_starts × σ².
    """
    total = 0.0
    breakdown: list[dict] = []
    for s in starts:
        opp_factor = sp_opp_factor(s.opp_bat_index)
        confidence = 1.0 if s.confirmed else cfg.unconfirmed_start_conf
        fp = per_start_base * opp_factor * recent_factor * calib * confidence * momentum
        total += fp
        breakdown.append({
            'date': s.date, 'opp': s.opp_team,
            'opp_idx': s.opp_bat_index or 1.0, 'factor': opp_factor,
            'recent_factor': recent_factor,
            'confidence': confidence,
            'sp_momentum': momentum,
            'fp': fp, 'type': 'start',
            'confirmed': s.confirmed,
        })
    return ProjResult(fp=total, units=len(starts),
                      sigma2=len(starts) * sigma ** 2, breakdown=breakdown)


# =============================================================================
# Hitter — projected games
# =============================================================================

@dataclass(frozen=True)
class HitterGameCtx:
    """One projected hitter game.  Exactly one of ``opp_per_start`` (opposing
    SP's rp3 per-start projection, preferred) or ``team_pit_index`` (fallback)
    drives the opp factor; ``platoon_xwoba`` is the opposing SP's xwOBA vs the
    batter's *effective* stance (already resolved for switch hitters), or None."""
    date: str
    opp_team: str
    opp_probable_name: str = '?'
    opp_per_start: Optional[float] = None
    team_pit_index: Optional[float] = None
    platoon_xwoba: Optional[float] = None


def hitter_opp_factor(opp_per_start: Optional[float],
                      team_pit_index: Optional[float],
                      cfg: MatchupConfig) -> tuple[float, Optional[float]]:
    """Opposing-pitching factor for a hitter game.  Prefers the opposing SP's
    own projection (tougher SP = bigger suppression); falls back to the team
    pitching index.  The SP path is chosen by *availability* (``opp_per_start
    is not None``), so a zero-projection SP still takes the SP branch (neutral
    factor) rather than silently falling through to the team index.  Returns
    (factor, opp_proj_for_breakdown)."""
    if opp_per_start is not None:
        if opp_per_start:
            return _clamp(cfg.league_avg_sp_fp_per_start / opp_per_start,
                          *_HIT_OPP_SP_CLAMP), opp_per_start
        return 1.0, opp_per_start
    if team_pit_index is not None:
        return _clamp(team_pit_index, *_HIT_OPP_TEAM_CLAMP), None
    return 1.0, None


def platoon_factor(platoon_xwoba: Optional[float], cfg: MatchupConfig) -> float:
    """Platoon factor from the opposing SP's xwOBA vs the batter's stance."""
    if platoon_xwoba and platoon_xwoba > 0 and cfg.league_avg_xwoba:
        return _clamp(platoon_xwoba / cfg.league_avg_xwoba, *_PLATOON_CLAMP)
    return 1.0


def _is_missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def project_hitter_games(
    per_game_base: float,
    games: list[HitterGameCtx],
    *,
    recent_factor: float = 1.0,
    lineup_factor: float = 1.0,
    il_factor: float = 1.0,
    calib: float = 1.0,
    momentum: float = 1.0,
    sigma_factor: Optional[float] = None,
    pa_per_g: Optional[float] = None,
    legacy_sigma: bool = False,
    cfg: MatchupConfig = MatchupConfig(),
) -> ProjResult:
    """Project a hitter's in-window games.

    FP per game = base × opp × recent_form × lineup × park(=1) × platoon × IL
                  × calibration × momentum.
    Variance: heteroscedastic (per-PA σ × per-batter factor, summed over PAs)
    when ``sigma_factor`` is available, else the legacy fixed per-game σ.
    """
    park_factor = 1.0
    total = 0.0
    breakdown: list[dict] = []
    for g in games:
        opp_factor, opp_proj = hitter_opp_factor(g.opp_per_start, g.team_pit_index, cfg)
        plat = platoon_factor(g.platoon_xwoba, cfg)
        fp = (per_game_base * opp_factor * recent_factor * lineup_factor
              * park_factor * plat * il_factor * calib * momentum)
        total += fp
        breakdown.append({
            'date': g.date, 'opp': g.opp_team,
            'opp_sp': g.opp_probable_name,
            'opp_sp_proj': opp_proj, 'factor': opp_factor,
            'recent_factor': recent_factor,
            'lineup_factor': lineup_factor,
            'park_factor': park_factor,
            'platoon_factor': plat,
            'il_factor': il_factor,
            'h_momentum': momentum,
            'fp': fp, 'type': 'game',
        })
    n = len(games)
    if legacy_sigma or _is_missing(sigma_factor):
        sigma2 = n * cfg.sigma_per_hitter_game ** 2
    else:
        ppg = pa_per_g or cfg.league_pa_per_game
        sigma_pa = cfg.global_sigma_pa_fp * float(sigma_factor)
        sigma2 = n * (sigma_pa ** 2) * ppg
    return ProjResult(fp=total, units=n, sigma2=sigma2, breakdown=breakdown)


# =============================================================================
# RP — projected appearances
# =============================================================================

def project_rp(
    xfp_ros: float,
    n_team_games: int,
    *,
    role: str,
    app_rate: float,
    days_remaining_season: int,
    il_factor: float = 1.0,
    calib: float = 1.0,
    rp_sigma: Optional[float] = None,
    cfg: MatchupConfig = MatchupConfig(),
) -> ProjResult:
    """Project a reliever's in-window appearances.

    Per-team-game FP = RoS FP / days remaining; scaled to a per-appearance rate,
    multiplied by expected appearances (team games × appearance rate), then IL
    pro-rate and calibration.  Variance = expected_appearances × σ².
    """
    if not xfp_ros or n_team_games <= 0:
        return ProjResult(fp=0.0, units=0, sigma2=0.0, breakdown=[])
    days = max(days_remaining_season, 1)
    per_team_game = xfp_ros / days
    expected_appearances = n_team_games * app_rate
    per_app = (per_team_game / cfg.default_rp_app_rate) if cfg.default_rp_app_rate else per_team_game
    proj = per_app * expected_appearances * il_factor * calib
    sigma = rp_sigma if rp_sigma is not None else cfg.sigma_per_rp_game
    return ProjResult(
        fp=proj,
        units=round(expected_appearances, 1),
        sigma2=expected_appearances * sigma ** 2,
        breakdown=[{
            'role': role, 'app_rate': app_rate,
            'n_team_games': n_team_games,
            'expected_apps': expected_appearances,
            'il_factor': il_factor,
            'fp': proj,
        }],
    )


# =============================================================================
# IL availability window (date-known case)
# =============================================================================

def il_availability_factor(return_date, today, week_end) -> Optional[float]:
    """Fraction of the remaining week an IL'd player is available, given a known
    return date.  Returns None when the player returns *after* the week (caller
    should zero them out entirely)."""
    if return_date > week_end:
        return None
    days_avail = max(0, (week_end - max(return_date, today)).days + 1)
    days_total = max(1, (week_end - today).days + 1)
    return days_avail / days_total


# =============================================================================
# Win probability (Candidate 4) — two adapters over the same seam
# =============================================================================

def win_prob_normal(my_total: float, opp_total: float,
                    my_sigma2: float, opp_sigma2: float) -> float:
    """P(my_team > opp) under a normal-approx of remaining-FP distributions."""
    gap = my_total - opp_total
    sigma = math.sqrt(my_sigma2 + opp_sigma2)
    if sigma == 0:
        return 1.0 if gap > 0 else 0.0
    z = gap / sigma
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def win_prob_bootstrap(my_players, opp_players,
                       my_wtd: float, opp_wtd: float,
                       n_trials: int = 5000, seed: int = 42) -> float:
    """Monte-Carlo win prob with right-skewed (lognormal) per-player marginals.

    ``my_players`` / ``opp_players`` are iterables of ``(mean_fp, variance)``
    tuples.  Lognormal captures HR/upside right tails the normal-approx misses;
    falls back to a normal draw for non-positive mean/variance.  Deterministic
    given ``seed``.
    """
    import numpy as np
    rng = np.random.default_rng(seed=seed)

    def _draws(mu: float, var: float):
        if mu <= 0 or var <= 0:
            return rng.normal(mu, max(math.sqrt(max(var, 0)), 1e-6), n_trials)
        sig2 = math.log(1 + var / (mu * mu))
        lmu = math.log(mu) - sig2 / 2
        return rng.lognormal(lmu, math.sqrt(sig2), n_trials)

    my_trials = np.full(n_trials, my_wtd, dtype=float)
    for mu, var in my_players:
        my_trials = my_trials + _draws(mu, var)
    opp_trials = np.full(n_trials, opp_wtd, dtype=float)
    for mu, var in opp_players:
        opp_trials = opp_trials + _draws(mu, var)
    return float((my_trials > opp_trials).mean())


def win_prob(my_total: float, opp_total: float,
             my_sigma2: float, opp_sigma2: float,
             *, method: str = 'normal',
             my_players=None, opp_players=None,
             my_wtd: float = 0.0, opp_wtd: float = 0.0,
             n_trials: int = 5000, seed: int = 42) -> float:
    """Unified win-prob seam.  ``method='normal'`` uses the totals+variances;
    ``method='bootstrap'`` requires the per-player ``(mean, var)`` iterables and
    week-to-date scores."""
    if method == 'bootstrap':
        if my_players is None or opp_players is None:
            raise ValueError("bootstrap requires my_players/opp_players")
        return win_prob_bootstrap(my_players, opp_players, my_wtd, opp_wtd,
                                  n_trials=n_trials, seed=seed)
    return win_prob_normal(my_total, opp_total, my_sigma2, opp_sigma2)
