# Vegas / betting-market signals — feasibility + integration study

Date: 2026-06-13
Author: research agent
Script: `scripts/_oneoff/vegas_markets_study.py`
Status: **FEASIBILITY ASSESSMENT — no backtest performed (no free historical data).**

## TL;DR

- **Collectability verdict:** CURRENT / upcoming odds are **collectable for free**
  (the-odds-api.com free tier, 500 credits/mo, no anonymous access — needs a free
  key). HISTORICAL closing lines 2021-2025 are **GATED** (paid plans only, and a
  10x credit multiplier on top). MLB Stats API has **zero** odds fields (confirmed).
- **Therefore:** a pre-registered historical backtest is **not feasible for free**.
  The honest path is **forward-only**: wire the live market signal into
  `/pregame-check` and `/stream-the-stack` as an EXOGENOUS context lens and let it
  accumulate its own forward track record (same posture we already take for boom_stack /
  sustainability per CLAUDE.md #13 — context/conviction layer, NOT a headline-moving term).
- **Value note:** the implied opponent **team total** is the single best market
  signal for us — it is a forward-looking, lineup/park/weather-adjusted version of
  the exact quantity our model already approximates with a season xwOBA `bat_index`.
  Likely incremental over our static proxy *on the day of*, but unvalidated. Treat as
  promising-but-unproven; do NOT let it move the rh3/rp3/rprs2 headline.

## 1. What is actually collectable (free vs gated)

| Source | Odds? | Free? | History? | Verdict |
|---|---|---|---|---|
| **MLB Stats API** (`statsapi.mlb.com`) | NO | yes | n/a | Confirmed no odds/line/bet fields on `/schedule` (15-game probe 2026-06-13). Schedule + probables only. Use as the **join key** (gamePk, teams, probablePitcher), not the signal. |
| **the-odds-api.com v4** | YES | free tier 500 credits/mo | **paid only** | Live + upcoming games work on free tier. `/sports` and `/events` cost **0**. Game `/odds` (h2h+totals) costs **2**. Per-event props cost **(markets x regions)**. Historical endpoints are **paid-plan-only AND 10x cost**. |
| Kaggle / sportsbookreview archives (free historical) | YES | varies | partial | Reachable in principle but: stale, schema-inconsistent, no guarantee of **closing** lines, and no clean join to our gamePk/pitcher_id. Not worth a backtest build vs the forward path. Documented as a fallback, not pursued. |

Auth probe (2026-06-13):
- `GET /v4/sports/` no key -> `{"message":"API key is missing"}`
- dummy key -> HTTP 401 `INVALID_KEY`
- So: **no anonymous free access; a (free) key is mandatory.** No key is committed in
  this repo (`.env` holds only ESPN_* creds; confirmed).

## 2. Exact API spec (the-odds-api v4, baseball_mlb)

Market keys (verified against the-odds-api docs):
- Moneyline -> `h2h`  (American odds -> implied win prob, no de-vig)
- Game over/under -> `totals`
- **Per-team implied runs -> `team_totals`** (the signal we most want)
- **SP strikeout prop -> `pitcher_strikeouts`** (Over/Under line + price)

Endpoint routing:
- `h2h`, `totals` -> `GET /sports/baseball_mlb/odds?regions=us&markets=h2h,totals`
- `team_totals`, `pitcher_strikeouts` are **"additional markets"** -> must use the
  per-event endpoint `GET /sports/baseball_mlb/events/{eventId}/odds?markets=team_totals,pitcher_strikeouts`.

Credit math (free tier = 500/mo):
- `/sports`, `/events` = **0** credits.
- game `/odds` (h2h+totals, 1 region) = **2** credits.
- per-event props = (unique markets returned) x regions = **2/event** for our two markets.
- **Full 15-game slate w/ props** = 2 + 15*2 = **32/day -> ~960/mo (over budget).**
- **Targeted** (props only for my ~9 starts + opp ~9 SPs) = ~**20/day -> ~600/mo.**
- **Cheapest** (game-level h2h+totals only, no per-event props) = **2/day -> ~60/mo**
  (well inside 500). Game total + ML alone already give a usable run-environment +
  win-prob read; per-team split needs the per-event call.

Recommended free-tier budget: pull **game-level h2h+totals daily** (60/mo), and add
**per-event team_totals/pitcher_strikeouts only for games involving my roster**
(~300-400/mo). Stays under 500 with headroom.

## 3. Signal -> model mapping

The market-implied **opponent team total** maps to an opponent-offense multiplier
centered at 1.0, on the **same scale as our existing `bat_index`** in
`data/research/xfp_cache/team_strength_2026.csv` (observed range min 0.95 / med 1.00 /
max 1.10). That means it drops straight into the slot `stream_the_stack.py` already
reads (`opp_bat_index_recent`).

```
opp_offense_mult = 1.0 + 0.10 * (implied_opp_team_total - 4.40)
   3.4 R implied -> 0.90  (soft opponent -> START the SP, fade my hitters in that game)
   4.4 R implied -> 1.00  (neutral)
   5.5 R implied -> 1.11  (high-offense day -> bench-risk SP, boost my hitters)
```
(4.40 = anchor league-avg implied team total; sensitivity 0.10 chosen to match the
empirical bat_index spread. Refresh the anchor from the live slate median if wired in.)

Per-signal use:
- **team_totals (opp)** — primary. Forward opp-offense for SP start/sit + hitter boost.
  This is the headline of the four.
- **totals (game O/U)** — run environment / park+weather proxy; secondary to team total.
- **h2h -> win prob** — context only (blowout risk -> bullpen-game / early-hook risk for
  a streamer); NOT a points-scoring driver in our format.
- **pitcher_strikeouts** — market's K projection for an SP. Direct cross-check on the K
  term of our SP FP formula (`K + IP*3.3 - H - 2*ER - BB - HBP`). A 7.5 SO line on a
  streamer the model is cold on = market disagreement flag.

Why it should add value *on the day of*: our `bat_index` is a **season-to-date xwOBA
average** — it does not know today's lineup (rest days, platoon, call-ups), the park, or
weather. The market price bakes all of that in a few hours before lock. It is the
single cleanest exogenous upgrade to the opp-offense input we have.

## 4. Where it plugs in (forward-only)

- **`/pregame-check`** (morning-of START vs CAP-BENCH): for each of my SPs starting
  today, fetch the **opponent's** `team_total`. Feed `opp_offense_mult` into the existing
  v2 conservative rule as a *refinement of `opp_bat`* (today the rule uses our static
  bat_index). High implied opp total (>1.10) + low blend = stronger CAP-BENCH case;
  soft opp total (<0.95) reinforces the existing "always START on SOFT opp" rule. Also
  use opp SP `pitcher_strikeouts` line to flag my hitters facing a high-K start.
- **`/stream-the-stack`** (FA SP streamer board): replace/augment `opp_bat_index_recent`
  for the streamer's opponent with the live `team_total`-derived mult, and surface the
  streamer's own `pitcher_strikeouts` line next to rp3 as a market cross-check. boom_stack
  `opp_soft` component could read the live number instead of the season proxy.

Both are **forward, daily, no-history** use cases — they need a live feed, not a
backtest, to be useful. That is the right shape for this signal.

## 5. Honest expected-value note

- **Upside:** team total is a genuinely exogenous, same-day signal that strictly
  dominates a season-average proxy *in information content* for opp offense. For
  start/sit and streaming (binary, day-of decisions) that is exactly the lens that
  helps. ML/SO props are nice cross-checks.
- **Caveats / why this is NOT a headline term:**
  1. **Unvalidated for our scoring.** No free history -> no backtest. Per CLAUDE.md #13,
     we do not treat a new lens as additive point-forecast lift without validation. It
     enters as a **context / conviction** layer only.
  2. **Vig + efficiency.** Closing MLB totals are sharp; the *edge* over our own
     bat_index may be small and mostly matters on the tails (extreme parks/weather/
     lineup news), not the median game.
  3. **Operational fragility.** Free tier is rate-limited; lines move until lock; a
     daily cron must pull near lineup-lock to be current. Fail-soft is mandatory (the
     scaffold already falls back to spec mode with no key/network).
  4. **Format fit.** Win prob (h2h) barely matters in points scoring; only team total
     and SO prop carry real signal for us.
- **Recommendation:** ship as an **opt-in forward lens** behind a free `ODDS_API_KEY`,
  scoped to my-roster games (budget ~300-400/mo), feeding `opp_offense_mult` into
  `/pregame-check` + `/stream-the-stack` as a refinement of the existing opp-offense
  input and a market cross-check on SP K. Let it build a forward record before anyone
  considers it for a ranker. **Do not** spend money on historical lines for a backtest —
  the marginal-vs-bat_index edge is unlikely to justify the paid-plan + 10x cost.

## 6. Reproduce

```
# spec/dry mode (no key — prints integration spec + mapping math, fetches nothing):
python -X utf8 scripts/_oneoff/vegas_markets_study.py

# live mode (needs a free key; pulls current/upcoming odds, maps team_total->mult):
ODDS_API_KEY=xxxx python -X utf8 scripts/_oneoff/vegas_markets_study.py --max-events 3
```
No odds are fabricated anywhere; without a key the script prints labelled HYPOTHETICAL
mapping examples only.
