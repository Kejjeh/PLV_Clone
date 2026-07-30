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
  apply    take the best positive-dpwin move onto a VIRTUAL roster
  repeat   up to --max-moves times, re-scoring against the updated roster
  pair     then exhaustively check pairs among the top-10 round-1 moves

The pair check exists for one real interaction: two SP adds competing for the
same remaining cap slots, where the second is worth much less than its solo
score suggests. Outside the cap the objective is close to separable, which is
why greedy is adequate and a full K=2 sweep (~45k evals) buys almost nothing.

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
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from scripts.xfp.lib.leverage_engine import (  # noqa: E402
    build_state, precompute_draws, assemble, pwin, mc_se, delta_pwin,
    ensure_candidate_draws, classify_regime, REGIME_BLURB, emp_series,
    series_stats, _draw_key, OUT,
)
from scripts.xfp.lib import roster_rules as RR  # noqa: E402
from scripts.xfp.lib import dpwin_history  # noqa: E402
from scripts.xfp.lib.boom_bust import SP_BOOM, SP_BUST, H_BOOM, H_BUST  # noqa: E402
from build_matchup_dashboard import (  # noqa: E402
    project_player, ESPN_TO_MLB_TEAM, IL_INJURY_STATES, _norm,
)

HIT_POS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH'}


# ─────────────────────────────────────────────────────────────────────────────
# Candidate pool
# ─────────────────────────────────────────────────────────────────────────────

def build_candidates(state, top_n: int = 8, verbose: bool = True) -> list[dict]:
    """Top-N FA per bucket, projected through project_player.

    Uses the ONE FA pull already on the state (gotcha #6: never per-position
    size caps — a single free_agents(size=2000) then filter). Every candidate is
    projected through the same path as a rostered player so its units match;
    that matters most for RP, whose rprs2 sigma is a rest-of-season TOTAL derived
    from an IQR rather than a per-appearance number.
    """
    league = state['mu']['league_obj']
    try:
        fas = league.free_agents(size=2000)
    except Exception as exc:
        print(f'  WARN FA pool fetch failed ({exc}) — add candidates unavailable')
        return []

    maps = state['proj_maps']
    cands: list[dict] = []
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
        else:
            continue
        try:
            proj = project_player(p, state['schedules_by_team'],
                                  state['sp_starts_by_pitcher'],
                                  maps['rh3'], maps['rp3'], maps['rp3_by_mlbam'],
                                  maps['rprs2'], maps['ts'],
                                  state['today'], state['week_end'])
        except Exception:
            continue
        units = float(proj.get('units') or 0)
        fp = float(proj.get('fp') or 0)
        if units <= 0 or fp <= 0:
            continue          # no remaining events in the window -> cannot help
        cands.append({
            'name': p.name, 'bucket': bucket, 'espn_pos': pos, 'eligible': elig,
            'team': getattr(p, 'proTeam', ''), 'proj': proj,
            'fp': fp, 'units': units, 'per_unit': fp / units,
            'pct_owned': float(getattr(p, 'percent_owned', 0) or 0),
            'injury_status': inj,
            'starts': [b for b in (proj.get('breakdown') or [])
                       if b.get('type') == 'start'],
        })

    # rank within bucket by projected FP over the remaining window — the honest
    # pre-filter, since dpwin scoring is what actually orders them
    out = []
    for b in ('H', 'SP', 'RP'):
        sub = sorted([c for c in cands if c['bucket'] == b],
                     key=lambda c: -c['fp'])[:top_n]
        out.extend(sub)
    if verbose:
        n = {b: sum(1 for c in out if c['bucket'] == b) for b in ('H', 'SP', 'RP')}
        print(f'  candidate pool: {len(out)} FAs (H {n["H"]} / SP {n["SP"]} / RP {n["RP"]})'
              f' from {len(cands)} projectable')
    return out


def resolve_candidate_mlbams(state, cands: list[dict]) -> None:
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
        c['mlbam'] = int(m) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────────────────

def _cand_for_engine(c: dict, effective: str | None = None) -> dict:
    return {'mlbam': c.get('mlbam'), 'name': c['name'], 'bucket': c['bucket'],
            'proj': c['proj'], 'starts': c.get('starts') or [],
            'n_rem_games': c.get('units'), 'effective_date': effective}


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
                       verbose=True) -> list[dict]:
    """Every legal single swap + pure drop, scored by Delta-P(win)."""
    rows, skipped = [], []
    droppables = [p for p in roster if not p.get('on_il')]
    _legal_kw = dict(cap_remaining=state['cap_remaining_mine'],
                     hitter_games=hgames,
                     days_remaining=state.get('days_remaining'))

    # pure adds are impossible at a full roster, so an add is always paired with
    # a drop; a pure drop is scored too (it is occasionally the right move)
    for d in droppables:
        probs = RR.check_swap(roster, drop=d)
        if not probs:
            r = delta_pwin(state, D, drop=[d['mlbam'] or d['name']],
                           base_pwin=base_p)
            rows.append({'kind': 'drop', 'add': None, 'drop': d,
                         'dpwin': r['dpwin'], 'pwin': r['pwin'],
                         'mc_se': r['mc_se']})

    for c in cands:
        eng = _cand_for_engine(c)
        for d in droppables:
            probs = RR.check_swap(roster, add=c, drop=d, **_legal_kw)
            if probs:
                skipped.append((c['name'], d['name'], probs[0]))
                continue
            r = delta_pwin(state, D, add=[eng],
                           drop=[d['mlbam'] or d['name']], base_pwin=base_p)
            rows.append({'kind': 'swap', 'add': c, 'drop': d,
                         'dpwin': r['dpwin'], 'pwin': r['pwin'],
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
                  if c else {'boom_pct': None, 'bust_pct': None})
            r['_boom'] = st.get('boom_pct') or 0
            r['_bust'] = st.get('bust_pct') if st.get('bust_pct') is not None else 100
        if regime == 'TRAILING':
            tied.sort(key=lambda r: (-r['dpwin'] // 1, -r['_boom']))
            tied.sort(key=lambda r: -r['_boom'])
        elif regime == 'LEADING':
            tied.sort(key=lambda r: r['_bust'])
    return tied + rest


def optimize(state, D, base_p, regime, cands, *, max_moves=2, verbose=True):
    """Greedy best-swap, re-scored against a virtual roster, then a pair check."""
    roster = [dict(p) for p in state['my_roster']]
    chosen, all_rows, all_skipped = [], [], []
    remaining = [dict(c) for c in cands]
    hgames = _hitter_games(state, cands)

    for step in range(max_moves):
        rows, skipped = score_single_moves(state, D, roster, remaining, base_p,
                                          hgames=hgames, verbose=verbose)
        all_rows.append(rows)
        all_skipped.extend(skipped)
        if not rows:
            break
        rows = _regime_tiebreak(rows, regime)
        best = rows[0]
        if best['dpwin'] <= 0:
            if verbose:
                print(f'  step {step+1}: best available move is {best["dpwin"]*100:+.2f}pp '
                      f'— stopping (no positive move)')
            break
        chosen.append(best)
        roster = RR.apply_swap(roster, add=best.get('add'), drop=best.get('drop'))
        if best.get('add'):
            remaining = [c for c in remaining if c['name'] != best['add']['name']]
        if verbose:
            lbl = (f"ADD {best['add']['name']} / DROP {best['drop']['name']}"
                   if best.get('add') else f"DROP {best['drop']['name']}")
            print(f'  step {step+1}: {lbl}  {best["dpwin"]*100:+.2f}pp')

    # pair interaction check over the top of round 1 — the case that matters is
    # two SP adds competing for the same remaining cap slots
    pairs = []
    if all_rows and len(all_rows[0]) > 1:
        top = [r for r in all_rows[0][:10] if r.get('add')]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = top[i], top[j]
                if a['add']['name'] == b['add']['name']:
                    continue
                if a['drop']['name'] == b['drop']['name']:
                    continue          # cannot drop the same player twice
                r = delta_pwin(
                    state, D,
                    add=[_cand_for_engine(a['add']), _cand_for_engine(b['add'])],
                    drop=[a['drop']['mlbam'] or a['drop']['name'],
                          b['drop']['mlbam'] or b['drop']['name']],
                    base_pwin=base_p)
                pairs.append({
                    'moves': [a, b], 'dpwin': r['dpwin'], 'mc_se': r['mc_se'],
                    'sum_solo': a['dpwin'] + b['dpwin'],
                    'interaction': r['dpwin'] - (a['dpwin'] + b['dpwin'])})
        pairs.sort(key=lambda p: -p['dpwin'])
        if verbose and pairs:
            print(f'  pair check: {len(pairs)} combinations; best '
                  f'{pairs[0]["dpwin"]*100:+.2f}pp (solo sum '
                  f'{pairs[0]["sum_solo"]*100:+.2f}pp, interaction '
                  f'{pairs[0]["interaction"]*100:+.2f}pp)')
    return {'chosen': chosen, 'rounds': all_rows, 'skipped': all_skipped,
            'pairs': pairs}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sims', type=int, default=10000)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--max-moves', type=int, default=2,
                    help='max sequential swaps to propose (default 2)')
    ap.add_argument('--pool', type=int, default=8,
                    help='top-N FA candidates per bucket (default 8)')
    ap.add_argument('--no-log', action='store_true',
                    help='skip the dpwin_history write')
    args = ap.parse_args()

    print('=== /weekly-optimizer — maximize P(win), not E[FP] ===')
    state = build_state(verbose=True)
    D = precompute_draws(state, args.sims, args.seed)
    my, opp = assemble(state, D)
    base_p = pwin(my, opp)
    regime = classify_regime(base_p)

    print(f'\n--- BASELINE ---')
    print(f'  P(win) = {base_p*100:.1f}%   (+/- {mc_se(base_p, args.sims)*100:.2f}pp MC)')
    print(f'  REGIME: {regime} — {REGIME_BLURB[regime]}')
    print(f'  cap remaining: {state["cap_remaining_mine"]} SP starts')
    rc = {b: sum(1 for p in state['my_roster']
                 if p['bucket'] == b and not p['on_il']) for b in ('H', 'SP', 'RP')}
    print(f'  roster (active): {rc["H"]}H / {rc["SP"]}SP / {rc["RP"]}RP '
          f'(RP floor {RR.RP_FLOOR})')

    print('\n--- CANDIDATES ---')
    cands = build_candidates(state, top_n=args.pool)
    resolve_candidate_mlbams(state, cands)

    print('\n--- SEARCH ---')
    res = optimize(state, D, base_p, regime, cands,
                   max_moves=args.max_moves)

    print('\n--- RECOMMENDED PLAN ---')
    if not res['chosen']:
        print('  HOLD — no legal move improves P(win). The regime guidance above '
              'still applies to daily lineup calls.')
    cum = base_p
    for i, m in enumerate(res['chosen'], 1):
        lbl = (f"ADD {m['add']['name']} ({m['add']['bucket']}, {m['add']['team']})"
               f"  /  DROP {m['drop']['name']} ({m['drop']['bucket']})"
               if m.get('add') else f"DROP {m['drop']['name']} ({m['drop']['bucket']})")
        cum += m['dpwin']
        print(f'  {i}. {lbl}')
        print(f'     dP(win) {m["dpwin"]*100:+.2f}pp  (+/- {m["mc_se"]*100:.2f}pp MC)'
              f'   running P(win) ~ {cum*100:.1f}%')

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

    payload = {
        'base_pwin': round(base_p, 6), 'regime': regime, 'period': state['period'],
        'sims': args.sims, 'seed': args.seed,
        'cap_remaining': state['cap_remaining_mine'],
        'plan': [{'add': (m['add'] or {}).get('name') if m.get('add') else None,
                  'add_bucket': (m['add'] or {}).get('bucket') if m.get('add') else None,
                  'drop': m['drop']['name'], 'drop_bucket': m['drop']['bucket'],
                  'dpwin': m['dpwin'], 'mc_se': m['mc_se']} for m in res['chosen']],
        'top_single_moves': [
            {'add': r['add']['name'] if r.get('add') else None,
             'drop': r['drop']['name'], 'dpwin': r['dpwin'], 'mc_se': r['mc_se']}
            for r in (res['rounds'][0][:15] if res['rounds'] else [])],
    }

    if not args.no_log and res['rounds']:
        try:
            moves = []
            for r in res['rounds'][0]:
                mv = {'move_type': 'swap' if r.get('add') else 'drop',
                      'dpwin': r['dpwin'], 'pwin': r['pwin'], 'mc_se': r['mc_se'],
                      'candidate_source': 'optimizer:round1',
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
