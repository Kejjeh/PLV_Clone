# Validation runs index

Pre-registration files for `/validate-feature` skill runs. Each file
locks the test design BEFORE the validation runs, per Rule 1 of the
multi-testing protocol. If anything in a file's frontmatter changes
after results are seen, the run is invalidated.

When adding a new pre-registration:
1. Save as `<signal_name>_<YYYY-MM-DD>.md` in this directory.
2. Add a one-line entry to the table below with the verdict once
   the validation finishes.
3. Keep entries sorted reverse-chronological so the newest run is
   at the top.

## Pre-registration template

```markdown
---
signal: <name>
formula: <exact computation>
outcome: <exact column / frame>
expected_sign: <+ or ->
theory: <one sentence>
production_target: <rh3 | rp3 | rprs2 | research-only>
framing: <full-year | in-season → ros | both>
holdout_years: <list>
training_years: <list>
validation_script: scripts/xfp/validate_<signal_name>.py
date: <YYYY-MM-DD>
verdict: <PASS | MARGINAL | REJECTED | RESEARCH-ONLY>
purpose: <why this is being run now>
---
```

## Rule 5 honesty note template (use when source data is short)

```markdown
### Rule 5 sample-size honesty note (pre-acknowledged)

Source data <signal> began <year>. To compute <signal>, both year T-K
and T-K+1 must exist. This gives:
- <year>: <can / cannot> compute — explain
- ...
We have AT MOST <N> valid training years. Rule 2(b) requires ≥ 5 of 7.
This test <can / cannot> clear that gate with current data.
The expected outcome is <PASS / REJECTION at Step 2.5>. Re-run viable
starting <year Y>.
```

## Index

| Date | Signal | Target | Verdict | Notes |
|---|---|---|---|---|
| 2026-05-23 | avg_ext_prior | rp3 | MARGINAL | Lift +0.0005 vs full RP3_FEATS; sign 5/7, holdout +0.0033. Below +0.005 gate. Extension info absorbed by avg_velo_to + in-season rates. |
| 2026-05-23 | pitch_entropy_prior | rp3 | REJECTED | Lift -0.0001 vs full RP3_FEATS; holdout -0.0061 (wrong sign). Mix-diversity info downstream of stuff features already in baseline. |
| 2026-05-23 | vaa_ff_prior | rp3 | REJECTED | Lift +0.0011 vs full RP3_FEATS; sign 4/7 (fails 5/7 bar). Holdout +0.0030 but pooled & sign fail. Whiffs from flat FB are already captured by swstr_pct_to_sh / c_plus_swstr_to_sh. |
| 2026-05-23 | started_pct_to | rh3 | REJECTED | Δr -0.0003 vs full RH3_FEATS; redundant with pa_to + cumulative rates |
| 2026-05-23 | pa_per_started_game_to | rh3 | MARGINAL | Δr +0.0033 (best of 3-cell sweep); stable across split_days but below +0.005 gate |
| 2026-05-23 | lineup_spot_to | rh3 | MARGINAL | Δr +0.0009; signal strongest at split_day 30 (+0.0028), decays to noise by mid-season |
| 2026-05-16 | attack_angle_consistency_delta | rh3 (component) | REJECTED — Step 2.5 sample-size | Defer to 2028+; caught BEFORE script writing (Step 2.5 gap-fix works) |
| 2026-05-16 | squared_up_rate_delta_prior_year | rh3 (component) | REJECTED — sample-size | Defer to 2028 |
| 2026-05-16 | bat_speed_delta_prior_year | rh3 | REJECTED — sample-size | Defer to 2028 |
| 2026-05-16 | xwoba_gap_to (re-audit) | rh3 | MARGINAL → research-stage recommended | Marginal lift now -0.0003 vs full baseline; career_stage carries the v2 joint lift |
