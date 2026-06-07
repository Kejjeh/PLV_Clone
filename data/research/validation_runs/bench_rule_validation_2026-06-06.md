# Bench-Rule Validation 2026-06-06

- Panel: `_boom_stack_per_start_panel_cache.parquet`
- Years: 2023-2025 (2023-2025)
- Total starts: **13,716**
- Overall mean FP: **10.22**, bust rate (<5.0): 0.278, boom rate (>=20.0): 0.149
- REPLACEMENT_FP (handcuff/cap-fodder baseline): 5.0

## Operationalization note

Live rp3 / blend / sustainability tags are present-day snapshots and cannot
be reconstructed point-in-time historically. We use the documented per-start
proxies: `boom_stack_pre` (tier signal), `opp_tertile` (TOUGH=3 / SOFT=1),
`k_pct` rolling 5+5 split (Rule 3 K%-drop), `boom_outcome` L8 (Rule 4).

## Per-rule results

### R1_ACE  (n=0)

### R2_MID_TOUGH  (n=231)
- n_bench: 231
- n_start: 0
- mean_fp_if_started: 10.04
- mean_fp_bench_cases: 10.04
- mean_fp_start_cases: None
- precision_bench_correct: 0.286
- recall_busts_caught: 1.0
- saved_from_busts: 500.3
- lost_from_goods: 1663.8
- net_fp_swing: -1163.5
- net_fp_swing_per_bench: -5.04
- boom_rate_among_bench: 0.156
- bust_rate_among_bench: 0.286

### R3_FLAGGED  (n=405)
- n_bench: 405
- n_start: 0
- mean_fp_if_started: 9.4
- mean_fp_bench_cases: 9.4
- mean_fp_start_cases: None
- precision_bench_correct: 0.294
- recall_busts_caught: 1.0
- saved_from_busts: 935.1
- lost_from_goods: 2715.1
- net_fp_swing: -1780.0
- net_fp_swing_per_bench: -4.4
- boom_rate_among_bench: 0.136
- bust_rate_among_bench: 0.294

### R3_FLAGGED_SOFT  (n=217)
- verdict_breakdown: all START (217)
- mean_fp_start: 11.42
- boom_rate_start: 0.171
- bust_rate_start: 0.267

### R4_CAP_RENTAL  (n=1677)
- n_bench: 1677
- n_start: 0
- mean_fp_if_started: 8.94
- mean_fp_bench_cases: 8.94
- mean_fp_start_cases: None
- precision_bench_correct: 0.316
- recall_busts_caught: 1.0
- saved_from_busts: 3789.8
- lost_from_goods: 10401.5
- net_fp_swing: -6611.7
- net_fp_swing_per_bench: -3.94
- boom_rate_among_bench: 0.108
- bust_rate_among_bench: 0.316

## Pooled outcomes if all 4 rules applied 2023-2025

- BENCH calls (R2+R3+R4): **2,313** out of 13,716 starts (16.9%)
- Bust rate among benched: **0.309**  (vs overall 0.278)
- Recall of all bust starts caught: **0.187**
- Total FP swing: **-9,555.2 FP** across 13,716 starts
- Per-start FP lift over naive (start everyone): **-0.697 FP/start**

## Recommendations

- **R1_ACE**: zero applicable starts in panel — rule too restrictive or unobserved.
- **R2_MID_TOUGH**: net -1163.5 FP across 231 BENCH calls (per-bench -5.04). Precision 0.29, recall 1.0. -> **REJECT (negative swing, benching good starts)**
- **R3_FLAGGED**: net -1780.0 FP across 405 BENCH calls (per-bench -4.4). Precision 0.29, recall 1.0. -> **REJECT (negative swing, benching good starts)**
- **R3_FLAGGED_SOFT**: pure START rule (n=217); mean FP 11.42 -> SHIP.
- **R4_CAP_RENTAL**: net -6611.7 FP across 1677 BENCH calls (per-bench -3.94). Precision 0.32, recall 1.0. -> **TUNE (marginal)**

## Caveats

- Top-rank sampling: panel includes every SP start, not just top-200-by-rp3.
  For top-rank-only sampling, restrict to pitchers with prior-year fp_total >= ~250.
- Replacement FP assumed = 5.0 (cap-fodder handcuff). True replacement varies by
  league depth (BrownU 8-team: probably closer to 6-8 FP for actual streamers).
- Rule 3's K%-drop proxy is mechanical; the spec's 'sustainability NOISE/REGRESS' is
  not directly available historically. Live deployment should use that tag instead.
- Rule 4 boom_outcome threshold is panel-defined (>=20 FP). Matches CLAUDE.md.
- 2026 in-season starts excluded (not in panel cache). Re-run after refresh.
