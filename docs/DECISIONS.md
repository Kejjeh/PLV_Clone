# Decision log

Settled decisions. **Do not re-litigate these** — re-open one only with new
evidence, and say so explicitly. Architecture decisions live as ADRs in
`docs/adr/` (authoritative full text); methodology closures live in
`docs/memory/` and `data/research/validation_runs/`. Items marked
"(inferred)" were reconstructed from code/history rather than found stated.

## Architecture (ADRs — read the file before touching that area)

| ADR | Decision | Rejected alternative |
|---|---|---|
| [0001](adr/0001-engine-as-toolkit-not-orchestrator.md) | `models/xfp/engine.py` is a toolkit; each of rh3/rp3/rprs2 owns its own `fit_and_project()` | One `fit_and_project(config)` orchestrator — became config-as-code; the 3 pipelines diverge at 3 independent touchpoints |
| [0002](adr/0002-cap-math-via-injected-data.md) | `cap_math` is pure-over-data; `mlb_stats.py` owns the MLB API fetch and injects `WeekProbables` | cap_math fetching internally — hides a remote dep, untestable without mocks |
| [0003](adr/0003-validated-signals-registry-from-markdown.md) | Validation-run markdowns in `data/research/validation_runs/` ARE the signals registry; import-time assert blocks unvalidated FEATS entries | Typed Python registry as primary source — two sources of truth |
| [0004](adr/0004-league-state-omits-injured-players.md) | `league_state` deliberately has NO `injured_players()` method — IL accounting must use `lineup_slot=='IL'` | Method + docstring warning — was tried, callers used it wrong anyway |
| [0005](adr/0005-no-player-profile-lens-facade.md) | No `player_profile()` facade; skills import specific lens modules | Facade over `model_row` — shallow pass-through, invites over-fetch and lens misuse |
| [0006](adr/0006-snapshot-rating-no-deep-core.md) | No deep `rate_snapshot` core; the hard nuclei are already in `lib/archetype_engine.py` / `lib/sp_start_snapshots.py` | `RoleSpec` adapter layer over the 3 snapshot builders |
| [0007](adr/0007-skills-consolidation-scope.md) | Name normalization has TWO legitimate concerns; only projection-join `_norm`s merged onto `name_match.join_key` | "Merge all the `_norm`s" — the ESPN-ownership and triangulate normalizations are verified non-equivalent |
| [0008](adr/0008-lens-stack-as-context-metadata.md) | Lens stack is context metadata, never a projection input (enforced by tests, not discipline) | Folding lenses into FEATS — OOS study showed ΔR² ≈ 0 / negative |
| [0009](adr/0009-plv-legacy-subsystem-dormant-retained.md) | PLV/Process+ legacy subsystem: dormant, retained. **Addendum 2026-09-01**: the master_hitter position edge is SEVERED (live map via `player_positions.load_position_frame`), scripts-side drivers archived, weekly `plv update` retired; the PACKAGE stays (step 2.55 + tests + CLI) | Archive/delete the package too — still has live package-level consumers |

## Modeling methodology (closed research families)

- **RoS totals = rate × volume.** Rate models (rh3/rp3/rprs2) are per-PA /
  per-start; the volume companions convert to totals. Validated 2026-07-09.
  Never hand-multiply by flat PA/g or starts/wk when a volume row exists.
- **RPs rank by rprs2, never rp3.** rp3 is SP-only scale.
- **SP trajectory/recency-trend is non-predictive** (2026-06-24, Δr ≈ 0 AND
  ΔAUC ≈ 0). Downside → `floor_adj_xfp`/`floor_flag`; decline type →
  `stuff_cmd_tag`. Both context-only.
- **In-season "different player now" is CLOSED** — five independent attempts;
  ~89% of apparent change is sampling noise. Event-given split: judge at
  z > 1.83; searched-for split: SP 2.58 / hitters 2.79. Nothing
  regime-derived may move rh3/rp3/rprs2. (Late-Aug 2026 "new-leaf" family
  re-confirmed with multiple recorded negative results.)
- **Hitter in-season rate DELTAS add ~0** — family closed, no re-open
  condition left. Anchor on season level; L21d for recent form; L7 only for
  bat speed. Bat-speed trajectory never moves a rank.
- **Lens stack is conviction/conflict surfacing only** (2026-06-11 OOS study:
  ΔR² +0.006 H n.s. / −0.014 SP; the apparent +0.033 was L7 leakage).
- **Forward calibration is deliberately conservative** — the small
  under-projection on regulars is GOOD. No intercept, no shading, no reduced
  shrinkage.
- **Boom/bust cutoffs recalibrated 2026-06-28** to empirical ~p78/p22
  quantiles (SP boom 20→17; hitter 10/2 was useless).
- **`n_pos_flags` / composite rolling-trend flag validated as noise**
  (2026-05-11). Never rank or filter FAs on them.
- **Read the OUTCOME for hitters, the PROCESS for pitchers.** Hitter FP level
  beats rate metrics; SP K% beats the SP's own FP level. Walks invert: the
  walk belongs to the batter.
- **Two statistical traps checked in every study** (don't-do #17): never
  compare r across frames; assert `1/(B+1) < q/M` before believing a BH-FDR
  result.

## League/process decisions

- **P(win) is the roster objective, not expected FP.** One engine
  (`lib/leverage_engine.py`); title-equity curve prices a weekly win
  (period 15 = 2.67pp vs period 17 = 0.88pp). Run the optimizer BEFORE any
  move — unevaluated moves can't be graded.
- **4 true RPs is a FLOOR** (Josh's standing rule, 2026-07-18): RP drops are
  only ever RP-for-RP.
- **SP-start cap is period-aware**: `10 × weeks`, ASG-block override 16.
  Always via `plv_clone.cap_math.sp_cap_for_period`.
- **New model features require `/validate-feature`** (9-rule protocol);
  Rule 9 baseline must include ALL existing production features (the rh3/rp3
  v2 lesson: stripped baselines over-claimed lift 4×).

- **Never-pairable decision records get a TERMINAL ungradeable mark**
  (2026-09-01, closed issue #54): UNSETTLEABLE + `ungradeable: true` +
  per-population reason, written only past the 2-day attribution horizon,
  invisible to §7-§9 scorecard math. Rejected alternative: proxy actuals
  for unrostered FAs — grades a counterfactual nobody measured.
- **Hitter positions come from the live MLB-API map** (2026-09-01,
  ADR-0009 addendum): `player_positions.load_position_frame(year)`,
  nightly cache in `data/reference/`. Rejected: ESPN `get_all_teams()`
  (covers only ~230 league-rostered players — misses the FA/call-up case)
  and per-consumer fetches (single-owner doctrine).

## Repo/process decisions

- **CLAUDE.md is budget-capped and two-sided-ratcheted**
  (`tests/test_claude_md_budget.py`, issue #46: it had drifted to 635 lines).
  Detail goes in `docs/memory/`; one headline line in CLAUDE.md. Numbered
  gotchas/don't-dos are cited by number in memos — retire in place, never
  renumber.
- **Two-repo split is intentional**: plv_clone private working repo;
  `xfp-model/` (nested, gitignored, its own git repo) is the public GitHub
  Pages artifact.
- **Tests run through `scripts/ci/run_summary.py`**, never raw pytest —
  full log cached to `.cache/test-logs/`, compact summary printed. Coverage
  is opt-in (5.1× slowdown measured, audit 2026-08-01 item 53).
- **Behavior-preserving refactors are refereed by `scripts/ci/golden_run.py`**
  (A/B byte-identical outputs with input-hash freezing).
- **xgboost is a HARD dependency** (2026-08-27): `nonlinear_ceiling` takes
  max(xgb, rf); degrading to RF-only silently weakens the Rule-9 gate.
- **Daily refresh runs on a self-hosted runner in Josh's real working tree**
  (not a fresh checkout) so hardcoded roots, `.env`, the sibling repo, and
  git credentials work unchanged. (inferred: chosen for pragmatism over
  hermeticity — do not "fix" by moving it to a hosted runner without
  addressing all four of those dependencies.)
- **Player identity is MLBAM-id-anchored everywhere**; name matching is
  two-pass (full normalized, then last + first-initial), never last-only,
  never `str.contains`. A large test family pins this.
