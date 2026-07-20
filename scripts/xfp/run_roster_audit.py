"""run_roster_audit.py — executes the /roster-audit skill protocol
end-to-end and prints the structured report.

This is the concrete script the /roster-audit skill invokes. Edit the
SKILL.md if the protocol changes; edit this file if the implementation
changes.
"""
from __future__ import annotations
import os, sys
# Windows cp1252 console guard — this report prints —/→/⚠ etc. (item 23)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from datetime import datetime, date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plv_clone.league_state import LeagueState
from plv_clone.utils.name_match import build_safe_name_index, safe_lookup
from scripts.xfp.lib.pitcher_role import build_role_lookup, detect_pitcher_role
from scripts.xfp.lib.bucket_dispatch import _flip_lastfirst  # shared 'Last, First' flip (audit item 9)

_BS_PITCHERS = ROOT / 'data' / 'research' / 'xfp_cache' / 'boxscore_pitchers.parquet'
_BS_LOOKBACK_DAYS = 14


def _load_bs_last_start() -> dict[int, dict]:
    """Return {mlbam_id: most-recent-start-row} from boxscore bridge (last 14d)."""
    if not _BS_PITCHERS.exists():
        return {}
    try:
        df = pd.read_parquet(_BS_PITCHERS)
        cutoff = (date.today() - pd.Timedelta(days=_BS_LOOKBACK_DAYS)).isoformat()
        df = df[df['game_date'] >= cutoff].copy()
        if df.empty:
            return {}
        idx = df.sort_values('game_date').groupby('mlbam_id')['game_date'].idxmax()
        return {int(row['mlbam_id']): row.to_dict()
                for _, row in df.loc[idx].iterrows()}
    except Exception:
        return {}

_ls = LeagueState()
get_my_roster_with_injuries = _ls.my_roster_with_injuries
def get_free_agents(position=None, size=None):
    return _ls.available_fa(position=position)

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 30)


def match(df_proj, name_index, projection_col, player_name, team=None):
    """Collision-safe projection lookup (CLAUDE.md rule 10).

    Exact normalized full-name join via `safe_lookup` (accents/suffixes/
    'Last, First' handled), with `team` breaking true same-name collisions
    (Max Muncy LAD vs ATH). NEVER fuzzy: the old difflib-0.78 path let FA
    prospect "Hayden Alvarez" inherit Yordan Alvarez's rh3 row and invented
    "Bryce Mayer" from Bryce Miller (2026-07-19). No/ambiguous match →
    (None, None); the row is skipped, not guessed.
    """
    lbl = safe_lookup(player_name, name_index, team=team)
    if lbl is None:
        return None, None
    row = df_proj.loc[lbl]
    return row[projection_col], int(row['rank']) if pd.notna(row.get('rank')) else None


def join_proj(df, df_proj, name_index, projection_col):
    """Add `proj`/`rank` to `df` by collision-safe name join (one lookup per
    row, team-hinted from `pro_team`)."""
    pairs = [match(df_proj, name_index, projection_col,
                   r['player_name'], team=r.get('pro_team'))
             for _, r in df.iterrows()]
    df['proj'] = [p[0] for p in pairs] if pairs else pd.Series(dtype=float)
    df['rank'] = [p[1] for p in pairs] if pairs else pd.Series(dtype=float)
    return df


def main():
    import argparse
    _ap = argparse.ArgumentParser(description='Roster audit')
    _ap.add_argument('--fresh', action='store_true',
                     help='Catch local data up to yesterday via the two fast bridges '
                          '(boxscore + statcast gf) before auditing. Skips if current.')
    _args, _ = _ap.parse_known_args()
    if _args.fresh:
        from scripts.xfp.lib.freshness import ensure_fresh
        ensure_fresh()

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

    # Collision-safe name indexes, built ONCE per projection frame (rule 10).
    # rh3 carries a team column, so its true same-name collisions (both Max
    # Muncys appear as the identical string) resolve via the pro_team hint;
    # rp3/rprs2 have no team column → ambiguous names skip rather than guess.
    rh3_idx = build_safe_name_index(
        rh3['player_name'], rh3['team'] if 'team' in rh3.columns else None)
    rp3_idx = build_safe_name_index(rp3['player_name'])
    rprs2_idx = build_safe_name_index(rprs2['name_api'])

    # Boxscore bridge: recent actual start stats (fills statcast lag).
    # Build name→mlbam from rp3, then look up each rostered SP's last start.
    bs_last = _load_bs_last_start()
    _rp3_mlbam: dict[str, int] = {}
    for _, row in rp3.iterrows():
        pid = row.get('pitcher')
        nm = str(row.get('player_name', ''))
        if pid and nm:
            _rp3_mlbam[nm.lower().strip()] = int(pid)
            if ',' in nm:
                _rp3_mlbam[_flip_lastfirst(nm).lower().strip()] = int(pid)

    def _bs_last_str(player_name: str) -> str:
        mlbam = _rp3_mlbam.get(player_name.lower().strip())
        if not mlbam:
            return ''
        row = bs_last.get(mlbam)
        if not row:
            return ''
        d = str(row['game_date'])[5:]  # MM-DD
        ip = float(row['ip'])
        ip_disp = f"{int(ip)}.{int(round((ip % 1) * 3))}" if ip % 1 else f"{int(ip)}.0"
        so = int(row['so'])
        fp = float(row['fp_sp'])
        flag = ' ⚡' if fp >= 20 else (' 🔥' if fp >= 15 else '')
        return f' | last {d}: {ip_disp}IP {so}K → {fp:.1f}FP{flag}'

    il_used = (roster['lineup_slot'] == 'IL').sum()
    be_used = (roster['lineup_slot'] == 'BE').sum()
    # BE counts as active: owner manages lineup daily, bench players get activated.
    # Only true IL slots are excluded from scoring.
    active = (~roster['lineup_slot'].isin(['IL'])).sum()
    injured_not_il = roster[(roster['injured']) & (roster['lineup_slot'] != 'IL')]

    il_df = roster[roster['injured']].sort_values('days_until_return')

    # Detect effective pitcher role from eligible_slots + MLB Stats API for dual-eligible.
    # Canonical bug: Detmers position='RP' in ESPN but eligible for SP and GS=6 → should
    # use rp3 (SP model), not rprs2. Never bucket pitchers by .position alone.
    pitcher_rows = roster[roster['position'].isin(['SP', 'RP', 'P'])].copy()
    role_lookup = build_role_lookup(pitcher_rows, rp3_df=rp3, rprs2_df=rprs2)
    roster = roster.copy()
    roster['effective_role'] = roster.apply(
        lambda r: role_lookup.get(r['player_name'], r['position'])
        if r['position'] in ('SP', 'RP', 'P') else r['position'],
        axis=1,
    )

    healthy_sp_count = (
        (roster['effective_role'] == 'SP') &
        (roster['lineup_slot'] != 'IL') &
        (~roster['injured'])
    ).sum()
    from plv_clone.cap_math import projected_starts as _cap_proj
    projected_starts = _cap_proj(healthy_sp_count)

    # Period-aware SP cap (2026-07-11): the current matchup period's cap comes
    # from the ONE shared resolver (cap = 10×weeks, ASG period 15 override = 16),
    # never a hardcoded 10 — so this matches /matchup-leverage and matchup.html.
    # Banked count is ESPN's authoritative statId-33 counter (the x/16 on-screen).
    from scripts.xfp.lib.period_meta import resolve_current_period_meta, espn_period_meta
    _league = _ls._get_league()
    _pmeta = resolve_current_period_meta(_league)   # reads live currentMatchupPeriod
    _period = _pmeta['period']
    sp_cap = _pmeta['sp_cap']
    _weeks = _pmeta['weeks']
    try:
        _my_team = _ls._find_my_team()
        _banked = espn_period_meta(_league, _period,
                                   getattr(_my_team, 'team_id', None), None)
    except Exception:
        _banked = {}
    banked_mine = _banked.get('my_banked')

    hitters = roster[~roster['position'].isin(['SP', 'RP', 'P'])].copy()
    hitters = join_proj(hitters, rh3, rh3_idx, 'xfp_rh3_per_pa')
    hit_drops = hitters.sort_values('proj', ascending=True, na_position='first').head(3)

    sps = roster[(roster['effective_role'] == 'SP') & (~roster['injured'])].copy()
    sps = join_proj(sps, rp3, rp3_idx, 'xfp_rp3_per_start')
    sp_drops = sps.sort_values('proj', ascending=True, na_position='first').head(3)

    rps = roster[(roster['effective_role'] == 'RP') & (~roster['injured'])].copy()
    rps = join_proj(rps, rprs2, rprs2_idx, 'xfp_ros')
    rp_drops = rps.sort_values('proj', ascending=True, na_position='first').head(2)

    # Bug fix: was get_free_agents(position='SP', size=200) — silently truncates pool.
    # available_fa() always pulls size=2000 internally.
    # 2026-07-04 audit: ONE fetch + local position filters (was 4 available_fa()
    # calls per run, two byte-identical — each a fresh ESPN roundtrip).
    fa_all = get_free_agents()
    fa_sp_all = fa_all[fa_all['position'] == 'SP'].copy()
    fa_sp = fa_sp_all[fa_sp_all['percent_owned'] < 95].copy()
    fa_sp = join_proj(fa_sp, rp3, rp3_idx, 'xfp_rp3_per_start')
    fa_sp = fa_sp.dropna(subset=['proj']).sort_values('proj', ascending=False).head(10)

    # Recency outlier alert: FA SPs where L21d form significantly exceeds model projection.
    # Criteria: gs_to >= 10, recency_form_gap > 2.5 — "model may be lagging" candidates
    # the main rp3-ranked table misses because the model weights longer history.
    # NOTE: cross-reference against full FA SP pool (not just top-10 above).
    # Collision-safe: exact normalized name join against the FA pool. The old
    # fuzzy pass could tag rostered "Rogers, Trevor" as FA via Tyler Rogers.
    fa_sp_pool_idx = build_safe_name_index(
        fa_sp_all['player_name'],
        fa_sp_all['pro_team'] if 'pro_team' in fa_sp_all.columns else None)
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
            if safe_lookup(row['player_name'], fa_sp_pool_idx) is not None:
                recency_matches.append(row)
        recency_alerts = pd.DataFrame(recency_matches) if recency_matches else pd.DataFrame()
    else:
        recency_alerts = pd.DataFrame()

    # Bug fix: was get_free_agents(size=300) — size param ignored by wrapper; made explicit.
    fa_hit = fa_all[~fa_all['position'].isin(['SP', 'RP', 'P'])].copy()
    fa_hit = fa_hit[fa_hit['percent_owned'] < 95].copy()
    fa_hit = join_proj(fa_hit, rh3, rh3_idx, 'xfp_rh3_per_pa')
    fa_hit = fa_hit.dropna(subset=['proj']).sort_values('proj', ascending=False).head(5)

    fa_rp = fa_all[fa_all['position'] == 'RP'].copy()
    fa_rp = fa_rp[fa_rp['percent_owned'] < 95].copy()
    fa_rp = join_proj(fa_rp, rprs2, rprs2_idx, 'xfp_ros')
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
    _cov = ('OVERRIDE' if _pmeta['covered']
            else (f"10×{_weeks}wk" if _weeks > 1 else 'default'))
    print(f"_Period {_period} · {_pmeta['week_start']} → {_pmeta['week_end']} · "
          f"{_weeks}-week · SP cap **{sp_cap}** ({_cov})._\n")
    if banked_mine is not None:
        _rem = max(sp_cap - banked_mine, 0)
        print(f"**Banked (ESPN, authoritative): {banked_mine}/{sp_cap} SP starts this "
              f"period → {_rem} remaining.**")
    # Projected starts scale by the period's week count so a multi-week period
    # (ASG/playoff) compares like-for-like against its period cap. weeks=1 keeps
    # a normal week byte-identical to the old `10 - projected_starts`.
    period_proj = projected_starts * _weeks
    gap = sp_cap - period_proj
    print(f"**{healthy_sp_count} healthy SPs → ~{projected_starts:.1f} starts/week "
          f"(~{period_proj:.1f} over {_weeks}wk) vs {sp_cap}-start cap → {gap:+.1f} gap**")
    if gap > 0.5:
        print(f"→ Streaming needed (~{gap:.0f} starts short of the {sp_cap} cap).")
    elif gap < -0.5:
        print(f"→ OVER cap by {abs(gap):.1f} — bench/drop required.")
    else:
        print("→ At cap, no streaming needed this period.")
    print("\nForward-looking SP transitions:")
    running = healthy_sp_count
    for _, r in il_df[il_df['position'] == 'SP'].sort_values('days_until_return').iterrows():
        running += 1
        from plv_clone.cap_math import projected_starts as _cap_proj2
        proj = _cap_proj2(running)
        g = sp_cap - proj * _weeks
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
        bs = _bs_last_str(r['player_name'])
        print(f"  - {r['player_name']} ({r['pro_team']}) — xfp_rp3 {p} fp/start, rank {rk}{bs}")
    print("\n### RPs (healthy)")
    for _, r in rp_drops.iterrows():
        p = f"{r['proj']:.1f}" if pd.notna(r['proj']) else "no-match"
        rk = f"#{int(r['rank'])}" if pd.notna(r['rank']) else "?"
        print(f"  - {r['player_name']} — xfp_ros {p}, rank {rk}")
    print()

    # --- RP FADE-WATCH (rp-decline convergence; Tier-B context flag) ----------
    # Surface any of the user's OWN relievers whose velo is fading YoY AND whose
    # skill/role-share is slipping (ROLE-RISK) or one leg firing (WATCH) — a
    # slipping closer is exactly the sell-high target. This NEVER moves the rprs2
    # headline (CLAUDE.md #13) and is honestly weaker/noisier than /sp-decline
    # (velo +0.112 vs SP whiff/K +0.235; role loss ~1/3 manager-driven). Degrades
    # to a no-op if the rolling cache / model is unavailable.
    try:
        sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
        from rp_decline_model import tier_map as _rpd_tier_map  # type: ignore
        import unicodedata as _ud
        def _rpd_norm(s):
            return _ud.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower().strip()
        _rpd = _rpd_tier_map()
    except Exception:
        _rpd = {}
    if _rpd:
        watch = []
        for _, r in rps.iterrows():
            d = _rpd.get(_rpd_norm(r['player_name']))
            if d and d['tier'] in ('ROLE-RISK', 'WATCH'):
                watch.append((r['player_name'], d))
        if watch:
            print("### RP FADE-WATCH (rp-decline — Tier-B context, never moves rprs2)")
            # ROLE-RISK first, then WATCH; within each, worst velo first
            order = {'ROLE-RISK': 0, 'WATCH': 1}
            watch.sort(key=lambda t: (order.get(t[1]['tier'], 9),
                                      t[1].get('velo_yoy') if t[1].get('velo_yoy') is not None else 0))
            for name, d in watch:
                vy = f"{d['velo_yoy']:+.1f}" if d.get('velo_yoy') is not None else '--'
                tag = ('velo down AND skill/role slipping — sell-high candidate while '
                       'saves/holds still land' if d['tier'] == 'ROLE-RISK'
                       else 'one leg firing — monitor, not yet a role-loss setup')
                print(f"  - {name} ({d.get('role','') or 'RP'}) — {d['tier']}: velo YoY {vy}, "
                      f"{d['legs']}/3 legs. {tag}.")
            print("  _Conviction/watch gate only (role loss ~1/3 manager-driven, AUC 0.683). "
                  "Verify via /triangulate + /rp-decline before a sell/drop._")
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
