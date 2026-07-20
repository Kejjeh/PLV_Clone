---
name: sp-form
description: Unified SP form/decline invocation surface with `--lens {breakout|decline|sustainability|shadow}` — four SEPARATELY-VALIDATED engines behind one entry point, never blended into one signal. `--lens breakout` = rolling-window good-start persistence (33k starts, fp_proxy_per_bf ≥ −0.0476; NOISE/WATCH/ACTIONABLE/STRONG/LOCK) — the old /sp-breakout-signal. `--lens decline` = RoS DECLINE-RISK board from the whiff/K stuff LEVEL vs propped FP (the catch-a-Framber-early / ERA-trap lens, with vYoY/vIn/v2y velo flags) — the old /sp-decline. `--lens sustainability` (DEFAULT) = 9-marker Statcast skill decomposition on rp3 with LEGIT→REGRESS buckets + BUY-LOW/SELL-HIGH divergence — the old /pitcher-sustainability. `--lens shadow` = process-grade 20-80 scouting card for SPs with no rp3/archetype row (rookies, callups, post-injury) — the old /shadow-scout. Use for "is X on a hot streak", "should I trust X's recent starts", "X has been dealing lately", any FA SP whose last 3-5 starts are cited as evidence, "is X declining", "who on my staff is fading", "decline risk", "catch a Framber early", "which of my SPs will regress", "sell-high SP", "is X's good results sustainable", "is this monster game real / will rp3's number move", "audit my SP staff for hidden regression risk or buy-low", "is rookie X any good", triangulate blanks on a recently-promoted SP. Merges /sp-breakout-signal + /sp-decline + /pitcher-sustainability + /shadow-scout (2026-07-20).
maturity: unified-sp-form
---

# sp-form — unified SP form lenses (`--lens {breakout|decline|sustainability|shadow}`)

**This is an INVOCATION surface only.** The four lenses are four separately-
validated engines with different calibrations, different targets, and different
failure modes — they are routed from one place but **never blended into one
composite signal**. Each lens's verdict stands on its own; when they disagree,
show the disagreement (Rule 12) and reconcile per
`reference_lens_merge_protocol.md`. All joins by MLBAM pitcher_id
(`resolve_pitcher_id`), never name.

## Pick the lens by the question

| Ask | Lens | Complete recipe lives in | Engine |
|---|---|---|---|
| "is X on a hot streak", "trust his last 3-5 starts?", streamer cited on recent form | **`breakout`** | `/sp-breakout-signal` SKILL.md | `scripts/xfp/run_sp_breakout.py` (codified 2026-07-20 — `--names "A,B"` or default my-roster healthy SPs; tier table worst→best, + Signal A / SigStuff / MODEL-LAG? flags; NEGATIVE outranks NOISE) |
| "is X declining", "who's fading", "will his results hold?", "sell-high SP", "catch a Framber early" | **`decline`** | `/sp-decline` SKILL.md | `scripts/xfp/sp_decline_model.py` |
| "was that monster game real?", "audit my staff for regression risk / buy-low", "FA SP skill confirmation" | **`sustainability`** | `/pitcher-sustainability` SKILL.md | `scripts/xfp/pitcher_sustainability.py` |
| "is rookie X any good", rp3 + archetype both blank, stale archetype vs live Statcast (Ben Brown) | **`shadow`** | `/shadow-scout` SKILL.md | `scripts/xfp/lib/shadow_scout.py` |

**Default when unspecified: `sustainability`** (the general "is the form real"
confidence layer on rp3). Route to `breakout` when the evidence cited is a
run of recent starts; to `decline` when the worry is results outrunning stuff;
to `shadow` when the model rows are blank (rookie / callup / post-injury).

## Why four engines, not one score

- **breakout** is OUTCOME-based (good-start counts, 2018-2025 persistence
  table) — optimized for ADD evaluation, not drops.
- **decline** is LEVEL-based (whiff/K stuff level vs FP percentile, partial-r
  +0.235; in-season *deltas* validated as noise) — a risk board, direction not
  magnitude.
- **sustainability** is a MARKER DECOMP (9 Statcast markers vs prior year) —
  the confidence layer + divergence flag on rp3's number.
- **shadow** is a POPULATION-PERCENTILE card (20-80 grades vs the live ~432-SP
  pool) — fills the gap where rp3/archetype are null; adds noise for
  established SPs.

Their validations are independent; averaging them would launder three distinct
calibrations into an unvalidated composite (Rule 9 / don't-do #1).

## Shared preconditions (all lenses)

1. **`/roster-verify` first** — never label a pitcher "yours" (or FA) from
   session context; FA availability via a live `league.teams` roster scan,
   never percent_owned (Sheehan 2026-05-25).
2. **Id resolution** — `resolve_pitcher_id(name, team=…, role=…)`; role via
   `detect_pitcher_role`, never ESPN `.position` alone (Detmers, gotcha #8).
3. **Rule 13** — every lens is context/conviction on rp3 (or on the Stuff+
   board for `marcel_il` arms). None moves the headline projection; `decline`
   ⚠DEC acts only as the Tier-B one-step verdict downgrade.
4. **Rule 12** — when lenses disagree (canonical: Stuff+ "buy-low" vs decline
   DECLINE-RISK → headline DECLINING, don't-do #14), show the full stack and
   the reconciliation; never flip silently.
5. **marcel_il gotcha (#1)** — `decline` and `shadow` read live data, so IL'd /
   FA-tier arms with suppressed Marcel rp3 rows still get a real read here;
   rank those by Stuff+ `proj_ros_fp`, not rp3.

## Relationship to the other pitcher skills

- **`/rp-decline` and `/rp-archetype` stay standalone** — the RP seam
  (save/hold leverage context, rprs2 ranking) is deliberately separate; none of
  these four lenses is validated for relievers. Cross-link there for any RP
  form question.
- `/sp-stuff-board` (Stuff+ mean) and `/sp-floor` (K−BB per-start bust) are the
  companion single-lens boards; `sustainability`/`decline` are their mandatory
  decline cross-checks before any veteran "buy-low" headline.
- `/sp-board` is the joined decision board that CONSUMES these lenses as
  columns; `/triangulate` is the per-player synthesis card.
- `/sp-archetype` = process-based career profile; `breakout` here is its
  outcome-based complement — use both for the highest-confidence call.

**Deprecation note:** `/sp-breakout-signal`, `/sp-decline`,
`/pitcher-sustainability`, and `/shadow-scout` remain as aliases holding the
complete recipes; new invocations should use `/sp-form --lens
{breakout|decline|sustainability|shadow}`.
