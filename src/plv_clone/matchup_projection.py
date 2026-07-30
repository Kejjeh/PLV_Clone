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


# --- hitter per-game outcome σ: units, and the constant ------------------------
# Calibrated 2026-07-29.  Script: scripts/xfp/validate_hitter_sigma_scale.py.
# Memo: data/research/validation_runs/hitter_sigma_scale_2026-07-29.md.
#
# ``MatchupConfig.global_sigma_pa_fp`` (0.517) is NOT a per-PA σ, despite its
# name and every comment that ever cited it.  build_hitter_sigma_calibration.py
# (lines 77-83) computes it as the PA-weighted RMS of the per-GAME residual of
# ``fp_proxy / PA`` — that is a per-GAME RATE, one observation per game.  Proof
# on the same 245,712-batter-game panel: PA-weighted 0.516968 vs the UNWEIGHTED
# SD of the identical rate 0.518566 (+0.31%), so the PA weighting does not
# convert the unit.  Two consequences, both corrected below:
#
#  (1) EXPONENT.  Per-game σ = rate_σ × PA/game, so PA/game enters the VARIANCE
#      squared.  Dimensional test on the panel (mean PA/g 4.3483, measured
#      within-batter per-game SD of fp_proxy 2.2816):
#          per-PA reading   0.517 × sqrt(4.3483) = 1.0780   (−52.8% vs measured)
#          per-game-rate    0.517 × 4.3483       = 2.2479   (− 1.5% vs measured)
#      Confirmed on per-batter PA/g variation (377 batters, 26,199 started 2026
#      games): σ = C·ppg fits with weighted R² +0.2142 vs +0.1654 for C·sqrt(ppg).
#
#  (2) SCALE.  ``fp_proxy = TB + BB + HBP − K`` OMITS R, RBI and SB, so it is not
#      the BrownU formula (R + TB + RBI + BB + HBP + SB − K) at all.  Measured on
#      2026 boxscore rows that carry both: canonical/proxy per-game-RATE σ ratio
#      = 1.4742.
#
# _FP_PROXY_TO_FULL_FP_SIGMA carries (2) plus the through-origin recalibration of
# the per-batter slope:  1.4742 (formula gap) × 1.0295 (slope recal) = 1.5175, so
#     0.517 × 1.5175 = 0.784563 FP per PA-of-a-game, canonical units.
# Realised check: canonical within-batter per-game hitter FP SD = 3.2502 FP;
# 0.784563 × mean pa_per_g 4.0016 = 3.1395 FP; the per-batter ratio
# realised/model has mean 0.9961 and SD 0.1583.
#
# The per-batter ``sigma_factor`` needs NO refit: it is pred_σ/global_σ
# re-centred to mean 1.0, ridge is scale-equivariant in y, and rescaling the
# fitted σ_emp by 2× and 10× reproduces the factors to max |Δ| = 0.0 / 2.0e-15.
_FP_PROXY_TO_FULL_FP_SIGMA = 1.517531

# Measured mean PA per STARTED game over 2026 regulars (>= 30 started games) —
# the fallback when a batter has no lineup-map entry.  The old 3.5 was inherited
# from rh3's per-game construction constant, not measured as a PA mean.
_LEAGUE_PA_PER_GAME_MEASURED = 4.0016


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
    # Heteroscedastic hitter variance.  ``global_sigma_pa_fp`` is the pooled
    # within-batter σ of the PROXY per-game FP RATE (fp_proxy/PA, where
    # fp_proxy = TB+BB+HBP−K) from the 2018-2025 boom-bust panel — NOT a per-PA σ
    # and NOT in canonical BrownU FP units.  ``hitter_sigma_per_game`` converts
    # it; see _FP_PROXY_TO_FULL_FP_SIGMA above.  The historical field name is kept
    # so callers that pass it keep working, but the docstring is the contract.
    global_sigma_pa_fp: float = 0.517
    # Fallback PA/started-game when a batter has no lineup-map entry (measured,
    # see _LEAGUE_PA_PER_GAME_MEASURED).
    league_pa_per_game: float = _LEAGUE_PA_PER_GAME_MEASURED


@dataclass(frozen=True)
class Adjusters:
    """The matchup dashboard's adjuster *data* as one immutable value.

    Bundles the ~10 maps + toggles the dashboard used to keep as mutable module
    globals (MA2 form, lineup, platoon splits, bat side, IL returns, calibration,
    RP appearance rates, within-week momentum).  ``project_player`` reads from an
    injected ``Adjusters`` instead of globals, so its dependencies are its
    signature and the shadow A/B pass builds a *second* value (via
    ``dataclasses.replace``) rather than mutating shared state mid-run.
    """
    adjusters_on: bool = False
    ma2_hitter_on: bool = False
    ma2_sp_on: bool = False
    calib: float = 1.0
    sp_form: dict = field(default_factory=dict)        # mlbam -> recency-form factor (SP)
    hitter_form: dict = field(default_factory=dict)    # legacy SP-form map (kept for compat)
    lineup: dict = field(default_factory=dict)         # batter mlbam -> {modal_spot, pa_per_g}
    park: dict = field(default_factory=dict)           # MA4 dropped; empty stub
    psplit: dict = field(default_factory=dict)         # pitcher mlbam -> platoon split
    bat_side: dict = field(default_factory=dict)       # batter mlbam -> stance
    il_returns: dict = field(default_factory=dict)     # player_id -> return date
    rp_app_rates: dict = field(default_factory=dict)   # mlbam -> appearance rate
    weekly_momentum: dict = field(default_factory=dict)  # join_key -> within-week form factor

    @classmethod
    def neutral(cls) -> "Adjusters":
        """All-inert adjusters: empty maps, calib 1.0, every toggle off.  A
        projection run with neutral adjusters is the baseline xfp model."""
        return cls()


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


def hitter_sigma_per_game(sigma_factor: float,
                          pa_per_g: Optional[float],
                          cfg: "MatchupConfig" = None) -> float:
    """Per-GAME outcome σ (canonical BrownU FP units) for one hitter game.

        σ_game = global_proxy_rate_σ × proxy→canonical × sigma_factor × PA/game

    PA/game is LINEAR here, so it enters the variance SQUARED — see
    ``_FP_PROXY_TO_FULL_FP_SIGMA`` for the measurement that establishes both the
    exponent and the constant.

    ``pa_per_g`` may be omitted (None/NaN), in which case the measured league
    mean ``cfg.league_pa_per_game`` stands in.  A *supplied* pa_per_g that is
    non-positive is a broken input, not a missing one, and raises: silently
    substituting a default for bad data is how the 2026-07-28 ROOT bug happened.
    """
    if cfg is None:
        cfg = MatchupConfig()
    if _is_missing(sigma_factor):
        raise ValueError("hitter_sigma_per_game requires a real sigma_factor; "
                         "callers must route missing factors to the legacy σ path")
    if _is_missing(pa_per_g):
        ppg = float(cfg.league_pa_per_game)
    else:
        ppg = float(pa_per_g)
        if ppg <= 0:
            raise ValueError(
                f"pa_per_g must be > 0 when supplied, got {pa_per_g!r}. "
                "A batter with no measurable PA/game must be passed as None so "
                "the measured league fallback is used explicitly."
            )
    if ppg <= 0:
        raise ValueError(f"cfg.league_pa_per_game must be > 0, got {ppg!r}")
    return (float(cfg.global_sigma_pa_fp) * _FP_PROXY_TO_FULL_FP_SIGMA
            * float(sigma_factor) * ppg)


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
    Variance: heteroscedastic — ``n × hitter_sigma_per_game(...)²``, where the
    per-game σ is LINEAR in PA/game (see ``hitter_sigma_per_game``) — when
    ``sigma_factor`` is available, else the legacy fixed per-game σ.
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
        sigma2 = n * hitter_sigma_per_game(sigma_factor, pa_per_g, cfg) ** 2
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
# Display kernels — pure logic lifted out of the dashboard's render_* functions
# (R2-3). The render functions keep the HTML; these own the decisions/math so
# they can be tested without generating a page.
# =============================================================================

def two_start_multiplier(pf_wOBA: float, opp_idx: float) -> float:
    """2-start-gem FP multiplier: hitter-park (pf_wOBA) suppresses a pitcher,
    a strong opposing offense (opp_idx) suppresses more.  Clamped to [0.6, 1.4]."""
    mult = (1 - 0.5 * (pf_wOBA - 1)) * (1 - 0.7 * (opp_idx - 1))
    return max(0.6, min(1.4, mult))


def matchup_tier(opp_idx: float) -> str:
    """soft / avg / tough from the opposing-offense index (mirrors
    stream_the_stack's bucketing)."""
    if opp_idx <= 0.97:
        return 'soft'
    if opp_idx >= 1.03:
        return 'tough'
    return 'avg'


def boom_verdict_sp(row: dict) -> list:
    """Conviction/risk tags for an SP boom-bust row (pure over the row's tag
    booleans)."""
    tags = []
    if (row.get('boom_stack') or 0) >= 2: tags.append('🎯 HIGH-CONVICTION')
    if row.get('is_high_k'):              tags.append('🎯K')
    if row.get('is_elite_framer'):        tags.append('🧊 elite-framer')
    if row.get('anti_pred'):              tags.append('⛔ anti-predictive')
    if row.get('is_framing_tax'):         tags.append('⚠ framing-tax')
    if row.get('is_il_return'):           tags.append('🏥 IL-return')
    return tags


def boom_verdict_hit(row: dict) -> list:
    """Conviction tags for a hitter boom-bust row."""
    tags = []
    comps = row.get('components') or {}
    if (row.get('boom_stack') or 0) >= 3:   tags.append('🎯 HIGH-CONVICTION')
    elif (row.get('boom_stack') or 0) >= 2: tags.append('✨ stack 2+')
    if comps.get('lineup_amp_hitter'):  tags.append('🔥 lineup-amp')
    if comps.get('skill_spike_hitter'): tags.append('🎯 skill-spike')
    return tags


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
