---
name: fa-sp-pool
description: Identify FA starting pitchers actually available in your ESPN league, ranked by quality with PL Top 100 cross-reference. Pulls all FA SPs (size=2000), verifies each is truly available (not on another team's roster — the Connelly Early gotcha), cross-references with the latest PL Top 100 SP article via WebFetch, compares against the user's current SP staff, and flags meaningful upgrades. Use whenever the user asks "what SPs are available", "is there an SP upgrade", "who should I add for streaming", or wants to validate a pickup target's availability.
maturity: legacy-lens-stack
---

# fa-sp-pool

You are identifying which starting pitchers are ACTUALLY available
in the user's ESPN league and ranking them by quality with Pitcher
List as the external authority.

**For TODAY's streamer view, prefer `/stream-the-stack`** — that skill
runs the same Connelly-Early-verified FA SP pool intersected with
confirmed next-3-day probables, ranked by boom_stack tier. This skill
is the broader season-rosterable scan; stream-the-stack is the daily
boom-shot filter.

**Secondary rank within this pool:** after rp3 + PL Top 100, use
boom_stack tier as a tiebreaker. A `boom_stack >= 2` at ace/sp2_sp3
tier is a stronger add than a stack=0 equivalent-rp3 candidate.
At backend/streamer tiers, treat skill_spike as ANTI-predictive
(see `reference_boom_stack_tag.md`).

The skill exists because of the **Connelly Early bug** (2026-05-18):
PL ranked Early at #42 T6 with a "discount Max Fried" comp, but he
was already rostered on another team in the user's league — not
available as a FA. The PL rank doesn't guarantee availability; ESPN
roster verification is mandatory.

---

## Inputs

1. **Optional**: minimum season FP threshold (default 50 for SPs —
   filters out callups with no track record yet)
2. **Optional**: max ownership % filter (default 100 = no filter; set
   to 50 if user wants "low-owned upside plays")
3. **Optional**: limit to top N by season FP (default top 50 for
   tractable PL cross-reference)

---

## Step 1 — Pull FA SP pool (use single unfiltered call)

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)   # single unfiltered call
# Bucket by ACTUAL role, never the raw ESPN position tag (gotcha #8 — the
# Detmers dual-eligible bug: position='RP' but a starter). eligible_slots
# pre-filter keeps the detect_pitcher_role calls cheap.
from scripts.xfp.lib.pitcher_role import detect_pitcher_role
sps = [p for p in fas
       if 'SP' in str(getattr(p, 'eligibleSlots', []))
       and detect_pitcher_role(p) == 'SP']
```

**Do NOT use** `get_free_agents(position='SP', size=300)` — per
`feedback_fa_pool_size_cap.md`, this silently truncates the pool.

Capture for each: `name`, `playerId`, `proTeam`, `total_points` (season FP),
`projected_total_points`, `percent_owned`, `injuryStatus`.

---

## Step 2 — Verify availability against ALL rosters (CRITICAL)

**This is the Connelly Early lesson.** ESPN's `get_free_agents()`
returns the FA pool BUT some "FAs" can be misclassified, and the
PL Top 100 may rank pitchers who are rostered in your specific league.

For the top 50 candidates by season FP (or any specifically-named
candidate from a PL article):

```python
from app.espn_connector import get_all_teams
teams = get_all_teams()

# Sanity check named candidates
for name in candidates_of_interest:
    on_roster = teams[teams['player_name'].str.contains(name, case=False, na=False)]
    if len(on_roster):
        print(f"⚠ ROSTERED: {name} on {on_roster.iloc[0]['team_name']} — NOT FA")
```

Always run this check before recommending a PL-ranked pitcher as
a pickup. If a name comes from a PL article, the assumption
"PL-ranked = available" is FALSE.

---

## Step 3 — Sort FA pool by quality metric

> **MLBAM-only join-guard (one-liner).** Join FA SPs to rp3 / Stuff+ / archetype
> by MLBAM pitcher_id via `resolve_pitcher_id(name, team=…)` from
> `plv_clone.utils.name_match` — NEVER on a bare normalized name. Same-name
> pitchers collide silently (the Max Muncy collision, transposed: e.g. the two
> Logan Allens). ESPN `playerId` is NOT MLBAM (Castillo ESPN=33748 vs MLBAM=622491),
> so resolve, don't assume.

Default sort: `season_fp` descending (top-50 cut). Optional sorts:
- By `projected_total_points` (more forward-looking)
- By rh3/rp3 model rank if available (cross-join with
  `data/outputs/xfp_rp3_projections.csv`)

**Position grouping:** this pool is all-SP, so it is the single **SP** group in
the canonical taxonomy (`from plv_clone.positions import position_group`, with
`bucket=detect_pitcher_role(row)` the SP/RP authority — a dual-eligible arm like
Detmers resolves to SP via `eligible_slots` + `gamesStarted`, not the ESPN
`.position` tag). RP/closer FAs are a separate group (CLOSER saves / SETUP holds)
handled by `/fa-rp-pool`. See `/triangulate` "Canonical roster + FA report format"
for the full position-grouped house style (C · 1B/3B · 2B/SS · OF · UTIL · DH · SP ·
CLOSER · SETUP).

For low-ownership upside plays, also surface bottom-quartile owned
candidates with high season FP — these are the "league hasn't
noticed yet" picks.

### Recency outlier alert (model-lagging candidates)

After the main sort, run a secondary scan for SPs whose recent form
significantly exceeds their model projection:

```python
# Join rp3 projections to FA SP pool by name
rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rp3_fa = fa_sp_df.merge(rp3, on='player_name', how='left')

# Flag: gs_to >= 10, recency_form_gap > 2.5, fp_per_start_last21 available
outliers = rp3_fa[
    (rp3_fa['gs_to'] >= 10) &
    (rp3_fa['recency_form_gap'] > 2.5) &
    (rp3_fa['fp_per_start_last21'].notna())
].sort_values('recency_form_gap', ascending=False)
```

Surface each as:
`⚠ RECENCY OUTLIER: {name} — rank #{rank}, xfp {xfp:.1f}/start, L21d {l21d:.1f}/start, gap +{gap:.1f}`

**Why 10 GS threshold:** K% stabilizes at ~70 TBF (~5-6 GS); by 10 GS
the season carries 67% weight in the prior blend and K% signal is fully
credible. Below 10 GS the L21d gap can reflect a single dominant outing,
not a skill shift.

**Prior refresh trigger (10 GS):** When a SP has `gs_to >= 10` AND
`recency_form_gap > 2.5` AND (`career_k_percentile >= 0.85` OR
`k_pct improvement vs prior > 0.025`), flag them for manual prior review.
The Bayesian prior anchors on career history and needs ~15+ GS to fully
update, but K% signal is credible by 6 GS. At 10 GS the model is still
31% prior-anchored but the evidence is real. Don't wait for 15 GS.

**Why this exists:** On 2026-05-25, Max Meyer (rank #65, xfp=10.58) averaged
17.0 FP/start in L21d with a +3.1 gap but was invisible to the main FA scan
because he ranked below the replacement threshold (rank 45). Career form:
PEAK/PEAK (k_pct 90th, velo 93.5th percentile). He was picked up by another
team before surfacing. This alert exists to catch those cases.

### sp-decline trap filter (catch the ERA-trap add BEFORE you make it)

The recency-outlier scan above finds arms whose RESULTS lead their model. The
**opposite** failure is just as costly: an FA whose good results are **propped
above his whiff/K stuff LEVEL** — tempting by ERA but about to regress DOWN the
moment you roster him. This is the **Holmes / Keller / Ober** pattern. The
validated `/sp-decline` lens flags it.

After the main sort, join the sp-decline tier (by MLBAM) onto the FA pool:

```python
import sys; sys.path.insert(0, 'scripts/xfp')
from sp_decline_model import build as build_decline
dec, _ = build_decline()            # DataFrame keyed on mlb_id (MLBAM)
dec_by_mlbam = dec.set_index('mlb_id')[
    ['tier', 'stuff_level_pctl', 'decline_gap', 'velo_flag']
].to_dict('index')

# For each FA SP resolved to an MLBAM id:
d = dec_by_mlbam.get(mlbam_id)
if d and d['tier'] == 'DECLINE-RISK':
    print(f"⚠ PROPPED — {name}: results above whiff/K stuff (lvlPct "
          f"{d['stuff_level_pctl']:.0f}, gap {d['decline_gap']:+.0f}); will regress. "
          f"Do NOT add despite the line.")
```

**Validated 2026-06-13** (`sp_decline_stuff_decay_2026-06-13.md`, partial-r ~0.235
on the whiff/K LEVEL). **DECLINE-RISK** = below-average stuff level
(`stuff_level_pctl ≤ 45`) with FP still propped above it. When an FA carries this
tier, **flag it as `⚠ PROPPED` in the output and do NOT recommend the add** even
if season FP / PL rank look attractive — the box score is the trap.

**Context/risk flag ONLY — never moves the headline** (CLAUDE.md #13). rp3 / PL
Top 100 / Stuff+ still drive the ranking. sp-decline only vetoes the *recommendation*
on a propped name. The mirror tier **RISING** (whiff/K level ahead of FP) marks the
sustainable / buy-low-safe adds — surface it as a positive when present. For the
full decomposition behind a flag, run `/sp-decline --players "X"`.

---

## Step 4 — Fetch current PL Top 100 SP article

Use WebSearch to locate the latest:

```python
WebSearch(
  query="Pitcher List Top 100 Starting Pitchers 2026 latest week rankings",
  allowed_domains=["pitcherlist.com"]
)
```

Pick the highest week-number result. URL pattern:
```
https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-{MM-DD}-week-{N}-rankings/
```

Then WebFetch with a prompt naming the top 30-50 FA SP candidates by
ESPN season FP:

```python
WebFetch(
  url=top100_url,
  prompt="Find rank, tier, weekly change, and any analyst commentary for these
  specific pitchers — they are top FA candidates: <list of names>. For each,
  report: rank, tier, weekly change. **CRITICAL: For any pitcher NOT on the
  list, explicitly say 'NOT ON LIST' — do not silently skip absent pitchers.**"
)
```

The explicit "NOT ON LIST" instruction is required — otherwise
absent players get silently dropped.

---

## Step 5 — Also fetch streamer ranks for the current week (optional)

If the question is about THIS WEEK's pickups (not season-long
rosterables), also fetch the daily streamer-ranks article:

```
https://pitcherlist.com/starting-pitcher-streamer-ranks-fantasy-baseball-{MM-DD}-{MM-DD}-{MM-DD}/
```

This gives Auto-Start / Probably Start / Questionable / Do Not Start
tiers for specific dates — useful for one-week streaming decisions.

---

## Step 6 — Compare to user's current SP staff

Pull the user's current SPs:

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
my_sps = roster[(roster['position']=='SP') & (~roster['injured'])]
```

For each of the user's SPs, look up their PL rank (from cached
prior fetch or a separate WebFetch). Build a "your staff vs best
FA" comparison:

```markdown
| Your SP | PL # | Best FA at same/better rank? | Net upgrade if swap |
|---|---|---|---|
| Your worst | #49 | Yes — Soroka at #35 | +14 PL ranks |
| ... | ... | ... | ... |
```

A meaningful "upgrade" needs to clear at least 5-10 PL ranks AND
materially improve season-FP trajectory. If best FA is within 5
ranks of user's worst SP, the swap is cosmetic — recommend HOLD.

---

## Step 7 — Categorize each FA SP

Bucket the PL-cross-referenced FA pool:

| Category | Criteria | Action |
|---|---|---|
| **Real upgrade** | PL rank ≥ 10 ranks better than user's worst rostered SP | Strong add candidate |
| **Marginal swap** | Within 5-10 PL ranks of user's worst | Hold unless specific niche |
| **Speculative stash** | Low ownership (<10%), rising trajectory (+UR or +5 weekly) | Stash candidate if roster slot |
| **Streamer only** | Tier 9-11 (#75-100), Probably Start tier in current week | Weekly streaming, not season hold |
| **⚠ Propped (ERA trap)** | sp-decline **DECLINE-RISK** — results above whiff/K stuff LEVEL | Do NOT add; will regress (Holmes/Keller/Ober) |
| **Avoid** | Falling -10+ weekly OR injury concern | Skip entirely |

---

## Step 8 — Output format

```markdown
## FA SPs in your league — ranked by PL Week N

### Verified availability check
(List any candidates of interest that were NOT actually FA, with the
team that's rostering them. Example: Connelly Early — rostered on
"Frendy's Fantastic Team", NOT available.)

### Ranked FA SPs (sorted by PL rank)
| PL Rank | Pitcher | Tier | Δ | League Owned% | Season FP | Notes |
... full table ...

### Notable FA SPs NOT in PL Top 100
- High-FP earners PL doesn't rank (sometimes signals "production but
  poor underlying" — e.g., Bailey Ober today)
- Names from recent waiver-watch discussion

### Your staff vs FA pool
| Your SP | PL # | vs Best FA |
... 1-line each ...
**Translation: your bottom-N SPs are within striking distance of FA pool;
top-M are clear holds.**

### Recommendations
- **Real upgrade**: <name(s)> — swap for <which SP>
- **Speculative stash**: <name(s)> — if IL slot frees up
- **Streamer this week**: <name(s)> from streamer article
- **Skip**: <name(s)> with declining PL trajectory
```

---

## Anti-patterns this skill exists to prevent

- **Recommending a PL-ranked pitcher as a FA pickup without ESPN
  roster verification.** The Connelly Early gotcha. Always cross-check
  `get_all_teams()` for any specifically-named candidate before
  recommending.
- **Per-position `get_free_agents(position='SP', size=300)`** —
  truncates pool silently. Use single unfiltered size=2000 call.
- **Treating "high season FP" as "PL likes them"**. Many high-FP
  arms (Wacha, Vásquez, McGreevy at the top of the FA-by-FP list)
  are mid-T6/T8/T9 in PL — counting-stats accumulated by volume,
  not skill. The PL cross-reference is the quality filter. **Also cross-ref
  the validated FanGraphs Stuff+ board (`/sp-stuff-board`)** — it flags
  buy-low FA SPs whose elite stuff leads their results (canonical: Eury Pérez,
  Aaron Nola) before the box score catches up, and `/sp-floor` ranks the
  pool by bust risk (K−BB%) for floor-aware adds.
- **Skipping the "user's staff vs FA" comparison.** Without it,
  recommending an FA add is meaningless — you don't know if it's
  an actual upgrade vs a sidegrade.
- **Recommending a streamer add as a season-long hold.** The
  weekly-streamer article ranks for ONE START; long-term
  rosterability is the Top 100 article's domain.
- **Ignoring injury status in the FA pool.** A 90-FP earner on IL15
  with no return date is a worse hold than a 60-FP earner who's
  active. Surface injury status alongside the rank.
- **Adding an ERA-trap arm whose stuff doesn't back the results.** A low ERA /
  good recent line can be propped above the pitcher's whiff/K LEVEL → it regresses
  the moment you roster him (Holmes/Keller/Ober). Run the **sp-decline trap filter**
  (Step 3) and never recommend a DECLINE-RISK arm as an add even if season FP / PL
  rank look good — flag it `⚠ PROPPED`. It's a risk flag, not a headline mover.
- **Ignoring recency_form_gap outliers below the replacement threshold.**
  The model intentionally excludes L21d as a feature (failed +0.005r
  validation gate); below-replacement pitchers with large positive gaps
  are "model-lagging" candidates that need manual review. Run the
  recency outlier scan (Step 3) every time — don't skip it because the
  player ranks below the normal cut.

---

## Complementary skills

- **`/sp-archetype <name>`** — after this skill surfaces a candidate, run sp-archetype to get the 20-80 ratings + archetype label + historical comps (T+1/T+2 outcomes for 5-8 similar SP-years). Especially powerful when paired with the recency-outlier scan — a SUPER-tier SUPER tier outlier whose archetype matches MOVE_CTRL_ACE (44% historical breakout rate) is the highest-conviction add.
- **`/sp-decline`** — the propped-results / ERA-trap risk board behind the Step 3 trap filter. Run `/sp-decline --players "X"` for the full whiff/K-LEVEL decomposition behind any ⚠ PROPPED flag before passing on a tempting-by-ERA add.

## When NOT to use this skill

- Hitter FAs — use `/fa-replacement-pool` instead
- Single-pitcher deep dive — use `/fa-pickup-deep-dive` with bucket=SP
- Mid-game streaming decision — use `live_monitor.py` for in-progress
  game context
- RP/closer FA scan — different model (rprs2) and different role
  context (save situations). Build `/fa-rp-pool` separately if needed.
- Long-term rotation outlook (which prospect to stash for September) —
  better handled by `/roster-audit` or a future MiLB-translation skill
