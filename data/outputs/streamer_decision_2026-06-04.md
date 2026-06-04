# Streamer Decision — 2026-06-04 → 2026-06-07

**Context:** User did not execute the prior Holmes (6/3) + Rogers (6/4) plan. Holmes is gone (start completed 6/3). Recommendation refreshed against tonight's confirmed probables and the remainder of the scoring week.

## Cap math (current state)

| | starts |
|---|---|
| Soriano 6/1 (done, 8.4 FP banked) | 1 |
| Peralta 6/3 | 1 |
| Rodón 6/4 | 1 |
| Valdez 6/5 | 1 |
| Messick 6/5 | 1 |
| Bradish 6/6 | 1 |
| Warren 6/6 | 1 |
| Kelly 6/6 | 1 |
| Soriano 6/7 | 1 |
| **Scheduled total** | **9** |
| Cap | 10 |
| **Headroom** | **1** |

## Top FA SPs in 6/4 → 6/7 window (boom_stack ≥ 2)

Source: `stream_the_stack_2026-06-04.md` (442 verified FA SPs, Connelly-Early filtered; 27 FA SP starts in window).

| pitcher | team | date | opp | rp3 (p25–p75) | stack | boom% | matchup | own% |
|---|---|---|---|---|---|---|---|---|
| **Noah Cameron** | KC | 6/7 | @MIN | **9.5** (3.6–15.4) #114 | 2/3 | 13.2% | soft | 11% |
| **Slade Cecconi** | CLE | 6/4 | @NYY | 8.4 (2.5–14.3) #180 | 2/3 | 13.2% | **tough** | 2% |
| **Anthony Kay** | CWS | 6/5 | @PHI | 7.5 (1.5–13.4) #230 | 2/3 | 13.2% | neutral | 7% |
| **Adrian Houser** | SF | 6/4 | @MIL | 7.4 (1.4–13.3) #237 | 2/3 | 13.2% | neutral | 1% |

### Notable STACK=1 fallbacks

| pitcher | team | date | opp | rp3 | matchup |
|---|---|---|---|---|---|
| Jack Leiter | TEX | 6/6 | vsCLE | 10.4 (#76) | soft |
| Ryne Nelson | AZ | 6/5 | vsLAD | 10.2 (#80) | tough |
| Brandon Sproat | MIL | 6/6 | @COL | 9.8 (#99) | soft (Coors caveat) |
| Cade Cavalli | WSH | 6/7 | @AZ | 9.6 (#106) | neutral |

## User SP baseline (rp3 per_start)

| SP | scheduled | rp3 |
|---|---|---|
| Soriano (6/1, banked 8.4 actual) | — | 12.1 |
| Peralta 6/3 | done | 11.8 |
| Rodón 6/4 | tonight | 11.2 |
| Valdez 6/5 | 10.4 |
| Messick 6/5 | 10.8 |
| Bradish 6/6 | 10.5 |
| Warren 6/6 | 10.5 |
| **Kelly 6/6** | **8.4** ← weakest scheduled |
| Soriano 6/7 | 12.1 |

Kelly is the clear cut/replace candidate. Messick (10.8) should NOT be benched — benching him just to make room for streamers (~9.5) is a negative-EV trade.

---

## Three chains

### Chain A — Conservative (recommended baseline)
**Keep Kelly. Add 1 streamer for the 1-start headroom.**

- **ADD:** Noah Cameron (KC, 6/7 @MIN, rp3=9.5, stack=2)
  - Pickup window: now-through-Sunday morning; @MIN is a soft offense; this is the highest-projection stack=2 in the window.
- **DROP:** lowest-value bench player (non-Kelly). User should pick the drop based on roster shape — likely a hitter or RP whose week is over.
- **Final starts:** 10 (at cap).
- **Expected FP gain vs no-action:** +9.5 (Cameron added; nothing displaced).

### Chain B — Moderate (highest EV — RECOMMENDED)
**Drop Kelly. Add 2 streamers.**

- **DROP:** Merrill Kelly (rp3 8.4, weakest scheduled start)
- **ADD #1:** Noah Cameron (6/7 @MIN, rp3=9.5, stack=2)
- **ADD #2 (tonight):** Slade Cecconi (6/4 @NYY, rp3=8.4, stack=2) — tough opp but stack=2 boom edge still 13.2%. If you prefer the matchup over the projection, swap in **Anthony Kay** (CWS @PHI 6/5, rp3=7.5, stack=2, neutral opp).
- **Final starts:** 9 − 1 (Kelly out) + 2 (streamers) = **10** (at cap).
- **Expected FP gain vs no-action:**
  - Replace Kelly's 8.4 with Cameron's 9.5 = +1.1
  - Bonus streamer (Cecconi 8.4) into headroom = +8.4
  - **Net ≈ +9.5 FP** vs Chain A's identical +9.5… but Chain B locks in the Kelly replacement, which means if Kay (7.5) is the #2 instead of Cecconi, you still net +7.5 over the empty headroom while only -0.9 vs Kelly. Chain B dominates Chain A when the #2 streamer ≥ ~5 FP, which all stack=2s clear.

### Chain C — Aggressive (NOT recommended)
**Drop Kelly + bench Messick + add 3 streamers.**

- Benching Messick (rp3=10.8) to free a slot for a stack=2 streamer (~9.5) is a **−1.3 FP swap per slot**. Negative EV.
- The 10-start cap is also binding: 9 − 1 (Kelly) + 3 = 11 starts; with Messick benched, 10 starts count. Net move = Kelly (8.4) out, Cameron + Cecconi + Kay in (~25), Messick (10.8) zero'd = +25 − 8.4 − 10.8 = **+5.8 FP vs Chain B's +17.9 FP**.
- **Skip this chain.** Chain B is strictly better.

---

## Bottom line

**Execute Chain B (Moderate).**

| step | action | reason |
|---|---|---|
| 1 | DROP Merrill Kelly | rp3 8.4, weakest scheduled start |
| 2 | ADD Slade Cecconi (CLE) — start him 6/4 vs NYY | tonight's stack=2; +8.4 FP into headroom slot |
| 3 | ADD Noah Cameron (KC) — start him 6/7 @MIN | top stack=2 in window; +9.5 FP replacing Kelly's slot |
| 4 | Leave Messick active 6/5 — do not bench | rp3 10.8 is well above any streamer |

**Cap math after execution:** 8 retained scheduled + 2 streamers = **10 starts** (at cap, all count).

**Expected FP gain vs no-action:** Kelly (8.4) → Cameron (9.5) + Cecconi (8.4) into empty headroom = **+9.5 FP over Chain A** if no-action means leaving headroom empty, or **+1.1 FP** over Chain A if Cameron alone fills headroom. Recommended Chain B vs status quo (Kelly + empty headroom): **~+9.5 FP net.**

### ESPN UI sequence
1. Drop Kelly.
2. Add Cecconi → set as ACTIVE SP for 6/4.
3. (after Cecconi's start clears) Add Cameron → set as ACTIVE SP for 6/7.
4. If Cameron isn't critical to grab tonight (start is 6/7), an alternative ADD #2 is Anthony Kay (6/5 @PHI, neutral matchup, rp3=7.5) if Cameron gets sniped before Sunday.

### Risk notes
- Cecconi @ NYY is a **tough matchup** — the stack=2 tag picks up his recent skill spike + recform but does not override park/lineup. Boom% 13.2% is the right-tail probability; downside is real. Expected value still positive at rp3=8.4, but variance is high.
- Cameron @ MIN is the cleaner play (soft opp + stack=2). If forced to choose one streamer, pick Cameron.
- Stack=2 is ~13% boom rate — **not** a sure thing. The decision is +EV in expectation, not deterministic.

---

## Diagnostic footer
- Source: `data/outputs/stream_the_stack_2026-06-04.{md,json}`
- Confirmed probables in window: 65
- FA SPs verified after Connelly-Early filter: 442
- FA SP starts in window: 27
- Stack distribution: {3:0, 2:4, 1:10, 0:13}
