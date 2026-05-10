"""opponent_matchup_history.py — auto-pull head-to-head history from ESPN.

Walks the current and prior season schedules, computes per-opponent W/L
record vs the Ligers, average margin, blowout count, and most-recent
result. Updates the AUTO-GENERATED section of data/research/opponent_notes.md
without touching manual observations the user has written by hand.

Output:
  - data/research/opponent_notes.md (auto section refreshed in-place)
  - data/outputs/opponent_matchup_history.json (for dashboard reuse)

Usage:
    python scripts/xfp/opponent_matchup_history.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'data' / 'outputs'
NOTES = ROOT / 'data' / 'research' / 'opponent_notes.md'
AUTO_START = '<!-- AUTO-GENERATED:matchup_history -->'
AUTO_END = '<!-- /AUTO-GENERATED:matchup_history -->'

MY_TEAM_NAME = 'New York Ligers'


def fetch_matchup_results(league) -> list[dict]:
    """Walk Ligers' Matchup objects from team.schedule, extract completed weeks."""
    rows = []
    my_team = next((t for t in league.teams if t.team_name == MY_TEAM_NAME), None)
    if my_team is None:
        return rows

    for i, m in enumerate(getattr(my_team, 'schedule', None) or []):
        if m is None:
            continue
        home = getattr(m, 'home_team', None)
        away = getattr(m, 'away_team', None)
        hs = getattr(m, 'home_final_score', 0)
        as_ = getattr(m, 'away_final_score', 0)
        winner = getattr(m, 'winner', None)
        if not home or not away:
            continue
        if (hs or 0) == 0 and (as_ or 0) == 0:
            continue  # unplayed
        if winner not in ('HOME', 'AWAY', 'TIE'):
            continue  # in-progress week (winner not yet decided)
        if home.team_name == MY_TEAM_NAME:
            opp = away; my_score = float(hs); opp_score = float(as_)
            result = 'W' if winner == 'HOME' else ('L' if winner == 'AWAY' else 'T')
        else:
            opp = home; my_score = float(as_); opp_score = float(hs)
            result = 'W' if winner == 'AWAY' else ('L' if winner == 'HOME' else 'T')
        rows.append({
            'year': league.year,
            'week': i + 1,
            'opp_team_id': opp.team_id,
            'opp_name': opp.team_name,
            'my_score': my_score,
            'opp_score': opp_score,
            'margin': my_score - opp_score,
            'result': result,
        })
    return rows


def summarize_per_opponent(rows: list[dict]) -> dict:
    by_opp = defaultdict(list)
    for r in rows:
        by_opp[r['opp_name']].append(r)
    summary = {}
    for opp, games in by_opp.items():
        wins = sum(1 for g in games if g['result'] == 'W')
        losses = sum(1 for g in games if g['result'] == 'L')
        ties = sum(1 for g in games if g['result'] == 'T')
        margins = [g['margin'] for g in games]
        avg_margin = sum(margins) / len(margins) if margins else 0.0
        blowouts_win = sum(1 for m in margins if m >= 25)
        blowouts_loss = sum(1 for m in margins if m <= -25)
        latest = max(games, key=lambda g: (g['year'], g['week']))
        summary[opp] = {
            'opp_name': opp,
            'n_games': len(games),
            'wins': wins, 'losses': losses, 'ties': ties,
            'avg_margin': round(avg_margin, 1),
            'blowouts_win': blowouts_win,
            'blowouts_loss': blowouts_loss,
            'latest_year': latest['year'],
            'latest_week': latest['week'],
            'latest_result': latest['result'],
            'latest_margin': round(latest['margin'], 1),
            'all_games': games,
        }
    return summary


def update_notes(summary: dict) -> None:
    """Insert/refresh AUTO-GENERATED block in opponent_notes.md, preserving manual sections."""
    existing = NOTES.read_text(encoding='utf-8') if NOTES.exists() else '# Opponent Notes — BrownU League\n\n'

    # Build auto block
    lines = [AUTO_START, '## Auto-pulled matchup history', '']
    for opp, s in sorted(summary.items(), key=lambda kv: -kv[1]['wins']):
        record = f"{s['wins']}-{s['losses']}" + (f"-{s['ties']}" if s['ties'] else '')
        lines.append(f"### vs {opp}")
        lines.append(f"- All-time vs Ligers: **{record}** "
                     f"(avg margin {s['avg_margin']:+.1f}, latest {s['latest_year']} W{s['latest_week']}: "
                     f"{s['latest_result']} by {abs(s['latest_margin']):.1f})")
        if s['blowouts_win'] or s['blowouts_loss']:
            lines.append(f"- Blowouts: {s['blowouts_win']} W of 25+ FP, {s['blowouts_loss']} L of 25+ FP")
        # Most-recent game line
        recent = sorted(s['all_games'], key=lambda g: (g['year'], g['week']), reverse=True)[:5]
        lines.append('- Last 5 results:')
        for g in recent:
            lines.append(f"  - {g['year']} W{g['week']}: {g['result']} ({g['my_score']:.1f}–{g['opp_score']:.1f}, "
                         f"{'+' if g['margin'] >= 0 else ''}{g['margin']:.1f})")
        lines.append('')
    lines.append(AUTO_END)
    auto_block = '\n'.join(lines)

    if AUTO_START in existing:
        new = re.sub(
            re.escape(AUTO_START) + r'.*?' + re.escape(AUTO_END),
            auto_block, existing, flags=re.DOTALL)
    else:
        new = existing.rstrip() + '\n\n' + auto_block + '\n'
    NOTES.write_text(new, encoding='utf-8')


def main():
    from app import espn_connector as ec
    league = ec._get_league()
    print(f'Pulling {league.year} season matchups for {MY_TEAM_NAME}...')
    rows = fetch_matchup_results(league)
    print(f'  {len(rows)} completed matchups in {league.year}')

    if not rows:
        print('No completed matchups yet this season.')
        return

    summary = summarize_per_opponent(rows)
    for opp, s in summary.items():
        rec = f"{s['wins']}-{s['losses']}" + (f"-{s['ties']}" if s['ties'] else '')
        print(f"  vs {opp}: {rec}  avg_margin={s['avg_margin']:+.1f}  "
              f"latest=W{s['latest_week']} {s['latest_result']}")

    # Save raw + update notes
    with open(OUT / 'opponent_matchup_history.json', 'w', encoding='utf-8') as f:
        json.dump({'rows': rows, 'summary': summary},
                   f, separators=(',', ':'), default=str)
    print(f'\nwrote {OUT / "opponent_matchup_history.json"}')

    update_notes(summary)
    print(f'wrote auto-section in {NOTES}')


if __name__ == '__main__':
    main()
