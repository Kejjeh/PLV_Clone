---
name: rp-decline
description: RELIEVER role-loss / FP-crater CONVERGENCE WATCH board — flags relievers whose velo is declining YoY AND whose skill or role-share is slipping, the "is my closer about to lose the job" lens. Honestly weaker/noisier than /sp-decline. Triggers: "is my closer fading", "RP role risk", "will X lose the job", "sell-high reliever", "is my closer about to lose saves", "which of my RPs is declining", "should I sell my closer".
---

# rp-decline

You are rendering the **reliever role-loss CONVERGENCE WATCH** lens. RP fantasy
value is opportunity-dominated (rprs2 r≈0.87 vs rp3 0.55 — saves/holds are the
ROLE, not per-batter skill), so the decline that matters for an RP is a **role
crater**, not rate regression. This board flags the relievers most at risk of
losing the role that carries their FP.

Engine: `python scripts/xfp/rp_decline_model.py`
(`--players "A,B"` for a focus list).

## The validated basis (read this — it shapes the whole signal)

Two backtests, both 2026-06-13, both player-clustered GroupKFold with incremental
partial-r over an rprs2-style base (Rule 9), leakage-checked by split-day:

**1. `rp_decline_stuff_velo_2026-06-13.md` — velo DECLINE is the stuff signal.**
- **`velo_DECLINE_yoy`** (current cumulative velo vs **prior-season-END** velo) is
  the strongest *stuff* predictor of RP RoS-FP decline: **partial-r +0.112**
  [+.052, +.166], full-fit coef +0.168 (velo drop → decline). It **survives**
  even when the base also holds K/SwStr/velo LEVEL (partial-r +0.092).
- This **REVERSES the SP finding** (`/sp-decline`: whiff/K **LEVEL** +0.235, velo
  weak). For RPs it is specifically the **radar-gun DROP** — `swStr_DECLINE_yoy`
  (+0.033) and `k_DECLINE_yoy` (+0.020) are **n.s.**, and velo **LEVEL** alone is
  weak (+0.064). Max-effort one-inning arms have no pace-managing fallback, so a
  velo drop is the louder alarm. `xwoba_LEVEL` (−0.107) is the best contact-quality
  companion (a velo-decline + soft-xwoba pairing is the cleanest RP decline duo).
- **Caveats the report insists on:** modest magnitude (~half the SP signal), only
  **56% coverage** (needs a prior MLB season of velo), and it's NOT promoted —
  it's a **Tier-B conviction/conflict gate**, not an rprs2 driver.

**2. `rp_decline_role_leverage_2026-06-13.md` — role loss is the MECHANISM.**
- A reliever who **loses his role** (RoS save+hold share ≥40% below to-date)
  craters from **4.01 → 2.49 FP/app (−38%)**. Role is where RP FP lives.
- **But the role TREND barely predicts** (ΔAUC +0.013, and the headline trend
  `sv_share_trend` is a late-season **leakage artifact** — do NOT use it as a
  standalone point term). Role loss itself is only **AUC 0.683 — ~1/3 of the
  signal is manager-driven noise** (a coach yanking a closer, a deadline trade).
  **You cannot front-run role loss reliably; you can only tilt the odds.**
- **Skill markers predict role-loss BETTER than the role trend** (skill-only AUC
  0.652 vs role-trend 0.604). The causal chain is sequential, not competing:
  **skill/velo erosion → manager strips the role → FP craters.** The **ONLY**
  configuration that materially beats the base is the **two-lens CONVERGENCE**:
  eroding velo/skill **AND** early role-share slippage (AUC 0.683 vs role-state-
  only 0.576).

## The signal = CONVERGENCE WATCH (not a confident point predictor)

The board computes three **legs** per RP and tiers on their convergence:

- **V (velo)** — velo declining YoY vs 2025 season-end (`▼` ≤ −0.8 mph, `▼▼` ≤
  −1.5; `▲` ≥ +0.5 = tailwind). The validated **primary** leg.
- **S (skill)** — whiff/K **LEVEL** weak (≤ 40th pctl of the 2026 RP pool) **or**
  contact-quality soft (xwoba-against ≥ 60th pctl). The leading indicator of role
  loss. (YoY skill *deltas* were n.s., so this is a LEVEL read — leakage-safe.)
- **R (role)** — recent sv+hld share ≥25% below to-date, **and** the arm actually
  had a role (to-date sv+hld/app ≥ 0.12). The early mechanism. (Uses the as-of
  recent vs to-date SHARE, **not** the leakage-prone trend term.)

**Tiers** (explicit, defensible):

- **ROLE-RISK** — `V` **AND** (`S` **OR** `R`) **AND has a role to lose** (to-date
  sv+hld/app ≥ 0.12). This is the only config validated to beat base. A `middle`
  mop-up arm with no leverage opportunity **cannot** suffer a role-loss crater, so
  it never reaches ROLE-RISK (drops to WATCH) — the thesis is about closers/setups.
- **WATCH** — one leg firing (or velo+skill converged but no role to lose). A fade
  to monitor; not yet a role-loss setup.
- **NA-VELO** — **no 2025 velo, so the primary signal can't fire.** This is **NOT a
  clean bill of health** — it's marked NA, never false-SECURE'd. If a secondary leg
  also fires it's bumped to WATCH.
- **SECURE** — velo stable/up and skill+role intact.

## Honest confidence — this is weaker + noisier than /sp-decline

The skill text and the engine header both say this out loud, deliberately:

- velo-decline **+0.112** here vs SP whiff/K-LEVEL **+0.235** there — **about half
  the signal**.
- role loss is **~1/3 manager-driven** (AUC 0.683) and only modestly forecastable
  from the pitcher's own line. **~32% of the gap to perfect is irreducible** —
  much of role loss is the manager, not the arm.
- velo coverage is only **~56%** (needs a prior MLB season) — rookies / post-TJ /
  first-year arms land in **NA-VELO**.

So this is a **conviction / watch gate, NOT a confident call.** Treat a ROLE-RISK
flag as "the odds of a role-loss crater are tilted up — verify and size bets
accordingly," never as a prediction the closer *will* lose the job.

## What it outputs

`scripts/xfp/rp_decline_model.py` (default, league-wide):
1. **ROLE-RISK board** — league-wide converged arms (V + S/R, has-role),
   tier→legs→velo-sorted, with ownership tags.
2. **YOUR RP STAFF** — your RPs ranked by convergence, with a **ROLE-RISK WATCH**
   line, a **VELO FADE** line (primary leg only, role/skill not yet converged),
   and an **NA-VELO** line (primary signal blind — not a clean bill).
3. **FA ROLE-RISK** — fragile-role FAs to NOT chase for saves.

`--players "A,B"` renders just those.

## How to read it against the other lenses

| lens | question | tool |
|---|---|---|
| RP RoS value (HEADLINE) | who scores most RoS? (role/opportunity) | **rprs2** (`/triangulate`) |
| role-loss DECLINE risk | whose role/FP is likely to crater? | **this** |
| skill-confirmation | is the rp3 number backed by stuff? | `/pitcher-sustainability` |
| measured variance | who HAS been booming/busting? | `/boom-bust-history` |
| FA closer opportunity | who's gaining a role? | `/fa-rp-pool` |

## Guardrails

- **Headline stays rprs2.** Per CLAUDE.md #13, the lens stack is **not** additive
  point-forecast lift — this is a **Tier-B conviction/conflict gate only** and
  **NEVER moves** the rprs2 role/opportunity headline. Feed any flagged name into
  `/triangulate` for the full stack before a sell/hold/drop verdict.
- **Single-lens risk board.** It ranks role-loss *risk*; it does not quantify the
  FP drop. "Will my closer lose the job" → it tilts the odds, it does not decide.
- **NA-VELO ≠ SECURE.** No prior-season velo means the validated primary signal is
  blind — the arm is shown NA, never quietly cleared.
- **Ownership two-pass.** MINE/opp/FA tags come from a LIVE ESPN call via the same
  full-norm → (last, first-initial) match as `/sp-stuff-board` (never last-only —
  the Cam/Cameron + Logan/Gunnar Henderson gotcha). Tags omit cleanly when ESPN is
  offline.
- **Role label vs role STATE.** The board's `role` column is the prior-year
  `role_lag1` label and can be stale; the ROLE-RISK gate uses the **current
  to-date sv+hld SHARE**, matching the report's "had a role to lose" definition —
  trust the gate, not the label.
- **Manager noise is real.** Accept the irreducible ~1/3. A SECURE closer can still
  lose the job to a trade or two blown saves; a ROLE-RISK arm can hold it all year.
  This shifts probabilities, it does not foretell.
