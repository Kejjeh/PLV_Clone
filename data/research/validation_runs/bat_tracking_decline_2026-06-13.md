# Bat-Tracking Decline as a Hitter-Decline Lens — Leakage-Safe OOS Study

**Date:** 2026-06-13  **Status:** EXPLORATORY (net-new lens, NOT promoted)
**Author:** automated study (`scripts/_oneoff/bat_tracking_study.py`)

## Question
Does **bat-tracking decline** (bat_speed, swing_length) predict a hitter's
**rest-of-season decline** — the hitter-side analog of SP velo decline, which
the model currently has **no equivalent of**?

## Coverage constraint (read this first)
Statcast `bat_speed` / `swing_length` exist **only 2024+**. That leaves
**2 usable full seasons (2024, 2025)** for an as-of train/test. 2026 is a
partial season (study run 2026-06-13) and is **excluded as a cutoff year** —
it cannot supply a full forward window. **Everything below is 2-year evidence.
Do not overclaim.**

## Design (leakage-safe as-of)
For each `(year in {2024,2025}, cutoff in {mid-May, mid-Jun, mid-Jul})`:
- **Features** computed ONLY from swings/PAs **before** the cutoff.
- **Target** computed ONLY from PAs **on/after** the cutoff.
- Panel = batter × cutoff. Filters: ≥120 to-date PA, ≥80
  forward PA, ≥60 to-date swings with bat_speed.
- **Panel size: 1548 (batter×cutoff) rows, 410 unique batters, 6 cutoffs.**

### Forward-target proxy (stated plainly)
BrownU hitter FP = `R + TB + RBI + BB + HBP + SB − K`. Pitch-level Statcast
does **not** carry R / RBI / SB (baserunning + game-state outcomes), so the
forward target is a **CORE-FP/PA proxy = (TB + BB + HBP − K) / PA** — the
BrownU scoring components that ARE derivable from PA outcomes — plus a parallel
**forward xwOBA/PA**. R/RBI/SB are correlated with TB and on-base, so the proxy
captures the bat-driven core; absolute magnitudes are **proxy units**, not
BrownU FP/game.

### Baseline (Rule-9 spirit)
Partial-r residualizes each decline feature **and** the target on a baseline of
`[to-date xwOBA-on-contact LEVEL, to-date core-FP/PA LEVEL]`. Honest test:
does bat-speed *decline* add anything once we already know how good and how
productive the hitter has been to-date?

## Partial-r table
(raw_r = unconditional; partial_r = after baseline; positive feature = LESS
decline, so a positive partial_r means "more decline → worse forward outcome".)

| target | feature | n | raw_r | raw_p | partial_r | partial_p |
|---|---|---|---|---|---|---|
| forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA | bat_speed recent(L21d) - to-date mean | 1513 | 0.0349 | 0.1742 | 0.0245 | 0.3410 |
| forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA | bat_speed recent(L21d) - rolling 21d peak | 1513 | 0.0302 | 0.2408 | 0.0319 | 0.2151 |
| forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA | swing_length recent - to-date | 1513 | 0.0180 | 0.4845 | 0.0186 | 0.4687 |
| forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA | fast-swing(>=75mph) rate recent - to-date | 1513 | 0.0241 | 0.3490 | 0.0306 | 0.2337 |
| forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA | bat_speed YoY 2024->2025 (season means) | 725 | 0.0976 | 0.0086 | 0.0650 | 0.0801 |
| forward xwOBA/PA | bat_speed recent(L21d) - to-date mean | 1513 | 0.0215 | 0.4041 | 0.0349 | 0.1754 |
| forward xwOBA/PA | bat_speed recent(L21d) - rolling 21d peak | 1513 | 0.0325 | 0.2066 | 0.0526 | 0.0409 |
| forward xwOBA/PA | swing_length recent - to-date | 1513 | 0.0051 | 0.8435 | 0.0033 | 0.8977 |
| forward xwOBA/PA | fast-swing(>=75mph) rate recent - to-date | 1513 | 0.0441 | 0.0865 | 0.0402 | 0.1178 |
| forward xwOBA/PA | bat_speed YoY 2024->2025 (season means) | 725 | 0.1044 | 0.0049 | 0.0705 | 0.0579 |

## Downside bust-gap
Worst-20% decliners on `bat_speed recent(L21d) − rolling-21d peak` vs the rest.
`gap` < 0 means decliners do WORSE forward (proxy units). `bust_rate_*` =
share landing in the bottom forward quartile.

| target | n_decliners | decliner_mean_fwd | rest_mean_fwd | gap | bust_rate_decliners | bust_rate_rest |
|---|---|---|---|---|---|---|
| forward CORE-FP/PA proxy (TB+BB+HBP-K)/PA | 303 | 0.2397 | 0.2399 | -0.0001 | 0.2772 | 0.2438 |
| forward xwOBA/PA | 303 | 0.3173 | 0.3176 | -0.0003 | 0.2739 | 0.2446 |

## Read / verdict

**VERDICT: NOT a usable hitter-decline lens (as tested). Mostly NULL; one weak
directional ember (YoY bat-speed delta) that is not significant after baseline.**

What the numbers say:

- **Within-season bat-speed/swing-length DECLINE features are null.** Every
  L21d-based decline feature (recent vs to-date, recent vs rolling-21d peak,
  swing-length shift, fast-swing-rate drop) lands at **partial-r ≈ 0.02–0.05,
  all p > 0.04** against both the core-FP/PA proxy and forward xwOBA/PA, over
  n≈1,513 batter×cutoff rows. After controlling for to-date contact quality +
  to-date production, intra-season bat-speed dips carry **no forward signal**.
- **The downside bust-gap is ≈ 0.** The worst-20% bat-speed-vs-peak decliners
  (n=303) match the rest on forward outcome (gap −0.0001 / −0.0003 proxy units)
  and bust at essentially the same rate (~27% vs ~24%). No "avoid bad days" edge.
- **The only ember is the YoY (2024→2025 season-mean) bat-speed delta:**
  raw-r ≈ 0.10 (p≈0.005–0.009), but it **decays to partial-r ≈ 0.065–0.07
  (p≈0.06–0.08) once you control for to-date level** — i.e. not significant,
  and it's a SEASON-over-SEASON gainer/decliner signal, not the
  daily/L21d "decline" lens we were probing. Stable to outlier filtering
  (no |delta|>6 rows survived the PA floors). Worth a second look with another
  bat-tracking season, but it is **not the SP-velo analog** — it's a slow,
  annual stuff-level shift, and it's weak.

Why this differs from SP velo decline:

- SP velo is a **direct stuff input** and intra-season velo loss is a known
  injury/fatigue tell. Hitter bat_speed is far more **selection-driven** (count,
  pitch type, take-vs-swing decisions), so a short-window bat-speed "dip" is
  mostly swing-decision mix, not a talent change — which is exactly what the
  null partial-r shows.

Honesty / caveats (load-bearing):

- **2-year coverage only** (bat-tracking starts 2024; 2026 partial, excluded as
  a cutoff year). Treat ALL of this as directional, NOT validated.
- **Forward target is a proxy** — `(TB+BB+HBP−K)/PA` + xwOBA/PA, because
  pitch-level Statcast has no R/RBI/SB. The bat-driven core is captured; the
  baserunning/context tail is not.
- Partial-r is the load-bearing number; raw-r is inflated because good hitters
  both swing faster and produce more.
- **Do NOT add any of these to rh3.** This is EXPLORATORY; even the YoY ember
  would need `/validate-feature` with the full Rule-9 production baseline and
  ≥1 more bat-tracking season before it could be considered.
