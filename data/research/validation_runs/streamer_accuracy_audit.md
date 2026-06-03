# Streamer Accuracy Audit — Cameron 6/2 Boom Post-Mortem

**Generated:** 2026-06-03
**Trigger:** Noah Cameron 6/2/2026 @ CIN — we flagged CAUTION / SKIP pre-game, he posted 28.1 FP (top-decile streamer outcome).
**Scope:** 2023-2025 per-start outcomes joined with prior-year archetype/ratings as the pre-game "lens."

---

## 1. Cameron's 6/2 line (MLB Stats API confirmed)

| IP  | H | R | ER | BB | K | HR | HBP | **BrownU FP** |
|-----|---|---|----|----|---|----|-----|---------------|
| 7.0 | 1 | 1 | 1  | 0  | 8 | 1  | 0   | **28.1**      |

Formula: K + IP*3.3 - H - 2*ER - BB - HBP = 8 + 23.1 - 1 - 2 - 0 - 0 = 28.1. User's "28 FP" confirmed.

**Game context:** KC @ CIN (Final). The Reds were missing De La Cruz, McLain, and Hays from the lineup — Cameron faced Bleday/Sal Stewart/Suárez/Steer/Friedl/Dunn/Arroyo/Benson around Nathaniel Lowe. Cincinnati's projected lineup_xfp on the day was 0.49 (bottom-quartile of slate offensive strength). This was a soft matchup, not a peak Reds lineup.

---

## 2. Why we flagged CAUTION (the rationale)

Pre-game profile from `sp_ratings_master.csv` (2026 row, pitcher_id 702070):

| Signal              | Value              | Verdict driver |
|---------------------|--------------------|----------------|
| archetype           | GENERIC_HR_PRONE   | Bear-case tier |
| velo_tier           | FINESSE (86.8)     | Bottom-decile  |
| OVERALL             | 40 (vs 54 in 2025) | Sharp drop     |
| OVERALL_career_pct  | 0.00               | Floor          |
| traj_flag           | TRENDING_DOWN      | Bear           |
| cell                | AVG/MINUS/AVG      | Movement crater|
| xwoba_contact       | 0.385              | Top-of-bad     |
| barrel_pct          | 13.3%              | 80th+ %ile bad |
| hard_hit_pct        | 44.8%              | Bad            |
| hr_per_bf           | 3.47%              | Elevated       |

The CAUTION verdict was a defensible read of process metrics. Six independent bear signals lined up.

---

## 3. Pre-game signals that pointed UP (and were under-weighted)

### 3a. Last-3 starts skill spike (5/16, 5/22, 5/27)

| Window                    | K%   | BB%  | swstr% | FB velo | FP avg |
|---------------------------|------|------|--------|---------|--------|
| Pre last-3 (4/1 - 5/10)   | 20.0 | 8.8  | 10.0   | 92.13   | 6.0    |
| Last 3 (5/16, 5/22, 5/27) | 24.2 | 4.5  | 10.7   | 92.40   | 15.4   |

K% up +4.2 pts, BB% down -4.3 pts, FB velo up +0.3 mph. **This is a genuine process signal we had access to.**

### 3b. recform was +3.67 (~"hot" tier)

Our model already exposed this — but the triangulate verdict overrode it because the archetype layer (process bear case) outranked the recform layer in the synthesis rule.

### 3c. Opponent context

CIN's day-of lineup_xfp was bottom-quartile — a known boom-friendly tertile for streamers (see §4c below).

### Verdict: this boom was **partially predictable** — a 3-signal stack (skill-spike + recform-hot + soft opponent) all pointed UP. We had the inputs but the verdict synthesis didn't weight them against the process-archetype layer.

---

## 4. Historical CAUTION-tier distribution (2023-2025)

Used prior-year archetype as the "what we would have known pre-game" lens. 9,081 starts where prior-year ratings exist.

### 4a. Outcome distribution by tier

| Tier               | n     | mean FP | BOOM (20+) | GOOD (15-20) | OK (10-15) | MEH (0-10) | BOMB (<0) |
|--------------------|-------|---------|------------|--------------|------------|------------|-----------|
| CAUTION            | 4,853 | 10.19   | **14.9%**  | 16.7%        | 21.6%      | 32.3%      | 14.5%     |
| NON-CAUTION        | 4,228 | 11.37   | **19.3%**  | 18.1%        | 21.0%      | 28.7%      | 12.9%     |

**Headline:** CAUTION-tier starts boom at 14.9% — only 4.4 pp lower than non-CAUTION. CAUTION is not a "won't boom" verdict; it's a "slightly worse expected value" verdict. Treating CAUTION as DON'T-START is overcalibrated.

### 4b. By archetype (n>=200)

| archetype          | n    | mean FP | BOOM% | BOMB% |
|--------------------|------|---------|-------|-------|
| GENERIC_HR_PRONE   | 493  | 9.23    | 11.6  | 16.2  |
| WILD_MID           | 288  | 9.49    | 12.5  | 13.9  |
| FILLER             | 350  | 7.79    | 12.6  | 20.6  |
| AVERAGE_4_5        | 3612 | 10.22   | 15.1  | 14.5  |
| PURE_CONTROL       | 630  | 11.16   | 17.6  | 14.3  |
| PURE_MOVEMENT      | 946  | 11.70   | 19.8  | 11.6  |
| MOVE_CTRL_ACE      | 277  | 11.94   | 21.3  | 10.1  |
| PURE_STUFF         | 725  | 12.59   | 21.5  | 10.8  |
| STUFF_PLUS_CTRL    | 266  | 14.48   | 29.3  | 7.9   |
| STUFF_PLUS_MOVE    | 289  | 15.01   | 31.8  | 6.9   |

GENERIC_HR_PRONE booms 11.6% of the time. So a 28-FP outcome from a GENERIC_HR_PRONE streamer is ~roughly a 1-in-9 event, not a 1-in-1000 event. **The boom rate floor is not zero for any archetype tier.**

### 4c. Cameron-exact profile

`archetype=GENERIC_HR_PRONE AND traj_flag=TRENDING_DOWN AND OVERALL_career_pct=0`:
- n = 201 starts in 2023-2025
- mean FP = 9.23, median = 9.50
- **BOOM (20+) = 9.5%**, BOMB (<0) = 12.4%

Cameron's 28.1 FP sits at roughly the 92nd percentile of this exact-profile cohort. It's the long tail of a real distribution, not a model breaking.

### 4d. Triple-bear filter

`bad arch + bad traj + bottom-decile career_pct`:
- n = 908 starts
- mean FP = 8.86, BOOM% = 11.5, BOMB% = 16.4

Even our worst-of-the-worst profile booms 11.5% of the time. There is no such thing as a "zero-boom" streamer profile in this data.

---

## 5. Streamer-pool model accuracy (2023-2025)

"Streamer pool" = pitchers with preseason_proj ≤ 12 FP (back-end SP).

### 5a. Accuracy stats

| Metric                                | Value |
|---------------------------------------|-------|
| Streamer-pool starts (2023-2025)      | 6,057 |
| Mean actual FP                        | 9.53  |
| BOOM (20+) rate                       | **13.0%** |
| BOMB (<0) rate                        | 15.7% |
| MAE (preseason_proj vs actual)        | 7.52 FP |
| Signed bias (actual - proj)           | -0.55 (slight overprojection) |
| Underprojected by 5+ FP               | 29.1% of starts |
| Underprojected by 10+ FP              | 12.7% of starts |
| Corr(preseason_proj, actual_FP)       | **r = 0.149** |

**The streamer-pool signal-to-noise is very low.** Pre-season projection explains 2.2% of outcome variance among back-end starters. The model is essentially flat across this tier.

### 5b. Missed-boom share

Of the 1,535 starts in 2023-2025 with 20+ FP, **790 (51.5%) came from the streamer pool** — i.e., players we'd have rated as back-end / streamer-class. **More than half of all top-decile SP outcomes happen below our top-tier line.** Refusing to start streamers means refusing access to half the league's biggest outcomes.

### 5c. Tier-by-tier streamer breakdown

| Tier                       | n     | mean FP | BOOM% | BOMB% |
|----------------------------|-------|---------|-------|-------|
| Back-end (proj 9-12)       | 3,919 | 9.83    | 13.4  | 15.1  |
| Deep streamer (proj ≤8)    | 441   | 6.50    | 5.4   | 22.2  |

Real separation between "back-end SP" and "deep streamer" — the back-end pool is where streaming pays off; the deep pool is a coin flip with downside.

---

## 6. Signal-by-signal lift in the streamer pool

What CAN distinguish a streamer-pool boom in advance?

### 6a. recform (rolling 3-start FP minus preseason proj)

| Bucket             | n     | mean FP | BOOM% | BOMB% |
|--------------------|-------|---------|-------|-------|
| COLD (<-3)         | 1,711 | 9.26    | 12.3  | 15.8  |
| BELOW (-3 to 0)    | 1,077 | 9.10    | 11.8  | 17.0  |
| OK (0 to +3)       | 1,100 | 10.13   | 14.4  | 13.7  |
| WARM (+3 to +6)    | 847   | 9.97    | 13.7  | 15.2  |
| HOT (>+6)          | 694   | 11.04   | 15.0  | 11.7  |

Modest signal: HOT recform = 15.0% boom vs COLD = 12.3% boom. **+2.7 pp lift**.

### 6b. Skill-spike (K% delta +3 AND BB% delta -1, vs preseason)

| Group         | n     | mean FP | BOOM% | BOMB% |
|---------------|-------|---------|-------|-------|
| SKILL-SPIKE   | 793   | 10.01   | 14.4  | 15.0  |
| NO SPIKE      | 4,636 | 9.70    | 13.0  | 15.0  |

Weak: +1.4 pp lift on boom rate. Within CAUTION-tier only, skill-spike lifts boom% from 11.8 → 14.8 (**+3.0 pp**).

### 6c. Opponent lineup_xfp (the strongest signal)

| Opp tertile | All streamer boom% | CAUTION-tier boom% |
|-------------|--------------------|--------------------|
| SOFT        | 14.4               | **13.7**           |
| MED         | 13.7               | 13.4               |
| TOUGH       | 11.0               | 10.0               |

**Cleanest signal in the table.** SOFT vs TOUGH = +3.4 pp lift on boom rate (or **+3.7 pp** within CAUTION). For CAUTION-tier streamers, soft matchup raises boom rate from 10.0% → 13.7% — closing most of the CAUTION-vs-non-CAUTION gap.

### 6d. Stacked

CAMERON 6/2 stacked: HOT recform + skill-spike + SOFT opponent. The expected boom rate of this 3-signal stack (rough combinatorial): ~17-18%. Not a slam-dunk, but **almost double** the bare CAUTION baseline (9.5%).

---

## 7. Honest verdict

**Cameron 6/2 was a noise-skill blend, not pure noise.** Three pre-game signals (Statcast skill-spike, hot recform, soft CIN lineup) all pointed UP. We had the inputs; the triangulate verdict synthesis weighted the process-archetype layer too heavily and didn't surface the stack.

**System-level findings:**

1. **CAUTION ≠ DON'T START.** Even bottom-decile-career-pct + GENERIC_HR_PRONE + TRENDING_DOWN profile booms 9.5% of the time. A 28-FP outcome from this profile is rare but not unprecedented.

2. **51.5% of all 20+ FP outcomes 2023-2025 came from streamer-class pitchers.** Refusing to start streamers means refusing half the league's upside.

3. **Streamer-pool model correlation is r=0.149.** The preseason projection has very weak discriminative power across back-end SPs. Within this tier, we are nearly blind to outcome — and we're treating model verdicts as more confident than the signal supports.

4. **Opponent lineup strength is the cleanest in-pool discriminator** (+3.4 pp boom lift SOFT vs TOUGH; +3.7 pp within CAUTION). It's the most underutilized signal in our current streamer workflow.

5. **The skill-spike stack (K%+3, BB%-1 over last 3) lifts CAUTION boom rate by +3 pp.** It's real but small; needs to be combined with opp context to be actionable.

**There IS a fixable blind spot:** our triangulate synthesis treats the archetype layer as a binary CAUTION gate. It should be a probabilistic prior that gets updated by recent-form + opponent signals before the final verdict.

---

## 8. Proposed feature candidate for /validate-feature

**Candidate name:** `streamer_boom_stack_v1`

**Definition:** A 3-signal additive score for streamer-pool SPs (`preseason_proj <= 12`):

```
boom_stack = 0
if rolling_3_start_K_pct - preseason_K_pct >= +3 AND
   rolling_3_start_BB_pct - preseason_BB_pct <= -1:
    boom_stack += 1
if recform >= +3:
    boom_stack += 1
if opponent_lineup_xfp <= 33rd percentile of slate:
    boom_stack += 1
```

**Hypothesis (pre-registered):** Streamer-pool starts with boom_stack >= 2 will have ≥17% boom rate (20+ FP), vs ≤12% for boom_stack <= 0.

**Test against existing rp3 baseline (Rule 9):** Add boom_stack to rp3 feature list, run k=5 grouped CV by pitcher-year, require both (a) MAE improvement vs full production rp3 and (b) Bonferroni-corrected ΔR² > 0.005 on streamer-pool subset.

**Why this and not something else:** All three components have already been measured to give independent boom-rate lift in this audit (+2.7 pp, +1.4 pp, +3.4 pp respectively). The component pieces are not novel; what's novel is using the stack as a verdict override layer in triangulate when the streamer is in CAUTION tier. The downside risk is small (it would only fire on ~5-10% of streamer-pool starts).

**Pre-registration target:** Create `data/research/validation_runs/streamer_boom_stack_v1_preregistration.md` BEFORE running the validation.

---

## Appendix — files used

- `data/research/per_start_predictor_battle.csv` — 41,077 starts 2016-2025 with actual_FP
- `data/research/sp_ratings_master.csv` — annual archetype/ratings (used prior-year row to avoid look-ahead)
- `data/research/sp_archetype_career_panel.parquet` — season-level archetype panel (reference)
- `data/research/xfp_cache/statcast_2026.parquet` — Cameron pitch-level for last-3 trend
- MLB Stats API gameLog for Noah Cameron (pitcher_id 702070) — confirmed 6/2 line
