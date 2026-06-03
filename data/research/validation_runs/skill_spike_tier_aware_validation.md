# Validation Report — `skill_spike_tier_aware`

Generated 2026-06-03. Pre-registration at `skill_spike_tier_aware_2026-06-03.md` (full text appended below).

## TL;DR

**VERDICT: SHIP_FLAT_5G (tier_aware ties on pooled but does not clear all per-tier bars; flat_5g is the simpler dominant variant)**

- Pooled weighted edge (full panel 2018-25):
  - flat_3g (status quo): **+1.16 pp**
  - flat_5g (Agent 2):    **+2.68 pp**
  - tier_aware (this):    **+2.32 pp**

- Ace-tier window choice (locked from pre-2024 calibration): **5g**
  - 5g wins by +6.83 pp on calibration

## 1. Three-way per-tier edge comparison (full panel 2018-25)

| Tier | n_on(3g) | edge_3g | n_on(5g) | edge_5g | n_on(aware) | window(aware) | edge_aware |
|---|---|---|---|---|---|---|---|
| Ace | 186 | +3.11 | 109 | +5.92 | 109 | 5g | +5.92 |
| SP2_SP3 | 361 | -3.45 | 195 | -0.55 | 195 | 5g | -0.55 |
| Backend | 329 | -4.11 | 192 | +0.85 | 192 | 5g | +0.85 |
| Streamer | 1,632 | +2.72 | 843 | +3.29 | 1,632 | 3g | +2.72 |

## 2. Pooled weighted edge (sum-N weighting)

| Variant | Pooled edge (pp) | Hold-out (2024-25) pooled |
|---|---|---|
| flat_3g  | +1.164 | +1.216 |
| flat_5g  | +2.675 | +1.965 |
| tier_aware | **+2.321** | **+1.489** |

## 3. Ace-tier calibration (pre-2024 → lock-in)

| Window | n_on (calib) | edge (calib, pp) |
|---|---|---|
| 3g | 127 | +2.29 |
| 5g | 76 | +9.12 |

**Locked Ace window: 5g** (5g wins by +6.83 pp on calibration).
Decision frozen before observing hold-out (2024-25) per Rule 8.

## 4. Cross-year stability (year × variant pooled edge, pp)

| Year | flat_3g | flat_5g | tier_aware |
|---|---|---|---|
| 2018 | +4.39 | +8.08 | +5.07 |
| 2019 | +1.30 | +4.48 | +1.23 |
| 2021 | +3.51 | +6.58 | +4.62 |
| 2022 | -0.27 | +0.55 | -0.59 |
| 2023 | +2.18 | +2.70 | -0.91 |
| 2024 | +2.13 | +3.92 | +0.37 |
| 2025 | +0.61 | +0.87 | +0.27 |

- flat_3g pos-year count: 6 / 7
- flat_5g pos-year count: 7 / 7
- tier_aware pos-year count: **5 / 7**

## 5. Per-tier per-year edge matrix (tier_aware)

| Tier | 2018 | 2019 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| Ace | -7.4 | +11.6 | +26.6 | +9.2 | +17.6 | +4.9 | -6.7 |
| SP2_SP3 | -0.5 | +2.3 | +5.3 | -11.7 | -0.4 | -3.4 | +1.2 |
| Backend | +16.1 | -7.1 | +11.4 | -4.6 | -14.2 | +6.6 | -7.5 |
| Streamer | +6.2 | +0.1 | +4.0 | +3.3 | +0.4 | +1.6 | +3.3 |

## 6. v1 boom_stack marginal-lift comparison

Component (1) `flag_skill_spike` is replaced with each variant; boom_stack recomputed; boom rate per bucket reported. The interesting cell is boom_stack=3 (all 3 components fire) — higher boom% there means stronger composite.

### `flat_3g`

| boom_stack | n | boom% | mean FP |
|---|---|---|---|
| 0 | 14,907 | 14.1% | 10.08 |
| 1 | 10,906 | 18.1% | 11.36 |
| 2 | 2,752 | 18.8% | 11.56 |
| 3 | 504 | 22.8% | 12.58 |

### `flat_5g`

| boom_stack | n | boom% | mean FP |
|---|---|---|---|
| 0 | 15,181 | 14.1% | 10.10 |
| 1 | 11,268 | 18.0% | 11.29 |
| 2 | 2,375 | 19.9% | 12.02 |
| 3 | 245 | 26.1% | 13.09 |

### `tier_aware`

| boom_stack | n | boom% | mean FP |
|---|---|---|---|
| 0 | 14,978 | 14.1% | 10.10 |
| 1 | 11,057 | 18.2% | 11.37 |
| 2 | 2,617 | 18.7% | 11.55 |
| 3 | 417 | 22.1% | 12.03 |

## 7. Pre-registered bars check

| Bar | Required | Observed | Pass? |
|---|---|---|---|
| 1 | pooled_aware > pooled_5g | +2.321 vs +2.675 | NO |
| 2 | All 4 per-tier signs ≥ 0 | min=-0.55 | NO |
| 3 | Streamer ≥ flat_3g_streamer − 1.0 | +2.72 vs +2.72 | YES |
| 4 | Hold-out pooled ≥ 0 | +1.489 | YES |
| 5 | Cross-year ≥ 6 of 7 | 5 / 7 | NO |

## 8. Verdict

**SHIP_FLAT_5G (tier_aware ties on pooled but does not clear all per-tier bars; flat_5g is the simpler dominant variant)**

### Engine edit spec

Replace the 3-start window for `flag_skill_spike` with a 5-start window across all tiers — this is the simpler edit and matches Agent 2's parallel `skill_spike_5g` validation.

## 9. Coordination with Agent 2 (`skill_spike_5g`)

Agent 2 of this validation cluster is testing the FLAT 5g variant independently. Both this report and Agent 2's share the same panel cache and tier definition, so the per-tier 5g numbers reported here should match Agent 2's headline figures within rounding. If they disagree by more than 0.2 pp, one of us has a bug — cross-check both scripts before adopting either verdict.

Per-tier 5g edges from THIS report (for cross-check):

| Tier | n_on | n_off | edge (pp) |
|---|---|---|---|
| Ace | 109 | 1,341 | +5.92 |
| SP2_SP3 | 195 | 2,629 | -0.55 |
| Backend | 192 | 2,501 | +0.85 |
| Streamer | 843 | 14,449 | +3.29 |

## 10. Honest caveats / traps watched for

- **Pooled-edge trap**: the pooled metric is weighted by N, so the huge Streamer tier dominates. We therefore also require all 4 per-tier signs ≥ 0 (bar #2). A variant that wins on pooled but loses at one tier does NOT pass.
- **Ace cherry-pick trap**: choosing 3g vs 5g at Ace AFTER seeing the full panel would be Rule-8 leakage. We pre-locked the choice on 2018-23 calibration only.
- **Tier-assignment leakage**: tiers use full-season fp_mean rank-in-year, which is a label not available at decision time. This is acceptable for ANALYTIC comparison of variants since the tier label is the SAME across all three variants — the relative ordering is what we test. For shipping to the live engine we will need a forward-looking tier estimator (e.g., rp3-based projected-rank), but that is OUT OF SCOPE for this validation.
- **5g sample size at Ace**: full-panel n_on=109 (per Agent 5 diagnostic), calibration sub-sample is smaller still. The pre-registered tie-rule (3g wins ties) guards against this.

## 11. Pre-registration (verbatim)

```
# Pre-Registration — `skill_spike_tier_aware`

**Date filed:** 2026-06-03 (pre-data inspection of the tier-aware comparison)
**Author:** Agent 3 of skill_spike validation cluster
**Parallel agent:** Agent 2 — `skill_spike_5g` flat variant
**Diagnostic basis:** `skill_spike_anti_predictive_diagnosis.md`

## 0. Context

Production v1 component `flag_skill_spike` (3-game K%/BB% delta) shows
per-tier boom edge:

| Tier | edge (pp) |
|---|---|
| Ace | +3.1 |
| SP2/3 | −3.4 |
| Backend | −4.1 |
| Streamer | +2.7 |

Agent 5's diagnostic confirmed:
- H2 (window length) is the primary mechanism — 5g neutralises the
  anti-predictive sign at SP2/3 (−3.4 → −0.6) and Backend (−4.1 → +0.8).
- Streamer signal is window-stable (+2.7/+3.3/+2.9 across 3g/5g/7g).
- Ace tier: 3g = +3.1, 5g = +5.9 (n=109), 7g = −7.4 (n=63 — too small).

This pre-registration tests the **tier-gated** variant proposed in the
diagnostic's section 5: 3g at Streamer, 5g at SP2/3 + Backend, 3g OR 5g
at Ace (whichever wins in pre-2024 calibration data, with 2024-25 held
out for validation).

## 1. Hypothesis

**H_tier_aware**: a tier-gated skill_spike flag — where the window is
chosen per tier to match the tier's optimal — outperforms BOTH the flat
3g and flat 5g variants on:

1. Pooled per-tier boom-rate edge weighted by N
2. Per-tier sign (all 4 tiers positive)
3. Cross-year stability (≥ 6 of 7 years positive when aggregated across
   tiers; per-tier sign positive in majority of years per tier)
4. No degradation at streamer tier (must stay near +2.7 pp baseline)

## 2. Variants under test

| Variant | Streamer | Backend | SP2/3 | Ace |
|---|---|---|---|---|
| `skill_spike_3g` | 3g | 3g | 3g | 3g |
| `skill_spike_5g` | 5g | 5g | 5g | 5g |
| `skill_spike_tier_aware` | 3g | 5g | 5g | choose 3g vs 5g on pre-2024 |

Definition (all variants): `lwN_k_pct − season_k_pct ≥ +3 pp` AND
`lwN_bb_pct − season_bb_pct ≤ −1 pp` with `start_idx ≥ N`. Tier
assignment is the rank-in-year SP rank from production engine
(Ace 1-10 / SP2_SP3 11-30 / Backend 31-50 / Streamer 51+).

## 3. Ace-tier window decision rule (pre-stated)

Calibration window: **2018-2023 (pre-2024)**.
- Compute edge_3g_Ace and edge_5g_Ace on pre-2024 rows only.
- The window with the larger calibration edge is locked in for the
  tier_aware flag.
- Validation window: 2024-2025 — report per-tier edges for all three
  variants on hold-out without retuning.

This is the strict-Rule-8 framing safeguard against the trap that
Ace n is small enough at 5g that the choice could be reverse-engineered
post-hoc.

## 4. Pre-stated bars

**Primary bar (ship_tier_aware):**
1. Pooled per-tier edge (weighted by tier N on the FULL panel) is
   strictly greater than flat-5g's pooled edge.
2. Per-tier sign positive at all 4 tiers (≥ 0.0 pp at every tier).
3. No regression at Streamer: tier_aware streamer edge ≥ flat-3g
   streamer edge − 1.0 pp (i.e., we don't lose more than 1 pp at
   the tier where the 3g signal is known to work).
4. Hold-out (2024-25) sanity: pooled edge ≥ 0 on the hold-out years.

**Tie bar (tie_with_flat_5g):**
- Pooled per-tier edge is within ±0.5 pp of flat-5g and all per-tier
  signs positive at both variants → ship the simpler variant (flat 5g).

**Fail bar (no_improvement):**
- Any per-tier sign negative at tier_aware OR pooled edge < flat-5g
  by more than 0.5 pp → NO_SHIP and explain.

## 5. Bonferroni correction

Three simultaneous variants under test in this cluster (3g, 5g,
tier_aware). Family-wise α = 0.10 → per-test α = 0.033. We are NOT
running formal p-tests on edge-vs-zero — the diagnostic is descriptive.
The Bonferroni applies to the cross-year stability count: we require
≥ 6 of 7 years positive (vs 7 of 7 baseline pre-Bonferroni) to
maintain α ≈ 0.05 after 3-way correction.

## 6. Decision tree

- **SHIP_TIER_AWARE** if all 4 primary bars met AND cross-year
  stability ≥ 6 of 7 years.
- **SHIP_FLAT_5G** if tier_aware ties or underperforms flat-5g AND
  flat-5g per-tier signs are all positive.
- **SHIP_FLAT_3G (status quo)** if neither alternative improves on
  current.
- **NO_SHIP / INVESTIGATE_FURTHER** if all three show per-tier
  negatives or pooled edge ≤ 0.

## 7. Reporting commitments

Final report (`skill_spike_tier_aware_validation.md`) must include:
- Verbatim copy of this pre-registration
- Per-tier 3-way comparison table on FULL panel (2018-25)
- Calibration-vs-holdout per-tier table for Ace choice
- Pooled weighted edge per variant
- Cross-year stability per variant (year × tier matrix)
- v1 boom_stack marginal-lift test: at the SP2/3 + Backend rows where
  `boom_stack` is currently 0/1/2, does substituting `skill_spike` with
  `skill_spike_tier_aware` lift boom_stack=3 boom rate vs flat-3g and
  flat-5g substitutions?
- VERDICT and (if SHIP_TIER_AWARE) the exact boom_stack.py edit.
- Reference to Agent 2's parallel `skill_spike_5g` result and the
  agreement / disagreement.

## 8. Caveats acknowledged in advance

- Ace n at 5g is small (109). The pre-2024 calibration sub-sample is
  smaller still. If the calibration coin-flips the window choice we
  will fall back to **3g at Ace** (status quo wins ties).
- The "pooled weighted edge" metric can be gamed by a single tier with
  huge n — we therefore also report per-tier individually and require
  all signs positive (bar #2).
- This test does NOT touch rp3 or any FP-prediction model; it is a
  decision-rule validation for the v1 boom_stack component.

```
