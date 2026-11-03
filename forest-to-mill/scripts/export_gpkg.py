"""Export the map data as a GeoPackage for QGIS / ArcGIS (custom spherical Albers, metres).
Reads ../data/map_data.json (the same file the web app and the poster use) and writes ../data/south_connectivity.gpkg.
Both ways of placing county removals are kept side by side: evenly (the original method) and by NLCD tree canopy.
Traffic model: each forest hex splits its removals across every mill within 120 min by road, weights exp(-(t - t_nearest)/15 min)
('spread15'); 'nearest' sends everything to the single nearest mill. Loads are summed over every route crossing a segment."""
import json, base64, os
import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point, MultiPolygon

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "..", "data", "map_data.json")))
OUT = os.path.join(HERE, "..", "data", "south_connectivity.gpkg")
CRS_WKT = ('PROJCS["US_Wood_Mills_Albers_Sphere",GEOGCS["GCS_Sphere",DATUM["D_Sphere",SPHEROID["Sphere",6371008.8,0.0]],PRIMEM["Greenwich",0.0],'
           'UNIT["Degree",0.0174532925199433]],PROJECTION["Albers"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
           'PARAMETER["Central_Meridian",-96.0],PARAMETER["Standard_Parallel_1",29.5],PARAMETER["Standard_Parallel_2",45.5],'
           'PARAMETER["Latitude_Of_Origin",37.5],UNIT["Meter",1.0]]')
CAP, SPREAD = 120.0, 15.0

N = D["n"]; raw = base64.b64decode(D["e"])
EC = np.frombuffer(raw[:N * 8], dtype=np.int16).reshape(N, 4) / 10.0 * 1000.0       # metres
CLS = np.frombuffer(raw[N * 8:], dtype=np.uint8)
CLASS_NAMES = ["Major Highway", "Secondary Highway", "Beltway", "Bypass", "Road"]
rows = D["hexes"]      # [id,x,y,county,state,rem_even,ff,km2,isForest,routes,canopy,rem_canopy]  (km, M ft3/yr)
mills = D["mills"]     # [idx,id,name,company,state,type,x,y,nx,ny]
mIdx = {m[0]: i for i, m in enumerate(mills)}

def loads(rem_col, spread):
    load = np.zeros(N); recv = np.zeros(len(mills))
    for r in rows:
        v = r[rem_col]
        if not v: continue
        rs = [q for q in r[9] if q[1] <= CAP]
        if not rs: continue
        t0 = rs[0][1]
        w = np.array([1.0 if q[1] == t0 else 0.0 for q in rs]) if spread == 0 else np.exp(-(np.array([q[1] for q in rs]) - t0) / spread)
        w /= w.sum()
        for q, f in zip(rs, w):
            recv[mIdx[q[0]]] += v * f
            for i in q[4]: load[i] += v * f
    return load, recv

L = {}
for name, col in (("even", 5), ("canopy", 11)):
    for sp, tag in ((0, "nearest"), (SPREAD, "spread15")):
        L[(name, tag)] = loads(col, sp)

# ---- hexes
R, rot = D["hexR"] * 1000.0, D["hexRot"]
def hexpoly(x, y):
    return Polygon([(x * 1000 + R * np.cos(rot + j * np.pi / 3), y * 1000 + R * np.sin(rot + j * np.pi / 3)) for j in range(6)])
rec = []
for r in rows:
    inr = sorted(q[1] for q in r[9] if q[1] <= CAP)
    rs = [q for q in r[9] if q[1] <= CAP]
    rec.append(dict(hex_id=r[0], county=r[3], state_fips=r[4], fia_forest_share=r[6], fia_forest_km2=r[7], is_forest_source=int(bool(r[8])),
                    nlcd_canopy_mean_pct=r[10], removals_even_Mft3=r[5], removals_canopy_Mft3=r[11],
                    n_mills_60=sum(t <= 60 for t in inr), n_mills_120=len(inr),
                    nearest_min=(inr[0] if inr else None), nearest_mill=(mills[mIdx[rs[0][0]]][1] if rs else None)))
hx = gpd.GeoDataFrame(rec, geometry=[hexpoly(r[1], r[2]) for r in rows], crs=CRS_WKT)

# ---- roads
segs = [LineString([(EC[i, 0], EC[i, 1]), (EC[i, 2], EC[i, 3])]) for i in range(N)]
roads = gpd.GeoDataFrame(dict(road_class=[CLASS_NAMES[c] for c in CLS], len_km=[round(s.length / 1000, 2) for s in segs],
                              load_even_nearest_Mft3=L[("even", "nearest")][0].round(2), load_even_spread15_Mft3=L[("even", "spread15")][0].round(2),
                              load_canopy_nearest_Mft3=L[("canopy", "nearest")][0].round(2), load_canopy_spread15_Mft3=L[("canopy", "spread15")][0].round(2)),
                         geometry=segs, crs=CRS_WKT)

# ---- mills, states
ml = gpd.GeoDataFrame(dict(mill_id=[m[1] for m in mills], name=[m[2] for m in mills], company=[m[3] for m in mills], state=[m[4] for m in mills], mill_type=[m[5] for m in mills],
                           received_even_spread15_Mft3=L[("even", "spread15")][1].round(2), received_canopy_spread15_Mft3=L[("canopy", "spread15")][1].round(2),
                           hexes_in_range=[sum(1 for r in rows if any(q[0] == m[0] and q[1] <= CAP for q in r[9])) for m in mills]),
                      geometry=[Point(m[6] * 1000, m[7] * 1000) for m in mills], crs=CRS_WKT)
st = gpd.GeoDataFrame(dict(fips=[s[0] for s in D["states"]], name=[s[1] for s in D["states"]], in_study=[s[2] for s in D["states"]]),
                      geometry=[MultiPolygon([Polygon([(a * 1000, b * 1000) for a, b in ring]) for ring in s[3]]) for s in D["states"]], crs=CRS_WKT)

if os.path.exists(OUT): os.remove(OUT)
for lname, g in (("hex_forest_connectivity", hx), ("roads_traffic", roads), ("mills", ml), ("states", st)):
    g.to_file(OUT, layer=lname, driver="GPKG"); print(lname, len(g))
print("busiest segment, canopy / spread15: %.0f M ft3/yr" % roads.load_canopy_spread15_Mft3.max())
