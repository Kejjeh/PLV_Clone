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

