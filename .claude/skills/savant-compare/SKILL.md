---
name: savant-compare
description: Side-by-side Baseball Savant percentile comparison for 2-6 players. WebFetches each player's public Savant profile page, extracts percentile rankings (xwOBA, xBA, xSLG, EV, Barrel%, Hard-hit%, Sweet Spot%, Bat Speed, K%, BB%, Whiff%, Chase%, Sprint Speed), builds a comparative table, identifies fantasy archetype clusters (five-tool / contact-specialist / power-or-bust), and optionally anchors to a historical comp season. Use whenever the user asks "how do these players compare on Savant", "what does X's Savant page look like", or wants visual-percentile-style validation of a model verdict.
---

# savant-compare

You are pulling Baseball Savant percentile rankings for 2-6 players
and producing a structured side-by-side comparison. Savant is the
"visual proof" layer that anchors fantasy verdicts in scout-friendly
percentile language.

The skill exists because Savant pages are scattered (one URL per
player, no built-in compare tool), and the percentile rankings are
the most-credible authority for "is this skill elite or not?"
Building the comparison once per session is straightforward but
manual; the skill encodes the WebFetch URLs, the percentile-extraction
prompt, and the archetype-classification synthesis.

---

## Inputs

1. **2-6 player names** (required). Use full names; accents OK.
2. **Optional season override** — defaults to current 2026. To pull
   a historical season (e.g., "Eugenio Suárez 2025 as archetype
   comp"), specify the year — adds `?season=2025` to the URL.
3. **Optional archetype anchor** — a known comp player+season to
   include in the comparison (e.g., "anchor to Suárez 2025 to test
   if Montgomery has 49-HR upside profile").

---

## Step 1 — Resolve MLBAM IDs

Use `data/outputs/xfp_rh3_projections.csv` (`batter` column) for
known hitters. For players not in rh3, use MLB Stats API search:

```python
import requests
r = requests.get(f"https://statsapi.mlb.com/api/v1/people/search?names={name.replace(' ','%20')}", timeout=10).json()
for p in r.get('people',[])[:5]:
    if matches_team_or_position(p): break
```

Disambiguate by team or position when same-name (Max Muncy LAD vs
ATH). For accented names (Iván Herrera, José Soriano), normalize
when matching but preserve original for display.

---

## Step 2 — Build Savant URLs

URL pattern:
```
https://baseballsavant.mlb.com/savant-player/{slug}-{mlbam_id}
```

Slug convention: lowercase, hyphenated, no accents.
- "Max Muncy" → `max-muncy`
- "Iván Herrera" → `ivan-herrera`
- "Colson Montgomery" → `colson-montgomery`
- "Luis García Jr." → `luis-garcia-jr` (verify on actual page)

For historical season, append `?season=YYYY`:
```
https://baseballsavant.mlb.com/savant-player/eugenio-suarez-553993?season=2025
```

If unsure of the exact slug, the savant-player URL is forgiving —
even partially wrong slugs route to the right player if the ID is
correct. **The ID is what matters; slug is cosmetic.**

---

## Step 3 — WebFetch each player in parallel

Use a structured prompt that extracts the full percentile table:

```python
WebFetch(
  url=savant_url,
  prompt="""Extract <Player Name>'s {season} Statcast percentile rankings
  from the player profile page. List every percentile rank shown — including:
  xwOBA, xBA, xSLG, average exit velocity, max exit velocity, barrel %,
  hard-hit %, K %, BB %, whiff %, chase rate, sweet spot %, sprint speed,
  OAA (if shown), arm strength (if shown), and any bat tracking metrics
  (bat speed, swing length, fast-swing rate). Format as: Metric — Percentile (Value).
  Also note current season slash line (AVG/OBP/SLG), splits vs LHP/RHP if visible,
  and season HR/RBI/R totals."""
)
```

Run all player fetches in parallel (one Agent call with multiple
parallel WebFetch invocations, or sequential WebFetch in same
message block).

**Percentile convention reminder:** Savant displays percentiles such
that **HIGHER = BETTER** even for negative stats. So a K% percentile
of 75 means "strikes out less than 75% of MLB" = good. A Whiff%
percentile of 41 means "whiffs more than 59% of MLB" = below average.
**Double-check this if a Whiff% rank seems mismatched with the raw
whiff rate.** Some scraped extracts inadvertently flip the convention.

---

## Step 4 — Build the comparison table

Standard table format:

```markdown
| Metric | Player 1 | Player 2 | Player 3 | Anchor (if used) | Winner |
|---|---|---|---|---|---|
| Slash | .AAA/.OBP/.SLG | ... | ... | ... | |
| HR / RBI / R | N/N/N | ... | ... | ... | |
| xwOBA pct | 97th | 93rd | 65th | 42nd | P1 |
| xBA pct | 88th | 93rd | 21st | 4th | P2 |
| xSLG pct | 98th | 94th | 79th | 73rd | P1 |
| Exit Velocity (avg) | 97th | 74th | 90th | 55th | P1 |
| Barrel % | 93rd | 91st | 90th | 89th | tied |
| Hard-hit % | 97th | 40th | 79th | 78th | P1 |
| Sweet Spot % | 87th | 97th | 61st | 32nd | P2 |
| Bat Speed | 93rd | n/r | 96th | n/r | P3 |
| K% | 61st | 75th | 56th | 27th | P2 |
| BB% | 77th | 51st | 18th | 53rd | P1 |
| Whiff % | 41st | 82nd | 95th | 18th | P2/P3 mixed |
| Chase % | 56th | 34th | 78th | 27th | P2 |
```

Bold the metrics where players visibly cluster vs diverge — those
are the "what makes each player different" axes.

---

## Step 5 — Archetype classification

Cluster each player using percentile patterns:

| Archetype | Percentile signature |
|---|---|
| **Five-tool elite** | All categories ≥75th, no clear weakness |
| **Power-driven elite** | EV/Barrel/Hard-hit/xSLG ≥90th, K%/Whiff might be 30-60th |
| **Contact specialist** | Sweet Spot/xBA/K% ≥75th, EV/Barrel/Hard-hit modest (40-70th) |
| **Power-or-bust** | Bat speed/EV/Barrel ≥85th, K%/Whiff/Chase ≤30th, low xBA |
| **Slap-and-walk** | K%/BB% top 15%, EV/Barrel bottom 25%, high contact-no-power |
| **Aging veteran** | Modest decay across power axes from prior season |

Surface the archetype call inline. Example:

> Muncy = **five-tool elite** (all categories ≥77th except whiff/chase).
> Steer = **contact specialist** (Sweet Spot 97th, but only 40th hard-hit).
> Montgomery = **power-or-bust** (top-10% bat speed/EV/Barrel, bottom-5% whiff).
> Donovan = **slap-and-walk** (top-15% K%/BB%, bottom-20% power).
> Suárez 2025 (anchor) = **power-or-bust** — Montgomery archetype ceiling proof.

---

## Step 6 — Cross-player synthesis

Explicitly call out:

1. **Who's elite at what.** Use the table to highlight 3-5 distinct
   player vs player findings.
2. **Sustainable signal vs outcome.** Pair with skill-level insights
   if relevant (e.g., "Steer's Sweet Spot 97th is one of the most
   stable skills in baseball — supports the breakout call").
3. **Archetype matchup to user's roster need.** If user is filling
   a power slot, prioritize the power-driven archetypes. If filling
   AVG/OBP, the contact specialists.
4. **Anchor comparison if used.** Quantify the gap between current
   players and the archetype anchor (e.g., "Montgomery's EV/xwOBA
   actually exceeds Suárez 2025 — the 49-HR season is a realistic
   ceiling target, not aspirational").

---

## Step 7 — Verdict tied to user's actual decision

Don't end with just a percentile table. Convert the Savant findings
into actionable picks:

- "**Highest confidence pickup**: Muncy. All-axis elite + 8-year
  history at this profile."
- "**Highest ceiling pickup**: Montgomery. Bat speed says 35+ HR is
  on the table; whiff% says .230 AVG is the cost."
- "**Most narrow-but-real breakout**: Steer. Sweet Spot 97th is the
  load-bearing finding — sustainable contact specialist."

---

## Anti-patterns this skill exists to prevent

- **Extracting percentiles without checking the convention.** Savant
  uses HIGHER=BETTER for all metrics including K%/Whiff%/Chase. If
  a player has Whiff% percentile 95 but raw whiff rate 35.6%, the
  extraction has flipped the metric. Sanity check by cross-referencing
  raw value with percentile direction.
- **Forgetting historical-season URL parameter.** Default Savant URL
  shows current season. To compare to a player's prior breakout year
  (Suárez 2025), explicitly add `?season=YYYY` to the URL.
- **Treating Savant percentiles as decisive without the underlying
  context.** Percentile rankings are relative to MLB qualified
  hitters — a player with limited PA might be ranked but with low
  sample-size confidence. Cross-check PA count.
- **Skipping archetype classification.** A table of percentiles is
  useful; calling out that "Player A and Player B are the same
  archetype, Player C is a different one entirely" is the value-add.
- **Comparing fielding/baserunning percentiles for the fantasy
  decision.** Sprint speed and OAA matter for real baseball but
  rarely matter for fantasy points formats. Skip or note as
  context-only.

---

## When NOT to use this skill

- Single-player Savant page check — just fetch directly, no
  comparison needed
- Pitchers (SP/RP) — Savant pitcher pages have different metrics
  (pitch movement, spin rate); could be built as `/savant-compare-sp`
  later
- Real-time game performance — Savant pages update next-day; use
  `live_monitor.py` for current-day situational info
- "Should I draft X next year" — Savant snapshots are season-specific;
  draft prep needs multi-year trend analysis
