---
signal: velo_decline_flag
formula: Reframe velocity from a (rejected) linear mean-FP term into the two roles it
  actually fills — a LEADING year-over-year DECLINE flag and a BUST-risk tilt. Three
  as-of velo features built from the leakage-safe rolling panel:
    velo_yoy   = avg_velo_to (current, cumulative-to-cutoff) - prior-year SEASON-END velo
    velo_intra = avg_velo_last21 - EARLY-season velo (first split row, clean baseline)
    velo_pers  = personal z of current velo vs the pitcher's own multi-year mean/sd
  Avoid-oriented: POSITIVE = more velo loss = hypothesized worse forward FP / higher bust.
outcome: ros_fp_per_start (BrownU SP scoring) over forward ros_gs starts (MEAN), AND
  forward BUST = bottom-tercile ros_fp_per_start within each as-of cell (DOWNSIDE).
expected_sign: velo loss -> lower forward mean FP and higher bust rate
theory: Velocity decline is the canonical aging/injury signal, but it acts on the
  DOWNSIDE (blow-up starts) more than the mean, and most of its mean-effect already
  flows through K%/whiff (velo loss -> fewer Ks). The as-built version
  (stuff_translation_gap, declining-velo bucket) rejected it because it asked the wrong
  question the wrong way.
production_target: supplementary FLAG/lens on sp_decline_model.py (NOT an additive point
  term; NOT a reweight of the validated whiff/K-level headline) per lens_value_add_2026-06-11.
framing: in-season -> ros
holdout_years: expanding-window OOS (train years < test year), test 2019,2021-2025
training_years: 2018,2019,2021,2022,2023,2024,2025
validation_script: scripts/_oneoff/velo_signal_study.py
date: 2026-06-13
verdict: PASS as a DECLINE FLAG + BUST tilt (NOT as a linear mean-FP term — that stays REJECTED)
purpose: Turn velo from "noise (as built — proxy-grade)" into a usable signal by fixing
  three construction flaws and reframing to the role it actually fills.
---

## Why the as-built velo signal was rejected (and it was right to be — for that question)

`stuff_translation_gap_sp_2026-06-13` bucket (f) declining-velo: ΔR² **−0.012**, rho
+0.030 → NOISE. Three structural flaws made velo look like noise:

1. **Contaminated delta.** `velo_delta = avg_velo_last21 − avg_velo_to`, but `*_to`
   *contains* `last21` → a delta of a window against its own superset, on tiny samples
   → regressed toward zero by construction.
2. **Range-restricted cohort.** Tested ONLY inside the top-quartile high-Stuff cohort,
   which is selected *partly on velo*. Restriction of range crushes velo's variance
   exactly where it was measured.
3. **Wrong target + linear z.** Within-cell z-score of the delta vs the forward MEAN.
   Velo's effect is (a) a THRESHOLD (only real drops bite) and (b) on the DOWNSIDE
   (bust risk), neither of which a linear-z-on-the-mean can see.

## The fix — three clean features, tested on the FULL panel and on the downside

Panel: `rolling_pitchers_2018_2026.csv`, SP-weeks **19,797** (gs_to≥5, ros_gs≥3).
New, uncontaminated baselines the panel never used:
- **velo_yoy** vs PRIOR-YEAR season-end velo (real aging/injury, n=11,633 linked)
- **velo_intra** vs EARLY-season velo (first split, clean within-season base)
- **velo_pers** = personal z vs the pitcher's own multi-year velo distribution

### 1. Threshold gradient on the MEAN (full panel, monotonic)
The linear z hid a clean monotonic gradient:

| YoY velo Δ vs prior season | n | forward FP/start |
|---|---|---|
| ≥ +0.5 mph (gaining) | 2,565 | **11.32** |
| −0.5 .. +0.5 | 4,363 | 10.77 |
| −1.0 .. −0.5 | 2,160 | 10.25 |
| −1.5 .. −1.0 | 1,479 | 9.72 |
| ≤ −1.5 mph (real loss) | 1,066 | **9.44** |

**−1.9 FP/start** across the velo-change range, monotonic. A pitcher down ≥1.5 mph
vs last year averages ~0.9 FP below the panel mean (10.33) and ~1.9 below an arm
adding velo. Legible and actionable as a FLAG; a linear term dilutes it.

### 2. Velo is a BUST signal, not a mean signal (the real home)
Forward bust = bottom-tercile FP within as-of cell. Quintile bust rates:

| feature | bust% Q1 | bust% Q5 | Δbust | rho | p |
|---|---|---|---|---|---|
| personal velo z (full panel) | 24.5% | **41.7%** | +0.172 | +0.135 | 0 |
| velo level z (full panel) | 24.1% | 43.3% | +0.192 | +0.132 | 0 |
| YoY velo (full panel) | 26.1% | 39.7% | +0.135 | +0.116 | 0 |
| **velo level z (HIGH-Stuff cohort)** | 20.9% | **43.2%** | **+0.224** | +0.168 | 0 |

**OOS bust AUC (expanding window):**
- Full panel: stuff_proxy 0.641 → +velo (pers+yoy) **0.654**.
- **HIGH-Stuff cohort: stuff_proxy alone 0.519 (≈ useless) → velo level 0.561.**
  Among good-stuff arms, stuff *can't* tell you who busts — **velo can, and beats it.**
  This is velo's unique contribution: it sees the downside exactly where the
  mean/stuff models are blind.

### 3. Rule-9 honesty — what velo does NOT do
Over the STRONG production baselines, the mean-FP increment is marginal (as expected,
since velo loss mostly flows through K%):
- Over floor baseline (K−BB% + barrel%, AUC 0.725): +velo → 0.732 (**+0.007**); ~0 within
  high-Stuff.
- Over decline baseline (whiff/K level + to-date FP, R²=0.245): YoY velo ΔR² **+0.006**,
  partial-r **−0.090** (n=11,633); personal-z ΔR² +0.009.

So velo is **NOT** a free additive mean-lift term (that would violate
`lens_value_add_2026-06-11` / Don't-do #13). Its partial-r −0.09 over the decline
baseline is real and **non-redundant** (a *change* signal, orthogonal to the *level*
the model already weights), which is exactly the bar for a supplementary LENS/FLAG.

## Convergence-curve leakage check (clean)
Per-split rho(personal velo z, forward bust): early(≤79) +0.121 vs late(≥135) +0.137.
Not flat-identical-across-splits (no leakage smoking gun); features are strictly as-of,
target strictly forward.

## In-season drops: rescued by the right CUTOFF (sample size + date)

The decline backtest REJECTED the within-season velo delta — correctly, *as it was
pooled*. Conditioning reveals it was a sample-size artifact, not a dead signal.
Construct = L21 velo − pitcher's own 2026 SEASON-PEAK cumulative velo (avoids the
warmup confound of "vs early-season" and the self-contamination of "vs to-date").
partial-r vs forward FP, controlling for whiff/K level + to-date FP:

**By L21 sample (batters faced):**

| L21 window | partial-r | bust% @drop≥1.5 vs @flat |
|---|---|---|
| < 25 BF (~1 start) | **−0.002 (NOISE)** | 38.5 vs 41.5 *(inverted)* |
| 25–50 BF | +0.055 | 43.6 vs 42.6 |
| 50–75 BF | +0.037 | 42.2 vs 35.2 |
| **≥ 75 BF (≥3 starts)** | **+0.075** | **37.0 vs 27.5 (+9.5pp)** |

Pooling the 1-start blips (zero signal, inverted bust gap) is exactly what made the
original rejection look right. **Gated at ≥75 BF, the in-season drop is a PEER of the
YoY signal** (partial-r +0.075 vs −0.090) with a clean +9.5pp bust gap.

**By split-day cutoff (when in the season the read is taken):**

| window | partial-r |
|---|---|
| early (d30–51) | +0.073 |
| **early-mid (Jun, d58–86)** | **+0.088** |
| mid (Jul, d93–128) | +0.064 |
| late (Aug+, d135+) | +0.037 |

Strongest before ~August (a drop needs RoS runway to manifest); decays late — the
expected as-of pattern, not leakage. Combined (≥75 BF AND d≥93): partial-r +0.073,
≤−1.5 drop → 10.16 FP / 35.4% bust vs flat 11.32 FP / 27.5%.

**Why keep BOTH flags:** YoY is the stronger, full-season-baseline construct but only
covers ~59% of pitcher-weeks (needs a prior-season velo). The gated in-season drop
covers everyone with ≥3 recent starts — the coverage complement for rookies / post-TJ
returners (no 2025 velo) and for a fresh dip the YoY line hasn't absorbed yet.

## Deeper cutoff sweeps (six dimensions)

Run on the gated (≥75 BF L21) in-season-drop cohort unless noted; partial-r controls
for whiff/K level + to-date FP.

**(A) BF-gate sweep — signal climbs monotonically with sample.**

| gate | partial-r | n |
|---|---|---|
| ≥40 BF | +0.060 | 17,462 |
| ≥75 BF | +0.075 | 10,845 |
| ≥80 BF | +0.084 | 9,263 |
| ≥100 BF | +0.102 | 2,646 |
| ≥110 BF | +0.144 | 277 |

More sample = cleaner read. **80 BF is the better signal/coverage knee** (+0.084 at
n=9,263); above 100 the n collapses. Production gate set to **80**.

**(B) Magnitude — bust STEPS at any real drop; FP severity is GRADED.**

| drop off peak | fwd FP | bust% |
|---|---|---|
| −0.4 .. +0.4 (flat) | 11.11 | 27.3 |
| −0.7 .. −0.4 | 10.52 | 33.6 |
| −1.0 .. −0.7 | 10.31 | 35.9 |
| −1.5 .. −1.0 | 10.22 | 34.5 |
| −2.0 .. −1.5 | 10.06 | 35.6 |
| ≤ −2.0 | 9.67 | 39.4 |

Bust jumps ~27%→34% the moment a real drop appears (~−0.5) and plateaus; forward FP
keeps sliding to −2 mph. So the soft flag fires at **−0.5** (bust onset), `▼▼` at −1.5
(FP-severity tail).

**(C) Relative % vs absolute mph — no difference** (+0.076 vs +0.075). Normalizing the
drop by the pitcher's velo level adds nothing; keep absolute mph (interpretable).

**(D) Pitcher-type interaction — velo loss bites HARDEST for LOW-velo arms.**

| velo tertile | partial-r | bust% @drop≥1 vs flat |
|---|---|---|
| **low-velo** | **+0.107** | **46.4 vs 33.1 (+13.3pp)** |
| mid | +0.060 | 34.7 vs 28.9 (+5.8) |
| high-velo | +0.062 | 25.4 vs 20.0 (+5.4) |

Counter-intuitive but mechanistic: a finesse / sinker arm has **no margin** — losing
the little velo it has collapses it, while a 97→96 fireballer still plays. The drop
flag is **escalated for sub-median-velo arms**.

**(E) Double-confirmation — the strongest cutoff of all.** YoY drop AND in-season drop
(both ≤ −0.7), gated cohort:

| | fwd FP | bust% |
|---|---|---|
| neither | 11.56 | 23.1 |
| in-season only | 10.97 | 27.0 |
| YoY only | 10.52 | 31.9 |
| **BOTH** | **9.02** | **49.5** |

Double-confirmed velo decline is a **coin-flip bust** (49.5%, 2.1× the no-drop rate)
and −2.5 FP/start — far beyond either flag alone. This is the **SEVERE fade tier**.

**(F) Persistence adds nothing over the gate.** Drop present at this split AND the
prior split (35.2% bust) vs a one-split flicker (34.4%) — essentially identical. The
BF gate already removes the noise a persistence rule would target; no 2-split
requirement needed (keeps the flag simple + timely).

## Deepest cuts — mechanism, normalization, interaction, multi-year

**(G) Velo drop is ORTHOGONAL to whiffs** (gated ≥80 BF). Bust rate by velo×whiff
quadrant — the "velo only matters if it erodes whiffs" hypothesis is REJECTED:

| | fwd FP | bust% |
|---|---|---|
| velo↓ & whiff↓ | 10.23 | 33.9 |
| **velo↓ & whiff held** | 10.26 | **35.6** |
| velo steady & whiff↓ | 11.09 | 26.6 |
| velo steady & whiff held | 11.07 | 27.5 |

Velo loss predicts bust **whether or not whiffs fall** — it carries information the
whiff/K lens doesn't (fatigue/injury surfacing in contact/command/HR, not Ks). This
is the mechanistic proof of non-redundancy behind the partial-r.

**(H) Normalizing the drop by the pitcher's own velo VOLATILITY: null** (+0.084 raw =
+0.084 per-sd). Third normalization idea rejected (after relative-% and warmup-base).
Raw mph off season-peak is the right construct.

**(I) Velo drop AMPLIFIES the propped-FP (decline-gap) signal.**

| cohort | partial-r | bust% @drop vs flat |
|---|---|---|
| propped (gap>0) | +0.100 | 36.7 vs 27.3 |
| not propped (gap≤0) | +0.061 | 34.2 vs 27.6 |

Velo loss and the core decline read reinforce — the velo flag is most valuable on the
DECLINE-RISK board (gap>0), exactly where it's displayed.

**(J) Absolute velo LEVEL: strong bust gradient with a soft floor ~90 mph** — but this
is the *level* lens (already weighted 0.20), not the drop:

| L21 velo | fwd FP | bust% |
|---|---|---|
| <90 | 10.24 | 33.2 |
| 90–93 | 12.23 | 20.7 |
| 93–95 | 14.57 | 8.4 |

The cliff sits at ~90 — consistent with the LOW-VELO tilt (D): sub-floor arms have no
margin.

**(K) Multi-year decline is the STRONGEST velo construct.**

| construct | partial-r | n |
|---|---|---|
| 1-year velo Δ | +0.101 | 10,579 |
| **2-year velo Δ** | **+0.175** | 7,070 |

A sustained two-season downtrend (vs 2-years-ago season-end) nearly doubles the
single-year signal — it filters single-year blips and captures genuine erosion/aging.
Cost: needs two prior seasons (lower coverage) and updates only yearly. Wired as the
`v2y` sustained-fade flag (vs 2024 season-end), the highest-conviction velo tier.

## Pitch-level dimensions tested and REJECTED (agent fan-out, pitch-level Statcast 2021-25)

Three pitch-level dimensions were evaluated against the same bar (partial-r over
whiff/K level + to-date FP, AND marginal over the overall-velo YoY delta). All three
are NULL once overall velo is controlled — confirming the simple all-pitch velo
constructs (vYoY/vIn/v2y) already capture the decline signal. Do NOT re-explore these
without a new construct.

| dimension | verdict | detail | report |
|---|---|---|---|
| per-pitch-type velo decline | **NULL** | no pitch-type cut beats overall velo (+0.104) at full coverage; SL/SI YoY look better only on ~½ coverage (self-selected subsets) | `velo_pitchtype_2026-06-13.md` |
| platoon (split / interaction) | **REJECT** | platoon split alone ≈0 (+0.009, p=0.66); signal lives in overall velo | `velo_platoon_2026-06-13.md` |
| TTO / in-game velo fade | **REJECT** | in-game fade ≈0 and wrong-signed; TTO3 wOBA penalty +0.063 → +0.043 over velo, never near bar; no fade×velo interaction | `velo_tto_2026-06-13.md` |

**Two honest near-misses (documented, not wired — candidates for a future
validate-feature run, NOT headline terms):**
- **FB-vs-offspeed velo SEPARATION erosion** — the only genuinely orthogonal construct
  (marginal partial-r +0.072 over overall velo at full n=2,484), but raw partial-r
  (+0.057) is below overall velo. A potential secondary complement only.
- **Platoon-vulnerability as a conviction amplifier** — velo-drop partial-r rises
  across opposite-hand-vulnerability tertiles (+0.106 → +0.128 → **+0.205**), product
  term NS (p=0.19). Display-only at most. **Converges with the LOW-VELO tilt (D):**
  low-margin / platoon-vulnerable arms crater hardest when velo goes.

## Production decision
Wire a **YoY velo-loss FLAG** into `sp_decline_model.py` (the "catch a Framber before the
crater" board) as a supplementary tag + column — NOT a reweight of the validated whiff/K
LEVEL headline. It is distinct from both things that model already settled:
- velo **LEVEL** (already in, light W=0.20, partial-r +0.16) — a static "how hard now";
- within-season L21 **delta** (REJECTED as noise) — the contaminated construct.
YoY velo loss (vs prior season-end) is the missing, validated, leading construct: it
tells you the arm is *fading vs what it used to be* before the K%/results fully crater.

## Practical rule
On the decline board, a `velo▼` flag (≥0.7 mph below 2025 season-end, ⚠ at ≥1.5 mph)
RAISES decline conviction and is a bust-risk tilt for /sp-floor — especially for a
high-Stuff arm whose stuff grade otherwise looks fine. It does NOT move the headline
projection (still whiff/K level). Velo gaining (≥+0.5) is a mild RISING tailwind.
