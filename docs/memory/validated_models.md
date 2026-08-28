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
tests/test_volume_semantics.py. SP-side decomposition is a follow-up.
