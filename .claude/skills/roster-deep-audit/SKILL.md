---
name: roster-deep-audit
description: Cross-skill roster + FA audit for YOUR team only. Orchestrates career-form-rank, hitter-sustainability, pitcher-sustainability, and slump-or-decline sweeps; produces a single synthesis report with an agreement matrix (where skills disagree is where the insight lives) + cross-validated swap recommendations. For a league-wide audit across all 8 teams with MC/Bayesian/historical-comps statistical deepening, use /league-deep-audit instead. Use this skill when the question is only about your roster + FA alternatives.
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
