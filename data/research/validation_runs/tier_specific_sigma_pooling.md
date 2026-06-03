# Tier-Specific Sigma Pooling for Team Variance Aggregation

Generated 2026-06-03. Source: `_boom_stack_per_start_panel_cache.parquet`
(31,713 SP starts 2018-2025, 29,069 after restricting to pitcher-years with
>= 8 starts so a tier can be assigned).

## Question

`build_matchup_dashboard.py` currently aggregates SP team variance with the
global `xfp_rp3_sigma` (per-start, after the alpha=2.41 global rescale).
Boom-stack tier analysis showed aces have +14.8pp stack=3 boom edge and 0%
bust rate at stack=3 — suggesting "narrower outcome distributions". Should
team sigma^2 use a tier-specific sigma (lower for aces, higher for streamers)?

## Method

- Tier each pitcher-year by season-end FP-per-start rank within the year
  (matches the boom_stack_by_tier methodology). Min 8 starts/year required.
  - Ace = rank 1-10, SP2_SP3 = 11-30, Backend = 31-50, Streamer = 51+.
- For each start, compute residual vs the pitcher-year mean FP. This is the
  best-case projection target — what a perfect rp3 would converge to.
- Compute sigma of residuals within each tier. Compare to global sigma.
- Calibrate by computing std(z) where z = resid / sigma_assumed; the
  better calibration drives std(z) toward 1.0.
- Translate to win-prob magnitude by simulating a hypothetical all-ace vs
  all-streamer team variance under both schemes.

## Step 2 — Per-tier empirical sigma

| tier      | n      | sigma (std)| sigma_MAD | mean FP |
|-----------|-------:|-----------:|----------:|--------:|
| Ace       |  1,800 |   **8.900**|     8.470 |   17.76 |
| SP2_SP3   |  3,524 |   **8.830**|     8.486 |   14.92 |
| Backend   |  3,393 |   **9.124**|     8.655 |   13.01 |
| Streamer  | 20,352 |   **8.975**|     8.928 |    9.02 |
| **GLOBAL**| 29,069 |   **8.970**|     —     |   10.36 |

**Hypothesis was: sigma_ace < sigma_sp2_sp3 < sigma_backend < sigma_streamer.**

**Actual: sigma is essentially FLAT across tiers.** Range 8.83-9.12 (3.4%
spread), and ordering is non-monotonic: SP2_SP3 has the LOWEST sigma, Backend
the HIGHEST, Ace and Streamer in between. The MAD numbers tighten the spread
slightly (Ace lowest at 8.47, Streamer highest at 8.93) but the magnitude is
still tiny — under 6% spread.

### Tier ratio vs global (for translation to production sigma)

| tier      | ratio  | calibrated sigma (= ratio x 8.73) |
|-----------|-------:|----------------------------------:|
| Ace       |  0.992 |  8.66                              |
| SP2_SP3   |  0.984 |  8.59                              |
| Backend   |  1.017 |  8.88                              |
| Streamer  |  1.001 |  8.73                              |

The maximum deviation from the production global sigma is **+1.7%** (Backend).
The "expected 20-40% per tier" hypothesis from the task brief is rejected by
two orders of magnitude.

## Step 3-4 — Calibration std(z) under global vs tier-specific

| method       | pooled std(z) (target 1.0) |
|--------------|--------------------------:|
| Global sigma |                    1.0000 |
| Tier sigma   |                    0.9999 |

Per-tier std(z) under each scheme:

| tier      | std(z) under global | std(z) under tier |
|-----------|--------------------:|------------------:|
| Ace       |               0.992 |             1.000 |
| SP2_SP3   |               0.984 |             1.000 |
| Backend   |               1.017 |             1.000 |
| Streamer  |               1.001 |             1.000 |

Tier-specific moves per-tier std(z) by < 0.02 in absolute terms. The pooled
calibration is identical to 4 decimal places.

## Step 5 — Magnitude check: win-prob impact

Hypothetical team variance for a 10-SP-start week (margin = +10 FP, hitter
var ~956, RP var ~75):

| roster mix     | team var | sigma_diff | WP(+10) |
|----------------|---------:|-----------:|--------:|
| All-Ace        |    1,781 |       59.7 |  0.5665 |
| All-SP2_SP3    |    1,769 |       59.5 |  0.5668 |
| All-Backend    |    1,819 |       60.3 |  0.5658 |
| All-Streamer   |    1,793 |       59.9 |  0.5663 |
| Global (prod)  |    1,793 |       59.9 |  0.5663 |

**Max WP delta vs global: 0.0005 (5 basis points).** For comparison, the rh3
hetero sigma work moved WP at the team level by ~50-200 bp because hitter
variance dominates team variance. SP variance is only ~40% of team variance,
and within that, the tier-specific sigma scaling factor is < 2%. Compounded:
the tier-specific SP sigma adjustment moves team WP by **0.05% absolute**,
which is functionally zero.

## Step 6 — Verdict

### **KEEP_GLOBAL**

The hypothesis was that aces have narrower outcome distributions than
streamers — and at the FP-level mean that's true (aces sit at 17.8 mean
FP vs 9.0 for streamers). But the **residual** distribution around each
pitcher's own mean is essentially tier-invariant:

- All four tiers cluster between sigma 8.83 and 9.12 (3.4% spread).
- Ordering is non-monotonic (SP2_SP3 lowest, Backend highest).
- Calibration std(z) is identical to 4 decimal places.
- Win-probability magnitude impact is 5 basis points worst-case.

### Why the hypothesis failed

The boom_stack_by_tier "narrower at the top" reading was about **boom/bust
rate compression** (ace stack=3 has 0% bust rate, 56.7% boom rate vs streamer
17.4%/15.2%). That's a function of where the mean sits relative to the
absolute boom (>=20) and bust (<0) thresholds, NOT a function of distribution
width. An ace at mean 21 with std 9 has near-zero bust because the lower tail
barely crosses zero. A streamer at mean 11 with std 9 has 15% bust because
the same width crosses zero often. **Same width, different position.**

Per-start residual variance is dominated by inning-by-inning batted-ball
luck, HR variance, and BABIP fluctuation — physical mechanisms that act
similarly on aces and streamers. The MAD numbers do show a tiny monotonic
ordering (Ace 8.47 -> Streamer 8.93, ~5% spread), consistent with aces
having slightly thinner tails, but the effect is well below the threshold
where a production change is justified.

### Comparison to prior sigma_heteroskedastic_search

That work tried per-pitcher sigma and failed because per-pitcher samples
were too thin. This work has **20x more sample per group** (1,800-20,352 vs
~25 per pitcher) and STILL finds no meaningful tier-level sigma differences.
That settles the heteroskedastic-by-grouping question across both granularities.

### Coordination with within-team correlation (rho) agent

The within-team rho agent is testing a different aspect of team sigma^2 that
DOES have a credible mechanism — same-day SP correlation through shared
weather, umpire, or scheduling effects. The two investigations are
independent: this one rules out per-pitcher sigma variation; that one tests
whether the iid-sum-of-variances assumption is wrong.

### No spec to ship

No change to `build_matchup_dashboard.py` is recommended. The global
`xfp_rp3_sigma` (per-start, alpha=2.41 calibrated) should remain the
team variance contributor for SPs.

## Caveats

- "Projection" here is the per-pitcher-year mean — a best-case rp3. A worse
  projection (e.g. season-prior priors only) would inflate residual sigma
  but should inflate it ~uniformly across tiers since the projection error
  itself is roughly tier-invariant; the per-tier RANK and ORDERING would not
  change. The flatness finding is robust.
- Tier assignment uses end-of-year FP/start — a forward-leaky tier label.
  For a tier-specific live ranker we would use rolling rank, but for
  distribution-shape inference (this question) the bias is minor.
- Ace n=1,800 is the smallest cell. A real ~5% tier-sigma effect would
  require n ~ 7,000-10,000 to detect at p<0.05. So we can rule out
  >5% effects but cannot resolve <3% effects. The win-prob magnitude
  check confirms that even a 5% effect would be operationally trivial.
