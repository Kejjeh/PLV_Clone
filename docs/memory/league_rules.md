# League rules — SP-cap mechanics (full text)

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). Nothing here
was rewritten — CLAUDE.md keeps the headline, this file keeps the detail. -->

- **SP-start cap is PERIOD-AWARE — never hardcode 10.** The cap is
  **10 SP starts per SCORING WEEK**; starts past the cap are zeros. **No**
  slot count limit on SPs themselves. A few periods span multiple weeks and
  carry a bigger cap:
  - Standard 1-week period → **10**.
  - **2-week playoff rounds → 20** (general rule `10 × weeks`, auto-derived
    from ESPN `matchupPeriods`).
  - **2026 All-Star block (period 15, Jul 6–19) → 16** (explicit override —
    a 2-calendar-week span but the ASG dead days Jul 13–15 remove game-days,
    so it is NOT 20).
  Always resolve the live cap via `plv_clone.cap_math.sp_cap_for_period(period,
  weeks=weeks)` (or `scripts/xfp/lib/period_meta.resolve_period_meta(league,
  period)`), and read the authoritative banked count from ESPN statId-33
  (`espn_period_meta`). Add a new ASG-style exception by adding one entry to
  `PERIOD_CAP_OVERRIDES` + `PERIOD_WINDOW_OVERRIDES`. Committed 2026-07-11.
