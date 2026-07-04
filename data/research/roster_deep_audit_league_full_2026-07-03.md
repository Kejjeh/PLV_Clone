# League-wide roster deep audit (v4 — statistical + calibrated) — 2026-07-03

**Hitters:** 119 | **Slumpers analyzed:** 51 | **PEAK validated:** 12 | **MC sims:** 10,000/player (λ=0.20 recency decay) | **Historical comps:** 2015-2025 Statcast (age-matched ±3yr) | **SP career-form:** 66 SPs

> **CONSENSUS_DROP gate:** requires REGRESS + process DECLINING/MIXED + shrunk_gap < −0.030 + bounce_pct < 50%. IMPROVING process or anchor_in_CI always overrides to HOLD.

> **v4 upgrades:** recency-weighted MC + Bayesian (λ=0.20), age-matched comps (±3yr), Wilson CIs on survival curves, injury signal integration (ESPN DTD/IL).

> **Calibration:** ECE=0.0197 (WELL_CALIBRATED, threshold < 0.05), Brier=0.2221, validated on 15,778 out-of-sample snapshots (2023-2025 holdout). _Known limitation: adjacent rolling-150 windows share 149/150 events — precision is slightly overstated vs true i.i.d._

## Power ranking

| team_name                 |   rank |   n |   mean_pct |   n_peak |   n_high |   n_slump |   n_improving |   n_declining |   n_bounce |   n_drop |   mean_rh3 |   mean_bayes_p_avg |   sp_proj |
|:--------------------------|-------:|----:|-----------:|---------:|---------:|----------:|--------------:|--------------:|-----------:|---------:|-----------:|-------------------:|----------:|
| Late Night Bettsing       |      1 |  13 |      0.537 |        2 |        0 |         2 |             4 |             5 |          2 |        0 |      0.585 |           0.697231 |      85.1 |
| New York Ligers           |      2 |  14 |      0.519 |        3 |        0 |         1 |             3 |             5 |          1 |        0 |      0.572 |           0.7419   |     107.4 |
| U Just Lost To Edwin Diaz |      3 |  14 |      0.438 |        1 |        4 |         4 |             2 |             7 |          4 |        0 |      0.563 |           0.501986 |      91.6 |
| Frendy's Fantastic Team   |      4 |  16 |      0.56  |        0 |        2 |         2 |             6 |             5 |          2 |        0 |      0.562 |           0.721475 |     103.1 |
| 2015 Draft First Round    |      5 |  15 |      0.371 |        1 |        2 |         6 |             1 |             5 |          5 |        0 |      0.553 |           0.71758  |      93.8 |
| Team Solomon              |      6 |  14 |      0.35  |        2 |        0 |         8 |             4 |             5 |          8 |        0 |      0.546 |           0.768107 |     128.4 |
| Boone's Bad Bullpen       |      7 |  15 |      0.566 |        2 |        1 |         3 |             5 |             4 |          3 |        0 |      0.535 |           0.735007 |      70   |
| Treasure Island Mashers   |      8 |  18 |      0.451 |        1 |        1 |         6 |             2 |             7 |          6 |        0 |      0.533 |           0.626228 |      93.7 |


## Per-team position breakdown


### New York Ligers ← YOU

**C**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:--------------------|:---------------|:--------------|
| Hunter Goodman |         0.947 |          0.358 | PEAK          | STABLE        | STABLE            |         0.2786 |           0.2646 |     107.5 |       108.1 |               96.7 |              | False          |               0.4792 |              0.6091 |                   99.5 |            345 |             0.156522 | UNKNOWN        |        0.583 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |

**1B**

| player_name           |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Pete Alonso           |         0.96  |          0.43  | PEAK          | STABLE        | DECLINING         |         0.2185 |           0.264  |     110.1 |       108.4 |               96.6 |              | False          |               0.6995 |              0.9947 |                   86.3 |            475 |             0.218947 | UNKNOWN             |        0.613 | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Vladimir Guerrero Jr. |         0.113 |          0.331 | SLUMPING      | STABLE        | IMPROVING         |         0.1922 |           0.1548 |     110.3 |       108.6 |               83   |      -0.001  | True           |               0.4776 |              0.7844 |                   77.8 |            619 |             0.641357 | DISCIPLINE_COLLAPSE |        0.589 | hold         |                |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |
| Luis Arraez           |         0.204 |          0.307 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.0382 |           0.078  |      96.6 |        96.5 |               94.8 |       0.0045 | True           |               0.3736 |              0.5227 |                   87.4 |            923 |             0.565547 | MIXED               |        0.57  | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kody Clemens          |         0.907 |          0.342 | PEAK          | STABLE        | DECLINING         |         0.2114 |           0.2135 |     106   |       103.1 |              100   |              | False          |               0.0708 |              0.4649 |                  109.6 |            257 |             0.171206 | UNKNOWN             |        0.52  | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Max Muncy     |         0.281 |          0.348 | BELOW_MEDIAN  | STABLE        | MIXED             |          0.215 |           0.2147 |     105.8 |         104 |                100 |      -0.0145 | True           |               0.7033 |              0.8245 |                   81.6 |            269 |             0.449814 | MIXED          |        0.393 | drop         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Bo Bichette     |         0.384 |          0.332 | BELOW_MEDIAN  | REGRESS       | STABLE            |         0.1576 |           0.1441 |     105.5 |       106.4 |              100   |      -0.0066 | True           |               0.627  |              0.7837 |                   94.1 |            846 |             0.462175 | K_DRIVEN       |        0.572 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Elly De La Cruz |         0.691 |          0.346 | ABOVE_MEDIAN  | STABLE        | STABLE            |         0.2788 |           0.271  |     107.7 |       112.4 |               66.1 |              | False          |               0.5646 |              0.7414 |                   96.9 |                |                      | UNKNOWN        |        0.536 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Aaron Judge       |         0.307 |          0.406 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.3159 |           0.3421 |     111.9 |       109.1 |               64   |      -0.0175 | True           |               0.5235 |              0.9887 |                   61.1 |            383 |             0.545692 | BABIP_DRIVEN   |        0.708 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Corbin Carroll    |         0.294 |          0.331 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2164 |           0.314  |     107.4 |       107.2 |               90   |      -0.0173 | True           |               0.4    |              0.7918 |                   77.3 |            610 |             0.518033 | MIXED          |        0.651 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Michael Harris II |         0.451 |          0.334 | TYPICAL       | STABLE        | IMPROVING         |         0.199  |           0.1782 |     108.6 |       108.9 |               59.8 |              | False          |               0.6599 |              0.6273 |                  103.3 |                |                      | UNKNOWN        |        0.622 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Dominic Canzone   |         0.785 |          0.381 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2264 |           0.1954 |     107.8 |       108.8 |               78.8 |              | False          |               0.5047 |              0.9501 |                  109.2 |                |                      | UNKNOWN        |        0.557 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Wyatt Langford    |         0.264 |          0.316 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2331 |           0.1845 |     107   |       105   |               90.6 |       0.0163 | True           |               0.8076 |              0.7662 |                   98.5 |            287 |             0.533101 | MIXED          |        0.557 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jordan Walker     |         0.68  |          0.34  | ABOVE_MEDIAN  | IMPROVING     | MIXED             |         0.3268 |           0.3066 |     110   |       111   |               51.8 |              | False          |               0.6268 |              0.5371 |                  143.4 |                |                      | UNKNOWN        |        0.539 | hold         |             |                     | STRENGTHENING          | NONE           |               |

**SP**

| player_name    |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:---------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Tyler Glasnow  | 13.824 |      0     |          |             |              | False       |             |                |
| Shota Imanaga  | 12.294 |     -1.804 |          |             |              | False       |             |                |
| Hunter Greene  | 12.27  |      0     |          |             |              | False       |             |                |
| Jose Soriano   | 11.822 |     -4.608 |          |             |              | False       |             |                |
| Parker Messick | 11.606 |     -0.131 |          |             |              | False       |             |                |
| Max Fried      | 11.554 |      0     |          |             |              | False       |             |                |
| Emmet Sheehan  | 11.544 |     -1.76  |          |             |              | False       |             |                |
| Carlos Rodon   | 11.515 |     -1.025 |          |             |              | False       |             |                |
| Freddy Peralta | 10.991 |     -8.025 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Jhoan Duran   |  142.5 |
| Ryan Helsley  |  126.9 |
| Tanner Scott  |  106.8 |
| Jacob Latz    |   93.2 |
| Reid Detmers  |  nan   |


### 2015 Draft First Round

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Will Smith    |         0.864 |          0.386 | HIGH          | STABLE        | DECLINING         |         0.1878 |           0.1157 |     105.6 |       102.6 |               95.4 |              | False          |               0.2997 |              0.9851 |                   85.6 |                |                      | UNKNOWN        |        0.564 | hold         |             |                     | STABLE_HIGH            | NONE           |               |
| Keibert Ruiz  |         0.224 |          0.275 | BELOW_MEDIAN  | NOISE         | MIXED             |         0.1028 |           0.1651 |     100.3 |       101.6 |               92.2 |       0.0038 | True           |               0.6121 |              0.2716 |                  106.6 |            679 |             0.571429 | K_DRIVEN       |        0.535 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**1B**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Paul Goldschmidt |         0.029 |          0.305 | SLUMPING      | NOISE         | DECLINING         |         0.1792 |           0.2238 |     105.3 |       101.5 |                nan |      -0.0225 | False          |               0.7921 |              0.5943 |                    110 |             23 |             0.608696 | K_DRIVEN       |         0.55 | hold         |             |                     | SLUMP_AMBIGUOUS | NONE           |               |

**2B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:--------------------|:---------------|:--------------|
| Ketel Marte   |         0.98  |          0.436 | PEAK          | STABLE        | MIXED             |         0.1844 |           0.1948 |     107.4 |       108.5 |               86.8 |              | False          |               0.3522 |              0.9859 |                   74.3 |            189 |             0.206349 | UNKNOWN        |        0.683 | add          | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |
| Brandon Lowe  |         0.151 |          0.318 | SLUMPING      | STABLE        | MIXED             |         0.2896 |           0.2901 |     106.4 |       107   |               54.1 |       0.0051 | True           |               0.7576 |              0.7428 |                   98.3 |            785 |             0.563057 | K_DRIVEN       |        0.54  | hold         |             |                     | HOLD_NOISE          | NONE           |               |
| Sam Antonacci |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1408 |           |       101.7 |              nan   |              | False          |               0.7337 |              1      |                  106.2 |                |                      | UNKNOWN        |        0.484 | hold         |             |                     | INSUFFICIENT_DATA   | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Alex Bregman  |         0.151 |          0.318 | SLUMPING      | REGRESS       | MIXED             |         0.1252 |           0.1154 |     102.8 |       100.9 |               98.5 |       0.0089 | True           |               0.5073 |              0.8606 |                   83.1 |            369 |             0.604336 | HOLDING        |        0.563 | hold         |             |                     | HOLD_NOISE      | NONE           |               |
| Josh Jung     |         0.82  |          0.361 | HIGH          | STABLE        | IMPROVING         |         0.2188 |           0.1143 |     103.9 |       102.2 |               57.2 |              | False          |               0.7023 |              0.6477 |                  121.5 |                |                      | UNKNOWN        |        0.53  | hold         |             |                     | STABLE_HIGH     | NONE           |               |

**SS**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Bobby Witt Jr. |         0.777 |          0.397 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.2097 |           0.1939 |     108.8 |       106.2 |               71.5 |              | False          |               0.3856 |              0.9969 |                   71.7 |                |                      | UNKNOWN             |        0.697 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Dansby Swanson |         0.024 |          0.253 | SLUMPING      | STABLE        | DECLINING         |         0.2812 |           0.3182 |     104.7 |       103.8 |               68.4 |       0.0196 | True           |               0.4631 |              0.5503 |                  108.1 |            264 |             0.681818 | DISCIPLINE_COLLAPSE |        0.445 | drop         |             |                     | HOLD_NOISE             | NONE           |               |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Daylen Lile   |         0.045 |          0.283 | SLUMPING      | STABLE        | DECLINING         |         0.1471 |           0.1756 |     103.9 |       103.6 |              100   |      -0.0064 | True           |               0.4859 |              0.6066 |                   82.7 |             72 |             0.805556 | MIXED               |        0.552 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Ian Happ      |         0.035 |          0.271 | SLUMPING      | STABLE        | DECLINING         |         0.2084 |           0.2737 |     105.7 |       105.3 |               64.4 |      -0.0013 | True           |               0.3622 |              0.4233 |                   97.4 |            364 |             0.684066 | DISCIPLINE_COLLAPSE |        0.528 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Jung Hoo Lee  |         0.462 |          0.32  | TYPICAL       | STABLE        | MIXED             |         0.1096 |           0.1088 |     101.3 |       100.4 |               97.1 |              | False          |               0.5779 |              0.3731 |                   97.1 |                |                      | UNKNOWN             |        0.526 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Riley Greene  |         0.272 |          0.324 | BELOW_MEDIAN  | STABLE        | STABLE            |         0.2628 |           0.2523 |     107.8 |       108.2 |               71.3 |       0.0146 | True           |               0.3947 |              0.7324 |                  102.3 |            737 |             0.514247 | MIXED               |        0.478 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Kyle Schwarber |          0.36 |          0.353 | BELOW_MEDIAN  | REGRESS       | MIXED             |         0.2979 |           0.2934 |     109.8 |       108.8 |               73.2 |      -0.0055 | True           |               0.5641 |              0.9931 |                   83.4 |            417 |             0.486811 | DISCIPLINE_COLLAPSE |        0.626 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name    |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:---------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Jacob deGrom   | 15.273 |      0.612 |          |             |              | False       |             |                |
| Logan Gilbert  | 14.68  |      6.024 |          |             |              | False       |             |                |
| Cam Schlittler | 14.485 |     -4.006 |          |             |              | False       |             |                |
| Drew Rasmussen | 12.747 |      4.35  |          |             |              | False       |             |                |
| Foster Griffin |  9.92  |      6.681 |          |             |              | False       |             |                |
| Bryce Elder    |  9.479 |    -15.429 |          |             |              | False       |             |                |
| Shane Baz      |  9.454 |      1.627 |          |             |              | False       |             |                |
| Nick Lodolo    |  7.808 |     -0.956 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Bryan Baker   |  108.7 |
| Trevor Megill |  107   |
| Jakob Junis   |   84.4 |
| Robert Garcia |   53   |
| Peter Lambert |  nan   |


### Boone's Bad Bullpen

**C**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| William Contreras |         0.751 |          0.352 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2113 |           0.129  |     107.4 |       105.8 |                 61 |              | False          |               0.7308 |              0.9091 |                   90.7 |                |                      | UNKNOWN        |        0.619 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Dillon Dingler    |         0.736 |          0.386 | ABOVE_MEDIAN  | IMPROVING     | DECLINING         |         0.2149 |           0.2256 |     105.4 |       104.3 |                 76 |              | False          |               0.0782 |              0.9065 |                  123.3 |                |                      | UNKNOWN        |        0.565 | hold         |             |                     | STRENGTHENING          | NONE           |               |

**1B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Freddie Freeman |         0.547 |          0.397 | TYPICAL       | STABLE        | IMPROVING         |         0.2516 |           0.1792 |     104.3 |       102.8 |               86   |              | False          |               0.6017 |              0.9975 |                   76.9 |                |                      | UNKNOWN        |        0.632 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Michael Busch   |         0.572 |          0.352 | TYPICAL       | REGRESS       | DECLINING         |         0.2208 |           0.2723 |     105.4 |       102.4 |               95.3 |              | False          |               0.7443 |              0.949  |                   96.4 |                |                      | UNKNOWN        |        0.535 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Ryan O'Hearn    |         0.046 |          0.271 | SLUMPING      | STABLE        | MIXED             |         0.1931 |           0.2047 |     103.1 |       103.8 |               58.6 |        0.018 | True           |               0.5059 |              0.5446 |                   93.5 |            362 |             0.671271 | MIXED          |        0.525 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**3B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Junior Caminero |         0.753 |          0.375 | ABOVE_MEDIAN  | STABLE        | STABLE            |         0.2194 |           0.1922 |     109.5 |       112.5 |               92.8 |              | False          |               0.3592 |              0.8701 |                   82.3 |                |                      | UNKNOWN        |        0.694 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kazuma Okamoto  |         0.023 |          0.276 | SLUMPING      | NO_BASELINE   | MIXED             |                |           0.3109 |           |       107.2 |              nan   |      -0.0096 | True           |               0      |              0.5206 |                  106.2 |             26 |             0.846154 | UNKNOWN        |        0.458 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Gunnar Henderson |         0.229 |          0.324 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2172 |           0.2165 |     106.8 |       104.5 |              100   |      -0.0092 | True           |               0.451  |              0.6734 |                   86.3 |            541 |             0.543438 | MIXED          |        0.558 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Zach Neto        |         0.125 |          0.298 | SLUMPING      | STABLE        | DECLINING         |         0.2667 |           0.2886 |     105.7 |       104.2 |               97.6 |      -0.0066 | True           |               0.3284 |              0.441  |                   99   |            525 |             0.63619  | BABIP_DRIVEN   |        0.492 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Konnor Griffin   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.2474 |           |       102.2 |              nan   |              | False          |               0.7385 |              0.4366 |                  106.2 |                |                      | UNKNOWN        |        0.424 | drop         |             |                     | INSUFFICIENT_DATA      | NONE           |               |

**OF**

| player_name         |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Tyler Soderstrom    |         0.714 |          0.35  | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2042 |           0.1645 |     107.2 |       106.9 |               98.4 |              | False          |               0.6203 |              0.8016 |                  103.5 |                |                      | UNKNOWN        |        0.566 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Pete Crow-Armstrong |         0.962 |          0.422 | PEAK          | STABLE        | IMPROVING         |         0.2465 |           0.2222 |     105.2 |       105.4 |               98.7 |              | False          |               0.6415 |              0.8397 |                   94.2 |            214 |             0.154206 | UNKNOWN        |        0.551 | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Bryan Reynolds      |         0.897 |          0.395 | HIGH          | NOISE         | MIXED             |         0.255  |           0.2578 |     106.3 |       106.3 |               79.7 |              | False          |               0.4795 |              0.9215 |                  107.5 |                |                      | UNKNOWN        |        0.536 | hold         |                |                     | STABLE_HIGH            | NONE           |               |
| Steven Kwan         |         0.625 |          0.322 | ABOVE_MEDIAN  | REGRESS       | MIXED             |         0.0749 |           0.084  |      98   |        96.7 |              100   |              | False          |               0.6681 |              0.4232 |                   90.6 |                |                      | UNKNOWN        |        0.461 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jac Caglianone      |         0.944 |          0.383 | PEAK          | STABLE        | IMPROVING         |         0.2432 |           0.2545 |     109.4 |       110.4 |              100   |              | False          |               1      |              0.7907 |                  159.4 |             64 |             0.015625 | UNKNOWN        |        0.403 | drop         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**SP**

| player_name   |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:--------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Paul Skenes   | 15.409 |      0.557 |          |             |              | False       |             |                |
| Jesus Luzardo | 13.509 |      5.075 |          |             |              | False       |             |                |
| Casey Mize    | 11.734 |      3.977 |          |             |              | False       |             |                |
| Gerrit Cole   | 10.452 |     -0.933 |          |             |              | False       |             |                |
| Michael King  | 10.192 |     -9.581 |          |             |              | False       |             |                |
| Nick Martinez |  8.715 |     -0.713 |          |             |              | False       |             |                |

**RP**

| player_name      |   proj |
|:-----------------|-------:|
| Raisel Iglesias  |  123.8 |
| David Bednar     |  117.4 |
| Garrett Whitlock |   90.8 |
| Abner Uribe      |   85.5 |
| Robert Suarez    |   82   |
| Andres Munoz     |  nan   |


### Frendy's Fantastic Team

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Drake Baldwin |         0.796 |          0.382 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.1592 |           0.2258 |     106.3 |       103.9 |               89.8 |              | False          |               0.3057 |               0.939 |                   80.2 |                |                      | UNKNOWN        |        0.633 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Josh Naylor   |         0.213 |          0.309 | BELOW_MEDIAN  | REGRESS       | IMPROVING         |         0.1965 |           0.1381 |     104.3 |       102.9 |               98.7 |       0.0039 | True           |               0.6124 |              0.6949 |                   77.7 |            914 |             0.533917 | HOLDING        |        0.58  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Sal Stewart   |         0.652 |          0.357 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.2124 |           0.2683 |     107.4 |       103.2 |              nan   |              | False          |               0.9346 |              0.9624 |                   90.8 |                |                      | UNKNOWN        |        0.569 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Nico Hoerner  |         0.381 |          0.311 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.092  |           0.0709 |     100.7 |       100.4 |               59.7 |      -0.0042 | True           |               0.5227 |              0.3588 |                   86.4 |            806 |             0.480149 | HOLDING        |        0.584 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Ozzie Albies  |         0.417 |          0.311 | TYPICAL       | STABLE        | IMPROVING         |         0.1757 |           0.1536 |     100.8 |       101.7 |               55.4 |              | False          |               0.7169 |              0.2885 |                   91   |                |                      | UNKNOWN        |        0.547 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict     | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:------------------|:---------------|:--------------|
| Miguel Vargas     |         0.882 |          0.406 | HIGH          | STABLE        | IMPROVING         |         0.1716 |           0.1453 |     103.1 |       103.9 |               53.8 |              | False          |               0.617  |              0.9669 |                  110.1 |                |                      | UNKNOWN        |        0.615 | add          |             |                     | STABLE_HIGH       | NONE           |               |
| Munetaka Murakami |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.3563 |           |       108.2 |              nan   |              | False          |               0.9494 |              1      |                  106.2 |                |                      | UNKNOWN        |        0.534 | hold         |             |                     | INSUFFICIENT_DATA | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Kevin McGonigle |          0.8  |          0.38  | HIGH          | NO_BASELINE   | MIXED             |                |           0.1744 |           |       102.6 |              nan   |              | False          |               0.596  |              0.9722 |                  106.2 |                |                      | UNKNOWN        |        0.546 | hold         |             |                     | STABLE_HIGH            | NONE           |               |
| Brooks Lee      |          0.75 |          0.292 | ABOVE_MEDIAN  | STABLE        | MIXED             |          0.214 |           0.1835 |     101.5 |       102.4 |               83.8 |              | False          |               0.7411 |              0.0456 |                  117   |                |                      | UNKNOWN        |        0.484 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Cody Bellinger  |         0.623 |          0.343 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.1489 |           0.1739 |     102.7 |       102.9 |               56.7 |              | False          |               0.7727 |              0.417  |                   78.3 |                |                      | UNKNOWN        |        0.63  | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jackson Chourio |         0.795 |          0.361 | ABOVE_MEDIAN  | STABLE        | STABLE            |         0.2257 |           0.2067 |     105.9 |       104.6 |              nan   |              | False          |               0.8747 |              0.7684 |                   88.1 |                |                      | UNKNOWN        |        0.627 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Taylor Ward     |         0.478 |          0.341 | TYPICAL       | STABLE        | IMPROVING         |         0.205  |           0.1613 |     105.1 |       103.2 |               69.7 |              | False          |               0.5694 |              0.6708 |                  100.6 |                |                      | UNKNOWN        |        0.504 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kyle Stowers    |         0.636 |          0.354 | ABOVE_MEDIAN  | REGRESS       | DECLINING         |         0.2914 |           0.3064 |     108.2 |       107.5 |               92.7 |              | False          |               0.7179 |              0.9556 |                  103   |                |                      | UNKNOWN        |        0.468 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**UTIL/DH**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Shohei Ohtani    |         0.774 |          0.446 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.3024 |           0.2283 |     110.1 |       108.6 |               88.1 |              | False          |               0.7138 |              0.998  |                   63.4 |                |                      | UNKNOWN             |        0.709 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| George Springer  |         0.133 |          0.321 | SLUMPING      | REGRESS       | DECLINING         |         0.2308 |           0.1823 |     107.2 |       105   |               95.7 |      -0.0201 | True           |               0.5894 |              0.828  |                   86.2 |            133 |             0.541353 | DISCIPLINE_COLLAPSE |        0.518 | add          |             |                     | HOLD_NOISE             | NONE           |               |
| Christian Yelich |         0.07  |          0.304 | SLUMPING      | STABLE        | DECLINING         |         0.2496 |           0.3172 |     106.7 |       102.9 |               92.3 |      -0.0072 | True           |               0.4625 |              0.6775 |                   85.8 |            186 |             0.66129  | K_DRIVEN            |        0.44  | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**SP**

| player_name      |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-----------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Joe Ryan         | 13.502 |     -2.928 |          |             |              | False       |             |                |
| Chase Burns      | 13.387 |     -2.951 |          |             |              | False       |             |                |
| Hunter Brown     | 11.98  |     -3.5   |          |             |              | False       |             |                |
| Brandon Woodruff | 11.562 |      9.5   |          |             |              | False       |             |                |
| Shane McClanahan | 11.273 |     -7.929 |          |             |              | False       |             |                |
| Payton Tolle     | 11.235 |     -4.105 |          |             |              | False       |             |                |
| Jared Jones      | 10.881 |     -0.936 |          |             |              | False       |             |                |
| Framber Valdez   |  9.715 |     -2.363 |          |             |              | False       |             |                |
| Connelly Early   |  9.591 |     -1.446 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Grant Taylor  |    nan |


### Late Night Bettsing

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Ben Rice          |         0.019 |          0.325 | SLUMPING      | STABLE        | DECLINING         |         0.1905 |           0.1746 |     107.7 |       104.8 |               87.5 |      -0.0234 | False          |               0.5407 |              0.8972 |                   91.8 |            194 |             0.757732 | DISCIPLINE_COLLAPSE |        0.609 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |
| Jonathan Aranda   |         0.658 |          0.383 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.218  |           0.1828 |     106.9 |       105.7 |               96.6 |              | False          |               0.2223 |              0.9532 |                   98.5 |                |                      | UNKNOWN             |        0.562 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Spencer Steer     |         0.581 |          0.324 | TYPICAL       | STABLE        | IMPROVING         |         0.2213 |           0.1627 |     102   |       101.9 |               90.8 |              | False          |               0.6179 |              0.2845 |                   97.7 |                |                      | UNKNOWN             |        0.557 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Willson Contreras |         0.45  |          0.347 | TYPICAL       | STABLE        | DECLINING         |         0.2476 |           0.2969 |     108.2 |       109.9 |               72.6 |              | False          |               0.5065 |              0.7116 |                   97.7 |                |                      | UNKNOWN             |        0.541 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Gleyber Torres |         0.546 |          0.342 | TYPICAL       | STABLE        | DECLINING         |         0.1628 |           0.2258 |     104.6 |       101.6 |               73.4 |              | False          |                0.532 |              0.7262 |                   98.3 |                |                      | UNKNOWN        |         0.48 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:--------------------|:---------------|:--------------|
| Isaac Paredes |         0.907 |          0.339 | PEAK          | STABLE        | DECLINING         |         0.1396 |            0.144 |     102.5 |       101.7 |               88.8 |              | False          |               0.4833 |              0.3612 |                   89.3 |            723 |             0.200553 | UNKNOWN        |         0.55 | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |

**SS**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Mookie Betts  |         0.296 |          0.337 | BELOW_MEDIAN  | STABLE        | STABLE            |         0.1313 |           0.1149 |     101.6 |       102.8 |              nan   |      -0.0055 | True           |               0.8546 |              0.9249 |                   73.4 |            178 |             0.550562 | MIXED          |        0.647 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| CJ Abrams     |         0.658 |          0.327 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.2123 |           0.2565 |     104.1 |       104.3 |               57.6 |              | False          |               0.4849 |              0.211  |                   93.7 |                |                      | UNKNOWN        |        0.552 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Alec Burleson   |         0.997 |          0.407 | PEAK          | STABLE        | MIXED             |         0.1486 |           0.1762 |     106.1 |       106.5 |               66.6 |              | False          |               0.6998 |              0.9575 |                   92.1 |            361 |             0.166205 | UNKNOWN             |        0.617 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Andy Pages      |         0.768 |          0.347 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.1915 |           0.1953 |     104.4 |       103.5 |               81.2 |              | False          |               0.5662 |              0.5376 |                  101.4 |                |                      | UNKNOWN             |        0.584 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kyle Tucker     |         0.236 |          0.342 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.1729 |           0.2057 |     103.9 |       102.6 |              100   |       0.0213 | False          |               0.5613 |              0.9617 |                   69.9 |            933 |             0.527331 | K_DRIVEN            |        0.558 | hold         |             |                     | BOUNCING_BACK          | NONE           |               |
| Jackson Merrill |         0.089 |          0.31  | SLUMPING      | REGRESS       | IMPROVING         |         0.2238 |           0.1439 |     105.3 |       103.4 |              100   |      -0.0116 | True           |               0.9962 |              0.5377 |                   89   |            207 |             0.661836 | DISCIPLINE_COLLAPSE |        0.539 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Yordan Alvarez |         0.773 |          0.458 | ABOVE_MEDIAN  | NOISE         | IMPROVING         |         0.1989 |           0.1652 |     110.3 |       110.2 |               52.9 |              | False          |               0.4864 |              0.9997 |                   72.9 |                |                      | UNKNOWN        |        0.803 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Dylan Cease        | 14.857 |     -1.757 |          |             |              | False       |             |                |
| Bryan Woo          | 13.576 |      2.384 |          |             |              | False       |             |                |
| Max Meyer          | 11.516 |     -2.531 |          |             |              | False       |             |                |
| Ben Brown          | 10.515 |     -4.875 |          |             |              | False       |             |                |
| Spencer Arrighetti |  9.107 |     -3.358 |          |             |              | False       |             |                |
| Noah Cameron       |  9.056 |    -10.681 |          |             |              | False       |             |                |
| Robbie Ray         |  8.497 |     11.273 |          |             |              | False       |             |                |
| Eduardo Rodriguez  |  8.024 |     -1.802 |          |             |              | False       |             |                |

**RP**

| player_name      |   proj |
|:-----------------|-------:|
| Cade Smith       |  149.7 |
| Aroldis Chapman  |  149.4 |
| Paul Sewald      |  120.6 |
| Devin Williams   |  104.1 |
| Braxton Ashcraft |  nan   |
| Justin Wrobleski |  nan   |


### Team Solomon

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict         | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------------|:---------------|:--------------|
| Cal Raleigh   |         0.093 |            0.3 | SLUMPING      | REGRESS       | IMPROVING         |         0.2717 |           0.2455 |       107 |       105.8 |               95.4 |       0.0001 | True           |               0.7725 |              0.7165 |                     87 |            711 |             0.649789 | K_DRIVEN       |        0.437 | drop         |             |                     | CONSENSUS_HOLD_BOUNCE | NONE           |               |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Bryce Harper  |         0.687 |          0.413 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.2764 |           0.2771 |     107.2 |       106.7 |               77.4 |              | False          |               0.671  |              0.9933 |                   83   |                |                      | UNKNOWN             |        0.652 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Matt Olson    |         0.157 |          0.324 | SLUMPING      | STABLE        | MIXED             |         0.2336 |           0.2258 |     108.4 |       108.8 |               55.8 |       0.0026 | True           |               0.2705 |              0.6641 |                   85.5 |            431 |             0.568445 | DISCIPLINE_COLLAPSE |        0.636 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**2B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Casey Schmitt     |         0.975 |          0.374 | PEAK          | MIXED         | IMPROVING         |         0.2318 |           0.1739 |     105.1 |       105.3 |               62.6 |              | False          |               0.2775 |              0.9034 |                  125.1 |            237 |             0.105485 | UNKNOWN        |        0.543 | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Jose Altuve       |         0.001 |          0.246 | SLUMPING      | REGRESS       | MIXED             |         0.1673 |           0.2624 |     102.4 |       101.7 |               97.1 |       -0.016 | True           |               0.4087 |              0.1935 |                   87.4 |             85 |             0.635294 | BABIP_DRIVEN   |        0.512 | hold         |                |                     | HOLD_NOISE             | NONE           |               |
| Jazz Chisholm Jr. |         0.498 |          0.32  | TYPICAL       | REGRESS       | DECLINING         |         0.2949 |           0.3029 |     105.4 |       100.3 |              100   |              | False          |               0.2554 |              0.5073 |                   93.6 |                |                      | UNKNOWN        |        0.455 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Manny Machado |          0.23 |          0.323 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.2358 |             0.25 |     107.7 |       103.9 |               92.4 |       0.0152 | True           |               0.5169 |              0.8707 |                   87.1 |            154 |             0.577922 | HOLDING        |        0.531 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SS**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| JJ Wetherholt |         0.073 |          0.348 | SLUMPING      | NO_BASELINE   | MIXED             |                |           0.1267 |           |       101.5 |              nan   |      -0.008  | True           |               0.6195 |              1      |                  106.2 |             32 |             0.75     | UNKNOWN             |        0.539 | hold         |             |                     | HOLD_NOISE      | NONE           |               |
| Corey Seager  |         0.178 |          0.344 | SLUMPING      | REGRESS       | DECLINING         |         0.2437 |           0.3171 |     108   |       105.3 |              100   |       0.0079 | True           |               0.6728 |              0.9425 |                   77.2 |            525 |             0.620952 | K_DRIVEN            |        0.522 | hold         |             |                     | HOLD_NOISE      | NONE           |               |
| Trea Turner   |         0.077 |          0.286 | SLUMPING      | REGRESS       | MIXED             |         0.2181 |           0.2339 |     104.2 |       103.9 |               81.4 |       0.0017 | True           |               0.3944 |              0.3409 |                   85.5 |            332 |             0.61747  | DISCIPLINE_COLLAPSE |        0.499 | hold         |             |                     | HOLD_NOISE      | NONE           |               |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| James Wood    |         0.76  |          0.422 | ABOVE_MEDIAN  | STABLE        | MIXED             |         0.3015 |           0.3097 |     112   |       110.6 |               82.1 |              | False          |               0.3872 |              0.98   |                  105.1 |                |                      | UNKNOWN        |        0.612 | add          |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Brandon Nimmo |         0.962 |          0.398 | PEAK          | STABLE        | IMPROVING         |         0.2106 |           0.1908 |     106.2 |       105   |               86.6 |              | False          |               0.7524 |              0.9217 |                   97   |            331 |             0.220544 | UNKNOWN        |        0.595 | add          | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict         | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------------|:---------------|:--------------|
| Mike Trout    |         0.142 |          0.377 | SLUMPING      | NOISE         | IMPROVING         |         0.2568 |           0.2064 |     107.9 |       109.4 |               73.2 |       0.0014 | True           |               0.5811 |              0.9959 |                  104.4 |            254 |             0.649606 | MIXED          |        0.579 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE | NONE           |               |
| Seiya Suzuki  |         0.074 |          0.3   | SLUMPING      | STABLE        | DECLINING         |         0.2086 |           0.2344 |     107   |       106.4 |               71.1 |      -0.007  | True           |               0.7608 |              0.7237 |                   93.7 |            392 |             0.665816 | MIXED          |        0.533 | hold         |             |                     | HOLD_NOISE            | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Tarik Skubal       | 15.992 |     -1.427 |          |             |              | False       |             |                |
| Cristopher Sanchez | 15.536 |     -5.622 |          |             |              | False       |             |                |
| Chris Sale         | 15.099 |     -0.13  |          |             |              | False       |             |                |
| Zack Wheeler       | 13.989 |      0.673 |          |             |              | False       |             |                |
| Nathan Eovaldi     | 12.859 |      1.606 |          |             |              | False       |             |                |
| George Kirby       | 11.633 |      3.675 |          |             |              | False       |             |                |
| Garrett Crochet    | 11.52  |      0     |          |             |              | False       |             |                |
| Logan Webb         | 11.261 |      7.731 |          |             |              | False       |             |                |
| Sonny Gray         | 11.222 |      8.948 |          |             |              | False       |             |                |
| Davis Martin       |  9.307 |     -9.925 |          |             |              | False       |             |                |

**RP**

| player_name    |   proj |
|:---------------|-------:|
| Josh Hader     |  207.7 |
| Pete Fairbanks |  142.1 |
| Riley O'Brien  |  100.4 |
| Louis Varland  |   85.8 |


### Treasure Island Mashers

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Adley Rutschman |         0.752 |          0.368 | ABOVE_MEDIAN  | NOISE         | DECLINING         |         0.1273 |           0.1412 |     104.6 |       102.6 |               55.2 |              | False          |               0.7153 |              0.441  |                  100.2 |                |                      | UNKNOWN             |        0.58  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Alejandro Kirk  |         0.165 |          0.312 | SLUMPING      | STABLE        | DECLINING         |         0.1531 |           0.1304 |     106.6 |       101   |              nan   |      -0.0029 | True           |               0.9515 |              0.4468 |                   97.6 |            662 |             0.610272 | DISCIPLINE_COLLAPSE |        0.453 | drop         |             |                     | HOLD_NOISE             | NONE           |               |

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Nick Kurtz        |         0.434 |          0.386 | TYPICAL       | STABLE        | STABLE            |          0.323 |           0.3142 |     108.5 |       109.8 |                100 |              | False          |               0.3436 |              0.9818 |                   75   |                |                      | UNKNOWN             |        0.669 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Spencer Torkelson |         0.352 |          0.312 | BELOW_MEDIAN  | REGRESS       | MIXED             |          0.23  |           0.3008 |     104.5 |       104.2 |                 72 |       0.0191 | True           |               0.7404 |              0.7422 |                  109.1 |            784 |             0.487245 | DISCIPLINE_COLLAPSE |        0.472 | drop         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Brice Turang   |         0.136 |          0.286 | SLUMPING      | STABLE        | DECLINING         |         0.1861 |           0.2081 |     104.2 |       103.3 |               57.4 |       0.0036 | True           |               0.9228 |              0.2585 |                  102.2 |            688 |             0.614826 | DISCIPLINE_COLLAPSE |        0.559 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Luke Keaschall |         0.725 |          0.308 | ABOVE_MEDIAN  | REGRESS       | MIXED             |         0.1667 |           0.1474 |     100.8 |       100.8 |              nan   |              | False          |               0.7705 |              0.2377 |                   79.8 |                |                      | UNKNOWN             |        0.524 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Nolan Arenado |         0.051 |          0.279 | SLUMPING      | STABLE        | DECLINING         |          0.162 |           0.2436 |     101.6 |       101.4 |               92.8 |      -0.0065 | True           |               0.9367 |              0.1087 |                   96.5 |            133 |             0.609023 | K_DRIVEN       |        0.483 | hold         |             |                     | HOLD_NOISE      | NONE           |               |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Jacob Wilson     |         0.451 |          0.291 | TYPICAL       | STABLE        | MIXED             |         0.0775 |           0.1269 |      99.4 |       101.4 |              100   |              | False          |               0.7356 |              0.134  |                   86.4 |                |                      | UNKNOWN        |        0.554 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Francisco Lindor |         0.664 |          0.364 | ABOVE_MEDIAN  | REGRESS       | MIXED             |         0.1803 |           0.1928 |     104.5 |       102.5 |               99.5 |              | False          |               0.6518 |              0.7819 |                   78.7 |                |                      | UNKNOWN        |        0.551 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Xander Bogaerts  |         0.178 |          0.294 | SLUMPING      | STABLE        | MIXED             |         0.1938 |           0.2483 |     105.6 |       106.6 |               77.8 |      -0.0003 | True           |               0.6007 |              0.4923 |                  101.5 |            211 |             0.587678 | MIXED          |        0.504 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**OF**

| player_name        |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Juan Soto          |         0.886 |          0.468 | HIGH          | STABLE        | MIXED             |         0.1958 |           0.1765 |     108   |       106.9 |               85.8 |              | False          |               0.6013 |              1      |                   67.9 |                |                      | UNKNOWN        |        0.756 | add          |             |                     | STABLE_HIGH            | NONE           |               |
| Wilyer Abreu       |         0.018 |          0.28  | SLUMPING      | STABLE        | DECLINING         |         0.2024 |           0.2121 |     107.5 |       104.3 |               50.5 |      -0.0141 | True           |               0.5188 |              0.4011 |                   96.7 |            185 |             0.745946 | K_DRIVEN       |        0.527 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Randy Arozarena    |         0.929 |          0.375 | PEAK          | STABLE        | DECLINING         |         0.2637 |           0.2476 |     106.7 |       104.5 |               74.2 |              | False          |               0.7938 |              0.5254 |                  103.7 |            780 |             0.225641 | UNKNOWN        |        0.522 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |
| Fernando Tatis Jr. |         0.51  |          0.377 | TYPICAL       | REGRESS       | IMPROVING         |         0.2462 |           0.2092 |     108.6 |       111.3 |              100   |              | False          |               0.7004 |              0.9674 |                   85.6 |                |                      | UNKNOWN        |        0.51  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Oneil Cruz         |         0.708 |          0.354 | ABOVE_MEDIAN  | NOISE         | MIXED             |         0.3046 |           0.3211 |     113.8 |       110.7 |               79.6 |              | False          |               0.5771 |              0.8401 |                  116.3 |                |                      | UNKNOWN        |        0.495 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Carson Benge       |         0.441 |          0.367 | TYPICAL       | NO_BASELINE   | MIXED             |                |           0.2172 |           |       102.5 |              nan   |              | False          |               0      |              0.9541 |                  106.2 |                |                      | UNKNOWN        |        0.46  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Roman Anthony      |         0.103 |          0.355 | SLUMPING      | BAD_LUCK      | IMPROVING         |         0.2792 |           0.2299 |     107.4 |       105.8 |              nan   |       0.0082 | True           |               0.9281 |              0.9999 |                   98.2 |             26 |             0.884615 | MIXED          |        0.459 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Rafael Devers |         0.609 |          0.375 | ABOVE_MEDIAN  | REGRESS       | DECLINING         |         0.2819 |           0.2893 |     108.2 |       106.5 |                100 |              | False          |               0.1549 |              0.9592 |                   86.8 |                |                      | UNKNOWN        |        0.507 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Jacob Misiorowski  | 18.473 |      2.038 |          |             |              | False       |             |                |
| Yoshinobu Yamamoto | 13.836 |      0.973 |          |             |              | False       |             |                |
| Kyle Harrison      | 12.499 |      4.547 |          |             |              | False       |             |                |
| Nolan McLean       | 11.461 |      1.543 |          |             |              | False       |             |                |
| Ranger Suarez      | 10.956 |      2.387 |          |             |              | False       |             |                |
| Sandy Alcantara    | 10.238 |      0.42  |          |             |              | False       |             |                |
| Seth Lugo          |  8.262 |     -7.931 |          |             |              | False       |             |                |
| Zac Gallen         |  7.978 |     -6.725 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Edwin Diaz    |    nan |


### U Just Lost To Edwin Diaz

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Shea Langeliers |         0.222 |          0.292 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.217  |           0.2414 |     107.8 |       105.8 |               63.1 |      -0.0119 | True           |               0.3999 |              0.4226 |                   97.9 |            680 |             0.566176 | K_DRIVEN       |        0.627 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Liam Hicks      |         0.026 |          0.276 | SLUMPING      | NOISE         | IMPROVING         |         0.1252 |           0.0873 |     100.6 |       101.1 |               64.8 |      -0.013  | True           |               0.742  |              0.3353 |                  105.8 |             89 |             0.808989 | MIXED          |        0.578 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |

**1B**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:--------------------|:---------------|:--------------|
| Christian Walker |          0.01 |          0.272 | SLUMPING      | NOISE         | DECLINING         |         0.2772 |           0.249  |     107.5 |       105.5 |               56.7 |      -0.0003 | True           |               0.522  |              0.4154 |                   98.6 |            198 |             0.732323 | HOLDING        |        0.541 | hold         |                |                     | HOLD_NOISE          | NONE           |               |
| Jake Bauers      |          1    |          0.398 | PEAK          | STABLE        | DECLINING         |         0.2188 |           0.2331 |     107.4 |       108.9 |               59.7 |              | False          |               0.0629 |              0.6527 |                  124.5 |            268 |             0.130597 | UNKNOWN        |        0.52  | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Xavier Edwards |         0.398 |          0.296 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.1043 |           0.1368 |     100.5 |       100.2 |               49.3 |       0.0063 | True           |               0.8511 |              0.1453 |                  100.5 |            401 |             0.473815 | HOLDING        |        0.555 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| TJ Rumfield   |         0     |          0.297 | SLUMPING      | NO_BASELINE   | MIXED             |                |           0.1658 |           |       102.8 |              nan   |       0.0043 | True           |               0.3485 |              0.6606 |                  106.2 |             28 |             0.785714 | UNKNOWN        |        0.544 | hold         |             |                     | HOLD_NOISE      | NONE           |               |
| Ernie Clement |         0.055 |          0.257 | SLUMPING      | STABLE        | DECLINING         |         0.1249 |           0.1181 |     100.3 |        99.6 |               71.4 |       0.0105 | True           |               0.4424 |              0.0123 |                   92.9 |            370 |             0.689189 | HOLDING        |        0.544 | hold         |             |                     | HOLD_NOISE      | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Geraldo Perdomo |         0.823 |          0.353 | HIGH          | REGRESS       | MIXED             |         0.1036 |           0.0929 |     101.7 |       101.2 |               62.9 |              | False          |               0.6991 |              0.7356 |                   82.8 |                |                      | UNKNOWN        |        0.573 | hold         |             |                     | STABLE_HIGH     | NONE           |               |
| Otto Lopez      |         0.807 |          0.353 | HIGH          | STABLE        | DECLINING         |         0.1594 |           0.186  |     104.6 |       102.2 |               81.1 |              | False          |               0.3629 |              0.7212 |                  101   |                |                      | UNKNOWN        |        0.562 | hold         |             |                     | STABLE_HIGH     | NONE           |               |

**OF**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Byron Buxton   |         0.812 |          0.371 | HIGH          | STABLE        | DECLINING         |         0.2867 |           0.2788 |     108.6 |       105.5 |               74.4 |              | False          |               0.493  |              0.8711 |                   84.6 |                |                      | UNKNOWN             |        0.62  | add          |             |                     | STABLE_HIGH            | NONE           |               |
| Chase DeLauter |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1436 |           |       104.9 |              nan   |              | False          |               0.754  |              0.8059 |                  106.2 |                |                      | UNKNOWN             |        0.579 | add          |             |                     | INSUFFICIENT_DATA      | NONE           |               |
| Mickey Moniak  |         0.51  |          0.315 | TYPICAL       | STABLE        | MIXED             |         0.2467 |           0.2372 |     106   |       105   |               69.1 |              | False          |               0.0416 |              0.4455 |                  105.5 |                |                      | UNKNOWN             |        0.567 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| JJ Bleday      |         0.803 |          0.344 | HIGH          | LEGIT         | IMPROVING         |         0.2826 |           0.2214 |     104.2 |       104.9 |              nan   |              | False          |               0.6187 |              0.5103 |                  109.7 |                |                      | UNKNOWN             |        0.562 | hold         |             |                     | STABLE_HIGH            | NONE           |               |
| Brandon Marsh  |         0.233 |          0.298 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.199  |           0.1969 |     103.7 |       104.1 |               61.9 |      -0.0109 | True           |               0.1145 |              0.294  |                  112.6 |            738 |              0.54878 | DISCIPLINE_COLLAPSE |        0.51  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name    |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:---------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Bryce Miller   | 14.465 |      1.25  |          |             |              | False       |             |                |
| Kevin Gausman  | 12.314 |     -5.681 |          |             |              | False       |             |                |
| Gavin Williams | 12.114 |    -11.331 |          |             |              | False       |             |                |
| Taj Bradley    | 11.335 |      2.407 |          |             |              | False       |             |                |
| MacKenzie Gore | 11.248 |      5.406 |          |             |              | False       |             |                |
| Gage Jump      | 10.248 |      1.071 |          |             |              | False       |             |                |
| Shane Bieber   | 10.05  |      0     |          |             |              | False       |             |                |
| Trey Yesavage  |  9.866 |      0.75  |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Mason Miller  |  154.1 |
| Gregory Soto  |   92.7 |
| Dylan Lee     |   83.8 |
| Rico Garcia   |   82.7 |


## Slump detail cards (v3 — with MC + Bayesian + historical comps)


### Matt Olson (Team Solomon, 1B)

- **Career %ile:** 15.7%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 56% of 1014 comparables bounced  | uplift: +0.014/PA

- **Bayesian shrunk gap:** +0.003  | anchor: 0.315  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.120 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 108.4→108.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **27.1%**  | Expected xwOBA: 0.366  | 95% CI: [0.352, 0.377]

- **Bayesian talent:** posterior μ = 0.333  | 95% CI: [0.271, 0.396]  | P(talent > career median) = 15.5%  | P(talent > league avg .320) = **66.4%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 431 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **56.8%**  | P(bounce 60PA) = 64.0%  | Median next-30PA xwOBA: 0.329  | 10-90 range: [0.246, 0.440]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -0.8pt (improving); chase% +0.4pt (worsening); z-contact% -2.8pt (worsening); EV90 +0.4mph (power up); hard-hit% +0.9pt (up); bat speed +1.1mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ben Rice (Late Night Bettsing, 1B)

- **Career %ile:** 1.9%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 88% of 152 comparables bounced  | uplift: +0.090/PA

- **Bayesian shrunk gap:** -0.023  | anchor: 0.351  | anchor_in_CI: No

- **xwOBACON gap:** -0.127 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 107.7→104.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **54.1%**  | Expected xwOBA: 0.384  | 95% CI: [0.375, 0.396]

- **Bayesian talent:** posterior μ = 0.354  | 95% CI: [0.301, 0.406]  | P(talent > career median) = 12.9%  | P(talent > league avg .320) = **89.7%**  | Games to 200 FP: 92

- **Historical comps (2015-25, age-matched):** 194 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **75.8%**  | P(bounce 60PA) = 79.9%  | Median next-30PA xwOBA: 0.313  | 10-90 range: [0.222, 0.393]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -1.6pt (improving); chase% +1.0pt (worsening); z-contact% -0.5pt (worsening); EV90 -2.9mph (power flagging); hard-hit% -10.1pt (down); bat speed -0.9mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — 88% historical bounce rate; shrunk gap -0.023


### Vladimir Guerrero Jr. (New York Ligers, 1B)

- **Career %ile:** 11.3%  | **Sust:** STABLE  | **Process:** IMPROVING

- **Bounce history (rh3):** 83% of 499 comparables bounced  | uplift: +0.069/PA

- **Bayesian shrunk gap:** -0.001  | anchor: 0.328  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.048 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 110.3→108.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **47.8%**  | Expected xwOBA: 0.381  | 95% CI: [0.367, 0.395]

- **Bayesian talent:** posterior μ = 0.345  | 95% CI: [0.283, 0.407]  | P(talent > career median) = 12.8%  | P(talent > league avg .320) = **78.4%**  | Games to 200 FP: 78

- **Historical comps (2015-25, age-matched):** 619 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **64.1%**  | P(bounce 60PA) = 71.6%  | Median next-30PA xwOBA: 0.319  | 10-90 range: [0.237, 0.425]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -3.7pt (improving); chase% +6.4pt (worsening); z-contact% +2.2pt (improving); EV90 -1.7mph (power flagging); hard-hit% -1.7pt (down); bat speed -0.9mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Mike Trout (Team Solomon, DH)

- **Career %ile:** 14.2%  | **Sust:** NOISE  | **Process:** IMPROVING

- **Bounce history (rh3):** 73% of 514 comparables bounced  | uplift: +0.066/PA

- **Bayesian shrunk gap:** +0.001  | anchor: 0.361  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.130 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.2→0.2  EV90 107.9→109.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **58.1%**  | Expected xwOBA: 0.403  | 95% CI: [0.384, 0.418]

- **Bayesian talent:** posterior μ = 0.402  | 95% CI: [0.341, 0.462]  | P(talent > career median) = 48.9%  | P(talent > league avg .320) = **99.6%**  | Games to 200 FP: 104

- **Historical comps (2015-25, age-matched):** 254 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.0%**  | P(bounce 60PA) = 68.9%  | Median next-30PA xwOBA: 0.334  | 10-90 range: [0.247, 0.447]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -5.0pt (improving); chase% +0.2pt (worsening); z-contact% +7.8pt (improving); EV90 +1.5mph (power up); hard-hit% +6.5pt (up); bat speed +1.0mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Liam Hicks (U Just Lost To Edwin Diaz, C)

- **Career %ile:** 2.6%  | **Sust:** NOISE  | **Process:** IMPROVING

- **Bounce history (rh3):** 65% of 88 comparables bounced  | uplift: +0.160/PA

- **Bayesian shrunk gap:** -0.013  | anchor: 0.278  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.096 (contact declining)

- **Process:** whiff% 0.1→0.1  chase% 0.2→0.3  EV90 100.6→101.1

- **MC bounce (10k sims):** P(next 30PA > career median) = **74.2%**  | Expected xwOBA: 0.319  | 95% CI: [0.311, 0.326]

- **Bayesian talent:** posterior μ = 0.311  | 95% CI: [0.270, 0.352]  | P(talent > career median) = 35.8%  | P(talent > league avg .320) = **33.5%**  | Games to 200 FP: 106

- **Historical comps (2015-25, age-matched):** 89 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **80.9%**  | P(bounce 60PA) = 88.8%  | Median next-30PA xwOBA: 0.304  | 10-90 range: [0.231, 0.381]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -3.8pt (improving); chase% +11.8pt (worsening); z-contact% +5.5pt (improving); EV90 +0.5mph (power up); hard-hit% -0.7pt (down); bat speed +1.1mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Alex Bregman (2015 Draft First Round, 3B)

- **Career %ile:** 15.1%  | **Sust:** REGRESS  | **Process:** MIXED

- **Bounce history (rh3):** 98% of 65 comparables bounced  | uplift: +0.136/PA

- **Bayesian shrunk gap:** +0.009  | anchor: 0.297  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.004 (contact intact (BABIP))

- **Process:** whiff% 0.1→0.1  chase% 0.2→0.2  EV90 102.8→100.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **50.7%**  | Expected xwOBA: 0.342  | 95% CI: [0.333, 0.352]

- **Bayesian talent:** posterior μ = 0.346  | 95% CI: [0.299, 0.394]  | P(talent > career median) = 56.9%  | P(talent > league avg .320) = **86.1%**  | Games to 200 FP: 83

- **Historical comps (2015-25, age-matched):** 369 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **60.4%**  | P(bounce 60PA) = 65.9%  | Median next-30PA xwOBA: 0.337  | 10-90 range: [0.252, 0.447]

- **Process notes:** whiff% -1.0pt (improving); chase% +2.2pt (worsening); z-contact% +0.8pt (improving); EV90 -1.9mph (power flagging); hard-hit% -8.2pt (down); bat speed -0.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Brice Turang (Treasure Island Mashers, 2B)

- **Career %ile:** 13.6%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 57% of 383 comparables bounced  | uplift: +0.022/PA

- **Bayesian shrunk gap:** +0.004  | anchor: 0.284  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.154 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 104.2→103.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **92.3%**  | Expected xwOBA: 0.322  | 95% CI: [0.311, 0.337]

- **Bayesian talent:** posterior μ = 0.300  | 95% CI: [0.241, 0.360]  | P(talent > career median) = 23.3%  | P(talent > league avg .320) = **25.9%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 688 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **61.5%**  | P(bounce 60PA) = 68.8%  | Median next-30PA xwOBA: 0.308  | 10-90 range: [0.222, 0.399]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +2.2pt (worsening); chase% +2.5pt (worsening); z-contact% -1.6pt (worsening); EV90 -0.9mph (power flagging); hard-hit% -6.1pt (down); bat speed -0.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Daylen Lile (2015 Draft First Round, RF)

- **Career %ile:** 4.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 4 comparables bounced  | uplift: +0.205/PA

- **Bayesian shrunk gap:** -0.006  | anchor: 0.293  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.012 (contact intact (BABIP))

- **Process:** whiff% 0.1→0.2  chase% 0.3→0.4  EV90 103.9→103.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **48.6%**  | Expected xwOBA: 0.340  | 95% CI: [0.329, 0.347]

- **Bayesian talent:** posterior μ = 0.327  | 95% CI: [0.279, 0.374]  | P(talent > career median) = 30.2%  | P(talent > league avg .320) = **60.7%**  | Games to 200 FP: 83

- **Historical comps (2015-25, age-matched):** 72 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **80.6%**  | P(bounce 60PA) = 86.1%  | Median next-30PA xwOBA: 0.320  | 10-90 range: [0.242, 0.397]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +2.9pt (worsening); chase% +13.9pt (worsening); z-contact% -3.9pt (worsening); EV90 -0.3mph (power flagging); hard-hit% -5.9pt (down); bat speed +1.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Paul Goldschmidt (2015 Draft First Round, 1B)

- **Career %ile:** 2.9%  | **Sust:** NOISE  | **Process:** DECLINING

- **Bayesian shrunk gap:** -0.022  | anchor: 0.350  | anchor_in_CI: No

- **xwOBACON gap:** -0.189 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.4  EV90 105.3→101.5

- **MC bounce (10k sims):** P(next 30PA > career median) = **79.2%**  | Expected xwOBA: 0.361  | 95% CI: [0.351, 0.375]

- **Bayesian talent:** posterior μ = 0.327  | 95% CI: [0.270, 0.384]  | P(talent > career median) = 11.7%  | P(talent > league avg .320) = **59.4%**  | Games to 200 FP: 110

- **Historical comps (2015-25, age-matched):** 23 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **60.9%**  | P(bounce 60PA) = 47.8%  | Median next-30PA xwOBA: 0.315  | 10-90 range: [0.235, 0.382]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +4.5pt (worsening); chase% +9.8pt (worsening); z-contact% -8.3pt (worsening); EV90 -3.8mph (power flagging); hard-hit% -14.7pt (down); bat speed -2.5mph

- **VERDICT:** SLUMP_AMBIGUOUS — mixed signals — run /slump-or-decline for full decomp


### TJ Rumfield (U Just Lost To Edwin Diaz, 3B)

- **Career %ile:** 0.0%  | **Sust:** NO_BASELINE  | **Process:** MIXED

- **Bayesian shrunk gap:** +0.004  | anchor: 0.304  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.036 (contact intact (BABIP))

- **MC bounce (10k sims):** P(next 30PA > career median) = **34.8%**  | Expected xwOBA: 0.328  | 95% CI: [0.324, 0.332]

- **Bayesian talent:** posterior μ = 0.326  | 95% CI: [0.298, 0.353]  | P(talent > career median) = 44.1%  | P(talent > league avg .320) = **66.1%**  | Games to 200 FP: 106

- **Historical comps (2015-25, age-matched):** 28 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **78.6%**  | P(bounce 60PA) = 92.9%  | Median next-30PA xwOBA: 0.312  | 10-90 range: [0.232, 0.378]

- **Process notes:** no baseline data

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ernie Clement (U Just Lost To Edwin Diaz, 3B)

- **Career %ile:** 5.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 71% of 280 comparables bounced  | uplift: +0.056/PA

- **Bayesian shrunk gap:** +0.011  | anchor: 0.260  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.066 (contact declining)

- **Process:** whiff% 0.1→0.1  chase% 0.4→0.4  EV90 100.3→99.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **44.2%**  | Expected xwOBA: 0.287  | 95% CI: [0.281, 0.292]

- **Bayesian talent:** posterior μ = 0.282  | 95% CI: [0.250, 0.315]  | P(talent > career median) = 40.2%  | P(talent > league avg .320) = **1.2%**  | Games to 200 FP: 93

- **Historical comps (2015-25, age-matched):** 370 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.9%**  | P(bounce 60PA) = 73.2%  | Median next-30PA xwOBA: 0.312  | 10-90 range: [0.229, 0.400]

- **Process notes:** whiff% -0.7pt (improving); chase% +1.0pt (worsening); z-contact% -0.5pt (worsening); EV90 -0.7mph (power flagging); hard-hit% -3.3pt (down); bat speed +2.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Christian Walker (U Just Lost To Edwin Diaz, 1B)

- **Career %ile:** 1.0%  | **Sust:** NOISE  | **Process:** DECLINING

- **Bounce history (rh3):** 57% of 926 comparables bounced  | uplift: +0.015/PA

- **Bayesian shrunk gap:** -0.000  | anchor: 0.280  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.036 (contact intact (BABIP))

- **Process:** whiff% 0.3→0.2  chase% 0.3→0.3  EV90 107.5→105.5

- **MC bounce (10k sims):** P(next 30PA > career median) = **52.2%**  | Expected xwOBA: 0.337  | 95% CI: [0.326, 0.346]

- **Bayesian talent:** posterior μ = 0.315  | 95% CI: [0.265, 0.364]  | P(talent > career median) = 19.4%  | P(talent > league avg .320) = **41.5%**  | Games to 200 FP: 99

- **Historical comps (2015-25, age-matched):** 198 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **73.2%**  | P(bounce 60PA) = 74.7%  | Median next-30PA xwOBA: 0.318  | 10-90 range: [0.232, 0.404]

- **Process notes:** whiff% -2.8pt (improving); chase% +2.3pt (worsening); z-contact% +4.4pt (improving); EV90 -2.0mph (power flagging); hard-hit% -9.5pt (down); bat speed +0.8mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Brandon Lowe (2015 Draft First Round, 2B)

- **Career %ile:** 15.1%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 54% of 582 comparables bounced  | uplift: +0.015/PA

- **Bayesian shrunk gap:** +0.005  | anchor: 0.327  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.249 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 106.4→107.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **75.8%**  | Expected xwOBA: 0.344  | 95% CI: [0.334, 0.353]

- **Bayesian talent:** posterior μ = 0.336  | 95% CI: [0.288, 0.384]  | P(talent > career median) = 38.0%  | P(talent > league avg .320) = **74.3%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 785 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **56.3%**  | P(bounce 60PA) = 58.2%  | Median next-30PA xwOBA: 0.306  | 10-90 range: [0.224, 0.407]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +0.1pt (worsening); chase% +1.7pt (worsening); z-contact% +2.5pt (improving); EV90 +0.6mph (power up); hard-hit% +0.9pt (up); bat speed -1.0mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Jackson Merrill (Late Night Bettsing, CF)

- **Career %ile:** 8.9%  | **Sust:** REGRESS  | **Process:** IMPROVING

- **Bounce history (rh3):** 100% of 13 comparables bounced  | uplift: +0.198/PA

- **Bayesian shrunk gap:** -0.012  | anchor: 0.308  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.012 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.1  chase% 0.4→0.3  EV90 105.3→103.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **99.6%**  | Expected xwOBA: 0.351  | 95% CI: [0.342, 0.365]

- **Bayesian talent:** posterior μ = 0.323  | 95% CI: [0.265, 0.380]  | P(talent > career median) = 17.0%  | P(talent > league avg .320) = **53.8%**  | Games to 200 FP: 89

- **Historical comps (2015-25, age-matched):** 207 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **66.2%**  | P(bounce 60PA) = 74.4%  | Median next-30PA xwOBA: 0.298  | 10-90 range: [0.219, 0.399]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -8.0pt (improving); chase% -3.8pt (improving); z-contact% +7.5pt (improving); EV90 -1.9mph (power flagging); hard-hit% -2.0pt (down); bat speed +1.1mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### JJ Wetherholt (Team Solomon, SS)

- **Career %ile:** 7.3%  | **Sust:** NO_BASELINE  | **Process:** MIXED

- **Bayesian shrunk gap:** -0.008  | anchor: 0.356  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.038 (contact intact (BABIP))

- **MC bounce (10k sims):** P(next 30PA > career median) = **62.0%**  | Expected xwOBA: 0.361  | 95% CI: [0.358, 0.364]

- **Bayesian talent:** posterior μ = 0.361  | 95% CI: [0.341, 0.382]  | P(talent > career median) = 49.2%  | P(talent > league avg .320) = **100.0%**  | Games to 200 FP: 106

- **Historical comps (2015-25, age-matched):** 32 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **75.0%**  | P(bounce 60PA) = 84.4%  | Median next-30PA xwOBA: 0.315  | 10-90 range: [0.232, 0.390]

- **Process notes:** no baseline data

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Seiya Suzuki (Team Solomon, DH)

- **Career %ile:** 7.4%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 71% of 370 comparables bounced  | uplift: +0.071/PA

- **Bayesian shrunk gap:** -0.007  | anchor: 0.295  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.017 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 107.0→106.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **76.1%**  | Expected xwOBA: 0.348  | 95% CI: [0.338, 0.358]

- **Bayesian talent:** posterior μ = 0.335  | 95% CI: [0.286, 0.384]  | P(talent > career median) = 30.5%  | P(talent > league avg .320) = **72.4%**  | Games to 200 FP: 94

- **Historical comps (2015-25, age-matched):** 392 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **66.6%**  | P(bounce 60PA) = 71.9%  | Median next-30PA xwOBA: 0.308  | 10-90 range: [0.224, 0.408]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +2.6pt (worsening); chase% +1.3pt (worsening); z-contact% -0.7pt (worsening); EV90 -0.6mph (power flagging); hard-hit% -6.3pt (down); bat speed -0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ian Happ (2015 Draft First Round, LF)

- **Career %ile:** 3.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 64% of 827 comparables bounced  | uplift: +0.050/PA

- **Bayesian shrunk gap:** -0.001  | anchor: 0.292  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.181 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.2→0.2  EV90 105.7→105.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **36.2%**  | Expected xwOBA: 0.341  | 95% CI: [0.329, 0.351]

- **Bayesian talent:** posterior μ = 0.315  | 95% CI: [0.262, 0.368]  | P(talent > career median) = 16.8%  | P(talent > league avg .320) = **42.3%**  | Games to 200 FP: 97

- **Historical comps (2015-25, age-matched):** 364 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.4%**  | P(bounce 60PA) = 75.0%  | Median next-30PA xwOBA: 0.324  | 10-90 range: [0.232, 0.434]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +6.5pt (worsening); chase% +0.6pt (worsening); z-contact% -5.1pt (worsening); EV90 -0.4mph (power flagging); hard-hit% -5.9pt (down); bat speed +1.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Wilyer Abreu (Treasure Island Mashers, RF)

- **Career %ile:** 1.8%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 50% of 216 comparables bounced  | uplift: +0.001/PA

- **Bayesian shrunk gap:** -0.014  | anchor: 0.300  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.093 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.4  EV90 107.5→104.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **51.9%**  | Expected xwOBA: 0.333  | 95% CI: [0.325, 0.342]

- **Bayesian talent:** posterior μ = 0.315  | 95% CI: [0.271, 0.358]  | P(talent > career median) = 19.9%  | P(talent > league avg .320) = **40.1%**  | Games to 200 FP: 97

- **Historical comps (2015-25, age-matched):** 185 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **74.6%**  | P(bounce 60PA) = 78.4%  | Median next-30PA xwOBA: 0.314  | 10-90 range: [0.221, 0.394]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +1.0pt (worsening); chase% +6.4pt (worsening); z-contact% -1.2pt (worsening); EV90 -3.2mph (power flagging); hard-hit% -9.0pt (down); bat speed -0.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ryan O'Hearn (Boone's Bad Bullpen, 1B)

- **Career %ile:** 4.6%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 59% of 544 comparables bounced  | uplift: +0.021/PA

- **Bayesian shrunk gap:** +0.018  | anchor: 0.260  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.230 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.3  EV90 103.1→103.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **50.6%**  | Expected xwOBA: 0.335  | 95% CI: [0.324, 0.345]

- **Bayesian talent:** posterior μ = 0.323  | 95% CI: [0.271, 0.375]  | P(talent > career median) = 32.3%  | P(talent > league avg .320) = **54.5%**  | Games to 200 FP: 94

- **Historical comps (2015-25, age-matched):** 362 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **67.1%**  | P(bounce 60PA) = 72.1%  | Median next-30PA xwOBA: 0.313  | 10-90 range: [0.234, 0.404]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +1.2pt (worsening); chase% +7.7pt (worsening); z-contact% +3.4pt (improving); EV90 +0.7mph (power up); hard-hit% -3.2pt (down); bat speed -0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Corey Seager (Team Solomon, SS)

- **Career %ile:** 17.8%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 63 comparables bounced  | uplift: +0.171/PA

- **Bayesian shrunk gap:** +0.008  | anchor: 0.328  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.103 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.2→0.3  EV90 108.0→105.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **67.3%**  | Expected xwOBA: 0.385  | 95% CI: [0.373, 0.397]

- **Bayesian talent:** posterior μ = 0.374  | 95% CI: [0.307, 0.440]  | P(talent > career median) = 37.0%  | P(talent > league avg .320) = **94.2%**  | Games to 200 FP: 77

- **Historical comps (2015-25, age-matched):** 525 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **62.1%**  | P(bounce 60PA) = 66.7%  | Median next-30PA xwOBA: 0.338  | 10-90 range: [0.245, 0.445]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +7.3pt (worsening); chase% +3.6pt (worsening); z-contact% -10.5pt (worsening); EV90 -2.7mph (power flagging); hard-hit% -9.4pt (down); bat speed -0.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### George Springer (Frendy's Fantastic Team, DH)

- **Career %ile:** 13.3%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 96% of 281 comparables bounced  | uplift: +0.179/PA

- **Bayesian shrunk gap:** -0.020  | anchor: 0.328  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.062 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 107.2→105.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **58.9%**  | Expected xwOBA: 0.357  | 95% CI: [0.347, 0.371]

- **Bayesian talent:** posterior μ = 0.349  | 95% CI: [0.289, 0.410]  | P(talent > career median) = 40.6%  | P(talent > league avg .320) = **82.8%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 133 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **54.1%**  | P(bounce 60PA) = 54.1%  | Median next-30PA xwOBA: 0.326  | 10-90 range: [0.248, 0.435]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -4.9pt (improving); chase% +2.9pt (worsening); z-contact% +4.0pt (improving); EV90 -2.2mph (power flagging); hard-hit% -3.9pt (down); bat speed -0.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Jose Altuve (Team Solomon, 2B)

- **Career %ile:** 0.1%  | **Sust:** REGRESS  | **Process:** MIXED

- **Bounce history (rh3):** 97% of 205 comparables bounced  | uplift: +0.113/PA

- **Bayesian shrunk gap:** -0.016  | anchor: 0.273  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.138 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.4→0.3  EV90 102.4→101.7

- **MC bounce (10k sims):** P(next 30PA > career median) = **40.9%**  | Expected xwOBA: 0.327  | 95% CI: [0.316, 0.339]

- **Bayesian talent:** posterior μ = 0.296  | 95% CI: [0.241, 0.351]  | P(talent > career median) = 13.4%  | P(talent > league avg .320) = **19.4%**  | Games to 200 FP: 87

- **Historical comps (2015-25, age-matched):** 85 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.5%**  | P(bounce 60PA) = 69.4%  | Median next-30PA xwOBA: 0.323  | 10-90 range: [0.245, 0.442]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% +9.5pt (worsening); chase% -4.2pt (improving); z-contact% -4.6pt (worsening); EV90 -0.7mph (power flagging); hard-hit% +1.9pt (up); bat speed -0.9mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Xander Bogaerts (Treasure Island Mashers, SS)

- **Career %ile:** 17.8%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 78% of 677 comparables bounced  | uplift: +0.073/PA

- **Bayesian shrunk gap:** -0.000  | anchor: 0.294  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.028 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 105.6→106.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **60.1%**  | Expected xwOBA: 0.327  | 95% CI: [0.318, 0.337]

- **Bayesian talent:** posterior μ = 0.320  | 95% CI: [0.269, 0.370]  | P(talent > career median) = 38.9%  | P(talent > league avg .320) = **49.2%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 211 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **58.8%**  | P(bounce 60PA) = 59.2%  | Median next-30PA xwOBA: 0.345  | 10-90 range: [0.262, 0.458]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +5.5pt (worsening); chase% -2.8pt (improving); z-contact% -2.2pt (worsening); EV90 +1.0mph (power up); hard-hit% +5.5pt (up); bat speed -0.9mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Trea Turner (Team Solomon, SS)

- **Career %ile:** 7.7%  | **Sust:** REGRESS  | **Process:** MIXED

- **Bounce history (rh3):** 81% of 167 comparables bounced  | uplift: +0.100/PA

- **Bayesian shrunk gap:** +0.002  | anchor: 0.286  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.114 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.4  EV90 104.2→103.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **39.4%**  | Expected xwOBA: 0.330  | 95% CI: [0.320, 0.342]

- **Bayesian talent:** posterior μ = 0.309  | 95% CI: [0.254, 0.363]  | P(talent > career median) = 22.2%  | P(talent > league avg .320) = **34.1%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 332 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **61.7%**  | P(bounce 60PA) = 70.5%  | Median next-30PA xwOBA: 0.337  | 10-90 range: [0.249, 0.454]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +1.6pt (worsening); chase% +5.1pt (worsening); z-contact% +2.6pt (improving); EV90 -0.3mph (power flagging); hard-hit% +1.9pt (up); bat speed +0.8mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Zach Neto (Boone's Bad Bullpen, SS)

- **Career %ile:** 12.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 98% of 42 comparables bounced  | uplift: +0.192/PA

- **Bayesian shrunk gap:** -0.007  | anchor: 0.308  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.027 (contact intact (BABIP))

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.4  EV90 105.7→104.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **32.8%**  | Expected xwOBA: 0.326  | 95% CI: [0.317, 0.334]

- **Bayesian talent:** posterior μ = 0.317  | 95% CI: [0.276, 0.358]  | P(talent > career median) = 32.6%  | P(talent > league avg .320) = **44.1%**  | Games to 200 FP: 99

- **Historical comps (2015-25, age-matched):** 525 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.6%**  | P(bounce 60PA) = 67.4%  | Median next-30PA xwOBA: 0.308  | 10-90 range: [0.223, 0.401]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% +2.2pt (worsening); chase% +6.2pt (worsening); z-contact% +0.2pt (improving); EV90 -1.5mph (power flagging); hard-hit% -8.5pt (down); bat speed -0.8mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Nolan Arenado (Treasure Island Mashers, 3B)

- **Career %ile:** 5.1%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 93% of 138 comparables bounced  | uplift: +0.107/PA

- **Bayesian shrunk gap:** -0.006  | anchor: 0.293  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.041 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.4  EV90 101.6→101.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **93.7%**  | Expected xwOBA: 0.319  | 95% CI: [0.310, 0.331]

- **Bayesian talent:** posterior μ = 0.286  | 95% CI: [0.233, 0.340]  | P(talent > career median) = 11.3%  | P(talent > league avg .320) = **10.9%**  | Games to 200 FP: 96

- **Historical comps (2015-25, age-matched):** 133 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **60.9%**  | P(bounce 60PA) = 69.9%  | Median next-30PA xwOBA: 0.324  | 10-90 range: [0.242, 0.439]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +8.2pt (worsening); chase% +1.2pt (worsening); z-contact% -6.3pt (worsening); EV90 -0.2mph (power flagging); hard-hit% +3.6pt (up); bat speed -0.7mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Roman Anthony (Treasure Island Mashers, RF)

- **Career %ile:** 10.3%  | **Sust:** BAD_LUCK  | **Process:** IMPROVING

- **Bayesian shrunk gap:** +0.008  | anchor: 0.343  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.136 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.2→0.3  EV90 107.4→105.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **92.8%**  | Expected xwOBA: 0.372  | 95% CI: [0.367, 0.376]

- **Bayesian talent:** posterior μ = 0.374  | 95% CI: [0.345, 0.403]  | P(talent > career median) = 54.6%  | P(talent > league avg .320) = **100.0%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 26 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **88.5%**  | P(bounce 60PA) = 100.0%  | Median next-30PA xwOBA: 0.324  | 10-90 range: [0.253, 0.384]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -4.9pt (improving); chase% +5.6pt (worsening); z-contact% +5.8pt (improving); EV90 -1.6mph (power flagging); hard-hit% +2.3pt (up); bat speed +1.5mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Kazuma Okamoto (Boone's Bad Bullpen, 3B)

- **Career %ile:** 2.3%  | **Sust:** NO_BASELINE  | **Process:** MIXED

- **Bayesian shrunk gap:** -0.010  | anchor: 0.294  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.023 (contact intact (BABIP))

- **MC bounce (10k sims):** P(next 30PA > career median) = **0.0%**  | Expected xwOBA: 0.332  | 95% CI: [0.323, 0.339]

- **Bayesian talent:** posterior μ = 0.321  | 95% CI: [0.272, 0.371]  | P(talent > career median) = 33.5%  | P(talent > league avg .320) = **52.1%**  | Games to 200 FP: 106

- **Historical comps (2015-25, age-matched):** 26 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **84.6%**  | P(bounce 60PA) = 80.8%  | Median next-30PA xwOBA: 0.321  | 10-90 range: [0.256, 0.411]

- **Process notes:** no baseline data

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Alejandro Kirk (Treasure Island Mashers, C)

- **Career %ile:** 16.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bayesian shrunk gap:** -0.003  | anchor: 0.257  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.016 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.1  chase% 0.3→0.3  EV90 106.6→101.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **95.2%**  | Expected xwOBA: 0.344  | 95% CI: [0.335, 0.358]

- **Bayesian talent:** posterior μ = 0.316  | 95% CI: [0.255, 0.376]  | P(talent > career median) = 18.3%  | P(talent > league avg .320) = **44.7%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 662 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **61.0%**  | P(bounce 60PA) = 64.2%  | Median next-30PA xwOBA: 0.309  | 10-90 range: [0.226, 0.395]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -2.3pt (improving); chase% +4.2pt (worsening); z-contact% +0.0pt (improving); EV90 -5.6mph (power flagging); hard-hit% -33.5pt (down); bat speed -1.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Dansby Swanson (2015 Draft First Round, SS)

- **Career %ile:** 2.4%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 68% of 936 comparables bounced  | uplift: +0.041/PA

- **Bayesian shrunk gap:** +0.020  | anchor: 0.233  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.317 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 104.7→103.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **46.3%**  | Expected xwOBA: 0.331  | 95% CI: [0.317, 0.341]

- **Bayesian talent:** posterior μ = 0.323  | 95% CI: [0.271, 0.376]  | P(talent > career median) = 39.1%  | P(talent > league avg .320) = **55.0%**  | Games to 200 FP: 108

- **Historical comps (2015-25, age-matched):** 264 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.2%**  | P(bounce 60PA) = 79.5%  | Median next-30PA xwOBA: 0.335  | 10-90 range: [0.243, 0.451]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +3.7pt (worsening); chase% +4.8pt (worsening); z-contact% -3.7pt (worsening); EV90 -0.9mph (power flagging); hard-hit% -4.7pt (down); bat speed +0.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Christian Yelich (Frendy's Fantastic Team, DH)

- **Career %ile:** 7.0%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 92% of 487 comparables bounced  | uplift: +0.133/PA

- **Bayesian shrunk gap:** -0.007  | anchor: 0.304  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.079 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.3→0.3  EV90 106.7→102.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **46.2%**  | Expected xwOBA: 0.353  | 95% CI: [0.342, 0.369]

- **Bayesian talent:** posterior μ = 0.335  | 95% CI: [0.270, 0.400]  | P(talent > career median) = 29.5%  | P(talent > league avg .320) = **67.8%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 186 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **66.1%**  | P(bounce 60PA) = 68.8%  | Median next-30PA xwOBA: 0.346  | 10-90 range: [0.256, 0.449]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +6.8pt (worsening); chase% -0.1pt (improving); z-contact% -7.2pt (worsening); EV90 -3.8mph (power flagging); hard-hit% -3.0pt (down); bat speed +0.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Cal Raleigh (Team Solomon, C)

- **Career %ile:** 9.3%  | **Sust:** REGRESS  | **Process:** IMPROVING

- **Bounce history (rh3):** 95% of 108 comparables bounced  | uplift: +0.189/PA

- **Bayesian shrunk gap:** +0.000  | anchor: 0.301  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.016 (contact intact (BABIP))

- **Process:** whiff% 0.3→0.2  chase% 0.3→0.3  EV90 107.0→105.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **77.2%**  | Expected xwOBA: 0.344  | 95% CI: [0.333, 0.353]

- **Bayesian talent:** posterior μ = 0.337  | 95% CI: [0.280, 0.393]  | P(talent > career median) = 39.9%  | P(talent > league avg .320) = **71.7%**  | Games to 200 FP: 87

- **Historical comps (2015-25, age-matched):** 711 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.0%**  | P(bounce 60PA) = 69.2%  | Median next-30PA xwOBA: 0.309  | 10-90 range: [0.229, 0.407]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% -2.6pt (improving); chase% -4.1pt (improving); z-contact% +0.8pt (improving); EV90 -1.2mph (power flagging); hard-hit% -20.6pt (down); bat speed -1.7mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


## PEAK player validator (v3 — with survival curves)


### Ketel Marte (2015 Draft First Round, 2B) — MIXED

- **Career %ile:** 98.0%  | **rh3:** 0.683  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.389  | P(true talent > .320) = **98.6%**  | P(true talent > career median) = 81.7%

- **Historical comps:** 189 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 20.6%  | Median next-30PA xwOBA: 0.356

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: z_contact% +4.5pt

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Alec Burleson (Late Night Bettsing, LF) — MIXED

- **Career %ile:** 99.7%  | **rh3:** 0.617  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.366  | P(true talent > .320) = **95.8%**  | P(true talent > career median) = 74.5%

- **Historical comps:** 361 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 16.6%  | Median next-30PA xwOBA: 0.306

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: xwOBAcon +0.054

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Pete Alonso (New York Ligers, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 96.0%  | **rh3:** 0.613  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.390  | P(true talent > .320) = **99.5%**  | P(true talent > career median) = 80.2%

- **Historical comps:** 475 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 21.9%  | Median next-30PA xwOBA: 0.348

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Brandon Nimmo (Team Solomon, LF) — PROCESS_DRIVEN

- **Career %ile:** 96.2%  | **rh3:** 0.595  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.356  | P(true talent > .320) = **92.2%**  | P(true talent > career median) = 71.2%

- **Historical comps:** 331 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 22.1%  | Median next-30PA xwOBA: 0.349

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- whiff% -2.8pt — z_contact% +3.4pt — xwOBAcon +0.071 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Hunter Goodman (New York Ligers, C) — MIXED

- **Career %ile:** 94.7%  | **rh3:** 0.583  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.326  | P(true talent > .320) = **60.9%**  | P(true talent > career median) = 71.8%

- **Historical comps:** 345 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 15.7%  | Median next-30PA xwOBA: 0.296

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: bat_speed +1.2mph; xwOBAcon +0.051

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Pete Crow-Armstrong (Boone's Bad Bullpen, CF) — PROCESS_DRIVEN

- **Career %ile:** 96.2%  | **rh3:** 0.551  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.351  | P(true talent > .320) = **84.0%**  | P(true talent > career median) = 81.2%

- **Historical comps:** 214 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 15.4%  | Median next-30PA xwOBA: 0.293

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- bat_speed +1.5mph — chase% -5.0pt — z_contact% +2.1pt — xwOBAcon +0.043 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Isaac Paredes (Late Night Bettsing, 3B) — OUTCOME_DRIVEN

- **Career %ile:** 90.7%  | **rh3:** 0.550  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.313  | P(true talent > .320) = **36.1%**  | P(true talent > career median) = 51.2%

- **Historical comps:** 723 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 20.1%  | Median next-30PA xwOBA: 0.315

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Casey Schmitt (Team Solomon, 2B) — PROCESS_DRIVEN

- **Career %ile:** 97.5%  | **rh3:** 0.543  | **Sust:** MIXED

- **Bayesian talent:** posterior μ = 0.357  | P(true talent > .320) = **90.3%**  | P(true talent > career median) = 86.8%

- **Historical comps:** 237 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 10.5%  | Median next-30PA xwOBA: 0.289

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- whiff% -3.7pt — z_contact% +3.3pt — xwOBAcon +0.047 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Randy Arozarena (Treasure Island Mashers, LF) — MIXED

- **Career %ile:** 92.9%  | **rh3:** 0.522  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.322  | P(true talent > .320) = **52.5%**  | P(true talent > career median) = 46.6%

- **Historical comps:** 780 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 22.6%  | Median next-30PA xwOBA: 0.328

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: whiff% -2.9pt

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Jake Bauers (U Just Lost To Edwin Diaz, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 100.0%  | **rh3:** 0.520  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.332  | P(true talent > .320) = **65.3%**  | P(true talent > career median) = 59.3%

- **Historical comps:** 268 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 13.1%  | Median next-30PA xwOBA: 0.303

- **Peak survival:** P(still PEAK at +30PA) = **89.2%** [89.0%, 89.5%]  | +60PA = 76.2% [75.9%, 76.5%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Kody Clemens (New York Ligers, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 90.7%  | **rh3:** 0.520  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.318  | P(true talent > .320) = **46.5%**  | P(true talent > career median) = 58.9%

- **Historical comps:** 257 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 17.1%  | Median next-30PA xwOBA: 0.287

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Jac Caglianone (Boone's Bad Bullpen, RF) — PROCESS_DRIVEN

- **Career %ile:** 94.4%  | **rh3:** 0.403  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.337  | P(true talent > .320) = **79.1%**  | P(true talent > career median) = 48.8%

- **Historical comps:** 64 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 1.6%  | Median next-30PA xwOBA: 0.251

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- EV90 +2.0mph — chase% -3.3pt — xwOBAcon +0.104 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


## SP velo flags (> 1.0 mph drop, injury/fatigue signal)

_No SP velo flags this week._

## Statistical confidence summary

_For each slumper, the convergence of 4 independent statistical tests:_

| Player | MC P(bounce) | Bayes P(>avg) | Hist comps | Hist P(bounce 30PA) | Injury | Verdict |

|---|---|---|---|---|---|---|

| Matt Olson | 27.1% | 66.4% | 431 | 56.8% | NONE | HOLD_NOISE |

| Ben Rice | 54.1% | 89.7% | 194 | 75.8% | NONE | CONSENSUS_HOLD_BOUNCE |

| Vladimir Guerrero Jr. | 47.8% | 78.4% | 619 | 64.1% | NONE | CONSENSUS_HOLD_BOUNCE |

| Mike Trout | 58.1% | 99.6% | 254 | 65.0% | NONE | CONSENSUS_HOLD_BOUNCE |

| Liam Hicks | 74.2% | 33.5% | 89 | 80.9% | NONE | CONSENSUS_HOLD_BOUNCE |

| Alex Bregman | 50.7% | 86.1% | 369 | 60.4% | NONE | HOLD_NOISE |

| Brice Turang | 92.3% | 25.9% | 688 | 61.5% | NONE | HOLD_NOISE |

| Daylen Lile | 48.6% | 60.7% | 72 | 80.6% | NONE | HOLD_NOISE |

| Paul Goldschmidt | 79.2% | 59.4% | 23 | 60.9% | NONE | SLUMP_AMBIGUOUS |

| TJ Rumfield | 34.8% | 66.1% | 28 | 78.6% | NONE | HOLD_NOISE |

| Ernie Clement | 44.2% | 1.2% | 370 | 68.9% | NONE | HOLD_NOISE |

| Christian Walker | 52.2% | 41.5% | 198 | 73.2% | NONE | HOLD_NOISE |

| Brandon Lowe | 75.8% | 74.3% | 785 | 56.3% | NONE | HOLD_NOISE |

| Jackson Merrill | 99.6% | 53.8% | 207 | 66.2% | NONE | CONSENSUS_HOLD_BOUNCE |

| JJ Wetherholt | 62.0% | 100.0% | 32 | 75.0% | NONE | HOLD_NOISE |

| Seiya Suzuki | 76.1% | 72.4% | 392 | 66.6% | NONE | HOLD_NOISE |

| Ian Happ | 36.2% | 42.3% | 364 | 68.4% | NONE | HOLD_NOISE |

| Wilyer Abreu | 51.9% | 40.1% | 185 | 74.6% | NONE | HOLD_NOISE |

| Ryan O'Hearn | 50.6% | 54.5% | 362 | 67.1% | NONE | HOLD_NOISE |

| Corey Seager | 67.3% | 94.2% | 525 | 62.1% | NONE | HOLD_NOISE |

| George Springer | 58.9% | 82.8% | 133 | 54.1% | NONE | HOLD_NOISE |

| Jose Altuve | 40.9% | 19.4% | 85 | 63.5% | NONE | HOLD_NOISE |

| Xander Bogaerts | 60.1% | 49.2% | 211 | 58.8% | NONE | HOLD_NOISE |

| Trea Turner | 39.4% | 34.1% | 332 | 61.7% | NONE | HOLD_NOISE |

| Zach Neto | 32.8% | 44.1% | 525 | 63.6% | NONE | HOLD_NOISE |

| Nolan Arenado | 93.7% | 10.9% | 133 | 60.9% | NONE | HOLD_NOISE |

| Roman Anthony | 92.8% | 100.0% | 26 | 88.5% | NONE | CONSENSUS_HOLD_BOUNCE |

| Kazuma Okamoto | 0.0% | 52.1% | 26 | 84.6% | NONE | HOLD_NOISE |

| Alejandro Kirk | 95.2% | 44.7% | 662 | 61.0% | NONE | HOLD_NOISE |

| Dansby Swanson | 46.3% | 55.0% | 264 | 68.2% | NONE | HOLD_NOISE |

| Christian Yelich | 46.2% | 67.8% | 186 | 66.1% | NONE | HOLD_NOISE |

| Cal Raleigh | 77.2% | 71.7% | 711 | 65.0% | NONE | CONSENSUS_HOLD_BOUNCE |


## Waiver wire targets — slumpers bouncing back

_Statistically supported bounce candidates on rival rosters — watch for drops or offer a low-cost add._

| team_name                 | player_name     | position   |   career_%ile | form_bucket   | process_verdict   |   mc_p_bounce_median |   bayes_p_above_avg |   hist_p_bounce_30pa |   rh3_per_pa |   replacement_delta | cross_verdict         |
|:--------------------------|:----------------|:-----------|--------------:|:--------------|:------------------|---------------------:|--------------------:|---------------------:|-------------:|--------------------:|:----------------------|
| Team Solomon              | Matt Olson      | 1B         |         0.157 | SLUMPING      | MIXED             |               0.2705 |              0.6641 |             0.568445 |        0.636 |               0.056 | HOLD_NOISE            |
| Late Night Bettsing       | Ben Rice        | 1B         |         0.019 | SLUMPING      | DECLINING         |               0.5407 |              0.8972 |             0.757732 |        0.609 |               0.03  | CONSENSUS_HOLD_BOUNCE |
| Team Solomon              | Mike Trout      | DH         |         0.142 | SLUMPING      | IMPROVING         |               0.5811 |              0.9959 |             0.649606 |        0.579 |               0.07  | CONSENSUS_HOLD_BOUNCE |
| U Just Lost To Edwin Diaz | Liam Hicks      | C          |         0.026 | SLUMPING      | IMPROVING         |               0.742  |              0.3353 |             0.808989 |        0.578 |               0.01  | CONSENSUS_HOLD_BOUNCE |
| 2015 Draft First Round    | Alex Bregman    | 3B         |         0.151 | SLUMPING      | MIXED             |               0.5073 |              0.8606 |             0.604336 |        0.563 |               0.032 | HOLD_NOISE            |
| Treasure Island Mashers   | Brice Turang    | 2B         |         0.136 | SLUMPING      | DECLINING         |               0.9228 |              0.2585 |             0.614826 |        0.559 |               0.035 | HOLD_NOISE            |
| Late Night Bettsing       | Kyle Tucker     | RF         |         0.236 | BELOW_MEDIAN  | DECLINING         |               0.5613 |              0.9617 |             0.527331 |        0.558 |               0.048 | BOUNCING_BACK         |
| 2015 Draft First Round    | Daylen Lile     | RF         |         0.045 | SLUMPING      | DECLINING         |               0.4859 |              0.6066 |             0.805556 |        0.552 |               0.042 | HOLD_NOISE            |
| U Just Lost To Edwin Diaz | Ernie Clement   | 3B         |         0.055 | SLUMPING      | DECLINING         |               0.4424 |              0.0123 |             0.689189 |        0.544 |               0.02  | HOLD_NOISE            |
| 2015 Draft First Round    | Brandon Lowe    | 2B         |         0.151 | SLUMPING      | MIXED             |               0.7576 |              0.7428 |             0.563057 |        0.54  |               0.016 | HOLD_NOISE            |
| Late Night Bettsing       | Jackson Merrill | CF         |         0.089 | SLUMPING      | IMPROVING         |               0.9962 |              0.5377 |             0.661836 |        0.539 |               0.03  | CONSENSUS_HOLD_BOUNCE |
| Team Solomon              | JJ Wetherholt   | SS         |         0.073 | SLUMPING      | MIXED             |               0.6195 |              1      |             0.75     |        0.539 |               0.015 | HOLD_NOISE            |
| Team Solomon              | Seiya Suzuki    | DH         |         0.074 | SLUMPING      | DECLINING         |               0.7608 |              0.7237 |             0.665816 |        0.533 |               0.024 | HOLD_NOISE            |
| 2015 Draft First Round    | Ian Happ        | LF         |         0.035 | SLUMPING      | DECLINING         |               0.3622 |              0.4233 |             0.684066 |        0.528 |               0.019 | HOLD_NOISE            |
| Treasure Island Mashers   | Wilyer Abreu    | RF         |         0.018 | SLUMPING      | DECLINING         |               0.5188 |              0.4011 |             0.745946 |        0.527 |               0.018 | HOLD_NOISE            |
| Boone's Bad Bullpen       | Ryan O'Hearn    | 1B         |         0.046 | SLUMPING      | MIXED             |               0.5059 |              0.5446 |             0.671271 |        0.525 |               0.016 | HOLD_NOISE            |
| Frendy's Fantastic Team   | George Springer | DH         |         0.133 | SLUMPING      | DECLINING         |               0.5894 |              0.828  |             0.541353 |        0.518 |               0.118 | HOLD_NOISE            |

## FA add candidates

_Available free agents with model projections. Ownership < 90% in this 8-team league._

### FA hitters (top 15 by rh3 projection)

| player_name        | position   |   owned_% |   xfp_rh3_per_pa | rh3_signal   | form_bucket   | process_verdict   |   career_%ile | cross_verdict   |
|:-------------------|:-----------|----------:|-----------------:|:-------------|:--------------|:------------------|--------------:|:----------------|
| Spencer Horwitz    | 1B         |       9.4 |            0.637 | hold         | N/A           |                   |           nan |                 |
| Julio Rodriguez    | C          |       0.1 |            0.632 | add          | N/A           |                   |           nan |                 |
| Carlos Cortes      | RF         |       5.2 |            0.598 | add          | N/A           |                   |           nan |                 |
| Ryan Jeffers       | C          |      26.4 |            0.597 | hold         | N/A           |                   |           nan |                 |
| Moises Ballesteros | DH         |       2.1 |            0.596 | hold         | N/A           |                   |           nan |                 |
| Jared Young        | DH         |       0.3 |            0.577 | hold         | N/A           |                   |           nan |                 |
| Vinnie Pasquantino | 1B         |      46.9 |            0.573 | hold         | N/A           |                   |           nan |                 |
| Gabriel Moreno     | C          |      37.1 |            0.572 | hold         | N/A           |                   |           nan |                 |
| Randal Grichuk     | RF         |       0.2 |            0.564 | hold         | N/A           |                   |           nan |                 |
| Colson Montgomery  | SS         |      40.2 |            0.557 | hold         | N/A           |                   |           nan |                 |
| Trent Grisham      | CF         |      25.2 |            0.556 | hold         | N/A           |                   |           nan |                 |
| Javier Sanoja      | LF         |       9.7 |            0.554 | hold         | N/A           |                   |           nan |                 |
| Bryce Eldridge     | DH         |      13.8 |            0.546 | hold         | N/A           |                   |           nan |                 |
| Miguel Andujar     | 3B         |       1.5 |            0.543 | hold         | N/A           |                   |           nan |                 |
| Daulton Varsho     | CF         |      11.3 |            0.538 | hold         | N/A           |                   |           nan |                 |

### FA starting pitchers (top 10 by rp3 projection)

| player_name           |   owned_% |   rp3_proj/start |   form_gap |
|:----------------------|----------:|-----------------:|-----------:|
| Blake Snell           |      66   |            13.02 |       0    |
| Spencer Schwellenbach |      11.6 |            12.75 |       0    |
| Nick Pivetta          |      56.5 |            12.39 |       0    |
| Ronel Blanco          |       0.3 |            12.11 |       0    |
| Corbin Burnes         |       4.8 |            12.06 |       0    |
| Cole Ragans           |      58.6 |            11.62 |       0    |
| Pablo Lopez           |       3   |            11.46 |       0    |
| Eury Perez            |      62.3 |            11.38 |       1.61 |
| Justin Steele         |       3.4 |            11.34 |       0    |
| Logan Henderson       |      14.9 |            11.07 |       0    |

### FA relief pitchers (top 10 by rprs2 projection)

| player_name         |   owned_% |   rprs2_proj_ros |
|:--------------------|----------:|-----------------:|
| Samy Natera Jr.     |       0.1 |            114.9 |
| Luke Weaver         |       5.4 |            104   |
| Cole Sands          |       0.3 |            101.8 |
| Graham Ashcraft     |       0.9 |             97.9 |
| Kenley Jansen       |      37.2 |             97.6 |
| Tyler Zuber         |       0   |             96   |
| Enyel De Los Santos |       0.3 |             95.4 |
| Jordan Romano       |       2.7 |             93.5 |
| Alex Vesia          |      10.9 |             90.3 |
| Jeff Hoffman        |      40.5 |             89.4 |

## Watch list — your players showing peak regression risk

_Consider dropping or monitoring before value fades._

_None._

---

## Optional — trade context (if relevant)


### Trade targets — rival slumpers to buy

| team_name                 | player_name     | position   |   career_%ile | form_bucket   | process_verdict   |   mc_p_bounce_median |   bayes_p_above_avg |   hist_p_bounce_30pa |   rh3_per_pa |   replacement_delta | cross_verdict         |
|:--------------------------|:----------------|:-----------|--------------:|:--------------|:------------------|---------------------:|--------------------:|---------------------:|-------------:|--------------------:|:----------------------|
| Team Solomon              | Matt Olson      | 1B         |         0.157 | SLUMPING      | MIXED             |               0.2705 |              0.6641 |             0.568445 |        0.636 |               0.056 | HOLD_NOISE            |
| Late Night Bettsing       | Ben Rice        | 1B         |         0.019 | SLUMPING      | DECLINING         |               0.5407 |              0.8972 |             0.757732 |        0.609 |               0.03  | CONSENSUS_HOLD_BOUNCE |
| Team Solomon              | Mike Trout      | DH         |         0.142 | SLUMPING      | IMPROVING         |               0.5811 |              0.9959 |             0.649606 |        0.579 |               0.07  | CONSENSUS_HOLD_BOUNCE |
| U Just Lost To Edwin Diaz | Liam Hicks      | C          |         0.026 | SLUMPING      | IMPROVING         |               0.742  |              0.3353 |             0.808989 |        0.578 |               0.01  | CONSENSUS_HOLD_BOUNCE |
| 2015 Draft First Round    | Alex Bregman    | 3B         |         0.151 | SLUMPING      | MIXED             |               0.5073 |              0.8606 |             0.604336 |        0.563 |               0.032 | HOLD_NOISE            |
| Treasure Island Mashers   | Brice Turang    | 2B         |         0.136 | SLUMPING      | DECLINING         |               0.9228 |              0.2585 |             0.614826 |        0.559 |               0.035 | HOLD_NOISE            |
| Late Night Bettsing       | Kyle Tucker     | RF         |         0.236 | BELOW_MEDIAN  | DECLINING         |               0.5613 |              0.9617 |             0.527331 |        0.558 |               0.048 | BOUNCING_BACK         |
| 2015 Draft First Round    | Daylen Lile     | RF         |         0.045 | SLUMPING      | DECLINING         |               0.4859 |              0.6066 |             0.805556 |        0.552 |               0.042 | HOLD_NOISE            |
| U Just Lost To Edwin Diaz | Ernie Clement   | 3B         |         0.055 | SLUMPING      | DECLINING         |               0.4424 |              0.0123 |             0.689189 |        0.544 |               0.02  | HOLD_NOISE            |
| 2015 Draft First Round    | Brandon Lowe    | 2B         |         0.151 | SLUMPING      | MIXED             |               0.7576 |              0.7428 |             0.563057 |        0.54  |               0.016 | HOLD_NOISE            |
| Late Night Bettsing       | Jackson Merrill | CF         |         0.089 | SLUMPING      | IMPROVING         |               0.9962 |              0.5377 |             0.661836 |        0.539 |               0.03  | CONSENSUS_HOLD_BOUNCE |
| Team Solomon              | JJ Wetherholt   | SS         |         0.073 | SLUMPING      | MIXED             |               0.6195 |              1      |             0.75     |        0.539 |               0.015 | HOLD_NOISE            |
| Team Solomon              | Seiya Suzuki    | DH         |         0.074 | SLUMPING      | DECLINING         |               0.7608 |              0.7237 |             0.665816 |        0.533 |               0.024 | HOLD_NOISE            |
| 2015 Draft First Round    | Ian Happ        | LF         |         0.035 | SLUMPING      | DECLINING         |               0.3622 |              0.4233 |             0.684066 |        0.528 |               0.019 | HOLD_NOISE            |
| Treasure Island Mashers   | Wilyer Abreu    | RF         |         0.018 | SLUMPING      | DECLINING         |               0.5188 |              0.4011 |             0.745946 |        0.527 |               0.018 | HOLD_NOISE            |
| Boone's Bad Bullpen       | Ryan O'Hearn    | 1B         |         0.046 | SLUMPING      | MIXED             |               0.5059 |              0.5446 |             0.671271 |        0.525 |               0.016 | HOLD_NOISE            |
| Frendy's Fantastic Team   | George Springer | DH         |         0.133 | SLUMPING      | DECLINING         |               0.5894 |              0.828  |             0.541353 |        0.518 |               0.118 | HOLD_NOISE            |

### Rival peakers cooling

_None._