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

Stage failures are NOT all equal (audit 2026-08-01 item 15). Each STAGES entry
declares `gating`: a gating stage's output is an input to a later stage, so its
failure ABORTS the run rather than letting the models rebuild from yesterday's
substrate. Non-gating tail stages are terminal artifacts — counted, not fatal.
Either kind still exits 1, so the caller's publish gate is unchanged.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'xfp'

# Pipeline stages — (label, script, optional skip-flag name, gating)
#
# GATING (audit 2026-08-01 item 15) is a property of the STAGE, not of loop
# position, so `--from-stage` resumes classify identically. A gating stage's
# output is an INPUT to a later stage: if it fails, its consumers would silently
# read yesterday's file and overwrite the shipped artifacts with projections
# derived from stale inputs (rh3 has no freshness guard on ROLLING_CSV). The
# loop therefore ABORTS on the first gating failure. Non-gating stages are
# terminal artifacts nothing downstream reads inside this process, so a failure
# there is counted and the run continues.
STAGES = [
    # Counting / API pulls (slow, daily-stable)
    ('Pitcher counting stats (MLB API)',         'build_pitcher_counting.py',     'counting',      True),
    # NON-gating: on a failed pull build_position_map refuses to overwrite
    # the cache, so H2/RH3 below read yesterday's positions instead of dying
    # (ADR-0009 edge-sever — positions no longer come from master_hitter).
    ('Player position map (MLB API)',            'build_player_positions.py',     None,            False),
    ('Team strength index (statcast-based)',     'build_team_strength.py',        'team-strength', True),
    # NON-gating (issue #37): nothing inside refresh_all consumes the
    # schedule artifact — it feeds matchup/boom/triangulate OUTSIDE this
    # driver and is refreshed independently at refresh_dashboards step 2.9.
    ('Pitcher schedule (MLB API probables)',     'build_pitcher_schedule.py',     'schedule',      False),
    # Substrate builders
    ('Hitter lineup substrate (statcast)',       'build_hitter_lineup.py',        None,            True),
    ('Reliever role usage (statcast SV/HLD/GF)', 'build_role_usage.py',           None,            True),
    ('Multiyr hitter substrate',                 'build_hitters_multiyr.py',      None,            True),
    ('Multiyr SP substrate',                     'build_sp_multiyr.py',           None,            True),
    ('Multiyr reliever substrate',               'build_relievers_multiyr.py',    None,            True),
    ('Rolling hitter substrate',                 'build_rolling_hitters.py',      None,            True),
    ('Rolling SP substrate',                     'build_rolling_pitchers.py',     None,            True),
    ('Rolling reliever substrate',               'build_rolling_relievers.py',    None,            True),
    # IL split features derive their (year, split_day) grid FROM the rolling
    # substrates, so this stage must run AFTER them (and before its consumers:
    # enrich_rolling_relievers + the models). It used to run at stage 2, which
    # left the IL grid one refresh behind the rolling grid every day — the
    # same shape as the 2026-07-09 dead-join bug. The scorecard's
    # il_grid_coverage tripwire asserts exact coverage.
    ('IL split features',                        'build_il_split_features.py',    'il',            True),
    ('Enrich rolling relievers (team context)',  'enrich_rolling_relievers.py',   None,            True),
    # Models
    ('H2 hitter cross-year lock',                'xfp_h2_lock.py',                None,            True),
    ('RH3 hitter RoS pipeline',                  'xfp_rh3_pipeline.py',           None,            True),
    ('V12 SP cross-year (uses sp_multiyr)',      'xfp_v12_lock.py',               None,            True),
    ('RP3 SP RoS pipeline',                      'xfp_rp3_pipeline.py',           None,            True),
    ('RP-S1 RP cross-year',                      'xfp_rps1_pipeline.py',          None,            True),
    ('RP-RS2 RP RoS pipeline',                   'xfp_rprs2_pipeline.py',         None,            True),
    # Weekly-FP substrate (audit 2026-07-04: existed but was never wired in —
    # consumers read a stale file whenever it wasn't run by hand). Terminal
    # within this process, so non-gating.
    ('Weekly FP substrate',                      'build_weekly_fp_substrate.py',  None,            False),
    # Dashboard — index.html only; a broken page must not withhold the
    # matchup/triangulate/xfp_board builds the caller runs after this script.
    ('Dashboard build',                          'build_index_dashboard.py',      None,            False),
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
    soft_fail_count = 0
    nongating_missing = 0
    aborted = None
    print('=' * 72)
    print('REFRESH ALL — xFP pipeline')
    print('=' * 72)
    for label, script, skip_key, gating in STAGES:
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
            if gating:
                fail_count += 1
                aborted = label
                print(f'  [ABORT] {label} is a REQUIRED stage — later stages '
                      'would consume yesterday\'s substrate')
                break
            # a missing NON-gating stage is a NON-GATING failure — same bucket
            # as a non-gating run failure (it still gates the publish via
            # exit 1, but the summary no longer misreports it as the gating
            # kind, which was the exact distinction item 15 exists to draw —
            # review 2026-08-01)
            soft_fail_count += 1
            nongating_missing += 1
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
            if gating:
                fail_count += 1
                aborted = label
                print(f'  [ABORT] {label} is a REQUIRED stage — later stages '
                      'would consume yesterday\'s substrate and overwrite the '
                      'shipped projections with it. Stopping here.')
                break
            soft_fail_count += 1
            print('  [NON-GATING] terminal artifact — continuing')
        else:
            print(f'  [OK] {dt:.1f}s')
    print('\n' + '=' * 72)
    print(f'DONE — {total_t:.1f}s total, {fail_count} gating failure(s), '
          f'{soft_fail_count} non-gating failure(s)')
    if aborted:
        print(f'ABORTED at: {aborted} — the stages after it did NOT run, so no '
              'artifact was rebuilt from a stale input.')
    print('=' * 72)
    # Propagate failure to the caller (audit 2026-07-04): a total model-rebuild
    # failure must not exit 0 and publish yesterday's numbers as today's. Both
    # failure kinds count — the caller's ok_models gate is unchanged.
    if nongating_missing:
        print(f'  ({nongating_missing} non-gating stage script(s) MISSING — '
              f'counted as non-gating failures; this run exits 1)')
    sys.exit(1 if (fail_count or soft_fail_count) else 0)


if __name__ == '__main__':
    main()
