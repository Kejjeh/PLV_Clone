---
name: fa-pickup-deep-dive
description: Structured FA pickup analysis for a single player — pulls model projection (xfp_rh3/rp3/rprs2), recent Statcast pitch-shape or bat-tracking, ESPN injury status with return date, ownership %, an archetype layer (label + sub-types + T+1/T+2 + top-5 historical comps with comp-density and trajectory adjustments; for RPs, leverage_tier + CLOSER + FIREMAN role tags), and produces a PASS / CONSIDER / SKIP recommendation. Use whenever the user asks "should I pick up X", "deep dive on X", "what does the model say about X", or shows a screenshot of a single player.
---

# fa-pickup-deep-dive

You are producing a single-player pickup writeup using the same
structured format every time. The skill exists because we did this
manually 4-5 times in one session (Henderson, Webb, Bleday, Sheehan)
and the format was always the same: model says X, recent shape says
Y, injury context Z, ownership W, recommendation.

The user's job is to name the player. Your job is to fetch all four
data streams and produce the writeup.

---

## Inputs

1. **Player name** (required) — fuzzy-match against the relevant
   projection file
2. **Position bucket** (optional) — `H` / `SP` / `RP`. If not given,
   infer from `position` field in ESPN roster/FA pool.
3. **Owner context** (optional) — "for my roster" (compares to your
   weakest at that bucket) vs "in general" (no comparison)

---

## Step 1 — Identify the player

Try in order:
1. `app.espn_connector.get_free_agents()` and check ownership
2. `app.espn_connector.get_all_teams()` to see if rostered
3. Projection files (`xfp_*_projections.csv`) for fuzzy match

If multiple matches (e.g., two players with same surname), surface
all candidates and ask user to pick.

**Same-name collision guard (mandatory):** Build the rh3 lookup keyed
on `(norm_name, pro_team)` tuple, never bare name. Canonical failure:
Max Muncy LAD (3B, 571970, rh3=0.578 — hold) vs Max Muncy ATH (C,
691777, rh3=0.379 — drop candidate) — identical `_norm()` keys, opposite
verdicts. A 2026-05-25 roster audit assigned the wrong projection.

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rh3_idx = {}
dup_keys = set()
for _, row in rh3.iterrows():
    key = (_norm(row['player_name']), str(row.get('team', '')).upper())
    if key in rh3_idx:
        dup_keys.add(key)
    rh3_idx[key] = row
if dup_keys:
    print(f"WARNING: duplicate rh3 keys {dup_keys} — resolve by team")
def rh3_row(name, team): return rh3_idx.get((_norm(name), str(team).upper()))
```

Use `pro_team` from the ESPN row. If absent, call `resolve_batter_id()`
from `plv_clone.utils.name_match`. See `/player-id-resolve`.

If no match anywhere: tell user, suggest a search alternative
(MLB Stats API athlete search).

Determine position bucket from:
- ESPN `position` field if rostered
- Player position from projection file
- Default fallback: if name has any pitching column populated, treat
  as P; else H

---

## Step 2 — Pull model projection

| Bucket | File | Projection col | Key context cols |
|---|---|---|---|
| Hitter | `data/outputs/xfp_rh3_projections.csv` | `xfp_rh3_per_pa` | `prior_fp_per_pa`, `pa_to`, `recency_form_gap`, `signal`, `rank` |
| SP | `data/outputs/xfp_rp3_projections.csv` | `xfp_rp3_per_start` | `xfp_rp3_p25`, `xfp_rp3_p75`, `data_quality_tag`, `marcel_baseline`, `data_driven_estimate`, `prior_fp_per_start`, `gs_to`, `gs_last21`, `fp_per_start_last21`, `recency_form_gap`, `signal`, `rank` |
| RP | `data/outputs/xfp_rprs2_projections.csv` | `xfp_ros` | `role_lag1`, `sv_lag1`, `hld_lag1`, `gf_pct_to`, `replacement_delta`, `signal`, `rank` |

Surface BOTH the recent rolling projection AND the prior/historical
projection. The gap between them is the story:
- Recent ≪ prior → injury or temporary slump; possible buy
- Recent ≈ prior → stable performer
- Recent ≫ prior → hot start; likely regression candidate (sell-high?)

### Hitter-specific: hetero σ + boom_stack advisory (2026-06-03)

- The rh3 file now carries a per-batter `batter_sigma_factor`
  (clamped [0.7, 1.5], POWER widen / CONTACT tighten). When discussing
  range/CIs for a hitter, note "σ factor X.XX" rather than assuming a
  pooled σ. See `reference_hitter_sigma_hetero.md`.
- For hitters who will play today, surface the live hitter boom_stack
  via `/triangulate <name>` — sums 4 components (skill_spike_hitter,
  recform_hot_hitter, opp_soft_hitter, **lineup_amp_hitter**) and
  displays `boom_stack=N/4` with per-stack boom rates. Advisory only;
  rh3 remains the headline point estimate. See
  `reference_hitter_boom_stack.md`.

### SP-specific: variance band + data quality tag (MANDATORY)

For SP candidates, the model-projection block must include **all three**
of the following alongside the headline `xfp_rp3_per_start`:

1. **Floor/ceiling band** — `xfp_rp3_p25` to `xfp_rp3_p75`. Format
   inline as `8.21 (5.75-10.66) FP/start`. A wide band signals that
   the headline is a midpoint with real variance, not a forecast.
2. **`data_quality_tag`** — one of:
   - `data_driven_full` — anchored on enough 2026 starts; treat the headline as the most trustworthy form.
   - `data_driven_thin` — too few starts; the headline is mostly Marcel with a small data nudge. Expect movement as more starts come in.
   - `marcel_il` — pure Marcel prior (player on IL). Do not quote as if it were a real projection.
   - `marcel_no_data` — pure Marcel prior (no 2026 data). Same caveat.
3. **Marcel vs data divergence flag** — when
   `|marcel_baseline − data_driven_estimate| >= 2 FP`, explicitly say
   "model and Marcel disagree by X FP (marcel=A, data-driven=B)". This is
   the canonical signal that the headline is in an unstable transition
   zone. The Grayson Rodriguez 2026-06-02 incident is the load-bearing
   example: writeup said "rp3 10.33" with no flag; the underlying tag was
   `marcel_thin`; a regeneration with 2 fresh starts dropped it to 8.21.

The user should never see a bare `rp3 = X.XX` for an SP. They should see
`rp3 = X.XX (P25-P75) FP/start | data_quality_tag` and, when applicable,
the divergence flag.

**Note on σ:** as of 2026-06-03 the p25/p75 band has been rescaled ×2.41
to produce calibrated 50% intervals. Wider bands are the new baseline,
not a model regression. See `reference_show_variance_and_data_quality.md`.

### SP-specific: boom_stack tier + advisory tags (2026-06-03)

For every FA SP candidate, also surface the tier-aware boom_stack token
and any standalone advisory flags. Run `/triangulate <name>` or call
`compute_boom_stack()` directly — both emit the same fields. Display:

- `boom_stack=N/4 [tier=ace|sp2_sp3|backend|streamer]` with per-tier
  boom%/bust% and mean-FP context. Components are skill_spike,
  recform_hot, opp_soft, **park_friendly** (4th component, validated
  2026-06-03 — soft hitter park = boom-rate lift across all tiers).
- `🔥 HIGH-K ARM z=+X.XX` when the SP's within-cohort season K% z-score
  is ≥ +0.5 (independent, standalone +6.84 pp boom edge).
- `🧊 ELITE FRAMER` / `⚠ FRAMING TAX` when the SP's team modal 2026
  catcher is in the Q5 / Q1 of framing-runs/100. Display-only.
- **Anti-predictive skill_spike warning** — if tier is `backend` or
  `sp2_sp3` AND skill_spike is lit, surface the regression-risk callout
  (skill_spike has negative per-component lift in those tiers). At
  ace/streamer tiers it's still boom-predictive.

These tags inform the verdict rationale but do NOT replace it. A
`boom_stack=3/4` streamer with rp3=6.0 is a high-variance lottery
ticket, not "expected 17 FP" — point estimate is still rp3.

See `reference_boom_stack_tag.md`, `reference_high_k_arm_tag.md`,
`reference_catcher_framing_tag.md`, `reference_park_friendly_component.md`.

Apply Rule: don't quote any feature whose validation lift has
degraded (see `reference_validated_signals_registry.md`). For example,
`xwoba_gap_to` should not be cited as a buy signal — its marginal
lift is now ~0.

---

## Step 3 — Pull recent Statcast (last 3-5 outings)

For SP / RP — query last 3-5 starts/appearances:
```python
import duckdb
con = duckdb.connect()
df = con.execute(\"\"\"
SELECT game_date, pitch_type, release_speed, release_spin_rate,
       pfx_x, pfx_z, release_extension, description, events
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE player_name = '<Last, First>' AND game_date >= <date>
\"\"\").df()
```

Surface per-game:
- Pitch count, SwStr%, CSW%
- Velocity trend (last 3-5 starts)
- Whiff/swing per pitch type
- Note any meaningful velo drop (>1 mph from career) or shape change

For HITTER — query last 5-10 games:
- xwOBA per PA recent vs season
- HR/PA, barrel%, EV90 recent vs season
- Bat tracking metrics if available (bat_speed, swing_length,
  attack_angle) — but apply Rule 5 (sample-size honesty), only
  surface if N ≥ 30 swings recent
- **xwOBACON year-over-year trajectory** (mandatory for any FA pickup
  or drop target where the user is weighing recent performance against
  historical norms):

```python
for yr in [2022, 2023, 2024, 2025, 2026]:
    con.execute(f"""
    SELECT COUNT(*) bb, AVG(estimated_woba_using_speedangle) xwobacon
    FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
    WHERE batter=? AND events IS NOT NULL AND events != ''
      AND launch_speed IS NOT NULL
    """, [batter_id]).df()
```

Display as a one-line table: `xwOBACON: 2022: 0.XXX | 2023: 0.XXX | 2024: 0.XXX | 2025: 0.XXX | 2026: 0.XXX → RISING/STABLE/DECLINING`

This answers: **is the model's history-weighted projection anchored on a rising, stable, or falling contact quality platform?** A declining trajectory means the model may be over-projecting based on prior seasons that are no longer representative. A rising trajectory means the model may be under-projecting.

---

## Step 4 — ESPN injury status

For any player with `injured: True`, fetch structured details:
```python
from app.espn_connector import get_injury_details
inj = get_injury_details([player_id])
```

Surface: injury_type, injury_detail, injury_side, return_date,
days_until_return, short_comment. If return_date is > 30 days,
explicitly flag that an IL stash is multi-week and may compete
with other IL slot uses.

---

## Step 5 — Ownership context

**Always pull from a single unfiltered call. Do NOT use the per-position
`get_free_agents(position=X, size=300)` pattern — it silently truncates
the pool and will miss the player you're looking for.** See
`feedback_fa_pool_size_cap.md` for the canonical fix.

```python
from app.espn_connector import _get_league
league = _get_league()
# CRITICAL: free_agents() LEAKS rostered players. Confirmed 2026-06-04: Julio
# Rodriguez was returned in free_agents() with percent_owned=0.1% while ALSO
# on Frendy's roster. ALWAYS build a rostered set first and subtract.
rostered_ids = {p.playerId for t in league.teams for p in t.roster}
rostered_names = {_norm(p.name) for t in league.teams for p in t.roster}
fas_raw = league.free_agents(size=2000)
fas = [p for p in fas_raw
       if p.playerId not in rostered_ids and _norm(p.name) not in rostered_names]
# Now `fas` is a verified-FA list. Find your target by name.
```

Find the player's `percent_owned`. **NEVER conclude a player is rostered
from percent_owned alone — always verify via `get_all_teams()`.** In an
8-team league, a player at 60-70% nationally owned is routinely
unclaimed. This was confirmed 2026-05-25: Emmett Sheehan showed 60.7%
owned and the analysis incorrectly concluded "almost certainly rostered"
without calling `get_all_teams()` — he was a FA.

```python
# MANDATORY: always verify actual roster status
league = _get_league()
for team in league.teams:
    for player in team.roster:
        if _norm(player.name) == _norm(target_name):
            print(f"ROSTERED on {team.team_name} — cannot pick up")
            break
else:
    print("Confirmed FA — available to add")
```

Ownership % as a **rough prior only** (not a conclusion):
- < 30%: almost certainly FA in 8-team
- 30-70%: unknown — must verify via `get_all_teams()`
- 70%+: likely rostered but still verify — do not assume

If they're on another team's roster, surface that — picking up isn't
possible without a trade.

If you're scanning the whole FA pool above a threshold (not just one
player), use `/fa-replacement-pool` instead — that's the right skill
for "show me all FAs above N FP." This skill (`/fa-pickup-deep-dive`)
is for a single named player.

---

## Step 6 — Compare to user's roster (if "for my roster" context)

Pull `get_my_roster()` and find the user's weakest at the same bucket
(lowest xfp projection). Drop-add math:
- New player's projection − weakest current player's projection
  = expected weekly FP gain
- If gain > 5 FP/week → meaningful upgrade
- If gain < 2 FP/week → cosmetic; not worth the transaction
- Also surface: positional flex of the candidate vs the drop target
  (the rh3 projection misses positional flex value)

---

## Step 7 — Pitcher List cross-check (cached PDF OR WebFetch)

Try in order:

1. **Cached PDF** — if a recent Pitcher List PDF is in scope (user
   pasted in this session or recently saved to
   `data/reference/pitcher_list/`), use it.

2. **WebFetch fallback** — if no PDF, delegate to `/pl-cross-reference`
   OR run a single WebFetch on the current week's Top 150 hitters /
   Top 100 starting pitchers article. The PL URL pattern is:
   - Hitters: `https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-2026-week-<N>/`
   - SPs: `https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-<MM-DD>-week-<N>-rankings/`
   - Per-player profile: `https://pitcherlist.com/player/<slug>/`

   WebSearch first (allowed_domains=`['pitcherlist.com']`) to find the
   latest week number. Don't guess.

Use as a sanity check on the model verdict, NOT as a tie-breaker — PL
is rate-stat-driven (12-team mindset) while our model is BrownU-points-
driven (8-team). Common divergence patterns and how to interpret them
are documented in `/pl-cross-reference`.

If the WebFetch dance feels heavy for a single player, just call out
the PL rank if you happen to know it from recent context — don't burn
multiple tool calls on a single-player deep-dive when the model
verdict is already clear.

---

## Step 7.5 — Archetype layer (supplementary)

The model (rh3/rp3/rprs2) is still the **primary** verdict driver. The
archetype layer adds character/comp/forward-trajectory color. It is
process-based, complementary to rh3/rp3/rprs2 (outcome-based).

Read the relevant current-year row from the master CSV:

| Bucket | File | Key cols |
|---|---|---|
| Hitter | `data/research/hitter_ratings_master.csv` | `archetype`, `contact_subtype`, `power_subtype`, `discipline_subtype`, `sb_tier`, `CONTACT`, `POWER`, `DISCIPLINE`, `SB`, `age_tier`, `boundary_tier`, `t1_fp_projection`, `fp_per_pa` |
| SP | `data/research/sp_ratings_master.csv` | `archetype`, `stuff_subtype`, `velo_tier`, `pitch_archetype`, `primary_group`, `STUFF`, `MOVEMENT`, `CONTROL`, `velo_rating`, `SWING_MISS`, `CALLED_STRIKE`, `DAMAGE_SUPP`, `GB_TENDENCY`, `WALK_AVOID`, `age_tier`, `boundary_tier`, `t1_fp_projection`, `t2_fp_projection`, `fp_per_start` |
| RP | `data/research/rp_ratings_master.csv` | `archetype`, `stuff_subtype`, `STUFF`, `CONTROL`, `BATTED_BALL`, `VELO` (rating), `SWING_MISS`, `CALLED_STRIKE`, `WALK_AVOID`, `GB_TENDENCY`, `BULK_IP`, `age_tier`, `boundary_tier`, `CLOSER`, `leverage_tier`, `HIGH_LEVERAGE`, `MULTI_INNING_BULK`, `FIREMAN` (may be absent — gracefully handle), `gmli`, `t1_fp_projection`, `t2_fp_projection`, `fp_per_g` |

If the player has no current-year row in the master (rookie, low PA/IP),
note that and skip this section.

### Top 3-5 historical comps

Filter the master CSV to age within ±3 of the target's `age`, then take
the 3-5 nearest neighbors by Euclidean distance in the rating space:

- **Hitter**: distance over `(CONTACT, POWER, DISCIPLINE)` — SB rated and shown but **excluded from distance** (matches `/hitter-archetype`).
- **SP**: distance over `(SWING_MISS, CALLED_STRIKE, DAMAGE_SUPP, GB_TENDENCY, WALK_AVOID, velo_rating)`.
- **RP**: distance over `(SWING_MISS, CALLED_STRIKE, WALK_AVOID, VELO, GB_TENDENCY, BULK_IP)`.

For each comp, pull the next-year row (`year+1`) keyed on the comp's
`batter`/`pitcher` ID to surface the T+1 actual outcome (and T+2 for
SP/RP). Report:

- Hitter: `<year> <name> — archetype@T → archetype@T+1` plus `fp_per_pa T → fp_per_pa T+1`
- SP / RP: `<year> <name> — archetype@T → @T+1 → @T+2` plus `fp_per_start T → T+1 → T+2` (or `fp_per_g` for RP)

If a comp has no T+1 row (career ended / injury year), mark as `NO_T+1`.

### Output block

```markdown
## Archetype layer
- **Archetype:** <LABEL> (Contact <C>, Power <P>, Discipline <D>[, SB <S>])
- **Sub-types:** <contact_subtype>, <power_subtype>, <discipline_subtype>[, <sb_tier>]
- **Boundary tier:** <SOLID | NEAR_EDGE | EDGE> (clearly inside / borderline)
- **Age tier:** <PRE_PEAK | PEAK | POST_PEAK> (<age>)
- **T+1 projection:** <X.XXX> <FP/PA or FP/start> (vs current <Y.YYY>)
- **T+2 projection (SP/RP only):** <Z.ZZZ>
- **RP-only tags:** CLOSER=<bool>, leverage_tier=<ELITE/HIGH/MID/LOW/GARBAGE>, HIGH_LEVERAGE=<bool>, MULTI_INNING_BULK=<bool>, FIREMAN=<bool|n/a>, gmLI=<X.XX>
- **Closest 5 historical comps** (age ±3, Euclidean over rating sub-domains):
  1. <year> <name> — <arch@T> → <arch@T+1> [→ <arch@T+2>] | <fp@T> → <fp@T+1> [→ <fp@T+2>]
  2. ...
- **Comp verdict:** <K>/<N> sustained-or-improved at T+1 → SUPPORTS_<CONSIDER|SKIP|NEUTRAL>
- **Archetype trajectory:** <UPGRADE | STABLE | DOWNGRADE> vs prior year
```

> Caveat for RPs: rprs2 R² ≈ 0.246 and `t1_fp_projection` from the RP
> master is **directional only**, not a precise forecast. Use it for
> sign, not magnitude.

If the player's archetype looks edge-case (`boundary_tier == NEAR_EDGE`
or `EDGE`) OR the comp distribution is wide, suggest the user run
`/hitter-archetype profile <name>` or `/sp-archetype profile <name>` or
`/rp-archetype profile <name>` for the full archetype deep-dive.

---

## Step 8 — Produce the writeup

Format:

```markdown
## <Player Name> deep dive (as of <date>)

### Model says (<bucket>):
- Recent rolling proj: **<X.XX> <FP/PA or FP/start>** (rank #<N>)
- (SP only) Floor/ceiling band: <P25>-<P75> | data_quality: <data_driven_full|data_driven_thin|marcel_il|marcel_no_data>
- (SP only, when |marcel − data| >= 2 FP) **Marcel vs data divergence: model and Marcel disagree by X FP (marcel=A, data-driven=B)** — headline is in an unstable transition zone
- Historical/prior:    <Y.YY>  (recency_form_gap: <±Z>)
- Signal: <hold / strong add / pass>
- Read: <one sentence interpretation of the gap>

### Recent shape (Statcast, last <N> outings):
- <key metric trend>: <values>
- <notable velo/whiff/bat-tracking observation>

### Injury status: <ACTIVE | IL10/IL15/IL60 with return date>
- <short_comment if injured>

### Availability:
- Owned <X.X>% (8-team translation: <FA-friendly | borderline | rostered>)
- If rostered: which team

### Vs your roster (if applicable):
- Weakest current <bucket>: <player> (<proj>)
- Net weekly FP gain if swap: <±N>
- Positional flex: <note>

### Archetype layer:
- Archetype: <LABEL> (<C/P/D or S/M/C ratings>), boundary <tier>, age tier <tier>
- T+1: <X.XXX> (and T+2 if SP/RP)
- RP-only: CLOSER/leverage_tier/FIREMAN tags
- Comps (3-5): <one-line summary of T+1 outcome distribution>
- Comp verdict: SUPPORTS_<CONSIDER|SKIP|NEUTRAL>

### Verdict: **PASS / CONSIDER / SKIP** (with one-sentence reason)
- Primary driver: <rh3/rp3/rprs2 signal>
- Archetype adjustment: <bumped toward X because Y, or "no adjustment">
```

### Verdict adjustment rules (archetype layer)

The model verdict is the anchor. Apply at most one archetype bump
(don't double-count):

1. **Comp-density rule.** Define "meaningfully" as ≥ 10% relative change
   in fp_per_pa (hitter), fp_per_start (SP), or fp_per_g (RP).
   - If ≥ 4 of 5 comps had T+1 outcomes meaningfully BELOW their T-year
     level → bump verdict one step toward SKIP.
   - If ≥ 4 of 5 comps had T+1 outcomes meaningfully ABOVE T-year level
     → bump verdict one step toward CONSIDER, even if rh3/rp3 is
     lukewarm.
   - Otherwise neutral.

2. **Archetype-trajectory rule.** Compare current-year archetype to the
   prior-year row (same player) if present:
   - DOWNGRADE (e.g. ELITE → POWER_EYE, or SP STUFF tier drop): bump
     toward SKIP **unless** rh3/rp3 is strongly positive (recency_form_gap
     ≥ +1.0 FP/start or +0.020 FP/PA).
   - UPGRADE (e.g. POWER → ELITE): bump toward CONSIDER.
   - STABLE: no adjustment.

3. **RP role overlay** (RPs only; applies BEFORE generic rules):
   - `leverage_tier in {MID, LOW, GARBAGE}` → cap verdict at SKIP
     regardless of rprs2. They are not seeing save/hold opportunities,
     and rprs2 can't fix that.
   - `CLOSER == True AND leverage_tier in {ELITE_LEVERAGE, HIGH_LEVERAGE,
     ELITE, HIGH}` → real add; bump toward CONSIDER if model is even
     neutral.
   - `FIREMAN == True` (when column present) → flag as "wins in tight
     games" — informational, no automatic bump.

If the archetype layer would flip PASS → SKIP or SKIP → CONSIDER, say
so explicitly in the verdict line ("Model said CONSIDER, archetype
downgraded to SKIP because 4/5 comps declined at T+1").

---

## Step 7.6 — Anti-overhype guardrail (MANDATORY before any "TOP ADD" / "model lagging" / "hidden gem" / "buy before model catches up" claim)

Triggered whenever the writeup would assert ANY of:
- "model hasn't caught up to him"
- "the model is anchored to an old prior"
- "near-elite hot bat"
- "hidden gem" / "TOP ADD"
- recent HR streak (≥3 HR in L7d) framed as evidence of skill change

Before stating any of those, you MUST run the four checks below and SURFACE THEIR RESULTS in the writeup. If any check fails, downgrade the label.

### 7.6.1 — Bayesian shrinkage on season + L21d xwOBA

```python
k = 150  # xwOBA stabilization
baseline = xwoba_2025          # or career mean if 2025 thin
shrunk_szn = (n_szn * obs_szn + k * baseline) / (n_szn + k)
shrunk_l21 = (n_l21 * obs_l21 + k * baseline) / (n_l21 + k)
```

**Decision rule:** anchor the verdict to the shrunk gap, not the raw gap.
- Shrunk gap ≥ +.040 → real improvement
- Shrunk gap +.015 to +.040 → modest, soft "consider"
- Shrunk gap < +.015 → **NOT a breakout. The model is right at his prior.**

### 7.6.2 — 95% CI overlap check

```python
se = 0.39 / sqrt(n);  ci = (obs - 1.96*se, obs + 1.96*se)
```

If 2025 baseline xwOBA is INSIDE the season-level CI → the "breakout" cannot be statistically distinguished from his baseline. Use phrasing like "consistent with prior baseline" — never "the model is lagging."

### 7.6.3 — L21d xwOBACON vs season xwOBACON (HR-streak sanity)

If recent HR rate is loud (L7d/L21d HR pace ≥ 2× season pace) but L21d xwOBACON is FLAT or BELOW season xwOBACON → the HR cluster is outcome-driven, NOT a contact-quality skill change. **Do not cite HR cluster as evidence of breakout.** Say "recent HR cluster is outcome-driven; contact quality (L21d xwOBACON) flat-to-below season."

### 7.6.4 — Historical comp T+1 regression

Pull 5-10 prior-year batter-seasons matching the candidate's current K%/BB%/xwOBACON/EV90 profile (±2 pp K, ±1.5 pp BB, ±.020 xwOBACON, ±2 mph EV90, PA ≥ 250). Compute mean T+1 xwOBA.

- If comp class T+1 mean is ≥ candidate's current → archetype sustains
- If comp class T+1 mean is < candidate's current by .020+ → **expect regression. Say so.**

### 7.6.5 — Output requirement

When the user asks "is X good" or "deep dive X" and you intend to recommend, the writeup MUST include a "Sustainability Check" section with:
- Shrunk gap (raw vs Bayes)
- 95% CI vs baseline
- L21d xwOBACON vs season xwOBACON
- Comp T+1 mean xwOBA vs current

If any of these fail and you still recommend, explicitly state "I'm recommending despite [failed check] because [reason]." Never silently omit a failed check.

### 7.6.6 — Verdict downgrade ladder

| Failed checks | Verdict cap |
|---|---|
| 0 failed | full CONSIDER allowed |
| 1 failed (typically comp T+1) | CONSIDER but flag as "narrow breakout" |
| 2 failed | SOFT_CONSIDER — match to drop target only |
| 3+ failed | **PASS or SKIP**, regardless of recent HR/xwOBA narrative |

**Canonical failure case (do not repeat):** Casey Schmitt 2026-05-31. Recommended as "near-elite hot bat the model hasn't caught up to" based on PL #50 vs rh3 #76 (26-rank gap) + 4 HR L7d. Subsequent rigorous check showed:
- L21d xwOBA EXACTLY = 2025 baseline (.328) — no actual breakout L21d
- Bayes shrunk season gap +.033 → **+.019**
- 2025 baseline INSIDE both season and L21d CIs
- L21d xwOBACON .388 BELOW 2025 .396 — power streak outcome-driven
- 8 comps regressed −.050 xwOBA at T+1 (Bichette, Perez)
- True verdict: NARROW BREAKOUT on K% only, not "hidden gem"

K% improvement WAS real (multi-axis), but the recommendation should have been "fair add at his rh3 #76 tier," not "model lagging."

---

## Anti-patterns this skill exists to prevent

- Quoting projection numbers without their prior/recent gap context
  (the gap IS the story for FAs)
- Citing xwoba_gap_to as a buy signal — degraded to no-op
  (see registry 2026-05-16 re-audit)
- Recommending an IL'd player without surfacing return_date
- Recommending someone who's actually on another team's roster
- **Inferring roster status from percent_owned** — "60% owned = probably rostered in 8-team"
  is WRONG. Always call `get_all_teams()` and check `team.roster` explicitly. The
  Sheehan error (2026-05-25): 60.7% owned → concluded "almost certainly rostered" →
  he was a FA. percent_owned is national ESPN data across all league sizes; it is
  not a reliable proxy for 8-team roster status.
- Forgetting to compare to user's drop target — "is X good" is less
  useful than "is X better than what I'd drop for him"
- Using rh3 to rank an RP (use rprs2)
- Resolving a named player to the wrong rh3/rp3 row because of a
  same-name collision. Always check for duplicate `_norm()` keys when
  Step 1 matches a player. See `/player-id-resolve`.
- **Citing a small PL/model rank gap (≤30 ranks) as "the model is lagging."**
  Schmitt 2026-05-31: PL #50 vs rh3 #76 is a 26-rank gap — well inside
  normal between-source noise. A "model anchored on prior" claim requires
  a ≥50-rank gap AND a Bayes-shrunk season xwOBA improvement of ≥+.040,
  not just a directional disagreement. Run Step 7.6 before any "model
  lagging" framing.
- **Selling a recent HR cluster as a breakout without checking L21d xwOBACON.**
  If L21d HR rate is ≥2× season pace but L21d xwOBACON is flat-to-below
  season xwOBACON, the HR streak is outcome-driven and will regress.
  Step 7.6.3.
- **Quoting raw observed gap instead of Bayes-shrunk gap.** A 75-PA L21d
  observation gets pulled hard toward baseline by k=150 shrinkage; the
  raw gap overstates the breakout by ~2-3×. Always report shrunk.

---

## When NOT to use this skill

- User wants to compare 2+ players head-to-head (use a different
  pattern: build a side-by-side comparison instead)
- User wants league-wide FA scan (use `/roster-audit` Step 7 instead)
- User wants a historical analog analysis (this is a different
  skill candidate: `/historical-analog` not yet built)


## Physical-trend layer (bat-tracking, added 2026-06-16)

Surface the physical getting-better/worse read from the validated `/trending`
engine. It is **DISPLAY/CONTEXT only** — never moves the projection or flips the
headline (CLAUDE.md #13) — and routing through the one engine keeps a player's
read identical across skills (#12).

```python
from scripts.xfp.lib.trend_signal import trend_line, hitter_trend_table, pitcher_trend_table
ht, pt = hitter_trend_table(), pitcher_trend_table()   # batch: reuse across players
tag = trend_line(name, team=pro_team, position=pos, hit_tbl=ht, pit_tbl=pt)  # or role='SP'/'RP'
```
Quick CLI: `python scripts/xfp/run_trending.py --names "A, B"`.

- **Hitters = 3-axis** (bat speed + attack angle toward ~15deg band + fast-swing%
  intent), each non-redundant; validated as an EARLY-WARNING read (bat speed
  trustworthy in ~20 swings vs 6-12 wks for the rate stats). **Pitchers = FB velo**
  (induced bat speed REJECTED for pitchers). Attack angle is direction-aware
  (toward band, NOT "up = good").
- **Necessary-not-sufficient:** a 🔺/🔻 flags the physical TOOL moving; confirm with
  the contact/results column in the tag (tool-moved-but-not-yet-translating is common).
- **Add the tag to the single-player card** next to the recent-Statcast block: a rising tool strengthens a CONSIDER; a 🔻 with confirming contact is a yellow flag on an add.

Validation: `data/research/validation_runs/early_season_bat_speed_2026-06-16.md`.
