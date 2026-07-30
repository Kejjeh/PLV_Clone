---
signal: verdict_backtest_host_repair
formula: >
  No model, no feature, no threshold changes. Two dead call sites in
  scripts/xfp/verdict_backtest.py are re-pointed from the DELETED row-wise
  helpers `rh3._signal` / `rp3._signal` (removed by commit de9f6e6, "model
  vectorization") to local vectorized functions `hitter_signal_vec(df)` /
  `pitcher_signal_vec(df)` that reproduce production's inline `np.select`
  EXACTLY:
    hitter (mirrors rh3.main()):
      cond1 replacement_delta.isna() | replacement_xfp_per_pa.isna() -> hold
      cond2 xfp_rh3_p25.notna() & (xfp_rh3_p25 > replacement)        -> add
      cond3 xfp_rh3_p75.notna() & (xfp_rh3_p75 < replacement)        -> drop
      default                                                        -> hold
    pitcher (mirrors rp3.main()):
      cond1 is_on_il_at_split.isna() | (is_on_il_at_split != 0)      -> il
      cond2 replacement_delta.isna() | replacement_per_start.isna()  -> hold
      cond3 xfp_rp3_decision_p25.notna() & (p25 > replacement)       -> add
      cond4 xfp_rp3_decision_p75.notna() & (p75 < replacement)       -> drop
      default                                                        -> hold
  Predicate ORDER, column names, and NaN semantics (NaN > x is False) are
  preserved verbatim. The pitcher rule reads the DECISION band (raw LOO sigma),
  NOT the displayed band (raw sigma x alpha_global = 2.41) — preserved from the
  pre-existing lines 276-277 of the script.
  Equality with production is not asserted by inspection: it is MEASURED by
  replaying both functions over the shipped production projection CSVs and
  comparing to the `signal` column the pipelines actually wrote.
outcome: >
  (a) both hosts execute end to end instead of raising AttributeError;
  (b) emitted signal identical to production on every shipped row.
expected_sign: "0 (exact equality — this is a repair, not a model change)"
theory: >
  The signal rule itself is correct in production and was correct in this
  script before de9f6e6; only the CALL was orphaned. Reproducing the current
  vectorized rule therefore must return the pre-de9f6e6 behavior exactly, and
  any deviation is a bug in the reproduction, not a modelling choice. A
  row-wise `_signal` shim was rejected: it would re-create the exact seam that
  rotted, and its per-row semantics could drift from the np.select the
  pipelines now use.
production_target: none (analysis/backtest host; rh3/rp3/rprs2 untouched)
framing: in-season -> ros (retrospective; unchanged from the original script)
holdout_years: [2026]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/verdict_backtest.py
date: 2026-07-29
verdict: REPAIRED (equality verified; no behavior change vs the pre-de9f6e6 rule)
---

# verdict_backtest.py host repair — both buckets were dead

## The rot

| # | Symptom | Introduced | Dead since |
|---|---|---|---|
| 1 | `KeyError: ['bx_prior_h']` in `build_hitter_panel` -> `dropna(subset=feats)` | `bx_prior_h` promoted into `RH3_FEATS` 2026-07-10 without mirroring the merge here | 2026-07-10 (HITTERS only) |
| 2 | `AttributeError: module 'plv_clone.models.xfp.rh3' has no attribute '_signal'` (line 237) and the identical failure on `RP3._signal` (line 284) | commit de9f6e6 "model vectorization" deleted both row-wise `_signal` helpers and inlined `np.select` into each pipeline's `main()` | de9f6e6 (BOTH buckets) |

Rot 1 was already fixed in the working tree before this change. Rot 2 is fixed
here.

**Reproduced before fixing** (`hasattr(RH3, '_signal') == False`,
`hasattr(RP3, '_signal') == False`; `run_hitters` raised at line 237 in 0.2s
after a 2.2s panel build).

## Why a local vectorized reimplementation, not a shim, and not an import

After de9f6e6 the production signal is **not a callable**. It is an inline
`np.select(...)` inside `rh3.main()` / `rp3.main()`, and `main()` retrains the
model and rewrites the production CSVs — there is no importable seam to call.
Three options:

1. **Restore a row-wise `_signal(row)` shim.** Rejected. It re-creates the
   exact API that rotted, and per-row `if` semantics can silently diverge from
   the vectorized `np.select` (NaN handling, predicate order) with no test able
   to see it.
2. **Extract `signal_vec(df)` into rh3.py / rp3.py and call it from both
   `main()` and here.** This is the correct long-term fix and is what a future
   change should do — one rule, one place. It is **out of this change's file
   set** (the pipelines are owned by a concurrent change), so it is recorded
   here as the follow-up rather than done half-way.
3. **Reproduce the rule locally and LOCK it with a test that replays it over
   production's own output.** Chosen. Duplication is real, but it is
   duplication that cannot drift undetected, which is strictly better than the
   status quo (duplication that could not even run).

## Measurement 1 — equality with production (the thing that makes (3) safe)

`hitter_signal_vec` / `pitcher_signal_vec` replayed over the shipped
projection CSVs, compared to the `signal` column those pipelines wrote:

| CSV | rows | production signal distribution | rows matched |
|---|---|---|---|
| `data/outputs/xfp_rh3_projections.csv` | 473 | hold 228 / drop 213 / add 32 | **473 / 473 (100%)** |
| `data/outputs/xfp_rp3_projections.csv` | 357 | il 134 / drop 114 / hold 97 / add 12 | **357 / 357 (100%)** |

Both distributions contain add, hold and drop, so the match is not vacuous.
Locked by `tests/test_verdict_backtest_hosts.py::test_hitter_signal_matches_production`
and `::test_pitcher_signal_matches_production`.

## Measurement 2 — the decision band is load-bearing (silent-failure guard)

The pitcher rule must read `xfp_rp3_decision_p25/p75` (raw LOO sigma), not the
displayed `xfp_rp3_p25/p75` (raw sigma x `alpha_global` = **2.41**). Swapping
them raises no error; it just flattens the verdicts. Measured on the real 2026
backtest panel (2,548 SP rows, 15 split-days):

| band feeding the add/drop rule | hold | il | add | drop | non-hold share |
|---|---|---|---|---|---|
| **DECISION** (raw sigma) — correct | 1368 | 232 | 194 | 754 | **37.2%** |
| DISPLAY (sigma x 2.41) — the trap | 2300 | 232 | 15 | 1 | 0.6% |

That is the failure mode the 2026-06-11 run found (100% hold) and 13bb4a1
fixed. `::test_run_pitchers_signal_is_not_inert` now fails if it returns.

## Measurement 3 — the hosts actually run (real output)

Full `python scripts/xfp/verdict_backtest.py`, AS_OF = 2026-06-09 as shipped:

* `build_hitter_panel()` -> `(91628, 122)`; `run_hitters()` -> **(5484, 12)**,
  signals hold 3101 / drop 1811 / add 572, 15 split-days (30..125).
* `build_pitcher_panel()` -> `(31135, 109)`; `run_pitchers()` -> **(2548, 12)**,
  signals hold 1368 / drop 754 / il 232 / add 194, 15 split-days.

Settled headline numbers (after the AS_OF settlement gate):

| bucket | n settled | Spearman(proj, realized fwd) | mean realized by tier | BUY_HIT | FADE_HIT |
|---|---|---|---|---|---|
| HITTERS (rh3, FP/PA) | 1234 (splits 30-51) | **0.500** (p=3.5e-79) | add 0.570 > hold 0.498 > drop 0.409 | 0.216 (n=139) | 0.395 (n=309) |
| STARTERS (rp3, FP/start) | 263 (splits 30-37) | **0.506** (p=1.7e-18) | add 16.17 > hold 10.58 > drop 8.22 | 0.652 (n=23) | 0.333 (n=78) |
| RELIEVERS (rprs2, ranking lens only) | 3099 | **0.802** pooled; 0.550 at split 30 rising to 0.962 at split 125 | add 237.6 > hold 146.4 > drop 90.2 | n/a | n/a |

`add > hold > drop` holds monotonically in all three buckets. The SP row
reproduces the 2026-06-11 commit-message numbers (add 17.0 / hold 10.6 /
drop 8.4, BUY_HIT 65%) to within cache/model-rebuild drift, which is
independent corroboration that the decision-band semantics were preserved.

## Provenance warning for anything that cited this script

* HITTER rows from this backtest have been unobtainable since **2026-07-10**.
* SP rows have been unobtainable since **de9f6e6**.
* Any `/verdict-scorecard` or verdict-backtest retro figure reported for
  hitters after 2026-07-10, or for **either** bucket after de9f6e6, did **not**
  come from this script. The tracked `_bt_hitters.csv` (1,270 rows) and
  `_bt_pitchers.csv` (300 rows) at HEAD were stale artifacts of the last
  working run; this change regenerates them at 5,484 and 2,548 rows.

## Known staleness NOT changed here

`AS_OF = date(2026, 6, 9)` is hardcoded, while the caches now run through
split 125 (2026-07-29). The settlement gate therefore silently discards
settleable rows: only splits 30-51 survive for hitters and 30-37 for SPs, out
of 15 available. Advancing `AS_OF` would change every reported retro number,
so it is a pre-registered decision, not a drive-by edit. **Left as-is and
flagged**; it is the natural next change to this file.

## Tests added (`tests/`)

`tests/test_verdict_backtest_hosts.py` (21 tests)
: executes `run_hitters` / `run_pitchers` / `run_relievers` on a 2-split
  subsample (fails on AttributeError or KeyError); asserts each panel builder
  reconstructs **every** feature in `RH3_FEATS` / `RP3_FEATS` (the `bx_prior_h`
  class of rot); production-lockstep equality (above); the SP signal is not
  inert; the decision band drives add/drop on a synthetic frame where the
  display band would say hold; IL precedence; NaN -> hold; and a
  fail-loud contract — every required signal input column, dropped one at a
  time, must raise `KeyError`, and a missing bx-priors cache must raise
  `FileNotFoundError` rather than default a feature to 0.0.

`tests/test_module_attr_rot.py` (5 tests)
: the general guard for this whole CLASS of rot. Statically parses every file in
  `scripts/xfp/`, `scripts/xfp/lib/`, `scripts/ci/`, `src/plv_clone/**`, `app/`,
  resolves each first-party module alias it imports, and asserts every
  `alias.attr` referenced actually exists. **0 violations today** across 300+
  files in ~2.5s, so it ships as a hard assertion with no quarantine list. It
  is proven capable of failing: `test_guard_detects_a_planted_violation` plants
  `RH3._signal` in a tmp file and asserts it is reported. False positives are
  avoided by design (module-valued aliases only; any alias rebound anywhere in
  the file is dropped; first-party roots only; scanned files are parsed, never
  imported).

Suite: **1005 passed, 0 failed** (`python scripts/ci/run_summary.py -- python -m pytest -q`).
