---
name: volume-watch
description: Surface PLAYING-TIME movers — players whose validated model volume projection (RoS PA/team-game for hitters, GS/team-game for SPs) diverges most from their naive season pace, ranked by FP IMPACT (volume gap x rh3/rp3 rate), with a live ESPN ownership overlay (MINE / opponent / FA). RISERS = role expanding (lineup-spot promotion, IL-return ramp, rotation entry) BEFORE the counting stats make it obvious; FADERS = role eroding. The volume parallel of /trending — trending = getting physically BETTER, volume-watch = playing MORE. Use when the user asks "who's gaining playing time", "role risers", "volume movers", "whose role is shrinking", "playing time watch", "who's playing more/less than their season line suggests", "lineup promotions", "rotation entries", "volume watch". DISPLAY/DECISION layer only — never moves an rh3/rp3 projection.
---

# volume-watch — playing-time movers board

## What this is

The **volume layer's decision surface**. Playing time is the #1 forward-error
lever — realized volume explains 3-5x more forward-total variance than rate —
yet every other skill reads the RATE side. This board reads the VOLUME side:
the validated volume models (`xfp_volume` / `xfp_sp_volume`, hitter +0.074 /
SP +0.100 Spearman vs naive pace, 7/7 yrs, holdout 2/2 each; refresh steps
4.09/4.09b) are recency-weighted (`pa_last21` / `gs_last21` features), so when
the model's projected RoS volume pulls away from the naive season-to-date
pace, that IS the recent role change, quantified — a lineup-spot promotion, an
IL return ramping to full-time, a rotation entry — before the counting stats
make it obvious.

- **RISER** — `proj_ros_vol >> naive_pace`: role expanded recently. FA risers
  are the pickup edge (the headline section).
- **FADER** — `proj_ros_vol << naive_pace`: role eroding (or IL'd — check the
  `IL@split` flag). MINE faders are the warning list.
- **Ranked by IMPACT, not raw gap**: `impact = (proj_vol − pace) × rate` =
  FP per TEAM-GAME the volume move is worth (rate = `xfp_rh3_per_pa` /
  `xfp_rp3_per_start`), so a +1.5 PA/tg move on a 0.60 FP/PA bat outranks the
  same move on a 0.38 bat, and hitter/SP impacts share one unit.

Positioning vs `/trending`: **trending = the PHYSICAL tool moving (bat speed /
velo); volume-watch = the ROLE moving (PA / GS).** They're orthogonal — a
player rising on BOTH lists (tool up AND role up) is the strongest pickup
signal in the repo. Cross-check any headline FA riser here against
`python scripts/xfp/run_trending.py --names "X"` before adding, and feed the
final call through `/triangulate` / `/fa-pickup-deep-dive`.

## Hard rules

1. **Display/decision layer ONLY (Rule 13).** The volume model is already
   consumed by xfp_board and the snapshot logger for RoS TOTALS
   (rate × volume, validated 2026-07-09); this skill just SURFACES the movers.
   Never use the gap to move an rh3/rp3/Blended-xFP number.
2. **Ownership is LIVE.** Every run walks `all_teams()` fresh and derives
   MY team name from a live `my_roster()` id-overlap — never session memory
   (`/roster-verify` rule). Anything on no roster = FA (all-8-rosters check,
   Connelly-Early safe).
3. **All joins by MLBAM id** (`resolve_batter_id` / `resolve_pitcher_id` with
   team + position/role hints; normalized FULL-name fallback is
   skip-on-ambiguous). Never last-name contains (Muncy / Warren collisions).
4. **Read the flags before acting.**
   - `IL@split` — player was on IL at the data split; a FADER here is an
     injury absence, not a benching. A MINE fader with `IL@split` (e.g. Judge)
     is an IL-timeline question, not a drop question.
   - `IL-return` — SP back from IL within ~30 days; riser = ramp to full
     rotation share (often the best stash-exit timing signal).
   - `marcel-rate` — SP rate is a SUPPRESSED Marcel prior
     (`data_quality_tag=marcel_il`), so impact is understated; rank the RATE
     of these arms by Stuff+ `proj_ros_fp` (`sp_stuff_model.py`), per the
     marcel_il gotcha. The VOLUME read is still valid.
   - `med-rate` — hitter has no rh3 row; rate is the league median (rough).
5. **Low-pace prospects need a second look.** A huge riser gap off a tiny
   pace (recent callup, pace < ~1 PA/tg) is real role news but a thin rate
   sample — confirm the bat via `/shadow-scout`-style level reads,
   `/trending` level fallback, or `/fa-pickup-deep-dive` before FAAB.
6. **RPs are out of scope.** The SP volume model covers STARTS only; RP
   opportunity (saves/holds/leverage) is `/fa-rp-pool` + rprs2 territory.

## How to run

```bash
# Full board: hitters + SPs, FA RISERS / MINE FADERS headlined,
# then all-owner riser/fader boards (top 15 each), CSV persisted
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_volume_watch.py

# Ad-hoc cards
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_volume_watch.py --names "Kyle Teel, Dean Kremer"

# Deeper boards
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_volume_watch.py --top 25
```

Engine: `scripts/xfp/run_volume_watch.py`. Output CSV:
`data/outputs/volume_watch.csv` (one row per volume-model player, hitters +
SPs, with `direction`, `impact`, `own`, `flags` — other skills can join it by
`mlbam_id`).

## Reading the output

- `proj` / `pace` — model RoS volume vs naive season pace (PA/tg or GS/tg).
- `gap` — proj − pace; the role signal.
- `pct` — volume percentile within the position universe.
- `L21` — raw PA (hitters) / GS (SPs) in the last 21 days: the recency
  evidence behind the model's read (Judge L21=0 explains his fader row).
- `rate` / `impact` — FP/PA or FP/start, and gap × rate = FP/team-game.
- Day-over-day section — WoW `proj_volume` deltas from
  `data/research/player_projection_history.parquet`. Logging began
  **2026-07-09**; the section prints `insufficient history (n days)` and
  auto-activates once ≥7 daily snapshots carry `proj_volume`.

## Caveats / scope

- The gap-vs-pace board is a LEVEL comparison (model vs season pace), so it
  also fires on early-season role changes that are already weeks old; the
  day-over-day section (once history accumulates) is the true "changed THIS
  week" detector — prefer it for freshness once live.
- Hitter volume model covers ~500 bats with a PA floor; SP model ~260 arms.
  Absent players (deep-bench, most rookies pre-callup) simply have no row.
- 4 rostered ESPN players currently fail mlbam resolution (two-way/ohtani-class
  edge cases) — they'd show as FA if they had a volume row; count is printed
  in the header every run.

## Future (proposals — do NOT wire without owner sign-off)

- **fa-monitor signal type P (volume riser):** add "FA hitter/SP with volume
  gap ≥ +1.0 PA/tg (≥ +0.05 GS/tg) and impact ≥ +0.5 FP/tg" as a scanned
  signal in `run_fa_monitor.py`, firing HIGH when the player also rises on
  /trending. Not wired here per the no-edit rule on that engine.
- **WoW delta alerts:** once ≥7 days of `proj_volume` history exist, flag
  players whose proj_volume moved ≥2 population SDs in a week.
- **Refresh integration:** a `volume_watch.csv` regen step in
  `refresh_dashboards.py` (post-4.09b) so the CSV is never stale.
