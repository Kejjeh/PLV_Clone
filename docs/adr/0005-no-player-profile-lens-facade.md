# No `player_profile()` lens facade — lean skills want subsets, model_row is today-coupled

An architecture review flagged that `scripts/xfp/lib/triangulate_core.py::model_row` — the assembler that bolts ~8 display lenses (boom_stack, hitter_boom_stack, sustainability, blend, catcher_framing, il_return, recform, pl_rank) onto a projection — has exactly one caller (`run_triangulate.py`), while other skills (`run_fa_monitor`, `stream_the_stack`, the slate grids) re-import lens subsets directly. The instinct was a thin `lib/player_profile.py` facade: `profile(name_or_id, bucket) -> dict` = `resolve_player(name)` then `model_row(p)`, so every skill consumes one lens-stack interface.

**Decision:** Do not build the facade. Skills that need a lens call the specific lens module (`compute_boom_stack`, etc.) or `model_row` directly.

## Why

- **Deletion test fails — it's a pass-through.** `profile()` is two lines (`p = resolve_player(name, hint); return model_row(p) if p else None`). Deleting it concentrates no complexity; callers just write those two lines. A module whose interface is as large as its implementation is shallow by definition.
- **The lean skills want different subsets, by design.** `stream_the_stack` uses `compute_boom_stack` *only* — its entire purpose is the boom-tier filter; routing it through `model_row` would over-fetch 7 unused lenses (each doing CSV reads / today lookups). `run_fa_monitor` uses no lens stack at all — it does raw rank matching deliberately. There is no shared "everyone wants the full stack" need for a facade to serve.
- **`model_row` is coupled to live "today" context.** It calls `resolve_opp_sp_id_for_today(...)`, so its output depends on the current schedule — it is not a pure function of the player. A facade named `profile()` would imply a stable, reusable player record that it isn't.
- **The lens stack is display-only (feedback #13 / `reference_lens_merge_protocol.md`).** Validated 2026-06-11: the multi-lens synthesis does NOT beat the base rank at point-forecasting; lenses earn their keep as conviction/conflict surfacing, never as additive lift. A reusable `profile()` would invite callers to treat the assembled stack as a richer projection and move headline numbers with it — exactly the misuse the feedback rule forbids.

## Considered and rejected

- **Thin `profile()` facade over `resolve_player` + `model_row`.** Rejected per the deletion test — a pass-through, not a deep module.
- **Migrate the lean skills onto `model_row` for uniformity.** Rejected as over-fetching — `stream_the_stack` would compute 8 lenses to use 1; `run_fa_monitor` would compute 8 to use 0.
- **Make `model_row` pure (drop the today-coupling) first, then facade it.** Larger, riskier change to a working triangulate engine for a display-only output whose value is already capped by feedback #13. Not worth the blast radius.

## Consequence

The lens duplication across skills is accepted as intentional variation, not friction to consolidate. A future architecture review that re-surfaces "unify the lens stack behind a facade" should stop here: the candidate was evaluated and the lean-skill subsets + today-coupling + display-only constraints make it a shallow, misuse-inviting abstraction.
