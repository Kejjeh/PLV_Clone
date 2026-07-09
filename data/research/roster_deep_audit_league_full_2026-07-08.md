# League-wide roster deep audit (v4 — statistical + calibrated) — 2026-07-08

**Hitters:** 119 | **Slumpers analyzed:** 56 | **PEAK validated:** 6 | **MC sims:** 10,000/player (λ=0.20 recency decay) | **Historical comps:** 2015-2025 Statcast (age-matched ±3yr) | **SP career-form:** 67 SPs

> **CONSENSUS_DROP gate:** requires REGRESS + process DECLINING/MIXED + shrunk_gap < −0.030 + bounce_pct < 50%. IMPROVING process or anchor_in_CI always overrides to HOLD.

> **v4 upgrades:** recency-weighted MC + Bayesian (λ=0.20), age-matched comps (±3yr), Wilson CIs on survival curves, injury signal integration (ESPN DTD/IL).

> **Calibration:** ECE=0.0197 (WELL_CALIBRATED, threshold < 0.05), Brier=0.2221, validated on 15,778 out-of-sample snapshots (2023-2025 holdout). _Known limitation: adjacent rolling-150 windows share 149/150 events — precision is slightly overstated vs true i.i.d._

## Power ranking

| team_name                 |   rank |   n |   mean_pct |   n_peak |   n_high |   n_slump |   n_improving |   n_declining |   n_bounce |   n_drop |   mean_rh3 |   mean_bayes_p_avg |   sp_proj |
|:--------------------------|-------:|----:|-----------:|---------:|---------:|----------:|--------------:|--------------:|-----------:|---------:|-----------:|-------------------:|----------:|
| Late Night Bettsing       |      1 |  13 |      0.393 |        0 |        1 |         4 |             4 |             7 |          4 |        0 |      0.573 |           0.681115 |      87.5 |
| New York Ligers           |      2 |  14 |      0.511 |        2 |        1 |         3 |             2 |             8 |          3 |        0 |      0.56  |           0.728107 |     121.1 |
| Frendy's Fantastic Team   |      3 |  15 |      0.393 |        1 |        0 |         5 |             4 |             5 |          5 |        0 |      0.556 |           0.691127 |     106.9 |
| U Just Lost To Edwin Diaz |      4 |  15 |      0.444 |        1 |        2 |         5 |             2 |             6 |          4 |        0 |      0.548 |           0.452279 |      91.8 |
| 2015 Draft First Round    |      5 |  15 |      0.378 |        0 |        2 |         6 |             3 |             5 |          5 |        0 |      0.543 |           0.69418  |      97.3 |
| Team Solomon              |      6 |  14 |      0.367 |        0 |        1 |         5 |             4 |             6 |          5 |        0 |      0.539 |           0.8021   |     135.1 |
| Boone's Bad Bullpen       |      7 |  15 |      0.519 |        1 |        1 |         2 |             4 |             4 |          2 |        0 |      0.531 |           0.773913 |      73.4 |
| Treasure Island Mashers   |      8 |  18 |      0.466 |        1 |        1 |         4 |             1 |             6 |          4 |        0 |      0.526 |           0.6466   |      96.2 |


## Per-team position breakdown


### New York Ligers ← YOU

**C**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict       | injury_class   | injury_note                                        |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:--------------------|:---------------|:---------------------------------------------------|
| Hunter Goodman |         0.999 |          0.388 | PEAK          | STABLE        | DECLINING         |         0.2786 |            0.274 |     107.5 |       106.8 |               96.7 |              | False          |               0.5765 |              0.5224 |                   99.3 |            229 |             0.131004 | UNKNOWN        |        0.575 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | DTD            | DTD (Jammed, Not Specified) — slump window unknown |

**1B**

| player_name           |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:--------------|
| Pete Alonso           |         0.813 |          0.396 | HIGH          | STABLE        | DECLINING         |         0.2185 |           0.2468 |     110.1 |       107.2 |               96.6 |              | False          |               0.658  |              0.9593 |                   86.2 |                |                      | UNKNOWN        |        0.593 | hold         |                |                     | STABLE_HIGH            | NONE           |               |
| Vladimir Guerrero Jr. |         0.079 |          0.317 | SLUMPING      | STABLE        | DECLINING         |         0.1922 |           0.2029 |     110.3 |       106.2 |               83   |      -0.0065 | True           |               0.4151 |              0.7998 |                   77.8 |            597 |             0.653266 | K_DRIVEN       |        0.564 | hold         |                |                     | HOLD_NOISE             | NONE           |               |
| Luis Arraez           |         0.226 |          0.309 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.0382 |           0.0676 |      96.6 |        97.3 |               94.8 |       0.0061 | True           |               0.3518 |              0.6504 |                   87.3 |            962 |             0.553015 | HOLDING        |        0.561 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kody Clemens          |         0.982 |          0.37  | PEAK          | STABLE        | DECLINING         |         0.2114 |           0.2308 |     106   |       105.4 |              100   |              | False          |               0.0908 |              0.6797 |                  109.3 |            164 |             0.115854 | UNKNOWN        |        0.534 | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Max Muncy     |         0.037 |          0.307 | SLUMPING      | STABLE        | DECLINING         |          0.215 |           0.2279 |     105.8 |       104.9 |                100 |       0.0001 | True           |               0.7353 |                0.61 |                   81.5 |            204 |             0.681373 | DISCIPLINE_COLLAPSE |        0.379 | drop         |             |                     | HOLD_NOISE      | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Bo Bichette     |         0.403 |          0.333 | TYPICAL       | REGRESS       | MIXED             |         0.1576 |           0.1775 |     105.5 |       106.2 |              100   |              | False          |               0.6238 |              0.7876 |                   94   |                |                      | UNKNOWN        |        0.563 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Elly De La Cruz |         0.757 |          0.355 | ABOVE_MEDIAN  | STABLE        | STABLE            |         0.2788 |           0.2595 |     107.7 |       109.7 |               66.1 |              | False          |               0.5348 |              0.6599 |                   96.8 |                |                      | UNKNOWN        |        0.515 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                             |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:----------------------------------------|
| Aaron Judge       |         0.307 |          0.406 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.3159 |           0.3419 |     111.9 |       109.1 |               64   |      -0.0186 | True           |               0.53   |              0.9895 |                   61.1 |            369 |             0.552846 | BABIP_DRIVEN   |        0.686 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Fracture, Right) — active DTD note |
| Corbin Carroll    |         0.117 |          0.308 | SLUMPING      | STABLE        | DECLINING         |         0.2164 |           0.2791 |     107.4 |       105.9 |               90   |      -0.0123 | True           |               0.3945 |              0.5517 |                   77.2 |            677 |             0.635155 | HOLDING        |        0.63  | add          |             |                     | HOLD_NOISE             | NONE           |                                         |
| Michael Harris II |         0.589 |          0.353 | TYPICAL       | MIXED         | MIXED             |         0.199  |           0.2327 |     108.6 |       107.5 |               59.8 |              | False          |               0.5452 |              0.7032 |                  103.1 |                |                      | UNKNOWN        |        0.612 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                         |
| Dominic Canzone   |         0.798 |          0.384 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2264 |           0.1905 |     107.8 |       107.3 |               78.8 |              | False          |               0.3605 |              0.8758 |                  108.9 |                |                      | UNKNOWN        |        0.541 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                         |
| Wyatt Langford    |         0.245 |          0.314 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2331 |           0.1753 |     107   |       103   |               90.6 |       0.0052 | True           |               0.8028 |              0.6882 |                   98.4 |            275 |             0.52     | MIXED          |        0.541 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Strain, Left) — active DTD note    |
| Jordan Walker     |         0.799 |          0.352 | ABOVE_MEDIAN  | IMPROVING     | IMPROVING         |         0.3268 |           0.2596 |     110   |       110.7 |               51.8 |              | False          |               0.5457 |              0.716  |                  143.1 |                |                      | UNKNOWN        |        0.54  | hold         |             |                     | STRENGTHENING          | NONE           |                                         |

**SP**

| player_name    |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:---------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Tyler Glasnow  | 13.957 |      0     |          |             |              | False       |             |                |
| Shota Imanaga  | 12.603 |     -2.517 |          |             |              | False       |             |                |
| Hunter Greene  | 12.27  |      0     |          |             |              | False       |             |                |
| Eury Perez     | 12.028 |      6.507 |          |             |              | False       |             |                |
| Jose Soriano   | 11.988 |     -5.145 |          |             |              | False       |             |                |
| Emmet Sheehan  | 11.897 |     -2.902 |          |             |              | False       |             |                |
| Parker Messick | 11.781 |      1.244 |          |             |              | False       |             |                |
| Carlos Rodon   | 11.704 |     -1.356 |          |             |              | False       |             |                |
| Max Fried      | 11.672 |      0     |          |             |              | False       |             |                |
| Freddy Peralta | 11.25  |     -9.486 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Jhoan Duran   |  144.3 |
| Tanner Scott  |  110   |
| Jacob Latz    |  102.2 |
| Reid Detmers  |  nan   |


### 2015 Draft First Round

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                              |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:---------------------------------------------------------|
| Will Smith    |         0.864 |          0.386 | HIGH          | STABLE        | DECLINING         |         0.1878 |           0.1157 |     105.6 |       102.6 |               95.4 |              | False          |               0.3142 |              0.985  |                   85.5 |                |                      | UNKNOWN        |        0.552 | hold         |             |                     | STABLE_HIGH            | DTD            | DTD (Inflammation, Not Specified) — slump window unknown |
| Keibert Ruiz  |         0.495 |          0.3   | TYPICAL       | NOISE         | MIXED             |         0.1028 |           0.104  |     100.3 |       101.6 |               92.2 |              | False          |               0.6649 |              0.2861 |                  106.4 |                |                      | UNKNOWN        |        0.527 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                          |

**1B**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Paul Goldschmidt |             0 |          0.262 | SLUMPING      | STABLE        | DECLINING         |         0.1792 |           0.2848 |     105.3 |       100.9 |                nan |      -0.0212 | False          |               0.7507 |              0.2267 |                  109.9 |             20 |                 0.55 | DISCIPLINE_COLLAPSE |        0.512 | hold         |             |                     | SLUMP_AMBIGUOUS | NONE           |               |

**2B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Ketel Marte   |         0.639 |          0.366 | ABOVE_MEDIAN  | STABLE        | STABLE            |         0.1844 |           0.1811 |     107.4 |       107.5 |               86.8 |              | False          |               0.3411 |              0.9621 |                   74.2 |                |                      | UNKNOWN        |        0.669 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Brandon Lowe  |         0.056 |          0.304 | SLUMPING      | STABLE        | STABLE            |         0.2896 |           0.3013 |     106.4 |       107.1 |               54.1 |        0.004 | True           |               0.752  |              0.8433 |                   98.2 |            581 |             0.654045 | HOLDING        |        0.527 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Sam Antonacci |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1566 |           |       100.6 |              nan   |              | False          |               0.4834 |              1      |                  102.2 |                |                      | UNKNOWN        |        0.482 | hold         |             |                     | INSUFFICIENT_DATA      | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                          |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:-----------------------------------------------------|
| Alex Bregman  |         0.097 |          0.307 | SLUMPING      | REGRESS       | DECLINING         |         0.1252 |           0.1353 |     102.8 |       100.7 |               98.5 |      -0.0056 | True           |               0.477  |              0.7021 |                   83   |            413 |             0.636804 | MIXED          |        0.55  | hold         |             |                     | HOLD_NOISE             | NONE           |                                                      |
| Josh Jung     |         0.568 |          0.326 | TYPICAL       | STABLE        | IMPROVING         |         0.2188 |           0.1325 |     103.9 |       102.9 |               57.2 |              | False          |               0.5984 |              0.5763 |                  121.3 |                |                      | UNKNOWN        |        0.511 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Soreness, Not Specified) — slump window unknown |

**SS**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict         | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------------|:---------------|:--------------|
| Bobby Witt Jr. |         0.856 |          0.408 | HIGH          | STABLE        | MIXED             |         0.2097 |           0.2269 |     108.8 |       108.1 |               71.5 |              | False          |               0.3953 |              0.9976 |                   71.6 |                |                      | UNKNOWN        |        0.683 | add          |             |                     | STABLE_HIGH           | NONE           |               |
| Dansby Swanson |         0.052 |          0.269 | SLUMPING      | STABLE        | IMPROVING         |         0.2812 |           0.2567 |     104.7 |       103.8 |               68.4 |       0.0235 | False          |               0.4403 |              0.8094 |                  108   |            343 |             0.655977 | MIXED          |        0.46  | hold         |             |                     | CONSENSUS_HOLD_BOUNCE | NONE           |               |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Daylen Lile   |         0.092 |          0.288 | SLUMPING      | STABLE        | MIXED             |         0.1471 |           0.1574 |     103.9 |       104.6 |              100   |       0.0064 | True           |               0.418  |              0.3112 |                   82.4 |            118 |             0.711864 | DISCIPLINE_COLLAPSE |        0.546 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Jung Hoo Lee  |         0.35  |          0.316 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.1096 |           0.1179 |     101.3 |        99.4 |               97.1 |      -0.0112 | True           |               0.5621 |              0.3335 |                   96.9 |            385 |             0.490909 | DISCIPLINE_COLLAPSE |        0.523 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Ian Happ      |         0.121 |          0.293 | SLUMPING      | STABLE        | DECLINING         |         0.2084 |           0.281  |     105.7 |       105.1 |               64.4 |      -0.0086 | True           |               0.3273 |              0.4505 |                   97.3 |            592 |             0.633446 | BABIP_DRIVEN        |        0.504 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Riley Greene  |         0.548 |          0.352 | TYPICAL       | STABLE        | IMPROVING         |         0.2628 |           0.2366 |     107.8 |       107.6 |               71.3 |              | False          |               0.406  |              0.9387 |                  102.2 |                |                      | UNKNOWN             |        0.491 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Kyle Schwarber |          0.55 |          0.373 | TYPICAL       | STABLE        | MIXED             |         0.2979 |           0.2954 |     109.8 |       109.2 |               73.2 |              | False          |               0.5661 |              0.9902 |                   83.3 |                |                      | UNKNOWN        |        0.605 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name    |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:---------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Jacob deGrom   | 15.529 |      0.478 |          |             |              | False       |             |                |
| Logan Gilbert  | 15.368 |      6.211 |          |             |              | False       |             |                |
| Cam Schlittler | 15.13  |     -2.051 |          |             |              | False       |             |                |
| Drew Rasmussen | 12.638 |     -3.739 |          |             |              | False       |             |                |
| Foster Griffin | 10.329 |      7.322 |          |             |              | False       |             |                |
| Shane Baz      |  9.853 |      1.083 |          |             |              | False       |             |                |
| Bryce Elder    |  9.845 |    -13.179 |          |             |              | False       |             |                |
| Nick Lodolo    |  8.561 |      1.261 |          |             |              | False       |             |                |

**RP**

| player_name          |   proj |
|:---------------------|-------:|
| Trevor Megill        |  118.3 |
| Bryan Baker          |  103   |
| Jakob Junis          |   72.9 |
| Robert Garcia        |   48.9 |
| Peter Lambert        |  nan   |
| Seranthony Dominguez |  nan   |


### Boone's Bad Bullpen

**C**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| William Contreras |         0.244 |          0.321 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.2113 |           0.1761 |     107.4 |       105.9 |                 61 |      -0.0186 | True           |               0.6896 |              0.8522 |                   90.6 |            892 |             0.530269 | BABIP_DRIVEN   |        0.597 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Dillon Dingler    |         0.43  |          0.365 | TYPICAL       | NOISE         | MIXED             |         0.2149 |           0.225  |     105.4 |       104.4 |                 76 |              | False          |               0.0596 |              0.8541 |                  122.9 |                |                      | UNKNOWN        |        0.544 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**1B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Freddie Freeman |         0.554 |          0.398 | TYPICAL       | STABLE        | IMPROVING         |         0.2516 |           0.2252 |     104.3 |       102.7 |               86   |              | False          |               0.5503 |              0.9956 |                   76.9 |                |                      | UNKNOWN        |        0.632 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Ryan O'Hearn    |         0.367 |          0.317 | BELOW_MEDIAN  | STABLE        | STABLE            |         0.1931 |           0.1734 |     103.1 |       104.7 |               58.6 |       0.0192 | True           |               0.5242 |              0.7996 |                   93.3 |            518 |             0.438224 | HOLDING        |        0.535 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Michael Busch   |         0.351 |          0.331 | BELOW_MEDIAN  | REGRESS       | DECLINING         |         0.2208 |           0.2236 |     105.4 |       101.8 |               95.3 |      -0.0028 | True           |               0.7907 |              0.7162 |                   96.2 |            565 |             0.463717 | BABIP_DRIVEN   |        0.524 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Junior Caminero |         0.736 |          0.372 | ABOVE_MEDIAN  | STABLE        | STABLE            |         0.2194 |           0.2164 |     109.5 |       111.5 |               92.8 |              | False          |               0.332  |              0.9605 |                   82.1 |                |                      | UNKNOWN        |        0.698 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kazuma Okamoto  |         0.484 |          0.332 | TYPICAL       | NO_BASELINE   | MIXED             |                |           0.3094 |           |       107.3 |              nan   |              | False          |               0.3629 |              0.705  |                  102.2 |                |                      | UNKNOWN        |        0.47  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict     | injury_class   | injury_note                               |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:------------------|:---------------|:------------------------------------------|
| Gunnar Henderson |         0.07  |          0.304 | SLUMPING      | STABLE        | DECLINING         |         0.2172 |           0.201  |     106.8 |       104.8 |              100   |      -0.0011 | True           |               0.4886 |              0.5348 |                   86.3 |            472 |             0.677966 | BABIP_DRIVEN   |        0.544 | hold         |             |                     | HOLD_NOISE        | NONE           |                                           |
| Zach Neto        |         0.079 |          0.288 | SLUMPING      | STABLE        | DECLINING         |         0.2667 |           0.3    |     105.7 |       104.8 |               97.6 |       0.0009 | True           |               0.3307 |              0.6216 |                   98.8 |            472 |             0.699153 | HOLDING        |        0.482 | hold         |             |                     | HOLD_NOISE        | NONE           |                                           |
| Konnor Griffin   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.2914 |           |       107.1 |              nan   |              | False          |               0.7682 |              0.6172 |                  102.2 |                |                      | UNKNOWN        |        0.434 | drop         |             |                     | INSUFFICIENT_DATA | DTD            | DTD (Strain, Left) — slump window unknown |

**OF**

| player_name         |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                      |
|:--------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:-----------------------|:---------------|:-------------------------------------------------|
| Tyler Soderstrom    |         0.736 |          0.353 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2042 |           0.1746 |     107.2 |       105.5 |               98.4 |              | False          |               0.6127 |              0.8363 |                  103.3 |                |                      | UNKNOWN        |        0.557 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Pinched Nerve, Left) — slump window unknown |
| Pete Crow-Armstrong |         0.953 |          0.42  | PEAK          | STABLE        | IMPROVING         |         0.2465 |           0.2241 |     105.2 |       104.2 |               98.7 |              | False          |               0.7779 |              0.8448 |                   94   |            247 |             0.186235 | UNKNOWN        |        0.55  | hold         | PROCESS_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |                                                  |
| Bryan Reynolds      |         0.633 |          0.363 | ABOVE_MEDIAN  | NOISE         | MIXED             |         0.255  |           0.2614 |     106.3 |       105.7 |               79.7 |              | False          |               0.4968 |              0.903  |                  107.4 |                |                      | UNKNOWN        |        0.531 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                  |
| Steven Kwan         |         0.764 |          0.335 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.0749 |           0.0609 |      98   |        95.9 |              100   |              | False          |               0.6348 |              0.4751 |                   90.6 |                |                      | UNKNOWN        |        0.458 | hold         |                |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                  |
| Jac Caglianone      |         0.869 |          0.387 | HIGH          | STABLE        | MIXED             |         0.2432 |           0.3096 |     109.4 |       109   |              100   |              | False          |               1      |              0.8927 |                  158   |                |                      | UNKNOWN        |        0.406 | drop         |                |                     | STABLE_HIGH            | NONE           |                                                  |

**SP**

| player_name   |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:--------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Paul Skenes   | 15.328 |     -8.417 |          |             |              | False       |             |                |
| Jesus Luzardo | 14.599 |      4.411 |          |             |              | False       |             |                |
| Casey Mize    | 12.197 |      0.613 |          |             |              | False       |             |                |
| Gerrit Cole   | 11.776 |     -4.4   |          |             |              | False       |             |                |
| Michael King  | 10.765 |      1.844 |          |             |              | False       |             |                |
| Nick Martinez |  8.73  |      0.475 |          |             |              | False       |             |                |

**RP**

| player_name      |   proj |
|:-----------------|-------:|
| David Bednar     |  121.8 |
| Raisel Iglesias  |  121.2 |
| Abner Uribe      |   96   |
| Garrett Whitlock |   92   |
| Robert Suarez    |   77.9 |
| Andres Munoz     |  nan   |


### Frendy's Fantastic Team

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Drake Baldwin |         0.388 |           0.36 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.1592 |           0.1943 |     106.3 |       106.2 |               89.8 |       0.0069 | True           |               0.4687 |              0.9377 |                     80 |            165 |             0.430303 | BABIP_DRIVEN   |        0.616 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict         | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------------|:---------------|:--------------|
| Josh Naylor   |         0.028 |          0.29  | SLUMPING      | REGRESS       | IMPROVING         |         0.1965 |           0.1657 |     104.3 |       103.8 |               98.7 |      -0.0193 | True           |               0.5649 |              0.5846 |                   77.6 |            518 |             0.662162 | BABIP_DRIVEN   |        0.565 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE | NONE           |               |
| Sal Stewart   |         0.109 |          0.323 | SLUMPING      | STABLE        | DECLINING         |         0.2124 |           0.244  |     107.4 |       104.7 |              nan   |      -0.0076 | True           |               0.9925 |              0.8378 |                   89.5 |             48 |             0.6875   | MIXED          |        0.541 | hold         |             |                     | HOLD_NOISE            | NONE           |               |

**2B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Nico Hoerner  |         0.22  |          0.301 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.092  |           0.1149 |     100.7 |       100.3 |               59.7 |      -0.0076 | True           |               0.5661 |              0.2964 |                   86.3 |            916 |             0.540393 | K_DRIVEN            |        0.559 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Ozzie Albies  |         0.166 |          0.293 | SLUMPING      | STABLE        | MIXED             |         0.1757 |           0.1765 |     100.8 |       100.9 |               55.4 |      -0.0114 | True           |               0.7487 |              0.1219 |                   90.9 |            695 |             0.595683 | DISCIPLINE_COLLAPSE |        0.54  | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**3B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict       | injury_class   | injury_note                                |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:--------------------|:---------------|:-------------------------------------------|
| Miguel Vargas     |         0.921 |          0.422 | PEAK          | IMPROVING     | IMPROVING         |         0.1716 |           0.1264 |     103.1 |       103.8 |               53.8 |              | False          |               0.5943 |              0.9787 |                  109.9 |            408 |             0.210784 | UNKNOWN        |        0.619 | add          | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |                                            |
| Munetaka Murakami |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.3563 |           |       108.2 |              nan   |              | False          |               0.8538 |              1      |                  102.2 |                |                      | UNKNOWN        |        0.532 | hold         |             |                     | INSUFFICIENT_DATA   | DTD            | DTD (Strain, Right) — slump window unknown |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   | whiff_pct_25   |   whiff_pct_l21d | ev90_25   |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|:---------------|-----------------:|:----------|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Kevin McGonigle |         0.719 |          0.371 | ABOVE_MEDIAN  | NO_BASELINE   | MIXED             |                |           0.1674 |           |         104 |                nan |              | False          |               0.4852 |              0.9816 |                  102.2 |                |                      | UNKNOWN        |        0.545 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Jackson Chourio |         0.695 |          0.348 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2257 |           0.1538 |     105.9 |       108.3 |              nan   |              | False          |               0.8219 |              0.3741 |                   88   |                |                      | UNKNOWN             |        0.608 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Cody Bellinger  |         0.328 |          0.308 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.1489 |           0.1991 |     102.7 |       103.7 |               56.7 |      -0.0186 | True           |               0.7947 |              0.3393 |                   78.2 |            609 |             0.541872 | DISCIPLINE_COLLAPSE |        0.598 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Taylor Ward     |         0.331 |          0.327 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.205  |           0.1965 |     105.1 |       102.4 |               69.7 |      -0.0042 | True           |               0.5401 |              0.576  |                  100.5 |            547 |             0.458867 | HOLDING             |        0.494 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kyle Stowers    |         0.66  |          0.356 | ABOVE_MEDIAN  | REGRESS       | STABLE            |         0.2914 |           0.2891 |     108.2 |       108.9 |               92.7 |              | False          |               0.7453 |              0.9654 |                  102.8 |                |                      | UNKNOWN             |        0.476 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**UTIL/DH**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Shohei Ohtani    |         0.709 |          0.433 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.3024 |           0.2256 |     110.1 |       109.8 |               88.1 |              | False          |               0.6543 |              0.9954 |                   63.3 |                |                      | UNKNOWN             |        0.709 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| George Springer  |         0.126 |          0.32  | SLUMPING      | REGRESS       | DECLINING         |         0.2308 |           0.1888 |     107.2 |       105.2 |               95.7 |      -0.0183 | True           |               0.5977 |              0.754  |                   86.1 |            136 |             0.551471 | DISCIPLINE_COLLAPSE |        0.5   | add          |             |                     | HOLD_NOISE             | NONE           |               |
| Christian Yelich |         0.105 |          0.31  | SLUMPING      | STABLE        | DECLINING         |         0.2496 |           0.2153 |     106.7 |       104.6 |               92.3 |       0.0043 | True           |               0.4602 |              0.624  |                   85.7 |            215 |             0.637209 | DISCIPLINE_COLLAPSE |        0.436 | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**SP**

| player_name      |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-----------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Joe Ryan         | 14.181 |     -0.864 |          |             |              | False       |             |                |
| Chase Burns      | 13.7   |     -4.01  |          |             |              | False       |             |                |
| Brandon Woodruff | 13     |      6.167 |          |             |              | False       |             |                |
| Payton Tolle     | 11.851 |      0.25  |          |             |              | False       |             |                |
| Hunter Brown     | 11.371 |     -7.817 |          |             |              | False       |             |                |
| Jared Jones      | 11.196 |      2.081 |          |             |              | False       |             |                |
| Shane McClanahan | 11.045 |     -1.727 |          |             |              | False       |             |                |
| Framber Valdez   | 10.375 |     -1.978 |          |             |              | False       |             |                |
| Connelly Early   | 10.202 |      4.263 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Grant Taylor  |    nan |


### Late Night Bettsing

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Ben Rice          |         0.148 |          0.341 | SLUMPING      | STABLE        | DECLINING         |         0.1905 |           0.177  |     107.7 |       105.5 |               87.5 |       0.0266 | False          |               0.4503 |              0.9435 |                   91.6 |            365 |             0.608219 | HOLDING             |        0.61  | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |
| Willson Contreras |         0.695 |          0.372 | ABOVE_MEDIAN  | STABLE        | IMPROVING         |         0.2476 |           0.2199 |     108.2 |       110.6 |               72.6 |              | False          |               0.5248 |              0.9608 |                   97.5 |                |                      | UNKNOWN             |        0.559 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Spencer Steer     |         0.159 |          0.287 | SLUMPING      | STABLE        | IMPROVING         |         0.2213 |           0.1969 |     102   |       102.6 |               90.8 |       0.0014 | True           |               0.6489 |              0.2075 |                   97.6 |            714 |             0.592437 | BABIP_DRIVEN        |        0.544 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |
| Jonathan Aranda   |         0.262 |          0.35  | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.218  |           0.2055 |     106.9 |       103.9 |               96.6 |      -0.0209 | False          |               0.2746 |              0.8796 |                   98.3 |            374 |             0.491979 | DISCIPLINE_COLLAPSE |        0.535 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                               |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:------------------------------------------|
| Gleyber Torres |         0.546 |          0.342 | TYPICAL       | STABLE        | DECLINING         |         0.1628 |           0.2258 |     104.6 |       101.6 |               73.4 |              | False          |               0.5293 |              0.7258 |                   98.2 |                |                      | UNKNOWN        |        0.469 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Strain, Left) — slump window unknown |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Isaac Paredes |         0.819 |          0.332 | HIGH          | STABLE        | DECLINING         |         0.1396 |            0.166 |     102.5 |       101.5 |               88.8 |              | False          |               0.4439 |              0.2724 |                   89.2 |                |                      | UNKNOWN        |        0.536 | hold         |             |                     | STABLE_HIGH     | NONE           |               |

**SS**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Mookie Betts  |         0.39  |          0.345 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.1313 |           0.0989 |     101.6 |       101.2 |              nan   |      -0.0001 | True           |               0.8354 |              0.8812 |                   73.3 |            189 |             0.439153 | BABIP_DRIVEN   |        0.644 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| CJ Abrams     |         0.307 |          0.294 | BELOW_MEDIAN  | STABLE        | STABLE            |         0.2123 |           0.209  |     104.1 |       104.4 |               57.6 |       0.0022 | True           |               0.5428 |              0.2651 |                   93.6 |            699 |             0.515021 | HOLDING        |        0.538 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Alec Burleson   |         0.76  |          0.372 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.1486 |           0.1688 |     106.1 |       104.9 |               66.6 |              | False          |               0.7086 |              0.7941 |                   92   |                |                      | UNKNOWN             |        0.592 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Andy Pages      |         0.251 |          0.305 | BELOW_MEDIAN  | STABLE        | STABLE            |         0.1915 |           0.1864 |     104.4 |       104.4 |               81.2 |      -0.0081 | True           |               0.5461 |              0.5918 |                  101.3 |            422 |             0.488152 | BABIP_DRIVEN        |        0.565 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Kyle Tucker     |         0.139 |          0.329 | SLUMPING      | REGRESS       | DECLINING         |         0.1729 |           0.2061 |     103.9 |       102   |              100   |       0.0001 | True           |               0.5658 |              0.9682 |                   69.8 |            946 |             0.584567 | MIXED               |        0.542 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Jackson Merrill |         0.029 |          0.299 | SLUMPING      | STABLE        | DECLINING         |         0.2238 |           0.2455 |     105.3 |       101.4 |              100   |      -0.0074 | True           |               0.9672 |              0.3654 |                   88.8 |            136 |             0.727941 | DISCIPLINE_COLLAPSE |        0.52  | hold         |             |                     | HOLD_NOISE             | NONE           |               |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Yordan Alvarez |         0.601 |          0.437 | ABOVE_MEDIAN  | NOISE         | IMPROVING         |         0.1989 |            0.162 |     110.3 |       108.8 |               52.9 |              | False          |               0.4825 |              0.9991 |                   72.8 |                |                      | UNKNOWN        |        0.794 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Dylan Cease        | 15.439 |      2.252 |          |             |              | False       |             |                |
| Bryan Woo          | 13.699 |      0.197 |          |             |              | False       |             |                |
| Max Meyer          | 11.369 |     -1.532 |          |             |              | False       |             |                |
| Ben Brown          | 10.764 |      0.375 |          |             |              | False       |             |                |
| Noah Cameron       |  9.507 |     -8.265 |          |             |              | False       |             |                |
| Spencer Arrighetti |  9.289 |     -5.036 |          |             |              | False       |             |                |
| Robbie Ray         |  9.251 |      6.68  |          |             |              | False       |             |                |
| Eduardo Rodriguez  |  8.214 |      3.344 |          |             |              | False       |             |                |

**RP**

| player_name      |   proj |
|:-----------------|-------:|
| Cade Smith       |  138.2 |
| Aroldis Chapman  |  130.2 |
| Paul Sewald      |  102.1 |
| Devin Williams   |   96.9 |
| Braxton Ashcraft |  nan   |
| Justin Wrobleski |  nan   |


### Team Solomon

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Cal Raleigh   |         0.036 |          0.276 | SLUMPING      | REGRESS       | DECLINING         |         0.2717 |           0.2585 |       107 |         104 |               95.4 |      -0.0062 | True           |               0.6998 |              0.5395 |                     87 |            470 |             0.689362 | DISCIPLINE_COLLAPSE |         0.43 | drop         |             |                     | HOLD_NOISE      | NONE           |               |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Matt Olson    |         0.215 |          0.339 | BELOW_MEDIAN  | STABLE        | IMPROVING         |         0.2336 |           0.1465 |     108.4 |         108 |               55.8 |       0.0041 | True           |               0.3692 |              0.8785 |                   85.5 |            460 |             0.558696 | DISCIPLINE_COLLAPSE |        0.644 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Bryce Harper  |         0.489 |          0.389 | TYPICAL       | STABLE        | MIXED             |         0.2764 |           0.2679 |     107.2 |         107 |               77.4 |              | False          |               0.6563 |              0.9865 |                   82.9 |                |                      | UNKNOWN             |        0.621 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Casey Schmitt     |         0.724 |          0.346 | ABOVE_MEDIAN  | NOISE         | IMPROVING         |         0.2318 |           0.1692 |     105.1 |       104.8 |               62.6 |              | False          |               0.2654 |              0.8262 |                  124.7 |                |                      | UNKNOWN        |        0.522 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jazz Chisholm Jr. |         0.404 |          0.314 | TYPICAL       | REGRESS       | MIXED             |         0.2949 |           0.2542 |     105.4 |       105   |              100   |              | False          |               0.3264 |              0.239  |                   93.5 |                |                      | UNKNOWN        |        0.446 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Manny Machado |         0.292 |          0.331 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2358 |           0.3005 |     107.7 |       104.3 |               92.4 |       0.0002 | True           |               0.5774 |              0.8452 |                   87.1 |            145 |              0.57931 | K_DRIVEN       |         0.53 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SS**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note                                         |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:----------------------------------------------------|
| JJ Wetherholt |         0.194 |          0.347 | SLUMPING      | NO_BASELINE   | MIXED             |                |           0.1596 |           |       101.7 |              nan   |       0.005  | True           |               0.5634 |              0.999  |                  102.2 |             59 |             0.59322  | UNKNOWN             |        0.538 | hold         |             |                     | HOLD_NOISE      | NONE           |                                                     |
| Corey Seager  |         0.178 |          0.344 | SLUMPING      | REGRESS       | DECLINING         |         0.2437 |           0.3171 |     108   |       105.3 |              100   |       0.0013 | True           |               0.6871 |              0.9424 |                   77.1 |            525 |             0.620952 | K_DRIVEN            |        0.51  | hold         |             |                     | HOLD_NOISE      | DTD            | DTD (Inflammation, Not Specified) — active DTD note |
| Trea Turner   |         0.051 |          0.28  | SLUMPING      | REGRESS       | DECLINING         |         0.2181 |           0.2669 |     104.2 |       103.4 |               81.4 |       0.0005 | True           |               0.3898 |              0.5641 |                   85.4 |            267 |             0.636704 | DISCIPLINE_COLLAPSE |        0.493 | hold         |             |                     | HOLD_NOISE      | NONE           |                                                     |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict     | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:------------------|:---------------|:--------------|
| James Wood      |         0.762 |          0.42  | ABOVE_MEDIAN  | IMPROVING     | IMPROVING         |         0.3015 |           0.2251 |     112   |       110.6 |               82.1 |              | False          |               0.2505 |              0.9955 |                  104.9 |                |                      | UNKNOWN        |        0.632 | add          |             |                     | STRENGTHENING     | NONE           |               |
| Brandon Nimmo   |         0.879 |          0.376 | HIGH          | STABLE        | DECLINING         |         0.2106 |           0.1885 |     106.2 |       104.1 |               86.6 |              | False          |               0.7693 |              0.9602 |                   96.9 |                |                      | UNKNOWN        |        0.588 | add          |             |                     | STABLE_HIGH       | NONE           |               |
| Esmerlyn Valdez |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.2833 |           |       110.7 |              nan   |              | False          |                      |                     |                        |                |                      | UNKNOWN        |        0.486 | hold         |             |                     | INSUFFICIENT_DATA | NONE           |               |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                           |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------------------------------|
| Mike Trout    |         0.16  |          0.38  | SLUMPING      | NOISE         | IMPROVING         |         0.2568 |           0.2064 |     107.9 |       109.4 |               73.2 |       0.0058 | True           |               0.5969 |              0.9969 |                  104.2 |            259 |             0.640927 | MIXED          |        0.569 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | DTD            | DTD (Strain, Right) — active DTD note |
| Seiya Suzuki  |         0.391 |          0.336 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.2086 |           0.223  |     107   |       103.2 |               71.1 |      -0.0093 | True           |               0.7846 |              0.6543 |                   93.6 |            522 |             0.452107 | MIXED          |        0.535 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                       |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Tarik Skubal       | 16.549 |      0.583 |          |             |              | False       |             |                |
| Cristopher Sanchez | 15.447 |     -9.522 |          |             |              | False       |             |                |
| Zack Wheeler       | 15.088 |      0.039 |          |             |              | False       |             |                |
| Chris Sale         | 14.926 |     -3.575 |          |             |              | False       |             |                |
| Nathan Eovaldi     | 13.441 |      4.139 |          |             |              | False       |             |                |
| Blake Snell        | 13.02  |      0     |          |             |              | False       |             |                |
| Sonny Gray         | 12.019 |      8.069 |          |             |              | False       |             |                |
| George Kirby       | 11.888 |      1.578 |          |             |              | False       |             |                |
| Garrett Crochet    | 11.734 |      0     |          |             |              | False       |             |                |
| Logan Webb         | 11.003 |     -2.213 |          |             |              | False       |             |                |

**RP**

| player_name    |   proj |
|:---------------|-------:|
| Josh Hader     |  187.7 |
| Pete Fairbanks |  139.5 |
| Riley O'Brien  |  101.3 |
| Louis Varland  |   89.7 |


### Treasure Island Mashers

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Adley Rutschman |         0.447 |          0.337 | TYPICAL       | NOISE         | MIXED             |         0.1273 |           0.1478 |     104.6 |       103.4 |               55.2 |              | False          |               0.7013 |              0.3418 |                  100.1 |                |                      | UNKNOWN        |        0.56  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Alejandro Kirk  |         0.017 |          0.287 | SLUMPING      | REGRESS       | DECLINING         |         0.1531 |           0.1481 |     106.6 |       101.7 |              nan   |       0.0069 | True           |               0.9585 |              0.2382 |                   97.5 |            414 |             0.748792 | BABIP_DRIVEN   |        0.442 | drop         |             |                     | HOLD_NOISE             | NONE           |               |

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Nick Kurtz        |         0.544 |          0.395 | TYPICAL       | STABLE        | MIXED             |          0.323 |           0.3194 |     108.5 |       109.9 |                100 |              | False          |               0.2312 |              0.9613 |                   74.9 |                |                      | UNKNOWN        |        0.652 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Spencer Torkelson |         0.614 |          0.331 | ABOVE_MEDIAN  | REGRESS       | DECLINING         |          0.23  |           0.2488 |     104.5 |       103.7 |                 72 |              | False          |               0.6892 |              0.7583 |                  109   |                |                      | UNKNOWN        |        0.452 | drop         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Brice Turang   |         0.135 |          0.285 | SLUMPING      | STABLE        | MIXED             |         0.1861 |           0.1609 |     104.2 |       104.7 |               57.4 |      -0.0029 | True           |               0.9353 |              0.3547 |                  102.1 |            719 |             0.616134 | MIXED          |        0.548 | hold         |             |                     | HOLD_NOISE             | NONE           |               |
| Luke Keaschall |         0.799 |          0.315 | ABOVE_MEDIAN  | REGRESS       | DECLINING         |         0.1667 |           0.1897 |     100.8 |        99.5 |              nan   |              | False          |               0.5994 |              0.1993 |                   79.5 |                |                      | UNKNOWN        |        0.522 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Nolan Arenado |             0 |          0.239 | SLUMPING      | STABLE        | MIXED             |          0.162 |           0.2513 |     101.6 |       102.2 |               92.8 |      -0.0122 | True           |                0.939 |              0.1769 |                   96.4 |             95 |             0.684211 | DISCIPLINE_COLLAPSE |        0.473 | hold         |             |                     | HOLD_NOISE      | NONE           |               |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Francisco Lindor |         0.508 |          0.345 | TYPICAL       | REGRESS       | MIXED             |         0.1803 |           0.1963 |     104.5 |       104.4 |               99.5 |              | False          |               0.6157 |              0.8737 |                   78.7 |                |                      | UNKNOWN        |        0.556 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Jacob Wilson     |         0.441 |          0.289 | TYPICAL       | STABLE        | MIXED             |         0.0775 |           0.1111 |      99.4 |       100.5 |              100   |              | False          |               0.8267 |              0.192  |                   86.2 |                |                      | UNKNOWN        |        0.543 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Xander Bogaerts  |         0.223 |          0.3   | BELOW_MEDIAN  | STABLE        | MIXED             |         0.1938 |           0.1832 |     105.6 |       103.1 |               77.8 |      -0.0065 | True           |               0.5927 |              0.4844 |                  101.4 |            207 |             0.574879 | K_DRIVEN       |        0.486 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**OF**

| player_name        |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                 |
|:-------------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------------------------------------|
| Juan Soto          |         0.713 |          0.445 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.1958 |           0.2078 |     108   |       107.1 |               85.8 |              | False          |               0.5441 |              1      |                   67.9 |                |                      | UNKNOWN             |        0.752 | add          |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                             |
| Wilyer Abreu       |         0.338 |          0.321 | BELOW_MEDIAN  | STABLE        | MIXED             |         0.2024 |           0.2    |     107.5 |       101.7 |               50.5 |       0.0016 | True           |               0.7997 |              0.6378 |                   96.5 |            438 |             0.474886 | K_DRIVEN            |        0.527 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                             |
| Randy Arozarena    |         0.976 |          0.387 | PEAK          | STABLE        | DECLINING         |         0.2637 |           0.2474 |     106.7 |       106.4 |               74.2 |              | False          |               0.8103 |              0.6258 |                  103.6 |            570 |             0.2      | UNKNOWN             |        0.513 | hold         | MIXED       | HOLD_SHORT          | CONSENSUS_HOLD_PEAK    | NONE           |                                             |
| Fernando Tatis Jr. |         0.272 |          0.355 | BELOW_MEDIAN  | REGRESS       | STABLE            |         0.2462 |           0.2395 |     108.6 |       110.8 |              100   |      -0.0168 | True           |               0.6895 |              0.9675 |                   85.5 |            831 |             0.536703 | DISCIPLINE_COLLAPSE |        0.504 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                             |
| Oneil Cruz         |         0.708 |          0.354 | ABOVE_MEDIAN  | NOISE         | MIXED             |         0.3046 |           0.3211 |     113.8 |       110.7 |               79.6 |              | False          |               0.5428 |              0.8406 |                  116.1 |                |                      | UNKNOWN             |        0.485 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | DTD            | DTD (Fracture, Left) — slump window unknown |
| Carson Benge       |         0.864 |          0.382 | HIGH          | NO_BASELINE   | MIXED             |                |           0.1698 |           |       104.9 |              nan   |              | False          |               0.0689 |              0.9891 |                  102.2 |                |                      | UNKNOWN             |        0.474 | hold         |             |                     | STABLE_HIGH            | NONE           |                                             |
| Roman Anthony      |         0.103 |          0.355 | SLUMPING      | BAD_LUCK      | IMPROVING         |         0.2792 |           0.2299 |     107.4 |       105.8 |              nan   |       0.0083 | True           |               0.8067 |              0.9999 |                   97.8 |             26 |             0.884615 | MIXED               |        0.45  | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | DTD            | DTD (Sprain, Right) — active DTD note       |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Rafael Devers |         0.678 |          0.381 | ABOVE_MEDIAN  | STABLE        | DECLINING         |         0.2819 |           0.2468 |     108.2 |       105.1 |                100 |              | False          |               0.1599 |              0.9975 |                   86.7 |                |                      | UNKNOWN        |         0.53 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**SP**

| player_name        |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:-------------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Jacob Misiorowski  | 18.459 |     -3.911 |          |             |              | False       |             |                |
| Yoshinobu Yamamoto | 14.493 |     -0.808 |          |             |              | False       |             |                |
| Kyle Harrison      | 12.799 |     -0.846 |          |             |              | False       |             |                |
| Nolan McLean       | 11.805 |      2.519 |          |             |              | False       |             |                |
| Ranger Suarez      | 11.18  |      0.674 |          |             |              | False       |             |                |
| Sandy Alcantara    | 10.862 |      1.513 |          |             |              | False       |             |                |
| Seth Lugo          |  8.522 |     -8.081 |          |             |              | False       |             |                |
| Zac Gallen         |  8.091 |     -3.133 |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Edwin Diaz    |    nan |


### U Just Lost To Edwin Diaz

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source        |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:--------------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Shea Langeliers |         0.319 |          0.304 | BELOW_MEDIAN  | STABLE        | DECLINING         |         0.217  |           0.2591 |     107.8 |       104.4 |               63.1 |       0.0063 | True           |               0.4158 |              0.4715 |                   97.8 |            731 |             0.487004 | DISCIPLINE_COLLAPSE |        0.61  | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Liam Hicks      |         0.029 |          0.273 | SLUMPING      | NOISE         | IMPROVING         |         0.1252 |           0.0862 |     100.6 |       101.1 |               64.8 |       0.004  | True           |               0.5816 |              0.2494 |                  105.5 |            106 |             0.773585 | HOLDING             |        0.566 | hold         |             |                     | CONSENSUS_HOLD_BOUNCE  | NONE           |               |

**1B**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type      | peak_trade_window   | cross_verdict       | injury_class   | injury_note   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:---------------|:--------------------|:--------------------|:---------------|:--------------|
| Christian Walker |         0.016 |          0.268 | SLUMPING      | STABLE        | DECLINING         |         0.2772 |           0.3004 |     107.5 |       106.7 |               56.7 |       0.0231 | False          |               0.4598 |              0.4774 |                   98.5 |            226 |             0.707965 | HOLDING        |        0.518 | hold         |                |                     | SLUMP_AMBIGUOUS     | NONE           |               |
| Jake Bauers      |         0.96  |          0.371 | PEAK          | STABLE        | DECLINING         |         0.2188 |           0.1749 |     107.4 |       108.3 |               59.7 |              | False          |               0.0079 |              0.6831 |                  124.2 |            363 |             0.15978  | UNKNOWN        |        0.502 | hold         | OUTCOME_DRIVEN | HOLD_SHORT          | CONSENSUS_HOLD_PEAK | NONE           |               |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Xavier Edwards |         0.444 |          0.298 | TYPICAL       | STABLE        | MIXED             |         0.1043 |           0.1741 |     100.5 |       102.9 |               49.3 |              | False          |               0.9225 |              0.2112 |                  100.3 |                |                      | UNKNOWN        |        0.541 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict   | injury_class   | injury_note   |
|:--------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:----------------|:---------------|:--------------|
| Ernie Clement |         0.105 |          0.263 | SLUMPING      | STABLE        | DECLINING         |         0.1249 |           0.1543 |     100.3 |        99.2 |               71.4 |       0.0088 | True           |               0.4632 |              0.0187 |                   92.7 |            570 |             0.650877 | MIXED          |        0.531 | hold         |             |                     | HOLD_NOISE      | NONE           |               |
| TJ Rumfield   |         0.048 |          0.287 | SLUMPING      | NO_BASELINE   | MIXED             |                |           0.1861 |           |       100.8 |              nan   |       0.0013 | True           |               0.3316 |              0.4894 |                  102.2 |             42 |             0.785714 | UNKNOWN        |        0.526 | hold         |             |                     | HOLD_NOISE      | NONE           |               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct | shrunk_gap   | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp | hist_n_comps   | hist_p_bounce_30pa   | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note   |
|:----------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|:-------------|:---------------|---------------------:|--------------------:|-----------------------:|:---------------|:---------------------|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------|
| Geraldo Perdomo |         0.71  |          0.334 | ABOVE_MEDIAN  | REGRESS       | MIXED             |         0.1036 |           0.0874 |     101.7 |       100.4 |               62.9 |              | False          |               0.6495 |              0.3165 |                   82.7 |                |                      | UNKNOWN        |        0.568 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |               |
| Otto Lopez      |         0.855 |          0.357 | HIGH          | NOISE         | STABLE            |         0.1594 |           0.142  |     104.6 |       105.6 |               81.1 |              | False          |               0.3906 |              0.7833 |                  100.9 |                |                      | UNKNOWN        |        0.563 | hold         |             |                     | STABLE_HIGH            | NONE           |               |

**OF**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   | process_verdict   |   whiff_pct_25 |   whiff_pct_l21d |   ev90_25 |   ev90_l21d |   slump_bounce_pct |   shrunk_gap | anchor_in_ci   |   mc_p_bounce_median |   bayes_p_above_avg |   bayes_games_to_200fp |   hist_n_comps |   hist_p_bounce_30pa | slump_source   |   rh3_per_pa | rh3_signal   | peak_type   | peak_trade_window   | cross_verdict          | injury_class   | injury_note                                       |
|:---------------|--------------:|---------------:|:--------------|:--------------|:------------------|---------------:|-----------------:|----------:|------------:|-------------------:|-------------:|:---------------|---------------------:|--------------------:|-----------------------:|---------------:|---------------------:|:---------------|-------------:|:-------------|:------------|:--------------------|:-----------------------|:---------------|:--------------------------------------------------|
| Byron Buxton   |         0.814 |          0.372 | HIGH          | STABLE        | DECLINING         |         0.2867 |           0.2857 |     108.6 |       105.4 |               74.4 |              | False          |               0.446  |              0.8452 |                   84.5 |                |                      | UNKNOWN        |        0.622 | add          |             |                     | STABLE_HIGH            | DTD            | DTD (Pinched Nerve, Right) — slump window unknown |
| Chase DeLauter |         0.082 |          0.302 | SLUMPING      | NO_BASELINE   | MIXED             |                |           0.1534 |           |       103.3 |              nan   |       -0.004 | True           |               0.508  |              0.6482 |                  102.2 |             38 |             0.789474 | UNKNOWN        |        0.581 | add          |             |                     | HOLD_NOISE             | NONE           |                                                   |
| Mickey Moniak  |         0.588 |          0.324 | TYPICAL       | STABLE        | MIXED             |         0.2467 |           0.25   |     106   |       103.8 |               69.1 |              | False          |               0.0415 |              0.3538 |                  105.4 |                |                      | UNKNOWN        |        0.553 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                   |
| JJ Bleday      |         0.747 |          0.334 | ABOVE_MEDIAN  | IMPROVING     | IMPROVING         |         0.2826 |           0.2033 |     104.2 |       105.4 |              nan   |              | False          |               0.5799 |              0.3267 |                  109.6 |                |                      | UNKNOWN        |        0.532 | hold         |             |                     | STRENGTHENING          | NONE           |                                                   |
| Brandon Marsh  |         0.497 |          0.324 | TYPICAL       | STABLE        | DECLINING         |         0.199  |           0.2186 |     103.7 |       103.3 |               61.9 |              | False          |               0.1776 |              0.4575 |                  112.4 |                |                      | UNKNOWN        |        0.515 | hold         |             |                     | CONSENSUS_HOLD_TYPICAL | NONE           |                                                   |
| Cole Carrigg   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   | MIXED             |                |           0.1944 |           |       102.2 |              nan   |              | False          |                      |                     |                        |                |                      | UNKNOWN        |        0.495 | hold         |             |                     | INSUFFICIENT_DATA      | NONE           |                                                   |

**SP**

| player_name    |   proj |   form_gap | k_form   | velo_form   | velo_delta   | velo_flag   | l5_k_rate   | career_k_pct   |
|:---------------|-------:|-----------:|:---------|:------------|:-------------|:------------|:------------|:---------------|
| Bryce Miller   | 14.691 |      0.333 |          |             |              | False       |             |                |
| Gavin Williams | 12.773 |     -7.019 |          |             |              | False       |             |                |
| Taj Bradley    | 12.757 |      6.638 |          |             |              | False       |             |                |
| Kevin Gausman  | 12.462 |     -9.354 |          |             |              | False       |             |                |
| MacKenzie Gore | 11.376 |      2.089 |          |             |              | False       |             |                |
| Trey Yesavage  | 10.595 |      3.656 |          |             |              | False       |             |                |
| Gage Jump      |  9.868 |     -2.75  |          |             |              | False       |             |                |
| Shane Bieber   |  7.328 |      0     |          |             |              | False       |             |                |

**RP**

| player_name   |   proj |
|:--------------|-------:|
| Mason Miller  |  156.7 |
| Dylan Lee     |   97.8 |
| Gregory Soto  |   87   |
| Rico Garcia   |   79.5 |


## Slump detail cards (v3 — with MC + Bayesian + historical comps)


### Corbin Carroll (New York Ligers, RF)

- **Career %ile:** 11.7%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 90% of 160 comparables bounced  | uplift: +0.113/PA

- **Bayesian shrunk gap:** -0.012  | anchor: 0.324  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.107 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.3→0.3  EV90 107.4→105.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **39.5%**  | Expected xwOBA: 0.351  | 95% CI: [0.341, 0.361]

- **Bayesian talent:** posterior μ = 0.323  | 95% CI: [0.273, 0.374]  | P(talent > career median) = 13.8%  | P(talent > league avg .320) = **55.2%**  | Games to 200 FP: 77

- **Historical comps (2015-25, age-matched):** 677 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.5%**  | P(bounce 60PA) = 71.3%  | Median next-30PA xwOBA: 0.311  | 10-90 range: [0.228, 0.411]

- **Process notes:** whiff% +6.3pt (worsening); chase% +2.6pt (worsening); z-contact% -4.3pt (worsening); EV90 -1.5mph (power flagging); hard-hit% +4.2pt (up); bat speed +1.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ben Rice (Late Night Bettsing, 1B)

- **Career %ile:** 14.8%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 88% of 152 comparables bounced  | uplift: +0.090/PA

- **Bayesian shrunk gap:** +0.027  | anchor: 0.314  | anchor_in_CI: No

- **xwOBACON gap:** +0.286 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 107.7→105.5

- **MC bounce (10k sims):** P(next 30PA > career median) = **45.0%**  | Expected xwOBA: 0.380  | 95% CI: [0.370, 0.392]

- **Bayesian talent:** posterior μ = 0.362  | 95% CI: [0.310, 0.414]  | P(talent > career median) = 24.3%  | P(talent > league avg .320) = **94.3%**  | Games to 200 FP: 92

- **Historical comps (2015-25, age-matched):** 365 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **60.8%**  | P(bounce 60PA) = 66.6%  | Median next-30PA xwOBA: 0.299  | 10-90 range: [0.218, 0.393]

- **Process notes:** whiff% -1.4pt (improving); chase% +5.8pt (worsening); z-contact% +1.8pt (improving); EV90 -2.2mph (power flagging); hard-hit% -10.7pt (down); bat speed -0.3mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — 88% historical bounce rate; shrunk gap +0.027


### Chase DeLauter (U Just Lost To Edwin Diaz, RF)

- **Career %ile:** 8.2%  | **Sust:** NO_BASELINE  | **Process:** MIXED

- **Bayesian shrunk gap:** -0.004  | anchor: 0.312  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.011 (contact intact (BABIP))

- **MC bounce (10k sims):** P(next 30PA > career median) = **50.8%**  | Expected xwOBA: 0.332  | 95% CI: [0.326, 0.339]

- **Bayesian talent:** posterior μ = 0.328  | 95% CI: [0.287, 0.369]  | P(talent > career median) = 43.0%  | P(talent > league avg .320) = **64.8%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 38 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **78.9%**  | P(bounce 60PA) = 86.8%  | Median next-30PA xwOBA: 0.312  | 10-90 range: [0.238, 0.392]

- **Process notes:** no baseline data

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Mike Trout (Team Solomon, DH)

- **Career %ile:** 16.0%  | **Sust:** NOISE  | **Process:** IMPROVING

- **Injury:** DTD (Strain, Right) — active DTD note

- **Bounce history (rh3):** 73% of 514 comparables bounced  | uplift: +0.066/PA

- **Bayesian shrunk gap:** +0.006  | anchor: 0.359  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.187 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.2→0.2  EV90 107.9→109.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **59.7%**  | Expected xwOBA: 0.403  | 95% CI: [0.384, 0.418]

- **Bayesian talent:** posterior μ = 0.405  | 95% CI: [0.344, 0.465]  | P(talent > career median) = 52.6%  | P(talent > league avg .320) = **99.7%**  | Games to 200 FP: 104

- **Historical comps (2015-25, age-matched):** 259 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **64.1%**  | P(bounce 60PA) = 68.3%  | Median next-30PA xwOBA: 0.338  | 10-90 range: [0.244, 0.441]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -5.0pt (improving); chase% +0.2pt (worsening); z-contact% +7.8pt (improving); EV90 +1.5mph (power up); hard-hit% +6.5pt (up); bat speed +1.0mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Liam Hicks (U Just Lost To Edwin Diaz, C)

- **Career %ile:** 2.9%  | **Sust:** NOISE  | **Process:** IMPROVING

- **Bounce history (rh3):** 65% of 88 comparables bounced  | uplift: +0.160/PA

- **Bayesian shrunk gap:** +0.004  | anchor: 0.270  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.021 (contact intact (BABIP))

- **Process:** whiff% 0.1→0.1  chase% 0.2→0.2  EV90 100.6→101.1

- **MC bounce (10k sims):** P(next 30PA > career median) = **58.2%**  | Expected xwOBA: 0.317  | 95% CI: [0.309, 0.324]

- **Bayesian talent:** posterior μ = 0.305  | 95% CI: [0.262, 0.348]  | P(talent > career median) = 30.2%  | P(talent > league avg .320) = **24.9%**  | Games to 200 FP: 106

- **Historical comps (2015-25, age-matched):** 106 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **77.4%**  | P(bounce 60PA) = 88.7%  | Median next-30PA xwOBA: 0.303  | 10-90 range: [0.227, 0.392]

- **Process notes:** whiff% -3.9pt (improving); chase% +6.5pt (worsening); z-contact% +6.6pt (improving); EV90 +0.5mph (power up); hard-hit% -3.7pt (down); bat speed +1.0mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Josh Naylor (Frendy's Fantastic Team, 1B)

- **Career %ile:** 2.8%  | **Sust:** REGRESS  | **Process:** IMPROVING

- **Bounce history (rh3):** 99% of 76 comparables bounced  | uplift: +0.083/PA

- **Bayesian shrunk gap:** -0.019  | anchor: 0.309  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.150 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.4→0.4  EV90 104.3→103.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **56.5%**  | Expected xwOBA: 0.332  | 95% CI: [0.325, 0.341]

- **Bayesian talent:** posterior μ = 0.325  | 95% CI: [0.282, 0.367]  | P(talent > career median) = 36.7%  | P(talent > league avg .320) = **58.5%**  | Games to 200 FP: 78

- **Historical comps (2015-25, age-matched):** 518 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **66.2%**  | P(bounce 60PA) = 73.2%  | Median next-30PA xwOBA: 0.307  | 10-90 range: [0.231, 0.405]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% -3.1pt (improving); chase% +6.7pt (worsening); z-contact% +4.3pt (improving); EV90 -0.5mph (power flagging); hard-hit% -3.6pt (down); bat speed -0.8mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Vladimir Guerrero Jr. (New York Ligers, 1B)

- **Career %ile:** 7.9%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 83% of 499 comparables bounced  | uplift: +0.069/PA

- **Bayesian shrunk gap:** -0.006  | anchor: 0.328  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.006 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 110.3→106.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **41.5%**  | Expected xwOBA: 0.380  | 95% CI: [0.366, 0.395]

- **Bayesian talent:** posterior μ = 0.345  | 95% CI: [0.287, 0.404]  | P(talent > career median) = 11.8%  | P(talent > league avg .320) = **80.0%**  | Games to 200 FP: 78

- **Historical comps (2015-25, age-matched):** 597 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.3%**  | P(bounce 60PA) = 71.9%  | Median next-30PA xwOBA: 0.318  | 10-90 range: [0.237, 0.428]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +1.1pt (worsening); chase% +11.4pt (worsening); z-contact% -2.0pt (worsening); EV90 -4.1mph (power flagging); hard-hit% -12.7pt (down); bat speed -0.4mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Alex Bregman (2015 Draft First Round, 3B)

- **Career %ile:** 9.7%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 98% of 65 comparables bounced  | uplift: +0.136/PA

- **Bayesian shrunk gap:** -0.006  | anchor: 0.304  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.067 (contact declining)

- **Process:** whiff% 0.1→0.1  chase% 0.2→0.2  EV90 102.8→100.7

- **MC bounce (10k sims):** P(next 30PA > career median) = **47.7%**  | Expected xwOBA: 0.342  | 95% CI: [0.332, 0.351]

- **Bayesian talent:** posterior μ = 0.333  | 95% CI: [0.285, 0.381]  | P(talent > career median) = 36.2%  | P(talent > league avg .320) = **70.2%**  | Games to 200 FP: 83

- **Historical comps (2015-25, age-matched):** 413 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.7%**  | P(bounce 60PA) = 72.2%  | Median next-30PA xwOBA: 0.338  | 10-90 range: [0.249, 0.456]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +1.0pt (worsening); chase% -3.0pt (improving); z-contact% +0.0pt (improving); EV90 -2.1mph (power flagging); hard-hit% -12.1pt (down); bat speed -1.0mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Brice Turang (Treasure Island Mashers, 2B)

- **Career %ile:** 13.5%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 57% of 383 comparables bounced  | uplift: +0.022/PA

- **Bayesian shrunk gap:** -0.003  | anchor: 0.299  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.000 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 104.2→104.7

- **MC bounce (10k sims):** P(next 30PA > career median) = **93.5%**  | Expected xwOBA: 0.322  | 95% CI: [0.310, 0.336]

- **Bayesian talent:** posterior μ = 0.310  | 95% CI: [0.256, 0.363]  | P(talent > career median) = 33.5%  | P(talent > league avg .320) = **35.5%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 719 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **61.6%**  | P(bounce 60PA) = 69.1%  | Median next-30PA xwOBA: 0.307  | 10-90 range: [0.222, 0.400]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -2.5pt (improving); chase% +1.4pt (worsening); z-contact% +0.1pt (improving); EV90 +0.5mph (power up); hard-hit% -10.7pt (down); bat speed +1.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Daylen Lile (2015 Draft First Round, RF)

- **Career %ile:** 9.2%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 100% of 4 comparables bounced  | uplift: +0.205/PA

- **Bayesian shrunk gap:** +0.006  | anchor: 0.273  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.214 (contact declining)

- **Process:** whiff% 0.1→0.2  chase% 0.3→0.4  EV90 103.9→104.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **41.8%**  | Expected xwOBA: 0.336  | 95% CI: [0.325, 0.344]

- **Bayesian talent:** posterior μ = 0.307  | 95% CI: [0.257, 0.358]  | P(talent > career median) = 13.4%  | P(talent > league avg .320) = **31.1%**  | Games to 200 FP: 82

- **Historical comps (2015-25, age-matched):** 118 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **71.2%**  | P(bounce 60PA) = 78.8%  | Median next-30PA xwOBA: 0.301  | 10-90 range: [0.226, 0.398]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +1.0pt (worsening); chase% +16.7pt (worsening); z-contact% -0.5pt (worsening); EV90 +0.7mph (power up); hard-hit% +3.4pt (up); bat speed +2.0mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Gunnar Henderson (Boone's Bad Bullpen, SS)

- **Career %ile:** 7.0%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 45 comparables bounced  | uplift: +0.130/PA

- **Bayesian shrunk gap:** -0.001  | anchor: 0.325  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.024 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.3  EV90 106.8→104.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **48.9%**  | Expected xwOBA: 0.345  | 95% CI: [0.333, 0.355]

- **Bayesian talent:** posterior μ = 0.322  | 95% CI: [0.272, 0.373]  | P(talent > career median) = 18.9%  | P(talent > league avg .320) = **53.5%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 472 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **67.8%**  | P(bounce 60PA) = 74.6%  | Median next-30PA xwOBA: 0.315  | 10-90 range: [0.232, 0.420]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% -1.6pt (improving); chase% +6.0pt (worsening); z-contact% +4.2pt (improving); EV90 -2.0mph (power flagging); hard-hit% -4.8pt (down); bat speed -1.1mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Spencer Steer (Late Night Bettsing, 1B)

- **Career %ile:** 15.9%  | **Sust:** STABLE  | **Process:** IMPROVING

- **Bounce history (rh3):** 91% of 163 comparables bounced  | uplift: +0.105/PA

- **Bayesian shrunk gap:** +0.001  | anchor: 0.314  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.018 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.3  EV90 102.0→102.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **64.9%**  | Expected xwOBA: 0.321  | 95% CI: [0.312, 0.335]

- **Bayesian talent:** posterior μ = 0.296  | 95% CI: [0.239, 0.353]  | P(talent > career median) = 19.8%  | P(talent > league avg .320) = **20.8%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 714 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **59.2%**  | P(bounce 60PA) = 62.9%  | Median next-30PA xwOBA: 0.309  | 10-90 range: [0.225, 0.402]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% -2.4pt (improving); chase% +2.6pt (worsening); z-contact% +4.1pt (improving); EV90 +0.6mph (power up); hard-hit% +7.8pt (up); bat speed +0.6mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Kyle Tucker (Late Night Bettsing, RF)

- **Career %ile:** 13.9%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 40 comparables bounced  | uplift: +0.197/PA

- **Bayesian shrunk gap:** +0.000  | anchor: 0.333  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.018 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 103.9→102.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **56.6%**  | Expected xwOBA: 0.370  | 95% CI: [0.360, 0.381]

- **Bayesian talent:** posterior μ = 0.372  | 95% CI: [0.317, 0.427]  | P(talent > career median) = 52.6%  | P(talent > league avg .320) = **96.8%**  | Games to 200 FP: 70

- **Historical comps (2015-25, age-matched):** 946 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **58.5%**  | P(bounce 60PA) = 62.4%  | Median next-30PA xwOBA: 0.310  | 10-90 range: [0.225, 0.412]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +3.3pt (worsening); chase% +2.9pt (worsening); z-contact% -2.1pt (worsening); EV90 -1.9mph (power flagging); hard-hit% +2.0pt (up); bat speed +0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Sal Stewart (Frendy's Fantastic Team, 1B)

- **Career %ile:** 10.9%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bayesian shrunk gap:** -0.008  | anchor: 0.328  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.005 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.3  EV90 107.4→104.7

- **MC bounce (10k sims):** P(next 30PA > career median) = **99.2%**  | Expected xwOBA: 0.352  | 95% CI: [0.345, 0.365]

- **Bayesian talent:** posterior μ = 0.345  | 95% CI: [0.296, 0.394]  | P(talent > career median) = 38.0%  | P(talent > league avg .320) = **83.8%**  | Games to 200 FP: 90

- **Historical comps (2015-25, age-matched):** 48 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.8%**  | P(bounce 60PA) = 79.2%  | Median next-30PA xwOBA: 0.293  | 10-90 range: [0.229, 0.376]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +3.2pt (worsening); chase% -3.7pt (improving); z-contact% -4.5pt (worsening); EV90 -2.7mph (power flagging); hard-hit% -13.5pt (down); bat speed -0.1mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ozzie Albies (Frendy's Fantastic Team, 2B)

- **Career %ile:** 16.6%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 55% of 955 comparables bounced  | uplift: +0.013/PA

- **Bayesian shrunk gap:** -0.011  | anchor: 0.303  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.056 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.4  EV90 100.8→100.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **74.9%**  | Expected xwOBA: 0.315  | 95% CI: [0.306, 0.325]

- **Bayesian talent:** posterior μ = 0.293  | 95% CI: [0.246, 0.339]  | P(talent > career median) = 17.4%  | P(talent > league avg .320) = **12.2%**  | Games to 200 FP: 91

- **Historical comps (2015-25, age-matched):** 695 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **59.6%**  | P(bounce 60PA) = 65.2%  | Median next-30PA xwOBA: 0.330  | 10-90 range: [0.240, 0.446]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +0.1pt (worsening); chase% +3.0pt (worsening); z-contact% +0.8pt (improving); EV90 +0.1mph (power up); hard-hit% -4.1pt (down); bat speed +0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### JJ Wetherholt (Team Solomon, SS)

- **Career %ile:** 19.4%  | **Sust:** NO_BASELINE  | **Process:** MIXED

- **Bayesian shrunk gap:** +0.005  | anchor: 0.337  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.070 (contact declining)

- **MC bounce (10k sims):** P(next 30PA > career median) = **56.3%**  | Expected xwOBA: 0.358  | 95% CI: [0.354, 0.362]

- **Bayesian talent:** posterior μ = 0.357  | 95% CI: [0.334, 0.381]  | P(talent > career median) = 49.1%  | P(talent > league avg .320) = **99.9%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 59 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **59.3%**  | P(bounce 60PA) = 67.8%  | Median next-30PA xwOBA: 0.280  | 10-90 range: [0.217, 0.354]

- **Process notes:** no baseline data

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ernie Clement (U Just Lost To Edwin Diaz, 3B)

- **Career %ile:** 10.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 71% of 280 comparables bounced  | uplift: +0.056/PA

- **Bayesian shrunk gap:** +0.009  | anchor: 0.253  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.072 (contact declining)

- **Process:** whiff% 0.1→0.2  chase% 0.4→0.5  EV90 100.3→99.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **46.3%**  | Expected xwOBA: 0.286  | 95% CI: [0.280, 0.291]

- **Bayesian talent:** posterior μ = 0.284  | 95% CI: [0.251, 0.318]  | P(talent > career median) = 46.9%  | P(talent > league avg .320) = **1.9%**  | Games to 200 FP: 93

- **Historical comps (2015-25, age-matched):** 570 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.1%**  | P(bounce 60PA) = 72.1%  | Median next-30PA xwOBA: 0.309  | 10-90 range: [0.224, 0.404]

- **K-decomp source:** MIXED

- **Process notes:** whiff% +2.9pt (worsening); chase% +11.2pt (worsening); z-contact% -1.3pt (worsening); EV90 -1.1mph (power flagging); hard-hit% -8.1pt (down); bat speed +0.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Brandon Lowe (2015 Draft First Round, 2B)

- **Career %ile:** 5.6%  | **Sust:** STABLE  | **Process:** STABLE

- **Bounce history (rh3):** 54% of 582 comparables bounced  | uplift: +0.015/PA

- **Bayesian shrunk gap:** +0.004  | anchor: 0.310  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.153 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 106.4→107.1

- **MC bounce (10k sims):** P(next 30PA > career median) = **75.2%**  | Expected xwOBA: 0.343  | 95% CI: [0.333, 0.352]

- **Bayesian talent:** posterior μ = 0.345  | 95% CI: [0.297, 0.392]  | P(talent > career median) = 53.2%  | P(talent > league avg .320) = **84.3%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 581 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.4%**  | P(bounce 60PA) = 68.0%  | Median next-30PA xwOBA: 0.309  | 10-90 range: [0.230, 0.393]

- **Process notes:** whiff% +1.2pt (worsening); chase% -2.3pt (improving); z-contact% +1.1pt (improving); EV90 +0.7mph (power up); hard-hit% +2.7pt (up); bat speed +0.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### TJ Rumfield (U Just Lost To Edwin Diaz, 3B)

- **Career %ile:** 4.8%  | **Sust:** NO_BASELINE  | **Process:** MIXED

- **Bayesian shrunk gap:** +0.001  | anchor: 0.290  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.018 (contact intact (BABIP))

- **MC bounce (10k sims):** P(next 30PA > career median) = **33.2%**  | Expected xwOBA: 0.321  | 95% CI: [0.315, 0.326]

- **Bayesian talent:** posterior μ = 0.320  | 95% CI: [0.283, 0.356]  | P(talent > career median) = 46.4%  | P(talent > league avg .320) = **48.9%**  | Games to 200 FP: 102

- **Historical comps (2015-25, age-matched):** 42 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **78.6%**  | P(bounce 60PA) = 88.1%  | Median next-30PA xwOBA: 0.312  | 10-90 range: [0.236, 0.390]

- **Process notes:** no baseline data

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Jackson Merrill (Late Night Bettsing, CF)

- **Career %ile:** 2.9%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 13 comparables bounced  | uplift: +0.198/PA

- **Bayesian shrunk gap:** -0.007  | anchor: 0.307  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.125 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.4→0.4  EV90 105.3→101.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **96.7%**  | Expected xwOBA: 0.349  | 95% CI: [0.340, 0.363]

- **Bayesian talent:** posterior μ = 0.310  | 95% CI: [0.255, 0.366]  | P(talent > career median) = 8.4%  | P(talent > league avg .320) = **36.5%**  | Games to 200 FP: 89

- **Historical comps (2015-25, age-matched):** 136 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **72.8%**  | P(bounce 60PA) = 78.7%  | Median next-30PA xwOBA: 0.308  | 10-90 range: [0.222, 0.399]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +2.2pt (worsening); chase% -1.7pt (improving); z-contact% -2.7pt (worsening); EV90 -3.9mph (power flagging); hard-hit% -3.2pt (down); bat speed +1.0mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Christian Walker (U Just Lost To Edwin Diaz, 1B)

- **Career %ile:** 1.6%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 57% of 926 comparables bounced  | uplift: +0.015/PA

- **Bayesian shrunk gap:** +0.023  | anchor: 0.256  | anchor_in_CI: No

- **xwOBACON gap:** +0.185 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 107.5→106.7

- **MC bounce (10k sims):** P(next 30PA > career median) = **46.0%**  | Expected xwOBA: 0.335  | 95% CI: [0.323, 0.345]

- **Bayesian talent:** posterior μ = 0.319  | 95% CI: [0.268, 0.369]  | P(talent > career median) = 26.0%  | P(talent > league avg .320) = **47.7%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 226 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **70.8%**  | P(bounce 60PA) = 76.5%  | Median next-30PA xwOBA: 0.316  | 10-90 range: [0.237, 0.403]

- **Process notes:** whiff% +2.3pt (worsening); chase% +3.7pt (worsening); z-contact% +5.0pt (improving); EV90 -0.8mph (power flagging); hard-hit% -5.2pt (down); bat speed -0.1mph

- **VERDICT:** SLUMP_AMBIGUOUS — mixed signals — run /slump-or-decline for full decomp


### Paul Goldschmidt (2015 Draft First Round, 1B)

- **Career %ile:** 0.0%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bayesian shrunk gap:** -0.021  | anchor: 0.292  | anchor_in_CI: No

- **xwOBACON gap:** -0.040 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.3→0.4  EV90 105.3→100.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **75.1%**  | Expected xwOBA: 0.360  | 95% CI: [0.350, 0.374]

- **Bayesian talent:** posterior μ = 0.298  | 95% CI: [0.241, 0.355]  | P(talent > career median) = 1.7%  | P(talent > league avg .320) = **22.7%**  | Games to 200 FP: 110

- **Historical comps (2015-25, age-matched):** 20 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **55.0%**  | P(bounce 60PA) = 55.0%  | Median next-30PA xwOBA: 0.332  | 10-90 range: [0.218, 0.426]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +10.6pt (worsening); chase% +9.7pt (worsening); z-contact% -17.3pt (worsening); EV90 -4.4mph (power flagging); hard-hit% -6.8pt (down); bat speed -2.4mph

- **VERDICT:** SLUMP_AMBIGUOUS — mixed signals — run /slump-or-decline for full decomp


### Corey Seager (Team Solomon, SS)

- **Career %ile:** 17.8%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Injury:** DTD (Inflammation, Not Specified) — active DTD note

- **Bounce history (rh3):** 100% of 63 comparables bounced  | uplift: +0.171/PA

- **Bayesian shrunk gap:** +0.001  | anchor: 0.334  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.007 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.3  chase% 0.2→0.3  EV90 108.0→105.3

- **MC bounce (10k sims):** P(next 30PA > career median) = **68.7%**  | Expected xwOBA: 0.385  | 95% CI: [0.373, 0.397]

- **Bayesian talent:** posterior μ = 0.374  | 95% CI: [0.307, 0.440]  | P(talent > career median) = 37.0%  | P(talent > league avg .320) = **94.2%**  | Games to 200 FP: 77

- **Historical comps (2015-25, age-matched):** 525 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **62.1%**  | P(bounce 60PA) = 66.7%  | Median next-30PA xwOBA: 0.338  | 10-90 range: [0.245, 0.445]

- **K-decomp source:** K_DRIVEN

- **Process notes:** whiff% +7.3pt (worsening); chase% +3.6pt (worsening); z-contact% -10.5pt (worsening); EV90 -2.7mph (power flagging); hard-hit% -9.4pt (down); bat speed -0.3mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Ian Happ (2015 Draft First Round, LF)

- **Career %ile:** 12.1%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 64% of 827 comparables bounced  | uplift: +0.050/PA

- **Bayesian shrunk gap:** -0.009  | anchor: 0.280  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.066 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.2→0.2  EV90 105.7→105.1

- **MC bounce (10k sims):** P(next 30PA > career median) = **32.7%**  | Expected xwOBA: 0.340  | 95% CI: [0.328, 0.351]

- **Bayesian talent:** posterior μ = 0.317  | 95% CI: [0.263, 0.370]  | P(talent > career median) = 19.5%  | P(talent > league avg .320) = **45.1%**  | Games to 200 FP: 97

- **Historical comps (2015-25, age-matched):** 592 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.3%**  | P(bounce 60PA) = 69.8%  | Median next-30PA xwOBA: 0.329  | 10-90 range: [0.234, 0.440]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% +7.3pt (worsening); chase% +3.7pt (worsening); z-contact% -4.5pt (worsening); EV90 -0.6mph (power flagging); hard-hit% -0.4pt (down); bat speed +1.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### George Springer (Frendy's Fantastic Team, DH)

- **Career %ile:** 12.6%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 96% of 281 comparables bounced  | uplift: +0.179/PA

- **Bayesian shrunk gap:** -0.018  | anchor: 0.328  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.093 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 107.2→105.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **59.8%**  | Expected xwOBA: 0.356  | 95% CI: [0.347, 0.371]

- **Bayesian talent:** posterior μ = 0.340  | 95% CI: [0.283, 0.398]  | P(talent > career median) = 28.9%  | P(talent > league avg .320) = **75.4%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 136 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **55.1%**  | P(bounce 60PA) = 55.9%  | Median next-30PA xwOBA: 0.328  | 10-90 range: [0.245, 0.435]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -4.2pt (improving); chase% +2.9pt (worsening); z-contact% +3.6pt (improving); EV90 -2.0mph (power flagging); hard-hit% -4.1pt (down); bat speed -0.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Trea Turner (Team Solomon, SS)

- **Career %ile:** 5.1%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 81% of 167 comparables bounced  | uplift: +0.100/PA

- **Bayesian shrunk gap:** +0.001  | anchor: 0.286  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.094 (contact declining)

- **Process:** whiff% 0.2→0.3  chase% 0.3→0.4  EV90 104.2→103.4

- **MC bounce (10k sims):** P(next 30PA > career median) = **39.0%**  | Expected xwOBA: 0.329  | 95% CI: [0.320, 0.341]

- **Bayesian talent:** posterior μ = 0.324  | 95% CI: [0.272, 0.377]  | P(talent > career median) = 42.7%  | P(talent > league avg .320) = **56.4%**  | Games to 200 FP: 85

- **Historical comps (2015-25, age-matched):** 267 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.7%**  | P(bounce 60PA) = 73.0%  | Median next-30PA xwOBA: 0.336  | 10-90 range: [0.250, 0.449]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +4.9pt (worsening); chase% +10.2pt (worsening); z-contact% -5.0pt (worsening); EV90 -0.8mph (power flagging); hard-hit% -1.9pt (down); bat speed +0.5mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Zach Neto (Boone's Bad Bullpen, SS)

- **Career %ile:** 7.9%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 98% of 42 comparables bounced  | uplift: +0.192/PA

- **Bayesian shrunk gap:** +0.001  | anchor: 0.283  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.078 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.4  EV90 105.7→104.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **33.1%**  | Expected xwOBA: 0.325  | 95% CI: [0.316, 0.333]

- **Bayesian talent:** posterior μ = 0.326  | 95% CI: [0.286, 0.367]  | P(talent > career median) = 51.9%  | P(talent > league avg .320) = **62.2%**  | Games to 200 FP: 99

- **Historical comps (2015-25, age-matched):** 472 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **69.9%**  | P(bounce 60PA) = 74.8%  | Median next-30PA xwOBA: 0.314  | 10-90 range: [0.233, 0.410]

- **Process notes:** whiff% +3.3pt (worsening); chase% +7.2pt (worsening); z-contact% +0.5pt (improving); EV90 -0.9mph (power flagging); hard-hit% -6.9pt (down); bat speed -1.1mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Nolan Arenado (Treasure Island Mashers, 3B)

- **Career %ile:** 0.0%  | **Sust:** STABLE  | **Process:** MIXED

- **Bounce history (rh3):** 93% of 138 comparables bounced  | uplift: +0.107/PA

- **Bayesian shrunk gap:** -0.012  | anchor: 0.272  | anchor_in_CI: YES — noise

- **xwOBACON gap:** -0.030 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.3  chase% 0.3→0.3  EV90 101.6→102.2

- **MC bounce (10k sims):** P(next 30PA > career median) = **93.9%**  | Expected xwOBA: 0.319  | 95% CI: [0.310, 0.330]

- **Bayesian talent:** posterior μ = 0.295  | 95% CI: [0.241, 0.348]  | P(talent > career median) = 18.9%  | P(talent > league avg .320) = **17.7%**  | Games to 200 FP: 96

- **Historical comps (2015-25, age-matched):** 95 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.4%**  | P(bounce 60PA) = 75.8%  | Median next-30PA xwOBA: 0.349  | 10-90 range: [0.251, 0.452]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +8.9pt (worsening); chase% -6.2pt (improving); z-contact% -9.7pt (worsening); EV90 +0.6mph (power up); hard-hit% +2.1pt (up); bat speed +0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Dansby Swanson (2015 Draft First Round, SS)

- **Career %ile:** 5.2%  | **Sust:** STABLE  | **Process:** IMPROVING

- **Bounce history (rh3):** 68% of 936 comparables bounced  | uplift: +0.041/PA

- **Bayesian shrunk gap:** +0.024  | anchor: 0.248  | anchor_in_CI: No

- **xwOBACON gap:** +0.238 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 104.7→103.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **44.0%**  | Expected xwOBA: 0.330  | 95% CI: [0.316, 0.341]

- **Bayesian talent:** posterior μ = 0.344  | 95% CI: [0.291, 0.396]  | P(talent > career median) = 69.2%  | P(talent > league avg .320) = **80.9%**  | Games to 200 FP: 108

- **Historical comps (2015-25, age-matched):** 343 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **65.6%**  | P(bounce 60PA) = 74.3%  | Median next-30PA xwOBA: 0.335  | 10-90 range: [0.248, 0.445]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -2.5pt (improving); chase% +0.7pt (worsening); z-contact% +3.2pt (improving); EV90 -0.9mph (power flagging); hard-hit% -6.2pt (down); bat speed +1.3mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Roman Anthony (Treasure Island Mashers, RF)

- **Career %ile:** 10.3%  | **Sust:** BAD_LUCK  | **Process:** IMPROVING

- **Injury:** DTD (Sprain, Right) — active DTD note

- **Bayesian shrunk gap:** +0.008  | anchor: 0.342  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.108 (contact declining)

- **Process:** whiff% 0.3→0.2  chase% 0.2→0.3  EV90 107.4→105.8

- **MC bounce (10k sims):** P(next 30PA > career median) = **80.7%**  | Expected xwOBA: 0.372  | 95% CI: [0.367, 0.377]

- **Bayesian talent:** posterior μ = 0.374  | 95% CI: [0.345, 0.403]  | P(talent > career median) = 54.6%  | P(talent > league avg .320) = **100.0%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 26 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **88.5%**  | P(bounce 60PA) = 100.0%  | Median next-30PA xwOBA: 0.324  | 10-90 range: [0.253, 0.384]

- **K-decomp source:** MIXED

- **Process notes:** whiff% -4.9pt (improving); chase% +5.6pt (worsening); z-contact% +5.8pt (improving); EV90 -1.6mph (power flagging); hard-hit% +2.3pt (up); bat speed +1.5mph

- **VERDICT:** CONSENSUS_HOLD_BOUNCE — process IMPROVING (whiff/chase/Z-contact) despite career-low percentile — outcome noise, not skill decline


### Alejandro Kirk (Treasure Island Mashers, C)

- **Career %ile:** 1.7%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bayesian shrunk gap:** +0.007  | anchor: 0.242  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.002 (contact intact (BABIP))

- **Process:** whiff% 0.2→0.1  chase% 0.3→0.3  EV90 106.6→101.7

- **MC bounce (10k sims):** P(next 30PA > career median) = **95.9%**  | Expected xwOBA: 0.343  | 95% CI: [0.334, 0.357]

- **Bayesian talent:** posterior μ = 0.299  | 95% CI: [0.240, 0.357]  | P(talent > career median) = 6.9%  | P(talent > league avg .320) = **23.8%**  | Games to 200 FP: 98

- **Historical comps (2015-25, age-matched):** 414 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **74.9%**  | P(bounce 60PA) = 80.9%  | Median next-30PA xwOBA: 0.318  | 10-90 range: [0.237, 0.406]

- **K-decomp source:** BABIP_DRIVEN

- **Process notes:** whiff% -0.5pt (improving); chase% +3.5pt (worsening); z-contact% +4.3pt (improving); EV90 -4.9mph (power flagging); hard-hit% -13.0pt (down); bat speed -2.4mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Christian Yelich (Frendy's Fantastic Team, DH)

- **Career %ile:** 10.5%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 92% of 487 comparables bounced  | uplift: +0.133/PA

- **Bayesian shrunk gap:** +0.004  | anchor: 0.299  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.123 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.3→0.2  EV90 106.7→104.6

- **MC bounce (10k sims):** P(next 30PA > career median) = **46.0%**  | Expected xwOBA: 0.352  | 95% CI: [0.341, 0.369]

- **Bayesian talent:** posterior μ = 0.330  | 95% CI: [0.270, 0.389]  | P(talent > career median) = 22.8%  | P(talent > league avg .320) = **62.4%**  | Games to 200 FP: 86

- **Historical comps (2015-25, age-matched):** 215 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **63.7%**  | P(bounce 60PA) = 68.4%  | Median next-30PA xwOBA: 0.347  | 10-90 range: [0.252, 0.457]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -3.4pt (improving); chase% -4.5pt (improving); z-contact% +3.9pt (improving); EV90 -2.1mph (power flagging); hard-hit% -5.4pt (down); bat speed -0.2mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Cal Raleigh (Team Solomon, C)

- **Career %ile:** 3.6%  | **Sust:** REGRESS  | **Process:** DECLINING

- **Bounce history (rh3):** 95% of 108 comparables bounced  | uplift: +0.189/PA

- **Bayesian shrunk gap:** -0.006  | anchor: 0.286  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.100 (contact declining)

- **Process:** whiff% 0.3→0.3  chase% 0.3→0.3  EV90 107.0→104.0

- **MC bounce (10k sims):** P(next 30PA > career median) = **70.0%**  | Expected xwOBA: 0.343  | 95% CI: [0.332, 0.353]

- **Bayesian talent:** posterior μ = 0.323  | 95% CI: [0.269, 0.376]  | P(talent > career median) = 22.9%  | P(talent > league avg .320) = **53.9%**  | Games to 200 FP: 87

- **Historical comps (2015-25, age-matched):** 470 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.9%**  | P(bounce 60PA) = 74.9%  | Median next-30PA xwOBA: 0.309  | 10-90 range: [0.229, 0.404]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% -1.3pt (improving); chase% +1.3pt (worsening); z-contact% +0.5pt (improving); EV90 -3.0mph (power flagging); hard-hit% -21.4pt (down); bat speed -0.6mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


### Max Muncy (New York Ligers, 3B)

- **Career %ile:** 3.7%  | **Sust:** STABLE  | **Process:** DECLINING

- **Bounce history (rh3):** 100% of 11 comparables bounced  | uplift: +0.062/PA

- **Bayesian shrunk gap:** +0.000  | anchor: 0.310  | anchor_in_CI: YES — noise

- **xwOBACON gap:** +0.078 (contact declining)

- **Process:** whiff% 0.2→0.2  chase% 0.2→0.2  EV90 105.8→104.9

- **MC bounce (10k sims):** P(next 30PA > career median) = **73.5%**  | Expected xwOBA: 0.371  | 95% CI: [0.360, 0.385]

- **Bayesian talent:** posterior μ = 0.328  | 95% CI: [0.271, 0.386]  | P(talent > career median) = 7.1%  | P(talent > league avg .320) = **61.0%**  | Games to 200 FP: 82

- **Historical comps (2015-25, age-matched):** 204 comparables at similar career %ile/PA/month/age  | P(bounce 30PA) = **68.1%**  | P(bounce 60PA) = 70.1%  | Median next-30PA xwOBA: 0.314  | 10-90 range: [0.237, 0.400]

- **K-decomp source:** DISCIPLINE_COLLAPSE

- **Process notes:** whiff% +1.3pt (worsening); chase% -1.2pt (improving); z-contact% -2.8pt (worsening); EV90 -0.9mph (power flagging); hard-hit% -3.9pt (down); bat speed +0.7mph

- **VERDICT:** HOLD_NOISE — L21d CI includes anchor — statistically indistinguishable from baseline


## PEAK player validator (v3 — with survival curves)


### Miguel Vargas (Frendy's Fantastic Team, 3B) — MIXED

- **Career %ile:** 92.1%  | **rh3:** 0.619  | **Sust:** IMPROVING

- **Bayesian talent:** posterior μ = 0.390  | P(true talent > .320) = **97.9%**  | P(true talent > career median) = 96.2%

- **Historical comps:** 408 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 21.1%  | Median next-30PA xwOBA: 0.297

- **Peak survival:** P(still PEAK at +30PA) = **92.7%** [92.5%, 92.8%]  | +60PA = 82.2% [82.0%, 82.4%]  | Expected weeks to reversion: 6.7  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: bat_speed +3.8mph; xwOBAcon +0.099

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Hunter Goodman (New York Ligers, C) — MIXED

- **Career %ile:** 99.9%  | **rh3:** 0.575  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.321  | P(true talent > .320) = **52.2%**  | P(true talent > career median) = 61.3%

- **Historical comps:** 229 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 13.1%  | Median next-30PA xwOBA: 0.297

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (2/6). Improving: bat_speed +1.2mph; xwOBAcon +0.042

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Pete Crow-Armstrong (Boone's Bad Bullpen, CF) — PROCESS_DRIVEN

- **Career %ile:** 95.3%  | **rh3:** 0.550  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.352  | P(true talent > .320) = **84.5%**  | P(true talent > career median) = 79.4%

- **Historical comps:** 247 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 18.6%  | Median next-30PA xwOBA: 0.297

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- bat_speed +1.5mph — chase% -5.4pt — xwOBAcon +0.046 — all physical inputs improved

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Kody Clemens (New York Ligers, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 98.2%  | **rh3:** 0.534  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.332  | P(true talent > .320) = **68.0%**  | P(true talent > career median) = 76.0%

- **Historical comps:** 164 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 11.6%  | Median next-30PA xwOBA: 0.289

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Randy Arozarena (Treasure Island Mashers, LF) — MIXED

- **Career %ile:** 97.6%  | **rh3:** 0.513  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.329  | P(true talent > .320) = **62.6%**  | P(true talent > career median) = 55.8%

- **Historical comps:** 570 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 20.0%  | Median next-30PA xwOBA: 0.329

- **Peak survival:** P(still PEAK at +30PA) = **91.4%** [91.3%, 91.5%]  | +60PA = 80.0% [79.8%, 80.2%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- Partial process improvement (1/6). Improving: whiff% -2.4pt

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


### Jake Bauers (U Just Lost To Edwin Diaz, 1B) — OUTCOME_DRIVEN

- **Career %ile:** 96.0%  | **rh3:** 0.502  | **Sust:** STABLE

- **Bayesian talent:** posterior μ = 0.333  | P(true talent > .320) = **68.3%**  | P(true talent > career median) = 60.4%

- **Historical comps:** 363 real peak comps (2015-25)  | P(meaningful bounce upward from current) = 16.0%  | Median next-30PA xwOBA: 0.308

- **Peak survival:** P(still PEAK at +30PA) = **89.2%** [89.0%, 89.5%]  | +60PA = 76.2% [75.9%, 76.5%]  | Expected weeks to reversion: 5.6  | Trade window: **HOLD_SHORT**

- No process metrics improved. Surface outcomes likely inflated over true skill.

- **Trade implication:** CONSENSUS_HOLD_PEAK — at career peak


## SP velo flags (> 1.0 mph drop, injury/fatigue signal)

_No SP velo flags this week._

## Statistical confidence summary

_For each slumper, the convergence of 4 independent statistical tests:_

| Player | MC P(bounce) | Bayes P(>avg) | Hist comps | Hist P(bounce 30PA) | Injury | Verdict |

|---|---|---|---|---|---|---|

| Corbin Carroll | 39.5% | 55.2% | 677 | 63.5% | NONE | HOLD_NOISE |

| Ben Rice | 45.0% | 94.3% | 365 | 60.8% | NONE | CONSENSUS_HOLD_BOUNCE |

| Chase DeLauter | 50.8% | 64.8% | 38 | 78.9% | NONE | HOLD_NOISE |

| Mike Trout | 59.7% | 99.7% | 259 | 64.1% | DTD | CONSENSUS_HOLD_BOUNCE |

| Liam Hicks | 58.2% | 24.9% | 106 | 77.4% | NONE | CONSENSUS_HOLD_BOUNCE |

| Josh Naylor | 56.5% | 58.5% | 518 | 66.2% | NONE | CONSENSUS_HOLD_BOUNCE |

| Vladimir Guerrero Jr. | 41.5% | 80.0% | 597 | 65.3% | NONE | HOLD_NOISE |

| Alex Bregman | 47.7% | 70.2% | 413 | 63.7% | NONE | HOLD_NOISE |

| Brice Turang | 93.5% | 35.5% | 719 | 61.6% | NONE | HOLD_NOISE |

| Daylen Lile | 41.8% | 31.1% | 118 | 71.2% | NONE | HOLD_NOISE |

| Gunnar Henderson | 48.9% | 53.5% | 472 | 67.8% | NONE | HOLD_NOISE |

| Spencer Steer | 64.9% | 20.8% | 714 | 59.2% | NONE | CONSENSUS_HOLD_BOUNCE |

| Kyle Tucker | 56.6% | 96.8% | 946 | 58.5% | NONE | HOLD_NOISE |

| Sal Stewart | 99.2% | 83.8% | 48 | 68.8% | NONE | HOLD_NOISE |

| Ozzie Albies | 74.9% | 12.2% | 695 | 59.6% | NONE | HOLD_NOISE |

| JJ Wetherholt | 56.3% | 99.9% | 59 | 59.3% | NONE | HOLD_NOISE |

| Ernie Clement | 46.3% | 1.9% | 570 | 65.1% | NONE | HOLD_NOISE |

| Brandon Lowe | 75.2% | 84.3% | 581 | 65.4% | NONE | HOLD_NOISE |

| TJ Rumfield | 33.2% | 48.9% | 42 | 78.6% | NONE | HOLD_NOISE |

| Jackson Merrill | 96.7% | 36.5% | 136 | 72.8% | NONE | HOLD_NOISE |

| Christian Walker | 46.0% | 47.7% | 226 | 70.8% | NONE | SLUMP_AMBIGUOUS |

| Paul Goldschmidt | 75.1% | 22.7% | 20 | 55.0% | NONE | SLUMP_AMBIGUOUS |

| Corey Seager | 68.7% | 94.2% | 525 | 62.1% | DTD | HOLD_NOISE |

| Ian Happ | 32.7% | 45.1% | 592 | 63.3% | NONE | HOLD_NOISE |

| George Springer | 59.8% | 75.4% | 136 | 55.1% | NONE | HOLD_NOISE |

| Trea Turner | 39.0% | 56.4% | 267 | 63.7% | NONE | HOLD_NOISE |

| Zach Neto | 33.1% | 62.2% | 472 | 69.9% | NONE | HOLD_NOISE |

| Nolan Arenado | 93.9% | 17.7% | 95 | 68.4% | NONE | HOLD_NOISE |

| Dansby Swanson | 44.0% | 80.9% | 343 | 65.6% | NONE | CONSENSUS_HOLD_BOUNCE |

| Roman Anthony | 80.7% | 100.0% | 26 | 88.5% | DTD | CONSENSUS_HOLD_BOUNCE |

| Alejandro Kirk | 95.9% | 23.8% | 414 | 74.9% | NONE | HOLD_NOISE |

| Christian Yelich | 46.0% | 62.4% | 215 | 63.7% | NONE | HOLD_NOISE |

| Cal Raleigh | 70.0% | 53.9% | 470 | 68.9% | NONE | HOLD_NOISE |

| Max Muncy | 73.5% | 61.0% | 204 | 68.1% | NONE | HOLD_NOISE |


## Waiver wire targets — slumpers bouncing back

_Statistically supported bounce candidates on rival rosters — watch for drops or offer a low-cost add._

| team_name                 | player_name      | position   |   career_%ile | form_bucket   | process_verdict   |   mc_p_bounce_median |   bayes_p_above_avg |   hist_p_bounce_30pa |   rh3_per_pa |   replacement_delta | cross_verdict         |
|:--------------------------|:-----------------|:-----------|--------------:|:--------------|:------------------|---------------------:|--------------------:|---------------------:|-------------:|--------------------:|:----------------------|
| Late Night Bettsing       | Ben Rice         | 1B         |         0.148 | SLUMPING      | DECLINING         |               0.4503 |              0.9435 |             0.608219 |        0.61  |               0.046 | CONSENSUS_HOLD_BOUNCE |
| U Just Lost To Edwin Diaz | Chase DeLauter   | RF         |         0.082 | SLUMPING      | MIXED             |               0.508  |              0.6482 |             0.789474 |        0.581 |               0.074 | HOLD_NOISE            |
| Team Solomon              | Mike Trout       | DH         |         0.16  | SLUMPING      | IMPROVING         |               0.5969 |              0.9969 |             0.640927 |        0.569 |               0.062 | CONSENSUS_HOLD_BOUNCE |
| U Just Lost To Edwin Diaz | Liam Hicks       | C          |         0.029 | SLUMPING      | IMPROVING         |               0.5816 |              0.2494 |             0.773585 |        0.566 |               0.011 | CONSENSUS_HOLD_BOUNCE |
| 2015 Draft First Round    | Alex Bregman     | 3B         |         0.097 | SLUMPING      | DECLINING         |               0.477  |              0.7021 |             0.636804 |        0.55  |               0.024 | HOLD_NOISE            |
| Treasure Island Mashers   | Brice Turang     | 2B         |         0.135 | SLUMPING      | MIXED             |               0.9353 |              0.3547 |             0.616134 |        0.548 |               0.03  | HOLD_NOISE            |
| 2015 Draft First Round    | Daylen Lile      | RF         |         0.092 | SLUMPING      | MIXED             |               0.418  |              0.3112 |             0.711864 |        0.546 |               0.039 | HOLD_NOISE            |
| Boone's Bad Bullpen       | Gunnar Henderson | SS         |         0.07  | SLUMPING      | DECLINING         |               0.4886 |              0.5348 |             0.677966 |        0.544 |               0.03  | HOLD_NOISE            |
| Late Night Bettsing       | Spencer Steer    | 1B         |         0.159 | SLUMPING      | IMPROVING         |               0.6489 |              0.2075 |             0.592437 |        0.544 |               0.037 | CONSENSUS_HOLD_BOUNCE |
| Late Night Bettsing       | Kyle Tucker      | RF         |         0.139 | SLUMPING      | DECLINING         |               0.5658 |              0.9682 |             0.584567 |        0.542 |               0.035 | HOLD_NOISE            |
| Frendy's Fantastic Team   | Ozzie Albies     | 2B         |         0.166 | SLUMPING      | MIXED             |               0.7487 |              0.1219 |             0.595683 |        0.54  |               0.023 | HOLD_NOISE            |
| Team Solomon              | JJ Wetherholt    | SS         |         0.194 | SLUMPING      | MIXED             |               0.5634 |              0.999  |             0.59322  |        0.538 |               0.02  | HOLD_NOISE            |
| U Just Lost To Edwin Diaz | Ernie Clement    | 3B         |         0.105 | SLUMPING      | DECLINING         |               0.4632 |              0.0187 |             0.650877 |        0.531 |               0.014 | HOLD_NOISE            |
| 2015 Draft First Round    | Brandon Lowe     | 2B         |         0.056 | SLUMPING      | STABLE            |               0.752  |              0.8433 |             0.654045 |        0.527 |               0.009 | HOLD_NOISE            |
| Late Night Bettsing       | Jackson Merrill  | CF         |         0.029 | SLUMPING      | DECLINING         |               0.9672 |              0.3654 |             0.727941 |        0.52  |               0.013 | HOLD_NOISE            |
| Frendy's Fantastic Team   | George Springer  | DH         |         0.126 | SLUMPING      | DECLINING         |               0.5977 |              0.754  |             0.551471 |        0.5   |               0.103 | HOLD_NOISE            |

## FA add candidates

_Available free agents with model projections. Ownership < 90% in this 8-team league._

### FA hitters (top 15 by rh3 projection)

| player_name         | position   |   owned_% |   xfp_rh3_per_pa | rh3_signal   | form_bucket   | process_verdict   |   career_%ile | cross_verdict   |
|:--------------------|:-----------|----------:|-----------------:|:-------------|:--------------|:------------------|--------------:|:----------------|
| Spencer Horwitz     | 1B         |       8.9 |            0.625 | hold         | N/A           |                   |           nan |                 |
| Julio Rodriguez     | C          |       0.1 |            0.618 | add          | N/A           |                   |           nan |                 |
| Carlos Cortes       | RF         |       4.9 |            0.591 | add          | N/A           |                   |           nan |                 |
| Moises Ballesteros  | DH         |       2   |            0.59  | hold         | N/A           |                   |           nan |                 |
| Ryan Jeffers        | C          |      26.8 |            0.588 | hold         | N/A           |                   |           nan |                 |
| Vinnie Pasquantino  | 1B         |      46.4 |            0.563 | hold         | N/A           |                   |           nan |                 |
| Javier Sanoja       | LF         |       8.1 |            0.56  | hold         | N/A           |                   |           nan |                 |
| Tyler Tolbert       | CF         |       4.9 |            0.56  | hold         | N/A           |                   |           nan |                 |
| Randal Grichuk      | RF         |       0.2 |            0.557 | hold         | N/A           |                   |           nan |                 |
| Jared Young         | DH         |       0.2 |            0.556 | hold         | N/A           |                   |           nan |                 |
| Gabriel Moreno      | C          |      38   |            0.555 | hold         | N/A           |                   |           nan |                 |
| Trent Grisham       | CF         |      27.9 |            0.547 | hold         | N/A           |                   |           nan |                 |
| Colson Montgomery   | SS         |      41.2 |            0.545 | hold         | N/A           |                   |           nan |                 |
| Heriberto Hernandez | LF         |       1.4 |            0.542 | hold         | N/A           |                   |           nan |                 |
| Alec Bohm           | 3B         |      18.4 |            0.536 | hold         | N/A           |                   |           nan |                 |

### FA starting pitchers (top 10 by rp3 projection)

| player_name           |   owned_% |   rp3_proj/start |   form_gap |
|:----------------------|----------:|-----------------:|-----------:|
| Spencer Schwellenbach |      11.3 |            12.76 |       0    |
| Nick Pivetta          |      55.7 |            12.62 |       0    |
| Ronel Blanco          |       0.3 |            12.12 |       0    |
| Corbin Burnes         |       4.7 |            12.06 |       0    |
| Cole Ragans           |      54.5 |            11.85 |       0    |
| Kyle Bradish          |      69   |            11.55 |       8.31 |
| Pablo Lopez           |       3   |            11.46 |       0    |
| Spencer Strider       |      54.9 |            11.42 |       0    |
| Justin Steele         |       3.1 |            11.35 |       0    |
| Logan Henderson       |      18.7 |            11.34 |       0    |

### FA relief pitchers (top 10 by rprs2 projection)

| player_name         |   owned_% |   rprs2_proj_ros |
|:--------------------|----------:|-----------------:|
| Ryan Helsley        |      41.7 |            136.2 |
| Logan VanWey        |       0   |            107.4 |
| Jordan Romano       |       3   |            103.4 |
| Luke Weaver         |       6.1 |            100.6 |
| Cole Sands          |       0.3 |             97.8 |
| Kenley Jansen       |      36.9 |             95.5 |
| Graham Ashcraft     |       0.8 |             93.9 |
| Enyel De Los Santos |       0.3 |             92.4 |
| Brandyn Garcia      |       0.4 |             90   |
| Jeff Hoffman        |      40.7 |             86.9 |

## Watch list — your players showing peak regression risk

_Consider dropping or monitoring before value fades._

_None._

---

## Optional — trade context (if relevant)


### Trade targets — rival slumpers to buy

| team_name                 | player_name      | position   |   career_%ile | form_bucket   | process_verdict   |   mc_p_bounce_median |   bayes_p_above_avg |   hist_p_bounce_30pa |   rh3_per_pa |   replacement_delta | cross_verdict         |
|:--------------------------|:-----------------|:-----------|--------------:|:--------------|:------------------|---------------------:|--------------------:|---------------------:|-------------:|--------------------:|:----------------------|
| Late Night Bettsing       | Ben Rice         | 1B         |         0.148 | SLUMPING      | DECLINING         |               0.4503 |              0.9435 |             0.608219 |        0.61  |               0.046 | CONSENSUS_HOLD_BOUNCE |
| U Just Lost To Edwin Diaz | Chase DeLauter   | RF         |         0.082 | SLUMPING      | MIXED             |               0.508  |              0.6482 |             0.789474 |        0.581 |               0.074 | HOLD_NOISE            |
| Team Solomon              | Mike Trout       | DH         |         0.16  | SLUMPING      | IMPROVING         |               0.5969 |              0.9969 |             0.640927 |        0.569 |               0.062 | CONSENSUS_HOLD_BOUNCE |
| U Just Lost To Edwin Diaz | Liam Hicks       | C          |         0.029 | SLUMPING      | IMPROVING         |               0.5816 |              0.2494 |             0.773585 |        0.566 |               0.011 | CONSENSUS_HOLD_BOUNCE |
| 2015 Draft First Round    | Alex Bregman     | 3B         |         0.097 | SLUMPING      | DECLINING         |               0.477  |              0.7021 |             0.636804 |        0.55  |               0.024 | HOLD_NOISE            |
| Treasure Island Mashers   | Brice Turang     | 2B         |         0.135 | SLUMPING      | MIXED             |               0.9353 |              0.3547 |             0.616134 |        0.548 |               0.03  | HOLD_NOISE            |
| 2015 Draft First Round    | Daylen Lile      | RF         |         0.092 | SLUMPING      | MIXED             |               0.418  |              0.3112 |             0.711864 |        0.546 |               0.039 | HOLD_NOISE            |
| Boone's Bad Bullpen       | Gunnar Henderson | SS         |         0.07  | SLUMPING      | DECLINING         |               0.4886 |              0.5348 |             0.677966 |        0.544 |               0.03  | HOLD_NOISE            |
| Late Night Bettsing       | Spencer Steer    | 1B         |         0.159 | SLUMPING      | IMPROVING         |               0.6489 |              0.2075 |             0.592437 |        0.544 |               0.037 | CONSENSUS_HOLD_BOUNCE |
| Late Night Bettsing       | Kyle Tucker      | RF         |         0.139 | SLUMPING      | DECLINING         |               0.5658 |              0.9682 |             0.584567 |        0.542 |               0.035 | HOLD_NOISE            |
| Frendy's Fantastic Team   | Ozzie Albies     | 2B         |         0.166 | SLUMPING      | MIXED             |               0.7487 |              0.1219 |             0.595683 |        0.54  |               0.023 | HOLD_NOISE            |
| Team Solomon              | JJ Wetherholt    | SS         |         0.194 | SLUMPING      | MIXED             |               0.5634 |              0.999  |             0.59322  |        0.538 |               0.02  | HOLD_NOISE            |
| U Just Lost To Edwin Diaz | Ernie Clement    | 3B         |         0.105 | SLUMPING      | DECLINING         |               0.4632 |              0.0187 |             0.650877 |        0.531 |               0.014 | HOLD_NOISE            |
| 2015 Draft First Round    | Brandon Lowe     | 2B         |         0.056 | SLUMPING      | STABLE            |               0.752  |              0.8433 |             0.654045 |        0.527 |               0.009 | HOLD_NOISE            |
| Late Night Bettsing       | Jackson Merrill  | CF         |         0.029 | SLUMPING      | DECLINING         |               0.9672 |              0.3654 |             0.727941 |        0.52  |               0.013 | HOLD_NOISE            |
| Frendy's Fantastic Team   | George Springer  | DH         |         0.126 | SLUMPING      | DECLINING         |               0.5977 |              0.754  |             0.551471 |        0.5   |               0.103 | HOLD_NOISE            |

### Rival peakers cooling

_None._