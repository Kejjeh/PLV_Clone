# Don't do these (load-bearing feedback) — full text

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). CLAUDE.md is
auto-loaded into every session and had drifted to 635 lines against its own
~200-line budget; every line is a permanent tax on every turn, and a gotcha
list nobody finishes reading is a gotcha list that does not fire.

Nothing here was rewritten or shortened — the text below is what CLAUDE.md
carried. CLAUDE.md keeps a one-line headline per rule, numbered identically,
so the rule still fires from the auto-loaded file and the evidence is one hop
away. Numbering is load-bearing: memos and skill docs cite "gotcha #12" and
"don't-do #10" by number. Never renumber; retire in place. -->

1. **Don't drop a feature into rh3/rp3/rprs2 without `/validate-feature`.**
   Rule 9: baseline must include ALL existing production features.
   Stripped-down backtests over-claim lift (we got burned 4× on rh3 v2).
2. **Don't count IL slots from `injured==True`.** Use `lineup_slot=='IL'`
   to compute free IL capacity. A player can be IL'd while in their
   starting slot (Langford OF) or on the bench (Helsley BE).
3. **Don't use n_pos_flags or the composite "rolling trend" flag** to
   rank or filter FAs. Validated as noise (v3, 2026-05-11).
4. **Don't recommend players from other teams' rosters** as "best available."
   FAs only — use `get_free_agents()` exclusively.
5. **Don't commit `*.parquet`, `*.pkl`, or `*.bak` files** — they're
   gitignored. The refresh script creates `.bak` backups automatically.
6. **Don't use per-position `get_free_agents(position=X, size=300)` for
   pool scans.** Silently drops low-owned high-FP candidates. Always
   `league.free_agents(size=2000)` + manual position filter for any
   "all FAs above threshold" query. See `feedback_fa_pool_size_cap.md`.
7. **Don't conclude a player is rostered without calling `get_all_teams()`.**
   Neither PL rank nor percent_owned is a substitute. PL ranks reflect
   MLB performance, not 8-team roster state (Connelly Early, 2026-05-18).
   percent_owned is national data — 60% nationally owned is routinely
   unclaimed in 8-team (Emmett Sheehan, 2026-05-25: 60.7% owned, confirmed
   FA). Always verify via `league.teams` roster scan before concluding
   anyone is unavailable. See `feedback_pl_rank_not_equal_fa_available.md`.
8. **Don't recommend dropping a hitter without checking xwOBA L21d
   vs 2025 baseline AND xwOBACON year-over-year trajectory first.**
   MC can show "drop" while the underlying contact quality says "bounce
   coming." The YoY trajectory determines whether prior slump/recovery
   patterns are valid templates: if xwOBACON is declining each year
   (Turner pattern), recovery will hit a lower ceiling than prior
   troughs. If xwOBACON is stable, prior recoveries predict this one.
   See `reference_xwoba_l21d_vs_2025_diagnostic.md`.
9. **Don't trust matchup.html SP projection blindly.** Four known bug
   patterns can cause undercount, IL'd-projected, or mlbam-None false
   matches. Run `/matchup-audit` after any change to
   `scripts/xfp/build_matchup_dashboard.py`. See
   `reference_matchup_dashboard_sp_gotchas.md`.
10. **Don't lookup batter IDs by name alone.** Same-name MLB players
    (canonical: Max Muncy LAD vs ATH) silently grab the wrong row in a
    `dict[name]=batter_id` map. Always use
    `plv_clone.utils.name_match.resolve_batter_id(name, team=..., position=...)`
    (or `resolve_pitcher_id(name, team=..., role=...)`) which consults
    `KNOWN_COLLISIONS` and refuses to silently guess. See
    `feedback_player_name_collisions.md` and `/player-id-resolve`.
    **NEVER `df[player_name.str.contains(last_name)]` for a stats/projection/draft
    lookup** — a surname substring grabs the wrong same-name player and `.iloc[0]`
    hides it. Canonical 2026-06-26: **Will Warren** (701542, NYY, STARTER) vs
    **Austin Warren** (681810, NYM, RELIEVER) — a `contains('Warren')` query pulled
    Austin's relief games into Will's profile, falsely showing Will "moved to the
    bullpen." (Will/Austin differ on FIRST name so they normalize differently —
    a normalized FULL-name match is safe; only same-FULL-name pairs like Muncy /
    the Garcias need a team hint.) A workflow audit fixed every skill engine doing
    this (`run_fa_monitor`, `build_sp_alerts`, `bench_tracker`, `week_schedule_tilt`,
    matchup boom-scan); the rule: resolve to mlbam with team/role, else a normalized
    FULL-name match (skip-on-ambiguous) — never last-name `contains`. The boxscore
    store + `lib/boom_bust.py` were already mlbam-keyed (safe). Locked by
    `tests/test_name_collision.py`.
11. **Don't label any player as "yours" without a live roster call.**
    On 2026-05-25, Weathers and Rasmussen were labeled "Your SP" from
    session memory — both were on opponent rosters. Always call
    `get_my_roster_with_injuries()` first and use `my_tag()` to annotate.
    See `/roster-verify` skill.
12. **Don't headline a single lens or let a verdict flip across turns.**
    The SAME player (Steer 2026-06-09) was called "cooling" one turn and
    "BUY/rising" the next because different runs foregrounded different
    slivers (the `decision_type_lens_registry` "Skip" columns optimize
    brevity over consistency). For ANY user-facing player verdict: COMPUTE
    and SHOW the full lens stack, give an explicit **actuals vs trajectory
    vs process** reconciliation when they diverge, and keep the headline
    **stable + lens-order-independent**. A verdict may change only on (a)
    new data (a refresh) or (b) a corrected error — and when it changes,
    say WHY. Never flip silently. See `reference_lens_merge_protocol.md`
    ("ALWAYS run + SHOW the full stack").
13. **Don't treat the lens stack as additive point-forecast lift.** Validated
    2026-06-11 (`lens_value_add_2026-06-11.md`, leakage-safe player-clustered
    OOS): the multi-lens synthesis does NOT beat the base rank at
    point-forecasting forward FP — clean ΔR² **+0.006 H (n.s.) / −0.014 SP
    (negative)**; the +0.033 was an L7 leakage artifact. Lenses earn their keep
    ONLY as **conviction / conflict surfacing** (agreement count sorts realized
    direction monotonically: LOW +0.15 → MED +0.30 → HIGH +0.47 FP/g), NOT as a
    free R² boost. **xwOBA-L21d (hitters)** and **boom-bust + sustainability
    (SPs)** are NON-additive / mildly negative as point terms — use them for
    CONTEXT and as Tier-B gates, NEVER to move the projection. Headline number
    stays rh3/rp3/rprs2 / baseline xFP. See `reference_lens_merge_protocol.md`.
14. **Don't headline a Stuff+ "buy-low" for a veteran without the decline
    cross-check.** Stuff+ measures stuff LEVEL, not TRAJECTORY — a high-Stuff+ /
    lagging-results SP can be a real decline, not a buy. Before headlining BUY,
    cross-check (a) archetype STUFF-rating YoY slope
    (`data/research/sp_archetype_career_panel.parquet`), (b) sustainability
    K%/SwStr decomp (`scripts/xfp/pitcher_sustainability.py`), (c) archetype
    trajectory + comp T+1. If ≥2 signal real decline → headline **"DECLINING —
    back-end / defensible drop, not a buy,"** NOT the Stuff+ buy. Canonical:
    **Framber Valdez 2026** (Stuff+ 103 looked buy-low, but STUFF 56→46 YoY,
    K% −4.7pp / SwStr −2.4pp, TRENDING_DOWN slope −4.5, comps avg 10.7 FP/start
    T+1 = real decline, not luck). See `/sp-stuff-board` mandatory cross-check +
    `reference_lens_merge_protocol.md` SP conflict rule #6.
15. **Don't execute/recommend a drop on a "declining" skill read from a SINGLE
    window** (one bad week of xwOBACON, K%, or bat speed). Require the decline
    to show in ≥2 non-overlapping windows (e.g. L7 AND L21, or L21 AND the
    trailing month) before it counts as a real trend — a one-week dip can look
    exactly like a trend and reverse completely within 2 weeks. **Canonical:
    Trea Turner** — dropped 2026-06-19 on xwOBACON/K% "decline," but the whole
    read traced to one bad week (6/8: bat speed 68.7mph, K% 37%) that had
    already partially recovered by the drop date (6/15: 70.9mph) and fully
    reversed by July (K% 19.3%, bat speed 70.2mph — his best month of the
    season). The call matched the data in hand at the time; the fix is
    requiring a second confirming window before the data counts as a trend,
    not blaming the read in hindsight. Apply this before any drop recommendation
    in `/moves`, `/roster-audit`, `/forced-drop-planner`, or `/decision-gates`.
16. **Don't let a short-hold FA add/drop (<48h, a same-day scouting look) go
    unchecked forever.** A player added and dropped within a day or two gets
    zero real evaluation — if he breaks out weeks later you'll never know
    unless something re-scans him. **Canonical: Louis Varland** — added/dropped
    same week 2026-04-19/20 by the Ligers, claimed by an opponent 8 days later,
    now rprs2 **#4 overall** (+136.2 replacement_delta) — a top-5 league-wide
    reliever that got a one-day look. **Bryan Baker** is the same pattern one
    level over: never rostered at all, now rprs2 **#5** (+114.7). Signal D
    (Drafted-Then-Dropped Comeback) in `/fa-monitor` only checks prior-YEAR
    draft history — it does not catch same-season short-hold churn. Signal P
    (Short-Hold Churn Re-scan, added 2026-07-20) closes this gap: it re-checks
    every player added-then-dropped within 48h by ANY team in the last 30 days
    against current rp3/rh3/rprs2 rank, 3+ weeks after the churn event so real
    signal has had time to show. Run as part of the regular `/fa-monitor` sweep.

17. **Two statistical traps that cost this repo real time — check both, every study
    (2026-08-27).**
    a. **NEVER compare an r across frames.** Target-window length alone moved r from
       0.363 (2-3 remaining starts) to 0.523 (16+) — larger than ANY feature effect
       measured in that session. A durability filter moved it 0.247 → 0.529. An
       "our metric beats the model" claim is a frame artifact until both sides are
       measured on the SAME population and the SAME target window. This retracted a
       headline finding the same day it was made.
    b. **A permutation p cannot go below 1/(B+1).** BH-FDR over M tests needs the
       smallest p ≤ q/M. With B=400 and M=1339 the floor is 0.0025 against a bar of
       7.5e-5, so NO test can EVER be rejected — a guaranteed null that looks like a
       finding. **Always assert `1/(B+1) < q/M` before believing a permutation null.**
    c. Corollary already bitten twice: **always report one-row-per-player-season next to
       any pooled result.** A pooled partial r of +0.047 (N=14,601) came from 1,327
       pitcher-seasons and flipped to −0.049 once collapsed. Pooled n is not sample size.
    d. **Dispersion (observed/binomial variance) is only valid on genuine 0/1-per-event
       rates.** TB/PA (0-4 per PA) and ER/TBF (a count) inflate to 1.81/1.36 while having
       the LOWEST reliability; including them flips the pooled correlation from +0.459 to
       −0.526.

18. **Don't ship a guard or a fix without sweeping its sibling call sites
    (issue #69).** Across the 2026-08 bug-audit waves this was the single most
    common bug shape by a wide margin — not a wrong algorithm, but a CORRECT fix
    applied to a strict subset of the places that needed it. Every wave but one
    found an instance: fail-soft breadcrumbs no caller could read; a season
    de-hardcode covering 3 driver commands and not the 125-site library layer;
    a collision gate added to `resolve_batter_id` but not to
    `lookup_batter_id_cached`, which front-runs it; a Rule 13 leak check naming
    three models while `rh3_april` went unchecked; an mlbam `KeyError` guard on
    the hitter and RP levers but not on either SP lever — including the bench
    lever the bug was named after.

    They keep happening because the sibling sites are NOT adjacent in the file
    and share no enforcing structure. Nothing says "these four levers must be
    guarded the same way." The invariant lives in a person's head at fix time,
    and the second half gets written later or not at all. Each one then failed
    SILENTLY — a 0.00pp delta, a wrong player id, a stale season — rather than
    crashing.

    Two habits close it:

    a. **Grep for the siblings before committing.** For the lever bug that was
       literally `grep -n "def assemble" -A 30` and reading the parameter list:
       four key-taking levers, two guarded. Thirty seconds.
    b. **Prefer DISCOVERY over ENUMERATION in guards.** Replace a hardcoded
       three-model dict with a package walk and the NEXT model is covered on
       the day it is written; a guard that enumerates will drift, a guard that
       discovers won't. Canonical examples in this repo: the `*_FEATS` package
       walk in `test_lens_context_only`, the `__all__` completeness check, the
       consumer walk in `test_schedule_fetch_contract` (CLAUDE.md named ONE
       consumer of `fetch_schedules_by_team`; discovery found five).
