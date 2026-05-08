"""compare_pl_top100_sp.py — PitcherList Top 100 SP (5/4/2026) vs my model.

Same approach as compare_pl_top50.py but for the SP universe.
"""
from __future__ import annotations
import json, re, unicodedata
from pathlib import Path
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path('c:/Users/Joshua/plv_clone')
PROJ = pd.read_csv(ROOT / 'data/outputs/xfp_rp3_projections.csv')
PROJ['ros_rank']   = PROJ['xfp_rp3_per_start'].rank(ascending=False, method='min')
PROJ['total_rank'] = PROJ['xfp_rp3_per_start'].rank(ascending=False, method='min')

def _strip(s): return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def norm(s):   return re.sub(r'[^a-z]+', '', _strip((s or '').lower()))

def name_key(name):
    """'Skenes, Paul' or 'Paul Skenes' → (last_norm, first_norm)."""
    if ',' in name:
        last, first = name.split(',', 1)
    else:
        parts = name.strip().split()
        if len(parts) < 2: return (norm(name), '')
        last, first = parts[-1], ' '.join(parts[:-1])
    return (norm(last), norm(first))

LOOKUP = {name_key(r['player_name']): r for _, r in PROJ.iterrows() if pd.notna(r.get('player_name'))}

# Skubal is IL on PL — I'll mark him separately
PL = [
  (1,'Paul Skenes'),(2,'Cam Schlittler'),(3,'Chris Sale'),(4,'Jacob deGrom'),
  (5,'Shohei Ohtani'),(6,'Yoshinobu Yamamoto'),(7,'Bryan Woo'),(8,'Max Fried'),
  (9,'Cristopher Sanchez'),(10,'Tyler Glasnow'),(11,'Cole Ragans'),(12,'Nolan McLean'),
  (13,'Shota Imanaga'),(14,'Chase Burns'),(15,'Logan Gilbert'),(16,'Jacob Misiorowski'),
  (17,'George Kirby'),(18,'Dylan Cease'),(19,'Kevin Gausman'),(20,'Drew Rasmussen'),
  (21,'Zack Wheeler'),(22,'Freddy Peralta'),(23,'Framber Valdez'),(24,'Jesus Luzardo'),
  (25,'Nathan Eovaldi'),(26,'Robbie Ray'),(27,'Logan Webb'),(28,'Emerson Hancock'),
  (29,'Parker Messick'),(30,'Jose Soriano'),(31,'Braxton Ashcraft'),(32,'Will Warren'),
  (33,'Kyle Harrison'),(34,'Shane McClanahan'),(35,'Edward Cabrera'),(36,'Gavin Williams'),
  (37,'Kris Bubic'),(38,'Michael King'),(39,'Eury Perez'),(40,'Sandy Alcantara'),
  (41,'MacKenzie Gore'),(42,'Nick Lodolo'),(43,'Logan Henderson'),(44,'Ryan Weathers'),
  (45,'Landen Roupp'),(46,'Randy Vasquez'),(47,'Michael Soroka'),(48,'Connelly Early'),
  (49,'Connor Prielipp'),(50,'Emmet Sheehan'),(51,'Reid Detmers'),(52,'Max Meyer'),
  (53,'Noah Schultz'),(54,'Payton Tolle'),(55,'Ryne Nelson'),(56,'Matthew Boyd'),
  (57,'Clay Holmes'),(58,'Foster Griffin'),(59,'Kyle Bradish'),(60,'Chase Dollander'),
  (61,'Bubba Chandler'),(62,'Griffin Canning'),(63,'Jake Bennett'),(64,'Spencer Strider'),
  (65,'Trey Yesavage'),(66,'Taj Bradley'),(67,'Tyler Mahle'),(68,'Michael Wacha'),
  (69,'Ranger Suarez'),(70,'Seth Lugo'),(71,'JR Ritchie'),(72,'Christian Scott'),
  (73,'Spencer Arrighetti'),(74,'Davis Martin'),(75,'Joey Cantillo'),(76,'Sean Burke'),
  (77,'Brandon Sproat'),(78,'Justin Wrobleski'),(79,'Noah Cameron'),(80,'Steven Matz'),
  (81,'Luis Severino'),(82,'Aaron Nola'),(83,'Shane Baz'),(84,'Peter Lambert'),
  (85,'Tanner Bibee'),(86,'Jack Leiter'),(87,'Bryce Elder'),(88,'Nick Martinez'),
  (89,'Jameson Taillon'),(90,'Colin Rea'),(91,'Merrill Kelly'),(92,'Zac Gallen'),
  (93,'Mitch Keller'),(94,'Cade Cavalli'),(95,'Carmen Mlodzinski'),(96,'Chad Patrick'),
  (97,'Eduardo Rodriguez'),(98,'Janson Junk'),(99,'Walbert Urena'),(100,'Luis Castillo'),
]

def find(name):
    last, first = name_key(name)
    rec = LOOKUP.get((last, first))
    if rec is not None: return rec
    cand = [(k,v) for k,v in LOOKUP.items() if k[0] == last]
    if len(cand) == 1 and first[:3] == cand[0][0][1][:3]:
        return cand[0][1]
    return None

rows = []
for pl_rank, name in PL:
    rec = find(name)
    if rec is None:
        rows.append({'pl_rank':pl_rank, 'name':name, 'mdl_rank':None,
                     'ros':None, 'total':None, 'sig':None, 'l21':None})
    else:
        rows.append({
            'pl_rank':pl_rank, 'name':name,
            'mdl_rank':int(rec['ros_rank']) if pd.notna(rec.get('ros_rank')) else None,
            'ros':float(rec.get('xfp_rp3_per_start')) if pd.notna(rec.get('xfp_rp3_per_start')) else None,
            'sched':float(rec.get('xfp_rp3_per_start_sched')) if pd.notna(rec.get('xfp_rp3_per_start_sched')) else None,
            'l21':float(rec.get('recency_form_gap')) if pd.notna(rec.get('recency_form_gap')) else None,
            'sig':rec.get('signal'),
        })
df = pd.DataFrame(rows)
covered = df.dropna(subset=['mdl_rank']).copy()
print(f'Coverage: {len(covered)}/{len(df)} of PL Top 100 in my model')

if len(covered) >= 10:
    rho, _ = spearmanr(covered['pl_rank'], covered['mdl_rank'])
    print(f'Spearman ρ (PL vs my model): {rho:+.3f}')

covered['delta'] = covered['pl_rank'] - covered['mdl_rank']
covered['avg_rank'] = (covered['pl_rank'] + covered['mdl_rank']) / 2

# Per-tier average disagreement
for label, lo, hi in [('Top 25 (elite)',1,25),('26-50 (mid)',26,50),
                      ('51-75 (back-end)',51,75),('76-100 (deep)',76,100)]:
    sub = covered[(covered['pl_rank']>=lo) & (covered['pl_rank']<=hi)]
    if len(sub) > 0:
        print(f'  {label:<22} n={len(sub):>3}  mean |Δ|={sub["delta"].abs().mean():.1f}  '
              f'mean Δ={sub["delta"].mean():+.1f}')

print('\n--- BIGGEST AGREEMENTS (both lists rate them top tier) ---')
print(covered.nsmallest(10,'avg_rank')[['pl_rank','mdl_rank','name','ros','sig']].to_string(index=False))
print('\n--- PL HIGH, model LOW (model says fade) ---')
print(covered.nlargest(12,'delta')[['pl_rank','mdl_rank','name','ros','sched','l21','sig']].to_string(index=False))
print('\n--- model HIGH, PL LOW (model says hidden gem) ---')
print(covered.nsmallest(12,'delta')[['pl_rank','mdl_rank','name','ros','sched','l21','sig']].to_string(index=False))
print('\n--- NOT IN MY MODEL (PL ranks them but I have insufficient sample) ---')
missing = df[df['mdl_rank'].isna()]
for _, r in missing.iterrows():
    print(f'  PL #{r["pl_rank"]}: {r["name"]}')
