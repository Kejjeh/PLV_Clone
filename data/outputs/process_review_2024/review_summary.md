# Process+ Review — 2024
Generated: 2026-04-23 04:56 UTC

---

## Executive Summary

1. **Qualified hitters**: 413 (min_pa=150)
2. **Process+ distribution**: mean=102.26, std=10.59, range=[60.1, 148.1]
3. **Scaling params frozen from training population** (646 hitters)
4. **Year-over-year Process+ stability**: 0.646 (target ≥0.30)
5. **Suspicious cases**: 1 flagged (0 HIGH, 0 MEDIUM)
6. **No new models trained** — Process+ reuses PLV sub-models directly

**VERDICT: READY for exploratory leaderboards.** Process+ is centred near 100, no HIGH-severity issues, and year-over-year stability is sufficient. All three components are in production shape.

---

## 1. Component Scaling Parameters

  decision    : mean=0.065826  std=0.010224
  contact     : mean=-0.004163  std=0.023066
  power       : mean=-0.007464  std=0.050745
  process     : mean=0.054199  std=0.047791


---

## 2. Component Stability (Spearman-Brown reliability)

  Decision+: reliable at ≥50 PA (SB r≥0.70)
  Contact+: reliable at ≥25 PA (SB r≥0.70)
  Power+: reliable at ≥100 PA (SB r≥0.70)


---

## 3. Pairwise Component Correlations

  decision_plus vs contact_plus: r=-0.476
  decision_plus vs power_plus: r=0.147
  contact_plus vs power_plus: r=-0.381
*(expect |r| < 0.5 — high correlation suggests double-counting)*

---

## 4. Year-over-Year Stability (2023 → 2024)

  decision_plus: r=0.740 (n=322)
  contact_plus: r=0.790 (n=322)
  power_plus: r=0.724 (n=322)
  process_plus: r=0.646 (n=322)

---

## 5. Top 10 Process+ Hitters (2024)

```
      batter_name  pa  process_plus  decision_plus  contact_plus  power_plus
      Aaron Judge 761         148.1          106.7          91.4       147.9
    Shohei Ohtani 803         142.7           99.1         101.3       139.8
        Juan Soto 798         137.2          103.9         105.3       131.9
   Yordan Álvarez 644         131.3           88.1         119.9       122.8
   Fernando Tatís 472         130.5          115.2         104.1       123.8
    Marcell Ozuna 697         130.1          113.1          93.9       128.4
       Bobby Witt 734         129.6          107.1         113.2       120.5
     Brent Rooker 618         128.5          103.7          96.3       127.7
Vladimir Guerrero 708         128.2          108.0         113.3       118.9
  Kerry Carpenter 340         128.1          101.1          98.4       127.0
```

---

## 6. Bottom 10 Process+ Hitters (2024)

```
     batter_name  pa  process_plus  decision_plus  contact_plus  power_plus
   Austin Hedges 168          60.1          124.7          82.4        65.5
      Luke Maile 154          75.8          104.3          82.9        84.1
Martín Maldonado 150          75.8           96.2          86.6        84.1
    Taylor Walls 253          76.8          105.3          96.7        78.6
    Cavan Biggio 248          77.4           81.8          91.4        86.3
    Alex Jackson 168          79.2           96.7          90.6        85.3
  Garrett Stubbs 196          80.2          103.6          92.9        83.9
Travis Jankowski 210          80.6           95.8         105.4        80.1
   Miguel Vargas 237          81.1          113.0          93.5        82.5
   Dylan Carlson 279          82.6          109.4          88.8        86.8
```

---

## 7. Suspicious Cases

```
                      category severity  count                 detail
Extreme decision_value (|z|>3)      LOW     27 z range: [-4.98, 4.38]
```

---

*Unofficial public-data clone. Not affiliated with Pitcher List.*
