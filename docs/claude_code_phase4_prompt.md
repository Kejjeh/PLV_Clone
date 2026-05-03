# Claude Code — Phase 4 Priority Prompt

Read `docs/model_audit_and_roadmap.md` before starting. Phases 1–3 are complete.
Two tasks only. Do them in order.

---

## Task 1 — Verify in-play rate denominator (ISSUE-09)

Find where `in_play_pct` is computed in `src/plv_clone/models/process_plus_model.py`.
Print the exact numerator and denominator.

The correct formula is:
  `in_play_pct = count(batted balls in play) / sum(woba_denom == 1)`

If the denominator is not `woba_denom == 1` (i.e. it's using all pitches with launch data
instead of PA-ending contacts only), fix it. The league average `in_play_pct` should
land around 0.28–0.32. If it's materially higher, the bug is confirmed.

Report what you find. If a fix was needed, say so and show the before/after.

---

## Task 2 — Regenerate 2026 outputs

Phases 1–3 changed the pipeline. Run the full export for 2026 so all downstream
analysis reflects the fixed model:

  plv score-process 2026
  plv export hitters 2026
  plv export pitchers 2026

If the pipeline commands differ, check `scripts/` or `CHANGELOG.md` for the correct
invocation. Confirm the output parquets are fresh (mtime or row count).

After regenerating, spot-check three things and report the numbers:
1. Max Fried — `plv_blended` should be > 4.825
2. Iván Herrera — `proc_plus_positional` should rank him top-tier among catchers
3. Any closer (e.g. Tanner Scott) — `sv_hd_fp_per_162` should be ~140

---

That's it. No other changes.
