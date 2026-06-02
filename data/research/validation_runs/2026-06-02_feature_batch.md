---
batch_date: 2026-06-02
target: rp3
candidates: [days_rest, lineup_handedness_match]
verdicts: [REJECTED, REJECTED]
bonferroni_alpha_per_test: 0.025
---

# Feature batch — 2026-06-02 summary

Two candidate rp3 features tested under the validated-feature 9-rule
multi-testing protocol. Both REJECTED on the same day.

## Side-by-side verdicts

| Metric | days_rest | lineup_handedness_match |
|---|---|---|
| Pre-registered expected sign | weakly negative for extra rest | positive (platoon-favorable matchup → ↑ FP) |
| Baseline r (RP3_FEATS, n=19,111) | 0.5548 | 0.5548 |
| Full r (+ candidate) | 0.5546 | 0.5542 |
| **Cross-year r lift** | **-0.0002** | **-0.0006** |
| Lift gate (≥ +0.005)? | FAIL | FAIL |
| Sign-consistent years (pre-bar: ≥5/7) | 3 / 7 | 4 / 7 |
| Holdout 2024-25 r lift | -0.0013 | +0.0010 |
| Holdout 2024-25 MAE gain (FP/start) | -0.0017 (worse) | +0.0028 (better) |
| **Partial r vs full baseline** | **-0.0007** | **-0.0131** |
| Convergence sd=30 lift | +0.0026 | -0.0018 |
| Convergence sd=44 lift | +0.0006 | -0.0006 |
| Convergence sd=58 lift | +0.0008 | -0.0019 |
| Leakage smell (later sd >> earlier sd)? | NO (gains DECREASE with sd) | NO (all 3 negative) |
| **Final verdict** | **REJECTED** | **REJECTED** |

## Bonferroni framing

Two independent candidates tested in one batch. Bonferroni-corrected
alpha-per-test = 0.025 (from 0.05 / 2). Neither candidate's effect
size approaches the +0.005 production lift gate, so the multiple-test
correction is academic — both fail unambiguously on raw effect size.

## Key takeaways

1. **days_rest is fully absorbed by IL features + cumulative state.**
   Partial r is essentially zero (-0.0007). The IL feature triad
   already encodes the most predictive slice of rest-pattern variation
   (post-IL ramp). Normal 4-vs-6 day rest variation does not move the
   RoS needle.

2. **lineup_handedness_match is at best redundant with
   `ros_opp_xwoba_weighted`, at worst adds noise.** Partial r is
   slightly negative (-0.0131). The team-strength channel already
   captures the handedness mix indirectly via per-team xwOBA. The
   season-to-date handedness fraction is not orthogonal to that
   channel.

3. **Neither feature shows a leakage smell.** Both convergence panels
   are well-behaved. The negative results are genuine "the signal is
   not there" verdicts rather than "leakage was inflating an apparent
   signal" verdicts. The 9-rule protocol successfully distinguished
   true-null from leakage-driven false positives — exactly what it was
   designed to do.

4. **Pattern consistent with the broader RP3 saturation story.** Like
   the recent `velo_trend` rejection (2026-06-02) and the 2026-05-24
   `avg_velo_last21` MARGINAL verdict, both of today's candidates fail
   not because they are uninformative in isolation but because the rp3
   model's 24-feature baseline (especially the velocity + shrunken
   contact + RoS schedule features) already extracts the predictive
   content these candidates encode. Future productive rp3 gains will
   need to come from genuinely orthogonal mechanisms.

## Leakage smells found

**None.** Both candidates have well-behaved convergence panels:

- `days_rest`: gains DECREASE with later split_day (+0.0026 → +0.0006
  → +0.0008). Opposite of canonical leakage signature.
- `lineup_handedness_match`: all three split_day gains are negative
  with no monotonic trend.

Both pre-registered framing-discipline checks held: pre-cutoff data
only, leave-one-year-out across training years, holdout never touched
during training-year tuning.

## Recommendation

- DO NOT add either feature to `RP3_FEATS`.
- Log both rejections in `reference_validated_signals_registry.md`
  under the rejected-candidates section.
- The rp3 v3 baseline remains the production model.

## Files

| Artifact | Path |
|---|---|
| days_rest pre-registration | `data/research/validation_runs/days_rest_2026-06-02.md` |
| days_rest report | `data/research/validation_runs/days_rest_validation.md` |
| days_rest raw JSON | `data/research/validation_runs/days_rest_results.json` |
| days_rest script | `scripts/xfp/validate_days_rest.py` |
| lineup_handedness pre-registration | `data/research/validation_runs/lineup_handedness_2026-06-02.md` |
| lineup_handedness report | `data/research/validation_runs/lineup_handedness_validation.md` |
| lineup_handedness raw JSON | `data/research/validation_runs/lineup_handedness_results.json` |
| lineup_handedness script | `scripts/xfp/validate_lineup_handedness.py` |
| This summary | `data/research/validation_runs/2026-06-02_feature_batch.md` |
