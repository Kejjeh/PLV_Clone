"""
pull_bref_rp_ir.py — Baseball-Reference RP inherited-runner scraper.

Fills the gap left by FanGraphs' combined-stats JSON endpoint (type=8 used by
pull_fg_rp_leverage.py), which does NOT expose IR / IS% (verified by 544-key
dump on 2026-05-29).

Source: https://www.baseball-reference.com/leagues/majors/{year}-reliever-pitching.shtml
The data we want lives in `<table id="players_reliever_pitching">`, which BBRef
hides inside an HTML comment to discourage scraping. We strip the comment
wrapper, parse the table with pandas, then map BBRef player IDs back to MLBAM
IDs via the existing FanGraphs leverage CSV (which has both mlb_id and
player_name_fg + team for the same cohort).

Output: data/research/xfp_cache/rp_ir_is_2018_2026.csv
Columns: mlb_id, season, ir, is_pct, bref_id, name_bref, team_bref, ip_bref

Years: 2018-2026 minus 2020 (RP archetype panel skips COVID-short year).

Run with:  python -X utf8 scripts/xfp/pull_bref_rp_ir.py

Polite scraping: 4s warm-up + 6s sleep between year requests (well within
BBRef's 20-requests/min ToS). Uses requests + BeautifulSoup — no browser
needed (BBRef does not Cloudflare-gate this endpoint).
"""
from __future__ import annotations
import sys, time, re, unicodedata
from io import StringIO
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / 'rp_ir_is_2018_2026.csv'
FG_LEVERAGE_CSV = OUT_DIR / 'fangraphs_rp_leverage_2018_2026.csv'

# 2017-2026 minus 2020 (matches RP archetype convention)
YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def _norm_name(s: str) -> str:
    """Lowercase, strip accents/punct/whitespace for fuzzy name matching.

    item 10 (2026-07-04): NOT routed to name_match — this STRIPS SUFFIXES
    (jr/sr/ii/iii) because BBRef attaches them and FanGraphs may not, so the
    suffix strip is load-bearing for the bref<->fg merge. join_key keeps
    suffixes (wrong owner here); the owner's _normalize strips them but differs
    on edge cases (e.g. 'Cal Ripken III' -> _normalize 'cal ripken' vs this
    fn's buggy 'cal ripkeni'). Migrating needs an output byte-diff of the
    bref/fg IL merge first; left local with suffix-aware behavior.
    """
    if not isinstance(s, str):
        return ''
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^a-zA-Z0-9 ]', '', s).lower().strip()
    s = re.sub(r'\s+', ' ', s)
    # Drop common suffixes that BBRef sometimes attaches with * or # markers
    s = s.replace(' jr', '').replace(' sr', '').replace(' ii', '').replace(' iii', '')
    return s.strip()


def fetch_year(session: requests.Session, year: int) -> pd.DataFrame | None:
    url = f'https://www.baseball-reference.com/leagues/majors/{year}-reliever-pitching.shtml'
    print(f'  [{year}] GET {url}', flush=True)
    r = session.get(url, timeout=45)
    if r.status_code != 200:
        print(f'  [{year}] HTTP {r.status_code}', flush=True)
        return None
    # BBRef serves UTF-8 but requests sometimes guesses ISO-8859-1 from
    # Content-Type. Force UTF-8 so accented names (José, Cedeño) parse cleanly.
    r.encoding = 'utf-8'

    # Table is hidden inside an HTML comment — strip the wrapper.
    m = re.search(
        r'<!--\s*(<div class="table_container" id="div_players_reliever_pitching".*?</div>)\s*-->',
        r.text, re.DOTALL,
    )
    if not m:
        # Fall back to raw table search in case BBRef inlines it
        m = re.search(
            r'(<table[^>]*id="players_reliever_pitching".*?</table>)',
            r.text, re.DOTALL,
        )
    if not m:
        print(f'  [{year}] table not found', flush=True)
        return None
    tbl_html = m.group(1)

    df = pd.read_html(StringIO(tbl_html))[0]
    # Drop header-repeat rows (BBRef injects one every ~25 data rows). pandas
    # represents these as rows where Rk == 'Rk' or Name == 'Name'.
    df = df[df['Rk'].astype(str) != 'Rk'].copy()
    df = df[df['Name'].astype(str).str.strip().str.lower() != 'name'].copy()
    df = df[df['Name'].notna() & (df['Name'].astype(str).str.strip() != '')].copy()
    df = df.reset_index(drop=True)

    # Walk the <tr> blocks in order, skipping header-repeat rows, to extract
    # bref_id per data row. A header row has "Name" as the player cell text
    # and no /players/x/...shtml href.
    row_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl_html, re.DOTALL)
    bref_ids: list[str | None] = []
    for rb in row_blocks:
        nm_match = re.search(r'data-stat="player"[^>]*>(?:<a[^>]*>)?([^<]+)', rb, re.DOTALL)
        if nm_match and nm_match.group(1).strip() == 'Name':
            continue  # header-repeat row
        if 'data-stat="player"' not in rb and 'data-stat="ranker"' not in rb:
            continue  # row without identifying cells
        pid = re.search(r'/players/[a-z]/([a-z0-9]+)\.shtml', rb)
        bref_ids.append(pid.group(1) if pid else None)

    if len(bref_ids) == len(df):
        df = df.assign(bref_id=bref_ids)
    else:
        print(f'  [{year}] bref_id row-count mismatch ({len(bref_ids)} vs {len(df)}); '
              f'leaving null — IR/IS% still usable via name match', flush=True)
        df = df.assign(bref_id=None)

    df = df.assign(season=year)

    # When a player was traded mid-season, BBRef emits one TOT row + per-team
    # splits. We want only the TOT (Tm == "TOT") if it exists; otherwise the
    # single-team row. Group on bref_id and pick the row with max IP.
    keep = ['bref_id', 'season', 'Name', 'Tm', 'IP', 'G', 'IR', 'IS', 'IS%']
    keep = [c for c in keep if c in df.columns]
    out = df[keep].copy()
    out = out.rename(columns={
        'Name': 'name_bref', 'Tm': 'team_bref', 'IP': 'ip_bref',
        'G': 'g_bref', 'IR': 'ir', 'IS': 'is_count', 'IS%': 'is_pct_raw',
    })

    # Coerce numeric
    for c in ('ir', 'is_count', 'ip_bref', 'g_bref'):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors='coerce')

    # BBRef "IS%" column is the % of inherited runners that SCORED (data-stat
    # name = `inherited_score_perc`). We invert to STRANDED% to align with the
    # FanGraphs convention (IR-S%, fireman skill = % stranded). Higher = better.
    def parse_pct(v):
        if pd.isna(v):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace('%', '').strip()
        if s in ('', '-', 'nan'):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    scored_pct = out['is_pct_raw'].apply(parse_pct)
    out['is_pct'] = scored_pct.apply(lambda v: round(100.0 - v, 1) if v is not None else None)
    out = out.drop(columns=['is_pct_raw'])

    # If a bref_id has multiple rows in the year (player was traded), keep the
    # TOT (totals) row when present, else the row with the most IP. Use a
    # sort+drop_duplicates pattern rather than groupby.apply, which can demote
    # the groupby key (bref_id) to the index and drop it from the column set.
    if out['bref_id'].notna().any():
        # Sort so TOT rows come first (sort_key=0 for TOT, 1 otherwise),
        # then by IP descending. drop_duplicates keeps the first row per group.
        out = out.copy()
        out['_is_tot'] = (out['team_bref'] == 'TOT').astype(int)
        # Rows with no bref_id stay as-is (one per row, never dup-collapsed)
        no_id = out[out['bref_id'].isna()].copy()
        has_id = out[out['bref_id'].notna()].copy()
        has_id = has_id.sort_values(['bref_id', '_is_tot', 'ip_bref'],
                                    ascending=[True, False, False])
        has_id = has_id.drop_duplicates(subset=['bref_id'], keep='first')
        out = pd.concat([has_id, no_id], ignore_index=True)
        out = out.drop(columns=['_is_tot'])

    print(f'  [{year}] {len(out)} unique RPs; IR populated={out["ir"].notna().sum()}, '
          f'IS% populated={out["is_pct"].notna().sum()}', flush=True)
    return out


def attach_mlb_id(bref_df: pd.DataFrame, fg_df: pd.DataFrame) -> pd.DataFrame:
    """Bridge bref_id → mlb_id via (norm_name, season) join against FG cache.

    Strategy:
      1. Per (norm_name, season): if unique on both sides, direct merge.
      2. Multiple matches: tiebreak on team (BBRef Tm vs FG team — both use
         standard 3-letter abbrs; minor disagreements exist for traded players
         but TOT row matches OPS-row-team-as-most-frequent, which is what FG
         reports for the season totals row).
      3. No match: drop with a count warning.
    """
    b = bref_df.copy()
    f = fg_df.copy()
    b['_nn'] = b['name_bref'].apply(_norm_name)
    f['_nn'] = f['player_name_fg'].apply(_norm_name)

    # Direct merge on (_nn, season)
    f_slim = f[['_nn', 'season', 'mlb_id', 'team']].rename(columns={'team': 'team_fg'})
    merged = b.merge(f_slim, on=['_nn', 'season'], how='left')

    # When >1 fg_id matches per (bref_id, season), pick the one with matching
    # team. Sort+drop_duplicates pattern: rows where team matches come first
    # (sort_key=0 for match, 1 otherwise), then mlb_id non-null first.
    if 'bref_id' in merged.columns:
        merged['_id_key'] = merged['bref_id'].fillna('NO_BREF_' + merged['name_bref'].apply(_norm_name))
    else:
        merged['_id_key'] = 'NO_BREF_' + merged['name_bref'].apply(_norm_name)
    merged['_team_match'] = (
        merged['team_bref'].fillna('') == merged['team_fg'].fillna('')
    ).astype(int)
    merged['_has_id'] = merged['mlb_id'].notna().astype(int)
    merged = merged.sort_values(['_id_key', 'season', '_has_id', '_team_match'],
                                ascending=[True, True, False, False])
    merged = merged.drop_duplicates(subset=['_id_key', 'season'], keep='first')
    merged = merged.drop(columns=['_nn', '_id_key', '_team_match', '_has_id', 'team_fg'],
                         errors='ignore').reset_index(drop=True)

    n_total = len(merged)
    n_mapped = int(merged['mlb_id'].notna().sum())
    print(f'  mlb_id mapped: {n_mapped}/{n_total} ({100*n_mapped/n_total:.1f}%)', flush=True)
    return merged


def main():
    if OUT_PATH.exists():
        try:
            ex = pd.read_csv(OUT_PATH)
            have = set(int(y) for y in ex['season'].dropna().unique())
            if all(y in have for y in YEARS) and ex['is_pct'].notna().sum() > 500 \
                    and ex['mlb_id'].notna().sum() > 500:
                print(f'Cached {OUT_PATH.name} already has all years + IS% + mlb_id — skip.', flush=True)
                return
        except Exception:
            pass

    if not FG_LEVERAGE_CSV.exists():
        print(f'FATAL: FG leverage cache not found at {FG_LEVERAGE_CSV} — '
              f'run pull_fg_rp_leverage.py first.', flush=True)
        sys.exit(1)
    fg_df = pd.read_csv(FG_LEVERAGE_CSV)
    fg_df['season'] = pd.to_numeric(fg_df['season'], errors='coerce').astype('Int64')

    session = requests.Session()
    session.headers.update(HEADERS)
    # Warm-up (BBRef doesn't gate, but courteous)
    try:
        session.get('https://www.baseball-reference.com/', timeout=30)
    except Exception:
        pass
    time.sleep(2)

    frames = []
    for yr in YEARS:
        per_year_path = OUT_DIR / f'rp_ir_is_{yr}.csv'
        if per_year_path.exists():
            try:
                cached = pd.read_csv(per_year_path)
                if len(cached) > 50 and cached['is_pct'].notna().sum() > 30:
                    print(f'[{yr}] per-year cached -> using ({len(cached)} rows)')
                    frames.append(cached)
                    time.sleep(0.1)
                    continue
            except Exception:
                pass
        try:
            df = fetch_year(session, yr)
            if df is not None and len(df) > 30:
                df.to_csv(per_year_path, index=False)
                frames.append(df)
                print(f'[{yr}] SUCCESS: {len(df)} RPs written to {per_year_path.name}')
            else:
                print(f'[{yr}] FAILED: empty/insufficient')
        except Exception as e:
            print(f'[{yr}] EXCEPTION: {e}')
        time.sleep(6)  # polite pacing

    if not frames:
        print('No data scraped — exiting.')
        sys.exit(1)
    merged_raw = pd.concat(frames, ignore_index=True)
    print(f'\nRaw BBRef rows: {len(merged_raw)}')
    merged_raw['season'] = pd.to_numeric(merged_raw['season'], errors='coerce').astype('Int64')

    final = attach_mlb_id(merged_raw, fg_df)
    final['mlb_id'] = pd.to_numeric(final['mlb_id'], errors='coerce').astype('Int64')

    # Order columns
    cols = ['mlb_id', 'season', 'ir', 'is_pct', 'is_count',
            'bref_id', 'name_bref', 'team_bref', 'ip_bref', 'g_bref']
    cols = [c for c in cols if c in final.columns]
    final = final[cols].sort_values(['season', 'mlb_id']).reset_index(drop=True)
    final.to_csv(OUT_PATH, index=False, encoding='utf-8')
    print(f'Wrote {OUT_PATH}: {len(final)} rows')
    print(f'  years: {sorted(final["season"].dropna().unique().tolist())}')
    print(f'  IR populated: {final["ir"].notna().sum()}')
    print(f'  IS% populated: {final["is_pct"].notna().sum()}')
    print(f'  mlb_id populated: {final["mlb_id"].notna().sum()}')


if __name__ == '__main__':
    main()
