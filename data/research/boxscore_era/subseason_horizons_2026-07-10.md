# Sub-season horizons (MONTH / PERIOD) from box-score data — feasibility probe + mini-study

Date: 2026-07-10. Companion to the deep-history SEASON model track (sibling agent owns
`data/research/boxscore_era/raw/` season panels — this memo owns `subseason_*` + `raw_probe/`).

---

## PRE-REGISTRATION (written before any correlations were computed)

**Question.** Does month-M hitter FP/PA carry ANY predictive signal for month-M+1 FP/PA
beyond (a) the player's season-to-date FP/PA level through month M and (b) his prior-season
FP/PA rate? Era-general version of the 2026-06-26 Statcast-era window study.

**Hypothesis (H0 we expect to CONFIRM).** Month-over-month adds ~0 beyond the level:
pooled partial r of month-M FP/PA with month-M+1 FP/PA, controlling for season-to-date
level + prior-season rate, will be |r| < 0.05 and its cluster-bootstrap 95% CI will span 0.
This is a confirmatory noise-floor measurement, NOT a promotion candidate (Rule 13 —
even a small positive result would be display/context-only pending /validate-feature).

**Design (fixed before data pull).**
- Sample: seasons **1985, 1995, 2005, 2015, 2024**; top ~45 hitters by PA per season
  (statsapi season leaderboard, playerPool=all) → target ~225 player-seasons.
- Data: statsapi `stats=byMonth&group=hitting` for season Y (1 call/player-season) +
  `stats=season` for Y−1 (1 call/player-season).
- Outcome/predictors: BrownU hitter FP = R + TB + RBI + BB + HBP + SB − K, per PA.
- Transitions: months April(4)–Sept(9) only; M ∈ {5,6,7,8} → M+1. Inclusion: **PA ≥ 50
  in both month M and month M+1**, prior-season **PA ≥ 300** (rows failing either are
  dropped; n reported honestly per era).
- Controls: `level` = cumulative FP/PA from April through month M (inclusive — this is
  the "full running season level" per the 2026-06-26 finding); `prior` = prior-season FP/PA.
- Primary statistic: partial r(month-M FP/PA, month-M+1 FP/PA | level, prior), per era and
  pooled, with a **player-season cluster bootstrap** 95% CI (2,000 resamples) on the pooled
  estimate. Secondary: the same for the within-player hot/cold delta (month − level), and
  the raw (unadjusted) r for reference.
- Decision rule: pooled partial r CI spanning 0 or |r| < 0.05 ⇒ "no exploitable
  month-over-month signal; sub-season projection = season-level anchor + variance band."
  Partial r ≥ 0.10 with CI excluding 0 in ≥3/5 eras ⇒ escalate to a full /validate-feature run.
- Weekly (PERIOD) analog: gameLog for a subsample (~10 players/era = ~50 player-seasons,
  1 call each), games aggregated to Mon–Sun weeks, weeks with PA ≥ 15, same partial-r test
  W → W+1 controlling for season-to-date level. Smaller n; treated as an extrapolation
  check on the monthly result, not a standalone verdict.
- Also computed (descriptive, feeds the variance-band deliverable): within-player SD of
  monthly FP/PA and weekly FP/PA by era.

---

## 1. Acquisition scoping (verified live 2026-07-10, probes cached in `raw_probe/`)

### 1.1 MLB Stats API reach — much deeper than expected

| Season probed | `byMonth` splits | `gameLog` (dated) | FP fields (PA/R/TB/RBI/BB/HBP/SB/K) |
|---|---|---|---|
| 1901 (Burkett) | ✅ 7 months | ✅ 142 games | ✅ all populated |
| 1927 (Combs) | ✅ 7 months | ✅ 152 games | ✅ all populated |
| 1955 (Al Smith) | ✅ 6 months | ✅ 154 games | ✅ all populated |
| 1975 (Cash) | ✅ 6 months | ✅ 162 games | ✅ all populated |
| 1985 / 1995 / 2005 | ✅ | ✅ | ✅ |

**Both `stats=byMonth` and `stats=gameLog` work back to 1901**, with every BrownU-FP
component present. The season top-PA leaderboard endpoint
(`/stats?stats=season&group=hitting&season=Y&sortStat=plateAppearances&playerPool=all`)
also works for every probed season, which solves player-id discovery without a Chadwick
crosswalk. Caveat: batter strikeouts were not an official stat in the NL 1897–1912 —
statsapi returns values (reconstructed), so treat pre-1913 K-dependent FP as approximate.

### 1.2 Call/time budget for a full month-level panel

Top-300 hitters/year × 30 years = 9,000 player-seasons:
- **byMonth panel**: 1 call/player-season + 30 leaderboard calls ≈ **9,030 calls ≈ 1.5 h**
  at the polite 2 req/s → **background job**, not a live-session build. (Optimization to
  verify later: bulk `people?personIds=…&hydrate=stats(...)` batches ~40 ids/call → ~15 min.)
- **gameLog panel** (needed for weekly/PERIOD): also 1 call/player-season but ~40× larger
  payloads → ~2–3 h + ~1–2 GB raw JSON → definitely background, and only worth it if the
  weekly variance-band deliverable (§4) is commissioned.
- The 5-era × 45-player mini-study below (≈500 calls, ~6 min) is the live-session ceiling.

### 1.3 Retrosheet (documented only — NOT downloaded)

- Free bulk event files (play-by-play) essentially complete from the 1910s; team game logs
  back to 1871. Zipped archives run ~10s of MB per decade, full event archive a few hundred
  MB. Parsing requires the Chadwick toolchain (`cwdaily` emits per-player per-game lines
  directly, which is exactly the month/week input shape).
- **Verdict: NOT needed for this track.** statsapi already serves per-game and per-month
  splits to 1901 with zero parsing infrastructure. Retrosheet only wins if we want (a) fully
  offline reproducibility, (b) context fields statsapi lacks (base-out states, park, batting
  order) or (c) independence from statsapi rate limits for an industrial rebuild. Rank:
  **statsapi byMonth/gameLog first; Retrosheet as the archival fallback.** Effort if ever
  needed: ~1–2 days for a cwdaily pipeline.

## 2. Mini-study results (pre-registered design above; panels in
`subseason_month_panel.csv` / `subseason_week_panel.csv`)

Realized sample: 225 player-seasons pulled → 900 month transitions → **856 qualifying**
(prior-season PA ≥ 300), 214 player-season clusters.

### 2.1 MONTH M → M+1, partial r(month-M FP/PA, month-M+1 FP/PA | level, prior)

| Era | n trans | n player-seasons | raw r | **partial r** |
|---|---|---|---|---|
| 1985 | 176 | 44 | +0.336 | **+0.076** |
| 1995 | 168 | 42 | +0.343 | **+0.083** |
| 2005 | 172 | 43 | +0.285 | **+0.021** |
| 2015 | 160 | 40 | +0.195 | **+0.063** |
| 2024 | 180 | 45 | +0.430 | **+0.197** |
| **POOLED** | **856** | **214** | +0.360 | **+0.101**, cluster-boot 95% CI [+0.027, +0.173] |

Benchmarks in the same panel: partial r(level | prior) = **+0.241**; partial r(prior |
level) = **+0.272**. ΔR² from adding the month term to level+prior: **+0.008 pooled**
(per era: +0.0045 / +0.0053 / +0.0004 / +0.0037 / **+0.0294**). Model R² tops out at 0.23
— **~77% of next-month FP/PA variance is unexplained by anything** (next-month SD 0.184
FP/PA).

**Pre-registered decision rule outcome:** the confirmation cell (|r| < 0.05, CI spans 0)
was NOT hit — but neither was the escalation cell (partial r ≥ 0.10 with CI excluding 0 in
≥ 3/5 eras: only **1/5** eras, 2024, clears 0.10). Post-hoc diagnostics (labeled as such):

- **Drop 2024:** pooled 1985–2015 partial r = **+0.070, CI [−0.015, +0.153] — spans 0.**
  The pooled significance is a single-era (2024) artifact; 2024 is also the one era the
  Statcast-era window study already covers with better (process) data and found L21 adds ~0.
- **By transition month:** +0.230 (May→Jun), −0.065 (Jun→Jul), +0.163 (Jul→Aug), +0.109
  (Aug→Sep) — sign-unstable, not a monotone momentum pattern.
- **Cleaner momentum split** (control = level through M−1, month M separate): month M
  partial r +0.208 vs old-months partial r +0.097 — i.e., what tiny signal exists is
  *recency-weighting of the talent estimate* (last month is worth somewhat more than a flat
  cumulative average when the season is young), NOT exploitable hot/cold streakiness. This
  is the same shape as the 2026-06-26 finding: the FULL running level absorbs it.

### 2.2 WEEK (PERIOD) W → W+1, gameLog subsample (50 player-seasons, weeks PA ≥ 15)

| Era | n trans | raw r | partial r (\| level) |
|---|---|---|---|
| 1985 | 235 | +0.019 | −0.002 |
| 1995 | 205 | +0.238 | +0.111 |
| 2005 | 240 | −0.017 | −0.055 |
| 2015 | 217 | +0.099 | +0.055 |
| 2024 | 221 | +0.123 | +0.013 |
| **POOLED** | **1,118** | +0.091 | **+0.023, CI [−0.046, +0.089] — spans 0** |

**Weekly hot/cold adds nothing beyond the season level, in every era since 1985.** The
PERIOD-horizon noise floor is confirmed directly, not just extrapolated.

### 2.3 Era-general variance bands (the useful by-product)

Within-player SD of FP/PA, by horizon (players with ≥4 qualifying months / ≥8 weeks):

| Era | monthly SD (n=45/era) | weekly SD (n=10/era) | mean rate |
|---|---|---|---|
| 1985 | 0.144 | 0.303 | 0.667 |
| 1995 | 0.140 | 0.269 | 0.695 |
| 2005 | 0.135 | 0.300 | 0.673 |
| 2015 | 0.150 | 0.315 | 0.615 |
| 2024 | 0.157 | 0.361 | 0.588 |

Two era-general facts: (a) a full-time hitter's true month is his level ± ~0.14 FP/PA
(≈ ±24% of the mean rate) and his week is ± ~0.30 (≈ ±50%) — the week is ~2× noisier than
the month, close to the √(PA-ratio) prediction, i.e. **pure sampling noise**; (b) the noise
band is remarkably stable across 40 years (mildly widening in the three-outcome era as
rates fall and K's rise). These are exactly the σ inputs /matchup-leverage and /season-sim
need, and they can now be quoted as era-general rather than Statcast-era-only.

## 3. Verdict

**Do not build a MONTH- or PERIOD-horizon box model.** The pre-registered escalation
criterion failed (1/5 eras); the pooled month effect is +0.07 (CI spans 0) once the single
2024 cell is removed, ΔR² ≈ +0.8 % (≈ +0.04 % at week level), and the weekly test confirms
the noise floor outright. This makes the 2026-06-26 Statcast-era conclusion **era-general**:
sub-season box prediction is level-anchored and variance-dominated in every era since 1985
(and the data to check earlier eras exists to 1901 if ever needed). The faint recency tilt
that does exist is already captured by using the running season level (and, in-season, by
rh3's own recency-decayed features) — Rule 13 applies: context, never a number-mover.

## 4. Roadmap recommendation

Deep history's value for sub-season horizons reduces to exactly the two channels the
mission anticipated:

1. **(a) Better SEASON/RoS priors.** The sibling's deep-history season model improves the
   anchor; every sub-season projection is (anchor × schedule/volume), so all sub-season
   lift flows through the anchor. No separate sub-season learner is warranted.
2. **(b) Era-general variance/noise bands per horizon** — the concrete deliverable:
   - A small table `subseason_variance_bands` keyed by (horizon ∈ {week, month}, PA-volume
     tier, era-bucket or era-adjusted K-environment), holding within-player SD of FP/PA and
     the implied shrinkage/reliability coefficient (var_true / var_observed) per horizon.
   - Built from a background-job statsapi pull (top-300 × 30 yrs byMonth ≈ 1.5 h; gameLog
     subsample for weekly ≈ +1 h for ~2,000 player-seasons — full 9,000 not needed for a
     variance estimate).
   - Consumers: `/matchup-leverage` and `/season-sim` σ inputs (replacing Statcast-era-only
     bands), and the CI widths quoted on any weekly matchup projection.
   - Pitcher analog (per-start FP SD by era) is a natural follow-on using the same
     endpoints (`group=pitching`), budget-equivalent.

If anyone revisits the 2024 month-level cell (+0.197): treat it as 1-of-5 multiple
comparisons on n=45 players until it replicates in 2025/2026 within the Statcast-era
harness — which already has better tools for that question.

---
*Artifacts: probes + raw JSON cache `data/research/boxscore_era/raw_probe/` (probe_api_reach.py,
subseason_ministudy.py, ministudy_manifest.csv, ~730 cached responses); panels
`data/research/boxscore_era/subseason_month_panel.csv` (900 transitions),
`subseason_week_panel.csv` (1,118 transitions). No commits made.*
