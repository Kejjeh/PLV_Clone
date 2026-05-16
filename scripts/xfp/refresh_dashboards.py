"""refresh_dashboards.py — one-command full refresh.

Steps:
  1. Pull latest statcast (lag=1 day, gets through yesterday)
  2. Rebuild all xFP models (rh3, rp3, rprs2, h2, v12, rps1)
  3. Regenerate live_dashboard.html (today's live stats snapshot)
  4. Regenerate matchup.html (weekly H2H projection)
  5. Copy both to xfp-model/docs/
  6. Commit + push xfp-model to GitHub Pages

Usage:
  python scripts/xfp/refresh_dashboards.py            # full refresh + push
  python scripts/xfp/refresh_dashboards.py --no-push  # build locally only
  python scripts/xfp/refresh_dashboards.py --no-models  # skip model rebuild (fast)
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path('c:/Users/Joshua/plv_clone')
XFP_MODEL = ROOT / 'xfp-model'
SCRIPTS = ROOT / 'scripts' / 'xfp'


def run(label, cmd, cwd=None, timeout=900):
    print(f'\n{"="*70}\n  {label}\n{"="*70}', flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=cwd or ROOT, shell=True, timeout=timeout)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f'  ⚠ {label} returned exit code {result.returncode} after {elapsed:.1f}s')
        return False
    print(f'  ✓ {label} done in {elapsed:.1f}s')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-push', action='store_true',
                    help='skip git commit/push at end')
    ap.add_argument('--no-models', action='store_true',
                    help='skip full model rebuild (use existing pkls)')
    ap.add_argument('--skip-statcast', action='store_true',
                    help='skip statcast refresh (use existing cache)')
    args = ap.parse_args()

    print(f'REFRESH DASHBOARDS — {datetime.now().strftime("%Y-%m-%d %H:%M")}')

    if not args.skip_statcast:
        run('1. Refresh statcast (yesterday\'s games)',
            'python -X utf8 scripts/xfp/refresh_xfp_statcast.py --year 2026 --lag 1')

    if not args.no_models:
        ok = run('2. Rebuild xFP models', 'python -X utf8 scripts/xfp/refresh_all.py',
                  timeout=1800)
        if not ok: print('  → continuing despite model rebuild issue')

    run('3. Build live_dashboard.html (snapshot)',
        'python -X utf8 scripts/xfp/live_monitor.py --dashboard')

    run('4. Build matchup.html (weekly H2H)',
        'python -X utf8 scripts/xfp/build_matchup_dashboard.py')

    if not args.no_push:
        if not XFP_MODEL.exists():
            print(f'\n  ⚠ xfp-model repo not found at {XFP_MODEL}')
            return
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        commit_cmd = (
            'git add docs/matchup.html docs/live_dashboard.html && '
            f'git commit -m "refresh: {timestamp} dashboards" --allow-empty'
        )
        run('5. Commit xfp-model dashboards', commit_cmd, cwd=XFP_MODEL)
        run('6. Push to GitHub Pages',
            'git push origin main', cwd=XFP_MODEL)

    print(f'\n{"="*70}\n  ALL DONE — {datetime.now().strftime("%Y-%m-%d %H:%M")}\n{"="*70}')
    print(f'  Live: https://kejjeh.github.io/xfp-model/live_dashboard.html')
    print(f'  Matchup: https://kejjeh.github.io/xfp-model/matchup.html')


if __name__ == '__main__':
    main()
