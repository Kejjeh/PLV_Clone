# League-wide roster deep audit (full) — 2026-05-24

Hitters: 125 resolved. Slump diagnostics (xwOBACON + Bayesian shrinkage + calendar): 42 SLUMPING/BELOW_MEDIAN players. Pitchers: 104.

> **cross_verdict logic**: CONSENSUS_DROP now requires slump_bounce_pct < 50 AND shrunk_gap < −0.030 AND NOT anchor_in_CI. High bounce_pct OR xwOBACON intact → HOLD_BOUNCE instead.

## Power ranking

| team_name                 |   rank |   n |   mean_pct |   n_peak_high |   n_slump |   n_legit |   n_regress |   n_bounce |   n_drop |   n_sell |   mean_rh3 |   sp_pitch |
|:--------------------------|-------:|----:|-----------:|--------------:|----------:|----------:|------------:|-----------:|---------:|---------:|-----------:|-----------:|
| Late Night Bettsing       |      1 |  15 |      0.609 |             5 |         1 |         0 |           2 |          1 |        0 |        0 |      0.574 |      732.6 |
| U Just Lost To Edwin Diaz |      2 |  16 |      0.543 |             3 |         1 |         1 |           5 |          1 |        0 |        0 |      0.555 |      672.2 |
| 2015 Draft First Round    |      3 |  14 |      0.659 |             4 |         1 |         0 |           4 |          1 |        0 |        0 |      0.551 |      515   |
| New York Ligers           |      4 |  13 |      0.534 |             3 |         3 |         1 |           8 |          3 |        0 |        0 |      0.549 |      862.7 |
| Frendy's Fantastic Team   |      5 |  18 |      0.619 |             6 |         2 |         0 |           5 |          2 |        0 |        1 |      0.545 |      137.8 |
| Team Solomon              |      6 |  13 |      0.335 |             1 |         5 |         0 |           5 |          5 |        0 |        0 |      0.52  |      487.6 |
| Treasure Island Mashers   |      7 |  19 |      0.468 |             4 |         4 |         0 |           6 |          4 |        0 |        0 |      0.52  |      nan   |
| Boone's Bad Bullpen       |      8 |  17 |      0.582 |             4 |         2 |         1 |           5 |          2 |        0 |        0 |      0.511 |      505.8 |


## Per-team breakdown (hitters by position, then pitchers)


### New York Ligers ← YOU

**C**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict         | verdict_rationale                               |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:----------------------|:------------------------------------------------|
| Salvador Perez |         0.145 |          0.288 | SLUMPING      | REGRESS       |        0.469 | hold         |                 97 |       0.0244 |          0.163 | False          | CONSENSUS_HOLD_BOUNCE | 97% bounce rate historically; shrunk gap +0.024 |

**1B**

| player_name           |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:----------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Vladimir Guerrero Jr. |         0.132 |          0.34  | SLUMPING      | REGRESS       |        0.585 | hold         |               83   |       0.0052 |         -0.04  | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Pete Alonso           |         0.676 |          0.379 | ABOVE_MEDIAN  | REGRESS       |        0.575 | hold         |               96.6 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Luis Arraez           |         0.309 |          0.32  | BELOW_MEDIAN  | STABLE        |        0.546 | hold         |               94.8 |      -0.0089 |         -0.083 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict   | verdict_rationale         |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:----------------|:--------------------------|
| Max Muncy     |         0.863 |          0.416 | HIGH          | REGRESS       |        0.379 | drop         |                100 |              |            nan | False          | STABLE_HIGH     | high career form, holding |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Bo Bichette     |         0.541 |          0.342 | TYPICAL       | REGRESS       |        0.565 | hold         |              100   |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Elly De La Cruz |         0.858 |          0.375 | HIGH          | STABLE        |        0.54  | hold         |               66.1 |              |        nan     | False          | STABLE_HIGH            | high career form, holding                                           |
| Trea Turner     |         0.165 |          0.306 | SLUMPING      | REGRESS       |        0.511 | hold         |               81.4 |       0.0071 |          0.101 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |

**OF**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Aaron Judge       |         0.391 |          0.418 | BELOW_MEDIAN  | REGRESS       |        0.7   | add          |               64   |      -0.0181 |          0.057 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Corbin Carroll    |         0.781 |          0.375 | ABOVE_MEDIAN  | STABLE        |        0.636 | add          |               90   |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Michael Harris II |         0.774 |          0.376 | ABOVE_MEDIAN  | STABLE        |        0.624 | add          |               59.8 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Jordan Walker     |         0.818 |          0.354 | HIGH          | IMPROVING     |        0.523 | hold         |               51.8 |              |        nan     | False          | STABLE_HIGH            | high career form, holding                     |
| Wyatt Langford    |         0.483 |          0.332 | TYPICAL       | REGRESS       |        0.489 | hold         |               90.6 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |

**SP / RP**

| player_name     | position   |    proj |   form_gap |
|:----------------|:-----------|--------:|-----------:|
| Pete Fairbanks  | RP         | 197.8   |    nan     |
| Jhoan Duran     | RP         | 190.7   |    nan     |
| Ryan Helsley    | RP         | 190.5   |    nan     |
| Tanner Scott    | RP         | 140.7   |    nan     |
| Daniel Palencia | RP         | 132     |    nan     |
| Logan Henderson | SP         |  11.036 |      3.105 |
| Max Fried       | SP         | nan     |    nan     |
| Framber Valdez  | SP         | nan     |    nan     |
| Freddy Peralta  | SP         | nan     |    nan     |
| Tyler Glasnow   | SP         | nan     |    nan     |
| Carlos Rodon    | SP         | nan     |    nan     |
| Hunter Greene   | SP         | nan     |    nan     |
| Jose Soriano    | SP         | nan     |    nan     |
| Parker Messick  | SP         | nan     |    nan     |
| Will Warren     | SP         | nan     |    nan     |
| Kyle Bradish    | SP         | nan     |    nan     |


### 2015 Draft First Round

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Will Smith    |         0.526 |          0.359 | TYPICAL       | REGRESS       |        0.541 | hold         |               95.4 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**2B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale              |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:-------------------------------|
| Ketel Marte     |         0.77  |          0.378 | ABOVE_MEDIAN  | REGRESS       |        0.62  | add          |               86.8 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| Brandon Lowe    |         0.968 |          0.404 | PEAK          | STABLE        |        0.555 | hold         |               54.1 |              |            nan | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact |
| Ildemaro Vargas |         0.717 |          0.301 | ABOVE_MEDIAN  | STABLE        |        0.544 | hold         |               54.1 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale              |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:-------------------------------|
| Alex Bregman  |         0.473 |          0.345 | TYPICAL       | REGRESS       |        0.564 | hold         |               98.5 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| Josh Jung     |         0.903 |          0.376 | PEAK          | STABLE        |        0.527 | hold         |               57.2 |              |            nan | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact |

**SS**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Bobby Witt Jr. |         0.729 |          0.391 | ABOVE_MEDIAN  | BAD_LUCK      |        0.667 | add          |               71.5 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |
| Dansby Swanson |         0.496 |          0.328 | TYPICAL       | STABLE        |        0.458 | hold         |               68.4 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Brandon Nimmo |         0.961 |          0.396 | PEAK          | STABLE        |        0.578 | add          |               86.6 |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                                      |
| Daylen Lile   |         0.336 |          0.338 | BELOW_MEDIAN  | REGRESS       |        0.559 | hold         |              100   |      -0.02   |         -0.158 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |
| Sal Frelick   |         0.093 |          0.268 | SLUMPING      | BAD_LUCK      |        0.511 | hold         |               81.5 |      -0.0066 |         -0.042 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Ian Happ      |         0.644 |          0.353 | ABOVE_MEDIAN  | BAD_LUCK      |        0.499 | hold         |               64.4 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Riley Greene  |         0.884 |          0.39  | HIGH          | STABLE        |        0.479 | hold         |               71.3 |              |        nan     | False          | STABLE_HIGH            | high career form, holding                                           |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Kyle Schwarber |         0.725 |          0.393 | ABOVE_MEDIAN  | BAD_LUCK      |        0.613 | add          |               73.2 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**SP / RP**

| player_name     | position   |   proj |   form_gap |
|:----------------|:-----------|-------:|-----------:|
| Trevor Megill   | RP         |  157.2 |        nan |
| Bryan Baker     | RP         |  155.8 |        nan |
| Jakob Junis     | RP         |  106.2 |        nan |
| Robert Garcia   | RP         |   95.8 |        nan |
| Logan Gilbert   | SP         |  nan   |        nan |
| Jacob deGrom    | SP         |  nan   |        nan |
| Cole Ragans     | SP         |  nan   |        nan |
| Spencer Strider | SP         |  nan   |        nan |
| Nick Lodolo     | SP         |  nan   |        nan |
| Drew Rasmussen  | SP         |  nan   |        nan |
| Cam Schlittler  | SP         |  nan   |        nan |
| Shane Baz       | SP         |  nan   |        nan |
| Bryce Elder     | SP         |  nan   |        nan |
| Foster Griffin  | SP         |  nan   |        nan |


### Boone's Bad Bullpen

**C**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale              |
|:------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:-------------------------------|
| William Contreras |         0.781 |          0.357 | ABOVE_MEDIAN  | STABLE        |        0.601 | add          |               61   |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| Ryan Jeffers      |         0.999 |          0.395 | PEAK          | IMPROVING     |        0.595 | hold         |               63.7 |              |            nan | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact |
| Dillon Dingler    |         0.583 |          0.372 | TYPICAL       | STABLE        |        0.513 | hold         |               76   |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |

**1B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Freddie Freeman |         0.141 |          0.358 | SLUMPING      | STABLE        |        0.612 | hold         |               86   |      -0.0048 |          0.145 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Ryan O'Hearn    |         0.655 |          0.348 | ABOVE_MEDIAN  | STABLE        |        0.533 | hold         |               58.6 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |

**3B**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict     | verdict_rationale         |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:------------------|:--------------------------|
| Junior Caminero |         0.895 |          0.393 | HIGH          | STABLE        |        0.661 | add          |               92.8 |              |            nan | False          | STABLE_HIGH       | high career form, holding |
| Kazuma Okamoto  |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   |        0.455 | hold         |              nan   |              |            nan | False          | INSUFFICIENT_DATA | no career sample          |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Gunnar Henderson |         0.021 |          0.285 | SLUMPING      | REGRESS       |        0.538 | hold         |              100   |       0.0151 |          0.245 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Zach Neto        |         0.486 |          0.33  | TYPICAL       | REGRESS       |        0.492 | hold         |               97.6 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Konnor Griffin   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   |        0.413 | drop         |              nan   |              |        nan     | False          | INSUFFICIENT_DATA      | no career sample                                                    |

**OF**

| player_name         |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:--------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Angel Martinez      |         0.969 |          0.32  | PEAK          | STABLE        |        0.51  | hold         |               55.2 |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                |
| Tyler Soderstrom    |         0.316 |          0.326 | BELOW_MEDIAN  | REGRESS       |        0.508 | hold         |               98.4 |      -0.0151 |         -0.13  | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Mauricio Dubon      |         0.678 |          0.299 | ABOVE_MEDIAN  | STABLE        |        0.476 | hold         |               70.6 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Pete Crow-Armstrong |         0.765 |          0.337 | ABOVE_MEDIAN  | REGRESS       |        0.475 | hold         |               98.7 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Bryan Reynolds      |         0.323 |          0.338 | BELOW_MEDIAN  | STABLE        |        0.471 | hold         |               79.7 |       0.0006 |          0.095 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Steven Kwan         |         0.208 |          0.296 | BELOW_MEDIAN  | REGRESS       |        0.465 | hold         |              100   |       0.0042 |         -0.069 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Jac Caglianone      |         0.903 |          0.34  | PEAK          | STABLE        |        0.37  | drop         |              100   |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                |

**SP / RP**

| player_name      | position   |   proj |   form_gap |
|:-----------------|:-----------|-------:|-----------:|
| Raisel Iglesias  | RP         |  196   |        nan |
| David Bednar     | RP         |  172.1 |        nan |
| Garrett Whitlock | RP         |  137.7 |        nan |
| Paul Skenes      | SP         |  nan   |        nan |
| Jesus Luzardo    | SP         |  nan   |        nan |
| Andres Munoz     | RP         |  nan   |        nan |
| Tanner Bibee     | SP         |  nan   |        nan |
| Michael King     | SP         |  nan   |        nan |
| Gerrit Cole      | SP         |  nan   |        nan |
| Casey Mize       | SP         |  nan   |        nan |
| Nick Martinez    | SP         |  nan   |        nan |


### Frendy's Fantastic Team

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict       | verdict_rationale              |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:--------------------|:-------------------------------|
| Drake Baldwin |         0.998 |          0.417 | PEAK          | STABLE        |        0.679 | add          |               89.8 |              |            nan | False          | CONSENSUS_HOLD_PEAK | at career peak, process intact |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict     | verdict_rationale              |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:------------------|:-------------------------------|
| Sal Stewart   |       nan     |        nan     | INSUFFICIENT  | STABLE        |        0.586 | hold         |              nan   |              |            nan | False          | INSUFFICIENT_DATA | no career sample               |
| Josh Naylor   |         0.924 |          0.368 | PEAK          | REGRESS       |        0.571 | hold         |               98.7 |              |            nan | False          | SELL_HIGH_WARNING | PEAK form cooling (shrunk N/A) |

**2B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Nico Hoerner  |         0.821 |          0.336 | HIGH          | STABLE        |        0.577 | hold         |               59.7 |              |        nan     | False          | STABLE_HIGH            | high career form, holding                     |
| Ozzie Albies  |         0.397 |          0.31  | BELOW_MEDIAN  | STABLE        |        0.52  | hold         |               55.4 |       0.0024 |         -0.043 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |

**3B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict       | verdict_rationale              |
|:------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:--------------------|:-------------------------------|
| Miguel Vargas     |         0.994 |           0.43 | PEAK          | STABLE        |        0.58  | hold         |               53.8 |              |            nan | False          | CONSENSUS_HOLD_PEAK | at career peak, process intact |
| Munetaka Murakami |       nan     |         nan    | INSUFFICIENT  | NO_BASELINE   |        0.509 | hold         |              nan   |              |            nan | False          | INSUFFICIENT_DATA   | no career sample               |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict     | verdict_rationale   |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:------------------|:--------------------|
| Kevin McGonigle |           nan |            nan | INSUFFICIENT  | NO_BASELINE   |         0.53 | hold         |                nan |              |            nan | False          | INSUFFICIENT_DATA | no career sample    |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale              |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:-------------------------------|
| Cody Bellinger  |         0.938 |          0.421 | PEAK          | STABLE        |        0.645 | add          |               56.7 |              |            nan | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact |
| Julio Rodriguez |         0.802 |          0.369 | HIGH          | REGRESS       |        0.587 | add          |               92.1 |              |            nan | False          | STABLE_HIGH            | high career form, holding      |
| Jackson Chourio |         0.486 |          0.31  | TYPICAL       | STABLE        |        0.533 | hold         |              nan   |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| Taylor Ward     |         0.71  |          0.362 | ABOVE_MEDIAN  | STABLE        |        0.491 | hold         |               69.7 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| Jo Adell        |         0.734 |          0.343 | ABOVE_MEDIAN  | REGRESS       |        0.452 | hold         |               80.6 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| Cam Smith       |         0.573 |          0.334 | TYPICAL       | STABLE        |        0.397 | drop         |              100   |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |

**UTIL/DH**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Shohei Ohtani    |         0.448 |          0.391 | TYPICAL       | REGRESS       |        0.658 | hold         |               88.1 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Ivan Herrera     |         0.382 |          0.357 | BELOW_MEDIAN  | STABLE        |        0.551 | hold         |               91.8 |      -0.0029 |          0.036 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |
| George Springer  |         0.017 |          0.301 | SLUMPING      | REGRESS       |        0.492 | hold         |               95.7 |       0.004  |          0.113 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Christian Yelich |         0.065 |          0.307 | SLUMPING      | STABLE        |        0.462 | hold         |               92.3 |      -0.0044 |          0.015 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |

**SP / RP**

| player_name      | position   |    proj |   form_gap |
|:-----------------|:-----------|--------:|-----------:|
| Erik Sabrowski   | RP         | 126.1   |    nan     |
| Payton Tolle     | SP         |  11.739 |      0.108 |
| Joe Ryan         | SP         | nan     |    nan     |
| Hunter Brown     | SP         | nan     |    nan     |
| Brandon Woodruff | SP         | nan     |    nan     |
| Chase Burns      | SP         | nan     |    nan     |
| Connelly Early   | SP         | nan     |    nan     |
| Andrew Painter   | SP         | nan     |    nan     |
| Emerson Hancock  | SP         | nan     |    nan     |
| Kris Bubic       | SP         | nan     |    nan     |
| Michael Wacha    | SP         | nan     |    nan     |


### Late Night Bettsing

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Ben Rice          |         0.528 |          0.388 | TYPICAL       | STABLE        |        0.62  | hold         |               87.5 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Jonathan Aranda   |         0.294 |          0.35  | BELOW_MEDIAN  | STABLE        |        0.524 | hold         |               96.6 |      -0.0072 |         -0.003 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Willson Contreras |         0.843 |          0.39  | HIGH          | STABLE        |        0.514 | hold         |               72.6 |              |        nan     | False          | STABLE_HIGH            | high career form, holding                     |

**2B**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:-----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Gleyber Torres   |         0.504 |          0.338 | TYPICAL       | STABLE        |        0.462 | hold         |               73.4 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |
| Jackson Holliday |         0.489 |          0.312 | TYPICAL       | STABLE        |      nan     | nan          |              nan   |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict   | verdict_rationale         |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:----------------|:--------------------------|
| Jose Ramirez  |         0.819 |          0.381 | HIGH          | BAD_LUCK      |        0.669 | add          |               90.2 |              |            nan | False          | STABLE_HIGH     | high career form, holding |

**SS**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale              |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:-------------------------------|
| Mookie Betts   |         0.537 |          0.365 | TYPICAL       | STABLE        |        0.629 | add          |              nan   |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer             |
| CJ Abrams      |         0.852 |          0.355 | HIGH          | STABLE        |        0.557 | hold         |               57.6 |              |            nan | False          | STABLE_HIGH            | high career form, holding      |
| Brayan Rocchio |         0.962 |          0.319 | PEAK          | NOISE         |        0.457 | hold         |               71.1 |              |            nan | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact |

**OF**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Alec Burleson   |         0.923 |          0.388 | PEAK          | STABLE        |        0.579 | hold         |               66.6 |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                                      |
| Kyle Tucker     |         0.29  |          0.35  | BELOW_MEDIAN  | REGRESS       |        0.568 | add          |              100   |       0.0066 |          0.08  | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |
| Andy Pages      |         0.618 |          0.331 | ABOVE_MEDIAN  | STABLE        |        0.56  | hold         |               81.2 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Jackson Merrill |         0.006 |          0.297 | SLUMPING      | REGRESS       |        0.521 | hold         |              100   |      -0.0163 |         -0.068 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |

**UTIL/DH**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Yordan Alvarez |         0.704 |          0.447 | ABOVE_MEDIAN  | NOISE         |        0.735 | add          |               52.9 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |
| Yandy Diaz     |         0.768 |          0.372 | ABOVE_MEDIAN  | STABLE        |        0.637 | hold         |               64.2 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**SP / RP**

| player_name      | position   |   proj |   form_gap |
|:-----------------|:-----------|-------:|-----------:|
| Cade Smith       | RP         |  226.2 |        nan |
| Aroldis Chapman  | RP         |  193.4 |        nan |
| Devin Williams   | RP         |  161.9 |        nan |
| Paul Sewald      | RP         |  151.1 |        nan |
| Bryan Woo        | SP         |  nan   |        nan |
| Dylan Cease      | SP         |  nan   |        nan |
| Luis Castillo    | SP         |  nan   |        nan |
| Robbie Ray       | SP         |  nan   |        nan |
| Mitch Keller     | SP         |  nan   |        nan |
| Joe Musgrove     | SP         |  nan   |        nan |
| Justin Steele    | SP         |  nan   |        nan |
| Clay Holmes      | SP         |  nan   |        nan |
| Braxton Ashcraft | RP         |  nan   |        nan |
| Ryan Weathers    | SP         |  nan   |        nan |


### Team Solomon

**C**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict   | verdict_rationale                                                   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:----------------|:--------------------------------------------------------------------|
| Cal Raleigh   |         0.198 |          0.315 | SLUMPING      | REGRESS       |        0.458 | hold         |               95.4 |      -0.0132 |         -0.051 | True           | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |

**1B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Matt Olson    |         0.749 |          0.394 | ABOVE_MEDIAN  | STABLE        |        0.636 | hold         |               55.8 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |
| Bryce Harper  |         0.587 |          0.399 | TYPICAL       | STABLE        |        0.607 | hold         |               77.4 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**2B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Jose Altuve       |         0.071 |          0.282 | SLUMPING      | BAD_LUCK      |        0.526 | hold         |               97.1 |      -0.001  |          0.019 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Jazz Chisholm Jr. |         0.26  |          0.301 | BELOW_MEDIAN  | REGRESS       |        0.425 | drop         |              100   |       0.0057 |          0.196 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict   | verdict_rationale                                                   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:----------------|:--------------------------------------------------------------------|
| Manny Machado |         0.07  |          0.302 | SLUMPING      | REGRESS       |        0.512 | hold         |               92.4 |       0.0062 |          0.195 | True           | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |
| Austin Riley  |         0.151 |          0.318 | SLUMPING      | STABLE        |        0.458 | hold         |               93.2 |      -0.0008 |          0.089 | True           | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |

**SS**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict     | verdict_rationale                                                   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:------------------|:--------------------------------------------------------------------|
| Corey Seager  |         0.047 |          0.317 | SLUMPING      | REGRESS       |        0.508 | hold         |                100 |      -0.0153 |         -0.081 | True           | HOLD_NOISE        | L21d CI includes anchor — statistically baseline noise, not a slump |
| JJ Wetherholt |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   |        0.506 | hold         |                nan |              |        nan     | False          | INSUFFICIENT_DATA | no career sample                                                    |

**OF**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict       | verdict_rationale              |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:--------------------|:-------------------------------|
| James Wood    |         0.937 |          0.441 | PEAK          | STABLE        |        0.576 | add          |               82.1 |              |            nan | False          | CONSENSUS_HOLD_PEAK | at career peak, process intact |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Mike Trout    |         0.453 |          0.415 | TYPICAL       | MIXED         |        0.563 | add          |               73.2 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Seiya Suzuki  |         0.276 |          0.333 | BELOW_MEDIAN  | STABLE        |        0.534 | hold         |               71.1 |      -0.0194 |         -0.128 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Brent Rooker  |         0.224 |          0.319 | BELOW_MEDIAN  | REGRESS       |        0.452 | hold         |              100   |      -0.002  |          0.06  | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |

**SP / RP**

| player_name        | position   |   proj |   form_gap |
|:-------------------|:-----------|-------:|-----------:|
| Kenley Jansen      | RP         |  166.4 |        nan |
| Louis Varland      | RP         |  164.1 |        nan |
| Riley O'Brien      | RP         |  157.1 |        nan |
| Tarik Skubal       | SP         |  nan   |        nan |
| Cristopher Sanchez | SP         |  nan   |        nan |
| Chris Sale         | SP         |  nan   |        nan |
| George Kirby       | SP         |  nan   |        nan |
| Zack Wheeler       | SP         |  nan   |        nan |
| Nathan Eovaldi     | SP         |  nan   |        nan |
| Josh Hader         | RP         |  nan   |        nan |
| Shota Imanaga      | SP         |  nan   |        nan |
| Sonny Gray         | SP         |  nan   |        nan |
| Nick Pivetta       | SP         |  nan   |        nan |
| Davis Martin       | SP         |  nan   |        nan |
| Shane McClanahan   | SP         |  nan   |        nan |
| Logan Webb         | SP         |  nan   |        nan |


### Treasure Island Mashers

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Adley Rutschman |         0.573 |          0.349 | TYPICAL       | STABLE        |        0.582 | hold         |               55.2 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Agustin Ramirez |         0.009 |          0.275 | SLUMPING      | STABLE        |        0.429 | drop         |               84.6 |       0.0022 |         -0.056 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Alejandro Kirk  |         0.807 |          0.375 | HIGH          | STABLE        |      nan     | nan          |              nan   |              |        nan     | False          | STABLE_HIGH            | high career form, holding                                           |

**1B**

| player_name       |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Nick Kurtz        |         0.757 |          0.418 | ABOVE_MEDIAN  | BAD_LUCK      |        0.631 | hold         |                100 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Spencer Torkelson |         0.225 |          0.306 | BELOW_MEDIAN  | BAD_LUCK      |        0.454 | drop         |                 72 |      -0.0232 |         -0.137 | False          | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Brice Turang   |         0.971 |          0.407 | PEAK          | STABLE        |        0.589 | hold         |               57.4 |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                |
| Luke Keaschall |         0.323 |          0.282 | BELOW_MEDIAN  | REGRESS       |        0.517 | hold         |              nan   |       0.0049 |          0.023 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict   | verdict_rationale         |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:----------------|:--------------------------|
| Nolan Arenado |         0.848 |           0.37 | HIGH          | STABLE        |        0.511 | hold         |               92.8 |              |            nan | False          | STABLE_HIGH     | high career form, holding |

**SS**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:-----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Jacob Wilson     |         0.385 |          0.284 | BELOW_MEDIAN  | REGRESS       |        0.556 | hold         |              100   |      -0.0004 |          0.038 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Francisco Lindor |         0.815 |          0.388 | HIGH          | REGRESS       |        0.535 | hold         |               99.5 |              |        nan     | False          | STABLE_HIGH            | high career form, holding                     |
| Xander Bogaerts  |         0.555 |          0.332 | TYPICAL       | STABLE        |        0.502 | hold         |               77.8 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |

**OF**

| player_name        |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:-------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Juan Soto          |         0.498 |          0.418 | TYPICAL       | REGRESS       |        0.706 | add          |               85.8 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Wilyer Abreu       |         0.787 |          0.354 | ABOVE_MEDIAN  | STABLE        |        0.549 | hold         |               50.5 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Randy Arozarena    |         0.349 |          0.309 | BELOW_MEDIAN  | STABLE        |        0.489 | hold         |               74.2 |       0.013  |          0.129 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |
| Oneil Cruz         |         0.221 |          0.3   | BELOW_MEDIAN  | STABLE        |        0.472 | hold         |               79.6 |      -0.015  |          0.005 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal                       |
| Fernando Tatis Jr. |         0.183 |          0.346 | SLUMPING      | REGRESS       |        0.47  | hold         |              100   |      -0.0002 |         -0.008 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Roman Anthony      |         0.103 |          0.355 | SLUMPING      | BAD_LUCK      |        0.46  | hold         |              nan   |       0.0082 |          0.136 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |
| Carson Benge       |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   |        0.455 | hold         |              nan   |              |        nan     | False          | INSUFFICIENT_DATA      | no career sample                                                    |

**UTIL/DH**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict   | verdict_rationale                                                   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:----------------|:--------------------------------------------------------------------|
| Rafael Devers |         0.018 |          0.273 | SLUMPING      | REGRESS       |        0.454 | drop         |                100 |        0.016 |          0.288 | True           | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |

**SP / RP**

| player_name        | position   |   proj |   form_gap |
|:-------------------|:-----------|-------:|-----------:|
| Yoshinobu Yamamoto | SP         |    nan |        nan |
| Edwin Diaz         | RP         |    nan |        nan |
| Nolan McLean       | SP         |    nan |        nan |
| Jacob Misiorowski  | SP         |    nan |        nan |
| Zac Gallen         | SP         |    nan |        nan |
| Ranger Suarez      | SP         |    nan |        nan |
| Sandy Alcantara    | SP         |    nan |        nan |
| Seth Lugo          | SP         |    nan |        nan |
| Kyle Harrison      | SP         |    nan |        nan |


### U Just Lost To Edwin Diaz

**C**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Shea Langeliers |         0.984 |          0.423 | PEAK          | STABLE        |        0.625 | add          |               63.1 |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                |
| Liam Hicks      |         0.337 |          0.314 | BELOW_MEDIAN  | IMPROVING     |        0.582 | hold         |               64.8 |      -0.0114 |         -0.093 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |

**1B**

| player_name        |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:-------------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Vinnie Pasquantino |         0.387 |          0.326 | BELOW_MEDIAN  | REGRESS       |        0.556 | hold         |              100   |      -0.0065 |          0.002 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Christian Walker   |         0.208 |          0.318 | BELOW_MEDIAN  | STABLE        |        0.535 | hold         |               56.7 |      -0.01   |         -0.012 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Jake Bauers        |         0.989 |          0.371 | PEAK          | STABLE        |        0.49  | drop         |               59.7 |              |        nan     | False          | CONSENSUS_HOLD_PEAK    | at career peak, process intact                |

**2B**

| player_name    |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict       | verdict_rationale              |
|:---------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:--------------------|:-------------------------------|
| Xavier Edwards |         0.943 |          0.365 | PEAK          | STABLE        |        0.584 | hold         |               49.3 |              |            nan | False          | CONSENSUS_HOLD_PEAK | at career peak, process intact |

**3B**

| player_name   |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                                                   |
|:--------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:--------------------------------------------------------------------|
| Ernie Clement |         0.496 |          0.29  | TYPICAL       | STABLE        |        0.548 | hold         |               71.4 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                                                  |
| Maikel Garcia |         0.078 |          0.294 | SLUMPING      | REGRESS       |        0.52  | hold         |               59.1 |      -0.0135 |         -0.076 | True           | HOLD_NOISE             | L21d CI includes anchor — statistically baseline noise, not a slump |

**SS**

| player_name     |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct | shrunk_gap   |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale   |
|:----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|:-------------|---------------:|:---------------|:-----------------------|:--------------------|
| Geraldo Perdomo |         0.774 |          0.342 | ABOVE_MEDIAN  | REGRESS       |        0.586 | hold         |               62.9 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |
| Otto Lopez      |         0.418 |          0.321 | TYPICAL       | STABLE        |        0.529 | hold         |               81.1 |              |            nan | False          | CONSENSUS_HOLD_TYPICAL | baseline performer  |

**OF**

| player_name      |   career_%ile |   current_l150 | form_bucket   | sust_bucket   |   rh3_per_pa | rh3_signal   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap | anchor_in_ci   | cross_verdict          | verdict_rationale                             |
|:-----------------|--------------:|---------------:|:--------------|:--------------|-------------:|:-------------|-------------------:|-------------:|---------------:|:---------------|:-----------------------|:----------------------------------------------|
| Byron Buxton     |         0.748 |          0.355 | ABOVE_MEDIAN  | STABLE        |        0.601 | add          |               74.4 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Chase DeLauter   |       nan     |        nan     | INSUFFICIENT  | NO_BASELINE   |        0.588 | add          |              nan   |              |        nan     | False          | INSUFFICIENT_DATA      | no career sample                              |
| Ronald Acuna Jr. |         0.31  |          0.376 | BELOW_MEDIAN  | REGRESS       |        0.566 | add          |               95.6 |      -0.0032 |         -0.047 | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Mickey Moniak    |         0.511 |          0.314 | TYPICAL       | STABLE        |        0.556 | hold         |               69.1 |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |
| Brandon Marsh    |         0.373 |          0.312 | BELOW_MEDIAN  | STABLE        |        0.509 | hold         |               61.9 |      -0.0174 |          0.04  | True           | CONSENSUS_HOLD_TYPICAL | below median but no structural decline signal |
| Jakob Marsee     |         0.586 |          0.301 | TYPICAL       | REGRESS       |        0.498 | hold         |              nan   |              |        nan     | False          | CONSENSUS_HOLD_TYPICAL | baseline performer                            |

**SP / RP**

| player_name     | position   |    proj |   form_gap |
|:----------------|:-----------|--------:|-----------:|
| Mason Miller    | RP         | 231.1   |     nan    |
| Gregory Soto    | RP         | 145.9   |     nan    |
| Rico Garcia     | RP         | 143.5   |     nan    |
| Dylan Lee       | RP         | 140.7   |     nan    |
| Trey Yesavage   | SP         |  11.026 |      -0.12 |
| Garrett Crochet | SP         | nan     |     nan    |
| Kevin Gausman   | SP         | nan     |     nan    |
| MacKenzie Gore  | SP         | nan     |     nan    |
| Gavin Williams  | SP         | nan     |     nan    |
| Edward Cabrera  | SP         | nan     |     nan    |
| Bryce Miller    | SP         | nan     |     nan    |
| Shane Bieber    | SP         | nan     |     nan    |
| Taj Bradley     | SP         | nan     |     nan    |


## Slump detail cards (SLUMPING players, full diagnostics)


### Freddie Freeman (Boone's Bad Bullpen, 1B)

- **Career %ile:** 14.1%  |  **Form:** SLUMPING  |  **Sust:** STABLE

- **rh3:** 0.612/PA  |  **slump_bounce_pct:** 86% (430 comparables)  |  **slump_delta (bounce uplift):** +0.125/PA

- **L21d xwOBA:** 0.330  |  **anchor (pre-L21d):** 0.369  |  **shrunk gap:** -0.005  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.514  |  gap vs anchor: +0.145 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Vladimir Guerrero Jr. (New York Ligers, 1B)

- **Career %ile:** 13.2%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.585/PA  |  **slump_bounce_pct:** 83% (499 comparables)  |  **slump_delta (bounce uplift):** +0.069/PA

- **L21d xwOBA:** 0.385  |  **anchor (pre-L21d):** 0.343  |  **shrunk gap:** +0.005  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.303  |  gap vs anchor: -0.040 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Gunnar Henderson (Boone's Bad Bullpen, SS)

- **Career %ile:** 2.1%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.538/PA  |  **slump_bounce_pct:** 100% (45 comparables)  |  **slump_delta (bounce uplift):** +0.130/PA

- **L21d xwOBA:** 0.393  |  **anchor (pre-L21d):** 0.271  |  **shrunk gap:** +0.015  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.516  |  gap vs anchor: +0.245 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Jose Altuve (Team Solomon, 2B)

- **Career %ile:** 7.1%  |  **Form:** SLUMPING  |  **Sust:** BAD_LUCK

- **rh3:** 0.526/PA  |  **slump_bounce_pct:** 97% (205 comparables)  |  **slump_delta (bounce uplift):** +0.113/PA

- **L21d xwOBA:** 0.302  |  **anchor (pre-L21d):** 0.309  |  **shrunk gap:** -0.001  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.328  |  gap vs anchor: +0.019 → contact quality intact (BABIP variance)

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Jackson Merrill (Late Night Bettsing, CF)

- **Career %ile:** 0.6%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.521/PA  |  **slump_bounce_pct:** 100% (13 comparables)  |  **slump_delta (bounce uplift):** +0.198/PA

- **L21d xwOBA:** 0.194  |  **anchor (pre-L21d):** 0.327  |  **shrunk gap:** -0.016  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.259  |  gap vs anchor: -0.068 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Maikel Garcia (U Just Lost To Edwin Diaz, 3B)

- **Career %ile:** 7.8%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.520/PA  |  **slump_bounce_pct:** 59% (281 comparables)  |  **slump_delta (bounce uplift):** +0.029/PA

- **L21d xwOBA:** 0.205  |  **anchor (pre-L21d):** 0.315  |  **shrunk gap:** -0.013  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.239  |  gap vs anchor: -0.076 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Manny Machado (Team Solomon, 3B)

- **Career %ile:** 7.0%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.512/PA  |  **slump_bounce_pct:** 92% (329 comparables)  |  **slump_delta (bounce uplift):** +0.157/PA

- **L21d xwOBA:** 0.349  |  **anchor (pre-L21d):** 0.299  |  **shrunk gap:** +0.006  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.494  |  gap vs anchor: +0.195 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Sal Frelick (2015 Draft First Round, RF)

- **Career %ile:** 9.3%  |  **Form:** SLUMPING  |  **Sust:** BAD_LUCK

- **rh3:** 0.511/PA  |  **slump_bounce_pct:** 82% (173 comparables)  |  **slump_delta (bounce uplift):** +0.046/PA

- **L21d xwOBA:** 0.225  |  **anchor (pre-L21d):** 0.278  |  **shrunk gap:** -0.007  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.236  |  gap vs anchor: -0.042 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Trea Turner (New York Ligers, SS)

- **Career %ile:** 16.5%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.511/PA  |  **slump_bounce_pct:** 81% (167 comparables)  |  **slump_delta (bounce uplift):** +0.100/PA

- **L21d xwOBA:** 0.343  |  **anchor (pre-L21d):** 0.285  |  **shrunk gap:** +0.007  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.386  |  gap vs anchor: +0.101 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Corey Seager (Team Solomon, SS)

- **Career %ile:** 4.7%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.508/PA  |  **slump_bounce_pct:** 100% (63 comparables)  |  **slump_delta (bounce uplift):** +0.171/PA

- **L21d xwOBA:** 0.218  |  **anchor (pre-L21d):** 0.342  |  **shrunk gap:** -0.015  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.261  |  gap vs anchor: -0.081 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### George Springer (Frendy's Fantastic Team, DH)

- **Career %ile:** 1.7%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.492/PA  |  **slump_bounce_pct:** 96% (281 comparables)  |  **slump_delta (bounce uplift):** +0.179/PA

- **L21d xwOBA:** 0.306  |  **anchor (pre-L21d):** 0.274  |  **shrunk gap:** +0.004  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.387  |  gap vs anchor: +0.113 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Fernando Tatis Jr. (Treasure Island Mashers, RF)

- **Career %ile:** 18.3%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.470/PA  |  **slump_bounce_pct:** 100% (11 comparables)  |  **slump_delta (bounce uplift):** +0.185/PA

- **L21d xwOBA:** 0.339  |  **anchor (pre-L21d):** 0.341  |  **shrunk gap:** -0.000  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.333  |  gap vs anchor: -0.008 → contact quality intact (BABIP variance)

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Salvador Perez (New York Ligers, C)

- **Career %ile:** 14.5%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.469/PA  |  **slump_bounce_pct:** 97% (201 comparables)  |  **slump_delta (bounce uplift):** +0.155/PA

- **L21d xwOBA:** 0.459  |  **anchor (pre-L21d):** 0.261  |  **shrunk gap:** +0.024  |  **anchor in CI:** No

- **L21d xwOBACON:** 0.424  |  gap vs anchor: +0.163 → contact quality declining

- **Verdict:** CONSENSUS_HOLD_BOUNCE — 97% bounce rate historically; shrunk gap +0.024


### Christian Yelich (Frendy's Fantastic Team, DH)

- **Career %ile:** 6.5%  |  **Form:** SLUMPING  |  **Sust:** STABLE

- **rh3:** 0.462/PA  |  **slump_bounce_pct:** 92% (487 comparables)  |  **slump_delta (bounce uplift):** +0.133/PA

- **L21d xwOBA:** 0.258  |  **anchor (pre-L21d):** 0.293  |  **shrunk gap:** -0.004  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.308  |  gap vs anchor: +0.015 → contact quality intact (BABIP variance)

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Roman Anthony (Treasure Island Mashers, RF)

- **Career %ile:** 10.3%  |  **Form:** SLUMPING  |  **Sust:** BAD_LUCK

- **rh3:** 0.460/PA  |  slump signals: N/A

- **L21d xwOBA:** 0.409  |  **anchor (pre-L21d):** 0.343  |  **shrunk gap:** +0.008  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.479  |  gap vs anchor: +0.136 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Cal Raleigh (Team Solomon, C)

- **Career %ile:** 19.8%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.458/PA  |  **slump_bounce_pct:** 95% (108 comparables)  |  **slump_delta (bounce uplift):** +0.189/PA

- **L21d xwOBA:** 0.204  |  **anchor (pre-L21d):** 0.311  |  **shrunk gap:** -0.013  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.260  |  gap vs anchor: -0.051 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Austin Riley (Team Solomon, 3B)

- **Career %ile:** 15.1%  |  **Form:** SLUMPING  |  **Sust:** STABLE

- **rh3:** 0.458/PA  |  **slump_bounce_pct:** 93% (73 comparables)  |  **slump_delta (bounce uplift):** +0.198/PA

- **L21d xwOBA:** 0.320  |  **anchor (pre-L21d):** 0.326  |  **shrunk gap:** -0.001  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.415  |  gap vs anchor: +0.089 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Rafael Devers (Treasure Island Mashers, DH)

- **Career %ile:** 1.8%  |  **Form:** SLUMPING  |  **Sust:** REGRESS

- **rh3:** 0.454/PA  |  **slump_bounce_pct:** 100% (7 comparables)  |  **slump_delta (bounce uplift):** +0.468/PA

- **L21d xwOBA:** 0.394  |  **anchor (pre-L21d):** 0.264  |  **shrunk gap:** +0.016  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.552  |  gap vs anchor: +0.288 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


### Agustin Ramirez (Treasure Island Mashers, C)

- **Career %ile:** 0.9%  |  **Form:** SLUMPING  |  **Sust:** STABLE

- **rh3:** 0.429/PA  |  **slump_bounce_pct:** 85% (13 comparables)  |  **slump_delta (bounce uplift):** +0.036/PA

- **L21d xwOBA:** 0.298  |  **anchor (pre-L21d):** 0.280  |  **shrunk gap:** +0.002  |  **anchor in CI:** YES — noise, not decline

- **L21d xwOBACON:** 0.224  |  gap vs anchor: -0.056 → contact quality declining

- **Verdict:** HOLD_NOISE — L21d CI includes anchor — statistically baseline noise, not a slump


## Trade targets — buy low on rivals

| team_name               | player_name      | position   |   career_%ile | form_bucket   | sust_bucket   |   slump_bounce_pct |   shrunk_gap |   xwobacon_gap |   rh3_per_pa |   replacement_delta | cross_verdict   | verdict_rationale                                                   |
|:------------------------|:-----------------|:-----------|--------------:|:--------------|:--------------|-------------------:|-------------:|---------------:|-------------:|--------------------:|:----------------|:--------------------------------------------------------------------|
| Boone's Bad Bullpen     | Freddie Freeman  | 1B         |         0.141 | SLUMPING      | STABLE        |               86   |      -0.0048 |          0.145 |        0.612 |               0.042 | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |
| Boone's Bad Bullpen     | Gunnar Henderson | SS         |         0.021 | SLUMPING      | REGRESS       |              100   |       0.0151 |          0.245 |        0.538 |               0.018 | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |
| Team Solomon            | Jose Altuve      | 2B         |         0.071 | SLUMPING      | BAD_LUCK      |               97.1 |      -0.001  |          0.019 |        0.526 |               0.009 | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |
| Late Night Bettsing     | Jackson Merrill  | CF         |         0.006 | SLUMPING      | REGRESS       |              100   |      -0.0163 |         -0.068 |        0.521 |               0.032 | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |
| 2015 Draft First Round  | Sal Frelick      | RF         |         0.093 | SLUMPING      | BAD_LUCK      |               81.5 |      -0.0066 |         -0.042 |        0.511 |               0.022 | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |
| Frendy's Fantastic Team | George Springer  | DH         |         0.017 | SLUMPING      | REGRESS       |               95.7 |       0.004  |          0.113 |        0.492 |               0.066 | HOLD_NOISE      | L21d CI includes anchor — statistically baseline noise, not a slump |

## Sell-high candidates on YOUR roster

_None._

## Rival peakers cooling

| team_name               | player_name   | position   |   career_%ile | form_bucket   | shrunk_gap   |   rh3_per_pa | cross_verdict     | verdict_rationale              |
|:------------------------|:--------------|:-----------|--------------:|:--------------|:-------------|-------------:|:------------------|:-------------------------------|
| Frendy's Fantastic Team | Josh Naylor   | 1B         |         0.924 | PEAK          |              |        0.571 | SELL_HIGH_WARNING | PEAK form cooling (shrunk N/A) |