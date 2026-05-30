---
name: league-deep-audit
description: Full league-wide statistical roster audit across all 8 BrownU teams. Runs league_wide_full_audit.py v4 (calibrated, ECE=0.0197 on 15,778 hold-out snapshots) which chains 11 layers — career-form percentile, 9-marker sustainability, xwOBACON/Bayesian shrinkage/anchor-in-CI slump diagnostics, process metrics (bat speed/whiff/chase/Z-contact/EV90), slump trajectory + K%-decomp + pitch-mix, PEAK validator (PROCESS_DRIVEN vs OUTCOME_DRIVEN), injury signal integration (ESPN DTD/IL), MC bounce simulator (10k sims, λ=0.20 recency decay), Bayesian posterior talent estimator (recency-weighted prior), historical comp matcher (54,026 real 2015-2025 snapshots, age-matched ±3yr), peak decay survival curves with Wilson CIs, and SP velo/k-form. Outputs: power ranking, per-team position breakdown, slump cards with 4-signal convergence, PEAK cards with survival curves + CIs, trade targets, sell-high alerts. Use weekly or when making a significant trade decision that requires knowing the full landscape across all 8 teams.
---

# league-deep-audit

You are running the full league-wide statistical roster audit.
The skill exists because individual player analysis (`/slump-or-decline`,
`/breakout-sustainability`) is expensive to run 8× across all teams — and
the most actionable information (trade targets, mispriced players, power
ranking) only emerges when you see the WHOLE landscape at once.

The engine is `scripts/xfp/league_wide_full_audit.py` (v4). All
11 statistical layers are pre-built and cached — this skill is the
orchestration and interpretation wrapper.

**v4 statistical upgrades (2026-05-25):**
- **Recency-weighted distributions** (λ=0.20): MC + Bayesian prior both use
  exponential decay by year so stale-form seasons don't pollute career estimates.
  Half-life ~3.5 years. Results: `decay_lambda`, `effective_n_windows` in output.
- **Age-matched historical comps** (±3yr): comp matcher now filters by player age.
  Freeman's comps dropped 384→104 and bounce rate corrected from 56% to 49%.
  Always check `n_comps_age_filtered` vs `n_comps_before_age_filter`.
- **Survival curve CIs** (Wilson score): each survival checkpoint has `ci_low/ci_high`.
  CIs are ±0.2-0.4pp (direction very reliable). PROCESS_DRIVEN_STRONG tier needs
  EV threshold recalibration — threshold of 92.0 is calibrated to single-pitch EV,
  not window mean EV (~85 mph peak). Currently shows 0% STRONG; use PROCESS_DRIVEN tier.
- **Injury signal integration**: ESPN DTD/IL status for all rostered hitters.
  `classify_injury_impact()` flags SLUMP_EXPLAINED / POSSIBLE_FACTOR / NO_OVERLAP.
  Slump verdicts modified when injury overlaps slump start window (±45 days).
- **Calibration validated**: ECE=0.0197 (WELL_CALIBRATED) + Brier=0.2221 on 15,778
  out-of-sample snapshots (train 2015-2022, test 2023-2025). Probabilities are
  trustworthy. _Known limitation: adjacent rolling-150 windows are not i.i.d.
  (share 149/150 events); stated precision is slightly optimistic._

---

## 11 layers as independent lenses

The audit's power comes from running 11 statistical layers that each anchor on a different aspect of player evaluation. They are **not** redundant — each lens has a different known failure mode, and the audit's verdicts depend on the agreement pattern across the panel. Reading "the X% bounce" without knowing which layer it came from is a category error.

| # | Layer | What it measures | Anchor | Known failure mode |
|---|---|---|---|---|
| 1 | Career-form percentile | Where current L150 sits in this player's career rolling-150 distribution | Career distribution | Mis-states "trough depth" when career sample is thin (<5 prior windows); a true rookie always looks at career-low |
| 2 | 9-marker sustainability | Statcast process decomposition: EV, EV90, HardHit, Barrel, xwOBA-contact, K, BB, chase, sweet-spot | Recent window vs season | Markers move on different time-scales — bat-speed stabilizes fast, K% slowly; reading the panel as one number flattens the signal |
| 3 | xwOBACON Bayesian shrinkage | Shrunk xwOBACON gap vs career baseline | Conjugate normal prior on career | Strong-prior veterans get pulled toward career mean regardless of how bad the season is, masking true decline |
| 4 | Anchor-in-CI test | Does the 95% CI of L21d xwOBA contain career baseline? | Sample-size statistical confidence | A wide CI (~80 PA) yields "noise" verdicts even when underlying decline is real but slow |
| 5 | Process metrics audit | Bat speed / whiff / chase / Z-contact / EV90 trend vs baseline | Within-player year-over-year | Year-over-year alone misses regime shifts — a player who lost EV in April and stabilized at lower level looks "stable" by August |
| 6 | Slump trajectory + K%-decomp | K%-by-pitch-type to identify which pitches are eating the bat | Pitch-shape attribution | Sample-size noise per pitch type — needs ~60 PA per pitch family to be stable; thin for short-stretch slumps |
| 7 | PEAK validator (PROCESS vs OUTCOME) | Distinguishes a peak driven by process improvement vs outcome variance | Recency-weighted process anchor | Threshold (EV ≥ 92.0) calibrated to single-pitch EV not window mean — currently under-reports STRONG tier |
| 8 | Injury signal integration | ESPN DTD/IL overlap with slump start window | Time-aligned injury timeline | ESPN injury data has lag and granularity issues; "playing through" undeclared injuries produces decline signature without an injury flag |
| 9 | MC bounce simulator (10k sims, λ=0.20) | Recency-decayed bootstrap of career rolling-150 windows | Career distribution with exponential decay | Adjacent windows share 149/150 events — i.i.d. assumption violated; stated probability precision is slightly optimistic |
| 10 | Bayesian posterior talent | Conjugate update P(true talent > threshold) | Career mean + recent data | Identical to lens 3 plus formal P() language — provides a number but is co-linear with shrinkage layer; agreement is structural, not independent confirmation |
| 11 | Historical comp matcher | 54k 2015-2025 snapshots, age-matched ±3yr | Population of comparable situations | Bucketing on age + percentile + month misses archetype context (power vs contact); thin for very old / very young players |

**Auxiliary**: SP velo/k-form (pitcher subset) — measures FB-velo trend + K-rate-stability for SPs. Failure mode: rookies + post-TJ pitchers have insufficient velo history to anchor.

**How to read disagreement**: the highest-value moments are when lenses point in different directions. Lens 9 (MC) says "bounce" but lens 4 (CI anchor) says "L21d CI excludes baseline" = the slump is statistically real even if it's historically common. Lens 2 (process markers) say "improving" while lens 11 (comps) say "fade" = the player has a new skill but historically that profile hasn't sustained — a real edge if your league hasn't priced it in.

---

## Inputs (all optional — sensible defaults apply)

1. **Focus** — `full` (default) / `hitters-only` / `pitchers-only`
2. **Rebuild caches?** — `yes` to force-rebuild statcast cache + career-form
   features before running. Default: use existing caches if < 24h old.
3. **Trade context** — if the user is evaluating a specific trade, name
   the players on each side so the report surfaces their detail cards first.

---

## Pre-flight (always run)

Verify required caches exist and are < 24h old:

```
data/research/xfp_cache/batter_rolling_features.csv
data/research/xfp_cache/name_resolution_2026.csv
data/research/xfp_cache/historical_comp_snapshots.parquet  (54k snapshots, age column required)
data/research/peak_survival_curves.json                    (v4: includes Wilson CI keys)
```

Optional reference:
```
data/research/bounce_calibration_report_2026-05-25.md  (ECE=0.0197 validation report)
```

Verify model projections < 48h old:
```
data/outputs/xfp_rh3_projections.csv
data/outputs/xfp_rp3_projections.csv
data/outputs/xfp_rprs2_projections.csv
```

If any are missing or stale: `python scripts/xfp/refresh_dashboards.py` first.

---

## Step 1 — Run the audit

```bash
python -X utf8 scripts/xfp/league_wide_full_audit.py
```

Expected runtime: 3-8 minutes (DuckDB queries dominate; MC + Bayesian
are vectorized and fast). The script prints step-by-step progress.

Output files:
- `data/research/roster_deep_audit_league_full_<TODAY>.md` — full report
- `data/research/league_sust_full_<TODAY>.csv` — raw per-player data

---

## Step 2 — Read and interpret the 11-layer report

The report sections in order:

### Section 1: Statistical confidence summary
The load-bearing table. Shows convergence of 4 independent tests for
each slumper:

| Player | MC P(bounce) | Bayes P(>avg) | Hist comps | Hist P(bounce 30PA) | Verdict |

**How to read it:**
- **MC P(bounce)** — bootstrap: what fraction of 10k career-distribution
  simulations project next-30PA xwOBA above career median? > 60% = bounce likely.
- **Bayes P(>avg)** — posterior talent vs 0.320 league average. The most
  important number: < 40% means even with full career history, Bayesian
  updating puts this player below average talent level right now.
- **Hist comps** — real 2015-2025 players at same career %ile/PA/month.
  > 200 comps = reliable estimate; < 50 = treat as directional only.
- **Hist P(bounce 30PA)** — of all historical comps, what fraction had
  a meaningful xwOBA improvement within 30 PA? > 60% = strong bounce base-rate.

A player with 4 green lights (MC > 50%, Bayes > 60%, comps > 100,
hist bounce > 60%) is an aggressive HOLD or BUY. A player with 4 red
lights is the only true DROP candidate.

**CONSENSUS_DROP gate:** requires ALL of — REGRESS sustainability + process
DECLINING/MIXED + Bayesian-shrunk gap < −0.030 + historical bounce pct < 50%.
If ANY one of those is missing, the verdict floors at SLUMP_AMBIGUOUS.
In practice this gate is rarely triggered — the 4 statistical layers
systematically identify which "career-low percentile" players are bounce
candidates vs structural declines.

### Section 2: Power ranking
Sorted by mean rh3 per-PA across the roster. Key columns:
- `mean_bayes_p_avg` — average posterior talent vs league average across the whole roster.
  This adjusts for "hot starts that are really OUTCOME_DRIVEN peaks."
  A team with mean_bayes_p_avg > 0.70 is genuinely deep.
- `n_improving` vs `n_declining` — process trajectory count. A team with
  3 IMPROVING processes is likely to see production rise; 4 DECLINING is a warning.
- `sp_velo_flags` — SP injury/fatigue signals in the rotation.

### Section 3: Per-team position breakdown
Full hitter table by position group per team, sorted by rh3. Key columns
added in v3:
- `mc_p_bounce_median` — for slumpers: how likely is a 30PA bounce?
- `bayes_p_above_avg` — Bayesian posterior talent estimate
- `bayes_games_to_200fp` — how many games to accumulate 200 FP at career rate
- `hist_p_bounce_30pa` — historical comp bounce rate
- `peak_trade_window` — HOLD_SHORT / SELL_NOW for peakers

### Section 4: Slump detail cards
Per-player card for each SLUMPING player. The card synthesizes all 11 layers:

```
### Player Name (Team, POS)
- Career %ile: X% | Sust: bucket | Process: verdict
- Bounce history (rh3): X% of N comparables bounced | uplift: +Y/PA
- Bayesian shrunk gap: ±Z | anchor: A.AAA | anchor_in_CI: YES/NO
- xwOBACON gap: ±Z (contact intact / contact declining)
- Process: whiff% 2025→L21d | chase% | EV90
- MC bounce (10k sims): P(next 30PA > career median) = X% | Expected xwOBA: X.XXX | 95% CI: [X, X]
- Bayesian talent: posterior μ = X.XXX | 95% CI | P(talent > career median) = X% | P(talent > .320) = X% | Games to 200 FP: N
- Historical comps (2015-25): N comparables | P(bounce 30PA) = X% | P(bounce 60PA) = X% | Median next-30PA: X.XXX | 10-90 range
- K-decomp source: TYPE
- May career history: YYY: X.XXX (NPa) | ...
- VERDICT: cross_verdict — rationale
```

### Real-world example (2026-05-25 run)

**Power ranking (top → bottom):**

| Rank | Team | mean_rh3 | mean_bayes_p_avg | n_improving | n_declining |
|------|------|----------|-----------------|-------------|-------------|
| 1 | Late Night Bettsing | 0.574 | 0.791 | 2 | 7 |
| 2 | U Just Lost To Edwin Diaz | 0.555 | 0.601 | 3 | 7 |
| 3 | 2015 Draft First Round | 0.551 | 0.732 | 4 | 5 |
| 4 | **New York Ligers** | 0.549 | 0.736 | 1 | 3 |
| 5 | Frendy's Fantastic Team | 0.545 | 0.756 | 6 | 7 |
| 6 | Team Solomon | 0.520 | 0.749 | 3 | 6 |
| 7 | Treasure Island Mashers | 0.520 | 0.631 | 5 | 9 |
| 8 | Boone's Bad Bullpen | 0.511 | 0.669 | 7 | 5 |

Note: Team Solomon (rank 6) has the worst mean_pct (0.335) despite decent mean_rh3 — 5 slumpers dragging it down. Frendy (rank 5) looks like a potential sell-high target: highest n_improving (6) and contains the league's only SELL_HIGH_WARNING (Naylor).

**Key slump cards from this run:**

**Freddie Freeman (Boone's Bad Bullpen — rival buy-low target):**
- Career %ile: 14.1% | Sust: STABLE | Process: **IMPROVING**
- MC bounce: 54.6% | Bayesian P(>avg): **97.0%** | Historical comps: 104 (age-matched) | Hist P(bounce 30PA): 49.0%
- Process notes: whiff% -5.7pt, chase% -4.5pt, Z-contact% +5.4pt, EV90 +1.8mph — K-driven slump with improving mechanics
- VERDICT: **CONSENSUS_HOLD_BOUNCE** — process improving despite career-low surface. Buy window is now.
- _Note: age-matching dropped comps from 384 to 104; bounce rate corrected from 56% → 49%. Still directionally positive._

**Vladimir Guerrero Jr. (New York Ligers — your slumper):**
- Career %ile: 13.2% | Sust: REGRESS | Process: DECLINING | DTD (Bruise, Right)
- MC bounce: 53.1% | Bayesian P(>avg): **84.8%** | Historical comps: 596 | Hist P(bounce 30PA): 65.1%
- Process notes: whiff% +3.5pt, chase% +11.3pt, EV90 -5.5mph — BABIP-driven; DTD injury overlaps slump window
- VERDICT: **HOLD_NOISE** — L21d CI includes anchor. Bayesian posterior still 84.8% above avg; 596 comps at 65.1% bounce rate says hold through the bruise.

**Gunnar Henderson (Boone's Bad Bullpen — rival buy-low candidate):**
- Career %ile: 2.1% | Sust: REGRESS | Process: DECLINING
- MC bounce: 36.7% | Bayesian P(>avg): 55.6% | Historical comps: 292 | Hist P(bounce 30PA): **78.1%**
- Process notes: chase% +6.6pt (DISCIPLINE_COLLAPSE sourced) — but anchor_in_CI=YES and shrunk gap only +0.015
- VERDICT: **HOLD_NOISE** — low Bayes (55.6%) is the cautionary flag; 78.1% historical bounce rate from 292 real comps is the buy signal. Lower conviction than Freeman.

**Josh Naylor (Frendy's Fantastic Team — rival SELL_HIGH target):**
- Career %ile: 92.4% | Peak type: **OUTCOME_DRIVEN** | Process: DECLINING
- Bayesian P(>avg): 80.7% | Peak survival: 89.2% at +30PA → 76.2% at +60PA | Expected weeks to reversion: **5.6**
- 778 historical peak comps: only 21.1% bounce upward from current level; median next-30PA xwOBA 0.319
- VERDICT: **SELL_HIGH_WARNING** — surface performance inflated vs true talent. No process metrics improved. Frendy's manager may be buying the narrative.

---

### Section 5: PEAK validator cards
Per-player card for PEAK players (career ≥ 90th percentile):

```
### Player Name (Team, POS) — PROCESS_DRIVEN / OUTCOME_DRIVEN
- Career %ile, rh3, Sust bucket
- Bayesian talent: posterior μ | P(true talent > .320)
- Historical comps: N comps | P(bounce upward from current) | Median next-30PA
- Peak survival: P(still PEAK at +30PA) = X% | +60PA = X% | Expected weeks to reversion: N | Trade window: SELL_NOW/HOLD_SHORT/HOLD_LONG
- Trade implication: cross_verdict — rationale
```

Peak survival curves are the key v3 addition:
- **PROCESS_DRIVEN peaks** (hard-hit + low-K): 81% still PEAK at +30PA,
  63% at +180PA. Expected duration > 7.7 weeks (doesn't cross 50% decay within window).
- **OUTCOME_DRIVEN peaks** (EV or BABIP running hot, discipline not improving):
  91% still PEAK at +30PA but drops to 47% by +150PA. Median survival ~5.6 weeks.
  Sell-high window is within 30-60 PA.

---

## Step 3 — Trade target identification

The trade targets section already filters for:
- Rival team
- CONSENSUS_HOLD_BOUNCE or HOLD_NOISE (statistically supported bounce)
- replacement_delta > 0.002

But manually surface the most actionable case: **rivals with SELL_HIGH_WARNING**
(PEAK + OUTCOME_DRIVEN) whose manager may be willing to sell. Cross-reference
with your roster's CONSENSUS_HOLD_BOUNCE players — the classic buy-low/sell-high
swap opportunity.

Example read: "Offer Vlad Guerrero Jr. (HOLD_NOISE, 63% historical bounce,
79% Bayes talent > avg) for Josh Naylor (OUTCOME_DRIVEN PEAK, 5.6-week
survival curve, only 76% Bayes > avg despite surface performance). Buy the
durable superstar, sell the mirage."

### Real-world example (2026-05-25 run)

The 2026-05-25 audit produced exactly one SELL_HIGH_WARNING across 125 hitters
in the entire league: **Josh Naylor** (Frendy's Fantastic Team).

**The buy-low / sell-high swap opportunity:**

- **Buy-low target:** Freddie Freeman (Boone's Bad Bullpen)
  - At career 14th percentile; IMPROVING process (whiff -5.7pt, chase -4.5pt, EV90 +1.8mph)
  - 97.0% Bayesian P(>avg) — posterior talent is elite despite surface slump
  - 104 age-matched comps; 49% bounce at 30PA, 56.7% at 60PA
  - rh3 = 0.612/PA (top-5 in league). Replacement delta: +0.042 vs your roster
  - **CONSENSUS_HOLD_BOUNCE** — Boone's manager may be willing to sell cheap

- **Sell-high target:** Josh Naylor (Frendy's Fantastic Team)
  - At career 92.4th percentile; OUTCOME_DRIVEN PEAK; process DECLINING
  - Only 21.1% of 778 historical peak comps bounced upward; median next-30PA xwOBA: 0.319
  - Peak survival: 5.6 weeks to expected reversion
  - **SELL_HIGH_WARNING** — surface stats inflated vs true talent (Bayes 80.7%, but no process support)

**The trade pitch:** Offer Freeman (who looks bad in box scores) for Naylor (who looks good). Bayesian priors say you're buying 97% above-avg talent and selling a 5.6-week mirage. Frendy's manager sees a slumping vet vs a hot first baseman — that perception gap is the trade edge.

**Also on the buy side:** Gunnar Henderson (292 comps, 78.1% historical bounce rate, HOLD_NOISE) is a lower-conviction buy-low than Freeman (IMPROVING process) but still a valid trade ask given career 2.1st percentile and Bayes only 55.6% (fair asking price is cheap).

---

## Step 3b — FA add candidates (layer 12)

The audit script calls `_get_league().free_agents(size=2000)` — a single
unfiltered call — and cross-references against the three validated models:

- **rh3** for hitters (keyed by `_norm(name)`)
- **rp3** for SPs (keyed by both "Last, First" and "First Last" with accent
  normalization)
- **rprs2** for RPs (keyed by `name_api`)

Three sub-tables are produced in the report:

**FA hitters — top 15 by `xfp_rh3_per_pa`**

| player_name | position | owned_% | xfp_rh3_per_pa | rh3_signal | form_bucket | process_verdict | career_%ile | cross_verdict |

**FA SPs — top 10 by `rp3_proj/start`**

Columns: player_name, owned_%, rp3_proj/start, form_gap.
Flag IL60 players explicitly — they are **stash candidates**, not immediate
pickups. Do not recommend an IL60 SP as a week-1 streamer.

**FA RPs — top 10 by `rprs2_proj_ros`**

Columns: player_name, owned_%, rprs2_proj_ros.

**Ownership threshold:** filter nothing. Surface all and let the user judge.
In an 8-team league, a player at 48% owned may be genuinely available
(another team may have dropped them since the last ESPN sync). Always verify
with `get_all_teams()` before making an add recommendation — the Connelly
Early bug (2026-05-18) showed that PL/model-ranked players can already be
rostered. See `feedback_pl_rank_not_equal_fa_available.md`.

---

## Step 4 — SP velo flag interpretation

Any SP with velo_flag=True has dropped > 1.0 mph from their L5 vs prior
10-20 start baseline. This is not necessarily an injury — could be load
management or seasonal variation — but it's a monitored list.

Priority checks:
1. Is the K-rate also declining (k_form = LOW or FALLING)? Both signals
   together = real concern.
2. Is the velo drop coupled with fewer starts (possible hidden IL)? Check
   ESPN injury status.
3. Single-start outlier vs trend? Look at velo_delta magnitude: −1.0 mph
   is borderline; −2.0+ mph is a real flag.

---

## Step 5 — Surface the actionable summary (≤ 5 moves)

Synthesize the full report into 5 or fewer concrete actions:

Format:
```
### Recommended moves this week

1. **TRADE OFFER** — [target] (rival team, form, bounce stats) for [offer] (your
   player, peak survival, rationale). Confidence: HIGH/MEDIUM based on convergence.
2. **HOLD** — [your slumper] through the slump. N historical comps, X% bounce rate,
   Bayes posterior still X% above avg. Monitor for N more weeks.
3. **SELL-HIGH** — [rival peaker] may be receptive to selling [rival peak player].
   OUTCOME_DRIVEN peak, X.X weeks to reversion.
4. **WATCH** — [sp velo flag] velocity down N mph. Check next start; if continues drop
   or K-rate falls, evaluate dropping.
5. **HOLD** — [your peak player] has X% survival at +60PA (PROCESS_DRIVEN).
   No action needed; trade interest from rivals is noise.
```

---

## When to re-run

- **Weekly** (Monday) — before each H2H matchup week begins
- **After a significant IL event** — power ranking shifts when a star goes down
- **Before/after a trade** — verify the counterparty player's statistical profile
- **When a player's hot/cold streak is visible in box scores** — the audit
  will surface whether it's a real signal or noise within 3 lines of their card

---

## Relationship to other skills

- `/roster-audit` — run first for slot/cap math. This skill is the statistical
  layer ON TOP of the mechanical roster state.
- `/slump-or-decline` — single-player deep-dive with interactive Statcast
  queries (splits, pitch-mix, rolling trajectory). Use when a player's card
  in this audit raises a question that the summary can't answer.
- `/breakout-sustainability` — single-player breakout decomp for hot players.
  The PEAK validator cards here are the batch equivalent; use the skill for
  a player the user is actively debating acquiring.
- `/fa-pickup-deep-dive` — single-FA evaluation. This audit surfaces who
  to target; the pickup skill does the execution-level due diligence.
- `/roster-deep-audit` — older meta-skill orchestrating 4 component skills
  manually. This skill replaces it for league-wide work. `/roster-deep-audit`
  is still the right choice for YOUR-ROSTER-ONLY audits.
- `/player-id-resolve` — resolves ambiguous player names to a canonical
  batter_id + team. Required when the audit surfaces a same-name collision
  (e.g., Max Muncy LAD vs ATH). Also consults `KNOWN_COLLISIONS` and refuses
  to silently guess. Call before any dict-keyed rh3/rp3/rprs2 join.

---

## Anti-patterns this skill exists to prevent

- **Calling CONSENSUS_DROP on a single signal.** The 4-test convergence
  table exists for exactly this reason. No single test (career percentile,
  rh3 signal, recent box score) is enough. Vlad at 13th career percentile
  looked like a drop; 1,177 historical comps + Bayesian posterior + IMPROVING
  process + 83% bounce rate all said hold.

- **Trusting PEAK form at face value without survival curves.** Josh Naylor
  (OUTCOME_DRIVEN, 5.6-week median survival) vs Ryan Jeffers (PROCESS_DRIVEN,
  7.7+ weeks) have the same surface career percentile but completely different
  trade implications. Always check peak_type + peak_trade_window.

- **Confusing Bayes P(>avg) with a binary good/bad.** A player at 55% P(>avg)
  is genuinely uncertain — their talent is right at the average threshold.
  That's useful context, not a verdict. A player at 9% P(>avg) despite
  being at peak form is a clear sell-high (Naylor pattern).

- **Ignoring the hist_n_comps count.** A 70% bounce rate from 15 comps is
  noise. A 63% bounce rate from 1,177 comps is load-bearing evidence.
  Always check n_comps before trusting hist_p_bounce.

- **Running this skill when you only need YOUR roster.** This is 8-team
  league-wide; 11 layers across 125+ hitters takes 3-8 minutes. For a
  quick "what's my roster situation" question, use `/roster-audit` instead.

- **Building `{_norm(name): row}` dicts over rh3/rp3/rprs2 without collision
  detection.** The canonical failure: Max Muncy LAD (3B, batter_id 571970,
  rh3=0.578 — hold) vs Max Muncy ATH (C, batter_id 691777, rh3=0.379 —
  drop) share identical `_norm()` keys. A live audit on 2026-05-25 used
  the wrong projection and produced a false drop recommendation for the
  wrong Muncy. **Mandatory canonical fix:**

  ```python
  rh3_idx = {}
  dup_keys = set()
  for _, row in rh3.iterrows():
      key = (_norm(row['player_name']), str(row.get('team', '')).upper())
      if key in rh3_idx:
          dup_keys.add(key)
      rh3_idx[key] = row
  if dup_keys:
      print(f"WARNING: duplicate rh3 keys {dup_keys}")
  def rh3_row(name, team): return rh3_idx.get((_norm(name), str(team).upper()))
  ```

  Always pass `pro_team` from the ESPN row as the second key. See
  `/player-id-resolve` for the full protocol.
