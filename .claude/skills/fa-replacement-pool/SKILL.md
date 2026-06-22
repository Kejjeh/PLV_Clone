---
name: fa-replacement-pool
description: Build a ranked FA replacement pool for a player being dropped. Pulls all hitters or pitchers above a season-FP threshold from ESPN, joins with our model (rh3/rp3/rprs2), computes Δ vs drop target, flags positional-flex match. Use whenever the user says "I'm dropping X, who do I pick up?", "find me a replacement for Y", or "show all FAs above N FP". Different from /fa-pickup-deep-dive (single-player deep-dive) — this is the BROAD scan.
maturity: legacy-lens-stack
---

# fa-replacement-pool

You are building a ranked replacement pool when the user has decided to
drop a specific player and wants to see all qualifying FA candidates
side-by-side with model context.

The skill exists because the obvious approach (`get_free_agents(position=X,
size=300)` per position) silently truncates — we missed Sheets, then
Cortes/Steer/Horwitz/García/Busch in one session before realizing the
per-position cap was the culprit. See
`feedback_fa_pool_size_cap.md` for the canonical fix.

---

## Inputs

If the user hasn't provided these, infer or ask:

1. **Drop target name** (required) — used as baseline for Δ comparison
   and positional-flex matching
2. **Bucket** (required) — `H` (hitters) / `SP` / `RP`. Infer from the
   drop target's primary position if not stated.
3. **Threshold** — minimum season FP to qualify. Default = 80 for
   hitters, 60 for SPs, 50 for RPs. The user often starts at 100 and
   asks to expand; default lower to surface adequate candidates first
   pass.
4. **Roster context** — "for my BrownU roster" (apply 8-team translation
   to ownership %) vs "in general"

---

## Step 1 — Establish the drop-target baseline

Pull the drop target's row from the relevant projection file:

| Bucket | File | Key cols |
|---|---|---|
| H | `data/outputs/xfp_rh3_projections.csv` | `xfp_rh3_per_game`, `expected_total_fp_remaining`, `signal`, `replacement_delta` |
| SP | `data/outputs/xfp_rp3_projections.csv` | `xfp_rp3_per_start`, `expected_total_fp_remaining`, `signal` |
| RP | `data/outputs/xfp_rprs2_projections.csv` | `xfp_ros`, `replacement_delta`, `signal` |

Also pull drop target's `eligible_slots` from
`get_my_roster_with_injuries()` — needed for positional-flex matching.

Surface drop-target baseline at top of output so the user can see what
"Δ vs Donovan" means.

---

## Step 2 — Pull the FA pool (CRITICAL: avoid the size cap trap)

**Always use a single unfiltered call:**

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)   # one call, then filter
```

**NEVER** use per-position calls like `get_free_agents(position='H',
size=300)` for "find all hitters above threshold" — the per-position
size cap silently drops candidates. The user explicitly flagged this
("you're missing hitters") in the session that prompted this skill.

Then filter to the bucket:

```python
hitter_positions = {'C','1B','2B','3B','SS','OF','LF','CF','RF','DH'}
sp_positions     = {'SP'}
rp_positions     = {'RP'}
```

For each FA in the bucket, capture:
- `player_name`, `player_id`, `position`, `eligibleSlots`
- `pro_team`, `total_points` (season), `projected_total_points`
- `percent_owned`, `injuryStatus`
- For hitters: `stats[0]['breakdown']` AB/R/HR/RBI/BB/K/SB/AVG

Filter by season FP ≥ threshold.

---

## Step 3 — Join with model projections

> **MLBAM-only join-guard (one-liner).** Join every player to projections by
> MLBAM id via `resolve_batter_id(name, team=…, position=…)` /
> `resolve_pitcher_id(...)` from `plv_clone.utils.name_match` — NEVER on a
> bare normalized name. Same-name players silently clobber (canonical: Max
> Muncy LAD 3B 571970 vs ATH C 691777 → false drop rec, 2026-05-25). The
> accent-key index below is a fallback only when an MLBAM id isn't resolvable.

Name-normalize for joining (Iván Herrera, Luis García Jr., José Soriano —
accents WILL bite):

```python
import unicodedata
def ascii_strip(s):
    if not isinstance(s, str): return ''
    return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower().strip()

# alias used throughout
norm = ascii_strip
```

**SP/RP accent fix — build 4-key index for rp3 "Last, First" format.**

rp3 stores names as `"Luzardo, Jesús"`. A naive `norm()` strips the accent
but keeps `"luzardo, jesus"` in Last-First order, which won't match the
ESPN First-Last `"Jesus Luzardo"`. This caused 4 missing SPs in a live
audit (Jesús Luzardo, Cristopher Sánchez, Carlos Rodón, José Soriano).

Always build all 4 key variants and index them:

```python
def build_sp_index(rp3_df):
    idx = {}
    for _, row in rp3_df.iterrows():
        fl_orig = row['player_name']            # "Luzardo, Jesús"
        fl_ascii = ascii_strip(fl_orig)         # "luzardo, jesus"
        if ',' in fl_orig:
            parts = [p.strip() for p in fl_orig.split(',', 1)]
            first_last = f"{parts[1]} {parts[0]}"          # "Jesús Luzardo"
            first_last_ascii = ascii_strip(first_last)      # "jesus luzardo"
        else:
            first_last = fl_orig
            first_last_ascii = fl_ascii
        for key in {fl_orig.lower(), fl_ascii, first_last.lower(), first_last_ascii}:
            idx.setdefault(key, row)  # first-seen wins; collisions handled below
    return idx
```

Then join FA SP names against this index using `norm(fa_name)` as key.

**Name-collision fix — use `(norm_name, pro_team)` tuple keys, never bare names.**

After building a `dict[norm_name] → projection_row`, scan for duplicate keys
before joining. The canonical collision as of 2026-05-25:

| Player | Team | Pos | batter_id | rh3 FP/g | signal |
|---|---|---|---|---|---|
| Max Muncy | LAD | 3B | 571970 | 0.578 | hold |
| Max Muncy | ATH | C | 691777 | 0.379 | drop |

Using the wrong Muncy row caused a false "drop" recommendation in a live
session (2026-05-25). The LAD Muncy is the fantasy-relevant player; the ATH
Muncy is a near-replacement-level catcher.

**Resolution — two options (use whichever is appropriate):**

Option A — key on `(norm_name, pro_team)` tuple:
```python
proj_dict = {}
for _, row in proj_df.iterrows():
    key = (norm(row['player_name']), row.get('pro_team', '').upper())
    proj_dict[key] = row

# Join: look up (norm(fa.name), fa.proTeam) first; fall back to norm(fa.name)
# only if there is exactly one match (no collision)
def lookup_proj(fa_name, fa_team):
    key_full = (norm(fa_name), fa_team.upper())
    if key_full in proj_dict:
        return proj_dict[key_full]
    # Fall back only if unambiguous
    candidates = [v for (n, t), v in proj_dict.items() if n == norm(fa_name)]
    return candidates[0] if len(candidates) == 1 else None
```

Option B — use `resolve_batter_id` from `plv_clone.utils.name_match`:
```python
from plv_clone.utils.name_match import resolve_batter_id
batter_id = resolve_batter_id(fa_name, team=fa_team, position=fa_pos)
# Consults KNOWN_COLLISIONS dict; raises ValueError (refuses to silently guess)
```

When the FA player's `pro_team` is available from ESPN (it always is), prefer
Option A's team-keyed lookup or Option B's `resolve_batter_id` call. Never
rely on bare `norm_name` alone when a collision could exist.

For hitters surface these joined cols:
- `rh3_rank`, `xfp_rh3_per_game`, `expected_total_fp_remaining`,
  `recency_form_gap`, `pa_last21`, `signal`, `replacement_delta`

Some FAs won't have a row in rh3 (insufficient PA). Don't drop them —
surface as "(insufficient PA in model)" with their ESPN season stats only.
These are often the recent callups (Angel Martínez was a great example
— PL had a glowing recap but rh3 didn't even have him in the file at
first; later he appeared at rank #121).

---

## Step 3b — Full roster comparison mode (optional)

**Trigger:** user says "evaluate my whole roster against the FA pool",
"tell me if I should drop anyone for an FA upgrade", "roster vs FA",
or similar.

In this mode, instead of a single drop target, you evaluate every
rostered player in a bucket against the FA pool simultaneously.

### 3b-1 — Pull roster

```python
roster_df = get_my_roster_with_injuries()
# columns: player_name, lineup_slot, position, eligible_slots,
#          pro_team, injury_status, projected_total_points, rh3/rp3/rprs2 (joined)
```

### 3b-2 — Separate buckets and sort weakest-first

For each bucket (H, SP, RP), sort rostered players by their projection
ascending (weakest first). This surfaces the most actionable drops at the
top of the table.

### 3b-3 — Match each roster player against FA candidates

For each rostered player, find FA candidates that beat them by a meaningful
margin:

| Bucket | Beat-by threshold |
|---|---|
| H | rh3 FP/g > roster_player_fpg + **0.010** |
| SP | rp3 FP/start > roster_player_fps + **0.20** |
| RP | rprs2 > roster_player_rprs2 + **5** |

Present as a "drop → add" table sorted by roster player projection ascending:

```markdown
| Drop (roster) | Proj | Add (FA) | FA Proj | Delta | FA Owned | FA Injury | Flex |
|---|---|---|---|---|---|---|---|
| Donovan, B | 3.41 fpg | Martínez, A | 3.68 fpg | +0.27 | 14% | — | ~ partial |
```

### 3b-4 — IL-stash carve-out

**Do not list IL60-stashed players as drop candidates** unless their
projected return date is > 60 days out. IL60-stashed players are sunk
costs for the IL slot — they do not occupy an active slot, so dropping
them costs only a future roster spot, not current production. Surface the
information ("X is on IL60, return TBD / [date]") but do not auto-flag
as drop unless the user asks specifically.

Players on IL10 or with "Day-to-Day" status who are in active slots ARE
valid drop candidates if a meaningful upgrade exists.

### 3b-5 — Injury status on ALL FA candidates (mandatory)

Always pull `injuryStatus` for every FA candidate surfaced in this mode.
A 0.1%-owned FA with a 12.11 rp3 projection may be on IL60 themselves.
Flag prominently:

> "**[FA name] — IL60, return date unknown — do not add without verifying.**"

Do not recommend an IL60 FA as a direct replacement for an active-slot
player without flagging the slot mismatch.

---

## Step 4 — Compute Δ vs drop target

For each candidate:
- `rh3_ros_delta = candidate_ros - drop_target_ros`
- `rh3_fpg_delta = candidate_fpg - drop_target_fpg`

Tier the table:
- **Meaningful upgrade:** rh3_ros_delta > +30 FP AND rh3_fpg_delta > 0
- **≈ baseline:** Δ within ±20 FP
- **Below baseline (skip):** Δ < −20 FP

---

## Step 5 — Position-flex match annotation

For each candidate, check what fraction of the drop target's eligible
slots they also cover. Direct positional matches matter — e.g., if
the drop target was a 2B/SS/IF guy and the candidate is also SS/2B/IF,
they slot in cleanly. If the candidate is OF-only, slot mismatch.

**Use the centralized helper** (PR 4, 2026-06-06):

```python
from plv_clone.fa_eligibility import filter_eligible_fa, positional_slots

# Filter the FA pool to only positionally-eligible rows BEFORE ranking.
# Strips BE/IL/UTIL/DH from the drop target's slot list — see
# NON_POSITIONAL_SLOTS in plv_clone/fa_eligibility.py.
fa_eligible = filter_eligible_fa(fa_df, drop_target['eligible_slots'])
```

The helper handles the BE/IL/UTIL/DH carve-out automatically. A drop
target with only UTIL/BE eligibility returns the full bucket pool
(caller wanted a bucket-wide scan), so you don't need to special-case
DH-only or pure-UTIL targets in the skill body.

Annotate the surviving candidates with one of:
- ✓ direct match (covers all drop target's IF/OF slots)
- ~ partial match (covers some)
- × mismatch (no overlap on drop target's slots — would need to bench
  someone else)

`filter_eligible_fa` returns only `~` and `✓` rows; `×` are dropped
upstream. If you need to surface `×` candidates (e.g. opportunity-cost
analysis on a bench reshuffle), bypass the filter and annotate manually.

---

## Step 6 — Verify candidates are TRUE FAs (mandatory, not optional)

**This step is mandatory before recommending ANY candidate, regardless
of ownership %.** The Connelly Early bug (2026-05-18) showed why:

- PL Top 100 ranked Early at #42 T6 with a "discount Max Fried" comp
- I recommended him as a stash candidate from a PL article cross-reference
- He was actually rostered on team "Frendy's Fantastic Team" in the user's
  league — entirely unavailable as a FA
- The user had to flag the error

The lesson: **PL rank ≠ available in your league.** Same goes for "MC
top-N candidate" or any list pulled from external rankings — always
verify against `get_all_teams()` for the user's specific ESPN league.

```python
from app.espn_connector import get_all_teams
teams = get_all_teams()

# For any specifically-named candidate from outside (PL, user mention,
# trending article), explicitly check:
for name in named_candidates:
    on_roster = teams[teams['player_name'].str.contains(name, case=False, na=False)]
    if len(on_roster):
        rostering_team = on_roster.iloc[0]['team_name']
        print(f"⚠ {name} is on '{rostering_team}' — NOT AVAILABLE (trade only)")
```

For the bulk FA pool returned by `league.free_agents()`, ESPN's
classification is usually correct (these are genuinely available).
But for high-owned candidates (>50%) AND for any name imported from
external rankings, always cross-check rosters.

If a recommended candidate is actually on another roster, surface it
prominently:
> "**X is on [Team Y] — not available as FA, would require a trade**"

Then either suggest an alternative or pivot to discussing trade
possibility.

---

## Step 7 — Sort and present

Sort by `xfp_rh3_per_game` descending (or `xfp_rp3_per_start` /
`xfp_ros` for pitchers).

### Canonical position-grouped house format

For any multi-position pool (e.g. "show all FAs above N FP" with no single
drop target), present **position-grouped** in the canonical house order, not
one flat list. Use the committed seam — do NOT re-derive grouping:

```python
from plv_clone.positions import position_group, primary_hitter_group, order_groups, GROUP_ORDER
from scripts.xfp.lib.pitcher_role import detect_pitcher_role  # SP/RP authority (Detmers)

# Hitters: primary_hitter_group(row) → C / 1B/3B / 2B/SS / OF / UTIL / DH
# Pitchers: position_group(row, bucket=detect_pitcher_role(row), rp_row=row)
#           → SP, or relievers split CLOSER (saves) vs SETUP (holds)
```

Taxonomy groups, in `GROUP_ORDER`: **C · 1B/3B · 2B/SS · OF · UTIL · DH · SP ·
CLOSER · SETUP**. DH is a DISTINCT bucket (UTIL = flex membership; DH = fallback
for a no-fielding hitter). Relievers split CLOSER vs SETUP via current-season
sv/hld (`detect_closer_status`; CLOSER = sv≥8 or save-share≥0.55, display-only,
CLAUDE.md #13). The triangulate batch CSV/JSON already emits a `position_group`
column you can read directly when joining triangulate output. Render one
sub-table per group, ordered by `order_groups(...)`, with FAs sorted by model
projection within each group. For a single-drop-target query the flat Δ-tiered
format below is fine. See `/triangulate` "Canonical roster + FA report format
(position-grouped, arcs + domains)" for the full validated house style.

Output format (single-target flat view):

```markdown
## FAs ≥<threshold> season FP — replacement candidates for <DropTarget>

(<DropTarget> baseline: <fpg> FP/g, <ros> RoS, signal=<signal>)

### Tier 1 — meaningful upgrade
| # | Player | Pos | Eligible | Sn FP | rh3 FP/g | RoS | Δ vs DropTarget | Recency | PA L21 | Owned | Signal | Flex |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Tier 2 — ≈ baseline
... same columns ...

### Tier 3 — skip
brief list only
```

Surface `pct_owned` honestly but DO NOT auto-exclude high-owned FAs —
the user has explicitly asked "ownership is not a concern" before,
and ESPN's "%owned" can be misleading in 8-team. Mention claim-risk
as commentary, not a filter.

---

## Step 8 — Auto-offer the natural next step

End the output with: "Want a deep-dive on the top N? (uses
`/fa-pickup-deep-dive` or `/hitter-compare`)"

The replacement-pool is the BROAD scan; the deep-dive is the FOCUSED
follow-on. Don't try to do both in one shot — the output gets
unreadable past ~10 candidates with full deep-dive details.

---

## Anti-patterns this skill exists to prevent

- **Per-position `size=300` truncation.** This is the central lesson.
  Single `size=2000` call, manual position filter. Always.
- Auto-excluding candidates because ownership > 50% — user often
  cares more about absolute upside than claim risk.
- Forgetting accent-normalization on name joins — Iván Herrera,
  José Soriano, Luis García Jr. will all fail naive string match.
- Same-name collisions (Max Muncy LAD vs Max Muncy ATH) — always key
  on `(norm_name, pro_team)` tuple or use `resolve_batter_id(name, team=..., position=...)`.
  Bare-name dict lookup caused a false "drop" recommendation on 2026-05-25.
- Treating "no rh3 row" as "skip" — recent callups are often the
  most interesting names (Angel Martínez, Logan Henderson, etc.).
  Surface them with ESPN stats only and a note.
- Recommending a "FA" who's actually on another roster. **Always run
  `get_all_teams()` check before recommending ANY externally-sourced
  candidate (PL article, podcast mention, trending name) — not just
  high-owned ones.** The Connelly Early bug (2026-05-18) was a low-owned
  player who happened to be rostered in the user's specific 8-team
  league. PL/MC rankings don't reflect your league's roster state.
- Doing full Statcast deep-dive on each candidate in this skill —
  that's `/fa-pickup-deep-dive` or `/hitter-compare`. Stay broad here.

---

## When NOT to use this skill

- User named a specific 1-3 players they're already considering →
  use `/fa-pickup-deep-dive` (single player) or `/hitter-compare`
  (multi-player head-to-head) instead.
- User wants a full league-wide audit → `/roster-audit` covers
  drop/add candidates as part of a broader sweep.
- User wants prospect / minor-league scouting → out of scope; this
  is FA-pool-only.
