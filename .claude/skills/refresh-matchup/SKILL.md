---
name: refresh-matchup
description: Rebuild the weekly matchup dashboard (matchup.html) and publish it to GitHub Pages via the xfp-model sibling repo. Lighter than /refresh-and-commit-and-push (no statcast pull, no model rebuild) — just rerun build_matchup_dashboard.py, sanity-check the output, commit both repos, push. Use whenever the user asks to "update the matchup page", "refresh the matchup dashboard", "ensure matchup reflects this week", or after roster/IL changes that need to flow into projections.
---

# refresh-matchup

You are rebuilding the H2H matchup dashboard for the current scoring
week and publishing it to GitHub Pages.

The skill exists because the matchup dashboard is the user's primary
weekly-decision surface, and stale projections lead to wrong bench/start
calls. The build is fast (~30s) — should be run whenever:
- A new scoring week starts (Monday)
- A roster change happens (add/drop, IL transaction)
- Confirmed probable pitchers update (mid-week)
- The user asks to verify projections

This is the LIGHT refresh — for the full daily ritual (statcast pull +
model rebuild + dashboard rebuild) use `/refresh-and-commit-and-push`.

---

## Inputs

No required inputs. Optional:
1. **Commit message override** — if the user wants a specific reason
   logged (e.g., "after Donovan IL update")
2. **Skip push?** — default = push to both repos. Only skip if user
   explicitly says "build only, don't push"

---

## Step 1 — Run the build

```bash
python -X utf8 scripts/xfp/build_matchup_dashboard.py
```

The script:
1. Loads ESPN matchup period + scoring (WTD)
2. Fetches MLB Stats API schedules for all 30 teams (week window)
3. Projects each rostered player: hitters per-game with opp-SP factor,
   SPs with rotation-gap fallback for unconfirmed late-week,
   RPs with role-based appearance rate
4. Applies 10-SP-start cap (sort by FP desc, zero excess)
5. Computes win probability from projected gap + combined variance
6. Logs the prediction to `predictions_history.csv` (one row per build)
7. Writes to BOTH `data/outputs/matchup.html` AND `xfp-model/docs/matchup.html`

Expected runtime: 20-45 seconds (depending on MLB Stats API responsiveness).

---

## Step 2 — Sanity-check the output

After the build, validate the projection looks reasonable:

```bash
grep -E "Win probability|WIN by|LOSS by|SP cap|probable starts" \
  xfp-model/docs/matchup.html | head -10
```

Red flags to surface:
- **Win prob > 98% or < 2%** — usually means a real signal but verify
  no projection bugs (e.g., opponent under-projected due to MLBAM
  lookup miss). Spot-check the opponent's SP count.
- **SP cap message says "Only N probable starts" with N < 7** — likely
  the rotation-gap predictor is failing for some pitchers. Run
  `/matchup-audit` to identify which.
- **Any IL'd player shows non-zero FP projection** — the IL filter
  failed. Check the player's row in matchup.html.
- **WTD = 0.0 for both teams** — ESPN matchup data didn't load. Build
  may be invalid; rerun in a few minutes.

If any red flag fires, **stop and run `/matchup-audit` before
committing** — committing a broken dashboard misleads the user.

---

## Step 3 — Verify the day-of-build context

The matchup dashboard auto-detects the scoring week from ESPN. Confirm
the build output matches the user's expected week:

```
week: 2026-05-18 → 2026-05-24 (today: 2026-05-19)
```

If the date range looks wrong (e.g., last week's window, or off by a
day), the matchup period parsing has drifted. Don't commit until
investigated.

---

## Step 4 — Commit xfp-model (the GitHub Pages source)

The user's `xfp-model/` sibling repo serves GitHub Pages at
https://kejjeh.github.io/xfp-model/matchup.html

```bash
cd xfp-model
git add docs/matchup.html
git commit -m "refresh: matchup dashboard for Week N (date range)

[1-2 sentence body: projection result, win prob, key context]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

Use a HEREDOC for multi-line message (avoid PowerShell quoting issues).

---

## Step 5 — Commit plv_clone (mirror)

The build also writes `data/outputs/matchup.html` (mirror) and appends
a row to `data/outputs/predictions_history.csv`. Commit both:

```bash
cd ..  # back to plv_clone root
git add data/outputs/matchup.html data/outputs/predictions_history.csv
git commit -m "refresh: matchup.html + predictions log for Week N

Mirrors the xfp-model push (<sha>).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

If the build also modified `scripts/xfp/build_matchup_dashboard.py`
(e.g., bug fix included in this run), bundle the script change into
the plv_clone commit with appropriate commit message style.

---

## Step 6 — Report back

```
✓ Matchup dashboard rebuilt for Week N (date range)
  Ligers WTD <X> + projected <Y> = total <Z>
  Opp    WTD <X> + projected <Y> = total <Z>
  Result: WIN/LOSS by <margin> at <win_prob>%
  SP cap: <N>/10 probable starts

  xfp-model: <sha> pushed → https://kejjeh.github.io/xfp-model/matchup.html
  plv_clone: <sha> pushed
```

Surface any noteworthy items from the build:
- 2-start pitchers flagged
- Players capped out of the 10-start budget
- Action items the dashboard generated (injuries, lineup conflicts)
- Specific bench-the-worst-start recommendations

---

## Anti-patterns this skill exists to prevent

- **Committing a broken dashboard.** Always sanity-check Step 2 before
  pushing. A broken matchup.html on GitHub Pages misleads the user's
  weekly decisions until next refresh.
- **Forgetting the sibling repo.** xfp-model is what GitHub Pages
  serves. plv_clone is the mirror. Push BOTH or the public page is
  stale.
- **Skipping the build entirely and just committing stale matchup.html.**
  If the file is "modified" but the build wasn't rerun, the commit
  doesn't reflect current data.
- **Running the full refresh ritual when only matchup needs updating.**
  /refresh-and-commit-and-push pulls statcast + rebuilds models — that's
  3-30 minutes. This skill is 30 seconds.
- **Pushing during a build error.** If the script exits non-zero,
  matchup.html may be partially written or unchanged. Do NOT commit.
  Investigate first.
- **Trusting WTD = 0.0 silently.** ESPN matchup endpoint can return
  empty data mid-day during scoring updates. Wait 10 minutes and retry.

---

## When NOT to use this skill

- Daily refresh ritual (statcast + model rebuild) — use
  `/refresh-and-commit-and-push` instead
- Bug investigation in the build script — use `/matchup-audit` to
  identify what's wrong before rebuilding
- One-off projection check (no commit needed) — just run the build
  script directly without pushing
- After a roster transaction that hasn't yet propagated to ESPN
  (check `get_my_roster()` first — if the new player isn't showing,
  matchup will project the old roster)
