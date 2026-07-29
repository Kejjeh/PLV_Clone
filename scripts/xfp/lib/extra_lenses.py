"""extra_lenses — four validated context lenses folded into triangulate.

All are CONTEXT-ONLY (CLAUDE.md #13): they never move the rh3/rp3/rprs2 headline or
the verdict. They add conviction / conflict color:

  • stuff_lens(name)      SP — FanGraphs Stuff+ level + the Stuff+-anchored RoS
                          fp/start projection + breakout gap (elite stuff, lagging
                          results = buy-low). Validated 2026-06-06.
  • floor_lens(name)      SP — per-start bust probability (P(fp<5)) + SAFE/MODERATE/
                          RISKY tier, driven by K-BB% (not stuff). Validated 2026-06-06.
  • trend_lens(mlbam,role) physical getting-better/worse: bat speed + attack-angle
                          (hitters) / FB velo (pitchers), 2026 vs prior-yr baseline.
  • shadow_lens(name)     SP process grade (20-80) for arms with no rp3/archetype
                          (rookies / thin post-callup) — fills the unranked gap.

Every accessor is defensive (returns None on any failure) and cached so a batch
run pays each underlying model fit once.
"""
from __future__ import annotations

import functools
import unicodedata
from pathlib import Path


# _norm routed to the name_match owner (item 10, 2026-07-04). Self-consistent:
# _stuff_frame() builds its lookup dict with this helper and the lens functions
# (floor_lens, stuff_command_lens) look up with it — one shared source. join_key
# is order-independent (a robustness gain); the triangulate golden test covers
# the floor_lens path.
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402

# Empirical sample-size minimums (measured 2026-07-29). Never hand-pick a
# window gate here — see docs/stabilization_minimums.md.
from plv_clone import stabilization as _stab  # noqa: E402


def _warn(section: str, exc: BaseException) -> None:
    """One-line stderr breadcrumb for fail-soft handlers (audit 2026-07-04:
    silent excepts hide dead lenses for weeks). Semantics unchanged — loud only."""
    import sys
    print(f"  ⚠ [extra_lenses.{section}] suppressed {type(exc).__name__}: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# Stuff+ and SP-floor share the FanGraphs 2026 SP frame (one fit, cached)
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _stuff_frame():
    """Build the Stuff+ board once; index by normalized FG name.
    Returns {norm_name: row_dict} or {} on failure."""
    try:
        import sys, os
        _xfp = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if _xfp not in sys.path:
            sys.path.insert(0, _xfp)
        from sp_stuff_model import build as _build
        d, _ = _build()
    except Exception as e:
        _warn("stuff_frame", e)
        return {}
    out = {}
    for _, r in d.iterrows():
        k = _norm(r.get("player_name_fg"))
        if k:
            out.setdefault(k, r.to_dict())
    return out


def stuff_lens(name: str) -> dict | None:
    """SP Stuff+ level + Stuff+-anchored RoS fp/start projection + breakout gap."""
    row = _stuff_frame().get(_norm(name))
    if not row:
        return None
    try:
        return {
            "stuff_plus": round(float(row["stuff_plus"]), 1),
            "proj_ros_fp": round(float(row["proj_ros_fp"]), 2),
            "breakout_gap": round(float(row["breakout_gap"])),
            "stuff_pctl": round(float(row["stuff_pctl"])),
        }
    except (KeyError, TypeError, ValueError):
        return None


def floor_lens(name: str) -> dict | None:
    """SP per-start bust probability + SAFE/MODERATE/RISKY tier from current K-BB%.
    Uses league-neutral lineup/rest (player-level read, not a specific matchup)."""
    row = _stuff_frame().get(_norm(name))
    if not row:
        return None
    try:
        import sys, os
        _xfp = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if _xfp not in sys.path:
            sys.path.insert(0, _xfp)
        from sp_floor_model import floor_for
        k = float(row["k_pct"]); bb = float(row["bb_pct"])
        # FG rates are percentages (e.g. 24.5) -> fractions
        if k > 1:
            k /= 100.0
        if bb > 1:
            bb /= 100.0
        probs, tiers = floor_for(k, bb)
        return {"bust_prob": round(float(probs[0]) * 100), "tier": tiers[0]}
    except Exception as e:
        _warn("floor_lens", e)
        return None


# --------------------------------------------------------------------------
# Physical trend (bat speed / attack angle — H; FB velo — P)
# --------------------------------------------------------------------------

def trend_lens(mlbam, role: str) -> dict | None:
    """Physical getting-better/worse tag for a resolved MLBAM id. Context-only."""
    try:
        from lib.trend_signal import trend_for_mlbam
        tag, row = trend_for_mlbam(int(mlbam), role)
    except Exception as e:
        _warn("trend_lens", e)
        return None
    if not tag:
        return None
    return {"tag": tag}


# --------------------------------------------------------------------------
# Shadow scout (process grade for unranked SPs)
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=512)
def shadow_lens(name: str) -> dict | None:
    """20-80 process grade for an SP with no rp3/archetype. None when the player
    has no usable 2026 MLB sample (verdict NO_MLB_DATA)."""
    try:
        from lib.shadow_scout import shadow_scout
        res = shadow_scout([name])
    except Exception as e:
        _warn("shadow_lens", e)
        return None
    if not res:
        return None
    r = res[0]
    if r.get("verdict") in (None, "NO_MLB_DATA"):
        return None
    return {
        "avg_grade": r.get("avg_grade"),
        "verdict": r.get("verdict"),
        "grades": r.get("grades"),
    }


# --------------------------------------------------------------------------
# Floor-adjusted (risk-aware) decision score — DECISION-LAYER, never a headline.
# --------------------------------------------------------------------------
# Validated 2026-06-24 (validate_rp3_ideas.py + validate_floor_trajectory.py):
# within-season trajectory / recency-trend features add ~0 OOS to BOTH the rp3 mean
# (Δr ≈ 0 vs the +0.005 gate) AND the per-start bust model (ΔAUC ≈ 0, bootstrap 95%
# CI spans 0). So a command-collapse arm (canonical: José Soriano 2026) cannot be
# flagged by a new *projection feature* — the right move is to SURFACE the already-
# validated sp_floor bust risk in the DECISION layer. floor_adj encodes H2H risk-
# aversion (a <5 FP start can lose a scoring week): it docks the mean for above-base
# bust probability and credits it for below-base (SAFE-floor) arms.
#
# Rule 13: this NEVER changes the rh3/rp3/rprs2/blended headline — it is a separate,
# clearly-labelled decision metric (registered context-only in lens_registry).
FLOOR_BUST_BASE = 0.27       # historical per-start bust (<5 FP) base rate (validation panel)
FLOOR_BUST_FP_COST = 9.0     # FP swing a bust start represents vs a typical non-bust start
FLOOR_RISK_LAMBDA = 0.5      # H2H risk-aversion knob (0 = mean-neutral; higher = penalize bust more)


def floor_adjusted_xfp(mean_fp, bust_prob_pct):
    """Risk-aware FP/start for H2H start/drop ranking. Returns (floor_adj_fp, penalty_fp):
    penalty>0 docks an above-base-bust arm, penalty<0 credits a SAFE-floor arm. Returns
    (mean_fp, 0.0) when either input is missing — never invents a number."""
    if mean_fp is None or bust_prob_pct is None:
        return (mean_fp, 0.0)
    try:
        bust = float(bust_prob_pct) / 100.0
        penalty = FLOOR_RISK_LAMBDA * (bust - FLOOR_BUST_BASE) * FLOOR_BUST_FP_COST
        return (round(float(mean_fp) - penalty, 2), round(penalty, 2))
    except (TypeError, ValueError):
        return (mean_fp, 0.0)


def floor_flag(penalty_fp, tier=None):
    """Mean-vs-floor conflict tag, aligned to the VALIDATED SAFE/MODERATE/RISKY floor
    tiers (the calibrated cut), with a penalty-sign sanity check. FLOOR-RISK = a RISKY-
    tier arm whose bust risk the mean doesn't show (command-collapse pattern); SAFE-FLOOR
    = a SAFE-tier arm the mean under-credits. None otherwise (incl. MODERATE)."""
    if penalty_fp is None or tier is None:
        return None
    if tier == 'RISKY' and penalty_fp > 0:
        return 'FLOOR-RISK'
    if tier == 'SAFE' and penalty_fp < 0:
        return 'SAFE-FLOOR'
    return None


# --------------------------------------------------------------------------
# Stuff-vs-command divergence — distinguishes REVERSIBLE from STRUCTURAL decline.
# --------------------------------------------------------------------------
# Built 2026-06-24 from the Soriano-vs-Framber process decomposition. The lesson:
# what decays *permanently* is STUFF (swing-and-miss / velo); COMMAND (walks / zone%)
# wobbles REVERT far more often, especially on a high-stuff arm (the stuff buys margin
# to fix the strike-throwing). This classifier reads the WITHIN-season process trend so
# a command-only slump (Soriano: SwStr intact, BB rising) isn't mistaken for a real
# decline (Framber: SwStr collapsed 12->8). Context-only (Rule 13): NEVER moves the
# headline, floor_adj, or verdict — it surfaces the *type* of decline as conviction color.

def classify_stuff_command(swstr_d, velo_d, bb_d, zone_d, yoy_swstr_d=0.0,
                           prior_ok=True):
    """Pure, unit-testable classifier of an SP's process divergence. Within-season deltas
    (recent minus early, 2026) PLUS a year-over-year SwStr delta (2026 minus 2025, pp) so a
    stuff decline that happened *across* seasons (Framber: SwStr 12.4->10.1 YoY) is caught
    even when 2026 looks flat. Returns:
      'STUFF-DECLINE'  swing-and-miss/velo eroding in-season OR YoY -> structural (sell cand.)
      'COMMAND-WATCH'  stuff intact (in-season AND YoY) but walks up / zone% down -> reversible
      None             no clear divergence.

    `prior_ok` (QA fix 2026-07-20): False when the arm has NO real prior-year
    sample (rookies/first-full-season — the memo-#11 gate that already guards
    the YoY leg). Without an established baseline, a single in-season signal
    is debut-adjustment noise, not structural decline (false-fired on Bennett
    and Messick): STUFF-DECLINE then requires BOTH in-season stuff signals
    (SwStr AND velo eroding) to fire.

    Measurement note (2026-07-29 pitcher stabilization study, see
    docs/stabilization_minimums.md) — the two tags do NOT rest on equally solid
    ground, and that asymmetry is the point:
      * STUFF-DECLINE's inputs are measured and fast-stabilizing: FB velo
        (r~=0.90 by 150 pitches, the most reliable pitcher metric we have) and
        SwStr% (175 pitches).
      * COMMAND-WATCH's `bb_d` leg is a pitcher BB% delta, and pitcher BB%
        **never stabilizes in-window at any sample size** — a recent walk spike
        carries essentially no information about the rest of the season.
        Rather than contradicting this lens, that finding is what JUSTIFIES its
        interpretation: COMMAND-WATCH means "reversible, hold-watch" precisely
        because the walk signal does not persist. So bb_d is retained as a
        DESCRIPTION of what happened, never as evidence that it will continue —
        which is why COMMAND-WATCH must never be read as a sell trigger.
        (`zone_d` is untested — not in the study's metric set.)"""
    if prior_ok:
        stuff_eroding = (swstr_d <= -2.0) or (velo_d <= -1.5) or (yoy_swstr_d <= -2.0)
    else:
        stuff_eroding = (swstr_d <= -2.0) and (velo_d <= -1.5)
    stuff_intact = (swstr_d >= -1.5) and (velo_d >= -1.0) and (yoy_swstr_d >= -1.0)
    command_eroding = (bb_d >= 2.5) or (zone_d <= -2.5)
    if stuff_eroding:
        return 'STUFF-DECLINE'
    if stuff_intact and command_eroding:
        return 'COMMAND-WATCH'
    return None


@functools.lru_cache(maxsize=1)
def _yoy_swstr_lookup():
    """{pitcher: {year: (season-end SwStr%, gs_to)}} from the rolling panel, for the
    year-over-year stuff-decline check. gs_to lets us require a real prior-year sample so
    a post-injury/TJ arm (compromised prior season, e.g. Bradish) doesn't false-flag.
    Empty dict on any failure (lens degrades to within-season only)."""
    try:
        import pandas as pd
        p = Path(__file__).resolve().parents[3] / 'data' / 'research' / 'xfp_cache' / 'rolling_pitchers_2018_2026.csv'
        df = pd.read_csv(p, usecols=['pitcher', 'year', 'split_day', 'swstr_pct_to', 'gs_to'])
        last = df.sort_values('split_day').groupby(['pitcher', 'year']).tail(1)
        out: dict = {}
        for _, r in last.iterrows():
            out.setdefault(int(r['pitcher']), {})[int(r['year'])] = (float(r['swstr_pct_to']), float(r['gs_to']))
        return out
    except Exception as e:
        _warn("swstr_yoy_map", e)
        return {}


@functools.lru_cache(maxsize=1)
def _statcast_2026_pitch():
    try:
        import pandas as pd
        p = Path(__file__).resolve().parents[3] / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet'
        if not p.exists():
            return None
        return pd.read_parquet(p, columns=['pitcher', 'game_date', 'pitch_type',
                                           'release_speed', 'description', 'events', 'zone'])
    except Exception as e:
        _warn("statcast_2026_pitch", e)
        return None


def stuff_command_lens(mlbam, season=2026):
    """Within-season STUFF-vs-COMMAND divergence for an SP (mlbam id). Splits the
    pitcher's 2026 pitches into early (first 50%) vs recent (last 30%) and compares
    SwStr% / FB velo (stuff) against BB% / zone% (command). Returns {tag, swstr_d,
    velo_d, bb_d, zone_d} or None (no divergence / thin sample). Context-only."""
    df = _statcast_2026_pitch()
    if df is None:
        return None
    try:
        import pandas as pd
        d = df[df['pitcher'] == int(mlbam)].sort_values('game_date')
    except Exception as e:
        _warn("stuff_command_lens.slice", e)
        return None
    # Sample gate is on the SPLIT WINDOWS, not the total. The lens compares an
    # early window (first 50%) against a recent one (last 30%), and the recent
    # window is the binding constraint: SP SwStr% stabilizes at 175 pitches
    # (measured 2026-07-29 — plv_clone.stabilization; docs/stabilization_minimums.md),
    # so 0.30*n >= 175 => n >= ~584. The old flat `len(d) < 300` gate let the
    # recent window run at ~90 pitches, about half the sample SwStr needs, which
    # meant the headline swstr_d could be computed off a window carrying no
    # forward information. Both windows are now checked explicitly.
    n = len(d)
    _swstr_min = _stab.minimum("swstr", "SP")[0]
    early, recent = d.iloc[:int(n * 0.5)], d.iloc[int(n * 0.7):]
    if len(early) < _swstr_min or len(recent) < _swstr_min:
        return None

    def _m(g):
        import pandas as pd
        swstr = 100.0 * (g['description'] == 'swinging_strike').sum() / max(1, len(g))
        velo = g[g['pitch_type'].isin(['FF', 'SI'])]['release_speed'].mean()
        ev = g[g['events'].notna()]
        bb = 100.0 * (ev['events'] == 'walk').mean() if len(ev) else float('nan')
        zone = 100.0 * g['zone'].between(1, 9).mean() if 'zone' in g.columns else float('nan')
        return swstr, velo, bb, zone

    import pandas as pd
    e, r = _m(early), _m(recent)
    swstr_d = round(r[0] - e[0], 1)
    velo_d = round((r[1] - e[1]) if pd.notna(r[1]) and pd.notna(e[1]) else 0.0, 1)
    bb_d = round((r[2] - e[2]) if pd.notna(r[2]) and pd.notna(e[2]) else 0.0, 1)
    zone_d = round((r[3] - e[3]) if pd.notna(r[3]) and pd.notna(e[3]) else 0.0, 1)
    # year-over-year SwStr delta (2026 minus 2025), in pp — only if the PRIOR season had a
    # real sample (>=10 GS), else 0.0 so post-injury/TJ arms (Bradish) don't false-flag.
    yoy = _yoy_swstr_lookup().get(int(mlbam), {})
    cur, prev = yoy.get(season), yoy.get(season - 1)
    prior_ok = bool(prev and prev[1] >= 10)   # real prior-year sample (memo #11 gate)
    yoy_swstr_d = round((cur[0] - prev[0]) * 100, 1) if (cur and prior_ok) else 0.0
    tag = classify_stuff_command(swstr_d, velo_d, bb_d, zone_d, yoy_swstr_d,
                                 prior_ok=prior_ok)
    if tag is None:
        return None
    return {'tag': tag, 'swstr_d': swstr_d, 'velo_d': velo_d, 'bb_d': bb_d, 'zone_d': zone_d,
            'yoy_swstr_d': yoy_swstr_d, 'prior_ok': prior_ok}


# --------------------------------------------------------------------------
# Next-start matchup CONTEXT (venue + opponent) — flag, NOT a projection multiplier.
# --------------------------------------------------------------------------
# Validated 2026-06-24 (validate_next_start_park.py, 2,364 real 2026 SP starts): a park
# OR opponent MULTIPLIER does NOT improve per-start SP FP prediction OOS (both best-k=0;
# MAE flat at ~7.7 on a ~10 FP mean — single SP starts are ~75% irreducible noise). The
# raw Coors gap is real as a POPULATION average (SP avg 7.67 FP at Coors vs 9.99 elsewhere,
# -2.32) but is confounded (rotation/opponent) and swamped by per-start variance. So we do
# NOT move the projection — we surface the matchup as DECISION CONTEXT: an extreme park
# (Coors) is a high-variance, cap-bench flag even though it's not a point-predictable dock.
# Rule 13: context-only, never a headline/feature.

# Statcast team abbreviations (MLB full name -> abbr; matches park/team_strength caches).
_TEAM_ABBR = {
    'Arizona Diamondbacks': 'AZ', 'Atlanta Braves': 'ATL', 'Baltimore Orioles': 'BAL',
    'Boston Red Sox': 'BOS', 'Chicago Cubs': 'CHC', 'Chicago White Sox': 'CWS',
    'Cincinnati Reds': 'CIN', 'Cleveland Guardians': 'CLE', 'Colorado Rockies': 'COL',
    'Detroit Tigers': 'DET', 'Houston Astros': 'HOU', 'Kansas City Royals': 'KC',
    'Los Angeles Angels': 'LAA', 'Los Angeles Dodgers': 'LAD', 'Miami Marlins': 'MIA',
    'Milwaukee Brewers': 'MIL', 'Minnesota Twins': 'MIN', 'New York Mets': 'NYM',
    'New York Yankees': 'NYY', 'Athletics': 'ATH', 'Oakland Athletics': 'ATH',
    'Philadelphia Phillies': 'PHI', 'Pittsburgh Pirates': 'PIT', 'San Diego Padres': 'SD',
    'San Francisco Giants': 'SF', 'Seattle Mariners': 'SEA', 'St. Louis Cardinals': 'STL',
    'Tampa Bay Rays': 'TB', 'Texas Rangers': 'TEX', 'Toronto Blue Jays': 'TOR',
    'Washington Nationals': 'WSH',
}


def park_env(pf_R):
    """Park run-environment tier from the multi-year pf_R (run factor). Coors-class is its
    own tier — the only park material enough to flag for a bench decision."""
    if pf_R is None:
        return None
    if pf_R >= 1.10:
        return 'EXTREME-HITTER'   # Coors
    if pf_R >= 1.03:
        return 'HITTER'
    if pf_R <= 0.95:
        return 'PITCHER'
    return 'NEUTRAL'


def opp_env(bat_index):
    """soft / avg / tough from the opposing offense's bat_index (mirrors matchup_tier)."""
    if bat_index is None:
        return None
    if bat_index <= 0.97:
        return 'soft'
    if bat_index >= 1.03:
        return 'tough'
    return 'avg'


# Venue eras: first season at the CURRENT venue. A multi-year blend is only valid
# while the team plays in the same park — ATH moved to Sutter Health Park in 2025
# (pf_R 1.044/1.096, pf_HR 1.05/1.16 vs Coliseum ~0.95-1.00 / 0.76-0.87) and TB's
# 2026 factor (1.030) matches 2025 Steinbrenner (1.024), not the Trop (~0.93-0.96).
# Blending across the move called Sutter "neutral" (1.001) when it plays HITTER —
# caught 2026-07-03 when a streamer board credited a visiting SP +0.9 there.
VENUE_ERAS = {'ATH': 2025, 'TB': 2025}


@functools.lru_cache(maxsize=1)
def _park_R_map():
    """Multi-year-stable pf_R per team abbr (PA-weighted mean, 2022+ but never earlier
    than the team's VENUE_ERAS start) — single-year park factors are half-season-noisy
    (2026 Coors pf_wOBA=1.0165), but blending across a VENUE CHANGE is worse."""
    try:
        import pandas as pd, numpy as np
        p = Path(__file__).resolve().parents[3] / 'data' / 'research' / 'xfp_cache' / 'park_factors_2018_2026.csv'
        df = pd.read_csv(p)
        df = df[df.apply(lambda r: r.year >= VENUE_ERAS.get(r.team_abbr, 2022), axis=1)]
        return {t: float(np.average(g.pf_R, weights=g.n_pa)) for t, g in df.groupby('team_abbr')}
    except Exception as e:
        _warn("park_R_map", e)
        return {}


# Empirical BrownU-FP conversion, derived 2026-07-03 from our own boxscore store:
# mean SP FP/start by venue (n=2,492 starts, 30 venues) regressed on venue-era pf_R
# gives slope -15.9 FP per pf_R unit (weighted fit, corr -0.61). Slope-based (not
# raw venue means) because raw means confound the home staff's quality — e.g. ATH
# observed -2.8 FP vs league includes the A's own arms; the causal visitor read is
# slope*(pf_R-1) = -0.9.
PARK_FP_SLOPE = -15.9


def park_fp_adj(team_abbr):
    """SP FP/start park adjustment for a start AT this team's venue (+ = pitcher-
    friendly, - = hitter-friendly). THE single owner of park->FP conversion: boards
    must call this instead of hand-typing park tables (the 2026-07-03 ATH bug).
    Returns 0.0 for unknown abbreviations — never invents a number."""
    pf = _park_R_map().get(str(team_abbr).upper())
    if pf is None:
        return 0.0
    return round(PARK_FP_SLOPE * (pf - 1.0), 1)


@functools.lru_cache(maxsize=1)
def _opp_bat_map():
    try:
        import pandas as pd
        p = Path(__file__).resolve().parents[3] / 'data' / 'research' / 'xfp_cache' / 'team_strength_2026.csv'
        df = pd.read_csv(p)
        return dict(zip(df.team, df.bat_index))
    except Exception as e:
        _warn("opp_bat_map", e)
        return {}


@functools.lru_cache(maxsize=1)
def _upcoming_schedule():
    """Next 9 days of MLB games with probable-pitcher ids + venue team abbr.
    Cached once per process; returns () on any failure so the lens degrades to
    None.

    Delegates the raw fetch to the mlb_stats.get_schedule owner (item 9,
    2026-07-04) — gains the 3-attempt retry + fail-soft caching, and drops the
    hand-rolled schedule?hydrate=probablePitcher walk. Output is byte-identical
    to the prior hand-mapped version (live-diffed 123/123 rows): get_schedule's
    API abbreviations match the old _TEAM_ABBR name→abbr map exactly, and the
    non-Final filter is preserved.
    """
    try:
        from datetime import date, timedelta
        from plv_clone.mlb_stats import get_schedule
        start = date.today(); end = start + timedelta(days=9)
        out = []
        for g in get_schedule(start.isoformat(), end.isoformat()):
            if g['game_state'] == 'Final':   # "next start" must be upcoming
                continue
            out.append((g['date'], g['home_abbr'], g['away_abbr'],
                        g['home_probable_id'], g['away_probable_id']))
        return tuple(out)
    except Exception as e:
        _warn("probables_schedule", e)
        return ()


def next_start_lens(mlbam):
    """Next CONFIRMED start matchup context for an SP (decision flag, not a multiplier).
    Returns {date, opp, venue, is_home, pf_R, park_env, opp_bat_index, opp_env} or None
    when the pitcher's next start isn't yet posted as a probable."""
    try:
        mlbam = int(mlbam)
    except (TypeError, ValueError):
        return None
    for d, home, away, hp, ap in _upcoming_schedule():   # already date-sorted
        if mlbam == hp or mlbam == ap:
            is_home = (mlbam == hp)
            venue = home                      # game is played at the home team's park
            opp = away if is_home else home
            pfR = _park_R_map().get(venue)
            oidx = _opp_bat_map().get(opp)
            return {'date': d, 'opp': opp, 'venue': venue, 'is_home': is_home,
                    'pf_R': round(pfR, 3) if pfR else None, 'park_env': park_env(pfR),
                    'opp_bat_index': round(oidx, 3) if oidx else None, 'opp_env': opp_env(oidx)}
    return None
