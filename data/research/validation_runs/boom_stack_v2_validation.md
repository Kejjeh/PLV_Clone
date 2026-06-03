# streamer_boom_stack_v2 — confirmatory validation report

**Date:** 2026-06-03
**Pre-registration:** `data/research/validation_runs/boom_stack_v2_2026-06-03.md` (written BEFORE running confirmatory tests)
**Validation script:** `scripts/xfp/validate_boom_stack_v2.py`
**Results JSON:** `data/research/validation_runs/boom_stack_v2_validation_results.json`
**Pre-computed streamer panel:** `data/research/validation_runs/boom_stack_v2_streamer_panel.csv` (12,713 rows, 2018+2019+2021-2025)

## Pre-registered hypothesis (recap, BEFORE results)

> Adding `flag_high_k_pitcher` (season K% z-score in (year, month) >= +0.5, n_prior_starts >= 3) to v1's 3-flag boom_stack creates a v2 sum 0-4. Stack=4 cohort boom rate **>= 26%** with **chi² p < 0.025** (Bonferroni-corrected for two tests: stack=4 vs stack<=2, stack=4 vs stack=3). Year-by-year stack>=3 edge positive in **>= 6 of 7** years. Independence preserved (pooled max |corr| <= 0.10).

Three live verdict tracks:
- **SHIP_AS_TAG_V2** — all gates clear
- **NEEDS_MORE_DATA** — point estimate supportive but stack=4 cell < 50 / marginal underpowered
- **DON'T_SHIP** — sign or independence violated, or stack=4 < 26%

## Results

### Mode B — boom-rate buckets in streamer pool (n=12,713)

| boom_stack_v2 | n | booms | boom rate | Wilson 95% CI | mean FP |
|--:|--:|--:|--:|--:|--:|
| 0 | 5,840 | 536 | 9.18% | [8.46%, 9.95%] | 8.22 |
| 1 | 4,986 | 598 | 11.99% | [11.12%, 12.93%] | 9.59 |
| 2 | 1,546 | 217 | 14.04% | [12.39%, 15.86%] | 10.16 |
| 3 | 329 | 61 | 18.54% | [14.71%, 23.10%] | 11.02 |
| **4** | **12** | **4** | **33.33%** | **[13.81%, 60.94%]** | **12.53** |

Distribution is monotonic in boom rate, as predicted. Stack=4 point estimate (33.33%) exceeds the 26% pre-registered bar, BUT the Wilson 95% CI is [13.81%, 60.94%] — too wide to confidently distinguish from stack=3 or even stack=2.

### Chi² tests

| Test | chi² | p-value | Bonferroni bar | Pass? |
|---|--:|--:|--:|---|
| stack=4 vs stack<=2 | 4.094 | 0.0430 | p < 0.025 | **FAIL** (close but fails the adjusted bar) |
| stack=4 vs stack=3 (marginal over v1 top) | 0.823 | 0.3642 | p < 0.025 | **FAIL** (underpowered at n=12 vs n=329) |

The stack=4 vs stack<=2 unadjusted p=0.043 would have cleared α=0.05 — but the pre-registration explicitly imposed Bonferroni for the two chi² tests, so the bar is 0.025. Observed 0.043 narrowly fails.

The stack=4 vs stack=3 test is the critical one for "is v2 better than v1?" Marginal lift +14.79 pp looks large but p=0.36 — at n=12 we cannot reject the null that stack=4 boom rate equals stack=3 boom rate.

### Standalone Mode B edge (full streamer pool, cand=1 vs cand=0)

Re-verifies the search result with the same panel:

| | n | boom rate | 95% CI |
|---|--:|--:|--:|
| cand=1 (high_k_pitcher fires) | 1,039 | 17.42% | [15.20%, 19.90%] |
| cand=0 | 11,674 | 10.58% | [10.02%, 11.17%] |
| **edge** | | **+6.84 pp** | chi² = 44.43, **p = 2.6e-11** |

Standalone evidence is overwhelming. n=1,039 in the flag=1 cell. This is the strong leg of the case.

### Independence diagnostics

Pearson correlation of `cand_high_k_pitcher` with each v1 flag.

**Pooled (n=12,713):**

| v1 flag | corr |
|---|--:|
| flag_skill_spike | +0.0176 |
| flag_recform_hot | +0.0006 |
| flag_opp_soft | −0.0050 |

Pooled max |corr| = **0.0176**. Far below the 0.10 pre-registered bar. Fully orthogonal.

**Per-year max |corr|:**

| year | max |corr| with any v1 flag |
|--:|--:|
| 2018 | 0.0334 |
| 2019 | 0.0972 |
| 2021 | 0.0343 |
| 2022 | 0.0405 |
| 2023 | 0.0361 |
| 2024 | 0.0499 |
| 2025 | 0.0348 |

Worst per-year |corr| = 0.0972 (2019). Below the 0.30 per-year bar AND below the 0.10 pooled bar. **Independence PASS.**

### Year-by-year stability at stack>=3 (combining v2 stack=3 and stack=4)

| year | hi(stack>=3) n | hi rate | lo(stack<=2) n | lo rate | edge_pp |
|--:|--:|--:|--:|--:|--:|
| 2018 | 41 | 19.51% | 1,784 | 13.29% | **+6.23** |
| 2019 | 48 | 16.67% | 1,741 | 10.86% | **+5.81** |
| 2021 | 35 | 17.14% | 1,707 | 9.61% | **+7.54** |
| 2022 | 60 | 26.67% | 1,765 | 9.80% | **+16.86** |
| 2023 | 47 | 14.89% | 1,768 | 10.12% | **+4.77** |
| 2024 | 67 | 22.39% | 1,769 | 12.32% | **+10.06** |
| 2025 | 43 | 11.63% | 1,838 | 10.39% | **+1.24** |

**Positive years: 7/7.** Pre-registered bar: >= 6/7. **PASS** (clears with one to spare).

Note 2025 edge of +1.24 pp is the weakest; this is the most-recent year (and likely a season-in-progress effect plus regression toward the mean from 2024's +10 pp). Still positive.

### Tier robustness — does the cand effect amplify with v1 stack?

Marginal effect of `cand_high_k_pitcher` (cand=1 boom rate − cand=0 boom rate) within each v1 stack tier:

| v1 stack tier | cand=1 n | cand=1 rate | cand=0 n | cand=0 rate | edge_pp |
|---|--:|--:|--:|--:|--:|
| 0 | 510 | 15.69% | 5,840 | 9.18% | +6.51 |
| 1 | 400 | 17.75% | 4,476 | 11.57% | +6.18 |
| 2 | 117 | 22.22% | 1,146 | 12.74% | **+9.48** |
| 3 | 12 | 33.33% | 212 | 16.51% | **+16.82** |

**Monotonic amplification.** The high_k_pitcher edge grows as the underlying v1 state improves — exactly the pattern predicted by the tier-amplification finding in `boom_stack_by_tier.md`. The signal interacts constructively with v1 (rather than substituting for it), which is what we want from a 4th orthogonal component.

This is the strongest piece of evidence beyond the standalone edge: even though the stack=4 cell itself is n=12, the directional shape across n=510 / n=400 / n=117 / n=12 is consistent and the edge increases.

### Mode A — model integration (pre-registered expected null)

Not re-run. The v1 result documented +0.0000 cross-year r lift, 4/7 sign consistency, and mixed convergence signs across split_days 30/44/58. high_k_pitcher is structurally redundant with rp3's existing `k_pct_to` feature for ROS-mean framing. The point-estimator framing buries the boom-rate signal that Mode B surfaces. This is the cross-mode synthesis the v1 report already established.

Within-streamer correlation of `boom_stack_v2` with per-start FP = **+0.0860** (vs v1 stack +0.0635). The +0.0225 gain is consistent with the standalone edge but does NOT establish point-estimator utility — it's a same-frame correlation, not a held-out predictive test.

**Mode A verdict: DON'T SHIP to RP3_FEATS** (pre-registered expected null, confirmed).

## Gate summary

| Gate | Pre-registered bar | Observed | Pass? |
|---|---|---|---|
| stack=4 boom rate point estimate | >= 26% | 33.33% (CI [13.8%, 60.9%]) | POINT-PASS, CI-FAIL |
| stack=4 vs stack<=2 chi² | p < 0.025 (Bonferroni) | p = 0.0430 | **FAIL** (narrowly) |
| stack=4 vs stack=3 marginal chi² | p < 0.025 (Bonferroni) | p = 0.3642 | **FAIL** |
| Standalone Mode B edge | >= +5 pp | +6.84 pp (p=2.6e-11) | **PASS** |
| Year-by-year at stack>=3 | >= 6 of 7 positive | 7/7 | **PASS** |
| Independence pooled | max \|corr\| <= 0.10 | 0.0176 | **PASS** |
| Independence per-year | max \|corr\| <= 0.30 | 0.0972 | **PASS** |
| Tier robustness | positive in >= 2 of 3 tiers | positive AND monotonically amplifying in 4/4 v1-tiers | **PASS** |

## VERDICT: **NEEDS_MORE_DATA**

The pre-registered SHIP_AS_TAG_V2 verdict required stack=4 to clear the Bonferroni-adjusted chi² gates. It does not (p=0.043 narrowly misses the stack<=2 cut; p=0.36 fails the stack=3 marginal entirely). The headline cell at n=12 is too thin to support a tier-4 tag confidently.

However, **the standalone signal IS validated** (+6.84 pp, p=2.6e-11, n=1,039) AND the tier-amplification pattern is monotonic AND year-by-year is 7/7 AND independence is fully clean. The signal is real; the problem is purely sample size at the headline tier.

This is the textbook NEEDS_MORE_DATA case the pre-registration anticipated. **Two viable paths forward**, ranked by honesty:

### Path A (recommended) — ship `flag_high_k_pitcher` as a STANDALONE display tag, NOT as v2

Promote the **standalone flag** (`high_k_pitcher`) to `/triangulate` and matchup-dashboard SP cards as a separate tag — not as a 4th component of boom_stack. The tag display:

- When `flag_high_k_pitcher=1` AND SP is in streamer pool: display `HIGH-K ARM — +6.8pp boom rate (n=1,039 historical)`
- When `flag_high_k_pitcher=1` AND v1 boom_stack >= 2: display `BOOM STACK 2/3 + HIGH-K ARM — tier-amplified boom EV`

This ships the validated signal without claiming a stack=4 tier that we cannot defend at n=12.

### Path B — defer v2 promotion to post-2026 season

Re-run validation in 2026-10 with one additional season of data. Expected stack=4 cell after 2026: ~14 starts (8.17% × ~1.8% × ~1,800 streamer starts per year ≈ 2-3 incremental observations on top of the 12 we have — i.e., we'd need MULTIPLE additional years to confidently power the chi² stack=4 vs stack=3 test). Given that math, Path A is strictly better — by 2028+ when n at stack=4 reaches ~30, the signal will already have been useful for 2 full seasons.

### What we are NOT doing

- **NOT promoting `boom_stack_v2` as a 4-component sum.** The headline cell fails the pre-registered Bonferroni bar. Shipping it under the v2 label would over-claim the stack=4 boom rate when the CI is [13.8%, 60.9%].
- **NOT adding `flag_high_k_pitcher` to RP3_FEATS.** Pre-registered Mode A expected null is confirmed. The signal lives in research/display artifacts, not in the ranker.

## Spec for Path A (DO NOT IMPLEMENT YET — just spec)

If you choose Path A on a follow-up, the minimal change is:

**File:** `scripts/xfp/lib/boom_stack.py` (or wherever the v1 stack tag is computed in `run_triangulate.py`)

```python
# Adjacent to (but NOT part of) the v1 boom_stack computation:
def compute_high_k_pitcher_flag(per_start_panel: pd.DataFrame) -> pd.Series:
    """flag_high_k_pitcher — pitcher's cumulative-prior season K%, z-scored
    within (year, month), >= +0.5, with n_prior_starts >= 3.

    Validated as a standalone boom-rate flagger 2026-06-03 (+6.84 pp, n=1,039,
    p=2.6e-11, 7/7 years positive, fully orthogonal to v1 components).

    NOT promoted as a 4th component of boom_stack — see
    data/research/validation_runs/boom_stack_v2_validation.md (NEEDS_MORE_DATA
    verdict at stack=4 cell n=12).
    """
    df = per_start_panel.copy()
    df['k_prior_sum'] = df.groupby(['pitcher', 'year'])['actual_K'].cumsum() - df['actual_K']
    df['pa_prior_sum'] = df.groupby(['pitcher', 'year'])['actual_PA'].cumsum() - df['actual_PA']
    df['season_k_pct'] = df['k_prior_sum'] / df['pa_prior_sum'].replace(0, np.nan)
    df['ym'] = df['game_date'].dt.to_period('M').astype(str)
    def _z(s):
        sd = s.std(ddof=0)
        if not np.isfinite(sd) or sd == 0:
            return pd.Series(np.zeros(len(s)), index=s.index)
        return (s - s.mean()) / sd
    df['k_pct_z'] = df.groupby(['year', 'ym'])['season_k_pct'].transform(_z)
    n_prior = df.groupby(['pitcher', 'year']).cumcount()
    return ((df['k_pct_z'] >= 0.5) & (n_prior >= 3)).astype(int)
```

**Triangulate display rule (in `run_triangulate.py`):**

```python
if sp_is_streamer and high_k_flag:
    tags.append(f"HIGH-K ARM (+6.8pp boom rate, validated 2026-06-03)")
if sp_is_streamer and v1_boom_stack >= 2 and high_k_flag:
    tags.append("STACK 2/3+ × HIGH-K — tier-amplified boom EV")
```

Registry entry to add to `reference_validated_signals_registry.md` under **VALIDATED (research-stage / display tag)**:

```markdown
### flag_high_k_pitcher — VALIDATED AS DISPLAY TAG (2026-06-03)
- **Standalone validation:** Mode B boom-rate classifier. Streamer-pool n=12,713
  (2018-2025 ex-2020). cand=1 (n=1,039) boom rate 17.42%; cand=0 (n=11,674)
  boom rate 10.58%. Edge **+6.84 pp**, chi² = 44.43, **p = 2.6e-11**.
- **Year-by-year:** edge_pp at stack>=3 positive in 7/7 years (range +1.24 to +16.86).
- **Independence vs v1 boom_stack components:** pooled max |corr| = 0.0176;
  worst per-year |corr| = 0.0972. Fully orthogonal.
- **Tier amplification:** edge grows monotonically with v1 stack tier
  (v1_stack=0: +6.5 pp, v1_stack=3: +16.8 pp). Constructive interaction
  with v1 confirms the orthogonal-dimension claim.
- **Definition:** cumulative-prior season K% z-scored within (year, month) >= +0.5,
  n_prior_starts >= 3.
- **Status:** SHIP AS DISPLAY TAG in `/triangulate` and matchup dashboard for
  streamer-class SPs. DO NOT add to RP3_FEATS (Mode A expected null, structurally
  redundant with `k_pct_to`).
- **NOT promoted as boom_stack_v2:** stack=4 cell n=12 too thin (Wilson 95% CI
  [13.8%, 60.9%]); chi² stack=4 vs stack=3 p=0.36 (underpowered). See
  `data/research/validation_runs/boom_stack_v2_validation.md`.
```

## Bonferroni / sweep context

This run tested 2 chi² hypotheses on the same winner that emerged from a 5-candidate search. The CONFIRMATORY bar is α/2 = 0.025 per chi² (in addition to the search's own 5-cell Bonferroni at α/5 = 0.01, which high_k_pitcher cleared at p=2.6e-11). Both confirmatory chi² tests failed the adjusted bar; the supporting evidence (standalone p=2.6e-11, 7/7 years, monotonic tier amplification) is what drives the partial-pass verdict.

## Sample-size honesty (Rule 5)

- Streamer pool: n=12,713. Per-bucket n: 5,840 / 4,986 / 1,546 / 329 / 12.
- Stack=4 cell (n=12) is the underpowered headline. Wilson 95% CI [13.8%, 60.9%] is the honest read.
- Stack>=3 combined (n=341 across years) is well-powered: Wilson CI on the 19.06% rate is roughly [15.1%, 23.7%].
- Standalone flag=1 cell (n=1,039) is well-powered: Wilson CI on 17.42% is [15.20%, 19.90%].
- Independence per-year n ranges from 1,742 (2018, 2021) to 1,881 (2025). All clear Rule 5 per-year floor.

## Anti-patterns checked

- **Did NOT use a stripped-down baseline.** Mode A baseline = full RP3_FEATS (24 features) per v1 result. Confirmed.
- **Did NOT change the pre-registration after seeing results.** Pre-registration was written before running `validate_boom_stack_v2.py`.
- **Did NOT pick the n=12 stack=3 cell from the search as the headline finding.** Pre-registration explicitly forbade this; the verdict uses the standalone edge as the load-bearing evidence.
- **Did NOT inflate the verdict to SHIP by reporting unadjusted p-values.** Bonferroni-adjusted 0.025 bar is what the pre-registration set; observed 0.043 narrowly fails and is reported as fail.

## Next step (per Rule 7)

Production integration of Path A (HIGH-K ARM display tag) is a SEPARATE request. Recommended path: post this verdict, await user decision, then plan the `boom_stack.py` + `run_triangulate.py` minimal edit.

---

## Frontmatter verdict (to be appended to `boom_stack_v2_2026-06-03.md`)

`verdict: NEEDS_MORE_DATA` (for the v2-as-stack-tag claim)
`verdict_standalone: PASS_AS_DISPLAY_TAG` (for the standalone flag claim)
