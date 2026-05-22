# plv_clone

Fantasy-baseball model and decision tooling for the BrownU league (8-team H2H points). Single context: model, league mechanics, and decision skills share one vocabulary.

## Language

### League mechanics

**SP cap**:
The 10-starting-pitcher-starts-per-week limit. Only the first 10 starts in a scoring week count; starts 11+ are zero. There is no slot cap on SP roster positions, just on counted starts.
_Avoid_: pitcher cap, start limit.

**RP slot cap**:
The 4-active-reliever roster limit (distinct from SP cap, which is about counted starts not slot count).
_Avoid_: bullpen cap.

**IL slot**:
A roster position that holds an injured player without consuming an active slot. Distinct from **IL status** — a player can have `injured=True` while still occupying a non-IL slot, and vice versa. Free IL capacity is measured by `lineup_slot=='IL'`, never by `injured==True`.
_Avoid_: injury reserve, DL slot.

**IL status**:
A player's ESPN `injured` flag. Indicates the player is hurt; says nothing about which roster slot they occupy. See **IL slot**.

**FA pool**:
Free agents in the BrownU league — players not on any of the 8 rosters. Queries against the FA pool must verify availability against all rosters (cross-team check), because the ESPN free-agent endpoint can lag.
_Avoid_: waiver pool, available players.

**Connelly Early bug**:
The bug class where a player is recommended as a FA pickup despite being on another team's roster. Caused by skipping cross-team verification. The shape of `league_state.available_fa()` makes this unspeakable — the cross-team filter is internal, not a caller obligation.

### Models

**rh3**:
The validated production hitter rest-of-season projection. Lives at `src/plv_clone/models/xfp/rh3.py`. Artifact: `data/outputs/xfp_rh3_projections.csv`.
_Avoid_: rh, rh2, rh4 (research-stage), hitter projection (ambiguous).

**rp3**:
The validated production starting-pitcher rest-of-season projection. Lives at `src/plv_clone/models/xfp/rp3.py`. Per-start scale (not per-game). Artifact: `data/outputs/xfp_rp3_projections.csv`.
_Avoid_: rp, rp2 (research), pitcher projection (ambiguous — RPs use rprs2).

**rprs2**:
The validated production reliever rest-of-season projection. Lives at `src/plv_clone/models/xfp/rprs2.py`. Includes SV/HLD scoring. **RPs are ranked with rprs2, never rp3.**
_Avoid_: reliever projection (use rprs2 explicitly).

**FEATS list**:
The frozen feature vector for a production model — `RH3_FEATS`, `RP3_FEATS`, `FEATS_RPRS2`. Every feature in a FEATS list must appear in the **validated-signals registry** with matching `production_target`.

**Validated signal**:
A feature that has passed the 9-rule multi-testing protocol. Source-of-truth: markdown files in `data/research/validation_runs/` (frontmatter + body). Loaded into a typed `REGISTRY` by `src/plv_clone/models/xfp/validated_signals.py`. Import-time enforcement asserts every FEATS entry is registered for its model.
_Avoid_: feature (too generic), predictor.

**Rule 9 gate**:
The accountability check inside each per-model `fit_and_project`. Compares the model's `cross_year_r` against a baseline that drops v2-added features. Hard assert: `Δr ≥ 0.005`. Failure halts the pipeline — a v2 feature that doesn't beat its baseline cannot ship.

**Sustainability bucket**:
Confidence-layer classification applied on top of a model projection — `LEGIT / IMPROVING / STABLE / MIXED / NOISE / BAD_LUCK / REGRESS`. Distinguishes skill-driven from outcome-luck performance.

### Modules

**league_state**:
The module owning *read-side* league rules. Encodes IL-slot-vs-status, FA cross-team verification, and the `size=2000` default as method-level invariants. Lives at `src/plv_clone/league_state.py`. Replaces `app/espn_connector.py`. Imports `cap_math` for constants (`SP_CAP`, `RP_SLOT_CAP`, `IL_SLOT_COUNT`).
_Avoid_: espn_connector, espn_client, league_client.

**cap_math**:
The module owning *applied* league mechanics — the 10-start SP cap, `weekly_sp_projection`, IL slot arithmetic. Pure functions over data passed in; never imports `league_state`. Lives at `src/plv_clone/cap_math.py`.
_Avoid_: decisions, scheduler, optimizer.

**mlb_stats**:
The adapter module for the MLB Stats API. Owns `fetch_week_probables(week_start, week_end) → WeekProbables` and `resolve_mlbam(names) → dict[str, int]`. Keeps the remote dependency out of `cap_math` so cap math stays pure-over-data and testable with literals. Lives at `src/plv_clone/mlb_stats.py`.
_Avoid_: mlb_api, statsapi_client.

**xfp engine**:
The deep *toolkit* of shared model helpers — `build_marcel_prior`, `compute_population_means`, `apply_shrinkage`, `cross_year_eval`, `fit_residual_ci`, `lookup_sigma`, `train_final`, `compute_replacement_delta`, `write_model_pkl`. Lives at `src/plv_clone/models/xfp/engine.py`. **Not an orchestrator** — each per-model file (`rh3.py`, `rp3.py`, `rprs2.py`) owns its own `fit_and_project` and composes the toolkit. Per-model orchestration is code, not config.
_Avoid_: pipeline base class, model framework.

**Per-model file**:
`rh3.py`, `rp3.py`, `rprs2.py`. Each owns its FEATS list, its data paths, and its `fit_and_project()` orchestration. Calls `engine` toolkit helpers at load-bearing steps. Differs from sibling per-model files at the touchpoints the side-by-side trace surfaced (prior layering, external feature merges, v2 features, eligibility filter, post-train steps, bundle shape).

### Types

**SPStart**:
Frozen dataclass returned by `cap_math.weekly_sp_projection`. Fields: `pitcher_name`, `mlbam_id: int` (non-Optional — unresolved pitchers are skipped, never emitted with None), `start_date`, `opponent_team`, `projected_fp`, `counts_toward_cap: bool`.

**WeekProbables**:
Frozen dataclass holding pre-fetched MLB probables for a date range. Internal shape: `dict[(mlbam_id, date), opponent_team]`. Built by `mlb_stats.fetch_week_probables`; consumed by `cap_math.weekly_sp_projection`. The injection point that keeps cap_math testable with literal data.

**ValidatedSignal**:
Frozen dataclass in `validated_signals.py`. Fields: `name`, `formula`, `production_target` (`rh3` | `rp3` | `rprs2`), `validation_date`, `expected_sign`, `validation_run_path`.

## Flagged ambiguities

- **"Decision"** is deliberately not a module name. Skill drivers (`run_roster_audit.py`, `fa_replacement_pool`, etc.) live in `scripts/` as thin CLIs that consume `league_state` + `cap_math` + the model CSVs. The word describes what the user does with the output, not a code module.
- **"Bundle"** referred to the dict serialized by joblib in the old pipeline files. Renamed to `model_pkl` — the function is `engine.write_model_pkl`. The on-disk artifact is still `.pkl`, but no code calls the contents a "bundle."
- **"Production"** means "in the package" (`src/plv_clone/models/xfp/`). The package boundary is the production marker; `scripts/xfp/` holds research/lock/stale pipelines. Memory-file claims about which model is production are advisory; the import path is authoritative.

## Example dialogue

> **Dev**: "Can we recommend Connelly Early as a FA pickup?"
>
> **Coach**: "Only if `league_state.available_fa()` returns him. The method does the cross-team check internally — if he's rostered, he doesn't appear."
>
> **Dev**: "What if he's on the IL?"
>
> **Coach**: "If he's in an IL slot on another team, he's still rostered, still excluded. If you mean *our* IL — that's `league_state.il_slots()`, not the `injured` flag."
>
> **Dev**: "Okay. His projection?"
>
> **Coach**: "He's an SP, so look at rp3, not rh3 or rprs2. If he were a closer, you'd use rprs2."
>
> **Dev**: "I want to add a new bat-tracking feature to rh3."
>
> **Coach**: "Then the feature needs a validation run markdown in `data/research/validation_runs/` declaring `production_target: rh3` and `outcome: pass`. Once it's there, you can add it to `RH3_FEATS`. The import-time assert in `validated_signals.py` will refuse to load if you skip step one."
>
> **Dev**: "And the matchup dashboard for this week?"
>
> **Coach**: "`weekly_sp_projection(team_roster, week_start, week_end, rp3, probables, mlbam_lookup)`. Probables come from `mlb_stats.fetch_week_probables`. The function returns every projected start with `counts_toward_cap: bool` — the dashboard sums where True."
