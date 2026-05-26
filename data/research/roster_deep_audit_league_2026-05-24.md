# League-wide roster deep audit — 2026-05-24

Universe: 8 BrownU teams (125 hitters resolved, 104 pitchers).

## Power ranking (aggregate roster strength)

| team_name                 |   rank |   n_hitters |   mean_percentile |   median_percentile |   n_peak_or_high |   n_slumping |   mean_rh3 |   sum_replacement_delta |   sp_rp_proj_total |
|:--------------------------|-------:|------------:|------------------:|--------------------:|-----------------:|-------------:|-----------:|------------------------:|-------------------:|
| Late Night Bettsing       |      1 |          15 |             0.592 |               0.622 |                4 |            1 |      0.574 |                   0.624 |              732.6 |
| New York Ligers           |      2 |          13 |             0.516 |               0.537 |                2 |            3 |      0.565 |                   0.631 |              862.7 |
| U Just Lost To Edwin Diaz |      3 |          16 |             0.495 |               0.403 |                3 |            2 |      0.555 |                   0.579 |              672.2 |
| 2015 Draft First Round    |      4 |          14 |             0.633 |               0.678 |                4 |            1 |      0.551 |                   0.568 |              515   |
| Frendy's Fantastic Team   |      5 |          18 |             0.55  |               0.536 |                6 |            3 |      0.545 |                   0.472 |              137.8 |
| Team Solomon              |      6 |          13 |             0.356 |               0.252 |                2 |            5 |      0.52  |                   0.025 |              487.6 |
| Treasure Island Mashers   |      7 |          19 |             0.469 |               0.46  |                4 |            5 |      0.52  |                   0.058 |              nan   |
| Boone's Bad Bullpen       |      8 |          17 |             0.511 |               0.537 |                3 |            3 |      0.511 |                  -0.004 |              505.8 |


## Per-team agreement matrix


### 2015 Draft First Round

| player_name     | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |   rh3 | signal   | cross_verdict          |
|:----------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|------:|:---------|:-----------------------|
| Brandon Lowe    | 2B         |       3184 |        0.398 |         0.956 | PEAK          |      0.008 | 0.555 | hold     | CONSENSUS_HOLD_PEAK    |
| Brandon Nimmo   | LF         |       4539 |        0.385 |         0.929 | PEAK          |     -0.001 | 0.578 | add      | CONSENSUS_HOLD_PEAK    |
| Riley Greene    | LF         |       2278 |        0.39  |         0.884 | HIGH          |     -0.012 | 0.479 | hold     | STABLE_HIGH            |
| Josh Jung       | 3B         |       1506 |        0.37  |         0.879 | HIGH          |     -0.007 | 0.527 | hold     | STABLE_HIGH            |
| Bobby Witt Jr.  | SS         |       2917 |        0.391 |         0.735 | ABOVE_MEDIAN  |     -0.008 | 0.667 | add      | STABLE_PRODUCER        |
| Ketel Marte     | 2B         |       5239 |        0.374 |         0.731 | ABOVE_MEDIAN  |     -0.005 | 0.62  | add      | STABLE_PRODUCER        |
| Ildemaro Vargas | 2B         |       1474 |        0.301 |         0.714 | ABOVE_MEDIAN  |     -0.031 | 0.544 | hold     | STABLE_PRODUCER        |
| Kyle Schwarber  | DH         |       5538 |        0.383 |         0.642 | ABOVE_MEDIAN  |     -0.005 | 0.613 | add      | STABLE_PRODUCER        |
| Ian Happ        | LF         |       4612 |        0.344 |         0.559 | TYPICAL       |      0.006 | 0.499 | hold     | CONSENSUS_HOLD_TYPICAL |
| Will Smith      | C          |       3066 |        0.359 |         0.523 | TYPICAL       |     -0.001 | 0.541 | hold     | CONSENSUS_HOLD_TYPICAL |
| Dansby Swanson  | SS         |       5388 |        0.328 |         0.496 | TYPICAL       |     -0.021 | 0.458 | hold     | CONSENSUS_HOLD_TYPICAL |
| Alex Bregman    | 3B         |       5512 |        0.345 |         0.473 | TYPICAL       |     -0.008 | 0.564 | hold     | CONSENSUS_HOLD_TYPICAL |
| Daylen Lile     | RF         |        574 |        0.332 |         0.249 | BELOW_MEDIAN  |     -0.01  | 0.559 | hold     | CONSENSUS_HOLD_TYPICAL |
| Sal Frelick     | RF         |       1499 |        0.268 |         0.091 | SLUMPING      |     -0.012 | 0.511 | hold     | SLUMP_AMBIGUOUS        |


### Boone's Bad Bullpen

| player_name         | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |   rh3 | signal   | cross_verdict          |
|:--------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|------:|:---------|:-----------------------|
| Ryan Jeffers        | C          |       1992 |        0.39  |         0.997 | PEAK          |     -0.006 | 0.595 | hold     | CONSENSUS_HOLD_PEAK    |
| Angel Martinez      | CF         |        822 |        0.315 |         0.957 | PEAK          |     -0.005 | 0.51  | hold     | CONSENSUS_HOLD_PEAK    |
| Junior Caminero     | 3B         |       1074 |        0.393 |         0.894 | HIGH          |      0.006 | 0.661 | add      | STABLE_HIGH            |
| William Contreras   | C          |       2702 |        0.357 |         0.787 | ABOVE_MEDIAN  |     -0.002 | 0.601 | add      | STABLE_PRODUCER        |
| Pete Crow-Armstrong | CF         |       1252 |        0.337 |         0.762 | ABOVE_MEDIAN  |      0.013 | 0.475 | hold     | STABLE_PRODUCER        |
| Jac Caglianone      | RF         |        396 |        0.332 |         0.761 | ABOVE_MEDIAN  |     -0     | 0.37  | drop     | STABLE_PRODUCER        |
| Ryan O'Hearn        | 1B         |       2641 |        0.348 |         0.657 | ABOVE_MEDIAN  |     -0.029 | 0.533 | hold     | STABLE_PRODUCER        |
| Mauricio Dubon      | LF         |       2235 |        0.293 |         0.589 | TYPICAL       |     -0.007 | 0.476 | hold     | CONSENSUS_HOLD_TYPICAL |
| Dillon Dingler      | C          |        736 |        0.368 |         0.537 | TYPICAL       |     -0.021 | 0.513 | hold     | CONSENSUS_HOLD_TYPICAL |
| Zach Neto           | SS         |       1706 |        0.327 |         0.443 | TYPICAL       |      0.009 | 0.492 | hold     | CONSENSUS_HOLD_TYPICAL |
| Konnor Griffin      | SS         |        181 |        0.321 |         0.406 | TYPICAL       |      0.007 | 0.413 | drop     | CONSENSUS_HOLD_TYPICAL |
| Bryan Reynolds      | RF         |       4184 |        0.338 |         0.321 | BELOW_MEDIAN  |     -0.008 | 0.471 | hold     | CONSENSUS_HOLD_TYPICAL |
| Tyler Soderstrom    | LF         |       1170 |        0.32  |         0.236 | BELOW_MEDIAN  |     -0.006 | 0.508 | hold     | CONSENSUS_HOLD_TYPICAL |
| Steven Kwan         | LF         |       2783 |        0.295 |         0.203 | BELOW_MEDIAN  |      0.003 | 0.465 | hold     | CONSENSUS_HOLD_TYPICAL |
| Freddie Freeman     | 1B         |       6791 |        0.354 |         0.114 | SLUMPING      |     -0.014 | 0.612 | hold     | SLUMP_AMBIGUOUS        |
| Gunnar Henderson    | SS         |       2339 |        0.283 |         0.022 | SLUMPING      |     -0.003 | 0.538 | hold     | SLUMP_AMBIGUOUS        |
| Kazuma Okamoto      | 3B         |        206 |        0.343 |         0     | SLUMPING      |     -0.01  | 0.455 | hold     | SLUMP_AMBIGUOUS        |


### Frendy's Fantastic Team

| player_name       | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |   rh3 | signal   | cross_verdict          |
|:------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|------:|:---------|:-----------------------|
| Drake Baldwin     | C          |        661 |        0.417 |         0.998 | PEAK          |      0.009 | 0.679 | add      | CONSENSUS_HOLD_PEAK    |
| Miguel Vargas     | 3B         |       1364 |        0.43  |         0.99  | PEAK          |      0.009 | 0.58  | hold     | CONSENSUS_HOLD_PEAK    |
| Cody Bellinger    | LF         |       4897 |        0.416 |         0.932 | PEAK          |      0.006 | 0.645 | add      | CONSENSUS_HOLD_PEAK    |
| Josh Naylor       | 1B         |       3031 |        0.362 |         0.888 | HIGH          |      0.01  | 0.571 | hold     | STABLE_HIGH            |
| Nico Hoerner      | 2B         |       3074 |        0.336 |         0.816 | HIGH          |     -0.011 | 0.577 | hold     | STABLE_HIGH            |
| Julio Rodriguez   | CF         |       2799 |        0.369 |         0.811 | HIGH          |     -0.004 | 0.587 | add      | STABLE_HIGH            |
| Jo Adell          | CF         |       1840 |        0.338 |         0.719 | ABOVE_MEDIAN  |      0.012 | 0.452 | hold     | STABLE_PRODUCER        |
| Taylor Ward       | LF         |       3053 |        0.36  |         0.681 | ABOVE_MEDIAN  |     -0.023 | 0.491 | hold     | STABLE_PRODUCER        |
| Munetaka Murakami | 3B         |        211 |        0.402 |         0.597 | TYPICAL       |     -0.02  | 0.509 | hold     | CONSENSUS_HOLD_TYPICAL |
| Cam Smith         | RF         |        680 |        0.328 |         0.475 | TYPICAL       |     -0.004 | 0.397 | drop     | CONSENSUS_HOLD_TYPICAL |
| Jackson Chourio   | CF         |       1225 |        0.306 |         0.44  | TYPICAL       |     -0.004 | 0.533 | hold     | CONSENSUS_HOLD_TYPICAL |
| Sal Stewart       | 1B         |        267 |        0.364 |         0.432 | TYPICAL       |     -0.012 | 0.586 | hold     | CONSENSUS_HOLD_TYPICAL |
| Shohei Ohtani     | DH         |       4412 |        0.387 |         0.414 | TYPICAL       |     -0.014 | 0.658 | hold     | CONSENSUS_HOLD_TYPICAL |
| Ozzie Albies      | 2B         |       4658 |        0.306 |         0.345 | BELOW_MEDIAN  |     -0.01  | 0.52  | hold     | CONSENSUS_HOLD_TYPICAL |
| Ivan Herrera      | DH         |        987 |        0.352 |         0.313 | BELOW_MEDIAN  |     -0.024 | 0.551 | hold     | FADING                 |
| Christian Yelich  | DH         |       6077 |        0.296 |         0.023 | SLUMPING      |     -0.003 | 0.462 | hold     | SLUMP_AMBIGUOUS        |
| George Springer   | DH         |       6096 |        0.301 |         0.017 | SLUMPING      |     -0.004 | 0.492 | hold     | SLUMP_AMBIGUOUS        |
| Kevin McGonigle   | SS         |        219 |        0.363 |         0     | SLUMPING      |     -0.026 | 0.53  | hold     | CONSENSUS_DROP         |


### Late Night Bettsing

| player_name       | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |     rh3 | signal   | cross_verdict          |
|:------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|--------:|:---------|:-----------------------|
| Brayan Rocchio    | SS         |       1089 |        0.318 |         0.956 | PEAK          |      0.005 |   0.457 | hold     | CONSENSUS_HOLD_PEAK    |
| Alec Burleson     | LF         |       1731 |        0.376 |         0.831 | HIGH          |     -0.01  |   0.579 | hold     | STABLE_HIGH            |
| Willson Contreras | 1B         |       4428 |        0.389 |         0.825 | HIGH          |     -0.013 |   0.514 | hold     | STABLE_HIGH            |
| Jose Ramirez      | 3B         |       6550 |        0.381 |         0.818 | HIGH          |     -0.015 |   0.669 | add      | STABLE_HIGH            |
| CJ Abrams         | SS         |       2352 |        0.347 |         0.799 | ABOVE_MEDIAN  |     -0.017 |   0.557 | hold     | STABLE_PRODUCER        |
| Yandy Diaz        | DH         |       3924 |        0.372 |         0.771 | ABOVE_MEDIAN  |     -0.011 |   0.637 | hold     | STABLE_PRODUCER        |
| Yordan Alvarez    | DH         |       3039 |        0.447 |         0.708 | ABOVE_MEDIAN  |     -0.042 |   0.735 | add      | STABLE_PRODUCER        |
| Andy Pages        | CF         |       1260 |        0.331 |         0.622 | ABOVE_MEDIAN  |     -0.006 |   0.56  | hold     | STABLE_PRODUCER        |
| Mookie Betts      | SS         |       6707 |        0.365 |         0.537 | TYPICAL       |      0.006 |   0.629 | add      | CONSENSUS_HOLD_TYPICAL |
| Ben Rice          | 1B         |        894 |        0.388 |         0.525 | TYPICAL       |     -0.035 |   0.62  | hold     | CONSENSUS_HOLD_TYPICAL |
| Jackson Holliday  | 2B         |        862 |        0.311 |         0.477 | TYPICAL       |    nan     | nan     | nan      | CONSENSUS_HOLD_TYPICAL |
| Gleyber Torres    | 2B         |       4422 |        0.334 |         0.459 | TYPICAL       |     -0.006 |   0.462 | hold     | CONSENSUS_HOLD_TYPICAL |
| Kyle Tucker       | RF         |       3308 |        0.35  |         0.289 | BELOW_MEDIAN  |      0.007 |   0.568 | add      | CONSENSUS_HOLD_TYPICAL |
| Jonathan Aranda   | 1B         |        956 |        0.346 |         0.25  | BELOW_MEDIAN  |      0.007 |   0.524 | hold     | CONSENSUS_HOLD_TYPICAL |
| Jackson Merrill   | CF         |       1252 |        0.297 |         0.009 | SLUMPING      |      0.002 |   0.521 | hold     | SLUMP_AMBIGUOUS        |


### New York Ligers ← YOU

| player_name           | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |   rh3 | signal   | cross_verdict          |
|:----------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|------:|:---------|:-----------------------|
| Max Muncy             | 3B         |       4102 |        0.416 |         0.861 | HIGH          |     -0.018 | 0.578 | hold     | STABLE_HIGH            |
| Elly De La Cruz       | SS         |       2017 |        0.375 |         0.859 | HIGH          |     -0.01  | 0.54  | hold     | STABLE_HIGH            |
| Michael Harris II     | CF         |       2249 |        0.376 |         0.777 | ABOVE_MEDIAN  |     -0.036 | 0.624 | add      | STABLE_PRODUCER        |
| Jordan Walker         | RF         |       1242 |        0.341 |         0.73  | ABOVE_MEDIAN  |     -0.016 | 0.523 | hold     | STABLE_PRODUCER        |
| Corbin Carroll        | RF         |       2262 |        0.367 |         0.707 | ABOVE_MEDIAN  |      0.014 | 0.636 | add      | STABLE_PRODUCER        |
| Pete Alonso           | 1B         |       4467 |        0.375 |         0.633 | ABOVE_MEDIAN  |      0.005 | 0.575 | hold     | STABLE_PRODUCER        |
| Bo Bichette           | SS         |       3497 |        0.342 |         0.537 | TYPICAL       |     -0.004 | 0.565 | hold     | CONSENSUS_HOLD_TYPICAL |
| Wyatt Langford        | LF         |       1205 |        0.332 |         0.476 | TYPICAL       |      0.007 | 0.489 | hold     | CONSENSUS_HOLD_TYPICAL |
| Aaron Judge           | RF         |       5097 |        0.418 |         0.394 | BELOW_MEDIAN  |     -0.027 | 0.7   | add      | FADING                 |
| Luis Arraez           | 1B         |       3689 |        0.32  |         0.308 | BELOW_MEDIAN  |      0.008 | 0.546 | hold     | CONSENSUS_HOLD_TYPICAL |
| Trea Turner           | SS         |       5773 |        0.306 |         0.164 | SLUMPING      |      0.001 | 0.511 | hold     | SLUMP_AMBIGUOUS        |
| Salvador Perez        | C          |       5438 |        0.286 |         0.137 | SLUMPING      |      0.003 | 0.469 | hold     | SLUMP_AMBIGUOUS        |
| Vladimir Guerrero Jr. | 1B         |       4380 |        0.34  |         0.131 | SLUMPING      |     -0.023 | 0.585 | hold     | CONSENSUS_DROP         |


### Team Solomon

| player_name       | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |   rh3 | signal   | cross_verdict          |
|:------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|------:|:---------|:-----------------------|
| James Wood        | LF         |       1250 |        0.431 |         0.886 | HIGH          |     -0.015 | 0.576 | add      | STABLE_HIGH            |
| JJ Wetherholt     | SS         |        218 |        0.371 |         0.812 | HIGH          |     -0.004 | 0.506 | hold     | STABLE_HIGH            |
| Matt Olson        | 1B         |       5348 |        0.385 |         0.644 | ABOVE_MEDIAN  |     -0.017 | 0.636 | hold     | STABLE_PRODUCER        |
| Bryce Harper      | 1B         |       6213 |        0.399 |         0.588 | TYPICAL       |      0.002 | 0.607 | hold     | CONSENSUS_HOLD_TYPICAL |
| Mike Trout        | DH         |       5088 |        0.415 |         0.451 | TYPICAL       |     -0.039 | 0.563 | add      | CONSENSUS_HOLD_TYPICAL |
| Seiya Suzuki      | DH         |       2398 |        0.333 |         0.28  | BELOW_MEDIAN  |     -0.023 | 0.534 | hold     | FADING                 |
| Jazz Chisholm Jr. | 2B         |       2531 |        0.301 |         0.252 | BELOW_MEDIAN  |     -0     | 0.425 | drop     | CONSENSUS_HOLD_TYPICAL |
| Brent Rooker      | DH         |       2246 |        0.319 |         0.223 | BELOW_MEDIAN  |      0.002 | 0.452 | hold     | CONSENSUS_HOLD_TYPICAL |
| Cal Raleigh       | C          |       2622 |        0.31  |         0.159 | SLUMPING      |     -0.021 | 0.458 | hold     | CONSENSUS_DROP         |
| Austin Riley      | 3B         |       3684 |        0.318 |         0.152 | SLUMPING      |      0.016 | 0.458 | hold     | CONSENSUS_HOLD_BOUNCE  |
| Manny Machado     | 3B         |       7025 |        0.302 |         0.072 | SLUMPING      |     -0.008 | 0.512 | hold     | SLUMP_AMBIGUOUS        |
| Jose Altuve       | 2B         |       6530 |        0.278 |         0.058 | SLUMPING      |     -0.008 | 0.526 | hold     | SLUMP_AMBIGUOUS        |
| Corey Seager      | SS         |       4993 |        0.317 |         0.046 | SLUMPING      |     -0.014 | 0.508 | hold     | SLUMP_AMBIGUOUS        |


### Treasure Island Mashers

| player_name        | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |     rh3 | signal   | cross_verdict          |
|:-------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|--------:|:---------|:-----------------------|
| Carson Benge       | CF         |        181 |        0.357 |         0.969 | PEAK          |      0.021 |   0.455 | hold     | CONSENSUS_HOLD_PEAK    |
| Brice Turang       | 2B         |       1913 |        0.394 |         0.951 | PEAK          |     -0.023 |   0.589 | hold     | SELL_HIGH_WARNING      |
| Alejandro Kirk     | C          |       2080 |        0.375 |         0.809 | HIGH          |    nan     | nan     | nan      | STABLE_HIGH            |
| Nolan Arenado      | 3B         |       6587 |        0.365 |         0.807 | HIGH          |      0.014 |   0.511 | hold     | STABLE_HIGH            |
| Francisco Lindor   | SS         |       6843 |        0.385 |         0.789 | ABOVE_MEDIAN  |     -0.006 |   0.535 | hold     | STABLE_PRODUCER        |
| Wilyer Abreu       | RF         |       1148 |        0.347 |         0.698 | ABOVE_MEDIAN  |     -0.009 |   0.549 | hold     | STABLE_PRODUCER        |
| Nick Kurtz         | 1B         |        708 |        0.412 |         0.687 | ABOVE_MEDIAN  |     -0.012 |   0.631 | hold     | STABLE_PRODUCER        |
| Adley Rutschman    | C          |       2290 |        0.349 |         0.575 | TYPICAL       |      0.011 |   0.582 | hold     | CONSENSUS_HOLD_TYPICAL |
| Xander Bogaerts    | SS         |       6550 |        0.329 |         0.53  | TYPICAL       |     -0.021 |   0.502 | hold     | CONSENSUS_HOLD_TYPICAL |
| Juan Soto          | RF         |       4859 |        0.414 |         0.46  | TYPICAL       |     -0.02  |   0.706 | add      | CONSENSUS_HOLD_TYPICAL |
| Jacob Wilson       | SS         |        785 |        0.282 |         0.357 | BELOW_MEDIAN  |      0.009 |   0.556 | hold     | CONSENSUS_HOLD_TYPICAL |
| Randy Arozarena    | LF         |       3558 |        0.304 |         0.285 | BELOW_MEDIAN  |      0.001 |   0.489 | hold     | CONSENSUS_HOLD_TYPICAL |
| Luke Keaschall     | 2B         |        406 |        0.28  |         0.284 | BELOW_MEDIAN  |      0.009 |   0.517 | hold     | CONSENSUS_HOLD_TYPICAL |
| Oneil Cruz         | CF         |       1759 |        0.297 |         0.205 | BELOW_MEDIAN  |     -0.018 |   0.472 | hold     | CONSENSUS_HOLD_TYPICAL |
| Fernando Tatis Jr. | RF         |       3113 |        0.346 |         0.178 | SLUMPING      |     -0.016 |   0.47  | hold     | SLUMP_AMBIGUOUS        |
| Spencer Torkelson  | 1B         |       2302 |        0.298 |         0.175 | SLUMPING      |     -0.036 |   0.454 | drop     | CONSENSUS_DROP         |
| Roman Anthony      | RF         |        430 |        0.355 |         0.125 | SLUMPING      |     -0     |   0.46  | hold     | SLUMP_AMBIGUOUS        |
| Rafael Devers      | DH         |       5066 |        0.272 |         0.015 | SLUMPING      |      0.014 |   0.454 | drop     | CONSENSUS_HOLD_BOUNCE  |
| Agustin Ramirez    | C          |        709 |        0.275 |         0.007 | SLUMPING      |      0.007 |   0.429 | drop     | SLUMP_AMBIGUOUS        |


### U Just Lost To Edwin Diaz

| player_name        | position   |   total_pa |   L150_xwoba |   career_%ile | form_bucket   |   form_gap |   rh3 | signal   | cross_verdict          |
|:-------------------|:-----------|-----------:|-------------:|--------------:|:--------------|-----------:|------:|:---------|:-----------------------|
| Jake Bauers        | 1B         |       2115 |        0.371 |         0.981 | PEAK          |      0.006 | 0.49  | drop     | CONSENSUS_HOLD_PEAK    |
| Shea Langeliers    | C          |       1903 |        0.417 |         0.978 | PEAK          |     -0.007 | 0.625 | add      | CONSENSUS_HOLD_PEAK    |
| Xavier Edwards     | 2B         |       1211 |        0.362 |         0.933 | PEAK          |     -0.008 | 0.584 | hold     | CONSENSUS_HOLD_PEAK    |
| Geraldo Perdomo    | SS         |       2282 |        0.338 |         0.754 | ABOVE_MEDIAN  |      0.002 | 0.586 | hold     | STABLE_PRODUCER        |
| Byron Buxton       | CF         |       3558 |        0.355 |         0.745 | ABOVE_MEDIAN  |      0.008 | 0.601 | add      | STABLE_PRODUCER        |
| Jakob Marsee       | CF         |        446 |        0.301 |         0.579 | TYPICAL       |      0.014 | 0.498 | hold     | CONSENSUS_HOLD_TYPICAL |
| Mickey Moniak      | RF         |       1522 |        0.314 |         0.514 | TYPICAL       |     -0.008 | 0.556 | hold     | CONSENSUS_HOLD_TYPICAL |
| Otto Lopez         | SS         |       1244 |        0.321 |         0.416 | TYPICAL       |     -0.016 | 0.529 | hold     | CONSENSUS_HOLD_TYPICAL |
| Vinnie Pasquantino | 1B         |       1984 |        0.326 |         0.39  | BELOW_MEDIAN  |      0.002 | 0.556 | hold     | CONSENSUS_HOLD_TYPICAL |
| Ernie Clement      | 3B         |       1586 |        0.285 |         0.365 | BELOW_MEDIAN  |      0.004 | 0.548 | hold     | CONSENSUS_HOLD_TYPICAL |
| Brandon Marsh      | CF         |       2255 |        0.31  |         0.356 | BELOW_MEDIAN  |     -0.003 | 0.509 | hold     | CONSENSUS_HOLD_TYPICAL |
| Liam Hicks         | C          |        565 |        0.314 |         0.327 | BELOW_MEDIAN  |     -0.022 | 0.582 | hold     | FADING                 |
| Ronald Acuna Jr.   | RF         |       3803 |        0.376 |         0.312 | BELOW_MEDIAN  |     -0.021 | 0.566 | add      | FADING                 |
| Christian Walker   | 1B         |       4079 |        0.318 |         0.204 | BELOW_MEDIAN  |     -0.023 | 0.535 | hold     | FADING                 |
| Maikel Garcia      | 3B         |       2035 |        0.292 |         0.068 | SLUMPING      |     -0.009 | 0.52  | hold     | SLUMP_AMBIGUOUS        |
| Chase DeLauter     | RF         |        197 |        0.339 |         0     | SLUMPING      |     -0.016 | 0.588 | add      | SLUMP_AMBIGUOUS        |


## Trade-target list — rival players to buy

Filter: not on YOUR roster + cross_verdict in {CONSENSUS_HOLD_BOUNCE, BOUNCING_BACK, SLUMP_AMBIGUOUS} + rh3 above replacement.

| team_name                 | player_name      | position   |   career_mean |   current_l150 |   percentile | form_bucket   |   recency_form_gap |   xfp_rh3_per_pa |   replacement_delta | cross_verdict   |
|:--------------------------|:-----------------|:-----------|--------------:|---------------:|-------------:|:--------------|-------------------:|-----------------:|--------------------:|:----------------|
| U Just Lost To Edwin Diaz | Chase DeLauter   | RF         |         0.359 |          0.339 |        0     | SLUMPING      |             -0.016 |            0.588 |               0.099 | SLUMP_AMBIGUOUS |
| Frendy's Fantastic Team   | George Springer  | DH         |         0.362 |          0.301 |        0.017 | SLUMPING      |             -0.004 |            0.492 |               0.066 | SLUMP_AMBIGUOUS |
| Boone's Bad Bullpen       | Freddie Freeman  | 1B         |         0.395 |          0.354 |        0.114 | SLUMPING      |             -0.014 |            0.612 |               0.042 | SLUMP_AMBIGUOUS |
| Late Night Bettsing       | Jackson Merrill  | CF         |         0.359 |          0.297 |        0.009 | SLUMPING      |              0.002 |            0.521 |               0.032 | SLUMP_AMBIGUOUS |
| 2015 Draft First Round    | Sal Frelick      | RF         |         0.291 |          0.268 |        0.091 | SLUMPING      |             -0.012 |            0.511 |               0.022 | SLUMP_AMBIGUOUS |
| Boone's Bad Bullpen       | Gunnar Henderson | SS         |         0.351 |          0.283 |        0.022 | SLUMPING      |             -0.003 |            0.538 |               0.018 | SLUMP_AMBIGUOUS |
| Team Solomon              | Jose Altuve      | 2B         |         0.337 |          0.278 |        0.058 | SLUMPING      |             -0.008 |            0.526 |               0.009 | SLUMP_AMBIGUOUS |


## Sell-high candidates on YOUR roster

_None — no peakers cooling on your roster._

## Rival peakers cooling — they may sell, you may buy cheap

| team_name               | player_name   | position   |   percentile | form_bucket   |   recency_form_gap |   xfp_rh3_per_pa | cross_verdict     |
|:------------------------|:--------------|:-----------|-------------:|:--------------|-------------------:|-----------------:|:------------------|
| Treasure Island Mashers | Brice Turang  | 2B         |        0.951 | PEAK          |             -0.023 |            0.589 | SELL_HIGH_WARNING |