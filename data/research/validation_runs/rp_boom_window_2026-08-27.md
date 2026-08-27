# RP boom-window shrinkage — the one window read that actually holds up

**Date:** 2026-08-27
**Scripts:** `scripts/xfp/build_rp_event_panel.py` (fetch),
`scripts/xfp/validate_boom_window.py` (`PLV_BOOM_SIDE=RP`),
`scripts/xfp/fit_boom_shrinkage.py` (new, all three sides)
**Panel:** `data/research/xfp_cache/rp_event_panel_2017_2026.csv` — 54,561
relief appearances (`gamesStarted == 0`), 1,282 RP-seasons, 394 rprs2 arms,
2017-2026. RP FP = `K + IP*3.3 − H − 2*ER − BB − HBP + 5*SV + 3*HLD`.
**Rule 13:** diagnostic / display only. Nothing here moves rprs2.
**Verdict:** SHIP the constants. The expected confirmation came back with an
unexpected sign.

## Why this was run

`boom_window_shrinkage_2026-08-27.md` measured how much of a short-window boom
rate is sampling noise for SPs (L8: 65% noise) and hitters (L21: 73%). The RP
line on `/boom-bust-history` was the last uncovered side. Going in I told Josh
this was likely "confirmation, not discovery — the same shrinkage story with
different constants." That prediction was half wrong, and the wrong half is
the finding.

## Result

Base RP boom rate (FP >= 6) = **0.266**. Slope = OLS of the next window's boom
rate on the observed window's, non-overlapping, within a player-season; 95% CI
from a 400-draw bootstrap **clustered on player-season** (don't-do 17c).

| window | pairs | slope | 95% CI | noise |
|---|---|---|---|---|
| L5 | 8,799 | 0.336 | [+0.308, +0.366] | 66% |
| L10 | 3,465 | 0.491 | [+0.451, +0.525] | 51% |
| **L15** (skill default) | 1,783 | **0.568** | [+0.520, +0.609] | **43%** |
| L20 | 991 | 0.586 | [+0.529, +0.637] | 41% |
| L30 | 319 | 0.601 | [+0.510, +0.690] | 40% |

**Relievers are the least noisy of the three sides, by a wide margin.** An L15
relief read retains **57%** of its signal against 35% for an SP's L8 and 25%
for a hitter's L21 — and it gets there on fewer observations than the hitter
window uses.

Mechanism: saves and holds are a *role* property, not a performance property,
and they enter RP FP at +5 and +3. A closer's boom rate is substantially a
statement about his job. That is durable in a way that a hitter's per-game
outcome distribution is not.

## The probability check — RP is the only window that beats its base rate

Brier vs a constant base-rate forecast (34,058 out-of-sample forecasts):

| | AUC | Brier vs base |
|---|---|---|
| **RP boom, L15** | **0.644** | **−0.0062** (better) |
| RP boom, season-to-date | 0.650 | −0.0097 |
| RP boom, parametric N(mean, 4.34) | 0.651 | −0.0114 |
| RP bust, L15 | 0.524 | +0.0070 (worse) |

Every SP and hitter window LOST to the base rate as a probability. The RP boom
window wins. It is still beaten by both longer/smoother alternatives, so the
ordering from the SP study survives — *season-to-date and a smooth parametric
summary beat the short window on every side, every time* — but the RP short
window is at least not actively harmful.

RP **bust** behaves like hitter bust: the window loses, and the parametric form
loses too. Prefer season-to-date on the bust line.

## Tail caveat

The shrink is linear, and boom rate is bounded at 0, so the fit under-shoots
the bottom. Empirical next-15 boom rate for an 0/15 reliever is **16.7%**; the
linear form says 11.5%. Read the linear value as a lower bound at that end. The
top end is fine (12/15 → predicted 56.9% vs empirical 57.0%).

## Side benefit: the SP and hitter constants were independently reproduced

`fit_boom_shrinkage.py` is a fresh implementation with a different pairing
scheme from `validate_boom_window.py`. Run on the SP and hitter panels it
reproduces the shipped tables inside the bootstrap CI at every window:

| | shipped | reproduced | in CI? |
|---|---|---|---|
| SP L8 | 0.353 | 0.368 [0.317, 0.413] | yes |
| SP L12 | 0.431 | 0.426 [0.362, 0.491] | yes |
| H L21 | 0.267 | 0.253 [0.231, 0.274] | yes |
| H L40 | 0.414 | 0.392 [0.359, 0.419] | yes |

**One real gap found.** `BOOM_SHRINK_SLOPE[20] = 0.575` (SP) cannot be
estimated from non-overlapping pairs — it needs 40 starts in a season and no
SP has one. The shipped value came from an overlapping estimator. It is only
reachable via `forward_rate(window>=20, side="SP")`, i.e. a cross-season read,
and it is left in place, but it is **not** measured to the standard of the
other cells. Flagged, not changed.

## Data-quality fix found along the way — and a guard that earned its keep

The holds multiplier moved **2 -> 3 in the 2026-08-12 league-setting change**.
`data/models/league_scoring.json` (`hd: 3.0`) and
`plv_clone.fantasy.scoring` tracked it. Three pieces of *documentation* did
not: the `pitcher_fp` docstring, the `/boom-bust-history` skill description,
and its embedded `fp_pitcher` snippet all still said 2. All three corrected.
These were not wrong when written — they were correct under the old setting
and nobody updated them. That is the more dangerous failure mode, because a
future agent copying the snippet gets a formula that was once true.

My first draft of `build_rp_event_panel.py` hardcoded the weights, and
`tests/test_no_hardcoded_scoring_weights.py` failed the build on it,
citing the 2026-08-12 incident by name. The script now routes through
`pitcher_fp`. **The guard did exactly the job it was written for, on the
exact failure it was written for, and it caught me** — worth recording
because the temptation in a research script is always to inline the formula.
Routed and hardcoded agree to the cent on the shipped panel, so no refetch was
needed.

**One framing note this raises.** The panel scores 2017-2025 relief
appearances under **today's** weights (hld x3). That is deliberate and correct
for this question -- we want the boom rate under the scoring we actually play
-- but it means the panel is not a historical record of FP as it was scored at
the time, and it will need rebuilding if the league changes a weight again.
