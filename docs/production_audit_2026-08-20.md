# Production audit — 2026-08-20 (issues-first round)

Method: the /production-audit 4-surface Explore fan-out, deduped against the
2026-07-19 and 2026-07-30 backlogs, top claims spot-verified in the main
session (all spot-checks confirmed this round). Per Josh's instruction the
output is GitHub ISSUES, not same-day fixes — only one trivial hygiene fix
shipped inline.

Context: audited AS ON DISK, including the week's uncommitted changes (PL
cache curl/parse rewrite, rprs2 data_quality_tag, atomic model CSV writes,
opener-aware gs_to, lag imputation, FB-velo + wOBA columns, SEVEN_DAY_DL).
Several findings are follow-ups to exactly those changes.

Registry drift check: tests/test_skills_registered.py 95 passed — clean.
Issue tracker was fully closed (27/27) before this round; no duplicates.

## SHIPPED inline
- .gitignore: `scratchpad_*` + `/fa_rp_pool_full.csv` (30 untracked session
  scratch files, incl. two .pkl a `git add -A` would have committed).

## FILED (17 issues, #28-#44)

Correctness / silent-failure (bug):
- #28 IL-state literals scattered ~14 inline lists — SEVEN_DAY_DL fix landed
  in 2; volume/probables/cap paths still treat concussed players as healthy.
  (Found independently by two surfaces; highest severity this round.)
- #29 rprs2 RoS p25/p75 from differencing independently-clipped quantiles →
  inverted bands; mechanism for the 12 corrupt rows in the 08-19 optimizer run.
- #30 rprs2 data_quality_tag inverts rp3 semantics under the same name;
  values outside every skill's vocabulary (Latz tagged lag_imputed).
- #31 opener filter applied to gs_to only; relief_pitches_only + role-rate
  denominators still unfiltered (Montgomery loses ~5 IP; role rates +~10%).
- #32 lag imputation mean-of-ratios vs ratio-of-means + nightly drift from
  2020/partial-2026 rows.
- #33 stuff-windows board still ranked on all-pitch velo; fb_velo has no
  fullness gate.
- #34 non-atomic to_csv on xwoba_l225 + sp_rp_stuff_windows (same race as
  the fixed EmptyDataError).
- #35 PL cache follow-ups: hitter week-vs-fetched staleness, closers
  single-URL fallback gap, RP universe 50 vs 100-row parser.
- #36 refresh step 2.85 timeout 120s < curl fan-out worst case ~400s —
  regression introduced by this week's curl change.
- #37 refresh_all: schedule stage mis-gated; missing non-gating script fails
  the run while printing "not counted".
- #38 refresh visibility bundle: calibration idle-gate keys on .md only; PL
  staleness check after push / skipped on gated nights; 12 discarded run()
  results incl. the 1.7 rh3 substrate; 1.98 plv gate retries 1800s nightly;
  per-artifact withholding consults only ok_profiles.
- #39 optimizer mlbam resolver CSV-only w/ SP cache frozen at 2015-2025 (the
  41 unresolved candidates); per-row projection failures swallowed.
- #40 _current_season_stale duplicated + FileNotFoundError on missing cache.
- #41 validate_role_lag_missing: holdout inside the selection signal;
  hand-rolled Rule 9 arithmetic (run was REJECTED, so no production harm).

Human decision / coverage / hygiene:
- #42 [ready-for-human] Bryan Woo canonical lock RED on fresh PL cache —
  pins a live PL rank; precedent says bucket-only lock on 2nd flip.
- #43 triangulate rendering/FA boundary: 1,259 untested lines; smoke-render
  test proposed.
- #44 data/outputs 261 MB — 30-day retention prune for dated snapshots.

## Deferred / not re-filed
Everything already on the 2026-07-19 backlog (items 6-23) and the 07-30
UNVERIFIED backlog (T13-T29) stands as recorded there. Checked-and-clean
this round: no live-network tests; skip sites all data-gated; refresh
boxscore 3*HLD docstring is correct (scoring.py hd=3.0).
