"""refresh_all.py — single-command pipeline rebuild.

Runs every script in dependency order. Use this after a fresh statcast pull or
when refreshing IL/team data.

Stages (skip flags can opt out):
  --skip-counting       skip MLB API pitcher counting stats fetch (~2 min)
  --skip-il             skip IL transaction fetch
  --skip-schedule       skip MLB API probable pitcher schedule (daily-changing)
  --skip-team-strength  skip team batting/pitching index rebuild

The longest steps are the API pulls (counting + IL). Skip them if you've
already pulled today.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'xfp'

# Pipeline stages — (label, script, optional skip-flag name)
STAGES = [
    # Counting / API pulls (slow, daily-stable)
    ('Pitcher counting stats (MLB API)',         'build_pitcher_counting.py',     'counting'),
    ('IL split features',                        'build_il_split_features.py',    'il'),
    ('Team strength index (statcast-based)',     'build_team_strength.py',        'team-strength'),
    ('Pitcher schedule (MLB API probables)',     'build_pitcher_schedule.py',     'schedule'),
    # Substrate builders
    ('Hitter lineup substrate (statcast)',       'build_hitter_lineup.py',        None),
    ('Reliever role usage (statcast SV/HLD/GF)', 'build_role_usage.py',           None),
    ('Multiyr hitter substrate',                 'build_hitters_multiyr.py',      None),
    ('Multiyr SP substrate',                     'build_sp_multiyr.py',           None),
    ('Multiyr reliever substrate',               'build_relievers_multiyr.py',    None),
    ('Rolling hitter substrate',                 'build_rolling_hitters.py',      None),
    ('Rolling SP substrate',                     'build_rolling_pitchers.py',     None),
    ('Rolling reliever substrate',               'build_rolling_relievers.py',    None),
    ('Enrich rolling relievers (team context)',  'enrich_rolling_relievers.py',   None),
    # Models
    ('H2 hitter cross-year lock',                'xfp_h2_lock.py',                None),
    ('RH3 hitter RoS pipeline',                  'xfp_rh3_pipeline.py',           None),
    ('V12 SP cross-year (uses sp_multiyr)',      'xfp_v12_lock.py',               None),
    ('RP3 SP RoS pipeline',                      'xfp_rp3_pipeline.py',           None),
    ('RP-S1 RP cross-year',                      'xfp_rps1_pipeline.py',          None),
    ('RP-RS2 RP RoS pipeline',                   'xfp_rprs2_pipeline.py',         None),
    # Weekly-FP substrate (audit 2026-07-04: existed but was never wired in —
    # consumers read a stale file whenever it wasn't run by hand)
    ('Weekly FP substrate',                      'build_weekly_fp_substrate.py',  None),
    # Dashboard
    ('Dashboard build',                          'build_v11_dashboard_v2.py',     None),
]


def parse_args():
    p = argparse.ArgumentParser(description='Refresh full xFP pipeline')
    p.add_argument('--skip-counting',     action='store_true', help='skip MLB API pitcher counting fetch')
    p.add_argument('--skip-il',           action='store_true', help='skip IL transactions')
    p.add_argument('--skip-team-strength',action='store_true', help='skip team-strength rebuild')
    p.add_argument('--skip-schedule',     action='store_true', help='skip MLB API schedule fetch')
    p.add_argument('--from-stage',        type=str, default=None,
                    help='start at stage matching this substring (skip earlier stages)')
    p.add_argument('--dry-run',           action='store_true', help='print what would run, do nothing')
    return p.parse_args()


def main():
    args = parse_args()
    skip_flags = {
        'counting': args.skip_counting,
        'il': args.skip_il,
        'team-strength': args.skip_team_strength,
        'schedule': args.skip_schedule,
    }
    started = False
    if args.from_stage is None:
        started = True
    total_t = 0.0
    fail_count = 0
    print('=' * 72)
    print('REFRESH ALL — xFP pipeline')
    print('=' * 72)
    for label, script, skip_key in STAGES:
        if not started:
            if args.from_stage.lower() in label.lower():
                started = True
            else:
                print(f'  [SKIP-START] {label}')
                continue
        if skip_key and skip_flags.get(skip_key):
            print(f'  [SKIP-FLAG] {label}  (--skip-{skip_key})')
            continue
        path = SCRIPTS / script
        if not path.exists():
            print(f'  [MISSING]  {label}  ({script})')
            fail_count += 1
            continue
        print(f'\n>>> {label}  ({script})')
        if args.dry_run:
            continue
        t0 = time.time()
        proc = subprocess.run(
            ['python', '-X', 'utf8', str(path)],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        dt = time.time() - t0
        total_t += dt
        # Print last 5 lines of output for confirmation
        for line in (proc.stdout.splitlines()[-5:] or ['(no stdout)']):
            print(f'    {line}')
        if proc.returncode != 0:
            print(f'  [FAILED] exit={proc.returncode}, stderr tail:')
            for line in proc.stderr.splitlines()[-10:]:
                print(f'    {line}')
            fail_count += 1
        else:
            print(f'  [OK] {dt:.1f}s')
    print('\n' + '=' * 72)
    print(f'DONE — {total_t:.1f}s total, {fail_count} failure(s)')
    print('=' * 72)
    # Propagate failure to the caller (audit 2026-07-04): a total model-rebuild
    # failure must not exit 0 and publish yesterday's numbers as today's.
    sys.exit(1 if fail_count else 0)


if __name__ == '__main__':
    main()
