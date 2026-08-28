"""log_roster_decisions.py — daily-refresh step.

Runs `triangulate_player()` for every player on the user's roster (and
optionally any extra names passed on the command line) so that each
call emits a DecisionRecord via the env-gated logging hook in
`scripts.xfp.lib.triangulate_core.triangulate_player`.

This script does NOT set PLV_LOG_DECISIONS itself — the caller
(refresh_dashboards.py) sets the env var so the gate is opt-in and
scoped to the production refresh.

Usage:
    PLV_LOG_DECISIONS=1 python -X utf8 scripts/xfp/log_roster_decisions.py
    PLV_LOG_DECISIONS=1 python -X utf8 scripts/xfp/log_roster_decisions.py "Aaron Judge" "Reid Detmers"
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

if sys.platform == 'win32' and sys.stdout is sys.__stdout__:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.xfp.lib.triangulate_core import triangulate_player  # noqa: E402


def _my_roster_names() -> list[str]:
    """Return live roster display names. Fail-soft to empty list."""
    try:
        from plv_clone.league_state import LeagueState
        df = LeagueState().my_roster_with_injuries()
        if df is None or df.empty:
            return []
        if 'name' in df.columns:
            return [str(n) for n in df['name'].dropna().tolist()]
        if 'player_name' in df.columns:
            return [str(n) for n in df['player_name'].dropna().tolist()]
        return []
    except Exception as exc:
        print(f'  ⚠ could not fetch roster: {exc}', file=sys.stderr)
        return []


def main(extras: list[str]) -> int:
    if os.environ.get('PLV_LOG_DECISIONS') != '1':
        print('  PLV_LOG_DECISIONS not set; this is a no-op.', file=sys.stderr)
        # Still walk to confirm wiring — but no records will be written.
    roster = _my_roster_names()
    names = list(dict.fromkeys(roster + list(extras)))  # dedup preserve-order
    if not names:
        print('  no roster names resolved; nothing to log.')
        return 0
    n_ok = 0
    n_fail = 0
    for nm in names:
        try:
            r = triangulate_player(nm)
            if r is not None:
                n_ok += 1
            else:
                n_fail += 1
        except Exception as exc:
            print(f'  ⚠ triangulate failed for {nm!r}: {exc}', file=sys.stderr)
            n_fail += 1
    print(f'  logged {n_ok}/{len(names)} decisions ({n_fail} failures)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
