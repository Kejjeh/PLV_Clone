---
name: streamer-precision-board
description: Daily ranked SP streamer decision board over a date window. For every MINE + FA confirmed probable SP, reconciles four lenses in one row — opponent+park-adjusted rp3 MEAN, season/L5 actuals + empirical bust%, the validated floor_adjusted_xfp (FADJ, which ranks the board), and process percentile — with marcel_il / decline flags. Use when the user asks "rank the streamers", "best FA start for 7/x", "who do I stream", "streamer board", or overlays their own arms against the FA market for cap-filling. Ranks by FADJ so a rich MEAN with a bad floor drops. Calls the owner modules (park_fp_adj, floor_adjusted_xfp, boom_bust, resolve_pitcher_id) — never re-types a park table or a cutoff.
---

# streamer-precision-board

The daily driver for "which SP do I stream." One row per confirmed probable SP
that is **MINE or FA** over a date window, reconciling the four lenses that
actually decide a start:

| Column | Meaning | Owner |
|---|---|---|
| **MEAN** | opponent-adjusted rp3 (`xfp_rp3_per_start_sched`) + venue park adj | `lib.extra_lenses.park_fp_adj` |
| **season/L5 (n)** | realized FP/start + sample size (variance the model can't show) | `boxscore_pitchers.parquet` |
| **bust%** | empirical share of starts < `SP_BUST` | `lib.boom_bust.SP_BUST` |
| **FADJ** | `floor_adjusted_xfp` — H2H risk-docked score; **ranks the board** | `lib.extra_lenses.floor_adjusted_xfp` |
| **Sw%** | SwStr percentile — flags a rich MEAN with weak process | `sp_decline_model` |
| **verdict** | RICH/LIGHT/FAIR + PRIOR/FLOOR-RISK/decline/bust flags | derived |

**Trigger phrases:** "rank the streamers", "best FA start for 7/4", "who should I
stream", "streamer board", "streamer options", "overlay my arms on the streamers".

---

## Why this skill exists

This exact board was rebuilt from scratch **~4 times in one session (2026-07-03)**,
and one rebuild hand-typed a park table that had **ATH backwards** (credited a
pitcher +0.9 FP at the 2nd-worst pitcher park in baseball), which propped up a
wrong "add Eury Pérez over Castillo" recommendation. Codifying it once — behind
the **owner modules** — removes the recurring bug-reintroduction risk. See
`.claude/skills/SKILL_REGISTRY.md`.

**Rule 13 note:** FADJ is a *decision-layer* metric (validated 2026-06-24 floor
model), not a headline projection. The headline number is still rp3; FADJ just
sorts start/stream priority by H2H risk. Never present FADJ as "the projection."

---

## Run it

```bash
# Default: today .. today+2
python scripts/xfp/run_streamer_board.py

# Explicit window (e.g. the last two days of the scoring period)
python scripts/xfp/run_streamer_board.py --start 2026-07-04 --end 2026-07-05

# Persist for downstream skills (daily-edge bundle)
python scripts/xfp/run_streamer_board.py --csv data/research/streamer_board_$(date +%F).csv
```

The engine (`run_streamer_board.py`) is thin: it fetches confirmed probables,
tags ownership via `get_all_teams()` (drops other teams' rostered arms — only
MINE + FA are streamable), joins rp3, and calls the owner modules for every
computed fact. It **owns nothing** — do not add a park table, a cutoff, or a
scoring formula to it.

---

## Reading the board

1. **Rank is by FADJ, not MEAN.** A high MEAN with a RISKY floor tier gets docked;
   a SAFE-floor arm gets credited. This is the "avoid a <5 FP start that loses the
   week" lens.
2. **`verdict` reconciles model vs actuals** (mandated by the lens-merge protocol,
   CLAUDE.md #12):
   - `RICH` = MEAN ≥ 1.5 over season actual → trust actuals more; expect regression.
   - `LIGHT` = MEAN ≤ 1.5 under season actual → model is conservative; sneaky value.
   - `FAIR` = within ±1.5 → number is honest.
   - `PRIOR-not-read` = `marcel_il` suppressed prior (IL returnee like Greene) →
     the START counts toward the cap, but the FP number is not a real read.
   - `FLOOR-RISK` / `SAFE-FLOOR` = the validated mean-vs-floor conflict flag.
3. **Overlay mode:** MINE arms appear inline with FA, so you can see exactly where
   your rostered starts sit vs the streamer market (usually your arms win on their
   own days; the market only helps where a FA MEAN beats all your arms that day).
4. **Always show the full stack** — do not headline a single lens or let a verdict
   flip across turns.

---

## Consumes (owner modules — call, never re-derive)

- `lib.extra_lenses.park_fp_adj` — venue-aware park→FP (VENUE_ERAS ATH/TB guard)
- `lib.extra_lenses.floor_adjusted_xfp` / `floor_lens` / `floor_flag` — H2H floor
- `lib.boom_bust.SP_BOOM` / `SP_BUST` — realized boom/bust cutoffs
- `plv_clone.utils.name_match.resolve_pitcher_id` — collision-safe id
- `app.espn_connector.get_all_teams` — ownership (MINE / FA / other)
- `sp_decline_model.build` — RISING/DECLINE-RISK tier + SwStr percentile

## Part of the `daily-edge` bundle

`roster-verify → pregame-check → streamer-precision-board → stream-the-stack`.
`stream-the-stack` then applies its boom_stack ≥2 filter over the *same* FA pool
this board already surfaced (don't re-fetch).

## When NOT to use

- Need the boom_stack-tier shortlist only → `/stream-the-stack` (thinner, FA-only).
- Weekly cap math / which of MY starts to bench → `/sp-week-plan` + `cap_math`.
- A single arm's deep dive → `/fa-pickup-deep-dive` or `/triangulate`.
