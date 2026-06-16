---
signal: bat_tracking_fp_family
formula: see per-signal table in body (6 candidates from 3 Savant bat-tracking leaderboards)
outcome: rh3/rp3 RoS FP (in-season-to-date -> rest-of-season), leave-one-year-out across TRAIN_YEARS
expected_sign: see per-signal table
theory: Savant bat-tracking (bat speed / blast / swords / attack-angle / swing-timing) exposes swing mechanics that should add orthogonal signal to outcome-based rh3/rp3 features.
production_target: research-only
framing: both (researched as year-over-year forward; production needs in-season -> ros)
holdout_years: [2026]
training_years: [2023, 2024, 2025] only — 3 of 7 TRAIN_YEARS have source data; see Rule 5 honesty note
validation_script: NOT WRITTEN — halts at Step 2.5 (sample-size pre-check)
date: 2026-06-16
verdict: REJECTED
purpose: User asked to validate all six bat-tracking candidates surfaced in the 2026-06-16 research session (handoff_bat_tracking_research_2026-06-16.md). Step 2.5 pre-check decides them before any script is written.
---

## Candidates under test (from 2026-06-16 research session)

Exploratory forward (T->T+1) correlations from the research session. These are
**context only — NOT validation** (computed on 2-3 cohorts; see honesty note).

| # | Signal | Source leaderboard | Target | Exploratory fwd r | Notes |
|---|---|---|---|---|---|
| 1 | `blast_per_swing` induced | bat-tracking main (pitcher) | rp3 | **-0.374*** | Strongest SP bat-tracking signal; Q1 vs Q5 = +2.06 FP/start |
| 2 | `swords_FF` induced | bat-tracking main, pitchType=FF (pitcher) | rp3 | +0.245 | n~200; fastball chase inducement |
| 3 | `ideal_attack_angle_rate` induced | swing-path-attack-angle (pitcher) | rp3 | -0.185** | attack-angle leaderboard |
| 4 | `blast_per_swing` | bat-tracking main (batter) | rh3 | +0.220*** | year-to-year stability 0.78 |
| 5 | `whiff_rate_FF` | swing-timing-miss-distance, split by pitch (batter) | rh3 | -0.167*** | pitch-type whiff |
| 6 | `swords_rate` | bat-tracking main (batter) | rh3 | -0.114** | K%-cousin; "BrownU paradox" (K penalty small) |

Production baselines that each candidate must beat (Rule 9, the +0.005 cross-year-r gate):
- **rp3** (#1-3): 24 features incl. `avg_velo_to`, `swstr_pct_to_sh`, `c_plus_swstr_to_sh`,
  `xwoba_per_pa_to_sh`, the `delta_velo/swstr/k_pct/bb_pct/chase/zone` drift layer, `ros_opp_xwoba_weighted`.
- **rh3** (#4-6): 21 features incl. `barrel_pct_to_sh`, `hard_hit_pct_to_sh`, `iso_to_sh`,
  `whiff_pct_to_sh`, `contact_pct_to_sh`, `swstr_pct_to_sh`, `k_pct_to_sh`, `xwoba_per_pa_to_sh`.

---

## Rule 5 sample-size honesty note (pre-acknowledged, halts at Step 2.5)

Statcast bat-tracking data exists for **2023, 2024, 2025, 2026** (verified this
session — see Data coverage audit below; **2023 is genuine**, an update to the
2026-05-24 `bat_speed_level_prior` note which assumed 2023 absent).

`cross_year_eval` (both rh3 and rp3) trains leave-one-year-out across
`TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]` (7 years; 2020 dropped)
and calls `df.dropna(subset=feats + [TARGET])`. A bat-tracking feature is NaN for
2018/2019/2021/2022, so adding it **collapses the usable training set to
2023/2024/2025 = 3 of 7 years.**

| TRAIN_YEAR | bat-tracking present? | counts toward 5/7? |
|---|---|---|
| 2018 | No | No |
| 2019 | No | No |
| 2021 | No | No |
| 2022 | No | No |
| 2023 | Yes | Yes |
| 2024 | Yes | Yes |
| 2025 | Yes | Yes |

Rule 2(b) requires sign consistency across **>= 5 of 7** training years. With
3 usable years this **cannot** clear the gate regardless of within-year effect
size. Per-year sample sizes are fine (211-226 hitters/SPs per year, >> Rule 5's
30-per-year floor) — the binding constraint is the **number of years**, not n.

**Both framings fail the same way:**
- *Year-over-year forward* (how the session researched it): usable (prior, outcome)
  pairs are (2023,2024), (2024,2025), and (2025,2026-partial) = 2 full + 1 partial.
- *In-season -> RoS* (the actual production framing): only 2023/2024/2025 seasons
  carry bat-tracking, and the saved panels are **full-season aggregates, not
  split-day to-date** — so they cannot even be computed as-of the cutoff without a
  fresh date-ranged pull (a Rule 8 framing gap on top of the sample-size gap).

Expected outcome: **REJECTION at Step 2.5.** No validation script written.

---

## Data coverage audit (Step 2.5)

Files: `data/research/bat_tracking_all_2023_2026.csv` (3478 rows; 2023:924 /
2024:846 / 2025:864 / 2026:844), `data/research/swing_timing_miss_dist_2023_2026.csv`
(4592 rows). FP outcome panels go back to 2015 (not the constraint).

**Year-bounds probe (`_probe_year_bounds.py`, live Savant pull 2026-06-16):**
The bat-tracking leaderboard was queried for **2019-2026**. Result: 2019/2020/
2021/2022 return **0 rows**; only **2023 (221), 2024 (214), 2025 (226),
2026 (211 partial)** serve data. Hawk-Eye hardware predates 2023 but Savant does
not expose bat-tracking before it. The empty (not defaulted) responses also prove
the `seasonStart`/`seasonEnd` param is honored — a ignored param would return
2026's 211 rows for every year, not 0. **2023 is the hard floor.** This is the
binding fact: 3 complete training seasons (2023-2025), 2026 partial.

**Integrity checks run this session (scripts in `scripts/xfp/research/`):**
1. `_check_year_integrity.py` — years are genuinely distinct, NOT a duplicated
   single-year pull: 0% identical rows across every adjacent-year pair; per-player
   values differ (id 519317 bat speed 80.99 -> 81.22) with cross-year r ~0.91-0.95
   (stable skill, not a copy). Resolves obs #1870 ("year params ineffective") — that
   was an early probe using wrong param names (`season[]`/`year`), which Savant
   ignores and defaults to the current season (2026). The saved panel uses the
   working `seasonStart`/`seasonEnd` params (obs #1882/#1886).
2. `_check_2023_legit.py` — **2023 bat-tracking is real, not relabeled 2024.**
   54 players appear ONLY in 2023 (Miguel Cabrera, Brandon Belt, Jose Abreu, Mike
   Moustakas, Whit Merrifield...). Cabrera retired after 2023 and cannot appear in
   2024 data, so Savant genuinely backfilled 2023 from Hawk-Eye. This buys one extra
   training year vs the prior precedent's assumption.

---

## Verdict: REJECTED — sample-size deferred

Same root cause as `bat_speed_delta_prior_year` (2026-05-16),
`bat_speed_level_prior` (2026-05-24), `squared_up_rate_delta_prior_year`
(2026-05-16), and `attack_angle_consistency_delta` (2026-05-16). The
"Recently closed dead ends" table already records: *bat speed features -> rh3
BLOCKED, 2024+ only, need 2028+.*

### Earliest viable re-validation (updated by the 2023 finding)

- **In-season -> RoS (production-relevant):** viable after the **2027 season**
  (2027-28 offseason). By then 5 complete seasons carry bat-tracking
  (2023, 2024, 2025, 2026, 2027). **Requires** capturing *split-day / to-date*
  bat-tracking each season — a date-ranged Savant pull, not the current
  full-season snapshot (infra task below).
- **Year-over-year forward (draft/offseason):** viable after the **2028 season**
  (5 forward pairs: 2023->24 ... 2027->28).

The prior precedent estimated 2028+; confirming 2023 availability this session
pulls the in-season window in to **2027**.

### Re-test priority (when the data wall clears)

1. **`blast_per_swing` induced (rp3)** — by far the strongest raw signal
   (r=-0.374; +2.06 FP/start Q1-Q5). The one most worth a real Rule 9 test.
2. `blast_per_swing` (rh3) — r=+0.220, stable.
3. The remaining four are lower-priority: `whiff_rate_FF`, `swords_rate`,
   `swords_FF` induced, `ideal_attack_angle_rate` induced.

### Secondary blocker to expect even in 2027/2028 (Rule 9)

Sample size is the immediate blocker; incremental lift over the saturated
baselines is the likely *ultimate* decider. The rp3/rh3 baselines already carry
the downstream outcomes of swing mechanics:
- SP blast-allowed is collinear with `avg_velo_to` + `c_plus_swstr_to_sh` +
  the `delta_*` drift layer (cf. `avg_pfxz_to` REJECTED -0.0007;
  `pitch_shape_early_warning_sweep` REJECTED — delta layer absorbs pitch-shape).
- Hitter `blast_per_swing` is collinear with `barrel_pct_to_sh` /
  `hard_hit_pct_to_sh` / `iso_to_sh`.
- `whiff_rate_FF` is a slice of `whiff_pct_to_sh` already in rh3 (and its |r| is
  *lower* than aggregate whiff). NOTE: this one could be reconstructed from
  2015+ raw Statcast pitch data (dodging the sample-size wall) — but that makes
  the redundancy with existing aggregate-whiff features worse, so it is not worth
  the re-pull.
- `swords_rate` is a K%-cousin; the session's own "BrownU paradox" shows the K
  penalty is small in points scoring.

So the realistic prior even post-2027 is MARGINAL/REJECTED for most of the six,
with `blast_per_swing` induced (rp3) the best shot.

### What would unblock / prepare (infra, cheap to do now)

- Keep capturing bat-tracking every season (already flowing into
  `bat_tracking_all_*.csv`).
- For the production-relevant in-season framing, add a **date-ranged (to-date)**
  bat-tracking pull keyed `(player, year, split_day)` so the 2027 re-validation is
  turnkey rather than blocked on a framing gap. Savant supports date filtering on
  these leaderboards.

**Not promoted to any FEATS list. Stays research-only.** The exploratory
correlations are preserved here (and in the handoff) as context for the 2027/2028
re-test; they are NOT a validated lift.
