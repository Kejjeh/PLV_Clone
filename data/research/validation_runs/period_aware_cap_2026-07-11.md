# Period-aware SP-start cap + matchup window (2026-07-11)

**Problem.** The current matchup period (15) is the All-Star **two-week** block:
ESPN caps SP starts at **16** (not 10) over **Jul 6 → Jul 19** (skipping the ASG
dead days Jul 13–15). The tooling silently assumed a single Mon–Sun week and a
hardcoded 10-start cap, so `/matchup-leverage` computed banked starts, days
remaining, the streamer sim, and P(win) over the wrong window at the wrong cap.

## STEP 1 — what ESPN actually exposes (probed live)

| Signal | Auto-detectable? | Source |
|---|---|---|
| **Banked SP-start count per team** (the `x` in `x/16`) | **YES** | `mMatchupScore` → schedule → side → `cumulativeScore.statBySlot["22"].value` (statId 33). Confirmed **Ligers = 3**, **Solomon = 6** — exactly the ESPN screen. `cumulativeScoreLive` includes today's in-progress starts (Ligers live = 6). |
| **Number of scoring weeks in a period** | **YES** | `settings.matchup_periods` → `len(matchupPeriods[str(period)])`. Playoffs: `22→[22,23]`=2, `23→[24,25]`=2, `21→[21]`=1. |
| **Per-scoring-period start RATE** | YES | `rosterSettings.lineupSlotStatLimits["22"].limitValue = 10/7 ≈ 1.4286` starts/day (statId 33). |
| **The period CAP as one number (16)** | **NO** | Not in settings or matchup blobs. It is `round(rate × game-days)` and the game-day count depends on the ASG schedule gap. Worse, `matchupPeriods["15"] = [15]` (a **single** week-index) despite the 2-week span, so the week count is *also* untrustworthy for the ASG block. |
| **Period date window** | Partially | `scoringPeriodId` ↔ date is a clean linear map (sp108 = 2026-07-11 today; sp103 = Jul 6 … sp116 = Jul 19), and elapsed scoring periods are readable — but the *future* ASG-skipped days are not cleanly machine-readable mid-period. |

## Design chosen — general formula + one explicit exception

**General rule (AUTO, no maintenance): `cap = 10 × weeks`**, where
`weeks = len(matchupPeriods[period])` from ESPN settings.
- every regular week and playoff round 1 (period 21) → **10**
- 2-week playoff rounds (periods 22, 23) → **20**

**The one exception (MANUAL override, takes precedence): the ASG block.**
Period 15 → cap **16** over **Jul 6–19**, because the All-Star break removes
game-days *and* ESPN lists the period as a single week — so `10×weeks` (which
would say 10, or 20) is wrong and can't be safely auto-derived. Seeded in
`cap_math.PERIOD_CAP_OVERRIDES` / `PERIOD_WINDOW_OVERRIDES`.

**Banked count** is read live from ESPN's authoritative statId-33 counter
(ground truth, matches `3/16`, `6/16`), with the boxscore-store count kept as a
fallback + cross-check. A **loud warning** fires if a period *looks* single-week
(`weeks==1`, no override) yet has already scored across >1 week — the exact
"ASG period with no override" trap — so 10 is never silently used for a 16-cap
period again.

Asymmetry, on purpose: **playoffs = automatic (10×weeks); ASG = manual override.**

## Files changed

| File | Change (one-liner) |
|---|---|
| `src/plv_clone/cap_math.py` | Added `PERIOD_CAP_OVERRIDES` / `PERIOD_WINDOW_OVERRIDES` (seed: 15→16, Jul 6–19), `sp_cap_for_period(period, *, weeks=1, default=SP_CAP)` (override wins, else `10×weeks`), `weeks_in_period(matchup_periods, period)`, `period_window()`, `is_period_covered()`. `SP_CAP=10` and all existing pure fns unchanged. |
| `scripts/xfp/run_matchup_leverage.py` | `build_state` resolves cap = `sp_cap_for_period(period, weeks=len(matchupPeriods[period]))` and the window from the override (ASG) or `Mon..Mon+7×weeks-1` (multi-week playoff) else Mon–Sun. Banked from new `espn_period_meta()` (statId-33, authoritative) with box fallback + loud multi-week warning. Cap/window/weeks surfaced in console + `matchup_leverage.json`. `MAX_SP_STARTS_PER_WEEK` import dropped (was the flat-10 footgun). `--calibrate` also period-aware. |
| `scripts/xfp/run_season_sim.py` | Current period scales by `cur_period_weeks` (ASG span, or `len(matchupPeriods[cur])`): the current-period draw is `mu·weeks·frac_left`, `sd·√(weeks·frac_left)`. `weeks=1` → byte-identical single-week draw. Surfaced in console/JSON + caveat. Playoff rounds already multi-week (unchanged). |
| `tests/test_cap_math.py` | +7 tests: default→10 regression guard, ASG 15→16 + 2-week window, override-arg, override-beats-formula, `10×weeks` playoff→20, `weeks_in_period`, end-to-end playoff caps. |
| `tests/test_matchup_leverage_period.py` (new) | Stubbed-league tests locking the ESPN banked cross-check (Ligers 3 / Solomon 6), statId-33 guard, fetch-failure → box fallback, multi-week span detection. |

**Not changed (out of editable scope / no cap math):** `build_matchup_dashboard.py`
is untouched (still SP_CAP=10 for its single-week planning view → no SP-projection
regression). `build_sp_pl_board.py` has no cap math (PL sentiment board only).
Follow-up worth flagging: `run_roster_audit.py` hardcodes `10 - projected_starts`
and matchup.html shows a flat single-week cap — both would benefit from the same
period-awareness but were outside this task's editable set.

## Validation

- **Full suite:** 638 passed (incl. 11 new period-aware tests). No regressions.
- **Banked cross-check (the anchor):** engine `banked_mine = 3`, `banked_opp = 6`
  — **matches ESPN exactly**. (Boxscore cross-check said 6 for Josh; the 3-start
  gap is starts made from the bench that don't count toward the cap — ESPN's
  count is authoritative and now used.)
- **`--calibrate auto`:** periods 13 & 14 (regular 1-week) both land INSIDE the
  simulated 80% band — unchanged behavior confirmed.

### Corrected `/matchup-leverage` (period 15, cap 16, Jul 6–19)

| | OLD (cap 10, single week — known wrong) | **NEW (cap 16, full window)** |
|---|---|---|
| P(win) | 69.6% | **20.6%** |
| Regime | — | **TRAILING** (down 22.4 WTD; variance = asset) |
| cap_remaining | — | **mine 13, opp 10** (banked 3 / 6) |
| Top ΔP(win) move | — | **ADD Ian Seymour (FA) +6.61pp**, Dustin May +6.46pp, Tanner Bibee +6.33pp |

The old 69.6% collapsed to a truthful **20.6%** once the window included the
opponent's *second-week* (Jul 16–19) games and SP starts: opp has **10** remaining
cap-eligible starts to Josh's **7**, and projects to out-score him the rest of the
way (proj final 567 vs 616, median margin −50). Actionable read: Josh is a
variance-hungry underdog this period and should **stream an extra SP start**, not
sit one.

### Season-sim (Josh), same seed — small, sane shift

| | P(playoffs) | P(title) | P(final) |
|---|---|---|---|
| OLD (current period = 1 week) | 91.7% | 10.9% | 22.7% |
| **NEW (current period = 2-week ASG span)** | **92.5%** | **10.8%** | **23.1%** |

Title odds barely move (the current period is 1 of ~6 remaining and Josh's spot
is ~93% secure) — confirming the change is correct **and** conservative.

## How Josh maintains the override

Regular + playoff periods need **nothing** — `10×weeks` is automatic. Only add an
override for another ASG-style block where the calendar span and the game-day
count disagree. In `src/plv_clone/cap_math.py` add one entry to **each** dict:

```python
PERIOD_CAP_OVERRIDES[<period>]    = <CAP from ESPN "Game Limits (Cur/Max): P: x/CAP">
PERIOD_WINDOW_OVERRIDES[<period>] = (date(start), date(end))   # inclusive, ASG days stay inside
```

Add a cap without a window (or vice-versa) and the leverage engine warns loudly
rather than silently falling back to 10.
