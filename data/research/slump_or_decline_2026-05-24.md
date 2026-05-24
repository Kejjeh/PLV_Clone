# Slump-or-Decline targeted analysis — 2026-05-24

Per skill `.claude/skills/slump-or-decline/SKILL.md`. Anchored on L150 PA (Bayesian, k=150), not L21d.


## Vladimir Guerrero Jr.  (ROSTER, MLBAM 665489, TOR)

### Step 1 — Multi-year baseline

| Year | PA | xwOBA | xBA | HR | G |
|---|---|---|---|---|---|
| 2022 | 706 | 0.354 | 0.338 | 32 | 156 |
| 2023 | 682 | 0.380 | 0.353 | 26 | 155 |
| 2024 | 697 | 0.412 | 0.375 | 30 | 158 |
| 2025 | 680 | 0.384 | 0.358 | 23 | 154 |
| 2026 | 216 | 0.362 | 0.347 | 3 | 51 |

### Step 2 — Multi-window xwOBA path (2026)

| Window | PA | xwOBA | xBA | xwOBACON | EV90 | K% | HR |
|---|---|---|---|---|---|---|---|
| L7d | 27 | 0.374 | 0.340 | 0.312 | 103.8 | 3.7% | 1 |
| L14d | 53 | 0.301 | 0.268 | 0.251 | 103.4 | 7.5% | 1 |
| L21d | 76 | 0.313 | 0.306 | 0.288 | 103.6 | 10.5% | 1 |
| L30d | 113 | 0.341 | 0.324 | 0.317 | 103.8 | 8.8% | 1 |
| **L150 PA** (2026-04-14 00:00:00 → 2026-05-22 00:00:00) | 150 | 0.342 | 0.342 | 0.341 | 108.2 | — | 2 |
| L150 pre-L21d (anchor) | 150 | 0.376 | — | 0.388 | 110.3 | — | — |
| 2026 season | 216 | 0.362 | 0.347 | — | — | — | 3 |
| 2025 season | 680 | 0.384 | 0.358 | — | — | — | 23 |

### Step 3 — Sample-size 95% CIs (vs L150 anchor)

Anchor: **L150 pre-L21d = 0.376** (150 PA)

| Window | xwOBA | n | 95% CI | Anchor in CI? |
|---|---|---|---|---|
| L7d | 0.374 | 27 | [0.227, 0.522] | YES |
| L14d | 0.301 | 53 | [0.196, 0.406] | YES |
| L21d | 0.313 | 76 | [0.225, 0.400] | YES |
| L30d | 0.341 | 113 | [0.269, 0.413] | YES |

> **L21d 95% CI includes the L150 anchor — cannot statistically distinguish slump from noise at this window.**

### Step 4 — Bayesian shrinkage (k=150 to L150 anchor)

- L21d observed xwOBA: **0.313** (n=76)
- Anchor (L150 pre-L21d): **0.376**
- Raw gap: **-0.063**
- Bayesian-shrunk L21d: **0.355**
- **Shrunk gap: -0.021** ← the verdict-driving number
- (2025-anchored reference: shrunk = 0.360, gap = -0.024)

### Step 5 — xwOBACON separation

- L21d xwOBACON: **0.288**
- L150 PA xwOBACON: 0.341
- L150 pre-L21d xwOBACON: 0.388
- xwOBACON gap (L21d vs pre-L21d): **-0.101**

### Step 6 — K%/BB% decomposition

| Window | PA | K% | BB% | HR |
|---|---|---|---|---|
| L21d | 76 | 10.5% | 11.8% | 1 |
| L30d | 113 | 8.8% | 11.5% | 1 |
| 2025 season | 680 | 13.5% | 10.7% | — |
| 2026 season | 216 | 10.6% | 10.6% | — |

### Step 7 — Process metrics (bat speed, whiff, chase, Z-contact)

| Window | Bat speed | Whiff% | Chase% | Z-Contact% | Swings |
|---|---|---|---|---|---|
| 2025 | 75.2 | 21.5% | 21.0% | 84.2% | 1056 |
| 2026 szn | 74.9 | 20.0% | 30.2% | 83.2% | 385 |
| L21d | 74.8 | 19.3% | 29.9% | 82.1% | 145 |
| L7d | 74.6 | 19.6% | 36.2% | 79.4% | 51 |

- Bat-speed direction (L21d vs base): **hold**
- Whiff direction (L21d vs base): **hold**  (DOWN = improving)
- EV90 direction (L21d vs L150): **down**

### Step 8 — Pitch-mix attack

| Window | FB% | BRK% | OFF% | Pitches |
|---|---|---|---|---|
| 2025 | 57.6% | 27.5% | 14.7% | 2502 |
| 2026 szn | 55.9% | 30.3% | 13.8% | 792 |
| L21d | 56.9% | 28.4% | 14.7% | 299 |

### Step 9 — Splits (2026, vs LHP/RHP)

| p_throws | PA | xwOBA |
|---|---|---|
| L | 49 | 0.480 |
| R | 167 | 0.328 |

### Step 10 — Calendar history (month=5, prior years)

| Year | PA | xwOBA | HR |
|---|---|---|---|

### Step 11 — Injury/news

Not pulled in this batch run; see ESPN roster/FA pool for live injuryStatus.

### Step 13 — rh3 slump signals

- rh3 rank: **#32**, rh3 FP/g: **2.05**
- slump_pct_rank: 53.0
- slump_n_comparable: 499.0
- **slump_bounce_pct: 83.0%** (already 0-100)
- slump_next_rate: 0.3881  slump_delta: 0.0689

### Step 15 — Verdict

**Verdict: HOLD with caveat**

_Rationale:_ Mixed signals; shrunk gap -0.021.

_Confidence:_ L21d n=76 PA → xwOBA SE ≈ 0.045; verdict has ±0.088 uncertainty on raw xwOBA.


## Trea Turner  (ROSTER, MLBAM 607208, PHI)

### Step 1 — Multi-year baseline

| Year | PA | xwOBA | xBA | HR | G |
|---|---|---|---|---|---|
| 2022 | 708 | 0.338 | 0.345 | 21 | 157 |
| 2023 | 694 | 0.331 | 0.343 | 26 | 151 |
| 2024 | 541 | 0.323 | 0.326 | 21 | 121 |
| 2025 | 642 | 0.321 | 0.330 | 15 | 138 |
| 2026 | 222 | 0.287 | 0.310 | 5 | 49 |

### Step 2 — Multi-window xwOBA path (2026)

| Window | PA | xwOBA | xBA | xwOBACON | EV90 | K% | HR |
|---|---|---|---|---|---|---|---|
| L7d | 21 | 0.343 | 0.318 | 0.386 | 100.4 | 19.0% | 1 |
| L14d | 46 | 0.295 | 0.311 | 0.346 | 100.5 | 23.9% | 1 |
| L21d | 79 | 0.295 | 0.340 | 0.366 | 100.8 | 24.1% | 1 |
| L30d | 111 | 0.291 | 0.322 | 0.350 | 102.3 | 23.4% | 3 |
| **L150 PA** (2026-04-14 00:00:00 → 2026-05-22 00:00:00) | 150 | 0.306 | 0.321 | 0.352 | 104.1 | — | 4 |
| L150 pre-L21d (anchor) | 150 | 0.286 | — | 0.315 | 104.2 | — | — |
| 2026 season | 222 | 0.287 | 0.310 | — | — | — | 5 |
| 2025 season | 642 | 0.321 | 0.330 | — | — | — | 15 |

### Step 3 — Sample-size 95% CIs (vs L150 anchor)

Anchor: **L150 pre-L21d = 0.286** (150 PA)

| Window | xwOBA | n | 95% CI | Anchor in CI? |
|---|---|---|---|---|
| L7d | 0.343 | 21 | [0.176, 0.510] | YES |
| L14d | 0.295 | 46 | [0.182, 0.407] | YES |
| L21d | 0.295 | 79 | [0.209, 0.381] | YES |
| L30d | 0.291 | 111 | [0.218, 0.363] | YES |

> **L21d 95% CI includes the L150 anchor — cannot statistically distinguish slump from noise at this window.**

### Step 4 — Bayesian shrinkage (k=150 to L150 anchor)

- L21d observed xwOBA: **0.295** (n=79)
- Anchor (L150 pre-L21d): **0.286**
- Raw gap: **+0.010**
- Bayesian-shrunk L21d: **0.289**
- **Shrunk gap: +0.003** ← the verdict-driving number
- (2025-anchored reference: shrunk = 0.312, gap = -0.009)

### Step 5 — xwOBACON separation

- L21d xwOBACON: **0.366**
- L150 PA xwOBACON: 0.352
- L150 pre-L21d xwOBACON: 0.315
- xwOBACON gap (L21d vs pre-L21d): **+0.051**

### Step 6 — K%/BB% decomposition

| Window | PA | K% | BB% | HR |
|---|---|---|---|---|
| L21d | 79 | 24.1% | 5.1% | 1 |
| L30d | 111 | 23.4% | 6.3% | 3 |
| 2025 season | 642 | 16.7% | 6.5% | — |
| 2026 season | 222 | 21.2% | 7.2% | — |

### Step 7 — Process metrics (bat speed, whiff, chase, Z-contact)

| Window | Bat speed | Whiff% | Chase% | Z-Contact% | Swings |
|---|---|---|---|---|---|
| 2025 | 69.5 | 24.8% | 31.0% | 86.0% | 1238 |
| 2026 szn | 70.0 | 25.9% | 34.6% | 86.0% | 425 |
| L21d | 69.8 | 23.8% | 37.1% | 89.4% | 160 |
| L7d | 69.0 | 24.4% | 25.6% | 90.0% | 41 |

- Bat-speed direction (L21d vs base): **hold**
- Whiff direction (L21d vs base): **down**  (DOWN = improving)
- EV90 direction (L21d vs L150): **down**

### Step 8 — Pitch-mix attack

| Window | FB% | BRK% | OFF% | Pitches |
|---|---|---|---|---|
| 2025 | 51.4% | 35.2% | 12.9% | 2407 |
| 2026 szn | 52.6% | 34.3% | 13.1% | 837 |
| L21d | 51.1% | 36.3% | 12.7% | 284 |

### Step 9 — Splits (2026, vs LHP/RHP)

| p_throws | PA | xwOBA |
|---|---|---|
| L | 69 | 0.306 |
| R | 153 | 0.278 |

### Step 10 — Calendar history (month=5, prior years)

| Year | PA | xwOBA | HR |
|---|---|---|---|

### Step 11 — Injury/news

Not pulled in this batch run; see ESPN roster/FA pool for live injuryStatus.

### Step 13 — rh3 slump signals

- rh3 rank: **#113**, rh3 FP/g: **1.79**
- slump_pct_rank: 13.7
- slump_n_comparable: 167.0
- **slump_bounce_pct: 81.4%** (already 0-100)
- slump_next_rate: 0.2886  slump_delta: 0.0996

### Step 15 — Verdict

**Verdict: NOT SLUMPING (structural)**

_Rationale:_ Shrunk gap +0.003 vs L150 anchor — current rate ≈ baseline.

_Confidence:_ L21d n=79 PA → xwOBA SE ≈ 0.044; verdict has ±0.086 uncertainty on raw xwOBA.


## Salvador Perez  (ROSTER, MLBAM 521692, KC)

### Step 1 — Multi-year baseline

| Year | PA | xwOBA | xBA | HR | G |
|---|---|---|---|---|---|
| 2022 | 473 | 0.324 | 0.317 | 23 | 112 |
| 2023 | 583 | 0.326 | 0.350 | 23 | 138 |
| 2024 | 653 | 0.361 | 0.347 | 27 | 155 |
| 2025 | 641 | 0.357 | 0.340 | 30 | 152 |
| 2026 | 207 | 0.291 | 0.287 | 8 | 48 |

### Step 2 — Multi-window xwOBA path (2026)

| Window | PA | xwOBA | xBA | xwOBACON | EV90 | K% | HR |
|---|---|---|---|---|---|---|---|
| L7d | 20 | 0.481 | 0.366 | 0.452 | 102.9 | 5.0% | 2 |
| L14d | 42 | 0.395 | 0.347 | 0.417 | 102.8 | 11.9% | 3 |
| L21d | 70 | 0.308 | 0.286 | 0.331 | 102.0 | 18.6% | 3 |
| L30d | 107 | 0.305 | 0.290 | 0.345 | 101.9 | 19.6% | 5 |
| **L150 PA** (2026-04-11 00:00:00 → 2026-05-22 00:00:00) | 150 | 0.288 | 0.301 | 0.349 | 105.1 | — | 6 |
| L150 pre-L21d (anchor) | 150 | 0.279 | — | 0.337 | 105.4 | — | — |
| 2026 season | 207 | 0.291 | 0.287 | — | — | — | 8 |
| 2025 season | 641 | 0.357 | 0.340 | — | — | — | 30 |

### Step 3 — Sample-size 95% CIs (vs L150 anchor)

Anchor: **L150 pre-L21d = 0.279** (150 PA)

| Window | xwOBA | n | 95% CI | Anchor in CI? |
|---|---|---|---|---|
| L7d | 0.481 | 20 | [0.310, 0.652] | no |
| L14d | 0.395 | 42 | [0.277, 0.513] | YES |
| L21d | 0.308 | 70 | [0.217, 0.399] | YES |
| L30d | 0.305 | 107 | [0.231, 0.379] | YES |

> **L21d 95% CI includes the L150 anchor — cannot statistically distinguish slump from noise at this window.**

### Step 4 — Bayesian shrinkage (k=150 to L150 anchor)

- L21d observed xwOBA: **0.308** (n=70)
- Anchor (L150 pre-L21d): **0.279**
- Raw gap: **+0.029**
- Bayesian-shrunk L21d: **0.288**
- **Shrunk gap: +0.009** ← the verdict-driving number
- (2025-anchored reference: shrunk = 0.342, gap = -0.016)

### Step 5 — xwOBACON separation

- L21d xwOBACON: **0.331**
- L150 PA xwOBACON: 0.349
- L150 pre-L21d xwOBACON: 0.337
- xwOBACON gap (L21d vs pre-L21d): **-0.006**

### Step 6 — K%/BB% decomposition

| Window | PA | K% | BB% | HR |
|---|---|---|---|---|
| L21d | 70 | 18.6% | 7.1% | 3 |
| L30d | 107 | 19.6% | 4.7% | 5 |
| 2025 season | 641 | 19.5% | 3.6% | — |
| 2026 season | 207 | 20.3% | 3.9% | — |

### Step 7 — Process metrics (bat speed, whiff, chase, Z-contact)

| Window | Bat speed | Whiff% | Chase% | Z-Contact% | Swings |
|---|---|---|---|---|---|
| 2025 | 71.3 | 26.9% | 41.6% | 82.7% | 1301 |
| 2026 szn | 70.0 | 26.5% | 44.9% | 83.1% | 437 |
| L21d | 69.9 | 28.1% | 44.4% | 87.2% | 146 |
| L7d | 69.5 | 18.9% | 34.9% | 95.5% | 37 |

- Bat-speed direction (L21d vs base): **hold**
- Whiff direction (L21d vs base): **up**  (DOWN = improving)
- EV90 direction (L21d vs L150): **hold**

### Step 8 — Pitch-mix attack

| Window | FB% | BRK% | OFF% | Pitches |
|---|---|---|---|---|
| 2025 | 50.5% | 37.1% | 12.2% | 2267 |
| 2026 szn | 50.7% | 39.2% | 10.1% | 761 |
| L21d | 47.7% | 41.5% | 10.9% | 258 |

### Step 9 — Splits (2026, vs LHP/RHP)

| p_throws | PA | xwOBA |
|---|---|---|
| L | 55 | 0.390 |
| R | 152 | 0.255 |

### Step 10 — Calendar history (month=5, prior years)

| Year | PA | xwOBA | HR |
|---|---|---|---|

### Step 11 — Injury/news

Not pulled in this batch run; see ESPN roster/FA pool for live injuryStatus.

### Step 13 — rh3 slump signals

- rh3 rank: **#170**, rh3 FP/g: **1.64**
- slump_pct_rank: 15.8
- slump_n_comparable: 201.0
- **slump_bounce_pct: 97.0%** (already 0-100)
- slump_next_rate: 0.2822  slump_delta: 0.1554

### Step 15 — Verdict

**Verdict: NOT SLUMPING (structural)**

_Rationale:_ Shrunk gap +0.009 vs L150 anchor — current rate ≈ baseline.

_Confidence:_ L21d n=70 PA → xwOBA SE ≈ 0.047; verdict has ±0.091 uncertainty on raw xwOBA.


## Carlos Cortes  (FA, MLBAM 666126, ATH)

### Step 1 — Multi-year baseline

| Year | PA | xwOBA | xBA | HR | G |
|---|---|---|---|---|---|
| 2022 | 0 | — | — | 0 | 0 |
| 2023 | 0 | — | — | 0 | 0 |
| 2024 | 0 | — | — | 0 | 0 |
| 2025 | 99 | 0.314 | 0.339 | 4 | 39 |
| 2026 | 133 | 0.389 | 0.366 | 4 | 40 |

### Step 2 — Multi-window xwOBA path (2026)

| Window | PA | xwOBA | xBA | xwOBACON | EV90 | K% | HR |
|---|---|---|---|---|---|---|---|
| L7d | 22 | 0.385 | 0.339 | 0.324 | 101.7 | 13.6% | 0 |
| L14d | 34 | 0.377 | 0.373 | 0.357 | 103.2 | 14.7% | 0 |
| L21d | 49 | 0.323 | 0.325 | 0.311 | 103.6 | 14.3% | 0 |
| L30d | 75 | 0.363 | 0.347 | 0.366 | 103.7 | 13.3% | 2 |
| **L150 PA** (2025-09-20 → 2026-05-22 00:00:00) | 150 | 0.373 | 0.356 | 0.378 | 104.5 | — | 4 |
| L150 pre-L21d (anchor) | 150 | 0.387 | — | 0.418 | 104.5 | — | — |
| 2026 season | 133 | 0.389 | 0.366 | — | — | — | 4 |
| 2025 season | 99 | 0.314 | 0.339 | — | — | — | 4 |

### Step 3 — Sample-size 95% CIs (vs L150 anchor)

Anchor: **L150 pre-L21d = 0.387** (150 PA)

| Window | xwOBA | n | 95% CI | Anchor in CI? |
|---|---|---|---|---|
| L7d | 0.385 | 22 | [0.222, 0.548] | YES |
| L14d | 0.377 | 34 | [0.246, 0.508] | YES |
| L21d | 0.323 | 49 | [0.214, 0.432] | YES |
| L30d | 0.363 | 75 | [0.275, 0.451] | YES |

> **L21d 95% CI includes the L150 anchor — cannot statistically distinguish slump from noise at this window.**

### Step 4 — Bayesian shrinkage (k=150 to L150 anchor)

- L21d observed xwOBA: **0.323** (n=49)
- Anchor (L150 pre-L21d): **0.387**
- Raw gap: **-0.064**
- Bayesian-shrunk L21d: **0.371**
- **Shrunk gap: -0.016** ← the verdict-driving number
- (2025-anchored reference: shrunk = 0.316, gap = +0.002)

### Step 5 — xwOBACON separation

- L21d xwOBACON: **0.311**
- L150 PA xwOBACON: 0.378
- L150 pre-L21d xwOBACON: 0.418
- xwOBACON gap (L21d vs pre-L21d): **-0.108**

### Step 6 — K%/BB% decomposition

| Window | PA | K% | BB% | HR |
|---|---|---|---|---|
| L21d | 49 | 14.3% | 12.2% | 0 |
| L30d | 75 | 13.3% | 10.7% | 2 |
| 2025 season | 99 | 20.2% | 3.0% | — |
| 2026 season | 133 | 10.5% | 10.5% | — |

### Step 7 — Process metrics (bat speed, whiff, chase, Z-contact)

| Window | Bat speed | Whiff% | Chase% | Z-Contact% | Swings |
|---|---|---|---|---|---|
| 2025 | 68.4 | 21.5% | 30.0% | 80.7% | 191 |
| 2026 szn | 68.9 | 19.2% | 22.6% | 85.1% | 239 |
| L21d | 68.9 | 23.5% | 24.3% | 84.5% | 85 |
| L7d | 70.1 | 11.1% | 17.0% | 92.6% | 36 |

- Bat-speed direction (L21d vs base): **hold**
- Whiff direction (L21d vs base): **up**  (DOWN = improving)
- EV90 direction (L21d vs L150): **hold**

### Step 8 — Pitch-mix attack

| Window | FB% | BRK% | OFF% | Pitches |
|---|---|---|---|---|
| 2025 | 55.5% | 23.2% | 20.8% | 375 |
| 2026 szn | 55.5% | 25.7% | 18.2% | 544 |
| L21d | 56.2% | 25.8% | 18.0% | 194 |

### Step 9 — Splits (2026, vs LHP/RHP)

| p_throws | PA | xwOBA |
|---|---|---|
| L | 9 | 0.347 |
| R | 124 | 0.392 |

### Step 10 — Calendar history (month=5, prior years)

| Year | PA | xwOBA | HR |
|---|---|---|---|

### Step 11 — Injury/news

Not pulled in this batch run; see ESPN roster/FA pool for live injuryStatus.

### Step 13 — rh3 slump signals

- rh3 rank: **#20**, rh3 FP/g: **2.16**
- slump_pct_rank: 100.0
- slump_n_comparable: 13.0
- **slump_bounce_pct: 100.0%** (already 0-100)
- slump_next_rate: 0.5122  slump_delta: 0.0396

### Step 15 — Verdict

**Verdict: NOT SLUMPING (structural)**

_Rationale:_ Shrunk gap -0.016 vs L150 anchor — current rate ≈ baseline.

_Confidence:_ L21d n=49 PA → xwOBA SE ≈ 0.056; verdict has ±0.109 uncertainty on raw xwOBA.


## Eugenio Suárez  (FA, MLBAM 553993, CIN)

### Step 1 — Multi-year baseline

| Year | PA | xwOBA | xBA | HR | G |
|---|---|---|---|---|---|
| 2022 | 630 | 0.344 | 0.345 | 31 | 146 |
| 2023 | 695 | 0.323 | 0.339 | 22 | 162 |
| 2024 | 641 | 0.335 | 0.355 | 30 | 156 |
| 2025 | 660 | 0.320 | 0.317 | 49 | 159 |
| 2026 | 100 | 0.273 | 0.305 | 3 | 25 |

### Step 2 — Multi-window xwOBA path (2026)

| Window | PA | xwOBA | xBA | xwOBACON | EV90 | K% | HR |
|---|---|---|---|---|---|---|---|
| L7d | 0 | — | — | — | — | — | 0 |
| L14d | 0 | — | — | — | — | — | 0 |
| L21d | 0 | — | — | — | — | — | 0 |
| L30d | 0 | — | — | — | — | — | 0 |
| **L150 PA** (2025-09-16 → 2026-04-22 00:00:00) | 150 | 0.288 | 0.325 | 0.398 | 105.8 | — | 7 |
| L150 pre-L21d (anchor) | 150 | 0.288 | — | 0.398 | 105.8 | — | — |
| 2026 season | 100 | 0.273 | 0.305 | — | — | — | 3 |
| 2025 season | 660 | 0.320 | 0.317 | — | — | — | 49 |

### Step 3 — Sample-size 95% CIs (vs L150 anchor)

Anchor: **L150 pre-L21d = 0.288** (150 PA)

| Window | xwOBA | n | 95% CI | Anchor in CI? |
|---|---|---|---|---|
| L7d | — | 0 | [—, —] | no |
| L14d | — | 0 | [—, —] | no |
| L21d | — | 0 | [—, —] | no |
| L30d | — | 0 | [—, —] | no |

### Step 4 — Bayesian shrinkage (k=150 to L150 anchor)

- Insufficient L21d or anchor PA for shrinkage.

### Step 5 — xwOBACON separation

- L21d xwOBACON: **—**
- L150 PA xwOBACON: 0.398
- L150 pre-L21d xwOBACON: 0.398

### Step 6 — K%/BB% decomposition

| Window | PA | K% | BB% | HR |
|---|---|---|---|---|
| L21d | 0 | — | — | 0 |
| L30d | 0 | — | — | 0 |
| 2025 season | 660 | 29.7% | 6.7% | — |
| 2026 season | 100 | 30.0% | 9.0% | — |

### Step 7 — Process metrics (bat speed, whiff, chase, Z-contact)

| Window | Bat speed | Whiff% | Chase% | Z-Contact% | Swings |
|---|---|---|---|---|---|
| 2025 | 69.5 | 33.3% | 30.9% | 78.8% | 1314 |
| 2026 szn | 68.6 | 32.6% | 28.0% | 76.7% | 178 |
| L21d | — | — | — | — | 0 |
| L7d | — | — | — | — | 0 |

- Bat-speed direction (L21d vs base): **na**
- Whiff direction (L21d vs base): **na**  (DOWN = improving)
- EV90 direction (L21d vs L150): **na**

### Step 8 — Pitch-mix attack

| Window | FB% | BRK% | OFF% | Pitches |
|---|---|---|---|---|
| 2025 | 53.4% | 35.6% | 10.8% | 2606 |
| 2026 szn | 57.1% | 29.3% | 13.6% | 396 |
| L21d | — | — | — | 0 |

### Step 9 — Splits (2026, vs LHP/RHP)

| p_throws | PA | xwOBA |
|---|---|---|
| L | 22 | 0.329 |
| R | 78 | 0.257 |

### Step 10 — Calendar history (month=5, prior years)

| Year | PA | xwOBA | HR |
|---|---|---|---|

### Step 11 — Injury/news

Per user context: recently back from IL.

### Step 13 — rh3 slump signals

- rh3 rank: **#318**, rh3 FP/g: **1.36**
- slump_pct_rank: 15.8
- slump_n_comparable: 239.0
- **slump_bounce_pct: 97.5%** (already 0-100)
- slump_next_rate: 0.2  slump_delta: 0.1455

### Step 15 — Verdict

**Verdict: INSUFFICIENT DATA**

_Rationale:_ Not enough PA in cache to anchor.


## Teoscar Hernández  (FA, MLBAM 606192, LAD)

### Step 1 — Multi-year baseline

| Year | PA | xwOBA | xBA | HR | G |
|---|---|---|---|---|---|
| 2022 | 536 | 0.357 | 0.379 | 25 | 128 |
| 2023 | 680 | 0.334 | 0.380 | 26 | 160 |
| 2024 | 642 | 0.347 | 0.360 | 33 | 151 |
| 2025 | 537 | 0.324 | 0.340 | 25 | 132 |
| 2026 | 187 | 0.333 | 0.363 | 6 | 46 |

### Step 2 — Multi-window xwOBA path (2026)

| Window | PA | xwOBA | xBA | xwOBACON | EV90 | K% | HR |
|---|---|---|---|---|---|---|---|
| L7d | 20 | 0.401 | 0.360 | 0.508 | 100.3 | 25.0% | 1 |
| L14d | 45 | 0.392 | 0.379 | 0.462 | 100.7 | 20.0% | 2 |
| L21d | 70 | 0.346 | 0.380 | 0.444 | 101.6 | 27.1% | 2 |
| L30d | 98 | 0.350 | 0.360 | 0.417 | 102.1 | 24.5% | 2 |
| **L150 PA** (2026-04-07 00:00:00 → 2026-05-22 00:00:00) | 150 | 0.332 | 0.344 | 0.405 | 104.1 | — | 4 |
| L150 pre-L21d (anchor) | 150 | 0.328 | — | 0.396 | 104.5 | — | — |
| 2026 season | 187 | 0.333 | 0.363 | — | — | — | 6 |
| 2025 season | 537 | 0.324 | 0.340 | — | — | — | 25 |

### Step 3 — Sample-size 95% CIs (vs L150 anchor)

Anchor: **L150 pre-L21d = 0.328** (150 PA)

| Window | xwOBA | n | 95% CI | Anchor in CI? |
|---|---|---|---|---|
| L7d | 0.401 | 20 | [0.230, 0.572] | YES |
| L14d | 0.392 | 45 | [0.278, 0.506] | YES |
| L21d | 0.346 | 70 | [0.254, 0.437] | YES |
| L30d | 0.350 | 98 | [0.273, 0.427] | YES |

> **L21d 95% CI includes the L150 anchor — cannot statistically distinguish slump from noise at this window.**

### Step 4 — Bayesian shrinkage (k=150 to L150 anchor)

- L21d observed xwOBA: **0.346** (n=70)
- Anchor (L150 pre-L21d): **0.328**
- Raw gap: **+0.017**
- Bayesian-shrunk L21d: **0.334**
- **Shrunk gap: +0.006** ← the verdict-driving number
- (2025-anchored reference: shrunk = 0.331, gap = +0.007)

### Step 5 — xwOBACON separation

- L21d xwOBACON: **0.444**
- L150 PA xwOBACON: 0.405
- L150 pre-L21d xwOBACON: 0.396
- xwOBACON gap (L21d vs pre-L21d): **+0.048**

### Step 6 — K%/BB% decomposition

| Window | PA | K% | BB% | HR |
|---|---|---|---|---|
| L21d | 70 | 27.1% | 5.7% | 2 |
| L30d | 98 | 24.5% | 10.2% | 2 |
| 2025 season | 537 | 24.6% | 4.7% | — |
| 2026 season | 187 | 27.3% | 8.6% | — |

### Step 7 — Process metrics (bat speed, whiff, chase, Z-contact)

| Window | Bat speed | Whiff% | Chase% | Z-Contact% | Swings |
|---|---|---|---|---|---|
| 2025 | 71.0 | 31.9% | 29.8% | 77.7% | 1058 |
| 2026 szn | 70.5 | 29.4% | 26.1% | 77.5% | 340 |
| L21d | 70.4 | 24.6% | 23.6% | 79.4% | 130 |
| L7d | 70.5 | 24.4% | 25.0% | 77.1% | 45 |

- Bat-speed direction (L21d vs base): **hold**
- Whiff direction (L21d vs base): **down**  (DOWN = improving)
- EV90 direction (L21d vs L150): **hold**

### Step 8 — Pitch-mix attack

| Window | FB% | BRK% | OFF% | Pitches |
|---|---|---|---|---|
| 2025 | 53.3% | 35.5% | 11.1% | 2107 |
| 2026 szn | 56.8% | 25.6% | 17.2% | 754 |
| L21d | 54.2% | 29.9% | 15.8% | 284 |

### Step 9 — Splits (2026, vs LHP/RHP)

| p_throws | PA | xwOBA |
|---|---|---|
| L | 43 | 0.388 |
| R | 144 | 0.317 |

### Step 10 — Calendar history (month=5, prior years)

| Year | PA | xwOBA | HR |
|---|---|---|---|

### Step 11 — Injury/news

Not pulled in this batch run; see ESPN roster/FA pool for live injuryStatus.

### Step 13 — rh3 slump signals

- rh3 rank: **#187**, rh3 FP/g: **1.61**
- slump_pct_rank: 36.6
- slump_n_comparable: 387.0
- **slump_bounce_pct: 93.0%** (already 0-100)
- slump_next_rate: 0.2206  slump_delta: 0.1168

### Step 15 — Verdict

**Verdict: NOT SLUMPING (structural)**

_Rationale:_ Shrunk gap +0.006 vs L150 anchor — current rate ≈ baseline.

_Confidence:_ L21d n=70 PA → xwOBA SE ≈ 0.047; verdict has ±0.091 uncertainty on raw xwOBA.


---

## Cross-player verdict summary

| Player | Role | Verdict |
|---|---|---|
| Vladimir Guerrero Jr. | ROSTER | **HOLD with caveat** |
| Trea Turner | ROSTER | **NOT SLUMPING (structural)** |
| Salvador Perez | ROSTER | **NOT SLUMPING (structural)** |
| Carlos Cortes | FA | **NOT SLUMPING (structural)** |
| Eugenio Suárez | FA | **INSUFFICIENT DATA** |
| Teoscar Hernández | FA | **NOT SLUMPING (structural)** |
