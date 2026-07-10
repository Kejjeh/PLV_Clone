---
name: consensus-diff
description: Ours-vs-MARKET divergence board — our validated models (rh3/rp3/rprs2 rate x volume RoS totals) against the external projection consensus (Steamer / ZiPS / ATC / FanGraphs Depth Charts rest-of-season, snapshotted daily in data/research/fg_proj_cache/). Per player - consensus mean + spread + n_systems, within-role z-scored divergence, and a VOLUME-vs-RATE decomposition (is the disagreement about playing time or about the rate?). WE'RE-HIGHER = buy-before-the-market-catches-up watch (or our-model-wrong watch); WE'RE-LOWER = sell-high / second-look list. Ownership-tagged (MINE / opp / FA), with a reality-check-my-roster section. Use when the user asks "what does Steamer/ZiPS think", "consensus check", "are we out on a limb on X", "market check on X", "where do we disagree with FanGraphs", "who does the market like more than we do", "consensus diff". Rule 13 — divergence NEVER moves rh3/rp3/rprs2; it routes attention to /triangulate. Engine scripts/xfp/run_consensus_diff.py.
---

# consensus-diff

The market-divergence board: where our validated models and the FG projection
consensus disagree, sorted by within-role z. The sibling of `/conviction-scan`
(ours-vs-PROCESS); this is ours-vs-MARKET. Agreement = conviction;
disagreement = the row worth a second look.

```bash
python scripts/xfp/run_consensus_diff.py                 # H + SP + RP, live ownership
python scripts/xfp/run_consensus_diff.py --role sp --top 8
python scripts/xfp/run_consensus_diff.py --no-espn       # skip the ESPN walk
```

Outputs: console boards + `data/outputs/consensus_diff.csv` +
`data/outputs/consensus_diff.html`.

## What each row carries

- **ours** — the validated rate x volume RoS total (hitter `xfp_rh3_per_pa`
  x volume model x team games remaining; SP `xfp_rp3_per_start` x GS-volume
  model; RP `xfp_rprs2` `xfp_ros` directly).
- **cons ± spread (n)** — mean/std of the systems' precomputed BrownU-FP RoS
  totals across whichever systems cover the player (Steamer covers ~everyone;
  ZiPS/ATC/DC only ~600-750 rostered-ish players — n=1 rows are Steamer-only
  and noisier).
- **z** — (ours − cons_mean) z-scored within the H / SP / RP bucket.
- **decomposition** — the genuinely novel readout. log(ours/cons) =
  log(vol ratio) + log(rate ratio): **VOLUME** = "we think he plays
  more/less" (role, lineup, IL-return timing — a different claim than
  talent); **RATE** = "we think he's better/worse per PA / per start";
  MIXED in between. n/a for RPs (rprs2 is a direct-total model) and for
  FG swing-man rows where vol x rate can't reconstruct their total.

## Reading it

1. **Calibration line first.** Our volume model is conditional-on-availability,
   so it sits systematically below FG's healthy-return assumption
   (bucket-median vol ratio ~0.85-0.9). Read a player's ratios RELATIVE to the
   bucket median — vol x0.59 on Acuña (IL) is a real availability claim;
   vol x0.85 on a healthy regular is just the systematic offset.
2. **WE'RE-HIGHER** — our model is ahead of the market. Rule-13 honesty: this
   is EITHER a buy-early edge OR our model being wrong — check the row's
   flags (`MARCEL` rows are excluded from boards entirely; `NO-VOL` = flat
   fallback) and route through `/triangulate` before acting. FA rows here are
   the buy-before-the-market-catches-up surface.
3. **WE'RE-LOWER** — the consensus likes him more. On MINE rows this is the
   sell-high / am-I-fooling-myself list; on FA rows it's a second-look
   (the market may know about a role/health change our inputs lag on).
4. **RP divergence is mostly SAVES.** rprs2 knows live closer roles; FG
   projects saves conservatively — Helsley/Díaz-class gaps are usually our
   role-read vs their role-agnosticism, not a rate disagreement.
5. marcel-suppressed rp3 rows (a prior, not a model read) are CSV-only,
   flagged `MARCEL`.

## Rules

1. **Rule 13** — divergence NEVER moves rh3/rp3/rprs2 and never re-ranks.
   Headline number stays the model. This board only routes attention.
2. Route every actionable row through `/triangulate` (full lens stack) first;
   hitter drop candidates still need the xwOBA-L21d + xwOBACON-YoY pre-check.
3. **Ensemble feature is NOT validated.** Blending consensus INTO the models
   is a separate `/validate-feature` study that unlocks once ~4 weeks of
   daily FG snapshots have accumulated (**≈2026-08-06**, snapshots began
   2026-07-09). Until then this skill is display/conviction layer only.
4. Ownership is a live `get_all_teams()` walk with team-hint disambiguation
   for same-name collisions (Muncy class); `CHECK` rows must be verified
   live before any claim.

## Owners consumed

`data/research/fg_proj_cache/` (daily FG RoS snapshots, refresh step 4.11) ·
`xfp_rh3/rp3/rprs2` + `xfp_volume` / `xfp_sp_volume` (our side) ·
`get_all_teams` (ownership). Sibling: `/conviction-scan` (process divergence)
· `/volume-watch` (our own volume vs naive pace).
