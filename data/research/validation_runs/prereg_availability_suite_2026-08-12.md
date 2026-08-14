# Pre-registration — availability/volume suite (2026-08-12, before any results seen)

Three studies, registered together BEFORE data inspection. Rule 8 framing: each
has one primary metric and one decision rule; anything else found is exploratory
and cannot ship without its own registration. Rule 9: every gate is against the
CURRENT shipped construction, not a strawman.

Motivating failures (2026-08-12 session): Cruz RoS volume 2.25 PA/tg (pace
carries injury zeros) vs 4.42 when-active; Muncy role shrink caught only as
pace drift; Glasnow/Pivetta marcel_il unrateable; Judge rate #7 × suppressed
volume. Every miss was availability/usage, not rate.

---

## Study A — September veteran-rest effect (pilot: ship or kill)

**Hypothesis.** Veterans on eliminated teams lose meaningful September playing
time vs their own August usage, beyond what contender veterans lose.

**Data.** statcast_{2021..2025}.parquet (PA = distinct (game_pk, at_bat_number)
per batter-game); MLB standings API as of Sep 1 each season for team context;
age from multiyr cache or MLB people API.

**Cohorts.** Veterans = age ≥ 30 with ≥ 350 PA through Aug 31. ELIMINATED =
team ≥ 10.0 games out of its last playoff spot on Sep 1. CONTENDER = holding a
spot or ≤ 5.0 out. (6-10 out = excluded gray zone.)

**Primary metric.** Δ_player = (Sept PA per TEAM game) − (Aug PA per team game),
per veteran; effect = mean Δ(eliminated) − mean Δ(contender), player-clustered
bootstrap CI (1000 reps).

**Gate (decision rule).** Effect ≤ −0.25 PA/tg AND 95% CI excludes 0 AND the
sign is negative in ≥ 4 of 5 seasons → SHIP a September availability multiplier
for eliminated-team vets in period-22/23 projections. Otherwise KILL — no
multiplier, no partial credit, no threshold shopping.

## Study B — Post-IL performance ramp by injury class (decision-layer only)

**Hypothesis.** Hitters underperform their own pre-injury baseline in their
first games back, with magnitude depending on injury class (hand/wrist worst).

**Data.** MLB transactions API 2021-2025 (statusChange to/from IL, sportId=1);
injury class parsed from transaction/stint text into {hand_wrist_finger,
hamstring_quad_calf, back_oblique_core, arm_shoulder_elbow, other}; per-game FP
from statcast-derived box lines (BrownU hitter formula).

**Primary metric.** Per activation: FP/PA over first 15 games back minus FP/PA
over the 30 games before IL placement; require ≥ 40 PA on both legs. Class
effect = mean paired deficit, player-clustered bootstrap CI.

**Gate.** A class ships a POST-IL RAMP display tag iff CI excludes 0 AND
|deficit| ≥ 0.04 FP/PA. Rule 13: tag is context-only — never moves rh3 or a
rank. Classes that fail simply carry no tag.

## Study C — IL-return volume overlay backtest (the load-bearing gate)

**Hypothesis.** For players ON IL at a mid-season as-of date who return that
season, RoS PA is predicted better by (when-active rate × post-return team
games) than by the pace-forward construction the current volume layer applies.

**Data.** 2021-2025; as-of dates Jul 15 / Aug 1 / Aug 15 each season; cohort =
hitters on IL at as-of who logged ≥ 1 PA after it that season. Truth = realized
PA from as-of to season end.

**Baseline (Rule 9).** pace_forward = (season PA to date ÷ team games to date)
× remaining team games — the shipped volume behavior for these players.

**Overlay.** when_active = (PA to date ÷ player games played) × team games
AFTER return date. Two variants scored: (i) actual return date (oracle upper
bound), (ii) estimated return = IL-placement date + minimum stint + 10 days
(realistic). The REALISTIC variant is the one gated.

**Gate.** Realistic overlay must (a) cut median |error| by ≥ 20% vs baseline
AND (b) improve Spearman of predicted-vs-realized RoS PA within the IL cohort.
Pass → overlay ships as the volume source for IL'd/returning players. Fail →
overlay stays a manual diagnostic; boards keep pace-forward.

---

Registered by Claude (Fable 5) at Josh's direction, 2026-08-12 ~9:40pm ET.
Studies run by background agents; this file is the contract the results are
judged against. No gate may be revised after results exist.
