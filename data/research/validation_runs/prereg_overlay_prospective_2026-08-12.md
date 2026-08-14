# Pre-registration — PROSPECTIVE overlay validation, ESPN-return-date variant
# (2026-08-12, registered before any outcomes accrue)

## Why prospective

Study C (prereg_availability_suite_2026-08-12.md) FAILED the overlay's
auto-ship gate: crude estimated return dates (placement + min stint + 10d)
made RoS PA predictions 83.8% WORSE by median |error| than pace-forward. But
the ORACLE variant (true return dates) cut median error 25.6% and lifted
Spearman 0.384 → 0.684 — the when-active-rate construction carries real
signal when the return date is right. The live boards use ESPN's return_date
feed, which is an informed date, not the crude estimate — a variant that
CANNOT be backtested (ESPN return dates are not archived historically).
Hence: prospective ledger, settled on realized outcomes.

## Protocol

- Every run of build_period_xfp_board.py writes a dated, append-only snapshot
  to data/research/validation_runs/overlay_prospective/predictions_{date}.csv
  containing, per player: headline pace-forward RoS PA-based total AND the
  diagnostic overlay total (ros_overlay_diag), plus return_date used.
- Cohort: rows with `bucket == 'H'` AND `vol_source == 'il_return_overlay'`
  (i.e., a hitter on IL with an ESPN return date at prediction time). First
  eligible snapshot per player-stint is the scored one.

### Schema clarification, 2026-08-14 (pre-outcome, no gate changed)

The cohort was originally written as "snapshot-day source was
`il_return_overlay`", and the board wrote that value into a column named
`qual`. When SP rows joined the same ledger, `qual` held the rp3
`data_quality_tag` (`marcel_il`, `data_driven_full`) — a MODEL-quality label,
not a VOLUME-construction label, in the same column of the same file. Nothing
broke loudly; the filter still selected only hitters. But a pre-registered
ledger that cannot be filtered unambiguously is precisely what this document's
schema check exists to prevent.

An explicit `vol_source` column now carries the volume construction on every
row regardless of bucket (`il_return_overlay` / `model_passthrough` /
`pace_forward_sp_volume` / `no_sp_volume`), and the cohort keys on it. `qual`
keeps its per-bucket model meaning.

The 2026-08-14 snapshot was rewritten with the corrected schema; the original
is preserved beside it as `predictions_2026-08-14.csv.superseded-schema-incomplete`.
This is permitted under "no revision after outcomes exist" because it happened
the same day the snapshot was written, with zero elapsed outcome time — the
gate, the metric, and the cohort definition are unchanged, and only the column
the cohort is read from was disambiguated. `tests/test_overlay_ledger_schema.py`
now enforces the schema so a future snapshot cannot silently regress.

## Primary metric & gate (locked now)

For each cohort player, realized PA from snapshot date to season end
(statcast). Score |error| of (a) pace-forward and (b) ESPN-date overlay
against realized PA-implied FP-neutral volume (PA itself, not FP — volume is
the quantity under test).

**Gate: settle on 2026-09-10 or when n ≥ 8 cohort players have ≥ 3 weeks
elapsed, whichever is later. Overlay ships as default for ESPN-dated IL
returnees iff it beats pace-forward on median |PA error| for the cohort
(any margin) AND does not lose on more than 40% of players.** Small-n is
acknowledged; the gate is deliberately modest and the result feeds the
offseason full state-model build either way.

No revision after outcomes exist. Cohort as of registration: Oneil Cruz
(ret 8/14), Aaron Judge (ret 8/25) — Glasnow/Pivetta are SP-bucket (starts,
not PA) and are OUT of this study's cohort.
