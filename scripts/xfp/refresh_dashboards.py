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


def run(label, cmd, cwd=None, timeout=900, env=None):
    """Run a subprocess. `env` is an optional dict of EXTRA env vars merged
    on top of os.environ for THIS step only (scoped — does not leak)."""
    print(f'\n{"="*70}\n  {label}\n{"="*70}', flush=True)
    t0 = time.time()
    proc_env = None
    if env:
        proc_env = {**os.environ, **env}
    try:
        result = subprocess.run(
            cmd, cwd=cwd or ROOT, shell=True, timeout=timeout, env=proc_env,
        )
    except subprocess.TimeoutExpired:
        print(f'  ⚠ {label} TIMED OUT after {timeout}s — continuing with next step')
        return False
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

    # 0.7: Build FA-pool snapshot (RP-only, Phase 2). Powers the live_marginal
    # line on RP triangulate cards. Fail-soft — if snapshot is stale/missing,
    # blend_score.py emits live_marginal=None with a note.
    ok_fa = run('0.7. Build FA-pool snapshot (RP)',
                'python -X utf8 scripts/xfp/build_fa_snapshot.py',
                timeout=180)
    if not ok_fa:
        print('  ⚠ FA snapshot failed — RP cards will show live_marginal=unavailable')

    if not args.skip_statcast:
        run('1. Refresh statcast (yesterday\'s games)',
            'python -X utf8 scripts/xfp/refresh_xfp_statcast.py --year 2026 --lag 1')

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

    run('1b. Build batter rolling-feature cache',
        'python -X utf8 scripts/xfp/build_batter_rolling_features.py')

    # Snapshot rolling caches — feed the Player-Profiles intra-season trajectory
    # view. AUDIT 2026-07-04 (-343s/day, 28% of the ritual): these write the
    # SAME rolling_*_2018_2026.csv files refresh_all's rolling stages rebuild
    # minutes later with no consumer in between — so run them here ONLY when
    # the model rebuild is being skipped (--no-models fast path).
    if args.no_models:
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
        # --skip-schedule: build_pitcher_schedule already ran as its own step
        # here (dead duplicate probables pull inside refresh_all otherwise).
        ok = run('2. Rebuild xFP models',
                 'python -X utf8 scripts/xfp/refresh_all.py --skip-schedule',
                  timeout=1800)
        if not ok: print('  → continuing despite model rebuild issue')

    # 2a. Patch stale is_on_il_at_split from live ESPN injury status.
    # The rp3 pipeline's is_on_il_at_split (and the data_quality_tag='marcel_il'
    # bucket derived from it) come from historical IL transactions that can be
    # days/weeks stale. This shim overrides the flag with live ESPN data and
    # writes xfp_rp3_projections_il_fixed.csv, which is the file the matchup
    # dashboard prefers (with a freshness guard — see build_matchup_dashboard
    # load_projections). Must run AFTER rp3 regen, BEFORE matchup build.
    # Fail-soft: if ESPN is down, the dashboard's freshness guard will raise.
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

    run('2.6. Build SP archetype ratings panel (20-80 + trajectories)',
        'python -X utf8 scripts/xfp/build_sp_archetypes.py',
        timeout=120)

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

    # 2.9. Refresh pitcher probable-starts schedule (next 14 days via MLB Stats
    # API). Consumed by build_matchup_dashboard.py and
    # build_sp_boom_stack_full_pool.py (via lib/boom_stack.py
    # _component_park_friendly). Must run BEFORE step 4 (matchup) and 4.45
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

    run('3. Build live_dashboard.html (snapshot)',
        'python -X utf8 scripts/xfp/live_monitor.py --dashboard')

    # Incremental backfill of closed-week actuals into predictions_history.csv.
    # Safe to run every day — idempotent (no-op if nothing new closed).
    # Must run BEFORE build_matchup_dashboard so any new actuals can flow
    # into matchup-page accuracy widgets if/when they're added.
    # Fail-soft: a backfill error must not stop the dashboard build.
    ok_backfill = run(
        '3.5. Backfill closed-week actuals (idempotent)',
        'python -X utf8 scripts/xfp/fetch_closed_matchup_actuals.py',
        timeout=180,
    )
    if not ok_backfill:
        print('  ⚠ actuals backfill failed — continuing (matchup build unaffected)')

    # Regenerate the calibration report from whatever's currently backfilled.
    # No-op safe: if no rows are backfilled, the report flags INSUFFICIENT.
    ok_calib = run(
        '3.6. Regenerate calibration report',
        'python -X utf8 scripts/xfp/report_calibration.py',
        timeout=120,
    )
    if not ok_calib:
        print('  ⚠ calibration report failed — continuing')

    # 3.7. Per-player backfill panel (slot-aware). Historical 2024+2025 ESPN
    # box-score data — one-time-ish; only re-runs if the output parquet is
    # missing. Pass --force to rebuild. Used for slot-aware projection tests
    # and per-player residual decomposition.
    ok_pp = run(
        '3.7. Per-player calibration backfill panel (one-time)',
        'python -X utf8 scripts/xfp/build_synthetic_calibration_with_slots.py',
        timeout=900,
    )
    if not ok_pp:
        print('  ⚠ per-player backfill panel failed — continuing (research-only)')

    # 2.95. Enrich projection CSVs (rh3/rp3/rprs2) with validated prior-season
    # features: slope_3yr_prior, arche_overall_prior, traj_career_low_prior
    # (all three CSVs) + high_k_z_year_prior, shadow_velo_pct_prior,
    # shadow_bb_pct_prior (rp3 only). Joined on mlbam ID, atomic write, NaN
    # propagation (no silent mean-fill). Consumed by the blend scorer.
    # Fail-soft: scorer falls back to NaN handling if enrichment skips.
    ok_enrich = run(
        '2.95. Enrich projection CSVs with prior-season features',
        'python -X utf8 scripts/xfp/enrich_projection_csvs.py',
        timeout=300,
    )
    if not ok_enrich:
        print('  ⚠ projection enrichment failed — blend scorer will see legacy '
              'columns only (rh3/rp3/rprs2 still valid as headline projections)')

    # ── PRODUCERS MOVED AHEAD OF CONSUMERS (audit 2026-07-04) ──
    # live_blend feeds matchup.html (step 4); stream_the_stack + hitter_boom_stack
    # feed triangulate.html (4.7-label), the triangulate universe (4.72) and
    # player_profiles (4.5). They previously ran AFTER those consumers, so every
    # dashboard rendered yesterday's blend/boom numbers next to today's
    # projections — and the PERMANENT nightly verdict history recorded day-old
    # boom components. Pure block moves, no logic change.
    # 4.11. Build the within-season weight-blend live projection
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

    # 4.6. Daily boom-stack streamer scan. Fail-soft: API errors or zero
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

    # 4.7. Daily hitter boom_stack batch. Fail-soft mirror of 4.6 but for
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

    run('4. Build matchup.html (weekly H2H)',
        'python -X utf8 scripts/xfp/build_matchup_dashboard.py')

    # 4.05. Refresh the offline injury-status cache from live ESPN — powers the
    # triangulate IL caveat (so an injured star isn't surfaced as a naked BUY).
    run('4.05. Refresh injury-status cache (ESPN IL flags)',
        'python -X utf8 scripts/xfp/lib/injury_status.py', timeout=120)

    # 4.7. Build triangulate.html (cyclable three-lens roster report). Depends on
    # the injury cache above + the archetype/projection panels. Fail-soft.
    run('4.7. Build triangulate.html (three-lens roster report)',
        'python -X utf8 scripts/xfp/build_triangulate_dashboard.py', timeout=300)

    # 4.72. Nightly league-wide triangulate backfill + verdict history append.
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
        '4.72a. Build triangulate player universe (ownership-tagged)',
        'python -X utf8 scripts/xfp/build_triangulate_universe.py',
        timeout=600,
    )
    if not ok_tri_universe:
        print('  ⚠ triangulate universe build failed — skipping nightly backfill')
    else:
        ok_tri_batch = run(
            '4.72b. Triangulate the full universe -> dated snapshot',
            f'python -X utf8 scripts/xfp/run_triangulate.py '
            f'--names-file {_tri_universe} --snapshot {_tri_label} '
            f'--run-id {_tri_runid} --csv-out {_tri_json.replace(".json", ".csv")} '
            f'--json-out {_tri_json}',
            timeout=1800,
        )
        if not ok_tri_batch:
            print('  ⚠ nightly triangulate batch failed — skipping history append')
        else:
            ok_tri_hist = run(
                '4.72c. Append verdicts to triangulate_verdict_history.parquet',
                f'python -X utf8 scripts/xfp/build_triangulate_history.py '
                f'--append {_tri_csv} --run-id {_tri_runid}',
                timeout=180,
            )
            if not ok_tri_hist:
                print('  ⚠ triangulate history append failed — continuing (non-gating)')

    # 4.45. Full-pool SP boom_stack pre-batch. Generates per-SP boom/bust/variance
    # records for the ENTIRE rp3 SP universe (~300 SPs), not just the rolling
    # probables window covered by stream_the_stack (~15-25). Lets the profiles
    # dashboard's Boom/Bust tab populate for any rostered SP. Fail-soft.
    ok_full_pool = run(
        '4.45. Build sp_boom_stack_full_pool (entire SP universe)',
        'python -X utf8 scripts/xfp/build_sp_boom_stack_full_pool.py',
        timeout=300,
    )
    if not ok_full_pool:
        print('  ⚠ sp_boom_stack_full_pool failed — continuing (non-gating)')

    # Fail-closed: if player_profiles build fails, skip publish to avoid stale docs.
    ok_profiles = run('4.5. Build player_profiles.html (archetype browser)',
                      'python -X utf8 scripts/xfp/build_player_profiles_dashboard.py',
                      timeout=420)   # 40MB embed reads the big rolling CSVs; 120s timed
                      # out on the self-hosted runner and killed the whole refresh.

    # 4.55. Build merged xFP boards (SP + 5 hitter buckets) + xfp_board.html.
    # Regenerates data/research/{sp,hitter}_merged_xfp_rank_<date>.csv and the
    # self-contained dashboard at data/outputs/xfp_board.html (mirrored to
    # xfp-model/docs/xfp_board.html). The dashboard builder imports the board
    # engine, so this single step rebuilds both CSVs and the page. Fail-soft:
    # an ESPN/MLB hiccup must not abort the pipeline (non-gating dashboard).
    ok_xfp_board = run(
        '4.55. Build merged xFP boards + xfp_board.html',
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


    # 4.10. Append today's per-player projection snapshot to the growing
    # panel at data/research/player_projection_history.parquet. Feeds the
    # opponent-action predictor's Δ-rank feature and any future per-player
    # residual analysis. Fail-soft.
    ok_pphist = run(
        '4.10. Append player projection history',
        'python -X utf8 scripts/xfp/build_player_projection_history.py',
        timeout=60,
    )
    if not ok_pphist:
        print('  ⚠ player projection history append failed — continuing (non-gating)')

    # 4.10a. Emit verdict-level decision records for the user's roster.
    # Scoped env var `PLV_LOG_DECISIONS=1` activates the env-gated logging
    # hook inside triangulate_player(). The var is scoped to THIS subprocess
    # only (via run(env=...)) and does not leak to subsequent steps.
    # Fail-soft — decision logging is observability only.
    ok_dec_log = run(
        '4.10a. Log roster decisions (PLV_LOG_DECISIONS=1)',
        'python -X utf8 scripts/xfp/log_roster_decisions.py',
        timeout=300,
        env={'PLV_LOG_DECISIONS': '1'},
    )
    if not ok_dec_log:
        print('  ⚠ roster decision logging failed — continuing (non-gating)')

    # 4.10b. Materialize the verdict-level decision log into a flat panel.
    # Walks data/research/decisions/ recursively, opportunistically settles
    # hitter decisions whose 21d window has elapsed (using statcast_{yr}.parquet),
    # and writes data/outputs/decisions_panel.csv. SP/RP settlement is not
    # implemented in this driver yet (see scripts/xfp/materialize_decisions.py).
    # NOTE: plan v11 called this "step 0.65 right after step 0.6"; the actual
    # projection-history persistence runs at step 4.10 (not 0.6), so we wire
    # immediately after 4.10 here. Fail-soft — panel is observability only.
    ok_decisions = run(
        '4.10b. Materialize decisions panel',
        'python -X utf8 scripts/xfp/materialize_decisions.py',
        timeout=120,
    )
    if not ok_decisions:
        print('  ⚠ decisions panel build failed — continuing (non-gating)')

    # 4.10c. Settle logged decisions vs realized FP + emit daily scorecard.
    # Walks data/research/decisions/, pulls actuals from the MLB Stats API
    # gameLog (H FP/PA, SP FP/start, RP FP/app), settles every ripe record,
    # and writes scorecard_{date}.{csv,md}. Idempotent + fail-soft.
    ok_settle = run(
        '4.10c. Settle decisions + scorecard',
        'python -X utf8 scripts/xfp/settle_decisions.py',
        timeout=180,
    )
    if not ok_settle:
        print('  ⚠ decision settlement failed — continuing (non-gating)')

    if not args.no_push:
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
        run('5. Commit xfp-model dashboards', commit_cmd, cwd=XFP_MODEL)
        # Pull-before-push: the cloud live-matchup job also pushes to xfp-model
        # throughout game days, so this local clone is often behind. Reconcile
        # first (this full build wins on conflict) so the push can't be rejected.
        run('6. Push to GitHub Pages',
            'git fetch origin && git merge -X ours --no-edit origin/main && '
            'git push origin main', cwd=XFP_MODEL)

    print(f'\n{"="*70}\n  ALL DONE — {datetime.now().strftime("%Y-%m-%d %H:%M")}\n{"="*70}')
    print(f'  Live: https://kejjeh.github.io/xfp-model/live_dashboard.html')
    print(f'  Matchup: https://kejjeh.github.io/xfp-model/matchup.html')


if __name__ == '__main__':
    main()
