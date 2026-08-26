---
signal: sp_regime_break (absence-anchored re-basing)
formula: split a pitcher's season at an inter-start gap >= 25 days (ABSENCE, an objective event) or at a searched changepoint (SEARCHED); post-break FP/start shrunk toward prior-year FP/start with a 5-start pseudo-count; CORROBORATED when post-break K% is within 5pp of prior-year K%
outcome: rest-of-season FP/start
expected_sign: +
theory: rp3 leans on `fp_per_start_to`, a season-to-date aggregate. When a season spans a structural break, that aggregate averages two different pitchers and describes neither; re-anchoring on the post-break segment, corroborated by prior-year level, should beat the contaminated mean.
production_target: research-only
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2017, 2018, 2019, 2021, 2022, 2023]
validation_script: TBD — NOT YET VALIDATED
date: 2026-08-26
verdict: RESEARCH-ONLY
---

# SP regime-break contamination — diagnostic finding, NOT a validated signal

## Status, stated first

**This is a DIAGNOSTIC, not a ranker.** No projection column moves. It has not
been through the Rule 2 bars. The related-but-different signal
`stuff_regime_delta` (short rolling K% window vs season-to-date) was **REJECTED**
earlier the same day — see `stuff_regime_delta_2026-08-26.md`. That rejection
does not cover this mechanism, and this memo does not claim it does.

## What differs from the rejected signal

| | stuff_regime_delta (REJECTED) | sp_regime_break (this) |
|---|---|---|
| trigger | rolling window, every split point | an OBJECTIVE event (>=25-day absence) |
| window | ~5 starts (100 TBF), max 8 | the whole post-break segment |
| comparator | season-to-date | **prior-year established level** |
| confirmation | none | two-source agreement (post-break K% ≈ prior-year K%) |

The rejected version searched blindly and its pooled positive was pseudo-
replication (sign flipped to −0.0488 at one row per pitcher-year). The ABSENCE
variant performs **no search**, so it carries no multiple-testing penalty. The
SEARCHED variant does search and is only reported when prior-year corroborates.

## Canonical cases (2026)

| pitcher | break | pre | post | prior yr | board | adj | Δ |
|---|---|---|---|---|---|---|---|
| Jacob Lopez | ABSENCE 40d, back 7/10 | 2.8 FP / 15.7% K | **14.8 / 29.6%** | 11.2 / 27.7% | 10.6 | 13.4 | **+2.8** |
| Bryce Miller | SEARCHED 7/09 | 21.2 / 34.3% | **4.1 / 15.9%** | 7.1 / 18.9% | 13.2 | 5.2 | **−8.0** |
| José Soriano | SEARCHED 4/28 | 22.4 / 30.6% | **9.2 / 21.6%** | 10.0 / 21.0% | 11.9 | 9.3 | **−2.6** |
| Noah Cameron | SEARCHED 7/11 | 8.8 / 21% | **17.2 / 21%** | 13.5 / 20% | 11.2 | 15.6 | **+4.4** |

Miller is the cautionary one in BOTH directions: a session recommendation earlier
the same day called him a "buy-low" on the strength of the widest ours-vs-PL gap
on the board. That gap was the contaminated season aggregate. His post-break
form is 4.1 FP/start on a 15.9% K%, and his prior-year K% (18.9%) says the
34.3% first half was the anomaly, not the 15.9% second half.

## Scale of the problem

`scripts/xfp/sp_regime_scan.py` flags **49 SPs** with |post-break − board rate|
>= 2.0 FP/start, of which 6 are on the Ligers roster and 11 are free agents.

## Secondary finding — IL feature coverage gap

`data/research/xfp_cache/il_split_features_2018_2026.csv` is a full-population
cache (2,723 pitchers for 2026, including `il_stints_to = 0` rows). Yet **2 of
the 11 absence-break pitchers have ZERO rows for 2026** — Jacob Lopez (40-day
gap) and Andrew Painter (44-day gap). For those pitchers all three rp3 IL
features fall back to defaults.

Note a correction against an earlier reading in-session: `is_on_il_at_split = 0`
for Lopez is **correct** (he is active). The defect is the missing rows, not
that flag. Same failure family as the 2026-07-10 incident where the three IL
features sat dead at a 0.45% join rate for six weeks. **Recommend a
`/model-health` tripwire on IL-cache row coverage per rostered SP.**

## Proposed model change — sequencing matters

1. **Now (no validation needed):** ship the scan as a context-only diagnostic
   and route flagged rows to `/triangulate`. Nothing re-ranks.
2. **Next:** pre-register and validate the ABSENCE variant on its own —
   restricted to pitcher-seasons that actually contain a >=25-day gap (~10-15%
   of the population), one row per pitcher-year to avoid the pseudo-replication
   that killed the rejected signal, full RP3_FEATS baseline on a machine with
   the statcast substrate.
3. **Only if it passes:** integration is a separate Rule 7 request. The likely
   shape is not a new feature but a **re-basing of `fp_per_start_to` and the
   rate terms onto the post-break segment** when an absence break exists and
   prior-year corroborates — a change to how an existing feature is computed,
   which needs its own full-pipeline backtest.

Do NOT skip step 2. The whole reason this memo exists is that a plausible
neighbouring signal failed its test the same day.

---

# BACKTEST RESULTS (2026-08-26, same day) — SEARCHED REJECTED, ABSENCE promising

`scripts/xfp/backtest_sp_regime.py`. **Strictly no lookahead**: at each as-of
point the break is detected using ONLY starts 1..t; prior-year aggregates are
legitimately known at t; the outcome (starts t+1..N) never touches the estimator.
Baseline = season-to-date mean FP/start, which is rp3's dominant term.

| slice | n | MAE base → adj | r base → adj | adj better |
|---|---|---|---|---|
| **TRAIN pooled, ABSENCE** | 197 | 3.44 → **2.80** (−0.63) | .530 → **.680** | 129/197 (65%) |
| **TRAIN pooled, SEARCHED** | 2970 | 3.15 → **3.47 (+0.33)** | .521 → .466 | 1274/2970 (43%) |
| TRAIN one-row, ABSENCE | 23 | 3.67 → 3.62 (−0.05) | .523 → .605 | 14/23 |
| TRAIN one-row, SEARCHED | 241 | 3.13 → **3.38 (+0.25)** | .543 → .497 | 107/241 (44%) |
| **HOLDOUT pooled, ABSENCE** | 82 | 3.39 → **3.17** (−0.22) | .453 → .469 | 39/82 (48%) |
| **HOLDOUT pooled, SEARCHED** | 1417 | 3.08 → **3.41 (+0.33)** | .499 → .400 | 573/1417 (40%) |
| HOLDOUT one-row, SEARCHED | 120 | 3.16 → **3.43 (+0.27)** | .497 → .444 | 45/120 (38%) |

## SEARCHED — REJECTED, and removed from the board

Worse on **every** slice: train and holdout, pooled and one-row-per-season. It
beats simply using the season level in only **38-44%** of cases — worse than a
coin flip. Applying it destroys correlation (holdout .499 → .400).

**Root cause, diagnosed:** `find_searched()` has no magnitude or significance
gate. It returns the max-separation split unconditionally, so it fires on
**80.1%** (1063/1327) of pitcher-seasons. It is not detecting structure; it is
splitting each season at its noisiest point, and prior-year K% corroboration is
too weak a filter to stop it. ABSENCE, with an objective trigger, fires on 19.9%.

`sp_regime_board.py` was patched the same day: SEARCHED breaks are surfaced as
`[SEA unvalidated]` for human review but **never move `adj`**. Ten previously
published adjustments were retracted, including Noah Cameron +4.5, Bryce Miller
−7.3, José Soriano −2.8 and Shota Imanaga −2.1.

Deliberately NOT tuned: adding a magnitude gate to SEARCHED and re-testing on
this holdout would be fitting to the test set. Any such gate needs a fresh
pre-registration and a fresh holdout.

## ABSENCE — promising, still NOT validated

Improves MAE and correlation on both train and holdout, and it is the variant
with the objective trigger and no multiple-testing exposure. But independent-
sample n is thin — **23 train / 9 holdout pitcher-seasons** — and the holdout
win rate is only 48%. The pooled −0.63 MAE gain is inflated by pseudo-
replication; the honest one-row train figure is −0.05.

Verdict: keep as a **diagnostic**. Do not promote to a ranker on this evidence.
A proper run needs the full RP3_FEATS baseline and many more absence seasons
(widening to 2015-2016 and relaxing the >=15 GS cohort would roughly double n).

## Decision consequence recorded

The two drops under consideration when this backtest ran — Imanaga and Soriano —
were **both SEARCHED**. The backtest says their adjusted numbers are not usable.
Imanaga's raw 2026 line shows no decline at all (K% 24.3 vs 20.6 in 2025; August
K% 30%, his second-best month), so that drop is affirmatively wrong. Soriano's
case survives only on evidence independent of this method (August/July K% 17-18%
vs a 21% career norm in both 2024 and 2025).
