"""build_matchup_dashboard.py — schedule + opp + role + cap aware H2H dashboard.

Polish features:
  1. Per-game hitter opp factor uses OPPOSING SP's projection (not just team
     pit_index) → tougher SP = bigger hitter suppression.
  2. RP appearance rates by role: closer 0.55, setup 0.40, middle 0.30 of
     team games.
  3. SP 10-start-per-week cap (BrownU rule): sort projected starts by FP
     descending, keep top 10.
  4. Win probability from projected gap + combined variance.
  5. Two-start pitchers flagged with 🔥 badge.

Output: data/outputs/matchup.html + xfp-model/docs/matchup.html
"""
from __future__ import annotations
import sys
import os
import json
import math
import shutil
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from html import escape as h
from typing import Optional

import pandas as pd

from plv_clone.paths import ROOT, XFP_DOCS  # noqa: E402  (single source for repo paths)
sys.path.insert(0, str(ROOT))

from plv_clone.mlb_stats import fetch_week_probables, resolve_mlbam  # noqa: E402
from plv_clone import matchup_projection as _mproj  # noqa: E402  (deep adjuster core)
from plv_clone.utils.name_match import (  # noqa: E402
    resolve_id,
    KNOWN_COLLISIONS as _KNOWN_COLLISIONS,
    KNOWN_PITCHER_COLLISIONS as _KNOWN_PITCHER_COLLISIONS,
)
from scripts.xfp.lib.pitcher_role import detect_pitcher_role  # noqa: E402
from scripts.xfp.lib.dashboard_chrome import (  # noqa: E402  (unified nav + theme owner)
    topnav, topnav_css, theme_css, theme_boot_js, theme_toggle_html,
    column_toggle_js,
)


def _warn_except(section: str, exc: BaseException) -> None:
    """One-line stderr breadcrumb for fail-soft exception handlers.

    Audit 2026-07-04: 62% of production exception handlers emitted nothing —
    a dead section/lens becomes months of silently wrong numbers. This keeps
    fail-soft SEMANTICS unchanged (caller still returns its fallback) but
    makes the suppression visible in the build log.
    """
    print(f'  ⚠ [{section}] suppressed {type(exc).__name__}: {exc}', file=sys.stderr)


def _section_error(heading: str, exc: BaseException) -> str:
    """Fallback HTML for a section builder that threw — WITH a full traceback
    to stderr so the root cause is visible in the CI log.

    The publish-integrity guard (see main()) detects the 'error:' marker this
    emits and fails the build. Historically the marker was all you got: the
    guard would abort with no way to tell WHICH section broke or WHY, because
    each handler swallowed its exception straight into HTML. Logging the
    traceback here — and naming the section in the guard — turns a bare
    'a section is throwing' into an actionable stack trace. `heading` is the
    exact <h2> text so the guard can attribute the failure back to it.
    """
    print(f'[section-error] {heading}: {type(exc).__name__}: {exc}', file=sys.stderr)
    traceback.print_exc()
    return f'<h2>{heading}</h2><p class="muted">error: {h(str(exc))}</p>'

# Layered display-tag library (validated 2026-06-03). All defensive — every
# compute_* call returns sentinel-tagged dicts on failure so the dashboard
# can never break on a tag compute error.
try:
    from scripts.xfp.lib.boom_stack import (  # noqa: E402
        compute_boom_stack, compute_high_k_pitcher,
    )
    from scripts.xfp.lib.hitter_boom_stack import compute_hitter_boom_stack  # noqa: E402
    from scripts.xfp.lib.catcher_framing import compute_catcher_framing  # noqa: E402
    from scripts.xfp.lib.il_return_flag import compute_il_return_flag  # noqa: E402
    _LAYERED_TAGS_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    print(f'  ⚠ layered-tag library unavailable: {_e}')
    _LAYERED_TAGS_AVAILABLE = False
    def compute_boom_stack(*a, **kw): return {}
    def compute_high_k_pitcher(*a, **kw): return {}
    def compute_hitter_boom_stack(*a, **kw): return {}
    def compute_catcher_framing(*a, **kw): return {}
    def compute_il_return_flag(*a, **kw): return {}

OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
# XFP_DOCS imported from plv_clone.paths (honors PLV_XFP_DOCS for CI).
_BS_PITCHERS = CACHE / 'boxscore_pitchers.parquet'
_BS_HITTERS  = CACHE / 'boxscore_hitters.parquet'



def _today_et():
    """Date in America/New_York (audit 2026-07-04): the hourly UTC runner made
    date.today() flip to TOMORROW during 8pm-2am ET games — Sunday-night builds
    computed NEXT week's matchup mid-game and excluded tonight's games."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('America/New_York')).date()


def _load_bs_week_actuals(week_start: date, yesterday: date) -> dict[str, dict]:
    """Return {norm_name: {fp, starts}} for boxscore-bridge SP starts in [week_start, yesterday].

    Used to supplement ESPN WTD when it hasn't yet processed a start (typically
    the few hours between midnight and ESPN's morning score update).  Only
    injects when p.points == 0 so it never double-counts confirmed ESPN scores.
    """
    if not _BS_PITCHERS.exists():
        return {}
    try:
        df = pd.read_parquet(_BS_PITCHERS)
        df = df[(df['game_date'] >= week_start.isoformat()) &
                (df['game_date'] <= yesterday.isoformat())]
        if df.empty:
            return {}
        out: dict[str, dict] = {}
        for _, row in df.iterrows():
            nk = _norm(row['player_name'])   # canonical join key (matches rh3/rp3 maps)
            if nk not in out:
                out[nk] = {'fp': 0.0, 'starts': []}
            out[nk]['fp'] += float(row['fp_sp'])
            out[nk]['starts'].append({
                'date': str(row['game_date']),
                'ip': float(row['ip']),
                'so': int(row['so']),
                'fp': float(row['fp_sp']),
            })
        return out
    except Exception as e:
        _warn_except('bs_week_actuals', e)
        return {}


def _load_bs_week_hitter_actuals(week_start: date, yesterday: date) -> dict[str, dict]:
    """Return {norm_name: {fp, games}} for boxscore-bridge hitter games in [week_start, yesterday]."""
    if not _BS_HITTERS.exists():
        return {}
    try:
        df = pd.read_parquet(_BS_HITTERS)
        df = df[(df['game_date'] >= week_start.isoformat()) &
                (df['game_date'] <= yesterday.isoformat())]
        if df.empty:
            return {}
        out: dict[str, dict] = {}
        for _, row in df.iterrows():
            nk = _norm(row['player_name'])   # canonical join key (matches rh3/rp3 maps)
            if nk not in out:
                out[nk] = {'fp': 0.0, 'games': []}
            out[nk]['fp'] += float(row['fp_h'])
            out[nk]['games'].append({
                'date': str(row['game_date']),
                'r':   int(row['r']),
                'tb':  int(row['tb']),
                'rbi': int(row['rbi']),
                'fp':  float(row['fp_h']),
            })
        return out
    except Exception as e:
        _warn_except('bs_week_hitter_actuals', e)
        return {}


def compute_weekly_momentum(bs_h_week: dict, rh3_map: dict,
                             bs_week: dict | None = None,
                             rp3_map: dict | None = None) -> dict:
    """Within-week Bayesian form signal keyed by normalized player name.

    Compares each player's actual FP/game so far this week to their rh3/rp3
    per-game/start projection.  Returns a momentum factor (1.0 = neutral) with
    λ=0.15 shrinkage toward 1.0 so outlier single-game noise is damped.

    Range before shrinkage: clipped [0.50, 2.00] → after λ: [0.925, 1.075].
    Applied multiplicatively in project_player after all other adjusters.
    Only fires when ≥1 game has been played this week.
    """
    LAMBDA = 0.15
    MIN_GAMES = 1  # need at least 1 completed game
    result: dict = {}

    # bs_h_week / bs_week are keyed with the canonical `_norm` join key (the same
    # sorted-parts key rh3_map / rp3_map use), so lookups match directly.
    for nk, data in bs_h_week.items():
        n_games = len(data.get('games', []))
        if n_games < MIN_GAMES:
            continue
        expected_fpg = (rh3_map.get(nk) or {}).get('per_game') or 0
        if expected_fpg <= 0.5:
            continue  # skip edge cases: IL'd proj, brand-new call-up, etc.
        actual_fpg = data['fp'] / n_games
        ratio = max(0.50, min(2.00, actual_fpg / expected_fpg))
        result[nk] = round(1.0 + LAMBDA * (ratio - 1.0), 4)

    # SP / RP momentum from bs_week (same λ, same canonical key)
    if bs_week and rp3_map:
        for nk, data in bs_week.items():
            n_starts = len(data.get('starts', []))
            if n_starts < MIN_GAMES:
                continue
            expected = (rp3_map.get(nk) or {}).get('per_start') or 0
            if expected <= 0.5:
                continue
            actual = data['fp'] / n_starts
            ratio = max(0.50, min(2.00, actual / expected))
            result[nk] = round(1.0 + LAMBDA * (ratio - 1.0), 4)

    return result


# Canonical IL statuses across ESPN. Any of these = IL'd; must be excluded
# from pickup/streamer/add suggestions. DAY_TO_DAY is included paranoidally
# per the user's spec — when in doubt, exclude.
IL_INJURY_STATES = frozenset({
    'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
    'INJURY_RESERVE', 'OUT', 'DAY_TO_DAY',
    'IL10', 'IL15', 'IL60',
})
IL_LINEUP_SLOTS = frozenset({'IL', 'IL10', 'IL15', 'IL60'})

# Slot-aware FP projection (validated 2026-06-03; ΔMAE +19.5 FP/team-period,
# n=80, paired t=4.91). Bench/IL/IR slots accrue ~0 actual FP in the BrownU
# active-only scoring; including them inflates team-total projection by ~20 FP
# and biases gauges/win-prob. See
# `data/research/validation_runs/slot_aware_fp_test_actual.md` and
# `reference_team_variance_aggregation.md` for full evidence.
INACTIVE_LINEUP_SLOTS = frozenset({
    # BE/BENCH intentionally excluded: Josh manages lineup daily, so every
    # healthy bench player will be activated before lock. Only true IL slots
    # and IR should count as non-scoring. DTD/injury zeroing is handled
    # separately inside project_player via injuryStatus — not by slot.
    'IL', 'IL10', 'IL15', 'IL60',
    'IR',
})


def _player_slot(player) -> str:
    slot = getattr(player, 'lineup_slot', None) or getattr(player, 'lineupSlot', None) or ''
    try:
        return str(slot).upper().strip()
    except Exception:
        return ''


def _is_active_slot(player) -> bool:
    """True if the player's lineup_slot is a SCORING (active) slot.

    Active = anything NOT in {BE, IL*, IR}. Defensive: case-insensitive,
    handles IL10/IL15/IL60 variants, BE/BENCH/BN aliases. Note: a player
    can be `injured == True` while still being in an active slot (Langford
    OF, Helsley BE pattern) — that's intentionally OK here. We filter by
    SLOT for the team-total projection (where the player is rostered),
    not by injury status (which is handled separately in project_player
    via IL_STATES → return-date pro-rate).
    """
    if player is None:
        return False
    return _player_slot(player) not in INACTIVE_LINEUP_SLOTS


def is_il_player(player) -> bool:
    """Paranoid IL check — TRUE if a player should be excluded from any
    'add this player' / streamer / pickup suggestion.

    Checks both ESPN `injuryStatus` (the canonical health state) AND the
    `lineup_slot` (a roster might park an IL'd player in BE without
    flipping their injury status). Either signal trips this filter.
    """
    if player is None:
        return False
    inj = (getattr(player, 'injuryStatus', None) or 'ACTIVE')
    try:
        inj = str(inj).upper()
    except Exception:
        inj = 'ACTIVE'
    if inj in IL_INJURY_STATES:
        return True
    slot = getattr(player, 'lineup_slot', None) or getattr(player, 'lineupSlot', None) or ''
    try:
        slot = str(slot).upper()
    except Exception:
        slot = ''
    if slot in IL_LINEUP_SLOTS:
        return True
    return False


def player_link(name: str, *, mlbam: Optional[int] = None) -> str:
    """Return HTML for a clickable player name that drills into profiles.

    Profiles dashboard uses an internal #-hash router; it doesn't currently
    accept ?player= query params (TODO upstream). We pass BOTH a query
    hint and a hash — the page loads cleanly with the current hash routes,
    and a future profiles-side handler can read the query hint to auto-
    open the player modal. Until then this functions as a graceful nav
    link straight to the profiles dashboard.
    """
    nm = h(name or '')
    if not nm:
        return ''
    href = 'player_profiles.html'
    if mlbam:
        href += f'?player={int(mlbam)}#player={int(mlbam)}'
    else:
        # URL-encode minimal — strip any quote chars.
        nm_q = (name or '').replace('"', '').replace("'", '')
        from urllib.parse import quote
        href += f'?name={quote(nm_q)}'
    return f'<a class="player-link" href="{href}" target="_blank" rel="noopener" title="Open in Profiles">{nm}</a>'

USER_AGENT = 'Mozilla/5.0 (matchup-dashboard)'
SEASON_END = date(2026, 9, 28)

# SP start cap per BrownU rules — single source of truth is cap_math.SP_CAP.
# MAX_SP_STARTS_PER_WEEK is the DEFAULT (single-week) cap; the live cap for the
# CURRENT matchup period is resolved period-aware via the shared period_meta
# resolver (ASG period 15 → 16, 2-week playoff round → 20) — see main().
from plv_clone.cap_math import SP_CAP as MAX_SP_STARTS_PER_WEEK  # noqa: E402
from scripts.xfp.lib.period_meta import (  # noqa: E402
    resolve_period_meta, espn_period_meta,
)


def derive_projection_window(league, period, today):
    """Period-TRUE projection window for the dashboard (fix 2026-07-30).

    The window used to be hardcoded to the ISO calendar week of ``today``
    (Mon .. Mon+6) — one week, always — while only the CAP was period-aware.
    Multi-week periods exist (the 2026 ASG block, period 15 = Jul 6–19; 2-week
    playoff rounds), and the one-week window truncated every projection for
    them: the period-15 07-06 build projected 322/383 against finals of
    552/581 (+230/+198 FP) purely from the missing second week
    (``pwin_mean_bias_2026-07-30.md`` §5). ``resolve_period_meta`` already
    returns the true span — ``leverage_engine.build_state`` consumes it
    directly — so this seam does the same and is what ``main()`` calls.

    Returns ``(week_start, week_end, days_remaining_after_today, pmeta)``.
    For a standard single-week period this is byte-identical to the old
    Mon–Sun derivation. ``days_remaining_after_today`` is clamped at 0 so a
    stale build (ESPN period not yet rolled past an override window's end)
    reports 0 days rather than a negative count.
    """
    pmeta = resolve_period_meta(league, period, today=today)
    week_start, week_end = pmeta['week_start'], pmeta['week_end']
    return week_start, week_end, max(0, (week_end - today).days), pmeta

# League-average per-event FP (for opp factor centering)
LEAGUE_AVG_SP_FP_PER_START = 11.5
LEAGUE_AVG_HITTER_PER_GAME = 2.8

# Per-event variance estimates (for win probability calculation).
# These are now FALLBACKS — when a per-player σ is available in
# xfp_rh3_projections.csv (hitters) or xfp_rp3_projections.csv (SPs),
# the per-player σ is used at the team-aggregate variance step. RPs still
# use the fixed value (no per-RP σ calibrated yet). See
# `reference_team_variance_aggregation.md`.
SIGMA_PER_HITTER_GAME = 3.5  # std dev of hitter daily FP
SIGMA_PER_SP_START = 5.5      # std dev of SP per-start FP
SIGMA_PER_RP_GAME = 2.5       # std dev of RP per-game FP
# Conservative per-start FP for a rostered SP who is making a start but is
# absent from xfp_rp3 (rookies / recent call-ups like Messick & Sasaki 2026).
# ~rp3 overall median (8.8) / data-driven p25 (8.3); keeps their start in the
# cap count + projection instead of silently dropping it.
FALLBACK_SP_PER_START = 8.0

# Rotation-gap predicted starts have ~80% probability of actually occurring
# (confirmed ESPN-probable = 1.0). Applied per-start so a 2-start week with
# one confirmed + one predicted gets the asymmetric discount correctly.
_UNCONFIRMED_START_CONF = 0.80

# Set MATCHUP_LEGACY_SIGMA=1 in env to force old fixed-σ aggregation (for
# before/after comparison). Default: use per-player σ where available.
import os as _os
LEGACY_SIGMA = _os.environ.get('MATCHUP_LEGACY_SIGMA', '0') == '1'
# Fallback PA/started-game when a hitter's lineup_map entry is missing.
# CORRECTED 2026-07-29 from 3.5 to the measured mean PA per STARTED game
# (4.0016, matching plv_clone.matchup_projection's default). The old 3.5 was
# the second half of the hitter-variance bug below: it both understated the
# multiplier AND overrode the corrected default that matchup_projection now
# carries, so leaving it would have held production between the fixed and
# unfixed sigma. Fires only for batters with <3 started games in the trailing
# 21 days, but at worst-case (firing for every hitter) it costs SD(z)
# 1.109 vs 1.045.
LEAGUE_PA_PER_GAME = 4.0016

# Empirical FP outcome σ used to build per-game hitter variance.
#
# *** READ THIS BEFORE TOUCHING THE VARIANCE MATH — the comment that used to
# live here contained the wrong identity and IS the documented root cause of a
# 9.68x variance understatement that shipped 2026-06-03 and survived until
# 2026-07-29. See data/research/validation_runs/hitter_sigma_scale_2026-07-29.md
# and src/plv_clone/matchup_projection.py. ***
#
# The retracted reasoning was: "σ_pa = 0.517 is a per-PA outcome σ, so per-game
# variance ≈ PA_per_game * σ_pa²  ⇒  3.5 * 0.517² ≈ 0.94 FP² (σ ≈ 0.97 FP/g)."
# Both halves are wrong:
#   1. 0.517 is NOT per-PA. build_hitter_sigma_calibration.py:82-83 defines it
#      as the PA-WEIGHTED RMS of the per-GAME-RATE residual. Proof on 245,712
#      batter-games: PA-weighted RMS 0.5170 vs UNWEIGHTED SD of the per-game
#      rate 0.5239 — the same number, so the PA-weighting does not convert units.
#   2. PA/game therefore enters variance QUADRATICALLY, not linearly (a rate
#      times a count is a total; scaling the count scales the total, so the
#      variance scales by the square).
# Ground truth, measured on the production population (2026, canonical fp_h,
# 26,199 started games / 377 batters): within-batter per-game hitter FP SD
# = 3.2502 FP. The old formula produced 0.9672-1.0444 (3.1-3.4x too small,
# 9.7-11.3x in variance); the corrected one gives 3.1138.
# Consequence while it shipped: hitters were ~9% of team σ² instead of ~48%, so
# matchup P(win) was badly overconfident (a logged 0.9896 is really 0.9600).
GLOBAL_SIGMA_PA_FP = 0.517

# Reliever appearance rates by role
RP_APP_RATE = {
    'closer': 0.55, 'setup': 0.40, 'long_low': 0.30,
    'middle': 0.30, 'long': 0.30,
}
DEFAULT_RP_APP_RATE = 0.35

# IL partial-credit fractions when no ESPN return date is known.
# Logic: TEN/FIFTEEN-day DL with unknown return means ESPN hasn't set the date yet,
# which typically happens early in the IL stint — player likely out most of the week.
# SIXTY_DAY / INJURY_RESERVE / OUT: definitively zero.
_IL_PARTIAL_CREDIT = {
    'TEN_DAY_DL': 0.20,
    'FIFTEEN_DAY_DL': 0.10,
    'SIXTY_DAY_DL': 0.0,
    'INJURY_RESERVE': 0.0,
    'OUT': 0.0,
}


def load_rp_appearance_rates(n_days: int = 21) -> dict:
    """Compute per-pitcher RP appearance rates from recent boxscore data.

    Bayesian shrinkage toward role priors so sparse pitchers (just called up,
    just acquired) stay anchored to their role's historical rate.

    ALPHA=8: equivalent to 8 prior-weighted games. With 7 team games available
    (~1 week), this gives ~46% weight to observed data and ~54% to the prior.
    As the parquet accumulates more history the observed rate takes over.

    Returns dict: mlbam_id (int) -> appearance_rate (float)
    """
    ALPHA = 8
    try:
        bp = pd.read_parquet(CACHE / 'boxscore_pitchers.parquet')
    except Exception as e:
        _warn_except('rp_appearance_rates.boxscore', e)
        return {}
    bp['game_date'] = pd.to_datetime(bp['game_date'])
    cutoff = pd.Timestamp.today() - pd.Timedelta(days=n_days)
    bp = bp[bp['game_date'] >= cutoff]
    if len(bp) == 0:
        return {}

    # mlbam_id → role mapping from rprs2
    try:
        rp_df = pd.read_csv(ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv',
                            usecols=['pitcher', 'role_lag1'])
        mlbam_to_role = dict(zip(rp_df['pitcher'].astype(int), rp_df['role_lag1']))
    except Exception as e:
        _warn_except('rp_appearance_rates.role_map', e)
        mlbam_to_role = {}

    appears = bp.groupby(['team_id', 'mlbam_id'])['game_pk'].nunique().reset_index()
    appears.columns = ['team_id', 'mlbam_id', 'n_apps']
    team_games = bp.groupby('team_id')['game_pk'].nunique().reset_index()
    team_games.columns = ['team_id', 'n_team_games']
    rates = appears.merge(team_games, on='team_id')

    rates['role'] = rates['mlbam_id'].map(mlbam_to_role).fillna('middle')
    rates['prior_rate'] = rates['role'].map(RP_APP_RATE).fillna(DEFAULT_RP_APP_RATE)
    rates['app_rate'] = ((rates['n_apps'] + ALPHA * rates['prior_rate'])
                         / (rates['n_team_games'] + ALPHA))
    return dict(zip(rates['mlbam_id'].astype(int), rates['app_rate'].round(4)))


ESPN_TO_MLB_TEAM = {
    'BAL': 110, 'BOS': 111, 'NYY': 147, 'TB': 139, 'TOR': 141,
    'CHW': 145, 'CWS': 145, 'CLE': 114, 'DET': 116, 'KC': 118, 'KCR': 118, 'MIN': 142,
    'HOU': 117, 'LAA': 108, 'OAK': 133, 'ATH': 133, 'SEA': 136, 'TEX': 140,
    'ATL': 144, 'MIA': 146, 'NYM': 121, 'PHI': 143, 'WSH': 120, 'WSN': 120,
    'CHC': 112, 'CIN': 113, 'MIL': 158, 'PIT': 134, 'STL': 138,
    'ARI': 109, 'COL': 115, 'LAD': 119, 'SD': 135, 'SDP': 135, 'SF': 137, 'SFG': 137,
}


from plv_clone.utils.name_match import join_key as _norm  # noqa: E402
# _norm is the canonical order-independent join key (sorted-parts). It now lives
# in name_match.join_key so the ~20 scripts that hand-rolled this share one home.


def _fetch_json(url):
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_matchup():
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    period = league.currentMatchupPeriod
    for bs in league.box_scores(matchup_period=period):
        if bs.home_team and 'Ligers' in bs.home_team.team_name:
            return {'mine': bs.home_team, 'opp': bs.away_team,
                    'my_score': bs.home_score, 'opp_score': bs.away_score,
                    'my_lineup': bs.home_lineup, 'opp_lineup': bs.away_lineup,
                    'period': period, 'league_obj': league}
        if bs.away_team and 'Ligers' in bs.away_team.team_name:
            return {'mine': bs.away_team, 'opp': bs.home_team,
                    'my_score': bs.away_score, 'opp_score': bs.home_score,
                    'my_lineup': bs.away_lineup, 'opp_lineup': bs.home_lineup,
                    'period': period, 'league_obj': league}
    raise RuntimeError('No Ligers matchup found')


# Note: the il_fixed shim selection + freshness guard now live in
# plv_clone.projections.ProjectionStore.rp3(live_il=True).


def load_projections():
    from plv_clone.projections import PROJECTIONS
    rh3 = PROJECTIONS.rh3().drop_duplicates('player_name')
    rh3['nk'] = rh3['player_name'].map(_norm)
    # MA1: per-player sigma. MA2 hitter: rh3.recency_form_gap (xpwOBA delta vs prior).
    rh3_map = {r['nk']: {'per_game': r.get('xfp_rh3_per_game') or 0,
                          'per_pa': r.get('xfp_rh3_per_pa') or 0,
                          'prior_fp_per_pa': r.get('prior_fp_per_pa'),
                          'recency_form_gap': r.get('recency_form_gap'),
                          'sigma': r.get('xfp_rh3_sigma'),
                          # Hetero σ work (2026-06-03): per-PA xwOBA-scale σ with
                          # per-batter dispersion. Falls back to global if missing.
                          'sigma_hetero_pa': r.get('xfp_rh3_sigma_hetero'),
                          'sigma_global_pa': r.get('xfp_rh3_sigma_global'),
                          'sigma_factor': r.get('batter_sigma_factor')}
                for _, r in rh3.iterrows()}

    # Collision-safe hitter lookup: build an id-keyed rh3 from the FULL (un-deduped)
    # projection so a same-name hitter (Max Muncy LAD vs ATH) can be resolved by
    # batter id + team in project_player, not just by name — which drop_duplicates
    # collapses to one row. Module global; read by project_player's hitter branch.
    global _RH3_BY_BATTER
    _RH3_BY_BATTER = {}
    _rh3_full = PROJECTIONS.rh3()
    if 'batter' in _rh3_full.columns:
        for _, r in _rh3_full.iterrows():
            try:
                _bid = int(r['batter'])
            except (TypeError, ValueError):
                continue
            _RH3_BY_BATTER[_bid] = {
                'per_game': r.get('xfp_rh3_per_game') or 0,
                'per_pa': r.get('xfp_rh3_per_pa') or 0,
                'prior_fp_per_pa': r.get('prior_fp_per_pa'),
                'recency_form_gap': r.get('recency_form_gap'),
                'sigma': r.get('xfp_rh3_sigma'),
                'sigma_hetero_pa': r.get('xfp_rh3_sigma_hetero'),
                'sigma_global_pa': r.get('xfp_rh3_sigma_global'),
                'sigma_factor': r.get('batter_sigma_factor'),
            }

    rp3 = PROJECTIONS.rp3(live_il=True).drop_duplicates('player_name')
    rp3['nk'] = rp3['player_name'].map(_norm)
    rp3_map = {r['nk']: {'per_start': r.get('xfp_rp3_per_start') or 0,
                          'per_start_sched': r.get('xfp_rp3_per_start_sched') or 0,
                          'sigma': r.get('xfp_rp3_sigma')}
                for _, r in rp3.iterrows()}
    # mlbam → rp3 lookup (for opposing-SP factor)
    sp_id = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv',
                          usecols=['pitcher', 'player_name']).drop_duplicates('player_name')
    sp_id['nk'] = sp_id['player_name'].map(_norm)
    rp3_by_mlbam = {}
    for _, r in sp_id.iterrows():
        rp_info = rp3_map.get(r['nk'])
        if rp_info and rp_info['per_start']:
            rp3_by_mlbam[int(r['pitcher'])] = rp_info

    rprs2 = PROJECTIONS.rprs2().drop_duplicates('name_api')
    rprs2['nk'] = rprs2['name_api'].map(_norm)
    # MA1: derive sigma from quantiles. σ ≈ (p75 - p25) / 1.35 (standard normal IQR identity)
    # GUARD (2026-07-30, rp_band_crps study §6): 5 of 347 published rprs2 rows
    # carry p75 < p25 (deep-negative xfp_ros scrubs), so the unguarded identity
    # yields a NEGATIVE sigma — which is truthy, survives every downstream
    # `rp_info.get('sigma') or FALLBACK`, and ends up clamped into a degenerate
    # point mass sold as a distribution. A corrupt band is a MISSING band: emit
    # None so consumers take their documented fallback, and say so out loud.
    rprs2_map = {}
    _bad_band = []
    for _, r in rprs2.iterrows():
        p25 = r.get('xfp_p25'); p75 = r.get('xfp_p75')
        sigma = (p75 - p25) / 1.35 if (pd.notna(p25) and pd.notna(p75)) else None
        if sigma is not None and sigma <= 0:
            _bad_band.append(str(r.get('name_api') or r.get('player_name') or '?'))
            sigma = None
        rprs2_map[r['nk']] = {'xfp_ros': r.get('xfp_ros') or 0,
                              'xfp_full_year': r.get('xfp_full_year') or 0,
                              'role': r.get('role_lag1') or 'middle',
                              'sigma': sigma,
                              'mlbam': int(r['pitcher']) if pd.notna(r.get('pitcher')) else None}
    if _bad_band:
        print(f'  ⚠ rprs2 band corrupt (p75 <= p25) for {len(_bad_band)} row(s) — '
              f'sigma set to None (consumers use their fallback): '
              f'{", ".join(sorted(_bad_band))}')

    team_strength = pd.read_csv(CACHE / 'team_strength_2026.csv')
    team_strength['team'] = team_strength['team'].str.upper()
    ts_map = team_strength.set_index('team')[['bat_index', 'pit_index']].to_dict('index')

    return rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map


def load_live_blend_map():
    """Phase 3 Agent 3: optional live within-season blend projection.

    Returns dict[mlbam_id] -> {'value': float, 'lo': float, 'hi': float, 'ptype': str}.
    Empty dict if the file is missing — surfacing is purely additive, callers
    must tolerate a missing key.
    """
    path = OUT / 'live_blend_xfp_latest.csv'
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception as e:
        _warn_except('live_blend_map', e)
        return {}
    out = {}
    for _, r in df.iterrows():
        try:
            mid = int(r['mlbam_id'])
        except Exception as e:
            _warn_except('live_blend_map.row', e)
            continue
        out[mid] = {
            'value': float(r['live_blend_xfp']) if pd.notna(r['live_blend_xfp']) else None,
            'lo': float(r['ci_lower']) if pd.notna(r['ci_lower']) else None,
            'hi': float(r['ci_upper']) if pd.notna(r['ci_upper']) else None,
            'ptype': r.get('player_type'),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# MA2-MA6 adjuster data loaders + helpers
# ─────────────────────────────────────────────────────────────────────────────
def _safe_csv(path, **kw):
    try: return pd.read_csv(path, **kw)
    except Exception: return None


def load_recent_form_maps():
    """MA2 — Rolling 21d / season ratios for hitters + SPs.

    Returns (hitter_form_map, sp_form_map): mlbam_id → factor in [0.85, 1.15]
    (Rolling data is keyed on MLBAM, not name.)
    """
    hitter_form, sp_form = {}, {}

    # Hitters: keyed on `batter` MLBAM ID. Use core_fp_per_pa as the rate.
    rh = _safe_csv(CACHE / 'rolling_hitters_2018_2026.csv')
    if rh is not None and 'batter' in rh.columns:
        if 'year' in rh.columns:
            rh = rh[rh['year'] == rh['year'].max()]
        if 'split_day' in rh.columns:
            rh = rh.sort_values('split_day').drop_duplicates('batter', keep='last')
        for _, r in rh.iterrows():
            l21 = r.get('core_fp_per_pa_last21')
            tot = r.get('core_fp_per_pa_to')
            pa_last21 = r.get('pa_last21', 0) or 0
            if pd.notna(l21) and pd.notna(tot) and tot > 0 and pa_last21 >= 30:
                factor = max(0.85, min(1.15, l21 / tot))
                hitter_form[int(r['batter'])] = factor

    # SPs: keyed on `pitcher` MLBAM ID
    rp = _safe_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
    if rp is not None and 'pitcher' in rp.columns:
        if 'year' in rp.columns:
            rp = rp[rp['year'] == rp['year'].max()]
        if 'split_day' in rp.columns:
            rp = rp.sort_values('split_day').drop_duplicates('pitcher', keep='last')
        for _, r in rp.iterrows():
            l21 = r.get('fp_per_start_last21')
            tot = r.get('fp_per_start_to')
            gs_last21 = r.get('gs_last21', 0) or 0
            if pd.notna(l21) and pd.notna(tot) and tot > 0 and gs_last21 >= 2:
                factor = max(0.85, min(1.15, l21 / tot))
                sp_form[int(r['pitcher'])] = factor

    return hitter_form, sp_form


def load_lineup_map():
    """MA3+MA7 — per-batter modal lineup spot + PA/game with RECENCY WEIGHTING.

    Last 7 games weighted ×2 vs games 8-21d ago (#7). This catches recent
    demotions/promotions faster than flat L21d modal.
    """
    parq = CACHE / 'hitter_lineup_appearances_2026.parquet'
    try:
        df = pd.read_parquet(parq)
    except Exception as e:
        _warn_except('lineup_map', e)
        return {}
    today = _today_et()
    cutoff_21 = today - timedelta(days=21)
    cutoff_7 = today - timedelta(days=7)
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df = df[df['game_date'] >= cutoff_21]
    out = {}
    for batter, sub in df.groupby('batter'):
        starts = sub[sub['started_game'] == True]
        if len(starts) < 3:
            continue
        # Recency weighting: last-7d games count 2x
        starts = starts.copy()
        starts['_w'] = starts['game_date'].apply(lambda d: 2.0 if d >= cutoff_7 else 1.0)
        # Weighted modal lineup spot
        spots = starts.dropna(subset=['lineup_spot'])
        if len(spots):
            spot_counts = spots.groupby('lineup_spot')['_w'].sum().sort_values(ascending=False)
            modal_spot = int(spot_counts.index[0])
        else:
            modal_spot = None
        # Weighted mean PA/g
        pa_per_g = float((starts['pa_in_game'] * starts['_w']).sum() / starts['_w'].sum())
        out[int(batter)] = {'modal_spot': modal_spot, 'pa_per_g': pa_per_g}
    return out


def lineup_spot_factor(modal_spot, pa_per_g):
    """MA3 — lineup-spot + PA-volume multiplier.

    rh3 builds `xfp_rh3_per_game` from `per_pa * PA_PER_GAME_LEAGUE` where the
    constant is 3.5. Per-player PA / 3.5 corrects rh3's flat assumption.
    Clamp widened to [0.70, 1.40] after audit (24/428 hitters at 1.30 ceiling,
    p99 factor was 1.37 — clamp was truncating legit elite-leadoff hitters).
    """
    LEAGUE_PA = 3.5
    pa_factor = (pa_per_g or LEAGUE_PA) / LEAGUE_PA
    spot_bonus = 0.0
    if modal_spot in (1, 2): spot_bonus = 0.03
    elif modal_spot == 3: spot_bonus = 0.02
    elif modal_spot == 4: spot_bonus = 0.03
    elif modal_spot == 5: spot_bonus = 0.01
    elif modal_spot in (7, 8, 9): spot_bonus = -0.02
    return max(0.70, min(1.40, pa_factor * (1 + spot_bonus)))


def load_park_factors():
    """MA4 DROPPED (#5). Trivial impact (±0.1 FP) and park_factors.csv is
    minimal. Stub returns empty so _PARK stays empty if anyone references it."""
    return {}


def load_pitcher_splits():
    """MA5 — pitcher mlbam → {p_throws, xwoba_vs_L, xwoba_vs_R}."""
    df = _safe_csv(CACHE / 'pitcher_splits.csv')
    if df is None or 'pitcher' not in df.columns: return {}
    if 'year' in df.columns:
        df = df[df['year'] == df['year'].max()]
    return df.set_index('pitcher')[['p_throws', 'xwoba_vs_L', 'xwoba_vs_R']].to_dict('index')


def load_bat_side_map():
    """MA5 helper — batter mlbam → 'L' | 'R' | 'S' (modal stance).

    ESPN player objects don't expose handedness. Derive from Statcast 2026
    `stand` column (modal per batter). Switch hitters get 'S' (could refine
    later by checking opposing pitcher hand, but most platoon math uses
    'L'/'R' so we'd treat S→opposite-of-pitcher).
    """
    parq = CACHE / 'statcast_2026.parquet'
    if not parq.exists(): return {}
    try:
        import duckdb
        con = duckdb.connect()
        df = con.execute(f"""
            SELECT batter, stand, COUNT(*) n
            FROM read_parquet('{parq}')
            WHERE batter IS NOT NULL AND stand IS NOT NULL
            GROUP BY batter, stand
        """).df()
        # Modal stand per batter
        df = df.sort_values('n', ascending=False).drop_duplicates('batter', keep='first')
        return df.set_index('batter')['stand'].to_dict()
    except Exception as e:
        _warn_except('bat_side_map', e)
        return {}


def load_il_returns(mu):
    """MA6 #10 — cache IL'd player → return_date map upstream.

    `player.returnDate` is unreliable (often None even when ESPN has it).
    Call `get_injury_details()` for all IL'd lineup players once at startup,
    cache return_date by player_id.
    """
    try:
        from plv_clone.league_state import LeagueState as _LS_inj
        get_injury_details = _LS_inj().injury_details
    except Exception as e:
        _warn_except('il_returns.league_state', e)
        return {}
    il_ids = []
    for p in (mu.get('my_lineup') or []) + (mu.get('opp_lineup') or []):
        inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
        if inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE', 'OUT'):
            pid = getattr(p, 'playerId', None)
            if pid: il_ids.append(int(pid))
    if not il_ids: return {}
    try:
        details = get_injury_details(il_ids)
    except Exception as e:
        print(f'  ⚠ get_injury_details failed: {e}')
        return {}
    out = {}
    for _, r in details.iterrows():
        rd = r.get('return_date')
        if pd.notna(rd):
            try: out[int(r['player_id'])] = date.fromisoformat(str(rd)[:10])
            except Exception: pass
    return out


def load_calibration_scalar():
    """MA7 — read MA0's calibration JSON. Returns 1.0 if not available.

    NOTE: only consume the scalar once MA0 was re-fit using POST-adjuster
    projections. The first MA0 fit (against pre-adjuster Period 7) is
    stale once MA1-MA6 are live — applying it would double-correct.
    The calibration JSON includes a `safe_to_consume` flag set by the
    re-fit step; if absent or false, return 1.0.
    """
    path = ROOT / 'data' / 'models' / 'matchup_calibration.json'
    try:
        import json
        d = json.loads(path.read_text())
        if not d.get('safe_to_consume', False):
            return 1.0
        return float(d['scalar_correction'])
    except Exception as e:
        _warn_except('calibration_scalar', e)
        return 1.0


# Adjuster data is no longer module-global state — it's bundled into a frozen
# matchup_projection.Adjusters value in main() and threaded into project_player
# (R2-1). The one remaining module cache is the collision-safe hitter lookup,
# populated by load_projections().
_RH3_BY_BATTER = {}          # batter mlbam → rh3 info; collision-safe hitter lookup (Max Muncy LAD vs ATH)
LEAGUE_AVG_XWOBA = 0.310     # MA5 platoon normalization

# Scalar knobs for the deep matchup_projection core, sourced from the dashboard
# constants above so they stay single-source. project_player passes this in.
_MCFG = _mproj.MatchupConfig(
    league_avg_sp_fp_per_start=LEAGUE_AVG_SP_FP_PER_START,
    league_avg_xwoba=LEAGUE_AVG_XWOBA,
    unconfirmed_start_conf=_UNCONFIRMED_START_CONF,
    default_rp_app_rate=DEFAULT_RP_APP_RATE,
    sigma_per_sp_start=SIGMA_PER_SP_START,
    sigma_per_rp_game=SIGMA_PER_RP_GAME,
    sigma_per_hitter_game=SIGMA_PER_HITTER_GAME,
    global_sigma_pa_fp=GLOBAL_SIGMA_PA_FP,
    league_pa_per_game=LEAGUE_PA_PER_GAME,
)


def fetch_espn_week_schedule(league, week_start, week_end):
    """Pull team game schedules from ESPN's proGamesByScoringPeriod.

    Replaces the old MLB Stats API team-schedule call with ESPN's own
    authoritative game calendar.  This makes the dashboard's team-game-day
    counts match exactly what ESPN shows in their UI (since it's the same
    source), and eliminates the separate MLB Stats API schedule fetch.

    Probable-pitcher fields (my_probable_id / opp_probable_id) are left None
    here; they are filled in later by build_sp_starts_by_pitcher via
    fetch_week_probables (MLB Stats API).

    Returns: {mlb_team_id: [game_dict, …]} — same shape as the old
    fetch_schedules_by_team so all downstream code is unchanged.
    """
    try:
        raw = league.espn_request.get_pro_schedule()
    except Exception as e:
        _warn_except('espn_week_schedule', e)
        return {}

    # ESPN internal team_id → uppercase abbreviation  (e.g. 11 → 'ATH')
    espn_id_to_abbr: dict[int, str] = {}
    for team in raw.get('settings', {}).get('proTeams', []):
        if team['id'] != 0:
            espn_id_to_abbr[team['id']] = team.get('abbrev', '').upper()

    # abbrev → MLB Stats API team_id (for keying the returned dict)
    abbr_to_mlb = ESPN_TO_MLB_TEAM  # defined at module level

    by_mlb: dict[int, list] = {}
    for team in raw.get('settings', {}).get('proTeams', []):
        espn_id = team['id']
        if espn_id == 0:
            continue
        abbr = espn_id_to_abbr.get(espn_id, '')
        mlb_id = abbr_to_mlb.get(abbr)
        if mlb_id is None:
            continue

        games = []
        for _sp, game_list in team.get('proGamesByScoringPeriod', {}).items():
            for g in game_list:
                cal = date.fromtimestamp(g['date'] / 1000)
                if not (week_start <= cal <= week_end):
                    continue
                home_id = g['homeProTeamId']
                away_id = g['awayProTeamId']
                is_home = (espn_id == home_id)
                opp_espn_id = away_id if is_home else home_id
                opp_abbr = espn_id_to_abbr.get(opp_espn_id, '?')
                # ESPN -> MLB StatsAPI abbr normalization (audit 2026-07-04):
                # downstream ts_map / pf_map are keyed on MLB abbrs, so an
                # un-normalized 'ARI'/'CHW'/'OAK' silently reads neutral 1.0.
                _E2M = {'ARI': 'AZ', 'CHW': 'CWS', 'OAK': 'ATH', 'WSN': 'WSH',
                        'KCR': 'KC', 'TBR': 'TB', 'SFG': 'SF', 'SDP': 'SD'}
                opp_abbr = _E2M.get(opp_abbr, opp_abbr)
                games.append({
                    'date': cal.isoformat(),
                    'is_home': is_home,
                    'opp_team': opp_abbr,
                    # Probable pitcher fields filled in later by fetch_week_probables
                    'my_probable_id': None,
                    'my_probable_name': None,
                    'opp_probable_id': None,
                    'opp_probable_name': None,
                })
        if games:
            # Sort chronologically; deduplicate (ESPN may list doubleheaders twice)
            seen = set()
            uniq = []
            for g in sorted(games, key=lambda x: x['date']):
                key = (g['date'], g['opp_team'])
                if key not in seen:
                    seen.add(key)
                    uniq.append(g)
            by_mlb[mlb_id] = uniq

    return by_mlb


def fetch_schedules_by_team(team_ids, start_date, end_date):
    """Fallback MLB Stats API schedule fetch (used only when ESPN schedule unavailable).

    The primary path is fetch_espn_week_schedule().  This function is kept as a
    fallback and for the SP probable-pitcher overlay inside build_sp_starts_by_pitcher.

    Returns a dict keyed by MLB team_id; missing teams default to empty list
    on lookup downstream.

    Dates are the schedule BLOCK date (the actual ET game day), NOT
    gameDate[:10] — that is a UTC instant which rolls to TOMORROW for evening-ET
    first pitches, pushing a period's final-day starts outside the cap window.
    Fixed 2026-07-27 (#10) together with the two matching sites in
    `plv_clone.mlb_stats.fetch_week_probables`; all three must stay on the same
    calendar, because `build_sp_starts_by_pitcher` joins probables to this
    schedule on (pitcher, date) and a split convention silently misses.
    """
    url = (f'https://statsapi.mlb.com/api/v1/schedule?sportId=1'
           f'&startDate={start_date}&endDate={end_date}'
           f'&hydrate=probablePitcher,team')
    try:
        data = _fetch_json(url)
    except Exception as e:
        _warn_except('mlb_schedule_fallback', e)
        return {tid: [] for tid in team_ids}
    by_team = {tid: [] for tid in team_ids}
    for d_block in data.get('dates', []):
        for g in d_block.get('games', []):
            home = g['teams']['home']
            away = g['teams']['away']
            home_id = home['team']['id']
            away_id = away['team']['id']
            home_p = home.get('probablePitcher', {}) or {}
            away_p = away.get('probablePitcher', {}) or {}
            date_s = d_block['date']
            home_abbr = home['team'].get('abbreviation', '?').upper()
            away_abbr = away['team'].get('abbreviation', '?').upper()
            if home_id in by_team:
                by_team[home_id].append({
                    'date': date_s,
                    'is_home': True,
                    'opp_team': away_abbr,
                    'my_probable_id': home_p.get('id'),
                    'my_probable_name': home_p.get('fullName'),
                    'opp_probable_id': away_p.get('id'),
                    'opp_probable_name': away_p.get('fullName'),
                })
            if away_id in by_team:
                by_team[away_id].append({
                    'date': date_s,
                    'is_home': False,
                    'opp_team': home_abbr,
                    'my_probable_id': away_p.get('id'),
                    'my_probable_name': away_p.get('fullName'),
                    'opp_probable_id': home_p.get('id'),
                    'opp_probable_name': home_p.get('fullName'),
                })
    return by_team


def player_mlbam_lookup(name, cache={}):
    if not cache:
        for csv, col in [(CACHE / 'hitters_multiyr_2015_2026.csv', 'batter'),
                          (CACHE / 'sp_multiyr_2015_2025.csv', 'pitcher'),
                          (CACHE / 'relievers_multiyr_2018_2026.csv', 'pitcher')]:
            try:
                cols = pd.read_csv(csv, nrows=1).columns.tolist()
                ncol = 'player_name' if 'player_name' in cols else 'name'
                df = pd.read_csv(csv, usecols=[col, ncol])
                df['_nk'] = df[ncol].map(_norm)
                for _, r in df.drop_duplicates('_nk').iterrows():
                    cache.setdefault(r['_nk'], int(r[col]))
            except Exception as e:
                _warn_except('mlbam_csv_cache', e)
    return cache.get(_norm(name))


def _resolve_mlbam_via_api(name, cache={}):
    """Fallback MLBAM resolution when player not in cached multi-year CSVs.

    Thin wrapper around `plv_clone.mlb_stats.resolve_mlbam` that retains the
    in-process per-name cache so repeated lookups don't re-hit the API.
    """
    if name in cache:
        return cache[name]
    try:
        result = resolve_mlbam([name])
    except Exception as e:
        _warn_except('resolve_mlbam_api', e)
        result = {}
    pid = result.get(name)
    cache[name] = pid
    return pid


def _pitcher_mlbam_lookup(name, cache={}):
    """Pitcher-ONLY name cache (sp_multiyr + relievers CSVs), consulted BEFORE
    the mixed player_mlbam_lookup cache. That mixed cache loads the HITTER csv
    first and setdefault ties go to whoever loads first — canonical bug
    (found 2026-07-11): SP Eury Pérez (691587) resolved to the retired OF
    Eury Pérez (516811), silently zeroing his projected starts. The pitcher
    CSVs also store "Last, First" names, so this cache indexes BOTH name
    orders; same-name pitcher pairs are handled upstream by the
    KNOWN_PITCHER_COLLISIONS branch."""
    if not cache:
        for csv, col in [(CACHE / 'sp_multiyr_2015_2025.csv', 'pitcher'),
                         (CACHE / 'relievers_multiyr_2018_2026.csv', 'pitcher')]:
            try:
                cols = pd.read_csv(csv, nrows=1).columns.tolist()
                ncol = 'player_name' if 'player_name' in cols else 'name'
                df = pd.read_csv(csv, usecols=[col, ncol])
                # _norm is name_match.join_key (order-independent), so the
                # 'Last, First' spelling already keys identically to
                # 'First Last' — no hand-rolled flip needed (audit item 9).
                for _, r in df.drop_duplicates(ncol).iterrows():
                    cache.setdefault(_norm(str(r[ncol])), int(r[col]))
            except Exception as e:
                _warn_except('pitcher_mlbam_csv_cache', e)
    return cache.get(_norm(name))


def _resolve_pitcher_mlbam(name, *, team=None, role=None):
    """Collision-safe pitcher name → MLBAM id — the single seam for resolving a
    rostered/FA pitcher's id in this module (mirrors the hitter collision guard
    in project_player).

    For a same-name pitcher (KNOWN_PITCHER_COLLISIONS, e.g. the two Logan Allens)
    disambiguate via resolve_id(team=...) BEFORE the name-based lookups, which
    would otherwise grab whichever same-name row landed in the cache first.
    Then the pitcher-only cache, then the mixed cache, then the API.
    """
    if name in _KNOWN_PITCHER_COLLISIONS:
        pid = resolve_id(name, kind='pitcher', team=(team or None), role=role)
        if pid is not None:
            return int(pid)
    return (_pitcher_mlbam_lookup(name) or player_mlbam_lookup(name)
            or _resolve_mlbam_via_api(name))


def build_sp_starts_by_pitcher(pitcher_ids, schedules_by_team, today, week_end):
    """Adapter — call `fetch_week_probables` once and reshape the result into
    `{mlbam: [game_dict]}` matching the original SP-start payload shape.

    Each game_dict carries the same keys the dashboard's downstream rendering
    consumes: `date`, `opp_team`, `is_home`, `my_probable_id`,
    `my_probable_name`, `opp_probable_id`, `opp_probable_name`, `confirmed`.

    The schedule data already in `schedules_by_team` is the source of truth
    for per-day team-game info (is_home, opp_probable_*). We look up each
    (pid, date) returned by `fetch_week_probables` against the pitcher's
    team-day schedule to recover those fields. `confirmed` is True when the
    pitcher matched as the listed probable; False when the start came from
    rotation-gap prediction.
    """
    pid_set = {int(p) for p in pitcher_ids if p}
    if not pid_set:
        return {}
    week_start = today  # fetch_week_probables semantic: window starts here
    try:
        wp = fetch_week_probables(
            week_start=week_start, week_end=week_end,
            pitcher_ids=pid_set,
        )
    except Exception as e:
        _warn_except('week_probables', e)
        return {pid: [] for pid in pid_set}

    # Index team schedules by date for quick per-pitcher lookup. The pitcher's
    # team_id is recoverable from any confirmed game in the schedule (or — for
    # pitchers with no confirmed in-window — from the start dates themselves,
    # which fetch_week_probables resolved via the /people endpoint fallback).
    team_by_date_lookup = {}  # team_id -> {date_str: game_dict}
    for tid, games in schedules_by_team.items():
        team_by_date_lookup[tid] = {g['date']: g for g in games}

    # Pre-compute: pitcher_id -> team_id.
    # Primary: scan schedules (ESPN-sourced) for teams with the pitcher's opp on the right day.
    # Fallback: use the mlbam → MLB team mapping from the schedule.
    pid_to_team = {}
    # Try matching via opp_team abbreviation on dates where we know the start
    for (pid, start_date), opp_abbr in wp.starts.items():
        date_s = start_date.isoformat()
        for tid, games in schedules_by_team.items():
            for g in games:
                if g['date'] == date_s and g['opp_team'].upper() == opp_abbr.upper():
                    pid_to_team.setdefault(pid, tid)
                    break
            if pid in pid_to_team:
                break

    starts_by_pid = {pid: [] for pid in pid_set}
    for (pid, start_date), opp_abbr in wp.starts.items():
        date_s = start_date.isoformat()
        # Confirmed iff this (pid, date) key was in MLB's confirmed-probable list.
        # This is authoritative regardless of schedule source (ESPN vs MLB Stats API).
        confirmed = (pid, start_date) in wp.confirmed_keys

        # Find which team this pitcher plays for so we can fetch is_home, etc.
        tid = pid_to_team.get(pid)
        game_meta = None
        if tid is not None:
            game_meta = team_by_date_lookup.get(tid, {}).get(date_s)
            # ±1 day tolerance for matching the team game (mirrors mlb_stats'
            # prediction tolerance).
            if game_meta is None:
                for offset in (1, -1):
                    alt = (start_date + timedelta(days=offset)).isoformat()
                    cand = team_by_date_lookup.get(tid, {}).get(alt)
                    if cand and cand.get('opp_team', '').upper() == opp_abbr.upper():
                        game_meta = cand
                        date_s = alt  # use the matched team-game date
                        break
        if game_meta:
            starts_by_pid[pid].append({
                'date': date_s,
                'opp_team': game_meta['opp_team'],
                'is_home': game_meta['is_home'],
                'my_probable_id': pid,
                'my_probable_name': ('(probable)' if confirmed else '(predicted)'),
                'opp_probable_id': game_meta.get('opp_probable_id'),
                'opp_probable_name': game_meta.get('opp_probable_name'),
                'confirmed': confirmed,
            })
        else:
            # No matching team-day record (pitcher's team wasn't fetched, or
            # the date drifted). Emit a stub so downstream SP cap math still
            # sees the start; opp_probable lookups fall back to defaults.
            starts_by_pid[pid].append({
                'date': date_s,
                'opp_team': opp_abbr.upper(),
                'is_home': True,
                'my_probable_id': pid,
                'my_probable_name': '(predicted)',
                'opp_probable_id': None,
                'opp_probable_name': None,
                'confirmed': False,
            })
    # Sort each pitcher's starts chronologically (matches old confirmed+predicted order).
    for pid in starts_by_pid:
        starts_by_pid[pid].sort(key=lambda s: s['date'])
    return starts_by_pid


def project_player(player, schedules_by_team, sp_starts_by_pitcher, rh3_map,
                     rp3_map, rp3_by_mlbam, rprs2_map, ts_map, today, week_end,
                     adj=None):
    """Schedule + opp + role aware projection. Returns dict with fp, units,
       per-game/start breakdown, sigma_total, and any badges.

       `adj` is the frozen Adjusters value (form/lineup/platoon/IL/calib/
       momentum maps + toggles). Defaults to neutral so a missing adjuster
       set yields the baseline xfp projection."""
    if adj is None:
        adj = _mproj.Adjusters.neutral()
    name, pos = player.name, (player.position or '?')
    nk = _norm(name)
    team = (player.proTeam or '').upper()
    mlb_id = ESPN_TO_MLB_TEAM.get(team)
    out = {'fp': 0.0, 'units': 0, 'breakdown': [], 'sigma2': 0.0, 'badges': []}
    if mlb_id is None: return out
    games = schedules_by_team.get(mlb_id, [])
    today_s = today.isoformat()
    week_end_s = week_end.isoformat()
    # Include TODAY in remaining-week projection (fix: was `today_s <` strict).
    # WTD score from ESPN reflects only what's been scored at build time, so
    # today's confirmed starts must contribute to the rest-of-week projection.
    rem = [g for g in games if today_s <= g['date'] <= week_end_s]

    # MA6 — IL-window pro-rate. #10: prefer upstream-cached _IL_RETURNS map
    # (built from get_injury_details()) since `player.returnDate` is usually None.
    # IL audit: skip is UNCONDITIONAL (not gated on _ADJUSTERS_ON) — an IL'd
    # player must not be projected for any games/starts they cannot play.
    # If no return date is known, zero them out entirely (no day-of-week
    # heroics; ESPN-confirmed probable starts override this via the SP path
    # in main() which already filters healthy SPs upstream).
    il_factor = 1.0
    inj = (getattr(player, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    IL_STATES = ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
                 'INJURY_RESERVE', 'OUT')
    if inj in IL_STATES:
        pid_for_il = getattr(player, 'playerId', None)
        rd = adj.il_returns.get(pid_for_il) if pid_for_il else None
        if rd is None:
            # fallback to player.returnDate if upstream cache missed
            rd_str = getattr(player, 'returnDate', None) or None
            if rd_str:
                try: rd = date.fromisoformat(str(rd_str)[:10])
                except Exception: rd = None
        if rd is not None:
            if rd <= week_end:
                days_avail = max(0, (week_end - max(rd, today)).days + 1)
                days_total = max(1, (week_end - today).days + 1)
                il_factor = days_avail / days_total
            else:
                return out  # returns after window — zero
        else:
            # No ESPN return date. Apply small partial credit for short-IL types
            # (TEN/FIFTEEN_DAY) because the missing date usually means the IL
            # stint is early and the minimum eligible return may fall this week.
            # SIXTY_DAY / INJURY_RESERVE / OUT → definitively zero.
            partial = _IL_PARTIAL_CREDIT.get(inj, 0.0)
            if partial <= 0.0:
                return out
            il_factor = partial

    # Effective pitcher role (gotcha #8): ESPN .position is stale for dual-
    # eligible pitchers (Detmers: position='RP' but starting). Resolve the real
    # role via MLBAM + gamesStarted so SP starts route here, not the RP branch —
    # and so this matches main()'s sp_pitcher_ids resolution exactly.
    pitch_mlbam = None
    eff_sp = False
    if pos in ('SP', 'RP', 'P'):
        pitch_mlbam = _resolve_pitcher_mlbam(
            name, team=team or None,
            role=(pos if pos in ('SP', 'RP') else None))
        eff_sp = (detect_pitcher_role(player, mlbam_id=int(pitch_mlbam)) == 'SP'
                  if pitch_mlbam else pos == 'SP')

    if eff_sp:
        # Skip only true IL/out — a DAY_TO_DAY pitcher with a scheduled start
        # still pitches (Soriano 2026), so DTD must not zero his starts.
        if inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE',
                   'OUT'):
            return out

        mlbam = pitch_mlbam
        if not mlbam:
            return out  # Can't match without an ID

        # SP starts (confirmed + rotation-gap predictions) come pre-computed
        # via fetch_week_probables → build_sp_starts_by_pitcher in main().
        # Filter to in-window starts.
        all_starts = sp_starts_by_pitcher.get(int(mlbam), [])
        starts = [s for s in all_starts
                  if today_s <= s['date'] <= week_end_s]

        # Collision-safe: for a same-name SP key rp3 by the resolved id, not the
        # shared norm-name key (which would grab whichever Logan Allen loaded first).
        rp_info = {}
        if name in _KNOWN_PITCHER_COLLISIONS and mlbam:
            rp_info = rp3_by_mlbam.get(int(mlbam), {})
        if not rp_info:
            rp_info = rp3_map.get(nk, {})
        if not starts:
            return out
        # Fallback for SPs absent from rp3 (rookies/recent call-ups, e.g.
        # Messick/Sasaki 2026): count the start with a conservative per-start so
        # the cap math + team projection don't silently drop it.
        per_start_base = rp_info.get('per_start') or FALLBACK_SP_PER_START
        if not rp_info.get('per_start'):
            out['badges'].append('≈ est')
        if len(starts) >= 2:
            out['badges'].append('🔥 2-START')

        # MA2 (SP): recent-form factor — gated on adj.ma2_sp_on
        recent_factor = adj.sp_form.get(mlbam, 1.0) if adj.ma2_sp_on else 1.0
        # Within-week momentum (λ=0.15 shrinkage toward neutral) — constant
        # across this pitcher's starts.
        sp_momentum = adj.weekly_momentum.get(nk, 1.0)
        # Per-player σ from xfp_rp3 (per-start FP units). Globally calibrated
        # — currently identical across SPs but still beats the legacy 5.5 FP.
        # Falls back to fixed SIGMA_PER_SP_START if the SP isn't in the projection
        # file (rare — e.g., minor-league call-up not yet in xfp_rp3).
        sp_sigma = SIGMA_PER_SP_START if LEGACY_SIGMA else (rp_info.get('sigma') or SIGMA_PER_SP_START)
        # Adjuster math lives in the deep matchup_projection module (ADR-0001/2):
        # the dashboard assembles per-start context, the module combines it.
        start_ctx = [
            _mproj.SPStartCtx(date=s['date'], opp_team=s['opp_team'],
                              opp_bat_index=ts_map.get(s['opp_team'], {}).get('bat_index'),
                              confirmed=s.get('confirmed', True))
            for s in starts
        ]
        res = _mproj.project_sp_starts(per_start_base, start_ctx,
                                       recent_factor=recent_factor, calib=adj.calib,
                                       momentum=sp_momentum, sigma=sp_sigma,
                                       cfg=_MCFG)
        out['fp'] = res.fp
        out['units'] = res.units
        out['sigma2'] = res.sigma2
        out['breakdown'] = res.breakdown
        return out

    elif pos in ('SP', 'RP', 'P'):
        # Any rostered pitcher not routed to the SP branch above (true RPs, or a
        # former starter now relieving) is projected here via rprs2.
        rp_info = rprs2_map.get(nk, {})
        role = rp_info.get('role') or 'middle'
        rp_mlbam = rp_info.get('mlbam')
        # Use observed appearance rate (Bayesian-shrunk toward role prior) when
        # available; fall back to static role rate for pitchers not in boxscore.
        app_rate = (adj.rp_app_rates.get(int(rp_mlbam), RP_APP_RATE.get(role, DEFAULT_RP_APP_RATE))
                    if rp_mlbam else RP_APP_RATE.get(role, DEFAULT_RP_APP_RATE))
        xfp_ros = rp_info.get('xfp_ros') or 0
        if not xfp_ros or not rem: return out
        # rest_of_season RoS / team games remaining (rough). Appearance-rate
        # scaling, IL pro-rate, calibration, and σ all live in the module.
        days_remaining_season = max((SEASON_END - today).days, 1)
        res = _mproj.project_rp(xfp_ros, len(rem), role=role, app_rate=app_rate,
                                days_remaining_season=days_remaining_season,
                                il_factor=il_factor, calib=adj.calib,
                                rp_sigma=SIGMA_PER_RP_GAME, cfg=_MCFG)
        out['fp'] = res.fp
        out['units'] = res.units
        out['sigma2'] = res.sigma2
        out['breakdown'] = res.breakdown
        return out

    else:  # hitter
        # Collision-safe: a same-name hitter (Max Muncy LAD vs ATH) can't be keyed
        # by name. For KNOWN_COLLISIONS, resolve the batter id via team and use the
        # id-keyed rh3; otherwise the fast name key (behavior-preserving).
        rh = None
        coll_batter_mlbam = None
        if name in _KNOWN_COLLISIONS:
            _bid = resolve_id(name, kind='batter',
                              team=getattr(player, 'proTeam', None) or None,
                              position=pos)
            if _bid is not None:
                rh = _RH3_BY_BATTER.get(int(_bid))
                coll_batter_mlbam = int(_bid)
        if rh is None:
            rh = rh3_map.get(nk, {})
        per_game_base = rh.get('per_game') or 0
        if not per_game_base or not rem: return out

        # MA3: lineup-spot adjuster (uses mlbam → lineup map)
        batter_mlbam = coll_batter_mlbam or player_mlbam_lookup(name)
        # MA2 hitter: use rh3.recency_form_gap directly (#8 — no double-count;
        # rh3 includes the column as display-only, not in features).
        # Gap is xwoba_per_pa_last21_sh - prior_fp_per_pa. Convert to factor.
        if adj.ma2_hitter_on:
            base_pa = rh.get('prior_fp_per_pa') or rh.get('per_pa') or 0
            gap = rh.get('recency_form_gap')
            if gap and base_pa and base_pa > 0:
                recent_factor = max(0.85, min(1.15, 1.0 + gap / base_pa))
            else:
                recent_factor = 1.0
        else:
            recent_factor = 1.0
        lineup_info = adj.lineup.get(batter_mlbam, {}) if batter_mlbam else {}
        lineup_factor = lineup_spot_factor(lineup_info.get('modal_spot'),
                                            lineup_info.get('pa_per_g')) if lineup_info else 1.0

        # MA5 stance resolution (data assembly stays here; switch hitters bat
        # opposite the pitcher's throwing arm). The clamp + combination math
        # live in matchup_projection.
        h_momentum = adj.weekly_momentum.get(nk, 1.0)
        game_ctx = []
        for g in rem:
            opp_sp_id = g.get('opp_probable_id')
            if opp_sp_id and opp_sp_id in rp3_by_mlbam:
                ops = rp3_by_mlbam[opp_sp_id]['per_start']
                tpi = None
            else:
                ops = None
                tpi = ts_map.get(g['opp_team'], {}).get('pit_index') or 1.0
            plat_xwoba = None
            if opp_sp_id and opp_sp_id in adj.psplit and batter_mlbam in adj.bat_side:
                stance = adj.bat_side.get(batter_mlbam, 'R')
                ps = adj.psplit[opp_sp_id]
                if stance == 'S':
                    p_throws = ps.get('p_throws', 'R')
                    stance = 'L' if p_throws == 'R' else 'R'
                if stance in ('L', 'R'):
                    _ox = ps.get(f'xwoba_vs_{stance}')
                    if _ox and _ox > 0:
                        plat_xwoba = _ox
            game_ctx.append(_mproj.HitterGameCtx(
                date=g['date'], opp_team=g['opp_team'],
                opp_probable_name=g.get('opp_probable_name', '?'),
                opp_per_start=ops, team_pit_index=tpi, platoon_xwoba=plat_xwoba))

        pa_per_g = (lineup_info.get('pa_per_g') if lineup_info else None)
        res = _mproj.project_hitter_games(
            per_game_base, game_ctx,
            recent_factor=recent_factor, lineup_factor=lineup_factor,
            il_factor=il_factor, calib=adj.calib, momentum=h_momentum,
            sigma_factor=rh.get('sigma_factor'), pa_per_g=pa_per_g,
            legacy_sigma=LEGACY_SIGMA, cfg=_MCFG)
        out['fp'] = res.fp
        out['units'] = res.units
        out['sigma2'] = res.sigma2
        out['breakdown'] = res.breakdown
        return out


def apply_sp_cap(team_projections, cap=MAX_SP_STARTS_PER_WEEK):
    """Cap SP starts at `cap` per team — zero the lowest-FP starts beyond the
    cap (the bench-your-worst planning rule). The ranking rule itself lives in
    cap_math.cap_excess_starts; this only applies it to the matchup's breakdown
    structure."""
    from plv_clone.cap_math import cap_excess_starts
    sp_starts = []
    for name, proj in team_projections.items():
        for i, b in enumerate(proj.get('breakdown', [])):
            if b.get('type') == 'start':
                sp_starts.append({'name': name, 'idx': i, 'fp': b['fp']})
    excess = cap_excess_starts([s['fp'] for s in sp_starts], cap)
    if not excess:
        return 0
    capped_fp = 0.0
    for j in excess:
        c = sp_starts[j]
        proj = team_projections[c['name']]
        b = proj['breakdown'][c['idx']]
        b['fp_capped'] = True
        b['fp_original'] = b['fp']
        proj['fp'] -= b['fp']
        capped_fp += b['fp']
        b['fp'] = 0
    return capped_fp


def synthesize_action_items(my_proj, my_lineup, schedules_by_team, win_prob,
                            cap=None):
    """Build a TOP-OF-PAGE list of urgent actionables."""
    if cap is None:
        cap = MAX_SP_STARTS_PER_WEEK
    items = []

    # Injuries
    for p in my_lineup:
        inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE')
        slot = getattr(p, 'lineupSlot', '')
        if inj not in ('ACTIVE', 'NORMAL', '') and slot not in ('IL', 'INJURY_RESERVE', 'BE'):
            items.append({'urgency': 'high', 'icon': '🏥',
                           'text': f'{p.name} ({inj}) is in active slot {slot} — consider IL/bench'})

    # Cap status — count confirmed and predicted separately
    n_confirmed = sum(1 for proj in my_proj.values()
                      for b in proj.get('breakdown', [])
                      if b.get('type') == 'start' and b.get('confirmed', True))
    n_predicted = sum(1 for proj in my_proj.values()
                      for b in proj.get('breakdown', [])
                      if b.get('type') == 'start' and not b.get('confirmed', True))
    n_starts = n_confirmed + n_predicted
    pred_s = f' (+{n_predicted} predicted)' if n_predicted else ''
    if n_starts < cap - 3:
        items.append({'urgency': 'med', 'icon': '📉',
                       'text': f'Only {n_confirmed} confirmed starts{pred_s} this week — add a streamer to hit the {cap}-start cap'})

    # Win prob extremes
    if win_prob < 0.40:
        items.append({'urgency': 'high', 'icon': '🚨',
                       'text': f'Trailing scenario — win probability {_fmt_winprob(win_prob)}. Aggressive streaming + lineup tweaks needed.'})
    elif win_prob > 0.85:
        items.append({'urgency': 'low', 'icon': '🟢',
                       'text': f'Strong position — win prob {_fmt_winprob(win_prob)}. Hold steady.'})

    if not items:
        items.append({'urgency': 'low', 'icon': '✅',
                       'text': 'No urgent action items — lineup, cap, and roster look set.'})

    out = ['<div class="action-items"><h3>⚡ Action Items</h3><ul>']
    for it in items[:6]:
        out.append(f'<li class="urgency-{it["urgency"]}">{h(it["icon"])} {h(it["text"])}</li>')
    out.append('</ul></div>')
    return '\n'.join(out)


def _fmt_winprob(win_prob):
    """Headline win-probability DISPLAY string. Caps the extremes so a
    bootstrap 1.000 / 0.000 doesn't read as a broken '100%' / '0%'. Use only
    for headline surfaces (gauge, action items) — history/accuracy tables keep
    the raw value since they're data, not a call."""
    p = win_prob * 100
    if p >= 99.5:
        return '>99%'
    if p <= 0.5:
        return '<1%'
    return f'{p:.0f}%'


def render_win_prob_gauge(win_prob):
    """CSS conic-gradient gauge with prominent display."""
    pct = win_prob * 100
    # Theme-var colors so the gauge tracks light/dark (was hardcoded hexes).
    if pct >= 55: color = 'var(--pos)'
    elif pct >= 45: color = 'var(--warn)'
    else: color = 'var(--neg)'

    return f'''<div class="gauge-wrap">
  <div class="gauge" style="background: conic-gradient({color} 0% {pct}%, var(--faint) {pct}% 100%);">
    <div class="gauge-inner">
      <div class="gauge-pct">{_fmt_winprob(win_prob)}</div>
      <div class="gauge-label">win probability</div>
    </div>
  </div>
</div>'''


def render_ci_bands(my_total, my_sigma2, opp_total, opp_sigma2):
    """Show P25/P75 CI bands around projected total."""
    import math
    my_sd = math.sqrt(my_sigma2)
    opp_sd = math.sqrt(opp_sigma2)
    # 50% CI = ±0.674 sigma
    return (f'<p class="notes">📐 <b>50% confidence intervals</b>: '
            f'Ligers [<b>{my_total - 0.674*my_sd:.1f}</b> – <b>{my_total + 0.674*my_sd:.1f}</b>] '
            f'vs Opp [<b>{opp_total - 0.674*opp_sd:.1f}</b> – <b>{opp_total + 0.674*opp_sd:.1f}</b>]. '
            f'80% CI: ±{1.282*my_sd:.0f} / ±{1.282*opp_sd:.0f} FP respectively.</p>')


def render_days_of_fire(my_proj):
    """7-day FP forecast per top Liger hitter."""
    rows = []
    for name, proj in my_proj.items():
        if not proj.get('breakdown'): continue
        # Hitters only
        if not any(b.get('type') == 'game' for b in proj['breakdown']): continue
        rows.append({
            'name': name,
            'games': [(b['date'], b['fp']) for b in proj['breakdown'] if b.get('type') == 'game'],
            'total': proj['fp'],
        })
    if not rows:
        return ''
    rows.sort(key=lambda r: -r['total'])
    out = ['<h2>🔥 Days of Fire <small class="muted">(per-day projected FP, top Ligers)</small></h2>',
           '<table style="font-size:.85em"><thead><tr><th>Player</th>']
    # collect unique dates
    all_dates = sorted({d for r in rows for d, _ in r['games']})
    for d in all_dates:
        out.append(f'<th>{d[5:]}</th>')
    out.append('<th>Total</th></tr></thead><tbody>')
    for r in rows[:8]:
        out.append(f'<tr><td>{h(r["name"])}</td>')
        date_to_fp = dict(r['games'])
        for d in all_dates:
            fp = date_to_fp.get(d)
            if fp is None:
                out.append('<td class="muted">—</td>')
            else:
                # Heatmap color tied to FP magnitude
                if fp < 0:
                    cls = 'heat-neg'
                elif fp < 1.5:
                    cls = 'heat-0'
                elif fp < 2.5:
                    cls = 'heat-1'
                elif fp < 3.5:
                    cls = 'heat-2'
                else:
                    cls = 'heat-3'
                out.append(f'<td class="{cls}">{fp:.1f}</td>')
        out.append(f'<td><b>{r["total"]:.1f}</b></td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


# The playoff section reports the ONE validated engine (run_season_sim.py),
# never its own sim (C12, 2026-08-01). The old inline Monte Carlo hardcoded
# playoff_threshold=12 minus an assumed 4 prior wins over max(20 - period, 0)
# remaining periods — arithmetically 0.0% for most of the season.
SEASON_SIM_JSON = OUT / 'season_sim.json'
#: refuse to render a number this many periods behind the live matchup
# One staleness bar, imported from its owner — a drifted copy here would let
# this section render odds title_equity itself refuses to convert through.
from scripts.xfp.lib.title_equity import STALE_PERIOD_HARD as PLAYOFF_SIM_STALE_PERIODS  # noqa: E402


def render_playoff_simulation(current_period=None):
    """Playoff/title odds from season_sim.json, stamped with the payload's age.

    Refuses to render (an explicit 'unavailable' line) when the payload is
    missing or stale rather than printing a dead 0.0% — loud beats silent.
    """
    head = ('<h2>🎲 Playoff Odds '
            '<small class="muted">(season_sim engine)</small></h2>')

    def _unavailable(why):
        return (head + f'<p class="notes muted">unavailable — {h(why)} · run '
                '<code>python scripts/xfp/run_season_sim.py</code> to '
                'refresh.</p>')

    try:
        payload = json.loads(SEASON_SIM_JSON.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return _unavailable('season_sim.json missing')
    except Exception as e:
        return _unavailable(f'season_sim.json unreadable ({e})')

    josh = payload.get('josh') or {}
    p_play = josh.get('p_playoffs')
    p_title = josh.get('p_title')
    if p_play is None:
        return _unavailable('season_sim.json carries no josh.p_playoffs')

    gen = payload.get('generated') or 'unknown date'
    pay_period = payload.get('period')
    sims = payload.get('sims')

    if current_period is not None and pay_period is not None:
        gap = int(current_period) - int(pay_period)
        if gap >= PLAYOFF_SIM_STALE_PERIODS:
            return _unavailable(
                f'season_sim.json is {gap} periods stale (generated '
                f'{gen} at period {pay_period}, now period {current_period})')

    bits = [f'P(playoffs) <b class="pos">{p_play * 100:.1f}%</b>']
    if p_title is not None:
        bits.append(f'P(title) <b>{p_title * 100:.1f}%</b>')
    stamp = f'as of {h(str(gen))}'
    if pay_period is not None:
        stamp += f' · period {pay_period}'
    if sims:
        stamp += f' · {sims} sims'
    return (head + '<p class="notes">' + ' · '.join(bits)
            + f'<br><small class="muted">{stamp} · '
            f'<code>run_season_sim.py</code></small></p>')


def render_position_competition(rh3_map):
    """For each position, top hot/cold movers among FAs + Ligers."""
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
        rh3['nk'] = rh3['player_name'].map(_norm)
        # for each position, top 5 by RoS league-wide
        rostered_by_team = {}
        for t in league.teams:
            for p in t.roster:
                rostered_by_team[_norm(p.name)] = t.team_name

        if 'primary_position' not in rh3.columns:
            return ''
        out = ['<h2>📍 Position-Specific Competition <small class="muted">(top 3 RoS by primary position)</small></h2>',
               '<table><thead><tr><th>Pos</th><th>Top 3 (RoS · owner)</th></tr></thead><tbody>']
        for pos in ['C', '1B', '2B', '3B', 'SS', 'OF']:
            sub = rh3[rh3['primary_position'] == pos].nlargest(5, 'expected_total_fp_remaining')
            entries = []
            for _, r in sub.iterrows():
                owner = rostered_by_team.get(r['nk'], '🆓')
                marker = '⭐' if 'Ligers' in str(owner) else ('🆓' if owner == '🆓' else '')
                entries.append(f'{h(r["player_name"])} <b>{r["expected_total_fp_remaining"]:.0f}</b> · {marker}{h(owner) if owner != "🆓" else "FA"}')
            out.append(f'<tr><td><b>{pos}</b></td><td>{" · ".join(entries[:3])}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return _section_error('📍 Position Competition', e)


def render_injury_alerts(my_lineup):
    """Flag any Liger with current injury status."""
    injured = []
    for p in my_lineup:
        inj = getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE'
        if inj not in ('ACTIVE', 'NORMAL', ''):
            slot = getattr(p, 'lineupSlot', '?')
            injured.append({'name': p.name, 'pos': p.position, 'injury': inj, 'slot': slot})
    if not injured:
        return '<h2>🏥 Injury Status</h2><p class="muted">No injury concerns on your active roster.</p>'
    out = ['<h2>🏥 Injury Status <small class="muted">(current per ESPN)</small></h2>',
           '<table><thead><tr><th>Player</th><th>Pos</th><th>Status</th><th>Slot</th></tr></thead><tbody>']
    for i in injured:
        out.append(f'<tr><td>{h(i["name"])}</td><td>{h(i["pos"])}</td>'
                   f'<td class="neg">{h(i["injury"])}</td><td>{h(str(i["slot"]))}</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def render_trend_watch(my_lineup):
    """Physical getting-better/worse watch for rostered players (DISPLAY/CONTEXT
    only — never a projection input, CLAUDE.md #13). Hitters = 3-axis bat-tracking
    (bat speed + attack angle + fast-swing%); SP/RP = FB velo (induced bat speed
    rejected for pitchers). Notable movers only (|z|>=1.0). Robust: any failure
    renders a VISIBLE 'unavailable this build' notice (never a blank section, and
    never a publish-gating error marker) so it can't break the build. Engine + validation:
    scripts/xfp/lib/trend_signal.py, early_season_bat_speed_2026-06-16.md."""
    try:
        from scripts.xfp.lib.trend_signal import (trend_line, hitter_trend_table,
                                                  pitcher_trend_table)
        ht, pt = hitter_trend_table(), pitcher_trend_table()
        risers, decliners = [], []
        for p in my_lineup:
            role = detect_pitcher_role(p)
            is_p = role in ('SP', 'RP')
            tag = trend_line(p.name, team=getattr(p, 'proTeam', None),
                             position=getattr(p, 'position', None),
                             role=role if is_p else None, hit_tbl=ht, pit_tbl=pt)
            if not tag:
                continue
            if tag.startswith('\U0001f53a'):
                risers.append((p.name, tag))
            elif tag.startswith('\U0001f53b'):
                decliners.append((p.name, tag))
        if not risers and not decliners:
            return ('<h2 id="trend">📈 Physical Trend Watch</h2>'
                    '<p class="muted">No notable physical risers/decliners on the roster '
                    '(all within ±1σ of prior-year baseline).</p>')
        out = ['<h2 id="trend">📈 Physical Trend Watch '
               '<small class="muted">(hitters: bat speed/swing-path/intent; SP/RP: FB velo · '
               'vs prior-yr baseline · display/context, NOT a projection input)</small></h2>',
               '<table><thead><tr><th>Player</th><th>Physical trend</th></tr></thead><tbody>']
        for name, tag in risers + decliners:
            cls = 'pos' if tag.startswith('\U0001f53a') else 'neg'
            out.append(f'<tr><td>{h(name)}</td><td class="{cls}">{h(tag)}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        _warn_except('trend_watch', e)
        # Fail-soft but VISIBLE (audit T30, 2026-08-01). `return ''` deleted the
        # section from the published page, and the publish-integrity guard in
        # main() cannot regex a section that is not there — so a dead trend
        # watch shipped with one stderr line as its only trace. The wording
        # deliberately avoids that guard's '<h2>..</h2><p class="muted">error:'
        # marker: this is a display/context lens (CLAUDE.md #13) and a
        # bat-tracking hiccup must not gate the nightly Pages publish.
        return ('<h2 id="trend">📈 Physical Trend Watch</h2>'
                f'<p class="notes muted">unavailable this build — {h(str(e))}</p>')


def render_power_rankings():
    """League-wide team rankings by total RoS projection."""
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
        rh3['nk'] = rh3['player_name'].map(_norm)
        rh3_ros = dict(zip(rh3['nk'], rh3['expected_total_fp_remaining'].fillna(0)))
        from plv_clone.projections import PROJECTIONS as _PROJ
        rp3 = _PROJ.rp3(live_il=True).drop_duplicates('player_name')
        rp3['nk'] = rp3['player_name'].map(_norm)
        SP_REM = 24
        rp3_ros = dict(zip(rp3['nk'],
                            (rp3.get('ros_fixed', rp3.get('xfp_rp3_per_start_sched',
                                       rp3.get('xfp_rp3_per_start', 0)) * SP_REM)).fillna(0)))
        rprs2 = pd.read_csv(OUT / 'xfp_rprs2_projections.csv').drop_duplicates('name_api')
        rprs2['nk'] = rprs2['name_api'].map(_norm)
        rprs2_ros = dict(zip(rprs2['nk'], rprs2['xfp_ros'].fillna(0)))
        rows = []
        for t in league.teams:
            total = 0
            for p in t.roster:
                nk = _norm(p.name)
                slots = set(getattr(p, 'eligibleSlots', []) or [])
                if slots & {'C','1B','2B','3B','SS','OF','DH','UTIL'}:
                    total += rh3_ros.get(nk, 0)
                else:
                    total += rp3_ros.get(nk, 0) + rprs2_ros.get(nk, 0) * 0.5
            rows.append({'name': t.team_name, 'ros': total})
        rows.sort(key=lambda r: -r['ros'])
        out = ['<h2>🏆 League Power Rankings <small class="muted">(by total RoS projection)</small></h2>',
               '<table><thead><tr><th>#</th><th>Team</th><th>Total RoS</th><th>Δ vs Avg</th></tr></thead><tbody>']
        avg = sum(r['ros'] for r in rows) / len(rows)
        for i, r in enumerate(rows, 1):
            delta = r['ros'] - avg
            cls = 'pos' if delta > 0 else 'neg'
            star = ' ⭐' if 'Ligers' in r['name'] else ''
            out.append(f'<tr><td>{i}</td><td>{h(r["name"])}{star}</td>'
                       f'<td>{r["ros"]:.0f}</td>'
                       f'<td class="{cls}">{delta:+.0f}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return _section_error('🏆 League Power Rankings', e)


def render_2start_gems(schedules_by_team=None, today=None, week_end=None,
                       fas=None, rostered=None):
    """Streamer targets ranked by next-start expected FP, augmented with
    the layered display-tag stack (boom_stack, HIGH-K ARM, catcher framing,
    IL_RETURN, anti-predictive).

    Rebuilt 2026-06-03 to wire today's engine work into the matchup page:
      * boom_stack 4/4 (skill_spike + recform_hot + opp_soft + park_friendly)
        with tier-aware boom%/bust% rates surfaced as a tooltip.
      * HIGH-K ARM badge when z-score >= +1.0 in current month cohort.
      * Catcher framing tag (🧊 elite Q5 / ⚠ Q1 tax).
      * IL_RETURN flag when >= 30d since last MLB start.
      * Anti-predictive warning when tier in {SP2/3, backend} AND
        skill_spike fires (recent K%↑ + BB%↓ = regression risk at those tiers).

    Ranking composite:
      composite_ev = rp3_per_start  ×  park_adj  ×  opp_adj
      tie-break = boom_stack DESC → matchup tier DESC → pct_owned ASC

    IL FILTER (PARANOID): any FA SP with injuryStatus in IL_INJURY_STATES
    OR with no in-window confirmed/predicted start is excluded outright.
    The earlier streamer block silently dropped pitchers via the "no
    in-window start" gate; this version layers an explicit `is_il_player`
    check FIRST so the audit trail is unambiguous.
    """
    try:
        if fas is None or rostered is None:
            # Fallback fetch — main() normally threads fas/rostered in
            # (network diet, audit 2026-07-04).
            from plv_clone.league_state import LeagueState
            league = LeagueState()._get_league()
            rostered = set()
            for t in league.teams:
                for p in t.roster:
                    rostered.add(_norm(p.name))
            fas = league.free_agents(size=2000)  # full pool — avoid silent truncation
        from plv_clone.projections import PROJECTIONS as _PROJ
        rp3 = _PROJ.rp3(live_il=True).drop_duplicates('player_name')
        rp3['nk'] = rp3['player_name'].map(_norm)
        # Phase 3 Agent 3: optional live within-season blend projection.
        # Display-only suffix appended to each streamer's projection band.
        live_blend = load_live_blend_map()

        # Floor + conviction context lenses (item 1, 2026-07-04). Both display-
        # only (Rule 13) — they NEVER move the rp3/exp_fp ranking.
        #  - floor: floor_adjusted_xfp / floor_flag (K-BB bust risk) keyed by name
        #  - conviction: run_conviction_scan divergence tag keyed by mlbam
        try:
            from lib.extra_lenses import floor_lens, floor_adjusted_xfp, floor_flag
        except Exception as e:
            _warn_except('streamers.floor_import', e)
            floor_lens = floor_adjusted_xfp = floor_flag = None
        conv_by_mlbam = {}
        try:
            from run_conviction_scan import scan as _conv_scan
            _cdf = _conv_scan('sp')
            if _cdf is not None and len(_cdf):
                conv_by_mlbam = {int(m): t for m, t in zip(_cdf['mlbam'], _cdf['tag'])
                                 if isinstance(t, str) and t}
        except Exception as e:
            _warn_except('streamers.conviction_scan', e)

        # Validated multipliers
        pf_path = CACHE / 'park_factors_2018_2026.csv'
        ts_path = CACHE / 'team_strength_2026.csv'
        pf_map = {}
        try:
            # OWNER (audit 2026-07-04): multi-year VENUE_ERAS-aware pf_R replaces
            # the single-current-year pf_wOBA read (half-season noise — Coors
            # streamers were docked only ~-0.8% vs the validated -3.2 FP).
            from lib.extra_lenses import _park_R_map
            pf_map = {k.upper(): v for k, v in _park_R_map().items()}
        except Exception as e:
            _warn_except('streamers.park_R_map', e)
            if pf_path.exists():
                pf_df = pd.read_csv(pf_path)
                pf_cur = pf_df[pf_df['year'] == pf_df['year'].max()]
                pf_map = dict(zip(pf_cur['team_abbr'].str.upper(), pf_cur['pf_wOBA']))
        ts_map_local = {}
        if ts_path.exists():
            ts_df = pd.read_csv(ts_path)
            ts_map_local = {row['team'].upper():
                            (row['bat_index_recent'] if pd.notna(row.get('bat_index_recent'))
                             else row.get('bat_index', 1.0))
                            for _, row in ts_df.iterrows()}

        # Collect candidate FAs with baseline projection
        candidates = []
        n_il_excluded = 0
        for fa in fas:
            if detect_pitcher_role(fa) != 'SP':
                continue
            nk = _norm(fa.name)
            if nk in rostered:
                continue
            # PARANOID IL FILTER — never recommend an injured pitcher.
            if is_il_player(fa):
                n_il_excluded += 1
                continue
            info = rp3[rp3['nk'] == nk]
            if info.empty:
                continue
            row0 = info.iloc[0]
            per_start = (row0.get('xfp_rp3_per_start_sched')
                         or row0.get('xfp_rp3_per_start') or 0)
            if per_start < 9:
                continue
            # rp3 row diagnostics used downstream by boom_stack
            try:
                rp3_rank = int(row0.get('rank')) if pd.notna(row0.get('rank')) else None
            except Exception:
                rp3_rank = None
            try:
                rec_form = float(row0.get('recency_form_gap')) if pd.notna(row0.get('recency_form_gap')) else None
            except Exception:
                rec_form = None
            try:
                p25 = float(row0.get('xfp_rp3_p25')) if pd.notna(row0.get('xfp_rp3_p25')) else None
                p75 = float(row0.get('xfp_rp3_p75')) if pd.notna(row0.get('xfp_rp3_p75')) else None
            except Exception:
                p25, p75 = None, None
            candidates.append({
                'name': fa.name,
                'team': (getattr(fa, 'proTeam', '?') or '?').upper(),
                'per_start': float(per_start),
                'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
                'rp3_rank': rp3_rank,
                'rec_form': rec_form,
                'p25': p25, 'p75': p75,
            })
        if n_il_excluded:
            print(f'  [streamers] IL filter excluded {n_il_excluded} FA SPs')

        if not candidates:
            return '<h2>💎 Streamer Targets</h2><p class="muted">No FA SPs above baseline.</p>'

        # Resolve next start for each candidate. Only keep starts whose date
        # falls in the current week window (today..week_end). Candidates with
        # no in-window start (typically IL'd, or whose next start is in a
        # later week) are dropped entirely — we never render them with `—`.
        next_start_by_name = {}
        today_s = today.isoformat() if today else ''
        week_end_s = week_end.isoformat() if week_end else ''
        if schedules_by_team and today and week_end:
            mlbam_by_name = {}
            for c in candidates:
                pid = _resolve_pitcher_mlbam(c['name'], team=c.get('team'), role='SP')
                if pid:
                    mlbam_by_name[c['name']] = int(pid)
            if mlbam_by_name:
                starts = build_sp_starts_by_pitcher(
                    set(mlbam_by_name.values()), schedules_by_team, today, week_end)
                for nm, pid in mlbam_by_name.items():
                    games = starts.get(pid, [])
                    in_window = [g for g in games
                                 if today_s <= g.get('date', '') <= week_end_s]
                    if in_window:
                        next_start_by_name[nm] = in_window[0]  # sorted by date

        # Filter: only candidates with a confirmed/predicted start IN the
        # current week window. Drops IL'd pitchers and pitchers whose next
        # start is outside this week — those are not streamable today.
        candidates = [c for c in candidates if c['name'] in next_start_by_name]
        if not candidates:
            return ('<h2>💎 Streamer Targets</h2>'
                    '<p class="muted">No FA SPs with starts this week.</p>')

        # Rank by adjusted expected FP + augment with layered tags
        for c in candidates:
            ns = next_start_by_name[c['name']]
            opp = (ns.get('opp_team') or '').upper()
            is_home = bool(ns.get('is_home'))
            venue = c['team'] if is_home else opp
            pf_wOBA = pf_map.get(venue, 1.0)
            opp_idx = ts_map_local.get(opp, 1.0)
            mult = _mproj.two_start_multiplier(pf_wOBA, opp_idx)
            c['opp'] = opp
            c['is_home'] = is_home
            c['pf_wOBA'] = pf_wOBA
            c['opp_idx'] = opp_idx
            c['adj_mult'] = mult
            c['exp_fp'] = c['per_start'] * mult
            c['date'] = ns.get('date', '')
            c['confirmed'] = ns.get('confirmed', False)

            # Layered display tags — all defensive (returns {} on failure).
            mlbam = _resolve_pitcher_mlbam(c['name'], team=c.get('team'), role='SP')
            c['mlbam'] = int(mlbam) if mlbam else None
            bs = compute_boom_stack(c['mlbam'], c['rec_form'], opp,
                                    rp3_rank=c['rp3_rank']) if c['mlbam'] else {}
            c['boom_stack'] = bs.get('boom_stack')
            c['boom_components'] = bs.get('components') or {}
            c['boom_tier'] = bs.get('tier')
            c['boom_rate'] = bs.get('boom_rate_expected')
            c['bust_rate'] = bs.get('bust_rate_expected')
            c['anti_pred'] = bool(bs.get('skill_spike_anti_predictive'))

            hk = compute_high_k_pitcher(c['mlbam']) if c['mlbam'] else {}
            c['is_high_k'] = bool(hk.get('is_high_k'))

            cf = compute_catcher_framing(c['team'])
            c['is_elite_framer'] = bool(cf.get('is_elite_framer'))
            c['is_framing_tax'] = bool(cf.get('is_framing_tax'))

            il = compute_il_return_flag(c['mlbam']) if c['mlbam'] else {}
            c['is_il_return'] = bool(il.get('is_first_back_long_il'))

            # Matchup-tier from opp_idx (mirrors stream_the_stack soft/avg/tough).
            c['matchup_tier'] = _mproj.matchup_tier(opp_idx)

            # Floor lens (item 1) — K-BB bust risk on the per_start mean.
            # Display-only (Rule 13): does NOT change exp_fp or the ranking.
            c['floor_flag'] = None
            if floor_lens is not None:
                fl = floor_lens(c['name'])
                if fl and fl.get('bust_prob') is not None:
                    _fadj, _pen = floor_adjusted_xfp(c['per_start'], fl['bust_prob'])
                    c['floor_flag'] = floor_flag(_pen, fl.get('tier'))
                    c['floor_tier'] = fl.get('tier')
                    c['floor_bust'] = fl.get('bust_prob')
            # Conviction lens (item 1) — model-vs-process divergence tag.
            c['conv'] = conv_by_mlbam.get(c['mlbam']) if c.get('mlbam') else None

        # Composite ranking: exp_fp DESC, then boom_stack DESC, then
        # matchup_tier (soft > avg > tough), then pct_owned ASC.
        _tier_rank = {'soft': 0, 'avg': 1, 'tough': 2}
        candidates.sort(key=lambda x: (
            -x['exp_fp'],
            -(x['boom_stack'] or 0),
            _tier_rank.get(x['matchup_tier'], 1),
            x['pct_owned'],
        ))

        out = [
            '<h2>💎 Top Streamer Targets <small class="muted">'
            '(rp3 × park × opp · tags layered)</small></h2>',
            '<p class="notes">'
            'Composite EV = rp3 baseline × park × opp batting index, ranked desc; '
            'ties broken by boom_stack desc → matchup tier desc → %owned asc. '
            'Tags layer on top — boom_stack (✦ N/4), 🎯 HIGH-K ARM, 🧊 elite framer, '
            '⚠ framing tax, 🏥 first-back-from-IL, ⛔ anti-predictive skill-spike. '
            'IL filter (paranoid): excluded ' + str(n_il_excluded) + ' FA SPs with '
            'injury status. Pitcher L/R splits excluded (failed YoY stability B1).'
            '</p>',
            '<table><thead><tr>'
            '<th>Pitcher</th><th>Tm</th><th>%Own</th>'
            '<th>Next</th><th>Date</th>'
            '<th>Tier</th>'
            '<th>rp3 (p25–p75)</th>'
            '<th>boom_stack</th>'
            '<th title="K-BB floor: FLOOR-RISK = RISKY-tier bust the mean hides; SAFE-FLOOR = SAFE-tier mean under-credits (context only)">Floor</th>'
            '<th title="Model-vs-process divergence: PROCESS&gt;MODEL buy-low / MODEL&gt;PROCESS sell-high (context only)">Conv</th>'
            '<th>Tags</th>'
            '<th>Exp FP</th>'
            '</tr></thead><tbody>',
        ]
        for g in candidates[:10]:
            opp_disp = g['opp']
            if g['opp'] != '—':
                arrow = 'vs' if g.get('is_home') else '@'
                opp_disp = f"{arrow} {g['opp']}"
                if not g['confirmed']:
                    opp_disp += ' <small class="muted">(pred)</small>'
            adj_pct = (g['adj_mult'] - 1) * 100
            adj_class = 'pos' if adj_pct >= 1 else ('neg' if adj_pct <= -1 else 'muted')

            # rp3 + band
            if g['p25'] is not None and g['p75'] is not None:
                band = f'{g["per_start"]:.1f} <small class="muted">({g["p25"]:.1f}–{g["p75"]:.1f})</small>'
            else:
                band = f'{g["per_start"]:.2f}'
            # Phase 3 Agent 3: additive within-season-blend suffix.
            # Format: "8.4 fp/start (blended 9.2 [7.8-10.5])". Does NOT replace
            # the headline rp3 number or alter win-prob; purely informational.
            lb = live_blend.get(g.get('mlbam')) if live_blend else None
            if lb and lb.get('value') is not None:
                band += (f' <small class="muted">(blended {lb["value"]:.1f} '
                         f'[{lb["lo"]:.1f}-{lb["hi"]:.1f}])</small>')

            # boom_stack render with tooltip
            bs_val = g['boom_stack']
            if bs_val is None:
                bs_cell = '<span class="muted">—</span>'
            else:
                comps = g['boom_components']
                tip_parts = [f"{k}={v}" for k, v in comps.items()]
                tip = ' '.join(tip_parts)
                if g['boom_rate'] is not None:
                    tip += f' · boom%≈{g["boom_rate"]*100:.0f} bust%≈{g["bust_rate"]*100:.0f} (tier={g["boom_tier"]})'
                stars = '✦' * bs_val + '·' * (4 - bs_val)
                cls = 'pos' if bs_val >= 2 else ('muted' if bs_val == 0 else '')
                bs_cell = f'<span class="{cls}" title="{h(tip)}">{stars} <small>{bs_val}/4</small></span>'

            # Tag chips
            chips = []
            if g['is_high_k']:
                chips.append('<span class="chip chip-k" title="HIGH-K ARM (z>=+1.0)">🎯K</span>')
            if g['is_elite_framer']:
                chips.append('<span class="chip chip-frame" title="Elite framer (Q5)">🧊F</span>')
            elif g['is_framing_tax']:
                chips.append('<span class="chip chip-bad" title="Framing tax (Q1)">⚠F</span>')
            if g['is_il_return']:
                chips.append('<span class="chip chip-il" title="First start back from >=30d gap">🏥IL</span>')
            if g['anti_pred']:
                chips.append('<span class="chip chip-bad" title="Anti-predictive skill-spike (regression risk at this tier)">⛔AP</span>')
            chips_html = ' '.join(chips) if chips else '<span class="muted">·</span>'

            # Matchup tier color
            tier_cls = {'soft': 'pos', 'tough': 'neg', 'avg': 'muted'}.get(g['matchup_tier'], 'muted')

            # Floor cell (item 1) — red FLOOR-RISK / green SAFE-FLOOR / muted dash
            ff = g.get('floor_flag')
            if ff == 'FLOOR-RISK':
                _tip = f"RISKY floor (bust≈{g.get('floor_bust','?')}%) the mean hides"
                floor_cell = f'<td class="neg" title="{h(_tip)}">FLOOR-RISK</td>'
            elif ff == 'SAFE-FLOOR':
                _tip = f"SAFE floor (bust≈{g.get('floor_bust','?')}%) the mean under-credits"
                floor_cell = f'<td class="pos" title="{h(_tip)}">SAFE-FLOOR</td>'
            else:
                floor_cell = '<td class="muted">·</td>'
            # Conv cell (item 1) — buy-low / sell-high divergence
            cv = g.get('conv')
            if cv == 'PROCESS>MODEL':
                conv_cell = '<td class="pos" title="STUFF pct &gt; model pct — buy-low watch">PROCESS&gt;MODEL</td>'
            elif cv == 'MODEL>PROCESS':
                conv_cell = '<td class="neg" title="model pct &gt; STUFF pct — sell-high watch">MODEL&gt;PROCESS</td>'
            else:
                conv_cell = '<td class="muted">·</td>'

            out.append(
                f'<tr>'
                f'<td>{player_link(g["name"], mlbam=g.get("mlbam"))}</td>'
                f'<td>{h(g["team"])}</td>'
                f'<td>{g["pct_owned"]:.0f}%</td>'
                f'<td>{opp_disp}</td>'
                f'<td>{h(g["date"])}</td>'
                f'<td class="{tier_cls}">{g["matchup_tier"]}</td>'
                f'<td>{band}</td>'
                f'<td>{bs_cell}</td>'
                f'{floor_cell}'
                f'{conv_cell}'
                f'<td>{chips_html}</td>'
                f'<td><b>{g["exp_fp"]:.1f}</b> '
                f'<small class="{adj_class}">({adj_pct:+.0f}%)</small></td>'
                f'</tr>'
            )
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return _section_error('💎 Streamer Targets', e)


def _get_player_add_dates(league, team_name, since_date):
    """Build {player_name: add_date} of when each currently-rostered player
    was most-recently ADDED to the user's team. Walks recent_activity back
    to `since_date`. Players added pre-window or via DRAFT are absent —
    callers should treat absence as "on roster the entire window."
    """
    add_dates = {}
    try:
        acts = league.recent_activity(size=500)
        for a in acts:
            try:
                ts_ms = getattr(a, 'date', None)
                if ts_ms is None:
                    continue
                act_date = datetime.fromtimestamp(ts_ms / 1000).date()
                if act_date < since_date:
                    break  # acts come newest→oldest; older than window
                for action in (a.actions or []):
                    team, action_str, player_name = action
                    if not team or getattr(team, 'team_name', None) != team_name:
                        continue
                    action_norm = (action_str or '').upper()
                    if 'ADDED' in action_norm or 'TRADED' in action_norm:
                        if player_name not in add_dates:
                            add_dates[player_name] = act_date
            except Exception as e:
                _warn_except('add_dates.activity_row', e)
                continue
    except Exception as e:
        print(f'  ⚠ recent_activity fetch failed: {e}')
    return add_dates


def _count_past_sp_starts(my_lineup, week_start, today, add_dates=None):
    """Count SP starts already pitched in [window_start, today) by rostered SPs.

    Per-player window_start = max(week_start, add_date_for_player). Prevents
    counting starts that occurred before a player joined the user's roster
    (the Kelly 5/25 bug 2026-05-31 — Kelly was FA-added 5/31 but his pre-add
    5/25 start was being counted as one of the user's past pitched starts).

    Critical for accurate cap math — render_cap_status was only counting
    forward-looking (today + future) starts before the prior fix.

    NETWORK DIET (audit 2026-07-04): rewritten to a single local read of
    boxscore_pitchers.parquet (mlbam_id, gs==1, game_date in window) instead
    of ~8-10 SEQUENTIAL per-pitcher MLB gameLog HTTP requests. Same return
    shape. Falls back to the old HTTP path if the parquet is missing/unreadable.
    """
    if today <= week_start:
        return 0
    add_dates = add_dates or {}
    # Per-pitcher counting window: {mlbam_id: window_start_date}
    windows = {}
    for p in my_lineup:
        if detect_pitcher_role(p) != 'SP':
            continue
        inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
        if inj in ('SIXTY_DAY_DL', 'INJURY_RESERVE', 'OUT'):
            continue
        pid = _resolve_pitcher_mlbam(p.name, team=(getattr(p, 'proTeam', None) or None), role='SP')
        if not pid:
            continue
        per_player_start = week_start
        added_on = add_dates.get(p.name)
        if added_on and added_on > week_start:
            per_player_start = added_on
        windows[int(pid)] = per_player_start
    if not windows:
        return 0

    bs_path = CACHE / 'boxscore_pitchers.parquet'
    if bs_path.exists():
        try:
            bp = pd.read_parquet(bs_path, columns=['mlbam_id', 'game_date', 'gs'])
            bp = bp[(bp['gs'] > 0) & (bp['mlbam_id'].isin(windows.keys()))]
            past = 0
            for _, r in bp.iterrows():
                game_date = datetime.strptime(str(r['game_date'])[:10], '%Y-%m-%d').date()
                if windows[int(r['mlbam_id'])] <= game_date < today:
                    past += 1
            return past
        except Exception as e:
            _warn_except('past_sp_starts.parquet', e)
    else:
        print('  ⚠ [past_sp_starts] boxscore_pitchers.parquet missing — falling back to per-pitcher gameLog HTTP', file=sys.stderr)
    return _count_past_sp_starts_http(windows, today)


def _count_past_sp_starts_http(windows, today):
    """Legacy fallback: sequential per-pitcher MLB Stats API gameLog requests.

    `windows` = {mlbam_id: window_start_date}. Only used when the boxscore
    parquet is unavailable (pre-2026-07-04 this was the primary path).
    """
    import requests
    past = 0
    for pid, per_player_start in windows.items():
        try:
            url = (f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
                   f"?stats=gameLog&group=pitching&season={per_player_start.year}")
            r = requests.get(url, timeout=10).json()
            splits = r.get('stats', [{}])[0].get('splits', [])
            for s in splits:
                game_date_s = s.get('date')
                if not game_date_s:
                    continue
                game_date = datetime.strptime(game_date_s, '%Y-%m-%d').date()
                if per_player_start <= game_date < today:
                    if int(s.get('stat', {}).get('gamesStarted', 0)) > 0:
                        past += 1
        except Exception as e:
            _warn_except(f'past_sp_starts.http.{pid}', e)
            continue
    return past


def render_cap_status(my_proj, my_lineup=None, week_start=None, today=None,
                       league=None, my_team_name=None, cap=None,
                       banked_espn=None, pmeta=None):
    """Show SP-start cap utilization for the period: banked/past + today/future.

    Pass `league` + `my_team_name` to enable add-date-aware past-start
    counting (filters out starts pitched before a player joined this roster).

    Period-aware (2026-07-11): `cap` is the current matchup period's SP cap
    (default `MAX_SP_STARTS_PER_WEEK`=10; 16 for the ASG block, 20 for a 2-week
    playoff round). When `banked_espn` (ESPN's authoritative statId-33
    period-to-date count) is supplied it is used as the "already used" figure —
    it correctly spans a multi-week/ASG period, unlike the this-week-only
    boxscore count that stays the fallback. `pmeta` (the resolver dict) drives
    the period/window label for a multi-week period.
    """
    if cap is None:
        cap = MAX_SP_STARTS_PER_WEEK
    n_confirmed = 0
    n_predicted = 0
    for proj in my_proj.values():
        for b in proj.get('breakdown', []):
            if b.get('type') == 'start':
                if b.get('confirmed', True):
                    n_confirmed += 1
                else:
                    n_predicted += 1
    n_forward = n_confirmed + n_predicted

    n_past = 0
    if my_lineup is not None and week_start is not None and today is not None:
        try:
            add_dates = {}
            if league is not None and my_team_name is not None:
                add_dates = _get_player_add_dates(league, my_team_name, week_start)
            n_past = _count_past_sp_starts(my_lineup, week_start, today, add_dates)
        except Exception as e:
            print(f'  ⚠ past-starts count failed: {e}')

    # Prefer ESPN's authoritative banked count (period-to-date; spans a
    # multi-week/ASG block) for the "already used" figure; fall back to this
    # week's boxscore count for a plain single-week period.
    if banked_espn is not None:
        n_used = int(banked_espn)
        used_note = f'<b>{n_used} banked (ESPN)</b> + '
    else:
        n_used = n_past
        used_note = (f'<b>{n_past} already pitched</b> + ' if n_past else '')

    n_starts = n_used + n_forward
    pred_note = (f' <span class="muted">(+{n_predicted} rotation-gap predicted)</span>'
                 if n_predicted else '')
    forward_note = (f'<b>{n_forward} today/upcoming</b>{pred_note}'
                    if n_forward else '0 today/upcoming')
    breakdown = f'{used_note}{forward_note}'

    # Period/window label — shown for a genuine multi-week period OR an override
    # block like the ASG span (which ESPN reports as weeks==1 despite spanning
    # two calendar weeks, so the covered flag is what makes it multi-week).
    span_word = 'week'
    win_lbl = ''
    if pmeta is not None and ((pmeta.get('weeks') or 1) > 1 or pmeta.get('covered')):
        span_word = 'period'
        win_lbl = (f' <span class="muted">(period {pmeta.get("period")}: '
                   f'{pmeta.get("week_start")}–{pmeta.get("week_end")})</span>')

    near = max(cap - 2, 0)
    if n_starts >= cap:
        msg = (f'<p class="notes"><b>⚠ SP cap at maximum:</b> {breakdown} · '
               f'{n_starts}/{cap} starts this {span_word}{win_lbl}. '
               f'Excess starts past {cap} are zeroed in scoring.</p>')
    elif n_starts < near:
        msg = (f'<p class="notes"><b>📉 Under SP cap:</b> {breakdown} · '
               f'only {n_starts}/{cap} starts this {span_word}{win_lbl}. '
               f'Add a streamer to claim more of the {cap}-start cap.</p>')
    else:
        msg = (f'<p class="notes">✓ SP cap: {breakdown} · '
               f'<b>{n_starts}/{cap}</b> total starts this {span_word}{win_lbl}.</p>')
    return msg


def _render_closer_tracker_simple():
    """Original simple table fallback — used if the leverage join fails."""
    try:
        save_csv = OUT / 'save_handcuffs.csv'
        if not save_csv.exists():
            return '<h2>🔒 Closer Tracker</h2><p class="muted">save_handcuffs.csv not found</p>'
        df = pd.read_csv(save_csv)
        if 'team' in df.columns and 'role' in df.columns:
            closers = df.groupby('team').first().reset_index() if 'role_rank' not in df.columns else df[df['role_rank'] == 1]
        else:
            closers = df.head(15)
        out = ['<h2>🔒 Closer-of-Record Tracker</h2>',
               '<p class="notes">From save_handcuffs analysis. Cross-reference with closer_persistence (~83%).</p>',
               '<table><thead><tr><th>Team</th><th>Closer</th><th>SV (current)</th></tr></thead><tbody>']
        cols = closers.columns.tolist()
        for _, r in closers.head(15).iterrows():
            name_col = 'name' if 'name' in cols else ('player_name' if 'player_name' in cols else cols[0])
            sv_col = 'sv' if 'sv' in cols else ('sv_2026' if 'sv_2026' in cols else 'saves')
            team_col = 'team' if 'team' in cols else 'proTeam'
            try:
                out.append(f'<tr><td>{h(str(r.get(team_col, "?")))}</td>'
                           f'<td>{h(str(r.get(name_col, "?")))}</td>'
                           f'<td>{r.get(sv_col, "—")}</td></tr>')
            except Exception as e:
                _warn_except('closer_tracker_simple.row', e)
                continue
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return _section_error('🔒 Closer Tracker', e)


# MLB team-id → ESPN-style abbreviation. Inverse of ESPN_TO_MLB_TEAM.
_MLB_TO_ABBR = {
    108: 'LAA', 109: 'ARI', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
    114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KC', 119: 'LAD',
    120: 'WSH', 121: 'NYM', 133: 'ATH', 134: 'PIT', 135: 'SD', 136: 'SEA',
    137: 'SF', 138: 'STL', 139: 'TB', 140: 'TEX', 141: 'TOR', 142: 'MIN',
    143: 'PHI', 144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}

_TIER_ORDER = {
    'ELITE_LEVERAGE': 0, 'HIGH_LEVERAGE': 1, 'MID_LEVERAGE': 2,
    'LOW_LEVERAGE': 3, 'GARBAGE_TIME': 4,
}

_TIER_COLOR_VAR = {
    'ELITE_LEVERAGE': '--pos',
    'HIGH_LEVERAGE': '--text',
    'MID_LEVERAGE': '--dim',
    'LOW_LEVERAGE': '--neg',
    'GARBAGE_TIME': '--neg',
}


def _tier_html(tier):
    """Wrap a leverage_tier value in a span colored by the dashboard token."""
    if not tier or pd.isna(tier):
        return '<span class="muted">—</span>'
    var = _TIER_COLOR_VAR.get(str(tier), '--dim')
    return f'<span style="color: var({var})">{h(str(tier))}</span>'


def _fetch_team_leaders(team_id, category, limit=5):
    """One MLB Stats API call for a team's season leader board on a stat
    (e.g. 'saves' or 'holds'). Returns list of dicts with name, value."""
    url = (f'https://statsapi.mlb.com/api/v1/teams/{team_id}/leaders?'
           f'leaderCategories={category}&season=2026&limit={limit}')
    try:
        data = _fetch_json(url)
    except Exception as e:
        _warn_except('team_leaders_fetch', e)
        return []
    out = []
    for cat in data.get('teamLeaders', []):
        for ldr in cat.get('leaders', []):
            person = ldr.get('person') or {}
            name = person.get('fullName')
            try:
                val = int(ldr.get('value', 0) or 0)
            except Exception:
                val = 0
            if name:
                out.append({'name': name, 'value': val})
    return out


def _load_closer_leaders_cache():
    """Per-day cache of closer/setup leader board across all MLB teams.

    Structure: {team_abbr: {'saves': [{name, value}], 'holds': [{name, value}]}}.
    One file per day so the dashboard refresh stays cheap after the first call.
    """
    cache_path = OUT / f'closer_leaders_{_today_et().isoformat()}.json'
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            _warn_except('closer_leaders.cache_read', e)
    cache = {}
    for mlb_id, abbr in _MLB_TO_ABBR.items():
        saves = _fetch_team_leaders(mlb_id, 'saves', limit=3)
        holds = _fetch_team_leaders(mlb_id, 'holds', limit=5)
        cache[abbr] = {'saves': saves, 'holds': holds}
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, separators=(',', ':'))
    except Exception as e:
        _warn_except('closer_leaders.cache_write', e)
    return cache


def render_closer_tracker():
    """Closer-of-record tracker enriched with rp_ratings_master leverage data.

    Main table columns: Team | Closer | Archetype | leverage_tier | gmLI |
    SV | FIREMAN. Sorted by leverage_tier (ELITE first) then SV desc.

    WATCH LIST: next-in-line setup RPs per team whose leverage_tier matches
    or exceeds the closer-of-record's tier (handcuff candidates).

    Falls back to the original simple table if rp_ratings_master.csv or the
    MLB team-leaders API are unavailable.
    """
    try:
        rp_path = ROOT / 'data' / 'research' / 'rp_ratings_master.csv'
        if not rp_path.exists():
            return _render_closer_tracker_simple()
        rp_df = pd.read_csv(rp_path)
        rp_df = rp_df[rp_df['year'] == 2026].copy()
        if rp_df.empty:
            return _render_closer_tracker_simple()
        rp_df['nk'] = rp_df['player_name'].astype(str).map(_norm)
        # Keep one row per player (highest gmli wins on dup) so lookups are stable.
        rp_df = (rp_df.sort_values('gmli', ascending=False)
                      .drop_duplicates('nk', keep='first'))
        rp_lookup = {row['nk']: row for _, row in rp_df.iterrows()}

        # Fetch closer/setup leaders per team (cached per day).
        leaders = _load_closer_leaders_cache()
        if not leaders:
            return _render_closer_tracker_simple()

        closer_rows = []
        watch_rows = []
        for abbr in sorted(leaders.keys()):
            entry = leaders.get(abbr) or {}
            saves = entry.get('saves') or []
            holds = entry.get('holds') or []
            if not saves:
                continue
            closer = saves[0]
            closer_nk = _norm(closer['name'])
            cinfo = rp_lookup.get(closer_nk)
            closer_tier = (str(cinfo['leverage_tier'])
                           if cinfo is not None and pd.notna(cinfo.get('leverage_tier'))
                           else None)
            closer_gmli = (float(cinfo['gmli'])
                           if cinfo is not None and pd.notna(cinfo.get('gmli'))
                           else None)
            closer_arch = (str(cinfo['archetype'])
                           if cinfo is not None and pd.notna(cinfo.get('archetype'))
                           else None)
            closer_fireman = bool(cinfo.get('FIREMAN')) if cinfo is not None else False
            closer_rows.append({
                'team': abbr,
                'name': closer['name'],
                'archetype': closer_arch,
                'leverage_tier': closer_tier,
                'gmli': closer_gmli,
                'sv': closer['value'],
                'fireman': closer_fireman,
                'tier_rank': _TIER_ORDER.get(closer_tier, 9),
            })

            # WATCH LIST: any candidate with HLD ≥ 5 OR HIGH_LEVERAGE tag in
            # rp_ratings_master whose leverage_tier ≥ closer's tier.
            closer_rank = _TIER_ORDER.get(closer_tier, 9)
            seen = {closer_nk}
            # Candidate pool = top setup men by HLD + any other top SV man.
            pool = []
            for h_row in holds:
                pool.append({'name': h_row['name'], 'hld': h_row['value'], 'sv': 0})
            for s_row in saves[1:]:  # rank 2+ save earners (also count as candidates)
                # match into existing pool by name, else add
                match = next((p for p in pool
                              if _norm(p['name']) == _norm(s_row['name'])), None)
                if match is not None:
                    match['sv'] = s_row['value']
                else:
                    pool.append({'name': s_row['name'], 'hld': 0,
                                 'sv': s_row['value']})
            for cand in pool:
                cnk = _norm(cand['name'])
                if cnk in seen:
                    continue
                cand_info = rp_lookup.get(cnk)
                # Trigger: HLD ≥ 5 OR (HIGH_LEVERAGE tag in rp_master).
                hld_trigger = cand['hld'] >= 5
                hl_trigger = bool(cand_info is not None
                                  and cand_info.get('HIGH_LEVERAGE'))
                if not (hld_trigger or hl_trigger):
                    continue
                cand_tier = (str(cand_info['leverage_tier'])
                             if cand_info is not None
                             and pd.notna(cand_info.get('leverage_tier'))
                             else None)
                cand_rank = _TIER_ORDER.get(cand_tier, 9)
                # "Next in line if closer falters": tier ≥ closer's tier (i.e.
                # lower-or-equal numeric rank — lower = better).
                if cand_rank > closer_rank:
                    continue
                cand_gmli = (float(cand_info['gmli'])
                             if cand_info is not None
                             and pd.notna(cand_info.get('gmli'))
                             else None)
                notes = []
                if cand['hld']:
                    notes.append(f'HLD {cand["hld"]}')
                if cand['sv']:
                    notes.append(f'SV {cand["sv"]}')
                if cand_info is not None and bool(cand_info.get('FIREMAN')):
                    notes.append('FIREMAN')
                if cand_info is not None and bool(cand_info.get('HIGH_LEVERAGE')):
                    notes.append('HIGH_LEV tag')
                watch_rows.append({
                    'team': abbr,
                    'closer': closer['name'],
                    'next': cand['name'],
                    'gmli': cand_gmli,
                    'tier': cand_tier,
                    'notes': ', '.join(notes) or '—',
                    'tier_rank': cand_rank,
                })
                seen.add(cnk)

        if not closer_rows:
            return _render_closer_tracker_simple()

        # Sort main table: leverage_tier ELITE→HIGH→MID→LOW→GARBAGE, then SV desc.
        closer_rows.sort(key=lambda r: (r['tier_rank'], -r['sv']))

        out = [
            '<h2>🔒 Closer-of-Record Tracker</h2>',
            '<p class="notes">'
            'Closer-of-record from MLB Stats API season SV leaders, enriched '
            'with leverage_tier / gmLI / archetype / FIREMAN tags from '
            'rp_ratings_master.csv. Sorted by leverage_tier (ELITE first) '
            'then SV desc. Cross-reference with closer_persistence (~83%).'
            '</p>',
            '<table><thead><tr>'
            '<th>Team</th><th>Closer</th><th>Archetype</th>'
            '<th>leverage_tier</th><th>gmLI</th><th>SV</th>'
            '<th title="FIREMAN = high-leverage multi-inning fireman role '
            '(enters mid-game with runners on, not just 9th-inning)">'
            'FIREMAN</th>'
            '</tr></thead><tbody>',
        ]
        for r in closer_rows:
            gmli_disp = f'{r["gmli"]:.2f}' if r['gmli'] is not None else '—'
            arch_disp = h(r['archetype']) if r['archetype'] else '<span class="muted">—</span>'
            fire_disp = ('<b class="pos" title="High-leverage fireman role — '
                         'enters with runners on in tight games">🚒</b>'
                         if r['fireman'] else '')
            out.append(
                f'<tr><td>{h(r["team"])}</td>'
                f'<td>{h(r["name"])}</td>'
                f'<td>{arch_disp}</td>'
                f'<td>{_tier_html(r["leverage_tier"])}</td>'
                f'<td>{gmli_disp}</td>'
                f'<td>{r["sv"]}</td>'
                f'<td>{fire_disp}</td>'
                f'</tr>'
            )
        out.append('</tbody></table>')

        # WATCH LIST sub-section.
        if watch_rows:
            watch_rows.sort(key=lambda r: (r['tier_rank'],
                                            r['gmli'] is None,
                                            -(r['gmli'] or 0)))
            out.append(
                '<h3>👀 Watch List — If Your Closer Falters</h3>'
                '<p class="notes">'
                'Setup RPs (HLD ≥ 5 OR HIGH_LEVERAGE in rp_ratings_master) '
                'whose leverage_tier matches or exceeds the closer-of-record. '
                'These are the most likely save-vultures or next-man-up '
                'candidates if the current closer loses the role.'
                '</p>'
                '<table><thead><tr>'
                '<th>Team</th><th>Current closer</th><th>If falters →</th>'
                '<th>Next-in-line gmLI</th><th>tier</th><th>Notes</th>'
                '</tr></thead><tbody>'
            )
            for r in watch_rows:
                gmli_disp = f'{r["gmli"]:.2f}' if r['gmli'] is not None else '—'
                out.append(
                    f'<tr><td>{h(r["team"])}</td>'
                    f'<td>{h(r["closer"])}</td>'
                    f'<td><b>{h(r["next"])}</b></td>'
                    f'<td>{gmli_disp}</td>'
                    f'<td>{_tier_html(r["tier"])}</td>'
                    f'<td><small>{h(r["notes"])}</small></td>'
                    f'</tr>'
                )
            out.append('</tbody></table>')

        return '\n'.join(out)
    except Exception as e:
        # Any unexpected failure → fall back to the original simple table.
        # Non-fatal (the simple table still renders), but log the traceback so
        # a silently-degraded closer tracker is visible in the build log.
        _warn_except('Closer Tracker leverage enrichment', e)
        traceback.print_exc()
        fallback = _render_closer_tracker_simple()
        # Say DEGRADED, not just 'error' (audit T30): the table that ships here
        # is a DIFFERENT table — no leverage_tier, no gmLI, no FIREMAN — and a
        # reader who skims the note reads the simple table as the full tracker.
        return (fallback
                + f'\n<p class="notes muted">⚠ DEGRADED — leverage enrichment '
                f'unavailable, so this is the simple closer table WITHOUT '
                f'leverage tiers / gmLI / FIREMAN: {h(str(e))}</p>')


def render_snapshot_diff():
    """Show what changed since last generation."""
    history_path = OUT / 'predictions_history.csv'
    if not history_path.exists():
        return ''
    df = pd.read_csv(history_path)
    if len(df) < 2:
        return ''
    df = df.tail(2)
    prev = df.iloc[0]
    curr = df.iloc[1]
    delta_my = curr['my_projected_total'] - prev['my_projected_total']
    delta_opp = curr['opp_projected_total'] - prev['opp_projected_total']
    delta_wp = (curr['win_probability'] - prev['win_probability']) * 100
    if abs(delta_my) < 0.5 and abs(delta_opp) < 0.5 and abs(delta_wp) < 0.5:
        return ('<p class="notes">📊 No meaningful change from previous snapshot.</p>')
    return (f'<p class="notes">📊 Since last snapshot: '
            f'Ligers projected <b class="{("pos" if delta_my >= 0 else "neg")}">{delta_my:+.1f}</b>, '
            f'Opp projected <b class="{("pos" if delta_opp <= 0 else "neg")}">{delta_opp:+.1f}</b>, '
            f'win prob <b class="{("pos" if delta_wp >= 0 else "neg")}">{delta_wp:+.1f} pp</b>.</p>')


def render_lineup_optimizer(lineup, projections, schedules_by_team, espn_to_mlb):
    """Find sub-optimal lineup placements: bench players projecting higher
       than active players at slots where they overlap.
       Returns HTML block + list of suggested swaps."""
    # Hitter slot eligibility mapping
    HITTER_SLOTS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF',
                     'DH', 'UTIL', 'MI', 'CI'}
    active_slots = {'C', '1B', '2B', '3B', 'SS', 'OF', 'MI', 'CI', 'UTIL'}

    # Build per-player view
    players = []
    for p in lineup:
        proj = projections.get(p.name, {})
        per_game = proj['fp'] / max(proj.get('units', 1), 1) if proj.get('units') else 0
        slot = p.lineupSlot
        if not slot: continue
        elig = set(p.eligibleSlots or [])
        is_hitter = bool(elig & HITTER_SLOTS)
        if not is_hitter: continue  # SP/RP optimization is more complex
        players.append({
            'name': p.name, 'slot': slot, 'elig': elig,
            'per_game': per_game, 'units': proj.get('units', 0),
            'is_active': slot in active_slots, 'is_bench': slot == 'BE',
            'is_il': slot in ('IL', 'INJURY_RESERVE'),
        })

    # Suggested swaps: for each bench (or low-active) player, find an active
    # player at any slot they could fill where bench > active by per-game.
    swaps = []
    bench = [p for p in players if p['is_bench'] and p['per_game'] > 0]
    active = [p for p in players if p['is_active']]
    for b in bench:
        # Could this bench player play at any of these active slots?
        for a in active:
            # Bench player must be eligible for active player's slot
            if a['slot'] not in b['elig']: continue
            # Also active player must have alternative (UTIL or other slot)
            # otherwise we'd just shift the lower projection elsewhere
            if b['per_game'] > a['per_game']:
                gain_per_game = b['per_game'] - a['per_game']
                weekly_gain = gain_per_game * max(b.get('units', 1), 1)
                swaps.append({
                    'bench_name': b['name'], 'bench_proj': b['per_game'],
                    'active_name': a['name'], 'active_proj': a['per_game'],
                    'slot': a['slot'], 'gain_per_game': gain_per_game,
                    'weekly_gain': weekly_gain,
                })
    # Sort by biggest gain. Filter duplicates (a bench player vs many actives).
    swaps.sort(key=lambda s: -s['weekly_gain'])
    seen_bench = set()
    seen_active = set()
    unique_swaps = []
    for s in swaps:
        if s['bench_name'] in seen_bench: continue
        if s['active_name'] in seen_active: continue
        seen_bench.add(s['bench_name']); seen_active.add(s['active_name'])
        unique_swaps.append(s)

    if not unique_swaps:
        return ('<h2>🎯 Lineup Optimizer</h2>'
                '<p class="muted">No obvious upgrades — current lineup looks well-set.</p>')

    out = ['<h2>🎯 Lineup Optimizer <small class="muted">— suggested swaps for next game day</small></h2>']
    out.append('<table><thead><tr>'
                '<th>Start (active → bench)</th><th>Current Proj</th>'
                '<th>Bench Better (bench → active)</th><th>Bench Proj</th>'
                '<th>Slot</th><th>Gain/wk</th></tr></thead><tbody>')
    for s in unique_swaps[:10]:
        out.append(
            f'<tr><td class="neg">{h(s["active_name"])} →BE</td>'
            f'<td>{s["active_proj"]:.2f}/g</td>'
            f'<td class="pos">{h(s["bench_name"])} →{h(s["slot"])}</td>'
            f'<td>{s["bench_proj"]:.2f}/g</td>'
            f'<td>{h(s["slot"])}</td>'
            f'<td><b class="pos">+{s["weekly_gain"]:.2f}</b></td></tr>')
    total_gain = sum(s['weekly_gain'] for s in unique_swaps)
    out.append(f'</tbody></table>'
                f'<p class="notes">Total weekly FP left on the bench: '
                f'<b class="pos">+{total_gain:.1f}</b> if all swaps executed. '
                f'Note: only obvious projection-based swaps shown; ESPN may auto-fill '
                f'optimal lineup if you set your lineup to "auto". Manual override only.</p>')
    return '\n'.join(out)


def render_accuracy_history():
    """Show prediction-vs-actual accuracy for past weeks. Returns HTML block."""
    history_path = OUT / 'predictions_history.csv'
    if not history_path.exists():
        return '<h2>📈 Prediction Accuracy</h2><p class="muted">No history yet — first snapshot saved today.</p>'
    df = pd.read_csv(history_path)
    if len(df) < 2:
        return (f'<h2>📈 Prediction Accuracy</h2>'
                f'<p class="muted">Tracking started — '
                f'{len(df)} snapshot{"s" if len(df) != 1 else ""} logged. '
                f'Accuracy chart populates as matchup periods complete.</p>')
    # Keep only one entry per (period, date)
    # Some legacy rows used ISO-week strings (e.g. "2025-W02") for the date
    # column; coerce and drop those so a single bad row can't kill the build.
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date')
    out = ['<h2>📈 Prediction Accuracy History</h2>',
           '<table><thead><tr><th>Period</th><th>Date</th><th>My WTD</th>'
           '<th>My Projected</th><th>Opp WTD</th><th>Opp Projected</th>'
           '<th>Win Prob</th></tr></thead><tbody>']
    for _, r in df.tail(20).iterrows():
        out.append(
            f'<tr><td>{int(r["period"])}</td><td>{r["date"].strftime("%m/%d")}</td>'
            f'<td>{r["my_wtd"]:.1f}</td><td><b>{r["my_projected_total"]:.1f}</b></td>'
            f'<td>{r["opp_wtd"]:.1f}</td><td><b>{r["opp_projected_total"]:.1f}</b></td>'
            f'<td>{r["win_probability"]*100:.1f}%</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def log_prediction(mu, my_total, opp_total, win_prob, today, model_version='baseline'):
    """Append current prediction to predictions_history.csv.

    `model_version` distinguishes which projection iteration produced this
    snapshot — 'baseline' (adjusters OFF, production) or 'MA_v1' (full
    adjuster chain). Shadow-logging writes both per build so we accumulate
    paired observations for backtest without flipping live.
    """
    history_path = OUT / 'predictions_history.csv'
    record = {
        'timestamp': datetime.now().isoformat(),
        'date': today.isoformat(),
        'period': mu['period'],
        'my_team': mu['mine'].team_name,
        'opp_team': mu['opp'].team_name,
        'my_wtd': round(mu['my_score'], 2),
        'my_projected_total': round(my_total, 2),
        'opp_wtd': round(mu['opp_score'], 2),
        'opp_projected_total': round(opp_total, 2),
        'win_probability': round(win_prob, 4),
        'model_version': model_version,
        # actuals backfilled post-period by fetch_closed_matchup_actuals.py
        'actual_my_final': pd.NA,
        'actual_opp_final': pd.NA,
    }
    if history_path.exists():
        df = pd.read_csv(history_path)
        # Ensure new schema columns exist (graceful migration for old rows)
        for c in ('model_version', 'actual_my_final', 'actual_opp_final'):
            if c not in df.columns: df[c] = pd.NA
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    else:
        df = pd.DataFrame([record])
    df.to_csv(history_path, index=False)
    print(f'  logged prediction ({model_version}) → predictions_history.csv ({len(df)} total entries)')


def win_probability(my_proj_total, opp_proj_total, my_sigma2, opp_sigma2):
    """P(my_team > opp) — normal-approx. Thin adapter over the tested seam in
    plv_clone.matchup_projection."""
    return _mproj.win_prob_normal(my_proj_total, opp_proj_total, my_sigma2, opp_sigma2)


def win_probability_bootstrap(my_proj, opp_proj, my_wtd, opp_wtd, n_trials=5000):
    """Monte-Carlo win prob (lognormal per-player marginals). Thin adapter over
    the tested seam; unpacks the player dicts into (mean, var) tuples."""
    my_players = [(p['fp'], p['sigma2']) for p in my_proj.values()]
    opp_players = [(p['fp'], p['sigma2']) for p in opp_proj.values()]
    return _mproj.win_prob_bootstrap(my_players, opp_players, my_wtd, opp_wtd,
                                     n_trials=n_trials, seed=42)


def render_boom_bust_scan(my_lineup, opp_lineup):
    """🎯 Boom / Bust Scan — week-ahead layered-tag bird's-eye view.

    Iterates every rostered SP + hitter on BOTH sides (Ligers + opponent)
    and computes the layered display tags. Surfaces:

      * 🎯 High-conviction lines  — SP boom_stack >= 2, or hitter stack >= 2,
        or HIGH-K ARM + elite framer pairing.
      * ⚠ Downside-risk lines    — anti_predictive_skill_spike, framing tax,
        IL_RETURN, or boom_stack=0 in a tough matchup.

    Intentionally additive — does NOT alter projections or cap math. Pure
    visualization of today's layered-tag library output applied to the
    matchup snapshot.
    """
    if not _LAYERED_TAGS_AVAILABLE:
        return ('<h2>🎯 Boom / Bust Scan</h2>'
                '<p class="muted">Layered tags unavailable (lib import failed).</p>')
    try:
        # Resolve all relevant pitchers' mlbam + team once.
        sps = []
        for side, lineup in (('mine', my_lineup), ('opp', opp_lineup)):
            for p in lineup:
                if detect_pitcher_role(p) != 'SP':
                    continue
                if is_il_player(p):
                    # IL'd SPs are not pitching this week — skip.
                    continue
                pid = _resolve_pitcher_mlbam(p.name, team=(p.proTeam or None), role='SP')
                if not pid:
                    continue
                team_abbr = (p.proTeam or '').upper()
                sps.append({'side': side, 'name': p.name, 'team': team_abbr,
                            'mlbam': int(pid)})

        hitters = []
        for side, lineup in (('mine', my_lineup), ('opp', opp_lineup)):
            for p in lineup:
                if (p.position or '') in ('SP', 'RP', 'P'):
                    continue
                if is_il_player(p):
                    continue
                team_abbr = (p.proTeam or '').upper()
                # Collision-safe (Max Muncy LAD vs ATH): resolve KNOWN_COLLISIONS
                # hitters by team via resolve_id; non-colliding names keep the fast
                # name lookup byte-identical. (collision fix 2026-06-26)
                pid = None
                if p.name in _KNOWN_COLLISIONS:
                    pid = resolve_id(p.name, kind='batter', team=(team_abbr or None),
                                     position=(p.position or None))
                pid = pid or player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)
                if not pid:
                    continue
                hitters.append({'side': side, 'name': p.name, 'team': team_abbr,
                                'mlbam': int(pid), 'pos': p.position or '?'})

        # rp3 row lookup for rank + recform + opp
        from plv_clone.projections import PROJECTIONS as _PROJ
        rp3 = _PROJ.rp3(live_il=True).drop_duplicates('player_name')
        rp3['nk'] = rp3['player_name'].map(_norm)
        rp3_idx = rp3.set_index('nk').to_dict('index')
        # id-keyed index (collision-safe): sp['mlbam'] was resolved safely above, so
        # prefer joining rp3 by pitcher id over the name key (the two Logan Allens /
        # same-name SPs). Falls back to the name key. (collision fix 2026-06-26)
        rp3_by_id = (rp3.dropna(subset=['pitcher'])
                        .assign(_pid=lambda d: d['pitcher'].astype(int))
                        .set_index('_pid').to_dict('index'))

        sp_rows = []
        for sp in sps:
            r = rp3_by_id.get(int(sp['mlbam'])) or rp3_idx.get(_norm(sp['name']), {})
            try:
                rec_form = float(r.get('recency_form_gap')) if pd.notna(r.get('recency_form_gap')) else None
            except Exception:
                rec_form = None
            try:
                rank = int(r.get('rank')) if r.get('rank') is not None and pd.notna(r.get('rank')) else None
            except Exception:
                rank = None
            next_opp = r.get('next_opp_team')
            if isinstance(next_opp, float) and pd.isna(next_opp):
                next_opp = None
            bs = compute_boom_stack(sp['mlbam'], rec_form,
                                    next_opp if isinstance(next_opp, str) else None,
                                    rp3_rank=rank) or {}
            hk = compute_high_k_pitcher(sp['mlbam']) or {}
            cf = compute_catcher_framing(sp['team']) or {}
            il = compute_il_return_flag(sp['mlbam']) or {}
            sp_rows.append({**sp,
                'boom_stack': bs.get('boom_stack'),
                'tier': bs.get('tier'),
                'boom_rate': bs.get('boom_rate_expected'),
                'bust_rate': bs.get('bust_rate_expected'),
                'anti_pred': bool(bs.get('skill_spike_anti_predictive')),
                'is_high_k': bool(hk.get('is_high_k')),
                'is_elite_framer': bool(cf.get('is_elite_framer')),
                'is_framing_tax': bool(cf.get('is_framing_tax')),
                'is_il_return': bool(il.get('is_first_back_long_il')),
            })

        h_rows = []
        for ht in hitters:
            try:
                hbs = compute_hitter_boom_stack(
                    batter_id=ht['mlbam'], opp_sp_id=None,
                    team=ht['team']) or {}
            except Exception as e:
                _warn_except(f'boom_scan.hitter_stack.{ht.get("name", "?")}', e)
                hbs = {}
            h_rows.append({**ht,
                'boom_stack': hbs.get('boom_stack'),
                'boom_rate': hbs.get('boom_rate_expected'),
                'bust_rate': hbs.get('bust_rate_expected'),
                'components': hbs.get('components') or {},
            })

        # Pure verdict kernels live in matchup_projection (R2-3) — tested there.
        _verdict_sp = _mproj.boom_verdict_sp
        _verdict_hit = _mproj.boom_verdict_hit

        # Conviction list (combined SP + hitter), downside list.
        conv_sp = [r for r in sp_rows
                   if (r['boom_stack'] or 0) >= 2 or r['is_high_k']]
        conv_sp.sort(key=lambda r: (-(r['boom_stack'] or 0), -int(r['is_high_k'])))
        risk_sp = [r for r in sp_rows
                   if r['anti_pred'] or r['is_framing_tax'] or r['is_il_return']]

        conv_h = [r for r in h_rows if (r['boom_stack'] or 0) >= 2]
        conv_h.sort(key=lambda r: -(r['boom_stack'] or 0))

        # Render
        out = ['<h2>🎯 Boom / Bust Scan <small class="muted">(layered tags · week ahead)</small></h2>']
        out.append('<p class="notes">Bird\'s-eye view of today\'s layered-tag library applied to '
                   'both rosters. Additive — does not alter projections.</p>')

        # ----- High-conviction SP -----
        out.append('<h3 style="margin-top:.6em">🎯 High-conviction SPs</h3>')
        if conv_sp:
            out.append('<table><thead><tr>'
                       '<th>Side</th><th>Pitcher</th><th>Team</th>'
                       '<th>boom_stack</th><th>tier</th><th>boom%</th><th>Flags</th>'
                       '</tr></thead><tbody>')
            for r in conv_sp[:12]:
                stars = ('✦' * (r['boom_stack'] or 0)) + ('·' * (4 - (r['boom_stack'] or 0)))
                br = f"{r['boom_rate']*100:.0f}%" if r['boom_rate'] is not None else '—'
                tags = ' '.join(_verdict_sp(r))
                side_cls = 'pos' if r['side'] == 'mine' else 'muted'
                out.append(
                    f'<tr><td class="{side_cls}">{("YOURS" if r["side"]=="mine" else "OPP")}</td>'
                    f'<td>{player_link(r["name"], mlbam=r.get("mlbam"))}</td>'
                    f'<td>{h(r["team"])}</td>'
                    f'<td>{stars} <small>{r["boom_stack"] or 0}/4</small></td>'
                    f'<td>{h(str(r["tier"] or "—"))}</td>'
                    f'<td>{br}</td>'
                    f'<td>{h(tags)}</td></tr>'
                )
            out.append('</tbody></table>')
        else:
            out.append('<p class="muted">No SPs at boom_stack&gt;=2 or HIGH-K this week.</p>')

        # ----- Downside-risk SP -----
        out.append('<h3 style="margin-top:.6em">⚠ Downside-risk SPs</h3>')
        if risk_sp:
            out.append('<table><thead><tr>'
                       '<th>Side</th><th>Pitcher</th><th>Team</th>'
                       '<th>bust%</th><th>Flags</th>'
                       '</tr></thead><tbody>')
            for r in risk_sp[:12]:
                bu = f"{r['bust_rate']*100:.0f}%" if r['bust_rate'] is not None else '—'
                flags = []
                if r['anti_pred']: flags.append('⛔ anti-predictive')
                if r['is_framing_tax']: flags.append('⚠ framing-tax')
                if r['is_il_return']: flags.append('🏥 IL-return')
                side_cls = 'neg' if r['side'] == 'mine' else 'muted'
                out.append(
                    f'<tr><td class="{side_cls}">{("YOURS" if r["side"]=="mine" else "OPP")}</td>'
                    f'<td>{player_link(r["name"], mlbam=r.get("mlbam"))}</td>'
                    f'<td>{h(r["team"])}</td>'
                    f'<td>{bu}</td>'
                    f'<td>{" · ".join(flags)}</td></tr>'
                )
            out.append('</tbody></table>')
        else:
            out.append('<p class="muted">No SP downside flags this week.</p>')

        # ----- Conviction hitters -----
        out.append('<h3 style="margin-top:.6em">✨ High-conviction Hitters</h3>')
        if conv_h:
            out.append('<table><thead><tr>'
                       '<th>Side</th><th>Hitter</th><th>Pos</th><th>Team</th>'
                       '<th>boom_stack</th><th>boom%</th><th>Flags</th>'
                       '</tr></thead><tbody>')
            for r in conv_h[:14]:
                stars = ('✦' * (r['boom_stack'] or 0)) + ('·' * (4 - (r['boom_stack'] or 0)))
                br = f"{r['boom_rate']*100:.0f}%" if r['boom_rate'] is not None else '—'
                tags = ' '.join(_verdict_hit(r))
                side_cls = 'pos' if r['side'] == 'mine' else 'muted'
                out.append(
                    f'<tr><td class="{side_cls}">{("YOURS" if r["side"]=="mine" else "OPP")}</td>'
                    f'<td>{player_link(r["name"], mlbam=r.get("mlbam"))}</td>'
                    f'<td>{h(r["pos"])}</td>'
                    f'<td>{h(r["team"])}</td>'
                    f'<td>{stars} <small>{r["boom_stack"] or 0}/4</small></td>'
                    f'<td>{br}</td>'
                    f'<td>{h(tags)}</td></tr>'
                )
            out.append('</tbody></table>')
        else:
            out.append('<p class="muted">No hitters at boom_stack&gt;=2 today (lineup amp / skill spike all quiet).</p>')

        return '\n'.join(out)
    except Exception as e:
        return _section_error('🎯 Boom / Bust Scan', e)


def render_team_table(label, lineup, wtd_score, projections, capped_fp=0,
                      bs_actuals: dict | None = None,
                      bs_h_actuals: dict | None = None):
    rows = []
    for p in lineup:
        proj = projections.get(p.name, {'fp': 0, 'units': 0, 'breakdown': [], 'badges': []})
        wtd = p.points or 0
        badges = list(proj['badges'])
        bs_starts = []
        bs_games = []
        pos = (p.position or '').upper()
        # Bridge inject: if ESPN WTD is 0 but the boxscore bridge has data this
        # week, show bridge FP so the dashboard reflects reality before ESPN's
        # morning score update. Never overrides a non-zero ESPN score.
        if wtd == 0:
            nk = _norm(p.name)
            if pos == 'SP' and bs_actuals:
                bs = bs_actuals.get(nk)
                if bs and bs['fp'] > 0:
                    wtd = bs['fp']
                    bs_starts = bs['starts']
                    badges.append('📋 bridge')
            elif pos not in ('SP', 'RP', 'P') and bs_h_actuals:
                bs = bs_h_actuals.get(nk)
                if bs and bs['fp'] > 0:
                    wtd = bs['fp']
                    bs_games = bs['games']
                    badges.append('📋 bridge')
        rows.append({
            'name': p.name, 'pos': p.position or '?',
            'wtd': wtd,
            'rest': proj['fp'],
            'units': proj['units'],
            'total': wtd + proj['fp'],
            'breakdown': proj['breakdown'],
            'badges': badges,
            'bs_starts': bs_starts,
            'bs_games': bs_games,
        })
    rows.sort(key=lambda r: -r['total'])
    total_rest = sum(r['rest'] for r in rows)
    total_proj = wtd_score + total_rest

    out = [f'<h2>{h(label)} '
           f'<span class="totals">WTD <b class="wtd">{wtd_score:.1f}</b> · '
           f'rest <b class="proj">{total_rest:.1f}</b>'
           f'{f" <small>(−{capped_fp:.1f} capped)</small>" if capped_fp > 0 else ""} · '
           f'total <b class="total">{total_proj:.1f}</b></span></h2>']
    out.append('<table class="player-table" data-cols="roster" data-col-lock="2"><thead><tr>'
                '<th>Player</th><th>Pos</th><th>WTD</th>'
                '<th>Units</th><th>Rest</th><th>Total</th><th></th></tr></thead><tbody>')
    for r in rows:
        wtd_cls = 'pos' if r['wtd'] > 0 else ('neg' if r['wtd'] < 0 else 'zero')
        if r['pos'] == 'SP':
            unit_label = f'{int(r["units"])} start{"s" if r["units"] != 1 else ""}'
        elif r['pos'] in ('RP', 'P'):
            unit_label = f'~{r["units"]:.1f} app'
        else:
            unit_label = f'{int(r["units"])} games'
        if r['units'] == 0:
            unit_label = '—'
        badges = ' '.join(f'<span class="badge">{h(b)}</span>' for b in r['badges'])
        out.append(f'<tr><td data-label="Player">{player_link(r["name"])}{(" " + badges) if badges else ""}</td>'
                   f'<td data-label="Pos">{h(r["pos"])}</td>'
                   f'<td data-label="WTD" class="{wtd_cls}">{r["wtd"]:+.1f}</td>'
                   f'<td data-label="Units" class="muted">{unit_label}</td>'
                   f'<td data-label="Rest">{r["rest"]:+.1f}</td>'
                   f'<td data-label="Total"><b>{r["total"]:+.1f}</b></td><td></td></tr>')
        if r.get('bs_starts'):
            for s in r['bs_starts']:
                ip_f = float(s['ip'])
                ip_disp = f"{int(ip_f)}.{int(round((ip_f % 1) * 3))}" if ip_f % 1 else f"{int(ip_f)}.0"
                out.append(f'<tr class="breakdown"><td colspan="7">'
                           f'→ 📋 {s["date"][5:]} actual: {ip_disp}IP {s["so"]}K '
                           f'<b>{s["fp"]:.1f} FP</b> (boxscore bridge)</td></tr>')
        if r.get('bs_games'):
            for g in r['bs_games']:
                out.append(f'<tr class="breakdown"><td colspan="7">'
                           f'→ 📋 {g["date"][5:]} actual: {g["r"]}R {g["tb"]}TB {g["rbi"]}RBI '
                           f'<b>{g["fp"]:.1f} FP</b> (boxscore bridge)</td></tr>')
        if r['breakdown']:
            for b in r['breakdown']:
                if b.get('type') == 'start':
                    cap_marker = ' <span class="capped">⚠ CAPPED</span>' if b.get('fp_capped') else ''
                    # Confirmed probable (✓) vs rotation-gap prediction (~)
                    conf_marker = ('✓' if b.get('confirmed', True) else
                                   '<span class="muted" title="rotation-gap prediction — not yet confirmed probable">~</span>')
                    txt = (f'{conf_marker} {b["date"][5:]} vs {b["opp"]} '
                           f'(opp bat {b["opp_idx"]:.2f}, ×{b["factor"]:.2f}, '
                           f'<b>{b.get("fp_original", b["fp"]):.1f} FP</b>){cap_marker}')
                    out.append(f'<tr class="breakdown"><td colspan="7">→ {txt}</td></tr>')
                elif b.get('type') == 'game':
                    opp_sp_s = ''
                    if b.get('opp_sp') and b.get('opp_sp') != '?':
                        opp_proj_s = f', {b["opp_sp_proj"]:.1f} FP/start' if b.get('opp_sp_proj') else ''
                        opp_sp_s = f' (vs {b["opp_sp"]}{opp_proj_s})'
                    txt = f'{b["date"][5:]} vs {b["opp"]}{opp_sp_s} · ×{b["factor"]:.2f} = {b["fp"]:.1f}'
                    out.append(f'<tr class="breakdown"><td colspan="7">→ {txt}</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out), total_rest, total_proj


def main():
    # MA0-MA7 adjuster gating: default OFF for production builds.
    # Set ADJUSTERS_ON=1 environment variable OR pass --with-adjusters to enable.
    import os, argparse
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument('--with-adjusters', action='store_true',
                          help='Enable MA0-MA7 accuracy adjuster chain (default OFF — pending validation)')
    _parser.add_argument('--no-bootstrap', action='store_true',
                          help='Use normal-approx CDF for win-prob (default: lognormal MC simulation)')
    _parser.add_argument('-h', '--help', action='store_true')
    _args, _ = _parser.parse_known_args()
    if _args.help:
        _parser.print_help(); return
    # Adjuster toggles are local; the adjuster DATA is bundled into a frozen
    # Adjusters value (built below) and threaded into project_player — no module
    # globals, no mid-run mutation. See plv_clone.matchup_projection.Adjusters.
    _ADJUSTERS_ON = _args.with_adjusters or os.environ.get('ADJUSTERS_ON') == '1'
    _USE_BOOTSTRAP = (not _args.no_bootstrap) and os.environ.get('WIN_PROB_BOOTSTRAP') != '0'
    # MA2 sub-toggles default to master flag (#6 — can be split independently
    # later via env vars if MAE shows one direction net-helps but the other doesn't)
    _ma2_hitter_on = _ADJUSTERS_ON and os.environ.get('MA2_HITTER_OFF') != '1'
    _ma2_sp_on = _ADJUSTERS_ON and os.environ.get('MA2_SP_OFF') != '1'

    print('Loading matchup + projections...')
    mu = get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map = load_projections()

    def _load_adjuster_maps(on: bool):
        """Load the adjuster data maps for the given toggle state. Returns a
        dict of the per-map locals; momentum + rp_app_rates are added by the
        caller (they don't depend on the toggle)."""
        if on:
            hitter_form, sp_form = load_recent_form_maps()  # SP form only used now
            return dict(hitter_form=hitter_form, sp_form=sp_form,
                        lineup=load_lineup_map(), park=load_park_factors(),
                        psplit=load_pitcher_splits(), bat_side=load_bat_side_map(),
                        il_returns=load_il_returns(mu), calib=load_calibration_scalar())
        # Calibration scalar is fit on baseline projections — safe to apply here.
        # The double-correction warning applies to applying a baseline-fit scalar
        # on top of post-adjuster projections, not the other direction.
        return dict(hitter_form={}, sp_form={}, lineup={}, park={}, psplit={},
                    bat_side={}, il_returns={}, calib=load_calibration_scalar())

    # RP appearance rates are objective data (not an adjuster) — always load.
    rp_app_rates = load_rp_appearance_rates()
    print(f'  RP appearance rates loaded: {len(rp_app_rates)} pitchers from boxscore')
    _maps = _load_adjuster_maps(_ADJUSTERS_ON)
    if _ADJUSTERS_ON:
        print(f'  ⚙ ADJUSTERS ON  MA2_hitter={_ma2_hitter_on} MA2_sp={_ma2_sp_on}  '
              f'caches: sp_form={len(_maps["sp_form"])} lineup={len(_maps["lineup"])} '
              f'pitcher_splits={len(_maps["psplit"])} bat_side={len(_maps["bat_side"])} '
              f'il_returns={len(_maps["il_returns"])} calib={_maps["calib"]:.3f}')
    else:
        print(f'  ⚙ ADJUSTERS OFF (baseline xfp model only) calib={_maps["calib"]:.3f}')
    today = _today_et()
    # Period-aware SP cap AND projection window (cap 2026-07-11; window
    # 2026-07-30): both come from the ONE shared resolver — matchup.html shows
    # the same cap and projects the same date span as /matchup-leverage and
    # /roster-audit (ASG period 15 → cap 16 over Jul 6–19, 2-week playoff
    # round → cap 20 over 14 days, normal week → cap 10 over Mon–Sun). The
    # window used to be a flat Mon..Mon+6 calendar week regardless of period
    # length, truncating every multi-week projection (pwin_mean_bias memo §5);
    # derive_projection_window() is the tested seam that keeps this fixed.
    week_start, week_end, days_remaining_in_week, _pmeta = \
        derive_projection_window(mu['league_obj'], mu['period'], today)
    sp_cap = _pmeta['sp_cap']
    try:
        _banked_meta = espn_period_meta(
            mu['league_obj'], mu['period'],
            getattr(mu['mine'], 'team_id', None),
            getattr(mu['opp'], 'team_id', None))
    except Exception as _e:
        print(f'  ⚠ ESPN banked-count fetch failed ({_e}); cap display uses this-week counts')
        _banked_meta = {}
    _banked_mine = _banked_meta.get('my_banked')
    if sp_cap != MAX_SP_STARTS_PER_WEEK or _pmeta['weeks'] > 1:
        print(f'  period {mu["period"]} SP cap {sp_cap} '
              f'({_pmeta["weeks"]}-week, {_pmeta["week_start"]}→{_pmeta["week_end"]}); '
              f'banked mine {_banked_mine}')

    # Boxscore bridge: load actuals for any SP starts already played this week
    # (week_start through yesterday). Injected into render_team_table when
    # ESPN WTD is still 0 — bridges the ~few-hour lag before ESPN scores games.
    yesterday = today - timedelta(days=1)
    bs_week   = _load_bs_week_actuals(week_start, yesterday)        if week_start <= yesterday else {}
    bs_h_week = _load_bs_week_hitter_actuals(week_start, yesterday) if week_start <= yesterday else {}

    # Within-week Bayesian momentum: compare each player's actual FP/game so
    # far this week to their model projection. λ=0.15 shrinkage applied inside.
    weekly_momentum = compute_weekly_momentum(
        bs_h_week, rh3_map, bs_week=bs_week, rp3_map=rp3_map)
    if weekly_momentum:
        print(f'  weekly momentum: {len(weekly_momentum)} players have mid-week form signal')

    # Bundle all adjuster data into one frozen value (R2-1). project_player reads
    # from this instead of module globals; the shadow A/B pass below builds a
    # SECOND value rather than mutating shared state.
    def _build_adjusters(on, maps):
        return _mproj.Adjusters(
            adjusters_on=on,
            ma2_hitter_on=(on and os.environ.get('MA2_HITTER_OFF') != '1'),
            ma2_sp_on=(on and os.environ.get('MA2_SP_OFF') != '1'),
            calib=maps['calib'], sp_form=maps['sp_form'], hitter_form=maps['hitter_form'],
            lineup=maps['lineup'], park=maps['park'], psplit=maps['psplit'],
            bat_side=maps['bat_side'], il_returns=maps['il_returns'],
            rp_app_rates=rp_app_rates, weekly_momentum=weekly_momentum)
    adj = _build_adjusters(_ADJUSTERS_ON, _maps)

    print(f'  matchup period: {mu["period"]}')
    print(f'  week: {week_start} → {week_end} (today: {today})')
    print(f'  Ligers WTD: {mu["my_score"]:.1f}  |  Opp WTD: {mu["opp_score"]:.1f}')

    # Fetch schedules — primary source is ESPN's proGamesByScoringPeriod
    # (same data ESPN uses in their UI → our team-game-day counts match theirs).
    # Falls back to MLB Stats API if ESPN schedule returns empty.
    print(f'  fetching schedules from ESPN proGamesByScoringPeriod...')
    schedules_by_team = fetch_espn_week_schedule(mu['league_obj'], week_start, week_end)
    if not schedules_by_team:
        # Fallback: MLB Stats API team schedule
        all_teams = set()
        for p in mu['my_lineup'] + mu['opp_lineup']:
            t = (p.proTeam or '').upper()
            if t: all_teams.add(t)
        team_ids = {ESPN_TO_MLB_TEAM[t] for t in all_teams if t in ESPN_TO_MLB_TEAM}
        print(f'  ⚠ ESPN schedule empty — falling back to MLB Stats API ({len(team_ids)} teams)')
        schedules_by_team = fetch_schedules_by_team(
            team_ids, today.isoformat(), week_end.isoformat())
        # Zero-game-week guard (audit 2026-07-04): API failure returns a TRUTHY
        # dict of empty lists -> every projection collapses to 0 and PUBLISHES.
        if schedules_by_team and sum(len(v) for v in schedules_by_team.values()) == 0:
            raise RuntimeError('fetch_schedules_by_team returned ZERO games for the week - refusing to publish a zeroed matchup page')
    else:
        n_teams = len(schedules_by_team)
        n_games = sum(len(v) for v in schedules_by_team.values())
        print(f'  ESPN schedule: {n_teams} teams, {n_games} game-slots this week')

    # Resolve mlbam for all rostered SPs; precompute their full SP-start lists
    # (confirmed probables + rotation-gap predictions) via
    # plv_clone.mlb_stats.fetch_week_probables.
    sp_pitcher_ids = set()
    for p in mu['my_lineup'] + mu['opp_lineup']:
        inj_p = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
        # Skip only true IL/out states. A DAY_TO_DAY pitcher with a scheduled
        # start still pitches (Soriano 2026: DTD but a confirmed probable), so
        # DTD must NOT drop him from the week's SP-start projection.
        if inj_p in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
                     'INJURY_RESERVE', 'OUT'):
            continue
        pid_sp = _resolve_pitcher_mlbam(p.name, team=(getattr(p, 'proTeam', None) or None), role='SP')
        if not pid_sp:
            continue
        # detect_pitcher_role MUST get the MLBAM id — without it a dual-eligible
        # starter (Detmers: ESPN position='RP' but 15 GS) can't be resolved via
        # gamesStarted and silently falls back to the stale 'RP' tag (gotcha #8).
        if detect_pitcher_role(p, mlbam_id=int(pid_sp)) != 'SP':
            continue
        sp_pitcher_ids.add(int(pid_sp))
    print(f'  resolving rotation for {len(sp_pitcher_ids)} healthy SPs...')
    sp_starts_by_pitcher = build_sp_starts_by_pitcher(
        sp_pitcher_ids, schedules_by_team, today, week_end)

    # Project each player
    print('  projecting (schedule + opp-SP + role + cap aware)...')
    my_proj = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                         rh3_map, rp3_map, rp3_by_mlbam,
                                         rprs2_map, ts_map, today, week_end, adj=adj)
               for p in mu['my_lineup']}
    opp_proj = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                          rh3_map, rp3_map, rp3_by_mlbam,
                                          rprs2_map, ts_map, today, week_end, adj=adj)
                for p in mu['opp_lineup']}

    # Apply SP cap (period-aware: 10/week, 16 for the ASG period, 20 for a
    # 2-week playoff round). A single week's ≤~7 starts fall under a 16/20 cap
    # — so nothing is wrongly zeroed during a multi-week period.
    my_capped = apply_sp_cap(my_proj, cap=sp_cap)
    opp_capped = apply_sp_cap(opp_proj, cap=sp_cap)
    if my_capped > 0: print(f'  Ligers SP cap removed {my_capped:.1f} FP')
    if opp_capped > 0: print(f'  Opp SP cap removed {opp_capped:.1f} FP')

    # Summarise confirmed vs rotation-gap predicted starts
    my_conf = sum(1 for p in my_proj.values()
                  for b in p.get('breakdown', [])
                  if b.get('type') == 'start' and b.get('confirmed', True))
    my_pred = sum(1 for p in my_proj.values()
                  for b in p.get('breakdown', [])
                  if b.get('type') == 'start' and not b.get('confirmed', True))
    my_total_starts = my_conf + my_pred
    pred_note = f' + {my_pred} rotation-gap predicted' if my_pred else ''
    print(f'  SP starts: {my_conf} confirmed{pred_note} = {my_total_starts}/{sp_cap} cap')

    # Team totals + variance — SLOT-AWARE (2026-06-03, updated 2026-06-15).
    # Exclude only true IL/IR slots. BE is treated as active because the
    # roster owner manages lineup daily — every healthy bench player gets
    # activated before lock. IL/DTD zeroing is handled inside project_player
    # via injuryStatus, not slot. Keep `my_proj` / `opp_proj` intact for
    # downstream consumers (render tables, IL warnings, days-of-fire scan).
    my_active = {p.name: my_proj[p.name] for p in mu['my_lineup']
                 if _is_active_slot(p) and p.name in my_proj}
    opp_active = {p.name: opp_proj[p.name] for p in mu['opp_lineup']
                  if _is_active_slot(p) and p.name in opp_proj}

    my_rest_all = sum(p['fp'] for p in my_proj.values())
    opp_rest_all = sum(p['fp'] for p in opp_proj.values())
    my_rest = sum(p['fp'] for p in my_active.values())
    opp_rest = sum(p['fp'] for p in opp_active.values())
    print(f'  [slot-aware] my_total: {mu["my_score"] + my_rest_all:.1f} '
          f'(all-rostered) -> {mu["my_score"] + my_rest:.1f} (active-only)')
    print(f'  [slot-aware] opp_total: {mu["opp_score"] + opp_rest_all:.1f} '
          f'(all-rostered) -> {mu["opp_score"] + opp_rest:.1f} (active-only)')

    my_total = mu['my_score'] + my_rest
    opp_total = mu['opp_score'] + opp_rest
    my_sigma2 = sum(p['sigma2'] for p in my_active.values())
    opp_sigma2 = sum(p['sigma2'] for p in opp_active.values())
    if _USE_BOOTSTRAP:
        win_prob = win_probability_bootstrap(my_active, opp_active,
                                              mu['my_score'], mu['opp_score'])
        wp_method = 'bootstrap'
    else:
        win_prob = win_probability(my_total, opp_total, my_sigma2, opp_sigma2)
        wp_method = 'normal'

    print(f'\n  Ligers: WTD {mu["my_score"]:.1f} + rest {my_rest:.1f} = {my_total:.1f} '
          f'(σ²={my_sigma2:.0f})')
    print(f'  Opp:    WTD {mu["opp_score"]:.1f} + rest {opp_rest:.1f} = {opp_total:.1f} '
          f'(σ²={opp_sigma2:.0f})')
    print(f'  Win probability ({wp_method}): {win_prob*100:.1f}%')

    # Hetero σ before/after instrumentation (2026-06-03). Recompute σ² as if
    # legacy fixed-σ-per-position were in force, to surface the delta the
    # per-player σ aggregation introduced. This is print-only — doesn't
    # affect logged predictions or the dashboard's published win probability.
    def _legacy_sigma2(proj_dict):
        s2 = 0.0
        for p in proj_dict.values():
            n_starts = sum(1 for b in p.get('breakdown', []) if b.get('type') == 'start')
            n_games = sum(1 for b in p.get('breakdown', []) if b.get('type') == 'game')
            n_rp = sum(b.get('expected_apps', 0)
                       for b in p.get('breakdown', []) if 'role' in b)
            s2 += (n_starts * SIGMA_PER_SP_START ** 2
                   + n_games * SIGMA_PER_HITTER_GAME ** 2
                   + n_rp * SIGMA_PER_RP_GAME ** 2)
        return s2
    legacy_my_s2 = _legacy_sigma2(my_active)
    legacy_opp_s2 = _legacy_sigma2(opp_active)
    legacy_wp = win_probability(my_total, opp_total, legacy_my_s2, legacy_opp_s2)
    print(f'  [hetero-σ delta] legacy σ²: Ligers {legacy_my_s2:.0f} → new {my_sigma2:.0f}; '
          f'Opp {legacy_opp_s2:.0f} → new {opp_sigma2:.0f}')
    print(f'  [hetero-σ delta] legacy WP: {legacy_wp*100:.1f}% → new {win_prob*100:.1f}% '
          f'(Δ {(win_prob - legacy_wp)*100:+.1f} pp)')

    my_block, _, _ = render_team_table(mu['mine'].team_name, mu['my_lineup'],
                                          mu['my_score'], my_proj, my_capped,
                                          bs_actuals=bs_week, bs_h_actuals=bs_h_week)
    opp_block, _, _ = render_team_table(mu['opp'].team_name, mu['opp_lineup'],
                                           mu['opp_score'], opp_proj, opp_capped,
                                           bs_actuals=bs_week, bs_h_actuals=bs_h_week)

    # ---- LINEUP OPTIMIZER ----
    opt_block = render_lineup_optimizer(mu['my_lineup'], my_proj, schedules_by_team,
                                          ESPN_TO_MLB_TEAM)

    # ---- LOG PREDICTION HISTORY ----
    live_version = 'MA_v1' if _ADJUSTERS_ON else 'baseline'
    log_prediction(mu, my_total, opp_total, win_prob, today, model_version=live_version)

    # ---- SHADOW LOG: also write the OTHER version so we accumulate paired data
    # without flipping live behavior. Off-build → shadow-logs MA_v1; on-build → shadow-logs baseline.
    try:
        shadow_on = not _ADJUSTERS_ON
        shadow_version = 'MA_v1' if shadow_on else 'baseline'
        # Build a SECOND Adjusters value for the shadow state — no global
        # mutation, no save/restore. The shadow projection is a pure function of
        # this value (rp_app_rates + weekly_momentum are toggle-independent).
        shadow_adj = _build_adjusters(shadow_on, _load_adjuster_maps(shadow_on))
        # Reproject under shadow state
        my_proj_s = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                              rh3_map, rp3_map, rp3_by_mlbam,
                                              rprs2_map, ts_map, today, week_end, adj=shadow_adj)
                     for p in mu['my_lineup']}
        opp_proj_s = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                                rh3_map, rp3_map, rp3_by_mlbam,
                                                rprs2_map, ts_map, today, week_end, adj=shadow_adj)
                      for p in mu['opp_lineup']}
        apply_sp_cap(my_proj_s, cap=sp_cap); apply_sp_cap(opp_proj_s, cap=sp_cap)
        # Slot-aware filter for shadow log (mirrors live aggregation 2026-06-03)
        my_active_s = {p.name: my_proj_s[p.name] for p in mu['my_lineup']
                       if _is_active_slot(p) and p.name in my_proj_s}
        opp_active_s = {p.name: opp_proj_s[p.name] for p in mu['opp_lineup']
                        if _is_active_slot(p) and p.name in opp_proj_s}
        my_total_s = mu['my_score'] + sum(p['fp'] for p in my_active_s.values())
        opp_total_s = mu['opp_score'] + sum(p['fp'] for p in opp_active_s.values())
        my_sig2_s = sum(p['sigma2'] for p in my_active_s.values())
        opp_sig2_s = sum(p['sigma2'] for p in opp_active_s.values())
        if _USE_BOOTSTRAP:
            wp_s = win_probability_bootstrap(my_active_s, opp_active_s,
                                              mu['my_score'], mu['opp_score'])
        else:
            wp_s = win_probability(my_total_s, opp_total_s, my_sig2_s, opp_sig2_s)
        log_prediction(mu, my_total_s, opp_total_s, wp_s, today, model_version=shadow_version)
    except Exception as e:
        print(f'  ⚠ shadow-log skipped: {e}')

    # ---- ACCURACY HISTORY VIEW ----
    accuracy_block = render_accuracy_history()

    # ---- ADDITIONAL ENHANCEMENT SECTIONS ----
    print('  building enhancement sections...')
    power_block = render_power_rankings()
    # NETWORK DIET (audit 2026-07-04): ONE free_agents(size=2000) fetch + ONE
    # rostered-name walk, threaded into both FA consumers below (was two
    # independent 2000-player fetches + repeated league.teams walks).
    fa_pool, rostered_names = None, None
    try:
        rostered_names = {_norm(p.name)
                          for t in mu['league_obj'].teams for p in t.roster}
        fa_pool = mu['league_obj'].free_agents(size=2000)  # never <2000 (feedback_fa_pool_size_cap.md)
        print(f'  FA pool fetched once: {len(fa_pool)} FAs · {len(rostered_names)} rostered names')
    except Exception as e:
        _warn_except('main.fa_pool_fetch', e)
        fa_pool, rostered_names = None, None  # consumers fall back to their own fetch
    # ---- DECISION CONSOLE (replaced the drop/pickup widget, 2026-07-11) ----
    # Built from main()'s in-hand artifacts — zero roster/FA/schedule/banked
    # refetch. The week ctx deliberately uses THIS PAGE's Mon–Sun planning
    # window (not the full multi-week period window) so the console's week
    # numbers agree with every other table on the page; the period cap +
    # banked count still come from the shared resolver. Lazy import both ways
    # (decision_console imports this module inside functions) — circularity
    # guard.
    try:
        from lib.decision_console import (build_console_data,
                                          render_console_html,
                                          roster_from_lineup)
        _week_ctx = {
            'pmeta': {'period': mu['period'], 'weeks': _pmeta['weeks'],
                      'sp_cap': sp_cap, 'week_start': week_start,
                      'week_end': week_end,
                      'covered': bool(_pmeta.get('covered'))},
            'banked_mine': _banked_mine,
            'schedules_by_team': schedules_by_team,
            'sp_starts_by_pitcher': sp_starts_by_pitcher,
            'today': today, 'source': 'matchup',
            'team_map': dict(ESPN_TO_MLB_TEAM),
        }
        console_data = build_console_data(
            roster=roster_from_lineup(mu['my_lineup'],
                                      il_returns=_maps['il_returns']),
            fas=fa_pool or [], league=mu['league_obj'],
            my_team_id=getattr(mu['mine'], 'team_id', None),
            week_ctx=_week_ctx, source='matchup',
            # reuse this module's collision-safe resolver (CSV caches + API
            # fallback + in-process cache) instead of the CSV-only default
            id_resolver=lambda name, team=None, role=None:
                _resolve_pitcher_mlbam(name, team=team, role=role))
        (OUT / 'console_data.json').write_text(
            json.dumps(console_data), encoding='utf-8')
        print(f'  decision console: {sum(len(b["players"]) for b in console_data["buckets"])} rows, '
              f'{len(console_data["headline_recs"])} headline recs -> console_data.json')
        console_block = render_console_html(
            console_data, theme='matchup', page_key='matchup',
            default_axis='week')
    except Exception as e:
        _warn_except('decision_console', e)
        console_block = ('<p class="muted">⚠ decision console unavailable '
                         f'this build ({type(e).__name__}: {h(str(e))})</p>')
    streamer_block = render_2start_gems(schedules_by_team, today, week_end,
                                        fas=fa_pool, rostered=rostered_names)
    boom_bust_block = render_boom_bust_scan(mu['my_lineup'], mu['opp_lineup'])
    cap_block = render_cap_status(my_proj, mu['my_lineup'], week_start, today,
                                    league=mu['league_obj'],
                                    my_team_name=mu['mine'].team_name,
                                    cap=sp_cap, banked_espn=_banked_mine,
                                    pmeta=_pmeta)
    closer_block = render_closer_tracker()
    diff_block = render_snapshot_diff()
    ci_block = render_ci_bands(my_total, my_sigma2, opp_total, opp_sigma2)
    action_items_block = synthesize_action_items(my_proj, mu['my_lineup'],
                                                    schedules_by_team, win_prob,
                                                    cap=sp_cap)
    gauge_html = render_win_prob_gauge(win_prob)
    fire_block = render_days_of_fire(my_proj)
    playoff_block = render_playoff_simulation(current_period=mu['period'])
    pos_comp_block = render_position_competition(rh3_map)
    injury_block = render_injury_alerts(mu['my_lineup'])
    trend_block = render_trend_watch(mu['my_lineup'])

    current_gap = mu['my_score'] - mu['opp_score']
    proj_gap = my_total - opp_total
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Win-prob bar color
    if win_prob >= 0.7: win_class = 'pos'
    elif win_prob >= 0.55: win_class = 'lean-pos'
    elif win_prob >= 0.45: win_class = 'toss'
    elif win_prob >= 0.30: win_class = 'lean-neg'
    else: win_class = 'neg'

    html = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ligers Weekly Matchup</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:wght@400;600;700&display=swap" rel="stylesheet">
<style>
{theme_css()}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{ font-family: 'Source Serif 4', 'Iowan Old Style', Georgia, serif;
       background: var(--bg); color: var(--text);
       font-size: 16px; line-height: 1.6; }}
.wrap {{ max-width: none; width: 100%; margin: 0; padding: 0 2em 4em 2em; }}
@media (min-width: 1600px) {{ .wrap {{ padding: 0 3em 4em 3em; }} }}
@media (min-width: 2100px) {{ .wrap {{ padding: 0 4em 4em 4em; }} }}
.notes, p {{ max-width: 95ch; }}
.mono {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; }}

header {{ border-bottom: 1px solid var(--border); padding: .9em 0;
         margin-bottom: 1em; position: sticky; top: 0;
         background: var(--bg); z-index: 100; }}
.header-row {{ display: flex; justify-content: space-between; align-items: baseline;
              flex-wrap: wrap; gap: 1.2em; }}
h1 {{ color: var(--accent); margin: 0; font-size: 2em; font-weight: 700;
     letter-spacing: .01em; line-height: 1.15;
     font-family: 'Source Serif 4', Georgia, serif; }}
h2 {{ color: var(--text); margin-top: 2em; font-size: 1.5em; font-weight: 600;
     border-bottom: 1px solid var(--border); padding-bottom: .35em;
     letter-spacing: .01em; line-height: 1.2;
     font-family: 'Source Serif 4', Georgia, serif; }}
h2 .totals {{ float: right; font-size: 0.6em; font-weight: 400; color: var(--dim);
             font-family: 'IBM Plex Mono', monospace; }}
h2 .totals b {{ color: var(--text); }}
h2 .totals .wtd {{ color: var(--pos); }}
h2 .totals .proj {{ color: var(--accent); }}
h2 .totals .total {{ color: var(--accent); font-size: 1.2em; }}

{topnav_css()}

.scoreboard {{ background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
              padding: 1.5em; margin: 1em 0; }}
.score-grid {{ display: grid; grid-template-columns: 1fr 0.3fr 1fr; gap: 1em;
              text-align: center; align-items: center; }}
.score-team .name {{ color: var(--dim); font-size: .85em; margin-bottom: .3em;
                    font-family: 'IBM Plex Mono', monospace;
                    text-transform: uppercase; letter-spacing: .1em; }}
.score-team .wtd {{ font-size: 2.5em; font-weight: 700; color: var(--pos);
                    font-family: 'Source Serif 4', Georgia, serif;
                    font-variant-numeric: tabular-nums; }}
.score-team.opp .wtd {{ color: var(--neg); }}
.score-team .proj {{ font-size: .85em; color: var(--dim); margin-top: .3em;
                    font-family: 'IBM Plex Mono', monospace; }}
.score-team .total-final {{ font-size: 1.4em; color: var(--accent); font-weight: 700;
                            font-family: 'Source Serif 4', Georgia, serif; }}
.vs {{ font-size: 1.5em; color: var(--dim);
       font-family: 'IBM Plex Mono', monospace; }}
.win-bar {{ margin-top: 1.5em; padding-top: 1em; border-top: 1px solid var(--border); }}
.win-bar-label {{ text-align: center; margin-bottom: .5em; font-size: 1.1em;
                 font-family: 'IBM Plex Mono', monospace; }}
.win-bar-label .pct {{ font-weight: 700; font-size: 1.5em;
                       font-family: 'Source Serif 4', Georgia, serif; }}
.win-bar-label .pos {{ color: var(--pos); }}
.win-bar-label .lean-pos {{ color: var(--pos); opacity: .85; }}
.win-bar-label .toss {{ color: var(--warn); }}
.win-bar-label .lean-neg {{ color: var(--neg); opacity: .85; }}
.win-bar-label .neg {{ color: var(--neg); }}
.win-bar-track {{ height: 14px; background: var(--stripe); border-radius: 7px; overflow: hidden;
                 border: 1px solid var(--faint); }}
.win-bar-fill {{ height: 100%; background: linear-gradient(90deg, var(--pos), var(--warn) 50%, var(--neg)); }}
.gap-row {{ text-align: center; margin-top: 1em; font-size: 1em; color: var(--dim);
           font-family: 'IBM Plex Mono', monospace; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.2em;
        font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .87em; }}
th {{ background: var(--panel); padding: .65em .8em; text-align: left;
      border-bottom: 1px solid var(--border); border-top: 1px solid var(--border);
      font-weight: 600; color: var(--dim);
      text-transform: uppercase; font-size: .72em; letter-spacing: .12em;
      font-family: 'IBM Plex Mono', monospace; }}
td {{ padding: .55em .8em; border-bottom: 1px solid var(--faint);
      font-variant-numeric: tabular-nums; }}
tr.breakdown td {{ color: var(--dim); font-size: .8em; padding-left: 2em;
                    border-bottom: 1px dashed var(--faint); }}
tbody tr:nth-child(even) td {{ background: var(--stripe); }}
tbody tr:hover td {{ background: var(--panel); }}
.pos {{ color: var(--pos); }} .neg {{ color: var(--neg); }} .zero {{ color: var(--dim); }}
.muted {{ color: var(--dim); }}
.badge {{ display: inline-block; padding: 1px 7px; border-radius: 2px;
          font-size: .72em; font-family: 'IBM Plex Mono', monospace;
          background: rgba(217,119,87,0.18); color: var(--accent);
          letter-spacing: .08em; font-weight: 600; }}
.capped {{ display: inline-block; padding: 1px 7px; border-radius: 2px;
          font-size: .7em; font-family: 'IBM Plex Mono', monospace;
          background: rgba(193,102,107,0.22); color: var(--neg);
          letter-spacing: .08em; font-weight: 600; }}
/* Clickable player names — drill into player_profiles.html */
a.player-link {{ color: inherit; text-decoration: none;
                  border-bottom: 1px dotted var(--faint); }}
a.player-link:hover {{ color: var(--accent); border-bottom-color: var(--accent); }}
/* Boom/bust chips on streamer + scan tables */
.chip {{ display: inline-block; padding: 0 5px; border-radius: 2px;
         font-size: .7em; font-family: 'IBM Plex Mono', monospace;
         background: var(--faint); color: var(--text);
         letter-spacing: .06em; font-weight: 600; margin-right: 2px; }}
.chip-k     {{ background: rgba(127,176,105,0.22); color: var(--pos); }}
.chip-frame {{ background: rgba(140,180,220,0.18); color: #8cb4dc; }}
.chip-il    {{ background: rgba(212,169,69,0.22);  color: var(--warn); }}
.chip-bad   {{ background: rgba(193,102,107,0.22); color: var(--neg); }}
.meta {{ color: var(--dim); font-size: .78em; margin-top: 2em; text-align: center;
         border-top: 1px solid var(--faint); padding-top: 1em;
         font-family: 'IBM Plex Mono', monospace; letter-spacing: .08em; }}
.notes {{ background: var(--panel); padding: .8em 1em; border-left: 3px solid var(--accent);
          border-radius: 3px;
          margin: 1em 0; font-size: .9em; color: var(--text);
          font-family: 'Source Serif 4', Georgia, serif; }}

/* ── Action items ── */
.action-items {{ background: var(--panel); border: 1px solid var(--border);
                  border-radius: 5px; padding: 1em 1.5em; margin: 1em 0; }}
.action-items h3 {{ margin: 0 0 .5em 0; color: var(--accent); font-size: 1.05em;
                    font-family: 'Source Serif 4', Georgia, serif; font-weight: 600; }}
.action-items ul {{ margin: 0; padding: 0; list-style: none; }}
.action-items li {{ padding: .5em .9em; margin: .3em 0; border-radius: 3px;
                     border-left: 3px solid var(--dim);
                     background: var(--stripe);
                     font-family: 'IBM Plex Mono', monospace; font-size: .85em; }}
.urgency-high {{ background: rgba(193,102,107,0.14); border-left-color: var(--neg); }}
.urgency-med  {{ background: rgba(212,169,69,0.14); border-left-color: var(--warn); }}
.urgency-low  {{ background: rgba(127,176,105,0.14); border-left-color: var(--pos); }}

/* ── Gauge ── */
.gauge-wrap {{ display: flex; justify-content: center; margin: .5em 0; }}
.gauge {{ width: 160px; height: 160px; border-radius: 50%; display: flex;
          align-items: center; justify-content: center; }}
.gauge-inner {{ width: 132px; height: 132px; background: var(--bg);
                 border-radius: 50%; display: flex; flex-direction: column;
                 align-items: center; justify-content: center;
                 border: 1px solid var(--border); }}
.gauge-pct {{ font-size: 2.2em; font-weight: 700; color: var(--text);
              font-family: 'Source Serif 4', Georgia, serif; }}
.gauge-label {{ font-size: .8em; color: var(--dim);
               font-family: 'IBM Plex Mono', monospace;
               text-transform: uppercase; letter-spacing: .1em; }}

/* ── Collapsibles ── */
details {{ margin-top: 1em; }}
details > summary {{ cursor: pointer; color: var(--text); font-size: 1em;
                      font-weight: 600; padding: .55em 0;
                      border-bottom: 1px solid var(--faint); user-select: none;
                      font-family: 'IBM Plex Mono', monospace;
                      text-transform: uppercase; letter-spacing: .12em; }}
details > summary:hover {{ color: var(--accent); }}
details[open] > summary {{ border-bottom: 1px solid var(--border); color: var(--accent); }}
details > summary::marker {{ color: var(--dim); }}

/* ── Heatmap cells ── */
.heat-0 {{ background: rgba(127,176,105,0.10); }}
.heat-1 {{ background: rgba(127,176,105,0.22); }}
.heat-2 {{ background: var(--pos); color: var(--bg); font-weight: 700; }}
.heat-3 {{ background: var(--pos); color: var(--bg); font-weight: 700; filter: brightness(1.1); }}
.heat-neg {{ background: rgba(193,102,107,0.22); color: var(--neg); }}

/* ── Section anchors ── */
section {{ scroll-margin-top: 100px; }}

/* ── Sortable hint ── */
th.sortable {{ cursor: pointer; user-select: none; }}
th.sortable:hover {{ background: var(--stripe); color: var(--accent); }}
th.sortable::after {{ content: ' ⇅'; opacity: 0.3; font-size: .8em; }}

/* ── TOC nav strip ── */
.toc {{ display: flex; gap: .4em; flex-wrap: wrap; padding: .55em 0; margin: 1em 0 1.2em 0;
        border-top: 1px solid var(--faint); border-bottom: 1px solid var(--faint);
        font-family: 'IBM Plex Mono', monospace;
        font-size: .78em; overflow-x: auto; }}
.toc a {{ color: var(--dim); text-decoration: none; padding: .25em .7em;
          border-radius: 3px; white-space: nowrap;
          text-transform: uppercase; letter-spacing: .08em; }}
.toc a:hover {{ color: var(--accent); background: var(--stripe); }}

/* ── Tablet (≤ 900px) ── */
@media (max-width: 900px) {{
  .wrap {{ padding: 0 .8em 4em .8em; }}
  h1 {{ font-size: 1.5em; }}
  h2 {{ font-size: 1.2em; margin-top: 1.2em; }}
  h2 .totals {{ display: block; float: none; margin-top: .3em; font-size: .85em; }}
  .scoreboard {{ padding: 1em; }}
  .score-team .wtd {{ font-size: 2em; }}
  .score-team .total-final {{ font-size: 1.2em; }}
  .scroll-x {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
}}

/* ── Phone (≤ 600px) — card-style player rows ── */
@media (max-width: 600px) {{
  .scoreboard {{ padding: .75em; margin: .5em 0; }}
  .score-grid {{ grid-template-columns: 1fr; gap: .5em; }}
  .vs {{ display: none; }}
  .score-team .wtd {{ font-size: 2.4em; line-height: 1; margin: .1em 0; }}
  .score-team .total-final {{ font-size: 1.3em; }}
  .score-team.opp {{ border-top: 1px solid var(--border); padding-top: .5em; }}
  .gauge {{ width: 130px; height: 130px; }}
  .gauge-inner {{ width: 108px; height: 108px; }}
  .gauge-pct {{ font-size: 1.8em; }}

  .toc {{ gap: .3em; font-size: .75em; padding: .4em 0; }}
  .toc a {{ padding: .35em .55em; }}

  .action-items {{ padding: .8em 1em; }}
  .action-items li {{ padding: .6em .8em; font-size: .9em; }}

  details > summary {{ padding: .8em 0; font-size: 1em; min-height: 44px; }}

  .player-table {{ font-size: .95em; }}
  .player-table thead {{ display: none; }}
  .player-table, .player-table tbody, .player-table tr, .player-table td {{
    display: block; width: 100%; }}
  .player-table tr {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
    padding: .6em .75em; margin-bottom: .5em; position: relative;
  }}
  .player-table tr:hover td {{ background: transparent; }}
  .player-table td {{
    border: none; padding: .15em 0;
    display: grid; grid-template-columns: 70px 1fr;
    align-items: baseline;
  }}
  .player-table td::before {{
    content: attr(data-label);
    color: var(--dim); font-size: .75em; text-transform: uppercase;
    letter-spacing: .08em; font-weight: 500;
  }}
  .player-table td[data-label="Player"] {{
    grid-template-columns: 1fr; padding-bottom: .35em;
    margin-bottom: .35em; border-bottom: 1px solid var(--faint);
    font-size: 1.05em; font-weight: 600; color: var(--text);
    font-family: 'Source Serif 4', Georgia, serif;
  }}
  .player-table td[data-label="Player"]::before {{ display: none; }}
  .player-table td[data-label="Total"] b {{ font-size: 1.15em; color: var(--accent); }}
  .player-table td:nth-last-child(1):empty {{ display: none; }}
  .player-table tr.breakdown {{
    background: transparent; border: none; padding: 0 0 0 1em;
    margin: -.4em 0 .4em 0; font-size: .82em; color: var(--dim);
  }}
  .player-table tr.breakdown td {{
    display: block; grid-template-columns: none; padding: .15em 0;
    border-bottom: none;
  }}
  .player-table tr.breakdown td::before {{ display: none; }}

  table:not(.player-table) {{
    display: block; overflow-x: auto; -webkit-overflow-scrolling: touch;
    font-size: .82em; max-width: 100%;
  }}
  table:not(.player-table) thead, table:not(.player-table) tbody,
  table:not(.player-table) tr {{ display: table; width: 100%; }}
  table:not(.player-table) tr {{ table-layout: auto; }}

  .win-bar-label .pct {{ font-size: 1.4em; }}
  .win-bar-track {{ height: 18px; }}

  h1 {{ font-size: 1.3em; }}
  h2 {{ font-size: 1.1em; }}

  header {{ padding: .6em 0; }}
  .header-row {{ gap: .6em; }}
  nav.topnav {{ font-size: .65em; }}
  nav.topnav a {{ padding: .3em .65em; }}
}}
</style>
{theme_boot_js()}
</head><body>
<div class="wrap">
<header>
  <div class="header-row">
    <div>
      <h1>Ligers Weekly Matchup</h1>
      {topnav("matchup")}
    </div>
    {theme_toggle_html()}
  </div>
</header>

<div class="scoreboard">
  <div class="score-grid">
    <div class="score-team">
      <div class="name">{h(mu["mine"].team_name)}</div>
      <div class="wtd">{mu["my_score"]:.1f}</div>
      <div class="proj">+ <b>{my_rest:.1f}</b> projected rest</div>
      <div class="total-final">→ {my_total:.1f}</div>
    </div>
    <div class="vs">vs</div>
    <div class="score-team opp">
      <div class="name">{h(mu["opp"].team_name)}</div>
      <div class="wtd">{mu["opp_score"]:.1f}</div>
      <div class="proj">+ <b>{opp_rest:.1f}</b> projected rest</div>
      <div class="total-final">→ {opp_total:.1f}</div>
    </div>
  </div>

  {gauge_html}
  <div class="gap-row">
    Current gap: <b class="{"pos" if current_gap >= 0 else "neg"}">{current_gap:+.1f}</b>
    &nbsp;·&nbsp; Projected final gap: <b class="{"pos" if proj_gap >= 0 else "neg"}">{proj_gap:+.1f}</b>
  </div>
</div>

{action_items_block}

<div class="toc">
  <a href="#optimizer">🎯 Optimizer</a>
  <a href="#fire">🔥 Days of Fire</a>
  <a href="#drops">🧭 Decision Console</a>
  <a href="#streamers">💎 Streamers</a>
  <a href="#boombust">🎯 Boom/Bust</a>
  <a href="#myteam">My Roster</a>
  <a href="#opp">Opponent</a>
  <a href="#closers">🔒 Closers</a>
  <a href="#power">🏆 Power Rankings</a>
  <a href="#playoff">🎲 Playoff Sim</a>
  <a href="#position">📍 By Position</a>
  <a href="#accuracy">📈 Accuracy</a>
</div>

<div class="notes">
  📅 Period <b>{mu["period"]}</b> · {h(str(week_start))} → {h(str(week_end))} ·
  Today is {h(today.strftime("%A %b %d"))} · {days_remaining_in_week} days remaining after today.<br>
  📊 SPs: probable starts × opp-bat-index factor (BrownU {sp_cap}-start cap applied).
  Hitters: per-game × opposing-SP-projection factor.
  RPs: role-based appearance rate (closer 55%, setup 40%, middle 30%).<br>
  🎲 Win probability: normal approximation from team variance estimates
  (σ/game: hitter {SIGMA_PER_HITTER_GAME}, SP start {SIGMA_PER_SP_START}, RP {SIGMA_PER_RP_GAME}).
</div>

{diff_block}
{ci_block}
{cap_block}

{injury_block}

{trend_block}

<section id="optimizer"><details open>
<summary>🎯 Lineup Optimizer</summary>
{opt_block}
</details></section>

<section id="fire"><details open>
<summary>🔥 Days of Fire — per-day forecast</summary>
{fire_block}
</details></section>

<section id="drops"><details open>
<summary>🧭 Decision Console — My Team vs FA</summary>
{console_block}
</details></section>

<section id="streamers"><details open>
<summary>💎 Streamer Targets</summary>
{streamer_block}
</details></section>

<section id="boombust"><details open>
<summary>🎯 Boom / Bust Scan</summary>
{boom_bust_block}
</details></section>

<section id="myteam"><details open>
<summary>My Roster — full breakdown</summary>
{my_block}
</details></section>

<section id="opp"><details>
<summary>Opponent — full breakdown</summary>
{opp_block}
</details></section>

<section id="closers"><details>
<summary>🔒 Closer-of-Record Tracker</summary>
{closer_block}
</details></section>

<section id="position"><details>
<summary>📍 Position Competition</summary>
{pos_comp_block}
</details></section>

<section id="power"><details>
<summary>🏆 League Power Rankings</summary>
{power_block}
</details></section>

<section id="playoff"><details>
<summary>🎲 Playoff Odds (season sim)</summary>
{playoff_block}
</details></section>

<section id="accuracy"><details>
<summary>📈 Prediction Accuracy History</summary>
{accuracy_block}
</details></section>

<p class="meta">Generated {h(now_s)} ·
<code>python scripts/xfp/build_matchup_dashboard.py</code>
<meta http-equiv="refresh" content="300">
</p>
</div>

<script>
// Click-to-sort tables (mark every <th> with class="sortable" via JS)
document.querySelectorAll('table').forEach(table => {{
  const headers = table.querySelectorAll('thead th');
  headers.forEach((th, idx) => {{
    th.classList.add('sortable');
    th.addEventListener('click', () => {{
      const tbody = table.querySelector('tbody');
      // Group each data row with the breakdown sub-rows that follow it, so the
      // sub-rows travel WITH their parent. Fix 2026-07-23: the old
      // filter+innerHTML='' path silently DELETED every .breakdown row on the
      // first sort click.
      const groups = [];
      Array.from(tbody.querySelectorAll('tr')).forEach(r => {{
        if (r.classList.contains('breakdown')) {{
          if (groups.length) groups[groups.length - 1].extra.push(r);
        }} else {{
          groups.push({{ main: r, extra: [] }});
        }}
      }});
      const dir = th.dataset.sortDir === 'asc' ? 'desc' : 'asc';
      th.dataset.sortDir = dir;
      groups.sort((a, b) => {{
        const av = a.main.children[idx]?.innerText.trim() || '';
        const bv = b.main.children[idx]?.innerText.trim() || '';
        const an = parseFloat(av.replace(/[^\\d.+-]/g, ''));
        const bn = parseFloat(bv.replace(/[^\\d.+-]/g, ''));
        if (!isNaN(an) && !isNaN(bn)) {{
          return dir === 'asc' ? an - bn : bn - an;
        }}
        return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }});
      tbody.innerHTML = '';
      groups.forEach(g => {{ tbody.appendChild(g.main); g.extra.forEach(e => tbody.appendChild(e)); }});
    }});
  }});
}});

// Expand/collapse all controls
const expandBtn = document.createElement('button');
expandBtn.textContent = 'Expand all';
expandBtn.style.cssText = 'margin: 1em .5em; padding: .4em 1em; background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: 3px; cursor: pointer; font-family: \\'IBM Plex Mono\\', monospace; font-size: .8em; text-transform: uppercase; letter-spacing: .12em;';
expandBtn.onclick = () => document.querySelectorAll('details').forEach(d => d.open = true);
const collapseBtn = document.createElement('button');
collapseBtn.textContent = 'Collapse all';
collapseBtn.style.cssText = expandBtn.style.cssText;
collapseBtn.onclick = () => document.querySelectorAll('details').forEach(d => d.open = false);
document.querySelector('.toc').appendChild(expandBtn);
document.querySelector('.toc').appendChild(collapseBtn);
</script>
{column_toggle_js("matchup")}
</body></html>
'''

    # Publish-integrity smoke check (audit 2026-07-04): the per-section
    # try/except-to-HTML pattern means a dead section ships silently as a
    # literal 'error: ...' block — that ran for 17 DAYS after a helper was
    # deleted. Fail the build loudly instead.
    #
    # Traceability (2026-07-23): attribute each marker back to its <h2> so the
    # failure message names the SECTION and the error text, not just the raw
    # marker. Section builders now also log a full traceback via
    # _section_error() — so the CI log shows the root cause above this abort.
    import re as _re
    _err_sections = _re.findall(
        r'<h2>([^<]*)</h2>\s*<p class="muted">error:\s*([^<]*)', html)
    _legacy_markers = [m for m in ('>error: name', 'NameError') if m in html]
    if _err_sections or _legacy_markers:
        detail = '; '.join(f'{t.strip()} → {e.strip()}' for t, e in _err_sections)
        if _legacy_markers:
            detail = (detail + '; ' if detail else '') + f'legacy markers {_legacy_markers}'
        raise RuntimeError(
            f'matchup.html contains rendered error sections: {detail} '
            '— a section builder is throwing; see the [section-error] traceback '
            'above for the root cause')
    local = OUT / 'matchup.html'
    local.write_text(html, encoding='utf-8')
    print(f'  wrote {local}')
    if XFP_DOCS.exists():
        target = XFP_DOCS / 'matchup.html'
        target.write_text(html, encoding='utf-8')
        print(f'  wrote {target}')
        live_local = OUT / 'live_dashboard.html'
        if live_local.exists():
            shutil.copy(live_local, XFP_DOCS / 'live_dashboard.html')

    print(f'\n  Win probability: {win_prob*100:.1f}%')
    print(f'  Projected: {"WIN" if proj_gap >= 0 else "LOSE"} by {abs(proj_gap):.1f}')


if __name__ == '__main__':
    main()
