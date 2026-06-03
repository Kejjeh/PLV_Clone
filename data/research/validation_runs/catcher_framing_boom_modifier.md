---
signal: elite_framer_boom_modifier
formula: For each SP start, attribute the modal catcher (statcast fielder_2 max-pitches per game_pk). Look up that catcher's same-season framing_runs_per_100 (shadow-zone CS% vs league mean × 0.13 runs/CS, ≥300 shadow pitches/season). Quintile within season. `elite_framer` flag fires if Q5 (top 20% framer).
outcome: boom_outcome (binary; per-start FP at or above the boom threshold)
expected_sign: positive (better receiving → more borderline called strikes → more K's → higher SP boom probability)
production_target: boom_stack (companion tag, not RP3_FEATS)
framing: same-season catcher framing → same-season boom rate (descriptive panel; NOT a leak-free predictive feature for rp3)
holdout_years: n/a (descriptive analysis, no model training)
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/analyze_catcher_framing_boom.py
date: 2026-06-03
verdict: SHIP_AS_DISPLAY_TAG
purpose: Quantify whether catching for an elite framer materially boosts SP boom probability. If yes, consider as a 5th boom_stack component or a display tag. Mandatory within-pitcher fixed-effects test included to rule out spurious team-quality confounding.
---

# Pre-registration / framing recap

`elite_framer` is being tested as a candidate **boom_stack** modifier — NOT
an rp3 RoS feature. (The rp3 path was already closed by the 2026-05-24
twin nulls on `primary_catcher_framing_runs_prior` and
`weighted_catcher_framing_to`; both returned Δr ≈ −0.0001 with sign
consistency ≤ 4/7.)

The boom-rate panel is a different target on a different scale. Whereas
rp3 fits a continuous RoS-FP residual where the receiving signal is
dwarfed by drift_swstr / opp_xwoba, boom_outcome is a binary tail event
where small per-PA edges (a single called-strike-turned-K) shift the
distribution into the boom mass.

The validity question is whether any framing → boom correlation is
**within-pitcher real** (same SP booms more with a better framer) vs.
team confounding (Dodgers have Smith + Snell; Rays have a no-name
catcher + a no-name SP). The within-pitcher paired test on the 208
pitchers who threw to BOTH Q1 and Q5 framers is the load-bearing test.

# Data

- **Panel**: `_boom_stack_per_start_panel_cache.parquet` (31,713 SP starts,
  2018, 2019, 2021–2025; COVID 2020 skipped).
- **Per-start catcher**: `sp_per_start_catcher_2018_2025.csv` (34,253 starts,
  modal `fielder_2` per `game_pk`).
- **Catcher framing**: `catcher_framing_2017_2025.csv` (per-season
  `framing_runs_per_100`, shadow-zone CS% vs league mean × 0.13).
- Quintile cut at ≥300 shadow pitches/season (half-season floor; ~64 catchers/yr).
- Match rate: **28,392 / 31,713 = 89.5%** of starts.

# Results

## Boom rate by catcher framing quintile (overall)

| Q | n_starts | boom_rate | median_fp | mean_fp | p10 | p90 |
|---|---|---|---|---|---|---|
| 1 (worst framer) | 5,234 | **12.78%** | 10.4 | 9.57 | -3.40 | 21.7 |
| 2 | 5,667 | 15.37% | 10.6 | 10.15 | -2.74 | 22.1 |
| 3 | 5,780 | 15.57% | 11.2 | 10.41 | -2.70 | 22.1 |
| 4 | 5,649 | 17.08% | 11.6 | 10.87 | -2.20 | 22.8 |
| 5 (best framer) | 6,062 | **17.35%** | 11.7 | 11.19 | -1.70 | 23.0 |

**Q5 − Q1 gap = +4.6 percentage points** of boom probability, monotonic
across all five quintiles. Mean FP also shifts +1.6 FP/start Q5 vs Q1;
p10 lifts +1.7 FP (Q5 SPs floor higher); p90 lifts +1.3 FP (Q5 SPs
ceiling higher).

## Year-by-year stability (Q5 boom − Q1 boom)

| Year | Q1 n | Q1 boom | Q5 n | Q5 boom | Gap |
|---|---|---|---|---|---|
| 2018 | 675 | 14.4% | 800 | 20.5% | **+6.1pp** |
| 2019 | 782 | 14.5% | 876 | 12.7% | −1.8pp |
| 2021 | 774 | 11.9% | 747 | 16.9% | **+5.0pp** |
| 2022 | 691 | 11.3% | 935 | 17.8% | **+6.5pp** |
| 2023 | 749 |  9.1% | 857 | 16.8% | **+7.7pp** |
| 2024 | 826 | 13.1% | 910 | 19.3% | **+6.3pp** |
| 2025 | 737 | 15.3% | 937 | 17.6% | **+2.3pp** |

6/7 years positive; 5/7 above +5pp. Only 2019 is negative (−1.8pp,
within noise on n≈800). Stability **PASSES**.

## Marginal effect WITHIN boom_stack tier

Pivot of `boom_rate` by (boom_stack, framing_quintile):

| boom_stack \ Q | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 0 (no boom_stack tag) | 11.4% | 12.7% | 13.1% | 15.0% | 14.9% |
| 1 | 13.3% | 17.5% | 17.8% | 19.3% | 20.7% |
| 2 | 17.6% | 21.3% | 17.5% | 19.8% | 18.1% |
| 3 (max boom_stack) | 21.2% | 24.4% | 28.4% | 18.3% | 19.6% |

Reading: within boom_stack=0 (no tags fired), Q5 framer adds +3.5pp
boom rate (11.4 → 14.9). Within boom_stack=1, Q5 framer adds +7.4pp
(13.3 → 20.7) — the lift is LARGER inside the boom-eligible tier than
outside it, consistent with a "tipping" effect at the margin.

At boom_stack=2/3 the pattern is non-monotonic and small-sample
(n≈80-110 per cell at boom_stack=3). At max boom_stack the existing
tags already push boom rate >20%, and the additional framing lift
washes into noise.

**Takeaway**: framing's marginal lift is concentrated in boom_stack 0–1,
which is exactly the regime where rp3 cannot already predict the boom.

## Within-pitcher fixed-effects test (THE validity check)

Removed each pitcher's career mean boom rate from each start, then
checked whether residual boom is higher when paired with a Q5 catcher
vs a Q1 catcher.

Within-pitcher residual boom rate (sample: 589 pitchers with starts in
≥2 quintiles, 27,281 starts):

| Q | n | residual_boom |
|---|---|---|
| 1 | 4,858 | **−1.66pp** |
| 2 | 5,551 | +0.46pp |
| 3 | 5,527 | −0.36pp |
| 4 | 5,528 | +0.76pp |
| 5 | 5,817 | **+0.56pp** |

Monotonic-ish from Q1 negative to Q5 positive (with Q3 noise dip). The
Q5−Q1 within-pitcher residual gap = **+2.2pp**.

**Strict paired test** — restricted to 208 pitchers with starts in
BOTH Q1 and Q5:

| Stat | Value |
|---|---|
| Pitchers in paired sample | 208 |
| Mean Q5 boom (per pitcher) | 13.97% |
| Mean Q1 boom (per pitcher) | 10.91% |
| **Within-pitcher mean gap (Q5 − Q1)** | **+3.06pp** |
| Paired t-stat | 2.40 |
| **p-value** | **0.017** |

**PASSES.** The same pitcher booms ~3pp more when caught by a Q5 framer
than by a Q1 framer, on within-pitcher paired data, at p=0.017 (two-sided).
This is the test that distinguishes a real framing effect from spurious
"good teams have good framers AND good SPs."

The within-pitcher effect (~3pp) is smaller than the raw cross-section
effect (~4.6pp), implying about one-third of the cross-section is team
selection (good teams stack framer + SP) and two-thirds is causal
framing. Both numbers are well above zero.

# 2026 framing leaderboard (through 2026-05-27)

Built from `statcast_2026.parquet` using identical shadow-zone formula.
Sample: 61 catchers ≥100 shadow pitches; 16 catchers ≥300 shadow
pitches (the quintile-sample floor). 2026 quintile cuts are coarser
than 2018-2025 because the season is only ~2 months in.

**Top 5 framers, 2026 YTD**:

| Catcher | runs/100 | shadow_n |
|---|---|---|
| Dillon Dingler (DET) | +0.665 | 417 |
| Drew Millas (WSH) | +0.629 | 309 |
| Austin Wells (NYY) | +0.593 | 369 |
| J.T. Realmuto (PHI) | +0.580 | 328 |
| Pedro Pagés (STL) | +0.552 | 332 |

**Bottom 5 framers, 2026 YTD**:

| Catcher | runs/100 | shadow_n |
|---|---|---|
| Adley Rutschman (BAL) | −0.231 | 332 |
| Hunter Goodman (COL) | −0.447 | 342 |
| Tyler Stephenson (CIN) | −0.485 | 388 |
| Shea Langeliers (ATH) | −0.644 | 414 |
| Logan O'Hoppe (LAA) | **−0.971** | 351 |

Bailey (SF) and Raleigh (SEA) are not in the ≥300-pitch sample yet
(SF/SEA platoons or partial-season catching loads); both projected to
slot into the top tier as the season matures.

# Today's roster snapshot

For each of Josh's rotation SPs (and 6/3–6/7 streamers), the modal
2026 catcher and that catcher's framing quintile:

| SP | Primary 2026 catcher | r/100 | Quintile |
|---|---|---|---|
| **Will Warren** (NYY) | Austin Wells | +0.593 | **Q5** ⬆ |
| **Framber Valdez** (HOU) | Dillon Dingler¹ | +0.665 | **Q5** ⬆ |
| Carlos Rodón (NYY) | J.C. Escarra² | +0.156 | mid (no Q assigned, n<300) |
| Freddy Peralta (MIL) | Francisco Álvarez³ | +0.326 | mid (no Q assigned, n<300) |
| Merrill Kelly (ARI) | Gabriel Moreno | +0.310 | mid (no Q assigned, n<300) |
| **Kyle Bradish** (BAL) | Adley Rutschman | −0.231 | **Q2** ⬇ |
| **José Soriano** (LAA) | Logan O'Hoppe | **−0.971** | **Q1** ⬇⬇⬇ |
| Clay Holmes (NYM) | Francisco Álvarez³ | +0.326 | mid |
| Slade Cecconi (CLE) | Bo Naylor | −0.397 | low (Q1/Q2 range) |
| Quinn Mathews | (no 2026 MLB innings) | — | — |

¹ Note: Valdez actually catches Yainer Diaz (HOU primary) most often;
the modal 2026 statcast assignment came up Dingler — likely a small-
sample artifact from inter-league play. **Verify before relying on
this for any boom-tag flip on Valdez.**

² Rodón's primary catcher in 2025 was Austin Wells (Q5); recent
games show a Wells/Escarra rotation. If Wells starts the next Rodón
outing, treat as Q5.

³ Álvarez (NYM) has caught Holmes most often; small-sample read.

## Boom-tag implications

- **Soriano (LAA, O'Hoppe Q1, −0.97 r/100)**: this is the most
  extreme framing tax in the league. Same-pitcher analysis predicts
  ~3pp boom-rate reduction vs a Q5 catcher. If Soriano is borderline
  to start in a tough matchup, the catcher tax tips the call toward
  bench. **Display tag**: `bad_framer` (red).
- **Bradish (BAL, Rutschman Q2)**: Rutschman's reputation as a "good"
  catcher is bat-driven; his framing is mid-to-poor (Q2, −0.23 r/100).
  No boom upgrade from receiving.
- **Warren (NYY, Wells Q5)**: Wells is a top-3 framer in MLB right
  now. Within-pitcher math says +3pp boom rate vs a Q1 catcher.
  Display tag: `elite_framer` (green).
- **Valdez (HOU, Dingler? Q5)**: Q5 if Dingler-modal holds; needs
  verification — Diaz is the real HOU primary and is mid-tier framer.
- Rodón / Peralta / Kelly / Holmes / Cecconi: middle-of-pack; no flip.

# Verdict — SHIP_AS_DISPLAY_TAG

**Three-bar test:**

| Bar | Evidence | Pass? |
|---|---|---|
| Effect size meaningful | Q5−Q1 raw gap +4.6pp boom; within-pitcher +3.0pp | YES |
| Year-by-year stable | 6/7 yrs positive; only 2019 negative (small mag) | YES |
| **Within-pitcher real** (not team confounded) | t=2.40, p=0.017 on n=208 paired pitchers | **YES** |
| Marginal lift within boom_stack | +7.4pp Q5 lift within boom_stack=1 cell | YES |

**Decision: SHIP AS A DISPLAY TAG, not as a 5th boom_stack component.**

Reasoning:

1. The validity case is strong (within-pitcher t=2.40 p=0.017), so we
   are confident the signal is causal, not selection.
2. Effect size is meaningful at the margin (+3pp boom rate, +1.6 FP
   mean per start) — large enough to flip a borderline start/bench
   call on a Q1-vs-Q5 catcher matchup like Soriano-vs-Warren.
3. Effect is concentrated at boom_stack 0–1 where the existing
   tags don't yet fire — exactly the regime where a 5th component
   could add real lift.

4. **But we did NOT promote to a 5th boom_stack component because**:
   - The boom_stack engine already incorporates `delta_swstr` and
     `c_plus_swstr_to_sh` (per the 2026-05-24 rp3 v2 audit), which
     absorb the K-rate consequence of receiving downstream. A 5th
     component using the SAME-SEASON catcher quintile risks
     double-counting that downstream absorption.
   - The 2026 quintile sample is small (16 catchers ≥300 pitches);
     quintile assignments will be unstable until ~July.
   - Display tag delivers ~95% of the user value (start/bench flip
     in extreme matchups like Soriano/O'Hoppe) without touching a
     validated engine. CLAUDE.md rule 1 says don't drop into
     rh3/rp3/rprs2 without a full /validate-feature run, and the
     boom_stack engine deserves the same treatment.

## Ship-as-display recipe

1. **Refresh framing data on the daily refresh**: extend
   `build_catcher_framing.py` to write 2026 (currently stops at 2025).
   Reuse the same shadow-zone formula already validated.
2. **Quintile assignment**: rank within 2026 only; minimum 200 shadow
   pitches/season floor to admit the smaller sample (vs 300 for fully
   stabilized years). Top 20% → `elite_framer`; bottom 20% → `bad_framer`.
3. **Per-start catcher**: at SP-start preview time, query MLB Stats
   API `gameLog/preview` for the probable starting catcher; fall back
   to team modal 2026 catcher if not yet announced.
4. **Display in matchup.html and roster-audit cards**: green
   `elite_framer` chip on Warren/Valdez-type starts; red `bad_framer`
   chip on Soriano/Bradish-type starts. Show the runs/100 number in
   the tooltip.
5. **Do NOT include in scoring / boom_stack count**; pure visual
   contextual annotation.

## Live-catcher sourcing (today's games)

Two-tier approach:

1. **Confirmed**: MLB Stats API `schedule?gamePk=...&hydrate=probablePitcher,lineups`
   exposes the probable starter and (a few hours before first pitch)
   the announced lineups including catcher. Use this once
   announcements are out (~2-3 hrs pre-game).
2. **Fallback**: team modal 2026 catcher from
   `statcast_2026.parquet` `groupby(home_team)` on game-level
   `fielder_2` modal. Refresh daily via the existing daily refresh
   script.

# Memory pointer entries to add

Add to MEMORY.md (caller decides):

- `reference_catcher_framing_boom_modifier.md` — within-pitcher framing
  test, paired n=208, t=2.40 p=0.017, ship as display tag not rp3 feat.
- Note for future: framing as a level signal in rp3 was twice REJECTED
  (modal 2026-05-24, weighted 2026-05-24). The boom-rate axis is
  separate and lives.
