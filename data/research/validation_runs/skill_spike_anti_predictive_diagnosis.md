# Why is `flag_skill_spike` Anti-Predictive at SP2/3 + Backend?

Generated 2026-06-03. Diagnostic follow-up to `boom_stack_by_tier.md`.

## 0. Finding being explained

From `boom_stack_by_tier.md` Section 3, edge of `flag_skill_spike` on boom% (next start FP ≥ 20):

| Tier | n(spike=1) | boom% on | boom% off | edge (pp) |
|---|---|---|---|---|
| Ace | 186 | 46.8% | 43.7% | +3.1 |
| SP2/3 | 361 | 26.6% | 30.0% | **−3.4** |
| Backend | 329 | 18.5% | 22.7% | **−4.1** |
| Streamer | 1,632 | 13.5% | 10.8% | +2.7 |

The signal **flips sign** at the non-streamer tiers and is most anti-predictive at Backend (−4.1 pp).

## 1. H1 — Regression to mean (within-season K% variance by tier)

If established pitchers have stable true K% baselines and lower within-season noise, a 3-start spike is more likely to be an outlier outcome window than a real skill change.

| Tier | n pitcher-years | mean season K% | median within-season per-start K% std | K% coef of variation (median) |
|---|---|---|---|---|
| Ace | 70 | 31.8% | 10.48 pp | 0.319 |
| SP2_SP3 | 140 | 26.9% | 9.72 pp | 0.367 |
| Backend | 140 | 25.1% | 9.60 pp | 0.390 |
| Streamer | 1,012 | 20.2% | 9.01 pp | 0.453 |

**H1 evidence (variance form): NOT SUPPORTED — and slightly inverted.** Absolute per-start K% std is roughly flat across tiers (9.0-10.5 pp). The *coefficient of variation* (std / mean) is highest at Streamer (0.453) and lowest at Ace (0.319). So Streamers actually have the noisiest K% relative to their baseline, not the cleanest — which is the opposite of what H1 predicts.

### H1b — Direct forward-K% reversion after spike (the cleanest H1 test)

For each `flag_skill_spike == 1` row, compute the spike-window K%, the pre-spike season K%, and the K% over the NEXT 3 starts. If next-3 K% reverts back toward the pre-spike baseline, H1 is confirmed.

| Tier | n | pre-spike K% | spike-3 K% | next-3 K% | next-3 minus pre (pp) |
|---|---|---|---|---|---|
| Ace | 161 | 28.5% | 37.7% | 31.1% | +2.6 |
| SP2_SP3 | 323 | 24.3% | 33.6% | 27.4% | +3.2 |
| Backend | 291 | 22.7% | 31.7% | 25.7% | +3.0 |
| Streamer | 1,391 | 18.4% | 27.0% | 20.8% | +2.4 |

**Reversion fraction** (1 − carry/spike): how much of the spike has reverted in next-3?

| Tier | spike size (pp) | next-3 carry vs pre (pp) | reversion fraction |
|---|---|---|---|
| SP2/3 | +9.4 | +3.2 | 66% reverted |
| Backend | +9.0 | +3.0 | 66% reverted |
| Streamer | +8.6 | +2.4 | 72% reverted |

**H1b verdict: PARTIALLY SUPPORTED but tier-flat.** Reversion is universal (~66-72% of the K% spike disappears within 3 starts) but does NOT differ systematically by tier — Streamer actually reverts most (72%). So H1 in its "non-streamer spikes revert more than streamer spikes" form fails.

However there is a subtler interpretation that DOES help explain the finding: at every tier, ~30% of the spike persists (~+2.5 to +3.2 pp lift over pre-spike season K%). At Streamer that residual lifts boom rate (true talent rises from 18.4% K% baseline to 20.8% — meaningful at the margin). At Backend / SP2/3, +3 pp of persistent K% gain doesn't move the boom dial — those pitchers already operate in the 23-27% K% range, and a +3 pp residual against an opponent in the next start doesn't survive to FP ≥ 20 boom. **In other words: the K% reversion fraction is tier-flat, but the marginal value of the surviving +3 pp differs sharply by tier.**

## 2. H2 — Sample-size noise (longer windows)

If the issue is just that 3 starts is too short, a 5- or 7-start spike window should restore the positive sign at non-streamer tiers.

### 3-start window

| Tier | n(on) | n(off) | boom% on | boom% off | edge (pp) | mean FP edge |
|---|---|---|---|---|---|---|
| Ace | 186 | 1,404 | 46.8% | 43.7% | +3.1 | +0.74 |
| SP2_SP3 | 361 | 2,743 | 26.6% | 30.0% | -3.4 | -0.08 |
| Backend | 329 | 2,644 | 18.5% | 22.7% | -4.1 | -0.56 |
| Streamer | 1,632 | 15,684 | 13.5% | 10.8% | +2.7 | +0.39 |

### 5-start window

| Tier | n(on) | n(off) | boom% on | boom% off | edge (pp) | mean FP edge |
|---|---|---|---|---|---|---|
| Ace | 109 | 1,341 | 49.5% | 43.6% | +5.9 | +1.37 |
| SP2_SP3 | 195 | 2,629 | 29.2% | 29.8% | -0.6 | +0.60 |
| Backend | 192 | 2,501 | 22.9% | 22.1% | +0.8 | +0.43 |
| Streamer | 843 | 14,449 | 14.2% | 10.9% | +3.3 | +0.52 |

### 7-start window

| Tier | n(on) | n(off) | boom% on | boom% off | edge (pp) | mean FP edge |
|---|---|---|---|---|---|---|
| Ace | 63 | 1,247 | 36.5% | 43.9% | -7.4 | -0.75 |
| SP2_SP3 | 113 | 2,431 | 35.4% | 29.5% | +5.9 | +1.32 |
| Backend | 97 | 2,316 | 15.5% | 22.2% | -6.7 | -0.71 |
| Streamer | 385 | 12,883 | 14.0% | 11.1% | +2.9 | +0.70 |

**H2 evidence: STRONGLY SUPPORTED at the 5-start window.** The anti-predictive 3-start edge **collapses to ~zero** at the 5-start window:

- SP2/3: -3.4 pp (3g) → **-0.6 pp (5g)** → +5.9 pp (7g, small n=113)
- Backend: -4.1 pp (3g) → **+0.8 pp (5g)** → -6.7 pp (7g, small n=97)
- Streamer: +2.7 pp (3g) → +3.3 pp (5g) → +2.9 pp (7g) — stable across windows

5g neutralizes the anti-predictive sign at both non-streamer tiers cleanly. 7g results are noisier (n=63-113) and bounce. **This is the cleanest single test in the diagnosis: 3 starts is too short to detect real K%/BB% change against an established baseline.** Streamers' positive edge is stable across windows precisely because their pre-spike baseline is itself unstable — a 3-start spike at Streamer often coincides with a real underlying skill move (the baseline itself is moving), while at SP2/3 + Backend it's mostly outcome noise around a fixed mean.

## 3. H3 — Context confound (opponent strength at the spike)

If the spike-3 starts were against softer opponents than the pitcher faces on average, the K% gain was matchup-driven and will not repeat against the next opponent.

`lineup_xfp` is the opponent lineup's expected hitter FP — higher = tougher lineup. A negative `spike_gap` means the spike-3 opponents were softer than the season baseline.

| Tier | n(spike) | spike-3 opp xfp | season opp xfp | spike gap | nospike gap (control) |
|---|---|---|---|---|---|
| Ace | 186 | 0.519 | 0.528 | -0.0088 | -0.0001 |
| SP2_SP3 | 361 | 0.524 | 0.529 | -0.0055 | -0.0020 |
| Backend | 329 | 0.522 | 0.527 | -0.0055 | -0.0011 |
| Streamer | 1,632 | 0.521 | 0.527 | -0.0067 | -0.0013 |

- Backend: spike-vs-nospike opp gap differential = -0.0044
- SP2/3:   spike-vs-nospike opp gap differential = -0.0036

**H3 evidence: WEAKLY SUPPORTED but NOT tier-specific.** Spike-3 windows ARE against slightly softer opponents than control (every tier shows a negative spike gap of -0.005 to -0.009, vs nospike controls near zero). But the softness gap is similar at *all* tiers, so it cannot uniquely explain why the edge flips sign only at non-streamer tiers. Opponent confound is real but tier-flat — it shaves a small amount of the spike's apparent predictive power at every tier rather than producing the differential.

## 4. Synthesis

The data points cleanly at **H2 (sample-size noise) as the primary mechanism**, with a secondary H1-flavored marginal-value story that explains *why* Streamers still benefit from the same noisy signal.

**Primary: H2 — 3 starts is too short at non-streamer tiers.**
The 5-start window neutralizes the anti-predictive sign at SP2/3 (-3.4 → -0.6) and Backend (-4.1 → +0.8). This is the single cleanest test in the diagnosis. A 3-start K%/BB% spike against an established 25-32% K% baseline is dominated by per-start outcome variance (~9 pp per-start std), not real skill change. Streamers' positive edge is window-stable (+2.7/+3.3/+2.9 across 3g/5g/7g) — for them the 3-start spike *does* track something real because their baseline is itself unstable enough that a 3-start jump often coincides with a genuine talent shift (velocity uptick, repertoire change, role change).

**Secondary: tier-dependent marginal value of the residual K% gain (H1 in spirit).**
H1b shows that K% reverts at the same rate (~66-72%) at every tier, leaving a residual +2.4 to +3.2 pp persistent gain over pre-spike season K%. At Streamer (18→21% K%), that residual is enough to push boom rate up by 2.7 pp. At Backend (22.7→25.7% K%), the residual lands the pitcher right back at a typical Backend K% — no marginal lift, and the spike-flagged starts also slightly underperform on FP for reasons unrelated to K% (mean FP edge at Backend 3g = -0.56, suggesting the spike *outcomes* did not translate to FP even when K% rose). At SP2/3, similar.

**Tertiary: H3 (opp confound) is real but tier-flat.**
Spike-3 windows are against ~0.005-0.009 softer opponents at every tier. This shaves a uniform sliver off the spike's predictive power but does not produce the cross-tier differential.

**Bottom-line mechanism:** *The 3-start spike at non-streamer tiers is mostly outcome variance against a stable baseline; the K% gain reverts at the same rate as Streamers, but the residual K% lift doesn't move boom rate when the baseline is already in the 23-27% K% range. At Streamer, the residual lift is meaningful because the baseline is itself fluid.*

## 5. Actionable recommendation

- **Move to a 5-start window for `flag_skill_spike` at non-streamer tiers** in the production engine. At a 5g window, the anti-predictive sign disappears at SP2/3 + Backend while the Streamer signal stays intact. This is the cleanest single fix.
- **Treat the existing 3g `flag_skill_spike == 1` at SP2/3 or Backend tier as a soft sell-high / regression-warning flag** when surfacing in `/triangulate` and `/sp-week-plan` — until the 5g version is validated and shipped. The mean FP edge at Backend 3g is -0.56, which is a non-trivial negative for daily decisions.
- **For Streamer tier, retain the existing 3g flag** — it remains the dominant tier-specific component (+2.7 pp boom edge, validated across 3g/5g/7g windows).
- **Do NOT pursue an opp-correction feature as the primary fix.** H3 is real but tier-flat; the differential lives in window length, not opponent context.

### Candidate features for future `/validate-feature` runs

- **`skill_spike_5g`** (primary): same K%-delta ≥ +3 pp AND BB%-delta ≤ -1 pp definition, but using the last 5 starts strictly prior. Pre-register against rp3 with full Rule 9 baseline. Expected result: positive lift overall, especially at SP2/3 + Backend.
- `skill_spike_tier_aware`: a tier-gated composite — 3g at Streamer, 5g at SP2/3 + Backend, 3g at Ace (where 3g already works). This is what the engine should ultimately implement.
- `skill_spike_residual_k_pct_gain`: the persistent residual K% gain (next-3 K% minus pre-spike season K%) as a continuous feature rather than a binary flag, which captures the +2.5 to +3.2 pp signal directly.

## 6. Caveats

- All windows still require `start_idx >= window` (strictly prior). 5g and 7g samples are smaller, especially at the Ace tier.
- `lineup_xfp` is the *modeled* opponent strength used in the per-start panel; tertile cuts in the production engine use a month-by-month slate definition (see `build_per_start_boom_stack`).
- Forward K% reversion uses the next 3 starts; if a pitcher had only 1-2 remaining starts in the season, that spike row is dropped from H1b.

## 7. Data dump

Full numeric tables in `skill_spike_diagnosis_data.json` alongside this file.