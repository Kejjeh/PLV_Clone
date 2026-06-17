"""opponent_profiler.py — derive per-team behavioral profile from transaction data.

For each of the 8 teams, computes:
  - Activity stats (volume, cadence, day-of-week peak)
  - Bucket churn (H vs SP vs RP) — what positions they touch
  - Quality of adds: avg PL rank, avg model rank, % TRENDING_UP archetype, % BUY verdict today
  - Quality of drops: % drops that landed on another roster (= undervaluation), % drops that triangulate FADE/CAUTION today (= correctly cut)
  - Hold time: median days between add and same-player drop (impulsiveness)
  - Style label (data-driven)

Then synthesizes a master "league navigation" strategy:
  - Who to bid against (high overlap profiles) vs avoid
  - Whose drops to scoop
  - Whose adds to mirror or fade
  - Trade-target ranking

Run:
  python scripts/xfp/opponent_profiler.py
  python scripts/xfp/opponent_profiler.py --team "Frendy's Fantastic Team"
  python scripts/xfp/opponent_profiler.py --navigate          # master strategy section only
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
TRI = ROOT / 'data' / 'research' / 'triangulate_universe'


def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower().strip()


def load_data():
    tx = pd.read_csv(TRI / 'all_transactions.csv')
    tx['dt'] = pd.to_datetime(tx['date'], unit='ms')
    tx['k'] = tx['player_name'].apply(_norm)
    tri = pd.read_csv(TRI / 'triangulate_results.csv')
    tri['k'] = tri['player_name'].apply(_norm)
    rosters = json.load(open(TRI / 'all_team_rosters.json'))
    # build "where is each player now" lookup from current rosters
    where = {}
    for team, players in rosters.items():
        for p in players:
            where[_norm(p['name'])] = team
    return tx, tri, rosters, where


def _bucket(pos: str) -> str:
    if not isinstance(pos, str):
        return '?'
    if pos in ('SP',):
        return 'SP'
    if pos in ('RP',):
        return 'RP'
    return 'H'


def profile_team(team: str, tx: pd.DataFrame, tri: pd.DataFrame, where: dict) -> dict:
    team_tx = tx[tx['team'] == team].sort_values('dt')
    if team_tx.empty:
        return {'team': team, 'error': 'no transactions'}

    adds = team_tx[team_tx['action'].str.contains('ADDED', na=False)]
    drops = team_tx[team_tx['action'].str.contains('DROPPED', na=False)]

    # Cadence
    span_days = max(1, (team_tx['dt'].max() - team_tx['dt'].min()).days)
    weekday_dist = team_tx['dt'].dt.weekday.value_counts(normalize=True).reindex(range(7), fill_value=0).to_dict()
    peak_dow = max(weekday_dist, key=weekday_dist.get) if weekday_dist else None
    dow_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    # Bucket distribution
    add_buckets = adds['position'].apply(_bucket).value_counts().to_dict() if not adds.empty else {}
    drop_buckets = drops['position'].apply(_bucket).value_counts().to_dict() if not drops.empty else {}

    # Quality of adds — join with current triangulate state (proxy for what they bought)
    add_tri = adds.merge(tri, on='k', how='left', suffixes=('', '_tri'))
    def _num(s):
        try: return float(s)
        except: return None
    pls = [_num(x) for x in add_tri['pl_rank'] if pd.notna(x)]
    pls = [p for p in pls if p is not None]
    mdls = [_num(x) for x in add_tri['model_rank'] if pd.notna(x)]
    mdls = [m for m in mdls if m is not None]
    traj_up = (add_tri['arche_traj'].astype(str).str.contains('TRENDING_UP', na=False)).sum()
    traj_down = (add_tri['arche_traj'].astype(str).str.contains('TRENDING_DOWN|CAREER_LOW', na=False)).sum()
    buy_now = (add_tri['verdict_top'] == 'BUY').sum()
    fade_now = (add_tri['verdict_top'].isin(['FADE', 'CAUTION'])).sum()

    avg_pl_add = sum(pls)/len(pls) if pls else None
    avg_mdl_add = sum(mdls)/len(mdls) if mdls else None
    pct_traj_up = traj_up / max(1, len(add_tri))
    pct_chase = fade_now / max(1, len(add_tri))

    # Quality of drops — for each drop, where is the player now?
    drops_scooped = 0
    drops_remain_fa = 0
    drops_fade_now = 0
    for _, r in drops.iterrows():
        k = r['k']
        if k in where and where[k] != team:
            drops_scooped += 1
        else:
            drops_remain_fa += 1
        tri_row = tri[tri['k'] == k]
        if not tri_row.empty and tri_row.iloc[0]['verdict_top'] in ('FADE', 'CAUTION'):
            drops_fade_now += 1
    n_drops = len(drops)
    pct_drops_scooped = drops_scooped / max(1, n_drops)
    pct_drops_vindicated = drops_fade_now / max(1, n_drops)

    # Hold-time (impulsiveness): for each (add then later drop) pair, days between
    hold_times = []
    for k in adds['k'].unique():
        adds_k = adds[adds['k'] == k].sort_values('dt')
        drops_k = drops[drops['k'] == k].sort_values('dt')
        for _, a in adds_k.iterrows():
            later_drops = drops_k[drops_k['dt'] > a['dt']]
            if not later_drops.empty:
                hold_times.append((later_drops.iloc[0]['dt'] - a['dt']).days)
    median_hold = sorted(hold_times)[len(hold_times)//2] if hold_times else None

    # Style label — data-driven
    label, one_liner = _classify_style(
        n_tx=len(team_tx), span=span_days,
        avg_pl_add=avg_pl_add, pct_traj_up=pct_traj_up, pct_chase=pct_chase,
        pct_drops_scooped=pct_drops_scooped, pct_drops_vindicated=pct_drops_vindicated,
        median_hold=median_hold, peak_dow=peak_dow,
    )

    return {
        'team': team,
        'style_label': label,
        'one_liner': one_liner,
        'tx_total': len(team_tx),
        'tx_per_week': round(len(team_tx) / max(1, span_days/7), 2),
        'n_adds': len(adds),
        'n_drops': n_drops,
        'peak_dow': dow_labels[peak_dow] if peak_dow is not None else None,
        'peak_dow_share': round(weekday_dist.get(peak_dow, 0), 2),
        'add_buckets': add_buckets,
        'drop_buckets': drop_buckets,
        'avg_pl_add': round(avg_pl_add, 1) if avg_pl_add else None,
        'avg_mdl_add': round(avg_mdl_add, 1) if avg_mdl_add else None,
        'pct_traj_up_adds': round(pct_traj_up, 2),
        'pct_chase_adds_FADE_now': round(pct_chase, 2),
        'pct_drops_scooped_by_others': round(pct_drops_scooped, 2),
        'pct_drops_vindicated': round(pct_drops_vindicated, 2),
        'median_hold_days_before_redrop': median_hold,
    }


def _classify_style(n_tx, span, avg_pl_add, pct_traj_up, pct_chase,
                    pct_drops_scooped, pct_drops_vindicated, median_hold, peak_dow):
    """Return (style_label, one_liner) from data-derived stats."""
    tx_rate = n_tx / max(1, span/7)
    # Decision tree based on observed behavior

    # Decision tree in priority order — the FIRST matching rule wins.

    # ASLEEP: very low volume
    if tx_rate < 1.5:
        return 'ASLEEP_AT_THE_WHEEL', f'Acts only ~{tx_rate:.1f}/wk; drafted-then-forgotten roster shape.'

    # OUTCOME_CHASER: high chase rate dominates — catch this first before patience metrics
    if pct_chase >= 0.30:
        return 'OUTCOME_CHASER', f'{pct_chase*100:.0f}% of adds triangulate FADE/CAUTION today; pays PL rent at avg #{avg_pl_add:.0f}.'

    # PL_PROCESS_FOLLOWER: TRENDING_UP heavy, low chase rate, PL-aware. The Late
    # Night signature: 46% TRENDING_UP + 0% chase + peak PL refresh day.
    if pct_traj_up >= 0.40 and pct_chase <= 0.15:
        return 'PL_PROCESS_FOLLOWER', f'{pct_traj_up*100:.0f}% TRENDING_UP adds, only {pct_chase*100:.0f}% chase; peak day {peak_dow}.'

    # DISCIPLINED_MINIMALIST: low volume + clean drops
    if tx_rate < 3.5 and pct_drops_vindicated >= 0.4 and pct_chase <= 0.25:
        return 'DISCIPLINED_MINIMALIST', f'Acts ~{tx_rate:.1f}/wk, drops {pct_drops_vindicated*100:.0f}% vindicated, chase rate only {pct_chase*100:.0f}%.'

    # IMPULSIVE_CHURNER: short hold-before-redrop
    if median_hold is not None and median_hold < 14:
        return 'IMPULSIVE_CHURNER', f'Median hold-before-redrop {median_hold}d (low patience); {pct_drops_scooped*100:.0f}% of drops scooped by other teams.'

    return 'BALANCED_SHARPSHOOTER', f'~{tx_rate:.1f}/wk, mixed signals, no extreme tendency.'


def navigation_strategy(profiles: list[dict]) -> str:
    """Synthesize a master navigation strategy table from profiles."""
    me = next((p for p in profiles if p['team'] == 'New York Ligers'), None)
    if not me:
        return 'New York Ligers profile not found.'

    lines = [
        '',
        '=' * 80,
        '  MASTER NAVIGATION — how to act around each opponent',
        '=' * 80,
        '',
        '| Opponent | Style | Bid against? | Scoop their drops? | Trade target | Drop window |',
        '|---|---|---|---|---|---|',
    ]
    for p in profiles:
        if p['team'] == 'New York Ligers':
            continue
        style = p['style_label']
        # Bid-against logic: same archetypes we want = overlap = compete
        bid = 'AVOID' if style in ('PL_PROCESS_FOLLOWER', 'DISCIPLINED_MINIMALIST') else \
              'COMPETE' if style == 'OUTCOME_CHASER' else 'SOFT'
        # Scoop logic: high drop-scoop rate means their drops are valuable
        scoop = 'YES' if p['pct_drops_scooped_by_others'] >= 0.20 else \
                'CHECK' if p['pct_drops_vindicated'] < 0.4 else 'PASS'
        # Trade-target logic: outcome chasers + asleep are easiest marks
        trade = 'TOP' if style == 'OUTCOME_CHASER' else \
                'YES' if style == 'IMPULSIVE_CHURNER' else \
                'COOL' if style in ('ASLEEP_AT_THE_WHEEL', 'DISCIPLINED_MINIMALIST', 'PL_PROCESS_FOLLOWER') else 'OK'
        # Drop window: when do they typically act, so when should we beat them
        window = f"before {p['peak_dow']}" if p['peak_dow'] else '—'
        lines.append(f"| {p['team']} | {style.replace('_',' ').lower()} | {bid} | {scoop} | {trade} | {window} |")

    # Operational rules — BrownU is FCFS (faab=False per league.settings).
    # See memory/reference_brownu_acquisition_rules.md.
    lines += [
        '',
        '### Tactical rules of engagement (BrownU = first-come-first-served, no FAAB)',
        '',
        '**Sniping FAs (timing is the only weapon):**',
        '- AVOID-list teams want the SAME archetypes you want — peak-day matters.',
        '  Claim BEFORE their peak day or accept the loss; there is no late equalizer.',
        '- COMPETE-list teams (outcome chasers) act AFTER a hot streak peaks — beat them',
        '  to a target by acting on process signal BEFORE the box-score confirms it.',
        '- SOFT-list teams are inconsistent — your normal cadence is fine.',
        '',
        '**Scooping opponent drops (waiver window ~24-48h):**',
        '- Recently-dropped players enter waivers before becoming FA. Submit claim',
        '  immediately on any "YES"-team drop; you may be one of multiple claimants and',
        '  ESPN resolves by rolling waiver order (no bid).',
        '- "YES" teams have a track record of drops that other rosters immediately want',
        '  (Varland, Suarez, Bradish, Senga — all panic-dropped, all re-rostered fast).',
        '- "CHECK" teams have low vindication — their drops may be impulsive; worth a look.',
        '- "PASS" teams cut wisely — usually no edge.',
        '',
        '**Trade negotiation:**',
        '- "TOP" trade targets (outcome chasers) — pitch them PL top-50 names they want;',
        '  give up TRENDING_DOWN archetype bats from your bench.',
        '- "YES" trade targets are impulsive — accept same-tier swaps framed as upgrade.',
        '- "COOL" trade targets are disciplined — only move on clear wins for them.',
        '',
        '**Drop-window timing summary:**',
        '- The peak-day-of-week column = when each manager USUALLY acts. Claim BEFORE',
        '  that day to win head-to-head FA races; you cannot outbid them, you can only',
        '  out-time them.',
        '- For waiver-period claims on recently-dropped players, submit immediately —',
        '  ESPN priority order is the only tiebreaker.',
    ]
    return '\n'.join(lines)


def format_card(p: dict) -> str:
    if 'error' in p:
        return f"\n=== {p['team']} ===\nERROR: {p['error']}\n"
    lines = [
        '',
        f"=== {p['team']} — {p['style_label']} ===",
        f"  {p['one_liner']}",
        '',
        f"  Activity:    {p['tx_total']} tx total, {p['tx_per_week']} per week. Peak day: {p['peak_dow']} ({p['peak_dow_share']*100:.0f}% of all moves).",
        f"  Bucket mix:  ADDS  {p['add_buckets']}    DROPS {p['drop_buckets']}",
        f"  Add quality: avg PL rank #{p['avg_pl_add']}, avg mdl rank #{p['avg_mdl_add']}, {p['pct_traj_up_adds']*100:.0f}% TRENDING_UP, {p['pct_chase_adds_FADE_now']*100:.0f}% FADE/CAUTION today",
        f"  Drop quality: {p['pct_drops_scooped_by_others']*100:.0f}% scooped by other teams, {p['pct_drops_vindicated']*100:.0f}% vindicated as FADE today",
        f"  Patience:    median hold-before-redrop = {p['median_hold_days_before_redrop']}d" if p['median_hold_days_before_redrop'] else "  Patience:    no add-then-drop history",
    ]
    return '\n'.join(lines)


def rank_pickup_drop_skill(profiles: list[dict]) -> list[tuple[str, float, dict]]:
    """Score each manager's pickup-and-drop skill 0-100 with components."""
    out = []
    for p in profiles:
        if 'error' in p:
            continue
        # Add quality: fewer chase adds = better, more traj_up = better, lower avg PL (good adds) = better
        add_score = 0.0
        add_score += (1 - p['pct_chase_adds_FADE_now']) * 40       # 0-40 pts for not chasing
        add_score += p['pct_traj_up_adds'] * 30                    # 0-30 pts for traj_up
        # Drop quality: high vindication, low scooped
        drop_score = 0.0
        drop_score += p['pct_drops_vindicated'] * 20               # 0-20 pts for vindicated drops
        drop_score += (1 - p['pct_drops_scooped_by_others']) * 10  # 0-10 pts for not getting scooped
        total = round(add_score + drop_score, 1)
        out.append((p['team'], total, {
            'add_quality_40+30': round(add_score, 1),
            'drop_quality_20+10': round(drop_score, 1),
            'style': p['style_label'],
        }))
    out.sort(key=lambda x: -x[1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--team', type=str, help='Profile a single team only')
    ap.add_argument('--navigate', action='store_true', help='Show master navigation only')
    ap.add_argument('--rank-only', action='store_true', help='Show only the pickup-and-drop skill ranking')
    args = ap.parse_args()

    tx, tri, rosters, where = load_data()
    teams = sorted(rosters.keys())
    profiles = [profile_team(t, tx, tri, where) for t in teams]

    if args.team:
        p = next((x for x in profiles if x['team'] == args.team), None)
        if not p:
            print(f'team not found: {args.team}', file=sys.stderr)
            print(f'available: {teams}', file=sys.stderr)
            sys.exit(1)
        print(format_card(p))
        return

    if not args.navigate and not args.rank_only:
        # Print all 8 cards
        for p in profiles:
            print(format_card(p))

    # Skill ranking
    print()
    print('=' * 80)
    print('  PICKUP-AND-DROP SKILL RANKING')
    print('=' * 80)
    print(f'  {"Rank":<5}{"Team":<35}{"Score":>7}    {"Add (40+30)":<15}{"Drop (20+10)":<15}{"Style":<25}')
    for i, (team, score, comp) in enumerate(rank_pickup_drop_skill(profiles), 1):
        print(f'  {i:<5}{team:<35}{score:>7.1f}    {str(comp["add_quality_40+30"]):<15}{str(comp["drop_quality_20+10"]):<15}{comp["style"]:<25}')

    if args.rank_only:
        return

    # Master navigation
    print(navigation_strategy(profiles))


if __name__ == '__main__':
    main()
