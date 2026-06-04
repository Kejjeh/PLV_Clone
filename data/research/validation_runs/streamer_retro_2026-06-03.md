# Streamer Retrospective — 2026-06-03

Single-day retrospective comparing the `stream_the_stack` daily recommender + `matchup.html` tags
against actual game outcomes. **Single-day samples are noisy** — this is a calibration sanity check,
not a validation. The validated boom_stack rates (stack=3 → 22.6% boom vs 13% baseline; HIGH-K
edge +6.84 pp) imply we expect roughly 1 in 7-8 streamer picks to boom on any given day.

## Predictions vs outcomes

FA streamers + rostered SPs who actually pitched 6/3. Soriano (LAA, ⚠ framing tax) was *tagged*
as a downside-warning SP but did not start 6/3 — no opportunity to validate the framing-tax call.

| SP | Pre-game stack | Other tags | Tier | Predicted FP (rp3) | Matchup | Actual | Verdict |
|---|---|---|---|---|---|---|---|
| Grant Holmes (ATL vs TOR) | **2/3** (matchup top rec) — matchup.html: **3/4** (incl. park) | — | STREAM (preferred) | 10.1 (p25–p75: 4.2–16.0) | soft | **11.80** | FAIR |
| Andre Pallante (STL vs TEX) | 1/3 | — | MODEST | 9.0 | neutral | **15.70** | FAIR-to-beat |
| Chris Bassitt (BAL @ BOS) | 1/3 | — | MODEST | 7.5 | neutral | **−3.10** | BUST (modest tier, no upside flag — consistent with #225 rp3 rank) |
| Walker Buehler (SD @ PHI) | 1/3 | — | MODEST | 7.4 | neutral | **17.80** | BEAT (no flag predicted it) |
| Erick Fedde (CWS @ MIN) | 1/3 | — | MODEST (soft) | 6.7 | soft | **15.50** | BEAT |
| Freddy Peralta (NYM, YOURS) | **2/4** | 🎯 HIGH-K HIGH-CONVICTION | rostered (backend) | ~11.6 | — | **15.80** | FAIR (slight beat; HIGH-K showed — 6 K's) |
| Jose Soriano (LAA, YOURS) | 0/4 | ⚠ framing-tax | sp2_sp3 | — | — | **DNS** (no 6/3 start) | N/A |

**Boom threshold (≥20 FP): 0 hits across 6 actual starts.**
**Bust threshold (<0 FP): 1 hit (Bassitt).**

## Verdict counts

- BOOM HITs: **0/6** (expected base rate ≈13% → 0.78 expected; 0 observed is well within noise)
- BOOM MISSes: **0** — none of our stack=2+ picks busted (Holmes 11.8, Peralta 15.8)
- BUST PREDICTED + HIT: 0 explicit (Bassitt 1/3 stack was MODEST, not a downside flag — soft FAIR call)
- FAIRs: 4 (Holmes, Pallante, Fedde, Peralta)
- MISSED BOOMs (≥20 FP, untagged): **0** of the 6 we tracked. Buehler 17.80 came closest from a MODEST tier.

## Calibration check

1. **Did boom_stack rank correlate with actual FP?** Mixed.
   - Stack 2/3 SPs (Holmes, Peralta): mean 13.8 FP — outperformed rp3 baseline (~10.9).
   - Stack 1/3 SPs (Pallante, Bassitt, Buehler, Fedde): mean **11.5 FP** — much higher than their rp3
     baseline of ~7.6 (driven by Buehler/Fedde/Pallante overperforming; Bassitt offsetting).
   - Rank correlation (stack → FP) is **flat-to-slightly-positive** on n=6; nothing to read into.

2. **HIGH-K edge?** Peralta (only 🎯K SP who actually pitched) hit 6 K's in 6 IP — consistent
   with the HIGH-K thesis. Cecconi (2/3 HIGH-skill_spike) starts 6/4, not yet evaluable.

3. **Anti-predictive warnings?** Soriano (⚠F framing tax) didn't pitch — no signal.

4. **Untagged blowups?** None — every 6/3 result was within or modestly above p25–p75 except
   Bassitt (below p25, consistent with #225 ranking). No surprise booms outside our flagged set.

## User decision cost

User did not stream Holmes (the day's preferred play). The replacement-level outcome was their
bench SP for 6/3 — likely a streamer-quality alternative ≈ 0–5 FP, or a zero if no replacement
was started. Conservative cost estimate:

- **Holmes actual: 11.80 FP**
- Counterfactual: empty SP slot → 0 FP, or a worse streamer → ~5 FP
- **Estimated leave-on-table: 6–12 FP for the day**

Not catastrophic. Holmes was a "preferred play" but not a stack=3 lock — within a normal range
where skipping costs ~half a starter-day. The bigger structural cost is **not having a streamer
queue built at all** — that's the lesson, not the Holmes specific call.

## Lessons learned

1. **The day's top stack=2 picks (Holmes, Peralta) both produced FAIR-to-positive FP** — exactly
   what the model implies. No catastrophic miss.
2. **Bassitt at rp3 #225 / stack=1 busted (−3.1 FP)** — model rank correctly predicted "MODEST",
   user should treat sub-#200 rp3 as bust-risk even with stack=1.
3. **Buehler/Fedde overperformed rp3 by ~10 FP** — both stack=1, in MODEST tier, no upside flag.
   This is consistent with rp3's ~6 FP RMSE for sub-#200 SPs: a 1-day +10 deviation is ~1.5σ,
   unremarkable. Don't update from this.
4. **0 BOOM HITs in 6 starts** is fully consistent with the validated 13% base rate
   (expected booms ≈ 0.78; observing 0 is the modal outcome).
5. **No new bug or gap surfaced.** Tags fired where expected; outcomes landed in expected ranges.

## Cross-reference to validated rates

| Metric | Validated rate | 6/3 observed | Consistent? |
|---|---|---|---|
| Boom rate (stack=1+) | ~14% | 0/6 = 0% | Yes (CI on 6 is wide; p≈0.40 of seeing 0) |
| Bust rate (sub-#200 rp3) | ~30% | 1/3 = 33% (Bassitt) | Yes |
| HIGH-K edge | +6.84pp | Peralta 6K in 6IP | Directionally yes (n=1) |

**Take:** Today's results do not deviate meaningfully from validated rates. The model is behaving.

## Path forward

- Re-run this retro after Cecconi (6/4 stack=2 #2 pick) and the 6/5 starts complete — that gives
  n=10–13 across the window and tighter signal.
- If by end of week we have 0 booms across all stack=2+ picks (~4 candidates), the cumulative
  p-value of "0 in 4" at 13% rate is still 0.57 — wouldn't reject the model. We'd need a multi-week
  rollup to detect calibration drift.
