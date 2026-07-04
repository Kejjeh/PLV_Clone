# Rating-System Re-Imagining — 7-Angle Research Synthesis

**Date:** 2026-07-04 | **Status:** RESEARCH MEMO ONLY — nothing ships from this document. Every promotion candidate must pass `/validate-feature` (9-rule protocol, Rule-9 full baseline).
**Question:** Break down and re-imagine the 20-80 rating system to tie better to BrownU FP — slice all available data, change nothing, find what we missed.
**Baselines going in (Step-4 known ground):** SP STUFF forward .57 (beats FP .51); hitter OVERALL .48 (loses to FP .51); all ratings add ~0 beyond rp3/rh3/rprs2 in-season.

**One-line verdict:** The 20-80 layer's problem is CONSTRUCTION, not concept. The pillars measure real things, but the weights are wrong for FP (SP: 76% of the signal is STUFF/SWING_MISS), actively destructive (hitters: the .55/.35/.10 composite forward-predicts worse than doing nothing), and pointed at the wrong target (RP: the predictable part of RP FP is who has the job). The biggest unrated dimensions are **role + age** (hitters), **K-composition of FP** (SP), and **job security** (RP).

---

## 0. Protocol notes

- **Forward design everywhere:** T→T+1 CV-by-year on the career panels (`sp_archetype_career_panel`, hitter panel, `rp_archetype_career_panel`); in-season forward vs git-recovered 2026-06-06 model snapshots (rp3/rh3/rprs2) with FP measured after the snapshot.
- **Mandatory baselines:** raw FP level at T (always), current OVERALL, and rp3/rh3/rprs2 where joinable. Player-clustered bootstraps and dedup checks on headline partials.
- **Key confounds, flagged per angle:**
  - *Angle 1 SP in-season:* rating as-of 5/04 but rp3 snapshot dated 6/06 → ~1 month of target in-sample for rp3. This biases **toward** rp3 — and ratings still added (+.434) — but absolute r's are inflated. Ranking/partials directionally real; needs a clean re-test.
  - *Angle 5:* career panels not joinable to historical rp3 → all partials are "beyond FP level," not "beyond rp3."
  - *Angle 7 FB share:* regime-emergent (2021 pairs negative, monotone rise since).
  - *Angle 3 ROLE+AGE:* validated at the YoY horizon only.
  - *Angle 2/4:* survivorship quantified where relevant (77% appear in T+1; RP pairs require g≥20 both ends).

---

## 1. What we missed (ranked)

| # | Impact | Discovery | Key evidence |
|---|--------|-----------|--------------|
| 1 | HIGH | **Hitter OVERALL destroys signal.** The fixed .55C/.35P/.10D composite forward-predicts *worse than carrying last year's FP*. POWER is ~2× overweighted; SB is wrongly excluded; DISC shrinks. | OVERALL r=.477 < raw FP .510 < refit-pillars .515 < refit-subs .548 (n=2,105, CV). Optimal ≈ CONTACT 58 / POWER 17 / SB 17 / DISC 8. Drop-SB costs .515→.493. |
| 2 | HIGH | **ROLE+AGE is the missing hitter pillar** — first hitter construct ever to beat the raw-FP baseline. The unrated dimension: who keeps the job and the lineup slot. PA-free: −0.5·z(lineup spot) − 0.5·z(age). | Partial +.241 beyond fp_total (n=1,314); +.238 beyond fp_total+OVERALL; +.164 beyond t1_fp_projection; 5/5 year-pairs (+.21→+.32); dedup +.226; uncond +.239; r_equiv .615→.650. ~2/3 volume channel, ~1/3 rate. |
| 3 | HIGH | **SP ratings should be ~76% STUFF, SWING_MISS-dominant.** Reweighted subratings beat the current OVERALL at both horizons and are the *only* rating candidate showing signal beyond rp3. | Panel: refit-subs .590 > pillars .577 > OVERALL .551 > FP .507 (n=987). Partial(subs\|OVERALL)=+.261. In-season partial(subs\|rp3)=+.434 (n=151; +.435 data_driven-only) — confounded window, biased *toward* rp3, ratings still added. |
| 4 | HIGH | **SP FP-source composition carries forward.** Realized K/start is the best year-ahead FP predictor found anywhere in this program; IP-sourced FP mean-reverts. Rating layer needs a realized-K-volume term; the endurance-pillar hypothesis is dead. | k_per_start fwd r=+.590 (n=1,105) vs STUFF .562, OVERALL .545, FP .489; partial +.192 \|FP+STUFF (CI [+.124,+.256]); +.210 \|FP+STUFF+OVERALL. ip\|FP = −.139 (flips negative). Endurance partial +.026-.062, CI spans 0. |
| 5 | HIGH | **RP rating is pointed at the wrong target.** Predictable part of RP FP = who has the job. CONTROL + BATTED_BALL pillars carry literally zero; holds are anti-signal; STUFF's real mechanism is job security. | Role FP next-yr r=.649 vs skill FP .282 (own persistence .248/.119). CONTROL .048, BATTED_BALL −.041, hld_g −.082; sv .655 vs hld .368 sticky. Retention by STUFF tercile 33/52/88% (AUC .766); promotion by velo 6.8→26.1% (AUC .682). Role-first model r=.558 vs FP .508 (n=1,154). |
| 6 | MED | **Low-FB-share decay flag (SP).** Kitchen-sink arms (<~48% FB share) under-deliver ~0.75-1.2 FP/start next year at fixed FP+OVERALL — and it survives controlling rp3 itself. Threshold-shaped. | Persistence .81; partial +.147 (n=353, CI [+.037,+.244]); vs rp3 +.153/+.170 (n=118). Q1 residual −0.75. Caveat: regime-emergent (2021 −.035 → 2025 +.175); ~half proxies velo+GB. |
| 7 | MED | **SP STUFF×CONTROL is super-additive.** Command worth ~0 without stuff, ~+1.4 FP/start atop high stuff. The additive OVERALL credits CONTROL universally and misses this. | Partial .121 \|S,C,S²,lvl (n=1,373); clustered .126±.031; OOS split fwd r .507→.515. Quadrants 8.90 / 9.00 / 11.19 / 12.60. Limitation: baseline = FP level, not rp3. |
| 8 | MED | **Early-season SP process should anchor PRIOR-YEAR process.** 2025 composite beats the 2026 in-season composite at every cutoff through mid-June; April in-season reads mostly re-measure known talent. | r25 .577 vs r26 .491 (4/25, n=93); .553/.475; .462/.415; .410/.314 — no crossover. In-season adds +.051 after prior controls. April bridge: +.368 partial vs FP-to-date (n=115), decays to ~0 by 6/15, negative beyond rp3 at 6/6. |
| 9 | MED | **Age is unrated and pervasive** — predicts both rate decline and roster exit; main effect only, no interaction. | fp/PA partial −.117 \|FP+OVERALL (n=2,105). PA_T+1\|PA_T partial −.185/−.237; dPA by age −26/−66/−80/−122/−178; P(keep 250 PA) .80→.54; survival partial −.137. Age×PA interaction +.064 (skip). |
| 10 | LOW | **Rating-change asymmetry.** Hitter rating jumps are anti-predictive (career-year noise); SP declines are sticky. Don't chase upward hitter rating momentum. | Hitters dOVERALL\|lvl: improvers −.150 (n=853) vs decliners −.071. SP: decliners −.102 (n=409) vs improvers +.091 (n=324). |
| 11 | LOW | **STUFF banding sheds some raw K-BB%** — the one place banding loses anything. | Raw K-BB% r=.534 vs banded STUFF .528; mutual partials +.104/+.124. (Hitters: banding is *richer* — CONTACT .469 vs raw −K% .298.) |
| 12 | LOW | **IP/start stabilizes faster than FP** — early bulk reads are reliable; display lens only (forward value null). | Split-half 2026 (n=135): IP/start .649 vs FP/start .507. Forward partial +.026, CI spans 0. |

---

## 2. Per-angle detail

### Angle 1 — FP-optimal reweighting (pillars + subratings)

**SP (n=987 pairs, gs≥8 both yrs, CV-by-year):**

| Predictor | Fwd r |
|---|---|
| raw FP/start(T) | .507 |
| current OVERALL | .551 |
| STUFF alone | .572 |
| refit pillars | .577 |
| **refit subratings** | **.590** |
| FP + subs | .591 |

Partials: subs\|rawFP **+.357**; subs\|OVERALL **+.261**. Ridge pillar weights STUFF .197 / MOV .035 / CTRL .026 (**76/13/10%**). Sub weights: SWING_MISS .174 ≫ velo .036, DAMAGE_SUPP .034, WALK_AVOID .026, STRIKE_THROW .021, CALLED_STR .018, GB .010. Dropping MOVEMENT: .577→.571 (free).

**SP 2026 in-season (rating as-of 5/04 → FP 5/04–7/03, n=152):** refit-subs .732 > pillars .712 > OVERALL .693 > rp3 .684; partial(subs\|rp3) **+.434** (+.435 data_driven-only, n=150). *Confound: rp3 snapshot 6/06, ~1 mo of target in-sample for rp3 — biases toward rp3; absolutes inflated, partials directionally real.*

**Hitters (n=2,105, CV):** refit-subs .548 / FP+subs .549 > raw FP .510 > refit-pillars .515 ≫ **current OVERALL .477**. Optimal pillars CONTACT ~58% / POWER ~17% / SB ~17% / DISC ~8%. Subs: RAW_POWER .007, K_AVOID .005 lead; CONTACT_QUALITY −.001, SPRAY ~0. Drop-SB hurts (.515→.493). **In-season (6/06→7/03, n=227): rh3 .337 dominates everything; partial(subs\|rh3) = −.041 — hitter reweighting is a cross-annual fix, not an in-season edge.**

### Angle 2 — Workhorse hypothesis (SP volume/endurance)

- Descriptively real: 3.3·IP is 36-39% of FP variance, corr(3.3·IP, FP)=+.72 per start.
- But endurance is only moderately persistent (ip/start YoY .489 = exactly FP's own noise level; vs STUFF .720, K% .713) and forward-NULL beyond baselines: ip\|FP+STUFF +.026, CI [−.044,+.092]; ENDURANCE 20-80 construct +.048-.062, CI spans 0; pitches/out +.024. In-season beyond rp3: −.042/+.006.
- **Discovery instead: FP-source composition.** k_per_start fwd r=+.590 (best in program); partial +.192 \|FP+STUFF (CI [+.124,+.256], dedup +.173); k_share +.129. Component fwd-r ladder: K/start +.590, negatives +.282, IP +.262; YoY .708/.379/.489. ip\|FP = **−.139** — innings-sourced FP fades. In-season beyond rp3: zero (−.083) → rating-layer fix only.
- Interaction "endurance matters for low-stuff arms": absent/reversed (terciles −.056/+.068/+.082).

### Angle 3 — Rate × volume (hitter playing time)

- PA persistence .512 ≈ rate .510; PA/G .693 (most persistent volume stat); G .357 (noisiest — never rate on games).
- Splitting rate×PA adds nothing over raw fp_total (R² .369 vs .378) — the raw total already carries the product.
- **ROLE+AGE** (PA-free): partial **+.241** \|fp_total; +.243 \|tot+rate+PA; +.238 \|tot+OVERALL; +.164 \|t1_fp_projection; per-year +.206/+.259/+.315/+.207/+.227; dedup +.226 (n=554); uncond +.239 (n=1,595); incl-2019/20 +.282. R² .378→.422 (r .615→.650); uncond .430→.477. Channels: →PA +.247, →rate +.142 (age→rate +.182).
- PA-based durability: +.03-.06 only (PA redundant with FP level) — must build PA-free.
- Survivorship: 77.0% appear at T+1, 65.1% reach 250 PA. Age predicts exit beyond fp+lineup (−.137); lineup does not beyond fp+age (−.011) — lineup works through PA-when-present, age through roster exit.
- **In-season: solved.** rh3 expected_total_fp_remaining r=.504 vs rate-only .407; all role/volume adds <.15 at n=320.

### Angle 4 — RP: role vs stuff

- Per-game FP variance is 83% skill / 10% role, but role is 24% of the MEAN and ~52% of between-pitcher variance. Closer premium ~2 FP/g, mostly role.
- Forward (n=1,154): fp_per_g .508 | role_fp_g .468 | sv_g .458 | k% .433 | STUFF .431 | CLOSER .414 | **CONTROL .048 | BATTED_BALL −.041 | hld_g −.082**.
- Decomposed target: role FP next-yr r=.649 (in-season .750); skill FP best r=.282, own persistence .248/.119 — **irreducible noise; don't promise to predict it**.
- STUFF survives role conditioning (partial +.305 \|role block; +.244 \|role+FP) — stuff is real, but its *mechanism* is job security: retention terciles 33/52/88% (AUC .766, vs fp_per_g .816, CONTROL .535); promotion velo AUC .682 (terciles 6.8/9.2/26.1%), gmli .477.
- Weight sketch (std OLS, R²=.323): role_fp_g +.266, fp_per_g +.168, STUFF +.165, k% +.124, age −.085, CONTROL +.047, skill_fp_g ~0. Nested: role .219 → +STUFF .291 → +skill_fp .311 (r .558) vs FP-alone .258 (r .508).
- **In-season: all inside rprs2** (r=.490; STUFF partial +.017). Borderline: sv_pre +.175 (p=.054, n=123) — watch, don't promote.
- Ignore the in-season table's "xfp_ros partial\|rprs2=+.303" cell — self-residualization artifact.

### Angle 5 — Nonlinearity & construction choices

- **STUFF×CONTROL (SP):** partial .121 \|S,C,S²,lvl (n=1,373); clustered .126±.031; OOS train≤2022/test≥2023: fwd r .507→.515 (+.008 R²). Quadrant next-FP: 8.90 / 9.00 / 11.19 / **12.60**. Not curvature (STUFF² only .065). *Baseline = FP level; rp3 join untested.*
- CONTACT×POWER (H): dead — .058 after curvature; POWER partial\|lvl = .013 hi-contact / .005 lo-contact.
- Banding: fine (H banded CONTACT .469 ≫ raw .298; SP exception raw K-BB% +.104). Within-year z: fine (pooled adds .033). Cell FE: nothing (+.0247 SP / +.011 H, in-sample-inflated).
- Change asymmetry: SP decliners −.102 sticky vs improvers +.091; **hitter improvers −.150 anti-predictive** (career-year noise), decliners −.071.

### Angle 6 — Stabilization kinetics

- Ladder (split-half k, r=.5 at n=k): velo **0.2 FF pitches** | bat speed 8.9 swings | EV90 16.7 BBE | hardhit 41.9 | K%_bat 46.8 PA | z-contact/chase_bat ~57 | GB 60.5 BBE | K%_pit 74 BF | K-BB 114.5 BF | BB_bat 122.6 PA | SwStr 173 p | BB_pit 217 BF | chase_pit 225.
- April process>results bridge (4/25→): SP composite r=.481 vs FP-to-date .351; partial **+.368** (R² .123→.242). Decays +.37→+.28→+.10-.15→~0 by 6/15; **beyond rp3 at 6/6: negative** (SwStr −.124).
- **Prior-year process dominates:** r25 .577 > r26 .491 at every cutoff through 6/15; in-season adds +.051 after full prior controls. In-season reads = no-prior arms + April bridge only.
- **EWMA sweep = clean null** (13 stats × 5 half-lives × 5 cutoffs): season-to-date wins or ties everywhere. Gotcha-11 extends from FP trajectory to process-stat inputs.
- Hitters: K%/BB% zero-to-negative beyond FP at every cutoff; EV90/hardhit +.10-.15 early; bat speed +.03-.08 (replicates validated +.076). Early-trust index: velo .280 ≫ SwStr .147 > K/KBB ~.12 ≫ EV90 .084 > … 
- EV90\|rh3 +.147 at 6/6 failed replication at 4 other cutoffs — multiple-testing noise, discarded.

### Angle 7 — Untapped statcast dimensions

- **Survivor: FB_pct** (see ranked table #6). Everything else died: TTO decay (persistence .045-.129 — not a trait), platoon splits both sides (.16/.06 — noise), first-pitch strike% and zone%-behind (real skills, persist .47/.54, fully subsumed: partials −.022/+.020), HBP (−.052), induced chase (+.252 raw → **−.054 partial** — classic priced-in), arsenal entropy (.792 persistent, −.023 forward — mix *diversity* is not the axis, FB *share* is), GDP (persistent trait, no FP consequence in this scoring), sprint speed (R/PA channel genuinely robust +.237-.296, but total-FP nets to zero: +.063→+.014 w/age→−.008 w/age+SB, CI spans 0).
- **Bycatch:** hitter AGE partial −.117 \|FP+OVERALL — larger than every statcast candidate in the angle.

---

## 3. The v2 blueprint

### SP v2 — "STUFF-forward composite + K-composition + gated command"

| Change | Grounding |
|---|---|
| Reweight to ~76% STUFF / ~10-13% CONTROL; drop MOVEMENT from composite (keep as display trait) | weights .197/.026/.035; drop costs .577→.571 |
| Score OVERALL_FP from reweighted SUBS, SWING_MISS-dominant | subs .590 vs OVERALL .551; SWING_MISS .174 vs all else ≤.036 |
| ADD realized-K-volume term (k_per_start / k_share) at the rating layer | +.192 partial \|FP+STUFF, CI excl 0; ip\|FP −.139 |
| ADD stuff-gated command credit (STUFF×CONTROL) | partial .121, clustered .126±.031, OOS +.008 |
| ADD LOW_FB_RELIANCE flag (<~48% FB share, binary) | +.147 \|FP+OVERALL; +.153-.170 \|rp3; Q1 −0.75 FP/start |
| OPTIONAL raw K-BB% blend into STUFF | raw partial +.104 beyond banded STUFF |
| NO endurance pillar, NO trajectory/EWMA, NO cell FE; within-year z stays | endurance CI spans 0; EWMA null; FE +.0247 in-sample; pooled-z +.033 |
| Early season (pre mid-June): anchor on prior-year process; in-season reads for no-prior arms + April bridge | r25 .577 > r26 .491; bridge +.368; crossover none by 6/15 |

**Ceiling:** panel forward r .551 → ~.59-.60. In-season beyond rp3: the +.434 partial is queue #1 — until it passes cleanly, all of this is a rating/context layer (Rule 13).

### Hitter v2 — "fix the composite + ROLE+AGE pillar; it's a valuation layer, not a weekly layer"

| Change | Grounding |
|---|---|
| Reweight pillars ≈ CONTACT 58 / POWER 17 / SB 17 / DISC 8 (or refit subs: RAW_POWER + K_AVOID lead; drop CONTACT_QUALITY/SPRAY at margin) | OVERALL .477 < FP .510; refit .515/.548; drop-SB costs .515→.493 |
| ADD ROLE+AGE pillar: −0.5·z(lineup spot) − 0.5·z(age), PA-free | +.241 \|fp_total; 5/5 years; dedup +.226; r .615→.650 |
| ADD age main effect (no interaction) | −.117 \|FP+OVERALL; age×PA only +.064 |
| NO CONTACT×POWER, NO cell FE, NO momentum, don't chase rating jumps | .058; +.011; improvers −.150 anti-predictive |
| Banding + within-year z stay | banded CONTACT .469 ≫ raw .298 |

**Scope honesty:** cross-annual only. In-season every reweighting loses to rh3 (subs .251 vs rh3 .337; partial −.041). Hitter v2 = **draft / keeper / rest-of-career valuation + display layer.** In-season volume already solved by rh3 (.504 vs .407).

### RP v2 — "role-first, stuff-as-gatekeeper; stop pretending to predict run prevention"

| Change | Grounding |
|---|---|
| Re-target: predict ROLE FP, not skill FP | role r=.649/.750 vs skill .282, persistence .248/.119 |
| Composite ≈ 55-60% save-role (saves ONLY) / 30% STUFF-K / 10% prior FP | nested R² .219→.291→.311 (r .558 vs .508) |
| DROP CONTROL and BATTED_BALL pillars | fwd .048 / −.041; retention AUC .535; promotion .483 |
| Exclude holds from role credit | hld fwd −.082; persistence .368 vs sv .655 |
| Surface retention/promotion sub-lenses | STUFF terciles 33/52/88%; velo AUC .682 (6.8→26.1%) |
| Season-prior layer ONLY | in-season all inside rprs2 (STUFF +.017 vs rprs2 .490) |

### Cross-cutting construction law (all roles)

1. Within-year z-norms stay (+.033 pooled). 2. Banding stays (sole exception: SP raw K-BB% blend). 3. No cell fixed effects. 4. **No EWMA / recency-weighting of any rating input** — gotcha-11 extended to process stats. 5. Prior-year anchor early season for established players. 6. Stabilization ladder governs sub-rating readability (velo instant → BB% never). 7. Rule 13: rp3/rh3/rprs2 stay the headline unless a queue item passes `/validate-feature`.

---

## 4. /validate-feature queue (ranked by expected lift × plausibility)

1. **SP reweighted STUFF/SWING_MISS subs composite → rp3 candidate.** Clean re-test: freeze weights on pre-2026 panel, score vs a same-date *logged* rp3 snapshot, FP strictly after. Prior: +.434 partial in a window biased toward rp3.
2. **LOW_FB_RELIANCE flag (<~48% FB share) → rp3 context/feature.** Pre-register: binary threshold, recent-era only, velo+GB in baseline. Prior: +.153-.170 beyond rp3 (n=118).
3. **Hitter ROLE+AGE → YoY/total-FP valuation layer** (draft/keeper board, NOT in-season rh3). Prior: +.241, 5/5 years.
4. **SP STUFF×CONTROL interaction → OVERALL construction.** Must first build the historical rp3-snapshot join it has never faced.
5. **SP k_per_start/k_share → archetype rating layer** (pre-register rating-layer target; known in-season null beyond rp3, −.08).
6. **RP role-first rebuild** (season-prior layer). Deferred companion: sv_pre beyond rprs2 (+.175, p=.054, n=123) — re-run when post-window sample doubles.
7. **Hitter OVERALL reweight** (display/archetype-accuracy only; batch with #3).
8. **Prior-year-process April anchor** — needs an April rp3 snapshot; schedule April 2027 (snapshot logger is live, refresh step 4.10).

---

## 5. Unchanged truths (what the research confirmed)

1. **Ratings add ~0 beyond the models in-season by June** — hitter refit \|rh3 −.041; RP STUFF \|rprs2 +.017; SP process \|rp3 6/6 negative. Sole open exception: queue #1.
2. **SP STUFF is real** (fwd .528-.572 > FP .479-.507; persistence .720).
3. **CONTACT carries hitters, POWER ~0 forward** (partial −.035; not rescued by contact).
4. **Mean-reversion (gotcha 11) extended, not overturned** — EWMA of process inputs null everywhere.
5. **Bat speed is still the only hitter process stat adding beyond the FP level** (+.079 replication of the validated +.076); early-readable, not early-decisive.
6. **Rule 13 survives:** chase, FPS, zone-behind, sprint, entropy, endurance — every big raw r was already priced in.
7. **Construction mechanics sound:** within-year z, banding, no-cell-FE all validated as-built.
8. **In-season hitter volume solved** by rh3's expected_total_fp_remaining (.504 vs .407).
9. **Raw K-BB% is still the strongest single raw SP skill** (.534) — consistent with sp_floor.
10. **SB/speed ≈ 0 for total FP at the channel level** (sprint nets to zero) — but the SB *pillar* carries small real composite signal (~17% optimal) because SB is a direct FP component.
11. **Season-sample splits are not traits:** TTO, platoon (both sides) — permanent kills.
12. **Shadow-scout scoping confirmed:** in-season process reads are for no-prior arms + the April bridge.

---

## 6. Dead-end registry (do not re-derive)

**SP:** endurance/ip-per-start pillar (CI spans 0) | pitches/out, pitches/start | endurance×low-stuff interaction (reversed) | in-season K-composition beyond rp3 (−.08) | MOVEMENT pillar (drop costs .006) | TTO decay (persistence .045) | platoon splits (.158) | first-pitch strike%, zone%-behind (subsumed) | HBP rate | induced chase (−.054 partial) | arsenal entropy | EWMA any half-life | in-season process beyond rp3 at 6/6 | in-season 2026 composite vs prior-year for established arms.
**Hitters:** in-season reweighting beyond rh3 (−.041) | CONTACT×POWER (.058) | CONTACT_QUALITY (−.001) / SPRAY (~0) subs | PA-based durability (+.03-.06) | rate-vs-PA split as separate predictors | age×PA interaction | games-played as volume anchor (.357) | K%/BB% early in-season reads | EV90-at-6/6 flicker (failed replication) | platoon splits (.062) | GDP | sprint→total FP | pull-air (already rated) | upward rating momentum (−.150).
**RP:** CONTROL + BATTED_BALL pillars | holds as forward signal | gmli as promotion predictor (.477) | STUFF/OVERALL overlay on rprs2 (+.017) | next-year skill FP as a target (persistence .248) | team-context promotion term (team_abbr 0% populated — data-blocked).
**Data-blocked (not attempted, not faked):** SP quantile ceiling/floor from career panels (per-year means only; multi-year game logs needed); April rp3 baseline (no snapshot exists pre-2026-06).

---

## 7. Artifacts

| Angle | Scratch path |
|---|---|
| 1 Reweighting | `.cache/rating_reimagine/angle1_reweight/` (reweight.py, reweight_2026fwd.py) |
| 2 Workhorse | `.cache/rating_reimagine/workhorse/` (wh1-wh4 + parquets) |
| 3 Rate×volume | `.cache/rating_reimagine/rate_x_volume/` (yoy_volume, yoy_role_age, inseason_volume, role_age_2026_demo.csv) |
| 4 RP role | `.cache/rating_reimagine/rp_role_vs_stuff/` (analyze.py, inseason.py, 6/06 snapshots) |
| 5 Nonlinearity | `.cache/rating_reimagine/angle5_nonlinearity/` (run.py, run2.py) |
| 6 Kinetics | `.cache/rating_reimagine/stabilization_kinetics/` (early_trust_index.csv) |
| 7 Statcast dims | `.cache/rating_reimagine/angle7_statcast_dims/` |

*Memo location: `data/research/rating_reimagine_2026-07-04.md`. No production changes ship from this document.*