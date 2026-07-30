---
signal: verdict_backtest settlement gate — replace the hardcoded AS_OF with a
  per-bucket cutoff derived from the panel's own data freshness
formula: |
  OLD: keep row iff (AS_OF_const - cutoff_date).days >= SETTLEMENT_WINDOWS[b]["days"],
       AS_OF_const = date(2026, 6, 9)   # frozen literal, bucket-blind
  NEW: data_asof(b) = max(cutoff_date) over the bucket's own 2026 panel rows
       keep row iff cutoff_date <= data_asof(b) - SETTLEMENT_WINDOWS[b]["days"]
       (H 21d, SP 35d, RP 35d; optional --as-of override reproduces a historic run)
outcome: rank skill (Spearman proj vs realized forward), the add/hold/drop
  realized-FP ladder, and BUY_HIT / FADE_HIT rates, per bucket
expected_sign: NEGATIVE for the headline Spearman in all three buckets — this
  change is expected to make the reported record WORSE, not better. See
  "pre-registered expectations" below. A retro that got *better* on 3-8x the
  data would be the surprising result and would need explaining.
theory: |
  AS_OF exists so a decision is graded only after its settlement window has
  fully closed. A frozen literal is wrong in two independent ways.

  (1) STATIC. The caches advanced from split_day 51 to 125 (cutoffs 2026-04-25
      -> 2026-07-28/29) while the literal stayed at 2026-06-09. The gate
      therefore discarded 11 of 15 hitter split-days and 13 of 15 SP
      split-days. The script reported n=1234 / n=263 as "the record" when the
      panel held 3-5x that.
  (2) BUCKET-BLIND. One date cannot express three windows. It was already being
      *used* per-bucket (H 21d vs SP 35d subtract off the same anchor), so the
      per-bucket shape was implicit; making it explicit is the honest form.

  WHY THE ANCHOR IS DATA FRESHNESS, NOT WALL-CLOCK `today`.
  The realized target in these panels (`ros_full_fp_per_pa`, `ros_fp_per_start`)
  is rest-of-season TRUNCATED AT THE LAST DATE IN THE CACHE, not at season end.
  Measured: split 121 (cutoff 07-25) has max ros_pa = 17 (3 days of forward
  data); split 125 has ros_pa = NaN (zero forward data). So a `today`-anchored
  gate is only accidentally correct — it is right exactly when the cache is
  fresh, and silently wrong the moment a refresh fails. If wall-clock ran a
  week ahead of the cache, `today - 21d` would admit split-days holding 14 days
  of forward data and grade them as closed 21-day windows. That is the
  silent-default failure class of docs/rh3_harness_root_bug_2026-07-28.md
  wearing a different hat: a confident number computed from an input that
  wasn't there. Anchoring on max(cutoff_date) of the bucket's own panel makes
  the gate structurally incapable of admitting a window the data cannot cover.
  (Today the two anchors happen to agree: 2026-07-30 - 21 = 07-09 and
  2026-07-28 - 21 = 07-07 both admit exactly splits 30..100. The point is that
  they agree by luck, and only the data anchor keeps agreeing.)

  THIRD DEFECT FOUND WHILE READING: the RP bucket had NO gate at all. `main()`
  applied `window_elapsed` to H and SP only, so the reported reliever number
  (rho=0.802, n=3099) included split 125 — a split whose forward window is
  literally empty. The RP lens reports a FULL-YEAR-basis rank correlation
  (proj_full vs season-to-date fp_year_total) rather than a forward one, which
  is why the omission was invisible: that statistic is defined at every split.
  It is also why it is partly MECHANICAL — `fp_with_role_to`, an input to the
  projection, is contained in `fp_year_total` — and the per-split ladder in the
  OLD run shows it plainly: rho climbs monotonically 0.550 (split 30) ->
  0.962 (split 125) as more of the season becomes already-banked. Pooling that
  across all 15 splits is what produced 0.802. Gating RP on the same rule
  removes the highest-rho (most mechanical) splits, so RP rho must FALL.
production_target: none. Rule 13 — this is the measurement layer. No rh3 / rp3 /
  rprs2 / baseline-xFP value moves, no FEATS list is touched. The only thing
  that changes is WHICH already-computed rows the retro is allowed to grade.
framing: |
  Not a feature search. One pre-registered structural change to one gate, three
  buckets, reported whether it helps or hurts. No knob is tuned to a result: if
  the add/hold/drop ladder stops being monotone at the larger sample that is
  reported AS a finding about decision quality, not repaired.
holdout_years: |
  2026 in-season only. The graded panel is 2026 split_days 30-125, cutoff dates
  2026-04-25 through 2026-07-28 (hitters/starters) and 2026-07-29 (relievers).
  This is a single in-season window, NOT a multi-year holdout — stated
  explicitly because a prior memo was flagged for carrying boilerplate
  holdout_years [2024, 2025] over a single-window panel.
training_years: |
  2018-2025 (RH3.TRAIN_YEARS / RP3.TRAIN_YEARS). The production pkls are loaded,
  not refit, so predicting 2026 rows is out-of-sample BY YEAR. Unchanged by this
  edit.
validation_script: scripts/xfp/verdict_backtest.py
date: 2026-07-30
---

# verdict_backtest was grading four hitter split-days out of fifteen

## The defect

`scripts/xfp/verdict_backtest.py:32`

```python
# "today" = data freshness cutoff. Models/data run through 2026-06-09.
AS_OF = date(2026, 6, 9)
```

The comment is the giveaway: the constant is a *cache-freshness* claim, written
as a literal, in a file that reads the cache. The cache has since advanced ten
split-days. The comment is now false and nothing in the program can notice.

Panel span actually available (all three rolling caches, 2026 rows):

| split_day | 30 | 37 | 44 | 51 | 58 | 65 | 72 | 79 | 86 | 93 | 100 | 107 | 114 | 121 | 125 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cutoff | 04-25 | 05-02 | 05-09 | 05-16 | 05-23 | 05-30 | 06-06 | 06-13 | 06-20 | 06-27 | 07-04 | 07-11 | 07-18 | 07-25 | 07-28/29 |

Admitted by the OLD gate: hitters `30,37,44,51` (4 of 15); starters `30,37`
(2 of 15); relievers all 15 (no gate applied at all).

## The design chosen, and the one rejected

Rejected: `AS_OF = date.today()`. It fixes the staleness and nothing else. It
still cannot express three windows, and it decouples the gate from the thing the
gate is actually about — whether the forward data exists. It is correct only
while the refresh is healthy, which is precisely the condition under which a
guard is not needed.

Chosen: **per-bucket cutoff derived from the bucket's own panel.**

```python
data_asof(panel) = max(cutoff_date) over its 2026 rows
settlement_cutoff(bucket) = data_asof - SETTLEMENT_WINDOWS[bucket]["days"]
keep row iff cutoff_date <= settlement_cutoff(bucket)
```

Three properties the literal did not have: it cannot go stale (it is read from
the data each run); it is per-bucket by construction (H 21d, SP 35d, RP 35d,
sourced from `SETTLEMENT_WINDOWS`, so a window edit propagates); and it cannot
admit a window the cache cannot cover.

`--as-of YYYY-MM-DD` overrides the derived anchor, and only exists to reproduce
a historical run (e.g. `--as-of 2026-06-09` reproduces the numbers below in the
OLD column). A missing or unparseable `cutoff_date` raises rather than being
dropped or defaulted — an unparseable date silently failing the `<=` comparison
would quietly shrink the panel with no diagnostic, which is the same silent
class of bug in miniature.

## Pre-registered expectations (written before running the new gate)

1. **n rises sharply for H and SP, and FALLS for RP.** H 4 -> 11 split-days,
   SP 2 -> 9. RP goes the other way, 15 -> 9, because RP was never gated.
2. **Headline Spearman falls in all three buckets.**
   - H/SP: the surviving early splits carry the longest forward windows
     (split 30 = ~94 days of forward data), and a longer window averages out
     more per-PA / per-start noise, so its rank correlation is the flattering
     end of the range. Adding 06-27 and 07-04 anchors, whose forward windows
     are 21-31 days, pulls toward the honest short-horizon number. Prior art
     (gotcha #13, `model_forward_calibration_2026-06-26.md`) puts real forward
     rank skill at rh3 ~0.35 / rp3 ~0.40 over 2-3 weeks, so I expect movement
     from 0.500/0.506 toward roughly **0.42-0.48 (H)** and **0.42-0.50 (SP)**.
   - RP: mechanically, dropping the six highest-rho splits (0.878-0.962) must
     lower the pool. Expect roughly **0.68-0.74** vs 0.802.
3. **The add/hold/drop ladder narrows.** I expect add > hold > drop to survive
   in H and RP. SP is the one I would not bet on: its OLD `add` cell is n=23
   with a BUY_HIT rate of 0.652, which is 15 hits — a number that has no right
   to replicate. I expect the SP BUY_HIT rate to fall substantially toward the
   H-like 0.2-0.4 band, and I am pre-committing that if the SP ladder loses
   monotonicity it is **reported as a finding about the SP add signal**, not
   patched, re-thresholded, or re-gated.
4. **Every number in the F3 repair report is superseded.** Named in full below.

---

## RESULTS

Both runs are the same script over the same caches and the same production
pkls; the ONLY difference is which rows the gate admits. OLD is reproducible
today with `python scripts/xfp/verdict_backtest.py --as-of 2026-06-09` (verified
below).

### Panel admitted

| bucket | window | OLD anchor / cutoff | OLD split-days | NEW anchor / cutoff | NEW split-days |
|---|---|---|---|---|---|
| H  | 21d | 2026-06-09 / <=2026-05-19 | 4 of 15 (30-51) | 2026-07-28 / <=2026-07-07 | 11 of 15 (30-100) |
| SP | 35d | 2026-06-09 / <=2026-05-05 | 2 of 15 (30-37) | 2026-07-28 / <=2026-06-23 | 9 of 15 (30-86) |
| RP | 35d | *(no gate applied)* | 15 of 15 (30-125) | 2026-07-29 / <=2026-06-24 | 9 of 15 (30-86) |

### HITTERS (rh3, FP/PA)

| | OLD | NEW |
|---|---|---|
| n settled | 1234 | **3546** (+187%) |
| Spearman(proj, realized fwd) | 0.500 (p=3.5e-79) | **0.444** (p=5.9e-171) |
| ladder: add | 0.5700 (n=139) | 0.5610 (n=410) |
| ladder: hold | 0.4981 (n=786) | 0.5033 (n=2151) |
| ladder: drop | 0.4089 (n=309) | 0.4186 (n=985) |
| ladder monotone add>hold>drop | YES | **YES** |
| BUY n / BUY_HIT rate | 139 / 0.216 | 410 / **0.224** |
| BUY mean residual | -0.045 | -0.062 |
| FADE n / FADE_HIT rate | 309 / 0.395 | 985 / **0.373** |
| FADE mean residual | +0.012 | +0.022 |

### STARTERS (rp3, FP/start)

| | OLD | NEW |
|---|---|---|
| n settled | 263 | **1134** (+331%) |
| Spearman(proj, realized fwd) | 0.506 (p=1.7e-18) | **0.423** (p=2.0e-50) |
| ladder: add | 16.17 (n=23) | 15.48 (n=101) |
| ladder: hold | 10.58 (n=162) | 10.83 (n=722) |
| ladder: drop | 8.22 (n=78) | 8.62 (n=311) |
| ladder monotone add>hold>drop | YES | **YES** |
| BUY n / BUY_HIT rate | 23 / 0.652 | 101 / **0.485** |
| BUY mean residual | +2.065 | +0.890 |
| FADE n / FADE_HIT rate | 78 / 0.333 | 311 / **0.350** |
| FADE mean residual | +0.399 | +0.644 |

### RELIEVERS (rprs2, ranking lens only — full-year proj vs season-to-date FP)

| | OLD (ungated) | NEW (35d gate) |
|---|---|---|
| n | 3099 (15 splits) | **1846** (9 splits) |
| Spearman pooled | 0.802 | **0.702** |
| per-split range | 0.550 (sp30) -> 0.962 (sp125) | 0.550 (sp30) -> 0.849 (sp86) |
| ladder: add | 237.6 (n=209) | 241.2 (n=107) |
| ladder: hold | 146.4 (n=704) | 142.1 (n=487) |
| ladder: drop | 90.2 (n=2186) | 92.3 (n=1252) |
| ladder monotone add>hold>drop | YES | **YES** |

### Is the ladder still monotone at the larger sample? YES — in all three buckets.

`add > hold > drop` in realized forward FP survives 2.9x the hitter sample and
4.3x the starter sample. The ordering was NOT an artifact of the four
early-season split-days. The gaps narrow (H add-minus-drop 0.161 -> 0.142
FP/PA; SP 7.95 -> 6.87 FP/start) but the sign and order hold everywhere. Per the
pre-registration this was the outcome I would not have bet on for SP, and it
came out clean, so it stands as evidence for the SP add/drop signal rather than
against it.

### Pre-registration scorecard

| prediction | outcome |
|---|---|
| H 4 -> 11 split-days, SP 2 -> 9, RP 15 -> 9 | **HIT**, exactly |
| H rho falls to ~0.42-0.48 | **HIT** — 0.500 -> 0.444 |
| SP rho falls to ~0.42-0.50 | **HIT** — 0.506 -> 0.423 |
| RP rho falls to ~0.68-0.74 | **HIT** — 0.802 -> 0.702 |
| ladder narrows but add>hold>drop survives in H and RP | **HIT** |
| SP BUY_HIT falls substantially, toward 0.2-0.4 | **PARTIAL MISS** — it fell hard (0.652 -> 0.485, and BUY mean residual 2.065 -> 0.890) but landed above my band. Reported as it came out; the band is not moved after the fact. |

## What the larger panel reveals that four split-days hid

Forward rank skill **decays monotonically as the forward window shortens**, and
the OLD gate reported only the fattest-window end of that decay:

| split (cutoff) | 30 (04-25) | 44 (05-09) | 58 (05-23) | 72 (06-06) | 86 (06-20) | 100 (07-04) |
|---|---|---|---|---|---|---|
| H rho | 0.551 | 0.484 | 0.490 | 0.449 | 0.394 | 0.367 |
| SP rho | 0.504 | 0.458 | 0.416 | 0.368 | 0.337 | — |

Split 30's forward window is ~94 days; split 100's is ~24. So 0.500/0.506 was
never "the model's forward skill" — it was the model's skill at the longest
horizon in the panel, averaged over the only four (two) anchors the frozen
literal let through. The NEW pooled 0.444 / 0.423 sit between the long-horizon
and short-horizon ends, and the per-split tail (H 0.357-0.367, SP 0.337 at ~3-5
weeks) lands right on the independently-measured forward skill in
`model_forward_calibration_2026-06-26.md` (rh3 ~0.35, rp3 ~0.40 over 2-3 weeks)
— two different harnesses converging on the same honest number.

Quintile calibration is unchanged in shape at the larger n (mild compression:
bottom quintile proj 0.378 vs realized 0.396; top 0.605 vs 0.574 for hitters;
SP 7.67 vs 8.51 and 13.53 vs 14.00), consistent with gotcha #13 — no
intercept, no shrinkage change, nothing to fix.

The RP number moves the most and is the one to re-read carefully: the OLD 0.802
was a pool over 15 splits whose per-split rho climbs 0.550 -> 0.962 purely
because `fp_year_total` (the "actual") increasingly consists of
`fp_with_role_to` (a model input). The gated 0.702 is less contaminated but the
lens remains partly mechanical — that caveat was already in the script and is
unchanged.

## Reproduction check

```
$ python scripts/xfp/verdict_backtest.py --as-of 2026-06-09
[settlement] AS-OF OVERRIDE 2026-06-09 — reproducing a historical run
  H   data_asof=2026-06-09  window=21d  cutoff<=2026-05-19  rows 5484->1302  split_days=[30, 37, 44, 51]
  SP  data_asof=2026-06-09  window=35d  cutoff<=2026-05-05  rows 2548->318   split_days=[30, 37]
HITTERS  n=1234  rho=0.500  BUY_HIT 0.216 (n=139)  FADE_HIT 0.395 (n=309)
STARTERS n=263   rho=0.506  BUY_HIT 0.652 (n=23)   FADE_HIT 0.333 (n=78)
```

Byte-identical to the F3 numbers for H and SP, so the OLD column above is the
actual historical run and not a re-derivation. RP does **not** reproduce under the
override (0.555 / n=372 vs the reported 0.802 / n=3099) — because RP was never
gated at all, so there is no anchor that reproduces it. That non-reproduction is
the RP defect made visible.

## Prior numbers this invalidates

Every one of these came from the AS_OF=2026-06-09 gate and must be replaced by
the NEW column above. They were correct as *arithmetic*; they were wrong as *the
record*, because they described 4/15 and 2/15 of the available panel.

1. `data/research/validation_runs/verdict_backtest_host_repair_2026-07-29.md`
   (F3), results table lines 128-130 — all three rows:
   - HITTERS n=1234, rho **0.500**, ladder 0.570/0.498/0.409, BUY_HIT 0.216 (n=139), FADE_HIT 0.395 (n=309)
   - STARTERS n=263, rho **0.506**, ladder 16.17/10.58/8.22, BUY_HIT 0.652 (n=23), FADE_HIT 0.333 (n=78)
   - RELIEVERS n=3099, rho **0.802** pooled — additionally invalidated as an
     *ungated* pool, not merely a stale one.
2. `docs/next_level_program_2026-07-29.md:117` — "hitters Spearman 0.500,
   starters 0.506, relievers 0.802".
3. `data/research/validation_runs/verdict_backtest_2026-06-11.md` — the original
   run. Its H/SP numbers were honest at the time (the caches genuinely ended
   2026-06-09), so it is superseded by data rather than wrong; its RP figures
   were ungated then too and are wrong for that reason.
4. `data/research/validation_runs/_bt_hitters.csv`, `_bt_pitchers.csv`,
   `_bt_relievers.csv`, `_bt_results.pkl` — regenerated by this run; any
   downstream read of the previous files is stale.

Not invalidated: `scripts/xfp/validate_band_crps.py` and
`band_crps_calibration_2026-07-29.md`, which import only `build_hitter_panel` /
`build_pitcher_panel` / `lookup_sigma_vec` and never touched the settlement gate
(verified by import inspection).

## Rule 13 / scope

No projection value changes. No FEATS list touched. `rh3` / `rp3` / `rprs2` /
baseline xFP are loaded from the shipped pkls and are byte-identical across both
runs — only the row filter differs. Files changed:
`scripts/xfp/verdict_backtest.py`,
`tests/test_verdict_backtest_settlement_gate.py`, this memo.

## Test coverage added

`tests/test_verdict_backtest_settlement_gate.py`, 17 tests. **All 17 were run
against the pre-change `scripts/xfp/verdict_backtest.py` (restored from HEAD)
and all 17 FAIL there**; all 17 pass after. They pin: the anchor is derived from
the panel (a panel fresh to 2026-09-01 must not be emptied by a 2026-06-09
literal); each bucket anchors on its own panel's freshness; the cutoff is
per-bucket and read from `SETTLEMENT_WINDOWS` (a 25-day-old decision settles for
H and not for SP — unrepresentable with one date); an unclosed window is
excluded at an inclusive boundary matching `settle_decision`; the
zero-forward-data split is excluded in every bucket; `gate_panels` covers all
three buckets and RAISES if a reported bucket is missing; missing / unparseable
/ null `cutoff_date` and an empty panel all RAISE; and no module-level `AS_OF`
default exists any more.

Full suite: **1227 passed** (1210 baseline + 17 new).

---

verdict: SHIP. The settlement gate is now derived per bucket from each panel's
own data freshness, with the 2026-06-09 literal retained only as an explicit
`--as-of` reproduction override. The graded panel grows 1234 -> 3546 hitter rows
and 263 -> 1134 starter rows, and the reliever bucket is gated for the first
time (3099 ungated -> 1846). All three headline Spearmans FALL as
pre-registered — H 0.500 -> 0.444, SP 0.506 -> 0.423, RP 0.802 -> 0.702 — and
those lower numbers are the correct ones: the old figures described the
longest-forward-window corner of the panel. The add > hold > drop ladder REMAINS
MONOTONE in all three buckets at 3-4x the sample, so the decision signal's
ordering is real and not an early-season artifact. Rule 13 respected; no
projection moves.

