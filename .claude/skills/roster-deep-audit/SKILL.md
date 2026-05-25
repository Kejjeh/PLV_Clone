---
name: roster-deep-audit
description: Cross-skill roster + FA audit. Orchestrates career-form-rank, hitter-sustainability, pitcher-sustainability, and slump-or-decline sweeps; produces a single synthesis report with an agreement matrix (where skills disagree is where the insight lives) + cross-validated swap recommendations. Use weekly OR when the user wants the full landscape in one report instead of running the 4 skills separately. Replaces the manual end-of-session synthesis with a structured composition.
---

# roster-deep-audit

You are running the canonical weekly roster audit by orchestrating the
4 individual sweep skills and producing ONE synthesis report. The skill
exists because running each skill separately produces 4 reports that
need manual cross-checking — the actually-useful decisions only emerge
when you see WHERE the skills disagree.

This is the meta-skill. The 4 component skills (`/career-form-rank`,
`/hitter-sustainability`, `/pitcher-sustainability`, `/slump-or-decline`)
remain primary tools for surgical use; this one is the convenience
composition.

---

## Inputs (all optional — sensible defaults apply)

1. **Focus** — `full` / `hitters-only` / `pitchers-only`. Default `full`.
2. **Slump-or-decline target list** — pre-named players to deep-dive on.
   Default: bottom-3 by career percentile from step 1's output + any FA
   the synthesis flags below the gate.
3. **FA universe filter** — `meaningful` (default; uses
   `LeagueState.available_fa_meaningful()` to drop zero-PA callup
   noise, ~6× speedup) or `all`.
4. **Cache freshness override** — `force-rebuild` to ignore the daily
   `batter_rolling_features.csv` + `name_resolution_2026.csv` caches.

---

## Step 1 — Pre-flight

Verify both daily caches exist + are < 24h old:

- `data/research/xfp_cache/batter_rolling_features.csv` (built by
  `scripts/xfp/build_batter_rolling_features.py`)
- `data/research/xfp_cache/name_resolution_2026.csv` (built by
  `scripts/xfp/build_name_resolution_cache.py`)

If either is missing or stale, trigger the builder before proceeding.
The audit downstream of stale caches is misleading.

Also verify the model projections (`xfp_rh3`, `xfp_rp3`, `xfp_rprs2`)
are < 48h old. Warn if not — same `refresh_dashboards.py` ritual.

---

## Step 2 — Run `/career-form-rank` (sweep)

Read the skill spec at `.claude/skills/career-form-rank/SKILL.md` and
execute it as a sweep across roster + FA hitters. Capture per-player:

- `current_l150_xwoba`
- `career_percentile`
- `verdict_bucket` — derived from percentile (PEAK ≥ 90, HIGH 80-90,
  ABOVE_MEDIAN 60-80, TYPICAL 40-60, BELOW_MEDIAN 20-40, SLUMPING < 20)

Cache the structured output to a transient `dict[name] -> verdict_row`.

---

## Step 3 — Run `/hitter-sustainability` (sweep)

Spec at `.claude/skills/hitter-sustainability/SKILL.md`. Sweep produces
per-player:

- `bucket` (LEGIT / IMPROVING / STABLE / MIXED / NOISE / BAD_LUCK /
  REGRESS)
- `divergence_flag` (BUY-LOW if decomp >> rh3; SELL-HIGH if decomp <<
  rh3)
- per-marker scores

Capture as `dict[name] -> verdict_row`.

---

## Step 4 — Run `/pitcher-sustainability` (sweep)

Spec at `.claude/skills/pitcher-sustainability/SKILL.md`. SP-only
analog. Same shape of output: bucket + divergence flag + markers.

If `Focus == hitters-only`, skip this step.

---

## Step 5 — Pick slump-or-decline targets

The 4th skill is per-player and computationally heavy; never sweep it.

Targets:
1. Bottom-3 of YOUR roster by career-form-rank percentile (from step 2)
2. Any FA candidate the synthesis flags as a potential swap (i.e.
   `BUY-LOW` bucket from sustainability AND `TYPICAL` or `ABOVE_MEDIAN`
   from career-form-rank — NOT peakers)
3. Any owned player the user has specifically asked about in the
   session (carry over from `/fa-pickup-deep-dive` or
   `/breakout-sustainability` context)

Cap the target list at 8 — beyond that you're sweeping by another name.

---

## Step 6 — Run `/slump-or-decline` on targets

Spec at `.claude/skills/slump-or-decline/SKILL.md`. Per-player verdict:
HOLD / SELL-HIGH / DROP / NOT-SLUMPING-STRUCTURAL.

Capture as `dict[name] -> verdict_row`.

---

## Step 7 — Build the agreement matrix

For each YOUR-ROSTER name, build:

```
| Player | career-form bucket | sustainability bucket | slump verdict | CROSS_VERDICT |
```

Where `CROSS_VERDICT` is:

- **CONSENSUS_DROP** — career-form SLUMPING + slump-or-decline
  NOT-SLUMPING (i.e. structurally at lower baseline) + sustainability
  REGRESS or STABLE-with-no-bounce-signal. **Drop confirmed.**
- **CONSENSUS_HOLD_BOUNCE** — career-form SLUMPING + slump-or-decline
  HOLD (CI engulfs anchor) + sustainability REGRES with model-already-
  priced. **Wait 2 weeks.**
- **CONSENSUS_HOLD_PEAK** — career-form PEAK + sustainability LEGIT.
  Player at top of his game; don't sell.
- **CONSENSUS_HOLD_TYPICAL** — career-form TYPICAL + sustainability
  STABLE + (slump-or-decline not run). Default healthy player.
- **DISAGREEMENT_INVESTIGATE** — skills give conflicting signals; flag
  for manual review. Often the most-actionable cases.
- **SELL_HIGH_WARNING** — career-form PEAK + sustainability SELL-HIGH.
  Trade target; market the surface line.

For each FA candidate, build:

```
| Player | career-form bucket | sustainability bucket | slump verdict (if run) | CROSS_VERDICT |
```

Where `CROSS_VERDICT` for FAs is:

- **HONEST_UPGRADE** — career-form TYPICAL or ABOVE_MEDIAN +
  sustainability BUY-LOW or LEGIT. Real upgrade candidate.
- **PEAK_MIRAGE** — career-form PEAK. Will revert; skip.
- **NOISE** — sustainability NOISE or insufficient sample.

---

## Step 8 — Recommended actions (cross-validated)

A swap enters the final recommendation only if:
1. The drop target has `CROSS_VERDICT == CONSENSUS_DROP` AND
2. The pickup target has `CROSS_VERDICT == HONEST_UPGRADE` AND
3. Position fit is plausible (eligible-slots overlap)

Cap at 3 recommended swaps. If no swap meets the bar, that's the
honest answer — surface "no cross-validated swap available; hold."

---

## Step 9 — Write the final report

Output `data/research/roster_deep_audit_<YYYY-MM-DD>.md` with:

```markdown
# Roster deep audit — <date>

## Pre-flight
- Caches: batter_rolling_features (<age>h), name_resolution (<age>h)
- Projections: rh3 (<age>h), rp3 (<age>h), rprs2 (<age>h)

## Agreement matrix — your roster
[table]

## Agreement matrix — FA pool (HONEST_UPGRADE + SELL_HIGH only)
[table]

## Cross-validated actions
[≤ 3 swap recommendations OR "no action" verdict]

## Disagreement-investigate cases
[where skills disagreed; useful for manual follow-up]

## Component reports
- career-form-rank: <path>
- hitter-sustainability: <path>
- pitcher-sustainability: <path>
- slump-or-decline: <path> (N targets)
```

Print the headline (counts + ≤ 3 actions) to stdout; full report
lives in the markdown file.

---

## Anti-patterns this skill exists to prevent

- **Recommending a swap based on a single skill.** The whole point of
  this meta-skill is the agreement matrix. If only `/career-form-rank`
  says "drop X for Y" but `/slump-or-decline` says "X will bounce,"
  flag as DISAGREEMENT_INVESTIGATE rather than acting.
- **Sweeping `/slump-or-decline`.** That skill is per-player and slow;
  target the 5-8 most-leveraged names only.
- **Skipping the pre-flight cache check.** Stale caches produce stale
  agreement matrices. Always verify freshness or trigger a rebuild.
- **Hiding individual skill outputs behind the meta-skill.** Always
  link to the component reports in Step 9's "Component reports"
  section so the user can drill in if a verdict surprises them.
- **Adding PEAK-form FAs to the recommendation list.** The mirage
  check (Step 8 rule 2) exists exactly to prevent this — peak-form
  FAs will revert.

---

## Relationship to other skills

- `/career-form-rank` — per-skill component; run alone when you only
  need the L150 + career-percentile view.
- `/hitter-sustainability` — per-skill component; run alone when you
  only need the 9-marker decomp + BUY-LOW / SELL-HIGH signals.
- `/pitcher-sustainability` — per-skill component for SPs.
- `/slump-or-decline` — per-player diagnostic; run alone when the
  question is "should I hold X through this cold spell."
- `/breakout-sustainability` — single-player breakout decomp; orthogonal
  to this skill (this one is sweep-style; that one is deep-dive).
- `/roster-audit` — slot/IL/cap-math audit; complementary not
  redundant (roster-audit is mechanical roster state; this one is
  performance + projection + diagnostic landscape).

The natural cadence:
- **Weekly:** `/roster-audit` for slot/cap state, then this skill for
  performance landscape.
- **Mid-week / on demand:** the individual component skills for
  surgical questions.
- **Pickup-specific:** `/fa-pickup-deep-dive` for a single named
  target.

---

## When NOT to use this skill

- You only need ONE perspective (just run the relevant component skill)
- You're investigating a single player (use `/fa-pickup-deep-dive` or
  `/breakout-sustainability` or `/slump-or-decline` directly)
- The user hasn't asked for the FULL landscape — this is a heavyweight
  audit; don't run it on every roster question
- The daily caches haven't been built (the meta-skill is built ON the
  daily caches; without them every run is a from-scratch sweep that
  wastes compute)
