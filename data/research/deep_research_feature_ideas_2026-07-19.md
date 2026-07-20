# Deep-research prompt: new validation candidates for xFP models (2026-07-19)

## The task

Survey public sabermetric research (2020–2026: FanGraphs incl. community research,
Baseball Prospectus, Baseball Savant/Statcast articles, Driveline, SABR, Tango's
blog, academic sports-analytics papers) and produce **15–30 candidate features**
for in-season rest-of-season fantasy-baseball projection models, each one
plausibly ADDITIVE beyond a strong cumulative baseline (described below). The
deliverable is a ranked idea list with per-idea cards — NOT a literature summary.

## The models you are feeding

Ridge regressions on shrunken as-of (leakage-safe, season-to-date) features,
predicting rest-of-season outcomes, trained cross-year 2018–2023, holdout 2024–25:

- **rh3 (hitters):** RoS fantasy points per PA. FP = R + TB + RBI + BB + HBP + SB − K.
- **rp3 (SP):** RoS FP per start. FP = K + 3.3·IP − H − 2·ER − BB − HBP.
- **rprs2 (RP):** RoS total FP incl. 5·SV + 2·HLD (role/leverage matters).
- **Volume companions:** RoS PA per team-game (hitters), GS per team-game (SP).

## The hurdle every idea must clear (this kills ~90% of ideas)

The baseline already contains: season-to-date shrunken rates for ISO, K%, BB%,
HR/PA, hard-hit%, barrel%, contact%, whiff%, SwStr%, chase%, in-play%, SB rate,
xwOBA/PA; Marcel-style multi-year priors; sample-size and season-day cues;
career stage; career xwOBA-minus-wOBA residual; RoS opponent-SP schedule
strength; days-since-IL-return. For SPs additionally: FanGraphs Stuff+ (level),
K−BB% floor/bust model. **The season-to-date FP level is an extremely strong
absorber** — our tournament showed almost every "recent form" or process signal
adds ~0 once the cumulative level is controlled. An idea is only interesting if
its information is plausibly ORTHOGONAL to cumulative outcomes and cumulative
contact/discipline rates.

## The graveyard — do NOT re-propose these (all empirically closed 2026)

Momentum/recency/trailing-window anything (L7/L21 rates, EWMA, slopes,
change-points); trajectory/decline slopes for SP; weather; park factors
(schedule-weighted, marginal); FG Location+/Command for points leagues;
opponent-lineup hand-matchup (team platoon splits — true null, 0-for-4 matchup
family); reliever leverage lag-year features; pitch-mix-change/entropy;
age×drift interactions; xwOBA-minus-wOBA in-season gap; sprint speed;
EV90 (marginal, early-season only, closed); hard-hit/whiff/K trailing windows
(redundant with as-of stack); injury-proneness counts (all null vs volume
models); swing-decision metrics as FP predictors (persistent but non-additive);
catcher framing (already a validated display tag); days-rest.

## Where we suspect unexploited signal (steer here, but don't limit to these)

1. **2023–2026 rule-change exploitables:** pitch-clock fatigue effects on
   specific pitcher types; shift-ban interaction with pull-side ground-ball
   hitters (spray-angle × handedness × infield alignment history); bigger-bases
   SB ecosystem (who gains attempts, catcher/pitcher hold interactions).
2. **Bat tracking (2024+, same-year usage only):** attack-angle match to pitch
   height distributions; swing-length consistency; squared-up rate per swing —
   we validated bat SPEED as the only additive process metric; adjacent
   bat-tracking constructs are open if same-year framed.
3. **Spray/direction quality:** pulled-air-ball rate (the "pulled fly ball"
   literature), direction-adjusted xwOBA variants that Savant's xwOBA ignores
   (xwOBA is direction-blind — a known gap).
4. **Usage/role micro-structure:** batting-order position dynamics beyond our
   lineup-spot features; SP pitch-count leash trajectory (manager behavior);
   RP usage patterns predicting role promotion (beyond lag-year leverage —
   in-season gmLI-to-date is UNTESTED here and registered as open).
5. **Team-context spillovers:** team offensive environment for counting stats
   (R/RBI are lineup-dependent — is teammate-quality-as-of additive for R+RBI
   specifically?); defense behind a pitcher (team OAA as-of) for H/ER terms.
6. **Pitch-level arsenal interactions:** pitch-shape complementarity /
   tunneling metrics with public formulations; arm-angle changes (Savant
   publishes arm angle 2020+); release-point consistency as injury/decline
   leading indicator.
7. **Biomechanics/fatigue leading indicators:** velocity WITHIN games (1st
   inning vs late), time-through-order patterns as skill, extension changes.
8. **Minor-league/pipeline signals:** Triple-A stat translation for callups
   (we have MiLB priors but only AA/AAA counting stats); age-vs-level.

## Per-idea card format (required)

For each candidate:
- **Name + exact formula sketch** (as-of computable, no future data)
- **Data source + years available** (Statcast pitch-level 2015+, bat tracking
  2024+, arm angle 2020+, MLB Stats API, FanGraphs — flag anything requiring
  new scraping)
- **Mechanism** (one sentence — why it predicts RoS outcomes)
- **Why it survives the absorber** (what information it carries that
  season-to-date FP + the rate stack above cannot)
- **Closest graveyard relative + why this is different** (mandatory — if you
  can't name the difference, drop the idea)
- **Honest effect-size expectation** (our gate: +0.005 cross-year r vs the FULL
  baseline, 5/7 year sign consistency, positive 2024–25 holdout; a "huge"
  claim is a red flag)
- **Which model** (rh3 / rp3 / rprs2 / volume) **and framing** (in-season as-of)

## Ranking criteria

Rank by: (a) orthogonality argument strength, (b) data already on hand
(Statcast parquets 2015–2026 local) vs new acquisition, (c) sample depth
(features needing 2024+ data can't clear our 5-of-7-year consistency gate
until ~2028 — flag these as FUTURE, don't rank them top), (d) published
empirical support with effect sizes, not just theory.

## Hard constraints

- Points league (rates × volume), NOT category/roto — SV/HLD/SB values differ.
- Everything must be computable as-of a mid-season date with no leakage.
- Prefer 2015+ data availability; 2018+ acceptable; 2024+ = FUTURE-flagged.
- No proprietary data (Trackman, Hawk-Eye raw, team-internal).
