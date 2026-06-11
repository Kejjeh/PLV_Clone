---
backtest_date: 2026-06-11
title: Leakage-safe retrospective backtest — headline projection + add/hold/drop signal vs realized forward FP
models: [rh3, rp3, rprs2]
data_through: 2026-06-09
as_of_today: 2026-06-09
engine: scripts/xfp/verdict_backtest.py
settler_contract: src/plv_clone/decisions/settler.py
scope: reconstructable MODEL+SIGNAL backbone only (live-lens verdict layer NOT reconstructable as-of historical dates)
leakage_status: clean for H/SP; RP full-year target NOT reconstructable in-season (flagged below)
---

# Verdict backtest — does our headline projection + signal predict realized forward FP?

Generated 2026-06-11. Engine: `scripts/xfp/verdict_backtest.py`. Panels cached
to `data/research/validation_runs/_bt_{hitters,pitchers,relievers}.csv`.

## TL;DR verdict

**The headline PROJECTION layer is aligned with realized forward FP for all
three buckets.** The hitter (rh3) and reliever (rprs2) projections rank realized
forward outcomes well; the SP (rp3) projection is positive but the weakest.

**The add/hold/drop SIGNAL layer is only meaningfully alive for HITTERS.** There:
add > hold > drop holds cleanly on realized forward FP, and the directional call
(does the player beat positional replacement?) is right 75% (add) / 82% (drop) of
the time. **For SP the signal is effectively inert — it emits `hold` on 100% of
2026 rows** (the calibrated σ bands are too wide to ever clear the ADD/DROP
gate). For RP the signal orders correctly but its settler classification is **not
reconstructable in-season** (target-unit problem, see caveat).

Weakest links, in order: (1) SP signal layer never commits; (2) rp3 projection
rank-corr (~0.40) is the lowest of the three and decays with the forward horizon;
(3) RP calibration is unscoreable until the 2026 season completes.

---

## Method & leakage discipline

For each `(player, split_day)` row in the 2026 rolling caches I:

1. **Predicted out-of-sample.** The production pkls (`data/models/xfp_*.pkl`)
   train ONLY on `TRAIN_YEARS` (2018–2025) — predicting 2026 split rows is
   genuinely OOS *by year*. No model-fit leakage. Features were reconstructed
   exactly as each pipeline's `main()` builds them, from the cache's
   cumulative-to-split (`*_to`) columns (Marcel prior from prior-year lags,
   shrinkage population means from TRAIN_YEARS only, schedule/opp caches joined
   on `(player, year, split_day)`).
2. **Derived the signal exactly as the pipelines do** (`_signal()`):
   `p25 > replacement → add`; `p75 < replacement → drop`; else `hold`.
   Replacement level + p25/p75 bands were recomputed **per split** from the
   projected population at that split, so the as-of decision is faithfully
   reconstructed (not borrowed from the latest-split production CSV).
3. **Took the realized forward target straight from the cache:**
   hitter `ros_full_fp_per_pa` (FP/PA over forward PA), SP `ros_fp_per_start`
   (FP/start over forward starts). These vary by split and the forward window
   shrinks as the season advances (hitter mean `ros_pa` 98→8; SP mean `ros_gs`
   6.3→1.0 from split 30→72) — confirming they are true *forward* outcomes, not
   season totals. The target is never a feature.
4. **Settled** per `settler.py`: H 21d/30PA/thr 0.02 FP/PA; SP 35d/5 starts/thr
   1.0 FP/start. An **as-of gate** keeps only rows whose settler window had fully
   elapsed by 2026-06-09 (mirrors `today >= snapshot + window_days`), so we only
   score decisions that could actually have been graded by now.
   `BUY_HIT = realized − proj > thr` (add); `FADE_HIT = realized − proj < −thr`
   (drop).

### Leakage I can rule out
- Model fit: production pkls exclude 2026 → OOS by year.
- Feature construction: only `*_to` cumulative-to-split columns; shrinkage means
  and Marcel priors derived from TRAIN_YEARS / prior-year lags.
- Target: realized-forward columns vary by split and the window shrinks — not a
  full-season constant.

### Leakage / contract issue I CANNOT rule out (RP)
`rprs2` targets **full-SEASON FP total** and trained on COMPLETE seasons. For
in-progress 2026 the cache's `fp_year_total` is the **season-to-date total as of
the 6/9 pull (~70 games), not a realized full-162 outcome** (verified: it is
identical across all 2026 split_days for a given pitcher, whereas in 2024 it is
the true completed-season value). Therefore the RP full-year projection (a
full-162 estimate) **cannot be settler-classified or calibration-checked**
against a partial actual — the units don't match. The settler's per-appearance
FP/g threshold (0.5) is also meaningless against a hundreds-of-FP season-total
residual. I report RP on the **ranking lens only** (does the projection order RPs
correctly vs season-to-date production), which is valid and leakage-safe.

---

## Headline numbers

### Spearman rank-corr (projection vs realized forward FP)

| Bucket | Basis | ρ overall | n | Per-split ρ (cutoff) |
|---|---|---|---|---|
| **Hitters (rh3)** | FP/PA forward | **0.491** | 1128 | 0.521 (4/25) · 0.529 (5/2) · 0.478 (5/9) · 0.447 (5/16) |
| **Starters (rp3)** | FP/start forward | **0.405** | 236 | 0.413 (4/25) · 0.389 (5/2) |
| **Relievers (rprs2)** | full-yr proj vs season-to-date actual | **0.761** | 1176 | rises 0.61 (4/25) → 0.90 (6/6) as sample grows |

Hitter ρ decays with the forward horizon (0.52 early → 0.27 by split 65 on the
ungated panel) — expected, since later splits have a tiny noisy forward window.
SP only has settleable rows at splits 30 & 37 (35-day window + ≥5 forward starts
exhausts the panel after that). RP ρ rises across splits purely because the
season-to-date actual is a larger, less noisy sample later — it is **not** a
forward-skill statement.

### Signal-tier mean realized forward FP — does add > hold > drop hold up?

**Hitters (FP/PA, settleable, n=1128):** YES, cleanly.

| signal | mean realized FP/PA | n |
|---|---|---|
| add  | **0.576** | 113 |
| hold | 0.488 | 684 |
| drop | **0.400** | 331 |

**Starters (FP/start, settleable, n=236):** signal is **inert — 100% `hold`.**
No add/drop rows exist to order. Mean realized over all (hold) rows = 10.75.

**Relievers (season-to-date actual, ordinal check only):** ordering holds —
add 157.4 > hold 99.1 > drop 67.9 (n add/hold/drop = 74/377/725). Magnitudes are
season-to-date totals, not forward, so read as ordinal only.

### BUY/FADE hit rates (hitters — the only bucket with live add/drop)

Two framings; both reported because they answer different questions.

**(a) Settler framing — beat the model's own PROJECTION by the ±0.02 FP/PA
threshold** (a deliberately hard bar):
- BUY (add): n=113, **BUY_HIT 30.1%**, mean residual −0.040 FP/PA
- FADE (drop): n=331, **FADE_HIT 44.4%**, mean residual −0.002 FP/PA

**(b) Decision framing — did the call beat positional REPLACEMENT** (what the
signal actually claims):
- add → realized FP/PA > replacement: **75.2%** of the time (n=113)
- drop → realized FP/PA < replacement: **81.9%** of the time (n=331)

The signal's *directional* claim (above/below replacement) is strongly right; it
just doesn't systematically beat its own point estimate by 0.02 (residuals are
near-zero-mean, i.e. the projection is roughly unbiased — which is the calibration
result below, not a signal failure).

### Calibration — bucket projections into quintiles, realized per quintile

**Hitters (FP/PA):** monotonic and near the 45° line (projection ≈ unbiased).

| quintile | n | mean proj | mean realized |
|---|---|---|---|
| Q1 | 226 | 0.380 | 0.371 |
| Q2 | 225 | 0.442 | 0.422 |
| Q3 | 226 | 0.480 | 0.450 |
| Q4 | 225 | 0.522 | 0.525 |
| Q5 | 226 | 0.596 | 0.587 |

**Starters (FP/start):** monotonic in realized; top quintile under-projected
(proj 12.7 vs realized 15.6 — the model is conservative on the best arms).

| quintile | n | mean proj | mean realized |
|---|---|---|---|
| Q1 | 48 | 7.15 | 8.28 |
| Q2 | 47 | 8.62 | 10.10 |
| Q3 | 47 | 9.57 | 9.62 |
| Q4 | 47 | 10.54 | 10.23 |
| Q5 | 47 | 12.73 | 15.56 |

**Relievers:** NOT reported — full-season projection vs partial actual is a unit
mismatch (would falsely show ~2× over-projection that is purely the partial-season
artifact, not model error).

---

## Why the SP signal is inert (the sharpest weakness)

At split 30 the SP-45 replacement is 10.35 FP/start. The 2026-06-03 σ
recalibration (×2.41, which made the p25/p75 bands honestly cover ~50% of
outcomes) blows the band width to ≈±5.4 FP/start (mean σ ≈ 8.0). Result: the best
p25 across all SPs is 10.0 (never > replacement → no ADD), and the worst p75 is
11.2 (never < replacement → no DROP). The calibration fix that made the CI honest
**simultaneously neutered the add/drop trigger.** The rp3 *projection* still
carries signal (ρ 0.40, monotonic quintiles), but the SP *signal column* is
decoration in 2026. This is the single clearest place the headline+signal layer is
weak and worth a design look (e.g. a separate decision-band σ vs a
coverage-calibrated display σ).

---

## n per cell

Hitters, settleable (as-of gate + ≥30 forward PA):

| split (cutoff) | add | drop | hold |
|---|---|---|---|
| 30 (4/25) | 28 | 83 | 162 |
| 37 (5/2)  | 25 | 78 | 183 |
| 44 (5/9)  | 30 | 82 | 175 |
| 51 (5/16) | 30 | 88 | 164 |

Starters, settleable: split 30 n=120, split 37 n=116 (all `hold`).
Relievers, ranking panel: 163–171 per split, splits 30–72.

---

## Honest scope caveat (per memory rule 12 — full-stack lens)

This backtest tests the **reconstructable MODEL + SIGNAL backbone** only:
rh3/rp3/rprs2 point projection, p25/p75 bands, replacement-relative add/hold/drop.
It does **NOT** test the live-lens verdict layer (PL ranks, archetype model,
boom_stack, sustainability buckets, triangulate synthesis). Those depend on
WebFetched PL snapshots, live ESPN roster state, and as-of archetype caches that
are **not faithfully reconstructable** for historical dates — re-deriving them
today would smuggle in post-hoc information (the exact leakage this exercise
guards against). So the user-facing "verdict" can be better or worse than this
backbone; this run bounds only the part we can score cleanly. The hitter backbone
is the strongest-supported layer; the SP signal and RP in-season calibration are
the parts to trust least.
