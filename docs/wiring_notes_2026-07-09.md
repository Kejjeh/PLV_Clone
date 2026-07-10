# Wiring notes — 2026-07-09 data-infrastructure batch

Three additive pieces landed today. `refresh_dashboards.py` had uncommitted
in-flight edits, so NOTHING was wired there — the orchestrator should apply
the snippets below. All three scripts are idempotent + fail-soft, so wiring
them non-gating (print a warning, continue) matches the existing step style.

## 1. FanGraphs RoS projection snapshotter (DAILY — wire this one for sure)

New script: `scripts/xfp/pull_fg_ros_projections.py`
Writes date-keyed snapshots to `data/research/fg_proj_cache/{date}_{system}_{bat|pit}.csv`
(+ `manifest.csv`). Skips combos already snapshotted today, so a rerun is free.
The value is the ACCUMULATION — every missed day is a hole in the forward-
validation panel, so it belongs in the daily refresh.

Suggested slot: **step 4.11**, right after the existing 4.10 projection-history
append (both are "persist today's projections for later validation" steps):

```python
    # 4.11. Snapshot FanGraphs RoS projections (steamerr/rzips/ratcdc/
    # rfangraphsdc, bat+pit). Date-keyed accumulation for the ~4-week
    # forward validation of external playing-time/RoS systems. Idempotent
    # (skips combos already pulled today). Cloudflare pass is intermittent
    # -> retries internally; fail-soft.
    ok_fgros = run(
        '4.11. Snapshot FanGraphs RoS projections',
        'python -X utf8 scripts/xfp/pull_fg_ros_projections.py',
        timeout=600,
    )
    if not ok_fgros:
        print('  ⚠ FG RoS projection snapshot failed — continuing (non-gating)')
```

Note: uses `cloudscraper` (already installed). Plain requests AND curl_cffi
are 403'd by Cloudflare on this endpoint; cloudscraper passes intermittently,
so the script retries each combo up to 6x with a fresh scraper. Typical
runtime ~1-3 min for all 8 combos.

## 2. IL transaction ingestion (WEEKLY cadence is enough)

New script: `scripts/xfp/fetch_il_transactions.py`
Historical 2015..today pull is DONE (chunks cached under
`data/research/xfp_cache/il_tx_chunks/`). Incremental reruns only refetch the
current month (~2 requests) and rebuild the derived outputs — cheap, but the
injury-proneness features are as-of-Jan-1 (they only change when new stints
land), so weekly is plenty. If you want it daily anyway it costs ~5s.

Suggested slot: **step 4.12** (or gate on weekday like the existing weekly
cadence steps 1c-1e):

```python
    # 4.12. Refresh IL transaction history + injury-proneness features
    # (current month refetch only; historical chunks cached). Weekly
    # cadence is sufficient — features are as-of-Jan-1. Fail-soft.
    if date.today().weekday() == 0:  # Monday, match other weekly steps
        ok_iltx = run(
            '4.12. Refresh IL transactions + injury proneness',
            'python -X utf8 scripts/xfp/fetch_il_transactions.py',
            timeout=300,
        )
        if not ok_iltx:
            print('  ⚠ IL transaction refresh failed — continuing (non-gating)')
```

Outputs:
- `data/research/xfp_cache/il_transactions_2015_2026.parquet`
- `data/research/xfp_cache/injury_proneness_by_year.csv`
  (per (mlbam_id, year): il_stints_prior3yr, il_days_prior3yr,
  career_il_days_to_jan1 — leakage-safe as of Jan 1)

`--derive-only` flag rebuilds the stint/proneness outputs from the cached
parquet without any API calls.

## 3. Projection snapshot logger upgrade (NO wiring change needed)

`scripts/xfp/build_player_projection_history.py` (already wired at step 4.10)
now also logs per row:
- `position` — hitter `primary_position` from rh3 (null for SP/RP)
- `data_quality_tag` — SP only, from rp3 (`marcel_il` vs `data_driven_*`)
- `proj_volume` — reserved, NaN until a volume model ships

Backward compatible: rows appended before 2026-07-09 read back with NaN in
the new columns (verified with a full-parquet read + rerun-dedup no-op test).
Today's (2026-07-09) rows were appended by this morning's refresh under the
OLD schema and were intentionally NOT rewritten (dedup respected); the new
columns start populating with tomorrow's refresh.
