# Volume-model integration into the merged xFP board — 2026-07-09

Integrates the two forward-volume models validated earlier today
(`hitter_volume_model_2026-07-09.md`, `sp_volume_model_2026-07-09.md`, both
PASS) into the live board engine so RoS / playoff totals use per-player
projected volume instead of flat league constants.

## What changed (engine: `scripts/xfp/build_xfp_boards.py`; renderer: `build_xfp_board_dashboard.py`)

The live engine is `build_xfp_board_dashboard.py` (refresh step 4.55), which
imports `build_xfp_boards.py` — the integration lives in the boards module so
both the CLI CSVs and the HTML get it.

- **Hitters** (join: **MLBAM batter id** — the board already resolves ids via
  `resolve_batter_id`; `_HIT_VOL` dict `mlbam_id -> proj_ros_pa_per_teamgame`
  from `data/outputs/xfp_volume_projections.csv`):
  `RoS FP = xfp_rh3_per_pa × proj_ros_pa_per_teamgame × team_games_in_window`,
  where team_games = existing window `(avail→season-end days)/7 × 6.3`.
  talent_prior rows with a volume row use the algebraically identical ratio
  form `per_game × vol/3.5` (rh3 convention: `per_game = per_pa × 3.5`).
- **SPs** (join: name map built from `xfp_sp_volume_projections.csv` — SP board
  rows are ESPN-name-keyed; volume names "Last, First" flipped via
  `TP.flip_name`; **20 NaN-name volume rows recovered via rp3's `pitcher`
  mlbam → player_name**; skip-on-ambiguous on normalized full names, plus the
  existing unique-(last, first-initial) fallback):
  `RoS FP = per_start × proj_ros_gs_per_teamgame × team_games_in_window`.
- **Playoff columns**: the SAME multiplier `vol / flat_const` is applied to the
  existing playoff-window count (equivalent to playoff games × player-vol /
  league-flat-vol) — consistent with the RoS substitution and preserves the
  3-scoring-weeks discount baked into `PLAYOFF_FULL` / `PLAYOFF_GAMES_FULL`.
- **IL scaling unchanged**: both paths reduce to `flat_xfp × (vol/flat_const)`,
  so the availability-date window math is preserved exactly.
- **Fallback**: rows absent from the volume CSVs keep the flat path
  (`1.19 starts/wk`; `3.5 PA/g × 6.3 g/wk`) — this is exactly the
  talent_prior / marcel_il IL-stash population, which keeps its LOW-CONF flag.
- **Visibility**: `src` gets a `·vol` suffix; new `vol` column (per-teamgame
  number) rendered on every board table; header counts + legend updated.
- Flat constants: hitter `FLAT_PA_PER_TEAMGAME = 3.5`;
  SP `FLAT_GS_PER_TEAMGAME = 1.19/6.3 ≈ 0.1889`.

## Coverage (board build 2026-07-09)

| universe | ranked | vol rows | flat (all talent_prior) |
|---|---|---|---|
| SP (MINE+FA) | 215 | 151 (100% of Stuff+/rp3_dd rows) | 64 |
| Hitters (MINE+FA) | 477 | 357 (100% of id/name rh3 joins + 7 talent_prior) | 113 |

No model-scored row missed its volume join.

## Sanity gate (old = new ÷ ratio, exact — single build, immune to the concurrent rp3 regen)

Window at build: 73 days → 65.7 team games.

- **(a) flat-equivalent-volume players move <10%**: hitters with vol within
  ±5% of 3.5 PA/tg (n=20): max |move| = 4.9%. PASS. (No SP sits within ±5% of
  the flat 0.1889 — see level note below.)
- **(c) everyday-star band**: durable regulars stay in `per_game × ~66 g`
  band and move mildly UP, e.g. Carroll 144→151 (+4.9%), Bichette 129→139
  (+7.7%), Vlad Jr. 132→135 (+2.3%); no healthy everyday player cratered.
  Implied star PA ≈ 3.6-3.8 × 65.7 ≈ 236-248, plausible. Top SP implied
  starts 10.6-11.5 over 73 days (every ~6.5 days — the model prices in skips/
  IL risk vs the 5-man ideal of 14).

### (b) Top movers — hitters (Δ RoS FP, flat_ros ≥ 60)

UP (durable everyday regulars — flat 3.5 PA/tg under-credited them):

| player | own | vol PA/tg | flat → new | Δ | % |
|---|---|---|---|---|---|
| Bo Bichette | MINE | 3.77 | 129 → 139 | +10 | +7.7% |
| Corbin Carroll | MINE | 3.67 | 144 → 151 | +7 | +4.9% |
| Pete Alonso | MINE | 3.65 | 138 → 144 | +6 | +4.3% |
| Jackson Merrill | FA | 3.65 | 120 → 125 | +5 | +4.3% |
| Chase Meidroth | FA | 3.62 | 95 → 98 | +3 | +3.4% |
| Vladimir Guerrero Jr. | MINE | 3.58 | 132 → 135 | +3 | +2.3% |
| Jarren Duran | FA | 3.60 | 102 → 105 | +3 | +2.9% |
| Ceddanne Rafaela | FA | 3.59 | 99 → 102 | +3 | +2.6% |
| Luis Arraez | MINE | 3.55 | 129 → 131 | +2 | +1.4% |
| Elly De La Cruz | MINE | 3.55 | 121 → 123 | +2 | +1.4% |

DOWN (bench / backup-C / platoon — flat 6.3 g/wk × 3.5 PA/g grossly
overcredited part-timers):

| player | own | vol PA/tg | flat → new | Δ | % |
|---|---|---|---|---|---|
| Moises Ballesteros | FA | 1.00 | 137 → 39 | −98 | −71% |
| Luis Campusano | FA | 0.80 | 123 → 28 | −95 | −77% |
| Jahmai Jones | FA | 0.29 | 97 → 8 | −89 | −92% |
| Connor Joe | FA | 0.26 | 94 → 7 | −87 | −93% |
| Santiago Espinal | FA | 0.30 | 93 → 8 | −85 | −91% |
| Miguel Rojas | FA | 0.98 | 118 → 33 | −85 | −72% |
| Randal Grichuk | FA | 1.21 | 127 → 44 | −83 | −65% |
| Tyler Tolbert | FA | 1.22 | 126 → 44 | −82 | −65% |
| Jhonny Pereda | FA | 0.94 | 112 → 30 | −82 | −73% |
| Eric Wagaman | FA | 0.75 | 103 → 22 | −81 | −79% |

Every DOWN mover is a bench/backup/platoon FA — the exact population the
volume model was built to deflate. Every UP mover is a durable regular.

### (b) Top movers — SPs (Δ RoS FP, flat_ros ≥ 100)

No SP moves UP (see level note). Biggest DOWN (rookies with tiny track
records, IL-risk arms, spot starters — volume model shrinks their forward
start pace hard):

| pitcher | own | vol GS/tg | flat → new | Δ | % | note |
|---|---|---|---|---|---|---|
| Logan Henderson | FA | 0.08 | 171 → 77 | −94 | −55% | rookie, few MLB starts |
| Grayson Rodriguez | FA | 0.06 | 134 → 44 | −90 | −67% | IL15 |
| Andrew Morris | FA | 0.06 | 129 → 41 | −88 | −68% | spot/rookie |
| Andrew Painter | FA | 0.07 | 135 → 47 | −88 | −65% | rookie ramp |
| Shane Smith | FA | 0.05 | 111 → 30 | −81 | −73% | swing role |
| Spencer Miles | FA | 0.06 | 120 → 40 | −80 | −67% | |
| Kodai Senga | FA | 0.08 | 133 → 55 | −78 | −59% | injury history |
| Drew Anderson | FA | 0.08 | 137 → 61 | −76 | −56% | |
| Elmer Rodriguez | FA | 0.07 | 119 → 44 | −75 | −63% | |
| Janson Junk | FA | 0.08 | 133 → 60 | −73 | −55% | |

Durable front-line arms are docked only mildly (Soriano 154→143 −7%,
Bibee 150→138 −8%, Peralta 136→122 −10%).

## Known caveats / follow-ups

1. **SP level shift is one-directional.** The flat 0.1889 GS/tg (1.19/wk)
   exceeds even the highest projected SP volume in the board universe (max
   0.175), so every vol'd SP moves down (median ratio 0.61). Within-board
   RANKING is what matters and it now reflects real start-volume risk, but:
2. **Flat-path (talent_prior / marcel_il) rows are now relatively optimistic.**
   They keep the generous flat rate while scored arms are docked — e.g. IL-stash
   Hunter Greene (152, LOW-CONF flat) now headlines the SP board above healthy
   Soriano (143·vol); FA arms like Tyler Wells / Kershaw / J.P. France float
   high on the flat path. LOW-CONF badges flag them, but a follow-up could dock
   flat-path rows by the population-median vol ratio (or a per-tier prior) to
   restore cross-path comparability.
3. **Currently-IL players with a volume row** get both the availability-date
   window haircut AND a volume projection whose IL features already shave
   volume (mild double-count, e.g. Grayson Rodriguez). Kept per design (window
   handles the return date; volume handles post-return pace) — worth a
   targeted look if IL returners seem too cheap.
4. SP volume model is conditional on ≥1 more start (substrate truncation, per
   pre-registration) — "low vol" means few starts, never zero; zero-start risk
   stays decision-layer.
5. rh3's own `expected_total_fp_remaining` (etfr) runs ~10-15% below the new
   volume-based totals for stars (it uses a different PA pace); not reconciled
   here — the board headline is the volume path, etfr remains a display column.

Gate artifacts: scratchpad `gate_sp_board.csv` / `gate_hit_board.csv`
(session-local); comparison is exact-arithmetic (new = flat × vol/const).

---

# ADDENDUM (same day) — flat-path comparability dock (follow-up #1, approved)

Caveat #2 above is now fixed in the engine. Flat-path rows (no volume row)
that are **IL'd or prior-only** (talent_prior / marcel_il class) are docked by
the **75th-percentile vol ratio** (`vol / flat_const`) of the volume-modeled
rows in the SAME universe — i.e. an unmodeled player is credited the volume of
a **top-quartile** modeled player, not the flat league constant. Rationale:
flat-path rows are mostly IL stashes and priors-only arms whose
healthy-workload ceiling is top-quartile-like, but crediting them the full
flat constant (which exceeds even the MAX modeled volume — ratio 1.0 vs max
~0.93 for SPs) systematically over-ranks them vs volume-modeled rows that
embed forward injury/rest risk. Dock applies to both `xfp_ros` and `xfp_po`;
LOW-CONF flags unchanged; marker = src suffix `·flat↓` + legend line.

**Healthy-but-uncovered exemption:** rows that are flat merely because they
fall below the volume model's coverage floor but are ACTIVE/healthy (not
prior-only src AND no ESPN injury status) are NOT docked. In practice this
class is **empty** on today's board (every flat row is talent_prior and/or
IL'd — 0 plain-flat rows in both universes), so the dock is effectively
universe-wide over flat rows, but the exemption is coded for the day coverage
gaps appear.

## Dock parameters + counts (build 2026-07-09)

| universe | p75 vol ratio | docked (·flat↓) | ·vol | plain flat |
|---|---|---|---|---|
| SP | ×0.7279 | 64 | 151 | 0 |
| Hitters | ×0.7057 | 120 | 357 | 0 |

## Verification

**(a) Greene vs Soriano:** Hunter Greene (IL stash, talent_prior) 152 → 111,
now BELOW healthy modeled ace Jose Soriano (143·vol). Reads sensibly.

**SP top-10 headline, before → after the dock:**

| # | before (flat headline) | ros | # | after (docked headline) | ros |
|---|---|---|---|---|---|
| 1 | Hunter Greene (MINE, prior·flat↓) | 152 | 1 | Jose Soriano (MINE, ·vol) | 143 |
| 2 | Jose Soriano (MINE, ·vol) | 143 | 2 | Eury Perez (MINE, ·vol) | 141 |
| 3 | Eury Perez (MINE, ·vol) | 141 | 3 | Tanner Bibee (FA, ·vol) | 138 |
| 4 | Tanner Bibee (FA, ·vol) | 138 | 4 | Aaron Nola (FA, ·vol) | 130 |
| 5 | Aaron Nola (FA, ·vol) | 130 | 5 | Will Warren (FA, ·vol) | 128 |
| 6 | Tyler Wells (FA, prior·flat↓) | 129 | 6 | Ryan Weathers (FA, ·vol) | 127 |
| 7 | Will Warren (FA, ·vol) | 128 | 7 | Parker Messick (MINE, ·vol) | 126 |
| 8 | Ryan Weathers (FA, ·vol) | 127 | 8 | Landen Roupp (FA, ·vol) | 124 |
| 9 | Parker Messick (MINE, ·vol) | 126 | 9 | Cade Cavalli (FA, ·vol) | 123 |
| 10 | Clayton Kershaw (FA, prior·flat↓) | 124 | 10 | Freddy Peralta (MINE, ·vol) | 122 |

The top-10 is now entirely healthy volume-modeled arms; prior-only FAs
(Wells 129→94, Kershaw 124→90) and IL stashes (Greene 152→111) drop out of
the headline but remain visible with LOW-CONF + ·flat↓.

**(b) No healthy everyday flat-path hitter craters:** all 120 docked hitters
are prior-only fringe/stash vets (Profar 125→88, Blackmon 118→83, Heyward,
Santana, J.D. Martinez...) taking a modest ~29% dock — no rh3-modeled
(id/name-joined) hitter is touched by the dock, and 105/120 docked are
healthy prior-only rows (dock class per design), 15 also IL'd.

**(c) Rendered HTML:** 19 `·flat↓` rows visible in tables (docked rows below
the display cut stay in CSVs), legend line present, both HTML outputs
regenerated (`data/outputs/xfp_board.html` + `xfp-model/docs/xfp_board.html`).

Implementation: `FLAT_DOCK_Q = 0.75` + `_dock_flat_rows()` in
`build_xfp_boards.py`, applied pre-sort in `build_sp_board()` and at the end
of `build_hitter_board()`; p75 + dock counts carried in `df.attrs`
(`flat_dock_p75`, `n_flat_dock`) and printed by `main()` and shown in the
dashboard header totals.
