---
name: matchup-audit
description: Cross-check the current matchup dashboard's projections against ground truth (MLB Stats API confirmed probables + rotation-gap predictions + ESPN injury status). Flags specific bugs — IL'd players projected non-zero, MLBAM lookup failures producing None==None matches, today's games excluded, undercount of SP starts, win probability extremes. Use whenever the user says "the matchup dashboard looks broken", "the SP start logic seems off", "audit the matchup page", or after any change to build_matchup_dashboard.py.
---

# matchup-audit

You are auditing the matchup dashboard for projection correctness. The
skill exists because the dashboard's complexity (3 player buckets ×
6-day window × confirmed/predicted starts × cap math × variance model)
creates many failure modes that aren't visible without explicit checks.

We found 4 distinct bugs in one audit session (2026-05-19):
1. `today_s < g['date']` strict excluded today's games
2. Only confirmed probables counted (no rotation-gap fallback)
3. `mlbam=None` false-matching TBD probables (None==None=True)
4. IL'd pitchers had stale probables not filtered

Future changes to `build_matchup_dashboard.py` can regress any of these.
This skill catches them before they mislead a weekly decision.

---

## Inputs

No required inputs. Auto-detects current scoring week from ESPN.

Optional:
1. **Specific player to investigate** — e.g., "audit Henderson's row"
   for focused debugging
2. **Cross-comparison mode** — compare against `/sp-week-plan` output
   line by line

---

## Step 1 — Pull current dashboard state

```bash
# Read the deployed matchup.html (xfp-model is the source of truth for
# GitHub Pages; data/outputs/matchup.html is the mirror)
DASHBOARD = "xfp-model/docs/matchup.html"
```

Extract from the HTML:
- WTD scores (Ligers + Opp)
- Total projected (Ligers + Opp)
- Win probability
- SP cap message ("⚠ SP cap at maximum: N probable starts" or "Only N
  probable starts — add a streamer")
- Each rostered player's row with: position, units, rest, total

Use regex on the HTML structure. The matchup.html format:
- Player row: `<tr><td>NAME ...</td><td>POS</td>...<td><b>FP</b></td>`
- Breakdown rows: `<tr class="breakdown"><td>→ DATE vs OPP ...`
- Cap status: `<p class="notes"><b>⚠ SP cap...</b> N probable starts`
- Action items: `<li class="urgency-X">ICON TEXT</li>`

---

## Step 2 — Build ground truth for SP starts

Pull confirmed probables from MLB Stats API for the week:

```python
import requests
roster_sp_ids = {<name>: <mlbam_id>, ...}  # from cached map or API resolve

url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1"
       f"&startDate={today}&endDate={week_end}&hydrate=probablePitcher,team")
data = requests.get(url, timeout=15).json()
confirmed = [...]  # list of {date, name, opp, home} where probable matches roster SP
```

Then for each healthy SP (not on IL), predict rotation-gap starts:

```python
def predict_remaining(pid, latest_actual_date, confirmed_dates, week_end):
    # gap from last 2 gameLog starts, clamped 4-7
    # anchor to max(latest_actual, latest_confirmed)
    # predict up to 3 dates, dedup ±1d with confirmed
    ...
```

Total ground-truth starts = `len(confirmed) + len(predicted_unique)`.

---

## Step 3 — Cross-reference dashboard vs ground truth

Build the comparison table:

| Check | Dashboard says | Ground truth | Status |
|---|---|---|---|
| Total SP starts | N from cap message | M from API+rotation | ✓ if N==M |
| IL'd SPs projected | Fried: X FP | Fried IL15: 0 expected | ⚠ if X>0 |
| Today's games included | Today's confirmed shown? | Yes per MLB API | ⚠ if missing |
| Henderson MLBAM-resolution | Show real start count | Real start (1 predicted) | ⚠ if dashboard shows 3+ |
| Win probability sanity | X% | (visual check) | ⚠ if >97% or <3% |

For EACH mismatch, identify the likely bug pattern:

### Bug pattern A: IL'd SP projected non-zero
- Symptom: Fried/Glasnow/Greene row shows units > 0
- Cause: `injuryStatus` filter missing in project_player SP block
- Fix: `if inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', ...): return out`

### Bug pattern B: SP undercount (e.g., "Only N starts" with N < 7)
- Symptom: Dashboard says under-cap when reality is 10 starts
- Cause: Confirmed-only projection, no rotation-gap fallback
- Fix: Call `_predict_rotation_starts()` for non-confirmed late-week

### Bug pattern C: Player projected for too many starts
- Symptom: Single SP shows 3+ starts (impossible — rotation is 5+ days)
- Cause: `mlbam=None` and `g.get('my_probable_id') == None` is True for
  any game with TBD probable
- Fix: `if mlbam is None: skip` OR require `g.get('my_probable_id') is not None`

### Bug pattern D: Today's games not counted
- Symptom: Today's confirmed start shows no rest-of-week projection
  AND WTD hasn't yet credited it
- Cause: `today_s < g['date']` strict filter
- Fix: Change to `today_s <= g['date']`

### Bug pattern E: Hitter expected-games count seems off
- Symptom: Hitter row shows fewer games than team has scheduled
- Cause: Same `today_s <` strict filter, OR opponent factor zeroing
- Verify: count team games in MLB API window

### Bug pattern F: Win probability extreme (>97% or <3%)
- Symptom: Unrealistic confidence
- Cause: Variance underestimated (sigma2 too low) — sometimes due to
  missing SP starts driving down combined variance
- Verify: opponent should have ~similar variance to your team

---

## Step 4 — Spot-check IL slots

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
il_players = roster[roster['injured'] | (roster['lineup_slot']=='IL')]
```

For each IL'd player, verify the dashboard shows:
- Their row in the "Injury Status" section
- Zero FP projection in the lineup table
- No predicted starts (for SPs)

Any IL'd player with non-zero projection is bug A.

---

## Step 5 — Spot-check MLBAM resolution

For each rostered player, verify the dashboard would resolve a valid
MLBAM ID:

```python
# Replicate the build's lookup logic
from scripts.xfp.build_matchup_dashboard import player_mlbam_lookup
for player_name in roster_names:
    mlbam = player_mlbam_lookup(player_name)
    if mlbam is None:
        # Try API fallback (only works if /matchup-audit invokes it)
        print(f"⚠ {player_name}: not in cached CSVs, requires API resolve")
```

Any None lookup for a roster player is a latent bug C waiting to fire
when their team has a TBD probable on a day they're not actually
pitching.

---

## Step 6 — Cross-reference with /sp-week-plan

If `/sp-week-plan` has been run today (or run it fresh), compare its
SP start identification to the dashboard's:

```
sp-week-plan says:        matchup dashboard says:    Status
Bradish 2 starts          Bradish 2 starts           ✓
Messick 2 starts          Messick 2 starts           ✓
Henderson 1 start         Henderson 1 start          ✓
... etc ...
TOTAL: 10                 SP cap: 10/10              ✓
```

Discrepancy means a regression — investigate which bug pattern applies.

---

## Step 7 — Report findings

```markdown
## Matchup dashboard audit — Week N (date range)

### Headline numbers (from dashboard)
- Ligers WTD <X> + projected <Y> = total <Z>
- Opp    WTD <X> + projected <Y> = total <Z>
- Win prob: <P>%

### Ground truth comparison
[Table with check/dashboard-says/truth/status per Step 3]

### Bugs found (if any)
- Bug pattern A — IL'd SP projected: <list of affected players>
- Bug pattern B — SP undercount: dashboard says N, reality M
- (etc.)

### Recommended fixes
- For each bug found, point to specific line in build_matchup_dashboard.py
- Suggest the fix pattern from Step 3 catalog

### Status
✓ Clean — projections match ground truth, dashboard is reliable
OR
⚠ N bugs found — rebuild required after fixes; do not trust current
  dashboard for weekly decisions until resolved
```

---

## Anti-patterns this skill exists to prevent

- **Auditing matchup.html without rerunning the build.** A "fresh"
  matchup.html in xfp-model might be from 3 days ago; check the file
  timestamp. If stale, the audit is auditing stale state.
- **Reporting "looks fine" without spot-checking specific players.**
  Bug pattern C only manifests for specific players (callups without
  cached MLBAM IDs); whole-dashboard summary metrics can hide it.
- **Treating "Win probability 97%+" as a quality indicator.** It's a
  symptom of UNDER-counting both teams' projections (the gap looks
  bigger when both totals are smaller). Always verify SP start count
  matches ground truth.
- **Skipping the IL spot-check.** Bug A reappears whenever the
  injuryStatus filter is touched. Always check.
- **Not running `/sp-week-plan` for the ground-truth comparison.**
  The matchup dashboard and sp-week-plan should agree on start count
  (both use same rotation-gap logic). Mismatch = regression.

---

## When NOT to use this skill

- Routine matchup refresh — use `/refresh-matchup` (which DOES include
  Step 2 sanity checks but skips the full audit)
- Investigating a specific player not in the dashboard at all — use
  `/fa-pickup-deep-dive` or `/hitter-compare`
- Diagnosing an ESPN API issue (matchup score not updating) — that's
  upstream of this skill; check ESPN's site directly
- Daily/multi-day variance investigation — variance estimates in the
  dashboard are static parameters (SIGMA_PER_*); auditing them requires
  validation work, not a single dashboard check
