import pandas as pd, unicodedata
# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402

p = pd.read_parquet('data/research/sp_archetype_career_panel.parquet')
p['key'] = p['name'].apply(_norm)

targets = [
    ('Bryan Woo','AUTO','9'),('Drew Rasmussen','AUTO','19'),('Parker Messick','AUTO','26'),
    ('Trey Yesavage','PROB','48'),('Sonny Gray','PROB','37'),('Michael King','PROB','36'),
    ('Ryne Nelson','PROB','49'),('Christian Scott','PROB','64'),('Reid Detmers','PROB','61'),
    ('Ryan Weathers','PROB','34'),('Foster Griffin','PROB','68'),
    ('Framber Valdez','Q','42'),('Seth Lugo','Q','86'),('Bailey Ober','DNS','UR'),
]

def show(name, tier, pl_rank):
    key = _norm(name)
    rows = p[p['key']==key].sort_values('year')
    if rows.empty:
        print(f"\n=== {name} ({tier}) PL#{pl_rank} — NO ARCHETYPE PROFILE ===")
        return
    cur = rows[rows['year']==2026]
    if cur.empty:
        cur = rows.iloc[[-1]]
    r = cur.iloc[0]
    print(f"\n=== {name} ({tier}) | PL#{pl_rank} | age={int(r['age'])} {r['age_tier']} | gs={int(r['gs'])} ===")
    print(f"  ARCHETYPE:  {r['archetype']}  [{r['stuff_subtype']}]   cell={r['cell']}")
    if pd.notna(r['pitch_archetype']):
        print(f"  PITCH MIX:  {r['pitch_archetype']}  (entropy={r['arsenal_entropy']:.2f})")
        mix = []
        for pt in ['FB','SL','CB','CH','FS']:
            v = r[f'{pt}_pct']
            if pd.notna(v) and v > 0.05:
                mix.append(f"{pt} {v*100:.0f}%")
        if mix:
            print(f"              {' / '.join(mix)}")
    print(f"  RATINGS (20-80):  STUFF {int(r['STUFF'])}  MOVEMENT {int(r['MOVEMENT'])}  CONTROL {int(r['CONTROL'])}  ->  OVERALL {int(r['OVERALL'])}")
    print(f"  Sub-ratings:      SwMiss {int(r['SWING_MISS'])} | CalledStr {int(r['CALLED_STRIKE'])} | DamageSup {int(r['DAMAGE_SUPP'])} | GBten {int(r['GB_TENDENCY'])} | WalkAvoid {int(r['WALK_AVOID'])} | StrikeThrow {int(r['STRIKE_THROWING'])}")
    print(f"  Velo:             {r['avg_velo']:.1f} mph [{r['velo_tier']}, rating {int(r['velo_rating'])}]")
    print(f"  Boundary:         {r['boundary_tier']} (distance {int(r['boundary_distance'])})  career_yr {int(r['career_year'])}")
    traj = r.get('traj_flag', None)
    slope = r.get('OVERALL_slope_3yr', None)
    cpct = r.get('OVERALL_career_pct', None)
    print(f"  Trajectory:       {traj}  3yr-slope={slope if pd.isna(slope) else f'{slope:+.1f}'}  career-pct={cpct if pd.isna(cpct) else f'{cpct*100:.0f}%'}")
    print(f"  T+1 fp/start:     {r['t1_fp_projection']:.2f}")
    print(f"  T+2 fp/start:     {r['t2_fp_projection']:.2f}")
    # Multi-year archetype shift
    if len(rows) >= 2:
        recent = rows.tail(4)[['year','archetype','OVERALL']]
        shift = ' -> '.join([f"{int(y)}:{a}({int(o)})" for y,a,o in zip(recent['year'],recent['archetype'],recent['OVERALL'])])
        print(f"  Career arc:       {shift}")

for name, tier, pl in targets:
    show(name, tier, pl)
