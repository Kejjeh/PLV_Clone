# Hitter sub-domain validation — empirical YoY stability tests

**Date:** 2026-05-30
**Purpose:** Apply the same RP/SP archetype YoY-stability discipline to the hitter archetype dataset. Before committing the hitter archetype build to its current sub-domain set, validate that each one behaves as signal (not noise) for batters with PA ≥ 250.

**Cohort floor:** `PA >= 250` in BOTH year T and year T+1 (matches `PA_FLOOR_FULL` in `build_hitter_archetypes.py`).

**Years covered:** 2018, 2019, 2021, 2022, 2023, 2024, 2025. Drops:
- **2020** — COVID short season (already excluded in the build script)
- **2026** — in-progress year

**YoY pair pool:** 2018→2019, 2021→2022, 2022→2023, 2023→2024, 2024→2025. `n_pairs = 1,141`.

**Bar (mirrors RP):**
- `r ≥ 0.40` → **KEEP**
- `0.20 ≤ r < 0.40` → MAYBE
- `r < 0.20` → **DROP**

**Validation script:** `scripts/xfp/_research/hitter_subdomain_validation.py`

**Cohort sizes by year (PA ≥ 250):**

| 2018 | 2019 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| 313 | 322 | 312 | 317 | 328 | 325 | 308 |

---

## Headline result

**Every one of the 12 current hitter sub-domains clears the r ≥ 0.40 bar.** No DROP candidates. The hitter dataset is structurally healthier than the RP dataset — hitters get 500–700 PA/year vs RPs at 200–300 BIP/year, so contact-quality estimates stabilize cleanly.

This is the inverse of the RP finding (where DAMAGE_SUPP failed at r=0.12–0.20). For hitters, `CONTACT_QUALITY` (xwoba_on_contact) is rock-solid at **r = +0.75**.

---

## Test A — YoY stability of underlying r_* rate inputs

Output: `HITTER_VALIDATION_A_raw_inputs.csv`

| r_* column         | source rate         | n_pairs | r       | Verdict |
|--------------------|---------------------|---------|---------|---------|
| r_Sprint           | sprint_speed        | 1141    | +0.9493 | **KEEP** (gold standard) |
| r_EV90             | ev90                | 1141    | +0.8923 | **KEEP** |
| r_Contact          | contact_pct         | 1141    | +0.8707 | **KEEP** |
| r_Chase            | chase_pct           | 1141    | +0.8405 | **KEEP** |
| r_OContact         | o_contact_pct       | 1141    | +0.8315 | **KEEP** |
| r_ZContact         | z_contact_pct       | 1141    | +0.8275 | **KEEP** |
| r_K                | k_pct               | 1141    | +0.8187 | **KEEP** |
| r_ZSwing           | z_swing_pct         | 1141    | +0.8094 | **KEEP** |
| r_HardHit          | hard_hit_pct        | 1141    | +0.7916 | **KEEP** |
| r_Barrel           | barrel_pct          | 1141    | +0.7780 | **KEEP** |
| r_SBrate           | sb_per_opp          | 1141    | +0.7654 | **KEEP** |
| r_xCON             | xwoba_on_contact    | 1141    | +0.7397 | **KEEP** |
| r_BB               | bb_pct              | 1141    | +0.7222 | **KEEP** |
| r_SprayEnt         | spray_entropy       | 1141    | +0.6266 | **KEEP** |
| r_PullFB           | pull_fb_pct         | 1141    | +0.5980 | **KEEP** |
| r_HBP              | hbp_pct             | 1141    | +0.5970 | **KEEP** |
| r_HRrate           | hr_per_pa           | 1141    | +0.5837 | **KEEP** |
| r_ISO              | iso                 | 1141    | +0.5783 | **KEEP** |
| r_SweetSpot        | sweet_spot_pct      | 1141    | +0.4580 | **KEEP** |
| r_BABIP            | babip               | 1141    | +0.3881 | MAYBE   |

### Notes
- **r_BABIP is the only sub-bar input (r = +0.39, MAYBE).** This matches sabermetric folklore — BABIP is the noisiest rate stat in baseball. The build script already handles this correctly: `BABIP` only ever enters the rating via the `contact_subtype` shape detector and via the `babip_luck_flag` (HOT/COLD/NORMAL display tag). It is **NOT** an input to any sub-domain composite. The build comment line 348 explicitly calls this out: *"Year-to-year BABIP stability is r~0.39 (mostly noise)."* No action needed.
- **r_Sprint is the gold-standard signal for hitters (r = +0.95)**, matching velocity for SPs (r = +0.93). Sprint speed is essentially a physical attribute, modulo aging.
- **r_EV90 (r = +0.89) is the most stable Statcast hitter metric**, beating barrel% (r = +0.78) and hard-hit% (r = +0.79). The build script's choice to fold EV90 into RAW_POWER is well-supported.

---

## Test B — YoY stability of the 12 sub-domain composites

Output: `HITTER_VALIDATION_B_subdomains.csv`

Each composite is built as the mean of its component within-year z-scores (Pearson is invariant to monotonic within-year rescale, so testing on z-mean is equivalent to testing on the 20-80 mean).

| Sub-domain        | Domain      | Inputs | n_pairs | r       | Verdict |
|-------------------|-------------|--------|---------|---------|---------|
| **SPEED_TOOL**        | SB          | sprint_speed | 1141 | +0.9471 | **KEEP** |
| **Z_CONTACT**         | CONTACT     | z_contact_pct | 1141 | +0.8725 | **KEEP** |
| **RAW_POWER**         | POWER       | hard_hit + barrel + ev90 | 1141 | +0.8652 | **KEEP** |
| **O_CONTACT**         | CONTACT     | o_contact_pct | 1141 | +0.8312 | **KEEP** |
| **K_AVOIDANCE**       | CONTACT     | k_pct | 1141 | +0.8200 | **KEEP** |
| **AGGRESSION**        | DISCIPLINE  | z_swing_pct | 1141 | +0.8162 | **KEEP** |
| **SB_CONVERSION**     | SB          | sb_per_opp | 1141 | +0.7678 | **KEEP** |
| **PATIENCE**          | DISCIPLINE  | bb + chase + hbp | 1141 | +0.7640 | **KEEP** |
| **CONTACT_QUALITY**   | CONTACT     | xwoba_on_contact | 1141 | +0.7549 | **KEEP** |
| **DAMAGE_PROD**       | POWER       | iso + hr_per_pa | 1141 | +0.6172 | **KEEP** |
| **SPRAY_PROFILE**     | CONTACT     | spray_entropy | 1141 | +0.6153 | **KEEP** |
| **LAUNCH_OPTIM**      | POWER       | sweet_spot + pull_fb | 1141 | +0.5358 | **KEEP** |

### Verdict per sub-domain
| Sub-domain | r | Recommendation |
|------------|---|----------------|
| Z_CONTACT | +0.87 | **KEEP** — passes comfortably; semantically distinct from O_CONTACT (Judge profile vs Yandy Diaz profile) |
| O_CONTACT | +0.83 | **KEEP** — see above |
| K_AVOIDANCE | +0.82 | **KEEP** — overlaps r_Contact (r ≈ 0.7 cross-corr in practice) but is the FP-relevant axis (K is the only −1 event for hitters in scoring), so keep both |
| CONTACT_QUALITY | +0.75 | **KEEP** — this is the RP DAMAGE_SUPP analog and it passes cleanly for hitters because PA volume is 2–3× the BIP volume RPs see |
| SPRAY_PROFILE | +0.62 | **KEEP** — spray entropy is genuinely sticky. Alternative single-metric (pull_pct r=0.68, oppo_pct r=0.63) test in C confirms |
| RAW_POWER | +0.87 | **KEEP** — strongest power sub-domain, anchored by EV90 |
| LAUNCH_OPTIM | +0.54 | **KEEP** — weakest sub-domain that passes; sweet_spot_pct (r=0.46) and pull_fb_pct (r=0.60) are both noisier than the rest. Keep but flagged for v2 review |
| DAMAGE_PROD | +0.62 | **KEEP** — ISO and HR/PA each ~0.58, the composite is slightly stickier |
| PATIENCE | +0.76 | **KEEP** — chase + bb both very sticky |
| AGGRESSION | +0.82 | **KEEP** — z_swing is highly stable |
| SPEED_TOOL | +0.95 | **KEEP** — gold standard |
| SB_CONVERSION | +0.77 | **KEEP** — solidly sticky |

---

## Test C — Alternative metrics for the weakest sub-domains

Output: `HITTER_VALIDATION_C_alternatives.csv`

Even though everything passes, we tested alternative formulations of the three weakest sub-domains (LAUNCH_OPTIM, SPRAY_PROFILE, DAMAGE_PROD) and a few reference metrics.

| Metric                          | n_pairs | r       | Verdict | Notes |
|---------------------------------|---------|---------|---------|-------|
| ALT_SPRAY_pull_pct              | 1141    | +0.6816 | KEEP    | Higher r than spray_entropy (+0.62) — simpler too |
| ALT_SPRAY_oppo_pct              | 1141    | +0.6288 | KEEP    | Marginally above current |
| ALT_SPRAY_pull_fb_pct           | 1141    | +0.5980 | KEEP    | Already used in LAUNCH_OPTIM |
| ALT_CONTACT_QUALITY_xwoba_bip   | 1141    | +0.7397 | KEEP    | Same as current xwoba_on_contact |
| ALT_CONTACT_QUALITY_avg_ev      | 1141    | +0.7810 | KEEP    | **Slightly more stable than xwoba_on_contact** |
| ALT_SB_sb_per_pa                | 1141    | +0.7500 | KEEP    | Slightly less stable than current sb_per_opp (+0.77) |
| REF_xwoba_per_pa                | 1141    | +0.6502 | KEEP    | Overall production sanity check |
| REF_fp_per_pa_actual            | 1141    | +0.5137 | KEEP    | FP/PA itself has r=0.51 YoY — the signal-vs-noise frame |
| ALT_LAUNCH_blast_rate           | 0       | n/a     | INSUFFICIENT | Bat-tracking only available 2026 (435 batters); cannot YoY test |
| ALT_LAUNCH_squared_up_rate      | 0       | n/a     | INSUFFICIENT | Same |
| ALT_LAUNCH_avg_swing_speed      | 0       | n/a     | INSUFFICIENT | Same — strongly suspected to be the cleanest LAUNCH_OPTIM signal, test in 2027 |

### Action from Test C
- **SPRAY_PROFILE — consider simplifying to pull_pct in v2** (r=0.68 > current r=0.62). Spray entropy is semantically richer (captures balanced vs lopsided sprays) but pull_pct is the dominant axis. Low priority — both pass.
- **LAUNCH_OPTIM bat-tracking upgrade is BLOCKED until 2027** — same situation as RP gmLI. The cleanest LAUNCH_OPTIM signals (blast_rate, squared_up_rate, avg_swing_speed) only have one year of data. Re-test after 2026 closes.

---

## Comparison vs RP-tested-pattern sub-domains

| Pattern axis | RP equivalent | RP r | Hitter equivalent | Hitter r | Notes |
|--------------|--------------|------|-------------------|----------|-------|
| Damage suppression / contact quality | DAMAGE_SUPP (xwoba_contact) | +0.12 **DROP** | CONTACT_QUALITY (xwoba_on_contact) | +0.75 **KEEP** | Hitters get 5–10× the BIP-per-year RPs do; estimate stabilizes |
| Damage suppression / contact quality (alt) | DAMAGE_SUPP (barrel_pct) | +0.20 MAYBE | RAW_POWER (barrel input) | +0.78 **KEEP** | Same reason |
| K rate | K_RATE (k_pct, reference) | +0.57 | K_AVOIDANCE (k_pct, inverted) | +0.82 | Hitter K rate stabilizes faster than RP K rate |
| Walk avoid / patience | WALK_AVOID (bb_pct) | +0.44 | PATIENCE (bb+chase+hbp) | +0.76 | Hitter discipline is dramatically more stable |
| Velo / sprint | velo_rating | +0.93 | SPEED_TOOL (sprint) | +0.95 | Both are physical-attribute proxies |
| Bulk / volume | ip_per_appearance | +0.47 | (no direct analog) | — | Could test PA/game one day |
| Splits | L/R xwOBA (RP) | +0.25 MAYBE | (not tested) | — | Hitter L/R splits would likely also fail, but no current build uses them |

**Takeaway:** Every "weak axis for RPs" is "strong axis for hitters" because of the PA-volume gap. The RP archetype lives with a 5-axis rating (after DAMAGE_SUPP got dropped); the hitter archetype keeps all 12.

---

## Estimated impact if recommendations applied

**Zero forced changes.** All 12 sub-domains pass the r ≥ 0.40 bar. The hitter archetype dataset is robust.

**Optional v1.1 polish (not required):**
1. Replace `spray_entropy` with `pull_pct` in SPRAY_PROFILE (r 0.62 → 0.68). Marginal; spray_entropy is semantically richer. **Skip unless we revisit the build.**
2. Replace `xwoba_on_contact` with `avg_ev` in CONTACT_QUALITY (r 0.75 → 0.78). Marginal and avg_ev sacrifices the wOBA-event-weighted property. **Skip.**

**Required v2 work (post-2026 season):**
1. Re-test LAUNCH_OPTIM with bat-tracking metrics (blast_rate, squared_up_rate, avg_swing_speed) once we have a second year of bat-tracking data. These almost certainly beat sweet_spot_pct + pull_fb_pct as proxies for swing-quality and would lift LAUNCH_OPTIM from r=0.54 toward the EV90/sprint tier.
2. Re-evaluate if year T+1 = 2026 adds any sub-domain failures (especially after bat-tracking inputs are folded in).

---

## Recommended changes to `build_hitter_archetypes.py`

**None.** The current 12-sub-domain architecture is empirically validated. The build script's existing handling of BABIP (display tag only, never a composite input) correctly anticipated the r ≈ 0.39 finding.

**One documentation update worth making** (optional): add a line in the sub-domain block (~line 275) referencing this validation file so the next reviewer doesn't have to re-derive.

```
# All 12 sub-domains validated YoY r >= 0.40 — see
# scripts/xfp/_research/HITTER_SUBDOMAIN_VALIDATION.md (2026-05-30).
# BABIP intentionally excluded from sub-domain composites (r=0.39 YoY).
```

---

## Files written

- `scripts/xfp/_research/hitter_subdomain_validation.py` — validation script
- `scripts/xfp/_research/HITTER_VALIDATION_A_raw_inputs.csv` — 20 r_* underlying rate columns
- `scripts/xfp/_research/HITTER_VALIDATION_B_subdomains.csv` — 12 sub-domain composites
- `scripts/xfp/_research/HITTER_VALIDATION_C_alternatives.csv` — alternative metric tests
- `scripts/xfp/_research/HITTER_VALIDATION_summary.json` — full bundle for downstream consumers
- `scripts/xfp/_research/HITTER_SUBDOMAIN_VALIDATION.md` — this report
