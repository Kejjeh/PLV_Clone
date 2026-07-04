# Roster deep audit — 2026-07-03 (New York Ligers)

## Pre-flight
- Caches fresh (batter_rolling / name_resolution 2026-07-03).
- Projections rh3/rp3/rprs2 all 0d old.
- PL Top100 SP + closers caches STALE (Mon/Tue editions out) — SP ranks below use our model; PL ranks are ~1wk old, treated as context only.
- Collision guard: Max Muncy = LAD 3B (mlbam 571970, rh3 2.04). Not the ATH catcher. Confirmed in live pull.

## Slot occupancy (LIVE)
IL slots: **3/3 FULL** (Judge OF, Fried SP, Glasnow SP) | Active 26/22 | Bench 8/4 (overflowing with IL'd bodies).

### The 4 injured NOT in an IL slot (sitting as ZEROS on active/bench)
| Player | Current slot | IL type | Return | Frees IL slot on activation? |
|---|---|---|---|---|
| Hunter Greene (SP) | BE | IL60 | 2026-07-04 (tomorrow) | No — activates to active |
| Wyatt Langford (OF) | BE | IL10 | 2026-07-17 | No |
| Ryan Helsley (RP) | P (active) | IL15 | 2026-07-17 | No |
| Carlos Rodon (SP) | BE | IL15 | 2026-07-19 | No |

These 4 are dead roster weight until their return dates. IL slots can't hold them (all 3 taken by Judge/Fried/Glasnow, who return LATER). This is the core roster-management tension.

## IL return cascade
Greene 7/4 → Langford + Helsley 7/17 → Rodon 7/19 → Fried 7/24 → Glasnow 8/1 → Judge 8/3.
2 IL slots free within 30d (Fried 7/24, Glasnow 8/1). Judge frees the 3rd on 8/3.

## SP cap math (10-start weekly cap)
- Now: 6 healthy SPs → ~7.1 starts/wk → **~3 starts short, stream needed.**
- 7/4 Greene back → 7 SPs → 8.3/wk (still stream OK).
- 7/19 Rodon back → 8 SPs → 9.5/wk (**at cap**).
- 7/24 Fried back → 9 SPs → 10.7/wk (**FORCED DROP — first breach**).
- 8/1 Glasnow back → 10 SPs → 11.9/wk (**second FORCED DROP**).

Two SP drops are mathematically forced between 7/24 and 8/1. Pre-identify the weakest arms NOW.

## Drop candidates — RANKED (cross-validated via triangulate)

| Rank | Player | Model | Triangulate verdict | Note |
|---|---|---|---|---|
| 1 (bat) | **Kody Clemens (util)** | rh3 1.82, #130 | MIXED, boom29/bust24 low ceiling | Weakest bat, no positional lock. **Correct 7/4 drop.** |
| 2 (arm) | **Freddy Peralta (SP)** | rp3 10.99, #57 | MIXED, **STUFF🔻**, boom12/**bust50%** | Weakest healthy SP + real stuff decline. 1st forced-SP-drop target. |
| 3 (arm) | **Emmet Sheehan (SP)** | rp3 11.54, #42 | MIXED, **STUFF🔻** | STUFF-DECLINE tag confirmed. 2nd forced-SP-drop target. |
| — | Parker Messick (SP) | rp3 11.61, #39 | CAUTION, velo +1.5▲, boom38/bust0 | **KEEP** — velo rising, clean floor. Better than Freddy/Sheehan. |

### DO NOT DROP (engine override of the "weak bat" framing)
- **Jordan Walker (OF)** — rh3 1.89 (#92) looks droppable, but triangulate = **BUY (archetype breakout, PL #21, T+1 0.58, career arc 63▲)**. Low rh3 is stale; the archetype + PL both say hold. Dropping him is selling low.
- Elly De La Cruz, Bo Bichette — low current rh3 but core SS talent, not drop material.

## FA add candidates
### Planned 7/4 stream — VERIFIED
- **Luis Castillo (SP)** — confirmed FA (not on any of 8 rosters). rp3 10.93/start (#60), `data_driven_full`, SOFT matchup vs TOR (opp_bat 0.94). Valid same-day stream. Value ~lateral to Freddy (10.99) but healthy + soft opp today.

### Better SP FA targets if adding for RoS (not just a stream)
- Bryce Mayer (Hou) rp3 14.47 #10, 0% owned — top available arm.
- Spencer Schwellenbach (Atl) 12.75 #22, 11.6% owned.
- Blake Snell (LAD) 13.02 #19 — IL stash, 66% owned (likely FA in 8-team; verify).
- Corbin Burnes (Ari) 12.06 #32, 4.8% owned.

### Hitter FA (only if a bat spot opens — roster is bat-light on upside)
- Spencer Horwitz (1B) rh3 0.637 #14, 9.4% owned — best realistically-available bat.

## Cross-validated forward-move sequence (prioritized)

1. **TODAY 7/4 — Drop Kody Clemens → add Luis Castillo (SP).** Stream the soft TOR matchup. Clemens is the weakest asset and has no positional lock; Castillo is a healthy same-day start. Confidence HIGH. (Note: this is a hitter-for-SP swap on an already SP-stacked roster — fine as a one-day stream, but see #2.)
2. **7/4 — Activate Hunter Greene off IL60** (returns tomorrow). His rp3 tag is `marcel_il` (suppressed prior) — expect the number to firm up post-return; he's a keep.
3. **7/17-7/19 — Langford, Helsley, Rodon return.** As each activates, the bench decompresses. Roster hits the 10-SP cap at Rodon (7/19). Stop streaming SPs at that point.
4. **By 7/24 (Fried返) — FIRST forced SP drop: cut Freddy Peralta.** Weakest healthy SP + STUFF🔻 + 50% bust. Frees a slot for Fried.
5. **By 8/1 (Glasnow返) — SECOND forced SP drop: cut Emmet Sheehan.** STUFF-DECLINE tag; next-weakest. Frees a slot for Glasnow.
6. **8/3 — Judge activates**, IL slot #3 frees; roster reaches full health. Re-audit bat depth then (Clemens already gone; consider Horwitz-class add if a util spot is soft).

Net: 3 drops over the next month (Clemens now, Freddy ~7/24, Sheehan ~8/1) absorb the entire IL return cascade. Messick, Walker, Greene are all KEEPS despite surface-low numbers.
