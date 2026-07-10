# opp-watch v2 refit — panel-data weight refit + honest backtest

Date: 2026-07-10
Owner: opponent_action_predictor.py (v1 → v2 candidate)
Status at write time of this header: **PRE-REGISTERED, no results computed yet.**
Results are appended below the marker line only after the design was frozen.

## Why now

v1 (2026-06-04) uses hardcoded per-team behavioral profile weights. The plan
(hidden-percolating-harp — plan file itself no longer on disk; design intent
preserved in the engine docstring) deferred a panel refit until
`player_projection_history.parquet` + date-keyed `pl_cache` snapshots had
accumulated ~4 weeks. As of 2026-07-10: 26 projection snapshots
(2026-06-04 → 07-10), 33 dated pl_cache files, daily `triangulate_nightly_*`
snapshots (06-23 → 07-10) with date-keyed `arche_traj`/`owner_team`, and
`transactions_history.parquet` with 371 ledger rows (03-24 → 07-09).

The original pre-registered gate ("backtest at least as well on the LNB
canonical adds") was UNCLEARABLE (canonical adds predate the panel). Per the
docstring's own escape hatch, this refit **re-anchors the test set to
in-panel-window adds and re-pre-registers** — that is this document.

## Pre-registered design (frozen before results)

### Event set

- Event = `FA ADDED` or `WAIVER ADDED` by any of the 8 BrownU teams,
  add date in **2026-06-05 → 2026-07-09** (needs a projection snapshot
  strictly before the add date, ≤7 days stale, else event dropped).
- In-window raw count checked before design freeze: **61 adds** (≥40
  powered threshold). Per-team: NYL 17, LNB 12, Frendy 8, Solomon 8,
  2015 6, EdwinDiaz 6, Boone 4, TreasureIsland 0.
- Josh's own team (New York Ligers) is INCLUDED in the training pool for
  power; pooled-excluding-NYL reported as a sensitivity (deploy use case
  is opponents).
- Player resolution: `mlbam_id` from the ledger when present (59%
  in-window); else normalized full-name `join_key` match against the
  projection panel, **skip-on-ambiguous** (Rule 10 — full-name normalized
  match, never last-name contains).

### Candidate pool per event (leakage-safe)

- As-of date A = latest projection snapshot date **strictly before** the
  add date D.
- Pool = all players in snapshot A **minus** players rostered as-of A per
  an ownership ledger reconstructed from `all_team_rosters.json`
  (2026-06-04 baseline) rolled forward through the transaction ledger in
  timestamp order. The added player is forced into the pool (they were an
  FA by definition immediately before the add).

### Features (all as-of A; identical inputs feed both v1 and v2 arms)

1. `pl` — PL-rank score from the latest pl_cache file dated ≤ A for the
   bucket (SP: `pl_sps_top100_*`/`pl_top100_*`; H: `pl_hitters_top150_*`;
   RP: `pl_closers_*`); v1 mapping `1 − rank/150` (H) / `1 − rank/100`
   (SP/RP), 0 if unranked.
2. `traj` — v1 mapping (TRENDING_UP=1 / STABLE=0.5 / else 0) from the
   latest `triangulate_nightly_*` ≤ A; events before 06-23 backfill from
   the 06-23 file (arche_traj is slow-moving; small staleness noted,
   applied EQUALLY to both arms).
3. `model` — v1 mapping `max(0, 1 − model_rank/100)` from the projection
   panel rank as-of A.
4. `outcome` — v1 mapping `clip((replacement_delta + 0.5·recency_form_gap)/1.5, 0, 1)`
   from the panel as-of A.
5. `role` — v1 mapping (RP & signal add = 1.0 / RP = 0.4 / else 0).
6. `d7` — Δ-rank over trailing ~7d: `(rank_{A−7} − rank_A)/100`, nearest
   snapshot to A−7 within ±3d, clipped [−1, 1], 0 if missing (rising = +).
7. `d14` — same at ~14d.
8. `fp_l7` — recent-performance salience: total BrownU FP in the 7 days
   before D from the boxscore store (mlbam-keyed), `clip(fp/30, 0, 1.5)`.
9. `v1_prior` — v1's own add score computed with the ACTING team's
   hardcoded profile weights over components 1–5. This is how per-team
   behavior enters v2.

### Learner + per-team choice (stated per task)

- **Pooled logistic regression** (sklearn, L2, C=1.0,
  class_weight='balanced'); positives = the added player row per event,
  negatives = every other candidate in that event's pool.
- **Per-team weights are fully shrunk to pooled**; team-specific behavior
  enters ONLY through the `v1_prior` feature (zero extra df). Reason:
  max per-team n in-window is 17 (own team) / 12 (LNB); all others ≤8 —
  per-team interactions or separate fits would overfit at this n
  (Rule 5: below n=5 per team, pooled-only claims).
- v2 deploy score = the fitted linear index over the same features;
  output shape (ranked add candidates + components) unchanged so
  /opp-watch keeps working.

### Backtest (chronological, honest)

- Order events by add timestamp; **train = first 70%, test = last 30%**.
  No refit, no threshold tuning on the test slice.
- Primary metric: **top-12 hit rate** — is the actually-added player in
  the arm's top-12 scored candidates for that event? Secondary: top-25
  hit rate, median rank of the added player.
- v1 arm = `_score_player_for_add` with the acting team's profile over
  the SAME as-of features. v2 arm = fitted model. Identical pools.
- Per-team hit rates reported with n; teams with test n<5 are
  pooled-only claims (Rule 5).

### Ship rule (frozen)

- v2 replaces v1 default weights **only if pooled top-12 hit rate on the
  held-out slice ≥ v1's**. Ties → prefer v2 (maintainability; refitable
  from data), and say so. v1 stays available behind `--weights v1`.
- Trigger stage (P(transact 24h)) is NOT refit here — separately
  calibrated in v1; out of scope.
- Drop-side scoring is NOT refit — its marginal-upgrade term consumes the
  add scores, so it inherits v2 automatically if shipped; its intrinsic
  weights stay v1. Stated scope limit.
- If usable events after resolution/pool filtering fall below 40 total:
  report UNDERPOWERED, keep v1, write the powered date.

---- RESULTS BELOW THIS LINE WERE APPENDED AFTER THE DESIGN FREEZE ----

## Results (2026-07-10, harness `scripts/xfp/refit_opp_watch_v2.py`)

### Panel

- Usable events: **56 of 61** in-window adds (skipped: 4 add-player-not-in-
  snapshot — mostly just-called-up rookies absent from the projection
  universe; 1 snapshot-too-stale >7d during the 06-08→06-14 snapshot gap).
- Per-team n (full window): NYL 15, LNB 11, Solomon 8, Frendy 7, 2015 6,
  EdwinDiaz 5, Boone 4, TreasureIsland 0.
- Chronological split: **train 39 events (2026-06-06 → 06-29), test 17
  events (06-29 → 07-09)**.

### Held-out top-12 hit rate (primary metric)

| arm | TEST top-12 | TEST top-25 | TEST median rank | TRAIN top-12 |
|---|---|---|---|---|
| v1 (hardcoded profiles) | **3/17 (17.6%)** | 4/17 (23.5%) | 95 | 5/39 (12.8%) |
| v2 (panel refit)        | **10/17 (58.8%)** | 11/17 (64.7%) | 8 | 12/39 (30.8%) |

Sensitivity excluding Josh's own team (deploy use case = opponents):
v2 **7/12 (58.3%)** vs v1 **2/12 (16.7%)**.

Per-team TEST (Rule 5: every team is below n=5 except NYL/LNB at exactly
n=5 — treat per-team rows as descriptive only; claims are POOLED):
NYL 3/5 vs 1/5 · LNB 4/5 vs 1/5 · Solomon 2/3 vs 1/3 · Frendy 0/2 vs 0/2 ·
2015 0/1 vs 0/1 · EdwinDiaz 1/1 vs 0/1 (v2 vs v1).

### Gate decision: **SHIP v2** (58.8% ≥ 17.6%, not a tie)

Deploy weights refit on the full 56-event window and written to
`data/research/opp_watch_v2_weights.json`:

```
pl +3.006 · traj +0.280 · model +3.563 · outcome +0.456 · role −5.227
d7 −1.206 · d14 +0.744 · fp_l7 +3.508 · v1_prior +1.211 · intercept −2.227
```

Reading: managers chase **PL rank, our-model rank, and last-7-day box-score
heat** far more than v1 assumed; the big NEGATIVE `role` coefficient says
RPs are added much less often than their FA-pool share (v1 over-weighted
the role-change RP heuristic — its v1-mode top adds were all RPs; actual
LNB adds that day were SP/H). `d7` negative with `d14` positive ≈ managers
react to the ~2-week rise, not the last-3-days blip. `v1_prior` stays
positive — the per-team profiles carry real residual signal and remain in
the model as the only per-team term.

### Engine changes shipped

- `scripts/xfp/opponent_action_predictor.py`: v2 scorer
  (`_score_player_for_add_v2`, sigmoid of the fitted linear index → same
  [0,1] scale so the drop-side marginal-upgrade term is unchanged),
  `load_v2_weights()`, `_build_v2_extras()` (deploy-time d7/d14/fp_l7,
  mlbam-keyed via unambiguous normalized full-name map — Rule 10),
  `--weights {v2,v1}` CLI flag (default v2, auto-fallback to v1 when the
  weights json is missing). Trigger stage + drop intrinsic weights + report
  shape untouched; /opp-watch contract preserved.

### Honest caveats

- TEST (58.8%) > TRAIN (30.8%) for v2 is small-n variance (no tuning
  touched the test slice); the 17-event test CI is wide — binomial 95% CI
  for 10/17 is ~[33%, 82%], for v1's 3/17 ~[4%, 43%]. The intervals barely
  overlap; direction is decisive, magnitude is not precise.
- `arche_traj` for events before 06-23 was backfilled from the earliest
  nightly file (quasi-static, both arms identically affected).
- Ownership/FA pool per event is a ledger reconstruction (06-04 baseline +
  tx roll-forward, name-keyed); small drift possible but the added player
  is always force-included, so hit rates are unaffected by pool leakage of
  already-rostered names (they only add distractors, symmetrically).
- v2 sigmoid scores saturate near 0.97-0.99 at the top of the FA pool
  (class_weight='balanced' shifts the intercept); ranking — the thing the
  metric tests — is unaffected. Drop marginal-upgrade differences compress
  slightly; monitored, not re-tuned (would need re-pre-registration).
- Treasure Island Mashers: 0 in-window adds — the pooled model is the only
  read on them; their v1 profile still shapes `v1_prior`.
- Re-refit cadence: rerun `refit_opp_watch_v2.py` after ~4 more weeks of
  ledger accumulation (next natural checkpoint ~2026-08-07); per-team
  interaction terms become defensible once most teams pass n≈15 adds
  in-panel.

