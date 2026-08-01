"""refresh_dashboards.py — one-command full refresh.

Step numbering is decimal-inserted so new work slots between existing steps
without renumbering the world; when a step IS renumbered the old number is kept
in its label (e.g. '4.91 (was 4.09)'). `run()` never raises — a timeout kills
the step's whole process tree, and a timeout or nonzero exit prints a warning
and the pipeline continues. Only step 2 (model rebuild) gates: if it fails, the
git publish steps are skipped AND .cache/PUBLISH_GATED is written so the
nightly workflow can mark its commit (the process still exits 0 on purpose —
see publish_gated_marker()).

Bands, in execution order:
  0.5-0.8   persistence/snapshots (rosters, transactions, FA snapshot, FG)
  1-1.6     statcast pull, gf bridge (1.05), boxscore bridge (1.5), SB gamelog
  1.65-1.98 feature/rolling caches, schedule + bx priors, velo & bat-speed
            trending, plv cli update (several mtime-gated)
  2-2.85    MODEL REBUILD (gating) + IL patch, name-resolution cache, alerts,
            archetype panels, PL cache
  3-3.65    live dashboard, calibration report/panel
  4-4.4     matchup.html, injury cache, triangulate chain, boom stacks,
            console payload, index re-emit (4.31 — index.html must be built
            AFTER its decision payload), player profiles, xfp_board
  4.8-4.93  history panels (boom stack, PL rank), volume pipelines
  4.94-4.97 snapshot logger + decision log/panel/settle, FG RoS, IL txns,
            model scorecard, verdict scorecard (some Monday-only)
  5-7       git commit + push xfp-model (gated on step 2), PL freshness notice

Docstring last reconciled with main() 2026-07-29 (it had described a long-since
superseded 6-step pipeline).

Usage:
  python scripts/xfp/refresh_dashboards.py            # full refresh + push
  python scripts/xfp/refresh_dashboards.py --no-push  # build locally only
  python scripts/xfp/refresh_dashboards.py --no-models  # skip model rebuild (fast)
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from plv_clone.paths import ROOT
XFP_MODEL = ROOT / 'xfp-model'
SCRIPTS = ROOT / 'scripts' / 'xfp'


# Every xfp-model/docs artifact the daily refresh publishes. Tests assert this
# list matches the tracked pages so a new dashboard can't silently go stale
# (the triangulate.html incident, audit 2026-07-04).
PUBLISH_PAGES_CORE = (
    'docs/index.html', 'docs/matchup.html', 'docs/live_dashboard.html',
    'docs/triangulate.html', 'docs/xfp_board.html',
)
PUBLISH_PAGES_PROFILES = ('docs/player_profiles.html', 'docs/player_profiles_data.js')


def season_year():
    """The season the nightly INGESTION steps target.

    Was a literal `2026` in three driver commands (audit 2026-08-01 item 42).
    Two of the three scripts already default to the current calendar year, so
    the literal was redundant today and wrong on 2027-01-01 — the pull would
    keep growing the OLD season's parquet while reporting success. The third
    (build_batter_sb_gamelog) defaults to ALL years, so it needs a computed
    value rather than a deletion.

    PLV_SEASON_YEAR overrides it, so an off-season backfill can pin the season
    without editing the driver.
    """
    override = os.environ.get('PLV_SEASON_YEAR')
    return int(override) if override else datetime.now().year


def publish_gated_marker():
    """Path of the file that records "the last publishing run was GATED".

    The gate used to announce itself only by printing and returning, and main()
    is invoked bare — so the process still exited 0, the nightly workflow saw a
    green job, and its `git add data` step committed the stale-projection CSVs
    regardless (audit 2026-08-01 item 16). The exit code is deliberately left
    alone: daily-refresh.yml's commit step has no `if:`, so a non-zero exit
    would drop a day of ESPN transaction/roster archival that rolls off the API
    in 7-14 days and can never be recovered. This marker gives the workflow
    something to READ instead, mirroring the SCORECARD_ALERT idiom.

    Lives under .cache/ (already gitignored) rather than data/outputs/, because
    the workflow's `git add data` would otherwise commit the marker on a gated
    night and stage its deletion the next clean night. The signal is local to
    one run in one working tree; it has no business in the history.
    """
    return ROOT / '.cache' / 'PUBLISH_GATED'


def _kill_tree(proc):
    """Kill `proc` AND every descendant it spawned.

    shell=True means proc is the shell, not the worker — killing it alone
    leaves the worker running. Windows walks the tree with `taskkill /T`;
    posix uses the process group created by start_new_session. Both paths are
    best-effort: a race where the tree exits between the wait() timeout and the
    kill is a resolved timeout, not an error to raise into the pipeline.
    """
    try:
        if os.name == 'nt':
            subprocess.run(f'taskkill /T /F /PID {proc.pid}', shell=True,
                           capture_output=True)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception as e:      # never let cleanup abort the pipeline
        print(f'  ! could not kill the timed-out process tree ({e})')
    try:
        proc.wait(timeout=30)
    except Exception:
        pass


def run(label, cmd, cwd=None, timeout=900, env=None):
    """Run a subprocess. `env` is an optional dict of EXTRA env vars merged
    on top of os.environ for THIS step only (scoped — does not leak).

    NOTE (audit 2026-07-19 item 16): relying on the implicit 900s default is
    BANNED for publish-critical steps — pass timeout= explicitly there."""
    print(f'\n{"="*70}\n  {label}\n{"="*70}', flush=True)
    t0 = time.time()
    proc_env = None
    if env:
        proc_env = {**os.environ, **env}
    # Popen + wait(timeout) rather than subprocess.run(timeout=) (audit
    # 2026-08-01 item 17): run()'s timeout path kills only the DIRECT child,
    # which under shell=True is cmd.exe. The python worker it spawned was
    # orphaned and kept WRITING into the same data/outputs files the next step
    # was about to read, while the log said "continuing with next step".
    # Kill the whole tree instead. Only the already-abandoned path changes.
    proc = subprocess.Popen(
        cmd, cwd=cwd or ROOT, shell=True, env=proc_env,
        **({} if os.name == 'nt' else {'start_new_session': True}),
    )
    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        print(f'  ⚠ {label} TIMED OUT after {timeout}s — process tree killed, '
              'continuing with next step')
        return False
    elapsed = time.time() - t0
    if returncode != 0:
        print(f'  ⚠ {label} returned exit code {returncode} after {elapsed:.1f}s')
        return False
    print(f'  ✓ {label} done in {elapsed:.1f}s')
    return True


def main():
    # ESPN snapshot mode for every child step (audit 2026-07-19 F3): one live
    # free_agents(size=2000) pull + one injury-detail sweep feed the whole
    # refresh via short-TTL disk caches (see plv_clone/espn.py and
    # league_state.injury_details). Interactive/skill runs never set this.
    os.environ['PLV_ESPN_SNAPSHOT'] = '1'
    os.environ.setdefault('PLV_ESPN_SNAPSHOT_TTL_MIN', '240')
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-push', action='store_true',
                    help='skip git commit/push at end')
    ap.add_argument('--no-models', action='store_true',
                    help='skip full model rebuild (use existing pkls)')
    ap.add_argument('--skip-statcast', action='store_true',
                    help='skip statcast refresh (use existing cache)')
    args = ap.parse_args()

    print(f'REFRESH DASHBOARDS — {datetime.now().strftime("%Y-%m-%d %H:%M")}')

    # 0.5/0.6: Persist daily roster snapshot + transactions log. Both fail-soft —
    # archival only, no downstream consumer in the current refresh chain.
    # Combined they let us reconstruct roster state at any point in any future
    # closed period (ESPN's recent_activity is rolling ~7-14 days, so daily
    # runs are required to capture transactions before they fall off).
    ok_rost = run('0.5. Persist daily roster snapshot (matchup_rosters_history)',
                  'python -X utf8 scripts/xfp/persist_matchup_rosters.py',
                  timeout=180)
    if not ok_rost:
        print('  ⚠ roster snapshot failed — continuing (archival only)')

    ok_tx = run('0.6. Persist daily transactions log (transactions_history)',
                'python -X utf8 scripts/xfp/persist_transactions.py',
                timeout=180)
    if not ok_tx:
        print('  ⚠ transactions persist failed — continuing (archival only)')

    # 0.65: Reconcile executed transactions against the dpwin surface —
    # stamps executed_at on open v3 decision records and auto-creates v3
    # records (with the passed-on alternative) for unlogged moves. Must run
    # right after 0.6 so the ledger attributes today's moves while they are
    # inside the ATTRIBUTION_DAYS window. Fail-soft + non-gating, mirroring
    # settle_decisions (4.94c).
    ok_reconcile = run(
        '0.65. Reconcile executed moves x dpwin surface (decision ledger)',
        'python -X utf8 scripts/xfp/reconcile_decisions.py',
        timeout=180)
    if not ok_reconcile:
        print('  ⚠ decision reconcile failed — continuing (non-gating; '
              'the ledger catches up on the next run)')

    # 0.7: Build FA-pool snapshot (RP-only, Phase 2). Powers the live_marginal
    # line on RP triangulate cards. Fail-soft — if snapshot is stale/missing,
    # blend_score.py emits live_marginal=None with a note.
    ok_fa = run('0.7. Build FA-pool snapshot (RP)',
                'python -X utf8 scripts/xfp/build_fa_snapshot.py',
                timeout=180)
    if not ok_fa:
        print('  ⚠ FA snapshot failed — RP cards will show live_marginal=unavailable')

    # 0.8: Refresh the FanGraphs 2026 snapshot (Stuff+/K%/BB%/GS) that powers the
    # stuff board, floor model, and sustainability. Fail-soft: it's a Chrome scrape
    # that can flake, and sp_stuff_model now (a) reconciles GS from the daily
    # boxscore so role classification is immune to FG staleness, and (b) prints a
    # loud STALE warning past 5 days. This step keeps the RATE stats current.
    # (Root cause of the 2026-07-08 Jax RP-mislabel: this file sat un-refreshed
    # from 06-06 because it lived only as a manual _oneoff.)
    ok_fg = run('0.8. Refresh FanGraphs 2026 snapshot (Stuff+/GS) [fail-soft]',
                'python -X utf8 scripts/_oneoff/fg_2026_current.py',
                timeout=240)
    if not ok_fg:
        print('  ⚠ FG snapshot refresh failed — stuff/floor keep prior rate stats; '
              'role classification still live via boxscore GS reconciliation')

    if not args.skip_statcast:
        # explicit timeout (audit 2026-07-19 item 16): the implicit default is
        # banned for publish-critical steps — same effective value (900s).
        # No season literal (item 42): refresh_xfp_statcast.py's --year already
        # defaults to date.today().year, so the pull follows the calendar.
        run('1. Refresh statcast (yesterday\'s games)',
            'python -X utf8 scripts/xfp/refresh_xfp_statcast.py --lag 1',
            timeout=900)

    # 1.05. Statcast gf bridge — fills the SAME 1-2 day Statcast lag at PITCH level
    # (the boxscore bridge only fixes FP actuals; this makes the MODELS same-day
    # current). Pulls Savant's per-game feed for the days the pybaseball CSV hasn't
    # finalized, maps pitches into the statcast schema (provisional), reconstructs
    # xwOBA-on-contact. Runs BEFORE the rolling builders so they see yesterday.
    # Provisional rows are overwritten by the canonical CSV on a later pull. Fail-soft.
    if not args.skip_statcast:
        ok_gf = run('1.05. Statcast gf bridge (fills lag at pitch level)',
                    'python -X utf8 scripts/xfp/build_statcast_gf_bridge.py',
                    timeout=300)
        if not ok_gf:
            print('  ⚠ statcast gf bridge failed — models may lag 1 day (boom/bust still current)')

    # 1.5. Boxscore bridge — fills the 1-2 day Statcast lag.
    # MLB Stats API boxscores are real-time (available minutes after game end)
    # while Savant/pybaseball pitch-level data lags 1-2 days. This step pulls
    # all final game boxscores for yesterday, computes BrownU FP from counting
    # stats (K + IP*3.3 − H − 2*ER − BB − HBP for SP/RP; R+TB+RBI+BB+HBP+SB−K
    # for hitters), and writes to boxscore_pitchers.parquet + boxscore_hitters.parquet.
    # Idempotent — skips game_pks already cached. Fail-soft.
    ok_bs = run('1.5. Bridge boxscores (fills Statcast lag)',
                'python -X utf8 scripts/xfp/refresh_boxscores.py',
                timeout=120)
    if not ok_bs:
        print('  ⚠ boxscore bridge failed — recent actuals may lag 1-2 days')

    # 1.6. As-of SB gamelog refresh (sb_asof_feature_2026-07-10.md): the rh3
    # feature sb_per_pa_to_sh went LIVE on the MLB Stats API gameLog source.
    # Completed years are immutable; the 2026 cache goes stale as the season
    # progresses, so re-pull + assemble (~5-6 min) BEFORE the rolling-hitters
    # rebuild (step 1.75 on the --no-models path; inside refresh_all in step 2)
    # so the rolling cache sees yesterday's steals. Fail-soft: on failure the
    # rolling builder carries the LAST PULLED CUTOFF forward — leakage-safe,
    # but recent SBs won't be credited until the next successful pull.
    # --years MUST name the season explicitly here (item 42): the script's own
    # default is None = EVERY year in the batter-years table (2018..current),
    # so dropping the flag would re-pull ~9 immutable seasons and blow the
    # 900s timeout. Computed, not literal.
    ok_sb = run(f'1.6. Refresh as-of SB gamelog ({season_year()} pull + assemble)',
                'python -X utf8 scripts/xfp/build_batter_sb_gamelog.py pull '
                f'--years {season_year()} --force && '
                'python -X utf8 scripts/xfp/build_batter_sb_gamelog.py assemble',
                timeout=900)
    if not ok_sb:
        print('  ⚠ as-of SB refresh failed — rolling builder carries the last '
              'pulled SB cutoff forward (leakage-safe, but sb_per_pa_to_sh '
              'will lag until the next successful pull)')

    # Bat-speed daily accumulator (2026-07-29). Bat speed is the ONLY validated
    # forward hitter process metric, but until now it was readable only as a
    # YoY delta — the season-aggregate artifacts carry no history and
    # bat_speed_trending_2026.csv is overwritten nightly. This appends one row
    # per (batter, day) so an IN-SEASON bat-speed study becomes possible (the
    # sole declared re-open condition for the closed in-season-delta family).
    # Derived from the pitch-level xfp_cache parquets, so it inherits the gf
    # bridge's same-day currency and needs no extra network call.
    ok_batspeed = run('1.65. Append bat-speed daily accumulator',
                      'python -X utf8 scripts/xfp/build_bat_speed_daily.py --days 10',
                      timeout=900)
    if not ok_batspeed:
        print('  ⚠ bat-speed accumulator failed — store keeps its last good day; '
              'idempotent on (batter, game_date) so the next run backfills the '
              'gap (non-gating)')

    run('1.7 (was 1b). Build batter rolling-feature cache',
        'python -X utf8 scripts/xfp/build_batter_rolling_features.py')

    # Snapshot rolling caches — feed the Player-Profiles intra-season trajectory
    # view. AUDIT 2026-07-04 (-343s/day, 28% of the ritual): these write the
    # SAME rolling_*_2018_2026.csv files refresh_all's rolling stages rebuild
    # minutes later with no consumer in between — so run them here ONLY when
    # the model rebuild is being skipped (--no-models fast path).
    if args.no_models:
        run('1.75 (was 1c). Build hitter rolling snapshot cache (weekly cadence 2024-2026)',
            'python -X utf8 scripts/xfp/build_rolling_hitters.py',
            timeout=300)
        run('1.8 (was 1d). Build SP rolling snapshot cache (weekly cadence 2024-2026)',
            'python -X utf8 scripts/xfp/build_rolling_pitchers.py',
            timeout=300)
        run('1.85 (was 1e). Build RP rolling snapshot cache (weekly cadence 2024-2026)',
            'python -X utf8 scripts/xfp/build_rolling_relievers.py',
            timeout=300)

    # 1.9. RoS schedule-strength caches (audit 2026-07-04): these VALIDATED
    # features (ros_opp_xwoba_weighted, rp3 +0.0145) froze at split 58 for ~6
    # weeks and silently constant-filled 100% of projection rows. Rebuild the
    # in-season grid daily, BEFORE the model rebuild consumes them. Fail-soft:
    # the pipelines' >50%-NaN guard (rh3/rp3) now catches a re-freeze loudly.
    ok_ros = run('1.9. Rebuild RoS schedule-strength caches',
                 'python -X utf8 scripts/xfp/build_ros_schedule_features.py && '
                 'python -X utf8 scripts/xfp/build_ros_opp_sp_xwoba_per_hitter.py',
                 timeout=600)
    if not ok_ros:
        print('  ⚠ ros schedule-strength rebuild failed — pipelines may trip the NaN guard')

    # 1.95. Box-score-era bx priors (bx_ensemble_2026-07-10.md): bx_prior_h is
    # a PROMOTED rh3 feature (B1 PASS + live-SB pre-flight PROMOTE 2026-07-10),
    # so this must run BEFORE the rh3 rebuild in step 2. The cache is built
    # from COMPLETED T-1 seasons, so it is static within a season — the step
    # is effectively annual (season rollover / boxscore-era panel rebuild).
    # mtime gate: skip when the CSV exists and is <30 days old; the rebuild is
    # cheap and idempotent, so the gate is purely a time saver. Fail-soft: rh3
    # raises loudly on a missing/stale cache (>50%-current-year-NaN guard).
    _bx_csv = ROOT / 'data' / 'research' / 'xfp_cache' / 'bx_priors_2018_2026.csv'
    _bx_fresh = (_bx_csv.exists()
                 and (time.time() - _bx_csv.stat().st_mtime) < 30 * 86400)
    if _bx_fresh:
        print('\n  1.95. bx priors cache fresh (<30 days) — skip rebuild')
    else:
        ok_bx = run('1.95. Build bx box-score priors (annual-ish, mtime-gated)',
                    'python -X utf8 scripts/xfp/build_bx_priors.py',
                    timeout=900)
        if not ok_bx:
            print('  ⚠ bx priors rebuild failed — rh3 (bx_prior_h is a promoted '
                  'feature) will fail loudly if the existing cache is missing/stale')

    # 1.96/1.97. Context-lens trending caches (Rule 13 display-only). These read
    # the statcast cache refreshed in step 1/1.05 and are cheap (seconds each).
    # Historically NOT wired into any pipeline, so they silently drifted 1-2
    # months stale while rp3/rh3/rprs2 stayed same-day (fixed 2026-07-20). Both
    # fail-soft — they feed /trending and Section B of the daily-edge briefing,
    # no model consumes them.
    run('1.96. Rebuild SP fastball-velocity trend cache (sp_velocity_trend.csv)',
        'python -X utf8 scripts/xfp/sp_velocity_trend.py',
        timeout=300)
    run('1.97. Rebuild bat-speed trending cache (bat_speed_trending_2026.csv)',
        'python -X utf8 scripts/xfp/research/early_season_trending_2026.py',
        timeout=300)

    # 1.98. PLV target boards (hitter_pre_breakout / breakout_flags + master_*,
    # process_plus_rolling). `plv update` does a full-season pitch-feature
    # rebuild (heavy, ~minutes), so it runs on a WEEKLY cadence via an mtime gate
    # on its pre_breakout output — same pattern as the bx priors (1.95). Skipped
    # on --no-models (the fast path never does the heavy PLV rebuild). Fail-soft:
    # these are display-only boards; no publish-critical dashboard gates on them.
    if not args.no_models:
        _pb_csv = ROOT / 'data' / 'outputs' / 'hitter_pre_breakout_2026.csv'
        _pb_fresh = (_pb_csv.exists()
                     and (time.time() - _pb_csv.stat().st_mtime) < 7 * 86400)
        if _pb_fresh:
            print('\n  1.98. PLV target boards fresh (<7 days) — skip weekly rebuild')
        else:
            # No season literal (item 42): cli.update's --year already defaults
            # to the current calendar year.
            run('1.98. Rebuild PLV target boards (plv update, weekly, mtime-gated)',
                'python -X utf8 -m plv_clone.cli update',
                timeout=1800)

    # ok_models gates the git publish (steps 5/6): a failed model rebuild means
    # every downstream dashboard is rendered from STALE projections — publishing
    # them as "fresh" is the failure mode the audit 2026-07-19 flagged (F2).
    ok_models = True
    if not args.no_models:
        # --skip-schedule: build_pitcher_schedule already ran as its own step
        # here (dead duplicate probables pull inside refresh_all otherwise).
        ok_models = run('2. Rebuild xFP models',
                        'python -X utf8 scripts/xfp/refresh_all.py --skip-schedule',
                        timeout=1800)
        if not ok_models:
            print('  → continuing (build steps still run) but the PUBLISH will be '
                  'GATED — dashboards would carry stale projections')

    # 2a. Patch stale is_on_il_at_split from live ESPN injury status.
    # The rp3 pipeline's is_on_il_at_split (and the data_quality_tag='marcel_il'
    # bucket derived from it) come from historical IL transactions that can be
    # days/weeks stale. This shim overrides the flag with live ESPN data and
    # writes xfp_rp3_projections_il_fixed.csv, which is the file the matchup
    # dashboard prefers (with a freshness guard — see build_matchup_dashboard
    # load_projections). Must run AFTER rp3 regen, BEFORE matchup build.
    # Fail-soft: if ESPN is down, the dashboard's freshness guard will raise.
    # CAUTION (2026-07-09 post-mortem): this patch fixes the DISPLAYED flag,
    # which is exactly why the dead training-time IL join went unnoticed for
    # 6 weeks — dashboards looked right while the model trained on constants.
    # Never treat this shim's output as evidence the rolling×IL join works;
    # that is what the scorecard's il_join_match_rate + il_grid_coverage
    # tripwires are for.
    ok_ilfix = run('2a. Patch is_on_il_at_split from live ESPN status',
                   'python -X utf8 scripts/xfp/fix_il_flag_from_espn.py',
                   timeout=180)
    if not ok_ilfix:
        print('  ⚠ ESPN IL-flag patch failed — il_fixed CSV may be stale; '
              'matchup build will assert freshness and fall back to canonical')

    run('2b. Build name-resolution cache',
        'python -X utf8 scripts/xfp/build_name_resolution_cache.py',
        timeout=120)

    run('2.5. Build SP/hitter upgrade alerts',
        'python -X utf8 scripts/xfp/build_sp_alerts.py',
        timeout=120)

    # 2.55. Refresh pitch_features parquets — the PLV research pipeline owns
    # them, but step 2.6's pitch-mix/arsenal columns read year=<current>.
    # Weekly cadence via the wrapper's staleness guard (no-op most days).
    # Fail-soft: arsenal columns just stay at their last build.
    ok_pf = run('2.55. Refresh pitch_features (arsenal source, weekly cadence)',
                'python -X utf8 scripts/xfp/refresh_pitch_features.py',
                timeout=1200)
    if not ok_pf:
        print('  ⚠ pitch_features refresh failed — arsenal columns stay stale')

    run('2.6. Build SP archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_sp_archetypes.py',
        timeout=120)

    # 2.62. In-house Stuff+ fallback (2026-07-20): archetype STUFF (step 2.6,
    # same-day) + PLV quantile-mapped onto the FG stuff_plus scale. Consumed
    # by sp_stuff_model.load_2026 ONLY when the FG scrape (step 0.8) is stale
    # — which it silently is whenever chromedriver flakes (model-health
    # tripwire fg_scrape_silent_fail). Fail-soft: without this file a stale
    # FG just stays frozen (pre-fallback behavior).
    ok_inh_stuff = run(
        '2.62. Build in-house Stuff+ fallback (arch+PLV, FG-scale)',
        'python -X utf8 scripts/xfp/build_inhouse_stuff.py',
        timeout=120)
    if not ok_inh_stuff:
        print('  ⚠ in-house stuff build failed — stuff lens falls back to '
              'frozen FG when stale (non-gating)')

    # Lineup-spot context (structural-leverage signal, gmLI analog for hitters).
    # Display-only; joined into the hitter master in step 2.7 below. Must run
    # BEFORE step 2.7 so the new columns are populated downstream.
    run('2.65. Build hitter lineup-spot features (mean_lineup_spot / tier / entropy)',
        'python -X utf8 scripts/xfp/build_hitter_lineup_features.py',
        timeout=300)

    run('2.7. Build hitter archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_hitter_archetypes.py',
        timeout=120)

    run('2.75. Derive RP damage/GB columns from statcast (one-time-ish)',
        'python -X utf8 scripts/xfp/build_rp_damage_gb_from_statcast.py',
        timeout=300)

    # NOTE: Two RP-tag caches are populated by manual scrapers and NOT wired
    # into the daily chain. Both are read directly by build_rp_archetypes.py
    # if present. Re-run manually after mid-season closer / role changes:
    #
    #   1. FanGraphs leverage (gmLI / pLI / Shutdowns / Meltdowns):
    #      python -X utf8 scripts/xfp/pull_fg_rp_leverage.py
    #      Output: data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv
    #      Browser-driven (undetected-chromedriver) — same pattern as
    #      pull_fg_undetected.py. Drives `leverage_tier`.
    #
    #   2. Baseball-Reference IR / IS% (inherited-runner stranded% → FIREMAN):
    #      python -X utf8 scripts/xfp/pull_bref_rp_ir.py
    #      Output: data/research/xfp_cache/rp_ir_is_2018_2026.csv
    #      Plain requests+BS4 (no browser), ~1 min for all years. BBRef's
    #      `inherited_score_perc` is inverted to stranded%. Drives FIREMAN tag
    #      (`inherited_stranded_pct ≥ 80 AND ir ≥ 20`).

    run('2.8. Build RP archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_rp_archetypes.py',
        timeout=120)

    # 2.85. PL cache auto-pull. Cadence-gated (lib/pl_cache._cache_is_stale) —
    # only WebFetches editions that have actually published since the cached
    # snapshot (Top 100 SP Mon, closers ~Tue, Top 150 hitters ~Wed, streamers
    # rolling). Fail-soft: consumers (triangulate, sp-slate-grid, sp-pl-board)
    # fall back to the existing cached snapshots.
    ok_pl = run('2.85. PL cache auto-pull',
                'python -X utf8 scripts/xfp/build_pl_cache.py',
                timeout=120)
    if not ok_pl:
        print('  ⚠ PL cache auto-pull failed — consumers will use existing '
              'cached PL snapshots')

    # 2.9. Refresh pitcher probable-starts schedule (next 14 days via MLB Stats
    # API). Consumed by build_matchup_dashboard.py and
    # build_sp_boom_stack_full_pool.py (via lib/boom_stack.py
    # _component_park_friendly). Must run BEFORE step 4 (matchup) and 4.25
    # (full-pool boom_stack). Fail-soft: consumers have inline-API fallbacks
    # and the existing CSV remains if this fails (no partial write — atomic
    # temp+rename in the builder).
    ok_sched = run(
        '2.9. Refresh pitcher_schedule_2026.csv (next 14d probables)',
        'python -X utf8 scripts/xfp/build_pitcher_schedule.py',
        timeout=180,
    )
    if not ok_sched:
        print('  ⚠ pitcher_schedule refresh failed — downstream consumers will '
              'use stale cache + inline-API fallbacks')

    # explicit timeout (audit 2026-07-19 item 16): the implicit default is
    # banned for publish-critical steps — same effective value (900s).
    run('3. Build live_dashboard.html (snapshot)',
        'python -X utf8 scripts/xfp/live_monitor.py --dashboard',
        timeout=900)

    # Incremental backfill of closed-week actuals into predictions_history.csv.
    # Safe to run every day — idempotent (no-op if nothing new closed).
    # Must run BEFORE build_matchup_dashboard so any new actuals can flow
    # into matchup-page accuracy widgets if/when they're added.
    # Fail-soft: a backfill error must not stop the dashboard build.
    # --repair: stored actuals that disagree with ESPN's DECLARED final are
    # rewritten (pre-2026-07-30 rows hold single-day partials — period 17's
    # will only become repairable once ESPN closes it). Safe nightly: open
    # periods are refused (PeriodNotFinal), synthetic backfill_* rows are
    # excluded by LIVE_MODEL_VERSIONS, and a clean store repairs 0 rows.
    ok_backfill = run(
        '3.5. Backfill closed-week actuals (idempotent, self-repairing)',
        'python -X utf8 scripts/xfp/fetch_closed_matchup_actuals.py --repair',
        timeout=180,
    )
    if not ok_backfill:
        print('  ⚠ actuals backfill failed — continuing (matchup build unaffected)')

    # Regenerate the calibration report from whatever's currently backfilled.
    # No-op safe: if no rows are backfilled, the report flags INSUFFICIENT.
    # Driver-level idle gate (audit 2026-07-19 item 17, same idiom as 1.95):
    # the report is a pure function of predictions_history.csv, so skip the
    # subprocess entirely when the report already post-dates its input.
    _calib_in = ROOT / 'data' / 'outputs' / 'predictions_history.csv'
    _calib_out = ROOT / 'data' / 'outputs' / 'projection_accuracy_report.md'
    _calib_fresh = (_calib_out.exists() and _calib_in.exists()
                    and _calib_out.stat().st_mtime >= _calib_in.stat().st_mtime)
    if _calib_fresh:
        print('\n  3.6. calibration report newer than predictions_history.csv — skip')
    else:
        ok_calib = run(
            '3.6. Regenerate calibration report',
            'python -X utf8 scripts/xfp/report_calibration.py',
            timeout=120,
        )
        if not ok_calib:
            print('  ⚠ calibration report failed — continuing')

    # 3.65 (was 3.7 — relabeled, audit 2026-07-19 item 16: label collided with
    # the live_blend step below). Per-player backfill panel (slot-aware).
    # Historical 2024+2025 ESPN box-score data — one-time-ish. Pass --force
    # (to the script) to rebuild. Used for slot-aware projection tests and
    # per-player residual decomposition.
    # Driver-level idle gate (audit 2026-07-19 item 17, same idiom as 1.95):
    # the script itself skips when its output parquet exists, but spawning
    # python + ESPN imports just to print "skipping" wastes ~10s/day.
    _pp_parquet = ROOT / 'data' / 'research' / 'calibration_panel_per_player.parquet'
    if _pp_parquet.exists():
        print('\n  3.65. per-player calibration panel exists — skip (one-time build)')
    else:
        ok_pp = run(
            '3.65 (was 3.7). Per-player calibration backfill panel (one-time)',
            'python -X utf8 scripts/xfp/build_synthetic_calibration_with_slots.py',
            timeout=900,
        )
        if not ok_pp:
            print('  ⚠ per-player backfill panel failed — continuing (research-only)')

    # 3.67 (was 2.95 — relabeled, audit 2026-07-19 item 16: it EXECUTES here,
    # after 3.65). Enrich projection CSVs (rh3/rp3/rprs2) with validated prior-season
    # features: slope_3yr_prior, arche_overall_prior, traj_career_low_prior
    # (all three CSVs) + high_k_z_year_prior, shadow_velo_pct_prior,
    # shadow_bb_pct_prior (rp3 only). Joined on mlbam ID, atomic write, NaN
    # propagation (no silent mean-fill). Consumed by the blend scorer.
    # Fail-soft: scorer falls back to NaN handling if enrichment skips.
    ok_enrich = run(
        '3.67 (was 2.95). Enrich projection CSVs with prior-season features',
        'python -X utf8 scripts/xfp/enrich_projection_csvs.py',
        timeout=300,
    )
    if not ok_enrich:
        print('  ⚠ projection enrichment failed — blend scorer will see legacy '
              'columns only (rh3/rp3/rprs2 still valid as headline projections)')

    # ── PRODUCERS MOVED AHEAD OF CONSUMERS (audit 2026-07-04) ──
    # live_blend feeds matchup.html (step 4); stream_the_stack + hitter_boom_stack
    # feed triangulate.html (4.2), the triangulate universe (4.1) and
    # player_profiles (4.35). They previously ran AFTER those consumers, so every
    # dashboard rendered yesterday's blend/boom numbers next to today's
    # projections — and the PERMANENT nightly verdict history recorded day-old
    # boom components. Pure block moves, no logic change.
    # 3.7 (was 4.11). Build the within-season weight-blend live projection
    # (live_blend_xfp_<date>.csv + live_blend_xfp_latest.csv). Phase 3 Agent 3,
    # validated 2026-06-04: within-season R^2 doubles vs preseason at split_day=90
    # (H 0.642, SP 0.584, RP 0.398). Display-additive — does NOT replace rh3/rp3/
    # rprs2 headline numbers; surfaced by build_matchup_dashboard as a "blended X.X
    # [lo-hi]" suffix on each player projection cell. Fail-soft: matchup build
    # tolerates a missing latest CSV and silently skips the suffix.
    ok_blend = run(
        '3.7 (was 4.11). Build live_blend_xfp (within-season blend ROS projection)',
        'python -X utf8 scripts/xfp/build_live_blend_xfp.py',
        timeout=300,
    )
    if not ok_blend:
        print('  ⚠ live_blend_xfp build failed — continuing (display-only)')

    # 3.8 (was 4.6). Daily boom-stack streamer scan. Fail-soft: API errors or zero
    # candidates must not abort the pipeline — outputs land at
    # data/outputs/stream_the_stack_<date>.{md,json}. Depends on rp3
    # projections (step 2) + team_strength cache.
    ok_stream = run(
        '3.8 (was 4.6). Build stream_the_stack daily streamer ranks',
        'python -X utf8 scripts/xfp/stream_the_stack.py',
        timeout=180,
    )
    if not ok_stream:
        print('  ⚠ stream_the_stack failed — continuing (non-gating)')

    # 3.85 (was 4.7). Daily hitter boom_stack batch. Fail-soft mirror of 3.8 but for
    # batters in today+tomorrow's scheduled games. Outputs at
    # data/outputs/hitter_boom_stack_<date>.{md,json}. Consumed by the
    # profiles dashboard Boom/Bust/Variance tab on the next build.
    ok_hboom = run(
        '3.85 (was 4.7). Build hitter_boom_stack daily batch',
        'python -X utf8 scripts/xfp/build_hitter_boom_stack_daily.py',
        timeout=300,
    )
    if not ok_hboom:
        print('  ⚠ hitter_boom_stack failed — continuing (non-gating)')

    # explicit timeout (audit 2026-07-19 item 16): the implicit default is
    # banned for publish-critical steps — same effective value (900s).
    run('4. Build matchup.html (weekly H2H)',
        'python -X utf8 scripts/xfp/build_matchup_dashboard.py',
        timeout=900)

    # 4.05. Refresh the offline injury-status cache from live ESPN — powers the
    # triangulate IL caveat (so an injured star isn't surfaced as a naked BUY).
    # 4.05 also fetches per-player injury_details (return dates) for the
    # injured-rostered subset (~30-80 bounded GETs) since 2026-07-11 (A2/E1.5b
    # estimate log) — timeout raised 120→300 to absorb them.
    run('4.05. Refresh injury-status cache (ESPN IL flags + return dates)',
        'python -X utf8 scripts/xfp/lib/injury_status.py', timeout=300)

    # triangulate.html (now 4.2, was 4.7) MOVED below the nightly batch (now
    # 4.1, was 4.72) on 2026-07-19: the dashboard now hydrates its FA cards
    # from the batch's --cards-out store, so it must build AFTER tonight's
    # store exists. One build, full fidelity — replaces the old 4.7
    # roster-only build + 4.73 ~50-min --live-fa re-run pair.

    # 4.1 (was 4.72). Nightly league-wide triangulate backfill + verdict history append.
    # Builds the player universe (roster + my drops + opp churn + FA_TOP with
    # owner_team), triangulates it into a dated snapshot (CSV+JSON+run manifest),
    # then appends those verdicts to triangulate_verdict_history.parquet — the
    # audit trail behind CLAUDE.md #12 (never flip a verdict silently). Fail-soft
    # and non-gating: any ESPN/MLB hiccup must not abort the publish pipeline.
    _tri_date = datetime.now().strftime('%Y-%m-%d')
    _tri_label = f'nightly_{_tri_date}'
    _tri_runid = datetime.now().strftime('%Y%m%d-%H%M%S')
    _tri_csv = f'data/research/triangulate_universe/snapshots/triangulate_{_tri_label}_{_tri_date}.csv'
    _tri_json = f'data/research/triangulate_universe/triangulate_{_tri_label}.json'
    _tri_universe = 'data/research/triangulate_universe/master_universe.csv'
    ok_tri_universe = run(
        '4.1a (was 4.72a). Build triangulate player universe (ownership-tagged)',
        'python -X utf8 scripts/xfp/build_triangulate_universe.py',
        timeout=600,
    )
    if not ok_tri_universe:
        print('  ⚠ triangulate universe build failed — skipping nightly backfill')
    else:
        ok_tri_batch = run(
            '4.1b (was 4.72b). Triangulate the full universe -> dated snapshot',
            f'python -X utf8 scripts/xfp/run_triangulate.py '
            f'--names-file {_tri_universe} --snapshot {_tri_label} '
            f'--run-id {_tri_runid} --csv-out {_tri_json.replace(".json", ".csv")} '
            f'--json-out {_tri_json} '
            f'--cards-out {_tri_json.replace(".json", "_cards.json")}',
            timeout=1800,
        )
        if not ok_tri_batch:
            print('  ⚠ nightly triangulate batch failed — skipping history append')
        else:
            ok_tri_hist = run(
                '4.1c (was 4.72c). Append verdicts to triangulate_verdict_history.parquet',
                f'python -X utf8 scripts/xfp/build_triangulate_history.py '
                f'--append {_tri_csv} --run-id {_tri_runid}',
                timeout=180,
            )
            if not ok_tri_hist:
                print('  ⚠ triangulate history append failed — continuing (non-gating)')

    # 4.2 (was 4.7). Build triangulate.html (three-lens roster report + full-fidelity FA
    # section). Runs AFTER the 4.1 chain so tonight's --cards-out store exists:
    # roster cards run the live engine (~26 players, fast); FA cards hydrate
    # from the store — identical schema to live (assemble_result seam), zero
    # per-FA recompute. Replaced the old-4.73 --live-fa re-run (~45-60 min/night,
    # ~100% duplicate of 4.1b — audit 2026-07-19 F1). If tonight's batch
    # failed, the dashboard falls back to the freshest prior store/batch with
    # its own staleness warning. Fail-soft.
    ok_tri_page = run(
        '4.2 (was 4.7). Build triangulate.html (roster live + FA from nightly cards store)',
        'python -X utf8 scripts/xfp/build_triangulate_dashboard.py',
        timeout=600,
    )
    if not ok_tri_page:
        print('  ⚠ triangulate.html build failed — prior page stands')

    # 4.25 (was 4.45). Full-pool SP boom_stack pre-batch. Generates per-SP boom/bust/variance
    # records for the ENTIRE rp3 SP universe (~300 SPs), not just the rolling
    # probables window covered by stream_the_stack (~15-25). Lets the profiles
    # dashboard's Boom/Bust tab populate for any rostered SP. Fail-soft.
    ok_full_pool = run(
        '4.25 (was 4.45). Build sp_boom_stack_full_pool (entire SP universe)',
        'python -X utf8 scripts/xfp/build_sp_boom_stack_full_pool.py',
        timeout=300,
    )
    if not ok_full_pool:
        print('  ⚠ sp_boom_stack_full_pool failed — continuing (non-gating)')

    # 4.3 (was 4.52). Decision-console payload FALLBACK writer. The matchup build
    # (step 4) is the authoritative writer of data/outputs/console_data.json
    # (freshest week context); --if-stale makes this a no-op when that
    # succeeded and a same-day rebuild when it didn't, so xfp_board (4.4)
    # and index (refresh_all) always have a fresh payload. Fail-soft.
    ok_console = run(
        '4.3 (was 4.52). Decision-console payload (fallback writer, --if-stale)',
        'python -X utf8 scripts/xfp/build_console_data.py --if-stale',
        timeout=300,
    )
    if not ok_console:
        print('  ⚠ console payload build failed — continuing (consoles show stale stamp)')

    # 4.31. Re-emit index.html now that TODAY's console payload exists.
    #
    # WHY (audit 2026-08-01 item 13): index.html embeds console_data.json only
    # when its generated_at date is today (build_index_dashboard.py, the __TOKEN__ replace chain in main())
    # — the check that stops a stale payload being displayed as current. But
    # the index build is the LAST stage of refresh_all.py, i.e. inside step 2,
    # while the payload is written at step 4 (matchup, authoritative) and 4.3
    # (fallback). The page was therefore always written minutes BEFORE its own
    # payload — 09:18 vs 09:22 on the 2026-07-31 run — so the date test always
    # failed and the published page shipped `window.XFP_DECISION = null` on 10
    # of its last 12 publishes. Rebuilding here (idempotent; reads committed
    # CSVs plus console_data.json) is the cheap correct fix; relaxing the date
    # test is NOT, it is the only thing preventing a silently stale payload.
    # Fail-soft and non-gating: the step-2 build stands if this one fails.
    ok_index = run(
        '4.31. Re-emit index.html with today\'s decision payload',
        'python -X utf8 scripts/xfp/build_index_dashboard.py',
        timeout=900,
    )
    if not ok_index:
        print('  ⚠ index re-emit failed — the step-2 index build stands, but its '
              'Decision tab will show the "not built today" notice')

    # Fail-closed: if player_profiles build fails, skip publish to avoid stale docs.
    # --payload-only (item 16, 2026-07-04): the shell is now BYTE-STABLE (meta line
    # renders client-side from the payload), so the daily refresh only rewrites the
    # ~40MB data.js and skips re-emitting the ~1MB shell. First build (no shell yet)
    # OR a template change (delete the shell / run without the flag once) does a full
    # build to republish the shell.
    _pp_shell = os.path.join(ROOT, 'data', 'outputs', 'player_profiles.html')
    _pp_flag = ' --payload-only' if os.path.exists(_pp_shell) else ''
    ok_profiles = run('4.35 (was 4.5). Build player_profiles.html (archetype browser)',
                      f'python -X utf8 scripts/xfp/build_player_profiles_dashboard.py{_pp_flag}',
                      timeout=420)   # 40MB embed reads the big rolling CSVs; 120s timed
                      # out on the self-hosted runner and killed the whole refresh.

    # 4.4 (was 4.55). Build merged xFP boards (SP + 5 hitter buckets) + xfp_board.html.
    # Regenerates data/research/{sp,hitter}_merged_xfp_rank_<date>.csv and the
    # self-contained dashboard at data/outputs/xfp_board.html (mirrored to
    # xfp-model/docs/xfp_board.html). The dashboard builder imports the board
    # engine, so this single step rebuilds both CSVs and the page. Fail-soft:
    # an ESPN/MLB hiccup must not abort the pipeline (non-gating dashboard).
    ok_xfp_board = run(
        '4.4 (was 4.55). Build merged xFP boards + xfp_board.html',
        'python -X utf8 scripts/xfp/build_xfp_board_dashboard.py',
        timeout=300,
    )
    if not ok_xfp_board:
        print('  ⚠ xfp_board build failed — continuing (non-gating dashboard)')



    # 4.8. Append today's SP + hitter boom_stack snapshots to the growing
    # history panel at data/research/boom_stack_history_panel.parquet.
    # Idempotent — only adds dates not already present. Required so that in
    # ~12-16 weeks we have enough archived panel data to test whether
    # boom_stack predicts team residual scoring (see
    # boom_stack_residual_test.md). Fail-soft.
    ok_panel = run(
        '4.8. Append boom_stack snapshots to history panel',
        'python -X utf8 scripts/xfp/build_boom_stack_history_panel.py',
        timeout=120,
    )
    if not ok_panel:
        print('  ⚠ boom_stack history panel append failed — continuing (non-gating)')

    # 4.9. Archive today's PL rank cache snapshots (date-keyed). Feeds the
    # opponent-action predictor's Δ-PL-rank feature. Idempotent — skips
    # snapshots already present. Fail-soft.
    ok_plhist = run(
        '4.9. Archive PL rank cache snapshots',
        'python -X utf8 scripts/xfp/build_pl_rank_history.py',
        timeout=60,
    )
    if not ok_plhist:
        print('  ⚠ PL rank history archive failed — continuing (non-gating)')


    # 4.91 (was 4.09). Build forward-volume projections (validated 2026-07-09, PASS:
    # pooled Spearman +0.074 vs naive pace, 7/7 years, holdout 2/2 —
    # hitter_volume_model_2026-07-09.md). Volume (PA/starts) explains 3-5x
    # more forward-total-FP variance than projected rate; this companion
    # model converts the rate models into honest RoS totals. Runs before
    # 4.94 so the snapshot logger can log proj_volume. Fail-soft.
    ok_vol = run(
        '4.91 (was 4.09). Build hitter volume projections',
        'python -X utf8 scripts/xfp/xfp_volume_pipeline.py',
        timeout=600,
    )
    if not ok_vol:
        print('  ⚠ hitter volume projections failed — proj_volume stays NaN today (non-gating)')

    # 4.92 (was 4.09b). SP forward-starts volume (validated 2026-07-09, PASS: pooled
    # Spearman +0.100 vs naive gs-pace, 7/7 years, holdout 2/2 —
    # sp_volume_model_2026-07-09.md). Fail-soft.
    ok_spvol = run(
        '4.92 (was 4.09b). Build SP volume projections',
        'python -X utf8 scripts/xfp/xfp_sp_volume_pipeline.py',
        timeout=600,
    )
    if not ok_spvol:
        print('  ⚠ SP volume projections failed — proj_volume stays NaN today (non-gating)')

    # 4.93 (was 4.09c). RP forward-appearance volume (validated 2026-07-10, PASS: pooled
    # Spearman +0.127 vs naive g-pace, 6/6 years, holdout 2/2 —
    # rp_volume_model_2026-07-10.md). Completes the volume layer (H/SP/RP).
    # Must run AFTER rprs2 (name fallback) and BEFORE 4.94 (logger fill).
    # Fail-soft.
    ok_rpvol = run(
        '4.93 (was 4.09c). Build RP volume projections',
        'python -X utf8 scripts/xfp/xfp_rp_volume_pipeline.py',
        timeout=600,
    )
    if not ok_rpvol:
        print('  ⚠ RP volume projections failed — proj_volume stays NaN today (non-gating)')

    # 4.94 (was 4.10). Append today's per-player projection snapshot to the growing
    # panel at data/research/player_projection_history.parquet. Feeds the
    # opponent-action predictor's Δ-rank feature and any future per-player
    # residual analysis. Fail-soft.
    ok_pphist = run(
        '4.94 (was 4.10). Append player projection history',
        'python -X utf8 scripts/xfp/build_player_projection_history.py',
        # 60→180 (2026-07-11): the A2 lens columns widen the parquet and add
        # offline artifact joins (PL cache, archetype panels, boom pools).
        timeout=180,
    )
    if not ok_pphist:
        print('  ⚠ player projection history append failed — continuing (non-gating)')

    # 4.94a (was 4.10a). Emit verdict-level decision records for the user's roster.
    # Scoped env var `PLV_LOG_DECISIONS=1` activates the env-gated logging
    # hook inside triangulate_player(). The var is scoped to THIS subprocess
    # only (via run(env=...)) and does not leak to subsequent steps.
    # Fail-soft — decision logging is observability only.
    ok_dec_log = run(
        '4.94a (was 4.10a). Log roster decisions (PLV_LOG_DECISIONS=1)',
        'python -X utf8 scripts/xfp/log_roster_decisions.py',
        timeout=300,
        env={'PLV_LOG_DECISIONS': '1'},
    )
    if not ok_dec_log:
        print('  ⚠ roster decision logging failed — continuing (non-gating)')

    # 4.94b (was 4.10b). Materialize the verdict-level decision log into a flat panel.
    # Walks data/research/decisions/ recursively, opportunistically settles
    # hitter decisions whose 21d window has elapsed (using statcast_{yr}.parquet),
    # and writes data/outputs/decisions_panel.csv. SP/RP settlement is not
    # implemented in this driver yet (see scripts/xfp/materialize_decisions.py).
    # NOTE: plan v11 called this "step 0.65 right after step 0.6"; the actual
    # projection-history persistence runs at step 4.94 (not 0.6), so we wire
    # immediately after 4.94 here. Fail-soft — panel is observability only.
    ok_decisions = run(
        '4.94b (was 4.10b). Materialize decisions panel',
        'python -X utf8 scripts/xfp/materialize_decisions.py',
        timeout=120,
    )
    if not ok_decisions:
        print('  ⚠ decisions panel build failed — continuing (non-gating)')

    # 4.94c (was 4.10c). Settle logged decisions vs realized FP + emit daily scorecard.
    # Walks data/research/decisions/, pulls actuals from the MLB Stats API
    # gameLog (H FP/PA, SP FP/start, RP FP/app), settles every ripe record,
    # and writes scorecard_{date}.{csv,md}. Idempotent + fail-soft.
    ok_settle = run(
        '4.94c (was 4.10c). Settle decisions + scorecard',
        'python -X utf8 scripts/xfp/settle_decisions.py',
        timeout=180,
    )
    if not ok_settle:
        print('  ⚠ decision settlement failed — continuing (non-gating)')

    # 4.95 (was 4.11). Snapshot FanGraphs RoS projections (steamerr/rzips/ratcdc/
    # rfangraphsdc, bat+pit). Date-keyed accumulation for the ~4-week
    # forward validation of external playing-time/RoS systems. Idempotent
    # (skips combos already pulled today). Cloudflare pass is intermittent
    # -> retries internally; fail-soft.
    ok_fgros = run(
        '4.95 (was 4.11). Snapshot FanGraphs RoS projections',
        'python -X utf8 scripts/xfp/pull_fg_ros_projections.py',
        timeout=600,
    )
    if not ok_fgros:
        print('  ⚠ FG RoS projection snapshot failed — continuing (non-gating)')

    # 4.96 (was 4.12). Refresh IL transaction history + injury-proneness features
    # (current month refetch only; historical chunks cached under
    # il_tx_chunks/). Weekly cadence is sufficient — the derived features
    # are as-of-Jan-1. Fail-soft.
    if datetime.now().weekday() == 0:  # Monday, match other weekly steps
        ok_iltx = run(
            '4.96 (was 4.12). Refresh IL transactions + injury proneness',
            'python -X utf8 scripts/xfp/fetch_il_transactions.py',
            timeout=300,
        )
        if not ok_iltx:
            print('  ⚠ IL transaction refresh failed — continuing (non-gating)')

        # 4.97 (was 4.13). Model scorecard + data-health tripwires (Mondays). Forward
        # accuracy per model at 7/14/21/28d anchors + PASS/WARN/FAIL data
        # regression checks (IL join, ros caches, statcast/boxscore lag, FG
        # snapshots, row counts, proj_volume fill). Built 2026-07-10 after
        # the rp3 IL-join regression sat undetected for ~6 weeks. Fail-soft:
        # a scorecard problem must never block the refresh — but exit 1
        # (>=1 FAIL tripwire) is surfaced loudly.
        ok_scorecard = run(
            '4.97 (was 4.13). Model scorecard + data-health tripwires',
            'python -X utf8 scripts/xfp/build_model_scorecard.py',
            timeout=600,
        )
        if not ok_scorecard:
            print('  ! model scorecard reported FAIL tripwire(s) — read '
                  'data/outputs/model_scorecard.md (non-gating)')

        # 4.97b (was 4.13b). VERDICT scorecard (Mondays, paired with 4.97). model-health
        # grades the MODELS; this grades the CALLS — the settled triangulate
        # verdicts (BUY/HOLD/CAUTION/FADE vs realized FP). Added 2026-07-18:
        # first full read showed a monotonic hitter ladder but an INVERTED
        # confidence calibration (1.00-conf hit 7.7% vs 0.75-conf 32.5%) and
        # SP MIXED missing proj by -5.5/start — both flagged for re-check as
        # cohorts settle. Fail-soft, non-gating.
        ok_verdicts = run(
            '4.97b (was 4.13b). Verdict scorecard (decision-quality, settled calls)',
            'python -X utf8 scripts/xfp/run_verdict_scorecard.py',
            timeout=600,
        )
        if not ok_verdicts:
            print('  ! verdict scorecard failed — continuing (non-gating)')

    if not args.no_push:
        _marker = publish_gated_marker()
        if not ok_models:
            print('\n  ✖ PUBLISH GATED: the model rebuild (step 2) FAILED, so the '
                  'dashboards above were rendered from STALE projections.\n'
                  '    Nothing was committed or pushed to xfp-model. Fix the model '
                  'rebuild and re-run refresh_dashboards.py (or push manually if '
                  'the staleness is understood and acceptable).')
            try:
                _marker.parent.mkdir(parents=True, exist_ok=True)
                _marker.write_text(datetime.now().isoformat(), encoding='utf-8')
                print(f'    (wrote {_marker} — the workflow prefixes its commit '
                      'message and job summary with GATED)')
            except OSError as e:
                print(f'    ! could not write the gate marker: {e}')
            return
        # Clear a previous night's marker so it can never alert on a clean run.
        try:
            _marker.unlink(missing_ok=True)
        except OSError:
            pass
        if not XFP_MODEL.exists():
            print(f'\n  ⚠ xfp-model repo not found at {XFP_MODEL}')
            return
        # Dynamic publish list (audit 2026-07-04): one failed page must not
        # block the other five dashboards from publishing — withhold ONLY the
        # failed artifact. (--allow-empty dropped: a no-change day should not
        # mint an empty commit into xfp-model's already-heavy history.)
        pages = list(PUBLISH_PAGES_CORE)
        if ok_profiles:
            pages += list(PUBLISH_PAGES_PROFILES)
        else:
            print('\n  ⚠ player_profiles build failed — WITHHOLDING profiles from '
                  'the publish; other dashboards still ship')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        commit_cmd = (
            f'git add {" ".join(pages)} && '
            f'git commit -m "refresh: {timestamp} dashboards"'
        )
        # explicit timeouts (audit 2026-07-19 item 16): the implicit default is
        # banned for publish-critical steps — git ops get a tighter 300s.
        run('5. Commit xfp-model dashboards', commit_cmd, cwd=XFP_MODEL,
            timeout=300)
        # Pull-before-push: the cloud live-matchup job also pushes to xfp-model
        # throughout game days, so this local clone is often behind. Reconcile
        # first (this full build wins on conflict) so the push can't be rejected.
        run('6. Push to GitHub Pages',
            'git fetch origin && git merge -X ours --no-edit origin/main && '
            'git push origin main', cwd=XFP_MODEL, timeout=300)

    # 7. PL cache freshness — the SINGLE loud checkpoint (2026-07-20). The PL
    # rank/streamer caches can't be auto-refreshed here (they need a live
    # WebSearch/WebFetch of pitcherlist.com — an agent capability, not a
    # headless scrape; deliberately NOT another FG-style Chrome scrape). This
    # prints the cadence-aware staleness report + exact refresh steps once per
    # daily run, so staleness surfaces at the maintenance moment instead of
    # only as per-call WARNs on every triangulate. Fail-soft, display-only.
    print(f'\n{"="*70}\n  7. PL cache freshness (manual refresh — agent WebFetch)\n{"="*70}')
    try:
        from scripts.xfp.lib.pl_cache import print_refresh_instructions
        print_refresh_instructions()
    except Exception as e:
        print(f'  ! PL cache freshness check failed — continuing (non-gating): {e}')

    print(f'\n{"="*70}\n  ALL DONE — {datetime.now().strftime("%Y-%m-%d %H:%M")}\n{"="*70}')
    print(f'  Live: https://kejjeh.github.io/xfp-model/live_dashboard.html')
    print(f'  Matchup: https://kejjeh.github.io/xfp-model/matchup.html')


if __name__ == '__main__':
    main()
