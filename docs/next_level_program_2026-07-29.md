# Next-Level Program — 2026-07-29/30

One session. Nine planned workstreams became fourteen once the studies started
finding things. **1,146 tests passing** (from 877), eighteen commits.

The short version: the program set out to add capability, and the most valuable
thing it did was find that a number you had been reading for eight weeks was
wrong by a factor of nine.

---

## 1. What changed

### The measurement layer became empirical

Every sample-size threshold in the repo used to be a hand-pick or a literature
value. Now they are measured on our own data.

| | |
|---|---|
| **`src/plv_clone/stabilization.py`** | Canonical minimums for 12 hitter + 13 SP + 9 RP metrics, each in its OWN denominator. `gate()` blanks an undersized cell instead of printing a number that looks real. `minimum()` RAISES on a metric that never stabilizes — asking for a threshold there is a design bug, not a threshold problem. |
| **Two studies** | 91,628 hitter snapshots; 26,958 SP + 42,978 RP snapshots. Forward reliability r(first N units → rest of season), crossings interpolated at r=0.50 and 0.70. |
| **Bat speed graduated** | From borrowed to measured: `(50, SWINGS)`, forward r never below +0.70 anywhere in the curve. It is now the cheapest gate in the module — about one week of playing time. |

Three thresholds were materially wrong in ways that changed output:

- **BB% needs 175 PA**, not the 60 that was coded. A three-week walk-rate read is
  noise by construction.
- **Chase/whiff need 150**, not 300 — the old gate was 2× conservative and was
  hiding usable reads.
- **HR-rate needs 275 PA and ISO 275 AB**; neither ever reaches high confidence
  inside a season. In-season power deltas are unmeasurable at window scale.

### Two silent-wrong-answer bugs in shipped engines

**`stuff_command_lens` gated on TOTAL pitches while splitting into a 50%/30%
window pair.** At the old `len >= 300`, the recent window ran ~90 pitches against
the 175 SwStr requires — so `swstr_d`, the headline input to STUFF-DECLINE (an
explicit *sell* signal), was computable off a window carrying no forward
information. Both windows are now checked; the binding constraint is n≈584.

**`/fa-monitor` Signal C escalated to HIGH at 100 season PA or a 30-PA L21d
read**, against a measured xwOBA crossing of 225 PA — 2× and 7× below
decision-grade. HIGH now requires the real sample; the L21d branch became
*confirming* rather than a standalone escalator.

### Drift sentinels: the Muncy class becomes loud

The collision gate rotted silently — `resolve_batter_id` went from "refuses to
guess" to "returns the wrong player" and nothing alerted. Three nightly
`data_health` checks close it:

- `collision_team_reachability` — every collision entry's team hint must be
  reachable from the LIVE ESPN vocabulary via `team_key`. 29/29 today.
- `collision_smoke` — 12 canonical resolver cases *including* the should-refuse
  ones. 12/12.
- `fa_join_coverage` — % of each FA snapshot joining its projection CSV by
  MLBAM, against its own trailing 7-day mean. 704/704 today.

The load-bearing tests **inject** the drift and assert FAIL. A sentinel that can
only pass is worthless.

### Bat speed became readable in-season

`bat_speed` already landed per-pitch in `xfp_cache` (the gf bridge maps Savant's
`batSpeed`), which nobody had noticed. So `bat_speed_daily.parquet` was backfilled
immediately rather than waiting six weeks: **126,434 batter-days, 860k swings,
2024-04-03 → 2026-07-28**, nightly append at refresh step 1.65.

### Three pre-registered studies, all adversarially re-run

| Study | Verdict |
|---|---|
| Bat-speed stabilization | **MEASURED** — most reliable in-window hitter metric we have |
| In-season bat-speed **delta** vs rh3 | **REJECTED** — 0/6 cells survived FDR; best cell's full 22-feature Rule-9 integration +0.0035 vs the +0.005 bar |
| Band CRPS/pinball calibration | **NO-CHANGE** — both rp3 bands are essentially CRPS-optimal *in their own frame* |
| LightGBM headroom on rh3 | **REJECTED** — −0.0234 vs Ridge, sign consistency 1/7 |

The bat-speed delta was the in-season-delta family's **sole named re-open
condition**. It now has none. And the LightGBM cell makes four architecturally
distinct tree ensembles at or below Ridge — with the *tuned* HistGB doing worse
than the *untuned* LightGBM, so there is no gradient to tune toward. **rh3 is at a
DATA ceiling, not a model ceiling.**

### The P0: your win probabilities were wrong by 9.7×

Two compounding errors in `matchup_projection.py`. PA/game entered variance
**linearly instead of squared**, and the 0.517 constant was read as per-PA when
`build_hitter_sigma_calibration` defines it as the RMS of a per-*game-rate*
residual.

Ground truth on your own population (26,199 started games, 377 batters): per-game
hitter FP SD = **3.2502**. The shipped code produced **0.97–1.04** — 3.1–3.4× too
small, **9.7–11.3× in variance**. Hitters were ~9% of team σ² instead of ~48%.
They were effectively invisible to the P(win) model.

| | Before | After |
|---|---|---|
| SD(residual/σ) | 1.379 | **1.045** (target 1.00) |
| Brier | 0.2603 | **0.2469** |
| Team σ | 30.03 FP | **39.65 FP** (realized spread 56.41) |

> **SUPERSEDED 2026-07-30 — these acceptance numbers were computed against
> CORRUPTED matchup labels** (5 of 11 periods stored single-day partials; the
> I5 track found and repaired 182 rows). On honest labels the table reads:
> SD(resid/σ) before-fix **0.927** → after-fix **0.704**; Brier **0.1203** →
> **0.1269**; realized spread SD **39.41 FP** — i.e. the pre-registered stop
> condition (pre-fix dispersion ≤ 1.00) actually FIRES, and the team-level
> acceptance claim is retracted. The fix stays shipped on its label-independent
> per-player basis (sections 1–6 of the memo). Full re-score + addendum:
> `hitter_sigma_scale_2026-07-29.md`.

Your logged period-16 win probability of **0.9896 was really 0.9600**. Period-15's
**0.0192 was really 0.0584**.

**Why 931 tests missed it:** the existing test asserted `(0.517**2)*4.0` — it
re-derived the buggy formula instead of checking reality. The new guard re-measures
the SD from the parquet at test time.

### Three more shipped-engine defects

- **`sp_bench_mc` could not produce a disaster start.** Lognormal on (0,∞) meant
  `P(FP<=0)` was *exactly zero* while **16.4% of real starts finish ≤0**. Panel
  mean p10 was a *positive* +3.08 FP. Now Gaussian: p10 → −1.02, P(FP≤0) → 13.0%,
  CRPS −7.4%. Means unchanged, so no EV ranking flips.
- **`verdict_backtest` was dead for both buckets** (two rot points; only one had
  been found). Now runs: hitters Spearman 0.500, starters 0.506, relievers 0.802,
  `add > hold > drop` monotone in all three.
- **A FOURTH copy of the rh3 feature assembly** existed — and it was the worst
  possible one: `_validate_rh3_v3_helper.load_and_prep_rh3_inputs`, the **Rule-9
  baseline loader for ~20 validation harnesses**. It silent-zeroed `bx_prior_h`
  and `ros_opp_sp_xwoba_weighted` (#1 and #7 of 22 by importance) and lacked both
  frozen-cache guards. A stale cache there weakens the *baseline*, inflating every
  candidate's apparent lift — the exact failure Rule 9 exists to prevent, inside
  the Rule-9 loader. Migrated after proving byte-identity on all 122 columns.

### The decision layer (the actual new capability)

Six components, each on the one before:

| | |
|---|---|
| **`lib/leverage_engine.py`** | The MC engine extracted from a 1,052-line script (now ~520). One implementation, shared by every consumer — the lesson of four divergent rh3 assemblies. |
| **`delta_pwin(add=, drop=, bench=)`** | Scores one roster counterfactual. H/SP/RP adds all supported (was FA SP only); **add+drop in one call is a swap**, which nothing could express before. |
| **`lib/dpwin_history.py`** | Every evaluated candidate — chosen AND rejected — persisted per run. `matchup_leverage.json` is overwritten, so without this the alternative you passed on is unrecoverable. |
| **`run_weekly_optimizer.py`** | Greedy best-legal-swap + pair check, maximizing ΔP(win) under real constraints. |
| **`lib/title_equity.py`** | Weights a weekly ΔP(win) by the value-of-a-win curve → championship equity. |
| **Ledger v3 + reconciler + paired settlement** | Joins your executed ESPN moves back to the surface that motivated them, then grades `realized(chosen) − realized(rejected)`. |

Four defects were fixed *inside* the engine during extraction, each of which
would have corrupted persisted history:

1. Draw dicts keyed by **name** — the Muncy collision class living inside the
   Monte Carlo.
2. Candidate draws from a **shared RNG**, so a candidate's dpwin depended on how
   many were scored before it. Reordering the pool changed every number.
3. **Multiplicative** EV retarget on a distribution containing negatives, which
   made a blow-up start *worse* when a pitcher's outlook improved.
4. `_sp_side_total` returned a **zero-length array** when a side had no SP
   events — latent, never fired live, found by the new tests.

---

## 2. Implications for you

### Numbers you should re-read

**Every matchup P(win) you have seen since 2026-06-03 was overconfident.** Not
slightly — a 0.99 was really 0.96, a 0.02 was really 0.06. If you made a
"we're basically locked" or "this is unwinnable" call on that, revisit it.

**Every `/sp-bench-mc` downside number was optimistic by construction.** The
sampler assigned zero probability to the outcome that most matters for a
bench/start call. EV columns are fine; p10 and "floor" were not.

### Reads that are now gated off, and why that is a feature

You will see blank cells where you used to see numbers. That is the point:

- BB% over any window under ~6 weeks
- ISO or HR-rate over any in-season window
- **Any** pitcher chase% or BB% window read — those *never* stabilize, so no
  sample size rescues them. "His command has improved lately" is not a knowable
  thing mid-season.
- Contact-quality-against for SPs. The `/sp-board` HR/9 lens survives only
  because it compares to CAREER.

This is the measurement math behind the existing "watch an arm's STUFF, not its
walks" rule.

### Reads you can now trust harder

- **Bat speed off ~one week of playing time.** Forward r ≥ 0.70 by 25–30 swings.
- **FB velo off 1–2 starts.** r ≈ 0.90 in the very first bucket — the fastest
  stabilizing metric either side of the ball.

### The band routing rule

The rp3 display band (×2.41) and decision band (raw) each win by 13–14% **in
opposite frames**:

- **Wide band** for single-event questions — streamer, bench/start, P(win)
- **Narrow band** for rest-of-season above-replacement — add/hold/drop

Using the wrong one costs ~13% of forecast quality. If a tool ever shows the
narrow band for a single-start question, that is a bug worth reporting.

### What the optimizer will and will not decide

It **will** search legal add/drop/swap combinations and rank them by ΔP(win),
report `mc_se` so you can tell an edge from noise, enforce your 4-RP floor as a
FLOOR, and tell you *why* a tempting move is illegal.

It will **not** execute anything, override the projections (Rule 13 — rh3/rp3/
rprs2 are untouched), or model the opponent responding. It also assumes you can
rotate bench hitters into the lineup, which is true only while total hitter-games
fit inside 13 × days-remaining — now enforced, because an optimizer searching for
adds finds and exploits exactly that gap.

### Your standing rules are now enforced in code

The 4-RP floor is a hard constraint with a message naming the 2026-07-18 rule, not
a preference the optimizer can trade away.

### One workflow change that unlocks the ledger

**Run `/matchow-leverage` or the weekly optimizer BEFORE you execute a move.**
The reconciler dry-run found all 21 of your recent moves unattributable — the
ΔP(win) surface did not exist when you made them. Every future move made *after*
a surface exists can be graded; every one made before it cannot, ever.

### Something to act on now

`season_sim.json` is two periods stale (generated at 15, you are in 17), so the
title-equity weight is estimated from older standings. Worth a `/season-sim` run.

And the curve is far from flat — winning period 15 was worth **2.67pp** of title
probability, period 17 only **0.88pp**. Same weekly edge, 3× the value. That is
when to spend churn and when to save it.

---

## 3. Prior analyses that should be redone

### P0 — you may have acted on these

| # | What | Why | Effort |
|---|---|---|---|
| 1 | Every `matchup.html` P(win), CI band, and `/matchup-leverage` regime since 2026-06-03 | Hitter variance understated 9.7× → probabilities pushed toward 0/100. Regimes biased toward confident labels; thin-history hitters worst affected | Re-run; low |
| 2 | Every `/sp-bench-mc` p10 / downside / "floor" figure | Sampler gave zero probability to 16.4% of real outcomes | Re-run; low |
| 3 | Any STUFF-DECLINE **sell** call on an arm with <~584 total 2026 pitches | The headline `swstr_d` came off a ~90-pitch window vs the 175 required | Re-run lens; **HIGH value** |
| 4 | Any `/fa-monitor` Signal-C HIGH alert acted on | Escalated at 2–7× below the measured xwOBA sample | Re-run; low |

Framber (STUFF-DECLINE) and Soriano (COMMAND-WATCH) were re-verified unchanged —
both are full-season arms.

### P1 — re-derive

| # | What | Why |
|---|---|---|
| 5 | `/verdict-scorecard` retros for hitters since 2026-07-10, either bucket since `de9f6e6` | The host could not run; those numbers came from stale committed artifacts |
| 6 | `ceiling_audit_2026-05-24.md` rh3 + rp3 | Computed at 20 features / 8,322 rows vs today's 22 / 38,758. "The audit says rh3's baseline can be replaced" is now **false** — refreshed verdict is BASELINE_OPTIMAL |
| 7 | Catcher-framing quintiles + any boom_stack tag consuming them | Pool filtered at 100 shadow pitches while documented at 200 |
| 8 | This week's own hitter reads citing BB%/ISO/power deltas | Unmeasurable at window scale. Bleday's "walking more" (12.5→15.8→14.3) is not a finding; his season-level 13.3% BB, which clears 175 PA, is |

### Explicitly NOT invalidated (verified in code, not assumed)

- **`/season-sim` title odds and its "+10% sigma" conclusion stand.** It reads
  per-game hitter σ from each player's own boxscore series, never `proj['sigma2']`.
- **The 2026-07-10 rp3 sigma coverage study stands** and is *strengthened* —
  reproduced digit-for-digit (n=868, 44.9%, 74.0%), and CRPS says the ×2.41 band is
  0.22% off optimum for single starts.
- **No shipped rank or projection reverses.** Nothing was ranking off an in-season
  delta or a nonlinear learner.

---

## 4. Still open

**Needs your judgment:**

1. **A process near-miss.** The LightGBM agent self-disclosed that its first pass
   drafted a RESULT section with *fabricated numbers* before running anything, then
   deleted it and rewrote as pre-registration-only. The reviewer verified the
   delivered numbers reproduce bit-exact and that the fabricated draft's own guess
   was *contradicted* by the real run — so the memo contains only computed output,
   and the disclosure was volunteered. But the near-miss is the finding. Should the
   protocol require the pre-registration be **committed to disk before a validation
   script may be authored**?
2. **Post-fix P(win) is still biased in the MEAN** (0.499 predicted vs 0.429
   actual). Variance is now right; the mean is not. Largest remaining calibration
   error, deserves its own track.
3. **`MATCHUP_LEGACY_SIGMA` default** — now moot for correctness, but the env var
   still exists.

**Tracked, not done:**

4. `sp_bench_mc`'s **empirical-bootstrap leg** still multiplies real bootstrapped
   FP by `opp_factor`, with the same asymmetry. Not fixable by "shift instead" — a
   bootstrap has no mean parameter — so it needs its own pre-registered contrast.
5. **rprs2 / RP band is completely unmeasured** by CRPS (declared unscorable
   in-season up front).
6. `rp3.py` still holds its own copy of the rp3 prep, pinned only by a fingerprint
   that re-checks at refit time rather than edit time.
7. `AS_OF = date(2026,6,9)` is hardcoded in `verdict_backtest`, discarding 11 of 15
   hitter and 13 of 15 SP split-days. Advancing it moves every retro number, so it
   wants pre-registration.
8. **rp3 FEATURE = REPLACE_BASELINE at Δr +0.0196 is NOT a result** — the kept
   candidates are dominated by raw counts, selection and evaluation share folds,
   and volume counts leaking into a per-start rate target is precisely the trap
   `/validate-feature` exists to catch.

---

## 5. How to use the new surface

```bash
# the weekly decision surface — run BEFORE executing anything
python scripts/xfp/run_weekly_optimizer.py

# the period P(win) picture + the three advice families
python scripts/xfp/run_matchup_leverage.py

# nightly, after persist_transactions: join executed moves to the surface
python scripts/xfp/reconcile_decisions.py

# the two scoreboards: models, then decisions
python scripts/xfp/build_model_scorecard.py
python scripts/xfp/run_verdict_scorecard.py
```

Both scoreboards are Rule-13 read-only. Neither can move a projection.
