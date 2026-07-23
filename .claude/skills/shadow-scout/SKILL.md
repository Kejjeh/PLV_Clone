---
name: shadow-scout
description: ALIAS → /sp-form --lens shadow. Recipe lives below; routing/triggers live on the canonical.
---

> **⚠ MERGED (2026-07-20) → `/sp-form --lens shadow`.** This SKILL holds the
> complete shadow-scout recipe (20-80 grades vs the live SP population,
> verdict table) and stays live as the delegate; new invocations should prefer
> `/sp-form --lens shadow` (routing + trigger phrases live on the canonical).

# shadow-scout

You are filling in the missing process layer for a starting pitcher whose rp3
and archetype lookups both return blank — usually a rookie, recent callup, or
post-injury return with insufficient sample for either career-anchored model.

## Why this skill exists

The 2026-06-04 PL universe sweep surfaced 21 SPs with no rp3 and no archetype
row but valid PL ranks (Henderson, Sasaki, Imai, Drohan, Abel, etc.). The
triangulate engine printed "no convergence" for all of them — useless for
roster decisions. The shadow-scout lens uses their live 2026 MLB Statcast
(once they cross 200 pitches) and grades against the 432-SP population.

It also recovers signal when the archetype panel is wrong: Ben Brown was
labeled CAREER_LOW / GENERIC_HR_PRONE because the panel is annual-aggregated
and trails by ~6 weeks; the shadow lens says **PLUS_PROCESS** (61 avg grade,
96.6 mph velo, 26.4% K%, 28.2% CSW). Andrew adding Brown 2026-06-04 made
sense once the shadow lens confirmed his stuff.

## Engine

`scripts/xfp/lib/shadow_scout.py`

```python
from scripts.xfp.lib.shadow_scout import shadow_scout, format_card
for card in shadow_scout(['Logan Henderson', 'Roki Sasaki', 'Ben Brown']):
    print(format_card(card))
```

CLI also works:

```bash
python -X utf8 scripts/xfp/lib/shadow_scout.py "Logan Henderson" "Roki Sasaki"
```

## What the verdict means

| Verdict | Avg grade | Read |
|---|---|---|
| **PLUS_PROCESS** | >=60 | Top-quartile process across most metrics; treat as a hold/buy even with no model row |
| **AVG_PROCESS** | 50-59 | League-average process; stash-worthy if PL rank supports |
| **BELOW_AVG** | 40-49 | One+ axis below average; skip unless PL rank is high |
| **BELOW_AVG_HARD** | <40 | Multiple weak metrics; PL rank is outcome noise |
| **NO_MLB_DATA** | <200 pitches | Fall back to MiLB Statcast via `scripts/xfp/build_sp_rehab_tracker.py` pattern |

## When to invoke

- Triangulate returns "no convergence" with all three lenses blank or rp3+archetype both blank
- User asks "is X any good" / "what about rookie Y" for a recently-promoted SP
- Resolving disagreements where the archetype panel says CAREER_LOW but the pitcher has accumulated significant 2026 MLB sample (Ben Brown pattern)
- Pre-claiming a PL-ranked rookie nobody has decoded yet (Logan Henderson)

## Anti-patterns

- **Don't run on established SPs** — for anyone with rp3 + archetype, both already integrate this data and the shadow lens adds noise.
- **Don't override rp3 with the shadow lens unilaterally.** If rp3 returns a real projection, that's the headline. Use shadow only when rp3 is blank or when the archetype panel clearly hasn't refreshed (n_pitches >= 500 + archetype tagged CAREER_LOW from prior year).
- **Don't treat <200-pitch verdicts as actionable.** That's NO_MLB_DATA — fall back to MiLB or pass.
- **Don't grade in isolation.** Always pair the shadow card with the PL rank, return date (if IL'd), and matchup context.

## Limitations and queued improvements

1. **MiLB Statcast extension.** Players with 0 MLB pitches (Jonah Tong, Gage Jump, Walbert Ureña, etc.) need MiLB ratings. The pattern in `build_sp_rehab_tracker.py` already pulls minor-league Statcast — extending that to all PL-ranked rookies is the durable fix.
2. **Population baseline drift.** The population is computed on a single point-in-time pull. Re-run weekly so the 432-SP sample stays current.
3. **No GB% / chase% yet.** Could add for completeness; not critical for the Henderson/Brown decisions.

## Related

- `/triangulate` — primary engine. Should fall back to shadow-scout when both rp3 and archetype are blank.
- `/sp-stash-finder` — the IL-stash workflow that ranks rookies via the shadow lens as one input.
- `scripts/xfp/build_sp_rehab_tracker.py` — MiLB pattern for the future extension.
