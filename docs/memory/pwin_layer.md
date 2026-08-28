# The P(win) decision layer — full text

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). CLAUDE.md is
auto-loaded into every session and had drifted to 635 lines against its own
~200-line budget; every line is a permanent tax on every turn, and a gotcha
list nobody finishes reading is a gotcha list that does not fire.

Nothing here was rewritten or shortened — the text below is what CLAUDE.md
carried. CLAUDE.md keeps a one-line headline per rule, numbered identically,
so the rule still fires from the auto-loaded file and the evidence is one hop
away. Numbering is load-bearing: memos and skill docs cite "gotcha #12" and
"don't-do #10" by number. Never renumber; retire in place. -->

`P(my_total > opp_total)` is what wins BrownU, and it is NOT the same objective as
expected FP. The whole layer lives behind ONE engine — never reimplement a piece of
it, the four-divergent-rh3-assemblies lesson applies here too.

`scripts/xfp/lib/leverage_engine.py` — MC engine + `delta_pwin(state, D, add=,
drop=, bench=)`, which scores one roster counterfactual (H/SP/RP adds; add+drop in
one call is a SWAP). Draws are precomputed once, so a scenario is a cheap numpy
re-assembly — that is what makes searching thousands of permutations affordable.
Draw dicts are keyed by **mlbam**, and `assemble()` RAISES on a non-key: passing a
name used to match nothing and report every hitter as free to bench (0.00pp).

`lib/dpwin_history.py` → `data/research/dpwin_history.parquet`. Every evaluated
candidate, chosen AND rejected, per run. `matchup_leverage.json` is overwritten
each run, so this is the only durable record — and the REJECTED surface is the
counterfactual the ledger settles against.

`lib/title_equity.py` — weights a period ΔP(win) by the value-of-a-win curve from
`season_sim.json`. **The curve is far from flat** (period 15 = 2.67pp of title
probability, period 17 = 0.88pp), so the same weekly edge can be worth 3× more
depending on the week. Staleness is labelled, never laundered; unavailable returns
None, never 0.0.

`lib/roster_rules.py` — legality as pure functions. **4 RPs is a FLOOR, never a
target** (standing rule 2026-07-18): an RP may only be dropped for an RP.

**THE WORKFLOW RULE THAT MAKES THE LEDGER WORK:** run the optimizer or
`/matchup-leverage` **BEFORE executing a move**. `reconcile_decisions.py` joins
executed ESPN transactions back to the surface that motivated them and picks the
best *unexecuted* same-bucket candidate as the counterfactual. A move made when no
surface existed can NEVER be graded — the 2026-07-29 dry run found all 21 recent
moves unattributable for exactly that reason.

Then `settle_decisions.py` grades `realized(chosen) − realized(rejected)` over a
common window (H 21d / SP+RP 35d) in **total FP, not per-unit** — playing time is
part of what you chose, so an alternative who got hurt scores 0 and that is the
decision paying off, not missing data. `/verdict-scorecard` §7-9 reports regret by
bucket, cumulative FP vs the road not taken, and whether ΔP(win) has real
resolution (gated at n≥30).

Rule 13 throughout: this layer never touches rh3/rp3/rprs2/baseline xFP.

