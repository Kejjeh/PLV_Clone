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
| 2026-05-24 | primary_catcher_framing_runs_prior | rp3 | REJECTED | First catcher-influence feature in rp3. Prior-yr framing_runs_per_100 of pitcher's prior-yr modal catcher. Δr −0.0001 vs full RP3_FEATS (23→24); sign 4/7 FAIL, holdout 2024-25 avg +0.0001 (trivial). 86.4% non-null (4721/5462). Eye-test on framing data layer PASSED (Bailey/Raleigh/Wells top; Realmuto/Smith/Perez bottom — matches industry). Per-pitcher catcher dimension as encoded is dead for rp3 — drift_swstr + c_plus_swstr_to_sh already absorb the K-rate consequence of better receiving. Built `catcher_framing_2017_2025.csv` + `sp_primary_catcher_2018_2025.csv` as reusable cache. RP3_FEATS NOT modified. |
| 2026-05-24 | rp3_all_marginals_bundle | rp3 | MARGINAL | 4-feat bundle (avg_ext_prior + c_plus_swstr_last21 + avg_velo_last21 + park_pf_HR_ros) jointly added to full RP3_FEATS (23→27). Δr +0.0032 vs sum-of-marginals +0.0034 (essentially no independence bonus). Sign 4/7 FAIL (positives 2018/2021/2023/2024; negatives 2019/2022/2025). Holdout 2024-25 avg +0.0022. Joint Ridge coefs: ext +0.171, csw +0.264, velo +0.196, park -0.174 — all directionally sensible. No PASS → no drop-one. Confirms rp3 saturated against these axes; 2025 reversal echoes park_pf_HR_ros standalone behavior. RP3_FEATS NOT modified. |
| 2026-05-24 | park_pf_HR_ros | rp3 | MARGINAL | Lift +0.0017 vs full RP3_FEATS (24 feats); sign 6/7 PASS, holdout 2024-25 avg -0.0013 FAIL (2025 alone -0.0059), coef -0.1845 OK. v1 SP-home-park-only proxy. Directionally healthy (6/7 years, correct sign) but pooled lift below +0.005 gate and 2025 reversal kills holdout. Stuff/command rates already absorb most park signal. Full RoS rotation-weighted version might clear gate; not worth investment given marginal headroom. |
| 2026-05-24 | velo_x_swstr_to_sh | rp3 | REJECTED | Interaction sweep cell 1/4. Δr −0.0001 vs full RP3_FEATS; sign 4/7, holdout +0.0007. "Stuff index" product absorbed by individual avg_velo_to + swstr_pct_to_sh entries. |
| 2026-05-24 | velo_x_delta_velo | rp3 | REJECTED | Interaction sweep cell 2/4. Δr +0.0000 vs full RP3_FEATS; sign 3/7 (chance), holdout +0.0001. delta_velo magnitude too small for product to add variance. |
| 2026-05-24 | gs_x_prior_ip_resid | rp3 | REJECTED | Interaction sweep cell 3/4. Δr −0.0013 vs full RP3_FEATS; sign 2/7, holdout −0.0023 (2025 −0.0043). Worst of sweep — early-season GS noise amplified by prior-IP residual. prior_gs_eff already encodes durability. |
| 2026-05-24 | xwoba_x_bb_to_sh | rp3 | REJECTED | Interaction sweep cell 4/4. Δr −0.0001 vs full RP3_FEATS; sign 3/7, holdout −0.0001. "Trouble pitcher" badness² flat noise — joint contribution already captured linearly. |
| 2026-05-24 | bat_speed_level_prior | rh3 | REJECTED — Step 2.5 sample-size | Bat-tracking began 2024; only 1 train-eligible year (2025 outcomes from 2024 prior). Same Rule 5 gate that killed `bat_speed_delta` (2026-05-16). Raw `bat_speed` IS in `statcast_{2024,2025}.parquet` but not rolled into `hitters_multiyr` cache. Re-runnable 2028+. |
| 2026-05-24 | stuff_plus_prior | rp3 | REJECTED — Step 2.5 data unavailable | No FG Stuff+/Pitching+ cache in repo; user constraint forbids re-scrape. Closest in-repo proxy `avg_pfxz_to` already REJECTED (-0.0007), so bar for external Stuff+ is high. |
| 2026-05-24 | park_pf_wOBA_ros | rh3 | MARGINAL | Δr +0.0014 vs full RH3_FEATS; sign 5/7 PASS, holdout 1/2, coef WRONG SIGN (-0.0062). v1 home-park-only proxy. Lift exists but coef inverted suggests RH3_FEATS already absorb park signal via rate stats; the small Δr is regularization noise. Not worth promoting; full RoS-schedule pipeline unlikely to clear +0.005. |
| 2026-05-24 | prior_pa_eff_x_pa_to | rh3 | MARGINAL | Δr +0.0008 (best of rh3 interaction 4-cell sweep); sign 5/7, holdout 1/2, WRONG-sign coef (expected +, got −0.0117), and every per-split_day Δr negative. Pooled positive looks like averaging artifact. Do not promote. |
| 2026-05-24 | lineup_spot_x_split_day | rh3 | REJECTED | Δr −0.0001; sign 5/7 but 2024 disaster (−0.0029) drags pooled negative. split_day 30 lift (+0.0027) reaffirms 2026-05-23 lineup_spot finding but linear product cannot encode the mid-season decay — needs piecewise framing. |
| 2026-05-24 | bb_pct_x_xwoba_per_pa_to_sh | rh3 | REJECTED | Δr +0.0000; sign 3/7; flat at every split_day. xwOBA already weights BB so discipline × power interaction is collinear with marginal. |
| 2026-05-24 | pa_to_x_hr_per_pa_to_sh | rh3 | REJECTED | Δr −0.0002; sign 4/7; negative at every split_day. Volume × HR-rate redundant with the two marginals already in RH3_FEATS. |
| 2026-05-24 | rh3_opportunity_bundle | rh3 | MARGINAL | Joint 3-feat bundle (pa_per_started_game_to + lineup_spot_to*split_day + park_pf_wOBA_ros) Δr +0.0036 vs full RH3_FEATS; sign 5/7 PASS, holdout 1/2. Joint fit UNDERSHOT sum-of-marginals (+0.0046) by −0.0010 → collinearity hurts, doesn't help. Park coef wrong-sign (-0.003) in joint fit confirms venue feat is fighting career_stage/prior. Volume (pa_per_started_game_to, +0.015) is the load-bearing positive component. |
| 2026-05-24 | bip_to | rh3 | REJECTED | Δr +0.0000 vs full RH3_FEATS; sign 4/7, holdout 2/2 but pooled flat. Redundant with pa_to × in_play_pct_to_sh joint. Ceiling-audit raw-count candidate. |
| 2026-05-24 | contact_to | rh3 | MARGINAL | Δr +0.0001 vs full RH3_FEATS; sign 5/7, holdout 2/2, coef sign OK. Best of the 3-cell raw-count sweep but two orders of magnitude below +0.005 gate. |
| 2026-05-24 | hr_to | rh3 | REJECTED | Δr -0.0001 vs full RH3_FEATS; sign 3/7, holdout 0/2 (wrong direction on the years that matter). Redundant with hr_per_pa_to_sh × pa_to. |
| 2026-05-24 | avg_velo_last21 | rp3 | MARGINAL | Lift +0.0001 vs full RP3_FEATS (23→24); sign 4/7, holdout +0.0011. L21 velo level redundant with (avg_velo_to, delta_velo) pair. Ceiling-audit follow-up. |
| 2026-05-24 | c_plus_swstr_last21 | rp3 | MARGINAL | Lift +0.0011 vs full RP3_FEATS; sign 5/7 PASS, holdout −0.0008 FAIL. Strongest pooled lift of 3-cell sweep but train-only signal — 2025 negative. Ceiling-audit follow-up. |
| 2026-05-24 | avg_pfxz_to | rp3 | REJECTED | Lift −0.0007 vs full RP3_FEATS; sign 1/7 (6 of 7 years negative). Signed arsenal-average IVB acts as distraction — outcome rates already encode pitch shape. Ceiling-audit follow-up. |
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
