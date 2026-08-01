# Production audit — 2026-07-30 (six-surface, TDD-shipped)

Method: the `/production-audit` five-wave process extended to SIX read-only
surfaces (the four canonical ones + the 2026-07-29 decision layer, absent from
the July audit, + a TDD lens on the test suite itself), then dedupe/rank, then
one adversarial verifier per top finding (the July audit measured 2/30 findings
stale-or-wrong; this round the verifiers REFUTED 1 of 12 and downgraded the
severity of 5 — the verify pass keeps earning its cost). 64 raw findings ->
52 after dedupe/known-backlog drop -> top 12 verified: 11 CONFIRMED, 1 REFUTED.
Implementation: strict red-green-refactor per behavior (see the cycles in each
track's tests); every fix track adversarially reviewed before commit.

Registry drift check (step 3): tests/test_skills_registered.py 92 passed;
cheat-sheet grep clean — no dead skill names.

## CONFIRMED + SHIPPED (11)

### C1 [important] scripts/xfp/lib/leverage_engine.py:789 — Candidate draw cache and RNG key on `mlbam or 0`, so every identity-less candidate reuses the first one's draws

- category: correctness · effort S · surface decision
- fix: Make the cache/RNG key identity-complete: fall back to the roster path's `_draw_key` (`id:<mlbam>` else `nm:<_norm(name)>`) instead of collapsing to 0, and seed `candidate_rng` from a hash of that key. Refusing to score an unidentifiable candidate is an acceptable alternative; silently serving another player's array is not.
- spec: The optimizer scores two identity-less candidates independently: given two FA candidates whose mlbam never resolved and whose projections differ, each candidate's scored distribution reflects its own projected mean, and swapping their order in the pool leaves both ΔP(win) values unchanged.
- verifier: MECHANISM CONFIRMED (executed). Code at scripts/xfp/lib/leverage_engine.py:789 reads `key = (int(cand.get('mlbam') or 0), bucket, cand.get('effective_date') or '')` and :794 `rng = candidate_rng(D['seed'], cand.get('mlbam'), bucket)`, exactly as cited. Read-only probe (two identity-less hitter candidates, projected totals 60.0 vs 12.0, same D):

### C2 [important] scripts/xfp/lib/dpwin_history.py:66 — Upsert dedup key treats unresolved ids as one player, silently evicting ~15-18% of every run's counterfactual surface

- category: silent-failure · effort M · surface decision
- fix: Add identity columns that are never a shared sentinel (`add_key`/`drop_key` built from `_draw_key` semantics) and put those in KEY_COLS instead of the raw `_mlbam` sentinels. Keep `_norm_mlbam(0)` only for the genuinely-not-applicable leg (a pure drop has no add). Separately, count and warn on evicted keys.
- spec: The dpwin panel preserves every evaluated candidate: given one run in which two distinct add candidates with unresolvable ids are each paired with the same drop, both rows are readable back from the panel afterwards and the stored row count equals the number of candidates the run evaluated.
- verifier: CORE DEFECT CONFIRMED BY EXECUTION; two of the finding's supporting claims are wrong, which is why I downgrade blocking -> important.

### C3 [important] scripts/xfp/reconcile_decisions.py:122 — Every executed move is bucketed 'H' because transactions_history.position is empty for all 410 rows

- category: silent-failure · effort M · surface decision
- fix: Stop deriving the bucket from a column this store never populates. Resolve it from the matching dpwin row's `add_bucket` (already joined by run_id), MLBAM primaryPosition via the collision-safe resolver, or membership in the rp3/rprs2 projection maps; when no source yields a bucket, record `bucket=None` and count the move as unattributable rather than defaulting to 'H'. Also correct the module docstring's 'TWO REALITIES OF THE ACTUAL DATA' block, which documents the NaN mlbam_id but not the empty position.
- spec: The reconciler files an executed pitcher add in the pitcher bucket: given a transactions row whose position is blank and whose player is a known SP, the created record's bucket is 'SP', its rejected alternative is drawn from same-bucket SP candidates, and its realized totals come from the pitching game log.
- verifier: CORE DEFECT CONFIRMED, STATED IMPACT REFUTED. Severity drops blocking -> important.

### C4 [important] scripts/xfp/lib/bucket_dispatch.py:56 — resolve_player() silently returns the wrong player on a name collision and never consults KNOWN_COLLISIONS

- category: silent-failure · effort M · surface libs (correctness) + tests (coverage) — one defect, one fix; the tests surface's 'pin current first-row-wins behavior' proposal is explicitly rejected in favour of refusing to guess
- fix: Consult `plv_clone.utils.name_match.KNOWN_COLLISIONS` before the `_key` join; on an unresolvable multi-match return None with a loud message instead of iloc[0]; widen `hint` to accept an optional team/position disambiguator. Byte-identical for the 473 unambiguous names — only the ambiguous case changes, from 'silently wrong player' to 'no answer'.
- spec: The triangulate resolver refuses to return a player when two rows in the projection pool share a name key and the caller supplied no disambiguator, and returns the Athletics Max Muncy when the caller names that team.
- verifier: CONFIRMED as a real defect; severity revised blocking -> important. Tried to refute on four fronts (stale code, upstream guard, prior-art duplicate, live-impact); the code claim survived, the "blocking" framing did not.

### C5 [important] scripts/xfp/build_index_dashboard.py:123 — Name-keyed roster/projection dicts collapse the Max Muncy collision — the shipped dashboard labels BOTH mlbIds as roster "mine"

- category: correctness · effort M · surface engines
- fix: Join on MLBAM id where both sides have one — ESPN's MY_TEAM payload already supplies `mlbId` (:666) and the projection CSVs supply `batter`/`pitcher`. For name-only paths use `build_safe_name_index` + `safe_lookup(name, index, team=)` (the pattern run_roster_audit.py:56-70 already uses) so an ambiguous key returns None and the row is skipped. Add a build-time assertion that no two records collapse to one key without a team tiebreak.
- spec: The published index dashboard gives each distinct MLBAM id its own ownership label and its own projection row: when two players share a name, only the one on the user's ESPN roster is marked as owned and the other keeps its own xfp values.
- verifier: TRIED TO REFUTE ON FIVE FRONTS; ALL FAILED. The finding survives.

### C6 [important] scripts/xfp/lib/roster_rules.py:179 — check_swap reports pre-existing roster deficits as violations of the proposed move, so one IL'd RP blocks every candidate

- category: correctness · effort S · surface decision
- fix: Make the floor checks relative to the move (`before_c['RP'] >= RP_FLOOR and after_c['RP'] < RP_FLOOR`), likewise for the active-pitcher count, and surface an already-below-floor roster once as a run-level warning rather than attaching it to every candidate. The RP-for-RP rule at :183-189 already handles the at-the-floor case correctly and must stay.
- spec: A move that does not touch the constrained bucket stays legal under a pre-existing shortfall: with one RP on the IL and three active, a hitter-for-hitter swap is reported legal, while dropping an active RP for a non-RP is still blocked by the standing floor rule.
- verifier: CORE DEFECT CONFIRMED BY EXECUTION — but the rank justification is refuted, so this belongs at the bottom of "important", not above the attribution defects.

### C7 [important] scripts/xfp/build_sp_alerts.py:149 — Nightly FA-SP alert engine falls back to last-name + first-INITIAL matching against the FA pool

- category: correctness · effort S · surface engines
- fix: Delete the last-name/first-initial fallback and resolve both sides through `resolve_pitcher_id(name, team=, role='SP')`, comparing MLBAM ids against the id set of `LeagueState.available_fa(position='SP')`. When an id cannot be resolved on either side, treat the pitcher as NOT-FA and print a one-line skip breadcrumb — losing an alert beats inventing one.
- spec: The SP alert board never lists a pitcher as a free agent when another team's roster holds him, even when a genuine free agent shares his surname and first initial.
- verifier: CONFIRMED by execution against production inputs; two supporting details in the finding's rationale are wrong but do not touch the defect.

### C8 [important] scripts/xfp/reconcile_decisions.py:141 — find_run attributes a transaction to a dpwin run generated LATER the same day, leaking hindsight into the ledger

- category: correctness · effort S · surface decision
- fix: Compare against the run's full `generated_at` timestamp (already stored on every row) and select the latest run with `generated_at <= ev['when']`, still bounded below by ATTRIBUTION_DAYS. When every run in the window post-dates the transaction, report the move as unattributed — that outcome is already supported and is the honest state.
- spec: A move is graded only against a surface that existed before it: given a transaction executed at 09:00 and dpwin runs at 00:30 and 10:42 the same day, the reconciler attributes the move to the 00:30 run, and given only the 10:42 run it reports the move as unattributed.
- verifier: CODE READ (scripts/xfp/reconcile_decisions.py:136-150) — cited mechanism is exactly as described. `lo = (when_date - timedelta(days=ATTRIBUTION_DAYS)).isoformat()`; `sub = hist[(hist['snapshot_date'].astype(str) <= when_date.isoformat()) & (... >= lo)]`; `runs = sorted(sub['run_id'].unique()); chosen = runs[-1]`. Call site :216 is `run_id, note = find_run(hist, ev['date'])` — it passes `ev['date']

### C9 [minor] scripts/xfp/settle_decisions.py:580 — Paired counterfactual settlement is computed then discarded for every name-only record, and re-fetched every night

- category: silent-failure · effort M · surface decision
- fix: Persist the paired settlement independently of the residual path — when `_settle_counterfactual_one` produced a block, write the mirror regardless of residual status — and make step 0's skip-gate consult the existing mirror. Add `paired_settled` to the returned summary and the printed line. Note the adjacent mislabel this exposes: on the resolved-id branch a record counted as `newly_settled` with `settlement: None` lands in `_build_scorecard`'s total but in no classification.
- spec: A decision with a recorded alternative is graded even when the chosen player's id never resolved: after settlement runs, the record's counterfactual settlement is readable from disk, and a second run reuses it without issuing another game-log fetch.
- verifier: MECHANISM CONFIRMED BY EXECUTION, HARM MATERIALLY NARROWER THAN WRITTEN -> severity important -> minor.

### C11 [important] scripts/xfp/reconcile_decisions.py:45 — The reconciler is unscheduled and its documented executed_at stamping step is unimplemented; zero v3 records exist

- category: coverage-gap · effort S · surface decision
- fix: Either wire the reconciler into refresh_dashboards immediately after step 1's persist_transactions (fail-soft, like settle_decisions at :792) and implement the documented stamping step, or correct the docstring to say it is manual-only and drop the unused `is_executed_record`/`DecisionRecord`/`DECISIONS_ROOT` imports. The current state is the worst of both.
- spec: The nightly pipeline closes the ledger loop: after a refresh cycle that persists a transaction for which a dpwin surface exists, an executed record for that move is readable from the decisions tree.
- verifier: Tried to refute on four fronts (wiring, stamping, unused import, record count); all four survived. Every sub-claim verified by direct read or execution.

### C12 [important] scripts/xfp/build_matchup_dashboard.py:1638 — render_playoff_simulation hardcodes 'assumes 4 prior wins', so matchup.html publishes a playoff probability of exactly 0.0% by arithmetic

- category: correctness · effort S · surface engines
- fix: Either drop the section and surface season_sim.json's title/playoff odds (one engine, not two), or read actual current wins from `LeagueState.standings()` and derive the seeding cutoff from the standings table instead of the literals 12 and 4. Either way the section must refuse to render rather than print 0.0% when the threshold is unreachable given remaining_periods.
- spec: The matchup page's playoff-probability figure moves when the team's current win total changes, and never reports 0.0% purely because the remaining schedule is shorter than a hardcoded win requirement.
- verifier: CONFIRMED — attempted refutation on five fronts, all failed; the finding is understated if anything.

## REFUTED (1)

- R10 "Reconciler collapses two same-day moves on one player to a single file"
  — the cited mechanism (one event per swap leg) is wrong and all three cited
  instances were disproved by execution: collapse_swaps groups by ts_ms and
  pairs one add + one drop per timestamp. Recorded so it is not re-derived.

## BACKLOG — ranked, UNVERIFIED (41; verify before acting, per house rule)

- T13 [important/correctness] scripts/xfp/refresh_dashboards.py:641 (S) — index.html publishes `window.XFP_DECISION = null` every night — the Decision tab has been dead for nine consecutive publishes
- T14 [blocking/silent-failure] scripts/xfp/build_rp_archetypes.py:304 (S) — RP leverage/IR joins have no coverage or staleness guard; 2026 gmLI coverage has silently fallen 100% → 80.2% on caches last written 2026-05-30
- T15 [important/silent-failure] scripts/xfp/refresh_all.py:119 (M) — refresh_all continues past a failed substrate stage, so model stages overwrite shipped projection CSVs from yesterday's substrate
- T16 [important/silent-failure] scripts/xfp/refresh_dashboards.py:864 (S) — PUBLISH GATED exits 0, so the nightly workflow reports success and still commits the stale-projection data
- T17 [important/silent-failure] scripts/xfp/refresh_dashboards.py:68 (S) — A timed-out step is abandoned, not killed — the worker python keeps running and writing while the pipeline moves on
- T18 [important/correctness] scripts/xfp/lib/volume_model.py:203 (S) — All three volume pipelines' pre-registered LOO gates are scored on a model trained on rows the shipped model never sees
- T19 [important/drift] scripts/xfp/run_decision_trend.py:44 (S) — Decision-trend prints chase%/z-swing% off a 15-pitch window against stabilization.py's measured 150-pitch minimum
- T20 [important/drift] .github/workflows/monday-brief.yml:5 (S) — monday-brief.yml claims the daily refresh writes four decision-layer artifacts that no scheduled job produces
- T21 [minor/silent-failure] scripts/xfp/lib/title_equity.py:156 (S) — A season_sim payload with no `period` key is labelled 'fresh' rather than unknown-staleness
- T22 [minor/correctness] src/plv_clone/decisions/counterfactual.py:85 (S) — Settlement window truncates executed_at to a date, crediting both players a day the decision could not affect
- T23 [minor/correctness] scripts/xfp/run_weekly_optimizer.py:210 (S) — `n_rem_games` is populated with `units`, forcing an RP candidate's appearance probability to 1.0
- T24 [minor/correctness] scripts/xfp/lib/leverage_engine.py:817 (S) — Candidate hitter draws mix denominators — per-game rate over `units` but game count over `round(units)`
- T25 [minor/drift] scripts/xfp/lib/leverage_engine.py:593 (S) — `if e['model_fp'] > 0` still guards the EV retarget — a leftover from the removed multiplicative rescale
- T26 [minor/silent-failure] .github/workflows/daily-refresh.yml:80 (S) — The tripwire alert step re-reports last Monday's scorecard all week with no age threshold
- T27 [minor/silent-failure] scripts/xfp/refresh_boxscores.py:229 (S) — Per-game boxscore failures are printed but never counted, so a partial pull reports success with a silently short game count
- T28 [minor/silent-failure] scripts/xfp/build_statcast_gf_bridge.py:185 (S) — gf-bridge drop tripwire divides by newly-appended rows instead of mapped pitches, so a --start repair run can fire a false schema-drift warning
- T29 [minor/silent-failure] data/outputs/xfp_rp3_projections.csv:1 (S) — Two rows in the shipped rp3 projections have a null player_name, making them unreachable by every name-keyed board join
- T30 [minor/silent-failure] scripts/xfp/build_matchup_dashboard.py:3417 (S) — 11 of 17 matchup.html section builders lack the file's own _section_error guard
- T31 [important/coverage-gap] .github/workflows/daily-refresh.yml:44 (M) — Nothing runs pytest — the 1,367-test suite gates neither commits nor the nightly publish
- T32 [important/coverage-gap] scripts/xfp/refresh_dashboards.py:858 (M) — The publish gate (audit F2) — the guard that stops stale projections shipping to Pages — has no test at all
- T33 [important/coverage-gap] scripts/xfp/lib/disk_cache.py:81 (M) — The disk cache that feeds rh3/rp3/rprs2 training rows has zero tests and swallows every error
- T34 [important/coverage-gap] scripts/xfp/lib/variance_bands.py:54 (S) — fallback_sigma — the sigma source for all three Monte Carlo engines — has no behavioral test and degrades to the caller's default in silence
- T35 [important/coverage-gap] scripts/xfp/lib/volume_model.py:1 (M) — volume_model — the shared expected-playing-time engine behind all three volume pipelines — has no test file
- T36 [important/coverage-gap] tests/test_contract_schemas.py:103 (S) — Eight export 'contract' tests assert a hand-written fixture against the constant it was copied from
- T37 [important/drift] pyproject.toml:55 (S) — Coverage config claims to measure the whole production surface but silently drops scripts/xfp — 125k of 146k lines
- T38 [minor/coverage-gap] tests/test_verdict_backtest_hosts.py:66 (S) — About 250 tests are data-presence-gated — green here, green-by-skipping on any checkout without built artifacts
- T39 [minor/coverage-gap] tests/test_bat_speed_daily.py:183 (S) — A refresh-registration guard passes on a docstring: `assert "1.65" in src`
- T40 [minor/drift] tests/test_audit_regressions_0704.py:78 (M) — Refresh producer/consumer ordering is pinned only by substring index into main()'s source text
- T41 [important/duplication] scripts/xfp/xfp_rp_volume_pipeline.py:147 (M) — RP volume pipeline keeps local forks of four hoisted helpers, and its attach_team_games fork lacks the unmapped-team visibility guard
- T42 [important/drift] scripts/xfp/refresh_dashboards.py:144 (S) — Nightly driver pins the season year to 2026 in three ingestion steps whose scripts already default to the current year
- T43 [minor/drift] src/plv_clone/models/xfp/rh3_april.py:364 (S) — rh3_april still hardcodes year == 2026 after its three siblings were migrated to the latest-substrate-year idiom
- T44 [minor/drift] scripts/xfp/run_positional_board.py:40 (S) — Positional board's SP rest-of-season column is frozen at a June-15 horizon (18.4 starts) while its hitter and RP columns are date-aware
- T45 [minor/drift] scripts/xfp/run_decision_trend.py:66 (S) — Decision-trend resolves both data inputs by bare relative path and its default roster store is 13 days stale with no producer script
- T46 [minor/hygiene] .gitignore:1 (S) — 213 dated free-agent pool parquets are tracked in git against CLAUDE.md's no-parquet rule, and no consumer reads any of them
- T47 [minor/hygiene] tests/test_repo_root_paths.py:37 (M) — The repo-root guard only covers the parents[N] form, leaving 148 hardcoded machine-specific absolute paths untested
- T48 [minor/hygiene] scripts/xfp/build_index_dashboard.py:775 (L) — build_index_dashboard.py is 4,981 lines, 71% of it a single f-string holding the whole React app
- T49 [minor/hygiene] scripts/xfp/build_sp_archetypes.py:206 (S) — build_ratings_panel takes a current_year=2026 parameter that neither archetype builder ever reads
- T50 [minor/drift] scripts/xfp/build_index_dashboard.py:4931 (S) — Stale step-number references survive the 2026-07-19 renumber: two files still point at 'step 4.52'
- T51 [minor/hygiene] scripts/xfp/refresh_dashboards.py:198 (S) — `ok_bs` is bound twice — the boxscore-bridge result is shadowed by the bat-speed step
- T52 [minor/perf] scripts/xfp/xfp_rp_volume_pipeline.py:119 (M) — RP volume pipeline re-reads all eight season statcast parquets uncached every night
- T53 [minor/perf] pyproject.toml:47 (S) — addopts forces --cov and -v on every invocation and never deselects `slow`

Notable in the tail (verify first): T14 (RP gmLI join coverage silently 100%->80.2%,
flagged blocking by its finder), T31 (nothing runs pytest in CI — the 1,367-test
suite gates neither commits nor the nightly publish), T16 (publish gate exits 0 so
the nightly reports success while shipping stale projections), T37 (coverage config
silently omits scripts/xfp — 125k of 146k lines unmeasured), T13 (index.html
Decision tab dead nine nights).

## IMPLEMENTATION RECORD (same day, TDD)

All 11 confirmed findings shipped via strict red-green-refactor — 27 recorded
red-green cycles across 5 tracks, every red either observed against pre-fix
code (verifiers replayed them from git HEAD scratch copies) or a DISCLOSED
mutation-red where the fix necessarily preceded the test. Each track was then
adversarially reviewed; the review round found and we fixed:

- collision gate OVER-refusal: hintless /triangulate broke for pool-unique
  KNOWN_COLLISIONS names (Will Smith, Jacob Wilson, Luis Garcia Jr.) — refusal
  now decided by ambiguity IN THE POOLS, with a visibility breadcrumb on the
  single-candidate path;
- the index dashboard's MY_TEAM merge still joined by the lossy name dict —
  now mlbId-first at both merge sites;
- reconciler stamping now honors ACTION KIND (an executed add never closes a
  logged drop), survives list-shaped scorecard JSON, and the two neighbor
  ledger tests were made hermetic (explicit roots);
- _bucket_via_resolver got its positive test (mutation-verified);
- roster_rules floors now fire on crossing OR worsening (the below-floor
  blind spot), and preexisting_shortfalls() is actually wired into the
  optimizer's run header;
- the playoff-sim staleness bar imports title_equity.STALE_PERIOD_HARD
  instead of duplicating it;
- materialize_decisions skips the settled/ mirror subtree (no double-load);
- _stable_ident_int coerces float-integral mlbams like _draw_key;
- the dpwin name-fallback key now normalizes through the CANONICAL join_key
  (the W8 no-new-normalizers guard caught the track's hand-rolled copy in the
  full-suite run — the guard working exactly as designed);
- dpwin_history legacy-parquet migration got a committed, mutation-verified
  test.

Suite: 1,367 -> 1,404 passed, 0 failed.
