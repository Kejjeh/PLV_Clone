# BrownU League History

All data captured 2026-05-25 from ESPN historical league pages.

## Files

| File | Contents | Source |
|---|---|---|
| `draft_2024.csv` | Full 2024 snake draft (208 picks, 8 teams) | ESPN draft recap seasonId=2024 |
| `draft_2025.csv` | Full 2025 snake draft (240 picks, 8 teams) | ESPN draft recap seasonId=2025 |
| `rosters_2025_endseason.csv` | End-of-2025-season rosters (all 8 teams, slot+ACQ method) | ESPN league rosters seasonId=2025 |
| `rosters_2024_endseason.csv` | End-of-2024-season rosters (all teams, slot+ACQ method) | ESPN league rosters seasonId=2024 |

## Team name mapping (known continuity)

| 2024 Team | 2025 Team | 2026 Team |
|---|---|---|
| New York Ligers | New York Ligers | New York Ligers |
| Team Solomon | Team Solomon | Team Solomon |
| Big Dumpers | Big Dumpers | Big Dumpers |
| U Just Lost To Yainer Diaz | U Just Lost To Yainer Diaz | U Just Lost To Yainer Diaz |
| Bregman's Wheelbarrows | The Polar Pasquatch (?) | The Polar Pasquatch |
| Big Scoops For All | A Whole Ass Meal (?) | A Whole Ass Meal |
| WAR What Is It Good For? | — | — (may have left/renamed) |
| Jersey St Green Monsters | — | — (may have left/renamed) |
| — | — | Frendy's Fantastic Team |
| — | — | Late Night Bettsing |
| — | — | Boone's |
| — | — | 2015 Draft First Round |

Note: League appears to have had team turnover between 2024 and 2026. 2024 had 8 teams;
2025 draft shows 6-7 teams active; 2026 has 8 teams with different names.

## Key SP breakout players and draft history

| Player | 2024 draft team | 2025 draft team | 2026 status |
|---|---|---|---|
| Hunter Greene | Big Scoops For All (R12, pick 93) | Team Solomon (R22, pick 128) | New York Ligers (drafted/kept) |
| Tarik Skubal | New York Ligers (R7, pick 49) | A Whole Ass Meal (R1, pick 6) | A Whole Ass Meal |
| Justin Steele | WAR What Is It Good For? (R8, pick 63) | New York Ligers (R19, pick 117) | Late Night Bettsing (Mar 26 add) |
| Taj Bradley | U Just Lost (R18, pick 140) | The Polar Pasquatch (R32, pick 191) | U Just Lost (Apr 12 add) |
| Shane Bieber | U Just Lost (R18, pick 140) | New York Ligers (bench, 2025 roster) | U Just Lost (IL, 0 starts 2026) |
| Cole Ragans | WAR What Is It Good For? (R10, pick 79) | New York Ligers (R4, pick 28) | Ligers (active) |
| Bryce Miller | WAR What Is It Good For? (R25, pick 194) | Big Dumpers (R19, pick 111) | U Just Lost (Apr 3 add) |
| Joe Musgrove | U Just Lost (R11, pick 85) | — | Late Night Bettsing (Mar 26) |
| Max Meyer | — | — | Late Night Bettsing (May 25 add) |
| Framber Valdez | Jersey St Green Monsters (R4, pick 26) | The Polar Pasquatch (R7, pick 38) | Ligers |

## Usage

Load in Python:
```python
import pandas as pd
draft_2024 = pd.read_csv('data/reference/league_history/draft_2024.csv')
draft_2025 = pd.read_csv('data/reference/league_history/draft_2025.csv')
```

Cross-reference with 2026 transaction history (from ESPN `league.recent_activity(size=500)`)
to track player movement from draft → end-of-season keeper → 2026 add.
