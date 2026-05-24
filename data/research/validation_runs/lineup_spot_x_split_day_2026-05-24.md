---
signal: lineup_spot_x_split_day
formula: lineup_spot_to * split_day (raw PA-weighted lineup spot times cutoff day-index)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: -
theory: lineup_spot_to in isolation was MARGINAL at +0.0009 (2026-05-23) with the lift concentrated at split_day=30 (+0.0028) and decaying by mid-season. The interaction lets Ridge use the early-season signal without diluting late-season fits; the coefficient × split_day product allows the effect to attenuate naturally.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_lineup_spot_x_split_day.py
date: 2026-05-24
verdict: REJECTED
purpose: Interaction-term sweep round (rh3). Rescue the lineup_spot_to MARGINAL by explicitly encoding its split_day-dependent attenuation. Lineup_spot_to itself is NOT in RH3_FEATS (rejected MARGINAL 2026-05-23) so this interaction is the path forward, not redundant.
---

### Bonferroni / sweep context

4-cell rh3 interaction sweep; see `pa_to_x_hr_per_pa_to_sh_2026-05-24.md`.

Note: lineup_spot_to alone is NOT in baseline. Adding only the interaction (without the marginal) is intentional — the marginal failed pre-screening. If the interaction passes, a follow-up could test joint promotion (marginal + interaction together).

### Rule 9 baseline

Full RH3_FEATS as of 2026-05-24. `split_day` IS in RH3_FEATS; `lineup_spot_to` is NOT.

### Step 2.5 data-coverage pre-check

Column verified via `df.columns.tolist()` lookup: `lineup_spot_to` present. `split_day` is the cutoff-day index used everywhere downstream.

### Expected-sign note

Lower lineup spot number = better hitter (1 = leadoff). split_day grows through the season. Negative coefficient = "early-season heavy-lineup-spot lift attenuates with time" — direction matches the 2026-05-23 finding.

### Convergence-curve framing (Rule 8)

Per split_day at 30/60/90/120. By construction the candidate column is constant within a split_day, so per-split eval mostly stress-tests that we're not over-fitting one cutoff.

---

## Result — REJECTED (2026-05-24)

### Headline (Rule 9 baseline = full RH3_FEATS)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6166 |
| **Δr** | **−0.0001** |
| Pooled n | 8,275 |

Below +0.005 gate; mildly negative pooled.

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | −0.0010 | − |
| 2019 | +0.0006 | + |
| 2021 | +0.0006 | + |
| 2022 | +0.0003 | + |
| 2023 | +0.0003 | + |
| 2024 | −0.0029 | − |
| 2025 | +0.0006 | + |

Positives **5/7** (clears the per-year bar) BUT 2024 disaster (−0.0029) tanks pooled. Holdout 1/2.

### Convergence (Rule 8)

| split_day | Δr |
|---|---|
| 30 | **+0.0027** |
| 60 | +0.0003 |
| 90 | −0.0006 |
| 120 | −0.0004 |

This is the most interesting curve in the sweep — the early-season lift (+0.0027 at split_day 30) cleanly mirrors what `lineup_spot_to` alone showed on 2026-05-23 (also +0.0028 at split_day 30). The interaction successfully isolates the early-season signal that decays to noise by split_day 90. However, the integrated full-season eval still flips negative because Ridge over-fits the early-season relationship at later split_days.

### Sign sanity

Coef −0.0037 (expected −). Direction OK.

### Why this failed (despite intriguing convergence curve)

The 2024 catastrophic year drag (−0.0029) and pooled-negative pooled mean it cannot earn promotion. The mid-season decay is real and unhandled by a single linear product; encoding lineup_spot's early-season value would require a split_day-bucketed feature (e.g., lineup_spot indicator * I[split_day ≤ 60]) — not a linear product.

### Decision

REJECTED at this framing. Research-worthy as a piecewise / bucketed candidate: try `lineup_spot_to * I[split_day <= 60]` in a future round. The 2026-05-23 finding that the marginal lift concentrates at split_day 30 is reaffirmed.

