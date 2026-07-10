# Era / regime diagnostic — 2026-07-10 (MEASUREMENT ONLY)

**Scope.** Honest map of rule-change and ball-composition regime effects in our data
and in the production models (rh3, rp3). No fixes, no promotions — this memo is the
evidence base for deciding whether regime-aware modeling is worth `/validate-feature`
cycles. Two companion agents are concurrently validating specific regime candidates.

**Data.** `statcast_2015..2026.parquet` (xfp_cache, pitch level), `hitters_multiyr_2015_2026.csv`,
`sp_multiyr_2015_2025.csv`, rolling substrates via the production-parity harnesses
(`scripts/xfp/_validate_rh3_v3_helper.py`, `scripts/xfp/_rp3_validation_harness.py`),
MLB Stats API team season stats (SB/CS). Models re-run at exact production parity —
per-year LOO r matches the 2026-07-10 shipped bundles to 4 decimals.

**Regime timeline used.** 2018-19 = pre (juiced-ball peak 2019); 2020 = excluded
(short season, 3-batter min); 2021-22 = transition (deadened ball, June-2021
sticky-stuff crackdown mid-season, universal DH 2022); 2023+ = new rules (shift ban,
bigger bases + pickoff limits, pitch clock, balanced schedule).

---

## 1. League environment by year, 2015-2026

From statcast parquets (needed columns only, year by year). BABIP proxy =
(1B+2B+3B)/(BIP−HR). LHB pull = GB+LD off LHB with spray angle >15° toward RF,
HR excluded. SB from MLB Stats API team hitting totals. FP/PA from multiyr
(PA-weighted, real MLB-API counting stats).

| year | FP/PA | HR/barrel | HR/FB | barrel/BIP | BABIP | LHB pull GB+LD BABIP | K% | SBatt/tm-g | SB% | FF velo | FF spin | SwStr% | PA/tm-g |
|------|-------|-----------|-------|------------|-------|----------------------|-----|-----------|-----|---------|---------|--------|---------|
| 2015 | .478 | .717 | .106 | .052 | .296 | .288 | 20.4 | 0.73 | 70.2 | 93.1 | 2239 | 9.9 | 37.9 |
| 2016 | .497 | .712 | .137 | .061 | .298 | .287 | 21.1 | 0.73 | 71.7 | 93.2 | 2267 | 10.1 | 38.1 |
| 2017 | .510 | .773 | .177 | .062 | .297 | .287 | 21.6 | 0.71 | 73.0 | 93.2 | 2260 | 10.4 | 38.2 |
| 2018 | .479 | .662 | .167 | .067 | .294 | .289 | 22.2 | 0.71 | 72.1 | 93.1 | 2266 | 10.7 | 38.1 |
| 2019 | .513 | .734 | .200 | .074 | .296 | .288 | 22.9 | 0.64 | 73.3 | 93.4 | 2289 | 11.2 | 38.4 |
| 2020 | .498 | .687 | .185 | .076 | .291 | .272 | 23.4 | 0.66 | 75.2 | 93.4 | 2304 | 11.4 | 37.1 |
| 2021 | .481 | .617 | .171 | .079 | .290 | .282 | 23.2 | 0.60 | 75.7 | 93.7 | 2274 | 11.3 | 37.5 |
| 2022 | .460 | .559 | .150 | .075 | .289 | .274 | 22.4 | 0.68 | 75.4 | 93.9 | 2275 | 11.2 | 37.5 |
| 2023 | .497 | .585 | .164 | .081 | .295 | .303 | 22.7 | 0.90 | 80.2 | 94.2 | 2283 | 11.2 | 37.9 |
| 2024 | .473 | .562 | .152 | .078 | .289 | .305 | 22.6 | 0.94 | 79.0 | 94.3 | 2298 | 11.1 | 37.6 |
| 2025 | .484 | .526 | .156 | .086 | .289 | .300 | 22.2 | 0.91 | 77.7 | 94.5 | 2323 | 11.0 | 37.7 |
| 2026 | .488 | .571 | .156 | .079 | .287 | .308 | 22.1 | 0.89 | 76.3 | 94.7 | 2315 | 10.8 | 37.9 |

**Read.** The regimes are unambiguously real in the raw environment: HR-per-barrel
(ball-drag proxy) fell ~30% from the 2017-19 juiced peak (.73-.77) to the deadened
era (.53-.59 since 2022, 2025 the deadest ball on record), SB attempts jumped +32%
in 2023 (0.68→0.90/team-game) with success rate +5pp (75→80%) and both have PERSISTED
through 2026, and LHB pull-side GB+LD BABIP broke +~30 points the moment the shift
ban landed (.274→.303) and stayed there. League offense level (FP/PA) oscillates in
a ±5% band (.460 trough 2022, .513 peak 2019) — big enough to matter for totals,
small relative to the player-to-player spread the models rank on.

### 1b. Mid-2021 sticky-stuff enforcement (monthly, 2021)

| month | FF spin | FF velo | SwStr% | K% |
|-------|---------|---------|--------|-----|
| Apr | 2312 | 93.6 | 11.6 | 24.4 |
| May | 2324 | 93.7 | 11.4 | 23.9 |
| Jun | 2259 | 93.8 | 11.3 | 23.2 |
| Jul | 2240 | 93.7 | 11.1 | 22.7 |
| Aug | 2245 | 93.6 | 11.1 | 22.6 |
| Sep | 2261 | 93.7 | 11.1 | 22.1 |

**Read.** The crackdown (announced Jun 3, enforced Jun 21, 2021) is a clean
within-season break: FF spin −84 rpm May→Jul with only partial recovery, K% −2.3pp
Apr→Sep (part seasonal, but the June step is visible). 2021 is therefore the one
training year whose first half and second half are DIFFERENT regimes — relevant to
§3, where 2021 is the worst rh3 LOO year and the biggest rp3 over-projection year.
(Year-level FF spin resumed climbing afterward — 2274→2323 by 2025 — so this was a
one-time within-2021 discontinuity, not a permanent level shift in the column.)

---

## 2. INCIDENTAL STRUCTURAL FINDING: the rh3 SB pipe is dead, and the 2023 rules tripled its cost

While checking whether `sb_per_pa_to_sh`'s coefficient rose post-2023 (§4), we found
**it cannot: `sb_per_pa_to` is 0.0 for all 90,248 rows of
`rolling_hitters_2018_2026.csv`** (all years, min=max=0). Root cause: `build_rolling_hitters.py`
counts SB from statcast `events` (`SB_EVENTS = {'stolen_base_2b', ...}`), but stolen
bases never appear as PA-ending statcast events. `build_hitters_multiyr.py` hit the
identical bug and FIXED it (line ~390: "SB events don't appear as PA-ending events,
so the in-aggregate sb_per_pa was always 0" — patched with MLB-API `mlb_sb`), but the
fix was never propagated to the rolling builder. Consequences:

1. **Feature:** `sb_per_pa_to_sh` in RH3_FEATS is a constant. Standardized coef is
   exactly 0.0 in every fit. Harmless as a feature, but it holds a PASS record in the
   validated-signals registry while being degenerate (registry hygiene issue).
2. **TARGET:** `ros_full_fp_per_pa` = statcast core FP (TB+BB+HBP+**SB=0**−K) plus a
   season-level (R+RBI)/PA rate. **The SB term of BrownU scoring is entirely missing
   from the rh3 target** (R and RBI are added back; SB is not). rh3 projects
   FP-without-SB.
3. The prior (`prior_fp_per_pa`, Marcel over multiyr `fp_per_pa_actual`) DOES include
   real SB — so the model's prior and its target disagree about what FP means.

**How big (from multiyr, real MLB-API SB):**

| year | league SB FP/PA omitted | p90 (PA≥300) | p99 | max |
|------|------------------------|--------------|-----|-----|
| 2018 | .0133 | .033 | .063 | .073 |
| 2021 | .0122 | .033 | .052 | .089 |
| 2022 | .0136 | .036 | .057 | .102 |
| 2023 | .0190 | .047 | .084 | .135 |
| 2024 | .0198 | .050 | .092 | .103 |
| 2025 | .0188 | .044 | .074 | .132 |
| 2026 | .0179 | .041 | .076 | .077 |

**Read.** Post-2023 the omitted component is ~.019 FP/PA league-wide (+50% vs
pre-2023) and ~.05 FP/PA at the 90th percentile of regulars — against an rh3 MAE of
.085 and a typical projection spread of ~.13 SD, an elite base-stealer
(.10-.13 SB-FP/PA) is structurally under-ranked by roughly one full MAE unit. Because
BOTH the target and the feature are blind, no amount of within-model validation can
see this; it only shows up against TRUE BrownU FP. This is the single most
actionable item in the memo, and it is regime-coupled: the 2023 running rules made
the blind spot ~50% more expensive and more player-differentiating.

---

## 3. Does the model fit regime years worse? (production LOO, per-year)

Exact production prep + `cross_year_eval` filters; per-year r/MAE match today's
shipped bundles. `bias` = mean(pred − actual) on the held-out year (not in bundles).

**rh3** (FP/PA):

| year | era | n | r | MAE | bias | mean actual | target SD |
|------|-----|---|-----|------|------|------------|-----------|
| 2018 | pre | 5154 | .615 | .0836 | +.0021 | .496 | .133 |
| 2019 | pre | 5387 | .685 | .0881 | −.0184 | .533 | .149 |
| 2021 | trans | 5258 | .584 | .0900 | −.0240 | .514 | .140 |
| 2022 | trans | 5055 | .653 | .0811 | +.0149 | .459 | .133 |
| 2023 | new | 5312 | .609 | .0859 | +.0059 | .493 | .137 |
| 2024 | new | 5271 | .609 | .0842 | +.0122 | .463 | .135 |
| 2025 | new | 5134 | .638 | .0821 | +.0120 | .477 | .134 |

**rp3** (FP/start):

| year | era | n | r | MAE | bias | mean actual | target SD |
|------|-----|---|-----|------|------|------------|-----------|
| 2018 | pre | 2677 | .544 | 2.88 | −0.33 | 10.78 | 4.37 |
| 2019 | pre | 2807 | .653 | 2.97 | +0.02 | 9.90 | 4.82 |
| 2021 | trans | 2709 | .573 | 2.73 | **+0.61** | 9.98 | 4.25 |
| 2022 | trans | 2767 | .591 | 2.86 | −0.17 | 10.98 | 4.40 |
| 2023 | new | 2740 | .506 | 2.91 | −0.43 | 10.18 | 4.20 |
| 2024 | new | 2698 | .474 | 2.81 | −0.09 | 10.62 | 4.20 |
| 2025 | new | 2713 | .572 | 2.71 | +0.30 | 10.22 | 4.23 |

**Read — rank skill (r/MAE): year noise dominates, no credible era degradation.**
MAE is flat across eras for both models (rh3 .081-.090; rp3 2.71-2.97, and the best
rp3 MAE year is 2025, a new-rules year). rp3's r dip in 2023-24 (.51/.47) looks
era-ish at first glance but rebounds fully in 2025 (.572 ≈ the pre-era mean), and r
differences track target SD (2019 has both the biggest target spread and the best r
in both models — a mechanical relationship, not model skill). Verdict: the new-rules
era is NOT systematically harder to model.

**Read — bias: era LEVEL leaks into the LOO at ~half strength, and 2021 is the
sticky-stuff casualty.** Per-year bias is strongly anti-correlated with the year's
league-level deviation from the pooled mean: **rh3 corr −0.91, slope −0.53** (a year
that runs +.04 hot vs pooled gets under-predicted by ~.02); rp3 corr −0.52, slope
−0.45. So features+prior absorb roughly half of a year's environment shift and the
other half lands in bias. Two important qualifiers: (a) a per-year additive bias
does NOT change within-year rank order — the product's primary use — it only
mis-levels FP-total forecasts (matchup dashboard, RoS totals); (b) 2021 is the
outlier both ways (rp3's largest over-projection +0.61 FP/start; rh3's worst r and
largest under-prediction), which is mechanistically consistent with §1b: pitchers
projected off pre-crackdown form underperformed after June 21, and hitters
outperformed. The mid-season regime break degrades 2021 as a training/eval year in a
way whole-year features cannot see.

---

## 4. Coefficient drift across eras

Production pipeline (StandardScaler + Ridge) refit on era subsets. IMPORTANT
methodology note: with RidgeCV, the late subsets chose much larger alphas (rp3: 262
early vs 1504 late), which mechanically shrinks all late coefficients — so the
comparison below uses a FIXED alpha (the pooled RidgeCV choice: rh3 747, rp3 2541).
Standardized (per-SD) coefficients; target units FP/PA (rh3), FP/start (rp3).

**rh3, 2018-2022 vs 2023-2025** (the shift-ban/running-rules split; big features):

| feature | early | late | Δ% | note |
|---------|-------|------|-----|------|
| sb_per_pa_to_sh | .0000 | .0000 | n/a | **degenerate — see §2; cannot rise** |
| hr_per_pa_to_sh | .0131 | .0073 | −44% | HR outcome de-weighted |
| barrel_pct_to_sh | .0084 | .0135 | +61% | barrel process up-weighted |
| iso_to_sh | .0169 | .0154 | −9% | stable |
| k_pct_to_sh | −.0169 | −.0138 | +18% | stable-ish |
| xwoba_per_pa_to_sh | .0117 | .0147 | +26% | stable-ish |
| hard_hit_pct_to_sh | .0207 | .0162 | −22% | mild down |
| prior_fp_per_pa | .0312 | .0264 | −15% | stable |

**rp3, 2018-2022 vs 2023-2025:**

| feature | early | late | Δ% | note |
|---------|-------|------|-----|------|
| k_pct_to_sh | .626 | .305 | −51% | but see block note below |
| c_plus_swstr_to_sh | .167 | .413 | +147% | collinear partner of k_pct |
| swstr_pct_to_sh | .400 | .377 | −6% | stable |
| bb_pct_to_sh | −.100 | −.053 | +47% | walk penalty softer |
| avg_velo_to | .313 | .419 | +34% | velo worth more |
| xwoba_per_pa_to_sh | −.414 | −.287 | +31% | softer |
| prior_fp_per_start | .641 | .540 | −16% | stable |
| ros_opp_xwoba_weighted | −.509 | −.229 | −55% mag | schedule spread compressed (balanced schedule 2023) |
| gs_to | .450 | −.016 | sign flip | volume cue collapse |
| fp_per_start_to | .368 | .181 | −51% | in-season level de-weighted |

**Honesty check — per-year single-year fits (fixed alpha) say most of this is
noise.** Refitting one year at a time shows year-to-year coefficient swings larger
than the era deltas: rh3 `hr_per_pa` runs −.001, +.007, +.013, +.013, +.005, −.007,
+.017 across 2018→2025 (no era step); rp3's k_pct "decline" is real in sequence
(.90 in 2022 → .40/.37/.06) **but the collinear K-block (k_pct + swstr + c_plus_swstr)
sums to ~1.0-1.5 in every year with no era pattern — the members reallocate, the
block doesn't move.** Same for contact/whiff (exactly collinear) in rh3. The three
drifts that survive scrutiny at least directionally (consistent sign in BOTH era
splits and in the per-year trend):

1. **rh3 HR-outcome → barrel-process swap** (hr_per_pa −44%, barrel_pct +61%
   post-2023): coherent with the deadened ball — a given HR rate now carries more
   luck, contact quality remains real. Direction is credible; magnitude is within
   year-noise, so treat as a hypothesis, not a fact.
2. **rp3 velo up-weighting** (+34% post-2023, and the per-year trend is upward-ish):
   consistent with the league-wide velo climb (93.1→94.7) making velo more
   FP-differentiating. Weak evidence.
3. **rp3 ros_opp_xwoba_weighted halving post-2023**: this one has a known mechanism —
   the 2023 balanced schedule compressed opponent-strength spread — and needs NO fix,
   because the feature is rebuilt from actual schedules every year (the smaller
   coefficient IS the correct response to a compressed regressor).

**Answer to the pre-registered question "did sb_per_pa's coefficient rise
post-2023?": unanswerable and guaranteed no — the column is structurally zero (§2).**
The question becomes answerable only after the rolling-builder SB fix.

---

## 5. Shrinkage mis-centering (pooled vs per-year population means)

`compute_population_means` pools 2018-2025 (denom-weighted). Worst per-year
deviation per feature, in SDs of the raw rate across the train panel:

**rh3** (worst offenders; all others < 0.09 SD):

| feature | worst year | dev (SD) | pooled μ | year μ |
|---------|-----------|----------|----------|--------|
| iso_to | 2019 | +0.17 | .163 | .182 |
| hard_hit_pct_to | 2018 | −0.17 | .387 | .363 |
| hr_per_pa_to | 2019 | +0.17 | .0318 | .0366 |
| barrel_pct_to | 2018 | −0.14 | .079 | .071 |

**rp3:**

| feature | worst year | dev (SD) | pooled μ | year μ | pattern |
|---------|-----------|----------|----------|--------|---------|
| zone_pct_to | 2019 | −0.48 | .491 | .474 | secular: −.14, **−.48**, +.06, −.04, .00, +.19, **+.46** (2018→2025) |
| o_swing_pct_to | 2018 | −0.30 | .282 | .271 | mostly 2018 |
| c_plus_swstr_to | 2021 | +0.25 | .284 | .291 | sticky-stuff year |
| swstr_pct_to | 2018 | −0.25 | .118 | .112 | early years |
| k_pct_to | 2021 | +0.20 | .222 | .233 | sticky-stuff year |

**Read.** The worst case is rp3 `zone_pct_to`: a clean secular drift where the
pooled center is ~0.5 SD wrong at BOTH ends of the training window (2019 pitchers
get pulled up toward a zone% that no longer existed; 2025 pitchers get pulled down
toward one that no longer exists). But the EFFECTIVE distortion after the shrinkage
weight k/(n+k) is small: for a mid-season SP (~1,200 pitches, k=200) it's ~14% of
0.48 SD ≈ **0.07 SD**; only early-season rows (300 pitches → 40% weight → ~0.19 SD)
feel it materially. rh3's worst cases are ≤0.17 SD raw and land at ≤~0.06 SD
effective for a 300-PA hitter. So: pooled-mean shrinkage IS mildly era-blind
(2019 hitters get pulled toward a deader-ball ISO/HR center and vice versa), but the
magnitude is a second-order, early-season-only effect — per-year (or era-local)
shrinkage centers are a legitimate micro-candidate, with a small expected ceiling.

---

## 6. Volume layer

| quantity | range 2015-2026 | 2022→2023 step | verdict |
|----------|-----------------|----------------|---------|
| PA / team-game | 37.1-38.4 (37.5 in 2021-22, 37.9 in 2023) | +0.42 (+1.1%) | stable — pitch clock changed game TIME, not PA volume |
| GS / team-game | 1.0 by rule | none | structural constant |
| TBF / GS (proxy, sp_multiyr gs≥5) | 25.7 (2015) → 23.5 (2021), 23.5-24.2 since | +0.43 | secular pre-2021 decline, FLAT through the 2023 rules |

**Read.** Nothing the volume models consume moved with the 2023 rules; the SB
environment matters to rh3 (scoring), not to volume. No action.

---

## 7. RANKED LIST

### (a) Real in our data AND plausibly actionable

1. **SB pipeline break (rh3 target + feature), amplified ~50% by the 2023 running
   rules.** `sb_per_pa_to` all-zero in the rolling substrate; `ros_full_fp_per_pa`
   omits the SB scoring term entirely. ~.019 FP/PA league / ~.05 p90 / ~.13 max
   post-2023 of systematic under-projection concentrated on base stealers, invisible
   to all within-model validation. Fix path is known (port the multiyr `mlb_sb`
   patch into `build_rolling_hitters.py`, rebuild substrate, re-run rh3 gates); only
   then is the "should SB be repriced post-2023" question even testable.
2. **2021 as a split-regime training year (sticky-stuff mid-season break).** Largest
   rp3 over-projection (+0.61 FP/start), worst rh3 r (.584), and a documented
   within-year mechanism (FF spin −84 rpm in June 2021). Candidate: down-weight 2021
   or add a post-crackdown split for 2021 rows in training. Expected gain small
   (one year of seven), but it is the cleanest causal story in the whole diagnostic.
3. **Year-level mis-centering of FP TOTALS (bias ≈ −0.5 × year environment
   deviation, rh3 corr −0.91).** Actionable ONLY for total-FP surfaces (matchup
   dashboard, RoS totals, playoff projections) — e.g., a league-environment-to-date
   level calibration. Explicitly NOT a re-rank lever: a per-year additive offset
   never changes within-year order, and memory item #13 (forward-calibration study)
   already warns against shading projections from bias diagnostics. File under
   "totals calibration," not "model fix."

### (b) Real but already absorbed by the pipeline

4. **Shift ban / LHB pull-BABIP break (+30 pts, persistent).** All `*_to` features
   are within-year by construction, so a hitter's post-ban BABIP gain flows straight
   into his observed rates AND his target; the Marcel prior's league term is
   per-target-year (`league_mean_by_year[tgt]`), so the prior level re-centers too.
   The only leak was one-time: 2023 priors built on 2020-22 player histories
   under-rated shift-suppressed LHB pull hitters for one season — already past.
   Residual exposure: pooled shrinkage centers (≤0.17 SD raw, ≤~0.06 SD effective).
5. **Ball-drag drift (HR/barrel .77→.53).** Same absorption logic: within-year HR
   rates reflect the current ball; the year-centered prior league term absorbs the
   level. The suggestive hr→barrel coefficient swap (§4) is the residual, and it is
   within year-noise. A barrel-first HR treatment is a legitimate but low-prior
   candidate under the +0.005 gate.
6. **Balanced schedule 2023 (ros_opp_xwoba coefficient halved).** The feature is
   rebuilt from actual schedules per year; the smaller coefficient is the correct
   fitted response to a compressed regressor. Nothing to do.
7. **Pooled-mean shrinkage era-blindness generally** (worst: rp3 zone_pct ±0.48 SD
   at the window ends). Real, secular, and mostly neutralized by the k/(n+k) weight
   except in April-May. Per-year shrinkage centers = cheap micro-test, small ceiling.

### (c) Not real / negligible in our data

8. **"New-rules era is harder to model."** No: MAE flat across eras for both models;
   rp3's 2023-24 r dip rebounds in 2025 and r co-moves with target SD (2019's best-r
   is a variance artifact). Year noise dominates.
9. **Era-specific coefficients beyond §4's three survivors.** The big era-subset
   swings (rp3 k_pct −51%, gs_to sign flip, IL-feature swings, rh3 swstr sign flip)
   are collinear-block reallocation and single-year noise — the K-block sum is
   era-stable. Do not chase era-interaction features off this table. (Half the
   apparent "late-era coefficient shrinkage" in a naive RidgeCV comparison was the
   alpha choice, not the data.)
10. **Pitch clock / universal DH / 3-batter-minimum effects on our layers.**
    PA/team-game, GS/team-game, TBF/GS all flat through 2023; DH is a pool-composition
    change absorbed by within-year features; 3-batter-min is a 2020/RP-side story and
    2020 is excluded from training. Volume layer unaffected (§6).

---

## Method appendix

- Scratch scripts + intermediates: session scratchpad (`era_env_scan.py`,
  `era_model_diag{,2,3,4}.py`; CSV/JSON intermediates alongside). Nothing in the
  repo was modified; this memo is the only repo addition.
- LOO parity: per-year r reproduced the shipped 2026-07-10 bundles exactly
  (rh3 overall r .6339, rp3 .5614).
- Era-subset fits: production Pipeline, alpha FIXED at the pooled RidgeCV choice
  (rh3 747, rp3 2541) to remove the regularization-path confound; RidgeCV-chosen
  alphas also computed (rh3 312 early / 890 late; rp3 262 early / 1504 late) and
  shown to distort a naive comparison.
- Per-year single-year fits used alpha/7 (n scales ~1/7) as a rough
  shrinkage-per-row match; used only as a noise yardstick, not as estimates.
- BABIP and LHB-pull definitions are proxies (see §1 header); they are
  internally consistent across years, which is all the break-detection needs.
- SB/CS: MLB Stats API team season hitting stats, all 12 seasons fetched live.
