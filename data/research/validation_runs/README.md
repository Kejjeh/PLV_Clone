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
| 2026-05-16 | attack_angle_consistency_delta | rh3 (component) | REJECTED — Step 2.5 sample-size | Defer to 2028+; caught BEFORE script writing (Step 2.5 gap-fix works) |
| 2026-05-16 | squared_up_rate_delta_prior_year | rh3 (component) | REJECTED — sample-size | Defer to 2028 |
| 2026-05-16 | bat_speed_delta_prior_year | rh3 | REJECTED — sample-size | Defer to 2028 |
| 2026-05-16 | xwoba_gap_to (re-audit) | rh3 | MARGINAL → research-stage recommended | Marginal lift now -0.0003 vs full baseline; career_stage carries the v2 joint lift |
