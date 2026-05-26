---
name: refresh-and-commit-and-push
description: Daily refresh ritual end-to-end — pull statcast, rebuild xFP models, regenerate dashboards, push xfp-model to GitHub Pages, commit regenerated outputs in plv_clone, optionally push plv_clone. Use whenever the user asks to "do the daily refresh", "ship the dashboard", "refresh and commit", or "refresh everything". Wraps refresh_dashboards.py + safe-commit so the user only has to ask once.
---

# refresh-and-commit-and-push

You are running the full end-of-day pipeline for plv_clone:
1. refresh data + models
2. regenerate dashboards
3. publish to GitHub Pages (via xfp-model auto-push)
4. commit the regenerated outputs in plv_clone
5. optionally push plv_clone

The script `scripts/xfp/refresh_dashboards.py` does steps 1-3 already
(and auto-commits + pushes the xfp-model sibling repo). This skill
wraps the remaining plv_clone commit + push that's easy to forget.

---

## Inputs

If the user gave these, use them. Otherwise default:

1. **Push plv_clone at end?** Default = no (just commit). Trigger
   push only if user's ask contained a push verb ("and push", "ship",
   "sync everything").
2. **Skip statcast?** Default = no. Add `--skip-statcast` if user
   says "use existing cache" or it's mid-day refresh.
3. **Skip model rebuild?** Default = no. Add `--no-models` if user
   says "just rebuild dashboards" — uses existing pkls.

---

## Step 1 — Run refresh_dashboards.py (background, monitored)

```bash
python -X utf8 scripts/xfp/refresh_dashboards.py
```

The script's 6 internal steps:
1. Refresh statcast (lag=1 day)
2. Rebuild all xFP models
3. Build live_dashboard.html
4. Build matchup.html
5. Commit xfp-model dashboards (local)
6. Push xfp-model → GitHub Pages

**Always run in background** (long: 3-30 min depending on model
rebuild). Use Monitor with this filter:

```bash
tail -f <output> | grep --line-buffered -E "^=+|^\s+[✓⚠]|^REFRESH|^ALL DONE|Traceback|Error|FAILED|→ live_dashboard|→ matchup"
```

Wait for the "ALL DONE" line (or Bash background-completion notification)
before proceeding. Halt and surface any `⚠` or `Traceback` event —
do not silently retry.

---

## Step 2 — Inspect plv_clone working tree

After the script completes, the model rebuild will have regenerated
many files in `data/outputs/`, `data/research/xfp_cache/`, and
possibly `data/models/`. Run:

```bash
git status --short
```

Common expected modifications:
- `data/outputs/live_dashboard.html`, `matchup.html` (always)
- `data/outputs/xfp_*_projections.csv` (always)
- `data/outputs/predictions_history.csv` (appended row)
- `data/outputs/{master,hitter,pitcher}_*.csv` (model-driven)
- `data/research/xfp_cache/*` (caches refreshed)
- Sometimes `data/models/*.json` if league config changed

Unexpected modifications (script files, unrelated configs) should be
surfaced for user review BEFORE committing — that means something
else changed outside the refresh.

---

## Step 3 — Commit via safe-commit skill (single-mode)

Invoke `safe-commit` to handle the plv_clone commit. The expected
flow is the simple single-commit case:

- Commit title: `refresh: regenerate dashboards + caches through <YYYY-MM-DD>`
- Use today's date (or the latest game_date in the statcast cache)
- Body should call out: today's live snapshot score + matchup win prob
  (read from the matchup.html output if easy, otherwise just the date)

Safe-commit will:
- Sensitive-scan (skip the recurring `.bak`)
- Stage by name (NOT `-A`)
- Verify
- NOT push by default

---

## Step 4 — Push plv_clone (only if user opted in)

If the user's original ask contained a push verb:

```bash
git push          # plain, never --force
```

(Safe-commit Step 7 handles this if you delegate the push to it.)

---

## Step 5 — Final report

```
Refresh complete:
  • Statcast through <date>
  • Models rebuilt in <X>s
  • Live snapshot: <Your Team> N vs <Opp> M (trailing/leading)
  • Matchup projection: <WIN/LOSS> by N at K% win prob
  • plv_clone: committed (<sha>) [+ pushed if applicable]
  • xfp-model: pushed (<sha>) — live at https://kejjeh.github.io/xfp-model/

Next checkpoints:
  • <returning IL player + date> if any
  • <forced-drop date> if SP cap will be hit
    Formula: forced-drop date = earliest return_date where (healthy_sp + 1) * 1.19 >= 10.
    At that date, pre-identified cut from bottom of rp3 rankings must be ready.
    Example: Glasnow Jun 15 (9 SPs → 10.7/wk) = forced drop by Jun 15; Fried Jun 16 = second cut.
```

---

## Anti-patterns this skill exists to prevent

- Running refresh_dashboards.py then forgetting to commit the
  regenerated plv_clone outputs (this happened multiple times
  before the skill existed).
- Pushing plv_clone without the user asking — push only on signal.
- Auto-retrying the refresh after an error — surface the error and
  let the user decide.
- Bypassing safe-commit and using `git add -A` to stage refresh
  outputs — sensitive files (recurring `.bak`) would slip in.

---

## When NOT to use this skill

- Working tree has unrelated uncommitted code changes — those should
  be committed separately first (use `/safe-commit` directly).
- User wants to skip parts of the pipeline (just rebuild dashboards,
  just commit, etc.) — use the individual scripts/skills directly.
- Mid-game inning when user wants live monitoring — use `live_monitor.py`
  in `--watch` mode instead.
