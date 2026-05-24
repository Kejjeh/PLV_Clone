---
signal: rp3_all_marginals_bundle
formula: avg_ext_prior + c_plus_swstr_last21 + avg_velo_last21 + park_pf_HR_ros (4-feat bundle added simultaneously)
outcome: ros_fp_per_start
expected_sign: + (bundle; component signs vary)
theory: All 4 individually MARGINAL signals tested as a bundle. Components sit in different axes (release / CSW / velo / venue) so joint fit may extract independent variance that the sum-of-marginals doesn't capture.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_rp3_all_marginals_bundle.py
date: 2026-05-24
verdict: MARGINAL
purpose: Per user-requested exhaustive ceiling-audit follow-up. Last bundle test on rp3 before declaring the model genuinely saturated.
---

### Component prior results

| Component            | Alone Δr  | Sign | Date       |
|----------------------|-----------|------|------------|
| avg_ext_prior        | +0.0005   | -    | 2026-05-23 |
| c_plus_swstr_last21  | +0.0011   | -    | 2026-05-24 |
| avg_velo_last21      | +0.0001   | -    | 2026-05-24 |
| park_pf_HR_ros       | +0.0017   | 6/7  | 2026-05-24 |

Sum-of-marginals = +0.0034. Bundle test asks if joint Ridge fit extracts more than the linear sum because the four axes (release / recent-CSW / recent-velo / venue) are partially independent.

### Verdict gates

- PASS: bundle Δr ≥ +0.005 AND sign ≥ 5/7 years positive
- MARGINAL: 0 < Δr < +0.005, OR sign 4/7
- REJECTED: Δr ≤ 0 OR sign ≤ 3/7

If PASS, follow with drop-one analysis to identify load-bearing components.
