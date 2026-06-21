# Player-analysis skills consolidation: what is shared, what stays separate

An architecture review (2026-06-21) of the player-analysis skills (triangulate,
sustainability, decline, stuff-board, floor) proposed consolidating four
cross-cutting concerns. Verifying-before-executing (an 8-agent adversarial
workflow + equivalence checks) pared the proposal down. This ADR records what was
consolidated and — more importantly — what was deliberately **left separate**, so
a future review does not re-propose the rejected merges.

## Decisions

**1. Name normalization has TWO legitimate concerns — do not force-merge them.**
- The **projection-join key** (orderless, accent-stripped, sorted tokens) is
  `name_match.join_key`. `pitcher_sustainability._norm` and
  `hitter_sustainability._norm` were byte-identical to it and were migrated onto
  it (C1). New projection-join code should import `join_key`.
- `sp_stuff_model._norm` (ESPN-roster ownership, order-/space-preserving, two-pass
  full-name → last+initial fallback) and `lib/bucket_dispatch._norm` (triangulate's
  resolver) are **different normalizations for different jobs**, NOT copies of the
  join key. They were verified non-equivalent to `join_key` and left alone. A
  future "merge all the `_norm`s" suggestion should stop here.

**2. The PL-cache reader (`lib/pl_cache.py`) is already where it belongs.**
The review proposed routing "all PL-consuming skills" through it. Verified a
mirage: the canonical consumers (triangulate, positional_board) already use it;
`sp-stuff-board` uses FanGraphs Stuff+ (not PL), and `stream-the-stack` /
`pl-cross-reference` / `sp-stash-finder` **WebFetch live PL articles** — a
different operation, not a cache read to consolidate. The only genuine inline
duplicate is `run_positional_board.py::load_pl_ranks` (a minor, optional tidy).
Do not re-propose a blanket pl_cache adoption.

**3. The Sustainability seam is a toolkit (C3+C4), not a deep core.**
The two sustainability engines shared identical logic differing only by scale:
the 7-bucket classifier (C3 → `verdict_tiers.classify_sustainability`) and the
`divergence_signal` + `ros_expectation` functions (C4 → `verdict_tiers`,
parametrized by threshold + model label; scale-free ROS scalars). These are pure,
parametrized helpers (ADR-0001 toolkit posture) — NOT a `classify_player(decomp,
role_spec)` deep core with strategy callables, which ADR-0006 already rejected as
config-as-code for the sibling snapshot subsystem. The engines keep their own
9-marker decomposition, cache loaders, and baseline semantics. Do not re-propose a
deep `sustainability_core` / `RoleSpec`.

## Lesson recorded (operational)

A scripts/xfp engine that imports a sibling `lib` module must do so in a way that
resolves under BOTH run contexts: direct script execution (`scripts/xfp` on
`sys.path`) AND package import (`from scripts.xfp.<engine> import …` with only
ROOT+src on path, as `league_wide_full_audit` does). C3 initially used a bare
`from lib.verdict_tiers import …` which crashed the package path (tests passed only
because they add `scripts/xfp` explicitly). Fix: fully-qualify
(`from scripts.xfp.lib.<mod> import …`) relying on the `sys.path.insert(0, ROOT)`
each engine already runs. A subprocess regression test
(`tests/test_sustainability_engines.py`) pins this.

## Consequence

Future reviews: the genuinely-shared scouting/verdict math lives in
`lib/archetype_engine` + `lib/verdict_tiers` (the toolkit). The per-role engines
compose it. The remaining "duplication" (the `_norm` variants, per-skill PL fetches)
is intentional variation reflecting different jobs — evaluated and kept separate.
