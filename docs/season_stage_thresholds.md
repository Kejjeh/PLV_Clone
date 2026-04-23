# Season-Stage Thresholds

## Overview

The core PLV and Process+ model scales are **frozen** — this document covers only the
workflow layer: confidence tiers, board filters, and fantasy decision thresholds.

Thresholds adapt to three season stages so that the same signal strength is required
at any point in the year. Early-season data has ~50% wider variance on Process+ and
Power+ than full-season data; without adjustment, the boards would flood with noise
and miss genuine signal.

---

## Stage Definitions

| Stage  | Hitter PA median | Approx. dates      | Detection                      |
|--------|------------------|--------------------|--------------------------------|
| Early  | < 150            | Mar 20 – May 15    | Auto from loaded dataset       |
| Mid    | 150 – 320        | May 16 – Jul 25    | Auto from loaded dataset       |
| Mature | > 320            | Jul 26 – end       | Auto from loaded dataset       |

Stage detection uses `infer_stage()` in `utils/season_stage.py`. It takes the
**league median PA** of whatever dataset is loaded — so it works correctly for any
year, including historical review.

A manual override is available in both the dashboard sidebar and the CLI:
```
plv build-target-boards 2026 --stage early
```

---

## Why Thresholds Change

### Process+ and Power+ variance inflation

From 2023–2025 full-season data (n ≈ 1,200 hitter-seasons):

| Metric      | Full season std | Early season std | Inflation |
|-------------|-----------------|------------------|-----------|
| Process+    | 10.6            | 16.2             | +53%      |
| Power+      | 10.6            | 15.6             | +47%      |
| Decision+   | ~11             | ~13              | +18%      |

The consequence: **PP >= 110 catches the top 18% of hitters at full season, but the
top 33% of hitters at early season**. Without gating, the breakout board becomes
meaningless in April.

### Decision+ is the most stable early metric

Split-half reliability at 50 PA: Decision+ r = 0.741 vs. Process+ r ≈ 0.45.
Decision+ is the most interpretable early-season filter — it measures the
swing/take *choice*, which stabilizes faster than contact or power outcomes.

### rank_gap noise

The rank_gap (Process+ percentile rank minus xwOBA percentile rank) has:
- std = 0.115 in early season
- std = 0.148–0.157 at full season

A threshold of 0.15 (mature) represents only 1.3 standard deviations in early
season data. Raising it to 0.20 early gives 1.74 std deviations (top ~4%),
ensuring the buy signal represents a real divergence rather than noise.

### Rolling and PLV thresholds are stable

Rolling decision_value p50 = 0.066, p75 = 0.083 — consistent across 2023, 2024,
and 2025. PLV p75 = 5.17–5.20 across all stages. These do not need adjustment.

---

## Threshold Table

### Hitter buy targets

| Parameter          | Early  | Mid    | Mature | Notes                                  |
|--------------------|--------|--------|--------|----------------------------------------|
| `min_pa_for_boards`| 40     | 50     | 150    | Minimum to appear on any board         |
| `buy_rank_gap_min` | 0.20   | 0.17   | 0.15   | pp_rank – xwoba_rank                   |
| `buy_pp_floor`     | 102.0  | 101.0  | 100.0  | Minimum Process+                       |
| `buy_dec_gate`     | 109.0  | None   | None   | Required Decision+ (early only)        |

### Regression flags

| Parameter          | Early  | Mid    | Mature | Notes                                  |
|--------------------|--------|--------|--------|----------------------------------------|
| `reg_rank_gap_max` | -0.20  | -0.17  | -0.15  | xwoba_rank – pp_rank (negative)        |
| `reg_xwoba_floor`  | 0.350  | 0.350  | 0.350  | Min xwOBA to appear on board           |
| `reg_dec_gate`     | 97.0   | 94.0   | None   | Require Decision+ below this           |

### Breakout flags

| Parameter            | Early  | Mid    | Mature | Notes                                  |
|----------------------|--------|--------|--------|----------------------------------------|
| `breakout_pp_min`    | 110.0  | 110.0  | 110.0  | Process+ floor (unchanged)             |
| `breakout_dec_gate`  | 112.0  | 109.0  | None   | Required Decision+ (tighter early)     |

### Discipline and Power

| Parameter              | Early  | Mid    | Mature | Notes                                  |
|------------------------|--------|--------|--------|----------------------------------------|
| `discipline_dec_min`   | 109.0  | 109.0  | 109.0  | Stable — Decision+ is reliable early   |
| `power_pow_min`        | 110.0  | 108.0  | 107.0  | Power+ bar raised early (wider std)    |

### Confidence tiers (hitters)

| Tier label   | Early PA | Mid PA | Mature PA | Description             |
|--------------|----------|--------|-----------|-------------------------|
| Tier A / Signal / Building | 80   | 200    | 400       | High-confidence signal  |
| Tier B / Watch / Early Signal | 40 | 100    | 250       | Use with caution        |
| Tier C / Too Early / Limited | 0  | 50     | 150       | Treat as watch list     |

---

## Calibration Notes

- Calibration dataset: 2023–2025 full-season data, n ≈ 1,200 hitter-seasons.
- 2026 is used **only for validation** (3-week snapshot as of calibration date).
- Decision+ thresholds (109.0 = top 25%) are the same across all stages because
  the metric is reliable even at 50 PA. No stage adjustment needed.
- Rolling thresholds and PLV thresholds are identical across all stages.
- All stage thresholds are defined in `utils/season_stage.py` (`_EARLY`, `_MID`, `_MATURE`).

---

## 2026 Validation (early season, ~3 weeks)

2026 auto-detects as **Early Season**. Board counts with early-stage thresholds:

| Board                   | 2026 rows | 2024 rows (mature) | Comment                            |
|-------------------------|-----------|--------------------|------------------------------------|
| Buy targets             | 3         | 48                 | Tight rank_gap + D+ gate working   |
| Breakout flags          | 1         | 8                  | D+ gate required (PP noise early)  |
| Regression flags        | 2         | 47                 | Low signal expected at 3 weeks     |
| Discipline targets      | 46        | 105                | D+ reliable — good board size      |
| Power targets           | 79        | 108                | Higher bar (110 vs 107)            |
| Pitcher PLV targets     | 162       | 229                | Lower pitch-count minimum          |

The tight buy/regression boards (3 and 2 rows) are intentional: at 3 weeks of
data, very few hitters have a stable enough rank_gap to trust. The discipline
and power boards remain useful because Decision+ and Power+ give signal sooner.

---

## How to Interpret Boards by Stage

**Early season** — trust the discipline board; treat buy/regression as a watchlist
only. The `[Early Season]` label in the tag column flags every board entry.
Decision+ gate on buy targets means every buy flag has confirmed process quality.

**Mid season** — buy/regression boards gain reliability as PA accumulates.
Decision+ gate is removed from buy flags; regression flags still require weak D+
to distinguish process weakness from BABIP luck.

**Mature season** — all boards operate at full confidence. Standard thresholds.
No stage labels appended to tags.
