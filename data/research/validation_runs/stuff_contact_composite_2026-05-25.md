---
signal: stuff_contact_composite
formula: binary flag: whiff_pct_to >= 26.0 AND xwoba_contact_to <= 0.320
outcome: good_start_rate_ros (fraction of remaining 2026 starts with fp_proxy_per_bf >= -0.0476)
expected_sign: positive (composite should predict above-baseline good-start rate)
theory: Harrison archetype — pitchers who generate high swing-and-miss AND suppress contact quality simultaneously should have persistently high good-start rates. MC agent 2 (2026-05-25) validated +16.2pp lift above 36.0% blind-pool baseline on 2021-2025 holdout. BABIP sub-filter (> 0.350 exclusion) should NOT be applied — high-BABIP composite fires showed 45.5% success vs 27.3% without BABIP filter.
production_target: rp3 (signal used in build_sp_alerts.py Signal A HIGH and fa-monitor Signal A; not yet a direct rp3 feature)
framing: in-season → ros (season-to-date whiff/xwOBACON → rest-of-season good-start rate)
holdout_years: [2021, 2022, 2023, 2024, 2025]
training_years: none (MC bootstrap on full 2018-2025 calendar, held out per year)
validation_script: scripts/xfp/validate_stuff_contact_composite.py
date: 2026-05-25
verdict: MARGINAL (binary flag) — SEE BELOW for xwoba_contact PASS finding
purpose: Harrison miss prevention — Kyle Harrison sat on FA wire (fpp +0.038, whiff 30%, rp3 #33) while Bradish (fpp -0.114) and Framber (fpp -0.138) were rostered. Signal A HIGH in build_sp_alerts.py now uses this composite. Pre-registering before any attempt to add directly to RP3_FEATS.
---

## MC bootstrap results (2026-05-25)

Source: `data/research/mc_harrison_composite_results.txt`

| Metric | Value |
|---|---|
| Correct baseline (2021-2025) | **36.0%** good-start rate |
| Composite fires (whiff ≥ 26% AND xwOBACON ≤ 0.320) | ~68% precision |
| Lift vs blind pool | **+16.2pp** (holdout: +15.7pp) |
| BABIP > 0.350 sub-fires | 45.5% success (do NOT exclude — BABIP is outcome noise) |
| BABIP ≤ 0.350 sub-fires | 27.3% success |

Note: earlier MC agent 2 run produced inflated 91.2% baseline due to wrong IP formula (used BF − BB − HBP − H as IP proxy with ER_approx). That result was discarded. The 36.0% baseline from MC agent 3 (rolling window agent) using the correct fpp formula is the authoritative number.

## Thresholds (MC-validated, 2026-05-25)

- whiff_pct_to: **≥ 26.0%** (no change from initial)
- xwoba_contact_to: **≤ 0.320**
- These are used as Signal A HIGH gates in `build_sp_alerts.py` and `run_fa_monitor.py`

## What a formal /validate-feature run would need

1. Build per-SP season rows: whiff_pct_to, xwoba_contact_to, good_start_rate_ros
2. For each year 2018-2025 as holdout:
   - Baseline = blind-pool good-start rate (should reproduce 36.0%)
   - Composite = good-start rate among pitchers with flag=1
   - Lift = composite rate − baseline
3. Apply Bonferroni at α=0.05 (single hypothesis — no sweep)
4. Decision: PASS if lift ≥ +0.10 (10pp above 36% baseline) in ≥ 5/8 years
5. Rule 9: if promoting to RP3_FEATS, baseline must include ALL current RP3_FEATS

## Current status

Signal is used operationally in `build_sp_alerts.py` (Signal A HIGH) and `run_fa_monitor.py` Signal A.
It is NOT yet added to RP3_FEATS. A formal /validate-feature run is required before any attempt to
add it as a direct rp3 feature.

## Step 2.5 data-coverage pre-check (for future formal run)

- `whiff_pct_to`: coverage ~100% for pitchers with ≥ 50 pitches season-to-date in statcast_2026.parquet
- `xwoba_contact_to`: coverage ~90% (requires launch_speed IS NOT NULL on events rows); pitchers with < 15 balls in play have NULL
- Fill strategy: pitchers below coverage threshold → exclude from composite flag (do not impute to 0 — that would spuriously fire the composite)

---

## Formal /validate-feature results (2026-05-25)

Script: `scripts/xfp/validate_stuff_contact_composite.py`
Rule 9 baseline: full RP3_FEATS (24 features incl. ros_opp_xwoba_weighted), r=0.5654

**Data caveat:** full-season whiff% and xwOBA-contact used as "to-date" proxy.
Optimism bias on the continuous features. Binary flag less affected (threshold is less
sensitive to exact value).

### Binary flag result: MARGINAL

| Gate | Value | Pass? |
|---|---|---|
| (a) Lift ≥ +0.005 | **+0.0021** | FAIL |
| (b) Sign ≥ 5/7 years | 7/7 | PASS |
| (c) Holdout (2024-25) lift > 0 | +0.0040 | PASS |

Per-year lifts: 2018 +0.0029, 2019 +0.0007, 2021 +0.0003, 2022 +0.0039, 2023 +0.0021, 2024 +0.0052, 2025 +0.0029

**Verdict: MARGINAL.** Consistent direction but the binary threshold is a lossy encoding —
it discards magnitude information and is absorbed by the continuous forms already proxied
in RP3_FEATS (swstr_pct_to_sh, xwoba_per_pa_to_sh). Do NOT add binary flag to RP3_FEATS.

### Emergent finding: continuous components show large lift (data-leakage caveat)

| Feature | Lift vs RP3_FEATS | Sign | Holdout |
|---|---|---|---|
| `whiff_pct` (continuous, full-season) | **+0.0521** | 7/7 | +0.0659 |
| `xwoba_contact` (continuous, full-season) | **+0.1012** | 7/7 | +0.1380 |
| Bundle (both + flag) | **+0.1369** | — | — |

`xwoba_contact` is the largest single-feature lift ever measured against the full RP3_FEATS
baseline. BUT: these numbers use full-season data (data leakage). Must re-validate with
proper split-day computation before any promotion.

**Next step:** pre-register `xwoba_contact_to` as a candidate for RP3_FEATS; build
per-pitcher split-day time series from statcast parquets; run proper in-season validation.

### Operational status (unchanged)

Signal A HIGH in `build_sp_alerts.py` and `run_fa_monitor.py` continues to use the
composite gate (whiff ≥ 26% AND xwOBACON ≤ 0.320) for SP alert screening. This is
correct — the MC result (+16.2pp lift above 36% blind-pool) remains valid for the alert
use case. The formal rp3 result says "don't add binary flag to the model" — it doesn't
invalidate the alert use case.
