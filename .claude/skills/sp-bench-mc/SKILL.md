---
name: sp-bench-mc
description: Monte Carlo decision tool for SP-bench calls under the period SP-start cap (10 standard week / 16 ASG block / 20 playoff 2-week; resolve live via resolve_current_period_meta(league)['sp_cap']). Pulls each healthy SP's per-start FP distribution from MLB Stats API (last 30 starts across 2024-2026), blends with rp3 priors, applies the chronological cap rule, and compares bench scenarios with win-prob deltas + bootstrap CIs. Self-aware: prints a "not earning complexity" verdict when scenario gap is within MC noise (<1pp). Use when (a) projected starts exceed cap by 1-2, AND (b) the obvious bench-by-rp3 call isn't clearly settled — e.g., the lowest-rp3 start faces a favorable matchup and a higher-rp3 start faces brutal opp.
---

# sp-bench-mc

You are running a Monte Carlo to evaluate SP bench scenarios. The skill
exists because point-estimate bench logic (rank by rp3 × opp_factor,
bench the lowest) ignores variance and the chronological-cap rule
interaction with manual bench choices. When the deltas are small the
MC will tell you to fall back to point estimates anyway; when they're
meaningful (1-3pp) it tells you which one and why.

The tool already addresses the structural gaps from the prior inline
MC (n=4 bootstrap noise, no matchup conditioning, no cap mechanics, no
sensitivity dial). Don't reimplement those — just invoke it.

---

## When to invoke

- Projected starts this week > 10 by 1-2 starts → real cap pressure
- Multiple borderline bench candidates with non-obvious EV ranking
- User specifically asks "should I bench X" or "what's the best bench
  this week" or "run an MC on the bench decision"

## When NOT to invoke

- 1 over cap and the lowest-EV start is obviously the bench (e.g., a
  bottom-tier SP facing a brutal matchup) — use point estimates
- 3+ over cap → roster-construction problem, not bench problem. Surface
  the drop candidate via `/fa-sp-pool` instead
- Mid-game live decisions — too late, lineups are locked
- Asking for a season-long projection — out of scope; this is one-week

---

## Invocation

Default (auto-enumerate all healthy SPs with remaining starts):

```bash
python scripts/xfp/sp_bench_mc.py
```

Common variants:

```bash
# Force-include a known start the rotation predictor missed
# (BrownU rotation gaps can mislead the auto-predictor — verify against
# the ESPN PP markers and add any missing starts)
python scripts/xfp/sp_bench_mc.py \
    --add-start "Will Warren:2026-05-24:TB"

# Specific shortlist (skip auto-enumeration)
python scripts/xfp/sp_bench_mc.py --bench Soriano --bench Warren

# rp3-only prior (matches dashboard --bootstrap baseline)
python scripts/xfp/sp_bench_mc.py --prior rp3

# Empirical-only prior (no model regression to mean)
python scripts/xfp/sp_bench_mc.py --prior empirical

# Dashboard cap convention (EV-based, optimistic) instead of live rule
python scripts/xfp/sp_bench_mc.py --cap-rule ev
```

Full CLI:

```
--bench <Name>           # repeatable; default = auto-enumerate
--prior <empirical|rp3|blend>  # default blend (Bayesian: n/(n+20))
--history-window <N>     # max starts per pitcher (default 30)
--trials <N>             # MC trials (default 10000)
--opp-window <season|recent>  # bat_index window (default recent)
--cap-rule <chronological|ev>  # default chronological (live rule)
--seed <N>               # reproducibility (default 7)
--k-prior <N>            # blend weight (default 20; higher = trust rp3 more)
--add-start "Name:YYYY-MM-DD:OPP"  # force-include missed starts; repeatable
```

---

## Understanding the output

Three sections:

1. **Per-pitcher sample stats** — sanity check. Look for:
   - Low `n_starts` (< 15) for any pitcher → empirical signal is weak,
     blend prior leans on rp3 hard (correct behavior, no action)
   - `emp_mean` vs `rp3` divergence > 4 FP → the pitcher's recent form
     is materially off model. Worth noting in your final recommendation.

2. **Scenario results** — one row per bench candidate. Read:
   - `WinProb` — absolute MC estimate
   - `95% CI` — bootstrap CI on the win prob
   - `ΔWin` — pp gain/loss vs no-bench baseline (the key number)
   - `ΔEV` — expected FP gain/loss

3. **Verdict** — self-aware recommendation:
   - **Gap > 1pp:** prints best + worst scenario and the gap. Recommend
     the best to the user with brief reasoning (matchup, recent form).
   - **Gap < 1pp:** prints "MC isn't earning its complexity" and falls
     back to `rp3 × opp_factor` ranking. Recommend the lowest-EV
     start in that ranking — the MC confirms there's no meaningful
     variance edge.

---

## Interpretation rules

- **Baseline ≠ ground truth.** Baseline is "no manual bench, let the
  chronological cap auto-zero start #11." If chronologically the last
  start is already your worst, baseline is hard to beat. The tool will
  surface this — most "bench X" scenarios will return ~0pp delta.
- **A positive ΔWin > 1pp means there's a real swap opportunity.** Usually
  this happens when an early-week start faces a brutal matchup (LAD,
  NYY) and benching it lets a chronologically-later favorable matchup
  (TB, MIA) take its slot.
- **Bench Peralta (or your #1 SP) is almost always the WORST scenario.**
  If the tool says otherwise, double-check sample stats — likely his
  empirical mean is depressed by a single bad outing.
- **--prior choice rarely flips the verdict, only its magnitude.** If
  ranking changes between priors, that's a strong signal the decision
  is genuinely uncertain (not a confident swap).

---

## Caveats / known limitations

- **Rotation predictor uses median gap from last 5 starts.** If a
  pitcher just skipped/doubled a turn, the gap can mislead and a real
  start gets missed. Verify against ESPN's PP markers and use
  `--add-start` to force-include any missed starts.
- **Same-day starts use alphabetical tiebreak for chronological cap.**
  ESPN actually uses start-time order. Error is small but real.
- **Opp SPs don't have user-controllable bench.** The tool sims their
  cap with no-bench (worst-case for you). Reality: opp also manages
  their cap optimally, which is captured by the model.
- **Hitter and RP contributions use the dashboard's point projection +
  static σ** (lognormal). Not the decision variables.
- **30-start window crosses year boundaries.** A pitcher who changed
  team / role between 2024 and 2026 has historical samples that don't
  reflect current talent. Lower `--history-window` if you want to
  emphasize recent form.

---

## Anti-patterns this skill exists to prevent

- **Running an inline ad-hoc MC.** I did this once with n=4 samples
  per pitcher and got noise-dominated results that contradicted both
  rp3 and PL. Use this tool instead.
- **Treating "bench Warren" as obvious because he's the chronologically
  last start.** With the chronological cap, that's the default — the
  question is whether a swap improves things, which the MC quantifies.
- **Ignoring the "not earning complexity" verdict.** If the tool says
  the gap is < 1pp, the decision is statistically tied. Don't overweight
  a 0.3pp MC delta — that's noise.
- **Trusting the tool when sample stats look thin.** A pitcher with
  n=5 starts has 20% empirical weight in blend; the result is mostly
  rp3 anyway. Note this in your recommendation.

---

## When NOT to use this skill

- Decisions about which RP to bench → out of scope (RP cap is roster
  size, not start count). Use `/roster-audit`.
- Hitter benches based on matchup → use `/hitter-compare` instead.
- Multi-week SP planning → use `/sp-week-plan` as the high-level view
  and this MC for any individual borderline calls.
- When the dashboard already shows a clear bench answer (e.g., 12
  starts and the bottom 2 are both 60-day IL → drop both, no need
  for MC).
