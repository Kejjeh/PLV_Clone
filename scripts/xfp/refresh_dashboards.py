"""refresh_dashboards.py — one-command full refresh.

Steps:
  1. Pull latest statcast (lag=1 day, gets through yesterday)
  2. Rebuild all xFP models (rh3, rp3, rprs2, h2, v12, rps1)
     — also mirrors xfp_dashboard.html → xfp-model/docs/index.html
  3. Regenerate live_dashboard.html (mirrored to xfp-model/docs/)
  4. Regenerate matchup.html (mirrored to xfp-model/docs/)
  5. Commit the three mirrored dashboards in xfp-model
  6. Push xfp-model to GitHub Pages

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

    run('1b. Build batter rolling-feature cache',
        'python -X utf8 scripts/xfp/build_batter_rolling_features.py')

    # Snapshot rolling caches — feed the Player-Profiles intra-season trajectory
    # view. Weekly cadence (2024-2026), monthly for older years (cost control).
    # Each ~30-90s. Failure here only affects the Profiles trajectory dots, not
    # the live ranker, so keep going.
    run('1c. Build hitter rolling snapshot cache (weekly cadence 2024-2026)',
        'python -X utf8 scripts/xfp/build_rolling_hitters.py',
        timeout=300)
    run('1d. Build SP rolling snapshot cache (weekly cadence 2024-2026)',
        'python -X utf8 scripts/xfp/build_rolling_pitchers.py',
        timeout=300)
    run('1e. Build RP rolling snapshot cache (weekly cadence 2024-2026)',
        'python -X utf8 scripts/xfp/build_rolling_relievers.py',
        timeout=300)

    if not args.no_models:
        ok = run('2. Rebuild xFP models', 'python -X utf8 scripts/xfp/refresh_all.py',
                  timeout=1800)
        if not ok: print('  → continuing despite model rebuild issue')

    run('2b. Build name-resolution cache',
        'python -X utf8 scripts/xfp/build_name_resolution_cache.py',
        timeout=120)

    run('2.5. Build SP/hitter upgrade alerts',
        'python -X utf8 scripts/xfp/build_sp_alerts.py',
        timeout=120)

    run('2.6. Build SP archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_sp_archetypes.py',
        timeout=120)

    run('2.7. Build hitter archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_hitter_archetypes.py',
        timeout=120)

    run('2.75. Derive RP damage/GB columns from statcast (one-time-ish)',
        'python -X utf8 scripts/xfp/build_rp_damage_gb_from_statcast.py',
        timeout=300)

    # NOTE: FG RP leverage cache (gmLI / pLI / Shutdowns / Meltdowns) is
    # browser-driven via undetected-chromedriver and NOT wired into the daily
    # chain — same pattern as pull_fg_undetected.py. Re-run manually after
    # mid-season closer changes:
    #   python -X utf8 scripts/xfp/pull_fg_rp_leverage.py
    # Output: data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv
    # build_rp_archetypes.py reads it directly if present (drives leverage_tier).

    run('2.8. Build RP archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_rp_archetypes.py',
        timeout=120)

    run('3. Build live_dashboard.html (snapshot)',
        'python -X utf8 scripts/xfp/live_monitor.py --dashboard')

    run('4. Build matchup.html (weekly H2H)',
        'python -X utf8 scripts/xfp/build_matchup_dashboard.py')

    # Fail-closed: if player_profiles build fails, skip publish to avoid stale docs.
    ok_profiles = run('4.5. Build player_profiles.html (archetype browser)',
                      'python -X utf8 scripts/xfp/build_player_profiles_dashboard.py',
                      timeout=120)

    if not args.no_push:
        if not ok_profiles:
            print('\n  ⚠ player_profiles build failed — skipping publish to avoid stale docs')
            return
        if not XFP_MODEL.exists():
            print(f'\n  ⚠ xfp-model repo not found at {XFP_MODEL}')
            return
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        commit_cmd = (
            'git add docs/index.html docs/matchup.html docs/live_dashboard.html docs/player_profiles.html && '
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
