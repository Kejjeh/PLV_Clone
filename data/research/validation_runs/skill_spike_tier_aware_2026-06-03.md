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
