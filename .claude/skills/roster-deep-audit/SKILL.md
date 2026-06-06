---
name: roster-deep-audit
description: Cross-skill roster + FA audit for YOUR team only. Orchestrates career-form-rank, hitter-sustainability, pitcher-sustainability, and slump-or-decline sweeps; produces a single synthesis report with an agreement matrix (where skills disagree is where the insight lives) + cross-validated swap recommendations. v2 chains the newer slate-grids, boom-bust-history, and Tier 3 gate alongside the legacy sustainability sweep, producing an agreement matrix per swap candidate. For a league-wide audit across all 8 teams with MC/Bayesian/historical-comps statistical deepening, use /league-deep-audit instead. Use this skill when the question is only about your roster + FA alternatives.
---

# roster-deep-audit

You are running the canonical weekly YOUR-ROSTER audit by orchestrating the
4 individual sweep skills and producing ONE synthesis report. The skill
exists because running each skill separately produces 4 reports that
need manual cross-checking — the actually-useful decisions only emerge
when you see WHERE the skills disagree.

**Scope:** YOUR roster + FA pool only. For the full 8-team league-wide
audit with statistical deepening (MC bounce, Bayesian talent, historical
comps, peak survival curves), use `/league-deep-audit` instead.

---

## Inputs (all optional — sensible defaults apply)

1. **Focus** — `full` / `hitters-only` / `pitchers-only`. Default `full`.
2. **Slump-or-decline target list** — pre-named players to deep-dive on.
   Default: bottom-3 by career percentile from step 1's output + any FA
   the synthesis flags below the gate.
3. **FA universe filter** — `meaningful` (default) or `all`.
4. **Cache freshness override** — `force-rebuild` to ignore daily caches.

---

## Step 1 — Pre-flight

Verify both daily caches exist + are < 24h old:

- `data/research/xfp_cache/batter_rolling_features.csv`
- `data/research/xfp_cache/name_resolution_2026.csv`

Also verify model projections (`xfp_rh3`, `xfp_rp3`, `xfp_rprs2`) < 48h old.
Warn if not.

---

## Step 2 — Run `/career-form-rank` (sweep)

Read `.claude/skills/career-form-rank/SKILL.md`. Capture per-player:
- `current_l150_xwoba`, `career_percentile`
- `verdict_bucket` (PEAK ≥90, HIGH 80-90, ABOVE_MEDIAN 60-80, TYPICAL 40-60,
  BELOW_MEDIAN 20-40, SLUMPING <20)

---

## Step 3 — Run `/hitter-sustainability` (sweep)

Spec at `.claude/skills/hitter-sustainability/SKILL.md`. Sweep produces:
- `bucket` (LEGIT / IMPROVING / STABLE / MIXED / NOISE / BAD_LUCK / REGRESS)
- `divergence_flag` (BUY-LOW / SELL-HIGH)
- per-marker scores

---

## Step 4 — Run `/pitcher-sustainability` (sweep)

SP-only analog. Skip if `Focus == hitters-only`.

---

## Step 5 — Pick slump-or-decline targets

Cap at 8 players:
1. Bottom-3 of YOUR roster by career-form-rank percentile
2. FA candidates flagged BUY-LOW by sustainability AND TYPICAL/ABOVE_MEDIAN
   by career-form (not peakers)
3. Players the user specifically asked about in the session

---

## Step 6 — Run `/slump-or-decline` on targets

Per-player verdict: HOLD / SELL-HIGH / DROP / NOT-SLUMPING-STRUCTURAL.

For each slumper in the target list, run the full 15-step slump-or-decline
protocol, which NOW includes (as of v3 upgrade 2026-05-25):

- **Step 14a — MC bounce simulator**: 10k bootstrap sims from career
  rolling-150 distribution. Reports P(next 30PA xwOBA > career median)
  and 95% CI on expected next-30PA xwOBA. Call:
  ```python
  from scripts.xfp.mc_bounce_simulator import batch_mc_bounce
  mc = batch_mc_bounce([batter_id])
  ```

- **Step 14b — Bayesian posterior talent**: conjugate normal-normal update
  of career distribution prior with L21d observations. Reports posterior μ,
  95% credible interval, P(true talent > .320 league average), and
  games-to-200-FP at career rate. Call:
  ```python
  from scripts.xfp.bayesian_talent_estimator import batch_bayesian_talent
  b = batch_bayesian_talent([batter_id])
  ```

- **Step 14c — Historical comp matcher**: find all 2015-2025 historical
  players at similar career %ile / career PA / calendar month. Reports
  n_comps, P(bounced within 30PA), P(bounced within 60PA), median and
  10-90 percentile range of next-30PA xwOBA. Call:
  ```python
  from scripts.xfp.historical_comp_matcher import batch_historical_comps
  comps = batch_historical_comps([batter_id])
  ```
  Cache at `data/research/xfp_cache/historical_comp_snapshots.parquet`
  loads in <1s after first build.

These three tests replace the single-step MC bounce in the original
Step 14. Report all three alongside the existing shrinkage/CI/xwOBACON
signals. A HOLD verdict requires at least 2 of 3 tests to support bounce.

---

## V2 orchestration (chains newer skills, 2026-06-06)

The legacy chain (Steps 2-6 above) covers career-form / sustainability /
slump-or-decline. v2 augments it with the slate-grids, boom-bust variance
lens, and the mandatory Tier 3 xwOBA gate shipped on 2026-06-06.

### The v2 chain in order

1. **Step 1 — `/sp-slate-grid`** — full SP picture across the next 1-2
   slate days. 14 layers including rp3 + per_start band, archetype OVERALL
   / traj / T+1, live boom_stack with boom%/bust%/E[FP], PL Top 100, PL
   streamers, ownership tag (MINE / opp / FA), HIGH-K ARM, catcher framing,
   IL_RETURN. Surfaces both YOUR-staff weak links and FA SP upgrades.
2. **Step 2 — `/hitter-slate-grid`** — full hitter FA picture. 14 layers:
   Blended xFP + 95% CI, rh3, live_marginal + value_tier (same-position
   pool delta), Triangulate verdict, Sustainability bucket (with BUY-LOW
   REJECTED caveat — display only), xwOBA L21d vs 2025 diagnostic,
   xwOBACON YoY trajectory, archetype master + T+1 + 5 comps, hitter
   boom_stack with lineup_amp, process panel composite, PL Top 150,
   lineup spot, park + vs LHP/RHP, eligibility. KNOWN_COLLISIONS check
   is mandatory (Max Muncy LAD-vs-ATH).
3. **Step 3 — `/boom-bust-history`** — variance + actuals lens across the
   full roster + the top FA candidates surfaced by Steps 1-2. Empirically
   calibrated thresholds: SP boom ≥20 / bust <5, hitter boom ≥5 / bust <0,
   RP boom ≥6 / bust <0. Catches the Bradish-pattern (model 12 FP behind
   live actuals) and Valdez-pattern (high projection, 0% boom 25% bust).
4. **Step 4 — Tier 3 gate (mandatory, per `reference_xwoba_l21d_vs_2025_diagnostic.md`)** —
   for every borderline hitter swap candidate:
   - **xwOBA L21d vs 2025 baseline**: gap ±0.020 = skill holding,
     < −0.060 = real decline.
   - **xwOBACON YoY trajectory**: RISING / STABLE / DECLINING. Distinguishes
     valid prior-trough recovery templates from structural decline where
     the recovery ceiling is lower (Turner pattern).
   - A drop recommendation that fails this gate is dropped from the final list.
5. **Step 5 — `/breakout-sustainability`** — deep-dive on any hot-streak
   FA the slate-grids surface as a buy candidate. SUSTAINABLE / NARROW /
   HOT-STREAK verdict. Prevents the Schmitt-pattern overhype.
6. **Step 6 — `/pitcher-sustainability` + `/hitter-sustainability` sweep** —
   legacy chain (Steps 3-4 above) still useful as the confidence layer on
   rh3/rp3 for any candidate still in contention after the slate-grid +
   boom-bust pass.
7. **Step 7 — Synthesize the agreement matrix** — see template below.
   The actually-useful insight is WHERE the new skills disagree with the
   legacy chain.

### Agreement matrix template (v2)

One row per candidate (roster member being considered for drop OR FA being
considered for add):

```
| Player | rh3 signal | Blended xFP | boom-bust | sustainability | xwOBA L21d | xwOBACON YoY | breakout | Triangulate | Final |
|--------|------------|-------------|-----------|----------------|------------|--------------|----------|-------------|-------|
```

Cell values:
- **rh3 signal** — rh3 rank tier (TOP25 / TOP50 / TOP100 / streamer / fodder)
- **Blended xFP** — point estimate + 95% CI band from blend_score.py
- **boom-bust** — boom% / bust% from `/boom-bust-history` actuals window
- **sustainability** — LEGIT / IMPROVING / STABLE / MIXED / NOISE / BAD_LUCK / REGRESS
- **xwOBA L21d** — gap vs 2025 baseline (signed FP-equivalent)
- **xwOBACON YoY** — RISING / STABLE / DECLINING
- **breakout** — SUSTAINABLE / NARROW / HOT_STREAK / n/a (only run if hot)
- **Triangulate** — BUY / HOLD / CAUTION / FADE / MIXED
- **Final** — agreement count out of 8 + HIGH_CONFIDENCE / CAUTION / DROP_REC

### Cross-validation rule

For each swap candidate, count the number of lenses agreeing with the
direction (positive = ADD, negative = DROP):

- **≥4 of 8 agree → HIGH_CONFIDENCE.** Surface in final recommendation list.
- **2-3 of 8 agree → CAUTION.** Surface with explicit caveat naming the
  disagreeing lenses.
- **<2 of 8 agree → DROP the recommendation.** Not enough convergence.

The Tier 3 gate (Step 4) is a HARD veto independent of the count: a
drop candidate with xwOBACON RISING + xwOBA L21d gap ≥ −0.020 cannot
be recommended for drop regardless of other lenses.

### Output: unified roster + FA board

The v2 final report has TWO joined tables, not the four legacy tables:

1. **Unified roster + FA board** — one row per player (your roster + every
   meaningful FA), all 8 v2 lenses as columns, sorted by Blended xFP
   within position group.
2. **Top 5 swap recommendations** — ranked by `agreement_count × FP/wk delta`,
   each row showing drop target, add target, agreement count, FP/wk delta,
   and the disagreeing lenses (if CAUTION).

---

<!-- BEGIN: conflict-resolution-algorithm -->
## Conflict resolution algorithm (v2 synthesis)

Synthesis MUST follow the canonical rules in
`reference_lens_merge_protocol.md` (Tier A/B/C/D lens classification + 5
conflict resolution rules + Tier B hard veto + confidence labels HIGH/MED/LOW
based on 8-lens agreement). When two lenses disagree on a candidate, apply
the rule below by name — do not freelance the synthesis.

- **Rule 1 — Model FADE + actuals BUY → check sustainability.** If rh3/Blended
  xFP says FADE but boom-bust history shows a hot run, defer to sustainability.
  Canonical 2026-06-06 case: **Bradish** (model fade, L5 actuals 17.88,
  sustainability NOISE → fade the hot streak).
- **Rule 2 — CAP_FODDER + xwOBA L21d gap within ±0.020 → HOLD.** Process
  trumps boom-bust when the contact-quality gap is inside the skill-holding
  band. Boom-bust variance does not override an intact process signal.
- **Rule 3 — REAL_DECLINE L21d + RISING xwOBACON → HOLD with sell-high
  optionality.** YoY trajectory veto on a stale L21d slump. Canonical case:
  **Muncy** (L21d decline, xwOBACON RISING → hold, optionally market as sell-high).
- **Rule 4 — Sustainability REGRESS + CAP_FODDER + replacement-level
  Blended xFP → HIGH_CONFIDENCE DROP.** Three Tier A/B lenses agreeing on
  decline + no FP floor = drop. Canonical case: **Valdez** (REGRESS +
  0% boom 25% bust + Blended xFP at replacement level).
- **Rule 5 — Hot streak + discipline capped + xwOBACON RISING → NARROW
  BREAKOUT, expect revert.** Surface the hot streak but tag it as narrow;
  do not promote to HIGH_CONFIDENCE add. Canonical case: **Goodman**
  (hot streak, chase% capped, xwOBACON RISING → narrow breakout).

Tier B veto: any Tier B lens (per `reference_lens_merge_protocol.md`) that
fires against the recommendation downgrades confidence by one level
(HIGH→MED, MED→LOW) regardless of the agreement count.
<!-- END: conflict-resolution-algorithm -->


## Step 7 — Build the agreement matrix

For each YOUR-ROSTER name:

```
| Player | career-form | sustainability | slump verdict | MC bounce | Bayes P(>avg) | Hist P(bounce) | CROSS_VERDICT |
```

CROSS_VERDICT definitions (updated for v3):

- **CONSENSUS_DROP** — career-form SLUMPING + sustainability REGRESS
  + process DECLINING/MIXED + Bayesian-shrunk gap < −0.030
  + Bayes P(>avg) < 40% + hist_bounce_pct < 50%.
  ALL signals must agree. This verdict is deliberately rare.
- **CONSENSUS_HOLD_BOUNCE** — career-form SLUMPING + anchor_in_CI OR
  process IMPROVING OR K-decomp BABIP_DRIVEN + hist_bounce > 60%
  + Bayes P(>avg) > 60%. Statistical convergence on bounce.
- **HOLD_NOISE** — slump is statistically indistinguishable from baseline
  (anchor in 95% CI). Not a real slump — random variation around career norm.
- **CONSENSUS_HOLD_PEAK** — career-form PEAK + peak_type PROCESS_DRIVEN
  + peak survival > 70% at +60PA. Don't sell.
- **SELL_HIGH_WARNING** — career-form PEAK + peak_type OUTCOME_DRIVEN
  + peak survival < 55% at +60PA + Bayes P(>avg) < 80% despite peak form.
- **CONSENSUS_HOLD_TYPICAL** — no alarm signals. Default healthy player.
- **DISAGREEMENT_INVESTIGATE** — signals conflict. Flag for manual review.

For each FA candidate:
- **HONEST_UPGRADE** — TYPICAL/ABOVE_MEDIAN form + LEGIT/BUY-LOW sustainability
  + Bayes P(>avg) > 60%.
- **PEAK_MIRAGE** — PEAK form + OUTCOME_DRIVEN validator. Will revert; skip.
- **NOISE** — sustainability NOISE or insufficient sample.

---

## Step 8 — Recommended actions (cross-validated)

A swap enters the final recommendation only if:
1. Drop target has CROSS_VERDICT == CONSENSUS_DROP AND
2. Pickup target has CROSS_VERDICT == HONEST_UPGRADE AND
3. Position fit plausible

For SELL_HIGH opportunities: recommend PROACTIVELY approaching the rival
manager if any rival roster player has SELL_HIGH_WARNING cross_verdict
(peer across league to identify via `/league-deep-audit`).

Cap at 3 recommended swaps.

<!-- BEGIN: confidence-weighted-verdict -->
## Confidence-weighted verdict output (REQUIRED)

Every recommendation in the v2 audit output MUST end with the block below.
Recommendations missing this block are invalid and must be regenerated.

```
RECOMMENDATION: <action> <player>
   Confidence: HIGH | MEDIUM | LOW
   Lens votes: rh3=<v> | Blended xFP=<v> | boom-bust=<v> | sustainability=<v> | xwOBA L21d=<v> | xwOBACON YoY=<v> | Triangulate=<v> | PL=<v>
   Agreement: N of 8
   Tier B veto: PASSED | DOWNGRADED (cite which Tier B lens triggered)
   Conflict rule applied: Rule #N (per reference_lens_merge_protocol.md) | none
   Decision type: <type> (per reference_decision_type_lens_registry.md)
```

Confidence is set by the agreement count combined with Tier B veto status:
- HIGH = ≥4 of 8 agree AND Tier B veto PASSED
- MEDIUM = ≥4 of 8 agree AND Tier B veto DOWNGRADED, OR 2-3 of 8 agree AND Tier B PASSED
- LOW = 2-3 of 8 agree AND Tier B veto DOWNGRADED

Anything below 2 of 8 is dropped from the recommendation list entirely
(per the existing cross-validation rule), never surfaced as LOW.
<!-- END: confidence-weighted-verdict -->

<!-- BEGIN: decision-type-lens-selection -->
## Decision-type aware lens selection

Before running the full 8-lens audit, classify the user's decision into one
of the types in `reference_decision_type_lens_registry.md` (FA pickup,
drop, streamer, trade, sell-high, buy-low, IL stash, same-position swap).
Skip lenses the registry marks as `Skip` for that decision type. This
prevents lens overload — a streamer pick doesn't need archetype T+2; a
trade target doesn't need boom_stack.

Example: For the **streamer pick** decision type, the registry says
boom_stack tier + PL daily + L5 = primary. Skip Blended xFP (wrong horizon),
skip archetype (RoS lens). Audit time drops from ~60s to ~10s.

The decision type is then echoed verbatim in the `Decision type:` line of
the confidence-weighted verdict block.
<!-- END: decision-type-lens-selection -->



---

## Step 9 — Write the final report

Output `data/research/roster_deep_audit_<YYYY-MM-DD>.md`:

```markdown
# Roster deep audit — <date>

## Pre-flight
[cache ages, projection ages]

## Statistical confidence summary (slumpers)
| Player | MC P(bounce) | Bayes P(>avg) | Hist comps | Hist P(bounce 30PA) | CROSS_VERDICT |

## Agreement matrix — your roster
| Player | career-form | sust | slump | MC | Bayes | Hist | CROSS_VERDICT |

## Agreement matrix — FA pool (HONEST_UPGRADE + SELL_HIGH only)

## Cross-validated actions (≤ 3)

## Disagreement-investigate cases
```

---

## Anti-patterns this skill exists to prevent

- **Shipping a recommendation without the confidence-weighted block.**
  Every action must end with the RECOMMENDATION block in the
  `Confidence-weighted verdict output` section above.
- **Calling CONSENSUS_DROP on a single signal.** The v3 gate requires
  ALL of: REGRESS + process DECLINING + shrunk gap < −0.030 + Bayes P <40%
  + hist bounce < 50%. One bad signal is a watch, not a drop.
- **Ignoring historical comp count.** A 70% bounce rate from 12 comps is
  noise. Check n_comps >= 100 before treating hist_p_bounce as load-bearing.
- **Using raw observed L21d gap for the verdict.** Always the Bayesian-shrunk
  gap. Raw Vlad gap −0.069, shrunk gap −0.022 — completely different verdicts.
- **Sweeping `/slump-or-decline`.** Cap at 8. Beyond that, use `/league-deep-audit`.
- **Skipping pre-flight cache check.** Stale caches → stale verdicts.
- **Adding PEAK-form FAs to the recommendation list.** The mirage check exists
  to prevent this. Check peak_type first.

---

## Relationship to other skills

- `/league-deep-audit` — league-wide version with 11 layers + MC + Bayesian
  + historical comps + peak survival. Run that when you need the FULL 8-team
  landscape. This skill is for YOUR-ROSTER surgical audits.
- `/career-form-rank` — component; run alone for L150 + career-percentile view.
- `/hitter-sustainability` — component; run alone for 9-marker decomp.
- `/pitcher-sustainability` — component for SPs.
- `/slump-or-decline` — per-player deep-dive; run alone for a specific question.
- `/roster-audit` — slot/IL/cap-math (mechanical roster state, not performance).

**Natural cadence:**
- **Weekly:** `/roster-audit` for slot/cap, this skill for YOUR performance landscape.
- **Trade decision:** `/league-deep-audit` to see all 8 teams, then this skill
  for FA alternatives.
- **Mid-week:** individual component skills for surgical questions.
