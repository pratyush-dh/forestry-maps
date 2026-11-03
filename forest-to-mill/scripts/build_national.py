"""Build the national (lower 48) web-map data: open mills only, every forest hex routed to every mill within 120 min by road.
Inputs: the package source CSVs, canopy_hex_nat.csv + canopy_nat_2km.png (canopy_nat.py), states.pkl, app_data.json (labels/graticule helpers).
Output: app_data_nat.json (read by the web map)."""
import json, base64, pickle, os, io
import numpy as np, pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from pyproj import CRS, Transformer
from PIL import Image

R = "../forest_to_mill_package/"
S = R + "source/"
e = pd.read_csv(S + "edges.csv"); h = pd.read_csv(S + "hexes.csv"); mf = pd.read_csv(S + "mills_flow.csv"); mc = pd.read_csv(S + "mills_clean.csv")
cn = pd.read_csv("canopy_hex_nat.csv").set_index("hex_id")
print("edges", len(e), "hexes", len(h), "open mills", len(mf), mf.operational_status.value_counts().to_dict())
assert set(mf.operational_status) <= {"open", "partial", "reopened"} and not mf.state.isin(["AK", "HI"]).any()

# ---------------- routing (same method as the southern build)
N = int(max(e.u.max(), e.v.max())) + 1
nx = np.zeros(N); ny = np.zeros(N); nx[e.u] = e.x1; ny[e.u] = e.y1; nx[e.v] = e.x2; ny[e.v] = e.y2
G = csr_matrix((np.r_[e.minutes, e.minutes], (np.r_[e.u, e.v], np.r_[e.v, e.u])), shape=(N, N))
used = np.zeros(N, bool); used[e.u] = used[e.v] = True; ids = np.where(used)[0]; tree = cKDTree(np.c_[nx[ids], ny[ids]])
md, mj = tree.query(np.c_[mf.x, mf.y]); mnode = ids[mj]; mleg = md * 1.35 / 1000 / 40 * 60
D = dijkstra(G, directed=False, indices=mnode, limit=200) + mleg[:, None]
fh = h[h.is_forest].reset_index(drop=True)
dd, jj = tree.query(np.c_[fh.x, fh.y], k=6); nodes = ids[jj]; leg = dd * 1.35 / 1000 / 40 * 60
T = np.full((len(fh), len(mf)), np.inf)
for k in range(6): T = np.minimum(T, D[:, nodes[:, k]].T + leg[:, [k]])
print("forest hexes", len(fh), "| pairs within 120 min:", int((T <= 120).sum()))
# validation against the package's own nearest-mill result
ok = fh.reached.values; tmin = T.min(1); near = T.argmin(1)
print("reach agreement %.4f | same nearest mill (where reached) %.4f | median |dt| %.4f min" % (((tmin <= 120) == ok).mean(), (near[ok] == fh.mill_idx.values[ok]).mean(), np.median(np.abs(tmin[ok] - fh.haul_min.values[ok]))))
eid = {}
for i, (u, v) in enumerate(zip(e.u.values, e.v.values)): eid[(u, v)] = i; eid[(v, u)] = i
routes = {int(i): [] for i in fh.hex_id}; hid = fh.hex_id.values; bad = 0
for mi in range(len(mf)):
    pairs = np.where(T[:, mi] <= 120)[0]
    if not len(pairs): continue
    dist, pred = dijkstra(G, directed=False, indices=mnode[mi], return_predecessors=True, limit=200)
    for hi in pairs:
        kk = np.argmin(dist[nodes[hi]] + mleg[mi] + leg[hi]); n = nodes[hi, kk]; path = []; cur = n
        while cur != mnode[mi]:
            p = pred[cur]; path.append(eid.get((p, cur), -1)); cur = p
        bad += (-1 in path)
        routes[int(hid[hi])].append([int(mi), round(float(T[hi, mi]), 1), round(nx[n] / 1000, 1), round(ny[n] / 1000, 1), [int(q) for q in path if q >= 0]])
for v in routes.values(): v.sort(key=lambda r: r[1])
print("routes", sum(map(len, routes.values())), "| with a missing edge:", bad)

# ---------------- removals: county totals placed evenly (removals_even) or by NLCD canopy
rows = []
rem_e = np.array([r / 1e6 if (isf and r == r) else np.nan for r, isf in zip(h.removals_ft3, h.is_forest)], float)
can = np.array([float(cn.loc[i, "canopy_mean"]) for i in h.hex_id]); fips = h.county_fips.values
rem_c = rem_e.copy()
for f in np.unique(fips):
    ix = np.where((fips == f) & np.isfinite(rem_e))[0]
    if len(ix) < 2: continue
    w = np.nan_to_num(can[ix])
    if w.sum() > 0: rem_c[ix] = rem_e[ix].sum() * w / w.sum()
print("forest-hex removals: even %.1f vs canopy %.1f M ft3 (package: %.1f)" % (np.nansum(rem_e), np.nansum(rem_c), S and 20800.0))
pkg_reach = h[h.is_forest & h.reached].removals_ft3.sum() / h[h.is_forest].removals_ft3.sum()
mine = sum(rem_e[i] for i in range(len(h)) if h.is_forest.iloc[i] and (routes.get(int(h.hex_id.iloc[i])) or [[0, 999]])[0][1] <= 120 and np.isfinite(rem_e[i])) / np.nansum(rem_e)
print("share of forest-hex removals within 120 min of a mill: package %.4f | rebuilt %.4f" % (pkg_reach, mine))
for i, r in enumerate(h.itertuples()):
    rows.append([int(r.hex_id), round(r.x / 1000, 1), round(r.y / 1000, 1), str(r.county), int(r.county_fips // 1000),
                 None if not np.isfinite(rem_e[i]) else round(float(rem_e[i]), 2), round(float(r.forest_frac), 3), round(float(r.forest_km2), 1), 1 if r.is_forest else 0,
                 routes.get(int(r.hex_id), []), int(round(can[i])), None if not np.isfinite(rem_c[i]) else round(float(rem_c[i]), 2)])

# ---------------- edges (all roads), mills, states, labels
co = np.round(np.c_[e.x1, e.y1, e.x2, e.y2] / 100.0).astype(np.int16)           # 0.1 km
cls = {"Major Highway": 0, "Secondary Highway": 1, "Beltway": 2, "Bypass": 3, "Road": 4}
blob = base64.b64encode(co.tobytes() + np.array([cls[c] for c in e.road_class], np.uint8).tobytes()).decode()
comp = dict(zip(mc.mill_id, mc.company))
mills = [[int(i), r.mill_id, r.name, comp.get(r.mill_id) if isinstance(comp.get(r.mill_id), str) else "", r.state, r.mill_type, round(r.x / 1000, 1), round(r.y / 1000, 1),
          round(nx[mnode[i]] / 1000, 1), round(ny[mnode[i]] / 1000, 1)] for i, r in enumerate(mf.itertuples())]
ABBR = {1: "AL", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE", 11: "DC", 12: "FL", 13: "GA", 16: "ID", 17: "IL", 18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD", 25: "MA",
        26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV", 33: "NH", 34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC",
        46: "SD", 47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI", 56: "WY"}
st = pickle.load(open("states.pkl", "rb")); states = []; stn = {}; sl = []
for f, s in st.items():
    if f not in ABBR: continue
    stn[str(f)] = s["name"]; rings = []
    for r in s["rings"]:
        p = Polygon(r).simplify(0.6)
        if p.is_empty: continue
        for g in (p.geoms if p.geom_type == "MultiPolygon" else [p]): rings.append([[round(a, 1), round(b, 1)] for a, b in g.exterior.coords])
    states.append([f, s["name"], 1, rings])
    hh = h[(h.county_fips // 1000 == f) & h.on_land]
    if len(hh): sl.append([s["name"], ABBR[f], round(float(hh.x.median() / 1000), 1), round(float(hh.y.median() / 1000), 1)])
crs = CRS.from_wkt(open(R + "data/map_projected/hexes.prj").read()); tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
grat = []
for lat in range(25, 55, 5):
    lo = np.arange(-135, -55, 1.0); x, y = tf.transform(lo, np.full_like(lo, lat)); grat.append([[round(a / 1000, 1), round(b / 1000, 1)] for a, b in zip(x, y)])
for lon in range(-125, -65, 5):
    la = np.arange(20, 55, 1.0); x, y = tf.transform(np.full_like(la, lon), la); grat.append([[round(a / 1000, 1), round(b / 1000, 1)] for a, b in zip(x, y)])
def pt(lon, lat): x, y = tf.transform(lon, lat); return [round(x / 1000, 1), round(y / 1000, 1)]
water = [["Gulf of America"] + pt(-90.5, 26.2), ["Atlantic" + chr(10) + "Ocean"] + pt(-70.5, 33.5), ["Pacific" + chr(10) + "Ocean"] + pt(-127.6, 40.5)]
# canopy raster: 16 grey levels, as before
a = np.asarray(Image.open("canopy_nat_2km.png").convert("L")).astype(float)
q = (np.round(a / 255 * 16) * 16).clip(0, 255).astype(np.uint8); buf = io.BytesIO(); Image.fromarray(q, "L").save(buf, "PNG", optimize=True)
meta = json.load(open("canopy_nat_meta.json"))
old = json.load(open("app_data.json"))
out = dict(n=len(e), e=blob, hexR=old["hexR"], hexRot=old["hexRot"], hexes=rows, mills=mills, states=states, sl=sl, nbr=[], grat=grat, water=water,
           mexico=pt(-102.0, 25.6), stn=stn, can=dict(png=base64.b64encode(buf.getvalue()).decode(), x0=meta["x0"], y1=meta["y1"], cell=meta["cell_km"], w=meta["w"], h=meta["h"], year=meta["year"]))
json.dump(out, open("app_data_nat.json", "w"), separators=(",", ":"))
print("app_data_nat.json MB", round(os.path.getsize("app_data_nat.json") / 1e6, 2), "| states", len(states), "| mills", len(mills), "| canopy png KB", len(buf.getvalue()) // 1024)
