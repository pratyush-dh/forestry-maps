"""Smooth the road-time polygon EDGES (display only). The hex-to-mill assignment and the wood per mill (vor_road.py) are unchanged; the 5 km label raster is blurred
(Gaussian, sigma 4 px = 20 km) and each pixel takes the strongest mill, so shared boundaries stay shared. Then area, density, overlap and the own-site check are recomputed."""
import os, pickle, numpy as np, pandas as pd
try:
    import rasterio; p_ = os.path.join(os.path.dirname(rasterio.__file__), "proj_data"); os.environ["PROJ_LIB"] = p_; os.environ["PROJ_DATA"] = p_
except Exception: pass
import shapely
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from rasterio import features
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

R = pickle.load(open("vor_road.pkl", "rb")); S = pickle.load(open("vor_cells.pkl", "rb"))
land, df, scells = R["land"], R["df"], S["cells"]; n = len(df)
px, py = df.x.values, df.y.values                                   # km already
cell = 5.0; lx0, ly0, lx1, ly1 = land.bounds; lx0 = np.floor(lx0 / cell) * cell; ly1 = np.ceil(ly1 / cell) * cell
wpx = int((lx1 - lx0) / cell) + 2; hpx = int((ly1 - np.floor(ly0 / cell) * cell) / cell) + 2
xs = lx0 + (np.arange(wpx) + .5) * cell; ys = ly1 - (np.arange(hpx) + .5) * cell
XX, YY = np.meshgrid(xs, ys)
inland = shapely.contains_xy(land.buffer(6), XX.ravel(), YY.ravel())
q = np.where(inland)[0]
lab = np.full(XX.size, -1, int); lab[q] = R["hex_road"][cKDTree(R["hex_xy"]).query(np.c_[XX.ravel()[q], YY.ravel()[q]])[1]]
lab = lab.reshape(XX.shape); inside = lab >= 0
# blur one mill at a time inside its bounding window and keep the strongest
best = np.full(lab.shape, -1.0); arg = np.full(lab.shape, -1, int); pad = 24
for i in range(n):
    r_, c_ = np.where(lab == i)
    if not len(r_): continue
    a0, a1, b0, b1 = max(r_.min() - pad, 0), min(r_.max() + pad + 1, lab.shape[0]), max(c_.min() - pad, 0), min(c_.max() + pad + 1, lab.shape[1])
    g = gaussian_filter((lab[a0:a1, b0:b1] == i).astype(float), 4)
    win = best[a0:a1, b0:b1]; m = g > win
    win[m] = g[m]; arg[a0:a1, b0:b1][m] = i
arg[~inside] = -1
# a catchment is one piece: detached fragments under 3,000 km2 (not the mill's largest piece) are merged into the surrounding polygon
from scipy import ndimage as ndi
frag = np.zeros(arg.shape, bool)
for i in range(n):
    L, nl = ndi.label(arg == i)
    if nl <= 1: continue
    sizes = ndi.sum(np.ones_like(L), L, range(1, nl + 1)); big = int(np.argmax(sizes)) + 1
    for j in range(1, nl + 1):
        if j != big and sizes[j - 1] * cell * cell < 3000: frag |= (L == j)
if frag.any():
    keep = (arg >= 0) & ~frag; _, (ri, ci) = ndi.distance_transform_edt(~keep, return_indices=True)
    arg = np.where(frag, arg[ri, ci], arg)
print("detached fragments merged: %d pixels (%.0f km2)" % (frag.sum(), frag.sum() * cell * cell))
tr = from_origin(lx0, ly1, cell, cell)
parts = {i: [] for i in range(n)}
for geom, v in features.shapes(arg.astype(np.int32), mask=arg >= 0, transform=tr, connectivity=4): parts[int(v)].append(shape(geom))
cells = []
for i in range(n):
    g = unary_union(parts[i]).simplify(3).buffer(0) if parts[i] else shapely.Polygon()
    cells.append(g.intersection(land))
area = np.array([c.area for c in cells])
print("smoothed: land covered %.1f%% | pixels that changed mill %.1f%%" % (100 * area.sum() / land.area, 100 * (arg != lab)[inside].mean()))
kept = np.array([cells[i].intersection(scells[i]).area / scells[i].area if not cells[i].is_empty else 0 for i in range(n)])
own = [cells[i].buffer(0.01).contains(Point(px[i], py[i])) for i in range(n)]
print("empty polygons:", [df.name[i] for i in range(n) if cells[i].is_empty], "| sites inside their own polygon: %d of %d" % (sum(own), n), [df.name[i] for i in range(n) if not own[i]])
df = df.copy(); df["area_road"] = area; df["dens_road"] = df.supply_road / np.maximum(area, 1) * 1e3; df["share_of_straight_cell_kept"] = kept
# share of land where both versions name the same mill, from the smoothed raster
sl = np.full(lab.shape, -1, int); sl[inside] = cKDTree(np.c_[px, py]).query(np.c_[XX[inside], YY[inside]])[1]
R2 = dict(R); R2["cells"] = cells; R2["df"] = df; R2["share_agree"] = float(((arg == sl) & inside).sum() / inside.sum())
print("agreement after smoothing %.1f%% (before %.1f%%)" % (100 * R2["share_agree"], 100 * R["share_agree"]))
pickle.dump(R2, open("vor_road_s.pkl", "wb")); df.to_csv("vor_road_stats.csv", index=False)
