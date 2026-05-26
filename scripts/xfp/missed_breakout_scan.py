import sys
sys.path.insert(0, r'c:\Users\Joshua\plv_clone')
import pandas as pd
from difflib import SequenceMatcher

rh3 = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\outputs\xfp_rh3_projections.csv')
rp3 = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\outputs\xfp_rp3_projections.csv')
rprs2 = pd.read_csv(r'c:\Users\Joshua\plv_clone\data\outputs\xfp_rprs2_projections.csv')

def normalize_model_name(n):
    if ',' in str(n):
        parts = [p.strip() for p in n.split(',')]
        return f'{parts[1]} {parts[0]}'.lower()
    return str(n).lower()

rp3['name_norm'] = rp3['player_name'].apply(normalize_model_name)
rprs2['name_norm'] = rprs2['name_api'].apply(normalize_model_name)
rh3['name_norm'] = rh3['player_name'].apply(lambda x: str(x).lower())

# All non-Ligers adds from activity data
adds = [
    ('2026-05-25','Late Night Bettsing','Max Meyer'),
    ('2026-05-24','U Just Lost To Edwin Diaz','JJ Bleday'),
    ('2026-05-23','U Just Lost To Edwin Diaz','Jake Bauers'),
    ('2026-05-21','Treasure Island Mashers','Kyle Harrison'),
    ('2026-05-21','Treasure Island Mashers','Xander Bogaerts'),
    ('2026-05-21','Frendy Fantastic Team','Michael Wacha'),
    ('2026-05-19','Frendy Fantastic Team','Ivan Herrera'),
    ('2026-05-19','Team Solomon','Logan Webb'),
    ('2026-05-19','U Just Lost To Edwin Diaz','Dylan Lee'),
    ('2026-05-17','Boone Bad Bullpen','Jeffrey Springs'),
    ('2026-05-16','U Just Lost To Edwin Diaz','Brandon Marsh'),
    ('2026-05-16','U Just Lost To Edwin Diaz','Jameson Taillon'),
    ('2026-05-12','Frendy Fantastic Team','Kris Bubic'),
    ('2026-05-11','Late Night Bettsing','Brayan Rocchio'),
    ('2026-05-10','Team Solomon','Jose Altuve'),
    ('2026-05-07','Boone Bad Bullpen','Nick Martinez'),
    ('2026-05-06','Team Solomon','Shane McClanahan'),
    ('2026-05-06','Late Night Bettsing','Xander Bogaerts'),
    ('2026-05-06','Late Night Bettsing','Jonathan Aranda'),
    ('2026-05-05','Team Solomon','Austin Riley'),
    ('2026-05-04','Late Night Bettsing','Clay Holmes'),
    ('2026-05-04','U Just Lost To Edwin Diaz','Mickey Moniak'),
    ('2026-04-29','U Just Lost To Edwin Diaz','Trey Yesavage'),
    ('2026-04-29','Boone Bad Bullpen','Jason Adam'),
    ('2026-04-29','Boone Bad Bullpen','Garrett Whitlock'),
    ('2026-04-29','Treasure Island Mashers','Jacob Wilson'),
    ('2026-04-28','Team Solomon','Louis Varland'),
    ('2026-04-28','Late Night Bettsing','Paul Sewald'),
    ('2026-04-28','Frendy Fantastic Team','Miguel Vargas'),
    ('2026-04-27','Late Night Bettsing','Carlos Correa'),
    ('2026-04-26','Team Solomon','Jeremy Pena'),
    ('2026-04-26','Team Solomon','Nick Pivetta'),
    ('2026-04-26','Boone Bad Bullpen','Keider Montero'),
    ('2026-04-26','Boone Bad Bullpen','Landen Roupp'),
    ('2026-04-24','2015 Draft First Round','Jakob Junis'),
    ('2026-04-23','Boone Bad Bullpen','Alex Vesia'),
    ('2026-04-21','Frendy Fantastic Team','Josh Naylor'),
    ('2026-04-21','Frendy Fantastic Team','Bubba Chandler'),
    ('2026-04-20','Frendy Fantastic Team','Max Muncy'),
    ('2026-04-19','U Just Lost To Edwin Diaz','Gregory Soto'),
    ('2026-04-19','U Just Lost To Edwin Diaz','Christian Walker'),
    ('2026-04-19','Frendy Fantastic Team','Colt Keith'),
    ('2026-04-19','Frendy Fantastic Team','Jorge Soler'),
    ('2026-04-19','Treasure Island Mashers','Nolan Arenado'),
    ('2026-04-17','Frendy Fantastic Team','Jo Adell'),
    ('2026-04-16','Team Solomon','Jazz Chisholm Jr.'),
    ('2026-04-16','Frendy Fantastic Team','Cam Smith'),
    ('2026-04-15','U Just Lost To Edwin Diaz','Ramon Laureano'),
    ('2026-04-15','Treasure Island Mashers','Agustin Ramirez'),
    ('2026-04-12','U Just Lost To Edwin Diaz','Taj Bradley'),
    ('2026-04-08','Team Solomon','Jordan Walker'),
    ('2026-04-05','U Just Lost To Edwin Diaz','Kyle Harrison'),
    ('2026-04-05','2015 Draft First Round','Lance McCullers Jr.'),
    ('2026-04-04','Team Solomon','Sonny Gray'),
    ('2026-04-04','U Just Lost To Edwin Diaz','Eric Lauer'),
    ('2026-04-03','U Just Lost To Edwin Diaz','Shane Bieber'),
    ('2026-04-03','U Just Lost To Edwin Diaz','Bryce Miller'),
    ('2026-04-02','U Just Lost To Edwin Diaz','Corbin Burnes'),
    ('2026-04-02','U Just Lost To Edwin Diaz','Joey Wiemer'),
    ('2026-04-02','Boone Bad Bullpen','Paul Sewald'),
    ('2026-03-31','Frendy Fantastic Team','Andrew Painter'),
    ('2026-03-30','2015 Draft First Round','Jordan Romano'),
    ('2026-03-26','Late Night Bettsing','Willson Contreras'),
    ('2026-03-26','Late Night Bettsing','Justin Steele'),
    ('2026-03-26','Late Night Bettsing','Joe Musgrove'),
    ('2026-03-26','Frendy Fantastic Team','Shane McClanahan'),
    ('2026-03-26','Team Solomon','Robert Suarez'),
    ('2026-03-26','Team Solomon','JJ Wetherholt'),
    ('2026-03-26','Boone Bad Bullpen','Kodai Senga'),
    ('2026-03-26','Treasure Island Mashers','Carson Benge'),
    ('2026-03-26','Late Night Bettsing','Jackson Holliday'),
]

def fuzzy_match(name, candidates, threshold=0.75):
    name_l = name.lower()
    best_score = 0
    best_match = None
    for c in candidates:
        score = SequenceMatcher(None, name_l, c).ratio()
        if score > best_score:
            best_score = score
            best_match = c
    if best_score >= threshold:
        return best_match, best_score
    return None, best_score

results = []
for add_date, team, player in adds:
    player_l = player.lower()

    match_rh3, s = fuzzy_match(player_l, rh3['name_norm'].tolist())
    if match_rh3:
        r = rh3[rh3['name_norm'] == match_rh3].iloc[0]
        if r['rank'] <= 120:
            results.append({
                'player': player, 'team': team, 'add_date': add_date,
                'model': 'rh3', 'rank': int(r['rank']),
                'metric': round(r['xfp_rh3_per_pa'], 4), 'metric_label': 'xfp/pa',
                'recency_form_gap': round(r['recency_form_gap'], 4), 'signal': r['signal']
            })

    match_rp3, s = fuzzy_match(player_l, rp3['name_norm'].tolist())
    if match_rp3:
        r = rp3[rp3['name_norm'] == match_rp3].iloc[0]
        if r['rank'] <= 120:
            results.append({
                'player': player, 'team': team, 'add_date': add_date,
                'model': 'rp3', 'rank': int(r['rank']),
                'metric': round(r['xfp_rp3_per_start'], 4), 'metric_label': 'xfp/start',
                'recency_form_gap': round(r['recency_form_gap'], 4), 'signal': r['signal']
            })

    match_rprs2, s = fuzzy_match(player_l, rprs2['name_norm'].tolist())
    if match_rprs2:
        r = rprs2[rprs2['name_norm'] == match_rprs2].iloc[0]
        if r['rank'] <= 80:
            results.append({
                'player': player, 'team': team, 'add_date': add_date,
                'model': 'rprs2', 'rank': int(r['rank']),
                'metric': round(r['xfp_ros'], 1), 'metric_label': 'xfp_ros',
                'recency_form_gap': None, 'signal': r['signal']
            })

res_df = pd.DataFrame(results).sort_values('rank')
print('=== ALL FLAGGED MISSED ADDS ===')
pd.set_option('display.max_rows', 200)
pd.set_option('display.width', 200)
pd.set_option('display.max_colwidth', 30)
print(res_df.to_string(index=False))

print('\n\n=== TOP-50 RANK ONLY ===')
top = res_df[res_df['rank'] <= 50].copy()
print(top.to_string(index=False))
