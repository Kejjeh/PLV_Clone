# RP Decline — Role / Leverage Erosion Backtest (2026-06-13)

**Question.** RP fantasy value is opportunity-dominated (rprs2 r≈0.87 vs rp3 0.55
because saves/holds = role, not per-batter skill). So does **role / leverage
erosion** — not rate regression — predict a reliever's rest-of-season (RoS) FP
crater? And is role loss **predictable**, or largely a manager-driven coin-flip?

**Data.** `xfp_cache/rolling_relievers_2018_2026.csv` (56,308 pitcher-year-split
rows, 2018–2026, 24 weekly as-of splits). RoS outcomes built by differencing
full-season totals minus cumulative-to-date (`fp_year_total − fp_with_role_to`,
etc.). Recent-window (≈14d) rates from differencing the cumulative `_to` value 2
splits prior. Target FP = role-FP per appearance (the rprs2 currency).

**Leakage discipline (lens_value_add lesson).** As-of split features ONLY;
player-clustered `GroupKFold(5)` (cluster = pitcher); **incremental** partial-r
over an rprs2-style base (to-date role-FP-rate + sv/hld share + GF%), Rule 9
baseline carries the production drivers; cluster-bootstrap 95% CIs (800 reps);
split-day convergence check.

---

## 1. Does role-loss actually crater RP FP? (YES — the thesis core holds)

Define **ROLE-LOSS** = a reliever who *had* a role to lose (to-date
save+hold per appearance ≥ 0.15, ≈ closer/setup tier) whose **RoS** save+hold
share falls **≥40% below** his to-date level (a material opportunity crater, not
noise).

| Group | RoS FP / appearance | n |
|---|---|---|
| ROLE-LOSS | **2.49** | 4,849 |
| No loss | **4.01** | 11,804 |
| **Crater** | **−1.51 FP/app (−38%)** | t-test p ≈ 0 |

Holds in the early/mid window (split ≤ 114, ≥ 60d RoS runway — i.e. NOT a
late-season short-RoS artifact): LOSS 2.39 vs NO-LOSS 3.84 = **−1.45 FP/app**.

**Verdict 1: role loss is the dominant FP-crater mechanism for relievers.** A
RP who keeps his role averages ~4 FP/app; one who loses it drops to ~2.5 — a
38% haircut, far larger than any rate-regression effect on per-batter skill.

---

## 2. Incremental signal table — role/leverage TRENDS over the rprs2 base

Sample: n = 24,086 (g_to≥8, RoS≥5 apps, valid recent window), 868 unique
pitchers, role-loss base rate 0.199. Partial-r = OOS-residual correlation of the
signal vs RoS FP/app after removing the rprs2-style base.

| Signal | partial-r | 95% CI | AUC (role-loss) | leakage flag |
|---|---|---|---|---|
| `sv_share_trend` (sv/g recent − to-date) | **0.073** | [0.057, 0.088] | 0.571 | late-window inflated |
| `g_per_split_to` (appearance rate) | 0.060 | [0.039, 0.083] | 0.548 | — |
| `gf_pct_trend` (games-finished % trend) | 0.060 | [0.044, 0.075] | 0.520 | — |
| `svhld_trend` (combined leverage-opp trend) | 0.045 | [0.032, 0.061] | 0.578 | late-window |
| `closer_loss` (was-closer × recent collapse) | 0.043 | [0.029, 0.057] | 0.524 | — |
| `lev_to` (to-date leverage opportunity LEVEL) | 0.017 | [−0.014, 0.048] n.s. | **0.688** | — |
| `hld_share_trend` | −0.004 | [−0.017, 0.011] n.s. | 0.552 | — |

**Incremental model fit over the rprs2-style base:**
- RoS FP/app OOS R²: base 0.092 → +role/leverage signals 0.100 (**ΔR² = +0.0075**)
- Role-loss flag OOS AUC: base 0.732 → +signals 0.745 (**ΔAUC = +0.013**)

The trends add **almost nothing incrementally**. Crucially, the single best
*level* predictor of the role-loss flag is `lev_to` — the **to-date leverage
LEVEL** (AUC 0.688) — which is *already inside rprs2*. The base alone hits
AUC 0.732 on the role-loss flag. **Role is the dominant axis, but the
predictive content lives in the current role STATE, not the recent trend.**

**Convergence-curve red flag.** The best trend signal (`sv_share_trend`) is a
near-pure late-season artifact — partial-r climbs +0.009 (split 30–65) →
+0.035 → +0.071 → **+0.146** (split 136–191). As RoS runway shrinks, "recent"
mechanically approaches "RoS." This is exactly the L7-leakage pattern
`lens_value_add` flagged. **Do not promote the trend as a point-forecast term.**

---

## 3. Is role-loss PREDICTABLE ahead of time, or a coin-flip?

OOS role-loss AUC (as-of features only, n=16,738, role-loss rate 0.292,
restricted to RPs with a to-date role and ≥10 RoS apps):

| Feature set | AUC |
|---|---|
| To-date role STATE only (svhld_to, sv/g, gf%) | 0.576 |
| + recent role TREND (svhld_rec) | 0.604 |
| **SKILL markers only** (K%, BB%, SwStr, xwOBA) | **0.652** |
| Role state + trend + skill (full) | **0.683** |

**Two findings that reframe the thesis:**

1. **Role-loss is only modestly predictable (best AUC 0.683).** That's
   meaningfully better than chance but far from deterministic — consistent with
   a **large manager-driven / stochastic component**. A coach yanking a closer
   after two blown saves, a deadline trade, a bullpen reshuffle: much of role
   loss is genuinely not forecastable from the pitcher's own line. **You cannot
   reliably front-run role loss; you can only tilt the odds.**

2. **SKILL markers predict role-loss BETTER than role-trend** (skill-only 0.652
   vs role-trend 0.604). Managers strip roles from RPs whose *underlying skill*
   has eroded. So **stuff/skill erosion is the LEADING INDICATOR of role loss,
   and role loss is the MECHANISM that craters FP.** They are not competing
   lenses — they are sequential links in the same causal chain:
   **skill erosion → manager pulls the role → FP craters.**

---

## Verdict

- **Does role/leverage erosion dominate for predicting RP FP DECLINE?**
  **Directionally yes, mechanically.** Role loss is the single largest FP-crater
  event for relievers (−38% / −1.5 FP/app), dwarfing per-batter rate regression.
  The opportunity axis is where RP value lives — confirming why rprs2 (role) >>
  rp3 (skill) for RPs.

- **But does the role/leverage *TREND* beat stuff as a *predictor*? No.** As an
  incremental point-forecast term over the rprs2 base, role/leverage trends add
  ΔR² +0.0075 and ΔAUC +0.013 — negligible, and the headline trend is a
  late-season leakage artifact. The predictive content of "role" is already
  captured by rprs2's to-date role STATE, not by a trend signal on top.

- **Is role loss predictable at all? Only modestly (AUC ≤ 0.68) — substantially
  a manager-driven coin-flip.** And the best *early-warning* lever is **skill
  erosion, not the role trend itself**: stuff leads, role lag-follows, FP
  craters. **Stuff and role are NOT competing lenses — they're the upstream
  cause and downstream mechanism of the same decline.**

### Actionable
1. **Headline stays rprs2** (role state). Do **not** add a save-share/GF% trend
   term to rprs2 as a projection driver — it's leakage-prone and non-additive.
2. **Use role-loss as a CONFLICT/CONVICTION gate, not a point forecast**
   (`lens_value_add` rule): when a rostered closer/setup shows BOTH eroding
   skill markers (K%↓, SwStr↓, xwOBA↑ — the OTHER agent's lens) AND early
   role-share slippage (GF%↓, sv/g↓), flag **ELEVATED ROLE-LOSS RISK → sell/avoid**.
   That two-lens convergence is the only configuration that materially beats the
   base (skill+role AUC 0.683 vs role-state-only 0.576).
3. **Accept irreducible uncertainty.** ~32% of the AUC gap to perfect is
   unrecoverable from the pitcher's own line — much of role loss is the manager.
   Size RP bets accordingly: opportunity is fragile and only partly forecastable.

---
*Engine: `scripts/research/rp_role_erosion_backtest.py`. Sig table CSV:
`_rp_role_erosion_sigtable.csv`. No git commit per instructions.*
