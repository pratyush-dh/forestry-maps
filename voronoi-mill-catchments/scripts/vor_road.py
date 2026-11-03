"""Day 3, road-time version: each land hex goes to the mill it can reach fastest on the road network (no 120-minute cap), and the hexes of one mill
are merged into that mill's road-time polygon. Same 116 mill sites, same land outline and same wood as the straight-line Voronoi (vor_analysis.py).
Output: vor_road.pkl (cells in km + stats), vor_road_stats.csv."""
import os, pickle, numpy as np, pandas as pd
try:
    import rasterio; pd_ = os.path.join(os.path.dirname(rasterio.__file__), "proj_data"); os.environ["PROJ_LIB"] = pd_; os.environ["PROJ_DATA"] = pd_
except Exception: pass
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import shape, Point
from shapely.ops import unary_union
import shapely
from rasterio import features
from rasterio.transform import from_origin

R = "../forest_to_mill_package/source/"
S = pickle.load(open("vor_cells.pkl", "rb")); land = S["land"]; sdf = S["df"].reset_index(drop=True); scells = S["cells"]
e = pd.read_csv(R + "edges.csv"); h = pd.read_csv(R + "hexes.csv"); mf = pd.read_csv(R + "mills_flow.csv")
mf["site"] = mf.x.round(0).astype(str) + "_" + mf.y.round(0).astype(str)
sites = mf.drop_duplicates("site").reset_index(drop=True); assert len(sites) == len(sdf) and (sites.mill_id.values == sdf.mill_id.values).all()
px, py = sites.x.values, sites.y.values

# ---- routing (same graph, speeds and off-network legs as the Day 2 build), uncapped
N = int(max(e.u.max(), e.v.max())) + 1
nx = np.zeros(N); ny = np.zeros(N); nx[e.u] = e.x1; ny[e.u] = e.y1; nx[e.v] = e.x2; ny[e.v] = e.y2
G = csr_matrix((np.r_[e.minutes, e.minutes], (np.r_[e.u, e.v], np.r_[e.v, e.u])), shape=(N, N))
used = np.zeros(N, bool); used[e.u] = used[e.v] = True; ids = np.where(used)[0]; tree = cKDTree(np.c_[nx[ids], ny[ids]])
md, mj = tree.query(np.c_[px, py]); mnode = ids[mj]; mleg = md * 1.35 / 1000 / 40 * 60
D = dijkstra(G, directed=False, indices=mnode) + mleg[:, None]                      # sites x nodes, minutes
lh = h[h.on_land | (h.is_forest & h.removals_ft3.notna())].reset_index(drop=True)      # land hexes plus coastal forest hexes with removals (so the wood totals match the straight-line version)
dd, jj = tree.query(np.c_[lh.x, lh.y], k=6); nodes = ids[jj]; leg = dd * 1.35 / 1000 / 40 * 60
T = np.full((len(lh), len(sites)), np.inf)
for k in range(6): T = np.minimum(T, D[:, nodes[:, k]].T + leg[:, [k]])
# A hex can also reach a mill straight across country at the off-network speed (40 km/h, detour 1.35). Without this, a mill that sits far from any mapped road pays its
# whole off-road leg on every route to it and loses even the hexes next to it. Time = the faster of the road route and the direct off-road route.
dkm = np.hypot(lh.x.values[:, None] - px[None, :], lh.y.values[:, None] - py[None, :]) / 1000
direct = dkm * 1.35 / 40 * 60
print("hex-mill pairs where the direct off-road route beats the road route: %.2f%% of all, %.1f%% of each hex's best" % (100 * (direct < T).mean(), 100 * (direct.min(1) < T.min(1)).mean()))
T = np.minimum(T, direct)
tmin = T.min(1); road = (T + 1e-4 * dkm).argmin(1)
straight = cKDTree(np.c_[px, py]).query(np.c_[lh.x, lh.y])[1]
bad = ~np.isfinite(tmin); road[bad] = straight[bad]
print("land hexes", len(lh), "| unreachable by road (fall back to straight line):", int(bad.sum()), "| median min to nearest mill %.0f, 90th %.0f" % (np.median(tmin[~bad]), np.percentile(tmin[~bad], 90)))
chg = road != straight
print("hexes whose nearest mill differs, road vs straight: %d of %d (%.1f%%)" % (chg.sum(), len(lh), 100 * chg.mean()))

# ---- wood per site, road-time catchment
f = (lh.is_forest & lh.removals_ft3.notna()).values; rem = np.where(f, lh.removals_ft3.fillna(0).values, 0.0)
sup_r = np.bincount(road, weights=rem, minlength=len(sites)) / 1e6; sup_s = np.bincount(straight, weights=rem, minlength=len(sites)) / 1e6
print("wood total %.0f | in hexes whose nearest mill differs: %.1f%%" % (rem.sum() / 1e6, 100 * rem[chg].sum() / rem.sum()))

# ---- polygons: 5 km grid inside the land outline, each pixel takes the mill of its nearest land-hex centre
cell = 5.0; lx0, ly0, lx1, ly1 = land.bounds; lx0 = np.floor(lx0 / cell) * cell; ly1 = np.ceil(ly1 / cell) * cell
wpx = int((lx1 - lx0) / cell) + 2; hpx = int((ly1 - np.floor(ly0 / cell) * cell) / cell) + 2
xs = lx0 + (np.arange(wpx) + .5) * cell; ys = ly1 - (np.arange(hpx) + .5) * cell
XX, YY = np.meshgrid(xs, ys)
inland = shapely.contains_xy(land.buffer(6), XX.ravel(), YY.ravel())
ht = cKDTree(np.c_[lh.x.values / 1000, lh.y.values / 1000])
lab = np.full(XX.size, -1, int); q = np.where(inland)[0]
lab[q] = road[ht.query(np.c_[XX.ravel()[q], YY.ravel()[q]])[1]]
lab_s = np.full(XX.size, -1, int); lab_s[q] = cKDTree(np.c_[px / 1000, py / 1000]).query(np.c_[XX.ravel()[q], YY.ravel()[q]])[1]
lab = lab.reshape(XX.shape); lab_s = lab_s.reshape(XX.shape)
tr = from_origin(lx0, ly1, cell, cell)
parts = {i: [] for i in range(len(sites))}
for geom, v in features.shapes(lab.astype(np.int32), mask=lab >= 0, transform=tr, connectivity=4):
    parts[int(v)].append(shape(geom))
cells = []
for i in range(len(sites)):
    g = unary_union(parts[i]).simplify(2.5).buffer(0) if parts[i] else None
    cells.append(g.intersection(land) if g is not None else shapely.Polygon())
area = np.array([c.area for c in cells])
inside = lab >= 0
agree = (lab == lab_s) & inside
print("land area where the road-time mill is also the straight-line mill: %.1f%%" % (100 * agree.sum() / inside.sum()))
print("mills with an EMPTY road-time polygon:", [sites.name[i] for i in range(len(sites)) if cells[i].is_empty])
overlap = np.array([cells[i].intersection(scells[i]).area / scells[i].area if not cells[i].is_empty else 0 for i in range(len(sites))])

# wood-weighted travel time to the mill, per road-time catchment
tfin = np.where(np.isfinite(tmin), tmin, np.nan)
def _wt(i):
    m_ = (road == i) & f & np.isfinite(tmin)
    return np.average(tmin[m_], weights=rem[m_]) if m_.any() and rem[m_].sum() > 0 else np.nan
wt = np.array([_wt(i) for i in range(len(sites))])
own = [cells[i].buffer(0.01).contains(Point(px[i] / 1000, py[i] / 1000)) for i in range(len(sites))]
print("mill sites lying inside their own road-time polygon: %d of %d" % (sum(own), len(sites)), [sites.name[i] for i in range(len(sites)) if not own[i]][:12])
out = sdf[["n_mills", "mill_id", "name", "company", "state", "mill_type", "x", "y"]].copy()
out["area_straight"] = sdf.area_km2; out["supply_straight"] = sdf.supply; out["dens_straight"] = sdf.dens
out["area_road"] = area; out["supply_road"] = sup_r; out["dens_road"] = np.where(area > 0, sup_r / np.maximum(area, 1) * 1e3, np.nan)
out["alloc_day2"] = sdf.alloc; out["share_of_straight_cell_kept"] = overlap; out["wood_minutes_to_mill"] = wt
out["hexes_road"] = np.bincount(road, minlength=len(sites))
pd.set_option("display.width", 200)
print(out[["area_straight", "area_road", "supply_straight", "supply_road", "alloc_day2", "dens_road", "share_of_straight_cell_kept", "wood_minutes_to_mill"]].describe().round(1).to_string())
print("corr(supply_road, alloc_day2) %.2f | total alloc_day2 %.0f vs supply_road %.0f" % (np.corrcoef(out.supply_road, out.alloc_day2)[0, 1], out.alloc_day2.sum(), out.supply_road.sum()))
d = out.assign(ratio=out.supply_road / out.supply_straight).sort_values("ratio")
print("biggest losers:", d.head(4)[["name", "state", "supply_straight", "supply_road"]].round(0).values.tolist())
print("biggest gainers:", d.tail(4)[["name", "state", "supply_straight", "supply_road"]].round(0).values.tolist())
pickle.dump(dict(cells=cells, land=land, df=out, hex_xy=np.c_[lh.x / 1000, lh.y / 1000], hex_road=road, hex_straight=straight, hex_min=tmin, hex_rem=rem / 1e6, hex_id=lh.hex_id.values,
                 share_agree=float(agree.sum() / inside.sum()), share_wood_changed=float(rem[chg].sum() / rem.sum())), open("vor_road.pkl", "wb"))
out.to_csv("vor_road_stats.csv", index=False)
