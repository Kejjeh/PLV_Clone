---
signal: gmli_todate
formula: per (pitcher, year, split_day) — mean empirical entry-LI over the pitcher's RELIEF appearances (first PA faced per game, starters-that-game excluded) with game_date <= season_start + split_day, min 5 appearances (else population-mean imputed). Cell 2 subtracts the pitcher's team-bullpen pooled mean entry-LI at the same cutoff. Cell 3 = count of same-team RPs (>=5 app) with strictly higher gmli_todate. LI from the frozen empirical table (lib/leverage_index.py, built on 2018-2023 ex-2020 statcast, league-mean normalized, no player info)
outcome: fp_year_total (rprs2 harness target)
expected_sign: "+"
theory: 5*SV + 2*HLD require high-leverage usage; entry-LI is the purest as-of measure of the ROLE that generates those opportunities, and role is a leading indicator of promotion/demotion that realized sv/hld counts lag
production_target: rprs2
framing: in-season as-of (rprs2 grid, all split_days)
holdout_years: [2024, 2025]
training_years: [2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_gmli_todate.py
date: 2026-07-19
verdict: REJECTED
---

## RESULT (2026-07-19 run)

n=34,115 (pitcher, year, split_day) rows; LI lib golden-tested (4/4).
- **1B-1 gmli_todate:** lift +0.0004, 4/6 years, holdout −0.0001. FAIL.
- **1B-2 teamrel:** lift +0.0004, 5/6, holdout −0.0002. FAIL (holdout + gate).
- **1B-3 n_teammates_higher:** +0.0000, 1/6. FAIL.
- **Joint redundancy:** −0.0002 beyond best cell. Nothing there.
- **Interpretation:** same absorber pattern as Wave 1A — FEATS_RPRS2's realized-role
  outcomes (sv_per_g_to, hld_per_g_to, gf_pct_to, fp_with_role_to) already price the
  role; entry-LI's "leading indicator" channel is too thin to add beyond them at the
  RoS-total horizon. The role-change subset (n=6,761) showed no differential lift
  either (+0.0001/+0.0003) — even where roles turn over, realized counts keep pace.

## Cells (campaign ledger, registry 2026-07-19; family α/3)

- **1B-1** `gmli_todate` (raw)
- **1B-2** `gmli_todate_teamrel` (− team bullpen pooled mean at cutoff)
- **1B-3** `n_teammates_higher_gmli`
- Joint redundancy check afterward if any cell shows lift (harness multi-col support).
- WPA is NEVER co-entered (circular; pre-declared).

## Rule 9 baseline — the honest absorber statement

FEATS_RPRS2 already contains `sv_per_g_to`, `hld_per_g_to`, `sv_plus_hld_to`,
`gf_pct_to`, `fp_with_role_to` and the full lag-year role stack — i.e., REALIZED role
outcomes. gmLI must add via the channel where entry-leverage LEADS realized counts:
setup men whose holds haven't converted yet, pre-promotion arms, role turnover.

## Closest graveyard relative (pre-declared difference)

`rp_leverage_lag1` family (REJECTED 2026-07-09, true null): those were PRIOR-YEAR
pli/gmli — cross-year gmLI is weak (published r=0.249) and the lag stack already
spans it. This is WITHIN-season as-of leverage (published within-season role
correlation r=0.408), explicitly noted "in-season gmLI-to-date remains
untested/unregistered" in that rejection. Different horizon, different data.

## Step 2.5 coverage

Statcast PBP game-state 2018-2026 local; LI table frozen on train-era years
(2018-2023 ex-2020; state-level structure only → applying to 2024-25 holdout is
leakage-safe). rprs2 grid has ~330-350 RPs/year. Clears Rule 5.

## Honest expectation

The research card called this "plausibly the largest single additive gain in the
task" BUT also confirmed no published study tests gmLI-to-date → RoS SV+HLD — it is
an informed inference. The realized-role absorber (sv/hld/gf to-date) is strong;
MARGINAL is a live outcome. Team-relative cell expected strongest per Baumann.
