# Fast-path gotchas — full text

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). CLAUDE.md is
auto-loaded into every session and had drifted to 635 lines against its own
~200-line budget; every line is a permanent tax on every turn, and a gotcha
list nobody finishes reading is a gotcha list that does not fire.

Nothing here was rewritten or shortened — the text below is what CLAUDE.md
carried. CLAUDE.md keeps a one-line headline per rule, numbered identically,
so the rule still fires from the auto-loaded file and the evidence is one hop
away. Numbering is load-bearing: memos and skill docs cite "gotcha #12" and
"don't-do #10" by number. Never renumber; retire in place. -->

Recurring rediscoveries that cost agents 3-5 tool calls each. Start here:

1. **`marcel_il` artifact (SP).** Many FA-tier + IL'd-at-split SPs (Valdez,
   Bradish, Detmers, Eury Pérez…) carry `data_quality_tag=marcel_il` in
   `xfp_rp3_projections.csv` — their `rp3 per_start` is a SUPPRESSED Marcel
   prior (`gs_to=0`), NOT a real read, NOT an injury flag. **Rank these by
   `Stuff+ proj_ros_fp` (`sp_stuff_model.py`), not rp3.** Trust rp3 only where
   `data_quality_tag` is `data_driven_*`.
2. **Console encoding (Windows).** Prefix python INLINE with
   `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 ` (or `python -X utf8`). cp1252 chokes
   on σ/→/emoji. The `set VAR=…&&` form does NOT persist in the Bash tool.
3. **`get_all_teams()` shape.** Flat pandas DataFrame of ~230 rostered players
   (`player_name, player_id, position, pro_team, team_name, lineup_slot,
   injured, injury_status`) — NOT team objects. Match names two-pass: full
   normalized, then `(last, first-initial)` (never last-only) — Cam/Cameron leak.
4. **Verify "dropped/added" LIVE.** `get_all_teams()` is the only truth; BrownU
   drops sit on ~24-48h waivers (`faab=False`). Canonical: Weathers 2026-06-11
   reported "dropped" but the live scan still showed him rostered.
5. **Don't fan out agents for a single-player / focused question** — do it inline
   in one script. Reserve agent fan-out for genuine broad FA-pool scans.
6. **`sp_bench_mc.py`** imports `fetch_schedules_by_team(team_ids, start, end)`
   (batch) from `build_matchup_dashboard`; keep in sync if that module refactors.
7. **BE slot = active for Josh.** He manages lineup daily — every healthy bench
   player gets activated before lock. **Only `IL`/`IR` slots and `injuryStatus`
   in `IL_INJURY_STATES` / `DAY_TO_DAY` zero a player.** `INACTIVE_LINEUP_SLOTS`
   in `build_matchup_dashboard.py` intentionally excludes `BE`/`BENCH`/`BN`.
   Never tell Josh a bench player "won't score" — the slot doesn't matter, health
   does. Canonical fix 2026-06-15.
8. **Never bucket pitchers by ESPN `.position` tag alone.** ESPN can mislabel
   dual-eligible pitchers (canonical: Detmers 2026 — `position='RP'` but
   `'SP' in eligible_slots` and `gamesStarted=6`; he's rp3 #29 @ 12.19
   fp/start, not an RP). Always use `detect_pitcher_role(player_or_row)`
   from `scripts/xfp/lib/pitcher_role.py`, which checks `eligible_slots`
   first and falls back to MLB Stats API `gamesStarted` for dual-eligible
   cases. The rule: SP `eligible_slots` only → SP; RP only → RP **unless the
   name is in rp3 (ESPN slot grants lag a mid-season RP→SP conversion —
   canonical: Griffin Jax 2026 post-trade, RP-only slots for weeks while
   starting for TB, so cap math ignored his starts; fixed 2026-07-19), then
   decide on `gamesStarted` like the dual path**; both →
   `gamesStarted / gamesPlayed >= 0.4` → SP. Applied in
   `build_matchup_dashboard.py` and `run_roster_audit.py`; wire it anywhere
   you filter pitchers by role. Canonical fix 2026-06-15.
9. **Data is through YESTERDAY — two bridges erase the Statcast lag (2026-06-23).**
   `pybaseball.statcast()` finalizes ~1-2 days late, so two bridges fill the gap and
   both run early in `refresh_dashboards.py`: (a) **boxscore bridge** (`refresh_boxscores.py`,
   step 1.5) → real-time per-game BrownU FP into `boxscore_{hitters,pitchers}.parquet`
   (powers boom/bust, `/boom-bust-history`); (b) **statcast gf bridge**
   (`build_statcast_gf_bridge.py`, step 1.05) → Savant per-game-feed pitches mapped into
   `statcast_2026.parquet` tagged `source='gf_provisional'`, so the MODELS (rh3/rp3/rprs2,
   archetypes, splits, expected-stats, in-season arcs) are same-day current too. The
   canonical pull overwrites the provisional rows once a day finalizes. **After a daily
   refresh, assume everything reflects yesterday's games** — don't caveat "models lag a day."
10. **PL rankings publish on a known cadence — staleness is cadence-aware (2026-06-23).**
    Top 100 SP drops **Monday**; closers/relievers **~Tuesday**; Top 150 hitters **~Wednesday**;
    SP streamers are **rolling 2-3 day** windows. `lib/pl_cache._cache_is_stale` (+ `/triangulate
    --check-caches`) flags a cache stale only once its NEXT edition has actually published —
    so a Friday SP pull is "stale" by Monday, not by a flat 7-day age. Refresh in that rhythm.
11. **Trajectory/recency-trend is NON-PREDICTIVE for SP projection — validated 2026-06-24.**
    Don't re-attempt slope / EWMA / change-point / "recent K-BB% is falling" features for rp3
    OR the floor model: tested leakage-safe through both models' own harnesses — **Δr ≈ 0**
    (rp3 mean, vs the +0.005 gate) AND **ΔAUC ≈ 0** (per-start bust, bootstrap CI spans 0).
    RoS FP and bust risk both **mean-revert**; the cumulative LEVEL already carries the decline.
    For H2H downside, use the shipped **`floor_adj_xfp`** (rp3 mean docked/credited by sp_floor
    bust risk) + **`floor_adj_rank`** + **`floor_flag`** (FLOOR-RISK on RISKY tier / SAFE-FLOOR on
    SAFE tier) — decision-layer, Rule-13 context-only (registered `floor_adjusted` family).
    Tunable knobs in `lib/extra_lenses` (FLOOR_RISK_LAMBDA=0.5). **Canonical:** Soriano's
    *validated* bust risk is only 22% (his Ks protect the floor) → floor_adj ranks him #1 of his
    peer set; his 63%-bust recent run is variance, not predictive decline — so "drop Soriano"
    is selling low vs every validated lens. See `floor_adjusted_ranking_2026-06-24.md`.
    **Companion flag (same memo):** `stuff_command_lens` classifies the TYPE of decline —
    **STUFF-DECLINE** (SwStr/velo eroding in-season OR YoY, gated on a real prior-year sample so
    post-TJ arms don't false-flag → structural, sell) vs **COMMAND-WATCH** (stuff intact but
    walks up → reversible, hold-watch). Columns `stuff_cmd_tag`/`_swstr_d`/`_velo_d`/`_bb_d`/
    `_yoy_swstr_d`, registered `stuff_command` family, context-only. Canonical split: **Framber =
    STUFF-DECLINE** (SwStr 12.4→10.1 YoY, good drop) vs **Soriano = COMMAND-WATCH** (SwStr rising
    YoY, hold). Watch an arm's STUFF, not its walks, to know when a wobble becomes a sell.
12. **Hitter rolling-window predictive validity — validated 2026-06-26.** Don't re-derive which
    window to read or re-attempt a "hot-streak momentum" term for hitter FP. On our own 2026 panel
    (leakage-safe, non-overlapping anchors, `window_predictive_validity_2026-06-26.md`): (a) **longer
    trailing window predicts forward FP better, monotonically** — full season-to-date is the single
    best predictor (L7 r~0.15 → season ~0.32); (b) recent form adds **~0 beyond the FULL running
    season level** (it DOES add vs an older baseline, but the season average already contains it →
    **no separate momentum term**, Rule 13); (c) **of all process metrics, ONLY bat speed adds
    forward-FP signal beyond the FP level** (incremental partial r +0.076, CI excludes 0; K%/xwOBACON/
    HardHit%/BB% are redundant/confirmatory). **Practical:** anchor on the season level, use **L21d**
    as the recent-form window, trust **L7 only for bat speed**, and a hot L21d rate with flat bat
    speed = variance, not a new tier. (Caveat: established everyday regulars only.)
    **Confirmed at 60-cell scale + empirical cutoffs (2026-07-29, `inseason_delta_grid`
    registry entry):** every in-season DELTA of a rate metric (12 metrics × feasible lags +
    discipline/contact composites, BH-FDR corrected) adds ~0 to rh3 beyond season-to-date
    levels — **family CLOSED with NO re-open condition remaining**: the one named re-open
    (in-season bat-speed deltas) was built and tested the same day —
    `bat_speed_stabilization_and_delta_2026-07-29.md`, 0/6 cells survived BH-FDR, best cell's
    full 22-feature Rule-9 integration **+0.0035 vs the +0.005 bar**. Window studies MUST use
    non-overlapping windows on **BOTH** legs with ≥2L spacing (the delta_grid harness's EARLIER
    leg was cumulative season-to-date, not a window — corrected in that memo; overlapping
    anchors had inflated a holdout +0.090 → ~0).
    **Bat speed itself is now MEASURED, and it is the most reliable in-window hitter metric we
    have:** forward r ≥ 0.70 by **25-30 swings** (r=.905 @ 87, .950 @ 612; no bucket below
    .70 anywhere) on 126,434 batter-days / 1,929 player-seasons. So: read the bat-speed LEVEL
    off ~one week of playing time and trust it; read the YoY step; but the **in-season
    trajectory is descriptive only and must never move a rank, add, or drop** (Rule 13).
    Canonical trap: a board sorted by in-season bat-speed delta surfaces Bichette (+1.87 mph,
    a slow April washing out, 25th-pctile level) as the riser and Cam Smith (flat +0.01 on a
    98th-pctile level, +3.10 YoY) as boring — exactly backwards.
    CAVEAT: `lib/trend_signal.py`'s 80/200 swing gates guard a YoY DELTA (~√2× a level's
    noise), so the level curve above does NOT license relaxing them — leave them alone until a
    delta-appropriate gate is derived.
    **Canonical empirical sample minimums** (forward r≥0.50 — use these, never hand-picks;
    each in the metric's OWN denominator): chase **150 OOZ pitches** · zswing **150 IZ
    pitches** · whiff **150 swings** · swstr **150 pitches** · K% **50 PA** ·
    hard-hit/barrel **50 BIP** · BB% **175 PA** · xwOBA/PA **225 PA** · ISO **275 AB** ·
    HR-rate **275 PA**. Consequence: any ≤3-week
    "walking more" / "ISO jumped" read is noise BY CONSTRUCTION (BB%/power never reach r=0.70
    in-window); short-window reads are legit only for swing-decision metrics, K%, and
    hard-hit/barrel at those minimums. **Pitcher-side (same method, same date,
    `pitcher_cutoff_stabilization`): velo 150 pitches (r=.90 immediately — the king pitcher
    metric) · whiff 150 · swstr 175-200 · K% 100 TBF SP / 125 RP · gb 50 BIP · csw 425;
    pitcher chase, pitcher BB%, and hard-hit/barrel/HR-AGAINST NEVER stabilize in-window** —
    mid-season "command improved" / "getting more chases" / "HR-prone lately" reads are noise
    by construction (the HR/9 lens is legit as season-vs-career only; gotcha #11's "watch
    STUFF, not walks" now has measurement math behind it).
13. **Model forward-calibration is GOOD — don't "fix" the small under-projection (validated
    2026-06-26).** True forward retrospective (real git-recovered rh3/rp3 snapshots, projected at
    T vs actuals AFTER T; `model_forward_calibration_2026-06-26.md`): forward rank skill is modest
    & honest (**rh3 r≈0.35, rp3 r≈0.40** over 2-3 wks — the same-period r 0.77-0.82 is INFLATED by
    the projection containing the actuals). Forward bias is mildly positive (**rh3 +0.19 at the
    survivorship floor → +0.56 for heavy-usage regulars**; corr(err, fwd games)=+0.31). **Do NOT
    add an intercept / shade projections up / reduce shrinkage / widen σ from this** — the +bias is
    conditional on "keeps playing" (unconditionally the models are centered-to-OVER, since they
    hold priors for faders), shrinkage is validated to help, and the band check was a units bug
    (rh3 p25/p75 are **per-PA** not per-game) / confounded (rp3). The conservatism on regulars is a
    faint floor, **context-only (Rule 13) — never a number-mover or re-rank reason.** Snapshot
    logger (`build_player_projection_history.py`, refresh step 4.10) re-verified live; re-run the
    retro on logged (not git) snapshots in ~3-4 wks + do a proper single-start rp3 σ-coverage study.
    **(Both closed: σ-coverage 2026-07-10 NO-CHANGE α=2.41; logged-snapshot retro 2026-07-19
    CONFIRMED — registry entry same date. New watch: SP volume edge decay, next 4.13 run.)**

14. **In-season "he's a different player now" is a CLOSED question — do not re-derive
    (2026-08-26/27).** Five independent attempts failed: short-window K% delta (REJECTED),
    searched changepoint (REJECTED, actively harmful), a 150-cell parameter sweep (no cell
    replicates), an event taxonomy (no event beats a matched random split), and a properly
    tested structural break (`sp_structural_break.py`: permutation null + BH-FDR → only
    **3 of 1339** pitcher-seasons have a real in-season K% break, 0.22%). **Nothing regime-
    derived may move rh3/rp3/rprs2.** What IS true and reusable:
    - **~89% of apparent in-season change is sampling noise.** Over-dispersion vs pure
      binomial is only **1.114x** (SP) / 1.104x (hitters).
    - **Two bars, and confusing them is the classic error.** Split point GIVEN by an event
      (IL, trade, role) → judge at **z > 1.83** (one test). Split point you SEARCHED for →
      **SP 2.58 / hitters 2.79**, because the max of ~100 draws is not one draw. 39% of
      pitcher-seasons and 50% of hitter-seasons clear the *given* bar at their best split
      BY CONSTRUCTION; the hitter max-split MEDIAN is exactly 1.83.
    - **Events do not CAUSE breaks** — excess |ΔK-BB%| over matched same-position controls
      is ~0 for every type (IL_SHORT +0.02, IL_MED +0.14, TRADE +0.09, IL_LONG −0.07, all
      n.s.). An event only supplies a split point that is *given*, so it pays no search
      penalty. IL returns LOOK like breaks purely because of where in the season they fall.
    - Use `scripts/xfp/lib/split_floor.py` (`/split-check`) as a SCREEN. Clearing the floor
      means the gap is real; it does NOT mean it predicts (the best rule lost on holdout,
      t = −2.16).
    Memo: `data/research/validation_runs/sp_regime_break_finding_2026-08-26.md`.

15. **Read the OUTCOME for hitters, the PROCESS for pitchers (validated 2026-08-27).**
    1st-half feature vs 2nd-half scoring, matched halves:
    - **Hitters — the FP LEVEL (+0.480) beats every rate metric** (TB/PA +0.288, K% −0.234,
      HR/PA +0.230, BB% +0.167, SB/PA +0.067). Five rates add **+0.010** OOS over the level.
    - **SPs — K% (+0.540) beats the pitcher's own FP level (+0.463).** Everything else adds
      +0.001 over K%. But K% is NOT uniquely informative: dropping it costs only +0.004
      because K is a term in the SP FP formula, so the two are algebraically linked.
    - **Bat speed is the real hitter exception** (confirms gotcha #12 from a fresh panel):
      partial r vs the FP level **+0.123, 95% CI [+0.042, +0.203]**, n=572 hitter-seasons
      2024-26; the bat-speed pair (mean + fast-swing%) adds **+0.058 r** over all other
      features. Read the LEVEL, never the trajectory.
    - **Pitchers and hitters INVERT on walks.** SP BB% is the weakest signal measured
      (r_fwd −0.144, wrong sign; reliability 0.483) while hitter BB% reliability is 0.625.
      The walk belongs to the batter — independent proof of "watch STUFF, not walks" and of
      `stabilization.NEVER_STABILIZES` listing pitcher `bb_pct`.
    Memo: `data/research/validation_runs/metric_reliability_2026-08-27.md`.


16. **A TBD probable is not a no-start — read the rotation ORDER
    (2026-08-28).**

**Cost a wrong recommendation on 2026-08-28.** Josh's ESPN app showed a PP
(probable-pitcher) badge on Tyler Glasnow for 8/30. The MLB Stats API
`schedule` endpoint hydrated with `probablePitcher` returned NO Glasnow for
8/29-8/31, and I read that absence as evidence he wasn't pitching. He was.
LAD's 8/30 slot was simply listed **TBD** — unannounced, not empty. ESPN's PP
badge projects the next turn into unannounced slots; the MLB feed only
publishes what the club has announced (typically 1-2 days out). Neither is
lying, and ABSENCE FROM THE FEED IS NOT ABSENCE OF A START.

**The reliable read is the rotation ORDER**, which is directly observable by
listing the team's game-by-game announced starters:

    8/25 Glasnow -> 8/26 Sasaki -> 8/27 Yamamoto -> 8/28 Skubal
      -> 8/29 Snell -> 8/30 TBD     (five-man cycle; T+5 returns to Glasnow)

A named cycle that returns to your arm at T+N is far stronger evidence than a
TBD slot is evidence against.

**Second trap in the same miss:** I also leaned on the measured season-median
turn (Glasnow 6.0 team games, from `lib/volume_semantics.sp_turn_map`) to
argue his next start fell outside the period. That median was STALE — it came
from an earlier six-man stretch, and LAD had since tightened to five. The turn
measure is for pricing in-role volume (gotcha: it is the right tool for
"how many starts per week when active"), NOT for predicting a specific date.
For a specific date, read the order.

**Consequence, and why it matters beyond one start.** The leverage engine
assigns no event to an unannounced start, so an arm mid-cycle looks like he
has ZERO starts left. That silently corrupts two things at once:
  * the SP-cap count — Josh looked like 9/10 with a spare slot when he was
    actually 10/10, exactly full; and
  * the optimizer's drop side — `ADD x / DROP Tyler Glasnow` scored +8.8pp
    purely because the engine credited Glasnow with nothing to lose.
The recommendation that fell out (ADD José Soriano, +5.28pp) evaporated to
**+0.47pp** once Glasnow's start was included, because the chronological cap
just zeroes an 8/30 start to pay for the 8/29 one. Glasnow's start alone was
worth **+9.5pp** (P(win) 69.2% -> 78.7%).

**Rule:** before claiming a rostered SP has no start left in a period —
especially before letting that claim justify a drop or a cap-slot add — list
the team's announced starters in order and check whether the cycle returns to
him inside the window. Treat a TBD slot in his turn as HIS until announced
otherwise.
