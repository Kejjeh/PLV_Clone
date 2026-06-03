# Streamer Week-Boom — Re-tested Under Alternative Definitions

Generated 2026-06-03. Source: `data/research/validation_runs/2start_week_panel.csv`
(n=3,186 streamer-tier 2-start weeks) + `_boom_stack_per_start_panel_cache.parquet`
(n=20,352 streamer-tier per-start rows; 954 at stack>=2).

## Question

Original finding (`2start_week_amplification.md`): at streamer tier with
`boom_stack_s1 >= 2`, week-boom rate (sum_FP >= 30) was 19.3% vs 20.0% base —
**no edge**. Hypothesis: the sum>=30 definition is wrong for streamers, who
get rotated through a slot rather than held all week. Re-test with
alternative boom definitions.

## 1. Four boom definitions — streamer tier

| stack_s1 | n     | A: sum>=30 | B: any>=20 | C: sum>=18 | D: min>=5 |
|---|---|---|---|---|---|
| 0 | 1,674 | 0.200 | 0.213 | 0.519 | 0.488 |
| 1 | 1,170 | 0.204 | 0.219 | 0.572 | 0.517 |
| 2 |   290 | 0.193 | 0.214 | 0.521 | 0.479 |
| 3 |    52 | 0.231 | 0.231 | 0.577 | 0.577 |

### Edge (stack_s1>=2) - (stack_s1=0) — pooled (n_stack>=2 = 342)

| Definition | Base (stack=0) | stack>=2 | Edge |
|---|---|---|---|
| A: sum_FP >= 30 (current)   | 0.200 | 0.199 | **-0.07 pp** |
| B: max(FP) >= 20 (any-boom) | 0.213 | 0.216 | **+0.31 pp** |
| C: sum_FP >= 18 (replacement+)| 0.519 | 0.529 | **+1.01 pp** |
| D: min(FP) >= 5 (high-floor)| 0.488 | 0.494 | **+0.61 pp** |

**No definition shows a meaningful streamer edge at stack_s1>=2.** All four
sit within 1 pp of the stack=0 base. The strongest (C, replacement-plus) is
+1 pp on n=342 — well inside noise.

## 2. Year-by-year stability (stack>=2 vs =0, per definition)

| year | n>=2 | A    | B    | C    | D    |
|---|---|---|---|---|---|
| 2018 | 46 | -0.048 | -0.148 | -0.109 | -0.037 |
| 2019 | 54 | -0.063 | -0.040 | -0.063 | -0.108 |
| 2021 | 45 | +0.076 | +0.054 | +0.035 | +0.053 |
| 2022 | 56 | -0.061 | -0.006 | +0.107 | +0.091 |
| 2023 | 42 | -0.011 | +0.039 | +0.113 | +0.048 |
| 2024 | 42 | +0.089 | +0.028 | +0.046 | +0.048 |
| 2025 | 57 | +0.044 | +0.095 | -0.034 | -0.030 |

**Every definition flips sign across years.** No definition is monotonically
positive. Definition B has the cleanest 2023+ trend (+3.9 / +2.8 / +9.5)
but is dragged negative by 2018-2019. No definition survives multi-year
replication at meaningful magnitude.

## 3. Rotating-slot framing — independence check

Per-start streamer boom rates by stack (n_start_total = 20,352):

| stack | n     | P(boom_20) |
|---|---|---|
| 0 | 15,848 | 0.101 |
| 1 |  3,550 | 0.122 |
| 2 |    954 | 0.149 |

For a streamer rotating slot picking **two independent stack>=2 streamers
per week** (Holmes Mon / Rogers Wed pattern):

| Outcome | Independent prediction | Bootstrap (10k pairs, no-replacement) | Same-SP stack_s1>=2 hold |
|---|---|---|---|
| any >=20 | 1 - 0.851^2 = 0.276 | **0.266** | 0.216 |
| sum >=30 | n/a (joint dist needed) | **0.222** | 0.199 |
| sum >=18 | n/a | **0.544** | 0.529 |
| mean sum | n/a | 18.98 | 18.23 |

**Independence holds (bootstrap matches the 1-(1-p)^2 prediction within
1 pp).** No hidden correlation. The rotating slot DOES beat same-SP-hold
by ~2-5 pp across definitions, but only by the amount predicted from the
single per-start stack>=2 lift (+5 pp at the per-start level).

**The win is just per-start stack picking, not a week-boom amplification.**
Streamer per-start stack>=2 is a +5 pp signal (10.1% → 14.9%); pick two of
them and you get the expected +5 pp single-game lift, no compounding bonus.

## 4. Per-component lifts (streamer week-boom)

Conditioning on individual flags at start 1 (n_streamer = 3,186):

| Flag                | n_on | A edge | B edge | C edge | D edge |
|---|---|---|---|---|---|
| flag_skill_spike_s1 |  256 | **+3.18 pp** | **+4.16 pp** | +1.65 pp | **+3.47 pp** |
| flag_recform_hot_s1 |  595 | +0.27 pp | -0.68 pp | -0.42 pp | -0.44 pp |
| flag_opp_soft_s1    | 1,055| -0.75 pp | -0.21 pp | **+4.36 pp** | +2.15 pp |

`flag_skill_spike_s1` is the only component with meaningful and consistently
positive lift across A/B/D. It's larger than the composite stack>=2 signal
(which gets diluted by recform_hot and opp_soft contributing zero or
negative). n=256 is small but the direction is uniform.

`flag_opp_soft_s1` lifts only on C (low-bar sum>=18), which makes sense —
a soft opp helps a streamer clear a low floor but doesn't push to a real
boom. And opp_soft is independent across starts (per prior work), so it's
a single-game signal, not a week one.

## 5. Verdict

### VERDICT: **DON'T SHIP**

None of the four alternative boom definitions surface a meaningful
streamer edge at `boom_stack_s1 >= 2`:

- All pooled edges within ±1 pp on n=342
- Every definition flips sign across years
- Rotating-slot bootstrap matches the independence prediction —
  no hidden positive correlation to exploit
- The per-start stack signal at streamer is real (+5 pp at stack=2),
  but it does NOT compound to a week-level amplification under any
  reasonable boom threshold

The original conclusion stands: **streamer-tier signals are single-start,
not week-level.** A streamer-streaming user already captures the per-start
edge by picking stack>=2 streamers — there's no additional week-boom
threshold that turns that into a multi-game amplification.

### One real finding to surface

The only signal that beats the composite at streamer tier is
**`flag_skill_spike_s1` alone**:

- Lift +3.2 pp (A), +4.2 pp (B), +3.5 pp (D) on n=256
- Larger and more consistent than composite stack>=2
- Mechanism: skill_spike persistence (44% sticky) carries to start 2;
  the composite is diluted by recform_hot (no week-boom lift) and
  opp_soft (single-start only)

This does NOT justify a week-boom table for streamers, but it suggests that
when choosing between two streamer options for a single slot, **prefer the
one with `flag_skill_spike` on, not just stack>=2**. This is a
single-start refinement, not a week-boom claim.

### Action

- **`/sp-week-plan`**: do NOT add a streamer-tier week-boom table. The
  signal is not there at any of the 4 definitions tested.
- **`/stream-the-stack`**: tie-breaker when two streamer candidates have
  the same composite stack — prefer the one whose stack is built on
  `flag_skill_spike` rather than `flag_recform_hot` or `flag_opp_soft`.
  Document this as a per-start refinement, not a week-boom claim.
- **No engine change.** This is research-only.

## 6. Caveats

- n=342 at stack_s1>=2 streamer is small; +1 pp edges have CI of roughly
  ±5 pp. We can't rule out a true +2-3 pp definition-C edge but we can't
  confirm one either.
- The flag_skill_spike_s1 finding (n=256) is itself thin. Pre-register
  before treating as a validated signal — recommended baseline test:
  `/validate-feature` Rule 9 against composite stack.
- Bootstrap pairs in section 3 sampled within the stack>=2 pool without
  enforcing same-year matching; results are stable across both samplings
  (checked separately; difference <0.5 pp).
- 2020 excluded throughout.

## Files

- This report: `data/research/validation_runs/streamer_week_boom_redefined.md`
- Panel: `data/research/validation_runs/2start_week_panel.csv`
- Per-start panel: `data/research/_boom_stack_per_start_panel_cache.parquet`
- Predecessor: `data/research/validation_runs/2start_week_amplification.md`
