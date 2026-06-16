# Release-point / Arm-angle drift as an SP decline signal — validation run

**Date:** 2026-06-13
**Script:** `scripts/_oneoff/release_armangle_study.py`
**Panel saved:** `data/research/validation_runs/_release_armangle_panel.csv`
**Target:** `ros_fp_per_start` (forward BrownU SP FP/start), leakage-safe as-of.

## Question

Does **release-point / arm-angle drift** add SP decline-prediction signal
**OVER our existing overall-velo-decline flag**?

**Theory under test:** we previously established velo loss is orthogonal to
whiffs — it's an injury/fatigue channel. Mechanics should then *separate*
injury-grade velo loss (velo drop **with** arm-slot/release drift) from benign
velo loss (drop **with** stable mechanics). If true, a mechanics-drift score —
or a velo×drift interaction — should beat plain velo YoY at flagging forward
decline / bust.

## Methodology (matched to protocol)

1. **Leakage-safe as-of.** All mechanics features built only from FB pitches
   (FF/SI/FC) with `game_date < cutoff_date`. Cutoffs = `split_day {51,72,93,114}`,
   years **2021-2025**. Joined to forward target on `(pitcher, year, split_day)`.
   Gate `gs_to>=5 & ros_gs>=3`.
2. **Rule-9 baseline.** Controls = whiff/K **level** = `rank(swstr_pct_to) +
   rank(k_pct_to)` AND `fp_per_start_to`. Partial-r of each feature reported over
   `[level, fp]` and — the bar — `[level, fp, overall_velo_yoy]`, where
   `overall_velo_yoy = (current FB velo as-of) − (prior-year full-season FB velo)`.
3. **Downside.** bust = bottom-tercile `ros_fp_per_start` within each
   `(year, split_day)` cell; bust-gap = standardized mean(feature|bust) −
   mean(feature|ok).
4. **Key interaction.** `ros_fp ~ level + fp + z_velo + z_mech + (z_velo×z_mech)`
   plus a 2×2 quadrant (worst-velo-tercile × most-drift-tercile).
5. **Honesty.** A feature wins only if it adds partial-r over **both** bars at
   adequate n. Nulls rejected plainly.

### Features built (as-of, FB-only)
- `rel_shift` — recent-21d release point (x,z) euclidean **shift** vs season-to-cutoff baseline (ft)
- `rel_scatter` — within-season release-point **scatter** = √(std_x²+std_z²) (ft) — mechanical inconsistency
- `ext_change` — recent vs season extension change (ft)
- `arm_shift_recent` — recent vs season arm-angle shift (deg)
- `arm_yoy` — arm-angle change vs prior full season (deg)
- `rel_yoy` — release-point shift vs prior season (ft)
- `ext_yoy` — extension change vs prior season (ft)
- `mech_drift` — composite z-sum of all six drift components (full, incl YoY)
- `mech_drift_ws` — composite of the within-season-only four (no prior-year ref needed)

## Coverage

| item | n |
|---|---|
| gated panel rows (2021-25, 4 cutoffs) | **2897** |
| with as-of FB release features | 2732 |
| with `overall_velo_yoy` (prior-yr ref) | 2500 |
| with `arm_yoy` | 2500 |
| with full composite `mech_drift` | 2897 |

`overall_velo_yoy` non-null splits evenly by year (~490-520 each, 2021-2025).

**arm_angle coverage note (correction to CLAUDE.md).** CLAUDE.md states arm_angle
is "2025+ only." That is **NOT** true of the local cache — the Statcast parquets
have arm_angle backfilled for **2021-2026** (Savant retroactively computed it):
non-null arm_angle is 687k/712k (2021) … 708k/712k (2025). So the YoY arm-angle
feature here has **full multi-year coverage** (n=2500 after the prior-year ref
gate), not a 2025-only sliver. The conclusion below is therefore on a real panel,
not an underpowered one.

## Results

### Partial-r table (target = ros_fp_per_start)
sign convention: a **drift** feature should be **negative** (more drift → worse fp).

| feature | partial-r [lvl,fp] | partial-r [+velo_yoy] (THE BAR) | n |
|---|---:|---:|---:|
| `overall_velo_yoy` (reference) | **+0.100** | — | 2500 |
| rel_shift | +0.036 | +0.033 | 2354 |
| rel_scatter | +0.028 | +0.023 | 2500 |
| ext_change | −0.026 | −0.021 | 2354 |
| arm_shift_recent | −0.040 | −0.030 | 2354 |
| arm_yoy | −0.015 | −0.021 | 2500 |
| rel_yoy | +0.010 | +0.002 | 2500 |
| ext_yoy | +0.014 | +0.009 | 2500 |
| **mech_drift** (composite) | **+0.006** | **−0.001** | 2500 |
| mech_drift_ws (composite) | +0.008 | +0.005 | 2500 |

- The **velo bar is real and strong**: `overall_velo_yoy` partial-r **+0.100** over
  [level, fp] — losing fastball velo robustly predicts lower forward FP/start.
- **Every mechanics-drift feature is near-zero.** Best single drift term is
  `arm_shift_recent` at −0.040 over [lvl,fp], decaying to −0.030 once velo is
  controlled. The **composite `mech_drift` is effectively 0** (+0.006 → −0.001).
  Signs are inconsistent (rel_shift is even mildly *positive*).
- **None survive the bar.** No drift feature adds meaningful partial-r over
  `[level, fp, overall_velo_yoy]`. The marginal drift signal is already inside velo.

### Bust-gap (bust = bottom-tercile ros_fp within cell)
positive gap on a drift feature = busts carry more drift.

| feature | gap (z\|bust − z\|ok) | n |
|---|---:|---:|
| `overall_velo_yoy` (reference) | **−0.269** | 2500 |
| arm_yoy | +0.157 | 2500 |
| mech_drift | +0.118 | 2897 |
| arm_shift_recent | +0.112 | 2732 |
| rel_scatter | +0.085 | 2897 |
| rel_shift | +0.058 | 2732 |
| ext_change | +0.003 | 2732 |

Drift features show the *right sign* on bust (busts have modestly more drift) but
the gaps are **2-4× smaller** than velo's −0.269. arm_yoy (+0.157) is the most
respectable, but it's collinear with velo loss, not additive to it (see partial-r
+velo column above: arm_yoy −0.021, indistinguishable from zero).

### KEY INTERACTION — velo-drop × mechanics-drift  (n=2500)
`ros_fp ~ level + fp + z_velo + z_mech + (z_velo × z_mech)`

| term | beta | se | t |
|---|---:|---:|---:|
| z_velo | 0.374 | 0.076 | **4.94** |
| z_mech | 0.013 | 0.076 | 0.17 |
| **interaction** | 0.032 | 0.071 | **0.45** |

The interaction is **null** (t=0.45, wrong sign for the theory). Velo carries all
the signal; mechanics drift adds nothing on its own and does **not** amplify the
velo effect.

### 2×2 quadrant — the clincher
worst-velo-tercile × most-drift-tercile:

| velo_lost | mech_drifted | n | mean ros_fp | bust_rate |
|:---:|:---:|---:|---:|---:|
| 0 | 0 | 1153 | 10.64 | 0.281 |
| 0 | 1 | 522 | 10.32 | **0.308** |
| 1 | 0 | 522 | 9.56 | **0.400** |
| 1 | 1 | 303 | 9.73 | 0.422 |

- **Velo loss alone** lifts bust rate 0.281 → 0.400 (+12 pp). This is the channel.
- **Drift alone** (velo intact) barely moves it: 0.281 → 0.308 (+3 pp, noise).
- **Drift on top of velo loss** moves 0.400 → 0.422 (+2 pp) — exactly the noise-
  scale of the drift-alone effect, and mean ros_fp actually *rises* (9.56 → 9.73).
  The theorized "injury-grade vs benign" split does **not** appear: a velo drop
  with stable mechanics busts essentially as hard as one with drift.

## VERDICT

**Do NOT wire a mechanics-drift conviction flag.** The theory is clean and the
test was well-powered (n≈2500, full multi-year arm_angle coverage), but the data
rejects it. Overall FB-velo YoY is a strong forward-decline / bust signal
(partial-r +0.100; bust-gap −0.269; bust rate 0.28→0.40 across the worst velo
tercile), and **release-point / arm-angle / extension drift adds nothing over
it** — every drift feature is near-zero partial-r over the [level, fp] baseline,
collapses further once velo is controlled, the composite `mech_drift` is
statistically zero, and the decisive **velo×drift interaction is null** (t=0.45).
The hoped-for separation — "velo loss WITH mechanics drift = injury-grade, velo
loss WITHOUT = benign" — does not exist in the panel: stable-mechanics velo
drops bust just as hard (40.0% vs 42.2%). Velo loss is the channel; mechanics
drift is not a usable second gate. Reject. Keep ranking decline risk on
overall-velo-decline; do not penalize a high-Stuff arm for release scatter.
