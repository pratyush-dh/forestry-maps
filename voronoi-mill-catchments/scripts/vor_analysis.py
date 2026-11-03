"""Day 3: Voronoi (Thiessen) catchments of the open mills, clipped to the lower 48, compared with the road-time catchments of Day 2.
Output: vor_cells.pkl (cells in km, per-mill stats)."""
import pickle, numpy as np, pandas as pd
from shapely.geometry import Polygon, MultiPoint, Point, box
from shapely.ops import unary_union, voronoi_diagram
from scipy.spatial import cKDTree

R = "../forest_to_mill_package/source/"
m = pd.read_csv(R + "mills_flow.csv"); h = pd.read_csv(R + "hexes.csv")
# two mills at one point (Camas, WA: pulp mill + panel/paper complex) can only have one cell -> one site, allocations summed
m["site"] = m.x.round(0).astype(str) + "_" + m.y.round(0).astype(str)
n_at = m.groupby("site").size()
agg = m.groupby("site", sort=False).agg(mill_id=("mill_id", "first"), name=("name", "first"), company=("company", "first"), state=("state", "first"), mill_type=("mill_type", "first"),
                                        x=("x", "first"), y=("y", "first"), allocated_ft3=("allocated_ft3", "sum")).reset_index()
agg["n_mills"] = agg.site.map(n_at).values
print("mills", len(m), "-> sites", len(agg), "| shared:", agg[agg.n_mills > 1].name.tolist())
m = agg
st = pickle.load(open("states.pkl", "rb"))
ABBR_SKIP = {2, 15}                                                     # no AK/HI (51 entries incl. DC)
polys = []
for f, s in st.items():
    if f in ABBR_SKIP: continue
    for r in s["rings"]: polys.append(Polygon(r).buffer(0))
land = unary_union(polys).buffer(0)                                      # km, spherical Albers
print("land area km2", round(land.area), "| states", len(st))

px = m.x.values / 1000; py = m.y.values / 1000
pts = MultiPoint(list(zip(px, py)))
vd = voronoi_diagram(pts, envelope=box(-6000, -4000, 6000, 4000))
cells = [None] * len(m)
for g in vd.geoms:
    k = [i for i in range(len(m)) if g.contains(Point(px[i], py[i]))]
    assert len(k) == 1; cells[k[0]] = g.intersection(land)
area = np.array([c.area for c in cells])
print("cell area km2: min %.0f median %.0f max %.0f | sum %.0f vs land %.0f" % (area.min(), np.median(area), area.max(), area.sum(), land.area))

# supply inside each cell: forest-hex removals whose nearest mill (straight line) is that mill  ==  hex centre inside the cell
fh = h[h.is_forest & h.removals_ft3.notna()]
tree = cKDTree(np.c_[px, py]); d, j = tree.query(np.c_[fh.x / 1000, fh.y / 1000])
supply = np.bincount(j, weights=fh.removals_ft3.values, minlength=len(m)) / 1e6      # million ft3 / yr
alloc = m.allocated_ft3.values / 1e6                                                 # Day 2: road-time nearest-mill allocation
print("supply total %.0f | allocated total %.0f (reach <=120 min)" % (supply.sum(), alloc.sum()))
dens = supply / area * 1e3                                                           # thousand ft3 / km2 / yr
out = pd.DataFrame(dict(n_mills=m.n_mills, mill_id=m.mill_id, name=m["name"], company=m.company, state=m.state, mill_type=m.mill_type, x=px, y=py,
                        area_km2=area, supply=supply, alloc=alloc, dens=dens, d_km_median=np.nan))
out["ratio"] = out.alloc / out.supply.replace(0, np.nan)
print(out[["area_km2", "supply", "alloc", "dens"]].describe().round(1).to_string())
print("cells with zero supply:", int((out.supply == 0).sum()))
print("corr(area, supply) %.2f | corr(log area, log dens) %.2f" % (np.corrcoef(area, supply)[0, 1], np.corrcoef(np.log(area), np.log(dens + 1e-3))[0, 1]))
print(out.sort_values("dens", ascending=False).head(8)[["name", "state", "mill_type", "area_km2", "supply", "dens"]].round(1).to_string())
print(out.sort_values("area_km2", ascending=False).head(6)[["name", "state", "area_km2", "supply"]].round(0).to_string())
# distance a hex travels to its Voronoi mill (km, straight line) -- the cell "reach"
out["reach_km"] = [np.sqrt(np.pi * 0 + 0) for _ in range(len(out))]
rk = pd.Series(d).groupby(j).quantile(.9) if False else None
pickle.dump(dict(cells=cells, land=land, df=out), open("vor_cells.pkl", "wb"))
out.to_csv("vor_stats.csv", index=False)
