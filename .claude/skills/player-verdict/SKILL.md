---
name: player-verdict
description: Master meta-skill for the CHOOSING-BETWEEN-PLAYERS domain — give it 1-6 names and it runs the full evaluation stack in one pass and ends with ONE firm answer. Chains roster-verify tags + pitcher-role truth → triangulate (three-lens card per player) → the bucket-correct head-to-head (/pitcher-compare for SP/RP, /hitter-compare for hitters) when 2+ names share a bucket → boom-bust-history (actuals variance). Use when the user asks "which of these N players", "A or B?", "full read on X vs Y", "who do I keep/add/drop between these", or names multiple players expecting a decision. One stable headline verdict per the lens-merge protocol — never a different answer per lens.
---

# player-verdict

The choosing-domain master: N names in, one firm answer out, full stack shown.

1. **Guards first** — live `my_tag()` ownership per name (roster-verify),
   `resolve_batter_id`/`resolve_pitcher_id` (collision-safe), and for
   pitchers `detect_pitcher_role` (incl. the Jax RP-slot-lag rule). A wrong
   bucket here poisons everything downstream.
2. **Triangulate every name** —
   `python -X utf8 scripts/xfp/run_triangulate.py "<A>" "<B>" ...`
   (one call; cards + comparison table).
3. **Head-to-head, bucket-correct** — if ≥2 names share a bucket:
   `/pitcher-compare` (SP/RP: role truth + 2H splits + Stuff+/floor + rp3 or
   rprs2 + verdict rules incl. DECLINE-RISK veto) or `/hitter-compare`
   (xwOBA-L21d vs baseline, YoY xwOBACON trajectory, PT). Mixed buckets:
   compare within bucket, then rank across buckets by replacement_delta.
4. **Actuals check** — `/boom-bust-history` on the finalists (variance the
   model layers can't show; the Bradish-37%-boom vs Valdez-0% class of fact).

## Output format

Per player: the triangulate card's headline row. Then ONE synthesis section:

```markdown
## Verdict: <NAME> over <NAME(s)>
Why (3 bullets max, reconciling actuals vs trajectory vs process)
What would flip it (the watch-list trigger)
```

## Hard rules (this is where verdicts go wrong)

1. **Rule 12 — one stable headline.** Compute and SHOW the full stack; the
   verdict may not flip across turns except on new data or a corrected
   error, and then say why.
2. **Rule 13** — context lenses (trending / decision-trend / 2H splits /
   consensus-diff) inform the narrative, never re-rank the models.
3. **marcel_il trap** — an FA/IL SP with `data_quality_tag=marcel_il` is
   ranked by Stuff+ `proj_ros_fp`, not rp3.
4. **User-veto slot** — a stated veto ("I don't trust X vs the Yankees")
   eliminates that option; re-rank the remainder rather than arguing.

## When NOT to use

- One player, quick check → `/triangulate X` alone.
- "Best available at a position" (open pool, no names) → `/all-boards` or the
  specific board.
- The winner still needs executing → `/moves` + `/churn-plan`.
