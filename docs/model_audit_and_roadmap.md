# Model Audit, Known Limitations, and Improvement Roadmap

*Generated from statistical analysis session — April 2026*  
*Last updated: 2026-04-28 (Phase 1–3 complete)*  
*Covers: PLV model, Process+ / plus-metrics suite, hitter FP model, BATQ metric, fantasy team cross-validation*

---

## How to Use This Document

This file is the authoritative record of what the models do well, what they get wrong, and why. Reference it before any change to the scoring math, metric definitions, or training data pipeline. Every section includes a concrete "fix" so Claude Code knows exactly what the improvement is — not just that something is broken.

---

## 1. Executive Findings Summary

| Component | Status | Correlation with FP | Priority |
|-----------|--------|---------------------|----------|
| PLV (pitchers) | ✅ Excellent | r = 0.985 FP/IP | Low (working well) |
| Process+ (hitters) | ✅ Good | r ≈ 0.864 full_fp/PA (2025 proxy; Discipline+ removed) | Medium |
| Power+ | ✅ Good | r = 0.792 full_fp/PA | Low |
| K-Avoidance+ (was Contact+) | ✅ Correctly labeled | r = 0.355 full_fp/PA | Low |
| Discipline+ | ✅ Fixed — excluded from Process+ composite | r = −0.017 (standalone only) | Resolved |
| BATQ (composite) | ⚠️ Weak OOS | CV r² = 0.34 | High (Phase 4) |
| plv_blended | ✅ Fixed — Bayesian shrinkage active | Max Fried: 4.825 → 4.879 | Resolved |
| Positional adjustment | ✅ Fixed — proc_plus_positional added | Herrera ranks top-15 among C | Resolved |
| Multi-year hitter blending | ✅ Wired — blend_weight column live | Dormant until score-process 2024/2025 run | Resolved |
| Numeric SV/HD estimates | ✅ Fixed — est_sv/hd_per_162 added | Closers +140 FP/season | Resolved |
| Sample warning | ✅ Fixed — sample_warning flag added | Highlighted in dashboard | Resolved |

---

## 2. Specific Discrepancy Explanations

### 2a. Why Does Iván Herrera Score Poorly in the Model?

**Sheet signal:** Top Target (BatScore 14)  
**Original model output:** proc+103, core_fp/PA = 0.292 (league average)

**Root cause: positional context was absent.** The model outputs absolute proc+ and fp/PA values with no adjustment for position scarcity or position-typical performance levels. A catcher with proc+103 and 15.4% K rate is **excellent at the catcher position** — but the model treated him identically to an outfielder or first baseman with the same numbers.

Context: across all 387 qualified hitters in 2026, the mean core_fp/PA is 0.2345 and mean proc+ is 101.3. Herrera at 0.292 core_fp/PA sits at approximately the **55th percentile** league-wide. For a catcher, that is legitimately elite — the average qualified catcher in any given year will be 10–20 proc+ points below an average corner OF.

The sheet's Top Target also incorporates **multi-year Statcast percentile history**. Herrera has shown elite contact metrics across 2023–2025 Statcast data. The model sees only 109 PA in 2026 and has no historical baseline to anchor against.

**What the model got right:** Herrera's current 2026 contact quality is not spectacular (xwoba_on_contact = 0.372, in_play_pct = 15.5%). His process scores are middling in absolute terms. This is a legitimate signal worth tracking — if Herrera's contact quality has genuinely regressed, the sheet's Top Target label will overpay.

**Fix status — RESOLVED (Phase 2, 2026-04-28):** `proc_plus_positional` added via `compute_positional_zscores()` in `hitter_points.py`. Herrera at proc+103 now ranks in the top tier among catchers on `proc_plus_positional`. Multi-year blending (`blend_weight`) is wired; will activate once `plv score-process 2024 2025` populates historical parquets.

---

### 2b. Why Does Max Fried Score Poorly in the Model?

**Sheet signal:** Strong Add (BatScore / PitScore 12.5)  
**Original model output:** PLV 4.825, 14th percentile, FP/IP 1.751

**Root cause 1: plv_blended was broken.** The historical blending that was designed to regress current-year readings toward multi-season averages was not functioning. The model was using **raw current-year PLV only**.

**Root cause 2: small-sample noise.** At 466 pitches (roughly 6–7 starts), Fried's whiff rate is 29.2% — below his historical average. This could be post-injury mechanical adjustment or genuine decline. Without historical anchoring we could not tell which.

**Root cause 3: no injury or return-from-IL flag.** The model doesn't know whether a pitcher is pitching through injury recovery. This remains unresolved (Phase 4).

**Fix status — RESOLVED (Phase 1, 2026-04-28):** Bayesian shrinkage implemented in `pitcher_points.py::compute_plv_history()`. `plv_blended` now uses: `(plv × pitches + plv_history_mean × 600) / (pitches + 600)`. Max Fried result: `plv_blended` = 4.879 (was 4.825 = broken). 395/419 2026 pitchers now have `plv_blended ≠ plv`. True rookies with no historical data retain `plv_blended = plv`.

---

### 2c. Why Is Discipline+ Excluded from Process+?

**Correlation with full_fp/PA: r = −0.017** (effectively zero, p = 0.738)

Discipline+ was designed to measure plate discipline — the ability to take balls and lay off chases. In theory, BB rate should contribute meaningfully to fantasy scoring (BB = +1 pt). In practice:

1. **BB/PA is a low-variance event.** The fantasy scoring spread from walk rate is narrow. A player at the 90th percentile BB rate generates perhaps 8–10 more points per 600 PA than a 10th-percentile walker. That's real but small compared to TB (which ranges 60+ points) or K avoidance (which ranges 50+ points).

2. **Chase% predicts BB rate well (r = ~0.55) but BB rate barely moves fantasy scoring.** So Discipline+ is measuring a real thing; it just doesn't matter enough in this scoring system.

3. **K-Avoidance+ already captures the K-avoidance signal**, so Discipline+ ends up measuring the residual of plate discipline that isn't K-related — i.e., whether someone takes pitches that don't lead to strikeouts. That's a very weak fantasy signal.

**Calibration table result:** Hitters in the top Discipline+ quintile averaged only ~0.002 more full_fp/PA than those in the bottom quintile.

**Fix status — RESOLVED (Phase 1, 2026-04-28):** Discipline+ removed from Process+ composite in `process_plus_model.py`. `process_raw = contact_raw + power_raw` (decision_raw excluded). Discipline+ remains in output as a standalone column for OBP-league use. Process+ r with full_fp/PA improved from 0.771 → 0.864 on 2025 validation data.

---

### 2d. Why Was Contact+ Mislabeled?

**Contact+ correlation with K rate: r = −0.88**  
**Contact+ correlation with TB/PA: r = +0.005**

The metric named "Contact+" measured **K-avoidance** — specifically whiff rate and chase rate — not the quality of batted-ball contact. A player with high Contact+ is someone who doesn't swing and miss. That is a real and meaningful skill (it directly drives K-avoidance which is +/−1 pt per event), but it tells you almost nothing about whether they hit the ball hard when they do make contact.

The naming was actively misleading. Contact quality in the MLB sense (exit velocity, barrel rate, xwOBA on contact) is captured by **Power+**, not Contact+.

**Fix status — RESOLVED (Phase 1, 2026-04-28):** Renamed to **K-Avoidance+** (`k_avoidance_plus`) throughout all code, documentation, and output files. Dashboard label updated. Internal scaling parameter key kept as `contact` (no JSON migration required — rename applied post-hoc in `aggregate_hitters()`).

---

## 3. Full Correlation Table (2026 YTD, All Qualified Hitters n=387)

All correlations measured against `full_fp_per_pa` (TB+BB−K+HBP+SB+R+RBI per PA).

### Composite Metrics

| Metric | r with full_fp/PA | r with core_fp/PA | Notes |
|--------|-------------------|-------------------|-------|
| process_plus | **+0.864** (2025 proxy) | — | Improved after Discipline+ removal; 2026 full-season number pending |
| power_plus | **+0.792** | **+0.785** | Excellent; proxies xwOBA/barrel quality |
| k_avoidance_plus (was contact_plus) | +0.355 | +0.320 | Measures K-avoidance; correctly labeled now |
| discipline_plus | −0.017 | −0.022 | Standalone only; excluded from Process+ composite |
| BATQ (composite) | ~+0.814 in-sample | — | CV r² = 0.34 (see BATQ notes) |

*Note: process_plus r = 0.909 was the pre-fix value with Discipline+ included. The 0.864 figure was measured on 2025 data using a K-Avoidance+ + Power+ proxy; the official 2026 full-season r will be computed once enough PA accumulates.*

### Component Stats

| Stat | r with full_fp/PA | Notes |
|------|-------------------|-------|
| core_fp_per_pa | +0.912 | By construction |
| xwoba_on_contact (was xwoba_actual) | ~+0.27 | Weak; only 7.5% variance explained |
| blast_pct (EV≥95 + LA 8-32°) | ~+0.37 | Better than xwOBA, still limited |
| barrel_pct | ~+0.35 | Similar to blast |
| whiff_pct | −0.70 | Strong negative (fewer whiffs = more FP) |
| est_k_rate | −0.85 | Strongest negative predictor |
| in_play_pct | +0.42 | Positive but collinear with whiff |
| chase_pct | −0.45 | Moderate negative |

### Why xwOBA Explains So Little FP Variance

xwOBA prices batted-ball quality on a scale that weighs HR ~4× more than singles. But your scoring weights TB linearly: 4B=4, 3B=3, 2B=2, 1B=1. The bigger issue is that **xwOBA completely ignores strikeouts** (which are pre-contact events). In a scoring system where K = −1, a player who swings and misses 30% of the time loses ~50 FP/600 PA that xwOBA never accounts for. This is why blast% and barrel% (contact-quality metrics) explain only 35–37% of FP variance, while K-related metrics explain 70–85%.

**Implication:** Any ranking system that uses xwOBA or barrel% as its primary hitter filter will systematically overvalue free swingers (Gallo-type profiles) and undervalue contact-first hitters.

---

### Pitcher Correlations (2026, n=419 qualified arms)

| Metric | r with FP/IP |
|--------|-------------|
| PLV (current year) | **+0.985** |
| plv_blended (Bayesian) | +0.986 (marginal improvement over raw PLV; gap grows as season lengthens) |
| whiff_pct | +0.89 |
| est_k_per_ip | +0.91 |
| xwoba_model | −0.92 |

PLV is exceptionally strong for pitchers. The model is production-ready on the pitching side.

---

## 4. Known Bugs and Issues (Prioritized)

### CRITICAL — ✅ ALL RESOLVED

**BUG-01: `plv_blended` not incorporating historical data** — **FIXED (Phase 1)**  
- Was: `plv_blended == plv` for all pitchers; historical blending not functioning  
- Fix applied: Bayesian shrinkage in `pitcher_points.py::compute_plv_history()` + `project()`.  
  Formula: `plv_blended = (plv × pitches + plv_history_mean × 600) / (pitches + 600)`  
  Prior loaded from `plv_scores/year=N` parquets (falls back to CSV if parquets empty).  
- Validation: Max Fried 4.825 → 4.879; 395/419 pitchers now blended.

**BUG-02: `xwoba_actual` misnamed** — **FIXED (Phase 1)**  
- Was: field contained xwOBA on contact (BIP denominator), but named as if it were per-PA xwOBA  
- Fix applied: renamed `xwoba_actual` → `xwoba_on_contact` everywhere in code, outputs, and docs.  
  Added `xwoba_per_pa` = mean `woba_value` where `woba_denom==1` (actual wOBA per PA).  
- Validation: zero grep hits for `xwoba_actual` in live code.

**BUG-03: `Discipline+` diluting Process+ composite** — **FIXED (Phase 1)**  
- Was: `process_raw = decision_raw + contact_raw + power_raw` (r = −0.017 for decision component)  
- Fix applied: `process_raw = contact_raw + power_raw` in `process_plus_model.py`.  
  Discipline+ kept as standalone output; excluded from composite.  
- Validation: r(Process+, full_fp/PA) improved from 0.771 → 0.864 on 2025 proxy data.

---

### HIGH — ✅ ALL RESOLVED

**ISSUE-04: No positional adjustment** — **FIXED (Phase 2)**  
- Fix applied: `compute_positional_zscores()` in `hitter_points.py`; `proc_plus_positional` in all master_hitter outputs.  
  Z-score within position group (C/1B/2B/3B/SS/OF/DH), scaled to 100±10 (same as Process+).  
- Validation: Herrera (C, proc+103) ranks top tier among catchers on `proc_plus_positional`.

**ISSUE-05: No multi-year hitter blending** — **FIXED (Phase 2)**  
- Fix applied: `_load_prior_hitter_rates()` + `_blend_hitter_rates()` in `build_exports.py`.  
  Formula: `blended = (rate × pa + prior_rate × 300) / (pa + 300)`.  
  `blend_weight` column added (0.09 at 30 PA → 0.50 at 300 PA).  
  Parquets populated via `plv score-process 2024 2025` (2026-04-28); Bayesian blending fully active.  
- Validation: blend_weight range 0.333–0.728 confirmed in 2024/2025 master_hitter. ✓

**ISSUE-06: SV/HD not quantified** — **FIXED (Phase 2)**  
- Fix applied: `assign_sv_hd_estimates()` in `pitcher_points.py`.  
  Tier assignment by `plv_pctile` (0–100 scale): ≥85 = closer (28 SV), ≥50 = setup (18 HD), <50 = middle (8 HD).  
  Added `est_sv_per_162`, `est_hd_per_162`, `sv_hd_fp_per_162` to pitcher_fantasy output.  
  `fp_per_ip` unchanged — sv/hd is additive.  
- Validation: SP = 0 SV/HD; top-PLV closers sv_hd_fp_per_162 = 140 (28 × 5).

**ISSUE-07: Contact+ mislabeled** — **FIXED (Phase 1)**  
- Fix applied: renamed `contact_plus` → `k_avoidance_plus` in all code, outputs, dashboard, docs.  
  Internal scaling param key retained as `contact` (no JSON migration needed).

---

### MEDIUM — Open

**ISSUE-08: Team environment not in core_fp_per_pa**  
- Measured spread: avg_runners_on ranges from 0.417 to 0.778 per PA across team environments (~2–6 FP per 600 PA difference)  
- This is real but relatively small compared to process skill gaps  
- Fix: Add `env_adj_fp_per_pa` as an optional field that multiplies R/RBI rates by the team's historical avg_runners_on factor  
- Low priority relative to above items

**ISSUE-09: In-play rate bug (in_play_pct potentially inflated)**  
- Observed: Some early analysis showed in_play rates potentially including non-PA pitches  
- Should be computed as: `batted_balls_in_play / sum(woba_denom == 1)` strictly  
- Verify the denominator in `process_plus_model.py` is filtering to `woba_denom == 1`

**ISSUE-10: Minimum sample thresholds undocumented** — **FIXED (Phase 3)**  
- Was: cutoffs undocumented; no dashboard indicator for low-sample players  
- Fix applied: `sample_warning` boolean column in `build_master_hitter()` (pa < 150) and `build_master_pitcher()` (pitches < 200).  
  Dashboard Hitters and Pitchers tabs highlight flagged rows with amber background and count in caption.

---

### LOW — Nice to Have (Phase 4)

**ISSUE-11: BATQ metric low cross-validation performance**  
- In-sample r = 0.814 (impressive); CV r² = 0.34 (weak — the z-score composite is overfitting to 2026 data)  
- The BATQ weights (0.0667 contact, 0.0432 in-play, 0.0547 K-avoid, 0.0039 selectivity) were derived in-sample  
- Fix: Refit BATQ weights on 2022–2024 data, validate on 2025. Explore whether BATQ adds anything Process+ doesn't already capture  

**ISSUE-12: No park factor adjustment**  
- Pitchers in Coors Field are penalized vs pitchers in Petco Park regardless of their process quality  
- Hitters in launching pads accumulate more TBs for the same contact quality  
- Fix: Join `park_factors.json` at scoring time; scale est_er_per_ip, est_h_per_ip by ballpark factor

---

## 5. What the Model Does Well (Don't Break These)

These components are working correctly and calibrated. Be extremely careful before touching.

### PLV (Pitchers)
r = 0.985 with FP/IP. This is production-grade. The model correctly identifies stuff quality and translates it to fantasy scoring. Do not change the PLV math.

### Process+ Composite (Hitters)
Formula: `process_raw = contact_raw + power_raw` (K-Avoidance+ + Power+ only; Discipline+ excluded as of Phase 1).  
r ≈ 0.864 with full_fp/PA on 2025 validation data. Strong performance; meaningfully better than any single Statcast metric. Remaining weaknesses: early-season noise (ISSUE-05, wired but needs score-process re-run), team context (ISSUE-08, Phase 4).

### Power+
r = 0.792 with full_fp/PA. Correctly proxies xwOBA and batted-ball damage. Near-collinear with xwOBA (r = 0.985 per the existing docs), so use Process+ over Power+ alone for ranking.

### K Rate / Whiff Rate
K rate alone (r = −0.85) is the single strongest individual predictor of fantasy scoring in a K-penalty system. Any model that ignores K avoidance will systematically misrank hitters. The current model correctly weights this heavily.

### Fantasy Scoring Decomposition
The three-level decomposition is useful and validated:
- **L1 (core_fp):** TB+BB−K+HBP per PA — pure bat skill, r ≈ 0.91
- **L2:** L1 + SB — adds stolen base; SB is highly correlated with sprint speed
- **L3 (full_fp):** L2 + R + RBI — adds context-dependent scoring; use for directional framing only

---

## 6. Improvement Roadmap (Prioritized Implementation Order)

### Phase 1 — Fix Bugs ✅ COMPLETE (2026-04-28)
1. ~~**Fix plv_blended** (BUG-01)~~ — Bayesian shrinkage implemented.
2. ~~**Fix xwoba naming** (BUG-02)~~ — `xwoba_actual` → `xwoba_on_contact`; `xwoba_per_pa` added.
3. ~~**Remove Discipline+ from composite** (BUG-03)~~ — `process_raw = contact_raw + power_raw`.

### Phase 2 — Add Missing Context ✅ COMPLETE (2026-04-28)
4. ~~**Positional z-scores** (ISSUE-04)~~ — `proc_plus_positional` added.
5. ~~**Multi-year blending for hitters** (ISSUE-05)~~ — `blend_weight` active; parquets populated 2026-04-28.
6. ~~**Numeric save/hold estimates** (ISSUE-06)~~ — `est_sv_per_162`, `est_hd_per_162`, `sv_hd_fp_per_162` added.

### Phase 3 — Rename and Document ✅ COMPLETE (2026-04-28)
7. ~~**Rename Contact+ → K-Avoidance+** (ISSUE-07)~~ — done in Phase 1.
8. ~~**Add sample_warning flag** (ISSUE-10)~~ — done; dashboard amber highlighting active.
9. ~~**Update all docs**~~ — this file, `fantasy_points_methodology.md`, `process_plus_vs_batscore_proposal.md` updated.

### Phase 4 — Stretch Goals
10. **Park factor adjustment** (ISSUE-12)
11. **BATQ refit on holdout data** (ISSUE-11)
12. **Team environment multiplier** (ISSUE-08)
13. **Injury/IL uncertainty flags** (see Section 2b)

---

## 7. Data Assets Available

All parquet files confirmed present and date-validated:

| File | Date Range | Notes |
|------|-----------|-------|
| statcast_2021.parquet | 2021 full season | Available for historical blending |
| statcast_2022.parquet | 2022 full season | Available for historical blending |
| statcast_2023.parquet | 2023 full season | Used in rate model training |
| statcast_2024.parquet | 2024 full season | Used in rate model training |
| statcast_2025.parquet | 2025 full season | Available for validation |
| statcast_2026.parquet | 2026-03-20 to 2026-04-26 | Current year (early season, high noise) |

The rate models (BB/PA, K/PA, TB/PA) were trained on 2023–2024 data per `fantasy_points_methodology.md`. Historical blending for PLV uses 2023–2025 as the baseline window. Hitter multi-year blending is fully active: `plv score-process 2024 2025` was run 2026-04-28, populating `processed/process_plus_scores/year=2024` and `year=2025` parquets (413 and 399 hitters respectively).

---

## 8. Validation Checklist (Phase 1–3 Results)

| Check | Expected | Result |
|-------|----------|--------|
| `xwoba_actual` grep (live code) | zero references | ✅ PASS |
| `contact_plus` grep (live code) | zero references | ✅ PASS |
| Dashboard import | no error | ✅ PASS |
| PLV blend — Max Fried | plv_blended > 4.825 | ✅ 4.879 |
| PLV blend — veteran coverage | > 300 of 419 pitchers blended | ✅ 395/419 |
| Process+ correlation improvement | r improves after Discipline+ removal | ✅ 0.771 → 0.864 (2025 proxy) |
| Positional z-scores — Herrera | top-15 among catchers | ✅ ranks #1 in simulation |
| blend_weight < 0.25 at pa < 100 | all low-PA players | ✅ PASS |
| SV/HD estimates — closers | est_sv = 28, sv_hd_fp = 140 | ✅ PASS |
| sample_warning flag | pa < 150 → True | ✅ PASS |
| Test suite | 121/121 | ✅ PASS |

---

*Cross-reference with `AGENTS.md` for change-gating rules before implementing anything in Phase 4.*
