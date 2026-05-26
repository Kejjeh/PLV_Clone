---
name: roster-verify
description: Verify which players are actually on the user's roster before labeling anyone as "your player", "your SP", "your hitter", etc. Required before any analysis that annotates players by team ownership. Prevents the Weathers/Rasmussen error (2026-05-25) where players on other teams were labeled "Your SP" in an SP performance evaluation because roster membership was assumed from memory instead of verified from the live ESPN API.
---

# roster-verify

You are enforcing a hard rule: **never label a player as rostered by the
user without pulling the live roster first.**

The skill exists because on 2026-05-25, a May 24 SP performance evaluation
labeled Ryan Weathers (Late Night Bettsing) and Drew Rasmussen (2015 Draft
First Round) as "Your SP" — they were on opponent rosters. The user had to
correct this manually. The cause: roster membership was assumed from prior
session context or memory rather than pulled from the live ESPN API.

---

## The rule (non-negotiable)

Before annotating ANY player in ANY analysis with:
- "Your SP / Your RP / Your hitter"
- "On your roster"
- "You own X"
- "Your rostered players on [date]"
- Any similar phrasing implying the user owns that player

You MUST first call:

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
my_names = set(roster['player_name'].str.lower().str.strip())
```

Then check membership explicitly:

```python
def is_mine(player_name: str) -> bool:
    return player_name.lower().strip() in my_names
```

Never assume. Never use memory from a prior turn. Never infer from a
previous roster audit in the same session. The roster changes — IL
transactions, drops, adds happen between sessions and even mid-session.

---

## When this rule fires

Apply before ANY of these:

- SP/RP/hitter performance evaluations ("how did my pitchers do on X date")
- League-wide stat line tables where you annotate teams or ownership
- Drop/add recommendations where you say "your weakest X is Y"
- Matchup previews where you identify "your starters this week"
- Any ad-hoc Statcast pull where you filter or label by roster membership

---

## Implementation pattern

```python
from app.espn_connector import get_my_roster_with_injuries
import unicodedata, re

def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'\s+', ' ', s).strip()

roster = get_my_roster_with_injuries()

# Build set of normalized names + position map
my_players = {
    _norm(row['player_name']): {
        'position': row['position'],
        'lineup_slot': row['lineup_slot'],
        'injured': row['injured'],
        'injury_status': row.get('injury_status', ''),
    }
    for _, row in roster.iterrows()
}

def is_mine(name: str) -> bool:
    return _norm(name) in my_players

def my_tag(name: str) -> str:
    """Return ' ← YOURS' if rostered, '' otherwise."""
    return ' ← YOURS' if is_mine(name) else ''
```

Apply `my_tag(name)` to every row in any performance table before
presenting it to the user.

---

## Canonical failure case

**2026-05-25 — SP performance eval, May 24 data:**

The evaluation table labeled:
- Ryan Weathers → "Your SP" ❌ (on Late Night Bettsing)
- Drew Rasmussen → "Your SP" ❌ (on 2015 Draft First Round)

Actual rostered SPs that started on 5/24:
- Framber Valdez ✓ (6 IP, 5K, 18.0 FP)
- Parker Messick ✓ (5.7 IP, 6K, 17.7 FP)

The other 9 rostered SPs (Soriano, Peralta, Rodón, Henderson, Bradish,
Warren, Fried IL, Glasnow IL60, Greene IL60) did not start that day.

**Root cause:** roster membership was inferred from prior session memory.
The fix is a live API call, every time, no exceptions.

---

## Name-collision roster tagging (critical)

Any roster_tag function that falls back to **last-name-only** matching will
silently assign the wrong team when two players share a surname.

**Canonical case — 2026-05-25:** Logan Henderson (New York Ligers SP) was tagged
as "Boone's Bad Bullpen" because the fallback matched his last name "Henderson"
to Gunnar Henderson (Boone's). The user had to correct this manually.

**Rule:** roster_tag lookups must match on normalized FULL name first, then — only
as a last resort — on (last_name, position) tuple. Never fall back to last name alone.

```python
def roster_tag(sc_name: str, league) -> str:
    """Map Statcast 'Last, First' or display name to 2026 team or FA."""
    if "," in sc_name:
        parts = sc_name.split(",", 1)
        display = parts[1].strip() + " " + parts[0].strip()
    else:
        display = sc_name
    n = _norm(display)
    # Pass 1: full normalized name match (exact)
    for team in league.teams:
        for p in team.roster:
            if _norm(p.name) == n:
                return team.team_name
    # Pass 2: (last, first_initial) tuple — never last-only
    parts = display.split()
    if len(parts) >= 2:
        last, first_init = parts[-1].lower(), parts[0][0].lower()
        for team in league.teams:
            for p in team.roster:
                pparts = p.name.split()
                if (len(pparts) >= 2
                        and pparts[-1].lower() == last
                        and pparts[0][0].lower() == first_init):
                    return team.team_name
    return "FA"
```

The `_harrison_meyer_scan.py` script previously used a single-last-name fallback
that caused the Logan/Gunnar Henderson collision. All roster-tag code must use
the two-pass pattern above.

---

## Anti-patterns

- Using `MY_TEAM = "New York Ligers"` + `df[df['team_name'] == MY_TEAM]`
  from the audit DataFrame to determine roster — the audit DataFrame is
  built from a point-in-time snapshot and may lag transactions.
- Checking a prior turn's roster output and saying "from the audit I can
  see X is yours" — the audit may be from a different date or pre-transaction.
- Skipping the check because "we just ran a roster audit" — the audit shows
  the state at run time, not now.
- Inferring from position ("Weathers is an SP and we discussed SPs") — wrong.
- Using the `pitchers` DataFrame from `league_wide_full_audit` to verify
  ownership — that DataFrame has team names but those come from ESPN and
  can be stale if the audit was run before a transaction.

---

## Integration with other skills

This skill is a **pre-condition** for:

- `/sp-week-plan` — must verify which SPs are actually yours before
  projecting starts
- `/league-deep-audit` — the "New York Ligers ← YOU" section is auto-built
  from ESPN team data, which is correct; but any ad-hoc annotation outside
  the audit pipeline must use `get_my_roster_with_injuries()`
- `/slump-or-decline` — when saying "this player is on your roster"
- `/hitter-compare` — when labeling comparison players as "yours vs theirs"
- Any raw Statcast pull where you filter and label by roster membership

If you are doing an ad-hoc analysis (not routed through the audit pipeline),
always call `get_my_roster_with_injuries()` at the top of the analysis
before labeling anything.
