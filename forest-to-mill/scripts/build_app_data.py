import json, base64, pickle, numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Polygon as SPoly
d = json.load(open('data2.json'))
E, H, M, S = d['edges'], d['hexes'], d['mills'], d['states']
# edges -> int16 (0.1 km) + class bytes, base64
co = np.round(np.array([e[:4] for e in E]) * 10).astype(np.int16); cl = np.array([e[4] for e in E], np.uint8)
blob = base64.b64encode(co.tobytes() + cl.tobytes()).decode()
# hex geometry: all hexes share radius/rotation
R = []; A = []
for h in H:
    ring = np.array(h[3]); c = np.array([h[1], h[2]]); v = ring[0] - c
    R.append(np.hypot(*v)); A.append(np.arctan2(v[1], v[0]) % (np.pi / 3))
print("hex R range", min(R), max(R), "rot range", min(A), max(A))
hexes = [[h[0], h[1], h[2], h[4], h[5], h[6], h[8], h[9], h[10], h[7]] for h in H]
# labels: study-state positions, neighbouring states, graticule
ST = {40:"Oklahoma",48:"Texas",5:"Arkansas",22:"Louisiana",28:"Mississippi",1:"Alabama",47:"Tennessee",21:"Kentucky",13:"Georgia",12:"Florida",45:"South Carolina",37:"North Carolina",51:"Virginia"}
AB = {40:"OK",48:"TX",5:"AR",22:"LA",28:"MS",1:"AL",47:"TN",21:"KY",13:"GA",12:"FL",45:"SC",37:"NC",51:"VA"}
OFF = {22:(-85,-55), 1:(-15,70), 45:(25,-10)}
sl = []
for f, nm in ST.items():
    pts = np.array([[h[1], h[2]] for h in H if h[4 if False else 5] == f]); cx, cy = np.median(pts[:,0]), np.median(pts[:,1]); dx, dy = OFF.get(f, (0,0))
    sl.append([nm, AB[f], round(cx+dx,1), round(cy+dy,1)])
allst = pickle.load(open('states.pkl','rb')); nbr = []
for f, s in allst.items():
    if f in ST or f in (2,15) or f > 56: continue
    p = max((SPoly(r) for r in s['rings']), key=lambda q: q.area)
    if p.area < 20000: continue
    c = p.representative_point(); nbr.append([s['name'], round(c.x,1), round(c.y,1)])
crs = CRS.from_wkt(open("../forest_to_mill_package/data/map_projected/hexes.prj").read())
tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True); grat = []
for lat in range(25, 50, 5):
    lo = np.arange(-116, -60, 1.0); x, y = tf.transform(lo, np.full_like(lo, lat)); grat.append([[round(a/1000,1), round(b/1000,1)] for a, b in zip(x, y)])
for lon in range(-110, -65, 5):
    la = np.arange(22, 52, 1.0); x, y = tf.transform(np.full_like(la, lon), la); grat.append([[round(a/1000,1), round(b/1000,1)] for a, b in zip(x, y)])
out = dict(n=len(E), e=blob, hexR=round(float(np.mean(R)),3), hexRot=round(float(np.mean(A)),5), hexes=hexes, mills=M, states=S, sl=sl, nbr=nbr, grat=grat,
           water=[["Gulf of America",760,-1245],["Atlantic\nOcean",1680,-430]], mexico=[-620,-1010])
json.dump(out, open('app_data.json','w'), separators=(',',':'))
import os; print("app_data.json MB", round(os.path.getsize('app_data.json')/1e6,2), "| n edges", len(E), "| neighbours", len(nbr))
