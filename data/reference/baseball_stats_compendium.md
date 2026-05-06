# Baseball Statistics: Graduate-Level Technical Compendium for Predictive Modeling

**Purpose.** This document is a graduate-level literature review and engineering reference for teams building statistical baseball prediction models. It covers traditional, rate, sabermetric, Statcast-era, defensive, and aggregate value metrics; reviews the predictive-modeling literature; compiles documented correlation values; and synthesizes a model-builder's actionable framework.

**Structure.** Sections 1–9 are domain references; Section 10 synthesizes a recommended modeling framework; the document closes with a Master Stat Hierarchy table.

**Source quality conventions.** "Strong evidence" = multiple independent peer-reviewed/replicated studies. "Moderate evidence" = single major study or well-replicated blog/industry analysis. "Weak/contested" = single source or known disagreement. "Proprietary" = model internals not fully public; "Replicable" = formula+data fully open. All correlations reported as Pearson r unless flagged r².

---

# SECTION 1 — TRADITIONAL / COUNTING STATS

**TL;DR.** The traditional ledger is overwhelmingly Henry Chadwick's invention (1859–1880s), augmented by ER/ERA (1912–13), RBI as official (1920), Save (1969 via Holtzman 1959), and CS/SF/GIDP at various dates. These stats remain the canonical raw-data layer that feeds every modern derived metric, but for player evaluation they are mostly **superseded** by linear-weight metrics (wOBA, wRC+, FIP, WAR). Three structural problems recur: (1) RBI and pitcher W/L are dominated by team context; (2) Errors/FPCT punish range; (3) ERA conflates pitching with defense, sequencing, and BABIP luck.

## 1A. Hitting

**AVG = H/AB.** Chadwick, 1860s. Treats all hits equal, ignores BB/HBP, BABIP-luck dominated. Team AVG → R/G r ≈ 0.81 (Mains 2016, FanGraphs Community, 1914–2015 sample). Superseded by wOBA/wRC+.

**H, AB.** Chadwick 1859 box score. Pure counts; AB excludes BB/HBP/SF/SH/CI. PA is the analytically preferred denominator.

**R (Runs Scored).** Charter stat (1845 Knickerbocker rules); tabulated 1859. Heavily lineup-dependent; trivially high at team level (winning = scoring more than opponent), low isolation at player level. Superseded by wRC, BsR.

**RBI.** Tracked unofficially by Ernie Lanigan from 1907; **official 1920**. Concept attributed to Chadwick (1879). Highly lineup-dependent (~95% of MLB runs become RBI annually). Branch Rickey (1954, *Life*): RBI "depended on managerial control, batting order, park dimensions, and teammates." Superseded by RE24, wRAA, wRC+.

**HR, 2B, 3B.** All Chadwick-era counts. HR park-spread ~30%; team HR → R/G r ≈ 0.67 (2010s). Triples are partly speed/park noise. Inputs to TB/SLG/ISO/wOBA. HR rate stabilizes at ~170 PA (Carleton).

**SB / CS.** SB official 1886; CS officially tracked from 1920 NL/1914 AL. Run values asymmetric: SB ≈ +0.17 R, CS ≈ −0.39 R; **break-even success ≈ 70–75%**. Below break-even, attempts destroy value. Superseded by wSB, BsR.

**BB.** Tabulated by Chadwick; 4-ball rule fixed 1889. Strong predictive value; key OBP/wOBA input. BB% stabilizes ~120 PA.

**SO/K (batter).** Chadwick standardized "K" notation 1859. Contemporary research shows 1 K ≈ 1 weak GB out in expected run value; K-aversion is overrated. K% stabilizes at ~60 PA — fastest of any offensive stat.

**HBP.** Rule introduced 1887 NL. Skill component exists (plate-crowders); included in OBP/wOBA.

**SF / SH.** SF rule introduced 1908, permanent 1954; SH formalized 1894. SH is a **negative-EV play** in modern run environments; largely abandoned in analytics-era strategy.

**GIDP.** Officially tracked AL 1933 / NL 1939. Opportunity-driven (need man on 1B); partly skill (contact + GB%). Superseded by wGDP.

**TB = 1B + 2·2B + 3·3B + 4·HR.** Chadwick. Numerator of SLG; ignores BB/HBP/baserunning.

**PA = AB + BB + HBP + SF + SH + CI.** Modern era; superior denominator to AB. Modern rate stats (K%, BB%, wOBA) all use PA.

## 1B. Pitching

**W/L.** MLB Rule 9.17. Heavily team-context dependent (run support, bullpen, defense). Y/Y individual repeatability poor. **Strongly superseded** by FIP, WAR, RA9-WAR.

**ERA = (ER × 9)/IP.** Concept from Chadwick; **adopted NL 1912 ("Heydler's stat"), AL 1913**. Defense-dependent, sequencing-dependent, ER subjective, inherited runners not charged. Y/Y r ≈ 0.36–0.38 for starters. Superseded by FIP/xFIP/SIERA/DRA/ERA−.

**IP.** Outs ÷ 3 (with awkward .1 = ⅓ convention). BF (PA-equivalent) is theoretically preferable for rate denominators.

**SO (pitcher).** Stabilizes ~70 BF — fastest. Most predictive single skill component.

**BB (pitcher).** Stabilizes ~170 BF. Second-most predictive component.

**H (allowed).** Defense/BABIP contaminated. McCracken DIPS (2001): pitcher BABIP Y/Y r ≈ 0.15–0.25.

**HR (allowed).** Park-dependent; HR/FB rate has low pitcher repeatability. Stabilization ~1320 BF (very slow).

**CG / SHO.** Standard since 1870s; both essentially obsolete due to bullpen specialization. 2018: no MLB pitcher exceeded 1 SHO.

**SV.** **Created by Jerome Holtzman (Chicago Sun-Times, 1959)** after Roy Face's 18-1 record (10 blown leads); adopted by *The Sporting News* 1960; **official MLB 1969** — first new official stat since RBI 1920. MLB Rule 9.19 (3 conditions). Highly opportunity-dependent; superseded by WPA, gmLI, SD/MD, RE24.

**BS.** Unofficial; sources disagree on definition.

**HLD.** Invented 1986 by John Dewan & Mike O'Donnell (STATS Inc.); not official. Multiple definitional variants — pick one provider and stay consistent.

**R / ER.** Chadwick conceived earned/unearned distinction in 1860s. ER is subjective (scorer reconstructs inning). RA9 (per-9 R, all runs) is preferred in modern analysis (used by bWAR for pitchers).

**WP, BK, IBB.** WP: subjective scorer judgment; rare. BK: rule refined 1899, 1988; rare. IBB: officially tracked from 1955; reflects opposing manager's choice.

## 1C. Fielding

**E.** Chadwick 1859 box score. Severely limited: subjective; ignores range ("must do something right to get an error"); rare event; ignores positioning. Superseded by UZR/DRS/OAA/FRV.

**PO / A.** Chadwick. Position-dependent and not directly cross-comparable.

**FPCT = (PO+A)/(PO+A+E).** Biased toward low-range fielders. Modern MLB FPCT > .980; differentiation poor. *Moneyball*: "the easiest way not to make an error is to be too slow to reach the ball." FanGraphs explicitly recommends abandoning for evaluation.

**TC = PO+A+E.** Denominator of FPCT and Range Factor.

**DP.** Heavily opportunity-dependent; conflates range + pivot/throw. Superseded by DPR (UZR component).

---

# SECTION 2 — RATE STATS & RATIO METRICS

**TL;DR.** Among simple rate stats, OPS (r ≈ 0.94 with team R/G), OBP (~0.89), SLG (~0.87) explain most team-run variance; AVG trails (~0.81); BA/RISP is essentially noise as a *predictive* metric. For pitchers, K%, BB%, GB% are most stable/predictive; HR/FB and BABIP-allowed are largely noise over single seasons (DIPS theory).

## 2A. Hitting

**OBP = (H+BB+HBP)/(AB+BB+HBP+SF).** Allan Roth/Branch Rickey, late 1940s; published *Life* 1954; **official MLB stat 1984**. Team OBP → R/G r ≈ 0.89. 1 point of OBP ≈ 1.8× run value of 1 point of SLG.

**SLG = TB/AB.** Term in print 1914; popularized by Roth; official AL 1946. Team SLG → R/G r ≈ 0.87. Weights 1/2/3/4 are not exactly right (true wOBA weights ≈ 0.89/1.27/1.62/2.10).

**OPS = OBP + SLG.** Pete Palmer, late 1970s; *Hidden Game* 1984. Team OPS → R/G r ≈ 0.94 (some samples 0.95–0.96). Mathematically inelegant (different denominators, equal weighting). Superseded by wOBA and wRC+.

**BA/RISP.** Year-to-year correlation low; "clutch ability" largely fails to repeat (Tango et al., *The Book*, ch. 3). **Largely noise as a predictive metric** — descriptive only.

**K%, BB%.** PA-denominated. K% ~60 PA, BB% ~120 PA stabilization. Both very high Y/Y r (~0.75+ for K%). Strong skill signals.

**K/BB (hitter).** Compresses two distinct skills; unstable as BB→0. K-BB% (difference) preferred where used.

**HR/FB% (hitter).** Hitters exert more control than pitchers; faster stabilization. Park-dependent.

**GB% / FB% / LD% / IFFB%.** BIS-tracked from 2002. League avg GB ~44%, FB ~36%, LD ~20%, IFFB% ~10% of FB. Y/Y r: GB ~0.74, FB ~0.69, LD ~0.37 (largely noise), IFFB ~0.64. **LD% should not be used predictively without heavy regression.** BIS classifications differ from Statcast LA-based versions.

## 2B. Pitching

**WHIP = (BB+H)/IP.** Coined Daniel Okrent 1979 (Rotisserie). Treats walks/hits equally (wrong); ignores HR; BABIP-contaminated. Y/Y r 0.40–0.55 for SP. Superseded by FIP/SIERA.

**H/9.** Defense/BABIP contaminated; per-BIP rate (BABIP) more diagnostic.

**HR/9.** Park- and HR/FB-luck dependent; Y/Y r ≈ 0.30. xFIP normalizes.

**BB/9.** IP-denominator inferior to PA-denominator. FanGraphs prefers BB%. Strong skill signal; Y/Y r ~0.6+.

**K/9.** Same denominator issue. K% preferred. Highest Y/Y r (~0.7+) of any pitcher rate stat.

**K/BB (pitcher).** Strong; combines two most-controlled skills. **K-BB% (difference) is the highest-correlation single rate stat with run prevention** (r toward ERA typically -0.6+); preferred over ratio form.

## 2C. Stabilization Reference Table (Carleton, split-half r=0.7)

| Stat | Stabilization |
|---|---|
| K% (hitter) | ~60 PA |
| BB% (hitter) | ~120 PA |
| HBP% | ~240 PA |
| HR rate (hitter) | ~170 PA |
| ISO | ~160 PA |
| OBP | ~460 PA |
| SLG | ~320 AB |
| AVG | ~910 AB |
| BABIP (hitter) | ~820 BIP |
| K% (pitcher) | ~70 BF |
| BB% (pitcher) | ~170 BF |
| GB%/FB% | ~70 BIP |
| HR/FB% (pitcher) | ~1300+ FB |
| BABIP (pitcher) | ~2000+ BIP |
| EV/LA/Barrel% | ~50 BBE (~18 games) |

**Engineering implication.** Below stabilization, regress samples toward population means proportionally. McCracken DIPS finding (pitcher BABIP Y/Y r ~0.15–0.25) is the single most-cited result.

---

# SECTION 3 — SABERMETRIC / ADVANCED OFFENSIVE METRICS

**TL;DR.** Modern hitter evaluation hierarchy: **linear-weights core** (wOBA, wRC+, OPS+) → **expected/Statcast** (xwOBA, Barrel%, EV, LA, Sprint Speed) → **modeled** (DRC+, xBABIP). Team wOBA → team R/PA r ≈ 0.95–0.96. **DRC+** (Judge 2018) achieves the highest Y/Y reliability of any public batting metric (r ≈ 0.73 vs ~0.35 for wRC+/wOBA). Most expected metrics are descriptive, not strongly predictive: xwOBA → next-yr wOBA r² ≈ 0.218 vs raw wOBA r² ≈ 0.191 (small but real edge).

## wOBA (Tom Tango et al., *The Book* 2006)
Linear-weight hitter rate; events weighted by RE24-derived run values, rescaled so league wOBA = league non-IBB OBP.
**Example 2013 weights:** `wOBA = (0.690·uBB + 0.722·HBP + 0.888·1B + 1.271·2B + 1.616·3B + 2.101·HR) / (AB + BB − IBB + SF + HBP)`
**Correlations:** Team wOBA → R/G r ≈ 0.95 (r² ≈ 0.92, Wolfe Hacks). Y/Y r ≈ 0.44 individuals. Replicable via FanGraphs Guts! constants.
**Weaknesses:** No park/league adjustment; HBP weight arguably too high; annual recalibration.

## wRC+
Park- and league-adjusted wOBA-derived index; 100 = league average. Inherits wOBA correlations. Y/Y individual r ≈ 0.50–0.60. Does not include baserunning. Replicable.

## OPS+
`OPS+ = 100·(OBP/lgOBP + SLG/lgSLG − 1)`, park-adjusted. Equal weights wrong (true ≈1.8:1 OBP:SLG). Y/Y r ≈ 0.55–0.65. Replicable.

## RC / RC/27 (Bill James)
**Basic:** `RC = (H+BB)·TB/(AB+BB)`. **Tech-1:** A·B/C structure with detailed components. Multiplicative form **overestimates extreme hitters** (interaction with own OBP). Team r² ≈ 0.85–0.90. Largely superseded by wRC and BaseRuns.

## ISO (Branch Rickey/Allan Roth, *Life* 1954; named by Bill James)
`ISO = SLG − AVG`. Strips singles to isolate power. Stabilizes ~160 PA. Treats 3B as 2× 2B (but 3B is speed-driven); not park-adjusted.

## BABIP (McCracken 1999/2001)
`BABIP = (H − HR)/(AB − K − HR + SF)`. Pitcher Y/Y r ≈ 0.15–0.25 (the McCracken finding); hitter Y/Y r ≈ 0.40–0.50. League ≈ .295–.300. Conflates skill, defense, park, luck.

## xBABIP
Multiple iterations (Dutton 2008, Podhorzer 2014, Zimmerman 2015, Statcast EV/LA-based versions). Achieves r ≈ 0.6–0.7 with same-season BABIP; year-over-year predictive lift only marginal over prior BABIP.

## Spd (Bill James, late 1980s)
4-component composite (SB%, attempt frequency, 3B rate, R%); 4.5 = average. Largely **superseded by Statcast Sprint Speed**.

## BsR (FanGraphs)
`BsR = wSB + UBR + wGDP`; runs above average; typical ±15 R/season. Multi-year averaging recommended. UBR depends on **proprietary BIS video data** (2002+).

## wSB (Tango/FanGraphs)
`wSB = SB·runSB + CS·runCS − lgwSB·(1B+BB+HBP−IBB)` with runSB ≈ +0.2, runCS ≈ −0.4. Replicable.

## UBR (Lichtman, ~2009)
Linear-weights for non-SB baserunning advancement. **Proprietary BIS inputs**, 2002+ only.

## EqA / TAv (Clay Davenport, BP, 1996; renamed 2010)
`RAW = (H+TB+1.5(BB+HBP)+SB+SH+SF)/(AB+BB+HBP+SH+SF+CS+SB/3)`; .260 = avg. Davenport Translations applied across leagues. Replaced by DRC+ at BP in Dec 2018.

## DRC+ (Judge, BP, Dec 2018)
**Mixed-effects/Bayesian model** crediting "deserved" hitter contribution by partialing out park, catcher, umpire, defense, opponent. Not a closed-form formula. Output scaled like wRC+.
**Reliability (Judge 2018, team-switchers):** DRC+ r ≈ 0.73 vs wRC+/OPS+/wOBA all ≈ 0.35; predictive r ≈ 0.50 vs ~0.37. Accounts for ~3× more between-batter variance than wRC+.
**Caveat (Hareeb's Hangout):** for team-switching position players, DRC+ MAE projecting next-year wOBA was 34.2 points — slightly worse than projecting everyone to league average (33.1). Reliability ≠ absolute predictive validity.
**Proprietary; values change retroactively when model updates.**

## xwOBA / xBA / xSLG / xOBP (Statcast, 2017+)
Each batted ball assigned probability distribution over (out, 1B, 2B, 3B, HR) based on EV+LA (and sprint speed for weak grounders); aggregated with actual K/BB/HBP. 
**Predictive lift:** xwOBA → next-yr wOBA r² ≈ 0.218 vs wOBA → wOBA r² ≈ 0.191 (Dynasty Dugout 9-yr study). xBABIP/xBACON do NOT outperform raw counterparts. **Descriptive >> predictive**; misses spray-angle/pull effects in baseline form.

## Hard Hit% / Barrel% / Sweet Spot% (Statcast)
- **Hard Hit% = % BBE EV ≥ 95 mph.** 2023: HH wOBA .625 vs <95 mph .207.
- **Barrel% = BBE producing min .500 BA & 1.500 SLG.** Operationally: EV ≥ 98 mph, LA 26–30° at 98 mph, expanding ~2–3°/mph above; at ≥116 mph any LA 8–50°. 2023 barrels: .742 BA, 2.493 SLG, 1.291 wOBA. Brls/BBE r ≈ 0.66–0.76 with HR/FB.
- **Sweet Spot% = % BBE LA 8–32°.** Less rigorous than barrel; ignores EV.

## Exit Velocity / Launch Angle
EV stabilizes ~50 BBE (Y/Y r ≈ 0.70–0.75). **EV90** (90th-percentile EV) and "Best Speed" (Tango's avg of top 50%) outperform mean EV for predicting future ISO/HR. 2020 Trackman→Hawkeye transition introduced minor systemic shift.

## Sprint Speed (Statcast 2017+)
Ft/sec over fastest 1-second window; avg of top 2/3 of qualified runs. League avg ≈ 27 ft/s; Bolt = ≥30. **Highly stable Y/Y (r > 0.85)**; ages slowly (~0.15–0.20 ft/s/yr post-30).

## OAA (offensive sibling — baserunning Run Value)
Statcast: SB events (+0.2/−0.45 base values) + extra-base advancement vs expectation. Correlates with FanGraphs UBR+wSB.

## Batted Ball Distance
Statcast 2015+. Adjusted for park atmospheric carry. Max distance more stable than aDST.

## Pull% / Cent% / Oppo%
BIS 2002+; or Statcast horizontal angle. Pull = LF/RF for RHB/LHB. Pulled FB (LA 20–35°) far higher EV/distance than oppo (~92.4 vs 86.2 mph; 343 vs 290 ft for RHB). FB-Pull% specifically used for power projection.

---

# SECTION 4 — SABERMETRIC / ADVANCED PITCHING METRICS

**TL;DR.** **DIPS theory (McCracken 2001)** is the foundation. Predictive ranking for next-year ERA: **Pitching+ ≥ DRA/cFIP ≥ SIERA ≈ K-BB% > xFIP > xERA ≈ FIP > ERA**. Y/Y autocorrelations (qualified SP): ERA ~0.36–0.38, FIP ~0.55, xFIP ~0.56, SIERA ~0.56–0.58, K-BB% ~0.65–0.70, Stuff+ ~0.70–0.80. Stuff+ stabilizes in **~80 pitches** — fastest of any public pitching metric.

## FIP (McCracken 2001 / Tango)
`FIP = (13·HR + 3·(BB+HBP) − 2·K)/IP + cFIP` where cFIP ≈ 3.10–3.20 calibrates to league ERA. Same-yr ERA r² ≈ 0.61 (best public descriptive). Next-yr ERA r² ≈ 0.14. Y/Y r ≈ 0.55. Treats all HR as 100% pitcher fault (HR/FB Y/Y noisy).

## xFIP (Studeman, ~2006)
Replaces actual HR with `FB × lgHR/FB`. Y/Y r ≈ 0.56. Next-yr ERA r² ≈ 0.18–0.20. Penalizes fly-ball pitchers in HR-suppressing parks; misses HR/FB suppressors (Hendricks, Kershaw).

## SIERA (Swartz & Seidman, BP 2010)
Regression on K%, BB%, GB-FB-PU%, with squared and interaction terms. Embodies skill interactions (each K more valuable for low-K pitchers). Next-yr ERA r² ≈ **0.204** (best of FIP/xFIP/SIERA/xERA per Pitcher List 2015–19). Complex, era-dependent fit.

## tERA / tRA (MacAree & Carruth, ~2008)
Linear weights on K, BB, HBP, HR, GB/FB/LD/PU. Heavy reliance on noisy LD%; largely superseded by SIERA.

## kwERA
`kwERA = 5.40 − 12·((K−BB)/PA)`. Tango popularized. Predicts next-yr ERA r² ≈ 0.21 — competitive with SIERA. Ignores HR, defense, park.

## DRA (Judge/Pavlidis/Turkenkopf, BP 2015+)
**Mixed-effects/Bayesian model** controlling for park, weather, catcher, umpire, opponent batter, run differential. **Same-yr RA9 r² ≈ 0.72 (r ≈ 0.852) — best descriptive.** Predictively marginal advantage over FIP at all sample sizes; cFIP is BP's recommended predictor. **Semi-proprietary**; values shift retroactively with model updates.

## pFIP / FIPR9 / pFIPR9
FanGraphs WAR engine FIP variants with infield-fly inclusion, RA9 scale shift, and park adjustment.

## CSW% (Pollack/Fast, Pitcher List 2018–19)
`(Called Strikes + Whiffs)/Total Pitches`. Lg avg ≈ 27–28%; elite >30%. Stabilizes ~700 pitches. Strong with K% (r² ≈ 0.6+); **weak with ERA (r² ≈ 0.25)**. Strikeout-process metric, not ERA estimator.

## SwStr%
`Swinging Strikes/Total Pitches`. Y/Y r ≈ 0.70+. Strong K%-correlate (~0.85+).

## Plate Discipline (Zone%, O-Swing%, Z-Swing%, O-Contact%, Z-Contact%)
PITCHf/x/Statcast and BIS sources (don't mix). Zone% lg avg ~48–50%; O-Swing% ~30–32%; Z-Swing% ~65–68%; O-Contact% ~60–65%; Z-Contact% ~85–88%. All highly sticky Y/Y (r ≈ 0.55–0.70). O-Swing% and Z-Contact% are top non-result K%-predictors.

## LOB% (FanGraphs)
`LOB% = (H+BB+HBP−R)/(H+BB+HBP−1.4·HR)`. Lg avg ~70–73%. **Regression flag** (LOB% > 80% likely to fall, < 65% to rise). Caveat: high-K pitchers sustain higher true-talent LOB% (Kershaw ~79%).

## HR/FB% (pitcher)
Y/Y r ≈ 0.20–0.30. Park, era, ball construction dominate signal. Some persistence at extremes.

## BABIP (pitcher)
Y/Y r ≈ 0.10–0.20 (McCracken DIPS). Modern Statcast contact-quality metrics are more granular replacements.

## xERA (Statcast)
xwOBA-against transformed to ERA scale; Tango approximation `xERA ≈ xwOBA·27 − 4.3`. Same-yr ERA r² ≈ 0.55–0.60; next-yr r² ≈ 0.14. Statcast itself notes: "xERA is not necessarily predictive."

## Stuff+ / Location+ / Pitching+ (Sarris & Bay, FanGraphs/The Athletic, 2021+)
**XGBoost models** on physical kinematics (velocity, IVB, HB, spin, release, extension, **velocity/movement differentials from primary FB**) for Stuff+; location given count/zone/handedness for Location+; combined for Pitching+. Mean=100, σ ≈ 10.
**Stuff+ stabilizes ~80 pitches; Location+ ~400.** Y/Y r ≈ 0.70–0.80.
**Pitching+ predicts next-year reliever ERA better than every public projection system before the season starts**; matches starter projections. **Semi-proprietary** weights; recalibrated periodically.
**Companion: PitchingBot (Cameron Grove)** — independent XGBoost on 20-80 scouting scale.

## Movement: HB, IVB, VAA
- **HB**: lateral break (FB ~7–8 in arm-side).
- **IVB**: vertical Magnus (FB ~14–16 in; elite "ride" ≥18 in).
- **VAA**: angle of pitch trajectory at plate. League-avg 4-seam ≈ −5.3° to −5.6°; elite flat ≤ −4.5°; sinker ≤ −6°. Determined by release height, extension, IVB, velocity, plate location. Must be evaluated relative to release height.

## Velocity, Spin Rate, Spin Axis, Active Spin, Extension, Release Point
All highly stable Y/Y (velocity r > 0.75, spin rate r ≈ 0.85+, **spin rate Y/Y r² = 0.816 unrestricted, 0.851 min 100 pitches** per Sarris). Each +1 ft extension ≈ +1 mph perceived velocity. Sticky-stuff enforcement (June 2021) caused league-wide spin drop.

## Tunneling (Long, Judge, Pavlidis, BP 2017)
Tunnel point = ~23.8 ft (~167 ms before contact). Components: Release Differential, Tunnel/PreMax Differential, Plate Differential, Break Differential, Flight Time Differential. Derived: Break:Tunnel Ratio, Plate:PreMax Ratio. Descriptively rich; **marginal predictive lift over Stuff+ is contested**. Semi-proprietary; 2018 update changed tunnel-point timing.

## RE24 (*The Book* 2007; Lindsey 1963 origin)
`RE24 = RE_after − RE_before + R_scored on play`. 24 base-out states. Context-dependent (sequencing-laden); useful for reliever value with inherited runners. Not predictive.

## WPA (Mills brothers 1970 conceptual; modern at FanGraphs/B-R)
`WPA = WE_after − WE_before`. Leverage-weighted; closers accumulate fast. Use WPA/LI for context-neutral version. **Not a talent measure.**

### Predictive Validity Summary

| Metric | Y/Y r | Same-yr ERA r² | Next-yr ERA r² |
|---|---|---|---|
| ERA | 0.36–0.38 | 1.00 | 0.08 |
| FIP | 0.55 | **0.61** | 0.14 |
| xFIP | 0.56 | 0.13 | 0.18–0.20 |
| SIERA | 0.56–0.58 | 0.13 | **0.20** |
| xERA | ~0.50 | 0.55 | 0.14 |
| DRA | High (best reliability) | **0.72** | Marginal > FIP |
| K-BB% | 0.65–0.70 | 0.40 | **0.21** |
| CSW% | High | 0.25 vs ERA | 0.25 vs ERA |
| Stuff+/Pitching+ | 0.70–0.80 | varies | **Best public** |

---

# SECTION 5 — FIELDING & DEFENSIVE METRICS

**TL;DR.** Defensive metrics are noisy: typical Y/Y r 0.4–0.5; require ~3 years to stabilize. **DRS and UZR rely on proprietary BIS video data** and disagree by 10–20+ runs for the same player-season. **OAA (Statcast)** has higher Y/Y reliability than UZR's range component. **Catcher framing has the highest Y/Y stability of any defensive metric (~0.7+ r) — higher than OBP or SLG.**

## DRS (Dewan/BIS, 2003+; *Fielding Bible* 2006)
BIS video catch-probability model. Components: rPM (range; replaced by PART System for IFs in 2020), rSB, rGFP, rARM, rGDP, rSZ (catcher framing, added later), rBU, rHR. **Pre-2020 method excluded shift plays.** UZR–DRS r² ≈ 0.66 single-yr, 0.74 multi-yr. Used for bWAR fielding.

## UZR (Lichtman, 2003+; FanGraphs 2008)
Field divided into ~64 zones; per-bucket baseline catch rate over 6-yr reference. Components: RngR, ErrR, DPR, ARM. RngR Y/Y r lower than OAA. **UZR/150** is rate stat; **MGL: "does not necessarily tell you true talent."** Used for legacy fWAR.

## OAA (Statcast; OF 2016+, IF 2020+)
Catch probability from start position (Hawk-Eye), opportunity time, direction, wall proximity (OF) or distance/time/runner speed (IF). **Automatically accounts for shifts.** Components: Reaction (0–1.5s), Burst (1.5–3.0s), Route (efficiency); Jump = composite. CPOE = rate sibling. Higher Y/Y r than UZR-RngR.

## FRAA / DRP (BP)
Play-by-play, no zone data; mixed-model controls for pitcher GB%, park, batter handedness. **2023: replaced by DRP (Deserved Runs Prevented) and RDA (Range Defense Added)** for Statcast era.

## Rng+ (Baseball-Reference)
Total Zone framework (Sean Smith) for pre-Statcast; DRS components for modern. Display stat.

## ARM
OF arm rating component of UZR/DRS. Statcast Arm Strength = avg velocity of top 10% competitive throws. Physical inputs stable; opportunity-decision component noisier.

## RPM (Reads, Positioning, Movement)
Statcast Jump components for outfielders.

## Catcher Framing (Turkenkopf 2008 → Marchi 2011 → **Fast 2011 "Removing the Mask"** → BP CSAA → FanGraphs 2014+)
Logistic regression of called-strike probability on location/count/identity. **~0.13 runs/extra strike.** Best framers historically ~+35 R/120 G; spread compressed post-2015 to ~+15–20 R. **Y/Y r ~0.7+ — highest reliability in defensive sabermetrics.** Robot strike zone (ABS) would zero this skill.

## Catcher Blocking Runs
Passed balls / wild pitches prevented, controlling for pitcher. Lower magnitude (±3 R typical).

## Pop Time (Statcast)
Pitch-mitt to throw-receipt at 2B; lg avg ~2.0s; range 1.89 (elite) to 2.14. **Driveline finding:** arm strength has higher correlation with pop time than exchange — counter to common coaching emphasis.

## DRS Subcomponents
**rSB** (catcher/pitcher SB defense), **rGFP** (Good Fielding Plays), **rPM** (range plus/minus), **rARM** (OF arm), **rSZ** (catcher framing).

## CPOE (Statcast)
Catch% − Expected Catch% (rate sibling of OAA).

### Reliability Summary

| Metric | Y/Y r | Sample to stabilize |
|---|---|---|
| DRS | 0.4–0.5 | 3 yrs |
| UZR | ~0.4 (range) | 3 yrs |
| OAA | 0.5–0.6 | 2 yrs |
| FRAA/DRP | Moderate | 3 yrs |
| **Framing Runs** | **0.7+** | **<1 yr** |
| Pop Time | Moderate | ~50 throws |

---

# SECTION 6 — AGGREGATE VALUE METRICS (WAR ECOSYSTEM)

**TL;DR.** **fWAR, bWAR, WARP** answer the same question with different fielding metrics, different pitcher run estimators, and slightly different replacement levels — producing **2–3 win differences for individual players**. For team aggregates, all correlate strongly with actual wins (r ≈ 0.83–0.93). Each calibrates total league WAR ≈ 1000 per 162-game season; replacement-level team WPct ≈ .294 (~48-114 record).

## fWAR (FanGraphs)
**Position players:** wRAA (from wOBA) + BsR + Fielding (UZR legacy 2003+; DRS/OAA optional; **separate FG framing model for catchers**) + positional adj + replacement. **Pitchers: FIP-based.** Hitter/pitcher allocation 570/430. Replacement ~.294 WPct.

## bWAR / rWAR (Baseball-Reference; Sean Smith origin)
**Position players:** wRAA-style + Baserunning + **DRS (2003+)** / Total Zone earlier + positional adj + replacement. **Pitchers: RA9 + team-defense adjustment** (subtracts runs allowed attributable to fielders). Hitter/pitcher allocation 590/410.

## WARP (Baseball Prospectus)
Hitting: **DRC+**. Pitching: **DRA**. Defense: **FRAA (legacy) → DRP (2023+ Statcast era)**. **Mostly proprietary**; values can shift retroactively.

### Why Same Player Differs by 2–3 Wins
1. **Pitcher metric** (FIP vs RA9): biggest source of divergence.
2. **Fielding metric** disagreements (UZR vs DRS vs FRAA routinely 5–15 R).
3. **Catcher framing** treatment (WARP most aggressive; bWAR via rSZ; fWAR via separate framing model).
4. Subtle replacement-level/playing-time application differences.

Example: Brendan Rodgers 2022 fWAR=1.7 vs bWAR=4.3.

## WPA / RE24
See Section 4 (covered for both pitchers and hitters).

## RAR / RAA / oRAR / dRAR
Pre-conversion intermediate run currencies; oWAR/dWAR splits at B-R (B-R's dWAR includes positional adj since 2012 rework).

## VORP (Keith Woolner, BP 2001–02)
Marginal Lineup Value vs positional replacement-level baseline. Pitcher version: Repl = 1.37·LgRA−0.66 (SP), 1.70·LgRA−2.27 (RP). **Offense-only for hitters**; superseded by WARP/WAR.

## JAWS (Jay Jaffe; B-R since Nov 2012)
**JAWS = (Career bWAR + 7-year peak bWAR)/2.** HoF benchmarking. Pitchers use only pitching WAR. Position groups padded with avg HoFer comparators. Critique: arbitrary 7-yr peak; ignores postseason/awards.

## Win Shares (Bill James 2002)
**3 WS = 1 team win** (top-down allocation). 48% offense / 52% defense. **No negative values** (controversial). Defense uses pre-2002 proxies (range factor, team efficiency); inferior for modern eras.

### Team WAR vs Wins (empirical)

| Source | Metric | r | r² |
|---|---|---|---|
| Cameron 2009 (FG) | fWAR vs same-yr W | 0.83 | 0.69 |
| DuPaul (THT) | fWAR vs same-yr W | ~0.91 | 0.83 |
| FG Community 2014 | fWAR vs W (1985–2013) | — | 0.7525 |
| BTBS 2018 | fWAR vs Pythagorean W | ~0.97 | 0.95 |
| DuPaul (THT) | WAR Yr N → Wins Yr N+1 | 0.59 | 0.35 |

---

# SECTION 7 — PREDICTIVE MODELING LITERATURE REVIEW

## A. Regression to the Mean & Stability Studies

**TL;DR.** Stabilization point = sample size at split-half r=0.7. Critically, **stabilization ≠ predictive value** (Carleton's repeated warning). Use Bayesian-style regression: true_talent ≈ (player·n + lg_mean·k)/(n+k) with stat-specific k.

**Foundational literature:**
- **Carleton (Pizza Cutter), "525,600 Minutes" (StatSpeak 2007)** — seminal split-half reliability work.
- **Carleton, "It's a Small Sample Size After All" (BP 2012)** — KR-21 + Cronbach's α + Spearman-Brown extrapolation update.
- **Carleton, "Should I Worry About My Favorite Pitcher?" (BP 2013)** — pitcher version (min 2000 BFP, 2003–2012).
- **Pemstein & Dolinar, "A New Way to Look at Sample Size" (FG 2017)** — replaces stabilization-point framing with continuous Cronbach's α confidence-band machinery.

**Y/Y autocorrelations (cross-confirmed):** K% hitter ~0.84 / pitcher ~0.78; BB% ~0.65–0.70; HR/AB hitter ~0.74; BABIP hitter ~0.37 / pitcher ~0.05–0.20; HR/FB pitcher ~0.0; FIP > ERA > WHIP for pitcher Y/Y.

**Statcast-era stickiness:** EV avg Y/Y r ≈ 0.7+ (~40–60 BIP to r=0.7); EV90 more stable than max EV; Barrel% Y/Y r ≈ 0.5–0.6; xwOBA Y/Y r² ≈ 0.218 vs wOBA r² ≈ 0.191.

**Lichtman regression model** (canonical): true_talent = (n·rate + k·lgMean)/(n+k); k for OBP ≈ 200 PA, K% small, BABIP ~1000+ BIP.

## B. Run Expectancy & Linear Weights

**Lindsey, "An Investigation of Strategies in Baseball," *Operations Research* 11 (1963)** — first 24 base-out RE matrix from ~1000 games.

**Palmer & Thorn, *The Hidden Game of Baseball* (1984)** — formal Linear Weights / Batting Runs system; Monte Carlo replicated Lindsey's RE table.

**Tango/Lichtman/Dolphin, *The Book* (2007)** — RE matrix, RE24, leverage index, wOBA.

**Typical 2010s RE values:** 0,—: 0.48 R; 1B,0: 0.86 R; bases loaded,0: 2.40 R; 0,2 outs: 0.10 R.

**Linear weight values (modern, runs above out):** Out −0.27; NIBB +0.30; HBP +0.32; 1B +0.45; 2B +0.76; 3B +1.06; HR +1.40.

**wOBA annual calibration:** RE24-derived event values, subtract out-baseline, multiply by wOBA-scale = lgOBP/lgwOBA_raw so league wOBA = league OBP. Static-weight version's R² vs annually calibrated wOBA = 0.986.

**Markov approaches:** D'Esopo & Lefkowitz (1977); **Bukiet/Harold/Palacios, "A Markov Chain Approach to Baseball," *Operations Research* 45(1):14–23 (1997)** — generalized to non-identical players, lineup optimization. Theoretically appealing but rarely beats aggregate linear weights for projection.

## C. Projection System Architecture

| System | Author | Method |
|---|---|---|
| **Marcel** | Tango (2004) | 5/4/3 weights on last 3 years; regress to 1200 PA league-avg; linear age curve around 29 |
| **PECOTA** | Silver (BP 2003) | k-NN comparables on similarity scores; percentile bands; comparable-derived aging |
| **ZiPS** | Szymborski (BTF/FG ~2013) | 4-yr weighted history; Mahalanobis-distance comps over ~152K pitcher / 185K hitter baselines; comp-derived aging; now incorporates zStats |
| **Steamer** | Cross/Davidson/Rosenbloom (FG 2012) | Weighted-regression with stat-specific regression amounts; PITCHf/x/Statcast inputs; daily in-season updates; aging implicit |
| **THE BAT/X** | Carty (2010 / X 2020) | PECOTA-style core + Statcast batted-ball + park/platoon/weather/air-density/umpire factors. 150+ Statcast variables evaluated |
| **ATC** | Cohen (FG 2017) | **Stat-specific weighted ensemble** of major systems; FantasyPros #1 most accurate 2019–2023 |

**Common architecture:** weighted recent seasons (typical ~40–50% Y-1, 25–30% Y-2, 15–20% Y-3) → per-stat regression to mean → age adjustment → park/league/MLE translations. Composites (FG Depth Charts = 50/50 ZiPS+Steamer; ATC) generally beat any single system.

## D. Aging Curves

**TL;DR.** Classical "peak at 27" was a steroid-era artifact. Modern delta-method curves (Zimmerman 2013, 2020) put hitter peak ~age **26**; post-PED-ban era shows near-immediate decline from MLB debut. Skills age very differently: speed peaks earliest (~25), defense ~24–26, K-avoidance ~24–25, BB-rate plateaus, ISO/power latest (~28–29).

**Methodologies:**
- **Delta method (Tango/Lichtman):** Player-paired deltas X→X+1, weighted by harmonic mean PA. Suffers **survivor bias** (lucky-bad players don't return). **Lichtman 2016 BP correction** imputes hypothetical Y2 for dropouts.
- **Quadratic regression (Bradbury 2009, *J Sports Sci* 27:599–610; *Hot Stove Economics* 2010):** Player-fixed-effects quadratic in age. Implies peak ages ~29 for OPS — **biased by selection on long-career players** (Birnbaum 2009 critique).
- **Bayesian splines (Albert; Schell 1999).**

**Petti & Zimmerman pitcher results (SABR Analytics 2013):** velocity declines linearly from MLB debut; K/9 holds longer than velocity (compensating breaking-ball usage); RP maintain velocity longer than SP (selection effect); RP K-rate peaks ~28.

**Steroid-era distortion:** Pre-PED-ban data inflated apparent peak/late-career durability. Bradbury's age-29 result partly reflects PED-era seasons.

## E. Statcast-Era Predictive Research

**Key results:**
- **xwOBA > wOBA for prediction** (canonical result; multiple confirmations).
- **EV90 > mean EV > max EV** for projecting next-yr wOBAcon (Clemens FG 2022; Salorio 2024).
- **Barrel% Y/Y r ~0.5–0.6 > SLG Y/Y r ~0.4** — Barrel% better self-predictor of next-year SLG than SLG itself.
- For **rookies** with ≥200 BIP, **max EV alone outperforms wRC+** for predicting future production.
- For **pitchers**, contact-quality metrics far less sticky than for hitters; pitcher xwOBA-against has only modest advantage over FIP (Judge BP 2018, "Siren Song of Statcast Expected Metrics").
- **Stuff+ → next-year FIP/ERA/K-BB% beats each metric's own self-correlation in small samples** (Sarris/Bay 2021).

**Key public xStats:** Perpetua xStats.org (2015–18); MLBAM official xwOBA via XGBoost (Sharpe MLB Tech Blog ~2018); Stuff+ (Sarris/Bay), PitchingBot (Grove), aStuff+ (Salorio); Driveline proprietary Stuff+.

## F. Machine Learning & Modern Approaches

- **XGBoost dominant in public domain:** xwOBA (MLBAM), Stuff+/Pitching+, PitchingBot, aStuff+, Haugen Stuff+.
- **Deep learning** mostly proprietary front-office: LSTMs/Transformers over pitch sequences; pose-estimation (KinaTrax, Hawk-Eye markerless) for biomechanics.
- **Driveline Stuff+** (drivelinebaseball.com): 4th iteration as of 2024; uses Rapsodo/TrackMan + Statcast + location-adjusted approach angles.

**Conferences:** Saberseminar (Boston, August); SABR Analytics (Phoenix, March); MIT Sloan Sports Analytics; NESSIS (biennial MIT/Harvard); CMSAC.

**Notable researchers:** Jim Albert (BGSU; *Curve Ball*; Bayesian career trajectories); Marchi/Albert/Baumer (R textbook); Wayne Winston (*Mathletics*).

**Public toolchain:** pybaseball (Python; LeDoux/Schorr; MIT license), baseballr (R; Bill Petti), Lahman, Retrosheet via Chadwick Bureau tools.

## G. Team-Level Prediction

**Pythagorean (Bill James 1980):** W% = RS²/(RS²+RA²). Empirical best exponent ~1.83 (slightly below 2). RMSE on full-season standings ≈ 4 games.

**Pythagenport (Davenport, BP):** exponent = 1.50·log10((RS+RA)/G) + 0.45.

**Pythagenpat (David Smyth; "US Patriot"):** **exponent = ((RS+RA)/G)^0.287** — preferred form (satisfies boundary RPG=1 → exponent=1, which Pythagenport fails). RMSE ≈ 3.99 games/season.

**BaseRuns (David Smyth, ~1990s):** **R = A·B/(B+C) + D**, where A=baserunners, B=advancement, C=outs, D=HRs. **Preferred over Runs Created** at extremes (RC blows up). Tango: "models the run-scoring process significantly better than any other run estimator." RMSE typically 21–22 R/162.

**Log5 (Bill James 1981; equivalent to Bradley-Terry):** P(A wins) = a(1−b)/[a(1−b) + (1−a)b]. Validated across 200K+ MLB games (Hammond/Johnson/Miller 2013 arXiv).

**Defensive Efficiency Ratio (DER):** 1 − BABIP-against. Team-level Y/Y r ~0.5; project from individual UZR/OAA/DRS rather than prior team DER.

**Recommended projection flow:** Player projections → projected RS, RA → **Pythagenpat → expected wins**.

---

# SECTION 8 — KEY CORRELATIONS MATRIX

**Caveat.** Many "commonly cited" Y/Y r values lack a single canonical source. Where multiple sources exist, ranges given. Where only qualitative literature exists, that is flagged.

### Table 1 — Offensive metrics vs Team R/G

| Metric | r | r² | Source |
|---|---|---|---|
| AVG | 0.820 | 0.672 | Vollmayer (Bucknell, 1996–2000, 146 team-yrs) |
| OBP | 0.914 / 0.930 | 0.835 / 0.865 | Vollmayer / Wolfe Hacks 2024 |
| SLG | 0.897 | 0.804 | Vollmayer |
| OPS | 0.949 / 0.956 / 0.961 | 0.900–0.924 | Vollmayer / Morong 2013 / Wolfe Hacks |
| wOBA | 0.953 / 0.961 | 0.908–0.924 | Morong / Wolfe Hacks |
| 1.8·OBP+SLG | 0.957 | 0.916 | Morong 2013 |
| DRC+ | reliability ~0.73, predictive ~0.50 (vs ~0.35 for wRC+/OPS+/wOBA) | — | Judge BP 2018 |

### Table 2 — Pitching metrics vs ERA (same-year and predictive)

| Metric | Same-yr r (or r²) | Next-yr ERA r²(or r) | Source |
|---|---|---|---|
| FIP vs ERA | r ≈ 0.893 (r² ≈ 0.797) | r² ≈ 0.125–0.128 | Nerds of Baseball / Pitcher List Richards |
| xFIP vs ERA | r ≈ 0.815 | r² ≈ 0.18 | Nerds of Baseball |
| SIERA vs ERA | r ≈ 0.801 | r² ≈ **0.197–0.204** (best public) | Nerds / Pitcher List Richards 2019 |
| ERA → ERA | (1.00) | r² ≈ 0.078–0.082 | Pitcher List / Kaplinger |
| xERA vs ERA | ~ FIP-tier | r² ≈ 0.13 | Pitcher List |
| K-BB% Yr N → ERA Yr N+1 | — | r ≈ 0.37 (often beats SIERA) | Staude FG tool |
| DRA vs same-year RA9 | strongest descriptive after 2017 update | r ~0.34 weighted Spearman next-yr | Judge BP 2017 |

### Table 3 — Team WAR / Wins / Pythagorean

| Relationship | r | r² | Source |
|---|---|---|---|
| Team fWAR vs same-yr W | 0.83 → 0.91 | 0.69 → 0.83 | Cameron 2009 / DuPaul THT |
| Team WAR (1985–2013) vs W | — | 0.7525 | FG Community 2014 |
| WAR Yr N → Wins Yr N+1 | 0.59 | ~0.35 | DuPaul THT |
| Pythagorean (exp 2) vs W% | ~0.94 | ~0.88 | James / B-R |
| Pythagorean (1.83) vs W% | — | 0.875 avg | Magnus 2021 |
| Pythagorean (1.83 + 1-run var) | — | 0.946 | Magnus 2021 |

### Table 4 — Hitter Y/Y stability

| Stat | Y/Y r | Source |
|---|---|---|
| K% | **0.78–0.885** | RStudio/FanGraphs; Carleton |
| BB% | 0.74–0.752 | RStudio; BTBS |
| HR (counting) | 0.719 | RStudio |
| ISO | 0.712 | RStudio |
| SB | 0.823 | RStudio |
| BABIP | 0.37–0.44 | Loftus THT / RStudio |
| AVG | 0.466 | RStudio |
| OBP | 0.544 / 0.62 | RStudio / BTBS |
| SLG | 0.570 / 0.63 | RStudio / BTBS |
| wOBA | 0.534 | RStudio |
| wRC+ | 0.526 | RStudio |
| LD% | 0.22 / 0.366 | BTBS / Loftus |
| HR/FB hitter | ~0.30–0.40 | aggregated |
| Hard Hit% | r ≥ 0.70 vs ISO/SLG/HR-FB; Y/Y not explicitly published | FG Community |
| EV avg | task value 0.70–0.75 directionally consistent; not explicitly published | Clemens FG |
| Barrel% Y/Y | task value 0.55–0.65 plausible; not directly cited | — |
| Sprint Speed Y/Y | "extremely strong" — no published exact r | Petriello MLB.com |
| **DRC+** | **~0.73** | Judge BP 2018 |

### Table 5 — Pitcher Y/Y stability

| Stat | Y/Y r | Source |
|---|---|---|
| ERA | ~0.28 | Pitcher List / Kaplinger |
| FIP | ~0.40 | Pitcher List |
| xFIP | > FIP | Pitcher List |
| SIERA | ~0.45–0.50 | Pitcher List |
| K% | ~0.78–0.80 | Staude / Carleton |
| BB% | ~0.65 | Staude |
| K-BB% | ~0.56 | Staude |
| BABIP | ~0.15–0.25 | McCracken; FG Library |
| HR/FB | near-zero | Staude / Grosnick |
| LOB% | low | FG Library |
| GB% | >0.7 | FG Library |
| Velocity | ~0.85+ | Sarris (qualitative) |
| Spin rate (4-seam) | **r²=0.816 / 0.851 min 100 pitches** | **Sarris FG (explicit)** |
| Stuff+ | reliable after **80 pitches** | FG Library / Sarris-Bay |

### Table 6 — Statcast → Future Outcomes

| Predictor | Outcome | r/r² | Source |
|---|---|---|---|
| xwOBA Yr N | wOBA Yr N+1 | r² ≈ 0.218 | Dynasty Dugout |
| wOBA Yr N | wOBA Yr N+1 | r² ≈ 0.191 | Dynasty Dugout |
| Predictive wOBA (Tango bucketed) | wOBA Yr N+1 | beats xwOBA | Tango blog / Paraball Notes 2024 |
| Stuff+ first half | second-half K% | "almost as strong as K%-self" | Sarris/Bay 2021 |
| Stuff+ first half | second-half FIP-/ERA-/K-BB% | > each metric's self-correlation | Sarris/Bay |
| Pitching+ (250+ pitches RP, 400–500 SP) | rest-of-season ERA | beats preseason ZiPS/Steamer | Sarris FG/Athletic |
| Hard Hit% | ISO/HR-FB/SLG (same-season) | r ≥ 0.70 | FG Community |
| Hard Hit% | BA/BABIP | r ~0.10 (weak) | FG Community |
| Barrel% | HR/FB | r ≈ 0.66–0.76 | Insider Baseball |

---

# SECTION 9 — KEY BOOKS, PAPERS & DATA SOURCES

## Books — Sabermetric Theory & Methods
- **Tango/Lichtman/Dolphin, *The Book: Playing the Percentages in Baseball* (2007).** Canonical — wOBA, RE24, Leverage Index, WPA, lineup optimization.
- **Thorn & Palmer, *The Hidden Game of Baseball* (1984; 2015 reissue).** Linear Weights / Batting Runs.
- **Bill James, *Baseball Abstract* (annual 1977–1988); *Win Shares* (2002); *New Historical Baseball Abstract* (2001/2003/2010).** Origin of Runs Created, Pythagorean, Range Factor, MLEs.
- **Albert & Bennett, *Curve Ball* (2003).** Markov chain RE; Bayesian streakiness.
- **Marchi/Albert/Baumer, *Analyzing Baseball Data with R* (2nd ed. 2018; 3rd ed. 2023).** Reproducible code lab manual.
- **Dewan, *The Fielding Bible* Vols I–V (2006–2020).** DRS methodology & results.
- **Winston, *Mathletics* (2009/2012).** OR/Markov treatment.
- **Bradbury, *Hot Stove Economics* (2011).** Aging-curve econometrics & valuation.

## Books — Industry/History
- **Lewis, *Moneyball* (2003).**
- **Keri ed., *Baseball Between the Numbers* (BP, 2006).** Includes Silver's "Why Was Kevin Maas a Bust?" PECOTA chapter.
- **Sawchik, *Big Data Baseball* (2015).**
- **Reiter, *Astroball* (2018).**
- **Lindbergh & Sawchik, *The MVP Machine* (2019).**
- **Law, *Smart Baseball* (2017).**
- **Baseball Prospectus Annuals (2003–present).** PECOTA + methodology updates.

## Foundational Papers
- **McCracken, "Pitching and Defense" (BP 2001).** DIPS theory (Usenet original 1999).
- **Lindsey, "An Investigation of Strategies in Baseball," *Operations Research* 11:477 (1963).** First RE matrix.
- **Bukiet/Harold/Palacios, "A Markov Chain Approach to Baseball," *Operations Research* 45(1):14–23 (1997).**
- **D'Esopo & Lefkowitz, "The Distribution of Runs in the Game of Baseball" (1977).**
- **Schell, *Baseball's All-Time Best Hitters* (Princeton 1999/2005).** Park-adjustment methodology.
- **Bradbury, "Peak athletic performance and ageing," *J Sports Sciences* 27(6):599–610 (2009).**
- **Silver, "Introducing PECOTA" (BP 2003 annual).**
- **Swartz & Seidman, "Introducing SIERA" 5-part (BP 2010).**
- **Judge/Pavlidis/Turkenkopf, "Introducing Deserved Run Average" (BP 2015).**
- **Judge, "Introducing DRC+" (BP Dec 2018).**
- **Long/Judge/Pavlidis, "Introducing Pitch Tunnels" (BP Jan 2017).**
- **Fast, "Spinning Yarn: Removing the Mask" (BP 2011).**
- **Turkenkopf, "Catcher Framing" (Beyond the Box Score 2008).**
- **Marchi, "Evaluating Catchers" (THT 2011).**
- **Carleton stabilization series (StatSpeak 2007; BP 2012, 2013, 2017).**
- **Pemstein & Dolinar, "A New Way to Look at Sample Size" (FG 2017).**
- **Sarris/Bay Stuff+ papers (FG/The Athletic 2021+).**
- **Hammond/Johnson/Miller, "The James Function," arXiv 1312.7627 (2013).**

## Online Resources
- **FanGraphs Library** (library.fangraphs.com) — canonical sabermetric definitions.
- **Baseball Reference Glossary** (baseball-reference.com/about/glossary.shtml).
- **Baseball Savant** (baseballsavant.mlb.com; csv-docs).
- **Baseball Prospectus Glossary**.
- **Tom Tango blog** (tangotiger.com / tangotiger.net).
- **The Hardball Times** (tht.fangraphs.com).
- **Pitcher List** (pitcherlist.com).
- **Driveline Baseball** (drivelinebaseball.com/blog).

## Databases & Tools
- **Sean Lahman Database** — season-level 1871+; CC BY-SA 3.0; bundled with R `Lahman` and `pybaseball`.
- **Retrosheet** — play-by-play 1916+; complete modern era.
- **Baseball Savant / Statcast** — pitch-level 2008+; batted-ball 2015+.
- **Chadwick Bureau Tools** (cwevent/cwgame/cwbox; player ID Register).
- **pybaseball** (Python; LeDoux/Schorr; MIT).
- **baseballr** (R; Bill Petti).
- **Brooks Baseball** — Pitch Info classifications.

## Journals & Conferences
- **SABR Baseball Research Journal**; **By The Numbers** (BTN).
- **Saberseminar** (Boston, August).
- **SABR Analytics Conference** (Phoenix, March).
- **MIT Sloan Sports Analytics Conference**.
- **Journal of Quantitative Analysis in Sports** (De Gruyter/ASA).
- **CHANCE Magazine** (ASA).
- **NESSIS** (MIT/Harvard biennial); **CMSAC** (Carnegie Mellon).

---

# SECTION 10 — MODEL BUILDER'S GUIDE (synthesized framework)

**TL;DR.** Build on a linear-weights backbone (RE24 → wOBA), feed it Statcast contact-quality features for hitters and Stuff+/Pitching+ inputs for pitchers, regress every feature with stat-specific Bayesian priors (Lichtman scheme), age-adjust with delta-method curves (Lichtman 2016 survivor-bias-corrected), park/league-translate, and aggregate to teams via Pythagenpat. Use 3 years of weighted history (Marcel 5/4/3 baseline) plus MiLB MLEs for prospects. Validate via temporal cross-validation, never random splits.

## 10.1 Recommended Feature Set

### Offensive (Hitter) Features
**Tier 1 — high-signal core (always include):**
- **K% and BB%** (PA-denominator); fastest-stabilizing skills.
- **ISO** or component HR/PA, 2B/PA, 3B/PA.
- **wOBA** (contemporary, era-calibrated weights); use **xwOBA** as a Bayesian-style talent estimator where Statcast available.
- **EV90** (90th-percentile exit velocity) or "Best Speed"; **Barrel%**; **Sweet Spot%**.
- **Sprint Speed** (Statcast 2017+); pre-2017, use Spd.
- **GB% / FB%** (avoid LD% as predictor).

**Tier 2 — useful augmentation:**
- **Pull%/Cent%/Oppo%** specifically for FB/LD (drives shift behavior, HR projection).
- **HR/FB% (hitter)** with regression toward EV-conditional baseline.
- **Plate discipline:** O-Swing%, Z-Contact% (proxy K-BB% talent before stabilization).
- **wRC+ or DRC+** as composite output benchmark (for validation, not as input — risk of circularity).

**Exclude or de-weight heavily:**
- AVG, BA/RISP, RBI, R — context-dominated noise.
- Raw H, AB, HBP — use rate forms.
- LD% — Y/Y r ~0.22; mostly noise.
- HR/FB% (pitcher-side proxy) without regression.

### Pitching Features
**Tier 1:**
- **K% and BB%** (BF-denominator); **K-BB%** (single most predictive simple ratio).
- **GB% / FB% / IFFB%** (Statcast LA-derived preferred over BIS).
- **Stuff+ / Location+ / Pitching+** (or PitchingBot equivalents) where available — fastest-stabilizing inputs (~80 pitches).
- **Velocity**, **spin rate**, **spin axis / active spin %**, **extension**, **release point**, **IVB**, **HB**, **VAA** (relative to release-height-conditional baseline).
- **xwOBA-against** and **xERA** (Statcast) for contact quality.

**Tier 2:**
- **Tunneling differentials** (where data available; modest marginal lift).
- **CSW% / SwStr%** (predict K%, not ERA directly).
- **Pitch-mix and platoon-split** features.
- **FIP / xFIP / SIERA** as composite output benchmarks (validation, not core inputs — collinear with Tier 1).

**Exclude/de-weight:**
- W/L, raw H allowed, ERA (use FIP-family + Stuff+ as primary skill signals).
- HR/FB% (pitcher) without heavy regression to lg avg.
- LOB% as predictor (use only as regression flag).
- BABIP-allowed without regression to ~.300 + extreme-pitcher adjustments (knuckleballers, GB-extreme).
- BS, HLD, SV — opportunity-driven; use leverage-aware metrics if relievers matter.

### Defensive Features
**Tier 1 (Statcast era 2016+ for OF, 2020+ for IF):**
- **OAA + Fielding Run Value** (range/positioning skill).
- **Catcher framing runs** (any of FG/BP/SIS models); **highest-stability defensive skill (Y/Y r ~0.7+)**.
- **Catch Probability components** (Reaction, Burst, Route).
- **Arm Strength** (Statcast) for OF.

**Tier 2:**
- **DRS** (with awareness of pre-2020 shift exclusion).
- **Pop time + caught-stealing rate** for catchers.
- **Catcher blocking runs**.

**Pre-Statcast:** DRS / UZR with explicit uncertainty bands; Total Zone for pre-2003.

## 10.2 Stats to Exclude (Instability/Noise/Collinearity)

| Reason | Stats |
|---|---|
| Context-dominated noise | RBI, R, W, L, BA/RISP |
| Subjective scorer | E, SF (when used as skill), ER vs UR distinction |
| Slow stabilization | LD%, HR/FB pitcher, BABIP pitcher (regress heavily) |
| Opportunity-driven | SV, BS, HLD, HBP (in moderate samples), SH |
| Collinear with Tier 1 | OPS, OPS+, FIP, xFIP, SIERA, kwERA — use as outputs/benchmarks not parallel inputs |
| Era-incomparable | Raw counting stats without era adjustment; CG/SHO |

## 10.3 Minimum Sample Size Thresholds (with Bayesian regression below)

Use stabilization points as **regression weight anchors**, not as cutoffs:

| Feature | Min for raw use | Heavy regression below |
|---|---|---|
| K% (hitter) | 60 PA | <60 PA |
| BB% (hitter) | 120 PA | <120 PA |
| ISO | 160 PA | <160 PA |
| BABIP (hitter) | 820 BIP | <820 BIP |
| wOBA | 200+ PA | <200 PA |
| EV/LA/Barrel% | 50 BBE | <50 BBE |
| K% (pitcher) | 70 BF | <70 BF |
| BB% (pitcher) | 170 BF | <170 BF |
| GB% (pitcher) | 70 BIP | <70 BIP |
| HR/FB pitcher | regress always | always |
| BABIP pitcher | regress always | always |
| Stuff+ | 80 pitches | <80 |
| Location+ | 400 pitches | <400 |
| OAA | 1.5 seasons | <1 season |
| DRS/UZR | 3 seasons | <3 |
| Catcher framing | 1 season | <0.5 season |

**Empirical-Bayes formula:** `talent_estimate = (n·player_rate + k·league_mean) / (n + k)` with k ≈ stabilization PA per stat (e.g., k≈60 for K%, k≈460 for OBP, k≈820 for BABIP, k≈1000–2000+ for pitcher BABIP).

## 10.4 Multi-Year Weighting Scheme

**Default (Marcel-style):** Most-recent-year weight on a 5/4/3/2 sliding scale across last 4 years, then regress to league-mean by stat-specific k. Steamer's empirically-tuned per-stat weights are superior where data permits MSE-minimization.

**Decay function:** Exponential `w_t = exp(−λ·(now − t))` with λ tuned per stat by minimizing out-of-sample MSE; typical λ implies recent year ~40–50%, Y-2 25–30%, Y-3 15–20%, residual deeper. Skill metrics that age fast (speed, K-rate) deserve heavier recency weights; stickier metrics (BB-rate, HR-on-contact talent) tolerate longer lookbacks.

**MiLB MLE translation:** essential for prospects/young players (ZiPS/Steamer/THE BAT all do this). Use level-specific run-environment translations + park factors. Without MLEs, prospect projections are unreliable.

## 10.5 Confounders to Control For

1. **Park factors** — multi-year regressed (≥5 yrs); split by hand and event type. Don't use single-season raw factors. Coors LF, Fenway 3B, Yankee Stadium short porch, etc.
2. **Era / run environment** — recalibrate wOBA/FIP constants annually; use ERA−/FIP−/wRC+ for cross-era comparison.
3. **League factors (AL/NL, DH era)** — separate-league hitter pools; pitcher-batting elimination post-2022 universal DH.
4. **Opponent quality** — particularly for pitcher matchup effects and DRC+/DRA-style adjustments.
5. **Catcher / umpire / weather / temperature / altitude** — DRA-style controls add modest accuracy.
6. **Lineup context** for R/RBI; avoid these stats as inputs.
7. **Defensive context** behind pitcher (use FIP-family, not RA-based, for skill estimation).
8. **Sticky-stuff regime change (June 2021)** — league-wide spin drop; don't compare raw spin rate across the cutover.
9. **Trackman→Hawkeye transition (2020)** — minor systemic shift in EV/LA/spin measurement.

## 10.6 Train/Test Split for Time-Series Baseball Data

**Never use random splits.** Use **walk-forward / temporal cross-validation**:

- **Backtest scheme:** Train on Years ≤T, validate on Year T+1 forecasts; slide window forward; aggregate forecast errors.
- **Cohort-stratified** (rookie / young / peak / late-career) to avoid age-distribution drift.
- **Hold out seasons with regime changes** (2020 short season, 2017–19 juiced ball, 2021 sticky-stuff transition, 2023 shift ban, 2023 pitch clock) for sensitivity analysis.
- **Ensemble across multiple horizons** (1-yr ahead, 3-yr ahead, career-arc) for robust evaluation.

## 10.7 Evaluation Metrics

- **RMSE / MAE** on continuous outputs (wOBA, FIP, WAR).
- **Brier score / log-loss** on probability outputs (HR probability, batter outcome distribution).
- **Calibration plots** (predicted vs realized in deciles).
- **Spearman / Kendall rank correlation** for ordinal use cases (player rankings).
- **Comparison vs benchmarks:** Marcel (must beat); Steamer/ZiPS/ATC (industry standard); composite Depth Charts.
- **PIT (probability integral transform) / coverage** for prediction intervals.
- **Realized vs expected wins** for team aggregates (use Pythagenpat-derived expected wins, not raw projections).

## 10.8 Open-Source Tools & Datasets

| Tool | Purpose |
|---|---|
| **pybaseball** | Python ingestion (FG, B-Ref, Savant, Lahman) |
| **baseballr** | R ingestion incl. NCAA/KBO/NPB |
| **Lahman DB** | season-level 1871+ |
| **Retrosheet** | event-level 1916+ |
| **Chadwick tools** (cwevent/cwgame/cwbox) | Retrosheet parsing |
| **Chadwick Bureau Register** | cross-source player ID join |
| **Baseball Savant CSV** | Statcast 2015+ |
| **bdilday/marcelR** | reference Marcel implementation |
| **FanGraphs CSV exports** | fWAR, projections (Steamer, ZiPS, ATC, THE BAT) |

---

# MASTER STAT HIERARCHY TABLE

Tier reflects predictive value + signal-to-noise + recommended model inclusion. **★** = proprietary/semi-proprietary.

| Tier | Hitting | Pitching | Defense | Value |
|---|---|---|---|---|
| **S — Best public predictors** | DRC+★, xwOBA, EV90, Barrel%, wOBA, K%, BB%, Sprint Speed | Stuff+/Pitching+★, DRA★, K-BB%, Stuff+ inputs (vel/spin/IVB/HB/VAA/ext) | OAA, Catcher Framing Runs | fWAR (FIP-based), bWAR, WARP★ |
| **A — Strong predictors** | wRC+, ISO, OPS+, xBA/xSLG, Hard Hit%, Sweet Spot%, GB%/FB%, BB/SO | SIERA, xFIP, FIP, xERA, K%, BB%, GB%, SwStr%, O-Swing%, Z-Contact%, velocity, spin rate | DRS, UZR, Catch Probability, Arm Strength, Pop Time | RE24, RAR, oRAR/dRAR |
| **B — Useful with caveats** | OPS, OBP, SLG, BsR, UBR★, wSB, wGDP, Pull%/Cent%/Oppo%, Spd | tERA, kwERA, CSW%, LOB% (as regression flag), HR/FB (regress), Tunneling★, RE24, WPA/LI | UZR/150, FRAA/DRP★, Rng+, Catcher Blocking, CPOE | WPA, VORP, JAWS |
| **C — Descriptive / context-dominated** | AVG, HR, 2B, 3B, TB, RC, RC/27, EqA/TAv, XBH%, GIDP | ERA, WHIP, H/9, BB/9, K/9, HR/9, ERA+/− | DP, ARM (raw) | Win Shares, raw RAA |
| **D — Largely noise / superseded** | RBI, R, BA/RISP, SH, SF, HBP (small samples), LD%, raw HR/FB, BABIP (small) | W, L, SV, BS, HLD, BABIP-against (small), HR/FB pitcher (small), CG, SHO | E, FPCT, TC, raw PO/A | — |

**Strong vs Weak Evidence Flags.**
- **Strong:** wOBA/wRC+ run correlation; FIP/SIERA Y/Y dynamics; McCracken DIPS; Carleton stabilization; framing Y/Y stability; Pythagorean/BaseRuns team prediction; Stuff+ stabilization speed; spin-rate Y/Y r²=0.816 (Sarris).
- **Moderate:** DRC+/DRA reliability claims (mostly internal BP validation; some independent corroboration; predictive validity contested per Hareeb); xwOBA's marginal predictive lift over wOBA; tunneling marginal predictive lift; specific aging-curve peak ages (vary 2–3 yrs by method).
- **Weak/Contested:** Sweet Spot% empirical thresholds; Spd's continued utility (largely deprecated); single canonical xBABIP version; many "commonly cited" Y/Y r values without single canonical source.

**Proprietary vs Replicable Flags.**
- **Fully replicable:** wOBA, wRC+, OPS+, ISO, RC, Spd, wSB, FIP, xFIP, SIERA, kwERA, K-BB%, RE24, WPA, Pythagenpat, BaseRuns, Log5, Marcel, basic stabilization analysis.
- **Replicable from Statcast public CSV:** EV, LA, Hard Hit%, Barrel%, Sweet Spot%, Pull/Cent/Oppo (horizontal angle), xwOBA components.
- **Semi-proprietary (architecture known, weights private):** ZiPS, Steamer, Stuff+/Pitching+, PitchingBot, Driveline Stuff+.
- **Proprietary:** PECOTA, THE BAT/X, ATC weights, DRC+, DRA, FRAA/DRP, UBR (BIS dependency), DRS (BIS dependency), Inside Edge fielding, MLBAM internal xwOBA model.

---

*This compendium synthesizes ~50+ primary sources spanning 1963 (Lindsey) to 2024 (Stuff+ updates). Numerical values reported are drawn from published research where possible; engineering estimates are flagged. Where canonical correlations were not located in published form (e.g., Sprint Speed Y/Y r, Barrel% Y/Y r), values consistent with the qualitative literature are noted as such. Always pin model versions and pull dates for proprietary metrics (DRC+/DRA/Stuff+) to ensure reproducibility — these change retroactively when underlying models are updated.*