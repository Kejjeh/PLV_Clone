# Historical Panel Coverage Report

Years: 2015-2025 (2020 retained, tagged covid_short=True)
Filters: hitter PA >= 100, pitcher IP >= 30

## Per-year row counts (after exposure filter)

| year | H | SP | RP | total |
|------|---|----|----|-------|
| 2015 | 445 | 209 | 226 | 880 |
| 2016 | 438 | 201 | 236 | 875 |
| 2017 | 435 | 205 | 257 | 897 |
| 2018 | 448 | 188 | 280 | 916 |
| 2019 | 452 | 189 | 268 | 909 |
| 2020 | 311 | 138 | 20 | 469 |
| 2021 | 463 | 201 | 271 | 935 |
| 2022 | 469 | 203 | 267 | 939 |
| 2023 | 462 | 207 | 269 | 938 |
| 2024 | 455 | 208 | 266 | 929 |
| 2025 | 461 | 212 | 263 | 936 |

## Per-year median season FP totals (sanity check)

| year | H median FP | SP median FP/start | RP median FP/g |
|------|-------------|--------------------|--------------:|
| 2015 | 1.67 | 11.09 | 2.14 |
| 2016 | 1.73 | 10.60 | 2.10 |
| 2017 | 1.77 | 10.04 | 2.85 |
| 2018 | 1.63 | 10.75 | 2.97 |
| 2019 | 1.76 | 10.43 | 2.88 |
| 2020 | 1.77 | 11.04 | 4.64 |
| 2021 | 1.66 | 10.42 | 2.96 |
| 2022 | 1.52 | 10.68 | 3.07 |
| 2023 | 1.66 | 10.50 | 3.12 |
| 2024 | 1.62 | 10.39 | 3.05 |
| 2025 | 1.62 | 10.82 | 3.10 |

## Predictor missingness (master panel)

| predictor | missing % |
|-----------|-----------|
| arche_career_pct | 15.4% |
| arche_career_pct_prior | 42.2% |
| arche_overall | 15.4% |
| arche_overall_prior | 42.2% |
| arche_traj | 15.4% |
| arche_traj_prior | 42.2% |
| prior_year_fp_per_g_rp | 79.0% |
| prior_year_fp_per_game | 58.7% |
| prior_year_fp_per_pa | 58.7% |
| prior_year_fp_per_start | 84.3% |
| prior_year_g_rp | 79.0% |
| prior_year_gs | 84.3% |
| prior_year_pa | 58.7% |

## Rookie handling

Rows with no prior-year FP anchor (rookies / gap-year returns): **2124** (22.1% of panel).

Suggested handling for the weight-fitter: **exclude from training** (anchor coefficient is undefined). Hold them out as a separate evaluation set where archetype + age + career_pct carry all the explanatory weight — those are exactly the cases where the archetype/historical-comp lens is load-bearing rather than a tag layer on top of a strong prior-year anchor.

## SV/HLD coverage
RP rows with sv_hld_missing=True (2015-2016, derived from statcast events): 462 / 2623. Recommend down-weighting these in the RP weight fit, or restricting RP training to 2017+ only.

## COVID-2020 handling
2020 rows retained (469 total) but tagged `covid_short=True`. Recommend either excluding 2020 from training or down-weighting season-totals by 162/60 ratio.

## Effective N estimates for weight regression
- Hitter weight regression: ~**3680** complete cases (excl. rookies + 2020)
- SP weight regression: ~**1394** complete cases (excl. rookies + 2020)
- RP weight regression: ~**1824** complete cases (excl. rookies + 2020 + sv_hld_missing)