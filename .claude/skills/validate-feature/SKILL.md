---
name: validate-feature
description: Run the full 9-rule multi-testing protocol on a candidate model feature/signal before promoting it to the validated registry. Use whenever the user proposes "this should improve rh3/rp3/rprs2" or asks to validate a new predictor. Prevents the rh3/rp3 v2 mistake where stripped-down baselines over-claimed lift by 4×.
---

# validate-feature

You are running a controlled validation on a candidate signal/feature before
it is allowed to influence any decision-making output (FA ranks, drops, lineup
calls, projections). The protocol exists because we have repeatedly been
burned by:
- Grid-sweep winners that were Bonferroni noise (rolling-trend v2)
- Backtests with stripped-down baselines that 4×-inflated apparent lift (rh3 v2)
- Coefficients that flipped sign between training framings (deep pitch shape)

The user's job is to propose the signal. Your job is to test it honestly
against the strongest baseline that already exists, and to produce a
registry-ready writeup at the end (pass OR fail — both get logged).

---

## Inputs to confirm with the user before running

If the user hasn't provided these, ASK before doing anything else:

1. **Signal definition** — exact formula. ("xwoba minus actual wOBA per
   plate appearance, season-to-date" — not "the xwOBA gap thing")
2. **Outcome to predict** — exact column + sample frame.
   ("fp_per_pa post-cutoff" or "fp_per_start rest-of-season")
3. **Expected sign** of correlation, with theory in one sentence.
4. **Production use case** — offseason/draft? in-season decision? Both?
   This determines Rule 8 framing.
5. **Which production model would integrate this** — rh3, rp3, rprs2,
   or research-only.
6. **Holdout years** declared off-limits — default 2024-2025, plus 2026
   if season complete.

If any of those are missing or vague, do not proceed. Tell the user
exactly what's missing.

---

## Step 1 — Pre-register (Rule 1)

Create `data/research/validation_runs/<signal_name>_<YYYY-MM-DD>.md` with
frontmatter:

```markdown
---
signal: <name>
formula: <exact computation>
outcome: <exact column / frame>
expected_sign: <+ or ->
theory: <one sentence>
production_target: <rh3 | rp3 | rprs2 | research-only>
framing: <full-year | in-season → ros | both>
holdout_years: <list>
training_years: <list>
validation_script: scripts/xfp/validate_<signal_name>.py
date: <today>
---
```

This file IS the pre-registration. If anything in the frontmatter changes
after seeing results, the run is invalidated — restart with a fresh
holdout window.

---

## Step 2 — Identify the production baseline (Rule 9, the CRITICAL one)

The baseline you compare against MUST include every feature already in
the target production pipeline. Anything less inflates lift.

Look up the current feature list:
- For rh3: read `scripts/xfp/xfp_rh3_pipeline.py`, find the `features = [...]`
  list passed into the model. That is your baseline feature set.
- For rp3: same pattern in `scripts/xfp/xfp_rp3_pipeline.py`.
- For rprs2: same in `scripts/xfp/xfp_rprs2_pipeline.py`.

Print the baseline feature list back to the user for confirmation. If
the user proposes a smaller "curated" baseline, push back — Rule 9
explicitly forbids that, and we have a documented 4× over-claim from
the rh3/rp3 v2 audit (2026-05-13).

The candidate signal is ADDED to this baseline. The lift number is:
`cross_year_r(baseline + candidate) − cross_year_r(baseline alone)`.

---

## Step 2.5 — Data-coverage pre-check (added 2026-05-16)

BEFORE writing any validation script, verify the candidate signal can
actually clear Rule 5 (sample-size) and Rule 2(b) (≥ 5 of 7 year
consistency). Many candidates die here; do not waste time writing a
script that cannot pass.

Required checks:

1. **Years of source data available for the signal.** If the signal
   depends on bat-tracking (`bat_speed`, `swing_length`, `attack_angle`,
   `squared_up`), only 2024+ exists. If it depends on Statcast launch
   metrics (`launch_speed`, `launch_angle`), 2015+ exists. If it depends
   on pitch-tracking velocity/spin, 2015+ exists. Be specific.

2. **Years of training-eligible cohorts.** Subtract any lookback the
   signal requires. Examples:
   - Year-prior delta signal (`x(T) − x(T-1)`): need ≥ 2 consecutive
     years of source data per training-year cohort.
   - Year-prior-prior delta: need ≥ 3 consecutive years.
   - Pure same-year signal: need 1 year of source data per cohort.

3. **Cohorts vs the bar.** Count training-eligible years available.
   Rule 2(b) needs ≥ 5 of 7. Rule 5 needs ≥ 30 hitter-years per
   counted year. If your year count is < 5, you CANNOT clear the bar
   even with perfect within-year results.

If the candidate fails this pre-check, do not proceed to Step 3.
Instead:

- Document the constraint in the pre-registration with a `Rule 5
  honesty note` block (use the template in
  `data/research/validation_runs/README.md`).
- Emit a `REJECTED — sample-size deferred to year Y` registry entry.
- Suggest the earliest year a re-run becomes viable (e.g., bat-tracking
  delta candidates can be re-validated starting 2028 season).
- Stop. The user gets a fast verdict instead of a wasted script.

If the user pushes to "try anyway," explain that the protocol exists
because we have been burned by overstated claims from underpowered
tests (rolling-trend v2). A 1-cohort exploratory finding is fine for
context, but it is NOT validation, and must not be promoted to the
ranker registry.

---

## Step 3 — Build the validation script

Output the script at the path declared in the pre-registration. Required
structure:

```python
# Pre-registered: see data/research/validation_runs/<signal>_<date>.md
import pandas as pd
from sklearn.linear_model import Ridge
from scipy.stats import pearsonr

# 1. Load multiyr data (e.g., hitters_multiyr_2015_2026.csv)
# 2. Build per-year (batter, year) frame with:
#    - baseline features (the EXACT production list from Step 2)
#    - candidate feature (the new one)
#    - outcome column (post-cutoff or RoS, matching pre-registration)
# 3. For each TRAINING year (e.g., 2018-2023):
#      Train Ridge on all OTHER training years
#      Predict the held-out year
#      Compute correlation with outcome
#      Compute partial r controlling for baseline
# 4. Aggregate: pooled partial r, per-year sign consistency, holdout partial r
```

DO NOT use a "stripped-down" baseline. If the production pipeline has 21
features, the baseline has 21 features.

For IN-SEASON framing (Rule 8): training data must mimic the production
use case. Inputs = first-N-weeks features → predict rest-of-season. Do
NOT train on full-year features then claim in-season utility.

---

## Step 4 — Run the 3-part bar (Rule 2)

After the script runs, compute the three gates:

**(a) Effect size:** partial r ≥ 0.10 after controlling for the most
obvious prior baseline (pre-cutoff level of the same metric, or pre-
cutoff RoS). Report exact partial r.

**(b) Year consistency:** sign of partial r consistent across ≥ 5 of 7
training years (2018, 2019, 2021, 2022, 2023, plus whichever others are
in your training set). Report sign per year.

**(c) Holdout:** partial r ≥ 0.05 with the same sign on the holdout
window that was declared off-limits in Step 1. Report exact partial r
on holdout.

Sample-size honesty (Rule 5):
- Per-year n ≥ 30 hitter-years to count toward consistency
- Pooled n ≥ 200 for stable partial r
- Holdout n ≥ 100; below that, sign-only check

---

## Step 5 — Bonferroni / grid correction (Rule 3)

If this validation is part of a sweep (testing N variants of a signal):
- Per-cell bar becomes α/N. E.g., 35-cell sweep at α=0.05 needs each
  cell at p < 0.0014 or equivalent partial r raise.
- Report: how many cells tested, how many passed.
- If only 1-2 pass out of N, those are the suspicious ones — treat with
  skepticism even if they cleared the unadjusted bar.

Single-feature test with no sweep: this step is a no-op, note that
in the writeup.

---

## Step 6 — Framing match check (Rule 8)

If the production use case is IN-SEASON (rh3, rp3, rprs2 RoS):
- Run a convergence-curve test: re-validate at weeks 4, 6, 8, 10, 12 cutoffs.
- A feature is production-ready ONLY if it passes at MOST cutoffs with
  the same coefficient sign.
- Features that pass at one cutoff but flip sign at another are unstable
  and must be rejected, even if their pooled result looks good.

If the production use case is OFFSEASON/DRAFT only:
- Full-year framing is fine, no convergence curve needed.

If BOTH:
- Run both framings. They are different prediction problems; coefficients
  often differ in magnitude and sometimes in sign. Validate each separately.

---

## Step 7 — Component-level retest (Rule 4)

If the candidate FAILED predicting the downstream composite outcome (FP)
but the theory says it should work — retest on the component metric the
signal is most directly tied to (e.g., test K%-related signals against
K% post-cutoff, not against fp_per_start).

Often the signal IS real but the composite framing buries it under
noise. A component-level pass with composite-level fail means: keep as
a tie-breaker / diagnostic, do NOT promote to ranker.

---

## Step 8 — Generate the verdict and writeup

Compose a registry entry in this exact format, ready to paste into
`reference_validated_signals_registry.md`:

```markdown
### <signal name> — <STATUS> (<date>)
- **Standalone validation:** <which script>. Pooled partial r <value>
  (vs cumulative baseline <value>, gain <±value>, N=<value>).
- **Integration validation (against full production baseline):**
  cross_year_r <baseline_value> → <new_value>, gain **<±value>**.
  <PASS / MARGINAL / FAIL relative to the +0.005 strict bar>.
- **Per-year:** <year>: <±value>, <year>: <±value>, ... (sign-consistent or not)
- **Framing tested:** <full-year | in-season → ros | both>
- **Convergence curve (if in-season):** weeks 4/6/8/10/12 → <pass list>
- **Bonferroni context (if sweep):** <N variants tested, <K passed at adjusted bar>
- **Definition (canonical):** `<column_name>` = <exact formula>
- **Status:** <LIVE in <pipeline.py> | RESEARCH-STAGE | REJECTED — reason>
```

If PASS: append under "✅ VALIDATED (production)" section of the registry.
If FAIL: append under "❌ DEPRECATED / REJECTED" section with date + reason.
If MARGINAL (clears +0.001-0.003 against full baseline but below +0.005):
keep in registry under VALIDATED, but flag explicitly as marginal so
future decisions don't over-rely on it. Note Rule 9 context: a marginal
lift against the FULL baseline is the honest measurement.

---

## Step 9 — Production integration is SEPARATE (Rule 7)

Passing validation does NOT auto-promote the signal into a pipeline.
That is a separate task requiring:
1. Implementation plan (which pipeline file, which lines)
2. Full-pipeline backtest with vs without (this is the in-pipeline gate
   in `xfp_<model>_pipeline.py` — verify the gate is actually meaningful;
   the gate was broken pre-2026-05-13 and could no-op)
3. Cross-year r comparison of the full RoS projection (must not degrade)
4. Explicit user sign-off on the model version bump

Tell the user: "Validation complete. Production integration is a
separate request — do you want to plan that now or later?"

Until that integration ships, the signal lives in research artifacts
(CSVs, diagnostic scripts) and may be used as a tie-breaker but NOT
as a ranker.

---

## Anti-patterns this skill exists to prevent

If at any point during a run you find yourself:
- Comparing against a baseline that is SMALLER than the live production
  feature list (Rule 9 violation) → stop and rebuild the baseline
- Treating a sweep winner as validated without Bonferroni adjustment
  (Rule 3 violation) → recompute the bar
- Training on full-year features but recommending the signal for in-season
  use (Rule 8 violation) → retrain on in-season framing
- Quietly dropping the pre-registration after seeing results (Rule 1
  violation) → the run is invalidated, restart
- Reporting a +0.01 gain that was measured against a curated baseline
  when full-production baseline shows +0.002 → report the +0.002 number,
  not the +0.01

If the user pushes to skip any of these, refer them to the 4× over-claim
incident (rh3/rp3 v2 audit, 2026-05-13) and Rule 9 in
`reference_multitesting_protocol.md`.

---

## Output expectations

At the end of a `/validate-feature` run, the user should have:
1. A pre-registration file in `data/research/validation_runs/`
2. A validation script at the declared path
3. Numbers for all 3 gates (effect size, year consistency, holdout)
4. Bonferroni context if applicable
5. Framing-appropriate convergence curve if in-season
6. A registry-ready writeup with PASS / MARGINAL / FAIL verdict
7. A clear next-step prompt about production integration (or rejection)

The writeup is the deliverable. Even a FAIL is valuable — it goes into
the rejected section of the registry to prevent re-investigating the
same dead end (Rule 6).
