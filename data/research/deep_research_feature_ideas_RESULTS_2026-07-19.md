# Ranked Candidate Features for In-Season RoS Fantasy-Baseball Projection Models (2020–2026 Sabermetric Survey)

## TL;DR
- The strongest additive candidates are **direction-quality features** (pulled-air-ball rate; spray-adjusted contact quality) for hitters and **in-season role/opportunity micro-structure** (gmLI-to-date, team-relative) for relievers — both carry information that season-to-date fantasy points and the cumulative contact/discipline stack provably cannot absorb, and both are computable from data already on hand (Statcast 2015+, MLB Stats API).
- A second tier of **team-context spillovers** (teammate-quality-as-of for R+RBI) and **rule-change exploitables** (bigger-bases SB ecosystem; shift-ban lefty line-drive/GB hitters) is theoretically orthogonal and historically sourced, but effect sizes are small and several are partially absorbed by lineup-spot and SB-rate features already in the baseline.
- Everything derived from **bat tracking (2024+)** and **swing-path/attack-angle (2025+)** is FUTURE-flagged: it cannot clear the 5-of-7-year sign-consistency gate until ~2028–2029, and the public record already shows squared-up rate and swing length add ~0 to power/K projection once contact-quality stats are controlled — so these are same-year experiments, not ranked top.

## Key Findings

**The absorber is the real adversary, and direction is the cleanest escape hatch.** The most robust orthogonality argument in the public literature is that Statcast's xwOBA is **direction-blind** — it uses exit velocity, launch angle, and (on some balls) sprint speed, but not spray angle. This is documented by xwOBA's own developers (MLB Technology Blog: "We currently do not control for spray angle since we haven't found strong enough evidence that certain pull-oppo tendencies lead to better wOBA results") and by Tom Tango. Because your baseline's contact-quality stack (hard-hit%, barrel%, xwOBA/PA) inherits that blindness, a **pulled-air-ball** feature carries genuinely new information about which hitters will out- or under-produce their expected-stat profile in the rest of the season. Baseball Savant's Statcast Batted Ball Leaderboard quantifies the descriptive gap: from 2022–24, pulled airballs were only 17.5% of batted balls but produced 66% of all home runs, hitting .547 with a 1.227 slugging percentage and a **.733 wOBA** — versus **.353 wOBA** for non-pulled airballs. FanGraphs' "The Pulled Fly Ball Revolution Was Always Underway" found that "each percentage point of pulled fly balls in excess of the league-average rate corresponded with about an 0.005 bump in actual minus expected wOBAcon (r² = 0.29)." Critically for prediction, air-pull rate is **sticky**: historical pull rate on medium-hit (95–105 mph) fly balls predicts future pull rate at r² = 62.4% (Ben Clemens, FanGraphs).

**But direction is a HR/power lever, not a batting-average or process lever.** Clemens' follow-up work ("Which Hitters Benefit From Pulling?") found that once you know a hitter's "best speed" and air/ground tendency, "Adding pull rate to that mix doesn't seem to help much" for overall wOBA — "the difference between being the pull-happiest and oppo-happiest hitter is worth only a handful of points of wOBA." The benefit concentrates in medium-power hitters and in the wOBA-minus-xwOBA residual, not raw production. This matters for your points model: the additive signal is on the **TB/HR component of FP**, and it should be framed as an interaction (pull-air × moderate-power) rather than a main effect.

**Reliever role is the biggest orthogonal-to-skill signal in the entire task, and it's under-exploited in-season.** For rprs2, where 5·SV + 2·HLD dominates, opportunity is nearly independent of ERA/skill. RotoGraphs states gmLI "has absolutely nothing to do with the pitcher himself, and deals solely with his usage." A structural nuance confirmed in deep research: cross-year gmLI autocorrelation is weak — FanGraphs' "What Determines Reliever Leverage?" (Jack Moore) reports "The highest year-to-year correlation... is a mere 0.249 with gmLI," while salary is the strongest predictor ("The correlation of yearly salary to gmLI is 0.36, nearly 1.5 times higher than any of the other measure tested"), so the graveyard's "reliever leverage lag-year features" verdict is correct. But **within-season** gmLI tracks role far more tightly. FanGraphs' "Do Managers Give Their Toughest Battles to Their Strongest Relievers?" (Michael Baumann, July 2024) found a reliever's K-BB% relative to his own bullpen correlated with gmLI at **r = 0.408**, and ERA-minus-team-bullpen-ERA at −0.314; practitioners (RotoWire's "Closer Encounters," The Hardball Times' "Predicting reliever wins") use in-season gmLI-to-date, filtered by team, as the leading indicator of role promotion. The user has registered in-season gmLI-to-date as UNTESTED — this is the highest-value single idea for rprs2.

**Team context genuinely drives R+RBI, but batting-order-spot features already absorb most of it.** The Tango-derived consensus (RotoGraphs' Scott Spratt; RotoBaller) is that R and RBI are "team-dependent" and "out of the hitter's control," driven by lineup slot and teammate quality. Spratt's chaining model shows "a typical power hitter should lose 7.6 RBI over the course of a season if he bats second in the order compared to if he bats fourth," but runs nearly offset it, so R+RBI is fairly flat across the heart of the order. Since your baseline already has lineup-spot features, the marginal open question is narrow: **teammate-quality-as-of** (on-base skill of hitters ahead for RBI; slugging behind for R).

**Most pitcher-mechanics leading indicators are real but either redundant, proprietary, or too noisy at the season-to-date level to clear +0.005.** Arm-angle change proxies release point (which the baseline can capture); within-game velocity decline risks the momentum graveyard; and time-through-order is now understood (Brill, Deshpande & Wyner, JQAS 2023) to be mostly smooth continuous decline — "there is little evidence of strong discontinuity in pitcher performance between times through the order... the start of the third time through the order should not be viewed as a special cutoff point" — which undercuts "TTO as skill" as a clean feature.

## Details — Ranked Candidate Cards

### TIER 1 — Strongest orthogonality + data on hand + historical depth (rank these top)

---

**#1. Pulled-air-ball rate (as-of)**
- **Formula:** `pulled_air_rate = (batted balls with launch angle ≥ ~10° AND adjusted spray angle in pull third) / (all batted balls)`, shrunk to a multi-year prior. Adjusted spray angle flips by handedness so negative = pull. Optionally split "pulled fly/line-drive" per the FanGraphs literature.
- **Data:** Statcast pitch/BBE level, 2015+ (spray angle derivable from hc_x/hc_y or launch_direction). **On hand** (local parquets). No new scraping.
- **Mechanism:** Pulled air contact converts to HR at vastly higher rates (66% of 2022–24 HR from 17.5% of batted balls; .733 vs .353 wOBA), so hitters clustering air contact to the pull side will out-earn their EV/LA profile on the TB/HR portion of FP.
- **Survives the absorber:** xwOBA/barrel%/hard-hit% are direction-blind by construction (per MLB Technology Blog and Tango); this feature is the residual xwOBA cannot see. Distinct from ISO/HR-rate-as-of because it predicts *future* HR conversion via a sticky skill (r² = 62.4% year-over-year on medium-hit flies), not just past HR level.
- **Closest graveyard relative:** "xwOBA-minus-wOBA in-season gap" (closed). **Difference:** that feature used the *realized* in-season gap (noisy, self-fulfilling, small-sample); this uses the *underlying batted-ball direction distribution*, which is far stickier and is a process input, not an outcome residual.
- **Effect-size expectation:** Plausibly clears +0.005 cross-year r for rh3, concentrated in the TB/HR term; sign consistency likely (structural, decade-stable). A "huge" claim would be a red flag — Clemens explicitly calls it "not a huge effect."
- **Model / framing:** rh3, in-season as-of. Best as pull-air × moderate-power interaction.

---

**#2. In-season gmLI-to-date, team-relative (reliever role/opportunity)**
- **Formula:** `gmLI_todate` (average leverage index at game entry, season-to-date) AND a team-relative version: `gmLI_todate − team_bullpen_mean_gmLI`, plus a role-competition count = number of teammates with higher gmLI-to-date, and a contract/salary anchor. Computable from MLB Stats API play-by-play (base/out/inning/score state → LI table) or FanGraphs splits.
- **Data:** MLB Stats API / Retrosheet-style PBP, 2015+ (LI is a deterministic function of game state). **On hand / derivable.** FanGraphs publishes gmLI but date-range splits may need scraping — flag the team-relative construct as light new computation, not new acquisition.
- **Mechanism:** Saves (5 pts) and holds (2 pts) require high-leverage usage; gmLI-to-date is the purest proxy for the role that generates those opportunities, and role is a leading indicator of promotion (RotoWire/THT methodology).
- **Survives the absorber:** Explicitly orthogonal to skill — RotoGraphs: gmLI "has absolutely nothing to do with the pitcher himself." Season-to-date FP for a reliever conflates skill innings with save/hold windfalls; gmLI isolates the opportunity channel that predicts *future* SV+HLD.
- **Closest graveyard relative:** "Reliever leverage lag-year features" (closed). **Difference:** the graveyard verdict is about *cross-year* gmLI (Moore: r = 0.249, weak). In-season gmLI-to-date tracks current role far more tightly (Baumann: team-relative K-BB% correlates with gmLI at r = 0.408) and updates as roles turn over — a fundamentally different, shorter-horizon signal the user has registered as untested.
- **Effect-size expectation:** For rprs2 specifically, plausibly the largest single additive gain in the task because SV/HLD are near-orthogonal to rate skill. Caution: WPA and gmLI are partly circular (WPA is defined using LI) — do not enter both as independent predictors.
- **Model / framing:** rprs2, in-season as-of. Refresh frequently (leverage distribution has flattened over time; roles turn over fast).

---

**#3. Spray-adjusted contact quality (direction-adjusted xwOBAcon / Spray DHH%)**
- **Formula:** Re-weight each BBE's expected value by an empirically estimated spray-angle-bin correction (the "Quantifying the Benefit of Spray Angle to xwOBA" bin approach), or use Connor Kurcon-style Spray DHH% (dynamic hard-hit threshold varying by spray direction). Aggregate to a per-PA rate, shrunk.
- **Data:** Statcast BBE 2015+. **On hand.** Requires building spray-bin lookup (light offline computation).
- **Mechanism:** Credits legitimate pull-side power and discounts "empty" oppo air contact, better predicting sustainable production than direction-blind xwOBA.
- **Survives the absorber:** Same direction-blindness gap as #1 but generalized beyond pull-air to full contact distribution; carries info beyond barrel%/hard-hit%/xwOBA.
- **Closest graveyard relative:** "swing-decision metrics as FP predictors (persistent but non-additive)" and "hard-hit/whiff trailing windows." **Difference:** this is a *direction* re-weighting of contact quality, not a discipline or trailing-window metric; the orthogonal axis (horizontal spray) is absent from every baseline feature.
- **Effect-size expectation:** Likely smaller than #1 (partially collinear with it). Tango's caution — including spray angle "makes xwOBA less *predictive*, not more" — means the naive version can hurt; the additive value is in the *residual/redemption* cases (e.g., Bryan Reynolds-type profiles, whose Spray DHH% jumped from the 33rd to 67th percentile vs standard HardHit%), so frame as a supplementary correction, not a replacement. May not clear +0.005 alone once #1 is in.
- **Model / framing:** rh3, in-season as-of.

---

**#4. Teammate-quality-as-of for R+RBI (lineup-context spillover)**
- **Formula:** For each hitter, a season-to-date weighted index of the on-base skill of hitters batting immediately ahead (RBI channel) and slugging/HR of hitters behind (runs channel), using actual lineup cards; e.g., `RBI_context = mean(OBP/wOBA of prior 2 slots)`, `R_context = mean(ISO of next 3 slots)`.
- **Data:** MLB Stats API lineup + FanGraphs/Statcast rate stats, 2015+. **On hand / light scraping** for daily lineups.
- **Mechanism:** R and RBI are structurally team-dependent; the quality of surrounding hitters sets the ceiling on counting-stat conversion independent of a hitter's own rates.
- **Survives the absorber:** Orthogonal to a hitter's own ISO/xwOBA/BB% AND to his own lineup-spot feature (two hitters in the same slot on different teams have different teammate quality). Season-to-date FP absorbs a hitter's *own* R+RBI level but not the *forward-looking* teammate context that will generate RoS opportunities.
- **Closest graveyard relative:** "opponent-lineup hand-matchup (true null)" and existing lineup-spot features. **Difference:** those are opponent-side or own-slot; this is *own-team surrounding-hitter quality*, a distinct axis the baseline lacks.
- **Effect-size expectation:** Small but plausibly additive for the R+RBI portion of rh3 (which is a large share of hitter FP). Risk: partial absorption by lineup-spot + team-implied-offense cues; may land near +0.005. Sign consistency likely.
- **Model / framing:** rh3, in-season as-of. Interacts with hitter's own power (RBI context matters more for sluggers per Spratt).

---

### TIER 2 — Rule-change exploitables, historically sourced but small/partially absorbed

---

**#5. Bigger-bases SB ecosystem: opportunity-adjusted steal propensity**
- **Formula:** `SB_attempt_rate_todate = attempts / (times on 1B or 2B with next base open)` (takeoff rate), interacted with a team green-light index and opposing catcher/pitcher hold quality on the RoS schedule. Success-probability from Statcast basestealing run value inputs.
- **Data:** MLB Stats API PBP 2015+ (bigger bases 2023+ era for regime). **On hand.**
- **Mechanism:** Post-2023, SB attempts are up (per-game SB attempts rose from 1.4 in 2022 to 1.8 in 2023) and success-rate-driven opportunity compounds ("success breeds opportunity"); takeoff rate is stickier and more predictive of RoS SB (positive FP) than raw SB count.
- **Survives the absorber:** Your baseline has "SB rate" but takeoff rate normalizes by *opportunity* (on-base events) and adds team-intent + RoS matchup — a decomposition the raw SB-rate cannot capture. Post-2023 regime shift means pre-2023 SB rates under-predict current attempts.
- **Closest graveyard relative:** "sprint speed" (closed, marginal). **Difference:** sprint speed is a physical tool; this is *behavioral opportunity* (green light, catcher hold), which post-rule-change matters more than raw speed (2023 research found speed's importance to SB success fell after the base-size change).
- **Effect-size expectation:** Modest additive for the SB term of rh3; the regime-shift angle helps cross-year but the 2023+ window limits clean multi-year testing (flag as partial-FUTURE for the regime interaction). Attempt rate itself testable 2015+.
- **Model / framing:** rh3 (SB term) + volume-adjacent. In-season as-of.

---

**#6. Shift-ban beneficiary: lefty pulled-line-drive / ground-ball hitter (BABIP channel)**
- **Formula:** For LHB, `pulled_GB_LD_rate_todate` and a pre-ban shift-exposure proxy, flagged for the 2023+ regime; expected BABIP uplift on pulled grounders/short liners.
- **Data:** Statcast 2015+. **On hand.**
- **Mechanism:** The shift ban raised lefty BABIP — MLB.com counted "more than 300 additional hits by lefty batters on pulled grounders" in the first half of 2023, and Baseball Prospectus found the BABIP increase was confined to LHB and largest on line drives — boosting the H-driven components (TB, R, RBI).
- **Survives the absorber:** Regime shift means pre-2023 in-play outcomes under-predict post-ban BABIP for this specific profile; the interaction (handedness × pull-GB/LD) is not in the baseline's in-play% or xwOBA.
- **Closest graveyard relative:** "park factors (schedule-weighted, marginal)" and "opponent-lineup hand-matchup." **Difference:** this is an own-batted-ball-profile × rule-regime interaction, not a park or opponent feature.
- **Effect-size expectation:** Small; MLB found "Nearly 90% of hitters are between +4 hits gained and -4 hits lost," so the effect is concentrated in a handful of extreme LHB pull hitters. Likely below +0.005 as a general feature; only worth including as a narrow interaction. FUTURE-flag multi-year (2023+ only).
- **Model / framing:** rh3, in-season as-of.

---

### TIER 3 — Pitcher mechanics/arsenal: real but redundant, noisy, or thin

---

**#7. Arm-angle change / release-point consistency (SP decline & command leading indicator)**
- **Formula:** `arm_angle_delta = arm_angle_todate − prior-year arm_angle`; and within-season release-point RMSE from centroid. Arm angle published 2020+; release point 2015+.
- **Data:** Statcast arm angle **2020+** (Savant leaderboard), release point 2015+. **On hand** for release point; arm angle scrapeable.
- **Mechanism:** Sudden arm-angle drops/rising release-point variance flag mechanical change linked to command loss and injury risk, predicting RoS ERA/IP deterioration.
- **Survives the absorber:** Potentially orthogonal to Stuff+ level and K−BB% if it leads the outcome; captures mechanical change before results move.
- **Closest graveyard relative:** "release-point/pitch-mix-change/entropy" and "days-since-IL-return." **Difference:** arm-angle *level* change is distinct from pitch-mix entropy; but honestly the *change* framing flirts with the momentum/trajectory graveyard.
- **Effect-size expectation:** Low confidence. FanGraphs found arm angle largely proxies release point (which baseline can capture), and injury signal is dominated by existing days-since-IL + volume models. Likely **fails +0.005**; arm angle's 2020+ availability also blocks the 5-of-7 gate. Recommend as monitoring flag, not ranked feature.
- **Model / framing:** rp3 / volume (GS). FUTURE-flag (2020+).

---

**#8. Arsenal complementarity / tunneling (public formulation)**
- **Formula:** Public tunneling constructs — BP Arsenal Metrics (movement/velocity spread, "surprise factor"), or Creally's Tunneling+/Repertoire+, or KEES+ — as an SP feature; or a simpler pairwise release-cluster-tightness × movement-divergence index from Statcast.
- **Data:** Statcast pitch level 2015+ (BP metrics 2023+ formulation). **On hand** for a home-brew; BP/third-party versions require scraping.
- **Mechanism:** Better tunneling/arsenal diversity sustains whiffs and weak contact, supporting RoS K and ERA beyond raw stuff.
- **Survives the absorber:** Claimed orthogonal to Stuff+ (which grades pitches in isolation); KEES+ author claims tunneling-aware model more predictive of future ERA than Stuff+.
- **Closest graveyard relative:** "pitch-mix-change/entropy" and "FanGraphs Stuff+ (level, already in baseline)." **Difference:** tunneling is *inter-pitch geometric relationship*, not single-pitch stuff or mix entropy.
- **Effect-size expectation:** Uncertain; arsenal effects are "not quite as predictive as high-quality stuff" (Creally), and only 3 pitchers scored 110+ on both Tunneling+ and Repertoire+ in 2025 (thin tail). Might clear +0.005 for K portion of rp3 but weak sign-consistency confidence. Medium priority, needs empirical test.
- **Model / framing:** rp3, in-season as-of.

---

**#9. Within-game velocity retention (1st-inning vs late) as SP durability signal**
- **Formula:** `velo_retention = mean_velo_innings_5-6 − mean_velo_inning_1`, season-to-date, fastballs only.
- **Data:** Statcast 2015+. **On hand.**
- **Mechanism:** Hard-throwers who lose velocity within games (Baseball Prospectus' "Ballad of the Fatigued" showed hard-throwers "lost significant velocity and vertical movement as the game went on") fade later and RoS, capping IP and inflating ER late.
- **Survives the absorber:** Possibly orthogonal to average-velocity level and Stuff+ (which use aggregate velo).
- **Closest graveyard relative:** "momentum/recency/trailing-window anything" and "trajectory/decline slopes for SP." **Difference:** this is a *within-game* physiological pattern averaged across the season, not a game-to-game trailing window — but the distinction is thin and the user's graveyard is aggressive here.
- **Effect-size expectation:** Low; high risk of being classified as a decline-slope relative. Likely fails the gate. Recommend deprioritize.
- **Model / framing:** rp3 / volume.

---

### TIER 4 — FUTURE-flagged (bat tracking 2024+, swing path 2025+): same-year usage only, cannot clear 5-of-7 until ~2028

---

**#10. Squared-up rate per swing (bat-to-ball skill)**
- **Formula:** squared-up contacts / swings (or / bat-contacts), same-year.
- **Data:** Statcast bat tracking **2024+**. On hand for 2024–26.
- **Mechanism:** Measures contact centering; per-swing version correlates negatively with K rate (−0.669, Adam Salorio).
- **Survives the absorber:** Weak case — FanGraphs (Mike Podhorzer) found the new bat-tracking metrics "won't help us project HR/FB rate (or strikeout rate or BABIP) any better than we're already able to with existing metrics," and Clemens found "neither raw swing speed nor squared-up rate do a great job of predicting overall production." Likely absorbed by existing contact%/whiff%.
- **Closest graveyard relative:** bat SPEED (validated as the *only* additive process metric) and "swing-decision metrics." **Difference:** squared-up-per-swing is bat-to-ball centering, adjacent to but distinct from bat speed; the user explicitly opened adjacent bat-tracking constructs if same-year framed.
- **Effect-size expectation:** Low-to-medium; probably absorbed. **FUTURE-flag** — cannot clear 5-of-7-year gate until ~2029.
- **Model / framing:** rh3, same-year only.

---

**#11. Attack-angle / swing-path match to pitch-height distribution**
- **Formula:** Per-hitter attack angle vs the vertical-approach-angle distribution of pitches faced; "in-plane" match rate, same-year.
- **Data:** Statcast swing path/attack angle **2025+** (released May 2025). On hand for 2025–26 only.
- **Mechanism:** Matching bat plane to pitch plane increases contact and productive air contact; MLB pegs the productive attack-angle band at roughly 5–20°, matching where pitches enter the zone (−5° to −20° downslope).
- **Survives the absorber:** Plausibly orthogonal to contact% if it captures *where* in the zone contact quality concentrates; ties to #1 (attack angle relates to launch/pull tendencies, though the hitter-level attack-angle→launch-angle relationship is only r² = 0.23 in 2025).
- **Closest graveyard relative:** bat speed (validated) and swing-decision metrics. **Difference:** swing *geometry*/plane-match, not speed or take decisions.
- **Effect-size expectation:** Unknown; only ~1.3 seasons of data. **Hard FUTURE-flag** — cannot test cross-year until ~2028+. Same-year experiment only.
- **Model / framing:** rh3, same-year only.

---

**#12. Swing-length consistency / swing-acceleration**
- **Formula:** SD of swing length per hitter; and swing acceleration (bat speed / swing length proxy), same-year.
- **Data:** Statcast bat tracking **2024+**.
- **Mechanism:** Creally reports swing acceleration is "more predictive of offensive output than swing length or tilt" after raw bat speed; consistency may reflect adjustability.
- **Survives the absorber:** Marginal; likely collinear with the already-validated bat speed.
- **Closest graveyard relative:** bat speed (validated additive). **Difference:** acceleration/consistency are second-order swing constructs, explicitly opened by the user if same-year.
- **Effect-size expectation:** Low; probably absorbed by bat speed. **FUTURE-flag.**
- **Model / framing:** rh3, same-year only.

---

**#13. Triple-A stat translation for callups (MLB equivalency, hitters)**
- **Formula:** For newly promoted hitters, a season-to-date Triple-A wOBA/ISO/K%/BB% translated to MLB via level-equivalency coefficients, blended with MiLB priors and age-vs-level, decaying as MLB PA accrue.
- **Data:** MiLB stats (MLB Stats API) + Triple-A Statcast (available for Triple-A since 2023). **Light new acquisition** — the user's current MiLB priors are AA/AAA counting stats only, so Triple-A batted-ball/rate translation is additive.
- **Mechanism:** For the callup population, season-to-date MLB FP is a tiny, high-variance sample; a Triple-A translation carries real skill information the thin MLB sample cannot.
- **Survives the absorber:** For low-MLB-PA players the "cumulative FP level" absorber is weak by definition (little data to absorb), so an as-of MiLB translation is one of the few features that beats the shrunken prior for this subgroup.
- **Closest graveyard relative:** "minor-league priors" (already partially in baseline via AA/AAA counting stats). **Difference:** this adds Triple-A *rate/quality* translation and age-vs-level, not just counting stats, and is applied dynamically in-season to fresh callups.
- **Effect-size expectation:** Potentially strong *within the callup subgroup* but near-zero on the full population (few players qualify); best implemented as a subgroup model / interaction, not a global feature. Cross-year testable 2015+ for counting-stat translation; Triple-A Statcast quality only 2023+ (partial-FUTURE).
- **Model / framing:** rh3 + volume (PA), in-season as-of, callup subgroup.

---

### TIER 5 — Explicitly evaluated and NOT recommended (documented dead-ends adjacent to open areas)

- **Time-through-order penalty as a pitcher skill:** Brill, Deshpande & Wyner (JQAS 2023) show the TTOP is mostly *smooth continuous decline*, not a sharp between-TTO skill discontinuity, after adjusting for batter/pitcher quality — "the start of the third time through the order should not be viewed as a special cutoff point." A "TTO-resistance skill" feature has weak theoretical footing and overlaps existing Stuff+/K−BB. **Drop.**
- **Team OAA-as-of behind a pitcher (for H/ER terms):** Real but small — team OAA/UZR explains only ~13–23% of ERA-estimator-vs-ERA gaps (Pitcher List), and defense-behind-pitcher OAA is itself noisy year-to-year and largely luck at the pitcher level (the Nola/Wheeler divergence within one team is unexplained). Modest orthogonality to FIP-based skill, but likely below +0.005 and partially in park/BABIP noise. **Borderline; low priority.** If tested, frame as team infield OAA-as-of for GB-heavy SPs only.
- **Catcher framing:** already a validated display tag (graveyard).
- **Sprint speed, EV90, xwOBA-minus-wOBA gap:** closed.

## Recommendations

1. **Build and test #1 (pulled-air-ball rate) and #2 (in-season gmLI-to-date) first.** Both use data on hand, have decade-plus depth (except gmLI's regime nuance), the strongest orthogonality arguments, and target the two model families (rh3 HR/TB term; rprs2 SV/HLD term) where the absorber is weakest. Threshold to promote to production: +0.005 cross-year r vs the full baseline, 5/7-year sign consistency, positive 2024–25 holdout.
2. **Test #1 as an interaction** (pulled-air × moderate-power, using a "best speed"/EV band) rather than a main effect — the literature is explicit that the benefit vanishes for elite-power hitters and concentrates in medium power. If the main effect adds ~0, the interaction likely still clears.
3. **For #2, engineer the team-relative version** (gmLI-to-date minus team-bullpen mean; count of teammates with higher gmLI) — research shows relative-to-teammates skill correlates with role better (team-relative K−BB% vs gmLI r = 0.408) than raw gmLI, and add a contract/salary anchor (Moore: r = 0.36 to gmLI, the strongest single role predictor). Do **not** enter WPA and gmLI as independent predictors (circular — WPA is defined using LI).
4. **Test #3 and #4 only after #1/#2**, as they are partially collinear (#3 with #1) or partially absorbed (#4 by lineup-spot). Keep them if they add ≥ +0.005 incrementally; drop otherwise.
5. **Treat all Tier 4 (bat tracking) ideas as same-year-only experiments**, reported with a FUTURE tag; do not let them compete for top ranking until ~2028–2029 provides the multi-year depth to clear the sign-consistency gate. Prioritize squared-up-per-swing and attack-angle-plane-match for *descriptive* validation now so they're ready when depth arrives. Build #13 (Triple-A translation) as a callup subgroup model, not a global feature.
6. **Deprioritize Tier 3 pitcher-mechanics ideas** (#7–#9): arm-angle change proxies release point the baseline captures, within-game velo decline risks the momentum graveyard, and injury signal is dominated by days-since-IL. Keep arm-angle drop as a *monitoring flag* outside the regression.
7. **Benchmark that would change the ranking:** if #1's additive r comes in below +0.003 on the 2024–25 holdout, demote it and elevate #3 (spray-adjusted contact quality) as the primary direction feature; if in-season gmLI-to-date shows <0.10 incremental R² for RoS SV+HLD, fall back to contract/role-tag features and the RotoWire closer-grid depth chart as a categorical input.

## Caveats

- **Direction features are HR/TB levers, not average/OBP levers.** Framing #1 or #3 as general production boosters will disappoint; the additive signal is narrow (power component) and modest by the original authors' own admission ("not a huge effect"; adding spray to xwOBA can *reduce* predictiveness per Tango). Guard against overfitting to Isaac Paredes-type outliers (his 2022–24 wOBAcon minus xwOBAcon was +0.056 — an extreme, not a median case).
- **The reliever gmLI signal decays and needs frequent re-estimation.** Leverage has become more distributed across bullpens over time, roles turn over fast in-season, and cross-year gmLI is genuinely weak (r = 0.249) — the value is strictly in the *short-horizon, in-season, team-relative* framing. Over-weighting it early in the season (small appearance samples) will add noise; multiple sources warn it is "too early" to act on gmLI leaderboards at ~10% of the season.
- **Rule-change features (#5, #6) have short clean windows** (2023+), so multi-year sign-consistency testing is impossible before ~2027–2028; treat regime-interaction terms as partial-FUTURE. Note also that SB success rates have declined since 2023 (defenses adapting: catcher pop times improved, throws to the first-base side of the bag), so the 2023 attempt-rate spike is itself non-stationary.
- **Bat-tracking timing is measured against an evolving instrument.** Swing timing biases bat speed/swing length (arXiv 2507.01238 filters to squared-up contact on primary fastballs to mitigate), MLB's 2023 data is "testing-only," and 2025 added new swing-path fields — any same-year feature must be built defensively against measurement drift.
- **Several ideas are partially collinear with each other** (#1/#3 both direction; #5 with the baseline SB rate; #4 with lineup-spot), so incremental testing order matters — additive gains are not simply summable, and the +0.005 gate must be applied *conditional on features already in* the model.
- **No published study directly tests in-season gmLI-to-date → RoS SV+HLD** (confirmed via targeted research — it appears to be an open/unpublished question; FanGraphs date-range gmLI splits make the original analysis feasible). The expectation that #2 clears the gate is an informed inference from adjacent within-season correlations, not a measured result — it should be validated, not assumed.