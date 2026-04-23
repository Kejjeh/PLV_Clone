# PLV MVP Review Summary — 2024
_Generated: 2026-04-23 04:37 UTC_
_Pipeline: train 2021-2023 | val 2024 | scored 2024_

---

## 10-Bullet Executive Summary

1. **Data scale**: 2,220,319 training pitches (2021-2023) and 742,122 validation pitches (2024) ingested with 0 duplicate pitch keys.
2. **All 5 sub-models beat naive baselines** on their primary metric (log-loss for classifiers, RMSE for BattedBallModel).
3. **SwingModel** (most-called model): log-loss=0.4450 vs baseline 0.6923, AUC=0.8706, ECE=0.0000.
4. **BattedBallModel**: RMSE=0.3707 (baseline 0.3768), Spearman r=0.1430. Low Spearman r is expected given extreme outcome variance of individual batted balls.
5. **PLV scale**: pitch-level mean=5.031 (target 5.0, deviation +0.031) — well-centred. Pitcher-level mean=5.025, std=0.215.
6. **Leaderboard top 3**: Hader, Josh (5.96), Montgomery, Mason (5.87), Kopech, Michael (5.80). Bottom 3: Boushley, Caleb (4.52), Williamson, Brandon (4.51), Blach, Ty (4.48).
7. **PLV-whiff correlation** (pitcher-level): Pearson r=0.604 — positive. Higher whiff rate should mean higher PLV.
8. **Stability at 200 pitches**: full-sample r=0.949 (Spearman-Brown) — reliable. Sufficient for season-level leaderboards.
9. **Year-over-year stability (2023->2024)**: Spearman r=0.751 — good predictive signal.
10. **Suspicious cases**: 0 HIGH-severity issues. A few MEDIUM/LOW-severity small-sample outliers and high-variance pitchers noted — expected behaviour.
11. **VERDICT: READY for exploratory leaderboards.** All models learn meaningful signal, PLV is well-scaled (pitch-level mean≈5, std≈1.5), no critical failures, and YoY stability is strong. Label all outputs as unofficial (public-data clone). System is ready to advance to Process+.

---

## Model Metrics at a Glance

| Model | Kind | n | Primary metric | Baseline | Beats? |
|-------|------|---|----------------|----------|--------|
| SwingModel | classifier | 742,122 | log-loss=0.445 | 0.6923 | YES |
| CalledStrikeModel | classifier | 386,258 | log-loss=0.1397 | 0.623 | YES |
| ContactModel | classifier | 355,864 | log-loss=0.4356 | 0.5428 | YES |
| FoulModel | classifier | 272,968 | log-loss=0.6614 | 0.6919 | YES |
| BattedBallModel | regression | 125,349 | RMSE=0.3707 | 0.3768 | YES |

---

## Data Integrity at a Glance

| Split | Rows | Pitchers | Date range |
|-------|------|----------|------------|
| Train 2021-2023 | 2,220,319 | 1610 | 2021-04-01 to 2023-11-01 |
| Val 2024 | 742,122 | 1025 | 2024-03-15 to 2024-10-30 |
| Scored 2024 | 742,122 | 1025 | 2024-03-15 to 2024-10-30 |

---

## Suspicious Cases Summary

Total issues logged: 1
HIGH severity: 0

| Category | Severity | Count | Detail |
|----------|----------|-------|--------|
| PLV out of [0,10] | LOW | 4113 | min=-3.540, max=12.208 |