"""run_roster_audit.py — executes the /roster-audit skill protocol
end-to-end and prints the structured report.

This is the concrete script the /roster-audit skill invokes. Edit the
SKILL.md if the protocol changes; edit this file if the implementation
changes.
"""
from __future__ import annotations
import os, sys
from datetime import datetime, date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plv_clone.league_state import LeagueState
from plv_clone.utils.name_match import fuzzy_match_name

_ls = LeagueState()
get_my_roster_with_injuries = _ls.my_roster_with_injuries
def get_free_agents(position=None, size=None):
    return _ls.available_fa(position=position)

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 30)


def match(df_proj, name_col, projection_col, roster_player):
    m = fuzzy_match_name(roster_player, df_proj[name_col].tolist())
    if m:
        row = df_proj[df_proj[name_col] == m].iloc[0]
        return row[projection_col], int(row['rank']) if pd.notna(row.get('rank')) else None
    return None, None


def main():
    roster = get_my_roster_with_injuries()

    proj_files = {
        'rh3': 'data/outputs/xfp_rh3_projections.csv',
        'rp3': 'data/outputs/xfp_rp3_projections.csv',
        'rprs2': 'data/outputs/xfp_rprs2_projections.csv',
    }
    ages = {}
    for k, f in proj_files.items():
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        ages[k] = (datetime.now() - mtime).days

    rh3 = pd.read_csv(proj_files['rh3']).dropna(subset=['player_name'])
    rp3 = pd.read_csv(proj_files['rp3']).dropna(subset=['player_name'])
    rprs2 = pd.read_csv(proj_files['rprs2']).dropna(subset=['name_api'])

    il_used = (roster['lineup_slot'] == 'IL').sum()
    be_used = (roster['lineup_slot'] == 'BE').sum()
    active = (~roster['lineup_slot'].isin(['IL', 'BE'])).sum()
    injured_not_il = roster[(roster['injured']) & (roster['lineup_slot'] != 'IL')]

    il_df = roster[roster['injured']].sort_values('days_until_return')

    healthy_sp_count = ((roster['position'] == 'SP') & (roster['lineup_slot'] != 'IL') & (~roster['injured'])).sum()
    projected_starts = healthy_sp_count * 1.19

    hitters = roster[~roster['position'].isin(['SP', 'RP', 'P'])].copy()
    hitters['proj'] = hitters['player_name'].apply(lambda n: match(rh3, 'player_name', 'xfp_rh3_per_pa', n)[0])
    hitters['rank'] = hitters['player_name'].apply(lambda n: match(rh3, 'player_name', 'xfp_rh3_per_pa', n)[1])
    hit_drops = hitters.sort_values('proj', ascending=True, na_position='first').head(3)

    sps = roster[(roster['position'] == 'SP') & (~roster['injured'])].copy()
    sps['proj'] = sps['player_name'].apply(lambda n: match(rp3, 'player_name', 'xfp_rp3_per_start', n)[0])
    sps['rank'] = sps['player_name'].apply(lambda n: match(rp3, 'player_name', 'xfp_rp3_per_start', n)[1])
    sp_drops = sps.sort_values('proj', ascending=True, na_position='first').head(3)

    rps = roster[(roster['position'] == 'RP') & (~roster['injured'])].copy()
    rps['proj'] = rps['player_name'].apply(lambda n: match(rprs2, 'name_api', 'xfp_ros', n)[0])
    rps['rank'] = rps['player_name'].apply(lambda n: match(rprs2, 'name_api', 'xfp_ros', n)[1])
    rp_drops = rps.sort_values('proj', ascending=True, na_position='first').head(2)

    # Bug fix: was get_free_agents(position='SP', size=200) — silently truncates pool.
    # available_fa() always pulls size=2000 internally; pass position for post-filter.
    fa_sp = get_free_agents(position='SP')
    fa_sp = fa_sp[fa_sp['percent_owned'] < 95].copy()
    fa_sp['proj'] = fa_sp['player_name'].apply(lambda n: match(rp3, 'player_name', 'xfp_rp3_per_start', n)[0])
    fa_sp['rank'] = fa_sp['player_name'].apply(lambda n: match(rp3, 'player_name', 'xfp_rp3_per_start', n)[1])
    fa_sp = fa_sp.dropna(subset=['proj']).sort_values('proj', ascending=False).head(10)

    # Recency outlier alert: FA SPs where L21d form significantly exceeds model projection.
    # Criteria: gs_to >= 10, recency_form_gap > 2.5 — "model may be lagging" candidates
    # the main rp3-ranked table misses because the model weights longer history.
    # NOTE: cross-reference against full FA SP pool (not just top-10 above).
    fa_sp_all = get_free_agents(position='SP')
    fa_sp_all_names = fa_sp_all['player_name'].tolist()
    rp3_all = pd.read_csv(proj_files['rp3']).dropna(subset=['player_name'])
    recency_cols = {'gs_to', 'recency_form_gap', 'fp_per_start_last21'}
    if recency_cols.issubset(set(rp3_all.columns)):
        recency_outliers = rp3_all[
            (rp3_all['gs_to'] >= 10) &
            (rp3_all['recency_form_gap'] > 2.5) &
            rp3_all['fp_per_start_last21'].notna()
        ].copy()
        recency_matches = []
        for _, row in recency_outliers.iterrows():
            m = fuzzy_match_name(row['player_name'], fa_sp_all_names)
            if m:
                recency_matches.append(row)
        recency_alerts = pd.DataFrame(recency_matches) if recency_matches else pd.DataFrame()
    else:
        recency_alerts = pd.DataFrame()

    # Bug fix: was get_free_agents(size=300) — size param ignored by wrapper; made explicit.
    fa_all = get_free_agents()
    fa_hit = fa_all[~fa_all['position'].isin(['SP', 'RP', 'P'])].copy()
    fa_hit = fa_hit[fa_hit['percent_owned'] < 95]
    fa_hit['proj'] = fa_hit['player_name'].apply(lambda n: match(rh3, 'player_name', 'xfp_rh3_per_pa', n)[0])
    fa_hit['rank'] = fa_hit['player_name'].apply(lambda n: match(rh3, 'player_name', 'xfp_rh3_per_pa', n)[1])
    fa_hit = fa_hit.dropna(subset=['proj']).sort_values('proj', ascending=False).head(5)

    fa_rp = get_free_agents(position='RP')
    fa_rp = fa_rp[fa_rp['percent_owned'] < 95].copy()
    fa_rp['proj'] = fa_rp['player_name'].apply(lambda n: match(rprs2, 'name_api', 'xfp_ros', n)[0])
    fa_rp['rank'] = fa_rp['player_name'].apply(lambda n: match(rprs2, 'name_api', 'xfp_ros', n)[1])
    fa_rp = fa_rp.dropna(subset=['proj']).sort_values('proj', ascending=False).head(3)

    # ─── Output ────────────────────────────────────────────────────────
    print(f"# Roster audit — {date.today().isoformat()}\n")
    print(f"_Projections: rh3 {ages['rh3']}d, rp3 {ages['rp3']}d, rprs2 {ages['rprs2']}d — fresh._\n")

    print("## Slot occupancy")
    print(f"**IL slots: {il_used}/3 used | Bench: {be_used}/4 used | Active: {active}/22 used**\n")
    if len(injured_not_il):
        print("Injured but NOT in IL slot (cleanup opportunity):")
        for _, r in injured_not_il.iterrows():
            print(f"  - {r['player_name']} ({r['injury_status']}) → in {r['lineup_slot']} slot")
        print()

    print("## IL return timeline")
    print("| Player | Slot | IL | Injury | Return | Days | Frees IL slot? |")
    print("|---|---|---|---|---|---|---|")
    for _, r in il_df.iterrows():
        frees = "Yes" if r['lineup_slot'] == 'IL' else "No"
        inj = f"{r['injury_type']} {r['injury_detail']} ({r['injury_side']})"
        print(f"| {r['player_name']} | {r['lineup_slot']} | {r['status_code']} | {inj} | {r['return_date']} | {int(r['days_until_return'])} | {frees} |")
    returns_7d = (il_df['days_until_return'] <= 7).sum()
    returns_30d = (il_df['days_until_return'] <= 30).sum()
    il_frees_30d = ((il_df['lineup_slot'] == 'IL') & (il_df['days_until_return'] <= 30)).sum()
    print(f"\n_Summary: {returns_7d} returns ≤7d, {returns_30d} ≤30d, {il_frees_30d} IL slots free up within 30d._\n")

    print("## SP cap math")
    gap = 10 - projected_starts
    print(f"**{healthy_sp_count} healthy SPs → ~{projected_starts:.1f} starts/week vs 10-start cap → {gap:+.1f} gap**")
    if gap > 0.5:
        print(f"→ Streaming needed (~{gap:.0f} starts short).")
    elif gap < -0.5:
        print(f"→ OVER cap by {abs(gap):.1f} — bench/drop required.")
    else:
        print("→ At cap, no streaming needed this week.")
    print("\nForward-looking SP transitions:")
    running = healthy_sp_count
    for _, r in il_df[il_df['position'] == 'SP'].sort_values('days_until_return').iterrows():
        running += 1
        proj = running * 1.19
        g = 10 - proj
        note = "⚠ FORCED DROP" if g < -0.5 else ("streaming still OK" if g > 0.5 else "at cap")
        print(f"  - {r['return_date']} (+{int(r['days_until_return'])}d): {r['player_name']} → {running} SPs → {proj:.1f}/wk ({note})")
    print()

    print("## Drop candidates (bottom-3 per bucket)\n")
    print("### Hitters")
    for _, r in hit_drops.iterrows():
        p = f"{r['proj']:.3f}" if pd.notna(r['proj']) else "no-match"
        rk = f"#{int(r['rank'])}" if pd.notna(r['rank']) else "?"
        note = ""
        if r['injured']:
            note = f" — INJURED, {r['injury_status']}, ret {r['return_date']}"
        print(f"  - {r['player_name']} ({r['position']}, {r['pro_team']}) — xfp_rh3 {p}, rank {rk}{note}")
    print("\n### SPs (healthy)")
    for _, r in sp_drops.iterrows():
        p = f"{r['proj']:.2f}" if pd.notna(r['proj']) else "no-match"
        rk = f"#{int(r['rank'])}" if pd.notna(r['rank']) else "?"
        print(f"  - {r['player_name']} ({r['pro_team']}) — xfp_rp3 {p} fp/start, rank {rk}")
    print("\n### RPs (healthy)")
    for _, r in rp_drops.iterrows():
        p = f"{r['proj']:.1f}" if pd.notna(r['proj']) else "no-match"
        rk = f"#{int(r['rank'])}" if pd.notna(r['rank']) else "?"
        print(f"  - {r['player_name']} — xfp_ros {p}, rank {rk}")
    print()

    print("## FA add candidates (FA only, <95% owned)\n")
    print("### Top SP FAs")
    for _, r in fa_sp.iterrows():
        print(f"  - {r['player_name']} ({r['pro_team']}) — xfp_rp3 {r['proj']:.2f}, rank #{int(r['rank'])}, owned {r['percent_owned']:.1f}%")
    if not recency_alerts.empty:
        print("\n#### Recency outlier alerts (gs_to ≥ 10, L21d gap > 2.5 fp/start above model)")
        for _, r in recency_alerts.iterrows():
            rk = f"#{int(r['rank'])}" if 'rank' in r and pd.notna(r.get('rank')) else "?"
            xfp = r.get('xfp_rp3_per_start', float('nan'))
            l21d = r['fp_per_start_last21']
            gap = r['recency_form_gap']
            print(f"  ⚠ RECENCY OUTLIER: {r['player_name']} — rank {rk}, xfp {xfp:.1f}/start, L21d {l21d:.1f}/start, gap +{gap:.1f}")
    print("\n### Top hitter FAs")
    for _, r in fa_hit.iterrows():
        print(f"  - {r['player_name']} ({r['position']}, {r['pro_team']}) — xfp_rh3 {r['proj']:.3f}, rank #{int(r['rank'])}, owned {r['percent_owned']:.1f}%")
    print("\n### Top RP FAs")
    for _, r in fa_rp.iterrows():
        print(f"  - {r['player_name']} ({r['pro_team']}) — xfp_ros {r['proj']:.1f}, rank #{int(r['rank'])}, owned {r['percent_owned']:.1f}%")


if __name__ == '__main__':
    main()
