---
name: boom-stack-explain
description: Decompose any player's current boom_stack tag into components — explains WHY the stack value is what it is and what the user should do. Use when user asks "why is X's boom_stack 2/4" or "what's driving this tag" or "decompose this projection."
---

# /boom-stack-explain

## Purpose

Decompose a single player's current `boom_stack` tag into its component
signals so the user understands **why** the stack value is what it is —
not just that it's "3/4." Surface which sub-signals fired, which didn't,
the underlying number vs the threshold, and translate the stack tier
into actionable boom%/bust%/mean-FP expectations.

This is **explanatory**, not predictive. `boom_stack` is a probability
shift over the rp3 (or rh3) baseline — it does NOT replace the headline
projection.

## Trigger phrases

- "why is X's boom_stack 2/4"
- "what's driving this stack tag"
- "decompose X's boom_stack"
- "explain X's stack"
- "what does 3/4 mean for X"
- "boom_stack components on X"

## Workflow

### 1. Resolve player

Use `plv_clone.utils.name_match.resolve_batter_id` (hitters) or the
equivalent SP/RP resolver. Refuse to guess on same-name collisions
(Max Muncy LAD vs ATH pattern). Confirm team + position with user
if ambiguous.

### 2. Determine bucket

- **H** → run hitter branch
- **SP** → run SP branch
- **RP** → bail: boom_stack does not apply to RPs yet. Recommend
  `/triangulate` for the RP role/leverage view instead.

### 3. SP branch

Pull the player's `boom_stack` row from the current matchup dashboard
inputs or call `compute_boom_stack(pitcher_id, game_date)` directly.

Print **each of the 4 components** with status, value, threshold:

| Component | Status | Value | Threshold (tier-adjusted) |
|---|---|---|---|
| skill_spike (5g window) | FIRED / not | e.g. K-BB% Δ +4.2pp | tier-specific |
| recform_hot | FIRED / not | last-3 fp_proxy | tier-specific |
| opp_soft | FIRED / not | opp wRC+ vs L/R | tier-specific |
| park_friendly | FIRED / not | park HR factor + temp | tier-specific |

Then:

1. **Tier lookup** — is this an ace / sp2_sp3 / backend / streamer? Print the tier and the tier-specific thresholds used.
2. **Stack tier → outcome** — look up per-tier boom%/bust%/mean FP at this stack value (from validation registry).
3. **Standalone tags** — print whether HIGH-K ARM, catcher_framing (when shipped), or any anti-predictive skill_spike warning is active.
4. **Verdict** — one sentence: LOCK IT / CONSIDER / FADE. The verdict is the rp3-conditioned read with the boom_stack shift applied, NOT the headline number.

### 4. Hitter branch

Pull the hitter's `boom_stack_hitter` row.

Print each component:

| Component | Status | Value | Threshold |
|---|---|---|---|
| skill_spike_hitter | FIRED / not | xwOBACON Δ or bat-speed Δ | threshold |
| recform_hot_hitter | FIRED / not | L7d FP/g | threshold |
| opp_soft_hitter | FIRED / not | opp SP rp3 percentile | threshold |
| lineup_amp (when shipped) | FIRED / not | lineup spot 1-5 + on-base around | threshold |

Then same tier/outcome/verdict structure as the SP branch.

### 5. RP branch

Bail with: "boom_stack is not defined for RPs. For role/leverage
context use /triangulate, for save-share context use /fa-rp-pool."

## Anti-patterns

- **Don't treat boom_stack as a forecast.** It's a probability shift,
  not a prediction. The headline number is still rp3 (SP) or rh3 (H).
- **Don't compare stack values across tiers.** A 3/4 on a streamer
  means something different from a 3/4 on an ace — tier-aware
  thresholds were designed precisely to keep stack values comparable
  in *probability-shift* terms, not in *raw quality* terms.
- **Don't fire on a single component.** Stack=1/4 is noise; the
  validated boom signal kicks in at stack ≥ 2 (SP) — see registry.
- **Don't run this skill to rank players.** Use /triangulate or
  /stream-the-stack for ranking. This skill is decomposition only.

## When NOT to use

- Ranking or comparing players → /triangulate, /hitter-compare,
  /stream-the-stack
- Forecasting next start → rp3/rh3 directly
- Roster-wide audit → /roster-health
- "Should I pick X up?" → /fa-pickup-deep-dive

## References

- `docs/architectural_lessons_2026-06-03.md` — design rationale for
  tier-aware thresholds, σ rescale, anti-predictive guard
- Validated signals registry — per-tier boom%/bust%/mean-FP lookup
  tables
- `docs/architectural_lessons_2026-06-03.md` — skill_spike 3g→5g
  flip rationale, park_friendly addition, HIGH-K ARM standalone tag

## Example output sketch

```
PLAYER: Joe Pitcher (SP, ATL) — tier: sp2_sp3
boom_stack = 3/4 vs MIA on 2026-06-04

  [X] skill_spike (5g)   K-BB% +5.1pp     threshold +3.0pp   FIRED
  [X] recform_hot        last-3 fp 21.3   threshold 18.0     FIRED
  [X] opp_soft           MIA wRC+ vs R 84 threshold ≤90      FIRED
  [ ] park_friendly      loanDepot HR 0.92, 73°F             not fired

  Tags: HIGH-K ARM (K/9 ≥ 10.5 L30d)

Tier outcome lookup (sp2_sp3, stack=3):
  boom%: 38%  bust%: 14%  mean FP: 22.7  (baseline rp3: 18.9)

Verdict: LOCK IT. Three components fired, sp2_sp3 stack=3 has
historically converted at 38% boom rate, and HIGH-K provides
floor protection.
```
