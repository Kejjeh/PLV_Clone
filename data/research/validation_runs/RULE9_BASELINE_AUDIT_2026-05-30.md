---
audit: rule_9_baseline_gap
fix: scripts/xfp/_validate_rh3_v3_helper.py — merged ros_opp_sp_xwoba_weighted
date: 2026-05-30
trigger: lineup_role_tier validation surfaced that load_and_prep_rh3_inputs() was missing one of the 21 RH3_FEATS
---

# Rule 9 baseline audit — post-fix re-run of helper-routed validations

## Context

`scripts/xfp/_validate_rh3_v3_helper.py::load_and_prep_rh3_inputs()` was missing
the merge for `ros_opp_sp_xwoba_weighted` (the RoS opponent-SP xwOBA feature).
This meant candidate-feature validations routed through the helper without
their own workaround were running against a **20-feature baseline** instead of
the production **21-feature baseline**.

Fixed 2026-05-30 in commit `d11702c`. The fix is idempotent — historical scripts
with their own workarounds still run cleanly.

This audit re-runs all 9 helper-routed candidate validations to confirm
verdicts hold. Both the agent who flagged the gap and this audit agent
identified zero validations with their own workaround — all 9 needed re-runs.

## Results

| Candidate | Original Δr | New Δr | Original verdict | New verdict | Status |
|---|---|---|---|---|---|
| `bip_to` | +0.0000 | +0.0000 | REJECTED | REJECTED | UNCHANGED |
| `contact_to` | +0.0001 | +0.0001 | MARGINAL | MARGINAL | UNCHANGED |
| `hr_to` | −0.0001 | −0.0001 | REJECTED | REJECTED | UNCHANGED |
| `lineup_spot_to` | +0.0009 | +0.0004 | MARGINAL | MARGINAL | SHRUNK |
| `pa_per_started_game_to` | +0.0033 | +0.0019 | MARGINAL | MARGINAL | SHRUNK |
| `park_pf_wOBA_ros` | (~+0.002 original window) | +0.0016 | MARGINAL | MARGINAL | UNCHANGED |
| `prior_pa_eff_x_pa_to` | +0.0008 | +0.0009 | MARGINAL | MARGINAL | UNCHANGED |
| `started_pct_to` | −0.0003 | −0.0002 | REJECTED | REJECTED | UNCHANGED |
| `rh3_opportunity_bundle` | +0.0036 | +0.0020 | MARGINAL | MARGINAL | SHRUNK |

Baseline cross_year_r (proper 21-feature): **0.6287** (unchanged across all runs — confirms baseline is now stable).

## Verdict summary

- **0 verdict flips**. No feature was incorrectly promoted to RH3_FEATS as a result of the gap.
- **3 meaningful shrinks** (~45-55% Δr reduction):
  - `pa_per_started_game_to` +0.0033 → +0.0019
  - `lineup_spot_to` +0.0009 → +0.0004
  - `rh3_opportunity_bundle` +0.0036 → +0.0020
- The shrinks pattern is consistent: candidates correlated with RoS opponent context (PA volume, lineup spot, the opportunity bundle that includes ros features) had their apparent lift partially absorbed by the proper baseline. This is the expected directional outcome.

## Production-integrity implications

**None.** All 9 candidates were either REJECTED or MARGINAL — none had been promoted to RH3_FEATS. The Rule 9 baseline gap caused systematic **over-claiming** of lift for ROS-correlated features, but the +0.005 production gate filtered them all out anyway.

The next time a borderline candidate (~+0.005-0.008) goes through validation, the proper baseline ensures we don't over-promote.

## Side observation

The systematic ~45% shrinkage in ROS-flavored candidates suggests that
`ros_opp_sp_xwoba_weighted` is doing substantial work in the production
baseline. Worth confirming via a `validate_drop_one` run on RH3_FEATS to
see whether removing `ros_opp_sp_xwoba_weighted` would meaningfully hurt
production cross_year_r. Out of scope for this audit; flagged for future.

## Files

- `scripts/xfp/_validate_rh3_v3_helper.py` (fix in `d11702c`)
- Original reports: `data/research/validation_runs/<candidate>_2026-05-{23,24}.md`
- This audit: `data/research/validation_runs/RULE9_BASELINE_AUDIT_2026-05-30.md`
