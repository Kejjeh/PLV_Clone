"""
Build the player universe for the massive triangulate research report.

Outputs 4 CSVs to data/research/triangulate_universe/:
  - my_roster.csv
  - my_drops.csv
  - opp_churn.csv (other teams' adds + drops)
  - fa_above_50fp.csv

Each row: player_name, espn_id, position (raw), bucket (H/SP/RP), source_team, source_action

Run: python scripts/xfp/build_triangulate_universe.py
"""
import sys, os, unicodedata
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
from plv_clone.projections import PROJECTIONS
from app.espn_connector import _get_league, get_all_teams
from plv_clone.league_state import LeagueState

OUT_DIR = 'data/research/triangulate_universe'
os.makedirs(OUT_DIR, exist_ok=True)

# Canonical join-key normalizer (order-independent, accent/punct-safe); keys are
# produced and consumed only within this module, so the swap is join-preserving.
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402

def classify_bucket(pos):
    p = str(pos).upper()
    if p in ('SP',): return 'SP'
    if p in ('RP',): return 'RP'
    if p in ('P','SP/RP','RP/SP'): return 'SP'  # default to SP; downstream auto-detect will correct
    return 'H'

def build_owner_map():
    """Map normalized player_name -> owning team_name from the 8-team league.
    Players not in any roster are FAs (caller defaults to 'FA'). Source of truth
    is get_all_teams() (CLAUDE.md gotcha #4/#7 — live roster scan, not pct_owned)."""
    owner = {}
    try:
        teams = get_all_teams()
    except Exception as e:
        print(f"  [warn] get_all_teams() failed ({e}); owner_team falls back to FA")
        return owner
    for _, r in teams.iterrows():
        owner[_norm(r.get('player_name'))] = str(r.get('team_name') or '').strip()
    print(f"  owner_map: {len(owner)} rostered players across the 8-team league")
    return owner


def main():
    league = _get_league()
    roster_df = LeagueState().my_roster_with_injuries()
    my_team_name = roster_df.iloc[0]['on_team_name']
    print(f"My team: {my_team_name}")

    # Ownership as a first-class dimension — which of the 8 teams owns each player
    # (or FA). Built once from the live roster scan and joined onto every category.
    owner_map = build_owner_map()

    # --- 1. My roster ---
    roster_df['bucket'] = roster_df['position'].apply(classify_bucket)
    roster_df[['player_name','player_id','position','bucket','on_team_name','injured']].to_csv(
        f'{OUT_DIR}/my_roster.csv', index=False)
    print(f"my_roster.csv: {len(roster_df)} players")

    # --- 2. All transactions (we filter into my drops vs opp churn) ---
    all_txns = []
    offset = 0
    page_size = 100
    seen_ids = set()
    while True:
        acts = league.recent_activity(size=page_size, offset=offset)
        if not acts: break
        for a in acts:
            for action_tuple in a.actions:
                # action_tuple is (Team, action_str, player_name_str) — player is just a name in this API version
                team, action, pname = action_tuple
                key = (a.date, team.team_name, action, pname)
                if key in seen_ids: continue
                seen_ids.add(key)
                all_txns.append({
                    'date': a.date,
                    'team': team.team_name,
                    'action': action,
                    'player_name': pname,
                    'player_id': None,
                    'position': None,
                })
        if len(acts) < page_size: break
        offset += page_size
        if offset > 2000: break  # safety cap
    txns = pd.DataFrame(all_txns)
    txns['bucket'] = txns['position'].apply(classify_bucket)
    txns.to_csv(f'{OUT_DIR}/all_transactions.csv', index=False)
    print(f"all_transactions.csv: {len(txns)} rows")
    print(f"  date range: {txns['date'].min()} -> {txns['date'].max()}" if len(txns) else "  (empty)")

    if len(txns) == 0:
        print("WARN: no transactions returned — check API access")
        # still produce empty CSVs
        pd.DataFrame(columns=['player_name','espn_id','bucket','source_team','source_action']).to_csv(f'{OUT_DIR}/my_drops.csv', index=False)
        pd.DataFrame(columns=['player_name','espn_id','bucket','source_team','source_action']).to_csv(f'{OUT_DIR}/opp_churn.csv', index=False)
    else:
        # Sort by date DESCENDING so drop_duplicates(keep='first') retains the LATEST action per player
        txns_sorted = txns.sort_values('date', ascending=False)

        # --- 2a. My drops ---
        # Take ALL of my actions, dedupe to latest per player, then filter to those whose latest action is a DROP
        my_actions = txns_sorted[txns_sorted['team']==my_team_name]
        my_latest = my_actions.drop_duplicates(subset=['player_name'], keep='first').copy()
        my_latest['latest_action'] = my_latest['action']
        my_latest['latest_action_date'] = my_latest['date']
        my_drops_uniq = my_latest[my_latest['latest_action'].str.contains('DROP', case=False, na=False)]
        my_drops_uniq.to_csv(f'{OUT_DIR}/my_drops.csv', index=False)
        print(f"my_drops.csv: {len(my_drops_uniq)} unique players I've dropped (and not since re-added)")

        # --- 2b. Opp churn (any DROP or ADD by other teams) ---
        opp = txns_sorted[txns_sorted['team']!=my_team_name]
        opp_uniq = opp.drop_duplicates(subset=['player_name'], keep='first').copy()
        opp_uniq['latest_action'] = opp_uniq['action']
        opp_uniq['latest_action_date'] = opp_uniq['date']
        opp_uniq.to_csv(f'{OUT_DIR}/opp_churn.csv', index=False)
        print(f"opp_churn.csv: {len(opp_uniq)} unique players churned by opponents (latest action per player)")

    # --- 3. FAs above 50 FP (use model files since ESPN API doesn't expose applied totals reliably) ---
    # CRITICAL: league.free_agents() leaks rostered players (Julio Rodriguez 2026-06-04
    # showed as FA owned=0.1% while actually on Frendy's roster). Source of truth for
    # "rostered" is league.teams roster scan; subtract that set from the FA pool.
    rostered_ids = set()
    rostered_names = set()
    for t in league.teams:
        for p in t.roster:
            rostered_ids.add(p.playerId)
            rostered_names.add(_norm(p.name))
    print(f"  rostered set: {len(rostered_ids)} ids across {len(league.teams)} teams")
    fas_raw = league.free_agents(size=2000)
    fas = [p for p in fas_raw if p.playerId not in rostered_ids and _norm(p.name) not in rostered_names]
    leaked = len(fas_raw) - len(fas)
    if leaked:
        print(f"  [warn] filtered {leaked} rostered players that leaked into free_agents() enumeration")
    fa_df = pd.DataFrame([{
        'player_name': p.name, 'player_id': p.playerId, 'position': p.position,
        'bucket': classify_bucket(p.position), 'pct_owned': p.percent_owned,
    } for p in fas])
    print(f"  verified FA pool: {len(fa_df)}")
    # Compute season-to-date FP from model files
    rh3 = PROJECTIONS.rh3()
    rh3['fp_to'] = rh3['prior_fp_per_pa'] * rh3['pa_to']
    rh3['key'] = rh3['player_name'].apply(_norm)
    rp3 = PROJECTIONS.rp3()
    rp3['display_name'] = rp3['player_name'].apply(lambda s: f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if ',' in str(s) else s)
    rp3['fp_to'] = rp3['fp_per_start_to'] * rp3['gs_to']
    rp3['key'] = rp3['display_name'].apply(_norm)
    rprs2 = PROJECTIONS.rprs2()
    rprs2['fp_to'] = rprs2['fp_actual_2026']
    rprs2['key'] = rprs2['name_api'].apply(_norm)
    # Build name->fp lookup
    fp_map = {}
    for df in [rh3[['key','fp_to']], rp3[['key','fp_to']], rprs2[['key','fp_to']]]:
        for _, r in df.iterrows():
            k = r['key']; v = float(r['fp_to']) if pd.notna(r['fp_to']) else 0
            if k not in fp_map or v > fp_map[k]:
                fp_map[k] = v
    fa_df['key'] = fa_df['player_name'].apply(_norm)
    fa_df['fp_2026'] = fa_df['key'].map(fp_map).fillna(0)
    fa_filt = fa_df[fa_df['fp_2026'] >= 50].drop(columns=['key']).sort_values('fp_2026', ascending=False)
    fa_filt.to_csv(f'{OUT_DIR}/fa_above_50fp.csv', index=False)
    print(f"fa_above_50fp.csv: {len(fa_filt)} FAs above 50 FP (model-derived)")

    # --- Build master union list ---
    cols = ['player_name','player_id','position','bucket']
    parts = []
    parts.append(pd.read_csv(f'{OUT_DIR}/my_roster.csv')[cols].assign(category='ROSTER'))
    if os.path.exists(f'{OUT_DIR}/my_drops.csv') and os.path.getsize(f'{OUT_DIR}/my_drops.csv') > 100:
        d = pd.read_csv(f'{OUT_DIR}/my_drops.csv')
        if all(c in d.columns for c in cols):
            parts.append(d[cols].assign(category='MY_DROP'))
    if os.path.exists(f'{OUT_DIR}/opp_churn.csv') and os.path.getsize(f'{OUT_DIR}/opp_churn.csv') > 100:
        d = pd.read_csv(f'{OUT_DIR}/opp_churn.csv')
        if all(c in d.columns for c in cols):
            parts.append(d[cols].assign(category='OPP_CHURN'))
    if os.path.exists(f'{OUT_DIR}/fa_above_50fp.csv') and os.path.getsize(f'{OUT_DIR}/fa_above_50fp.csv') > 100:
        d = pd.read_csv(f'{OUT_DIR}/fa_above_50fp.csv')
        if all(c in d.columns for c in cols):
            parts.append(d[cols].assign(category='FA_TOP'))
    master = pd.concat(parts, ignore_index=True)
    # Build also_in map: for each player, collect ALL categories they appear in
    cat_lookup = master.groupby('player_name')['category'].apply(lambda s: sorted(set(s))).to_dict()
    # Dedupe keeping first category in priority order (ROSTER > MY_DROP > OPP_CHURN > FA_TOP)
    master['cat_pri'] = master['category'].map({'ROSTER':0,'MY_DROP':1,'OPP_CHURN':2,'FA_TOP':3})
    master = master.sort_values('cat_pri').drop_duplicates(subset=['player_name'], keep='first').drop(columns=['cat_pri'])
    # also_in = other categories the player appears in, comma-separated (empty string if only one)
    master['also_in'] = master.apply(
        lambda r: ','.join([c for c in cat_lookup.get(r['player_name'], []) if c != r['category']]),
        axis=1,
    )
    # owner_team = which of the 8 teams owns the player right now, or FA. First-class
    # ownership dimension; flows through run_triangulate into the CSV/JSON snapshot.
    master['owner_team'] = master['player_name'].apply(
        lambda nm: owner_map.get(_norm(nm)) or 'FA'
    )
    master.to_csv(f'{OUT_DIR}/master_universe.csv', index=False)
    print(f"\nmaster_universe.csv: {len(master)} unique players")
    print(master['category'].value_counts().to_string())
    print(master['bucket'].value_counts().to_string())
    print(master['owner_team'].value_counts().to_string())

if __name__ == '__main__':
    main()
