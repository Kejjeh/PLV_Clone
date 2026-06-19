"""compare_pl_top150_hitters.py — PL Top 150 Hitters (Week 6) vs my rh3 model.

PL is 5x5 categorical (R/RBI/HR/AVG/SB); my model is FP/PA total. Expect
structural disagreements on speed-only guys (PL high) and OBP/walk guys
(my model neutral, PL also neutral in 5x5).
"""
from __future__ import annotations
import re, unicodedata
from pathlib import Path
import pandas as pd
from scipy.stats import spearmanr

from plv_clone.projections import PROJECTIONS

ROOT = Path('c:/Users/Joshua/plv_clone')
PROJ = PROJECTIONS.rh3()

def _strip(s): return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def norm(s):   return re.sub(r'[^a-z]+', '', _strip((s or '').lower()))

def name_key(name):
    if ',' in name:
        last, first = name.split(',', 1)
    else:
        parts = name.strip().split()
        if len(parts) < 2: return (norm(name), '')
        last, first = parts[-1], ' '.join(parts[:-1])
    return (norm(last), norm(first))

LOOKUP = {}
for _, r in PROJ.iterrows():
    nm = r.get('player_name')
    if pd.isna(nm):
        continue
    k = name_key(nm)
    # On dup names, prefer the higher-PA / lower-rank entry (the "famous" one)
    if k in LOOKUP:
        prev = LOOKUP[k]
        if (r.get('pa_to') or 0) > (prev.get('pa_to') or 0):
            LOOKUP[k] = r
    else:
        LOOKUP[k] = r

PL = [
  (1,'Aaron Judge'),(2,'Shohei Ohtani'),(3,'Jose Ramirez'),(4,'Juan Soto'),
  (5,'Bobby Witt Jr.'),(6,'Julio Rodriguez'),(7,'Kyle Tucker'),(8,'Corbin Carroll'),
  (9,'Yordan Alvarez'),(10,'Elly De La Cruz'),(11,'Junior Caminero'),(12,'Nick Kurtz'),
  (13,'Matt Olson'),(14,'Kyle Schwarber'),(15,'Drake Baldwin'),(16,'Ben Rice'),
  (17,'Fernando Tatis Jr.'),(18,'Vladimir Guerrero Jr.'),(19,'Pete Alonso'),(20,'Gunnar Henderson'),
  (21,'Brice Turang'),(22,'Bryce Harper'),(23,'James Wood'),(24,'Jackson Chourio'),
  (25,'Cal Raleigh'),(26,'Shea Langeliers'),(27,'Josh Naylor'),(28,'Freddie Freeman'),
  (29,'Trea Turner'),(30,'Zach Neto'),(31,'Jackson Merrill'),(32,'Riley Greene'),
  (33,'Cody Bellinger'),(34,'Brent Rooker'),(35,'Ketel Marte'),(36,'Hunter Goodman'),
  (37,'William Contreras'),(38,'Sal Stewart'),(39,'Byron Buxton'),(40,'Michael Harris II'),
  (41,'Jazz Chisholm Jr.'),(42,'Manny Machado'),(43,'Nico Hoerner'),(44,'Alex Bregman'),
  (45,'Corey Seager'),(46,'Andy Pages'),(47,'CJ Abrams'),(48,'Seiya Suzuki'),
  (49,'Mike Trout'),(50,'Munetaka Murakami'),(51,'Austin Riley'),(52,'Rafael Devers'),
  (53,'Maikel Garcia'),(54,'Oneil Cruz'),(55,'Ian Happ'),(56,'Ozzie Albies'),
  (57,'Pete Crow-Armstrong'),(58,'Randy Arozarena'),(59,'Yandy Diaz'),(60,'Kevin McGonigle'),
  (61,'Ivan Herrera'),(62,'Will Smith'),(63,'Salvador Perez'),(64,'Taylor Ward'),
  (65,'Brandon Lowe'),(66,'Jo Adell'),(67,'Teoscar Hernandez'),(68,'Alec Burleson'),
  (69,'Tyler Soderstrom'),(70,'Jonathan Aranda'),(71,'Jordan Walker'),(72,'Konnor Griffin'),
  (73,'Xavier Edwards'),(74,'Jose Altuve'),(75,'Otto Lopez'),(76,'Michael Busch'),
  (77,'Christian Walker'),(78,'George Springer'),(79,'Max Muncy'),(80,'Vinnie Pasquantino'),
  (81,'Bryan Reynolds'),(82,'JJ Wetherholt'),(83,'Bo Bichette'),(84,'Willy Adames'),
  (85,'Brandon Nimmo'),(86,'Xander Bogaerts'),(87,'Roman Anthony'),(88,'Jarren Duran'),
  (89,'Dansby Swanson'),(90,'Isaac Paredes'),(91,'Kazuma Okamoto'),(92,'Chase DeLauter'),
  (93,'Willson Contreras'),(94,'Wilyer Abreu'),(95,'Colson Montgomery'),(96,'Jacob Wilson'),
  (97,'Josh Jung'),(98,'Liam Hicks'),(99,'Trent Grisham'),(100,'Geraldo Perdomo'),
  (101,"Ryan O'Hearn"),(102,'Daulton Varsho'),(103,'Matt Chapman'),(104,'Samuel Basallo'),
  (105,'Carlos Cortes'),(106,'Steven Kwan'),(107,'Miguel Vargas'),(108,'Ramon Laureano'),
  (109,'Luis Arraez'),(110,'Adley Rutschman'),(111,'Carter Jensen'),(112,'Dillon Dingler'),
  (113,'Chase Meidroth'),(114,'Brandon Marsh'),(115,'Chandler Simpson'),(116,'Jose Caballero'),
  (117,'Trevor Story'),(118,'Ceddanne Rafaela'),(119,'Spencer Torkelson'),(120,'Jac Caglianone'),
  (121,'Casey Schmitt'),(122,'Daylen Lile'),(123,'Kyle Stowers'),(124,'Colt Keith'),
  (125,'Bryson Stott'),(126,'TJ Rumfield'),(127,'Ildemaro Vargas'),(128,'Masyn Winn'),
  (129,'Jakob Marsee'),(130,'Mickey Moniak'),(131,'Mauricio Dubon'),(132,'Francisco Alvarez'),
  (133,'Garrett Mitchell'),(134,'Brooks Lee'),(135,'Jake Burger'),(136,'Marcus Semien'),
  (137,'Luke Keaschall'),(138,'J.P. Crawford'),(139,'Ryan Jeffers'),(140,'Kerry Carpenter'),
  (141,'JJ Bleday'),(142,'Jorge Soler'),(143,'Nathaniel Lowe'),(144,'Addison Barger'),
  (145,'Moises Ballesteros'),(146,'Jung Hoo Lee'),(147,'Ernie Clement'),(148,'Miguel Andujar'),
  (149,'Cam Smith'),(150,'Heliot Ramos'),
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
                     'fp_per_pa':None, 'fp_per_g':None, 'sig':None, 'team':None})
    else:
        rows.append({
            'pl_rank':pl_rank, 'name':name,
            'mdl_rank':int(rec['rank']) if pd.notna(rec.get('rank')) else None,
            'fp_per_pa':float(rec.get('xfp_rh3_per_pa')) if pd.notna(rec.get('xfp_rh3_per_pa')) else None,
            'fp_per_g':float(rec.get('xfp_rh3_per_game')) if pd.notna(rec.get('xfp_rh3_per_game')) else None,
            'ros_total':float(rec.get('expected_total_fp_remaining')) if pd.notna(rec.get('expected_total_fp_remaining')) else None,
            'repl_delta':float(rec.get('replacement_delta')) if pd.notna(rec.get('replacement_delta')) else None,
            'pa_to':int(rec.get('pa_to')) if pd.notna(rec.get('pa_to')) else None,
            'team':rec.get('team'),
            'pos':rec.get('primary_position'),
            'sig':rec.get('signal'),
        })
df = pd.DataFrame(rows)
covered = df.dropna(subset=['mdl_rank']).copy()
print(f'Coverage: {len(covered)}/{len(df)} of PL Top 150 in my model')

if len(covered) >= 10:
    rho, _ = spearmanr(covered['pl_rank'], covered['mdl_rank'])
    print(f'Spearman rho (PL vs my model): {rho:+.3f}')

covered['delta'] = covered['pl_rank'] - covered['mdl_rank']
covered['avg_rank'] = (covered['pl_rank'] + covered['mdl_rank']) / 2

for label, lo, hi in [('Top 25 (elite)',1,25),('26-50 (strong)',26,50),
                      ('51-75 (mid)',51,75),('76-100 (mid-back)',76,100),
                      ('101-125 (back)',101,125),('126-150 (deep)',126,150)]:
    sub = covered[(covered['pl_rank']>=lo) & (covered['pl_rank']<=hi)]
    if len(sub) > 0:
        print(f'  {label:<22} n={len(sub):>3}  mean |Δ|={sub["delta"].abs().mean():.1f}  '
              f'mean Δ={sub["delta"].mean():+.1f}')

print('\n--- BIGGEST AGREEMENTS (both rate top tier) ---')
print(covered.nsmallest(15,'avg_rank')[['pl_rank','mdl_rank','name','team','pos','fp_per_g','sig']].to_string(index=False))
print('\n--- PL HIGH, model LOW (model says fade) ---')
print(covered.nlargest(15,'delta')[['pl_rank','mdl_rank','name','team','pos','fp_per_g','pa_to','repl_delta','sig']].to_string(index=False))
print('\n--- model HIGH, PL LOW (model says hidden gem) ---')
print(covered.nsmallest(15,'delta')[['pl_rank','mdl_rank','name','team','pos','fp_per_g','pa_to','repl_delta','sig']].to_string(index=False))
print('\n--- NOT IN MY MODEL (PL ranks them; insufficient sample / not in rh3) ---')
missing = df[df['mdl_rank'].isna()]
for _, r in missing.iterrows():
    print(f'  PL #{r["pl_rank"]}: {r["name"]}')
