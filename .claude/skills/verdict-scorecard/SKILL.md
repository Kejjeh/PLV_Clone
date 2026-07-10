---
name: verdict-scorecard
description: Run the VERDICT SCORECARD engine — decision-quality accountability, the sibling of /model-health (that grades the MODELS; this grades the CALLS). Aggregates every SETTLED decision from the daily decision-logging chain (refresh steps 4.10a/b/c — triangulate BUY/HOLD/CAUTION/FADE/MIXED verdicts settled against realized BrownU FP-per-unit over H 21d / SP 35d / RP 35d windows) into a verdict ladder per player type — n, unique players, mean realized FP-per-unit vs matched projection, directional hit rate — plus a BUY>HOLD>CAUTION>FADE monotonicity check, BUY-vs-FADE discrimination test, confidence-field calibration, and a named worst-calls list. Honest n's everywhere (EARLY READ banner + the date the log becomes well-powered while settled n < 100; effective n = unique players). Use when the user asks "are our verdicts any good", "verdict scorecard", "how have our BUY calls done", "decision audit", "do our FADEs actually fade", or monthly alongside /model-health. Rule 13 — a scoreboard, never a ranker.
---

# verdict-scorecard — decision-quality accountability

## What this is

**/model-health measures whether the MODELS are accurate. This measures
whether our VERDICTS are any good** — the BUY / HOLD / CAUTION / FADE /
MIXED calls synthesized by `/triangulate` and logged for the whole roster
every daily refresh. A model can rank well while the verdict layer on top
adds nothing; nothing else in the repo scores the calls themselves.

Data chain consumed (read-only; runs daily in `refresh_dashboards.py`):

1. **4.10a `log_roster_decisions.py`** — triangulates the roster with
   `PLV_LOG_DECISIONS=1`, emitting one DecisionRecord per player-day to
   `data/research/decisions/{date}/{id}.json` (verdict_top, reason_tag,
   confidence 0.25/0.5/0.75/1.0, inputs incl. proj_per).
2. **4.10b `materialize_decisions.py`** — flat panel at
   `data/outputs/decisions_panel.csv`.
3. **4.10c `settle_decisions.py`** — settles ripe records against realized
   MLB gameLog BrownU FP into `data/research/decisions/settled/{date}/{id}.json`
   + `scorecard_{date}.{csv,md}`.

Settlement semantics (`plv_clone.decisions.settler.SETTLEMENT_WINDOWS`):
**H** 21d / min 30 PA / FP-per-PA / hit threshold ±0.02 · **SP** 35d /
min 5 starts / FP-per-start / ±1.0 · **RP** 35d / min 10 appearances /
FP-per-appearance / ±0.5. BUY_HIT = residual > +thr; FADE_HIT = residual
< −thr; HOLD/CAUTION/MIXED settle NEUTRAL (no directional claim).

## How to run

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_verdict_scorecard.py
```

Outputs: console report + `data/outputs/verdict_scorecard.csv` (the ladder,
one row per bucket × verdict).

## Steps

1. **Run the engine.** Read the header first: settled n, unique players
   (**effective n** — the same player is logged daily, so 83 settled records
   can be ~15 players), snapshot span, and the EARLY-READ / power line
   (below 100 settled decisions it prints the date the 100th record ripens).
2. **Read the ladder** per bucket: does realized FP-per-unit order
   BUY > HOLD > CAUTION > FADE? The monotonicity line says so explicitly;
   thin rungs (CAUTION n=3 from 1 player) can break it without meaning much.
3. **BUY vs FADE** is the headline discrimination test — it uses ONLY
   realized FP-per-unit, so it is unit-safe and survives the proj_per caveat
   below. A Mann-Whitney p is printed when scipy is present, with a tiny-n
   disclaimer (repeated player-days inflate significance — trust direction
   before p).
4. **Confidence calibration**: hit rate + mean realized by confidence bin.
   Until directional n per bin is ≥10 treat as descriptive only.
5. **Worst calls**: BUYs judged against the same-bucket BUY median realized
   (low = miss) and FADEs against the FADE median (high = miss), deduped by
   player. These are the review-queue names, not drop orders.

## Known caveat the engine surfaces (do not silently "fix")

`inputs['proj_per']` is **unit-inconsistent** with the settlement actual for
two buckets: **H** logs rh3 FP/**game** but settles FP/**PA** (~3.4× scale),
and **RP** logs the rprs2 RoS **total** vs FP/appearance. So residuals and
BUY/FADE **hit rates are only unit-honest for SP**; for H they degenerate
(every BUY → BUY_MISS, every FADE → FADE_HIT from the offset alone). The
engine prints a ⚠ UNITS WARNING whenever the scale ratio betrays this. The
ladder, monotonicity, BUY-vs-FADE, and worst-calls sections never touch
proj_per and stay valid. Fix belongs in `plv_clone/decisions/logger.py` /
`triangulate_core` model_proj units (flagged 2026-07-10), then re-settle.

## Hard rules

1. **Measurement only (Rule 13).** Nothing here moves rh3/rp3/rprs2 or
   changes a verdict. A bad ladder routes to investigating the verdict
   synthesis in `triangulate_core`, never to a silent re-weight.
2. **Honest n's every time (Rule 5).** Below 100 settled: EARLY READ banner
   + powered-from date. Always state effective n (unique players) — daily
   repeated measures make raw n flattering.
3. **Never conclude from a rung with n_players ≤ 2.** Name the thinness.
4. **All identity is decision_id / mlbam_id** from the records — no name
   joins.
5. **Settled tree is authoritative** (`decisions/settled/`); the panel CSV
   can contain duplicate settled rows for the same decision_id.

## First-run baseline (2026-07-10)

83 settled (15 players, H only — first SP/RP settlements ripen 2026-07-11;
well-powered from ~2026-07-11 with 612 pending). BUY mean 0.525 FP/PA
(n=37) vs FADE 0.292 (n=4): BUYs out-realized FADEs (direction only — 4
FADEs from 2 players). Ladder NON-MONOTONIC only because CAUTION (n=3, 1
player) sat above BUY. HOLD has zero settled decisions. Worst BUY:
Corbin Carroll 2026-06-19 (0.316 FP/PA vs BUY median 0.529).

## Cadence + companions

- **Monthly**, alongside `/model-health`, and after any change to the
  decision chain (logger / materializer / settler) or to triangulate's
  verdict synthesis.
- Companions: `/model-health` (model accuracy — the other half of the
  accountability pair), `/triangulate` (produces the verdicts being scored),
  `settle_decisions.py` scorecards (per-day classification counts this
  engine aggregates across all time).
