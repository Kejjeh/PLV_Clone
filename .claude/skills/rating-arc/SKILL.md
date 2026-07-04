---
name: rating-arc
description: In-season archetype-rating arc mover board — for every SP and hitter with a 2026 sample, the ~4-week arc on the role's VALIDATED load-bearing pillar (SP STUFF, hitter CONTACT — the only ratings that carry forward-FP signal per the 2026-07-04 study), tagged RISER/FLAT/FALLER and MINE/FA/opp. The early-warning lens - process ratings move before results do. Use when the user asks "whose stuff is trending", "rating risers", "who's improving under the hood", "arc on X", or wants FA adds surfaced before their surface stats move. Rule 13 - display/context only, never a ranker. Owner of the math - scripts/xfp/lib/rating_arc.py.
---

# rating-arc

In-season rating-arc movers: latest snapshot vs ~28 days earlier on the pillar
that actually ties to FP forward (2026-07-04 validation — SP **STUFF** in-season
forward r=.48, the only rating that out-predicts the raw FP level; hitter
**CONTACT** r=.29; CONTROL/DISCIPLINE/SB are dead for BrownU points and are
shown only as context columns).

**Trigger phrases:** "whose stuff is trending", "rating risers/fallers",
"who's improving under the hood", "rating arc on X", "process movers".

## Run it

```bash
python scripts/xfp/run_rating_arc.py                    # both roles, MINE + FA movers
python scripts/xfp/run_rating_arc.py --role sp --top 15
python scripts/xfp/run_rating_arc.py --names "Sheehan,Messick"   # card mode
python scripts/xfp/run_rating_arc.py --lookback 21 --csv out.csv
```

## Reading it

- **RISER / FALLER** = key-pillar delta ≥ +5 / ≤ −5 rating points (~0.5 SD) over
  the lookback. FLAT in between.
- **⚠STALE-ARC** = the player's *latest* snapshot is itself >21d old (IL,
  demoted) — history, not a current read. Excluded from FA boards automatically.
- SP snapshots are **start-anchored trailing-10 windows straight from statcast**
  (same-day current, unaffected by the ratings-master staleness bug); hitter
  snapshots are weekly with a 50-PA floor.
- Canonical first-run reads (2026-07-04): **Freddy Peralta STUFF 49→43 FALLER**
  (independently confirms the forced-drop cut order) and Rodón 47→55 in rehab.

## Rules

1. **Rule 13 — context only.** An arc never moves rh3/rp3 and never re-ranks a
   board by itself. It sets *conviction* and surfaces *watch-list* names.
2. Gotcha #11 distinction: within-season **FP-level** trajectory is validated
   non-predictive; this is a **process-stat** arc (SwStr/velo/contact-quality
   composites) — the family bat-speed/velo trending validated as early reads.
   Promotion to any ranker still requires `/validate-feature`.
3. Cross-check a RISER before adding: `/triangulate` (full stack) or
   `/shadow-scout` for no-rp3 arms.

## Interlocks

- `lib/rating_arc.py` **owns** arc computation — `/fa-monitor` signal O imports
  it; never re-derive.
- Complementary to `/trending` (physical: bat speed / FB velo) — rating-arc is
  the *skill-composite* layer above it; when both fire on the same player,
  that's the strongest early-read available.
- Feeds `/conviction-scan` (model-vs-rating divergence) with direction.
