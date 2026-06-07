# Per-lens reliability (calibration) diagrams

Generated 2026-06-06.

## Method

For each lens, the per-snapshot lens signal is mapped to a verdict in {-1, -0.5, 0, +0.5, +1} via population quintile cuts. Mean forward FP (`target`) is computed per verdict bin with 95% CIs. A CALIBRATED lens is strictly monotonic increasing. INVERTED = strictly decreasing. U-SHAPED / INVERTED-U = extremum in middle. FLAT = max-min spread < 5% of pooled mean.

**Caveat (top-rank sampling):** The snapshot is restricted to top-150 hitters and top-100 SPs by season-FP. This compresses the lower verdict bins (the FADEs are still above-average players population-wide) and narrows the BUY-to-FADE spread relative to a full-population calibration. Top-rank sampling tends to FLATTEN signals; rank-based lenses (L1, L8) are most affected because the top-k cutoff is itself the signal.

## Hitters

- n_snapshots = 1498
- forward target mean = 2.189 +/- 0.893
- tiers = {'51-150': 1089, 'top50': 409}

### L1 Blended-xFP / rh3-rank

**Verdict: CALIBRATED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 277 | 1.756 | [1.662, 1.849] |
| FADE-LITE (-0.5) | 276 | 1.953 | [1.854, 2.052] |
| HOLD (+0.0) | 277 | 2.129 | [2.035, 2.224] |
| BUY-LITE (+0.5) | 276 | 2.298 | [2.210, 2.387] |
| BUY (+1.0) | 277 | 2.875 | [2.773, 2.977] |

```
          FADE (-1.0): #                               mean= 1.756  n=277
     FADE-LITE (-0.5): #####                           mean= 1.953  n=276
          HOLD (+0.0): ##########                      mean= 2.129  n=277
      BUY-LITE (+0.5): ###############                 mean= 2.298  n=276
           BUY (+1.0): ##############################  mean= 2.875  n=277
      pop mean        : ..............................  mean= 2.189
```

### L2 boom-bust L21/L8

**Verdict: CALIBRATED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 307 | 1.852 | [1.760, 1.944] |
| FADE-LITE (-0.5) | 293 | 2.038 | [1.943, 2.132] |
| HOLD (+0.0) | 304 | 2.141 | [2.046, 2.236] |
| BUY-LITE (+0.5) | 318 | 2.328 | [2.232, 2.425] |
| BUY (+1.0) | 276 | 2.615 | [2.507, 2.723] |

```
          FADE (-1.0): #                               mean= 1.852  n=307
     FADE-LITE (-0.5): #######                         mean= 2.038  n=293
          HOLD (+0.0): ###########                     mean= 2.141  n=304
      BUY-LITE (+0.5): ###################             mean= 2.328  n=318
           BUY (+1.0): ##############################  mean= 2.615  n=276
      pop mean        : ..............................  mean= 2.189
```

### L3 sustainability proxy

**Verdict: U-SHAPED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 300 | 2.301 | [2.189, 2.413] |
| FADE-LITE (-0.5) | 299 | 2.101 | [2.000, 2.202] |
| HOLD (+0.0) | 300 | 2.220 | [2.121, 2.320] |
| BUY-LITE (+0.5) | 299 | 2.132 | [2.042, 2.222] |
| BUY (+1.0) | 300 | 2.188 | [2.087, 2.290] |

```
          FADE (-1.0): ##############################  mean= 2.301  n=300
     FADE-LITE (-0.5): #                               mean= 2.101  n=299
          HOLD (+0.0): ##################              mean= 2.220  n=300
      BUY-LITE (+0.5): #####                           mean= 2.132  n=299
           BUY (+1.0): #############                   mean= 2.188  n=300
      pop mean        : ..............................  mean= 2.189
```

### L4 prior-year baseline

**Verdict: CALIBRATED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 279 | 1.825 | [1.725, 1.926] |
| FADE-LITE (-0.5) | 278 | 1.959 | [1.867, 2.051] |
| HOLD (+0.0) | 274 | 2.129 | [2.032, 2.225] |
| BUY-LITE (+0.5) | 277 | 2.270 | [2.178, 2.361] |
| BUY (+1.0) | 275 | 2.837 | [2.732, 2.941] |

```
          FADE (-1.0): #                               mean= 1.825  n=279
     FADE-LITE (-0.5): ####                            mean= 1.959  n=278
          HOLD (+0.0): #########                       mean= 2.129  n=274
      BUY-LITE (+0.5): #############                   mean= 2.270  n=277
           BUY (+1.0): ##############################  mean= 2.837  n=275
      pop mean        : ..............................  mean= 2.189
```

### L5 xwOBA L21 vs prior

**Verdict: U-SHAPED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 277 | 2.225 | [2.117, 2.332] |
| FADE-LITE (-0.5) | 276 | 2.078 | [1.979, 2.177] |
| HOLD (+0.0) | 277 | 2.176 | [2.070, 2.282] |
| BUY-LITE (+0.5) | 276 | 2.188 | [2.092, 2.284] |
| BUY (+1.0) | 277 | 2.345 | [2.229, 2.461] |

```
          FADE (-1.0): ################                mean= 2.225  n=277
     FADE-LITE (-0.5): #                               mean= 2.078  n=276
          HOLD (+0.0): ###########                     mean= 2.176  n=277
      BUY-LITE (+0.5): ############                    mean= 2.188  n=276
           BUY (+1.0): ##############################  mean= 2.345  n=277
      pop mean        : ..............................  mean= 2.189
```

### L6 xwOBACON YoY direction

**Verdict: U-SHAPED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 135 | 2.165 | [1.998, 2.332] |
| FADE-LITE (-0.5) | 131 | 2.134 | [1.993, 2.275] |
| HOLD (+0.0) | 134 | 2.115 | [1.980, 2.251] |
| BUY-LITE (+0.5) | 130 | 2.345 | [2.207, 2.483] |
| BUY (+1.0) | 130 | 2.410 | [2.253, 2.568] |

```
          FADE (-1.0): #####                           mean= 2.165  n=135
     FADE-LITE (-0.5): ##                              mean= 2.134  n=131
          HOLD (+0.0): #                               mean= 2.115  n=134
      BUY-LITE (+0.5): #######################         mean= 2.345  n=130
           BUY (+1.0): ##############################  mean= 2.410  n=130
      pop mean        : ..............................  mean= 2.189
```

### L7 archetype/age decline

**Verdict: U-SHAPED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 135 | 2.165 | [1.998, 2.332] |
| FADE-LITE (-0.5) | 131 | 2.134 | [1.993, 2.275] |
| HOLD (+0.0) | 134 | 2.115 | [1.980, 2.251] |
| BUY-LITE (+0.5) | 130 | 2.345 | [2.207, 2.483] |
| BUY (+1.0) | 130 | 2.410 | [2.253, 2.568] |

```
          FADE (-1.0): #####                           mean= 2.165  n=135
     FADE-LITE (-0.5): ##                              mean= 2.134  n=131
          HOLD (+0.0): #                               mean= 2.115  n=134
      BUY-LITE (+0.5): #######################         mean= 2.345  n=130
           BUY (+1.0): ##############################  mean= 2.410  n=130
      pop mean        : ..............................  mean= 2.189
```

### L8 model rank vs replacement

**Verdict: CALIBRATED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 277 | 1.756 | [1.662, 1.849] |
| FADE-LITE (-0.5) | 276 | 1.953 | [1.854, 2.052] |
| HOLD (+0.0) | 277 | 2.129 | [2.035, 2.224] |
| BUY-LITE (+0.5) | 276 | 2.298 | [2.210, 2.387] |
| BUY (+1.0) | 277 | 2.875 | [2.773, 2.977] |

```
          FADE (-1.0): #                               mean= 1.756  n=277
     FADE-LITE (-0.5): #####                           mean= 1.953  n=276
          HOLD (+0.0): ##########                      mean= 2.129  n=277
      BUY-LITE (+0.5): ###############                 mean= 2.298  n=276
           BUY (+1.0): ##############################  mean= 2.875  n=277
      pop mean        : ..............................  mean= 2.189
```

---

## Starting Pitchers

- n_snapshots = 550
- forward target mean = 13.235 +/- 4.724
- tiers = {'top50': 314, '51-100': 236}

### L1 Blended-xFP / rp3-rank

**Verdict: U-SHAPED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 93 | 11.808 | [10.878, 12.739] |
| FADE-LITE (-0.5) | 92 | 11.659 | [10.611, 12.708] |
| HOLD (+0.0) | 93 | 14.302 | [13.462, 15.141] |
| BUY-LITE (+0.5) | 92 | 13.784 | [12.820, 14.749] |
| BUY (+1.0) | 93 | 15.192 | [14.364, 16.020] |

```
          FADE (-1.0): #                               mean=11.808  n=93
     FADE-LITE (-0.5): #                               mean=11.659  n=92
          HOLD (+0.0): ######################          mean=14.302  n=93
      BUY-LITE (+0.5): ##################              mean=13.784  n=92
           BUY (+1.0): ##############################  mean=15.192  n=93
      pop mean        : ..............................  mean=13.235
```

### L2 boom-bust L21/L8

**Verdict: CALIBRATED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 110 | 12.451 | [11.677, 13.224] |
| FADE-LITE (-0.5) | 110 | 12.514 | [11.630, 13.399] |
| HOLD (+0.0) | 110 | 13.151 | [12.215, 14.087] |
| BUY-LITE (+0.5) | 110 | 13.487 | [12.614, 14.359] |
| BUY (+1.0) | 110 | 14.571 | [13.675, 15.466] |

```
          FADE (-1.0): #                               mean=12.451  n=110
     FADE-LITE (-0.5): #                               mean=12.514  n=110
          HOLD (+0.0): ##########                      mean=13.151  n=110
      BUY-LITE (+0.5): ###############                 mean=13.487  n=110
           BUY (+1.0): ##############################  mean=14.571  n=110
      pop mean        : ..............................  mean=13.235
```

### L3 sustainability proxy

**Verdict: INVERTED-U**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 108 | 12.601 | [11.824, 13.379] |
| FADE-LITE (-0.5) | 107 | 13.792 | [12.870, 14.715] |
| HOLD (+0.0) | 108 | 13.303 | [12.417, 14.188] |
| BUY-LITE (+0.5) | 107 | 13.594 | [12.664, 14.523] |
| BUY (+1.0) | 108 | 13.232 | [12.309, 14.154] |

```
          FADE (-1.0): #                               mean=12.601  n=108
     FADE-LITE (-0.5): ##############################  mean=13.792  n=107
          HOLD (+0.0): ##################              mean=13.303  n=108
      BUY-LITE (+0.5): #########################       mean=13.594  n=107
           BUY (+1.0): ################                mean=13.232  n=108
      pop mean        : ..............................  mean=13.235
```

### L4 prior-year baseline

**Verdict: CALIBRATED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 94 | 11.951 | [11.040, 12.861] |
| FADE-LITE (-0.5) | 91 | 11.961 | [10.892, 13.029] |
| HOLD (+0.0) | 94 | 13.954 | [13.079, 14.829] |
| BUY-LITE (+0.5) | 94 | 14.203 | [13.280, 15.127] |
| BUY (+1.0) | 90 | 14.704 | [13.795, 15.613] |

```
          FADE (-1.0): #                               mean=11.951  n=94
     FADE-LITE (-0.5): #                               mean=11.961  n=91
          HOLD (+0.0): ######################          mean=13.954  n=94
      BUY-LITE (+0.5): #########################       mean=14.203  n=94
           BUY (+1.0): ##############################  mean=14.704  n=90
      pop mean        : ..............................  mean=13.235
```

### L5 xwOBA L21 vs prior

**Verdict: INVERTED-U**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 93 | 12.848 | [12.006, 13.690] |
| FADE-LITE (-0.5) | 92 | 13.394 | [12.490, 14.297] |
| HOLD (+0.0) | 93 | 13.467 | [12.331, 14.602] |
| BUY-LITE (+0.5) | 92 | 14.154 | [13.292, 15.016] |
| BUY (+1.0) | 93 | 12.907 | [11.869, 13.945] |

```
          FADE (-1.0): #                               mean=12.848  n=93
     FADE-LITE (-0.5): #############                   mean=13.394  n=92
          HOLD (+0.0): ##############                  mean=13.467  n=93
      BUY-LITE (+0.5): ##############################  mean=14.154  n=92
           BUY (+1.0): #                               mean=12.907  n=93
      pop mean        : ..............................  mean=13.235
```

### L6 xwOBACON YoY direction

**Verdict: INVERTED-U**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 41 | 13.361 | [12.106, 14.615] |
| FADE-LITE (-0.5) | 36 | 13.551 | [11.876, 15.226] |
| HOLD (+0.0) | 33 | 13.072 | [11.571, 14.572] |
| BUY-LITE (+0.5) | 39 | 14.519 | [12.884, 16.154] |
| BUY (+1.0) | 34 | 12.399 | [10.649, 14.150] |

```
          FADE (-1.0): ##############                  mean=13.361  n=41
     FADE-LITE (-0.5): ################                mean=13.551  n=36
          HOLD (+0.0): ##########                      mean=13.072  n=33
      BUY-LITE (+0.5): ##############################  mean=14.519  n=39
           BUY (+1.0): #                               mean=12.399  n=34
      pop mean        : ..............................  mean=13.235
```

### L7 archetype/age decline

**Verdict: INVERTED-U**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 41 | 13.361 | [12.106, 14.615] |
| FADE-LITE (-0.5) | 36 | 13.551 | [11.876, 15.226] |
| HOLD (+0.0) | 33 | 13.072 | [11.571, 14.572] |
| BUY-LITE (+0.5) | 39 | 14.519 | [12.884, 16.154] |
| BUY (+1.0) | 34 | 12.399 | [10.649, 14.150] |

```
          FADE (-1.0): ##############                  mean=13.361  n=41
     FADE-LITE (-0.5): ################                mean=13.551  n=36
          HOLD (+0.0): ##########                      mean=13.072  n=33
      BUY-LITE (+0.5): ##############################  mean=14.519  n=39
           BUY (+1.0): #                               mean=12.399  n=34
      pop mean        : ..............................  mean=13.235
```

### L8 model rank vs replacement

**Verdict: U-SHAPED**

| verdict | n | mean FP | 95% CI |
|---|---|---|---|
| FADE (-1.0) | 93 | 11.808 | [10.878, 12.739] |
| FADE-LITE (-0.5) | 92 | 11.659 | [10.611, 12.708] |
| HOLD (+0.0) | 93 | 14.302 | [13.462, 15.141] |
| BUY-LITE (+0.5) | 92 | 13.784 | [12.820, 14.749] |
| BUY (+1.0) | 93 | 15.192 | [14.364, 16.020] |

```
          FADE (-1.0): #                               mean=11.808  n=93
     FADE-LITE (-0.5): #                               mean=11.659  n=92
          HOLD (+0.0): ######################          mean=14.302  n=93
      BUY-LITE (+0.5): ##################              mean=13.784  n=92
           BUY (+1.0): ##############################  mean=15.192  n=93
      pop mean        : ..............................  mean=13.235
```


## Summary

| Lens | Hitters | SP |
|---|---|---|
| L1 Blended-xFP / rh3-rank | CALIBRATED (spread 1.12) | U-SHAPED (spread 3.53) |
| L2 boom-bust L21/L8 | CALIBRATED (spread 0.76) | CALIBRATED (spread 2.12) |
| L3 sustainability proxy | U-SHAPED (spread 0.20) | INVERTED-U (spread 1.19) |
| L4 prior-year baseline | CALIBRATED (spread 1.01) | CALIBRATED (spread 2.75) |
| L5 xwOBA L21 vs prior | U-SHAPED (spread 0.27) | INVERTED-U (spread 1.31) |
| L6 xwOBACON YoY direction | U-SHAPED (spread 0.29) | INVERTED-U (spread 2.12) |
| L7 archetype/age decline | U-SHAPED (spread 0.29) | INVERTED-U (spread 2.12) |
| L8 model rank vs replacement | CALIBRATED (spread 1.12) | U-SHAPED (spread 3.53) |
