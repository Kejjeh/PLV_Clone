# Decision record — drop Fairbanks (RP) → add a FA hitter (2026-06-16)

## Context
At/near the 10-SP-start cap for the week; dropping an RP to add an active hitter.
Engine: `scripts/xfp/research/eval_fa_hitter.py` (rh3 + Blended xFP + xwOBA-L21d-vs-2025
+ xwOBACON-YoY + physical-trend + recent-15g boom/bust, one consistent lens stack).

## Injury truth (drives OF priority)
- **Aaron Judge — IL, fracture, return ~7/24 (~38 days).** Durable OF hole → OF is the priority add.
- **Elly De La Cruz — IL, strain, return ~6/22 (~6 days).** SS/IF need is short-term.
- **Trea Turner — DAY_TO_DAY but played 6/15.** Playing through; the matchup dashboard
  zeroes him by the DTD rule → understates the projection (open fix).

## Fairbanks drop — confirmed
Lowest-ranked rprs2 RP on staff (Duran #3 ▸ Latz #9 ▸ Scott #12 ▸ Helsley #20 ▸
**Fairbanks #22**); saves covered by Duran/Helsley/Scott. Caveat: sheds a Rays closer
saves stream, acceptable given bullpen depth.

## Lineup bar
A FA must beat ~1.7-1.9 rh3 FP/game to start (weakest active: Langford 1.71, Walker 1.93).
**Key:** rh3 K-penalizes/undervalues power bats in this TB/HR format — also read Blended xFP.

## FA-OF board — top targets (full 28-player board: `fa_of_triangulate_set_2026-06-16.json`)
1. **Brent Rooker** — Blended 2.98, L21d xwOBACON .483 rising (real buy-low, RH masher).
   On IL, back ~6/19 (~3-day stash). Highest ceiling.
2. **Kerry Carpenter** — OF-eligible, Blended 2.32, POWER_HITTER, **9 HR vs RHP (.821 OPS)**,
   contact holding (L21d .405≈.408). Strong-side platoon: **start vs RHP, sit vs LHP.**
3. **Dominic Canzone** — clears both rankers (rh3 #64/1.89, Blended 1.95), contact RISING
   (+2 mph bat speed, K% falling), LH-mashes-RHP. Start-today, rising trend.
4. **Trent Grisham** — everyday Yankees CF (best PT security), Blended 2.24; .425 L21d is a
   cooling mirage. Stability play.

## Evaluated and PASSED
- **Eugenio Suárez** — NOT OF-eligible (3B/UTIL), declining (xwOBACON .430→.420→.359,
  archetype BACKUP_BAT TRENDING_DOWN, rh3 #210, K% 31-33%, 73% bust, live_marginal −87).
  Name/HR appeal only; doesn't fill the OF hole. PASS (UTIL HR-dart at most).
- **Spencer Steer / Jo Adell** — both RH (Steer) / extreme-RH (Adell) platoon bats that
  mash LHP but crater vs RHP (the side faced most weeks) → vs-LHP streamers, not the
  durable Judge fix. Steer eligibility corrected (OF-eligible) but cooling off his peak.
- **Luis Robert / Stanton / Chandler Simpson** — name-brand TRAPS (cratering / injured /
  empty-SB), not buy-lows.

## Recommendation
Drop **Fairbanks** → add **Rooker** (ceiling, if you can wear ~3 days to 6/19) **or
Carpenter** (most power that fills the OF hole today; platoon vs RHP) **or Canzone**
(rising-contact alternative). Suárez = pass for this need.
