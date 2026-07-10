---
name: stream-the-stack
description: Daily ranked FA SP streamer recommender filtered by boom_stack tier. Surfaces stack=2+ candidates from confirmed probables in the next 3 days, intersected with the league FA pool (Connelly-Early verified), with rp3 projection + variance band + opponent matchup. Use Monday-Friday mornings before lineup lock, or whenever the user asks "stream the stack", "boom stack streamers", "find me boom shots", or "best streamer adds today".
---

> **⚠ MERGED (P1, 2026-07-10) → `/streamer-precision-board --filter boom>=2`.** This
> SKILL is the boom-stack streamer recipe and stays live as the delegate; kept as
> alias. New invocations should prefer `/streamer-precision-board --filter boom>=2`
> — the precision board now carries the boom_stack column (live via
> `lib.boom_stack.compute_boom_stack`, tier-aware boom%, ⚠spike-anti flag) over the
> same confirmed-probables ∩ FA universe, with FADJ ranking within the shortlist.

# stream-the-stack

You are running the daily boom-stack streamer scan. The goal: surface FA SPs
who (a) actually have a confirmed start in the next 3 days, (b) are actually
available in the user's league, and (c) carry a boom_stack tier of 2+ —
where the historical right-tail rate is materially above the 9.7% baseline.

This skill exists because finding boom-stack streamers manually requires
one `/triangulate` call per name. This skill does it in bulk.

---

## What boom_stack means

**boom_stack ∈ {0, 1, 2, 3, 4}** — four independent components, each 0 or 1
(park_friendly added as 4th component 2026-06-03):

1. **skill_spike** — last-3-starts K% − season K% ≥ +3pp AND last-3-starts
   BB% − season BB% ≤ −1pp (requires ≥3 prior starts).
2. **recform_hot** — `recency_form_gap ≥ +3.0` from the rp3 row.
3. **opp_soft** — today's opponent `bat_index_recent` ≤ 33rd-percentile (soft slate).
4. **park_friendly** — today's venue is in the pitcher-friendly tier of the
   2026 park-factor table. Validated 2026-06-03 across tiers.

**Tier-aware thresholds** — boom rates compound differently by rp3 rank:
ace (rank 1-10) at stack=3 hits 56.7% boom; sp2_sp3 (11-30) 31.2%;
backend (31-50) 21.5%; streamer (51+) 17.4%. Tier-specific tables are
encoded in `BOOM_RATE_BY_TIER_STACK` in `scripts/xfp/lib/boom_stack.py`.

**Anti-predictive caveat:** at backend / sp2_sp3 tiers, `skill_spike` has
NEGATIVE per-component lift (regression-predictive, not boom-predictive).
The script flags this when the report renders.

For component-level decomposition on a single SP, hand off to
`/boom-stack-explain <name>`.

Validated 2026-06-03 (n=12,713 streamer starts, 2018-2025). Boom rate (FP≥20):

| stack | boom rate | mean FP |
|---|---|---|
| 0 | 9.70% | 8.44 |
| 1 | 12.08% | 9.62 |
| 2 | 13.62% | 9.92 |
| 3 | 17.41% | 10.14 |

Chi² (low ≤ 0 vs hi ≥ 2) = 25.25, p < 0.0001. See
`reference_boom_stack_tag.md` for the full validation report.

**boom_stack is a DISPLAY TAG**, not a verdict override. The point estimate
remains `xfp_rp3_per_start`. boom_stack is the right-tail confidence layer.

---

## The sp-decline trap filter (the ERA-trap guard)

A streamer can be **tempting by results** (low ERA / good recent box score) but
propped above his actual whiff/K stuff — the moment you add him, he regresses.
This is the Holmes/Keller/Ober pattern. The validated `/sp-decline` lens catches
it before the add.

The script joins the **sp-decline** tier (engine: `sp_decline_model.build()`,
keyed on MLBAM) onto every candidate as a `decline` column:

- **`⚠ PROPPED`** — sp-decline **DECLINE-RISK**: below-average whiff/K stuff LEVEL
  (`stuff_level_pctl ≤ 45`) with FP still propped above it. Validated 2026-06-13
  (`sp_decline_stuff_decay_2026-06-13.md`, partial-r ~0.235 on the whiff/K LEVEL).
  **When this fires, the per-candidate verdict is hard-capped at
  "do NOT stream/add despite the line"** even if boom_stack ≥ 2 — the boom tag is
  right-tail variance, but the central tendency is regressing DOWN.
- **`RISING`** — whiff/K level is well ahead of FP (sustainable / buy-low-safe).
- **`—`** — STABLE or not in the 2026 SP pool (< 5 GS).

**It is a context/risk flag, NEVER a headline mover** (CLAUDE.md #13). `rp3` still
carries the point estimate and boom_stack still carries the right-tail. sp-decline
only vetoes the *verbal recommendation* so an ERA trap doesn't get streamed. The
console prints an explicit `⚠ sp-decline PROPPED` line naming every propped
candidate; the lens is fail-soft (if the FG cache is missing / offline, streamers
still rank — the `decline` column just shows `—`).

For a full decline-board read on a propped name, run `/sp-decline --players "X"`.

---

## Workflow

This script runs **automatically** as step 4.6 of `refresh_dashboards.py`
(daily refresh). The latest report is always at
`data/outputs/stream_the_stack_<today>.md` after the morning refresh.

For ad-hoc reruns (e.g., probables updated mid-morning, or you want a
different window):

```bash
python -X utf8 scripts/xfp/stream_the_stack.py
```

Optional flags:
- `--days N` — change the forward window (default 3 = today through today+2).
- `--min-rp3 X` — drop candidates below an rp3-per-start floor (default: no floor).

Outputs written to `data/outputs/`:
- `stream_the_stack_<YYYY-MM-DD>.md` — human-readable ranked report
- `stream_the_stack_<YYYY-MM-DD>.json` — machine-readable sidecar (per-candidate
  diagnostic, including per-component boom detail)

Console summary prints the stack=2+ list directly.

---

## What the script does

1. Fetches MLB Stats API confirmed probables for the next N days
   (rotation-gap predictions are intentionally NOT used — streamers
   need confirmed starts).
2. Pulls the league FA pool via `league.free_agents(size=2000)`, filters
   to SPs.
3. **Connelly Early cross-check**: drops anyone appearing on another team's
   roster (via `get_all_teams()`), regardless of percent_owned.
4. Resolves each FA name to MLBAM via `sp_multiyr_2015_2025.csv`. The
   resolver handles both "Last, First" (cache format) and "First Last"
   (ESPN format) by normalizing both sides.
5. Intersects FA SPs ∩ confirmed probables → "FA SPs starting in window".
6. For each, joins rp3 (`xfp_rp3_per_start`, p25/p75, `recency_form_gap`,
   `data_quality_tag`, rank, signal) + team_strength bat_index_recent.
7. Computes `boom_stack` live via `scripts.xfp.lib.boom_stack.compute_boom_stack`.
8. Joins the **sp-decline** tier (`sp_decline_model.build()`, by MLBAM) → adds a
   `decline` column + `decline_propped` flag. DECLINE-RISK candidates get a hard
   ⚠ PROPPED verdict cap (do-not-stream) regardless of stack tier. Fail-soft.
9. Ranks: boom_stack desc → rp3 desc → percent_owned asc.
10. Renders markdown + JSON.

---

## Output sections

- **STACK=3 candidates (BOOM SHOTS)** — all 3 components lit. Rare.
- **STACK=2+ candidates** — high-leverage boom shots, preferred play of the day.
- **STACK=1 candidates** — modest edge, usable streamers.
- **STACK=0 omitted entirely** — at or below baseline boom rate.

If no stack=2+ candidates exist today, the report notes this is expected
(stack=2+ is ~10% of the streamer pool — most days surface 0-2 candidates).

---

## When to invoke

- **Monday-Friday mornings** before lineup lock (most actionable window).
- After a roster move that frees an SP slot — confirm there's a boom shot
  worth burning the slot on TODAY before committing.
- When the user asks "best streamer today" / "any boom shots" / "stack=2+ today".
- The script is wired into `refresh_dashboards.py` as step 4.6 (fail-soft),
  so the latest report is regenerated every daily refresh.

---

## Anti-patterns this skill exists to prevent

- **Recommending a stack=0 SP as a "stream"** — by definition at/below
  baseline. The skill omits these from the report.
- **Recommending a PL-ranked streamer without ESPN roster verification.**
  Connelly Early bug — `get_all_teams()` cross-check is mandatory.
- **Using rotation-gap predictions for streamer decisions** — too noisy.
  Confirmed probables only.
- **Treating boom_stack as a point-estimate booster.** It isn't. boom_stack
  shifts right-tail mass. rp3 is still the headline projection. A stack=3
  with rp3=6.0 is a high-variance lottery ticket, not an "expected 17 FP".
- **Streaming an ERA-trap arm whose stuff doesn't back the results.** A good
  recent line can be propped above the pitcher's whiff/K LEVEL → it regresses
  the moment you roster him (Holmes/Keller/Ober pattern). The `decline` column's
  ⚠ PROPPED flag (sp-decline DECLINE-RISK) catches this — heed the do-not-stream
  verdict cap even when boom_stack ≥ 2.

---

## Complementary skills

- `/boom-stack-explain <name>` — decomposes WHY a specific SP's stack
  value is what it is (component-by-component, tier context, anti-
  predictive flags). Use whenever the user asks "why is X's stack 2/4".
- `/triangulate <name>` — after this skill flags a stack=2+, run triangulate
  to get the full archetype + PL rank + verdict synthesis context.
- `/fa-sp-pool` — broader FA SP scan ranked by PL Top 100 (not by boom_stack).
  Use for season-long rosterables; stream-the-stack is for THIS WEEK's adds.
- `/sp-week-plan` — once you've added the streamer, confirm it doesn't push
  you past the 10-SP-start weekly cap.
- `/sp-decline` — the propped-results risk board this skill's `decline` column
  is sourced from. Run `/sp-decline --players "X"` for the full whiff/K-LEVEL
  decomposition behind any ⚠ PROPPED flag.
