# Umpire-Assignment Signal — Feasibility + Value Under ABS (2026)

**Date:** 2026-06-13
**Question:** Is pre-scanning tomorrow's home-plate umpire assignments worth
building into the BrownU model (8-team H2H points) to tilt start/sit decisions —
**given that ABS (Automated Ball-Strike challenge) is LIVE in MLB 2026**?
**Script:** `scripts/_oneoff/umpire_abs_study.py`
**Sample cache:** `data/research/xfp_cache/hp_umpire_sample.csv` (240 games, 2024-25)

**TL;DR VERDICT: LOW / DIMINISHED VALUE — document, do NOT prioritize.**
Data is fully collectable, but ABS challenges remove the majority of the
*consequential* umpire-driven swing. The residual maps to **<< 1 FP** of expected
SP-start value — below `rp3` per-start noise (~10 FP SD). Skip the build.

---

## (1) COLLECTABILITY — CONFIRMED, cheap, reliable

HP-umpire identity is **not** in statcast — the `umpire` column in our
`statcast_*.parquet` is **100% null** (pybaseball never populates it). But it
**is** trivially obtainable from the MLB Stats API game feed, keyed by the
`game_pk` we already carry in every statcast row:

```
GET https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live
  -> liveData.boxscore.officials[ officialType == "Home Plate" ]
       .official.fullName / .official.id
```

**Empirical proof (this run):** sampled 240 games evenly across 2024 + 2025
(120/yr) and resolved the HP umpire on **100.0%** of them — 84 distinct umpires,
each row carrying `game_pk, date, home, away, hp_umpire, hp_umpire_id`. Sample
written to `data/research/xfp_cache/hp_umpire_sample.csv`. Examples:

| game_pk | date | matchup | HP umpire | id |
|---|---|---|---|---|
| 747224 | 2024-03-28 | COL@AZ | Dan Bellino | 483564 |
| 745435 | 2024-03-29 | SF@SD | Adam Hamari | 503077 |
| 746815 | 2024-03-31 | DET@CWS | Dan Merzel | 605670 |

For a *forward* (pre-scan) signal you'd need the **assignment before the game**,
not the post-game feed. MLB does not publish next-day plate assignments via this
endpoint; the historical/public sources are **umpscorecards.com** and
**Retrosheet** (post-hoc) for zone-accuracy ratings, and crew-rotation inference
for next-day prediction. So: *historical* ump identity + accuracy is fully
collectable; *forward* assignment is only inferrable (crew rotation), which is
the first friction even before the ABS argument.

**Collectability verdict: trivially feasible for historical analysis; forward
assignment requires crew-rotation inference (extra, lossy step).**

---

## (2) PRE-ABS UMPIRE VARIANCE — quantified from local 2024 statcast

Method (all local, `statcast_2024.parquet`, pre-ABS season): take only *taken*
pitches (`called_strike` / `ball` / `blocked_ball`), classify in/out of zone from
`plate_x, plate_z` vs `sz_top, sz_bot` (rulebook half-plate 0.83 ft), then isolate
the **shadow zone** — borderline pitches within ~one baseball width (0.25 ft) of
the boundary, where the umpire actually has discretion.

| Metric | Value |
|---|---|
| Taken pitches w/ geometry (2024) | 366,222 |
| Borderline "shadow-zone" taken pitches | 114,043 (31.1% of taken) |
| League CS-rate: in-zone / out-zone | 0.927 / 0.084 (geometry sane) |
| League CS-rate **in shadow band** | **0.564** (where discretion lives) |
| Per-**game** shadow CS-rate SD (≥40 borderline px, n=1,960) | **0.084** |
| Per-game shadow CS-rate p10 → p90 | 0.455 → 0.667 (gap **0.212**) |
| **Between-UMP** shadow CS-rate SD (2024 sample, ≥2 games/ump, n=23) | **0.0525** |

**Key honesty caveat on the variance number:** the per-*game* SD (0.084) is an
**upper bound** on the ump-only signal — game variance also contains
pitcher/catcher-framing/roster noise. Re-grouping the 2024 API sample by *actual
umpire* gives a smaller between-ump SD of **0.0525**, and even that is inflated by
tiny per-ump samples (2 games each); published umpire-scorecard work puts the
stabilized between-ump SD nearer **0.03-0.04**. So the real ump-only signal is
**smaller** than the headline game-level dispersion.

### Translation to run environment (pre-ABS)
- Borderline taken calls per team-game: ~29
- Extreme (p10 vs p90) ump generosity gap flips ~6.2 called strikes/team-game
- At ~0.10 run per flipped borderline call (count-leverage value):
  - **Extreme ump-vs-ump:** ~**0.62 runs/team-game**
  - **Typical (1 SD) ump:** ~**0.24 runs/team-game** (and lower, ~0.10-0.15,
    using the cleaner 0.03-0.04 between-ump SD)

So even *pre-ABS*, a typical ump was worth ~0.1-0.25 run/team-game of run
environment — real but modest, and only the tails (Ángel Hernández-class) moved
a full half-run.

---

## (3) THE ABS DISCOUNT — why 2026 guts this signal

2026 ABS is a **challenge** system (not full robo-zone): 2 challenges/team/game,
ball/strike only, only batter/pitcher/catcher may challenge, challenge **retained
if successful**. Minors (2025) + spring-2026 data: ~3-4 challenges/game attempted,
~50% overturn.

Crucially, challenges are **spent on the most consequential missed borderline
calls** — 2-strike, 3-ball, high-leverage situations — which are *exactly* the
calls that carry the run value computed above. ABS does **not** shrink the whole
shadow band uniformly; it **selectively corrects the worst, highest-leverage
misses**. The residual is the low-leverage borderline calls nobody bothers to
challenge.

Modeled compression: **~62%** of the *consequential* ump-driven swing removed
(midpoint of a 55-70% range). Residual:

| Scenario | Pre-ABS run swing/team-game | Post-ABS residual |
|---|---|---|
| Typical (1 SD ump) | ~0.24 | **~0.09** |
| Extreme (p10 vs p90 ump) | ~0.62 | **~0.23** |

A ~0.09 run/team-game residual maps to **<< 1 FP** of expected SP-start value.
For reference, `rp3` per-start projections carry ~10 FP SD; our σ-rescaled p25/p75
bands span many FP. **The ABS-era ump signal sits an order of magnitude below the
noise floor of the projection it would be modifying.**

---

## VERDICT — SKIP for now (document, don't prioritize)

| Dimension | Finding |
|---|---|
| **Collectable?** | YES — 100% HP-ump resolution via Stats API by `game_pk`. Forward assignment needs crew-rotation inference (lossy). |
| **Pre-ABS signal size** | Real but modest: ~0.1-0.25 run/team-game typical, ~0.6 extreme. |
| **ABS discount** | ~62% of the *consequential* swing removed — challenges target exactly the high-leverage calls that carried the value. |
| **Post-ABS residual** | **~0.09 run/team-game typical → << 1 FP** of SP-start EV. Below `rp3` noise. |
| **Build recommendation** | **DO NOT build a daily ump pre-scan into start/sit.** Net EV per decision is dominated by `rp3`/matchup/boom_stack signals already in the stack. |

**Why not zero?** Two narrow residual uses, both LOW priority:
1. **Tail filter, not a ranker.** If a forward assignment is known *and* the ump
   is a documented extreme (top/bottom ~5% on umpscorecards) *and* the start is
   already a coin-flip cap-bench decision, it's a legal tie-breaker — but it
   can't move a projection (consistent with feedback rule #13: context/Tier-B
   gate only, never additive point-forecast lift).
2. **Re-evaluate if MLB switches to FULL ABS** (robo-zone for all calls). That
   would *eliminate* ump variance entirely (signal → 0), not merely compress it —
   at which point even the tail filter dies. The challenge system is the *only*
   regime where any residual exists.

**Bottom line:** ABS converts a modest-but-real angle into a sub-FP residual.
Documented here; not promoted to any ranker, not added to `/pregame-check` or
`/sp-slate-grid`. Revisit only if forward crew assignments become cheaply
available AND a full-ABS switch is announced (the latter would kill it outright).

---

### Reproduce
```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/umpire_abs_study.py
# --no-api  to skip the Stats API sample and run only the local variance estimate
```
Outputs: `data/research/xfp_cache/hp_umpire_sample.csv` + console variance/ABS-discount tables.
