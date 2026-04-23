# Live Usage Monitoring Guide

What to watch over the first 2–3 weekly review cycles. This is not a formal
evaluation protocol — just the signals worth paying attention to before making
any threshold changes.

---

## 1. Buy / Regression Board Hit Rate

**What to track:** Of the players you acted on from buy or regression boards,
how often did outcomes move in the expected direction within 2–3 weeks?

**Green flags:**
- Buy targets show xwOBA improvement within 2 weeks of appearance
- Regression flags show xwOBA decline or plate approach correction
- Board stays 30–60 rows at maturity (not too sparse, not flooded)

**Yellow flags:**
- Board is consistently empty or has fewer than 10 rows at mature stage
- Every recommended player regresses in the wrong direction (possible model drift)
- The same players appear every single week with no movement

**Red flags:**
- Hit rate below 40% after 3+ cycles at mature stage (rank_gap may need recalibration)
- Buy and regression boards have significant player overlap

---

## 2. Breakout / Discipline / Power Board Usefulness

**What to track:** Are these boards surfacing players you wouldn't have spotted
otherwise? Or are they just listing obvious names?

**Breakout flags** — should surface players with elite process whose surface
stats haven't caught up. Look for players in the top 25% of Process+ but not
yet in the top 25% of xwOBA. Useful if at least 2–3 names per week are
non-obvious.

**Discipline targets** — Decision+ is the most stable early-season metric.
This board should be consistently useful regardless of stage. If it feels
redundant with the buy board, check for overlap.

**Power targets** — most useful mid-to-late season when the bar is lower (107).
Early season (bar = 110) will show fewer names. That is expected behavior.

**If these boards feel useless:** Check whether the min_pa filter is too low
(surfacing garbage-sample outliers) or too high (missing relevant players).

---

## 3. Confidence Label Usefulness

**What to track:** Are the tier labels (Tier A / Signal / Too Early) helping
you decide how much weight to give a recommendation?

**Questions to ask each week:**
- Did I act differently on Tier A vs Tier B recommendations?
- Did Tier A recommendations pan out better than Tier B?
- Does "Signal" (early Tier A, 80+ PA) feel like enough sample to trust?

**If labels feel wrong:**
- Early "Signal" (80 PA) still has wide variance — note if these feel too aggressive
- "Too Early" (< 40 PA) entries appearing on boards means the min_pa filter
  isn't blocking them — check `min_pa_for_boards` in stage config

---

## 4. Auto Stage Detection

**What to track:** Does the detected stage match what you'd call it based on
how the season feels?

Auto-detection uses league median PA from the loaded dataset:
- < 150 PA median → Early
- 150–320 → Mid
- > 320 → Mature

**When it will feel off:**
- Late April with some high-PA players skewing the median up → might show Mid
  when Early still feels right. Use the manual override.
- Historical review of a mid-season snapshot will auto-detect correctly
  because the data itself is mid-season.

**Log when you use the manual override and why.** If you override consistently
for a certain date range, that suggests the PA boundaries need adjustment.

---

## 5. Manual Override Usage

Track whether you use `--stage` override (CLI) or the sidebar selector.

| Override used | Reason | Week |
|---------------|--------|------|
| | | |

If you use the override more than once per cycle, the auto-detect boundary
probably needs shifting. Bring this up after 3 cycles with a note on what
the detected stage was and what felt more appropriate.

---

## When to Revisit Thresholds

**Don't touch thresholds based on one cycle.** The review period is 2–3 cycles
to accumulate enough signal.

Threshold changes are warranted if:
1. Buy/regression hit rate is consistently below 40% at mature stage after 3 cycles
2. Breakout board is consistently empty or consistently full of obvious names
3. Manual stage override is used every week for the same reason
4. Confidence labels are consistently inverted (Tier B outperforms Tier A)

Document the specific pattern in the weekly review log before proposing a change.
The calibration rationale is in `docs/season_stage_thresholds.md` — any change
should explain why the calibration is now wrong.

---

## Files

| File                          | Purpose                                      |
|-------------------------------|----------------------------------------------|
| `docs/weekly_review_template.md` | Fill in each week; copy per cycle           |
| `docs/live_usage_monitoring.md`  | This file — reference only, don't modify    |
| `docs/season_stage_thresholds.md` | Calibration rationale for current thresholds |
| `docs/fantasy_decision_framework.md` | Core methodology and signal definitions  |
