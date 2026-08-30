"""lineup_optimizer.py — weekly SP-cap-aware start optimizer.

Pulls Ligers SPs + next-7-day MLB schedule. For each SP, identifies probable
start dates (via MLB Stats API probablePitcher field + 5-day rotation
fallback). Projects fp per start using rp3 (matchup-adjusted if available).
Identifies cap-binding situations (>10 projected starts in week) and
recommends which lowest-EV starts to bench.

Background: BrownU league caps SP scoring at the first 10 starts per week.
Beyond 10, additional starts don't count. The optimizer flags weeks where
we're projected to have more than 10 starts so we can bench the worst ones.

Outputs:
  - data/outputs/lineup_optimizer_weekly.csv (per-start expected fp table)
  - data/outputs/lineup_optimizer.json       (dashboard JSON)

Usage:
    python scripts/xfp/lineup_optimizer.py
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import json
import sys
import unicodedata
import re

import pandas as pd
from plv_clone.projections import PROJECTIONS
import requests

_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))

from plv_clone.paths import ROOT  # single source for the repo root (was a hardcoded literal)
OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

from plv_clone.cap_math import (  # single source for the SP-cap rule
    SP_CAP, UNRESOLVED_IMPUTE_NOTE, cap_excess_starts, impute_unresolved_fps)
# Default cap = a standard single week (10). main() resolves the CURRENT period's
# cap live (16 in the ASG block / 20 in a 2-week playoff round) and passes it to
# cap_excess_starts; this constant is only the fail-soft fallback when the live
# league object is unreachable. Period-aware fix 2026-07-11.
WEEK_CAP_SP_STARTS = SP_CAP

# MLB team_id → tricode mapping
TEAM_ID_TO_ABBR = {
    108: 'LAA', 109: 'AZ', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
    114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KC', 119: 'LAD',
    120: 'WSH', 121: 'NYM', 133: 'ATH', 134: 'PIT', 135: 'SD', 136: 'SEA',
    137: 'SF', 138: 'STL', 139: 'TB', 140: 'TEX', 141: 'TOR', 142: 'MIN',
    143: 'PHI', 144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}


# _norm was join_key's exact algorithm (accent-strip + sorted alpha tokens);
# routed to the name_match owner (item 10, 2026-07-04). Proven byte-identical on
# a diverse name set (accents, suffixes, "Last, First"), so this is a pure move.
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402
from plv_clone.league_config import MY_TEAM_NAME


def fetch_week_schedule(days_ahead: int = 7) -> pd.DataFrame:
    """Adapter over the plv_clone.mlb_stats.get_probables owner.

    Rebuilds the historical one-row-per-game frame (home/away probable
    columns) by pairing get_probables' per-slot rows on game_pk. Games with
    no confirmed probable on either side are dropped — downstream only
    matches on probable names, so those rows were never consumed.
    """
    from plv_clone.mlb_stats import get_probables
    today = date.today()
    end = today + timedelta(days=days_ahead - 1)
    games: dict = {}
    for r in get_probables(today, end):
        g = games.setdefault(r['game_pk'], {
            'date': r['date'],
            'gamePk': r['game_pk'],
            'home_id': None, 'home_abbr': r['park_abbr'],
            'away_id': None, 'away_abbr': None,
            'home_probable_id': None, 'home_probable_name': None,
            'away_probable_id': None, 'away_probable_name': None,
        })
        side = 'home' if r['team_abbr'] == r['park_abbr'] else 'away'
        g[f'{side}_abbr'] = r['team_abbr']
        g[f'{"away" if side == "home" else "home"}_abbr'] = r['opp_abbr']
        g[f'{side}_probable_id'] = r['pitcher_id']
        g[f'{side}_probable_name'] = r['pitcher_name']
    return pd.DataFrame(list(games.values()))


def main():
    from plv_clone.league_state import LeagueState
    _ls = LeagueState()
    teams = _ls.all_teams()
    # Resolve THIS matchup period's SP-start cap (10 normal / 16 ASG / 20 playoff
    # 2-week) instead of assuming a flat 10 — the same resolver matchup.html and
    # /roster-audit use. Fail-soft: any ESPN hiccup keeps the 10 default.
    week_cap = WEEK_CAP_SP_STARTS
    try:
        from scripts.xfp.lib.period_meta import resolve_current_period_meta
        _pmeta = resolve_current_period_meta(_ls._get_league())
        week_cap = _pmeta['sp_cap']
        print(f"Period {_pmeta['period']} · {_pmeta['weeks']}-week · "
              f"SP cap {week_cap}")
    except Exception as _e:
        print(f"  (period cap resolve failed: {type(_e).__name__}; "
              f"using default {week_cap})")
    ligers = teams[teams['team_name'] == MY_TEAM_NAME]
    sps = ligers[ligers['position'].isin(['SP', 'P'])][['player_name', 'pro_team']]
    print(f'Ligers SPs: {len(sps)}')
    print(sps['player_name'].tolist())

    # Pull next-7-day schedule
    sched = fetch_week_schedule(days_ahead=7)
    print(f'\nWeek schedule: {len(sched)} games')

    # Load rp3 projections + name normalization
    rp3 = PROJECTIONS.rp3()
    rp3['name_key'] = rp3['player_name'].map(_norm)
    # Dedupe by name_key — keep first (highest-rank duplicate)
    rp3 = rp3.drop_duplicates('name_key', keep='first')
    rp3_lookup = rp3.set_index('name_key')[['pitcher', 'xfp_rp3_per_start',
                                              'schedule_factor', 'xfp_rp3_per_start_sched']].to_dict('index')

    # For each SP, find their probable starts in week
    rows = []
    for _, sp in sps.iterrows():
        name = sp['player_name']
        nm = _norm(name)
        # Try direct match in probables (handles "Last, First" vs "First Last")
        for _, g in sched.iterrows():
            for side in ['home', 'away']:
                pname = g.get(f'{side}_probable_name')
                if not pname:
                    continue
                if _norm(pname) == nm:
                    # Find matching rp3 row
                    rp = rp3_lookup.get(nm) or {}
                    fp_base = rp.get('xfp_rp3_per_start')
                    fp_adj = rp.get('xfp_rp3_per_start_sched') or fp_base
                    rows.append({
                        'date': g['date'],
                        'pitcher': name,
                        'team_abbr': g[f'{side}_abbr'],
                        'opp_team_abbr': g['away_abbr'] if side == 'home' else g['home_abbr'],
                        'is_home': side == 'home',
                        'gamePk': g['gamePk'],
                        'xfp_per_start': fp_base,
                        'xfp_per_start_sched': fp_adj,
                    })

    starts = pd.DataFrame(rows).sort_values('date')

    if starts.empty:
        # Fallback: probables aren't published far ahead; use rotation cadence
        print('\nNo MLB probables matched. Using 5-day cadence fallback from rp3 schedule_factor.')
        # We'll project each rostered SP with one start in the week using their projection
        rp_l = rp3.merge(sps, left_on='player_name', right_on='player_name', how='inner')
        for _, r in rp_l.iterrows():
            rows.append({
                'date': 'TBD',
                'pitcher': r['player_name'],
                'team_abbr': r.get('team'),
                'opp_team_abbr': None,
                'is_home': None,
                'gamePk': None,
                'xfp_per_start': r['xfp_rp3_per_start'],
                'xfp_per_start_sched': r.get('xfp_rp3_per_start_sched') or r['xfp_rp3_per_start'],
            })
        starts = pd.DataFrame(rows)

    # Ensure numeric, fall back to base fp if sched-adj missing
    starts['xfp_per_start_sched'] = starts['xfp_per_start_sched'].fillna(starts['xfp_per_start'])
    # issue #61 (decided 2026-08-28): a start whose rp3 rate failed to resolve
    # must NOT carry a filler (the old flat 10.0) into bench-ranking — that
    # auto-decides the unknown (the Eury Pérez name-match miss read an elite
    # arm as the week's worst start). Impute at the MEDIAN of the week's
    # RESOLVED starts (neutral) and surface it loudly in every output row.
    _unres = starts['xfp_per_start_sched'].isna()
    starts['rate_unresolved'] = _unres
    if _unres.any():
        imputed, med = impute_unresolved_fps(
            starts['xfp_per_start_sched'].fillna(0.0).tolist(),
            (~_unres).tolist())
        if med is None:      # EVERY start unresolved — no median to anchor on;
            med = 10.0       # league-average fallback, still surfaced below
            imputed = [med] * len(starts)
        starts['xfp_per_start_sched'] = imputed
        for _nm in starts.loc[_unres, 'pitcher']:
            print(f'  !! {_nm}: {UNRESOLVED_IMPUTE_NOTE} ({med:.1f} fp)')
    starts['xfp_per_start'] = starts['xfp_per_start'].fillna(starts['xfp_per_start_sched'])

    # Rank globally by xfp_per_start_sched, descending (display column).
    starts['rank'] = starts['xfp_per_start_sched'].rank(ascending=False, method='min').astype(int)
    # Cap which starts count via the canonical planning cap (cap_math): start the
    # best `week_cap` by projected FP, bench the rest. cap_excess_starts takes
    # EXACTLY the top `week_cap` (stable tie-break) — unlike rank<=cap, which
    # over-counts when ties straddle the boundary. week_cap is period-resolved.
    _excess = cap_excess_starts(starts['xfp_per_start_sched'].tolist(), week_cap)
    starts['count_toward_cap'] = [i not in _excess for i in range(len(starts))]
    starts['decision'] = starts['count_toward_cap'].map(lambda x: 'START' if x else 'BENCH (cap)')
    # Loud in every output row (print / CSV / JSON / dashboard), separate from
    # `decision` so START/BENCH stays machine-readable.
    starts['rate_note'] = starts['rate_unresolved'].map(
        lambda x: f'⚠ {UNRESOLVED_IMPUTE_NOTE}' if x else '')

    total = len(starts)
    capped = starts['count_toward_cap'].sum()
    sum_count = starts.loc[starts['count_toward_cap'], 'xfp_per_start_sched'].sum()
    sum_total = starts['xfp_per_start_sched'].sum()
    benched_total = sum_total - sum_count

    print(f'\n=== Lineup Optimizer Summary ===')
    print(f'  Total projected SP starts this week: {total}')
    print(f'  Cap: {week_cap}')
    print(f'  Counting toward score: {capped}')
    if total > week_cap:
        print(f'  *** OVER CAP by {total - week_cap} starts ***')
        print(f'  Bench-loss without optimizing: {benched_total:.1f} fp (lowest ranked auto-skipped)')
    else:
        print(f'  Under cap by {week_cap - total}. All starts count.')
    print(f'  Expected counting-score fp this week: {sum_count:.1f}')

    print(f'\n=== Per-start ranking ===')
    cols = ['date', 'pitcher', 'team_abbr', 'opp_team_abbr', 'is_home',
            'xfp_per_start', 'xfp_per_start_sched', 'rank', 'decision',
            'rate_note']
    print(starts[cols].to_string(index=False))

    starts.to_csv(OUT / 'lineup_optimizer_weekly.csv', index=False)
    print(f'\nwrote {OUT / "lineup_optimizer_weekly.csv"}')

    payload = {
        'as_of': str(date.today()),
        'cap': week_cap,
        'total_starts': int(total),
        'counting_starts': int(capped),
        'expected_counting_fp': round(float(sum_count), 1),
        'bench_loss_if_unoptimized': round(float(benched_total), 1),
        # issue #61: pitchers whose bench-ranking fp is an imputed week median,
        # not a resolved rp3 rate — treat their START/BENCH rows with caution.
        'unresolved_rates': sorted(
            starts.loc[starts['rate_unresolved'], 'pitcher'].unique().tolist()),
        'starts': starts[cols].to_dict(orient='records'),
    }
    with open(OUT / 'lineup_optimizer.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote {OUT / "lineup_optimizer.json"}')


if __name__ == '__main__':
    main()
