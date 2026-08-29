"""run_weekly_optimizer — search roster moves that maximize P(win) this period.

WHAT MAKES THIS DIFFERENT FROM EVERY OTHER BOARD
------------------------------------------------
Every ranking skill in this repo sorts by expected fantasy points. But BrownU H2H
is won by P(my_total > opp_total), and those are not the same objective. A +5 RoS
FP add that raises weekly variance is worth MORE when you are trailing and LESS
when you are ahead — and an FP-sorted board cannot express that, because the
information is in the distribution, not the mean.

This searches actual add/drop/bench combinations and scores each by Delta-P(win)
under the real roster constraints.

WHY dpwin IS THE OBJECTIVE, WITH NO VARIANCE TERM BOLTED ON
-----------------------------------------------------------
P(win) ALREADY prices variance correctly. When trailing, a high-variance
candidate mechanically puts more mass above the opponent's distribution, so
maximizing dpwin automatically prefers boom profiles; when leading it
automatically prefers floor. Adding an explicit variance bonus would DOUBLE-COUNT
the very effect the objective already captures.

The regime label is still used, but only where it belongs: as a TIE-BREAK. Two
moves inside 2x the Monte-Carlo standard error are not distinguishable by dpwin,
and there the regime rule (TRAILING -> higher boom%, LEADING -> lower bust%) is
the honest discriminator. `mc_se` is reported on every row so a reader can see
which gaps are real.

SEARCH
------
Exhaustive is infeasible and unnecessary. One `assemble`+`pwin` is a sum of ~30
length-10k arrays over precomputed draws — low single-digit milliseconds — so:

  round 1  score every LEGAL single swap (add x drop) plus pure benches
  apply    take the best positive-MARGINAL move onto a VIRTUAL roster
  repeat   up to --max-moves times; every later step is scored CUMULATIVELY
           (original state + all prior adds − all prior drops + this move),
           because delta_pwin can only evaluate against the original state —
           and each row's `dpwin` is the MARGINAL gain vs the prior steps'
           endpoint, so marginals sum to the plan total and the running
           P(win) is real, never base + a sum of base-relative numbers
  pair     then exhaustively check pairs among the best row per distinct
           round-1 add; `assemble_plan` ADOPTS the pair when it beats the
           greedy endpoint by more than the pair's MC se

A later step may never drop a player an earlier step added: that is an UNDO
(the net plan is a shorter plan), and the engine cannot score it anyway — an
unrostered "drop" silently no-ops in _resolve_keys, which is how the
2026-07-30 run manufactured "ADD Jeffers / DROP Pederson +8.84pp" out of a
free add. Prior adds are excluded from the droppable pool (legality still
checks the FULL virtual roster).

The pair check exists for two real cases: two SP adds competing for the same
remaining cap slots (the second is worth much less than its solo score), and
greedy myopia — a tie-break-influenced step 1 that walks past the best joint
endpoint (2026-07-30: the boom tie-break took Pederson first while the
Jeffers+Pederson pair at +16.98pp was printed and discarded). Outside those
the objective is close to separable, which is why greedy is adequate and a
full K=2 sweep (~45k evals) buys almost nothing.

CONSTRAINTS are enforced by lib/roster_rules (13H/9P/4BE/3IL, the 4-RP floor as
a FLOOR never a target, positional coverage, period-aware SP cap). Illegal moves
are reported WITH THEIR REASON rather than silently dropped — "you cannot do the
obvious thing, and here is why" is most of the value when it applies.

Every evaluated candidate — chosen and rejected — is logged to
data/research/dpwin_history.parquet, because the rejected surface is what the
counterfactual ledger later settles against.

RULE 13: decision layer only. Never touches rh3/rp3/rprs2/baseline xFP.

Usage
  python scripts/xfp/run_weekly_optimizer.py
  python scripts/xfp/run_weekly_optimizer.py --max-moves 3 --pool 10 --sims 20000
  python scripts/xfp/run_weekly_optimizer.py --no-log        # skip history write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from scripts.xfp.lib.leverage_engine import (  # noqa: E402
    build_state, precompute_draws, assemble, pwin, mc_se, delta_pwin,
    ensure_candidate_draws, classify_regime, REGIME_BLURB, emp_series,
    series_stats, _draw_key, OUT, resolve_player_mlbam,
)
from scripts.xfp.lib import roster_rules as RR  # noqa: E402
from scripts.xfp.lib import dpwin_history  # noqa: E402
from scripts.xfp.lib import title_equity as TE  # noqa: E402
from scripts.xfp.lib.boom_bust import SP_BOOM, SP_BUST, H_BOOM, H_BUST  # noqa: E402
from build_matchup_dashboard import (  # noqa: E402
    project_player, ESPN_TO_MLB_TEAM, IL_INJURY_STATES, _norm,
    build_sp_starts_by_pitcher,
)
from plv_clone.utils.name_match import safe_name_key as _ckey  # noqa: E402

HIT_POS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH'}

# FA pitchers granted rotation-gap PREDICTION in build_candidates (top-N by rp3
# per-start rate). Confirmed probables are free for the whole pool; prediction
# is per-pitcher HTTP, so this bounds optimizer wall-clock at ~40 extra calls
# instead of ~2000 (the 2026-08-29 hang). 40 comfortably covers every arm that
# could crack a top-8 candidate pool.
FA_PREDICT_TOP_N = 40


# ─────────────────────────────────────────────────────────────────────────────
# Candidate pool
# ─────────────────────────────────────────────────────────────────────────────

def _realized_maps(days: int = 30) -> dict:
    """{mlbam: realized FP per game/start over the trailing window}.

    The realized leg's ranking key. Per-event rather than total so a player who
    missed time is not punished for the games he did not get.
    """
    import pandas as _pd
    out = {}
    for path, col in (('boxscore_hitters.parquet', 'fp_h'),
                      ('boxscore_pitchers.parquet', 'fp_sp')):
        p = ROOT / 'data' / 'research' / 'xfp_cache' / path
        if not p.exists():
            continue
        try:
            df = _pd.read_parquet(p)
        except Exception:
            continue
        df['game_date'] = _pd.to_datetime(df['game_date'])
        cut = df['game_date'].max() - _pd.Timedelta(days=days)
        w = df[df['game_date'] > cut]
        if col == 'fp_sp' and 'gs' in w.columns:
            w = w[w['gs'] > 0]
        if not len(w):
            continue
        for mid, v in w.groupby('mlbam_id')[col].mean().items():
            out[int(mid)] = float(v)
    return out


def build_candidates(state, top_n: int = 8, verbose: bool = True,
                     realized_n: int = 0, include=()) -> list[dict]:
    """Top-N FA per bucket, projected through project_player.

    Uses the ONE FA pull already on the state (gotcha #6: never per-position
    size caps — a single free_agents(size=2000) then filter). Every candidate is
    projected through the same path as a rostered player so its units match;
    that matters most for RP, whose rprs2 sigma is a rest-of-season TOTAL derived
    from an IQR rather than a per-appearance number.
    """
    _inc_keys = {_ckey(n) for n in (include or ())}
    league = state['mu']['league_obj']
    try:
        fas = league.free_agents(size=2000)
    except Exception as exc:
        print(f'  WARN FA pool fetch failed ({exc}) — add candidates unavailable')
        return []

    maps = state['proj_maps']

    # Pass 1 — classify buckets, then extend the SP-start map to FA pitchers.
    # build_state builds sp_starts_by_pitcher over ROSTERED ids only, so
    # without this every FA SP projects 0 starts and dpwin pins at +0.00
    # (found 2026-08-07 via the forced-include Griffin Jax scenario).
    pool: list[tuple] = []
    fa_pitcher_ids: set[int] = set()
    for p in fas:
        pos = (getattr(p, 'position', '') or '')
        elig = {str(s) for s in (getattr(p, 'eligibleSlots', []) or [])}
        inj = str(getattr(p, 'injuryStatus', '') or '').upper()
        if inj in IL_INJURY_STATES and inj != 'DAY_TO_DAY':
            continue
        if pos in HIT_POS or (elig & HIT_POS):
            bucket = 'H'
        elif pos in ('SP', 'RP', 'P') or ({'SP', 'RP'} & elig):
            bucket = 'SP' if ('SP' in elig or pos == 'SP') else 'RP'
            m = resolve_player_mlbam(p)
            if m:
                fa_pitcher_ids.add(int(m))
        else:
            continue
        pool.append((p, bucket, pos, elig, inj))

    starts_map = dict(state['sp_starts_by_pitcher'])
    if fa_pitcher_ids:
        # Rotation-gap prediction costs 1-2 sequential HTTP calls PER pitcher,
        # and this set is the whole FA pitcher pool (~1000 ids) — unbounded it
        # is a ~30-minute silent stall (the 2026-08-29 daily-briefing hang).
        # Confirmed probables stay free for EVERYONE (one schedule call);
        # prediction is granted only to the FA arms rp3 rates as plausible
        # streamers, plus any --include name (forced candidates must project).
        rp3_by_mlbam = state['proj_maps'].get('rp3_by_mlbam') or {}
        ranked = sorted(
            (pid for pid in fa_pitcher_ids if pid in rp3_by_mlbam),
            key=lambda pid: -(rp3_by_mlbam[pid].get('per_start') or 0))
        predict_ids = set(ranked[:FA_PREDICT_TOP_N])
        if _inc_keys:
            predict_ids |= {int(m) for p, b, *_ in pool
                            if b in ('SP', 'RP') and _ckey(p.name) in _inc_keys
                            and (m := resolve_player_mlbam(p))}
        try:
            starts_map.update(build_sp_starts_by_pitcher(
                fa_pitcher_ids, state['schedules_by_team'],
                state['today'], state['week_end'],
                predict_ids=predict_ids))
        except Exception as exc:
            print(f'  WARN FA SP start-map build failed ({exc}) — '
                  f'FA SP adds will project 0 starts')

    cands: list[dict] = []
    _proj_drops: dict = {}
    _pool_by_bucket: dict = {}
    for p, bucket, pos, elig, inj in pool:
        _pool_by_bucket[bucket] = _pool_by_bucket.get(bucket, 0) + 1
        try:
            proj = project_player(p, state['schedules_by_team'],
                                  starts_map,
                                  maps['rh3'], maps['rp3'], maps['rp3_by_mlbam'],
                                  maps['rprs2'], maps['ts'],
                                  state['today'], state['week_end'])
        except Exception as exc:
            # issue #39: a silent per-row drop can empty a whole bucket and
            # report "no pitching upgrade exists" — collect and gate below.
            _proj_drops[bucket] = _proj_drops.get(bucket, 0) + 1
            _proj_drops.setdefault('_names', []).append((p.name, repr(exc)))
            continue
        units = float(proj.get('units') or 0)
        fp = float(proj.get('fp') or 0)
        forced = _ckey(p.name) in _inc_keys
        if (units <= 0 or fp <= 0) and not forced:
            continue          # no remaining events in the window -> cannot help
        cands.append({
            'name': p.name, 'bucket': bucket, 'espn_pos': pos, 'eligible': elig,
            'team': getattr(p, 'proTeam', ''), 'proj': proj,
            'fp': fp, 'units': units,
            'per_unit': (fp / units) if units else 0.0,
            'pct_owned': float(getattr(p, 'percent_owned', 0) or 0),
            'injury_status': inj,
            'starts': [b for b in (proj.get('breakdown') or [])
                       if b.get('type') == 'start'],
        })

    # realized leg needs ids; resolve before ranking so the key exists
    if realized_n:
        _names = _proj_drops.pop('_names', [])
        if _names:
            print(f'  !! {len(_names)} candidate(s) dropped on projection error: '
                  f'{", ".join(n for n, _ in _names[:6])}'
                  f'{" ..." if len(_names) > 6 else ""}')
        check_projection_drops(_proj_drops, _pool_by_bucket)
        resolve_candidate_mlbams(state, cands, verbose=False)
        rmap = _realized_maps()
        for c in cands:
            c['realized_fp'] = rmap.get(int(c['mlbam'])) if c.get('mlbam') else 0.0
            c['realized_fp'] = float(c['realized_fp'] or 0.0)

    missing = []
    out = select_pool(cands, top_n=top_n, realized_n=realized_n,
                      include=include, missing_out=missing)
    if verbose:
        n = {b: sum(1 for c in out if c['bucket'] == b) for b in ('H', 'SP', 'RP')}
        print(f'  candidate pool: {len(out)} FAs (H {n["H"]} / SP {n["SP"]} / RP {n["RP"]})'
              f' from {len(cands)} projectable'
              + (f'  [top-{top_n} projected + top-{realized_n} realized]'
                 if realized_n else ''))
        forced = [c['name'] for c in out if c.get('forced_include')]
        if forced:
            print(f'  forced into pool via --include: {", ".join(forced)}')
        if missing:
            # NEVER silent: a typo'd --include must not read as a clean run.
            print(f'  !! --include names NOT FOUND in the FA pool (ignored): '
                  f'{", ".join(missing)}')
    return out


def parse_scratch(spec) -> list[tuple]:
    """'Name:YYYY-MM-DD[,Name:YYYY-MM-DD...]' -> [(name, date), ...].

    RAISES on anything malformed. A silently-dropped scratch is precisely the
    failure this flag exists to prevent: the run would look clean while the SP
    cap stayed wrong, which on 2026-08-01 moved one candidate by 7.7pp.
    """
    if not spec or not str(spec).strip():
        return []
    out = []
    for chunk in str(spec).split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ':' not in chunk:
            raise ValueError(
                f'--scratch entry {chunk!r} is not NAME:YYYY-MM-DD')
        name, _, dt = chunk.rpartition(':')
        name, dt = name.strip(), dt.strip()
        if not name:
            raise ValueError(f'--scratch entry {chunk!r} has no player name')
        try:
            parsed = datetime.strptime(dt, '%Y-%m-%d').date()
        except ValueError as exc:
            raise ValueError(
                f'--scratch entry {chunk!r}: {dt!r} is not YYYY-MM-DD') from exc
        out.append((name, parsed.isoformat()))
    return out


def select_pool(cands: list[dict], *, top_n: int, realized_n: int,
                include=(), missing_out=None) -> list[dict]:
    """Candidate pool = top-N PROJECTED  U  top-N REALIZED  U  forced includes.

    Two legs, because they fail differently. The projected leg cannot surface a
    player the model underrates however much he is actually scoring; the
    realized leg cannot surface a role change the box score has not caught up
    to yet. Union, deduped by canonical name key, so neither displaces the
    other.

    `include` bypasses BOTH legs and every upstream filter — that is the point:
    Griffin Jax projected 0.00 (unresolved mlbam, so no start was found) and
    was therefore invisible to a pool ranked on projection.
    """
    inc = {_ckey(n) for n in (include or ())}
    seen, out = set(), []

    def _take(c, forced=False):
        k = _ckey(c['name'])
        if k in seen:
            return
        seen.add(k)
        if forced:
            c['forced_include'] = True
        out.append(c)

    for c in cands:
        if _ckey(c['name']) in inc:
            _take(c, forced=True)
    for b in ('H', 'SP', 'RP'):
        sub = [c for c in cands if c['bucket'] == b]
        for c in sorted(sub, key=lambda x: -float(x.get('fp') or 0))[:top_n]:
            _take(c)
        if realized_n:
            for c in sorted(sub, key=lambda x: -float(x.get('realized_fp') or 0)
                            )[:realized_n]:
                _take(c)
    if missing_out is not None:
        have = {_ckey(c['name']) for c in cands}
        missing_out.extend(n for n in (include or ()) if _ckey(n) not in have)
    return out


def check_projection_drops(drops_by_bucket: dict, pool_by_bucket: dict,
                           max_frac: float = 0.20) -> None:
    """Refuse to report a silently-emptied candidate bucket as a clean run
    (issue #39). Raises when any bucket lost more than max_frac of its pool
    to projection errors."""
    for bucket, n_drop in drops_by_bucket.items():
        n_pool = pool_by_bucket.get(bucket, 0)
        if n_pool and (n_drop / n_pool) > max_frac:
            raise RuntimeError(
                f'{n_drop}/{n_pool} {bucket} candidates dropped on projection '
                f'errors (> {max_frac:.0%}) — a schema change upstream would '
                f'otherwise masquerade as "no upgrade exists"')


def resolve_candidate_mlbams(state, cands: list[dict],
                             verbose: bool = True) -> None:
    """Attach mlbam to each candidate (collision-safe), in place.

    A candidate without an id cannot be logged to dpwin history in a way the
    reconciler can join, so this is not cosmetic.
    """
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
    for c in cands:
        m = None
        try:
            if c['bucket'] == 'H':
                m = resolve_batter_id(c['name'], team=c.get('team') or None,
                                      position=c.get('espn_pos') or None)
            else:
                m = resolve_pitcher_id(c['name'], team=c.get('team') or None,
                                       role=c['bucket'])
        except Exception:
            m = None
        if not m:
            # SP candidates carry the probable-pitcher id on their start rows
            for s in (c.get('starts') or []):
                if s.get('mlbam') or s.get('pid'):
                    m = s.get('mlbam') or s.get('pid')
                    break
        if not m:
            # issue #39: CSV-only lookups miss current-season debutants; the
            # sibling resolvers already layer CSV -> MLB Stats API. Same here.
            try:
                from lib.leverage_engine import (_resolve_pitcher_mlbam,
                                                 _resolve_mlbam_via_api)
                if c['bucket'] in ('SP', 'RP'):
                    m = _resolve_pitcher_mlbam(c['name'],
                                               team=c.get('team') or None,
                                               role=c['bucket'])
                else:
                    m = _resolve_mlbam_via_api(c['name'])
            except Exception:
                m = None
        c['mlbam'] = int(m) if m else None
    # Visibility only (C1 companion, 2026-08-01): a None mlbam is legitimate —
    # the engine and dpwin history now key such candidates by normalized name —
    # but it must never be SILENT, because silent Nones are how identity-less
    # candidates used to collapse onto one sentinel key unnoticed.
    unresolved = sorted(c['name'] for c in cands if c.get('mlbam') is None)
    if unresolved:
        print(f'  !! {len(unresolved)} candidate(s) UNRESOLVED to mlbam — '
              f'name-fallback identity in use: '
              f'{", ".join(unresolved[:8])}{" ..." if len(unresolved) > 8 else ""}')


# ─────────────────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────────────────

def _cand_team_games(c: dict) -> int | None:
    """Remaining TEAM GAMES behind a candidate's projection, or None.

    Audit T23 (2026-08-01): this used to be ``c['units']``, which for an RP is a
    fractional EXPECTED-APPEARANCE count (``project_rp`` returns
    ``round(expected_appearances, 1)``), not a game count. The engine's
    ``p_app = min(units / n_rem_games, 1.0)`` therefore pinned every candidate
    reliever to an appearance probability of exactly 1.0 — one deterministic
    appearance per simulated week against a projection of 1.7 — and any
    candidate with units < 1.0 truncated to n_rem_games 0 and scored a hard zero.

    The denominator ``project_rp`` actually divided by is already carried on the
    projection (``breakdown[0]['n_team_games']``), so read it back rather than
    re-deriving a schedule that could disagree with it. Returning None lets the
    engine fall back to its own ``round(units)``.
    """
    for b in (c.get('proj') or {}).get('breakdown') or []:
        n = b.get('n_team_games')
        if n:
            return int(n)
    return None


def _cand_for_engine(c: dict, effective: str | None = None) -> dict:
    return {'mlbam': c.get('mlbam'), 'name': c['name'], 'bucket': c['bucket'],
            'proj': c['proj'], 'starts': c.get('starts') or [],
            'n_rem_games': _cand_team_games(c), 'effective_date': effective}


def _hitter_games(state, cands) -> dict:
    """{mlbam_or_name: remaining games} for rostered hitters AND candidates.

    Feeds the lineup-capacity check so the optimizer cannot recommend an add
    whose games are physically unplayable (13 hitter slots x days_remaining).
    """
    g = {}
    for h in state['my_hitters']:
        g[h.get('mlbam') or h['name']] = h['n_games']
        g[h['name']] = h['n_games']
    for c in cands:
        if c['bucket'] == 'H':
            g[c.get('mlbam') or c['name']] = c['units']
            g[c['name']] = c['units']
    return g


def score_single_moves(state, D, roster, cands, base_p, *, hgames=None,
                       prior_adds=(), prior_drop_keys=(), cur_pwin=None,
                       exclude_drops=(), verbose=True, bench_scratch=(),
                       _dp=delta_pwin) -> list[dict]:
    """Every legal single swap + pure drop, scored by MARGINAL Delta-P(win).

    CUMULATIVE SCORING (fix 2026-07-30). ``delta_pwin`` always evaluates against
    the ORIGINAL state — it has no concept of the greedy loop's virtual roster.
    The pre-fix loop therefore mis-scored every step after the first: step 2's
    candidates were scored as if step 1 had never happened, and a "drop" of the
    player step 1 added silently NO-OPed inside ``_resolve_keys`` (an unrostered
    name matches no draw key), which is exactly how the 2026-07-30 10:00 run
    produced "ADD Jeffers / DROP Pederson +8.84pp" — a free add masquerading as
    a swap. Every scenario is now expressed the only way the engine can honestly
    score it: original roster + ALL prior adds − ALL prior drops + this move.
    ``dpwin`` on each row is the MARGINAL gain vs ``cur_pwin`` (the pwin after
    the prior steps), so ranking, the stop rule, and the running-P(win) display
    all speak the same language; ``dpwin_from_base`` keeps the vs-base number
    for the history log. Round 1 (no priors) is byte-identical to the old
    behavior: marginal == from-base.

    ``_dp`` is an injection seam for tests (a fake ``delta_pwin`` over a toy
    additive model); production always passes the real engine primitive.
    """
    if cur_pwin is None:
        cur_pwin = base_p
    prior_adds = list(prior_adds)
    prior_drop_keys = list(prior_drop_keys)
    exclude_drops = list(exclude_drops)
    rows, skipped = [], []
    # exclude_drops filters only WHO may be dropped (undo suppression) — the
    # legality substrate stays the FULL virtual roster, otherwise check_swap
    # would see a phantom short roster and block every later step
    droppables = [p for p in roster if not p.get('on_il')
                  and not any(RR.same_player(p, x) for x in exclude_drops)]
    _legal_kw = dict(cap_remaining=state['cap_remaining_mine'],
                     hitter_games=hgames,
                     days_remaining=state.get('days_remaining'),
                     games_per_day=state.get('games_per_day'))

    # pure adds are impossible at a full roster, so an add is always paired with
    # a drop; a pure drop is scored too (it is occasionally the right move)
    for d in droppables:
        probs = RR.check_swap(roster, drop=d)
        if not probs:
            r = _dp(state, D, add=prior_adds,
                    drop=prior_drop_keys + [d['mlbam'] or d['name']],
                    bench=list(bench_scratch), base_pwin=base_p)
            rows.append({'kind': 'drop', 'add': None, 'drop': d,
                         'dpwin': r['pwin'] - cur_pwin,
                         'dpwin_from_base': r['dpwin'], 'pwin': r['pwin'],
                         'mc_se': r['mc_se']})

    for c in cands:
        eng = _cand_for_engine(c)
        for d in droppables:
            probs = RR.check_swap(roster, add=c, drop=d, **_legal_kw)
            if probs:
                skipped.append((c['name'], d['name'], probs[0]))
                continue
            r = _dp(state, D, add=prior_adds + [eng],
                    drop=prior_drop_keys + [d['mlbam'] or d['name']],
                    bench=list(bench_scratch), base_pwin=base_p)
            rows.append({'kind': 'swap', 'add': c, 'drop': d, '_eng': eng,
                         'dpwin': r['pwin'] - cur_pwin,
                         'dpwin_from_base': r['dpwin'], 'pwin': r['pwin'],
                         'mc_se': r['mc_se']})

    rows.sort(key=lambda r: -r['dpwin'])
    if verbose:
        print(f'  scored {len(rows)} legal moves ({len(skipped)} blocked by roster rules)')
    return rows, skipped


def _regime_tiebreak(rows: list[dict], regime: str) -> list[dict]:
    """Order ties (within 2x mc_se of the leader) by the regime's own preference.

    dpwin remains the objective; this only resolves what dpwin cannot
    distinguish. Without it the leader among statistically-identical moves is
    just Monte-Carlo luck.
    """
    if not rows:
        return rows
    lead = rows[0]
    tol = 2.0 * max(lead.get('mc_se') or 0.0, 1e-9)
    tied = [r for r in rows if (lead['dpwin'] - r['dpwin']) <= tol]
    rest = [r for r in rows if r not in tied]
    if len(tied) > 1:
        for r in tied:
            c = r.get('add')
            st = (series_stats(emp_series(c.get('mlbam'), c['bucket']),
                              SP_BOOM if c['bucket'] != 'H' else H_BOOM,
                              SP_BUST if c['bucket'] != 'H' else H_BUST)
                  if c else {'boom_pct': None, 'bust_pct': None,
                             'rate_precise': False})
            r['_boom'] = st.get('boom_pct') or 0
            r['_bust'] = st.get('bust_pct') if st.get('bust_pct') is not None else 100
            r['_rate_precise'] = bool(st.get('rate_precise'))
            r['_rate_n'] = st.get('n') or 0
        # Rank only on rates precise enough to mean something. A thin window can
        # show an 8% bust rate off ONE bust in twelve starts (CI [1%, 35%]) and
        # outrank a genuinely steadier arm at 21% over 24 starts (CI [9%, 40%])
        # — the intervals overlap almost entirely, so the ordering was noise
        # dressed as a floor (2026-08-07, the Drohan/Cavalli tie-break). Sorting
        # is STABLE, so imprecise candidates keep their dpwin order rather than
        # being pushed to the back: an unmeasured floor is unknown, not bad.
        precise = [r for r in tied if r['_rate_precise']]
        if len(precise) > 1 and regime in ('TRAILING', 'LEADING'):
            key = ((lambda r: -r['_boom']) if regime == 'TRAILING'
                   else (lambda r: r['_bust']))
            precise.sort(key=key)
            # Slot the reordered precise rows back into the positions they
            # already occupied, leaving imprecise rows exactly where dpwin put
            # them.
            it = iter(precise)
            tied = [next(it) if r['_rate_precise'] else r for r in tied]
    return tied + rest


def optimize(state, D, base_p, regime, cands, *, max_moves=2, verbose=True,
             bench_scratch=(), _dp=delta_pwin):
    """Greedy best-swap over a virtual roster (cumulatively scored), then a pair
    check. ``_dp`` is the test seam threaded through to ``score_single_moves``.
    """
    roster = [dict(p) for p in state['my_roster']]
    chosen, all_rows, all_skipped = [], [], []
    remaining = [dict(c) for c in cands]
    hgames = _hitter_games(state, cands)
    prior_adds: list[dict] = []       # engine dicts of every add so far
    prior_added: list[dict] = []      # candidate dicts, for droppable exclusion
    prior_drop_keys: list = []
    cur_pwin = base_p

    for step in range(max_moves):
        # UNDO SUPPRESSION (fix 2026-07-30): a player added by an earlier step
        # must never be droppable by a later one. Dropping him is an UNDO — the
        # net plan equals a shorter plan, so it never belongs in a forward
        # sequence — and the engine cannot score it anyway (he is not in the
        # original state's draws, so his "drop" silently no-ops; that silent
        # no-op is what let the 2026-07-30 run recommend dropping its own add).
        rows, skipped = score_single_moves(
            state, D, roster, remaining, base_p, hgames=hgames,
            bench_scratch=bench_scratch,
            prior_adds=prior_adds, prior_drop_keys=prior_drop_keys,
            cur_pwin=cur_pwin, exclude_drops=prior_added,
            verbose=verbose, _dp=_dp)
        all_rows.append(rows)
        all_skipped.extend(skipped)
        if not rows:
            break
        rows = _regime_tiebreak(rows, regime)
        best = rows[0]
        if best['dpwin'] <= 0:
            if verbose:
                print(f'  step {step+1}: best available move is {best["dpwin"]*100:+.2f}pp '
                      f'— stopping (no positive marginal move)')
            break
        chosen.append(best)
        roster = RR.apply_swap(roster, add=best.get('add'), drop=best.get('drop'))
        cur_pwin = best['pwin']       # true endpoint after this step
        prior_drop_keys.append(best['drop']['mlbam'] or best['drop']['name'])
        if best.get('add'):
            prior_adds.append(best.get('_eng') or _cand_for_engine(best['add']))
            prior_added.append(best['add'])
            remaining = [c for c in remaining if c['name'] != best['add']['name']]
        if verbose:
            lbl = (f"ADD {best['add']['name']} / DROP {best['drop']['name']}"
                   if best.get('add') else f"DROP {best['drop']['name']}")
            print(f'  step {step+1}: {lbl}  {best["dpwin"]*100:+.2f}pp marginal '
                  f'(P(win) now ~{cur_pwin*100:.1f}%)')

    # Pair interaction check over the top of round 1. Two real cases: two SP
    # adds competing for the same remaining cap slots (the second is worth much
    # less than its solo score), and greedy myopia — a tie-break-influenced
    # step 1 that walks past the best joint endpoint. Gated on max_moves >= 2:
    # a pair IS two moves, so `--max-moves 1` must never surface one (found by
    # adversarial review 2026-07-30).
    pairs = []
    n_pairs_illegal = 0
    if max_moves >= 2 and all_rows and len(all_rows[0]) > 1:
        roster0 = [dict(p) for p in state['my_roster']]
        _pair_legal_kw = dict(cap_remaining=state['cap_remaining_mine'],
                              hitter_games=hgames,
                              days_remaining=state.get('days_remaining'),
                              games_per_day=state.get('games_per_day'))
        # best rows per DISTINCT add (top few drop-variants each): one strong
        # candidate's many drop-variants can flood a plain top-N row window,
        # leaving the sweep zero usable pairs (every combination same-add-
        # skipped) — and two adds whose BEST drop is the same player would
        # collide even then (both Jeffers and Pederson wanted Detmers on
        # 2026-07-30). Rows are sorted, so each add's list is best-first and a
        # collision falls through to its next-best distinct drop.
        by_add: dict[str, list] = {}
        for r in all_rows[0]:
            if not r.get('add'):
                continue
            lst = by_add.setdefault(r['add']['name'], [])
            if len(lst) < 3 and all(x['drop']['name'] != r['drop']['name']
                                    for x in lst):
                lst.append(r)
        top = [lst[0] for lst in list(by_add.values())[:10]]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a = top[i]
                b = next((rb for rb in by_add[top[j]['add']['name']]
                          if rb['drop']['name'] != a['drop']['name']), None)
                if b is None:
                    continue          # cannot drop the same player twice
                # JOINT LEGALITY (blocking fix, adversarial review 2026-07-30):
                # each leg was checked only as a SINGLE swap vs the original
                # roster, but the pair executes BOTH — two singly-legal legs
                # can jointly drop the last catcher, breach the 4-RP floor, or
                # oversubscribe the 13-slot lineup (and the phantom games of an
                # oversubscribed pair INFLATE its score, biasing adoption
                # toward exactly the unchecked scenario). The brief promises
                # "either order", so require BOTH orderings legal; only the
                # intermediate roster differs between them.
                _pair_legal = True
                for first, second in ((a, b), (b, a)):
                    mid = RR.apply_swap(roster0, add=first['add'],
                                        drop=first['drop'])
                    if RR.check_swap(mid, add=second['add'],
                                     drop=second['drop'], **_pair_legal_kw):
                        _pair_legal = False
                        break
                if not _pair_legal:
                    n_pairs_illegal += 1
                    continue
                r = _dp(
                    state, D,
                    add=[_cand_for_engine(a['add']), _cand_for_engine(b['add'])],
                    drop=[a['drop']['mlbam'] or a['drop']['name'],
                          b['drop']['mlbam'] or b['drop']['name']],
                    bench=list(bench_scratch), base_pwin=base_p)
                pairs.append({
                    'moves': [a, b], 'dpwin': r['dpwin'], 'pwin': r['pwin'],
                    'mc_se': r['mc_se'],
                    'sum_solo': a['dpwin'] + b['dpwin'],
                    'interaction': r['dpwin'] - (a['dpwin'] + b['dpwin'])})
        pairs.sort(key=lambda p: -p['dpwin'])
        if verbose and (pairs or n_pairs_illegal):
            best_s = (f'; best {pairs[0]["dpwin"]*100:+.2f}pp (solo sum '
                      f'{pairs[0]["sum_solo"]*100:+.2f}pp, interaction '
                      f'{pairs[0]["interaction"]*100:+.2f}pp)') if pairs else ''
            print(f'  pair check: {len(pairs)} jointly-legal combinations '
                  f'({n_pairs_illegal} blocked by joint roster rules){best_s}')
    return {'chosen': chosen, 'rounds': all_rows, 'skipped': all_skipped,
            'pairs': pairs}


def assemble_plan(res: dict, base_p: float) -> dict:
    """Choose the RECOMMENDED PLAN: the greedy sequence or the best pair.

    The greedy loop and the pair sweep are two searches over the same space.
    Greedy commits to its (tie-break-influenced) step-1 choice; the pair sweep
    evaluates top round-1 combinations jointly, so it can find a strictly better
    two-move endpoint (2026-07-30: greedy's boom-tie-break took Pederson first
    and walked into churn, while the pair Jeffers+Pederson at +16.98pp was
    printed and then thrown away). Adopt the pair when it beats the greedy
    sequence's TRUE total by more than the pair's own MC standard error —
    inside 1×mc_se the two are indistinguishable and the sequenced greedy plan
    (whose ordering already encodes the regime tie-break) is kept.

    Plan items are UNIFORM in both shapes: ``dpwin`` is each move's MARGINAL
    gain given the moves before it, so the marginals sum to ``total_dpwin``
    and ``pwin_after`` is the honest running P(win) — never base + a sum of
    base-relative numbers.
    """
    chosen, pairs = res.get('chosen') or [], res.get('pairs') or []
    greedy_total = (chosen[-1]['pwin'] - base_p) if chosen else 0.0

    def _greedy_items():
        return [{'add': m.get('add'), 'drop': m['drop'], 'dpwin': m['dpwin'],
                 'mc_se': m['mc_se'], 'pwin_after': m['pwin'],
                 'dpwin_from_base': m.get('dpwin_from_base', m['dpwin'])}
                for m in chosen]

    if pairs:
        best = pairs[0]
        margin = best['dpwin'] - greedy_total
        if margin > (best.get('mc_se') or 0.0):
            a, b = sorted(best['moves'], key=lambda m: -m['dpwin'])
            items = [
                {'add': a.get('add'), 'drop': a['drop'], 'dpwin': a['dpwin'],
                 'mc_se': a['mc_se'], 'pwin_after': a['pwin'],
                 'dpwin_from_base': a['dpwin']},
                # move 2's marginal is the pair endpoint minus move 1 alone —
                # the two marginals sum to the pair total by construction.
                # dpwin_from_base is the CUMULATIVE endpoint vs base (same
                # semantics as a greedy item's), not b's solo score.
                {'add': b.get('add'), 'drop': b['drop'],
                 'dpwin': best['dpwin'] - a['dpwin'],
                 'mc_se': best['mc_se'], 'pwin_after': best['pwin'],
                 'dpwin_from_base': best['dpwin']},
            ]
            return {'source': 'pair_check', 'moves': items,
                    'total_dpwin': best['dpwin'], 'pwin_final': best['pwin'],
                    'greedy_total_dpwin': greedy_total,
                    'adoption_margin': margin, 'pair': best}
    if not chosen:
        return {'source': 'hold', 'moves': [], 'total_dpwin': 0.0,
                'pwin_final': base_p, 'greedy_total_dpwin': 0.0}
    return {'source': 'greedy', 'moves': _greedy_items(),
            'total_dpwin': greedy_total,
            'pwin_final': chosen[-1]['pwin'],
            'greedy_total_dpwin': greedy_total}


def build_payload(*, plan, res, base_p, regime, period, sims, seed,
                  cap_remaining, wv, generated_at=None, week_start=None,
                  week_end=None, banked=None, sp_cap=None,
                  banked_provisional=None) -> dict:
    """The weekly_optimizer.json payload — extracted from main() so its shape
    (which the Monday brief consumes) is testable without ESPN.

    The freshness block (generated_at/week window/banked/sp_cap) exists because
    consumers used to have only the file mtime to judge staleness: the
    2026-08-29 daily briefing found a 2am payload whose cap_remaining no longer
    matched the live banked count and had to infer that from timestamps. Now a
    consumer checks period + banked-vs-live directly and re-runs when they
    disagree."""
    return {
        'base_pwin': round(base_p, 6), 'regime': regime, 'period': period,
        'sims': sims, 'seed': seed,
        'generated_at': generated_at,
        'week_start': str(week_start) if week_start else None,
        'week_end': str(week_end) if week_end else None,
        'banked': banked, 'sp_cap': sp_cap,
        'banked_provisional': banked_provisional,
        'cap_remaining': cap_remaining,
        # plan[] semantics (fix 2026-07-30): `dpwin` is each move's MARGINAL
        # gain given the moves before it — the marginals sum to
        # `plan_total_dpwin`, and `pwin_after` is the honest running P(win).
        'plan_source': plan['source'],
        'plan_total_dpwin': plan['total_dpwin'],
        'plan_pwin_final': plan['pwin_final'],
        'plan': [{'add': (m['add'] or {}).get('name') if m.get('add') else None,
                  'add_bucket': (m['add'] or {}).get('bucket') if m.get('add') else None,
                  'drop': m['drop']['name'], 'drop_bucket': m['drop']['bucket'],
                  'dpwin': m['dpwin'], 'mc_se': m['mc_se'],
                  'pwin_after': m['pwin_after'],
                  'dpwin_from_base': m.get('dpwin_from_base'),
                  'dtitle_equity_pp': m.get('dtitle_equity_pp')}
                 for m in plan['moves']],
        'title_equity': {k: wv.get(k) for k in
                         ('dtitle_pp', 'status', 'source_period', 'payload_period',
                          'periods_stale', 'note', 'plus2_pp')},
        'top_single_moves': [
            {'add': r['add']['name'] if r.get('add') else None,
             'drop': r['drop']['name'], 'dpwin': r['dpwin'], 'mc_se': r['mc_se']}
            for r in (res['rounds'][0][:15] if res['rounds'] else [])],
        # the best pair is persisted whether or not it was adopted — the
        # console used to print it and throw it away (found 2026-07-30)
        'pair_check': ({
            'n_combos': len(res['pairs']),
            'adopted': plan['source'] == 'pair_check',
            'best': {
                'moves': [{'add': m['add']['name'], 'add_bucket': m['add']['bucket'],
                           'drop': m['drop']['name'],
                           'drop_bucket': m['drop']['bucket'],
                           'dpwin_solo': m['dpwin'], 'mc_se': m['mc_se']}
                          for m in res['pairs'][0]['moves']],
                'dpwin': res['pairs'][0]['dpwin'],
                'pwin': res['pairs'][0]['pwin'],
                'mc_se': res['pairs'][0]['mc_se'],
                'sum_solo': res['pairs'][0]['sum_solo'],
                'interaction': res['pairs'][0]['interaction']},
        } if res.get('pairs') else None),
    }



# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    # Line-buffer stdout: agents/cron run this piped, where full buffering sat
    # on every progress line for 25+ minutes during the 2026-08-29 stall and
    # made a slow network loop indistinguishable from a hang.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sims', type=int, default=10000)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--max-moves', type=int, default=2,
                    help='max sequential swaps to propose (default 2)')
    ap.add_argument('--pool', type=int, default=8,
                    help='top-N FA candidates per bucket (default 8)')
    ap.add_argument('--no-log', action='store_true',
                    help='skip the dpwin_history write')
    ap.add_argument('--realized-pool', type=int, default=4, metavar='N',
                    help='ALSO include the top-N FAs per bucket by REALIZED '
                         'FP/event over the last 30d (default 4). The projected '
                         'leg cannot surface a player the model underrates.')
    ap.add_argument('--include', default='', metavar='NAMES',
                    help='comma-separated names to FORCE into the candidate '
                         'pool, bypassing both ranking legs and the fp<=0 '
                         'filter (e.g. "Griffin Jax,Trent Grisham")')
    ap.add_argument('--banked', type=int, default=None, metavar='N',
                    help='Pin the true banked SP-start count for this period. '
                         'ESPN only credits a start once the game finalizes, and '
                         'a start made TODAY by a pitcher you have since DROPPED '
                         'lands in neither the ESPN count nor the live roster — '
                         'so cap room can read high while games are in flight. '
                         'Use this when the run says banked is PROVISIONAL.')
    ap.add_argument('--scratch', default='', metavar='NAME:YYYY-MM-DD',
                    help='comma-separated starts you KNOW will not happen. The '
                         'engine models an unconfirmed start at ~0.80; a scratch '
                         'it does not know about leaves the SP cap wrong (a '
                         '7.7pp swing on 2026-08-01). Malformed input errors out '
                         'rather than being ignored.')
    args = ap.parse_args()

    try:
        scratch = parse_scratch(args.scratch)
    except ValueError as exc:
        print(f'ERROR: {exc}')
        return 2
    bench_scratch = [('SP', n, d) for n, d in scratch]
    include = [x.strip() for x in (args.include or '').split(',') if x.strip()]

    print('=== /weekly-optimizer — maximize P(win), not E[FP] ===')
    state = build_state(verbose=True, banked_override=args.banked)
    D = precompute_draws(state, args.sims, args.seed)
    if scratch:
        # Condition EVERYTHING on the scratch: the baseline, the regime call and
        # every scenario. Scoring moves against an unscratched baseline would
        # compare them to a world that is not going to happen.
        bs = {(n, d) for n, d in scratch}
        my, opp = assemble(state, D, bench_starts=bs)
        print('\n  SCRATCHED (excluded from the cap + the baseline): '
              + '; '.join(f'{n} {d}' for n, d in scratch))
    else:
        my, opp = assemble(state, D)
    base_p = pwin(my, opp)
    regime = classify_regime(base_p)

    print(f'\n--- BASELINE ---')
    print(f'  P(win) = {base_p*100:.1f}%   (+/- {mc_se(base_p, args.sims)*100:.2f}pp MC)')
    print(f'  REGIME: {regime} — {REGIME_BLURB[regime]}')
    _prov = ' (PROVISIONAL — see NOTE above)' if state.get('banked_provisional') else ''
    print(f'  cap remaining: {state["cap_remaining_mine"]} SP starts{_prov}')
    rc = {b: sum(1 for p in state['my_roster']
                 if p['bucket'] == b and not p['on_il']) for b in ('H', 'SP', 'RP')}
    print(f'  roster (active): {rc["H"]}H / {rc["SP"]}SP / {rc["RP"]}RP '
          f'(RP floor {RR.RP_FLOOR})')
    # C6 companion: check_swap's floors are crossing-relative, so a deficit
    # the roster ALREADY carries is reported here ONCE, not blamed on every
    # candidate move the search scores.
    for w in RR.preexisting_shortfalls(state['my_roster']):
        print(f'  ⚠ {w}')

    print('\n--- CANDIDATES ---')
    cands = build_candidates(state, top_n=args.pool,
                             realized_n=args.realized_pool,
                             include=include)
    resolve_candidate_mlbams(state, cands)

    print('\n--- SEARCH ---')
    res = optimize(state, D, base_p, regime, cands,
                   max_moves=args.max_moves, bench_scratch=bench_scratch)

    plan = assemble_plan(res, base_p)

    # Season bridge (C4): weight the period-level dpwin by the value-of-a-win
    # curve. dpwin stays the sort key — this is a displayed conversion (Rule 13),
    # and the weight is a per-period constant so it cannot reorder anyway.
    # Annotate the FINAL plan's moves (marginal dpwins, which sum to the plan
    # total, so the per-move equities sum to the plan's equity too).
    wv = TE.annotate(plan['moves'], state['period'])
    if res['rounds']:
        TE.annotate(res['rounds'][0], state['period'])
    print('\n--- SEASON CONTEXT ---')
    print('  ' + TE.banner(wv).replace(chr(10), chr(10) + '  '))
    if wv.get('dtitle_pp') is not None:
        print(f"  => every +1.00pp of THIS period's P(win) converts to "
              f"{wv['dtitle_pp']/100:.4f}pp of title probability")

    print('\n--- RECOMMENDED PLAN ---')
    if plan['source'] == 'hold':
        print('  HOLD — no legal move improves P(win). The regime guidance above '
              'still applies to daily lineup calls.')
    elif plan['source'] == 'pair_check':
        print(f"  (adopted from the PAIR CHECK: {plan['total_dpwin']*100:+.2f}pp "
              f"jointly vs the greedy sequence's "
              f"{plan['greedy_total_dpwin']*100:+.2f}pp — margin "
              f"{plan['adoption_margin']*100:+.2f}pp exceeds the pair's MC se)")
    for i, m in enumerate(plan['moves'], 1):
        lbl = (f"ADD {m['add']['name']} ({m['add']['bucket']}, {m['add']['team']})"
               f"  /  DROP {m['drop']['name']} ({m['drop']['bucket']})"
               if m.get('add') else f"DROP {m['drop']['name']} ({m['drop']['bucket']})")
        print(f'  {i}. {lbl}')
        te = m.get('dtitle_equity_pp')
        te_s = f'   title equity {te:+.4f}pp' if te is not None else ''
        print(f'     dP(win) {m["dpwin"]*100:+.2f}pp marginal  '
              f'(+/- {m["mc_se"]*100:.2f}pp MC)'
              f'   running P(win) ~ {m["pwin_after"]*100:.1f}%{te_s}')
    if plan['moves']:
        print(f'  = plan total {plan["total_dpwin"]*100:+.2f}pp '
              f'-> P(win) ~ {plan["pwin_final"]*100:.1f}%')

    if res['rounds']:
        print('\n--- TOP 8 SINGLE MOVES (round 1) ---')
        for r in res['rounds'][0][:8]:
            lbl = (f"ADD {r['add']['name']:<20} / DROP {r['drop']['name']:<20}"
                   if r.get('add') else f"DROP {r['drop']['name']:<43}")
            flag = '' if abs(r['dpwin']) > 2 * (r['mc_se'] or 0) else '  (within MC noise)'
            print(f"  {r['dpwin']*100:+6.2f}pp  {lbl}{flag}")

    if res['skipped']:
        print('\n--- BLOCKED BY ROSTER RULES (top reasons) ---')
        seen = set()
        for a, d, why in res['skipped']:
            if why in seen:
                continue
            seen.add(why)
            print(f'  {a} / {d}: {why}')
            if len(seen) >= 5:
                break

    payload = build_payload(plan=plan, res=res, base_p=base_p, regime=regime,
                            period=state['period'], sims=args.sims,
                            seed=args.seed,
                            cap_remaining=state['cap_remaining_mine'], wv=wv,
                            generated_at=datetime.now().isoformat(timespec='seconds'),
                            week_start=state['week_start'],
                            week_end=state['week_end'],
                            banked=state['banked_mine'],
                            sp_cap=state['sp_cap'],
                            banked_provisional=state.get('banked_provisional'))

    if not args.no_log and res['rounds']:
        try:
            moves = []
            for r in res['rounds'][0]:
                mv = {'move_type': 'swap' if r.get('add') else 'drop',
                      'dpwin': r['dpwin'], 'pwin': r['pwin'], 'mc_se': r['mc_se'],
                      'candidate_source': 'optimizer:round1',
                      'dtitle_pp_per_win': r.get('dtitle_pp_per_win'),
                      'dtitle_equity_pp': r.get('dtitle_equity_pp'),
                      'drop': {'name': r['drop']['name'],
                               'mlbam': r['drop'].get('mlbam'),
                               'bucket': r['drop']['bucket']}}
                if r.get('add'):
                    mv['add'] = {'name': r['add']['name'],
                                 'mlbam': r['add'].get('mlbam'),
                                 'bucket': r['add']['bucket']}
                moves.append(mv)
            payload['dpwin_run_id'] = dpwin_history.log_run(
                state=state, regime=regime, base_pwin=base_p,
                sims=args.sims, seed=args.seed, moves=moves)
        except Exception as exc:
            print(f'  ⚠ dpwin history not written ({type(exc).__name__}: {exc})')

    path = OUT / 'weekly_optimizer.json'
    path.write_text(json.dumps(payload, indent=2, default=float), encoding='utf-8')
    print(f'\nwrote {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
