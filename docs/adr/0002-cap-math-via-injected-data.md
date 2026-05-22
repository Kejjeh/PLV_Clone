# cap_math takes MLB data as parameters; mlb_stats owns the fetch

`cap_math.weekly_sp_projection` needs MLB probables and MLBAM name resolution to project a week's SP starts under the 10-start cap. The one-call instinct is to have `cap_math` fetch internally so callers (matchup dashboard, `/sp-week-plan`, `/sp-bench-mc`) pass just a roster + dates.

**Decision:** `cap_math` accepts `WeekProbables` and `mlbam_lookup: dict[str, int]` as parameters. The MLB Stats API fetch lives in `src/plv_clone/mlb_stats.py` (`fetch_week_probables`, `resolve_mlbam`). Callers compose: `probables = mlb_stats.fetch_week_probables(...); starts = cap_math.weekly_sp_projection(roster, ..., probables, ...)`.

## Why

The whole point of extracting `weekly_sp_projection` from `build_matchup_dashboard.py` is to make the four known bug patterns (IL'd projected, mlbam=None false-positive, today excluded, undercount) **structurally unspeakable**, with tests at the new interface verifying it. A `cap_math` that hits MLB Stats API directly is a deep module with a hidden remote dependency — the tests that verify the four mechanisms would all require API mocking, which defeats the testability win. With injection, tests pass literal `WeekProbables` and the four bug mechanisms are checkable against pure inputs.

## Considered and rejected

- **`cap_math` fetches internally** — one-call ergonomics, but hides a remote dependency from the interface and forces test infrastructure to mock the API.
- **Every caller fetches** — no shared seam, fetch logic duplicates across the matchup dashboard, sp-week-plan, sp-bench-mc.

## Two-adapter rule

Production: `mlb_stats.fetch_week_probables` hits the MLB Stats API.
Tests: literal `WeekProbables` constructed in-test.
Two adapters justify the seam.
