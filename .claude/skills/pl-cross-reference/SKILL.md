---
name: pl-cross-reference
description: Cross-reference our model picks against current Pitcher List rankings + recent article takes. Fetches the latest "Top 150 Hitters" or "Top 100 Starting Pitchers" via WebFetch, pulls per-player dedicated profile pages, and surfaces divergence (where PL disagrees with our model and why). Use whenever the user asks "what does Pitcher List say about X" or "how does PL rank these guys" or wants an external sanity check before committing to a pickup.
---

# pl-cross-reference

You are doing an external-source sanity check on a set of players,
using Pitcher List as the comparison authority. The skill exists
because today's exercise (cross-checking Steer / Muncy / Montgomery /
Angel Martínez against PL's Week 7 Top 150) revealed real disagreement
that changed the verdict — and the WebFetch dance to find the right
URL was non-trivial.

PL is NOT a tie-breaker — they're rate-stat-driven and 12-team-mindset
oriented, while our model is BrownU points-driven and 8-team optimized.
Use them as a SANITY CHECK on whether you're missing something the
model can't see (e.g., year-over-year discipline gains, role/leverage
context, narrative shifts).

---

## Inputs

1. **List of player names** (required) — 1-6 players is the
   sweet spot. >6 → ask the user to narrow or run twice.
2. **Bucket** (optional) — `H` / `SP` / `RP`. Infer from player
   positions if not provided.
3. **Article preference** (optional) — by default fetch:
   - Hitters: latest weekly Top 150 article (`top-150-hitters-...week-N`)
   - SPs: latest weekly Top 100 article (`top-100-starting-pitchers-...week-N`)
   - RPs: latest "Closer Rankings" / "Fantasy Baseball Saves & Steals"

---

## Step 1 — Locate the current week's article

PL publishes weekly. The URL pattern (as of 2026):

```
https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-2026-week-<N>/
https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-<MM-DD>-week-<N>-rankings/
```

Don't guess the week number. Use WebSearch to find it:

```python
# WebSearch with allowed_domains=['pitcherlist.com']
query = "Top 150 Hitters Fantasy Baseball 2026 latest week"
# OR for pitchers:
query = "Top 100 Starting Pitchers 2026 latest week rankings"
```

Pick the most recent week (highest week number in titles). If the
search returns multiple, take Week N where N is highest.

---

## Step 2 — Fetch the rankings article (WebFetch)

```python
WebFetch(
    url="https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-2026-week-<N>/",
    prompt="Find mentions of <list of player names>. For each player, "
           "report their rank number if listed, tier classification, "
           "weekly change (+/-), and the analyst's written take (quoted "
           "if possible). If a player is not on the list, say so explicitly."
)
```

The prompt must explicitly name every player AND ask for "not found"
flags — otherwise the WebFetch will silently skip absent players.

---

## Step 3 — Fetch per-player profile pages for missing/light commentary

If a player isn't on the weekly list, or their listing has no
commentary, fetch the dedicated profile page:

```
https://pitcherlist.com/player/<slug>/
```

Slug convention: lowercase, spaces and accents stripped:
- "Spencer Steer" → `spencer-steer`
- "Iván Herrera" → `ivan-herrera`
- "Luis García Jr." → `luis-garcia-jr` (usually — verify)

If profile page commentary is thin OR the player has shown up in a
recent dedicated recap (e.g., "Angel Martinez Continues His Strong
Start — 5/13/26"), search for and fetch that recap article — it
usually has the strongest analyst take. WebSearch with the player's
name + "2026" + "Pitcher List" finds these.

---

## Step 4 — Cross-reference vs our model

For each player, build a row:

| Player | Our rh3/rp3 rank (FP/g or FP/start) | PL Hitter/Pitcher List | Divergence note |
|---|---|---|---|

The divergence note is the value-add. Possible patterns:

- **PL much cooler than us:** PL is dinging the player on rate-stat
  concerns (high K%, low AVG) that our points-format model
  underweights. Example today: Steer (our #42, PL ~#183/Taxi).
- **PL much hotter than us:** PL is seeing year-over-year
  improvement or role/lineup context our 21d snapshot misses. Example
  today: Angel Martínez (our #121, PL off-list but glowing recap).
- **Agreed:** Both surfaces converge — high confidence on the read.
  Example today: Muncy (our #19, PL #77, both treat as solid not
  spectacular).

---

## Step 5 — Surface PL's framing biases when explaining divergence

When PL disagrees, name *why* — don't just report the rank gap. Known
PL biases vs our model:

- **AVG-weighted:** PL overweights batting average; our points-format
  formula treats AVG only via TB/H rate. High-AVG low-power guys rank
  higher on PL than for us.
- **Discipline-weighted:** PL likes low K% and high BB%; our scoring
  has K as −1 but doesn't reward BB heavily.
- **12-team mindset:** PL ranks for 12-team scarcity; our 8-team has
  more depth available, so we can be pickier on per-game rate.
- **YoY context:** PL's analysts often anchor to a player's career
  baseline (e.g., Angel Martínez's K-rate improvement vs his 2024
  number), while our rh3 model uses a 21-day rolling window. The
  longer-context view sometimes catches what we miss.
- **Closer politics for RPs:** PL pays attention to manager comments,
  spring training role announcements, etc. — our rprs2 is empirical
  (recent SV/HLD usage). PL is often EARLIER on closer changes; we
  catch up after 2-3 SV events.

---

## Step 6 — Verdict synthesis

End with a clear synthesis:

```markdown
## What this changes

(Per-player verdict updates if PL data shifts the recommendation,
otherwise "PL is consistent with our verdict.")

If PL is very bullish on someone we were lukewarm on → bump them up
in priority order (Angel Martínez today). If PL is very bearish on
someone we were high on → flag the divergence and let the user
decide if PL's lens (rate-stats, longer context) is more relevant
than ours.
```

ALWAYS include source links at the end:

```markdown
Sources:
- [Top 150 Hitters Week N — Pitcher List](<url>)
- [<player> Player Page — Pitcher List](<url>)
- (any dedicated recap articles)
```

(WebSearch results explicitly require this — see the tool's CRITICAL
REQUIREMENT.)

---

## Anti-patterns this skill exists to prevent

- **Skipping the "not found" flag in the WebFetch prompt.** Without
  it, the fetch silently drops absent players and you misreport
  "no PL coverage" when really the prompt failed to surface them.
- **Treating PL as a tie-breaker.** PL ≠ ground truth. They have
  framing biases (rate-stats, 12-team), and our model has its own.
  Use PL as a sanity check to identify what each lens MIGHT be
  missing.
- **Forgetting to surface bias context.** If PL says "Steer's skill
  set isn't impressive," it matters WHY — they're applying their
  rate-stat lens to a player our K-rate-drop signal flagged. The
  user can weight that.
- **Auto-applying PL's verdict.** If PL disagrees with our model
  recommendation, surface the divergence and explain — don't just
  flip the verdict. The user gets to weight.
- **Fetching outdated week articles.** Always WebSearch for the latest
  week first; don't hardcode last-known URLs.
- **Skipping source links.** WebSearch tool explicitly requires them.

---

## When NOT to use this skill

- User wants a model-only recommendation (no external sanity check) →
  use `/fa-pickup-deep-dive` or `/hitter-compare` directly
- User wants to AUDIT our model against multiple external sources
  (FanGraphs, Razzball, NFBC ADP) — out of scope; PL only here
- User wants pitcher-list-style PLV breakdown of OWN pitchers (not
  comparison) — use the cached PLV PDFs + scripts/xfp/compare_to_pitcherlist.py
