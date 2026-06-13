"""trade_target_scan.py — surface trade opportunities across the BrownU
league by combining Phase 2 + 2.5 live_marginal with opponent_profiler
behavioral fingerprints.

Per opponent we produce:
  - SELL-BAIT: players on their roster with live_marginal < -10
    (DOWNGRADE / ACTIVE_LOSS). They are leaking value; may be willing
    to move.
  - TRADE-ASK TARGETS: opponent players with live_marginal > +30
    (OWN_THE_ROLE / OWN_THE_SLOT) that fit a positional gap on the
    user's roster.
  - PITCH TEMPLATE: behavioral-profile-matched pitch language.

API:
  python -X utf8 scripts/xfp/trade_target_scan.py
  python -X utf8 scripts/xfp/trade_target_scan.py --opponent "Frendy's Fantastic Team"
  python -X utf8 scripts/xfp/trade_target_scan.py --my-position SS

Read-only consumer of:
  - data/research/triangulate_universe/all_team_rosters.json
  - data/research/fa_snapshots/fa_pool_*_latest.parquet  (via blend_score)
  - data/outputs/xfp_rh3/rp3/rprs2_projections.csv      (via blend_score)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd

# Path setup so `from lib.blend_score import ...` works regardless of CWD.
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR))

from lib.blend_score import compute_blended_xfp  # noqa: E402

# rp-decline tier join (Tier-B CONTEXT flag only — NEVER moves rprs2/live_marginal;
# CLAUDE.md #13). A ROLE-RISK closer is a SELL-HIGH-NOW candidate: trade him while
# he still has saves, before velo decline -> role loss craters his value. Honestly
# weaker/noisier than /sp-decline (velo +0.112 vs SP whiff/K +0.235; role loss
# ~1/3 manager-driven). Degrades to {} if the rolling cache is unavailable.
try:
    from rp_decline_model import tier_map as _rp_decline_tier_map  # noqa: E402
except Exception:  # pragma: no cover - graceful degrade
    _rp_decline_tier_map = lambda: {}  # noqa: E731

ROOT = Path(r'c:/Users/Joshua/plv_clone')
TRI = ROOT / 'data' / 'research' / 'triangulate_universe'
FA_SNAP_DIR = ROOT / 'data' / 'research' / 'fa_snapshots'
MY_TEAM = 'New York Ligers'

# Behavioral pitch templates — keyed by opponent_profiler style label.
PITCH_TEMPLATES = {
    'OUTCOME_CHASER': (
        'Pitch PL top-50 names with high recent box-score. They chase '
        'outcome — package a flashy short-window hitter / SP for one of '
        'their high-live_marginal assets.'
    ),
    'IMPULSIVE_CHURNER': (
        'Same-tier swap framed as upgrade. They re-drop within 14d so a '
        'modest "fresh face" pitch lands. Lead with the new toy, not the cost.'
    ),
    'PL_PROCESS_FOLLOWER': (
        'HARD TARGET. Process-aware — they will not bite on dump trades. '
        'Only pitch clear wins for THEM (e.g. a TRENDING_UP archetype they '
        'lack at a position they need).'
    ),
    'DISCIPLINED_MINIMALIST': (
        'HARD TARGET. Low volume + vindicated drops = they cut wisely. '
        'Only move on clear wins for them; expect a counter, not a yes.'
    ),
    'BALANCED_SHARPSHOOTER': (
        'Standard offer. No strong tendency to exploit — lead with the '
        'positional fit + live_marginal math.'
    ),
    'ASLEEP_AT_THE_WHEEL': (
        'Unlikely to respond. Worth a one-line lowball offer in case '
        'they wake up; do not invest negotiation effort.'
    ),
}


def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower().strip()


# ---------- Data loaders ------------------------------------------------

def load_rosters() -> dict[str, list[dict]]:
    return json.load(open(TRI / 'all_team_rosters.json'))


def fa_snapshot_age_warning() -> str | None:
    """Return a top-of-report warning string if any snapshot is >36h old."""
    warns = []
    for f in ('fa_pool_H_latest.parquet', 'fa_pool_SP_latest.parquet',
              'fa_pool_RP_latest.parquet'):
        p = FA_SNAP_DIR / f
        if not p.exists():
            warns.append(f'MISSING: {f}')
            continue
        age_h = (time.time() - p.stat().st_mtime) / 3600.0
        if age_h > 36.0:
            warns.append(f'{f} is {age_h:.1f}h old (>36h)')
    if warns:
        return 'WARNING: FA snapshots stale — live_marginal may be unreliable.\n  ' + '\n  '.join(warns)
    return None


# ---------- Player-type / position helpers ------------------------------

def player_type_for(p: dict) -> str | None:
    """Return 'SP', 'RP', or 'H' (or None if not relevant)."""
    pos = p.get('position') or ''
    eligible = p.get('eligible') or []
    if pos == 'SP':
        return 'SP'
    if pos == 'RP':
        return 'RP'
    # Hitter — has a non-pitcher position.
    if pos and pos not in ('P', 'SP', 'RP'):
        return 'H'
    # Fallback by eligibility.
    if 'SP' in eligible:
        return 'SP'
    if 'RP' in eligible:
        return 'RP'
    return 'H' if eligible else None


def resolve_mlbam(name: str, team_abbr: str | None, player_type: str) -> int | None:
    """Best-effort resolution using utils.name_match. Falls back to a
    direct CSV lookup if needed."""
    try:
        from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
        if player_type == 'H':
            return resolve_batter_id(name, team=team_abbr)
        role = 'RP' if player_type == 'RP' else 'SP'
        return resolve_pitcher_id(name, team=team_abbr, role=role)
    except Exception:
        return None


# Cache to avoid recomputing blend per player across opponents.
_BLEND_CACHE: dict[tuple[str, int], dict] = {}


def get_blend(name: str, ptype: str, mlbam_id: int) -> dict | None:
    if not mlbam_id:
        return None
    key = (ptype, int(mlbam_id))
    if key not in _BLEND_CACHE:
        try:
            _BLEND_CACHE[key] = compute_blended_xfp(name, ptype, int(mlbam_id))
        except Exception as e:
            _BLEND_CACHE[key] = {'live_marginal': None, 'note_err': str(e)}
    return _BLEND_CACHE[key]


# ---------- Behavioral profile lookup -----------------------------------

def get_team_profiles() -> dict[str, dict]:
    """Run opponent_profiler logic in-proc to get per-team style labels."""
    try:
        from opponent_profiler import load_data, profile_team
        tx, tri, rosters, where = load_data()
        out = {}
        for team in rosters.keys():
            try:
                out[team] = profile_team(team, tx, tri, where)
            except Exception as e:
                out[team] = {'team': team, 'style_label': 'UNKNOWN', 'error': str(e)}
        return out
    except Exception as e:
        # Profiler unavailable — degrade gracefully.
        return {}


# ---------- My-roster positional gap detection --------------------------

def my_position_gap_map(rosters: dict, my_position_filter: str | None) -> dict[str, float]:
    """For each position on MY roster, compute the best live_marginal I
    currently field. Used to decide if an opponent star "fits a gap"
    (their live_marginal > mine at the same position).

    Returns dict[position -> my_best_live_marginal]. Missing positions
    map to -inf (any opponent star fits).
    """
    if MY_TEAM not in rosters:
        return {}
    out: dict[str, float] = {}
    for p in rosters[MY_TEAM]:
        ptype = player_type_for(p)
        if ptype is None:
            continue
        pos = p.get('position') or ''
        mlbam = resolve_mlbam(p['name'], None, ptype)
        if not mlbam:
            continue
        b = get_blend(p['name'], ptype, mlbam)
        if not b:
            continue
        lm = b.get('live_marginal')
        if lm is None:
            continue
        if my_position_filter and pos != my_position_filter:
            continue
        prev = out.get(pos, float('-inf'))
        if lm > prev:
            out[pos] = float(lm)
    return out


# ---------- Per-opponent block ------------------------------------------

def opponent_block(opp_name: str, opp_roster: list[dict], profile: dict,
                   my_gap: dict[str, float],
                   rp_decline: dict[str, dict] | None = None) -> str:
    style = (profile or {}).get('style_label', 'UNKNOWN')
    rp_decline = rp_decline or {}
    sell_bait: list[dict] = []
    trade_ask: list[dict] = []
    rp_sellhigh: list[dict] = []   # ROLE-RISK closers on this roster -> sell-high NOW

    for p in opp_roster:
        ptype = player_type_for(p)
        if ptype is None:
            continue
        name = p['name']
        pos = p.get('position') or ''
        mlbam = resolve_mlbam(name, None, ptype)
        if not mlbam:
            continue
        b = get_blend(name, ptype, mlbam)
        if not b:
            continue
        lm = b.get('live_marginal')
        if lm is None:
            continue
        tier = b.get('live_value_tier') or '-'
        # IL guard: snapshots can be stale for IL'd players; mark them.
        il_flag = p.get('lineup_slot') == 'IL' or p.get('injured')
        # rp-decline CONTEXT tier (RP only; Tier-B watch flag, never moves lm).
        rpd = rp_decline.get(_norm(name)) if ptype == 'RP' else None
        rec = {
            'name': name,
            'pos': pos,
            'live_marginal': float(lm),
            'tier': tier,
            'il': bool(il_flag),
            'blended': b.get('blended_xfp'),
            'display_unit': b.get('display_unit') or '',
            'rp_decline': (rpd or {}).get('tier'),
        }
        # SELL-HIGH surface: a ROLE-RISK reliever that still HAS a role to lose is
        # an arm whose owner should be selling while saves/holds are still landing.
        # As a trade *ask* it's a do-not-acquire flag; as bait awareness it's their
        # asset that's about to crater. Either way: surface it explicitly.
        if rpd and rpd.get('tier') == 'ROLE-RISK' and rpd.get('has_role'):
            rp_sellhigh.append({**rec, 'role': rpd.get('role', ''),
                                'velo_yoy': rpd.get('velo_yoy'),
                                'legs': rpd.get('legs')})
        if lm < -10:
            sell_bait.append(rec)
        if lm > 30:
            # Positional gap fit: opponent's lm must beat my best at same pos.
            my_best = my_gap.get(pos, float('-inf'))
            if lm > my_best:
                rec['my_best_at_pos'] = None if my_best == float('-inf') else my_best
                trade_ask.append(rec)

    sell_bait.sort(key=lambda r: r['live_marginal'])              # most negative first
    trade_ask.sort(key=lambda r: -r['live_marginal'])             # biggest plus first

    rp_sellhigh.sort(key=lambda r: (r.get('velo_yoy') if r.get('velo_yoy') is not None else 0))

    out = []
    out.append('')
    out.append(f'=== {opp_name} — {style} ===')

    # rp-decline SELL-HIGH surface (the killer app): ROLE-RISK closers/setups
    # this opponent holds whose role is most likely to crater. Trade-ask = do NOT
    # acquire (value about to fall); awareness = their asset is depreciating.
    if rp_sellhigh:
        out.append('')
        out.append('### ⚠ ROLE-RISK relievers on this roster → sell-high candidates '
                   '(rp-decline; Tier-B context, never moves rprs2):')
        for r in rp_sellhigh[:5]:
            vy = f'{r["velo_yoy"]:+.1f}' if r.get('velo_yoy') is not None else '--'
            out.append(f'  - {r["name"]} ({r.get("role","") or "RP"}) — velo YoY {vy}, '
                       f'{r.get("legs","?")}/3 legs converged. Their owner should sell '
                       f'while saves/holds still land; for YOU this is a do-NOT-acquire '
                       f'(role likely to crater). Weaker/noisier than /sp-decline '
                       f'(role loss ~1/3 manager-driven) — verify via /triangulate + '
                       f'/rp-decline before any move.')

    # Sell-bait table.
    out.append('')
    out.append('### Their sell-bait (live_marginal < -10):')
    if not sell_bait:
        out.append('  (none — roster has no DOWNGRADE/ACTIVE_LOSS players. Honest read: nothing to pry loose.)')
    else:
        out.append(f'  | {"Player":<25} | {"Pos":<4} | {"live_marg":>9} | {"Tier":<14} | IL | rp-decline |')
        out.append(f'  | {"-"*25} | {"-"*4} | {"-"*9} | {"-"*14} | -- | {"-"*10} |')
        for r in sell_bait[:8]:
            il = 'Y' if r['il'] else ' '
            rpd = r.get('rp_decline') or ''
            out.append(f'  | {r["name"][:25]:<25} | {r["pos"]:<4} | {r["live_marginal"]:>9.1f} | {r["tier"]:<14} | {il}  | {rpd:<10} |')

    # Trade-ask table.
    out.append('')
    out.append('### Their stars worth asking for (live_marginal > +30, fits MY positional gap):')
    if not trade_ask:
        out.append('  (none — either no big-plus players or my roster already covers those positions.)')
    else:
        out.append(f'  | {"Player":<25} | {"Pos":<4} | {"live_marg":>9} | {"Tier":<14} | my best |')
        out.append(f'  | {"-"*25} | {"-"*4} | {"-"*9} | {"-"*14} | ------- |')
        for r in trade_ask[:6]:
            mb = r.get('my_best_at_pos')
            mb_s = f'{mb:.1f}' if isinstance(mb, (int, float)) else 'none'
            out.append(f'  | {r["name"][:25]:<25} | {r["pos"]:<4} | {r["live_marginal"]:>9.1f} | {r["tier"]:<14} | {mb_s:>7} |')

    # Pitch template.
    out.append('')
    out.append('### Pitch template (behavioral-fit):')
    template = PITCH_TEMPLATES.get(style, 'Unknown style — default to standard live_marginal pitch.')
    out.append(f'  - {style}: {template}')
    if sell_bait and trade_ask:
        give = sell_bait[0]  # we offer something — pick something with high PL rank but low lm? we don't have PL here
        get_ = trade_ask[0]
        out.append(f'  - Example skeleton: "I send [your high-PL-rank, low-live_marginal name], you send {get_["name"]} '
                   f'({get_["pos"]}, live_marg +{get_["live_marginal"]:.0f})."')
        out.append(f'  - Anchor sell-bait of theirs to mention as "we both upgrade": {give["name"]} ({give["pos"]}, '
                   f'live_marg {give["live_marginal"]:.0f}) is leaking value — pitch them a replacement.')
    elif not sell_bait and not trade_ask:
        out.append('  - Honest read: no clear lever here. Skip and revisit after their next move.')
    return '\n'.join(out)


# ---------- Main --------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--opponent', type=str, help='Restrict to a single opponent')
    ap.add_argument('--my-position', type=str,
                    help='Only consider trade-ask targets at this position (e.g. SS)')
    args = ap.parse_args()

    warn = fa_snapshot_age_warning()
    if warn:
        print(warn)
        print()

    rosters = load_rosters()
    profiles = get_team_profiles()
    my_gap = my_position_gap_map(rosters, args.my_position)
    rp_decline = _rp_decline_tier_map()   # Tier-B RP context tiers (may be {})

    opponents = [t for t in rosters.keys() if t != MY_TEAM]
    if args.opponent:
        if args.opponent not in opponents:
            print(f'opponent not found: {args.opponent}', file=sys.stderr)
            print(f'available: {opponents}', file=sys.stderr)
            sys.exit(1)
        opponents = [args.opponent]

    print('=' * 80)
    print('  TRADE TARGET SCAN — live_marginal + behavioral profile')
    print(f'  My team: {MY_TEAM}    Opponents scanned: {len(opponents)}')
    if args.my_position:
        print(f'  Positional filter: {args.my_position}')
    print('=' * 80)

    for opp in opponents:
        print(opponent_block(opp, rosters[opp], profiles.get(opp, {}), my_gap,
                             rp_decline))

    print()
    print('=' * 80)
    print('  Done. Caveats: live_marginal is per-bucket FP scale '
          '(H FP/season, SP/RP FP/season-equivalent). IL=Y rows may be '
          'stale; do not act on them without re-pulling.')
    print('=' * 80)


if __name__ == '__main__':
    main()
