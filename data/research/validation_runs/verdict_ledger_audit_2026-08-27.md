# Verdict ledger audit — the plumbing works; the headline number does not mean
# what it looks like

**Date:** 2026-08-27
**Scripts:** `reconcile_decisions.py`, `settle_decisions.py`,
`run_verdict_scorecard.py`, `src/plv_clone/decisions/settler.py`
**Verdict:** attribution is FIXED (9/10 vs 0/21 in July). The directional
hit-rate is NOT a skill measure and must not be quoted as one.

## 1. Attribution is working

`reconcile_decisions.py` now attributes **9 of 10** executed ESPN transactions
to the ΔP(win) surface that motivated them, with a named counterfactual —
e.g. `+ SWAP Noah Cameron (SP) dpwin +5.37pp | passed on: Carlos Rodon`. The
2026-07-29 dry run attributed **0 of 21**, because moves were being executed
before any surface existed. The workflow rule in CLAUDE.md ("run the optimizer
BEFORE executing") is the whole fix, and it took.

The one miss (Bo Bichette) is the same failure mode surviving in miniature: the
surface post-dates the transaction. Nothing to fix in code.

## 2. The 34% "hit rate" is a calibration residual, not a directional call

`/verdict-scorecard` reports a directional hit rate over 405 BUY/FADE records:
34% overall, H 31%, SP 31%, RP 58%. Read cold, that says the process is wrong
two times in three. It says no such thing.

`settler._classify` defines a hit as the player **beating his own projection**
by a threshold:

```
residual = actual_fp_per_unit - inputs['proj_per']
BUY_HIT  iff residual > +threshold      (H 0.02 FP/PA, SP 1.0 FP/start, RP 0.5 FP/g)
```

So the metric answers "did rh3/rp3/rprs2 under-project this player?" — not
"was the BUY right?" A perfectly calibrated model scores well under 50% by
construction, because the threshold sits strictly outside the median.

**The correct baseline is the same beat-rate over ALL settled records**, and
against that baseline the hitter signal vanishes entirely:

| bucket | settled | base beat-rate (all verdicts) | BUY beat-rate | edge |
|---|---|---|---|---|
| H | 1,305 | 23.0% | 23.1% | **+0.1pp — none** |
| SP | 509 | 53.6% | 30.5% | **−23.1pp — inverted** |
| RP | 69 | 59.4% | 59.4% | n/a (BUY-only, no baseline) |

The hitter BUY carries no information relative to the population. The SP BUY
looks actively anti-selected, and SP CAUTION beats it (69.5%) — but see §4
before believing that.

## 3. Two population facts the headline hides

**Hitter projections run high on this population by a lot.** Median residual
−0.105 FP/PA; collapsed to one row per player (n=21) the mean is **−0.245
FP/PA ± 0.104 (95% CI)**, i.e. about **−0.86 FP/g**. The CI excludes zero.

This is the opposite sign to `model_forward_calibration_2026-06-26.md`, which
found a mildly POSITIVE forward bias (+0.19 to +0.56 FP/g). Per don't-do 17a,
that is **not** a retraction of either: the two are different frames — a
different population (decision-logged players vs all rostered), a different
window, and a different date. What it most likely is:

> **Decision-logged hitters are selected on recent salience.** We log a
> decision when a player is on our mind, and he is on our mind after a hot
> stretch. rh3 at log time contains that hot stretch; the forward window
> regresses away from it. The ledger's residuals measure a selection effect
> on WHEN we look, not a bias in the model.

That is a testable claim and the right next study — pair each logged decision
with a same-day matched control (same projection level, no decision logged) and
see whether the residual gap survives. Until then the ledger's residual is not
usable as a calibration signal.

**SP settled records come from 14 unique pitchers.** This is don't-do 17c in
its purest form. Collapsing to one row per player:

| SP verdict | records | **players** | mean residual (collapsed) | 95% CI |
|---|---|---|---|---|
| BUY | 95 | 6 | +0.14 | ±2.99 |
| CAUTION | 210 | 8 | +0.64 | ±4.07 |
| MIXED | 191 | 8 | −0.88 | ±2.99 |

Every CI spans several FP/start and every pair overlaps. **The BUY-vs-CAUTION
inversion in §2 does not survive collapse.** The 509 is a pooled count; the
sample size is 14. Same for hitters: 1,305 records, 21 players.

## 4. What the ledger can and cannot say today

| claim | supported? |
|---|---|
| Attribution plumbing works | **YES** — 9/10, named counterfactuals |
| Process is ahead on settled decisions | **n=1** (+18.0 FP, H, RIGHT). Early read, nothing more |
| ΔP(win) has decision resolution | **NO** — 0 settled pairs, gate is n>=30 |
| Directional hit-rate is 34% | **Meaningless as stated** — see §2 |
| Hitter projections run high | Only on this population, and probably by selection — see §3 |

`settle_decisions.py` settled 1,017 records and paired **0** new ones; 1,014
pending. Pairing is the bottleneck, not settlement: a pair needs both the
chosen and the rejected side to reach their windows, and the rejected side is
usually an FA nobody rostered, so no actuals arrive. That is a real structural
gap in the counterfactual design and is worth an issue of its own.

## 5. Actions taken

- Nothing changed in `settler.py`. The classification is doing exactly what it
  documents; the error was in reading its output as a skill measure.
- `/verdict-scorecard` should print the all-verdict base beat-rate next to
  every bucket's hit-rate, and a unique-player count next to every pooled n.
  Filed as an issue rather than patched here, because it touches the shipped
  scorecard output.
