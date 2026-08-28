# CodeGraph — full usage rules

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). CLAUDE.md is
auto-loaded into every session and had drifted to 635 lines against its own
~200-line budget; every line is a permanent tax on every turn, and a gotcha
list nobody finishes reading is a gotcha list that does not fire.

Nothing here was rewritten or shortened — the text below is what CLAUDE.md
carried. CLAUDE.md keeps a one-line headline per rule, numbered identically,
so the rule still fires from the auto-loaded file and the evidence is one hop
away. Numbering is load-bearing: memos and skill docs cite "gotcha #12" and
"don't-do #10" by number. Never renumber; retire in place. -->

`.codegraph/` is **initialized and live** here (~550 files, real-time
file-watcher daemon). It's the pre-built semantic index; reaching for
grep/glob/read to explore wastes the ~90% token saving. Full rules in
the global `~/.claude/CLAUDE.md`; the load-bearing bits:

- **Exploration ("how does X work", "where is Y", architecture, tracing)
  → spawn an `Explore` agent** and paste the block below into its prompt.
  Do NOT call `codegraph_explore`/`codegraph_context` from the main
  session (they dump source and fill context).
- **Targeted pre-edit lookups → main session may call the lightweight
  tools directly:** `codegraph_search` (find a symbol), `codegraph_callers`
  / `codegraph_callees` (trace call flow), `codegraph_impact` (blast radius
  before editing), `codegraph_node` (one symbol's detail). Prefer
  `codegraph_impact` over a grep sweep before changing a shared signature.

Paste verbatim into every `Explore` agent prompt:

> This project has CodeGraph initialized (`.codegraph/` exists). Use
> `codegraph_explore` as your PRIMARY tool — one call returns full source
> for all relevant files. Follow the call budget in its tool description.
> Do NOT re-read files it already returned; only fall back to grep/glob/read
> for "Additional relevant files" or if it returns nothing.

Index hygiene: dead/one-off trees (`scripts/xfp/archive|research|_research/`,
`scripts/_oneoff/`) are `.gitignore`d **purely to keep them out of the index**
(they stay tracked in git) — CodeGraph 0.9.9 honors `.gitignore` and has no
ignore config of its own. Re-add a tree there if a future symbol search
surfaces stale `v9/v10/v11`-style duplicates.

