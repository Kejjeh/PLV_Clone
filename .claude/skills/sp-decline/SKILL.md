---
name: sp-decline
description: SP rest-of-season FP DECLINE-RISK board — flags starting pitchers whose results are propped above their whiff/K stuff LEVEL and are likely to regress DOWN, the "catch a Framber before the crater" lens. Complements Stuff+ (mean) and sp-floor (per-start bust). Triggers: "is X declining", "who on my staff is fading", "decline risk", "catch a Framber early", "which of my SPs will regress", "sell-high SP", "is X's good results sustainable".
---

# sp-decline

You are rendering the **rest-of-season DECLINE-RISK** lens. It answers: *which
SPs are likely to see their FP/start regress DOWN over the rest of the season* —
the early-warning board built to catch a Framber Valdez BEFORE his results fully
crater.

Engine: `python scripts/xfp/sp_decline_model.py`
(`--players "A,B"` for a focus list).

## The validated basis (read this — it's why the skill ignores the obvious signal)

Backtest: `data/research/validation_runs/sp_decline_stuff_decay_2026-06-13.md`
(n=23,598 split-day rows, 37.5% material-decline base rate, player-clustered
GroupKFold, partial-r controlling for the to-date FP base — Rule 9).

**The reliable forward-decline predictor is the CURRENT-SEASON whiff/K LEVEL,
NOT the in-season change/decay.**

- `swstr_z_pop` (SwStr% LEVEL) — partial-r **+0.235** over the to-date FP base
- `k_z_pop` (K% LEVEL) — partial-r **+0.234**, full-model AUC **~0.72**
- `velo_recent` (FB velo LEVEL) — partial-r **+0.16** (light third lens)

**REJECTED as noise — do NOT use** (this is the seductive-but-wrong version):
- Within-season recency **deltas** of whiff/K/velo (L21 − to-date): all
  partial-r < 0.05, ΔAUC ≈ 0. "His swing-and-miss is falling off this month"
  does **not** survive controlling for the base rate.
- Contact-quality / xwOBAcon, archetype, and age signals all **failed** too.
- YoY whiff/velo deltas have only ~39% coverage and `d_k_yoy` even flips sign.

Mechanism: a pitcher whose **results to date outrun his whiff/K stuff** is the
one who regresses. The *level* of stuff is exactly what the to-date FP fails to
encode — so it predicts RoS FP **beyond** what current FP shows.

### The vYoY velo flag (supplementary, validated 2026-06-13)

`data/research/validation_runs/velo_signal_2026-06-13.md`. The rejected velo
construct above is the *within-season L21 delta*. **Year-over-year velo loss**
(current cumulative velo vs **prior-season-END** velo) is a *different*,
validated, **leading** decline construct — orthogonal to the velo LEVEL already
in the blend:

- Monotonic forward-FP gradient: gaining ≥+0.5 mph vs last year → **11.32**
  FP/start; losing ≥1.5 mph → **9.44** (−1.9 across the range).
- Bust-risk tilt: partial-r **−0.090** over the whiff/K-level base; OOS bust-AUC
  **beats stuff** *within* the high-Stuff cohort (where stuff alone is ~useless,
  0.519 → 0.561). Velo sees the downside exactly where the mean models are blind.
- Rule-9 honest: it does NOT move the headline (ΔR² +0.006 over the level base) —
  it's surfaced as the **`vYoY` ▼/▼▼/▲ FLAG** only, a conviction/bust tilt, never
  folded into the whiff/K-level score (per `lens_value_add_2026-06-11`).

Flag thresholds: `▼` ≤ −0.7 mph, `▼▼` ≤ −1.5 mph (worst FP band), `▲` ≥ +0.5
(mild tailwind). A DECLINE-RISK arm with `▼▼` is the highest-conviction fade
(propped FP **and** a fading arm); a flagged arm with vYoY ≈ 0 (e.g. Framber,
−0.0) tells you the decline is the K%/whiff *level*, not velo.

### The vIn in-season-drop flag (the gated within-season read)

The decline backtest rejected the *within-season* velo delta — but only because it
pooled noisy 1-start blips. **Conditioned on sample size it is a PEER of YoY.**
Construct = L21 velo vs the pitcher's own **2026 season-peak** (not warmup-confounded
"vs early-season", not self-contaminated "vs to-date"), **gated at ≥75 BF in the L21
window** (≈3 starts):

- < 25 BF (~1 start): partial-r **−0.002** (noise, bust gap *inverts*) — why the
  raw version was rejected.
- ≥ 75 BF (≥3 starts): partial-r **+0.075**, bust **37.0% vs 27.5%** (+9.5pp) — on
  par with YoY. Strongest **before ~August** (a drop needs RoS runway), decays late.

The board prints `vIn` (the mph drop off season-peak) and a ▼/▼▼ flag **only when
≥80 BF** — below the gate it shows `--` rather than a noisy number. It's the
**coverage complement** to YoY: it fires for arms with no 2025 velo (rookies /
post-TJ, where `vYoY` is `--`, e.g. Justin Wrobleski) and for a fresh dip the YoY
line hasn't absorbed yet. Same downside-tilt discipline — a flag, never in the score.

### Two velo composites (deeper-cutoff findings, cutoffs D + E)

The MINE block escalates two ways when the data warrants — both validated in
`velo_signal_2026-06-13.md`:

- **⚠ SEVERE VELO FADE** (cutoff E, the strongest of all): YoY **and** in-season
  drops both firing → forward bust **49.5%** (2.1× the 23.1% no-drop base) and **−2.5
  FP/start** (9.02 vs 11.56). Far beyond either flag alone. This is independent of the
  tier — a STABLE arm whose whiff/K level still supports its FP can still be a SEVERE
  velo fade (early warning *before* the level craters; e.g. Bryan Woo).
- **LOW-VELO TILT** (cutoff D): a drop on a **sub-(pool-)median-velo** (finesse /
  sinker) arm bites ~2× harder (bust +13.3pp vs +5.4pp for high-velo) — no margin.
  Corbin / Civale-class.

Knobs settled by the sweeps: gate **80 BF** (signal/coverage knee; climbs
monotonically to +0.102 at 100 BF); soft flag **−0.5 mph** (where bust *steps*
27%→34%), `▼▼` at −1.5 (FP-severity tail). Absolute mph beats nothing by going
relative-% (+0.075 vs +0.076); a persistence requirement adds nothing over the gate.

### The v2y multi-year flag — the strongest velo construct (cutoff K)

The board's third velo column. **2-year velo Δ (vs 2024 season-end) is the single
most predictive velo construct: partial-r +0.175 vs +0.101 for 1-year.** A sustained
two-season downtrend filters single-year blips and captures genuine aging/erosion.
It's slow (updates yearly) and lower-coverage (needs two prior seasons), so it's a
**high-conviction confirming flag**, not a primary trigger. `v2y v` ≤ −1.0 mph, `▼▼`
≤ −2.0. It also fills a *distinct* coverage gap from YoY: an arm who pitched in 2024,
missed 2025 (TJ), and is back in 2026 has a blank `vYoY` but a live `v2y`.

### Deepest cuts — what they settled (velo_signal_2026-06-13.md §"Deepest cuts")

- **Velo loss is ORTHOGONAL to whiffs** (G): it predicts bust ~34–36% whether whiffs
  fell *or held*. Velo carries information the whiff/K lens doesn't (fatigue/injury
  in contact/command, not Ks) — the mechanistic reason it's non-redundant. **Don't
  dismiss a velo drop just because the strikeouts are holding.**
- **Velo drop AMPLIFIES the propped-FP gap** (I): bites harder when gap>0 (+0.100 vs
  +0.061). A propped-FP arm that's *also* losing velo is the top-conviction fade —
  which is exactly the top of this gap-sorted board.
- **Soft velo floor ~90 mph** (J): sub-90 L21 velo busts 33% vs 8% at 93–95 — the
  level cliff behind the LOW-VELO tilt.
- **Rejected:** normalizing the drop by the pitcher's own velo volatility (H, null) —
  third normalization idea killed after relative-% and warmup-base. Raw mph wins.

## The read: the level-vs-FP GAP

For every 2026 SP (≥5 GS), the engine computes percentiles **within the 2026 SP
pool**:

- `stuff_level_pctl` — combined whiff/K level (SwStr% 0.40 + K% 0.40 + velo 0.20,
  velo light per the backtest; velo drops out where missing)
- `curfp_pctl` — current BrownU FP/start percentile
- `decline_gap = curfp_pctl − stuff_level_pctl` — **large positive = FP propped
  above the whiff/K stuff = decline coming.**

**Tiers** (explicit, defensible):

- **DECLINE-RISK** — `stuff_level_pctl ≤ 45` (below-average whiff/K LEVEL — the
  validated primary gate) **AND** `decline_gap ≥ −10` (FP hasn't already fallen
  *below* the level). Sorted by gap so the most-propped ("hasn't fallen yet")
  arms surface at the top.
- **RISING** — `decline_gap ≤ −20` (whiff/K level well ahead of FP =
  sustainable / buy-low-safe).
- **STABLE** — everything else, including strong-stuff arms whose level supports
  their FP (aces never flag).

Why low-LEVEL is the primary gate, not the gap alone: the *level* is the
validated predictor (partial-r 0.235). A 27th-pctl whiff/K arm is a decline
candidate whether his FP has started falling or not — the gap is the *severity*
dial (still-propped = highest risk), not the on/off switch.

## The Framber 2026 canonical case

Framber Valdez 2026: K% **18.6%** / SwStr% **9.1%** → `stuff_level_pctl ≈ 27`
(below-average LEVEL), while his FP percentile (~39) hadn't fully caught down →
`gap ≈ +12`. He flags **DECLINE-RISK**. Aces stay clean: Skenes (lvl 86), Sale
(79), Skubal (88), Crochet (RISING). This is the exact arm the
`/sp-stuff-board` Stuff+ buy-low would have mis-read as a buy (Stuff+ 103) —
the whiff/K *level* says fade. (See CLAUDE.md "Don't do these" #14.)

## What it outputs

`scripts/xfp/sp_decline_model.py` (default, league-wide):
1. **DECLINE-RISK board** — all flagged SPs, gap-sorted, with ownership tags.
2. **YOUR SP STAFF** — your 9 SPs ranked by decline risk, with a **FADE WATCH**
   line naming any of yours in DECLINE-RISK, plus a **VELO FADE** line naming any
   of yours throwing ≥0.7 mph below 2025 (the leading-flag conviction tilt).
3. **FA DECLINE-RISK** — propped FAs to NOT stream (results won't hold).
4. **RISING** — whiff/K level ahead of FP = sustainable / buy-low-safe.

`--players "A,B"` renders just those, gap-sorted.

## How to read it against the other lenses

| lens | question | tool |
|---|---|---|
| MEAN level | who scores most RoS? | `/sp-stuff-board` (Stuff+) |
| per-START floor | who's least likely to crater tonight? | `/sp-floor` |
| RoS DECLINE | whose results will regress DOWN? | **this** |
| MEASURED variance | who HAS been booming/busting? | `/boom-bust-history` |

This **operationalizes the §2 DECLINE CROSS-CHECK** that `/sp-stuff-board` now
requires before headlining a Stuff+ "buy-low" on a veteran: when Stuff+ says buy
but this board says DECLINE-RISK, the whiff/K level wins → headline
**"DECLINING — back-end, defensible drop, not a buy."**

## Guardrails

- **Single-lens risk board.** It does not headline a point projection — the
  number is rh3/rp3/`/sp-stuff-board` projFP. Feed any flagged name into
  `/triangulate` for the full stack before a drop/hold verdict.
- **`marcel_il` gotcha respected.** This reads live FG SwStr%/K% (and rolling
  velo), NOT the suppressed `marcel_il` rp3 per_start — so IL'd / FA-tier arms
  with a Marcel-prior rp3 still get a real whiff/K read here. Rank by this
  board's level, not rp3, for those.
- **Ownership two-pass.** MINE/opp/FA tags come from a LIVE ESPN call using the
  same full-norm → (last, first-initial) match as `/sp-stuff-board` (never
  last-only — the Cam/Cameron + Logan/Gunnar Henderson gotcha). Tags are omitted
  cleanly when ESPN is offline.
- **Direction, not magnitude.** AUC ~0.72 is good for this target but it ranks
  *risk*, it doesn't quantify the FP drop. "How much will X fall" → not this; it
  says X is in the cohort that regresses.
- **Velo is the light lens — twice over.** As a *level* it's weighted 0.20 in the
  headline blend and drops out where the rolling cache has no 2026 velo. As a
  *year-over-year change* it is the supplementary **vYoY flag** (not in the score):
  a leading decline + bust tilt, not a mean-projection term. Whiff/K still carry
  the headline; velo raises/lowers conviction.
