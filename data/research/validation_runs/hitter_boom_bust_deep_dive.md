# Hitter Boom / Bust Deep Dive — Per-game Distribution by boom_stack

Generated 2026-06-03. n_starter_games = 245,712
Years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]  PA-floor: 3

## Boom/bust definitions

- `fp_proxy = TB + BB + HBP - K` (r=0.98 vs full FP across season aggregates)
- **boom_game**: fp_proxy ≥ 3.0 (empirical 80th pct across all starter-games)
- **bust_game**: fp_proxy ≤ 0 (worse than nothing)
- Caveat: SB, R, RBI are not included in fp_proxy because statcast is pitch-level.
  Run-creating events (HR, runs scored on play) are partially captured via TB. SB
  and standalone R/RBI variance is unmodeled — interpret results as TB/BB/HBP/K-driven
  boom/bust, which captures the largest single component of hitter FP variance.

## 1. Distribution of fp_proxy by boom_stack

| boom_stack | n | bust≤0 | low | mid | good | boom | megaboom |
|---|---|---|---|---|---|---|---|
| 0 | 161,766 | 70287 (43.4%) | 30278 (18.7%) | 22526 (13.9%) | 0 (0.0%) | 25081 (15.5%) | 13594 (8.4%) |
| 1 | 75,234 | 30634 (40.7%) | 14302 (19.0%) | 11020 (14.6%) | 0 (0.0%) | 12350 (16.4%) | 6928 (9.2%) |
| 2 | 7,971 | 3207 (40.2%) | 1405 (17.6%) | 1168 (14.7%) | 0 (0.0%) | 1360 (17.1%) | 831 (10.4%) |
| 3 | 741 | 278 (37.5%) | 133 (17.9%) | 103 (13.9%) | 0 (0.0%) | 132 (17.8%) | 95 (12.8%) |

## 2. Summary stats of fp_proxy by boom_stack

| boom_stack | n | mean | median | p10 | p25 | p75 | p90 | bust% | boom% | mega% |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 161,766 | 1.12 | 1.00 | -2.00 | 0.00 | 2.00 | 4.00 | 43.4% | 23.9% | 8.4% |
| 1 | 75,234 | 1.27 | 1.00 | -1.00 | 0.00 | 3.00 | 4.00 | 40.7% | 25.6% | 9.2% |
| 2 | 7,971 | 1.35 | 1.00 | -1.00 | 0.00 | 3.00 | 5.00 | 40.2% | 27.5% | 10.4% |
| 3 | 741 | 1.58 | 1.00 | -1.00 | 0.00 | 3.00 | 5.00 | 37.5% | 30.6% | 12.8% |

**Stack=3 vs Stack=0 edge:** mean fp_proxy +0.46, boom rate +6.7 pp, bust rate -5.9 pp

## 3. Year-by-year stability of boom_rate edge

| year | n | boom%(stack=0) | boom%(stack=2+) | edge |
|---|---|---|---|---|
| 2018 | 35,014 | 24.9% | 27.2% | +2.3 pp |
| 2019 | 35,191 | 26.4% | 29.0% | +2.6 pp |
| 2021 | 33,935 | 24.1% | 28.3% | +4.2 pp |
| 2022 | 35,567 | 22.2% | 27.5% | +5.3 pp |
| 2023 | 35,660 | 24.0% | 28.3% | +4.2 pp |
| 2024 | 35,163 | 22.5% | 26.3% | +3.8 pp |
| 2025 | 35,182 | 23.2% | 27.6% | +4.4 pp |

## 4. Component-level — which flag matters most?

| component | n_flag=1 | boom%(flag=1) | boom%(flag=0) | edge | bust%(flag=1) | bust%(flag=0) |
|---|---|---|---|---|---|---|
| flag_skill_spike | 21,690 | 25.5% | 24.5% | +1.1 pp | 42.2% | 42.5% |
| flag_recform_hot | 2,998 | 28.3% | 24.5% | +3.7 pp | 39.9% | 42.5% |
| flag_opp_soft | 68,711 | 26.1% | 24.0% | +2.2 pp | 40.1% | 43.4% |

## 5. Bust focus — stack=3 busts (the reality check)

Of 741 stack=3 starter-games, 278 (37.5%) busted (fp_proxy ≤ 0).
Mean bust fp_proxy at stack=3: -0.83

**Reality check:** stack=3 does NOT eliminate bust risk for hitters either. Daily hitter variance is intrinsic — even three converging positive signals can produce 0-fer days. boom_stack is a probability shift.

## 6a. Weekly (rolling 7-game) aggregate by boom_stack

Weekly aggregate fp_proxy (forward 7-game sum). boom_wk threshold = 14.0 (80th pct).

| boom_stack | n | mean wk7 fp_proxy | wk_boom% | wk_bust% (≤0) |
|---|---|---|---|---|
| 0 | 159,131 | 8.15 | 19.5% | 11.2% |
| 1 | 73,878 | 8.43 | 20.7% | 10.3% |
| 2 | 7,897 | 8.86 | 23.5% | 9.6% |
| 3 | 739 | 9.76 | 27.5% | 7.8% |

**Weekly edge (stack=3 vs stack=0): +7.9 pp boom rate** (vs per-game edge of +6.7 pp)

## 6. Where in the projected range do hitters land by boom_stack?

Uses current xfp_rh3 (2026 snapshot) `xfp_rh3_per_game` (mean) and `xfp_rh3_p25`, `xfp_rh3_p75` as the predicted range for each batter, joined to that batter's 2025 per-game outcomes. Tests whether stack shifts the whole distribution vs only the right tail.

Sample: 2025 starter-games joined to rh3 = 23,516 rows

| boom_stack | n | %above p75 | %above p50 | %below p25 |
|---|---|---|---|---|
| 0 | 15,344 | 57.5% | 55.0% | 42.5% |
| 1 | 7,311 | 59.5% | 56.6% | 40.5% |
| 2 | 791 | 61.4% | 58.2% | 38.6% |
| 3 | 70 | 50.0% | 42.9% | 50.0% |

Interpretation: if stack shifts the WHOLE distribution, %above p50 should rise AND %below p25 should fall. If it only shifts the right tail, %above p75 rises but %below p25 stays flat.

## 7. Hitter vs SP comparison

Loaded SP reference: stack=0 → 13.2% boom (≥20 FP), stack=3 → 22.6% boom, edge +9.4 pp.
Hitter: stack=0 → 23.9% boom, stack=3 → 30.6% boom, edge +6.7 pp.

**Signal-strength verdict: WEAKER but real**

## 8. Final verdict

- Hitter stack=3 vs stack=0 edge: **+6.7 pp boom rate**
- Year-by-year stability range (stack 0 vs 2+): **+2.3 pp to +5.3 pp**
- Strongest single component: **flag_recform_hot** (+3.7 pp)

**Ship decision: SHIP-CAUTIOUS as ADVISORY TAG (smaller than SP; do not let it drive rh3 ranking)**

Notes:
- fp_proxy excludes R, RBI, SB. The SP feedback "boom_stack" is a clean fit because SP scoring is K- and IP-dominated (which statcast captures fully). For hitters the fp_proxy captures TB+BB+HBP-K (the largest single subset, ~49% of full FP and r=0.98 in season aggregates).
- Hitters play near-daily — daily-game boom_stack is high-frequency but low per-game-edge by construction (high variance numerator). A weekly aggregate version (sum 6-7 games) would likely show a larger and more usable edge.
- Component 3 (opp_soft) for hitters is INVERTED vs SPs: weak opposing SP (high xwoba-allowed-to-date) = soft opp. Min 60 PA SP-sample to flag.