# PL name-resolution audit — 2026-06-05

Files scanned: 40
Total named players across all articles: 4,365

| Outcome | Count | Pct |
|---|---:|---:|
| clean | 4,304 | 98.6% |
| collision_guarded | 40 | 0.9% |
| fail_no_match | 15 | 0.3% |
| ambiguous_new_collision | 6 | 0.1% |

**Resolution rate (clean + guarded): 4,344/4,365 = 99.5%**

## Newly-discovered ambiguous names (2)

Names whose normalized form maps to >1 mlbam_id in the multiyr cache, not in KNOWN_COLLISIONS.

| Name | mlbam_ids |
|---|---|
| Luis Garcia | [472610, 677651] |
| Luis García | [472610, 677651] |

## Failed-to-match names (13 unique)

Top 50 by article count:

| Name | Article count | Sample file |
|---|---:|---|
| Mike Soroka | 2 | pl_sp_2019_W1.json |
| Hyun-Jin Ryu | 2 | pl_sp_2019_W1.json |
| Matt Boyd | 1 | pl_sp_2019_W1.json |
| Cody Poteet | 1 | pl_sp_2021_W13.json |
| Tommy Romero | 1 | pl_sp_2022_W1.json |
| Drey Jameson | 1 | pl_sp_2023_W2.json |
| Allan Winans | 1 | pl_sp_2023_W21.json |
| Louie Varland | 1 | pl_sp_2024_W2.json |
| AJ Smith-Shawver | 1 | pl_sp_2025_W1.json |
| Didier Fuentes | 1 | pl_sp_2025_W13.json |
| Sawyer Gipson-Long | 1 | pl_sp_2025_W13.json |
| Luis L. Ortiz | 1 | pl_sp_2025_W13.json |
| Jack Perkins | 1 | pl_sp_2025_W21.json |

## Per-file detail

| File | Total | Clean | Guarded | Fail | Ambig |
|---|---:|---:|---:|---:|---:|
| pl_h_2020_late.json | 146 | 145 | 1 | 0 | 0 |
| pl_h_2020_mid.json | 146 | 144 | 2 | 0 | 0 |
| pl_h_2021_early.json | 148 | 146 | 2 | 0 | 0 |
| pl_h_2021_late.json | 146 | 144 | 2 | 0 | 0 |
| pl_h_2021_mid.json | 149 | 147 | 2 | 0 | 0 |
| pl_h_2022_W1.json | 150 | 148 | 2 | 0 | 0 |
| pl_h_2022_W13.json | 150 | 147 | 3 | 0 | 0 |
| pl_h_2022_W21.json | 149 | 147 | 2 | 0 | 0 |
| pl_h_2023_W13.json | 148 | 146 | 2 | 0 | 0 |
| pl_h_2023_W21.json | 150 | 148 | 2 | 0 | 0 |
| pl_h_2024_W1.json | 150 | 148 | 2 | 0 | 0 |
| pl_h_2024_W13.json | 150 | 148 | 2 | 0 | 0 |
| pl_h_2024_W15.json | 150 | 148 | 2 | 0 | 0 |
| pl_h_2025_W1.json | 150 | 147 | 3 | 0 | 0 |
| pl_h_2025_W13.json | 150 | 146 | 4 | 0 | 0 |
| pl_h_2025_W20.json | 150 | 147 | 3 | 0 | 0 |
| pl_rp_2020_W13.json | 30 | 30 | 0 | 0 | 0 |
| pl_rp_2021_W12.json | 29 | 29 | 0 | 0 | 0 |
| pl_rp_2022_W14.json | 30 | 30 | 0 | 0 | 0 |
| pl_rp_2023_W11.json | 30 | 30 | 0 | 0 | 0 |
| pl_rp_2024_W13.json | 30 | 30 | 0 | 0 | 0 |
| pl_rp_2024_top100sv_hld.json | 96 | 96 | 0 | 0 | 0 |
| pl_rp_2025_W13.json | 40 | 40 | 0 | 0 | 0 |
| pl_sp_2019_W1.json | 100 | 97 | 0 | 3 | 0 |
| pl_sp_2020_W1.json | 100 | 98 | 0 | 2 | 0 |
| pl_sp_2021_W13.json | 99 | 97 | 0 | 1 | 1 |
| pl_sp_2021_W2.json | 99 | 98 | 1 | 0 | 0 |
| pl_sp_2021_W21.json | 100 | 99 | 0 | 0 | 1 |
| pl_sp_2022_W1.json | 100 | 98 | 0 | 1 | 1 |
| pl_sp_2022_W13.json | 100 | 99 | 0 | 0 | 1 |
| pl_sp_2022_W21.json | 100 | 99 | 0 | 0 | 1 |
| pl_sp_2023_W13.json | 100 | 99 | 1 | 0 | 0 |
| pl_sp_2023_W2.json | 100 | 98 | 0 | 1 | 1 |
| pl_sp_2023_W21.json | 100 | 98 | 1 | 1 | 0 |
| pl_sp_2024_W13.json | 100 | 100 | 0 | 0 | 0 |
| pl_sp_2024_W2.json | 100 | 98 | 1 | 1 | 0 |
| pl_sp_2024_W21.json | 100 | 100 | 0 | 0 | 0 |
| pl_sp_2025_W1.json | 100 | 99 | 0 | 1 | 0 |
| pl_sp_2025_W13.json | 100 | 97 | 0 | 3 | 0 |
| pl_sp_2025_W21.json | 100 | 99 | 0 | 1 | 0 |