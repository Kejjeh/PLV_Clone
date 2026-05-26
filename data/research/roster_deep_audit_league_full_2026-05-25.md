# League-wide roster deep audit (v4 — statistical + calibrated) — 2026-05-25

**Hitters:** 125 | **Slumpers analyzed:** 42 | **PEAK validated:** 17 | **MC sims:** 10,000/player (λ=0.20 recency decay) | **Historical comps:** 2015-2025 Statcast (age-matched ±3yr) | **SP career-form:** 76 SPs

> **CONSENSUS_DROP gate:** requires REGRESS + process DECLINING/MIXED + shrunk_gap < −0.030 + bounce_pct < 50%. IMPROVING process or anchor_in_CI always overrides to HOLD.

> **v4 upgrades:** recency-weighted MC + Bayesian (λ=0.20), age-matched comps (±3yr), Wilson CIs on survival curves, injury signal integration (ESPN DTD/IL).

> **Calibration:** ECE=0.0197 (WELL_CALIBRATED, threshold < 0.05), Brier=0.2221, validated on 15,778 out-of-sample snapshots (2023-2025 holdout). _Known limitation: adjacent rolling-150 windows share 149/150 events — precision is slightly overstated vs true i.i.d._

## Power ranking

| team_name                 |   rank |   n |   mean_pct |   n_peak |   n_high |   n_slump |   n_improving |   n_declining |   n_bounce |   n_drop |   mean_rh3 |   mean_bayes_p_avg |   sp_proj |
|:--------------------------|-------:|----:|-----------:|---------:|---------:|----------:|--------------:|--------------:|-----------:|---------:|-----------:|-------------------:|----------:|
| Late Night Bettsing       |      1 |  15 |      0.609 |        2 |        3 |         1 |             2 |             7 |          1 |        0 |      0.574 |           0.790447 |      98.8 |
| U Just Lost To Edwin Diaz |      2 |  16 |      0.543 |        3 |        0 |         1 |             3 |             7 |          1 |        0 |      0.555 |           0.601519 |     100.7 |
| 2015 Draft First Round    |      3 |  14 |      0.659 |        3 |        1 |         1 |             4 |             5 |          1 |        0 |      0.551 |           0.731436 |     112.5 |
| New York Ligers           |      4 |  13 |      0.534 |        0 |        3 |         3 |             1 |             3 |          3 |        0 |      0.549 |           0.736492 |     126.5 |
| Frendy's Fantastic Team   |      5 |  18 |      0.619 |        4 |        2 |         2 |             6 |             7 |          2 |        0 |      0.545 |           0.755544 |     109.2 |
| Team Solomon              |      6 |  13 |      0.335 |        1 |        0 |         5 |             3 |             6 |          5 |        0 |      0.52  |           0.748846 |     149.9 |
| Treasure Island Mashers   |      7 |  19 |      0.468 |        1 |        3 |         4 |             5 |             9 |          4 |        0 |      0.52  |           0.631279 |      90.9 |
| Boone's Bad Bullpen       |      8 |  17 |      0.582 |        3 |        1 |         2 |             7 |             5 |          2 |        0 |      0.511 |           0.668229 |      81.5 |


## Per-team position breakdown


### New York Ligers ← YOU

**C**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict         | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------------|:---------------|:--------------|
| Salvador Perez |         0.145 |          0.288 | SLUMPING      | REGRESS       | MIXED             |         0.2244 |           0.2353 |       107 |         106 |                 97 |       0.0244 | False          |               0.3207 |               0.525 |                  102.5 |            232 |             0.612069 | HOLDING        |        0.469 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE | NONE           |               |

**1B**

| player_name           |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                           |
|:----------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------------------------------|
| Vladimir Guerrero Jr. |         0.132 |          0.34  | SLUMPING      | REGRESS       | DECLINING         |         0.1922 |           0.2269 |     110.3 |       104.8 |               83   |       0.0052 | True           |               0.5024 |              0.8492 |                   77.9 |            596 |             0.651007 | BABIP_DRIVEN   |        0.585 | hold         |             |                     | HOLD_NOISE             | DTD            | DTD (Bruise, Right) — active DTD note |
| Pete Alonso           |         0.676 |          0.379 | ABOVE_MEDIAN  | REGRESS       | MIXED             |         0.2185 |           0.2519 |     110.1 |       108.6 |               96.6 |              | False          |               0.7565 |              0.9888 |                   86.3 |                |                      | UNKNOWN        |        0.575 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                       |
| Luis Arraez           |         0.309 |          0.32  | BELOW_MEDIAN  | STABLE        | MIXED             |         0.0382 |           0.0515 |      96.6 |        96.5 |               94.8 |      -0.0089 | True           |               0.2758 |              0.5042 |                   87.4 |            919 |             0.522307 | HOLDING        |        0.546 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                       |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note                                |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:-------------------------------------------|
| Max Muncy     |         0.863 |          0.416 | HIGH          | REGRESS       | DECLINING         |          0.215 |           0.2905 |     105.8 |       103.5 |                100 |              | False          |               0.7747 |              0.9798 |                   81.7 |                |                      | UNKNOWN        |        0.379 | drop         |             |                     | STABLE_HIGH     | DTD            | DTD (Bruise, Right) — slump window unknown |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Bo Bichette     |         0.541 |          0.342 | TYPICAL       | REGRESS       | MIXED             |         0.1576 |           0.1438 |     105.5 |       105.6 |              100   |              | False          |               0.6701 |              0.7411 |                   94.2 |                |                      | UNKNOWN        |        0.565 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Elly De La Cruz |         0.858 |          0.375 | HIGH          | STABLE        | IMPROVING         |         0.2788 |           0.2456 |     107.7 |       107.6 |               66.1 |              | False          |               0.6275 |              0.6217 |                   97   |                |                      | UNKNOWN        |        0.54  | hold         |             |                     | STABLE_HIGH            | NONE           |               |
| Trea Turner     |         0.165 |          0.306 | SLUMPING      | REGRESS       | STABLE            |         0.2181 |           0.2288 |     104.2 |       104.8 |               81.4 |       0.0071 | True           |               0.3262 |              0.4157 |                   85.5 |            370 |             0.608108 | MIXED          |        0.511 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**OF**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-------------------------------------------|
| Aaron Judge       |         0.391 |          0.418 | BELOW_MEDIAN  | REGRESS       | MIXED             |         0.3159 |           0.3217 |     111.9 |       110.7 |               64   |      -0.0181 | True           |               0.5523 |              0.9945 |                   61.1 |            412 |              0.48301 | DISCIPLINE_COLLAPSE |        0.7   | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |
| Corbin Carroll    |         0.781 |          0.375 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.2164 |           0.2193 |     107.4 |       106.8 |               90   |              | False          |               0.4291 |              0.9673 |                   77.3 |                |                      | UNKNOWN             |        0.636 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |
| Michael Harris II |         0.774 |          0.376 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.199  |           0.2143 |     108.6 |       110.2 |               59.8 |              | False          |               0.6237 |              0.5389 |                  103.4 |                |                      | UNKNOWN             |        0.624 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |
| Jordan Walker     |         0.818 |          0.354 | HIGH          | IMPROVING     | DECLINING         |         0.3268 |           0.3109 |     110   |       109.5 |               51.8 |              | False          |               1      |              0.824  |                  143.8 |                |                      | UNKNOWN             |        0.523 | hold         |             |                     | STABLE_HIGH            | NONE           |                                            |
| Wyatt Langford    |         0.483 |          0.332 | TYPICAL       | REGRESS       | MIXED             |         0.2331 |           0.2025 |     107   |       105.2 |               90.6 |              | False          |               0.6819 |              0.6242 |                   98.6 |                |                      | UNKNOWN             |        0.489 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Strain, Right) — slump window unknown |

**SP**

| player_name     |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:----------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Tyler Glasnow   | 14.351 |    -15.086 |          |             |              | False       |             |                |
| Hunter Greene   | 12.27  |      0     |          |             |              | False       |             |                |
| Jose Soriano    | 12.249 |     -5.145 |          |             |              | False       |             |                |
| Freddy Peralta  | 11.772 |     -1.52  |          |             |              | False       |             |                |
| Max Fried       | 11.542 |     -9.767 |          |             |              | False       |             |                |
| Carlos Rodon    | 11.394 |      0     |          |             |              | False       |             |                |
| Logan Henderson | 11.036 |      3.105 |          |             |              | False       |             |                |
| Kyle Bradish    | 10.696 |      4.485 |          |             |              | False       |             |                |
| Framber Valdez  | 10.606 |     -7.85  |          |             |              | False       |             |                |
| Parker Messick  | 10.376 |     -3.16  |          |             |              | False       |             |                |
| Will Warren     | 10.253 |     -5.44  |          |             |              | False       |             |                |

**RP**

| player_name     |   proj |
|:----------------|-------:|
| Pete Fairbanks  |  197.8 |
| Jhoan Duran     |  190.7 |
| Ryan Helsley    |  190.5 |
| Tanner Scott    |  140.7 |
| Daniel Palencia |  132   |


### 2015 Draft First Round

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Will Smith    |         0.526 |          0.359 | TYPICAL       | REGRESS       | DECLINING         |         0.1878 |           0.1707 |     105.6 |       103.1 |               95.4 |              | False          |               0.3158 |              0.9545 |                   85.7 |                |                      | UNKNOWN        |        0.541 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Ketel Marte     |         0.77  |          0.378 | ABOVE_MEDIAN  | REGRESS       | IMPROVING         |         0.1844 |           0.1429 |     107.4 |       106.5 |               86.8 |              | False          |                0.371 |              0.8966 |                   74.3 |                |                      | UNKNOWN        |        0.62  | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Brandon Lowe    |         0.968 |          0.404 | PEAK          | STABLE        | STABLE            |         0.2896 |           0.3471 |     106.4 |       108.5 |               54.1 |              | False          |                0.762 |              0.9725 |                   98.4 |            408 |             0.188725 | UNKNOWN        |        0.555 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Ildemaro Vargas |         0.717 |          0.301 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.1713 |           0.1009 |     104.9 |       100.1 |               54.1 |              | False          |                0.599 |              0.064  |                  105.9 |                |                      | UNKNOWN        |        0.544 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                 |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------------------------------------|
| Alex Bregman  |         0.473 |          0.345 | TYPICAL       | REGRESS       | DECLINING         |         0.1252 |           0.1379 |     102.8 |       101.5 |               98.5 |              | False          |               0.5042 |              0.7423 |                   83.1 |                |                      | UNKNOWN        |        0.564 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                             |
| Josh Jung     |         0.903 |          0.376 | PEAK          | STABLE        | IMPROVING         |         0.2188 |           0.1589 |     103.9 |       103.6 |               57.2 |              | False          |               0.9642 |              0.6633 |                  121.7 |            449 |             0.222717 | UNKNOWN        |        0.527 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | DTD            | DTD (Soreness, Left) — slump window unknown |

**SS**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Bobby Witt Jr. |         0.729 |          0.391 | ABOVE_MEDIAN  | BAD_LUCK      | MIXED             |         0.2097 |           0.2204 |     108.8 |       107.8 |               71.5 |              | False          |               0.4436 |              0.9902 |                   71.7 |                |                      | UNKNOWN        |        0.667 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Dansby Swanson |         0.496 |          0.328 | TYPICAL       | STABLE        | MIXED             |         0.2812 |           0.314  |     104.7 |       102.3 |               68.4 |              | False          |               0.5831 |              0.379  |                  108.2 |                |                      | UNKNOWN        |        0.458 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Brandon Nimmo |         0.961 |          0.396 | PEAK          | STABLE        | IMPROVING         |         0.2106 |           0.1705 |     106.2 |       104.6 |               86.6 |              | False          |               0.6825 |              0.9178 |                   97.1 |            329 |             0.197568 | UNKNOWN        |        0.578 | add          | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Daylen Lile   |         0.336 |          0.338 | BELOW_MEDIAN  | REGRESS       | MIXED             |         0.1471 |           0.1667 |     103.9 |       104.2 |              100   |      -0.02   | True           |               0.4908 |              0.9162 |                   83   |            101 |             0.524752 | BABIP_DRIVEN   |        0.559 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Sal Frelick   |         0.093 |          0.268 | SLUMPING      | BAD_LUCK      | STABLE            |         0.098  |           0.0976 |     100.3 |       101.6 |               81.5 |      -0.0066 | True           |               0.3546 |              0.0159 |                   99.4 |            313 |             0.686901 | BABIP_DRIVEN   |        0.511 | hold         |                |                     | HOLD_NOISE             | NONE           |               |
| Ian Happ      |         0.644 |          0.353 | ABOVE_MEDIAN  | BAD_LUCK      | DECLINING         |         0.2084 |           0.325  |     105.7 |       105.2 |               64.4 |              | False          |               0.3916 |              0.8799 |                   97.5 |                |                      | UNKNOWN        |        0.499 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Riley Greene  |         0.884 |          0.39  | HIGH          | STABLE        | IMPROVING         |         0.2628 |           0.2216 |     107.8 |       107.3 |               71.3 |              | False          |               0.2602 |              0.8707 |                  102.4 |                |                      | UNKNOWN        |        0.479 | hold         |                |                     | STABLE_HIGH            | NONE           |               |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Kyle Schwarber |         0.725 |          0.393 | ABOVE_MEDIAN  | BAD_LUCK      | DECLINING         |         0.2979 |           0.3429 |     109.8 |       110.2 |               73.2 |              | False          |               0.5599 |              0.9772 |                   83.4 |                |                      | UNKNOWN        |        0.613 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name     |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:----------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Cam Schlittler  | 14.272 |     -0.58  |          |             |              | False       |             |                |
| Jacob deGrom    | 13.904 |     -3.005 |          |             |              | False       |             |                |
| Logan Gilbert   | 12.965 |      2.72  |          |             |              | False       |             |                |
| Spencer Strider | 12.179 |      0     |          |             |              | False       |             |                |
| Cole Ragans     | 12.105 |      0.171 |          |             |              | False       |             |                |
| Drew Rasmussen  | 10.692 |     -2.778 |          |             |              | False       |             |                |
| Bryce Elder     | 10.169 |      2.207 |          |             |              | False       |             |                |
| Foster Griffin  |  8.9   |     -4.155 |          |             |              | False       |             |                |
| Shane Baz       |  8.747 |      0.65  |          |             |              | False       |             |                |
| Nick Lodolo     |  8.574 |      0     |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Trevor Megill |  157.2 |
| Bryan Baker   |  155.8 |
| Jakob Junis   |  106.2 |
| Robert Garcia |   95.8 |


### Boone's Bad Bullpen

**C**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:-------------------------------------------|
| William Contreras |         0.781 |          0.357 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2113 |           0.1681 |     107.4 |       107.1 |               61   |              | False          |               0.7001 |              0.8766 |                   90.7 |                |                      | UNKNOWN        |        0.601 | add          |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |
| Ryan Jeffers      |         0.999 |          0.395 | PEAK          | IMPROVING     | IMPROVING         |         0.1836 |           0.1089 |     105.7 |       107.5 |               63.7 |              | False          |               0.5969 |              0.8091 |                  102.9 |            362 |             0.146409 | UNKNOWN        |        0.595 | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | DTD            | DTD (Surgery, Left) — slump window unknown |
| Dillon Dingler    |         0.583 |          0.372 | TYPICAL       | STABLE        | DECLINING         |         0.2149 |           0.2373 |     105.4 |       101.4 |               76   |              | False          |               0.3307 |              0.8841 |                  123.7 |                |                      | UNKNOWN        |        0.513 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |

**1B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-------------------------------------------|
| Freddie Freeman |         0.141 |          0.358 | SLUMPING      | STABLE        | IMPROVING         |         0.2516 |           0.1944 |     104.3 |       106.1 |               86   |      -0.0048 | True           |               0.5528 |              0.9697 |                   77   |            104 |             0.490385 | K_DRIVEN       |        0.612 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |                                            |
| Ryan O'Hearn    |         0.655 |          0.348 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.1931 |           0.1562 |     103.1 |       104.1 |               58.6 |              | False          |               0.5672 |              0.6039 |                   93.6 |                |                      | UNKNOWN        |        0.533 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Strain, Right) — slump window unknown |

**3B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict     | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:------------------|:---------------|:--------------|
| Junior Caminero |         0.895 |          0.393 | HIGH          | STABLE        | STABLE            |         0.2194 |           0.2126 |     109.5 |       111.1 |               92.8 |              | False          |               0.4284 |              0.9785 |                   82.4 |                |                      | UNKNOWN        |        0.661 | add          |             |                     | STABLE_HIGH       | NONE           |               |
| Kazuma Okamoto  |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.3566 |           |       106.6 |              nan   |              | False          |               0.7701 |              1      |                  110.3 |                |                      | UNKNOWN        |        0.455 | hold         |             |                     | INSUFFICIENT_DATA | NONE           |               |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Gunnar Henderson |         0.021 |          0.285 | SLUMPING      | REGRESS       | DECLINING         |         0.2172 |           0.2197 |     106.8 |       106.2 |              100   |       0.0151 | True           |               0.3946 |              0.5572 |                   86.4 |            292 |             0.780822 | DISCIPLINE_COLLAPSE |        0.538 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Zach Neto        |         0.486 |          0.33  | TYPICAL       | REGRESS       | DECLINING         |         0.2667 |           0.2639 |     105.7 |       104.7 |               97.6 |              | False          |               0.2745 |              0.7038 |                   99.1 |                |                      | UNKNOWN             |        0.492 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Konnor Griffin   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.3789 |           |       108.7 |              nan   |              | False          |               0.1235 |              0.7145 |                  110.3 |                |                      | UNKNOWN             |        0.413 | drop         |             |                     | INSUFFICIENT_DATA      | NONE           |               |

**OF**

| player_name         |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Angel Martinez      |         0.969 |          0.32  | PEAK          | STABLE        | IMPROVING         |         0.1719 |           0.1389 |     102.2 |       104.9 |               55.2 |              | False          |               0.987  |              0.0108 |                  134.7 |             86 |             0.104651 | UNKNOWN        |        0.51  | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Tyler Soderstrom    |         0.316 |          0.326 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.2042 |           0.2523 |     107.2 |       106.1 |               98.4 |      -0.0151 | True           |               0.6802 |              0.6116 |                  103.7 |            328 |             0.536585 | BABIP_DRIVEN   |        0.508 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Mauricio Dubon      |         0.678 |          0.299 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.1331 |           0.14   |      99.8 |        98.6 |               70.6 |              | False          |               0.61   |              0.0427 |                  105.2 |                |                      | UNKNOWN        |        0.476 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Pete Crow-Armstrong |         0.765 |          0.337 | ABOVE_MEDIAN  | REGRESS       | MIXED             |         0.2465 |           0.2667 |     105.2 |       107.5 |               98.7 |              | False          |               0.397  |              0.589  |                   94.3 |                |                      | UNKNOWN        |        0.475 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Bryan Reynolds      |         0.323 |          0.338 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.255  |           0.2128 |     106.3 |       106.2 |               79.7 |       0.0006 | True           |               0.5165 |              0.9135 |                  107.6 |            758 |             0.530343 | BABIP_DRIVEN   |        0.471 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Steven Kwan         |         0.208 |          0.296 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.0749 |           0.0938 |      98   |        93.1 |              100   |       0.0042 | True           |               0.6151 |              0.3934 |                   90.7 |            692 |             0.562139 | HOLDING        |        0.465 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jac Caglianone      |         0.903 |          0.34  | PEAK          | STABLE        | IMPROVING         |         0.2432 |           0.3254 |     109.4 |       111   |              100   |              | False          |               0.5275 |              0.7015 |                  160.7 |             15 |             0        | UNKNOWN        |        0.37  | drop         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**SP**

| player_name   |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:--------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Paul Skenes   | 14.88  |      4.267 |          |             |              | False       |             |                |
| Gerrit Cole   | 13.11  |      0     |          |             |              | False       |             |                |
| Jesus Luzardo | 12.81  |     -0.815 |          |             |              | False       |             |                |
| Michael King  | 11.141 |      0.41  |          |             |              | False       |             |                |
| Tanner Bibee  | 10.825 |      2.439 |          |             |              | False       |             |                |
| Casey Mize    | 10.638 |      5.175 |          |             |              | False       |             |                |
| Nick Martinez |  8.106 |     -2.625 |          |             |              | False       |             |                |

**RP**

| player_name      |   proj |
|:-----------------|-------:|
| Raisel Iglesias  |  196   |
| David Bednar     |  172.1 |
| Garrett Whitlock |  137.7 |
| Andres Munoz     |  nan   |


### Frendy's Fantastic Team

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict       | injury_class   | injury_note                                |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:--------------------|:---------------|:-------------------------------------------|
| Drake Baldwin |         0.998 |          0.417 | PEAK          | STABLE        | MIXED             |         0.1592 |           0.1697 |     106.3 |       108.1 |               89.8 |              | False          |               0.2655 |              0.9995 |                   80.4 |             84 |            0.0595238 | UNKNOWN        |        0.679 | add          | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | DTD            | DTD (Strain, Right) — slump window unknown |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict     | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:------------------|:---------------|:--------------|
| Sal Stewart   |       nan     |        nan     | INSUFFICIENT  | STABLE        | DECLINING         |         0.2124 |           0.1988 |     107.4 |       102.6 |              nan   |              | False          |               0.9843 |              0.9859 |                   92   |                |                      | UNKNOWN        |        0.586 | hold         |                |                     | INSUFFICIENT_DATA | NONE           |               |
| Josh Naylor   |         0.924 |          0.368 | PEAK          | REGRESS       | DECLINING         |         0.1965 |           0.1667 |     104.3 |       104.7 |               98.7 |              | False          |               0.5925 |              0.8074 |                   77.7 |            778 |             0.210797 | UNKNOWN        |        0.571 | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | SELL_HIGH_WARNING | NONE           |               |

**2B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Nico Hoerner  |         0.821 |          0.336 | HIGH          | STABLE        | STABLE            |         0.092  |           0.1071 |     100.7 |       100.8 |               59.7 |              | False          |               0.596  |              0.5205 |                   86.4 |                |                      | UNKNOWN        |        0.577 | hold         |             |                     | STABLE_HIGH            | NONE           |               |
| Ozzie Albies  |         0.397 |          0.31  | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.1757 |           0.2358 |     100.8 |       102.6 |               55.4 |       0.0024 | True           |               0.6638 |              0.234  |                   91.1 |            777 |             0.509653 | HOLDING        |        0.52  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:--------------------|:---------------|:--------------|
| Miguel Vargas     |         0.994 |           0.43 | PEAK          | STABLE        | IMPROVING         |         0.1716 |           0.1667 |     103.1 |       102.9 |               53.8 |              | False          |               0.4703 |              0.9654 |                  110.3 |            222 |             0.121622 | UNKNOWN        |        0.58  | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |
| Munetaka Murakami |       nan     |         nan    | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.3879 |           |       107.6 |              nan   |              | False          |               0      |              1      |                  110.3 |                |                      | UNKNOWN        |        0.509 | hold         |                |                     | INSUFFICIENT_DATA   | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   | whiff_pct_25   |   whiff_pct_l21d | ev90_25   |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict     | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|:---------------|-----------------:|:----------|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:------------------|:---------------|:--------------|
| Kevin McGonigle |           nan |            nan | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1207 |           |       105.1 |                nan |              | False          |               0.0863 |                   1 |                  110.3 |                |                      | UNKNOWN        |         0.53 | hold         |             |                     | INSUFFICIENT_DATA | NONE           |               |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Cody Bellinger  |         0.938 |          0.421 | PEAK          | STABLE        | MIXED             |         0.1489 |           0.1368 |     102.7 |       100.8 |               56.7 |              | False          |               0.7603 |              0.9756 |                   78.3 |            570 |             0.205263 | UNKNOWN        |        0.645 | add          | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Julio Rodriguez |         0.802 |          0.369 | HIGH          | REGRESS       | IMPROVING         |         0.2549 |           0.2344 |     108.8 |       109.8 |               92.1 |              | False          |               0.5815 |              0.8603 |                   91.7 |                |                      | UNKNOWN        |        0.587 | add          |             |                     | STABLE_HIGH            | NONE           |               |
| Jackson Chourio |         0.486 |          0.31  | TYPICAL       | STABLE        | IMPROVING         |         0.2257 |           0.2    |     105.9 |       106.3 |              nan   |              | False          |               0.9678 |              0.4463 |                   88.2 |                |                      | UNKNOWN        |        0.533 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Taylor Ward     |         0.71  |          0.362 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.205  |           0.1442 |     105.1 |       103.3 |               69.7 |              | False          |               0.4517 |              0.5486 |                  100.7 |                |                      | UNKNOWN        |        0.491 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jo Adell        |         0.734 |          0.343 | ABOVE_MEDIAN  | REGRESS       | IMPROVING         |         0.2528 |           0.2183 |     109   |       108.3 |               80.6 |              | False          |               0.59   |              0.7419 |                  104   |                |                      | UNKNOWN        |        0.452 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Cam Smith       |         0.573 |          0.334 | TYPICAL       | STABLE        | DECLINING         |         0.252  |           0.3485 |     105.7 |       102.5 |              100   |              | False          |               0      |              0.4509 |                  138   |                |                      | UNKNOWN        |        0.397 | drop         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**UTIL/DH**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Shohei Ohtani    |         0.448 |          0.391 | TYPICAL       | REGRESS       | DECLINING         |         0.3024 |           0.2117 |     110.1 |       104.1 |               88.1 |              | False          |               0.7709 |              0.9926 |                   63.4 |                |                      | UNKNOWN             |        0.658 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Ivan Herrera     |         0.382 |          0.357 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.2076 |           0.1835 |     107.7 |       107.2 |               91.8 |      -0.0029 | True           |               0.8062 |              0.9052 |                   89   |            287 |             0.463415 | MIXED               |        0.551 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| George Springer  |         0.017 |          0.301 | SLUMPING      | REGRESS       | DECLINING         |         0.2308 |           0.2321 |     107.2 |       100.8 |               95.7 |       0.004  | True           |               0.5421 |              0.4563 |                   86.3 |            103 |             0.68932  | DISCIPLINE_COLLAPSE |        0.492 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Christian Yelich |         0.065 |          0.307 | SLUMPING      | STABLE        | DECLINING         |         0.2496 |           0.3077 |     106.7 |       107.2 |               92.3 |      -0.0044 | True           |               0.4747 |              0.7094 |                   85.9 |            224 |             0.678571 | MIXED               |        0.462 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**SP**

| player_name      |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-----------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Hunter Brown     | 12.935 |      0     |          |             |              | False       |             |                |
| Joe Ryan         | 12.627 |      5.473 |          |             |              | False       |             |                |
| Chase Burns      | 12.391 |      3.285 |          |             |              | False       |             |                |
| Payton Tolle     | 11.739 |      0.108 |          |             |              | False       |             |                |
| Brandon Woodruff | 11.403 |      0     |          |             |              | False       |             |                |
| Michael Wacha    | 10.93  |      1.565 |          |             |              | False       |             |                |
| Kris Bubic       | 10.577 |     -1.089 |          |             |              | False       |             |                |
| Emerson Hancock  |  9.383 |      0.88  |          |             |              | False       |             |                |
| Connelly Early   |  8.941 |     -0.03  |          |             |              | False       |             |                |
| Andrew Painter   |  8.271 |     -0.1   |          |             |              | False       |             |                |

**RP**

| player_name    |   proj |
|:---------------|-------:|
| Erik Sabrowski |  126.1 |


### Late Night Bettsing

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Ben Rice          |         0.528 |          0.388 | TYPICAL       | STABLE        | DECLINING         |         0.1905 |           0.1983 |     107.7 |       105.9 |               87.5 |              | False          |               0.5753 |              0.9756 |                   92   |                |                      | UNKNOWN        |        0.62  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jonathan Aranda   |         0.294 |          0.35  | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.218  |           0.1395 |     106.9 |       102.4 |               96.6 |      -0.0072 | True           |               0.2843 |              0.972  |                   98.7 |            269 |             0.509294 | BABIP_DRIVEN   |        0.524 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Willson Contreras |         0.843 |          0.39  | HIGH          | STABLE        | MIXED             |         0.2476 |           0.2541 |     108.2 |       109.1 |               72.6 |              | False          |               0.5233 |              0.9482 |                   97.8 |                |                      | UNKNOWN        |        0.514 | hold         |             |                     | STABLE_HIGH            | NONE           |               |

**2B**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                               |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:------------------------------------------|
| Gleyber Torres   |         0.504 |          0.338 | TYPICAL       | STABLE        | DECLINING         |         0.1628 |           0.2118 |     104.6 |        97.7 |               73.4 |              | False          |               0.4897 |              0.8466 |                   98.4 |                |                      | UNKNOWN        |        0.462 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Strain, Left) — slump window unknown |
| Jackson Holliday |         0.489 |          0.312 | TYPICAL       | STABLE        | INSUFFICIENT      |         0.2075 |           0.4667 |     103.7 |        96.9 |              nan   |              | False          |               0.0431 |              0.2666 |                  332.7 |                |                      | UNKNOWN        |      nan     | nan          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                           |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Jose Ramirez  |         0.819 |          0.381 | HIGH          | BAD_LUCK      | DECLINING         |         0.1275 |           0.1593 |     104.2 |       103.3 |               90.2 |              | False          |               0.5342 |              0.9151 |                   67.5 |                |                      | UNKNOWN        |        0.669 | add          |             |                     | STABLE_HIGH     | NONE           |               |

**SS**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Mookie Betts   |         0.537 |          0.365 | TYPICAL       | STABLE        | IMPROVING         |         0.1313 |           0.1071 |     101.6 |       102.7 |              nan   |              | False          |               0.7059 |              0.9438 |                   73.4 |                |                      | UNKNOWN        |        0.629 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| CJ Abrams      |         0.852 |          0.355 | HIGH          | STABLE        | MIXED             |         0.2123 |           0.2194 |     104.1 |       104.3 |               57.6 |              | False          |               0.5971 |              0.5658 |                   93.7 |                |                      | UNKNOWN        |        0.557 | hold         |             |                     | STABLE_HIGH            | NONE           |               |
| Brayan Rocchio |         0.962 |          0.319 | PEAK          | NOISE         | STABLE            |         0.2157 |           0.2124 |     102.3 |       102   |               71.1 |              | False          |               0.2629 |              0.1145 |                  132.3 |            203 |             0.133005 | UNKNOWN        |        0.457 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Alec Burleson   |         0.923 |          0.388 | PEAK          | STABLE        | MIXED             |         0.1486 |           0.1765 |     106.1 |       106.4 |               66.6 |              | False          |               0.67   |              0.9563 |                   92.2 |            542 |             0.188192 | UNKNOWN             |        0.579 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Kyle Tucker     |         0.29  |          0.35  | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.1729 |           0.1979 |     103.9 |       102   |              100   |       0.0066 | True           |               0.4763 |              0.978  |                   69.9 |            855 |             0.51462  | K_DRIVEN            |        0.568 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Andy Pages      |         0.618 |          0.331 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.1915 |           0.2067 |     104.4 |       102.2 |               81.2 |              | False          |               0.7032 |              0.6588 |                  101.6 |                |                      | UNKNOWN             |        0.56  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jackson Merrill |         0.006 |          0.297 | SLUMPING      | REGRESS       | MIXED             |         0.2238 |           0.232  |     105.3 |       102.3 |              100   |      -0.0163 | True           |               0.9741 |              0.7865 |                   89.1 |            108 |             0.796296 | DISCIPLINE_COLLAPSE |        0.521 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-------------------------------------------|
| Yordan Alvarez |         0.704 |          0.447 | ABOVE_MEDIAN  | NOISE         | DECLINING         |         0.1989 |           0.1513 |     110.3 |       107.9 |               52.9 |              | False          |               0.5953 |              0.9986 |                   73   |                |                      | UNKNOWN        |        0.735 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Spasms, Right) — slump window unknown |
| Yandy Diaz     |         0.768 |          0.372 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.1509 |           0.086  |     109.2 |       108.4 |               64.2 |              | False          |               0.5778 |              0.9303 |                   86.6 |                |                      | UNKNOWN        |        0.637 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |

**SP**

| player_name   |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:--------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Dylan Cease   | 14.129 |      2.37  |          |             |              | False       |             |                |
| Bryan Woo     | 13.33  |      8.35  |          |             |              | False       |             |                |
| Justin Steele | 11.34  |      0     |          |             |              | False       |             |                |
| Joe Musgrove  | 10.8   |      0     |          |             |              | False       |             |                |
| Luis Castillo | 10.677 |      3.467 |          |             |              | False       |             |                |
| Ryan Weathers | 10.173 |      1.689 |          |             |              | False       |             |                |
| Clay Holmes   |  9.802 |     -1.533 |          |             |              | False       |             |                |
| Mitch Keller  |  9.475 |     -3.41  |          |             |              | False       |             |                |
| Robbie Ray    |  9.075 |    -10.233 |          |             |              | False       |             |                |

**RP**

| player_name      |   proj |
|:-----------------|-------:|
| Cade Smith       |  226.2 |
| Aroldis Chapman  |  193.4 |
| Devin Williams   |  161.9 |
| Paul Sewald      |  151.1 |
| Braxton Ashcraft |  nan   |


### Team Solomon

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note                           |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------------------------------|
| Cal Raleigh   |         0.198 |          0.315 | SLUMPING      | REGRESS       | DECLINING         |         0.2717 |           0.2701 |       107 |         105 |               95.4 |      -0.0132 | True           |               0.7663 |              0.4294 |                   87.1 |            615 |              0.56748 | DISCIPLINE_COLLAPSE |        0.458 | hold         |             |                     | HOLD_NOISE      | DTD            | DTD (Strain, Right) — active DTD note |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Matt Olson    |         0.749 |          0.394 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2336 |           0.1576 |     108.4 |       109   |               55.8 |              | False          |               0.2295 |              0.9509 |                   85.6 |                |                      | UNKNOWN        |        0.636 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Bryce Harper  |         0.587 |          0.399 | TYPICAL       | STABLE        | MIXED             |         0.2764 |           0.2667 |     107.2 |       108.2 |               77.4 |              | False          |               0.7758 |              0.9984 |                   83.1 |                |                      | UNKNOWN        |        0.607 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                          |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-------------------------------------|
| Jose Altuve       |         0.071 |          0.282 | SLUMPING      | BAD_LUCK      | MIXED             |         0.1673 |           0.2547 |     102.4 |       102.4 |               97.1 |      -0.001  | True           |               0.4695 |              0.4306 |                   87.5 |            153 |             0.633987 | MIXED               |        0.526 | hold         |             |                     | HOLD_NOISE             | DTD            | DTD (Strain, Left) — active DTD note |
| Jazz Chisholm Jr. |         0.26  |          0.301 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.2949 |           0.2544 |     105.4 |       100.3 |              100   |       0.0057 | True           |               0.2267 |              0.2353 |                   93.7 |            643 |             0.572317 | DISCIPLINE_COLLAPSE |        0.425 | drop         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                      |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict         | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------------|:---------------|:--------------|
| Manny Machado |         0.07  |          0.302 | SLUMPING      | REGRESS       | IMPROVING         |         0.2358 |           0.1987 |     107.7 |       107.8 |               92.4 |       0.0062 | True           |               0.5353 |              0.5965 |                   87.2 |            138 |             0.637681 | DISCIPLINE_COLLAPSE |        0.512 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE | NONE           |               |
| Austin Riley  |         0.151 |          0.318 | SLUMPING      | STABLE        | DECLINING         |         0.2629 |           0.2481 |     109.2 |       104.4 |               93.2 |      -0.0008 | True           |               0.5193 |              0.8956 |                  102.3 |            819 |             0.603175 | K_DRIVEN            |        0.458 | hold         |             |                     | HOLD_NOISE            | NONE           |               |

**SS**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict     | injury_class   | injury_note                                         |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:------------------|:---------------|:----------------------------------------------------|
| Corey Seager  |         0.047 |          0.317 | SLUMPING      | REGRESS       | DECLINING         |         0.2437 |           0.2899 |       108 |       106.5 |                100 |      -0.0153 | True           |               0.6804 |              0.8854 |                   77.3 |            340 |             0.720588 | DISCIPLINE_COLLAPSE |        0.508 | hold         |             |                     | HOLD_NOISE        | DTD            | DTD (Inflammation, Not Specified) — active DTD note |
| JJ Wetherholt |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1696 |           |       102.8 |                nan |              | False          |               0.7546 |              1      |                  110.3 |                |                      | UNKNOWN             |        0.506 | hold         |             |                     | INSUFFICIENT_DATA | NONE           |                                                     |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:--------------------|:---------------|:--------------|
| James Wood    |         0.937 |          0.441 | PEAK          | STABLE        | MIXED             |         0.3015 |           0.3101 |       112 |       110.3 |               82.1 |              | False          |               0.2984 |              0.9862 |                  105.2 |            219 |             0.164384 | UNKNOWN        |        0.576 | add          | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Mike Trout    |         0.453 |          0.415 | TYPICAL       | MIXED         | IMPROVING         |         0.2568 |           0.1078 |     107.9 |       107.4 |               73.2 |              | False          |               0.5131 |              0.8691 |                  104.6 |                |                      | UNKNOWN        |        0.563 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Seiya Suzuki  |         0.276 |          0.333 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2086 |           0.234  |     107   |       105.1 |               71.1 |      -0.0194 | True           |               0.8089 |              0.5955 |                   93.8 |            419 |             0.529833 | MIXED          |        0.534 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Brent Rooker  |         0.224 |          0.319 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.2751 |           0.5    |     105.8 |       103.8 |              100   |      -0.002  | True           |               0.7346 |              0.8621 |                   91.6 |            440 |             0.6      | MIXED          |        0.452 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Tarik Skubal       | 15.066 |      0     |          |             |              | False       |             |                |
| Cristopher Sanchez | 14.864 |     10.702 |          |             |              | False       |             |                |
| Chris Sale         | 14.477 |      2.935 |          |             |              | False       |             |                |
| Zack Wheeler       | 13.3   |      0.953 |          |             |              | False       |             |                |
| Nathan Eovaldi     | 12.579 |     10.906 |          |             |              | False       |             |                |
| Nick Pivetta       | 12.542 |      0     |          |             |              | False       |             |                |
| Shota Imanaga      | 12.415 |     -2.485 |          |             |              | False       |             |                |
| George Kirby       | 11.569 |     -1.137 |          |             |              | False       |             |                |
| Shane McClanahan   | 11.431 |      3.2   |          |             |              | False       |             |                |
| Davis Martin       | 11.181 |      2.105 |          |             |              | False       |             |                |
| Sonny Gray         | 10.311 |      6.642 |          |             |              | False       |             |                |
| Logan Webb         | 10.203 |    -13.2   |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Kenley Jansen |  166.4 |
| Louis Varland |  164.1 |
| Riley O'Brien |  157.1 |
| Josh Hader    |  nan   |


### Treasure Island Mashers

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-------------------------------------------|
| Adley Rutschman |         0.573 |          0.349 | TYPICAL       | STABLE        | STABLE            |         0.1273 |           0.125  |     104.6 |       103.4 |               55.2 |              | False          |               0.7336 |              0.8703 |                  100.3 |                |                      | UNKNOWN        |        0.582 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                            |
| Agustin Ramirez |         0.009 |          0.275 | SLUMPING      | STABLE        | DECLINING         |         0.2229 |           0.2237 |     109.2 |       106.6 |               84.6 |       0.0022 | True           |               0.0542 |              0.4266 |                  100.7 |             74 |             0.837838 | HOLDING        |        0.429 | drop         |             |                     | HOLD_NOISE             | NONE           |                                            |
| Alejandro Kirk  |         0.807 |          0.375 | HIGH          | STABLE        | IMPROVING         |         0.1531 |           0.1    |     106.6 |       104.9 |              nan   |              | False          |               0.966  |              0.6888 |                  167.9 |                |                      | UNKNOWN        |      nan     | nan          |             |                     | STABLE_HIGH            | DTD            | DTD (Surgery, Left) — slump window unknown |

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Nick Kurtz        |         0.757 |          0.418 | ABOVE_MEDIAN  | BAD_LUCK      | IMPROVING         |          0.323 |           0.2789 |     108.5 |       111.8 |                100 |              | False          |               0.3371 |              0.9877 |                   75.2 |                |                      | UNKNOWN        |        0.631 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Spencer Torkelson |         0.225 |          0.306 | BELOW_MEDIAN  | BAD_LUCK      | DECLINING         |          0.23  |           0.281  |     104.5 |       102   |                 72 |      -0.0232 | False          |               0.7921 |              0.1399 |                  109.2 |            614 |              0.59772 | MIXED          |        0.454 | drop         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Brice Turang   |         0.971 |          0.407 | PEAK          | STABLE        | IMPROVING         |         0.1861 |           0.1504 |     104.2 |       104.3 |               57.4 |              | False          |               0.9195 |              0.6519 |                  102.3 |            447 |             0.161074 | UNKNOWN        |        0.589 | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Luke Keaschall |         0.323 |          0.282 | BELOW_MEDIAN  | REGRESS       | IMPROVING         |         0.1667 |           0.1373 |     100.8 |       101.9 |              nan   |       0.0049 | True           |               0.6979 |              0.1657 |                   80.2 |             41 |             0.536585 | MIXED          |        0.517 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Nolan Arenado |         0.848 |           0.37 | HIGH          | STABLE        | MIXED             |          0.162 |            0.178 |     101.6 |       101.7 |               92.8 |              | False          |               0.9464 |              0.7998 |                   96.6 |                |                      | UNKNOWN        |        0.511 | hold         |             |                     | STABLE_HIGH     | NONE           |               |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                               |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:------------------------------------------|
| Jacob Wilson     |         0.385 |          0.284 | BELOW_MEDIAN  | REGRESS       | MIXED             |         0.0775 |           0.0992 |      99.4 |        99.4 |              100   |      -0.0004 | True           |               0.6062 |              0.0779 |                   86.5 |            118 |             0.491525 | K_DRIVEN       |        0.556 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Dislocated, Left) — active DTD note  |
| Francisco Lindor |         0.815 |          0.388 | HIGH          | REGRESS       | MIXED             |         0.1803 |           0.2588 |     104.5 |       105.3 |               99.5 |              | False          |               0.6388 |              0.7343 |                   78.8 |                |                      | UNKNOWN        |        0.535 | hold         |             |                     | STABLE_HIGH            | DTD            | DTD (Strain, Left) — slump window unknown |
| Xander Bogaerts  |         0.555 |          0.332 | TYPICAL       | STABLE        | DECLINING         |         0.1938 |           0.1972 |     105.6 |       104.5 |               77.8 |              | False          |               0.612  |              0.3411 |                  101.6 |                |                      | UNKNOWN        |        0.502 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                           |

**OF**

| player_name        |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                               |
|:-------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:----------------------------------------------------------|
| Juan Soto          |         0.498 |          0.418 | TYPICAL       | REGRESS       | DECLINING         |         0.1958 |           0.2258 |     108   |       109.3 |               85.8 |              | False          |               0.5371 |              0.9954 |                   67.9 |                |                      | UNKNOWN             |        0.706 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Not Specified, Not Specified) — slump window unknown |
| Wilyer Abreu       |         0.787 |          0.354 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.2024 |           0.1846 |     107.5 |       101.5 |               50.5 |              | False          |               0.671  |              0.745  |                   96.8 |                |                      | UNKNOWN             |        0.549 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                           |
| Randy Arozarena    |         0.349 |          0.309 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2637 |           0.2887 |     106.7 |       104   |               74.2 |       0.013  | True           |               0.7739 |              0.5627 |                  103.8 |            811 |             0.487053 | HOLDING             |        0.489 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                           |
| Oneil Cruz         |         0.221 |          0.3   | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.3046 |           0.3383 |     113.8 |       111   |               79.6 |      -0.015  | True           |               0.5625 |              0.4096 |                  116.5 |            516 |             0.569767 | DISCIPLINE_COLLAPSE |        0.472 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                           |
| Fernando Tatis Jr. |         0.183 |          0.346 | SLUMPING      | REGRESS       | DECLINING         |         0.2462 |           0.2893 |     108.6 |       108.3 |              100   |      -0.0002 | True           |               0.603  |              0.9036 |                   85.7 |            647 |             0.581144 | MIXED               |        0.47  | hold         |             |                     | HOLD_NOISE             | NONE           |                                                           |
| Roman Anthony      |         0.103 |          0.355 | SLUMPING      | BAD_LUCK      | IMPROVING         |         0.2792 |           0.2299 |     107.4 |       105.8 |              nan   |       0.0082 | True           |               0.8863 |              0.9998 |                   98.6 |             26 |             0.884615 | MIXED               |        0.46  | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | DTD            | DTD (Sprain, Right) — active DTD note                     |
| Carson Benge       |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1667 |           |       105.2 |              nan   |              | False          |               1      |              0.7844 |                  110.3 |                |                      | UNKNOWN             |        0.455 | hold         |             |                     | INSUFFICIENT_DATA      | NONE           |                                                           |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Rafael Devers |         0.018 |          0.273 | SLUMPING      | REGRESS       | DECLINING         |         0.2819 |           0.2966 |     108.2 |         108 |                100 |        0.016 | True           |               0.1239 |              0.7098 |                   86.9 |            293 |             0.720137 | MIXED          |        0.454 | drop         |             |                     | HOLD_NOISE      | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Jacob Misiorowski  | 16.429 |      6.457 |          |             |              | False       |             |                |
| Yoshinobu Yamamoto | 13.739 |      2.944 |          |             |              | False       |             |                |
| Kyle Harrison      | 12.105 |      2.522 |          |             |              | False       |             |                |
| Nolan McLean       | 10.862 |     -6.625 |          |             |              | False       |             |                |
| Ranger Suarez      | 10.244 |     -0.689 |          |             |              | False       |             |                |
| Sandy Alcantara    |  9.934 |     -5.648 |          |             |              | False       |             |                |
| Seth Lugo          |  9.013 |     -4.96  |          |             |              | False       |             |                |
| Zac Gallen         |  8.566 |      0.817 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Edwin Diaz    |    nan |


### U Just Lost To Edwin Diaz

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Shea Langeliers |         0.984 |          0.423 | PEAK          | STABLE        | DECLINING         |         0.217  |           0.2426 |     107.8 |       108.3 |               63.1 |              | False          |               0.3545 |              0.9422 |                   98   |            396 |             0.151515 | UNKNOWN             |        0.625 | add          | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Liam Hicks      |         0.337 |          0.314 | BELOW_MEDIAN  | IMPROVING     | MIXED             |         0.1252 |           0.1389 |     100.6 |       101   |               64.8 |      -0.0114 | True           |               0.5631 |              0.4645 |                  106.2 |            138 |             0.449275 | DISCIPLINE_COLLAPSE |        0.582 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**1B**

| player_name        |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Vinnie Pasquantino |         0.387 |          0.326 | BELOW_MEDIAN  | REGRESS       | MIXED             |         0.1496 |           0.1387 |     105.7 |       105.6 |              100   |      -0.0065 | True           |               0.6451 |              0.675  |                   84.8 |            653 |             0.526799 | K_DRIVEN       |        0.556 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Christian Walker   |         0.208 |          0.318 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.2772 |           0.2358 |     107.5 |       107.6 |               56.7 |      -0.01   | True           |               0.5891 |              0.5622 |                   98.7 |            363 |             0.548209 | BABIP_DRIVEN   |        0.535 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jake Bauers        |         0.989 |          0.371 | PEAK          | STABLE        | DECLINING         |         0.2188 |           0.2136 |     107.4 |       106.1 |               59.7 |              | False          |               0.4948 |              0.7647 |                  124.8 |            329 |             0.161094 | UNKNOWN        |        0.49  | drop         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:--------------------|:---------------|:--------------|
| Xavier Edwards |         0.943 |          0.365 | PEAK          | STABLE        | IMPROVING         |         0.1043 |           0.1633 |     100.5 |       100.9 |               49.3 |              | False          |               0.8679 |               0.391 |                  100.6 |            292 |             0.164384 | UNKNOWN        |        0.584 | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Ernie Clement |         0.496 |          0.29  | TYPICAL       | STABLE        | DECLINING         |         0.1249 |           0.1359 |     100.3 |        98.8 |               71.4 |              | False          |               0.377  |              0.0293 |                   93   |                |                      | UNKNOWN        |        0.548 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Maikel Garcia |         0.078 |          0.294 | SLUMPING      | REGRESS       | DECLINING         |         0.1267 |           0.1038 |     105.5 |       102.8 |               59.1 |      -0.0135 | True           |               0.4513 |              0.4775 |                   97.1 |            431 |             0.719258 | BABIP_DRIVEN   |        0.52  | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Geraldo Perdomo |         0.774 |          0.342 | ABOVE_MEDIAN  | REGRESS       | STABLE            |         0.1036 |           0.0952 |     101.7 |       101.7 |               62.9 |              | False          |               0.9403 |              0.6326 |                   82.8 |                |                      | UNKNOWN        |        0.586 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Otto Lopez      |         0.418 |          0.321 | TYPICAL       | STABLE        | MIXED             |         0.1594 |           0.1802 |     104.6 |       103.4 |               81.1 |              | False          |               0.3134 |              0.5765 |                  101.2 |                |                      | UNKNOWN        |        0.529 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                    |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-----------------------------------------------|
| Byron Buxton     |         0.748 |          0.355 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2867 |           0.2395 |     108.6 |       107.1 |               74.4 |              | False          |               0.5413 |              0.9174 |                   84.7 |                |                      | UNKNOWN             |        0.601 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                |
| Chase DeLauter   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1717 |           |       105.2 |              nan   |              | False          |               0.6229 |              1      |                  110.3 |                |                      | UNKNOWN             |        0.588 | add          |             |                     | INSUFFICIENT_DATA      | NONE           |                                                |
| Ronald Acuna Jr. |         0.31  |          0.376 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.2662 |           0.1719 |     109.8 |       105   |               95.6 |      -0.0032 | True           |               0.7741 |              0.9825 |                   69.3 |            956 |             0.527197 | MIXED               |        0.566 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                |
| Mickey Moniak    |         0.511 |          0.314 | TYPICAL       | STABLE        | DECLINING         |         0.2467 |           0.1711 |     106   |       100.4 |               69.1 |              | False          |               0.0316 |              0.4174 |                  105.7 |                |                      | UNKNOWN             |        0.556 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Tendinitis, Right) — slump window unknown |
| Brandon Marsh    |         0.373 |          0.312 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.199  |           0.1826 |     103.7 |       105.2 |               61.9 |      -0.0174 | True           |               0.1987 |              0.5927 |                  112.8 |            687 |             0.521106 | DISCIPLINE_COLLAPSE |        0.509 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                |
| Jakob Marsee     |         0.586 |          0.301 | TYPICAL       | REGRESS       | DECLINING         |         0.1671 |           0.1932 |     104.6 |       100.4 |              nan   |              | False          |               0.9939 |              0.1988 |                   84.8 |                |                      | UNKNOWN             |        0.498 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                |

**SP**

| player_name     |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:----------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Gavin Williams  | 12.807 |     -1.734 |          |             |              | False       |             |                |
| Kevin Gausman   | 12.421 |     -1.116 |          |             |              | False       |             |                |
| Garrett Crochet | 11.787 |      0     |          |             |              | False       |             |                |
| Taj Bradley     | 11.606 |      2.662 |          |             |              | False       |             |                |
| Bryce Miller    | 11.288 |      0     |          |             |              | False       |             |                |
| Trey Yesavage   | 11.026 |     -0.12  |          |             |              | False       |             |                |
| Edward Cabrera  | 10.121 |     -4.46  |          |             |              | False       |             |                |
| Shane Bieber    | 10.05  |      0     |          |             |              | False       |             |                |
| MacKenzie Gore  |  9.604 |     -1.837 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Mason Miller  |  231.1 |
| Gregory Soto  |  145.9 |
| Rico Garcia   |  143.5 |
| Dylan Lee     |  140.7 |


## Slump detail cards (v3 — with MC + Bayesian + historical comps)


### Freddie Freeman (Boone's Bad Bullpen, 1B)

- **Career %ile:** 14.1%  | **Sust:** STABLE  | **Process:** IMPROVING

- **Bounce history (rh3):** 86% of 430 comparables bounced  | uplift: +0.125/PA

- **Bayesian shrunk gap:** -0.005  | anchor: 0.369  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.145 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.3→0.2  EV90 104.3→106.1

- **MC bounce (10k sims):** P(next 30PA > career median) = **55.3%**  | Expected xwOBA: 0.388  | 95% CI: [0.372, 0.401]

- **Bayesian talent:** posterior μ = 0.375  | 95% CI: [0.318, 0.432]  | P(talent > career median) = 33.2%  | P(talent > league avg .320) = **97.0%**  | Games to 200 FP: 77

- **Historical comps (2015-25, age-matched):** 104 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **49.0%**  | P(bounce 60PA) = 56.7%  | Median next-30PA xwOBA: 0.320  | 10-90 range: [0.250, 0.422]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% -5.7pt (improving); chase% -4.5pt (improving); z-contact% +5.4pt (improving); EV90 +1.8mph (power up); hard-hit% +11.8pt (up); bat speed +0.6mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Vladimir Guerrero Jr. (New York Ligers, 1B)

- **Career %ile:** 13.2%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Injury:** DTD (Bruise, Right) — active DTD note

- **Bounce history (rh3):** 83% of 499 comparables bounced  | uplift: +0.069/PA

- **Bayesian shrunk gap:** +0.005  | anchor: 0.343  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.040 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 110.3→104.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **50.2%**  | Expected xwOBA: 0.384  | 95% CI: [0.368, 0.398]

- **Bayesian talent:** posterior μ = 0.350  | 95% CI: [0.293, 0.407]  | P(talent > career median) = 12.3%  | P(talent > league avg .320) = **84.9%**  | Games to 200 FP: 78

- **Historical comps (2015-25, age-matched):** 596 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.1%**  | P(bounce 60PA) = 73.2%  | Median next-30PA xwOBA: 0.324  | 10-90 range: [0.246, 0.425]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% +3.5pt (worsening); chase% +11.3pt (worsening); z-contact% -9.9pt (worsening); EV90 -5.5mph (power flagging); hard-hit% -9.7pt (down); bat speed -1.0mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Gunnar Henderson (Boone's Bad Bullpen, SS)

- **Career %ile:** 2.1%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 45 comparables bounced  | uplift: +0.130/PA

- **Bayesian shrunk gap:** +0.015  | anchor: 0.271  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.245 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.3  EV90 106.8→106.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **39.5%**  | Expected xwOBA: 0.349  | 95% CI: [0.337, 0.358]

- **Bayesian talent:** posterior μ = 0.324  | 95% CI: [0.274, 0.373]  | P(talent > career median) = 16.1%  | P(talent > league avg .320) = **55.7%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 292 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **78.1%**  | P(bounce 60PA) = 80.5%  | Median next-30PA xwOBA: 0.318  | 10-90 range: [0.244, 0.417]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +0.2pt (worsening); chase% +6.6pt (worsening); z-contact% +0.8pt (improving); EV90 -0.6mph (power flagging); hard-hit% -7.4pt (down); bat speed -0.4mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Jose Altuve (Team Solomon, 2B)

- **Career %ile:** 7.1%  | **Sust:** BAD_LUCK  | **Process:** MIXED

- **Injury:** DTD (Strain, Left) — active DTD note

- **Bounce history (rh3):** 97% of 205 comparables bounced  | uplift: +0.113/PA

- **Bayesian shrunk gap:** -0.001  | anchor: 0.309  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.019 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.3  chase% 0.4→0.4  EV90 102.4→102.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **46.9%**  | Expected xwOBA: 0.329  | 95% CI: [0.317, 0.341]

- **Bayesian talent:** posterior μ = 0.315  | 95% CI: [0.262, 0.368]  | P(talent > career median) = 31.1%  | P(talent > league avg .320) = **43.1%**  | Games to 200 FP: 88

- **Historical comps (2015-25, age-matched):** 153 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.4%**  | P(bounce 60PA) = 70.6%  | Median next-30PA xwOBA: 0.325  | 10-90 range: [0.248, 0.442]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +8.7pt (worsening); chase% -0.6pt (improving); z-contact% -3.3pt (worsening); EV90 -0.0mph (power flagging); hard-hit% +4.1pt (up); bat speed +0.1mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Jackson Merrill (Late Night Bettsing, CF)

- **Career %ile:** 0.6%  | **Sust:** REGRESS  | **Process:** MIXED

- **Bounce history (rh3):** 100% of 13 comparables bounced  | uplift: +0.198/PA

- **Bayesian shrunk gap:** -0.016  | anchor: 0.327  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.068 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.4→0.3  EV90 105.3→102.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **97.4%**  | Expected xwOBA: 0.357  | 95% CI: [0.348, 0.370]

- **Bayesian talent:** posterior μ = 0.343  | 95% CI: [0.287, 0.399]  | P(talent > career median) = 30.8%  | P(talent > league avg .320) = **78.6%**  | Games to 200 FP: 89

- **Historical comps (2015-25, age-matched):** 108 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **79.6%**  | P(bounce 60PA) = 85.2%  | Median next-30PA xwOBA: 0.319  | 10-90 range: [0.238, 0.418]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +0.8pt (worsening); chase% -3.4pt (improving); z-contact% +2.3pt (improving); EV90 -3.0mph (power flagging); hard-hit% -0.8pt (down); bat speed +1.0mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Maikel Garcia (U Just Lost To Edwin Diaz, 3B)

- **Career %ile:** 7.8%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 59% of 281 comparables bounced  | uplift: +0.029/PA

- **Bayesian shrunk gap:** -0.013  | anchor: 0.315  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.076 (contact declining)

- **Process:** whiff% 0.1→0.1  chase% 0.2→0.2  EV90 105.5→102.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **45.1%**  | Expected xwOBA: 0.322  | 95% CI: [0.314, 0.328]

- **Bayesian talent:** posterior μ = 0.319  | 95% CI: [0.283, 0.355]  | P(talent > career median) = 42.8%  | P(talent > league avg .320) = **47.8%**  | Games to 200 FP: 97

- **Historical comps (2015-25, age-matched):** 431 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **71.9%**  | P(bounce 60PA) = 77.5%  | Median next-30PA xwOBA: 0.317  | 10-90 range: [0.238, 0.413]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% -2.3pt (improving); chase% +1.6pt (worsening); z-contact% +4.0pt (improving); EV90 -2.7mph (power flagging); hard-hit% -11.8pt (down); bat speed +0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Manny Machado (Team Solomon, 3B)

- **Career %ile:** 7.0%  | **Sust:** REGRESS  | **Process:** IMPROVING

- **Bounce history (rh3):** 92% of 329 comparables bounced  | uplift: +0.157/PA

- **Bayesian shrunk gap:** +0.006  | anchor: 0.299  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.195 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.3  EV90 107.7→107.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **53.5%**  | Expected xwOBA: 0.350  | 95% CI: [0.339, 0.361]

- **Bayesian talent:** posterior μ = 0.327  | 95% CI: [0.272, 0.382]  | P(talent > career median) = 20.2%  | P(talent > league avg .320) = **59.7%**  | Games to 200 FP: 87

- **Historical comps (2015-25, age-matched):** 138 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.8%**  | P(bounce 60PA) = 72.5%  | Median next-30PA xwOBA: 0.331  | 10-90 range: [0.251, 0.440]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -3.7pt (improving); chase% -2.9pt (improving); z-contact% +2.1pt (improving); EV90 +0.1mph (power up); hard-hit% -3.5pt (down); bat speed -1.7mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Sal Frelick (2015 Draft First Round, RF)

- **Career %ile:** 9.3%  | **Sust:** BAD_LUCK  | **Process:** STABLE

- **Bounce history (rh3):** 82% of 173 comparables bounced  | uplift: +0.046/PA

- **Bayesian shrunk gap:** -0.007  | anchor: 0.278  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.042 (contact declining)

- **Process:** whiff% 0.1→0.1  chase% 0.3→0.2  EV90 100.3→101.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **35.5%**  | Expected xwOBA: 0.291  | 95% CI: [0.286, 0.296]

- **Bayesian talent:** posterior μ = 0.286  | 95% CI: [0.256, 0.317]  | P(talent > career median) = 37.5%  | P(talent > league avg .320) = **1.6%**  | Games to 200 FP: 99

- **Historical comps (2015-25, age-matched):** 313 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.7%**  | P(bounce 60PA) = 75.4%  | Median next-30PA xwOBA: 0.311  | 10-90 range: [0.224, 0.412]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% -0.0pt (improving); chase% -5.1pt (improving); z-contact% +2.0pt (improving); EV90 +1.3mph (power up); hard-hit% +2.3pt (up); bat speed +1.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Trea Turner (New York Ligers, SS)

- **Career %ile:** 16.5%  | **Sust:** REGRESS  | **Process:** STABLE

- **Bounce history (rh3):** 81% of 167 comparables bounced  | uplift: +0.100/PA

- **Bayesian shrunk gap:** +0.007  | anchor: 0.285  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.101 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.3  EV90 104.2→104.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **32.6%**  | Expected xwOBA: 0.332  | 95% CI: [0.322, 0.344]

- **Bayesian talent:** posterior μ = 0.314  | 95% CI: [0.263, 0.366]  | P(talent > career median) = 24.8%  | P(talent > league avg .320) = **41.6%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 370 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **60.8%**  | P(bounce 60PA) = 65.4%  | Median next-30PA xwOBA: 0.343  | 10-90 range: [0.255, 0.442]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +1.1pt (worsening); chase% -0.8pt (improving); z-contact% +0.6pt (improving); EV90 +0.6mph (power up); hard-hit% +5.5pt (up); bat speed +0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Corey Seager (Team Solomon, SS)

- **Career %ile:** 4.7%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Injury:** DTD (Inflammation, Not Specified) — active DTD note

- **Bounce history (rh3):** 100% of 63 comparables bounced  | uplift: +0.171/PA

- **Bayesian shrunk gap:** -0.015  | anchor: 0.342  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.081 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.2→0.3  EV90 108.0→106.5

- **MC bounce (10k sims):** P(next 30PA > career median) = **68.0%**  | Expected xwOBA: 0.386  | 95% CI: [0.373, 0.398]

- **Bayesian talent:** posterior μ = 0.354  | 95% CI: [0.299, 0.409]  | P(talent > career median) = 13.0%  | P(talent > league avg .320) = **88.5%**  | Games to 200 FP: 77

- **Historical comps (2015-25, age-matched):** 340 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **72.1%**  | P(bounce 60PA) = 77.6%  | Median next-30PA xwOBA: 0.330  | 10-90 range: [0.247, 0.444]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +4.6pt (worsening); chase% +8.3pt (worsening); z-contact% -4.4pt (worsening); EV90 -1.5mph (power flagging); hard-hit% -8.6pt (down); bat speed -0.7mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### George Springer (Frendy's Fantastic Team, DH)

- **Career %ile:** 1.7%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 96% of 281 comparables bounced  | uplift: +0.179/PA

- **Bayesian shrunk gap:** +0.004  | anchor: 0.274  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.113 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 107.2→100.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **54.2%**  | Expected xwOBA: 0.359  | 95% CI: [0.349, 0.373]

- **Bayesian talent:** posterior μ = 0.317  | 95% CI: [0.258, 0.375]  | P(talent > career median) = 7.9%  | P(talent > league avg .320) = **45.6%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 103 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.9%**  | P(bounce 60PA) = 73.8%  | Median next-30PA xwOBA: 0.337  | 10-90 range: [0.247, 0.443]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +0.1pt (worsening); chase% +11.0pt (worsening); z-contact% +5.0pt (improving); EV90 -6.4mph (power flagging); hard-hit% -13.2pt (down); bat speed -2.1mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Fernando Tatis Jr. (Treasure Island Mashers, RF)

- **Career %ile:** 18.3%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 11 comparables bounced  | uplift: +0.185/PA

- **Bayesian shrunk gap:** -0.000  | anchor: 0.341  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.008 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.3  chase% 0.2→0.3  EV90 108.6→108.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **60.3%**  | Expected xwOBA: 0.376  | 95% CI: [0.366, 0.387]

- **Bayesian talent:** posterior μ = 0.355  | 95% CI: [0.302, 0.408]  | P(talent > career median) = 21.3%  | P(talent > league avg .320) = **90.4%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 647 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **58.1%**  | P(bounce 60PA) = 63.2%  | Median next-30PA xwOBA: 0.314  | 10-90 range: [0.232, 0.410]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +4.3pt (worsening); chase% +10.0pt (worsening); z-contact% +3.3pt (improving); EV90 -0.3mph (power flagging); hard-hit% -8.6pt (down); bat speed +1.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Salvador Perez (New York Ligers, C)

- **Career %ile:** 14.5%  | **Sust:** REGRESS  | **Process:** MIXED

- **Bounce history (rh3):** 97% of 201 comparables bounced  | uplift: +0.155/PA

- **Bayesian shrunk gap:** +0.024  | anchor: 0.261  | anchor_in_CI: No

- **xwOBACON gap:** +0.163 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.4→0.5  EV90 107.0→106.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **32.1%**  | Expected xwOBA: 0.343  | 95% CI: [0.329, 0.356]

- **Bayesian talent:** posterior μ = 0.322  | 95% CI: [0.263, 0.381]  | P(talent > career median) = 24.3%  | P(talent > league avg .320) = **52.5%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 232 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **61.2%**  | P(bounce 60PA) = 64.7%  | Median next-30PA xwOBA: 0.332  | 10-90 range: [0.252, 0.440]

- **Process notes:** whiff% +1.1pt (worsening); chase% +6.7pt (worsening); z-contact% +2.6pt (improving); EV90 -1.0mph (power flagging); hard-hit% +2.5pt (up); bat speed -1.2mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — 97% historical bounce rate; shrunk gap +0.024


### Christian Yelich (Frendy's Fantastic Team, DH)

- **Career %ile:** 6.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 92% of 487 comparables bounced  | uplift: +0.133/PA

- **Bayesian shrunk gap:** -0.004  | anchor: 0.293  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.015 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.3  chase% 0.3→0.3  EV90 106.7→107.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **47.5%**  | Expected xwOBA: 0.357  | 95% CI: [0.346, 0.373]

- **Bayesian talent:** posterior μ = 0.340  | 95% CI: [0.269, 0.411]  | P(talent > career median) = 32.3%  | P(talent > league avg .320) = **70.9%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 224 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **67.9%**  | P(bounce 60PA) = 71.9%  | Median next-30PA xwOBA: 0.337  | 10-90 range: [0.248, 0.438]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +5.8pt (worsening); chase% -0.2pt (improving); z-contact% -7.0pt (worsening); EV90 +0.5mph (power up); hard-hit% -15.5pt (down); bat speed +0.4mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Roman Anthony (Treasure Island Mashers, RF)

- **Career %ile:** 10.3%  | **Sust:** BAD_LUCK  | **Process:** IMPROVING

- **Injury:** DTD (Sprain, Right) — active DTD note

- **Bayesian shrunk gap:** +0.008  | anchor: 0.343  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.136 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.2→0.3  EV90 107.4→105.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **88.6%**  | Expected xwOBA: 0.372  | 95% CI: [0.367, 0.377]

- **Bayesian talent:** posterior μ = 0.374  | 95% CI: [0.345, 0.404]  | P(talent > career median) = 54.6%  | P(talent > league avg .320) = **100.0%**  | Games to 200 FP: 99

- **Historical comps (2015-25, age-matched):** 26 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **88.5%**  | P(bounce 60PA) = 100.0%  | Median next-30PA xwOBA: 0.324  | 10-90 range: [0.253, 0.384]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -4.9pt (improving); chase% +5.6pt (worsening); z-contact% +5.8pt (improving); EV90 -1.6mph (power flagging); hard-hit% +2.3pt (up); bat speed +1.5mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Cal Raleigh (Team Solomon, C)

- **Career %ile:** 19.8%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Injury:** DTD (Strain, Right) — active DTD note

- **Bounce history (rh3):** 95% of 108 comparables bounced  | uplift: +0.189/PA

- **Bayesian shrunk gap:** -0.013  | anchor: 0.311  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.051 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.4  EV90 107.0→105.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **76.6%**  | Expected xwOBA: 0.345  | 95% CI: [0.335, 0.355]

- **Bayesian talent:** posterior μ = 0.315  | 95% CI: [0.262, 0.369]  | P(talent > career median) = 13.8%  | P(talent > league avg .320) = **42.9%**  | Games to 200 FP: 87

- **Historical comps (2015-25, age-matched):** 615 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **56.7%**  | P(bounce 60PA) = 61.6%  | Median next-30PA xwOBA: 0.313  | 10-90 range: [0.233, 0.406]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -0.2pt (improving); chase% +11.2pt (worsening); z-contact% -7.1pt (worsening); EV90 -2.0mph (power flagging); hard-hit% -20.7pt (down); bat speed -0.4mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Austin Riley (Team Solomon, 3B)

- **Career %ile:** 15.1%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 93% of 73 comparables bounced  | uplift: +0.198/PA

- **Bayesian shrunk gap:** -0.001  | anchor: 0.326  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.089 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.3→0.3  EV90 109.2→104.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **51.9%**  | Expected xwOBA: 0.354  | 95% CI: [0.341, 0.368]

- **Bayesian talent:** posterior μ = 0.357  | 95% CI: [0.299, 0.414]  | P(talent > career median) = 53.4%  | P(talent > league avg .320) = **89.6%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 819 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **60.3%**  | P(bounce 60PA) = 64.2%  | Median next-30PA xwOBA: 0.316  | 10-90 range: [0.230, 0.418]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% -1.5pt (improving); chase% +4.6pt (worsening); z-contact% +5.8pt (improving); EV90 -4.8mph (power flagging); hard-hit% -8.0pt (down); bat speed -1.4mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Rafael Devers (Treasure Island Mashers, DH)

- **Career %ile:** 1.8%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 7 comparables bounced  | uplift: +0.468/PA

- **Bayesian shrunk gap:** +0.016  | anchor: 0.264  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.288 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 108.2→108.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **12.4%**  | Expected xwOBA: 0.360  | 95% CI: [0.346, 0.371]

- **Bayesian talent:** posterior μ = 0.337  | 95% CI: [0.278, 0.396]  | P(talent > career median) = 21.6%  | P(talent > league avg .320) = **71.0%**  | Games to 200 FP: 87

- **Historical comps (2015-25, age-matched):** 293 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **72.0%**  | P(bounce 60PA) = 79.9%  | Median next-30PA xwOBA: 0.331  | 10-90 range: [0.246, 0.450]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +1.5pt (worsening); chase% +7.2pt (worsening); z-contact% -1.8pt (worsening); EV90 -0.2mph (power flagging); hard-hit% -1.9pt (down); bat speed +0.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Agustin Ramirez (Treasure Island Mashers, C)

- **Career %ile:** 0.9%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 85% of 13 comparables bounced  | uplift: +0.036/PA

- **Bayesian shrunk gap:** +0.002  | anchor: 0.280  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.056 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.2  EV90 109.2→106.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **5.4%**  | Expected xwOBA: 0.324  | 95% CI: [0.316, 0.330]

- **Bayesian talent:** posterior μ = 0.316  | 95% CI: [0.270, 0.361]  | P(talent > career median) = 36.0%  | P(talent > league avg .320) = **42.7%**  | Games to 200 FP: 101

- **Historical comps (2015-25, age-matched):** 74 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **83.8%**  | P(bounce 60PA) = 82.4%  | Median next-30PA xwOBA: 0.303  | 10-90 range: [0.248, 0.411]

- **Process notes:** whiff% +0.1pt (worsening); chase% -11.4pt (improving); z-contact% -0.0pt (worsening); EV90 -2.6mph (power flagging); hard-hit% -9.7pt (down); bat speed +0.9mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


## PEAK player validator (v3 — with survival curves)


### Drake Baldwin (Frendy's Fantastic Team, C) — MIXED

- **Career %ile:** 99.8%  | **rh3:** 0.679  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.377  | P(true talent > .320) = **100.0%**  | P(true talent > career median) = 76.9%

- **Historical comps:** 84 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 6.0%  | Median next-30PA xwOBA: 0.263

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: xwOBAcon +0.110

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Cody Bellinger (Frendy's Fantastic Team, LF) — MIXED

- **Career %ile:** 93.8%  | **rh3:** 0.645  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.380  | P(true talent > .320) = **97.6%**  | P(true talent > career median) = 96.1%

- **Historical comps:** 570 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 20.5%  | Median next-30PA xwOBA: 0.339

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: chase% -6.3pt; xwOBAcon +0.046

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Shea Langeliers (U Just Lost To Edwin Diaz, C) — MIXED

- **Career %ile:** 98.4%  | **rh3:** 0.625  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.369  | P(true talent > .320) = **94.2%**  | P(true talent > career median) = 90.2%

- **Historical comps:** 396 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 15.2%  | Median next-30PA xwOBA: 0.312

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: bat_speed +1.6mph; xwOBAcon +0.094

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Ryan Jeffers (Boone's Bad Bullpen, C) — PROCESS_DRIVEN

- **Career %ile:** 99.9%  | **rh3:** 0.595  | **Sust:** IMPROVING

- **Bayesian talent:** posterior μ = 0.340  | P(true talent > .320) = **80.9%**  | P(true talent > career median) = 78.5%

- **Historical comps:** 362 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 14.6%  | Median next-30PA xwOBA: 0.310

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- bat_speed +1.1mph — EV90 +1.7mph — whiff% -4.9pt — z_contact% +5.6pt — xwOBAcon +0.050 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Brice Turang (Treasure Island Mashers, 2B) — PROCESS_DRIVEN

- **Career %ile:** 97.1%  | **rh3:** 0.589  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.331  | P(true talent > .320) = **65.2%**  | P(true talent > career median) = 63.4%

- **Historical comps:** 447 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 16.1%  | Median next-30PA xwOBA: 0.313

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- whiff% -2.1pt — chase% -3.3pt — xwOBAcon +0.052 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Xavier Edwards (U Just Lost To Edwin Diaz, 2B) — PROCESS_DRIVEN

- **Career %ile:** 94.3%  | **rh3:** 0.584  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.313  | P(true talent > .320) = **39.1%**  | P(true talent > career median) = 61.9%

- **Historical comps:** 292 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 16.4%  | Median next-30PA xwOBA: 0.305

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- bat_speed +2.3mph — EV90 +1.6mph — chase% -4.5pt — xwOBAcon +0.043 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Miguel Vargas (Frendy's Fantastic Team, 3B) — PROCESS_DRIVEN

- **Career %ile:** 99.4%  | **rh3:** 0.580  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.379  | P(true talent > .320) = **96.5%**  | P(true talent > career median) = 98.0%

- **Historical comps:** 222 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 12.2%  | Median next-30PA xwOBA: 0.297

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- bat_speed +3.4mph — whiff% -2.2pt — chase% -3.9pt — xwOBAcon +0.081 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Alec Burleson (Late Night Bettsing, LF) — MIXED

- **Career %ile:** 92.3%  | **rh3:** 0.579  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.363  | P(true talent > .320) = **95.6%**  | P(true talent > career median) = 76.8%

- **Historical comps:** 542 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 18.8%  | Median next-30PA xwOBA: 0.309

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: xwOBAcon +0.063

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Brandon Nimmo (2015 Draft First Round, LF) — PROCESS_DRIVEN

- **Career %ile:** 96.1%  | **rh3:** 0.578  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.354  | P(true talent > .320) = **91.8%**  | P(true talent > career median) = 72.9%

- **Historical comps:** 329 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 19.8%  | Median next-30PA xwOBA: 0.342

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- whiff% -4.1pt — z_contact% +3.7pt — xwOBAcon +0.059 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### James Wood (Team Solomon, LF) — MIXED

- **Career %ile:** 93.7%  | **rh3:** 0.576  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.391  | P(true talent > .320) = **98.6%**  | P(true talent > career median) = 72.1%

- **Historical comps:** 219 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 16.4%  | Median next-30PA xwOBA: 0.298

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: z_contact% +4.0pt; xwOBAcon +0.080

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Josh Naylor (Frendy's Fantastic Team, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 92.4%  | **rh3:** 0.571  | **Sust:** REGRESS

- **Bayesian talent:** posterior μ = 0.338  | P(true talent > .320) = **80.7%**  | P(true talent > career median) = 61.8%

- **Historical comps:** 778 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 21.1%  | Median next-30PA xwOBA: 0.319

- **Peak survival:** P(still PEAK at +30PA) = **89.2%** [89.0%, 89.5%]  | +60PA = 76.2% [75.9%, 76.5%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** SELL_HIGH_WARNING — PEAK form + process DECLINING + REGRESS (shrunk N/A)


### Brandon Lowe (2015 Draft First Round, 2B) — MIXED

- **Career %ile:** 96.8%  | **rh3:** 0.555  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.367  | P(true talent > .320) = **97.2%**  | P(true talent > career median) = 83.6%

- **Historical comps:** 408 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 18.9%  | Median next-30PA xwOBA: 0.314

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: z_contact% +3.8pt

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Josh Jung (2015 Draft First Round, 3B) — MIXED

- **Career %ile:** 90.3%  | **rh3:** 0.527  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.331  | P(true talent > .320) = **66.3%**  | P(true talent > career median) = 70.1%

- **Historical comps:** 449 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 22.3%  | Median next-30PA xwOBA: 0.307

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: whiff% -8.0pt; z_contact% +7.8pt

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Angel Martinez (Boone's Bad Bullpen, CF) — PROCESS_DRIVEN

- **Career %ile:** 96.9%  | **rh3:** 0.510  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.272  | P(true talent > .320) = **1.1%**  | P(true talent > career median) = 60.2%

- **Historical comps:** 86 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 10.5%  | Median next-30PA xwOBA: 0.279

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- bat_speed +1.2mph — EV90 +2.6mph — whiff% -5.3pt — z_contact% +5.8pt — xwOBAcon +0.065 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Jake Bauers (U Just Lost To Edwin Diaz, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 98.9%  | **rh3:** 0.490  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.341  | P(true talent > .320) = **76.5%**  | P(true talent > career median) = 77.2%

- **Historical comps:** 329 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 16.1%  | Median next-30PA xwOBA: 0.318

- **Peak survival:** P(still PEAK at +30PA) = **89.2%** [89.0%, 89.5%]  | +60PA = 76.2% [75.9%, 76.5%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Brayan Rocchio (Late Night Bettsing, SS) — MIXED

- **Career %ile:** 96.2%  | **rh3:** 0.457  | **Sust:** NOISE

- **Bayesian talent:** posterior μ = 0.299  | P(true talent > .320) = **11.5%**  | P(true talent > career median) = 70.2%

- **Historical comps:** 203 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 13.3%  | Median next-30PA xwOBA: 0.288

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: whiff% -2.2pt; z_contact% +2.7pt

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Jac Caglianone (Boone's Bad Bullpen, RF) — PROCESS_DRIVEN

- **Career %ile:** 90.3%  | **rh3:** 0.370  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.325  | P(true talent > .320) = **70.2%**  | P(true talent > career median) = 53.9%

- **Historical comps:** 15 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 0.0%  | Median next-30PA xwOBA: 0.253

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- EV90 +2.5mph — chase% -7.7pt — xwOBAcon +0.077 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


## SP velo flags (> 1.0 mph drop, injury/fatigue signal)

_No SP velo flags this week._

## Statistical confidence summary

_For each slumper, the convergence of 4 independent statistical tests:_

| Player | MC P(bounce) | Bayes P(>avg) | Hist comps | Hist P(bounce 30PA) | Injury | Verdict |

|---|---|---|---|---|---|---|

| Freddie Freeman | 55.3% | 97.0% | 104 | 49.0% | NONE | CONSENSUS_HOLD_BOUNCE |

| Vladimir Guerrero Jr. | 50.2% | 84.9% | 596 | 65.1% | DTD | HOLD_NOISE |

| Gunnar Henderson | 39.5% | 55.7% | 292 | 78.1% | NONE | HOLD_NOISE |

| Jose Altuve | 46.9% | 43.1% | 153 | 63.4% | DTD | HOLD_NOISE |

| Jackson Merrill | 97.4% | 78.6% | 108 | 79.6% | NONE | HOLD_NOISE |

| Maikel Garcia | 45.1% | 47.8% | 431 | 71.9% | NONE | HOLD_NOISE |

| Manny Machado | 53.5% | 59.7% | 138 | 63.8% | NONE | CONSENSUS_HOLD_BOUNCE |

| Sal Frelick | 35.5% | 1.6% | 313 | 68.7% | NONE | HOLD_NOISE |

| Trea Turner | 32.6% | 41.6% | 370 | 60.8% | NONE | HOLD_NOISE |

| Corey Seager | 68.0% | 88.5% | 340 | 72.1% | DTD | HOLD_NOISE |

| George Springer | 54.2% | 45.6% | 103 | 68.9% | NONE | HOLD_NOISE |

| Fernando Tatis Jr. | 60.3% | 90.4% | 647 | 58.1% | NONE | HOLD_NOISE |

| Salvador Perez | 32.1% | 52.5% | 232 | 61.2% | NONE | CONSENSUS_HOLD_BOUNCE |

| Christian Yelich | 47.5% | 70.9% | 224 | 67.9% | NONE | HOLD_NOISE |

| Roman Anthony | 88.6% | 100.0% | 26 | 88.5% | DTD | CONSENSUS_HOLD_BOUNCE |

| Cal Raleigh | 76.6% | 42.9% | 615 | 56.7% | DTD | HOLD_NOISE |

| Austin Riley | 51.9% | 89.6% | 819 | 60.3% | NONE | HOLD_NOISE |

| Rafael Devers | 12.4% | 71.0% | 293 | 72.0% | NONE | HOLD_NOISE |

| Agustin Ramirez | 5.4% | 42.7% | 74 | 83.8% | NONE | HOLD_NOISE |


## Waiver wire targets — slumpers bouncing back

_Statistically supported bounce candidates on rival rosters — watch for drops or offer a low-cost add._

| team_name               | player_name      | position   |   career_%ile | form_bucket   | process_verdict   |   mc_p_bounce_median |   bayes_p_above_avg |   hist_p_bounce_30pa |   rh3_per_pa |   replacement_delta | cross_verdict         |
|:------------------------|:-----------------|:-----------|--------------:|:--------------|:------------------|---------------------:|--------------------:|---------------------:|-------------:|--------------------:|:----------------------|
| Boone's Bad Bullpen     | Freddie Freeman  | 1B         |         0.141 | SLUMPING      | IMPROVING         |               0.5528 |              0.9697 |             0.490385 |        0.612 |               0.042 | CONSENSUS_HOLD_BOUNCE |
| Boone's Bad Bullpen     | Gunnar Henderson | SS         |         0.021 | SLUMPING      | DECLINING         |               0.3946 |              0.5572 |             0.780822 |        0.538 |               0.018 | HOLD_NOISE            |
| Team Solomon            | Jose Altuve      | 2B         |         0.071 | SLUMPING      | MIXED             |               0.4695 |              0.4306 |             0.633987 |        0.526 |               0.009 | HOLD_NOISE            |
| Late Night Bettsing     | Jackson Merrill  | CF         |         0.006 | SLUMPING      | MIXED             |               0.9741 |              0.7865 |             0.796296 |        0.521 |               0.032 | HOLD_NOISE            |
| 2015 Draft First Round  | Sal Frelick      | RF         |         0.093 | SLUMPING      | STABLE            |               0.3546 |              0.0159 |             0.686901 |        0.511 |               0.022 | HOLD_NOISE            |
| Frendy's Fantastic Team | George Springer  | DH         |         0.017 | SLUMPING      | DECLINING         |               0.5421 |              0.4563 |             0.68932  |        0.492 |               0.066 | HOLD_NOISE            |

## FA add candidates

_Available free agents with model projections. Ownership < 90% in this 8-team league._

### FA hitters (top 15 by rh3 projection)

| player_name        | position   |   owned_% |   xfp_rh3_per_pa | rh3_signal   | form_bucket   | process_verdict   |   career_%ile | cross_verdict   |
|:-------------------|:-----------|----------:|-----------------:|:-------------|:--------------|:------------------|--------------:|:----------------|
| Moises Ballesteros | DH         |       4.9 |            0.62  | add          | N/A           |                   |       nan     |                 |
| Carlos Cortes      | RF         |      13.2 |            0.616 | add          | N/A           |                   |       nan     |                 |
| Julio Rodriguez    | C          |       0.1 |            0.587 | add          | HIGH          | IMPROVING         |         0.802 | STABLE_HIGH     |
| Spencer Horwitz    | 1B         |       3.5 |            0.575 | hold         | N/A           |                   |       nan     |                 |
| Spencer Steer      | 1B         |      27.4 |            0.559 | hold         | N/A           |                   |       nan     |                 |
| Paul Goldschmidt   | 1B         |       2.4 |            0.551 | hold         | N/A           |                   |       nan     |                 |
| Daulton Varsho     | CF         |      16.3 |            0.548 | hold         | N/A           |                   |       nan     |                 |
| Miguel Andujar     | 3B         |       6.4 |            0.547 | hold         | N/A           |                   |       nan     |                 |
| Bryson Stott       | 2B         |      40   |            0.543 | hold         | N/A           |                   |       nan     |                 |
| Luis Garcia Jr.    | 2B         |      21.5 |            0.542 | hold         | N/A           |                   |       nan     |                 |
| Masataka Yoshida   | DH         |       0.9 |            0.542 | hold         | N/A           |                   |       nan     |                 |
| Gavin Sheets       | LF         |      26.3 |            0.541 | hold         | N/A           |                   |       nan     |                 |
| Javier Sanoja      | LF         |       3.8 |            0.534 | hold         | N/A           |                   |       nan     |                 |
| Brendan Donovan    | 2B         |      48.5 |            0.534 | hold         | N/A           |                   |       nan     |                 |
| Colson Montgomery  | SS         |      33.6 |            0.534 | hold         | N/A           |                   |       nan     |                 |

### FA starting pitchers (top 10 by rp3 projection)

| player_name           |   owned_% |   rp3_proj/start |   form_gap |
|:----------------------|----------:|-----------------:|-----------:|
| Blake Snell           |      74.2 |            13.02 |       0    |
| Spencer Schwellenbach |      12.6 |            12.75 |       0    |
| Ronel Blanco          |       0.1 |            12.11 |       0    |
| Corbin Burnes         |       9.7 |            12.06 |       0    |
| Emmet Sheehan         |      58   |            11.52 |      -0.61 |
| Pablo Lopez           |       3.2 |            11.46 |       0    |
| Eury Perez            |      68.2 |            11.15 |       1.15 |
| Dean Kremer           |       2   |            11.08 |       0    |
| Jack Leiter           |      16.9 |            10.93 |       3.73 |
| Max Meyer             |      62   |            10.58 |       3.1  |

### FA relief pitchers (top 10 by rprs2 projection)

| player_name    |   owned_% |   rprs2_proj_ros |
|:---------------|----------:|-----------------:|
| Abner Uribe    |      48.5 |            152.1 |
| Cole Sands     |       0.5 |            144.1 |
| Bryan Abreu    |      35.6 |            136.5 |
| Jacob Latz     |      13.6 |            136.3 |
| Jack Perkins   |       2.4 |            135.3 |
| Adrian Morejon |       8.8 |            134.5 |
| Jordan Romano  |       3.6 |            134   |
| Luke Weaver    |       3.9 |            132.3 |
| Kyle Hurt      |       0.2 |            132.2 |
| Lucas Erceg    |      32.4 |            130.9 |

## Watch list — your players showing peak regression risk

_Consider dropping or monitoring before value fades._

_None._

---

## Optional — trade context (if relevant)


### Trade targets — rival slumpers to buy

| team_name               | player_name      | position   |   career_%ile | form_bucket   | process_verdict   |   mc_p_bounce_median |   bayes_p_above_avg |   hist_p_bounce_30pa |   rh3_per_pa |   replacement_delta | cross_verdict         |
|:------------------------|:-----------------|:-----------|--------------:|:--------------|:------------------|---------------------:|--------------------:|---------------------:|-------------:|--------------------:|:----------------------|
| Boone's Bad Bullpen     | Freddie Freeman  | 1B         |         0.141 | SLUMPING      | IMPROVING         |               0.5528 |              0.9697 |             0.490385 |        0.612 |               0.042 | CONSENSUS_HOLD_BOUNCE |
| Boone's Bad Bullpen     | Gunnar Henderson | SS         |         0.021 | SLUMPING      | DECLINING         |               0.3946 |              0.5572 |             0.780822 |        0.538 |               0.018 | HOLD_NOISE            |
| Team Solomon            | Jose Altuve      | 2B         |         0.071 | SLUMPING      | MIXED             |               0.4695 |              0.4306 |             0.633987 |        0.526 |               0.009 | HOLD_NOISE            |
| Late Night Bettsing     | Jackson Merrill  | CF         |         0.006 | SLUMPING      | MIXED             |               0.9741 |              0.7865 |             0.796296 |        0.521 |               0.032 | HOLD_NOISE            |
| 2015 Draft First Round  | Sal Frelick      | RF         |         0.093 | SLUMPING      | STABLE            |               0.3546 |              0.0159 |             0.686901 |        0.511 |               0.022 | HOLD_NOISE            |
| Frendy's Fantastic Team | George Springer  | DH         |         0.017 | SLUMPING      | DECLINING         |               0.5421 |              0.4563 |             0.68932  |        0.492 |               0.066 | HOLD_NOISE            |

### Rival peakers cooling

| team_name               | player_name   | position   |   career_%ile | form_bucket   | peak_type      | process_verdict   |   bayes_p_above_avg |   peak_p_still_peak_30pa |   peak_expected_weeks_reversion |   rh3_per_pa | cross_verdict     |
|:------------------------|:--------------|:-----------|--------------:|:--------------|:---------------|:------------------|--------------------:|-------------------------:|--------------------------------:|-------------:|:------------------|
| Frendy's Fantastic Team | Josh Naylor   | 1B         |         0.924 | PEAK          | OUTCOME_DRIVEN | DECLINING         |              0.8074 |                    0.892 |                             5.6 |        0.571 | SELL_HIGH_WARNING |