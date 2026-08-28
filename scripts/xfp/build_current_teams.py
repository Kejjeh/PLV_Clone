"""build_current_teams — refresh the mlbam->club map and repoint the outputs.

Refresh step 2c — immediately AFTER the models write the projection CSVs and
before anything reads them. Running it earlier would simply be overwritten by
step 2.

The models derive `team` from historical Statcast, so a traded player keeps his
old club until his new one accumulates enough history. After the 2026 deadline
that left 85 players stale across rh3 and the volume models, with José Soriano
reading LAA while starting for Toronto. Park factors, schedule joins, opponent
context and every bullpen lens key on that column.

Two passes: pull all 30 40-man rosters into data/reference/current_teams.json,
then rewrite `team` in the four projection CSVs that carry it (rp3 and rprs2
have no team column). Both passes are idempotent.

Non-gating: every failure path prints and exits 0. A stale map still beats no
map — the previous file is kept and reused if the pull fails.
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, 'src')

import datetime  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from scripts.xfp.lib.team_override import (  # noqa: E402
    DEFAULT_MAP, MODEL_TEAM_CODES, apply_team_override, load_map,
)

# (csv, mlbam column). rp3/rprs2 deliberately absent — no team column.
TARGETS = [
    ('data/outputs/xfp_rh3_projections.csv', 'batter'),
    ('data/outputs/xfp_volume_projections.csv', 'mlbam_id'),
    ('data/outputs/xfp_sp_volume_projections.csv', 'mlbam_id'),
    ('data/outputs/xfp_rp_volume_projections.csv', 'mlbam_id'),
]


def pull_rosters() -> dict:
    """40-man for all 30 clubs. Returns {} on any failure (caller keeps the
    existing map rather than writing a partial one)."""
    try:
        tj = requests.get('https://statsapi.mlb.com/api/v1/teams',
                          params={'sportId': 1}, timeout=45).json()
    except Exception as exc:
        print(f'  team list fetch failed ({exc})')
        return {}
    clubs = [t for t in tj.get('teams', []) if t.get('active', True)]
    players, bad = {}, 0
    for t in clubs:
        abbr = str(t.get('abbreviation') or '').upper()
        if abbr not in MODEL_TEAM_CODES:
            bad += 1
            continue
        try:
            r = requests.get(
                f"https://statsapi.mlb.com/api/v1/teams/{t['id']}/roster",
                params={'rosterType': '40Man'}, timeout=45).json()
        except Exception as exc:
            print(f'  roster fetch failed for {abbr} ({exc}) — skipping club')
            continue
        for e in r.get('roster', []):
            p = e.get('person') or {}
            if not p.get('id'):
                continue
            players[str(p['id'])] = {
                'team': t.get('name'), 'abbr': abbr,
                'name': p.get('fullName'),
                'pos': (e.get('position') or {}).get('abbreviation'),
            }
    if bad:
        print(f'  {bad} club abbreviation(s) outside the model vocabulary — skipped')
    if len(players) < 800:
        print(f'  only {len(players)} players pulled (expected ~1200+) — '
              f'treating as a failed pull, keeping the existing map')
        return {}
    return players


def main() -> int:
    today = datetime.date.today()
    players = pull_rosters()
    if players:
        payload = {'as_of': today.isoformat(),
                   'source': 'statsapi 40Man rosters',
                   'players': players}
        try:
            DEFAULT_MAP.parent.mkdir(parents=True, exist_ok=True)
            tmp = DEFAULT_MAP.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                           encoding='utf-8')
            tmp.replace(DEFAULT_MAP)
            print(f'  wrote {DEFAULT_MAP} — {len(players)} players, as_of {today}')
        except Exception as exc:
            print(f'  map write failed ({exc}) — keeping previous map')

    tmap = load_map()
    print(f'  {tmap.label(today)}')
    if tmap.empty:
        print('  no map available — team override is a NO-OP tonight '
              '(non-gating; NOT an all-clear)')
        return 0

    total = 0
    for path, idcol in TARGETS:
        p = Path(path)
        if not p.exists():
            print(f'  {p.name}: missing — skipped')
            continue
        try:
            df = pd.read_csv(p)
            out, n, unknown = apply_team_override(df, tmap, mlbam_col=idcol)
        except KeyError as exc:
            print(f'  {p.name}: {exc} — SKIPPED (schema changed?)')
            continue
        except Exception as exc:
            print(f'  {p.name}: override failed ({exc}) — skipped')
            continue
        if n:
            try:
                out.to_csv(p, index=False)
            except Exception as exc:
                print(f'  {p.name}: write failed ({exc}) — left unchanged')
                continue
        total += n
        print(f'  {p.name}: {n} team(s) corrected, {unknown} not on any 40-man')
    print(f'  team override: {total} row(s) repointed across '
          f'{len(TARGETS)} projection file(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
