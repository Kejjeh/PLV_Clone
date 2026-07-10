---
signal: stuff_plus_asof (RP)
formula: FanGraphs Stuff+ (sp_stuff, type=36-family field returned on the type=8 payload) computed over the AS-OF window {Y}-03-01 .. {Y}-06-15 (FG leaders date-range API, month=1000, qual=0, pageitems=3000 so the reliever tail is NOT truncated), joined by mlb_id == pitcher onto the rolling_relievers_2018_2026 row at the split_day whose cutoff_date is nearest June 15 per year (2021:72, 2022:72, 2023:79, 2024:79, 2025:79 — all cutoffs within 3 days of June 15). FG rows restricted to relievers within the window (gs == 0 OR gs/g < 0.4).
outcome: fp_year_total (rprs2 production TARGET), scored via the production rprs2.cross_year_eval (RidgeCV LOO cross-year), rows restricted to the June-15-aligned split_day and years 2021-2025, g_to >= 5 (production EVAL_G_MIN)
expected_sign: +
theory: Stuff+ measures per-pitch quality, stabilizes fast, and already PASSED Rule-9 integration for the SP model (stuff_vs_rp3 2026-06-06, +0.0095 vs full baseline); rprs2's per-appearance pitching quality is essentially unpredicted (forward r 0.02-0.06 per the forward-error analysis), so an external stuff signal is the best candidate to fill that hole.
production_target: rprs2
framing: in-season -> ros @ the ~June-15 split_day ONLY (single-split validation — the FG as-of window is fixed at June 15, so only the split closest to it is honest; rprs2 trains at many split_days, and this run says NOTHING about other splits)
holdout_years: [2024, 2025]
training_years: [2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_rp_stuff_plus_asof.py
date: 2026-07-09
verdict: PASS (marginal — lift +0.0059 vs gate +0.005; holdout +0.0014; 2025 lift +0.0002)
purpose: rprs2 forward-error analysis shows per-appearance pitching quality unpredicted; Stuff+ is the strongest validated external stuff signal (already in-family for rp3).
---

# stuff_plus_asof → rprs2 (RP) — pre-registration

## Design (locked before results)

- **Baseline (Rule 9):** the FULL production `FEATS_RPRS2` list (BASE_FEATS +
  NEW_FEATS, 27 features) from `src/plv_clone/models/xfp/rprs2.py`, evaluated
  with the production `cross_year_eval` on the identical row population as the
  candidate run (rows pre-filtered to `stuff_plus_asof` non-null so baseline and
  candidate see the same sample).
- **Candidate:** `FEATS_RPRS2 + ['stuff_plus_asof']`.
- **Population:** `rolling_relievers_2018_2026.csv` rows at the June-15-aligned
  split_day per year, years 2021-2025, `g_to >= 5` (production EVAL_G_MIN),
  dropna over feats + target (production behavior).
- **Gates:**
  1. cross_year_r lift >= **+0.005** vs the FULL rprs2 baseline;
  2. per-year sign consistency **5/5** (see Rule 5 note below);
  3. holdout (2024, 2025) mean lift **positive**.
- **Scoring primitive:** `scripts/xfp/lib/rule9.rule9_lift`.

## Rule 5 sample-size honesty note (pre-acknowledged)

FanGraphs Stuff+ begins 2020; 2020 is COVID-excluded by construction; the rprs2
TRAIN_YEARS year 2019 has no Stuff+. That leaves EXACTLY **5 usable outcome
years (2021-2025)** — this meets the 5-year minimum EXACTLY, with zero slack.
Therefore the sign-consistency gate is **5/5** (a single wrong-sign year is a
REJECT, no "5 of 7" cushion exists). Stated before running.

## Known framing caveats (pre-acknowledged)

- FG window end is fixed at June 15; substrate cutoff_dates differ by up to 3
  days (2021: 06-12, 2022: 06-18, 2023: 06-17, 2024: 06-15, 2025: 06-14). The
  candidate can carry up to ~3 days of information the substrate row lacks (or
  vice versa) — small, symmetric across years, disclosed.
- Single-split validation: a PASS here licenses ONLY a June-15-split deployment
  claim; wiring into FEATS_RPRS2 (which trains at all split_days) would require
  as-of pulls at every split_day, a separate follow-up.
- The target `fp_year_total` is a FULL-SEASON total that includes the pre-split
  portion (this is the production target; the baseline sees the same leak-free
  to-date features, so the comparison is fair — same convention as every prior
  rprs2 validation).

## Step 2.5 data-coverage pre-check

(Filled after the join, BEFORE any model eval — join rates only, no outcome
contact.)

| year | split_day | substrate rows (g_to>=5) | FG RP rows (0615) | joined stuff+ non-null | join rate |
|---|---|---|---|---|---|
| 2021 | 72 | 318 | 459 | 318 | 100.0% |
| 2022 | 72 | 338 | 474 | 338 | 100.0% |
| 2023 | 79 | 320 | 459 | 320 | 100.0% |
| 2024 | 79 | 307 | 433 | 307 | 100.0% |
| 2025 | 79 | 322 | 476 | 322 | 100.0% |

Coverage: 5/5 years, 100% join by mlbam id (the pageitems=3000 pull fixed the
old 500-row cap that truncated the reliever tail). Step 2.5 CLEAR — proceeded.

## Results (appended AFTER the run, 2026-07-09)

Eval population after dropna(27 feats + candidate + target): **1,202 rows**
(2021: 243, 2022: 255, 2023: 227, 2024: 237, 2025: 240).

| year | baseline r (FEATS_RPRS2) | +stuff_plus_asof r | Δr |
|---|---|---|---|
| 2021 | 0.7995 | 0.8098 | **+0.0103** |
| 2022 | 0.8103 | 0.8221 | **+0.0118** |
| 2023 | 0.8473 | 0.8503 | **+0.0030** |
| 2024 | 0.8221 | 0.8247 | **+0.0026** |
| 2025 | 0.8225 | 0.8227 | **+0.0002** |
| **pooled** | **0.8188** | **0.8247** | **+0.0059** |

Gates:
1. cross_year_r lift **+0.0059 >= +0.005 — PASS** (thin margin: 0.0009 above gate)
2. sign consistency **5/5 — PASS** (but 2025 is +0.0002, effectively zero)
3. holdout (2024, 2025) mean lift **+0.0014 > 0 — PASS** (thin)

Diagnostics (context, not gates):
- raw r(stuff_plus_asof, fp_year_total) = **+0.4607** (p=3e-64, n=1202)
- partial r over ALL 27 production feats = **+0.1763** (p=8e-10) — the signal is
  genuinely NOT redundant with the production feature set
- top collinearity: fp_with_role_to 0.41, k_pct_to 0.40, xwoba_per_pa_to 0.39,
  sv_plus_hld_to 0.39, c_plus_swstr_to 0.37 — moderate, not absorbing

### Verdict: PASS (marginal)

All three pre-registered gates pass, so per the locked design this is a PASS —
but an honest read: the pooled lift clears the gate by 0.0009, the per-year
lifts decline monotonically 2021→2025 (+0.0103 → +0.0002), and the holdout lift
is +0.0014. The strong partial r (+0.176) says the information is real; the
small Ridge-level lift says the baseline's outcome-derived features already
carry most of it at this split. Comparable to the SP result (stuff_vs_rp3
+0.0095) but weaker and with a worrying recent-year fade.

### Deployment caveats (blocking items before FEATS_RPRS2 wiring)

1. **Single-split license only.** This validates a ~June-15-split deployment.
   FEATS_RPRS2 trains at ALL split_days (30..~180); wiring the feature in
   requires as-of Stuff+ at every split_day (per-date FG pulls), a separate
   data-engineering job + re-validation through rprs2's own gates
   (delta_overall >= 0, role-change subset unharmed).
2. **Recent-year fade.** 2024 +0.0026 / 2025 +0.0002 — the lift is carried by
   2021-2022. If Stuff+-like information is increasingly priced into RP usage
   (roles, leverage) the marginal value may be structurally shrinking.
3. **FG scrape dependency.** Same brittleness flagged in the SP integration
   (Cloudflare; undetected-chromedriver only, plain requests 403 as of
   2026-07-09).
4. **Not added to the README index or FEATS lists here** — this run only ADDs
   files; index row + any promotion decision belong to the owner session.
