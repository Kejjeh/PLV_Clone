# PL Rank Value vs rh3/rp3 Baseline (BrownU 8-team)

_Run date: 2026-06-06 — year tested: 2025_

## Method

- **Outcome:** season-end FP per game (hitters), FP per start (SP), FP per RP appearance (RP).
- **Year tested:** 2025 (most complete PL mid-season cache + final actuals).
- **Baseline (proxy for rh3/rp3):** prior-year FP/g — the dominant single feature both rh3 and rp3 are built on (anchor coefficient in the weight fit).
- **+PL model:** prior-year FP/g + PL mid-season rank.
- **Metric:** incremental R^2 + nested F-test + partial Spearman corr.

> Note: We use prior-year FP/g — not the live rh3/rp3 projection — because rh3/rp3 are themselves trained on prior-year FP + archetype + drift. A test against the full live model would be circular (PL ranks may indirectly inform the priors used to fit rh3/rp3 weights). Using the raw anchor is the conservative apples-to-apples test of whether PL adds info OVER AND ABOVE the strongest single feature.

## Results by position bucket

| Bucket | n | Univariate PL R^2 | Baseline R^2 (prior-y FP) | +PL Full R^2 | Incr. R^2 | F (df=1) | p-value |
|---|---:|---:|---:|---:|---:|---:|---:|
| H | 144 | 0.1292 | 0.4267 | 0.4303 | +0.36pp | 0.88 | 0.3485 |
| SP | 82 | 0.3167 | 0.0971 | 0.3179 | +22.08pp | 25.57 | 0.0000 |
| RP | 41 | 0.4971 | 0.2275 | 0.4978 | +27.03pp | 20.45 | 0.0001 |

## Spearman correlations (rank-based, robust)

| Bucket | rho(PL, FP) univariate | rho(prior, FP) | partial rho(PL | prior) | p partial |
|---|---:|---:|---:|---:|
| H | -0.532 (p=0.0000) | +0.417 (p=0.0000) | -0.246 | 0.0030 |
| SP | -0.583 (p=0.0000) | +0.325 (p=0.0029) | -0.558 | 0.0000 |
| RP | -0.792 (p=0.0000) | +0.412 (p=0.0074) | -0.652 | 0.0000 |

_PL rank is inversely scaled (rank 1 = best), so a negative correlation with FP/g = 'lower rank → higher production' = signal._

## Subgroup: streamer-tier vs core-hold

PL ranks may carry more decision value in the **streamer tier** (low PL ranks) where rh3/rp3's prior-year anchor is weaker (small sample / rookies), and less value in the **core-hold tier** where prior-year FP is itself elite-predictive.

Streamer tiers: H rank>80 / SP rank>50 / RP rank>25. Core tiers: H≤50 / SP≤25 / RP≤15.

| Bucket | tier | n | base R^2 | +PL R^2 | incr R^2 |
|---|---|---:|---:|---:|---:|
| H | streamer | 65 | 0.4037 | 0.4135 | +0.98pp |
| H | core-hold | 50 | 0.3571 | 0.4720 | +11.49pp |
| SP | streamer | 37 | 0.0272 | 0.0272 | +0.00pp |
| SP | core-hold | 26 | 0.0489 | 0.2278 | +17.89pp |
| RP | streamer | — | — | — | _n<20_ |
| RP | core-hold | — | — | — | _n<20_ |

## Verdict

- **Hitters (n=144):** **KEEP AS SANITY-CHECK** — directional signal present but small.
- **Starting Pitchers (n=82):** **KEEP AS LENS** — PL rank carries statistically and practically distinct information beyond the prior-year anchor.
- **Relievers (n=41):** **KEEP AS LENS** — PL rank carries statistically and practically distinct information beyond the prior-year anchor.

## Caveats

- Baseline = prior-year FP/g, not live rh3/rp3. Live rh3/rp3 contains additional features (archetype, drift, K-form for SPs) that may further compress incremental PL R^2.
- Single-year test (2025). The pl_rank_panel covers 2019-2025 — a multi-year pooled fit is the natural next step if a non-trivial signal is found here.
- Rookies excluded by inner-join requirement on prior_year_fp (PL's bias is plausibly highest for veterans with track record).
- 'Mid-season PL rank' is a single snapshot, not the rolling weekly rank a manager actually consumes; if anything this overstates PL's predictive value (it has more season already in it than an April rank would).
