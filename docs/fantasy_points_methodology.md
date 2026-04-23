# Fantasy Points Methodology

## Overview

The fantasy-point layer translates PLV and Process+ model outputs into
expected per-PA and per-IP fantasy point estimates for your league scoring.

**This is a projection layer, not a game-by-game forecast.** It estimates
the rate at which a player is expected to accumulate fantasy points based
on their process quality, not their playing time or role.

Core principle: the PLV and Process+ model math is unchanged. Only the
translation layer is new.

---

## League Scoring Used

Stored in `data/models/league_scoring.json`. Edit that file to change weights.

| Category | Event | Points |
|----------|-------|--------|
| Batting  | R     | +1     |
| Batting  | TB    | +1     |
| Batting  | RBI   | +1     |
| Batting  | BB    | +1     |
| Batting  | K     | −1     |
| Batting  | HBP   | +1     |
| Batting  | SB    | +1     |
| Pitching | IP    | +3.3   |
| Pitching | H     | −1     |
| Pitching | ER    | −2     |
| Pitching | BB    | −1     |
| Pitching | HB    | −1     |
| Pitching | K     | +1     |
| Pitching | SV    | +5     |
| Pitching | HD    | +3     |

---

## Hitter Model

### Two output views

**`core_fp_per_pa`** — the preferred ranking. Includes only skill-driven components:
TB, BB, K, HBP, SB. These are directly predicted by the model or estimated with
reliable proxies. Not contaminated by lineup context.

**`full_fp_per_pa`** — companion view. Adds context-dependent R and RBI via empirical
multipliers. Use for directional context; not for ranking when lineup position is unknown.

`fp_per_pa` is a backward-compatible alias for `full_fp_per_pa`.

### Rate estimation

Three rates are estimated from calibrated linear regression models
fit on 2023–2024 actual player outcomes (n = 828 hitter-seasons):

| Rate | Features | R² | Notes |
|------|----------|-----|-------|
| BB/PA | chase_pct, decision_plus | 0.49 | Chase rate is dominant signal |
| K/PA  | whiff_pct, chase_pct     | 0.71 | Best-fit hitter rate; whiff is key |
| TB/PA | in_play_pct, xwoba_actual, power_plus | 0.66 | In-play rate × contact quality |

Three additional rates are derived from empirical formulas:

**H/PA** (batting average proxy):
```
H/PA ≈ xwoba_actual × 0.85 − 0.015
```
At league avg xwOBA on contact (0.370) → H/PA ≈ 0.250.
At elite (0.450) → 0.368. At weak (0.250) → 0.198.

**R/PA** (empirical OBP multiplier):
```
R/PA ≈ 0.37 × (H/PA + BB/PA + HBP/PA)
```
Roughly: 37% of times a player reaches base, they score. Calibrated to
MLB 2023–2024 average ~0.105 R/PA. Lineup-context dependent — not in core_fp.

**RBI/PA** (empirical TB multiplier):
```
RBI/PA ≈ 0.24 × TB/PA + 0.06 × OBP_proxy
```
Calibrated to MLB 2023–2024 average ~0.095 RBI/PA. Lineup-context dependent — not in core_fp.

**HBP/PA**: Fixed at league average 0.9%. Not enough model signal to predict.

### SB proxy (shrinkage estimate)

SB is estimated via a Bayesian shrinkage toward the league average (0.020/PA):

```
est_sb_rate = (observed_sb_per_pa × pa + 0.020 × 150) / (pa + 150)
```

- At PA = 0: estimate = league average (0.020)
- At PA = 150: 50/50 blend of observed rate and league average
- At PA = 600: ~80% observed, ~20% league average prior

**What this does:** Speed players with real stolen base production (e.g. 25+ SBs)
will have their estimate pulled meaningfully above 0.020. Average players with few
SBs land near 0.010–0.020. Players with no SB production land near 0.006–0.010 at
full season. It is not a sprint-speed model — it responds directly to actual SB
events in our pitch data.

**Limitations:** Early-season estimates (< 100 PA) are unreliable — sample is too small
to distinguish fast starters from true speed players. At early season, the shrinkage
pulls everyone near 0.020. For known elite speed players, add a manual premium
until they have sufficient PA to demonstrate their rate.

### Playing-time assumption

`fp_per_game = full_fp_per_pa × pa_per_game` (default 3.5 PA/game for starters).

This is adjustable in the CLI (`--pa-per-game`) and dashboard slider.
Adjust down for platoon players, part-time players, or injury risk.

### What is most trustworthy

1. **K/PA estimate** (R²=0.71): The strongest predictor. Whiff rate is the
   primary driver, which is a genuine skill signal. K rate stability is high
   year-over-year.

2. **BB/PA estimate** (R²=0.49): Chase rate is very predictive of walks.
   Decision+ adds marginal improvement. BB rate is stable skill.

3. **TB/PA estimate** (R²=0.66): Improved by including in-play rate.
   Power+ captures above-expected damage. xwOBA on contact is stable.

4. **SB estimate**: Directionally useful for clear speed players at 200+ PA.
   Noisy early season. Cannot distinguish a cold speed player from a non-speed player.

5. **R and RBI**: Empirical multipliers only. Lineup-context
   dependent and have meaningful noise. In `full_fp_per_pa` only.

---

## Pitcher Model

### Rate estimation

Four rates are estimated from calibrated linear regression models
fit on 2023–2024 actual pitcher outcomes (n = 1,379 pitcher-seasons):

| Rate    | Features                        | R²   | Notes |
|---------|---------------------------------|------|-------|
| K/IP    | plv, whiff_pct                  | 0.37 | PLV + whiff carry real signal |
| BB/IP   | plv, cs_pct                     | 0.27 | Called-strike rate limits walks |
| H/IP    | plv, contact_pct, xwoba_model   | 0.20 | BABIP luck limits R²; directional |
| ER/IP   | plv, xwoba_model                | 0.16 | FIP-based target; ERA is noisy |

HBP/IP is fixed at league average (~0.033/IP). Not enough PLV signal.

IP estimation for calibration: `pitches / 15` (MLB average ~15 pitches/IP).
FIP formula for ER calibration target:
```
ER/IP ≈ (13×HR/IP + 3×(BB/IP + HBP/IP) − 2×K/IP + 3.17) / 9
```

Rolling PLV blend: projection uses 70% season PLV + 30% 30-day rolling PLV
when rolling data is available. This tilts toward recent form without
overweighting small-sample windows.

### Role classification

Pitchers are classified as SP or RP based on average pitches per game
appearance: > 50 pitches/game → SP, ≤ 50 → RP.

```
fp_per_start = fp_per_ip × ip_per_start (default 5.5 IP/start)
fp_per_app   = fp_per_ip × ip_per_app   (default 1.0 IP/app)
```

### SV/HD

**SV and HD are not included in fp_per_ip.** They are role-sensitive and
cannot be reliably predicted from PLV alone.

| Role     | Typical rate    | FP/app from role |
|----------|----------------|-------------------|
| Closer   | ~0.15 SV/app   | +0.75/app         |
| Setup    | ~0.25 HD/app   | +0.75/app         |
| Other RP | ~0.05 HD/app   | +0.15/app         |

Add these manually based on each pitcher's actual role in your league.
See `docs/reliever_role_model_future_work.md` for planned improvements.

### What is most trustworthy

1. **K/IP estimate** (R²=0.37): Best pitcher rate. Whiff rate is an
   excellent predictor of strikeout rate (both are process metrics, not luck).

2. **BB/IP estimate** (R²=0.27): Called-strike rate has real signal for
   walk rate. Pitchers who force poor decisions walk fewer batters.

3. **H/IP estimate** (R²=0.20): Moderate. BABIP is partially luck-driven
   (pitchers have limited control over ball-in-play outcomes). This rate
   has the most noise.

4. **ER/IP estimate** (R²=0.16): Weakest. ERA year-to-year correlation is
   inherently moderate (~0.35). Our estimates are directionally correct but
   have wide error bars. Use as a relative ranking signal, not an absolute
   ERA forecast.

---

## Rolling Fantasy Views

The dashboard provides a "Rolling Fantasy" subtab under Rolling Trends. These
views compute fantasy rates directly from events within 30-day rolling windows
and are updated when you re-run `plv build-exports <year>`.

**Hitter rolling:**
- `rolling_tb_pa`, `rolling_bb_pa`, `rolling_k_pa`, `rolling_sb_pa` — raw event rates
- `rolling_core_fp_pa` — core FP computed from rolling event rates using your scoring weights
- `rolling_full_fp_pa` — full FP including rolling R/RBI estimates

**Pitcher rolling:**
- `rolling_k_ip`, `rolling_bb_ip`, `rolling_h_ip`, `rolling_er_ip` — raw IP rates from events
- `rolling_fp_from_events` — FP/IP from rolling event rates

**Key distinction:** Rolling values show *recent actual production*. Season projected rates
show *expected future rate* based on process. Use rolling to identify hot/cold streaks;
use season projections for underlying skill.

---

## Player Name Mapping

Hitter names come from the Chadwick Bureau register via pybaseball, with an MLB Stats API
fallback for players missing from the register (recent debuts, international signings).
Pitcher names come from the Statcast data directly, with an MLB Stats API fallback for null
or numeric player_name values.

Unresolved IDs (where the name is a raw number) are logged as warnings during
`plv build-exports`. Call `validate_player_names()` from `build_exports` to audit.

---

## What is noisiest

In order from most to least noisy:

1. **Pitcher ER/IP and H/IP** — ERA and BABIP have substantial luck
   components. Year-to-year ERA r² ≈ 0.35 even with perfect information.

2. **Hitter R and RBI** — Lineup-context dependent. A .400 OBP player
   batting 8th scores far fewer runs than the same player batting 3rd.
   Only in `full_fp_per_pa`, not in `core_fp_per_pa`.

3. **Pitcher BB/IP** — Some signal from cs_pct but walk rate has more
   random variation than K rate.

4. **SB proxy early season** — Shrinkage keeps early-season estimates near
   league average. Not trustworthy until 150+ PA.

---

## Most actionable outputs

**Immediately useful:**
- Hitter K/PA rankings — directly identify K-risk players to avoid or target
- Hitter BB/PA rankings — directly identify walk contributors
- Hitter `core_fp_per_pa` — clean aggregate of skill components; use as default ranking
- Pitcher K/IP rankings — the cleanest pitching fantasy signal

**Good directional guides:**
- Hitter TB/PA — power and in-play frequency combined correctly
- Hitter SB estimate — useful for speed players with 150+ PA
- Pitcher BB/IP — catches pitchers with control problems
- `full_fp_per_pa` — context-aware companion to core; shows R/RBI upside

**Use with caution:**
- Hitter R/PA and RBI/PA — treat as relative ordering only
- Pitcher ER/IP — useful for separating elite vs. poor, noisy in the middle
- Pitcher H/IP — BABIP variation makes this a weak signal
- SB early season (< 150 PA)

**Early season (< 150 PA / < 50 IP):**
- K and BB rates stabilize fastest (reliable at ~50 PA)
- TB/PA and ER/IP need ~150+ PA / 30+ IP to stabilize
- Use Decision+ (for hitters) and PLV (for pitchers) as the primary
  early-season signal; let the TB/ER models update over time

---

## Calibration notes

- Calibration uses 2023 + 2024 completed seasons (n = 828 hitter-seasons,
  1,379 pitcher-seasons).
- Rate targets are computed directly from pitch-level events in our own
  parquets — no external data sources required.
- Pitcher ER calibration uses FIP computed from our event counts as the
  target (HR, BB, HBP, K per estimated IP), not actual ERA. FIP is a better
  predictor of future ERA than ERA itself.
- Re-run calibration annually: `plv calibrate-fantasy --years 2023,2024,2025`
- Do not include 2026 in calibration (early season, incomplete sample).
