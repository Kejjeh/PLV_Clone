# Rule 9 integrity bug — rh3 validation harness `ROOT` path, and blast-radius assessment

**Date:** 2026-07-28
**Severity:** HIGH potential, **ZERO realized** (see blast radius)
**Fixed in:** `scripts/xfp/research/validate_rh3_breakout_signals.py`
**Found by:** the `xwoba_L150pa` validation run
([`xwoba_L150pa_2026-07-28.md`](../data/research/validation_runs/xwoba_L150pa_2026-07-28.md),
"Incidental findings")

---

## The bugs

### Bug 1 — `ROOT` resolved one directory too shallow

```python
ROOT = Path(__file__).resolve().parents[2]   # was correct at scripts/xfp/
```

Correct while the file lived at `scripts/xfp/`. On **2026-07-19** (commit
`b42b561`, *"audit wave 4: … archive 95 orphan research scripts …"*) it moved to
`scripts/xfp/research/` — one level deeper — and `parents[2]` began resolving to
`<repo>/scripts` instead of the repo root.

The three baseline inputs below `ROOT` were treated as **optional**, so instead of
failing they silently became constants:

| Input | Feature filled with |
|---|---|
| `data/outputs/seasonality_h2_locked.csv` | `lift_h2_aug150 = 0.0` |
| `data/outputs/hitter_xwoba_residual.csv` | `xwoba_residual_career = 0.0` |
| `data/research/xfp_cache/ros_opp_sp_xwoba_per_hitter.csv` | `ros_opp_sp_xwoba_weighted = 0.0` |

All three files exist at the correct repo-root-relative paths. Nothing was missing
from disk — only from `ROOT`.

### Bug 2 — hardcoded `RH3_FEATS` went stale

The harness kept its own copy of the feature list, frozen at **21** features.
Production has had **22** since `bx_prior_h` was promoted on 2026-07-10. A copy of
a baseline is a baseline that will eventually be wrong.

---

## Why this is a Rule 9 violation, quantified

Rule 9 requires the baseline to contain every production feature, because a
weakened baseline inflates any candidate's apparent lift. Measured on the real
rh3 frame (LOO ridge, `TRAIN_YEARS` 2018–2025, n=36,571):

| Baseline | cross-year r |
|---|---|
| **Correct** — 22 features, real inputs | **0.6418** |
| Broken — 22 features, 3 zeroed | 0.6113 |
| Broken **as it actually stood** — 21 features, 3 zeroed | **0.6050** |

**The degraded baseline sat −0.0368 below the true one.** The promotion gate is
**+0.005**. So a candidate that merely *proxied* the zeroed features — anything
correlated with opposing-SP schedule strength, career xwOBA residual, or the H2
lift profile — had up to **7.4× the gate** in spurious headroom available to it.
A pure null could have been promoted.

This is the same failure mode as the 2026-05-13 rh3/rp3 v2 incident (4× over-claim
from a stripped-down baseline), reintroduced accidentally by a file move.

---

## Blast radius: **zero realized**

The bug was live from **2026-07-19 18:44 EDT** (the archive commit) until
**2026-07-28**. Assessed three ways; all agree.

**1. No recorded validation run used a broken script after the move.**
Cross-referencing all **283** pre-registration files in
`data/research/validation_runs/` against the 35 scripts whose `ROOT` is now broken:
**59 preregs cite a now-broken script, and every one of them is dated before
2026-07-19.** Those runs executed from `scripts/xfp/`, where `parents[2]` was
correct. **Their verdicts stand as recorded.**

**2. The nine preregs dated on or after the move all cite unmoved scripts.**

| Date | Verdict | Script | Location | Status |
|---|---|---|---|---|
| 2026-07-19 | MARGINAL | `validate_ev90_to_sh.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | REJECTED | `validate_gmli_todate.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | REJECTED | `validate_hand_aware_streamer.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | PASS | `validate_milb_aaa_translation.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | REJECTED | `validate_pulled_air_rate.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | REJECTED | `validate_sb_takeoff_rate.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | REJECTED | `validate_spray_adj_xwobacon.py` | `scripts/xfp/` | unaffected |
| 2026-07-19 | MARGINAL | `validate_teammate_context.py` | `scripts/xfp/` | unaffected |
| 2026-07-28 | MARGINAL | `validate_xwoba_l150pa.py` | `scripts/xfp/` | unaffected (overrode paths explicitly) |

All eight 2026-07-19 scripts sit at `scripts/xfp/` (depth 2 → `parents[2]` = repo
root ✓). None were among the 96 files moved by `b42b561`. Note
`validate_milb_aaa_iso_prior.py` and `validate_milb_aaa_kpct_prior.py` *were*
moved, but those are different scripts from `validate_milb_aaa_translation.py`
(the PASS), and both ran back on 2026-05-24.

**3. Nothing live depends on a broken script.** A repo-wide scan for imports or
invocations of the 35 files from non-archived code returns exactly two hits: this
document's own fix target (imported by `validate_xwoba_l150pa.py`, which overrode
the paths), and `refresh_dashboards.py:237` invoking
`scripts/xfp/research/early_season_trending_2026.py` — which uses `parents[3]`,
correct for its depth, and is not in the broken set. **The daily refresh is
unaffected.**

**The only realized execution of the broken code path** was the
`validate_xwoba_l150pa` run on 2026-07-28, which imported the harness's helpers,
hit the missing inputs, and was corrected before any result was read.

### Honest limit of this assessment

It assumes the pre-registration files are a complete record of validation runs. An
unrecorded sweep would not appear — though that would itself violate Rule 1, which
requires pre-registration before running. No re-runs of past verdicts are
therefore indicated, and **none have been performed or rewritten.**

---

## Fixes applied

Scope was limited to the research harness. **No production file was touched** —
`scripts/xfp/xfp_rh3_pipeline.py`, `src/plv_clone/models/xfp/rh3.py`, and every
production `FEATS` list are unchanged.

1. **Marker-based repo root.** `_repo_root()` walks up to the directory containing
   `pyproject.toml`, so a future move cannot reintroduce the bug. Aborts if no
   marker is found.
2. **Baseline inputs are now REQUIRED.** All six (`ROLLING_CSV`, `MULTIYR_CSV`,
   `H2_LOCKED`, `XWOBA_RESID`, `ROS_OPP_SP`, `BX_PRIORS`) are existence-checked at
   import; a missing one raises `SystemExit` with a Rule 9 message. Silent
   `0.0`-fallback is gone.
3. **`RH3_FEATS` imported live** from `plv_clone.models.xfp.rh3`. The stale copy is
   deleted; drift is now impossible.
4. **`bx_prior_h` wired into the assembly**, mirroring `rh3.main()` — required now
   that the live 22-feature list is used.
5. **Missing baseline features abort instead of warn.** `main()` previously printed
   `WARNING: missing baseline feats` and *dropped them from the baseline* — the
   same silent-degradation pattern one level up. It now raises.

### Verification

The fixed harness reproduces the correct baseline exactly:

```
Baseline: 22/22 production features (complete)
Baseline cross_year_r = 0.6418  n=36571
  2018 0.6268 | 2019 0.6944 | 2021 0.5863 | 2022 0.6474
  2023 0.6244 | 2024 0.6262 [HOLDOUT] | 2025 0.6436 [HOLDOUT]
```

This matches the independently-assembled baseline in
`scripts/xfp/validate_xwoba_l150pa.py` (r = 0.6418, n = 36,571) to four decimals —
two separate assembly paths agreeing on the same number.

---

## Repo-wide sweep — all 56 stale anchors fixed (2026-07-28)

The first scan undercounted. Widening the pattern beyond a bare line-start
`ROOT =` — to include indented assignments and the `_ROOT` / `pre_reg_path`
spellings, and to cover `scripts/xfp/_attic/` which the first pass missed
entirely — found **57** stale repo-root anchors, not 35.

| Tree | Stale anchors |
|---|---|
| `scripts/xfp/research/` | 30 |
| `scripts/xfp/_attic/` | 17 |
| `scripts/xfp/archive/` | 9 |
| **Total rewritten** | **56** |
| Intentional non-root (left alone) | 1 |

By variable: `ROOT` ×51, `pre_reg_path` ×3, `_ROOT` ×2.

**One false positive, deliberately not touched:** `scripts/xfp/lib/rating_arc.py`
sets `_XFP = Path(__file__).resolve().parents[1]`, which resolves to
`scripts/xfp` — that is *correct*; the variable is the xfp package dir it inserts
into `sys.path`, not the repo root. Blind-replacing every `parents[N]` would have
broken it.

All 56 now use a marker-based walk-up that survives any future move:

```python
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
```

Chosen over a shared helper because these are standalone scripts: importing a
helper would itself require knowing the repo root to set `sys.path`, which is the
same chicken-and-egg problem. Self-contained and one line.

**Verification:** all 56 evaluated at runtime resolve to the repo root (56/56);
`compileall` clean across `scripts/`; full suite **876 passed**.

## Regression test

`tests/test_repo_root_paths.py` makes this bug class impossible to reintroduce.

1. `test_hardcoded_parents_anchors_resolve_to_repo_root` — every
   `VAR = Path(__file__).resolve().parents[N]` in the repo that denotes a repo root
   (by name, or by being joined to `data/`, `src/`, `scripts/`, …) must actually
   resolve to the directory holding `pyproject.toml`. The failure message names the
   file, the variable, and where it wrongly points, and shows the marker form to
   switch to.
2. `test_intentional_non_root_anchors_are_still_accurate` — keeps the
   `INTENTIONAL_NON_ROOT` allowlist honest. A stale entry (file deleted, variable
   renamed, or now resolving to the root anyway) fails, so the allowlist cannot
   quietly grow into a place where real regressions hide.
3. `test_marker_walkup_finds_root_from_any_depth` — parametrized over every tree
   that uses the marker form.

Both guards were **negative-controlled**: injecting a broken anchor
(`scripts/xfp/research/_canary_broken_root.py` with `parents[2]`) fails test 1 with
the expected message, and injecting a bogus allowlist entry fails test 2. Both pass
again once reverted — the tests can actually fail.
