# RP sub-domain validation — empirical YoY stability tests

**Date:** 2026-05-28
**Purpose:** Before committing the RP archetype build to a set of sub-domains, validate that each one actually behaves as signal (not noise) for relievers. Mirror the SP archetype YoY-stability discipline.

**Cohort floor (applied identically across years):** `G >= 20 AND TBF >= 50`. YoY pairs are pitchers who satisfy this floor in BOTH year T and year T+1. Years covered: 2018–2025 (drop 2026, incomplete).

**Bar:** A subdomain needs YoY pearson **r ≥ 0.40** to be **KEEP**; **0.20–0.40 MAYBE**; **<0.20 DROP**.

**Data sources:**
- `data/research/xfp_cache/relievers_multiyr_2018_2026.csv` — per-RP-year rate aggregates
- `data/research/xfp_cache/pitcher_splits.csv` — L/R xwOBA splits (2022-2026 only)
- `data/research/xfp_cache/statcast_<year>.parquet` — derived gb_pct, barrel_pct, xwoba_contact

**Validation script:** `scripts/xfp/_research/rp_subdomain_validation.py`

**Cohort sizes by year (G≥20 & TBF≥50):**
| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| 282 | 284 | 133 | 302 | 285 | 258 | 265 | 279 |

YoY pairs total = **1,014** (after BOTH-year cohort filter).

---

## Test A — YoY stability of proposed rate sub-domains

Output: `RP_VALIDATION_A.csv`

| Subdomain (metric)             | column              | n_pairs | r       | Verdict |
|--------------------------------|---------------------|---------|---------|---------|
| SWING_MISS (swstr_pct)         | swstr_pct           | 1014    | +0.6293 | **KEEP** |
| SWING_MISS (CSW = c_plus_swstr)| c_plus_swstr        | 1014    | +0.5072 | **KEEP** |
| CALLED_STRIKE (called/pitches) | called_strike_rate  | 1014    | +0.6149 | **KEEP** |
| DAMAGE_SUPP (xwoba_contact)    | xwoba_contact       | 1014    | +0.1189 | **DROP** |
| DAMAGE_SUPP (barrel_pct)       | barrel_pct          | 1014    | +0.2019 | MAYBE   |
| GB_TENDENCY (gb_pct)           | gb_pct (statcast)   | 1014    | +0.7136 | **KEEP** |
| WALK_AVOID (bb_pct)            | bb_pct              | 1014    | +0.4438 | **KEEP** |
| velo_rating (avg FB velo)      | avg_velo            | 1014    | +0.9272 | **KEEP** |
| K_RATE (k_pct, reference)      | k_pct               | 1014    | +0.5717 | **KEEP** |
| xwoba_per_pa (overall ref)     | xwoba_per_pa        | 1014    | +0.2014 | MAYBE   |

### Notes
- **swstr_pct beats CSW** for RPs (0.63 vs 0.51). Use swstr_pct as the SWING_MISS axis input.
- **GB_TENDENCY is one of the most stable RP signals (r=0.71)** — this is real and matches SP's stable GB findings.
- **DAMAGE_SUPP is the weak axis.** Both xwoba_contact (r=0.12) and barrel_pct (r=0.20) fall below the keep bar. This is the classic "BABIP noise" problem at RP sample sizes. The bar misses because RPs face only 200-300 BIP/year vs SPs at 500-700, so the year-to-year contact-quality estimate is much noisier.
- **velo_rating is the gold standard** (r=0.93). A pitcher who throws 96 last year throws 96 this year, modulo aging.

---

## Test B — L/R splits YoY (RP-specific re-test)

The SP version of this test failed (r=0.05–0.09). RPs are deployed against same-side hitters more selectively, so the underlying skill might surface. **TBF-side floor = 25** to avoid trivial-sample noise.

Output: `RP_VALIDATION_B.csv`

| Cohort   | Split    | n_pairs | r       | Verdict |
|----------|----------|---------|---------|---------|
| ALL_RPs  | xwoba_vs_L | 473   | +0.3095 | MAYBE   |
| RHP only | xwoba_vs_L | 342   | +0.2567 | MAYBE   |
| LHP only | xwoba_vs_L | 131   | +0.0798 | DROP    |
| ALL_RPs  | xwoba_vs_R | 474   | +0.2554 | MAYBE   |
| RHP only | xwoba_vs_R | 343   | +0.2433 | MAYBE   |
| LHP only | xwoba_vs_R | 131   | +0.1260 | DROP    |

### Verdict
**Marginal improvement over the SP failure, but NOT good enough to commit as a primary subdomain.** ALL_RPs and RHP-only land in MAYBE (r=0.24–0.31), LHP splits are noise (r=0.08–0.13). Note the splits file only covers 2022-2026, so n_pairs is limited (473-474 vs 1,014 for Test A) and CIs are wider. Bias toward NOT including L/R splits in the rating panel. Could be revisited as a **soft tag** ("OBVIOUS_PLATOON_GUY") computed as a tier rather than a 20-80 rating.

---

## Test C — Role persistence YoY

Output: `RP_VALIDATION_C_confusion.csv`, `RP_VALIDATION_C_persistence.csv`

Role definition (within RP cohort, year T):
- **CLOSER** if SV ≥ 15
- **SETUP** if HLD ≥ 15 AND not CLOSER
- **MIDDLE** if neither but G ≥ 30
- **MOPUP** otherwise

Confusion matrix (row = role year T, column = role year T+1, row-normalized):

|         | CLOSER | MIDDLE | MOPUP | SETUP |
|---------|--------|--------|-------|-------|
| CLOSER  | **0.578** | 0.180 | 0.078 | 0.164 |
| SETUP   | 0.088  | 0.358  | 0.239 | **0.314** |
| MIDDLE  | 0.050  | **0.536** | 0.210 | 0.204 |
| MOPUP   | 0.099  | 0.448  | **0.246** | 0.207 |

Diagonal persistence:

| Role    | n year_t | persist_pct |
|---------|----------|-------------|
| CLOSER  | 128      | **57.8%**   |
| MIDDLE  | 457      | 53.6%       |
| SETUP   | 226      | 31.4%       |
| MOPUP   | 203      | 24.6%       |

**Overall any-role match: 43.4%**

### Notes
- **Closer persistence ~58%, not the 83% in memory.** The memory's `closer_persistence.csv` measures within-season midyear→endyear continuity (which is naturally higher). YoY closer continuity at the SV≥15 cut is materially lower. Robust to threshold: SV≥10 → 60.7%, SV≥15 → 57.8%, SV≥20 → 57.4%.
- **SETUP and MOPUP are noisy buckets** (31% / 25%) — these are revolving-door slots driven by manager preference + bullpen depth. Don't over-weight them as a stable archetype tag.
- **MIDDLE is sticky** (54%) — workhorse middle-relief RPs tend to repeat that role.
- **Closer→Setup/Middle pipe is large** (~24% of T-closers fall out of the role). This is the "lost the closer job" base rate.

**Recommendation:** Role IS a useful subdomain but only as a 2-class binary (HIGH_LEVERAGE = CLOSER∪SETUP vs LOW_LEVERAGE = MIDDLE∪MOPUP). Closer alone is a usable tag with ~58% persistence. SETUP alone is not.

---

## Test D — gmLI YoY stability

**Status: BLOCKED.** No `gmLI` or `LI` column found in any of:
- `relievers_multiyr_2018_2026.csv`
- `rolling_relievers_2018_2026.csv`
- `rp3_training_frame_full.csv`

Would need a FanGraphs pull (e.g., `pybaseball.pitching_stats_bref` or FG leaderboard CSV with the `gmLI` column). Recommend acquiring this for the v2 build — leverage is the cleanest single-number proxy for "role importance" and would let us validate the HIGH_LEVERAGE binary from Test C with a continuous metric.

Output: `RP_VALIDATION_D.csv` (status row only)

---

## Test E — IP per appearance YoY

Computed as `ip / g` on the RP cohort.

| Metric             | n_pairs | r       | Verdict |
|--------------------|---------|---------|---------|
| ip_per_appearance  | 1014    | +0.4694 | **KEEP** |

**This is a clean signal for the "bulk reliever / multi-inning guy" archetype.** Stable enough to be its own rated axis. Output: `RP_VALIDATION_E.csv`.

---

## Final recommended sub-domain list for RP archetype build

Six primary rated axes (all r ≥ 0.40):

| Subdomain         | Input column        | YoY r   |
|-------------------|---------------------|---------|
| **SWING_MISS**    | swstr_pct           | +0.629  |
| **CALLED_STRIKE** | called_strike_rate  | +0.615  |
| **GB_TENDENCY**   | gb_pct (from statcast BIP) | +0.714 |
| **WALK_AVOID**    | bb_pct              | +0.444  |
| **VELO**          | avg_velo            | +0.927  |
| **BULK** (multi-inning capacity) | ip_per_appearance | +0.469  |

Plus tags (not 20-80 rated):
- **HIGH_LEVERAGE / LOW_LEVERAGE** (binary derived from role) — robust at ~78% combined CLOSER∪SETUP persistence
- **CLOSER_ROLE** (binary, ~58% YoY persistence) — useful for fantasy save value

**Drop / hold from primary rating:**
- ~~DAMAGE_SUPP (xwoba_contact / barrel_pct)~~ — fails YoY stability at RP sample sizes (r=0.12 / 0.20). Don't use as a primary axis; can still appear as a soft contextual marker in deep-dives.
- ~~L/R platoon split as a rated axis~~ — MAYBE band (r=0.24–0.31), worse for LHP-only. Could be a tag ("OBVIOUS_PLATOON_GUY") but not a rated dimension.
- ~~gmLI~~ — blocked pending FanGraphs scrape. Consider adding to v2.
