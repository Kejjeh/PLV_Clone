"""eligibility_watch.py — diff ESPN eligibleSlots vs prior snapshot.

A player gaining new position eligibility opens up flex options. E.g.,
Donovan getting OF eligibility could let you start him at OF5 while
freeing UTIL for another bat.

Method:
  1. Snapshot per-player eligibleSlots to data/research/eligibility_snapshots/{date}.json
  2. Compare against most recent prior snapshot
  3. Report: players who gained any eligibility, players who lost any (rare)

Run weekly. Diff resets each time a new snapshot is saved.

Output:
  data/outputs/eligibility_changes.json
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import sys

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
SNAPS = ROOT / 'data' / 'research' / 'eligibility_snapshots'


def main():
    SNAPS.mkdir(parents=True, exist_ok=True)
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()

    today_snap = {}
    for t in league.teams:
        for p in t.roster:
            elig = list(getattr(p, 'eligibleSlots', None) or [])
            today_snap[p.name] = {
                'eligible': elig, 'team': t.team_name, 'pos': p.position,
            }

    today = date.today().isoformat()
    today_path = SNAPS / f'{today}.json'

    # Find most recent prior snapshot
    prior_paths = sorted(p for p in SNAPS.glob('*.json') if p.stem < today)
    prior_snap = {}
    if prior_paths:
        prior_path = prior_paths[-1]
        prior_snap = json.loads(prior_path.read_text(encoding='utf-8'))
        print(f'Comparing today vs {prior_path.stem}')
    else:
        print('No prior snapshot — saving baseline only')

    changes = []
    for name, today_info in today_snap.items():
        if name not in prior_snap:
            changes.append({'name': name, 'change': 'new_to_league',
                             'eligible_now': today_info['eligible']})
            continue
        prior_elig = set(prior_snap[name]['eligible'])
        today_elig = set(today_info['eligible'])
        gained = today_elig - prior_elig
        lost = prior_elig - today_elig
        if gained or lost:
            changes.append({
                'name': name,
                'team': today_info.get('team'),
                'gained_eligibilities': sorted(gained),
                'lost_eligibilities': sorted(lost),
                'eligible_now': today_info['eligible'],
            })

    # Save today's snapshot
    with open(today_path, 'w', encoding='utf-8') as f:
        json.dump(today_snap, f, separators=(',', ':'))

    print(f'\nFound {len(changes)} eligibility changes since prior snapshot.')
    for c in changes[:20]:
        gn = ', '.join(c.get('gained_eligibilities', [])) or 'none'
        ln = ', '.join(c.get('lost_eligibilities', [])) or 'none'
        team = c.get('team') or '?'
        print(f'  {c["name"]:<25s} ({team}): gained=[{gn}]  lost=[{ln}]')

    with open(OUT / 'eligibility_changes.json', 'w', encoding='utf-8') as f:
        json.dump({'as_of': today, 'changes': changes}, f,
                   separators=(',', ':'), default=str)
    print(f'\nwrote eligibility_changes.json + saved snapshot {today_path}')


if __name__ == '__main__':
    main()
