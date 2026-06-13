# RP decline signal — does velo (level/decline) beat whiff/K-level? — 2026-06-13

**Question.** For SPs we found the rest-of-season-decline predictor is whiff/K
**LEVEL** (SwStr%/K% percentile, partial-r +0.235), not recency deltas; velo was
only modest (+0.16) (`sp_decline_stuff_decay_2026-06-13.md`). **Hypothesis for
RPs:** velocity matters MORE — max-effort one-inning arms have no pace-managing
fallback, so a velo drop is a louder alarm. Tested, not assumed.

**Verdict — HYPOTHESIS CONFIRMED (qualified).** For relievers, **velocity DECLINE
(YoY) is the strongest *stuff* signal of rest-of-season FP decline (partial-r
+0.112, 95% CI [+0.052, +0.166]) and beats every whiff/K/velo LEVEL percentile.**
This **reverses the SP finding**, where LEVEL dominated and velo-delta was weak.
Crucially it is *velo* decline specifically — swStr-decline and K-decline YoY are
NOT significant (CIs cross zero). Velo LEVEL alone is weak (+0.064). So the RP
story is "velo TRAJECTORY," not "velo level" and not "whiff trajectory."

> Caveat on magnitude: the single best raw term is `fp_recent_vs_todate` (+0.147)
> — a recent-window-FP-vs-season-rate momentum term, i.e. the recency baseline,
> **not a stuff signal.** Among engineered stuff/velo signals, velo-decline wins.

## Method (leakage discipline — the lens_value_add lesson)
- Panel: `rolling_relievers_2018_2026.csv`, as-of-split cumulative `_to` features
  + `avg_velo_to` (level). Prior-year velo / swStr / K / archetype slope joined
  from `rp_archetype_career_panel.parquet` **on the completed prior season only**.
- Target: **RoS FP per appearance** = (`fp_year_total` − cum-FP-to-date) /
  estimated remaining appearances (g_to scaled by remaining-season fraction;
  target winsorized 1/99 pct). Filters: g_to≥8, est. g_rest≥5, tbf_to≥30 →
  **37,400 split-rows, 1,032 unique RPs** (velo-YoY subset n=19,275, 56% coverage).
- LEVEL signals = **percentile within split-day** (cross-sectional, leakage-safe).
- **Incremental partial-r over a Rule-9 base** = {to-date FP/app, skill FP/app,
  sv/g, hld/g, role_closer, role_setup} — so stuff isn't just proxying SAVE/HOLD
  role (the role/leverage agent owns that component). Player-clustered **GroupKFold(5)**
  (no reliever in train+test). Cluster-bootstrap 95% CIs (400 reps). Per-appearance
  RoS FP is the SKILL-leaning target; the +5·SV / +2·HLD role component is largely
  carried by the role base controls.

## Ranked signal table (by |partial-r| over base)
| signal | n | partial-r | 95% CI | ΔR² | decline-AUC | AUC-incr |
|---|---|---|---|---|---|---|
| fp_recent_vs_todate (recency baseline, not stuff) | 32,755 | **+0.147** | [+.119,+.173] | +.020 | 0.739 | +.009 |
| **velo_DECLINE_yoy** | 19,275 | **+0.112** | **[+.052,+.166]** | +.010 | 0.740 | +.009 |
| xwoba_LEVEL_pct (lower=better) | 32,755 | −0.107 | [−.138,−.075] | +.010 | 0.736 | +.006 |
| k_LEVEL_pct | 32,755 | +0.089 | [+.055,+.126] | +.007 | 0.736 | +.006 |
| archetype_OVERALL_slope_py | 11,606 | +0.076 | [+.015,+.140] | +.004 | 0.705 | +.003 |
| csw_LEVEL_pct | 32,755 | +0.074 | [+.043,+.106] | +.005 | 0.734 | +.003 |
| swstr_LEVEL_pct | 32,755 | +0.069 | [+.037,+.107] | +.004 | 0.734 | +.004 |
| velo_LEVEL_pct | 32,755 | +0.064 | [+.029,+.101] | +.003 | 0.730 | −.001 |
| swstr_minus_fp_gap | 32,755 | +0.054 | [+.019,+.090] | +.002 | 0.734 | +.004 |
| swstr_DECLINE_yoy | 19,275 | +0.033 | [−.017,+.079] **n.s.** | −.000 | 0.732 | +.001 |
| bb_LEVEL_pct | 32,755 | −0.031 | [−.066,+.004] **n.s.** | −.000 | 0.730 | +.000 |
| k_DECLINE_yoy | 19,275 | +0.020 | [−.026,+.069] **n.s.** | −.000 | 0.731 | +.000 |

"Material-decline" flag = RoS FP/app falls ≥1.5 below to-date FP/app (base rate
18.2%). All AUCs are full-model (base already ≈0.73); increments are small because
the role/recency base is strong — read the **partial-r** column as the signal test.

## Why this is a real reversal of the SP result (not an artifact)
1. **Head-to-head survival.** velo_DECLINE_yoy retains **partial-r +0.092** even
   when the base ALSO contains k-LEVEL + swStr-LEVEL + velo-LEVEL simultaneously
   (n=19,275, ΔR² +0.006). The stuff-LEVEL signals do **not** subsume it.
2. **Direction correct.** Full-fit velo_yoy coef **+0.168** (velo gain → higher RoS
   FP; velo drop → decline); corr(velo_yoy, decline_flag) = −0.081.
3. **Velo trajectory, not whiff trajectory.** swStr-YoY and K-YoY decline are
   insignificant — so it is specifically the radar-gun drop that flags RP decline,
   matching the max-effort mechanism in the hypothesis.
4. **Convergence / leakage check (partial-r by split-day bucket):**
   - velo_DECLINE_yoy: early +0.073 / mid +0.108 / late +0.095 / v.late +0.097 —
     **stable, no early-season inflation** (a YoY signal can't leak).
   - k_LEVEL: +0.127 early → +0.052 v.late — **decays**, partly small-sample early
     (consistent with SP "level" being noisier in RP-sized samples late-season).
   - velo_LEVEL & swStr_LEVEL: flat-to-decaying, all weak.

## Important framing — skill vs role
BrownU RP FP = K + IP·3.3 − H − 2ER − BB − HBP + **5·SV + 2·HLD**. The save/hold
component is **role-driven** and is handled by the separate role/leverage agent;
here it is absorbed by the sv/g, hld/g and role-dummy base controls so the stuff
signals are measured against the **skill** component. The velo-decline signal
predicts the SKILL slice of RoS FP decline — combine with the role agent's
leverage/closer-tenure read for the full RP picture, don't double-count.

## Takeaways for the model / boards
- **For RPs, prefer velo-TRAJECTORY over whiff/K-LEVEL** when flagging decline —
  the opposite default from `/sp-stuff-board` / `/sp-decline`. A high-Stuff/K RP
  whose velo is down YoY is a louder decline alarm than one whose K% percentile slips.
- Velo-decline is a candidate **Tier-B conviction/conflict gate for rprs2** (per
  feedback #13: surface conviction, don't move the headline). It is NOT yet
  promoted — `/validate-feature` Rule-9 run vs the live rprs2 production features
  would be required before it drives a rank. Coverage is also only 56% (needs a
  prior MLB season of velo), so it's an *augment-when-available* signal.
- xwoba_LEVEL (−0.107) is the best contact-quality LEVEL term and roughly ties
  velo-decline; a velo-decline + soft-xwoba pairing is the cleanest RP decline duo.

Engine: `scripts/research/rp_decline_stuff_velo_2026-06-13.py` ·
table CSV: `rp_decline_stuff_velo_table.csv`
