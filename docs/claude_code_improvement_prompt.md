# Claude Code Improvement Prompt
# Copy everything below the line and paste into Claude Code / VS Code terminal chat

---

You are working inside the `plv_clone` fantasy baseball analytics project. Before doing anything, read these two files completely:

1. `docs/model_audit_and_roadmap.md` — the authoritative list of known bugs, their root causes, and exact fixes
2. `AGENTS.md` — the change-gating rules you must follow (scope discipline, high-impact file list, confirmation requirements)

Work through the audit document **one phase at a time**. Do not proceed to Phase 2 until Phase 1 is complete and validated. After each change, run the relevant tests and confirm the sanity checks listed in Section 8 of the audit doc before moving on.

---

## Phase 1 — Critical Bug Fixes

### Task 1a: Fix `plv_blended` (BUG-01)

The `plv_blended` field in the pitcher output is currently identical to `plv` (current-year only). The historical blending was never wired up. Fix it as follows:

- Load pitcher-season PLV history from `statcast_2023.parquet`, `statcast_2024.parquet`, `statcast_2025.parquet`
- Compute per-pitcher mean PLV for 2023–2025 (grouped by pitcher ID, min 200 pitches per season to qualify)
- Blend: `plv_blended = (plv_2026 * pitch_count_2026 + plv_history_mean * 600) / (pitch_count_2026 + 600)` — this is Bayesian shrinkage toward the 3-year mean, weighted so that 600 "prior pitches" anchor the estimate
- For pitchers with no 2023–2025 history (true rookies), `plv_blended = plv_2026` unchanged
- After fix, confirm: `plv_blended != plv` for veteran pitchers with multi-year history
- Sanity check: Max Fried's `plv_blended` should be noticeably higher than 4.825 after incorporating his 2022–2025 history

File to edit: `src/plv_clone/models/plv_model.py`  
High-impact file — list your planned changes and confirm before editing.

---

### Task 1b: Rename `xwoba_actual` → `xwoba_on_contact` (BUG-02)

The field `xwoba_actual` is misnamed. It contains xwOBA computed on batted balls only (contact-only denominator), not per-PA xwOBA as Savant defines it. This causes confusion when comparing to Baseball Savant leaderboards.

Steps:
1. Grep for every occurrence of `xwoba_actual` across the entire codebase
2. Rename to `xwoba_on_contact` everywhere — source code, output column names, dashboard references, any existing docs
3. Add a new field `xwoba_per_pa` computed as: `sum(woba_value where woba_denom==1) / count(woba_denom==1)` — this matches Savant's definition
4. After rename, run a grep to confirm zero remaining `xwoba_actual` references
5. Verify the dashboard loads without KeyError on the renamed column

Files likely affected: `src/plv_clone/models/process_plus_model.py`, `app/dashboard.py`, any output generation scripts  
Check `AGENTS.md` high-impact file list before editing.

---

### Task 1c: Remove `discipline_plus` from Process+ composite (BUG-03)

`discipline_plus` has a Pearson r of −0.017 with full_fp_per_pa (p = 0.738, not significant). It is diluting the composite's predictive power. 

Steps:
1. Remove `discipline_plus` as a weighted input to the `process_plus` composite score
2. Recompute `process_plus` weights on the remaining three components (contact quality, K-avoidance, in-play rate) — refit if the weights are learned, or renormalize if they are fixed
3. Keep `discipline_plus` as a standalone output column (it predicts BB rate reasonably well, r ≈ 0.55, and may be useful in OBP leagues) — just remove it from the composite
4. Regenerate `data/outputs/hitter_fantasy_2026.parquet`
5. After fix: recompute r(process_plus, full_fp_per_pa) — it should improve from 0.909 toward 0.92+

File to edit: `src/plv_clone/models/process_plus_model.py`  
High-impact file — confirm planned diff before editing.

---

### Task 1d: Rename `contact_plus` → `k_avoidance_plus` (ISSUE-07)

`contact_plus` measures whiff rate and chase rate — it is a K-avoidance metric, not a contact quality metric. The name actively misleads analysis. Power+ already captures contact quality.

Steps:
1. Rename the field `contact_plus` → `k_avoidance_plus` everywhere in source, outputs, and the dashboard
2. Update the dashboard label from "Contact+" to "K-Avoidance+"
3. Update `docs/fantasy_points_methodology.md` to reflect the rename
4. Confirm no remaining `contact_plus` references after rename

This is lower-risk than 1a–1c but still requires updating the dashboard and output schema.

---

## Phase 2 — Missing Context (run after Phase 1 is complete and validated)

### Task 2a: Add positional z-scores for hitters (ISSUE-04)

Hitters are currently ranked on absolute process_plus values with no positional adjustment. A catcher at proc+103 is elite at the position but ranks average league-wide — the model can't tell the difference.

Steps:
1. Join player position data from `data/models/player_positions_*.json` at hitter output generation time
2. Compute `proc_plus_positional`: the player's process_plus z-score *within their position group* (C, 1B, 2B, 3B, SS, OF, DH), then scale to the same 0–200 range as the overall Process+
3. Add `proc_plus_positional` as an output column alongside the existing absolute `process_plus`
4. Do not remove or replace `process_plus` — keep both columns
5. Sanity check: Iván Herrera (C, proc+103) should rank top-15 among catchers on `proc_plus_positional`

File: `src/plv_clone/fantasy/hitter_points.py`  
High-impact file — confirm scope before editing.

---

### Task 2b: Multi-year blending for hitters (ISSUE-05)

Current hitter metrics use 2026 data only. With <150 PA in early season, this is very noisy.

Steps:
1. Load 2024 and 2025 per-player season aggregates (whiff_pct, chase_pct, in_play_pct, xwoba_on_contact) from the existing statcast parquets
2. For each hitter, blend current-year rates with prior-year rates using PA-weighted Bayesian shrinkage: `blended_rate = (rate_2026 * pa_2026 + rate_prior * 300) / (pa_2026 + 300)` — 300 PA of prior history as the anchor
3. Use blended rates as inputs to the Process+ and rate estimation models
4. Add a `blend_weight` output column (0–1) showing how much current-year data is driving the estimate — low early season, approaching 1.0 by September
5. Sanity check: Players with <100 PA in 2026 should show blend_weight < 0.25

---

### Task 2c: Numeric save/hold estimates (ISSUE-06)

`sv_upside` and `hd_upside` are currently string labels ("role-dependent"), not numbers. A closer generates +5 FP/save × ~30 saves = 150 bonus FP per season — larger than the entire PLV-derived FP/IP spread for many pitchers.

Steps:
1. Use the `pitcher_role` field and any closer/setup role data in `data/models/player_positions_*.json` to assign estimated save/hold counts:
   - Primary closer: est_sv = 28, est_hd = 0
   - Setup/high-leverage RP: est_sv = 2, est_hd = 18
   - Middle reliever: est_sv = 0, est_hd = 8
   - SP: est_sv = 0, est_hd = 0
2. Add `est_sv_per_162` and `est_hd_per_162` as numeric output columns
3. Add `sv_hd_fp_per_162` = (est_sv × 5) + (est_hd × 3) as a combined FP contribution from saves/holds
4. Do NOT bake sv/hd into the base fp_per_ip — keep it as a separate additive column so the pure stuff ranking (PLV) remains clean

---

## After All Phases: Final Validation Checklist

Run these checks after completing all tasks:

```
# 1. Correlation regression — process_plus should improve after Discipline+ removal
python3 -c "
import pandas as pd
from scipy.stats import pearsonr
df = pd.read_parquet('data/outputs/hitter_fantasy_2026.parquet')
r, p = pearsonr(df['process_plus'], df['full_fp_per_pa'])
print(f'process_plus r={r:.4f} (expect > 0.91)')
# k_avoidance_plus should exist, contact_plus should not
assert 'k_avoidance_plus' in df.columns, 'rename failed'
assert 'contact_plus' not in df.columns, 'old name still present'
assert 'xwoba_on_contact' in df.columns, 'xwoba rename failed'
assert 'xwoba_actual' not in df.columns, 'old xwoba name still present'
assert 'proc_plus_positional' in df.columns, 'positional z-score missing'
print('All column checks passed')
"

# 2. PLV blending check
python3 -c "
import pandas as pd
df = pd.read_parquet('data/outputs/pitcher_fantasy_2026.parquet')
veterans = df[df['pitches'] > 400]
diff = (veterans['plv_blended'] - veterans['plv']).abs()
print(f'PLV blend diff > 0 for {(diff > 0.01).sum()}/{len(veterans)} veteran pitchers')
fried = df[df['player_name'].str.contains('Fried', na=False)]
print('Max Fried plv:', fried['plv'].values, 'blended:', fried['plv_blended'].values)
"

# 3. Dashboard loads without error
python3 -c "import app.dashboard; print('dashboard import OK')" 2>&1 | head -5

# 4. No xwoba_actual references left
grep -r 'xwoba_actual' src/ app/ scripts/ && echo 'FAIL: references remain' || echo 'PASS: no references'

# 5. No contact_plus references left  
grep -r 'contact_plus' src/ app/ scripts/ && echo 'FAIL: references remain' || echo 'PASS: no references'
```

---

## Scope Reminder

Per `AGENTS.md`: list planned file changes and confirm before editing any high-impact file. Do not fix things you notice along the way that aren't in this list. If you find a related issue, note it but do not fix it without asking.

Do not change PLV scoring math, Process+ scoring math, or fantasy point formulas beyond what is explicitly described above.
