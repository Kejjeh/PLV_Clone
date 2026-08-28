# Validated models — RoS totals detail (full text)

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). Nothing here
was rewritten — CLAUDE.md keeps the headline, this file keeps the detail. -->

**RoS TOTALS = rate × volume (validated 2026-07-09).** The rate models are
per-PA / per-start; the volume companions (hitter +0.074 / SP +0.100 Spearman
vs naive pace, 7/7 yrs, holdout 2/2 each) convert them to totals. xfp_board and
the snapshot logger (`proj_volume`) already consume them (refresh steps
4.09/4.09b). Don't hand-multiply by flat 3.5 PA/g or 1.19 starts/wk when a
volume row exists. Full day's outcomes (incl. the rp3 IL-join regression fix,
47 arms re-tagged marcel_il): `reference_validated_signals_registry.md`
§2026-07-09.


## Volume projections are health-discounted (2026-08-29)

`proj_ros_pa_per_teamgame` ≈ in-role usage × expected availability. It is the
right number for RoS TOTALS and swap math, and the WRONG number for daily
start/sit — on a day a player is in the lineup, use his in-role usage.
Canonical: LAD Muncy, proj 2.72 vs 3.68 in-role (92% started, no platoon,
steady 3.7-4.2 PA/g all season) — the 0.74 factor prices his 2024-25 missed
time (73/100 games played), not a role loss. `lib/volume_semantics.py` is the
one owner of the decomposition and classifies every FADER gap as ROLE
(lineup signal, e.g. Tristan Peters) or AVAILABILITY (injury discount, role
intact); /volume-watch displays the kind. Guarded by
tests/test_volume_semantics.py.

**SP side (2026-08-29, same day).** `proj_ros_gs_per_teamgame` carries the
identical discount, and the role mechanism is the ROTATION TURN.
`sp_turn_map()` measures each starter's turn in TEAM GAMES (derived from the
boxscore frame's own distinct team_id×game_pk pairs — immune to off-days and
the ASG break, unlike calendar-day gaps); gaps > `SP_ABSENCE_GAP`=9 are
absences, excluded from the median and charged to availability. Then a fader
is ROLE if the turn itself is stretched (> 5.5 team games: six-man,
piggyback, innings limit) or the arm is healthy but no longer taking a turn;
AVAILABILITY if the turn is full; UNCLEAR below 3 measured turns (never
guessed).

Canonical: **Glasnow's turn is 6.0 team games — 1.02 starts/wk when active,
not the 1.19 league default** (LAD six-man), while his 95-team-game gap is an
absence, not evidence of a slow turn. Consequence: `1.19 starts/wk` is a
LEAGUE average and must not be applied to a six-man arm in cap or playoff
start-count math — use `in_role_vol × 6.10`. Fried, Cameron, Imanaga,
Messick, Rasmussen all measure a full 5.0 turn, so their sub-pace projections
are pure missed-time discounts.
