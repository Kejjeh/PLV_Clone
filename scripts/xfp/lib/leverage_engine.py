"""leverage_engine — the P(win) Monte-Carlo engine, extracted 2026-07-29.

This is the substrate every P(win)-denominated decision runs on. It was inline in
``scripts/xfp/run_matchup_leverage.py`` (which is now a thin CLI over this
module) and is extracted so the weekly optimizer, the dpwin history logger and
the decision ledger can all share ONE engine rather than growing copies — the
lesson of the four divergent rh3 feature assemblies (see
``plv_clone.models.xfp.frames``).

THE MODEL. BrownU H2H is won by P(my_total > opp_total), not by E[FP]. Per
remaining player-event the FP draw is a Bayesian blend of (a) a bootstrap from
the player's empirical per-game FP history (boxscore parquets, mlbam-keyed) and
(b) a parametric draw at the model mean/sigma, weight n/(n+k) — so thin
histories lean on the model. SP starts are event-level with the chronological
period cap applied INSIDE each trial; unconfirmed rotation-gap starts occur with
p=0.80.

Draws are precomputed ONCE (``precompute_draws``); every scenario is then a cheap
numpy re-assembly (``assemble`` / ``delta_pwin``), which is what makes searching
thousands of roster permutations affordable.

RULE 13: this is a decision layer. It never touches rh3/rp3/rprs2/baseline xFP.

--------------------------------------------------------------------------------
THREE DEFECTS FIXED DURING EXTRACTION (all verified against the pre-extraction
source; each would have silently corrupted persisted dpwin history)
--------------------------------------------------------------------------------

1. **Draw dicts were keyed by player NAME.** ``_hitter_arrays`` / ``_rp_arrays``
   returned ``out[h['name']]``, so two same-name players on one roster collapsed
   into a single array — the Max Muncy collision class, living inside the Monte
   Carlo engine. Now keyed by ``int(mlbam)``, with name carried as a field and
   resolved at the CLI boundary for human-facing arguments.

2. **Candidate draws were order-dependent.** ``fa_streamer_adds`` pulled from the
   shared ``D['rng']`` inside its per-candidate loop, so a candidate's draws — and
   therefore its dpwin — depended on how many candidates happened to be scored
   before it. Reordering the pool changed every number. Each candidate now gets
   its own stream, ``default_rng([seed, mlbam, bucket_ord])``, which makes dpwin
   reproducible and independent of pool composition. This had to be fixed before
   any dpwin could be persisted.

3. **EV retargeting multiplied a distribution containing negatives.** The old
   ``base = base * (target / ev)`` scaled draws to hit the model's per-start EV.
   For SP FP (``K + IP*3.3 - H - 2*ER - BB - HBP``) negatives are routine — 16.4%
   of real starts finish <= 0 — and multiplicative scaling makes a blow-up start
   *worse* when a pitcher's outlook improves, while also scaling the SD (despite
   a comment claiming variance shape was preserved). Replaced with a LOCATION
   shift, ``base + (target - ev)``, which hits the same target mean, preserves
   the empirical variance shape as intended, and cannot invert tail severity.
   Same class as the ``opp_factor`` defect fixed in ``sp_bench_mc`` on 2026-07-29.
"""
from __future__ import annotations

import hashlib
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

# ── reuse dashboard machinery (never reimplement; never edit it) ─────────────
from build_matchup_dashboard import (  # noqa: E402
    get_matchup,
    load_projections,
    fetch_espn_week_schedule,
    fetch_schedules_by_team,
    build_sp_starts_by_pitcher,
    project_player,
    player_mlbam_lookup,
    _resolve_mlbam_via_api,
    _resolve_pitcher_mlbam,
    _is_active_slot,
    _today_et,
    _norm,
    IL_INJURY_STATES,
    ESPN_TO_MLB_TEAM,
    SIGMA_PER_SP_START,
    SIGMA_PER_RP_GAME,
    FALLBACK_SP_PER_START,
)
from scripts.xfp.lib.pitcher_role import detect_pitcher_role  # noqa: E402
from scripts.xfp.lib.boom_bust import (  # noqa: E402
    SP_BOOM, SP_BUST, H_BOOM, H_BUST, RP_BOOM, RP_BUST,
)
from plv_clone.cap_math import (  # noqa: E402
    sp_cap_for_period, period_window, is_period_covered, weeks_in_period,
)
from scripts.xfp.lib.period_meta import (  # noqa: E402
    resolve_period_meta, espn_period_meta,
)
from scripts.xfp.lib.variance_bands import fallback_sigma  # noqa: E402


CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
BOX_P = CACHE / 'boxscore_pitchers.parquet'
BOX_H = CACHE / 'boxscore_hitters.parquet'

# Bayesian blend priors (sp_bench_mc idiom: weight = n_emp / (n_emp + K)).
K_PRIOR_SP = 12       # ~15-start history -> 56% empirical
K_PRIOR_H = 8         # ~25-game history -> 76% empirical
K_PRIOR_RP = 10
EMP_LAST_N = {'SP': 15, 'H': 25, 'RP': 20}
UNCONFIRMED_START_P = 0.80   # dashboard's rotation-gap occurrence probability

# Regime cuts on baseline P(win)
TRAILING_MAX = 0.40
LEADING_MIN = 0.60


# ── Empirical FP series (boxscore parquets, mlbam-keyed) ───────────────────
_BOX_CACHE: dict = {}


def _box(kind: str):
    """kind 'P'/'H' -> parquet frame (or None). Cached per process."""
    if kind not in _BOX_CACHE:
        path = BOX_P if kind == 'P' else BOX_H
        try:
            _BOX_CACHE[kind] = pd.read_parquet(path)
        except Exception:
            _BOX_CACHE[kind] = None
    return _BOX_CACHE[kind]


def emp_series(mlbam, bucket: str, before: str | None = None,
               last_n: int | None = None) -> list[float]:
    """Time-ordered per-game BrownU FP for one player from the boxscore store.
    bucket in {SP,RP,H}. `before` (ISO date) filters to games strictly earlier —
    the leakage guard for --calibrate. Uses the store's precomputed fp columns."""
    df = _box('P' if bucket in ('SP', 'RP') else 'H')
    if df is None or not mlbam:
        return []
    sub = df[df['mlbam_id'] == int(mlbam)]
    if bucket == 'SP':
        sub = sub[sub['gs'] == 1]; col = 'fp_sp'
    elif bucket == 'RP':
        sub = sub[sub['gs'] == 0]; col = 'fp_rp'
    else:
        col = 'fp_h'
    if before:
        sub = sub[sub['game_date'].astype(str) < before]
    if sub.empty:
        return []
    sub = sub.sort_values(['game_date', 'game_pk'])
    vals = [float(x) for x in sub[col].tolist()]
    n = last_n if last_n is not None else EMP_LAST_N[bucket]
    return vals[-n:]


def pooled_series(bucket: str, before: str | None = None,
                  max_n: int = 5000) -> list[float]:
    """League-pooled per-game FP distribution for a bucket (calibration fallback
    for thin-history players)."""
    df = _box('P' if bucket in ('SP', 'RP') else 'H')
    if df is None:
        return []
    sub = df
    if before:
        sub = sub[sub['game_date'].astype(str) < before]
    if bucket == 'SP':
        vals = sub.loc[sub['gs'] == 1, 'fp_sp']
    elif bucket == 'RP':
        vals = sub.loc[sub['gs'] == 0, 'fp_rp']
    else:
        vals = sub['fp_h']
    vals = vals.astype(float)
    if len(vals) > max_n:
        vals = vals.sample(max_n, random_state=0)
    return [float(x) for x in vals.tolist()]


def series_stats(vals: list[float], boom_thr: float, bust_thr: float) -> dict:
    if not vals:
        return {'n': 0, 'mean': None, 'std': None, 'boom_pct': None, 'bust_pct': None}
    a = np.asarray(vals, dtype=float)
    return {
        'n': int(len(a)),
        'mean': round(float(a.mean()), 2),
        'std': round(float(a.std(ddof=1)), 2) if len(a) > 1 else 0.0,
        'boom_pct': round(float((a >= boom_thr).mean()) * 100),
        'bust_pct': round(float((a < bust_thr).mean()) * 100),
    }



def _blend_draws(rng, emp: list[float], mean: float, sigma: float,
                 k_prior: int, n: int) -> np.ndarray:
    """One game/start worth of FP draws. Empirical bootstrap with prob
    w = n_emp/(n_emp+k); parametric normal otherwise. Falls back cleanly to
    pure-parametric (thin history) or pure-empirical (no model mean)."""
    sigma = max(float(sigma or 0) or 1e-6, 1e-6)
    n_emp = len(emp)
    if mean is None:
        if n_emp == 0:
            return np.zeros(n)
        w = 1.0
        mean = 0.0
    else:
        w = n_emp / (n_emp + k_prior) if n_emp else 0.0
    out = rng.normal(float(mean), sigma, n)
    if w > 0:
        mask = rng.random(n) < w
        n_m = int(mask.sum())
        if n_m:
            out[mask] = rng.choice(np.asarray(emp, dtype=float), size=n_m, replace=True)
    return out


def _hitter_total_draws(rng, n_games: int, emp, mean_g, sigma_g, n_sims) -> np.ndarray:
    total = np.zeros(n_sims)
    for _ in range(max(n_games, 0)):
        total += _blend_draws(rng, emp, mean_g, sigma_g, K_PRIOR_H, n_sims)
    return total


def _rp_total_draws(rng, n_rem_games: int, p_app: float, emp, mean_app,
                    sigma_app, n_sims) -> np.ndarray:
    """Appearance count ~ Binomial(n_rem_games, p_app) per sim; each appearance
    draws blended FP (SV/HLD credit lives inside the empirical fp_rp values)."""
    if n_rem_games <= 0 or p_app <= 0:
        return np.zeros(n_sims)
    n_apps = rng.binomial(n_rem_games, min(p_app, 1.0), n_sims)
    total = np.zeros(n_sims)
    for g in range(n_rem_games):
        active = n_apps > g
        if not active.any():
            break
        total += _blend_draws(rng, emp, mean_app, sigma_app, K_PRIOR_RP, n_sims) * active
    return total



def resolve_player_mlbam(p):
    """Collision-safe mlbam for a rostered ESPN player object."""
    pos = (p.position or '?')
    if pos in ('SP', 'RP', 'P'):
        return _resolve_pitcher_mlbam(p.name, team=(p.proTeam or None),
                                      role=(pos if pos in ('SP', 'RP') else None))
    return player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)


def banked_sp_starts_from_box(sp_mlbams: set[int], week_start: date, today: date) -> int:
    """SP starts already banked this scoring week (week_start..yesterday) from the
    boxscore store — role-correct (gs flag) and no per-pitcher API calls."""
    df = _box('P')
    if df is None or not sp_mlbams:
        return 0
    sub = df[(df['mlbam_id'].isin(list(sp_mlbams))) & (df['gs'] == 1)]
    dates = sub['game_date'].astype(str)
    return int(((dates >= week_start.isoformat()) & (dates < today.isoformat())).sum())


def build_state(verbose=True):
    """Pull live matchup + schedules + projections; classify every active-slot
    player into H/SP/RP with remaining units and model mean/sigma."""
    mu = get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map = load_projections()
    today = _today_et()
    period = mu['period']

    # ── PERIOD-AWARE cap + window (2026-07-11) ───────────────────────────────
    # General rule: cap = 10 × weeks, weeks = len(matchupPeriods[period]) from
    # ESPN settings — so regular weeks -> 10 and 2-week playoff rounds -> 20
    # automatically. The ASG block (period 15) is the ONE exception: an explicit
    # override (cap 16 + a real Jul 6–19 window) that beats the formula, because
    # the All-Star break removes game-days AND ESPN lists it as a single week.
    # A standard single-week period resolves to SP_CAP(10) + a Mon–Sun week —
    # byte-identical to before.
    pmeta = resolve_period_meta(mu['league_obj'], period, today=today)
    weeks = pmeta['weeks']
    sp_cap = pmeta['sp_cap']
    week_start, week_end = pmeta['week_start'], pmeta['week_end']

    # Authoritative banked counts + loud multi-week / cap cross-checks from ESPN.
    meta = espn_period_meta(mu['league_obj'], period,
                            getattr(mu['mine'], 'team_id', None),
                            getattr(mu['opp'], 'team_id', None))
    # Warn ONLY when the period LOOKS single-week (weeks==1, no override) yet has
    # already scored across >1 week — the ASG-without-override trap. A clean
    # multi-week playoff round (weeks>=2) is handled by 10×weeks and must NOT warn.
    if not is_period_covered(period) and weeks == 1:
        span = meta.get('elapsed_span_days')
        if span is not None and span > 6:
            print('  ' + '!' * 70)
            print(f'  LOUD WARNING: matchup period {period} has already scored across '
                  f'{span + 1} calendar days (>1 week) but ESPN lists it as a single '
                  f'week and it has NO override in cap_math.PERIOD_CAP_OVERRIDES. '
                  f'Falling back to cap {sp_cap} + a single Mon–Sun week — very likely '
                  f'WRONG for an ASG-style block. Add {{{period}: <cap>}} + a window to '
                  f'cap_math.py. See the maintenance note there.')
            print('  ' + '!' * 70)

    if verbose:
        cov = ('OVERRIDE' if is_period_covered(period)
               else (f'10×{weeks}wk' if weeks > 1 else 'default'))
        print(f'  period {period}  cap {sp_cap} ({cov})  weeks {weeks}  '
              f'window {week_start} -> {week_end}  today {today}')
        print(f'  WTD: Ligers {mu["my_score"]:.1f} | {mu["opp"].team_name} {mu["opp_score"]:.1f}')

    # Schedules: ESPN primary, MLB Stats fallback — but ALWAYS fetch the all-30
    # MLB schedule too (probable-pitcher hydrate powers the FA streamer scan).
    schedules_by_team = fetch_espn_week_schedule(mu['league_obj'], week_start, week_end)
    all30 = sorted(set(ESPN_TO_MLB_TEAM.values()))
    mlb_sched_all = fetch_schedules_by_team(all30, today.isoformat(), week_end.isoformat())
    if not schedules_by_team or sum(len(v) for v in schedules_by_team.values()) == 0:
        schedules_by_team = mlb_sched_all
        if sum(len(v) for v in schedules_by_team.values()) == 0:
            raise RuntimeError('No schedule data for the week — refusing to simulate.')

    # Role-aware SP id sets (gotcha #8 — never trust .position alone)
    def _sp_ids(lineup):
        ids = {}
        for p in lineup:
            if (p.position or '?') not in ('SP', 'RP', 'P'):
                continue
            m = resolve_player_mlbam(p)
            if not m:
                continue
            role = detect_pitcher_role(p, mlbam_id=int(m))
            if role == 'SP':
                ids[p.name] = int(m)
        return ids

    my_sp_ids = _sp_ids(mu['my_lineup'])
    opp_sp_ids = _sp_ids(mu['opp_lineup'])
    sp_starts_by_pitcher = build_sp_starts_by_pitcher(
        set(my_sp_ids.values()) | set(opp_sp_ids.values()),
        schedules_by_team, today, week_end)

    # rp3 CSV frame for data_quality_tag (marcel_il gotcha #1) keyed by mlbam
    try:
        rp3_csv = pd.read_csv(OUT / 'xfp_rp3_projections.csv',
                              usecols=['pitcher', 'data_quality_tag'])
        dq_by_mlbam = dict(zip(rp3_csv['pitcher'].astype(int), rp3_csv['data_quality_tag']))
    except Exception:
        dq_by_mlbam = {}

    def _classify(lineup, side_label):
        """-> (hitters, rps, sp_start_events) for one roster side."""
        hitters, rps, sp_events = [], [], []
        for p in lineup:
            if not _is_active_slot(p):     # IL/IR slots only — BE counts (gotcha #7)
                continue
            proj = project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                  rh3_map, rp3_map, rp3_by_mlbam, rprs2_map,
                                  ts_map, today, week_end)
            mlbam = resolve_player_mlbam(p)
            pos = (p.position or '?')
            is_sp_proj = any(b.get('type') == 'start' for b in proj.get('breakdown', []))
            if is_sp_proj:
                nk = _norm(p.name)
                rp_info = rp3_map.get(nk, {})
                per_start = rp_info.get('per_start') or None
                sigma = (rp_info.get('sigma')
                         or fallback_sigma('SP', default=SIGMA_PER_SP_START))
                dq = dq_by_mlbam.get(int(mlbam)) if mlbam else None
                for b in proj['breakdown']:
                    if b.get('type') != 'start':
                        continue
                    sp_events.append({
                        'name': p.name, 'mlbam': int(mlbam) if mlbam else None,
                        'date': b.get('date'), 'opp': b.get('opp') or b.get('opp_team'),
                        'confirmed': bool(b.get('confirmed', True)),
                        'model_fp': float(b.get('fp_original', b.get('fp', 0)) or 0),
                        'per_start': per_start, 'sigma': float(sigma),
                        'data_quality_tag': dq,
                    })
            elif pos in ('SP', 'RP', 'P'):
                units = float(proj.get('units') or 0)
                if units <= 0 or not mlbam:
                    continue
                mlb_id = ESPN_TO_MLB_TEAM.get((p.proTeam or '').upper())
                n_rem = len([g for g in schedules_by_team.get(mlb_id, [])
                             if today.isoformat() <= g['date'] <= week_end.isoformat()])
                if n_rem <= 0:
                    continue
                rps.append({'name': p.name, 'mlbam': int(mlbam),
                            'n_rem_games': n_rem,
                            'p_app': min(units / n_rem, 1.0),
                            'mean_app': (proj['fp'] / units) if units else 0.0,
                            'sigma_app': (math.sqrt(max(proj['sigma2'], 0) / units)
                                          or fallback_sigma('RP', default=SIGMA_PER_RP_GAME))
                                         if units
                                         else fallback_sigma('RP', default=SIGMA_PER_RP_GAME)})
            else:
                units = float(proj.get('units') or 0)
                if units <= 0 or proj.get('fp', 0) <= 0:
                    continue
                n_games = int(round(units))
                if n_games <= 0 or not mlbam:
                    continue
                hitters.append({'name': p.name, 'mlbam': int(mlbam),
                                'n_games': n_games,
                                'mean_g': proj['fp'] / n_games,
                                'sigma_g': math.sqrt(max(proj['sigma2'], 0) / n_games)
                                           if proj['sigma2']
                                           else fallback_sigma('H', default=3.0),
                                'slot': getattr(p, 'lineup_slot', None)
                                        or getattr(p, 'lineupSlot', '') or '',
                                'injury': str(getattr(p, 'injuryStatus', '') or '')})
        # chronological cap ordering (BrownU live rule: starts 11+ are zeros)
        sp_events.sort(key=lambda e: (e['date'] or '9999', e['name']))
        return hitters, rps, sp_events

    my_h, my_rp, my_sp = _classify(mu['my_lineup'], 'mine')
    opp_h, opp_rp, opp_sp = _classify(mu['opp_lineup'], 'opp')

    # Banked SP starts: ESPN's authoritative statId-33 count is ground truth
    # (matches the x/CAP shown on the matchup screen); the boxscore-store count
    # over the resolved window is the fallback AND an independent cross-check.
    box_mine = banked_sp_starts_from_box(set(my_sp_ids.values()), week_start, today)
    box_opp = banked_sp_starts_from_box(set(opp_sp_ids.values()), week_start, today)
    banked_mine = meta.get('my_banked') if meta.get('my_banked') is not None else box_mine
    banked_opp = meta.get('opp_banked') if meta.get('opp_banked') is not None else box_opp
    if verbose:
        src = 'ESPN' if meta.get('my_banked') is not None else 'box'
        print(f'  banked SP starts: mine {banked_mine} (source {src}; box cross-check '
              f'{box_mine}), opp {banked_opp} (box {box_opp})  cap {sp_cap}')
        if meta.get('my_banked') is not None and meta['my_banked'] != box_mine:
            print(f'  note: ESPN banked ({meta["my_banked"]}) != box cross-check '
                  f'({box_mine}) — ESPN wins (bench-day starts / roster churn differ)')
    if banked_mine >= sp_cap or banked_opp >= sp_cap:
        print(f'  WARNING: a side has banked >= cap ({banked_mine}/{banked_opp} vs cap '
              f'{sp_cap}) — if starts remain, the cap for period {period} may be too low.')

    return {
        'mu': mu, 'today': today, 'week_start': week_start, 'week_end': week_end,
        'period': period, 'sp_cap': sp_cap, 'period_weeks': weeks,
        'period_covered': is_period_covered(period),
        'days_remaining': (week_end - today).days + 1,
        'schedules_by_team': schedules_by_team, 'mlb_sched_all': mlb_sched_all,
        'my_hitters': my_h, 'my_rps': my_rp, 'my_sp_events': my_sp,
        'opp_hitters': opp_h, 'opp_rps': opp_rp, 'opp_sp_events': opp_sp,
        'banked_mine': banked_mine, 'banked_opp': banked_opp,
        'cap_remaining_mine': max(sp_cap - banked_mine, 0),
        'cap_remaining_opp': max(sp_cap - banked_opp, 0),
        # ── added 2026-07-29 for the weekly optimizer (C3) ────────────────────
        # The projection maps and the SP-start table are kept rather than
        # discarded so a CANDIDATE can be projected through the same
        # project_player() path as a rostered player — the only way its units
        # (and especially the rprs2 RoS-total sigma) come out right.
        'proj_maps': {'rh3': rh3_map, 'rp3': rp3_map, 'rp3_by_mlbam': rp3_by_mlbam,
                      'rprs2': rprs2_map, 'ts': ts_map},
        'sp_starts_by_pitcher': sp_starts_by_pitcher,
        'my_sp_ids': my_sp_ids,
        # Roster composition, role-correct (detect_pitcher_role, never .position
        # alone — gotcha #8). The optimizer needs it to enforce the 4-RP floor and
        # positional coverage before it proposes a drop.
        'my_roster': _roster_meta(mu['my_lineup'], my_sp_ids),
    }



def _roster_meta(lineup, sp_ids: dict) -> list[dict]:
    """One record per rostered player: role-correct bucket + eligibility + slot.

    Bucket comes from ``detect_pitcher_role`` for pitchers, NEVER from
    ``.position`` alone — ESPN mislabels dual-eligible arms (canonical: Detmers
    2026, position='RP' but SP-eligible and starting), and the optimizer would
    otherwise miscount the RP floor and propose an illegal drop.
    """
    out = []
    for p in lineup:
        pos = (p.position or '?')
        slot = getattr(p, 'lineup_slot', None) or getattr(p, 'slot_position', None)
        elig = {str(s) for s in (getattr(p, 'eligibleSlots', []) or [])}
        if pos in ('SP', 'RP', 'P'):
            m = None
            try:
                m = resolve_player_mlbam(p)
            except Exception:
                m = None
            role = None
            try:
                role = detect_pitcher_role(p, mlbam_id=int(m)) if m else None
            except Exception:
                role = None
            bucket = role or ('SP' if p.name in sp_ids else 'RP')
        else:
            bucket = 'H'
            m = None
            try:
                m = resolve_player_mlbam(p)
            except Exception:
                m = None
        out.append({
            'name': p.name, 'mlbam': (int(m) if m else None), 'bucket': bucket,
            'espn_pos': pos, 'slot': slot, 'eligible': elig,
            'on_il': str(slot).upper() in ('IL', 'IR'),
            'injury_status': str(getattr(p, 'injuryStatus', '') or '').upper(),
        })
    return out


def _draw_key(entry) -> str:
    """Stable per-player draw key: mlbam when we have one, else a normalized name.

    mlbam-first is the whole point (DEFECT 1) — a name key silently merges
    same-name players. The name fallback exists only for the rare roster entry
    whose mlbam never resolved; it is prefixed so it can never collide with an id.
    """
    m = entry.get('mlbam')
    if m:
        return f'id:{int(m)}'
    return f'nm:{_norm(entry.get("name") or "unknown")}'


_BUCKET_ORD = {'H': 1, 'SP': 2, 'RP': 3}


def _stable_ident_int(ident) -> int:
    """Deterministic non-negative int from a candidate identity.

    ``ident`` is either an mlbam int (passes through unchanged, so every
    persisted dpwin seeded on an id stays bit-reproducible) or a ``'nm:...'``
    draw-key string for a candidate whose mlbam never resolved. Python's builtin
    ``hash()`` is process-salted, so a real digest is required for the string
    path to be a pure function of the player across runs.
    """
    if isinstance(ident, (int, np.integer)):
        return int(ident)
    if isinstance(ident, float) and not np.isnan(ident) and float(ident).is_integer():
        # a NaN-able pandas column hands back 123.0 for mlbam 123 — coerce
        # exactly as _draw_key does, or the same player would seed two
        # different streams depending on which frame he arrived through
        return int(ident)
    digest = hashlib.sha256(str(ident).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big')


def candidate_rng(seed: int, ident, bucket: str) -> np.random.Generator:
    """A per-candidate independent stream (DEFECT 2).

    Candidate draws MUST NOT come from the shared ``D['rng']``: doing so made a
    candidate's dpwin depend on how many candidates were scored before it, so the
    same player scored differently depending on pool ordering — fatal once dpwin
    is persisted. Seeding on (seed, ident, bucket) makes each candidate's draws a
    pure function of the run seed and the player.

    ``ident`` is the mlbam when known, else the ``'nm:...'`` fallback draw key
    (C1, 2026-08-01) — collapsing every unresolved id to a shared 0 gave two
    identity-less candidates common random numbers.
    """
    return np.random.default_rng([int(seed), _stable_ident_int(ident or 0),
                                  _BUCKET_ORD.get(bucket, 0)])


def precompute_draws(state, n_sims: int, seed: int):
    rng = np.random.default_rng(seed)
    # seed is retained so candidate_rng() can derive independent per-candidate
    # streams later without re-threading it through every call site.
    D = {'n_sims': n_sims, 'seed': int(seed), 'cand': {}}

    # DEFECT 1 FIX: key by mlbam, not name. Two same-name players on one roster
    # used to collapse into a single draw array (the Muncy collision class inside
    # the MC engine). `name` is carried so callers can still render, and
    # `_key_of` below resolves human-facing name args at the boundary.
    def _hitter_arrays(hitters, bucket='H'):
        out = {}
        for h in hitters:
            emp = emp_series(h['mlbam'], 'H')
            out[_draw_key(h)] = {
                'name': h['name'], 'mlbam': h.get('mlbam'),
                'arr': _hitter_total_draws(
                    rng, h['n_games'], emp, h['mean_g'], h['sigma_g'], n_sims)}
        return out

    def _rp_arrays(rps):
        out = {}
        for r in rps:
            emp = emp_series(r['mlbam'], 'RP')
            out[_draw_key(r)] = {
                'name': r['name'], 'mlbam': r.get('mlbam'),
                'arr': _rp_total_draws(
                    rng, r['n_rem_games'], r['p_app'], emp, r['mean_app'],
                    r['sigma_app'], n_sims)}
        return out

    def _sp_event_draws(events):
        """Per start-event: fp draw array + occurrence mask (Bernoulli 0.80 for
        rotation-gap predicted starts). Empirical per-start FP blended with a
        parametric draw at the rp3 per-start mean; marcel_il rows lean parametric
        automatically (thin/no 2026 start history -> low empirical weight)."""
        arr = []
        emp_cache = {}
        for e in events:
            key = e['mlbam']
            if key not in emp_cache:
                emp_cache[key] = emp_series(key, 'SP')
            emp = emp_cache[key]
            mean = e['per_start'] if e['per_start'] else (
                float(np.mean(emp)) if len(emp) >= 3 else FALLBACK_SP_PER_START)
            base = _blend_draws(rng, emp, mean, e['sigma'], K_PRIOR_SP, n_sims)
            # Retarget the draw distribution to the model's per-start EV so the
            # opponent tilt (already inside model_fp via project_sp_starts)
            # survives, while preserving the empirical variance SHAPE.
            #
            # DEFECT 3 FIX — this was `base = base * (target / ev)`, a
            # MULTIPLICATIVE rescale, which is wrong for a quantity that lives on
            # all of R. SP FP is K + IP*3.3 - H - 2*ER - BB - HBP, so negatives are
            # routine (16.4% of real starts finish <= 0). Multiplying meant:
            #   * a pitcher whose outlook IMPROVED (target/ev > 1) had his blow-up
            #     starts made WORSE — -20 FP became -30 — inverting tail severity;
            #   * the SD was scaled by the same factor, despite the old comment
            #     claiming variance shape was preserved;
            #   * it needed an `ev > 1.0` guard purely to dodge division blowups.
            # A LOCATION shift hits the identical target mean, genuinely preserves
            # the variance, cannot invert the tail, and needs no guard. Same class
            # as the opp_factor defect fixed in sp_bench_mc on 2026-07-29.
            #
            # AUDIT T25 (2026-08-01): the test used to be `model_fp > 0`, a
            # leftover from the multiplicative era where a non-positive target
            # would have blown up the ratio. A LOCATION shift has no such
            # failure mode. (Precision, per review: project_sp_starts does not
            # emit non-positive projections TODAY, so the old guard was dead
            # weight rather than an active bug — but nothing enforces that
            # floor, and the candidate SP path in ensure_candidate_draws
            # shifts unconditionally, so `> 0` was a latent divergence waiting
            # on an upstream change.) The finite
            # check keeps the one thing `> 0` was still buying: a NaN
            # projection fails SAFE instead of poisoning every draw for him.
            if np.isfinite(e['model_fp']):
                # model_fp includes the 0.80 unconfirmed discount; undo it since
                # occurrence is simulated explicitly below.
                target = e['model_fp'] / (1.0 if e['confirmed'] else UNCONFIRMED_START_P)
                base = base + (target - float(np.mean(base)))
            occ = (np.ones(n_sims, dtype=bool) if e['confirmed']
                   else rng.random(n_sims) < UNCONFIRMED_START_P)
            arr.append({'event': e, 'fp': base, 'occ': occ})
        return arr

    D['my_h'] = _hitter_arrays(state['my_hitters'])
    D['opp_h'] = _hitter_arrays(state['opp_hitters'])
    D['my_rp'] = _rp_arrays(state['my_rps'])
    D['opp_rp'] = _rp_arrays(state['opp_rps'])
    D['my_sp'] = _sp_event_draws(state['my_sp_events'])
    D['opp_sp'] = _sp_event_draws(state['opp_sp_events'])
    D['rng'] = rng
    return D


def _sp_side_total(sp_draws: list[dict], cap_remaining: int,
                   bench: set | None = None, extra: list[dict] | None = None,
                   n_sims: int | None = None) -> np.ndarray:
    """Chronological cap inside each trial: among starts that OCCUR, only the
    first `cap_remaining` (by date) score. extra = additional event-draw dicts
    (FA adds), which correctly compete for the same cap slots.

    bench entries may be keyed EITHER (mlbam, date) or (name, date). The mlbam
    form is preferred and is what the engine emits; the name form is accepted so
    existing callers and human-facing args keep working (DEFECT 1 boundary).
    """
    def _benched(d) -> bool:
        if not bench:
            return False
        ev = d['event']
        m = ev.get('mlbam')
        return (((int(m), ev['date']) in bench) if m else False)             or ((ev['name'], ev['date']) in bench)

    events = [d for d in sp_draws if not _benched(d)]
    if extra:
        events = events + list(extra)
    if not events:
        # LATENT BUG FIXED 2026-07-29 (found by tests/test_leverage_engine.py):
        # the length used to be derived from sp_draws[0] / extra[0], so a side
        # with NO SP events at all returned a ZERO-LENGTH array and the caller
        # blew up on `my + <empty>` broadcast. It never fired live because both
        # sides always had starts — but dropping every SP, or an empty synthetic
        # roster, reaches it. n_sims is now passed explicitly so the return
        # length never depends on the contents.
        if n_sims is not None:
            return np.zeros(int(n_sims))
        n = (sp_draws[0]['fp'].shape[0] if sp_draws
             else (extra[0]['fp'].shape[0] if extra else 0))
        return np.zeros(n)
    events.sort(key=lambda d: (d['event']['date'] or '9999', d['event']['name']))
    occ = np.stack([d['occ'] for d in events])           # (E, S)
    fp = np.stack([d['fp'] for d in events])             # (E, S)
    order_count = np.cumsum(occ, axis=0)                 # nth occurred start
    keep = occ & (order_count <= cap_remaining)
    return (fp * keep).sum(axis=0)


def _resolve_keys(D, which: str, wanted) -> set:
    """Map human-facing names OR mlbam ids onto the mlbam-keyed draw dict.

    Callers (CLI args, skill prompts, the optimizer's candidate rows) legitimately
    speak in names; the draw dict speaks in ids after the DEFECT 1 fix. This is
    the single boundary where the translation happens.
    """
    if not wanted:
        return frozenset()
    table = D[which]
    out = set()
    for w in wanted:
        if w in table:                      # already a draw key
            out.add(w)
            continue
        if isinstance(w, (int, np.integer)) and f'id:{int(w)}' in table:
            out.add(f'id:{int(w)}')
            continue
        nw = _norm(str(w))
        hits = [k for k, v in table.items() if _norm(v['name']) == nw]
        if len(hits) == 1:
            out.add(hits[0])
        elif len(hits) > 1:
            # refuse-to-guess, same contract as resolve_batter_id: a duplicated
            # name is exactly the case DEFECT 1 was about
            raise ValueError(
                f'{w!r} matches {len(hits)} players in {which} '
                f'({[table[h]["name"] for h in hits]}) — pass an mlbam id')
    return out


def assemble(state, D, *, zero_hitters: set = frozenset(),
             bench_starts: set = frozenset(), extra_my_sp: list | None = None,
             drop_hitters: set = frozenset(), drop_rps: set = frozenset(),
             drop_sp_mlbams: set = frozenset(),
             extra_my_h: list | None = None, extra_my_rp: list | None = None):
    """-> (my_total, opp_total) arrays for one scenario.

    zero_hitters / bench_starts / extra_my_sp are the original three levers and
    keep their meaning. The drop_* and extra_my_{h,rp} arguments were added
    2026-07-29 so a full add/drop SWAP is one scenario (see ``delta_pwin``).

    zero_hitters vs drop_hitters both remove a hitter's remaining games; they are
    kept distinct because they mean different things to a reader — "sit him" vs
    "he is off the roster" — and the optimizer needs the latter.
    """
    n = D['n_sims']
    my = np.full(n, float(state['mu']['my_score']))
    opp = np.full(n, float(state['mu']['opp_score']))
    zeroed = set(zero_hitters) | set(drop_hitters)
    # Guard against the regression this refactor itself introduced: when D moved
    # from name-keys to mlbam-keys, callers still passing a NAME matched nothing,
    # so every "if benched" delta silently read 0.00pp — a wrong answer that
    # looked like a legitimate "benching him costs nothing". Anything that is not
    # a real draw key is now a hard error rather than a no-op. Use _draw_key(entry)
    # or _resolve_keys(D, 'my_h', names).
    _bad = [k for k in zeroed if k not in D['my_h']]
    if _bad:
        raise KeyError(
            f'assemble(): {_bad!r} are not draw keys in D["my_h"]. Draws are keyed '
            f'by mlbam since 2026-07-29 — pass _draw_key(entry), or translate '
            f'names with _resolve_keys(D, "my_h", names). Silently ignoring these '
            f'would report every hitter as free to bench.')
    _bad_rp = [k for k in set(drop_rps) if k not in D['my_rp']]
    if _bad_rp:
        raise KeyError(
            f'assemble(): {_bad_rp!r} are not draw keys in D["my_rp"] (same '
            f'mlbam-key contract as my_h).')
    for key, rec in D['my_h'].items():
        if key not in zeroed:
            my = my + rec['arr']
    for extra in (extra_my_h or []):
        my = my + extra['arr']
    for key, rec in D['my_rp'].items():
        if key not in drop_rps:
            my = my + rec['arr']
    for extra in (extra_my_rp or []):
        my = my + extra['arr']
    # A dropped SP's remaining events leave the pool entirely BEFORE the cap is
    # applied, which matters: benching frees a cap slot for a later start, and so
    # does dropping, but only dropping also removes him as a future candidate.
    my_sp = D['my_sp']
    if drop_sp_mlbams:
        my_sp = [d for d in my_sp
                 if int(d['event'].get('mlbam') or 0) not in drop_sp_mlbams]
    my = my + _sp_side_total(my_sp, state['cap_remaining_mine'],
                             bench=bench_starts, extra=extra_my_sp, n_sims=n)
    for rec in D['opp_h'].values():
        opp = opp + rec['arr']
    for rec in D['opp_rp'].values():
        opp = opp + rec['arr']
    opp = opp + _sp_side_total(D['opp_sp'], state['cap_remaining_opp'], n_sims=n)
    return my, opp


def pwin(my: np.ndarray, opp: np.ndarray) -> float:
    return float((my > opp).mean() + 0.5 * (my == opp).mean())


def mc_se(p: float, n_sims: int) -> float:
    """Monte-Carlo standard error of a P(win) estimate.

    Reported alongside every dpwin so a caller can tell a real edge from
    simulation noise. Scenarios sharing precomputed draws are strongly
    positively correlated, so this OVERSTATES the error on a *difference*
    between two such scenarios — it is the honest bound for comparing across
    independently-drawn candidates, which is the case that actually bites.
    """
    p = min(max(float(p), 0.0), 1.0)
    return float(np.sqrt(max(p * (1.0 - p), 1e-12) / max(int(n_sims), 1)))


# ─────────────────────────────────────────────────────────────────────────────
# Candidate draws + the general Delta-P(win) primitive
# ─────────────────────────────────────────────────────────────────────────────

def ensure_candidate_draws(state, D, cand: dict) -> dict:
    """Build (and memoize) the draw arrays for a candidate ADD.

    ``cand`` = {'mlbam', 'name', 'bucket' in {'H','SP','RP'}, 'player' (the ESPN
    Player object), optional 'starts' for SP}. Returns a dict shaped like the
    matching entry in ``D['my_h'] / D['my_rp']``, or for SP a list of event-draw
    dicts suitable for ``extra`` in ``_sp_side_total``.

    Everything routes through ``project_player`` so the candidate inherits the
    SAME unit conventions as a rostered player — critically for RP, whose rprs2
    sigma is a rest-of-season TOTAL derived from an IQR, not a per-appearance
    number. Deriving it by hand from the raw map is how you get a silently wrong
    variance.

    Draws come from ``candidate_rng`` (DEFECT 2), so a candidate's dpwin is a
    pure function of (run seed, player) and does not shift when the pool changes.

    The memo key is IDENTITY-COMPLETE (C1, 2026-08-01): it uses the same
    ``_draw_key`` semantics as the roster path — ``id:<mlbam>`` when the id
    resolved, else ``nm:<normalized name>``. The old ``int(mlbam or 0)`` key
    collapsed every unresolved id to a shared sentinel, so the SECOND
    identity-less candidate in a pool received the FIRST one's cached draw
    object (wrong name, wrong array) and its scored mean moved with pool order.
    """
    bucket = cand['bucket']
    ident = _draw_key(cand)
    key = (ident, bucket, cand.get('effective_date') or '')
    if key in D['cand']:
        return D['cand'][key]

    n_sims = D['n_sims']
    rng = candidate_rng(D['seed'], cand.get('mlbam') or ident, bucket)
    proj = cand.get('proj')
    if proj is None:
        raise ValueError(
            f"candidate {cand.get('name')!r} has no 'proj' — build it with "
            "project_player() so unit conventions match rostered players")

    units = float(proj.get('units') or 0)
    fp = float(proj.get('fp') or 0)
    sigma2 = float(proj.get('sigma2') or 0)
    if units <= 0:
        # No remaining events in the window -> the add cannot score. Zeros, not
        # a raise: a legitimately-idle candidate is a real answer (dpwin ~ 0).
        out = {'name': cand.get('name'), 'mlbam': cand.get('mlbam'),
               'arr': np.zeros(n_sims), 'units': 0.0}
        D['cand'][key] = out
        return out

    emp = emp_series(cand.get('mlbam'), bucket)
    if bucket == 'H':
        n_games = int(round(units))
        out = {'name': cand.get('name'), 'mlbam': cand.get('mlbam'),
               'units': units,
               'arr': _hitter_total_draws(rng, n_games, emp, fp / units,
                                         math.sqrt(sigma2 / units), n_sims)}
    elif bucket == 'RP':
        n_rem = int(cand.get('n_rem_games') or round(units))
        p_app = min(units / n_rem, 1.0) if n_rem > 0 else 0.0
        out = {'name': cand.get('name'), 'mlbam': cand.get('mlbam'),
               'units': units,
               'arr': _rp_total_draws(rng, n_rem, p_app, emp, fp / units,
                                      math.sqrt(sigma2 / units), n_sims)}
    else:  # SP -> a list of per-start event draws
        events = []
        starts = cand.get('starts') or []
        per_start = fp / units
        sigma = math.sqrt(sigma2 / units)
        for s in starts:
            base = _blend_draws(rng, emp, per_start, sigma, K_PRIOR_SP, n_sims)
            # location shift, per DEFECT 3 — never multiplicative
            base = base + (per_start - float(np.mean(base)))
            events.append({
                'event': {'name': cand.get('name'), 'date': s['date'],
                          'opp': s.get('opp'), 'confirmed': bool(s.get('confirmed', True)),
                          'mlbam': cand.get('mlbam')},
                'fp': base,
                'occ': (np.ones(n_sims, dtype=bool) if s.get('confirmed', True)
                        else rng.random(n_sims) < UNCONFIRMED_START_P)})
        out = {'name': cand.get('name'), 'mlbam': cand.get('mlbam'),
               'units': units, 'events': events}
    D['cand'][key] = out
    return out


def delta_pwin(state, D, *, add=(), drop=(), bench=(), base_pwin=None) -> dict:
    """The general Delta-P(win) primitive: score ONE roster counterfactual.

    add   — candidate dicts (see ``ensure_candidate_draws``). H / SP / RP all
            supported; previously only FA SP adds existed.
    drop  — rostered players leaving: names, mlbam ids, or draw keys. Mixed
            buckets fine; a dropped SP's remaining starts leave the cap pool.
    bench — start events withheld: ``('SP', name_or_mlbam, 'YYYY-MM-DD')``, or a
            bare ``(name_or_mlbam, date)`` pair; or ``('H', name_or_mlbam)`` to
            sit a hitter's remaining games.

    An add+drop in one call is a SWAP, evaluated as a single scenario — which is
    the thing the optimizer actually needs and which no previous entry point
    could express.

    LEGALITY IS NOT CHECKED HERE. This function scores; the optimizer enforces
    roster slots, the SP cap and the 4-RP floor. Keeping them separate means an
    illegal-but-informative scenario ("what would dropping a whole bucket do?")
    stays measurable.

    -> {'pwin', 'dpwin', 'mc_se', 'scenario'}
    """
    # --- partition the drop list by bucket
    drop_h = _resolve_keys(D, 'my_h', [d for d in drop])
    drop_rp = _resolve_keys(D, 'my_rp', [d for d in drop])
    sp_by_id, sp_by_name = {}, {}
    for d in D['my_sp']:
        ev = d['event']
        if ev.get('mlbam'):
            sp_by_id[int(ev['mlbam'])] = int(ev['mlbam'])
        sp_by_name.setdefault(_norm(ev['name']), set()).add(
            int(ev['mlbam']) if ev.get('mlbam') else 0)
    drop_sp = set()
    for d in drop:
        if isinstance(d, (int, np.integer)) and int(d) in sp_by_id:
            drop_sp.add(int(d))
        else:
            drop_sp |= {m for m in sp_by_name.get(_norm(str(d)), set()) if m}

    # --- benches
    bench_starts, zero_hitters = set(), set()
    for b in bench:
        if not isinstance(b, (tuple, list)):
            continue
        if len(b) == 3 and str(b[0]).upper() in ('SP', 'P'):
            bench_starts.add((b[1], b[2]))
            if isinstance(b[1], (int, np.integer)):
                bench_starts.add((int(b[1]), b[2]))
        elif len(b) == 2 and str(b[0]).upper() == 'H':
            zero_hitters |= _resolve_keys(D, 'my_h', [b[1]])
        elif len(b) == 2:
            bench_starts.add((b[0], b[1]))

    # --- adds
    extra_h, extra_rp, extra_sp = [], [], []
    for c in add:
        built = ensure_candidate_draws(state, D, c)
        if c['bucket'] == 'H':
            extra_h.append(built)
        elif c['bucket'] == 'RP':
            extra_rp.append(built)
        else:
            extra_sp.extend(built.get('events') or [])

    my, opp = assemble(
        state, D,
        zero_hitters=zero_hitters, bench_starts=bench_starts,
        extra_my_sp=(extra_sp or None),
        drop_hitters=drop_h, drop_rps=drop_rp, drop_sp_mlbams=drop_sp,
        extra_my_h=(extra_h or None), extra_my_rp=(extra_rp or None))

    p = pwin(my, opp)
    if base_pwin is None:
        b_my, b_opp = assemble(state, D)
        base_pwin = pwin(b_my, b_opp)
    return {
        'pwin': round(p, 6),
        'dpwin': round(p - base_pwin, 6),
        'mc_se': round(mc_se(p, D['n_sims']), 6),
        'scenario': {
            'add': [f"{c.get('name')}({c['bucket']})" for c in add],
            'drop': sorted(str(d) for d in drop),
            'bench': sorted(str(b) for b in bench),
        },
    }


def variance_sensitivity(state, my: np.ndarray, opp: np.ndarray,
                         scale: float = 1.2) -> dict:
    """dP(win)/d(variance): rescale MY remaining-FP deviations around their mean
    (the 'variance-scaled bench alternative' at team level) and re-measure P(win)."""
    base_score = float(state['mu']['my_score'])
    rem = my - base_score
    mu_rem = rem.mean()
    hi = base_score + mu_rem + (rem - mu_rem) * scale
    lo = base_score + mu_rem + (rem - mu_rem) / scale
    p0 = pwin(my, opp)
    return {
        'pwin_var_up20': round(pwin(hi, opp), 4),
        'pwin_var_down20': round(pwin(lo, opp), 4),
        'dpwin_dvar': round(pwin(hi, opp) - pwin(lo, opp), 4),
        'baseline': round(p0, 4),
    }


def classify_regime(p: float) -> str:
    if p < TRAILING_MAX:
        return 'TRAILING'
    if p > LEADING_MIN:
        return 'LEADING'
    return 'CLOSE'


REGIME_BLURB = {
    'TRAILING': 'variance is an ASSET — prefer boom/bust (high-sigma, high boom%) plays',
    'LEADING': 'variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays',
    'CLOSE': 'E[FP] is approximately the right objective — rank by expected points',
}

