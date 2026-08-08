# Pre-registration — PL streamer tier/rank as an rp3 feature

**Locked:** 2026-08-07 (written BEFORE the Rule-9 integration run)
**Family:** `pl_streamer_tier` (registered context-only in `lib/lens_registry`)
**Harness:** `scripts/xfp/run_pl_streamer_backtest.py`
**Status:** ⏸ EXPLORATORY READ COMPLETE — Rule-9 run NOT yet executed

---

## Why this is being considered at all

The matchup-adjacent feature family is **0-for-4** (weather REJECTED+CLOSED,
trajectory Δr≈0, Location+ REJECTED, hand-matchup REJECTED), so the prior is
pessimistic and stays that way. This candidate is different in kind: it is not
a matchup covariate we compute, it is a **human expert's published synthesis**,
which may encode information (bullpen state, weather, a manager's stated plan,
a scratched start) that no column in our panel carries.

## What has already been measured (exploratory, NOT a promotion)

Sample: **2,016 pitcher-days / 86 slates, 2026-05-07 → 2026-08-06.** As-of rp3
from `player_projection_history` (from 06-04) + git-recovered committed
projections (from 05-07). Actuals recomputed from boxscores. Cluster bootstrap
over slates.

| Quantity | Value | 95% CI |
|---|---|---|
| Nick rank skill (Spearman vs FP) | +0.237 | [+0.193, +0.278] |
| Our rp3 rank skill | +0.241 | [+0.205, +0.279] |
| Difference | −0.005 | [−0.036, +0.027] — **not separable** |
| **PL tier partial r, beyond rp3** | **+0.068** | **[+0.028, +0.107]** |
| Our rp3 partial r, beyond PL tier | +0.116 | [+0.079, +0.152] |
| corr(rp3, PL tier) | +0.751 | — |
| 50/50 percentile blend vs ours alone | +0.0185 | [+0.0048, +0.0329] |
| **Blend gain at top-1 per slate** | **+0.03 FP** | **[−1.43, +1.47] — nil** |

Tier means: Auto-Start **13.86** / Probably **11.18** / Questionable **9.80** /
Do Not Start **8.04**. Auto − Probably = **+2.68 FP [+1.62, +3.71]**.

## The finding that gates promotion

The blend improves **board-wide rank correlation** and does **nothing** at
**top-1 per slate** — which is the only decision this feature would ever
inform. The two sources already agree at the top of the board; they diverge in
the middle, where nobody streams from. A feature that moves a statistic we do
not act on is not worth a model dependency.

## Pre-registered cells (if a Rule-9 run is ever authorized)

1. `pl_tier_ordinal` (0–3) as an rp3 per-start feature.
2. `pl_rank_pctile_within_slate` (continuous, slate-normalized).

**Gates (all required, per cell, Bonferroni 2):** paired-bootstrap 97.5% CI on
holdout Δr excludes 0; **Δr ≥ +0.005** against a Rule-9 baseline containing
**every** current production feature; per-year sign consistency ≥5/7.

## Known blockers — read before running

- **Biased subsample.** PL lists ~30 streamer-relevant arms per slate. Aces and
  deep-bench arms are absent, so the training frame is not the rp3 population
  and coverage is ~2k rows against rp3's full panel.
- **Operational dependency.** rp3 would gain a same-day third-party fetch. A
  missed publish, a paywall change, or a parser break would degrade the
  *projection*, not just a display column. That is a real production risk for a
  feature whose measured decision value is +0.03 FP.
- **Only ~2 free days per edition** (day 3 is PL-Pro gated), so some slates are
  unavailable at any price.
- **Same-day leakage risk.** Ranks publish 10am–12pm ET and are revised
  intraday; the backfill takes whichever edition was fetched. A training run
  must pin the FIRST published edition per slate, not the latest.

## Decision

**Register as a context-only lens (Rule 13). Do NOT run the Rule-9
integration yet.** The exploratory partial r clears the bar comfortably, but
the decision-level payoff is nil and the operational cost is real. Re-open only
if a use case appears that ranks the MIDDLE of a slate — e.g. two-start-week
planning across many marginal arms, where board-wide ordering is what matters.

**Caveat on the exploratory numbers themselves:** three separate marginal
findings from this same dataset died as the sample grew (an "Auto == Probably"
tier collapse at n=150 reversed; a disagreement edge at n=18 and a top-2
streaming edge at n=1,360 both went ns). The partial-r result above is well
clear of zero, but the blend lift at +0.0185 [+0.0048, +0.0329] has exactly the
profile of the results that did not survive.
