---
name: team
description: Cross-position PL-spined team board — runs /sp-board --scope roster AND /hitter-board --mode pl in one pass over a single live roster+FA pull, then synthesizes both halves into one "state of my team" read. One row per Pitcher-List-ranked player (SP Top 100 + hitter Top 150) that is MINE or FA, sorted by PL rank within each universe, with ▲▼ movement vs the prior edition, our model rank/verdict/baseline, recent-form actuals, boom/bust, and PL sentiment. Use when the user asks "run the team board", "show me my whole team", "state of my team", "both boards", "run the hitter and SP boards together", "what does PL say about my whole roster", "team-wide PL check", or wants pitchers and hitters ranked on the same external yardstick in one look. Surfacing + synthesis only — no roster moves are executed; adds/drops route to /player-verdict then /moves.
maturity: meta-pl-cross-position
---

# team — the cross-position PL board

Runs the two **PL-spined** boards together and reconciles them:

1. **`/sp-board --scope roster`** → `scripts/xfp/build_sp_pl_board.py`
2. **`/hitter-board --mode pl`** → `scripts/xfp/build_hitter_pl_board.py`

Both have the same shape — one row per PL-ranked player that is MINE or FA,
sorted by PL rank, ▲▼ vs the prior edition, our model as the context column —
so they stack into a single team-wide surface without reformatting.

## Which board skill do I actually want?

Three adjacent surfaces exist. They differ by **spine**, not by data:

| Skill | Spine | Universe | Answers |
|---|---|---|---|
| **`/team`** | **PL rank** | MINE + FA, both positions | "What does PL say about my whole roster and the wire, and what moved?" |
| `/all-boards` | today's **slate** | FA-heavy market scan | "What's out there right now across every pool?" |
| `/xfp-board` | **our model** (RoS/playoff xFP) | MINE + FA, one merged scale | "Who's worth a roster spot by projected value?" |

**Do not route a market-browse or streamer question here** — that is
`/all-boards`. **Do not route a value-ranking question here** — that is
`/xfp-board`, which puts both universes on ONE numeric scale; `/team`
deliberately keeps them as two boards because PL ranks SPs and hitters in
separate articles with no shared scale.

## Run it

```bash
export PLV_ESPN_SNAPSHOT=1 PLV_ESPN_SNAPSHOT_TTL_MIN=45   # pull-once contract

python scripts/xfp/build_sp_pl_board.py --date <today> \
    --old-pl-json data/research/pl_cache/pl_sps_top100_<prior Monday>.json

python scripts/xfp/build_hitter_pl_board.py --date <today> \
    --old-pl-json data/research/pl_cache/pl_hitters_top150_<prior Wednesday>.json
```

The snapshot env is the same injection seam `/all-boards` uses: with it set,
every engine's `league.free_agents(size=2000)` after the first is served from a
shared disk pickle, so both boards run off ONE live pull with no engine changes.
45-min TTL = one chain's lifetime.

## Prerequisites — check these before running, they will bite

1. **The SP engine reads a differently-named cache file.** `build_pl_cache.py`
   writes `pl_sps_top100.json` / `pl_sps_top100_<date>.json`, but
   `build_sp_pl_board.py` opens `pl_top100_<date>.json`. Stage a copy first or it
   `FileNotFoundError`s:
   ```bash
   cp data/research/pl_cache/pl_sps_top100_<latest>.json \
      data/research/pl_cache/pl_top100_<today>.json
   ```
   (The hitter engine takes `--pl-json` directly and needs no copy. Worth
   unifying; until then this step is mandatory.)
2. **Both engines need a sentiment JSON** or the column renders all `—`:
   `nick_sentiment_<date>.json` (SP) · `pl_hitter_sentiment_<date>.json` (H).
   Absent files are handled gracefully, not fatally.
3. **Always pass `--old-pl-json`.** Once the nightly triangulate ingests a new
   edition its `pl_rank` IS the new rank and every move renders `·`. Point the
   flag at the *prior dated* cache for a real ▲▼.

## ⚠ The cadence asymmetry — the one thing unique to this skill

PL publishes the two lists on **different days**:

| List | Publishes | Cached by |
|---|---|---|
| SP Top 100 | **Monday** | Tue AM |
| Closers/RP | ~Tuesday | Wed AM |
| Hitter Top 150 | **Wednesday** | Thu AM |

So on any given day the two halves of this board are at **different edition
ages**, and the ▲▼ columns measure different windows. This is not a bug and it
cannot be fixed by refreshing — the articles simply publish 2 days apart.

**Always print an edition header before the boards** so the reader knows what
each half is anchored on:

```
SP Top 100  — wk19 (2026-07-27, 1d old)   movement vs wk18 (07-20)
Hitter T150 — wk16 (2026-07-22, 6d old)   movement vs wk15 (07-15)   ← next edition tomorrow
```

Staleness is **cadence-aware** (gotcha #10): a Wednesday hitter pull is current
until the *next* Wednesday, not stale at a flat 7 days. Never refresh off age
alone, and never describe the older half as "stale" when it is simply the
current edition of a slower-publishing list.

## Report shape

1. **Edition header** (above) — non-optional.
2. **SP board** — all rows, combined-column view (see `/sp-pl-board`).
3. **Hitter board** — all rows, combined-column view (see `/hitter-board` §`--mode pl`).
4. **Cross-position synthesis** — the part that justifies running them together:

> ### ⛔ TWO TABLES. NEVER ONE MERGED TABLE.
>
> Steps 2 and 3 render as **separate tables under separate headings** — SPs in
> one, hitters in the other. Do NOT interleave them, do NOT sort a combined
> roster by PL rank, and do NOT build a single "my whole team" table even when
> only the MINE rows are being shown. Three reasons, each sufficient:
>
> 1. **The scales are not comparable.** PL ranks SPs (Top 100) and hitters
>    (Top 150) in separate articles with separate universes. A merged sort puts
>    SP #23 above H #28 and implies a cross-position comparison PL never made.
>    `/xfp-board` is the skill that legitimately puts both on one scale, via OUR
>    model, in FP units — this one does not.
> 2. **The columns genuinely differ.** SP carries K/st (K-FED/IP-FED), HR/9
>    2026-vs-career, and per-START form; hitters carry platoon xwOBA, PA/team-game
>    vs pace, bat-speed z, and per-GAME form. Merging forces blank cells or, worse,
>    silently drops a lens to make the widths line up.
> 3. **The editions differ.** Per the cadence header the two halves are anchored
>    on different publication dates, so a single ▲▼ column would mix movement
>    measured over different windows.
>
> This is a real failure mode, not a hypothetical: the first `/team` run
> (2026-07-28) merged the MINE rows of both boards into one PL-sorted table and
> lost the SP K/st and hitter platoon columns doing it. Two tables, always.
   - **Roster coverage** — how many of my SPs / hitters are PL-ranked at all.
     An unranked starter is a real signal in an 8-team league.
   - **Biggest PL movers, both directions, MINE first.** ▲/▼ ≥10 is the cut.
   - **Widest PL-vs-model divergences**, tagged by direction:
     PL≫model = PL overvalues (sell-high / don't-chase);
     model≫PL = PL undervalues (buy-low / the wire is sleeping).
     Route these to `/conviction-scan` or `/triangulate`, never resolve them here.
   - **Weakest MINE row per universe vs the best FA row available**, stated as an
     explicit comparison. This is the swap surface.
   - **Health + eligibility flags** carried from both boards (IL10/60, DTD).

## Rules

1. **rp3 / rh3 stay the headline (Rule 13).** PL sets the SORT on this board and
   nothing else. A PL-vs-model gap is the surface this skill exists to expose —
   surface and route it, don't arbitrate it.
2. **Rule 12 — one stable verdict.** If the synthesis names a swap, it must match
   what `/player-verdict` would say on the same names. Don't let PL rank flip a
   verdict the model layer already settled.
3. **Opponent-rostered players are excluded** from both boards by design. For
   trade targets use `/trade-target-scan` or `/league-deep-audit`.
4. **Show ALL rows.** Truncate only with an explicit note — no silent caps.
   A truncation note does not license merging the two tables to save space; cut
   ROWS if you must, never fold the two universes together.
5. **PL sentiment coverage is asymmetric.** The SP column is dense (SP Roundup
   recaps essentially every starter); the hitter column runs ~15% (Hitter Recap
   features ~5-8 of ~250 hitters who played). Say so once; do not present the
   hitter gaps as missing data or fill them by inferring tone from the numbers.
6. **Attribution differs by half.** SP = Nick Pollack (Jake Crumpler some
   Roundups). Hitters = Scott Chu (Top 150) + rotating recap authors. Never
   label the hitter column "Nick".
7. **No moves are executed.** This is a decision surface. Adds/drops route to
   `/player-verdict` → `/moves`.

## Cadence for running it

- **Monday/Tuesday** — SP half is freshest; best day for staff decisions.
- **Wednesday/Thursday** — hitter half refreshes; best day for lineup decisions.
- Running it any other day is fine, just read the edition header first.

## Companions

`/player-verdict` (firm call on names this surfaces) · `/moves` (execute) ·
`/conviction-scan` (model-vs-process divergence) · `/all-boards` (market browse)
· `/xfp-board` (one merged value scale) · `/monday-morning` (the full weekly
roster ritual, of which this is the PL slice).
