# SP In-Season Stuff-Decay → RoS FP Decline Backtest (2026-06-13)

**Question:** Which in-season *stuff-decay* signals (velo + whiff/K + Stuff+-slope only)
best predict a starting pitcher's rest-of-season FP **decline** — catching
Framber-Valdez-types BEFORE the results fully crater?

**Scope:** velo, SwStr%/CSW%/whiff/K%, and Stuff+ slope. (Contact/damage/
xwOBAcon/pitch-mix/age handled by a separate agent — excluded here.)

## Data & method

- Panel: `data/research/xfp_cache/rolling_pitchers_2018_2026.csv` — per-(pitcher,
  split_day) **cumulative-to-split** (`_to`) + **last-21-day** (`_last21`) features +
  realized target `ros_fp_per_start`. Base/to-date = `fp_per_start_to`.
- Prior-year baselines (velo, swstr, k%, extension) joined from `sp_multiyr.csv`
  (year+1) — coverage only **39%** of split rows (many pitchers have no qualifying
  prior season).
- Filter: `ros_gs >= 3` (stable target). **n = 23,598** split-day rows; material-decline
  base rate **37.5%**.
- **Targets:** (a) `ros_fp_per_start`; (b) `decline = ros − to-date`; (c) binary
  `material_decline = decline < −2 FP/start`.
- **Leakage discipline:** as-of-split data only; **player-clustered GroupKFold**
  (5-fold, no pitcher in train+test) for AUC; **partial r controlling for the
  to-date FP base** (Rule 9 — incremental, not raw corr); **400× cluster bootstrap**
  CIs on pitcher; convergence-curve check across split_days 30/44/58/100/149.
- Note: with `decline = ros − base` and base partialled out, `partial_r(decline)` ≡
  `partial_r(ros)` by construction — they are the same incremental signal.

## Ranked signals (by |partial r| over the to-date base)

| Signal | desc | n | partial r (decline) | 95% CI | ΔAUC vs base | flag |
|---|---|---|---|---|---|---|
| `swstr_z_pop` | SwStr% z (current level) | 23598 | **+0.235** | [0.193, 0.273] | +0.017 | clean |
| `k_z_pop` | K% z (current level) | 23598 | **+0.234** | [0.194, 0.277] | +0.019 | clean |
| `swstr_recent` | SwStr% L21 level | 21946 | +0.187 | [0.152, 0.218] | +0.015 | clean |
| `k_recent` | K% L21 level | 21946 | +0.179 | [0.151, 0.207] | +0.012 | clean |
| `velo_recent` | FB velo L21 level | 21944 | +0.165 | [0.116, 0.214] | +0.011 | clean |
| `velo_z_pop` | velo z (level) | 23598 | +0.156 | [0.111, 0.206] | +0.007 | clean |
| `d_velo_yoy` | velo to-date − prior-yr | 9278 | +0.134 | [0.055, 0.199] | +0.003 | low-cov |
| `d_velo_recent_yoy` | velo L21 − prior-yr | 8634 | +0.132 | [0.074, 0.191] | +0.006 | low-cov |
| `d_k_yoy` | K% to-date − prior-yr | 9278 | −0.096 | [−0.181, −0.009] | +0.005 | wrong-sign/low-cov |
| `d_velo_recent` | **velo L21 − to-date** | 21944 | +0.044 | [0.010, 0.070] | +0.001 | **noise** |
| `d_csw_recent` | CSW% L21 − to-date | 21946 | +0.030 | [0.007, 0.050] | −0.000 | **noise** |
| `d_k_recent` | K% L21 − to-date | 21946 | +0.026 | [0.005, 0.049] | −0.000 | **noise** |
| `d_swstr_recent` | **SwStr% L21 − to-date** | 21946 | +0.020 | [−0.002, 0.041] | −0.000 | **noise** |
| `d_swstr_recent_yoy` | SwStr% L21 − prior-yr | 8634 | −0.002 | [−0.047, 0.046] | −0.001 | **noise** |
| `d_fp_recent` | [CTRL] recent FP − to-date | 21497 | +0.038 | [0.013, 0.062] | −0.000 | **noise** |

Best single full-model GroupKFold **AUC ≈ 0.72** (base+`k_z_pop`), vs base-only ≈ 0.70.

## Tail check (does a big drop catch decline?)

Material-decline rate by quintile of the velo-decay deltas (base rate 37.5%):

- **L21 velo vs to-date:** biggest-drop Q1 **39.1%** vs gain Q5 **33.5%** — only ~6 pp
  spread; mean decline −0.76 vs −0.14 FP. Weak.
- **to-date velo vs prior-yr:** biggest-drop Q1 **38.9%** vs Q5 **33.8%** — ~5 pp,
  mean decline −1.13 vs +0.13 FP. Modestly stronger in mean but still barely separates.

A pitcher in the worst velo-decay quintile is only marginally more likely to crater
than average. **Velo decay alone does not flag the Framber-Valdez crater early.**

## Convergence-curve (leakage) check — PASSED

Partial r by split_day for the top signals **DECAYS** with the season (correct
direction — earlier reads predict more remaining season):

```
swstr_z_pop   d30:+0.268  d44:+0.254  d58:+0.254  d100:+0.247  d149:+0.201
k_z_pop       d30:+0.265  d44:+0.249  d58:+0.247  d100:+0.244  d149:+0.227
swstr_recent  d30:+0.227  d44:+0.210  d58:+0.225  d100:+0.175  d149:+0.146
velo_recent   d30:+0.168  d44:+0.182  d58:+0.155  d100:+0.147  d149:+0.186
```

Near-**identical** lift across split_days would be the leakage smoking gun (the
`lens_value_add` ~5× inflation pattern). We see a **monotone-ish decay instead** —
no leakage flag. The signal is real but front-loaded.

## VERDICT

**The reliable early-warning signal is a pitcher's CURRENT whiff/K *level*, not the
in-season *change* in it.**

1. **`swstr_z_pop` (SwStr% level, population-z)** and **`k_z_pop` (K% level)** are the
   2 best, near-tied: partial r ≈ **+0.23** over the to-date FP base, CIs well clear of
   0, ΔAUC +0.017–0.019, AUC ≈ 0.72, strongest at day 30 (+0.27). These catch decline
   earliest and most reliably. Mechanism: a pitcher whose **results to date outrun his
   whiff/K stuff** is the one who regresses — the *level* of stuff is what to-date FP
   fails to encode.
3. **`velo_recent` / `velo_z_pop` (velo level)** is a useful third lens (partial
   +0.16), and **YoY velo drop** (`d_velo_yoy`, +0.13) adds a little where prior-year
   data exists — but only ~39% coverage and the tail spread is small.

**Honest noise / DO NOT use:**
- **Within-season recency *deltas* of whiff/K/velo (L21 − to-date)** are essentially
  noise: `d_swstr_recent` +0.020 (CI touches 0), `d_k_recent` +0.026, `d_velo_recent`
  +0.044, all ΔAUC ≈ 0. The intuitive "his swing-and-miss is falling off this month"
  signal does **not** survive controlling for the base rate.
- **`d_k_yoy` flips sign** (−0.096) — an artifact of low (39%) prior-year coverage and
  selection; do not trust.
- **In-season Stuff+ slope could NOT be tested as a true slope.** `data/research/fg_asof/`
  holds only one genuine intra-season as-of snapshot (`fg_pit_2024_asof_2024-06-06.csv`);
  the rest are seasonal pre/ros aggregates — there is no per-split-day Stuff+ series to
  compute a leakage-safe slope across the 24 split days. SwStr%/CSW% level (which IS
  per-split-day) is the available stand-in and is the top performer above.

**Bottom line:** to catch a Framber-Valdez before results crater, watch **where his
whiff/K stuff currently SITS vs his FP** (low whiff + high FP = regression coming),
**not** how much his velo or whiff dipped this month. The decay-delta framing is the
seductive-but-noisy version; the stuff-*level*-vs-results gap is the signal.
