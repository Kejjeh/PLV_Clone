---
name: sp-pl-board
description: The master SP decision board for the BrownU roster + FA pool. One row per Pitcher-List-ranked starter that is MINE or FA, integrating our validated models (rp3 rank, triangulate verdict, blended xFP), recent-form actuals (L1/L3/L5/L8/season FP per start), the HR structural lens (HR/9 2026 vs career), the reliable-boomer lens (boom%/bust%/net), K%, velo/decline flags, AND the full Pitcher List stack — The List Top-100 rank + move, SP Streamer previews, SP Roundup recaps — distilled into Nick Pollack's chronological sentiment per pitcher. Use when the user asks to "build/restate the SP board", "integrate the PL list", "what does Nick say about my SPs + FA", "add the new PL Top 100", or wants a one-look board to pick a streamer / SP add / drop.
maturity: models-actuals-hr-pl-sentiment
---

# sp-pl-board — master SP decision board (our models × actuals × HR × Pitcher List + Nick sentiment)

> **One board, every lens.** This is the consolidated SP view: our *validated* rank
> (rp3) and triangulate verdict are the HEADLINE; everything else — recent-form actuals,
> HR profile, boom/bust, PL ranks, and Nick's sentiment — is **context/conviction**
> (CLAUDE.md #13). Never let a single lens (a hot L3, a PL drop, a Nick quote) move the
> headline; surface the agreement/disagreement and reconcile explicitly.

## Trigger phrases
"build the SP board", "restate the integrated board", "master SP board", "add the new PL
Top 100", "what does Nick say about everyone", "SP board with the streamer/roundup blurbs",
"sp-pl-board".

## FP PROVENANCE — say this whenever FP is shown
Per-start FP is **computed BY US** from **MLB Stats API** box lines (real IP/H/ER/BB/K/HBP)
via the BrownU formula `K + IP*3.3 − H − 2*ER − BB − HBP` in `refresh_boxscores.py`. It is
**NOT** pulled from ESPN (ESPN's API doesn't expose applied totals). It **equals ESPN's
scoring by construction** (same real stats + same formula) and recomputes to the stored
`fp_sp` with **max |diff| = 0.0000** across all starts. If asked "is this real / ESPN /
ours" → "real MLB data, our calc, verified == ESPN."

## Columns (the full set — never drop one when restating)
`new_pl` · `old_pl` · `move` (▲ rose / ▼ fell) · `owner` (MINE⭐/FA) · `player` ·
`rp3` (validated rank — HEADLINE) · `verdict` (triangulate) · `xfp` (blended) ·
`L1 L3 L5 L8 season` (FP/start actuals) · `boom_pct boom%≥17` · `bust_pct bust%<5` ·
`net_boom` · `hr9_2026` · `hr9_career` · `k_pct` · `flags` (velo SEVERE/LOW-VELO,
DECLINE-RISK, RISING) · `nick_sentiment`.

## Workflow

### 1. Refresh MLB data through today
```
python scripts/xfp/refresh_boxscores.py --date <yesterday>      # per-start FP (our calc)
python scripts/xfp/build_statcast_gf_bridge.py                  # statcast (HR/K) current
```
Per gotcha #9 the bridges make everything same-day current; don't caveat "models lag a day."

### 2. Build the universe + triangulate (rp3 / verdict / xFP / old PL)
```
python scripts/xfp/build_triangulate_universe.py
python scripts/xfp/run_triangulate.py --names-file data/research/triangulate_universe/master_universe.csv \
       --csv-out data/research/triangulate_universe/results_<date>.csv --jobs 0
```
`--jobs 0` is the parallel fast path (~25s vs 152s; the engine self-shards and reassembles
identically — locked by `tests/test_triangulate_golden.py`).

### 3. Get the new PL Top 100 (The List) → `data/research/pl_cache/pl_top100_<date>.json`
WebFetch the latest "Top 100 Starting Pitchers" article, or accept the user's screenshot.
**CAVEAT:** the source Team column is frequently scrambled (Rodón→SEA, Cole→CHC, Webb→SFG) —
**ranks + names + tiers only; ignore Team and the matchup columns.** Write `{"ranks": {...}}`.

### 4. Fetch the PL blurbs (3 series) and build the per-pitcher chronological timeline
Fan out a Workflow over the recent articles (one agent per article, schema-structured), for:
- **The List** blurbs (per-rank prose) — `pitcherlist.com/top-100-...`
- **SP Streamer** previews — `.../starting-pitcher-streamer-ranks-...` (Nick Pollack)
- **SP Roundup** recaps — `.../sp-roundup-M-D-26/` (Nick Pollack; **Jake Crumpler** on some days)
Then a compile agent rolls them up per pitcher. **DATING IS LOAD-BEARING:** a **Roundup** is a
recap of a **COMPLETED** start (date = the start played `[R]`); a **Streamer/List** entry rates
an **UPCOMING** start (date = the start to come `[S]`). Tag and date every quote to the start it
addresses. (Reference build: `scripts/_oneoff/build_pl_timeline.py` →
`data/research/triangulate_universe/pl_timeline_<date>.md`.)
> **Author note:** SP Roundup + SP Streamer are **Nick Pollack** (Jake Crumpler some Roundups).
> Nate **Schwartz** writes the separate **"Going Deep"** deep-dives + the *Approach Angle* pod —
> different series; if the user wants "Nate," that's Going Deep, not the roundup.

### 5. Distill Nick's sentiment per pitcher → `nick_sentiment_<date>.json`
For each pitcher, read the timeline **oldest→newest** and write ONE latest-weighted sentiment
string: a 🟢/🟡/🔴 tone + a trend arrow (↑↑/↑/→/~/↓/↓↓) + the why in ≤12 words, quoting Nick's
signature phrase where vivid ("WE ARE SO BACK", "It's time to let go", "GET AMPED"). The arrow
is the CHRONOLOGICAL read (did his stance rise/fall across the window), not a single quote.

### 6. Assemble the board
```
python scripts/xfp/build_sp_pl_board.py --date <date>
```
Reads the Top-100 JSON + sentiment JSON + results CSV + boxscore + statcast → one row per
PL-ranked MINE/FA starter, all columns, saved to `sp_pl_board_<date>.csv`.

### 7. Completeness check (the rule that catches the misses)
Cross-reference the **FULL Top 100** against the live roster + FA pool — include **EVERY**
Top-100 arm that is MINE or FA, **even IL'd ones** (e.g. Hunter Greene #27, who carries no old
PL rank and no 2026 starts) and **newly-ranked FA** that weren't in the prior cache. Do NOT
filter to "had an old PL rank" — that silently drops the new entrants. Exclude only arms
rostered by opponents. The engine does this from the JSON; verify the count looks right
(~8 mine + ~30-40 FA).

## Gotchas / rules
1. **rp3 is the headline; all else is context** (Rule 13). A hot L3, a PL move, or a Nick quote
   never moves the rank — surface convergence/divergence and reconcile.
2. **marcel_il SP artifact** (gotcha #1): FA SPs sorted by xFP surface impossible 40+ fp/start
   swingmen. Rank by rp3, filter `headline_proj < 25`, trust rp3 only where `data_quality_tag`
   is `data_driven_*`.
3. **HR: career vs 2026** is the structural-vs-luck lens. `hr9_2026 ≈ hr9_career` = structural
   (no relief coming — e.g. Imanaga 1.92/1.81); `2026 ≫ career` = running hot (regress down);
   `2026 ≪ career` = low-HR mirage (regress up — e.g. Boyd 0.63/1.43). HR is a LEVEL/floor
   problem, not volatility (validated: +1 HR/9 → −4.2 FP/start, +13pp bust, std flat).
4. **PL streamer rank skill** (validated track record, `pl_streamer_track_record.parquet`):
   only the **numeric top-10** predicts FP (Spearman −0.23); rank 16+ is noise; the tier WORDS
   are miscalibrated (Auto-Start = safest floor, "Probably" = his boom tier). Trust the number.
5. **Player-id safety** (gotcha #10): resolve to mlbam with team/role or a normalized FULL-name
   match; never last-name `contains` (Will vs Austin Warren).
6. **Verdict stability** (gotcha #12): keep the headline stable across turns; a verdict changes
   only on new data or a corrected error — say WHY.

## Output
Present the board sorted by new PL (⭐ = mine), then a short **decision synthesis**: the
add/drop call, where our model and Nick agree vs diverge (flag PL outliers like Rodón ▼12 with
fine actuals), and IL/return notes. Save the CSV + the timeline `.md`. Companion skills:
`/triangulate`, `/sp-slate-grid`, `/stream-the-stack`, `/pl-cross-reference`, `/sp-week-plan`.

### ⚠ ALWAYS show ALL ROWS + ALL DATA, in the COMBINED display (load-bearing, 2026-06-30)
Show **every PL-ranked MINE/FA pitcher (all rows — never a "decision-relevant subset")** and
**every datapoint** — but fold related fields into the preferred **combined 10-column** view
(fewer columns, nothing lost):

| col | folds in |
|---|---|
| `PL ▲▼ (old)` | new_pl + move (▲ rose / ▼ fell) + old_pl, e.g. `33 ▼4 (29)` / `27 new` |
| `Own` | ⭐ MINE / FA |
| `Pitcher` | player |
| `rp3·verdict·xFP` | model rank + triangulate verdict + blended xFP, e.g. `#23 BUY 9.5` |
| `L1/L3/L5/L8/Sea` | the five FP-per-start windows, e.g. `11.9/11.4/11.9/6.5/12.6` |
| `boom/bust(net)` | boom% / bust% (net), e.g. `41/18 (+23)` |
| `HR 26/car` | hr9_2026 / hr9_career, e.g. `1.92/1.81` |
| `K%` | k_pct |
| `flags` | velo SEVERE/LOW-VELO, DECLINE-RISK, RISING |
| `Nick sentiment` | the chronological 🟢/🟡/🔴 + arrow + phrase |

**Fold, don't cut:** never drop a ROW and never drop a DATAPOINT — combine columns to stay
readable, but every number must be visible. The engine emits exactly this combined view to
`sp_pl_board_<date>.md` (paste-ready) and keeps the raw 21-column data in the `.csv`. Put the
decision synthesis AFTER the full table, never instead of rows.
