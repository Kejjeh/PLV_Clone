---
name: form-check
description: Master meta-skill for the FORM-CHECKS domain — one command that sweeps form/sustainability across the whole roster (optionally FA pool) in both directions. Chains sp-form across its four lenses (breakout / decline / sustainability / shadow) over my SPs → hitter-form --scope roster (+ --lens career) over my hitters → routes every RED/YELLOW flag to the standalone deep-dives (/slump-or-decline for downside, /breakout-sustainability for upside) as a follow-up list. Use when the user asks "form check everyone", "who's trending the wrong way", "full form sweep", "sustainability check on my roster", or after a rough/hot week wanting to know what's real. Context/confidence layer (Rule 13) — flags set conviction and route to deep-dives; they never re-rank rh3/rp3/rprs2.
---

# form-check

The form-domain master: every validated form lens, whole roster, one pass.

1. **SP side — `/sp-form`, all four lenses** over my healthy SPs:
   `--lens sustainability` (9-marker confidence), `--lens decline`
   (SwStr/K LEVEL + velo; STUFF-DECLINE vs COMMAND-WATCH tagging),
   `--lens breakout` (NOISE→LOCK hot-streak validity), `--lens shadow`
   (process card for arms with no rp3/archetype row). RPs: `/rp-decline`
   role-loss watch appended (RP seam stays separate).
2. **Hitter side — `/hitter-form --scope roster`** (9-marker sustainability
   sweep) + `--lens career` (L150 career-percentile position). Add
   `--scope fa` when the ask includes the pool.
3. **Route the flags** — hitters: RED/DOWN → `/slump-or-decline`, hot →
   `/breakout-sustainability`. SPs/RPs: ALL flags (either direction) →
   `/triangulate` (the SP deep-dive route; QA 2026-07-20). List them; run
   the deep-dives only for names the user confirms (they're long).
   Note: the breakout lens is an inline recipe (no engine script) — follow
   sp-breakout-signal's SKILL.md steps; NEGATIVE outranks NOISE when tiers
   conflict. Rookie caveat: STUFF-DECLINE requires a real prior-year sample
   (memo #11) — never auto-fire it from the in-season split alone.

## Pull-once contract

One roster pull tags MINE; the lens engines read cached stores (statcast,
archetype panels, sustainability CSVs) — no per-lens ESPN traffic.

## Output format

```markdown
# Form check — <date>
## SP (one row per SP × worst-lens flag, sorted worst-first)
## RP (role-loss watch)
## Hitters (sustainability + career-pct, sorted worst-first)
## Deep-dive queue (downside → /slump-or-decline; upside → /breakout-sustainability)
## Stable (one line — who's clean across every lens)
```

## Hard rules

1. **Rule 13 everywhere** — every lens here is display/context; headline
   numbers stay rh3/rp3/rprs2. Trajectory is NON-predictive for SP
   projection (validated 2026-06-24): a cold run is a floor_adj/context
   fact, not a drop reason.
2. Drop talk requires the deep-dive first (never from a sweep row alone —
   the xwOBA-L21d + YoY xwOBACON check lives in /slump-or-decline).
3. STUFF-DECLINE vs COMMAND-WATCH tags print with their canonical meaning
   (structural sell vs reversible hold-watch).

## When NOT to use

- One player's form → `/sp-form --lens X <name>` or `/hitter-form --scope
  player <name>` directly.
- League-wide (not roster) sweeps → `/hitter-form --scope league`,
  `/conviction-scan`.
- Deciding between specific players → `/player-verdict`.
