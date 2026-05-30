# Lessons from building `/triangulate`

The `/triangulate` skill (Pitcher List rank + projection model + archetype model, with batch
mode and parallel-agent dispatch) surfaced eight reusable design patterns. Each is captured
here with the problem it solves, the concrete triangulate implementation, how to apply it to
a new skill, and the anti-patterns to avoid. The closing section lists the structural
anti-patterns the build exposed across the broader skill library.

---

## Pattern A — Independent lenses with named failure modes

**What it solves.** "This player looks good" is unfalsifiable. Without independent sources
that can disagree, a skill can't tell you which signal is wrong when reality contradicts the
verdict. Triangulation only adds value when the lenses are genuinely independent and each
has a *named* failure mode you can point at when it misfires.

**Triangulate implementation.** Three lenses with different anchors and different blind
spots: Pitcher List rank (anchor: aggregated MLB perception; failure mode: rate-stat / 12-team
mindset), our projection model (anchor: per-PA validated regression; failure mode: stale on
in-season role changes), archetype model (anchor: 20-80 process ratings + historical comps;
failure mode: high-variance for low-PA tiers, comp scarcity for unusual profiles). The
diagnostic value lives in the *disagreement matrix*: when PL and model agree but archetype
disagrees, that's a process-vs-outcome story.

**How to apply.** For any new diagnostic skill: pick ≥2 sources with different anchors
(career vs recent, outcome vs process, internal vs external). Name each lens's failure mode
explicitly in SKILL.md. The verdict synthesis must reference *which lens fired*.

**Anti-patterns.** A "second opinion" that is actually the same data reweighted; lenses
without explicit failure modes ("triangulation" with three sources that all fail together);
hiding which lens drove the verdict.

---

## Pattern B — Verdict synthesis as named taxonomy

**What it solves.** "HOLD" tells the user nothing about *why* or what to do next. A named
verdict tier encodes the reasoning, so the follow-up action is obvious without re-reading the
analysis.

**Triangulate implementation.** 13 named verdict tiers including `BUY — archetype breakout`,
`BUY — model lags PL`, `SELL — outcome-driven peak`, `HOLD — three-lens consensus`,
`AVOID — comp scarcity`, etc. Each name fits the pattern `<ACTION> — <DOMINANT LENS>`. The
user reads the name and knows both the recommended move and the source of the conviction.

**How to apply.** Enumerate the cross-product of (action, dominant lens) ahead of time.
Reject any verdict string that doesn't include both. Document each tier with a one-line
rationale in the skill markdown. Keep the taxonomy stable across runs so the user builds
intuition.

**Anti-patterns.** Free-form verdict strings ("looks good", "consider it"); names that
encode action without lens; ad-hoc new tiers added per run that erode comparability.

---

## Pattern C — Layered rules (synthesize → overrides)

**What it solves.** As a skill matures, exceptions accumulate ("but if the archetype just
upgraded, don't sell"). Bolting these into the main rule function turns it into spaghetti and
makes regression-testing impossible.

**Triangulate implementation.** A pure `synthesize()` function produces the base verdict
from the three lenses. A second `apply_overrides()` layer runs after, and can *only* upgrade
bearish verdicts to neutral/bullish under specific named conditions (e.g.,
`archetype_just_upgraded`, `model_pre_role_change`). Each override is a single named
function with its own test. Synthesize never knows the overrides exist.

**How to apply.** Two-phase any skill where new exceptions arrive over time. Phase 1 is the
auditable base rule. Phase 2 is an ordered list of override predicates, each with a name
the verdict can cite (`HOLD — synthesize said SELL, overridden by archetype_just_upgraded`).
Adding a new override never touches prior logic.

**Anti-patterns.** A single `if/elif` cascade that mixes base reasoning and exceptions;
overrides that silently rewrite the verdict without surfacing which one fired; overrides
allowed to *downgrade* bullish calls (creates ambiguity about which layer "won").

---

## Pattern D — Batch mode as first-class

**What it solves.** Single-player skills get re-implemented as one-off scripts every time
the user wants a sweep. The sweep version drifts from the single-player version and the two
disagree on edge cases.

**Triangulate implementation.** The same entry point accepts `--names-file roster.txt
--csv-out triangulate_results.csv` and emits one row per player with every field the
single-player card uses. 1 player and 400 players run through identical code; only the
output formatter changes. Lets the skill scale from "deep-dive on Ohtani" to "score the
entire FA pool" without a parallel codebase.

**How to apply.** Retrofit existing single-player skills by lifting the per-player logic
into a function that returns a dict, then add `--names-file/--csv-out` flags that map over
it. Keep the human-readable card output for single-player; the CSV output for batch.

**Anti-patterns.** Per-player skill that hard-codes printing to stdout; a separate "sweep"
script that diverges from the canonical single-player logic; batch mode that silently skips
errors instead of emitting an error column.

---

## Pattern E — Universe builder + parallel agents

**What it solves.** "Score every FA in the league + cross-reference PL + rank by upside" is
too large for one context window and too varied for one prompt. Sequential per-player calls
take an hour.

**Triangulate implementation.** The orchestration is: (1) universe builder produces the
list of players to evaluate (FA pool, roster, position group); (2) split by category
(hitters / SPs / RPs, or by archetype tier); (3) dispatch one sub-agent per category in
parallel, each running batch-mode triangulate on its slice; (4) synthesizer reads all CSVs
and produces the unified ranking. The pattern reusably scales any "score a universe" task.

**How to apply.** For any mega-research query: explicitly build the universe first (write
it to disk so it's reproducible), partition along a natural axis, dispatch agents in
parallel via the Task tool, and write a synthesis step that only reads the agent outputs.
Never let agents talk to each other.

**Anti-patterns.** A single sequential loop across hundreds of players (slow + context
overflow); parallel agents that share state; a synthesizer that re-does the per-player work
instead of just reading the CSVs.

---

## Pattern F — Cache-with-staleness-warning for external data

**What it solves.** External sources (PL rankings, ESPN injuries, Savant pages) shouldn't
be re-fetched every run, but a stale cache without a warning produces silent wrong answers.

**Triangulate implementation.** The PL cache is a JSON file with schema
`{source_url, fetched, ranks}`. Every run that uses it prints `PL cache: 3d stale (fetched
2026-05-26 from <url>)`. Past 7 days it prints `⚠ Nd stale` and recommends a refresh. The
fetched-from URL is part of the schema so lineage is reproducible if PL changes their page
structure.

**How to apply.** Every external cache should be `{source_url, fetched, payload}`. Display
the staleness on every read, not just on miss. Warn loudly past a threshold tuned to how
fast the source changes (PL: weekly; injuries: daily).

**Anti-patterns.** Caches without a fetched timestamp; caches without the source URL; silent
reads that hide staleness; TTL-based eviction that throws away the prior copy instead of
keeping it as a fallback.

---

## Pattern G — In-memory caching via `@lru_cache`

**What it solves.** Batch mode hammers the same parquet/CSV loaders thousands of times. The
single biggest perf bottleneck in triangulate batch mode was loading rh3/rp3/rprs2
projections inside a per-player function — 23× speedup from one decorator.

**Triangulate implementation.** Every loader function (`load_rh3()`, `load_rp3()`,
`load_archetypes()`, `load_pl_cache()`) is wrapped with `@functools.lru_cache(maxsize=None)`.
First call costs ~200ms; subsequent calls are ~0ms. Total batch time for 400 players
dropped from ~6min to ~16s.

**How to apply.** Any function that returns a DataFrame/dict and is called from inside a
loop should be `@lru_cache`-ed by default. It's free correctness (idempotent loaders) and
free performance. Should be the first thing every analytical script does.

**Anti-patterns.** Reloading the same projection CSV per row; manual `if _cache is None`
patterns (verbose and error-prone vs lru_cache); caching mutable returns (lru_cache
shares the reference — return copies or freeze).

---

## Pattern H — Decision-tree pseudo-code in SKILL.md

**What it solves.** Once a skill has 5+ rules, you can't audit the rule order or add a new
case without reading the script. The skill markdown becomes a sales pitch for the skill
instead of a spec.

**Triangulate implementation.** A `## Verdict decision tree` section near the end of
SKILL.md contains a 9-rule pseudo-code block: `if PL_top10 and model_top20 and
archetype_elite: return CONSENSUS_BUY; elif PL_lags and model_top20 and archetype_improving:
return BUY — model leads PL; ...`. The pseudo-code matches the Python 1:1. A reviewer can
extend the rule set by reading the markdown, propose a change in the markdown, and only
then port it to Python.

**How to apply.** For any skill with a non-trivial verdict rule, include the rule order as
pseudo-code in SKILL.md. Keep it in sync with the implementation; if they drift, the
markdown is the spec and the code is the bug.

**Anti-patterns.** SKILL.md that describes verdicts in prose ("we consider several
factors"); pseudo-code that's aspirational and doesn't match the code; pseudo-code without
rule ordering (hides precedence bugs).

---

## Anti-patterns this skill exposed

- **Per-row I/O.** Loading the same projection CSV inside a per-player loop. Always preload
  + `@lru_cache`.
- **Hard-coded thresholds without validation.** Triangulate v1 had `archetype_elite =
  rating > 60` baked into synthesize(). Calibration showed 65 was the right cut. Thresholds
  belong in a constants block with a comment pointing at the calibration run.
- **Stale cache without lineage.** A PL cache from 3 weeks ago that doesn't know which URL
  it came from is uninvestigable when PL restructures their page.
- **Single-snapshot data.** Treating "today's PL rank" as a stable input. Cache the
  fetched timestamp and surface it; for trends, store the last N snapshots.
- **No regression tests.** Verdicts that change between runs with no diff explanation. Add
  a golden-file test of (N canonical players → expected verdict tier) that runs on every
  change to synthesize() or the overrides.
