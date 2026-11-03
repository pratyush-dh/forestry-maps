"""Day 3 static map: Voronoi (Thiessen) catchments of the open U.S. wood mills, coloured by wood supply inside each cell.
Inputs (same folder): vor_cells.pkl + vor_stats.csv (vor_analysis.py), states.pkl, app_data_nat.json (graticule, water labels), package hexes.csv.
Run: python voronoi_map.py <out_basename>      Page: 30 x 20 in (landscape), PNG + vector PDF."""
import json, sys, pickle, textwrap
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle, Polygon as MPoly, PathPatch
from matplotlib.path import Path
from matplotlib.collections import PatchCollection
from shapely.geometry import Polygon, Point
from shapely.ops import polylabel

OUT = sys.argv[1] if len(sys.argv) > 1 else "vor_map"
have = {f.name for f in fm.fontManager.ttflist}
FONT = ["Candara", "Segoe UI", "DejaVu Sans"] if "Candara" in have else ["Segoe UI", "DejaVu Sans"]
plt.rcParams.update({"font.family": FONT, "axes.unicode_minus": False, "pdf.fonttype": 42})
PAGE, WATER, LAND, INK, MUT, LINE, PANEL = "#ffffff", "#e6edf0", "#ffffff", "#1c1c1c", "#4a4a4a", "#d8d8d8", "#ffffff"
ACC, GRAT, WLAB, STATE = "#c2331f", "#7d7d7d", "#4d7a95", "#5b5b5b"
CLS = ["#cfe5a6", "#94cd7e", "#53b06c", "#1f8a57", "#095a3a"]          # sequential, 5 quintile classes

# ------------------------------------------------------------------ data
V = pickle.load(open("vor_cells.pkl", "rb")); cells, land, df = V["cells"], V["land"], V["df"].reset_index(drop=True)
G = json.load(open("app_data_nat.json")); grat = G["grat"]
st = pickle.load(open("states.pkl", "rb"))
ABBR = {1: "AL", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE", 11: "DC", 12: "FL", 13: "GA", 16: "ID", 17: "IL", 18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD", 25: "MA",
        26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV", 33: "NH", 34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC",
        46: "SD", 47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI", 56: "WY"}
n = len(df); tot_supply = df.supply.sum(); tot_area = df.area_km2.sum()
brk = np.round(np.quantile(df.dens, [0, .2, .4, .6, .8, 1]), 1); brk[0] = 0.0; brk[-1] = np.ceil(df.dens.max() * 10) / 10
cls = np.clip(np.searchsorted(brk, df.dens.values, side="right") - 1, 0, 4)
df["cls"] = cls
asz = df.area_km2.max() / df.area_km2.min()
print("breaks", brk, "| class counts", np.bincount(cls), "| area ratio %.0f" % asz)

# ------------------------------------------------------------------ page grid (inches)
W, HT = 36.0, 25.0
X0, MAPW = 1.8, 20.5
xmin, xmax, ymin, ymax = -2420, 2330, -1420, 1640
MAPH = MAPW * (ymax - ymin) / (xmax - xmin)
XR = X0 + MAPW + 1.1; RIGHT = W - .9; RW = RIGHT - XR
RULE_Y = HT - 3.2; MAP_T = RULE_Y - 1.05; MAP_B = MAP_T - MAPH
fig = plt.figure(figsize=(W, HT), facecolor=PAGE)
ov = fig.add_axes([0, 0, 1, 1]); ov.set_xlim(0, W); ov.set_ylim(0, HT); ov.axis("off"); ov.set_zorder(30)
def Rr(x, y, w, h): return [x / W, y / HT, w / W, h / HT]
def T(x, y, s, **k):
    k.setdefault("color", INK); return ov.text(x, y, s, **k)
def halo(c=LAND, w=3.4, al=.85): return [pe.withStroke(linewidth=w, foreground=c, alpha=al)]

T(RIGHT, HT - .75, "DAY 3  /  30 DAYS 30 MAPS  /  POLYGONS", fontsize=30, color=ACC, weight="bold", ha="right", va="center")
T(X0, HT - 1.65, "Nearest mill, mapped: Voronoi catchments of U.S. wood mills", fontsize=76, weight="bold", va="center")
T(X0, HT - 2.6, "Each polygon is the area closer to one mill site than to any other, coloured by the forest wood removed inside it   |   lower 48 states   |   a model, not a traffic count",
  fontsize=31, color=MUT, va="center")
ov.plot([X0, RIGHT], [RULE_Y, RULE_Y], color=INK, lw=2.2)

# ------------------------------------------------------------------ main map
ax = fig.add_axes(Rr(X0, MAP_B, MAPW, MAPH)); ax.set_facecolor(WATER)
for s in ax.spines.values(): s.set_linewidth(1.8); s.set_color(INK); s.set_zorder(60)
ax.set_xticks([]); ax.set_yticks([]); ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_aspect("equal")
KM_PT = (xmax - xmin) / (MAPW * 72)                                    # km per point on the page

def edge_cross(xx, yy, level, axis):
    v = (xx if axis == "x" else yy) - level; i = np.where(np.sign(v[:-1]) * np.sign(v[1:]) < 0)[0]
    if not len(i): return None
    i = i[0]; t = v[i] / (v[i] - v[i + 1]); return xx[i] + t * (xx[i + 1] - xx[i]), yy[i] + t * (yy[i + 1] - yy[i])
lats = list(range(25, 55, 5)); lons = list(range(-125, -60, 5))
for k, g in enumerate(grat):
    g = np.array(g); ax.plot(g[:, 0], g[:, 1], color=GRAT, lw=.9, ls=(0, (2, 3)), zorder=.8)
    if k < len(lats):
        for lvl, ha, dx in ((xmin, "right", -9), (xmax, "left", 9)):
            c = edge_cross(g[:, 0], g[:, 1], lvl, "x")
            if c and ymin < c[1] < ymax: ax.annotate(f"{lats[k]}°N", c, xytext=(dx, 0), textcoords="offset points", ha=ha, va="center", fontsize=22.5, color=MUT, style="italic", annotation_clip=False)
    else:
        lon = lons[k - len(lats)]
        for lvl, va, dy in ((ymin, "top", -7), (ymax, "bottom", 7)):
            c = edge_cross(g[:, 0], g[:, 1], lvl, "y")
            if c and xmin < c[0] < xmax: ax.annotate(f"{abs(lon)}°W", c, xytext=(0, dy), textcoords="offset points", ha="center", va=va, fontsize=22.5, color=MUT, style="italic", annotation_clip=False)

def geoms(g): return list(g.geoms) if g.geom_type in ("MultiPolygon", "GeometryCollection") else [g]
def patch_of(poly):
    ver, cod = [], []
    for ring in [poly.exterior] + list(poly.interiors):
        a = np.array(ring.coords); ver += list(a); cod += [Path.MOVETO] + [Path.LINETO] * (len(a) - 2) + [Path.CLOSEPOLY]
    return PathPatch(Path(ver, cod))
for i, c in enumerate(cells):                                          # the choropleth: one colour per Voronoi cell
    for p in geoms(c):
        if p.geom_type != "Polygon" or p.is_empty: continue
        pp = patch_of(p); pp.set_facecolor(CLS[cls[i]]); pp.set_edgecolor("none"); pp.set_linewidth(0); pp.set_zorder(2); ax.add_patch(pp)
        for ring in [p.exterior] + list(p.interiors):
            r_ = np.array(ring.coords); ax.plot(r_[:, 0], r_[:, 1], color=INK, lw=1.7, alpha=.72, zorder=3, solid_joinstyle="round")
for f, s in st.items():                                                # state lines on top, thin and light
    if f not in ABBR: continue
    for r in s["rings"]:
        r = np.array(r); ax.plot(r[:, 0], r[:, 1], color=STATE, lw=1.0, alpha=.5, zorder=5, solid_joinstyle="round")
for ring in [land.exterior] if land.geom_type == "Polygon" else [p.exterior for p in land.geoms]:   # coastline / border
    r = np.array(ring.coords); ax.plot(r[:, 0], r[:, 1], color=INK, lw=1.2, alpha=.85, zorder=6)

# mills: shape by type, size by wood inside the cell
MK = {"pulp": "o", "sawmill": "^", "osb": "s", "plywood": "D", "mdf": "p", "paper": "*"}
MLAB = {"pulp": "Pulp mill", "sawmill": "Sawmill", "osb": "OSB mill", "plywood": "Plywood mill", "mdf": "MDF mill", "paper": "Paper mill"}
size = lambda v: 52 + 440 * (v / df.supply.max())
for t, mk in MK.items():
    d = df[df.mill_type == t]
    ax.scatter(d.x, d.y, s=size(d.supply) * (2.6 if t == "paper" else 1.0), marker=mk, c=INK, edgecolors="#ffffff", linewidths=1.9, zorder=10)

# ---- label placement: state abbreviations first, then mill names; everything checked against mills and earlier labels
fig.canvas.draw(); rend = fig.canvas.get_renderer()
obst = []                                                                # display-space boxes
def bbox_of(t, pad=3):
    b = t.get_window_extent(rend); return (b.x0 - pad, b.y0 - pad, b.x1 + pad, b.y1 + pad)
def hit(a, b): return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
for i in range(n):
    r_pt = (np.sqrt(size(df.supply[i]) * (2.6 if df.mill_type[i] == "paper" else 1) / np.pi) + 2) * (fig.dpi / 72) * 1.15
    px, py = ax.transData.transform((df.x[i], df.y[i])); obst.append((px - r_pt, py - r_pt, px + r_pt, py + r_pt))
ax_box = ax.get_window_extent(rend)
NE = {"CT", "RI", "NJ", "DE", "MD", "DC", "MA", "NH", "VT"}               # too small to hold a label: leader lines into the Atlantic
placed = []; ne_list = []
for f, s in sorted(st.items(), key=lambda kv: -Polygon(max(kv[1]["rings"], key=lambda r: Polygon(r).area)).area if kv[0] in ABBR else 0):
    if f not in ABBR: continue
    polys = sorted([Polygon(r).buffer(0) for r in s["rings"]], key=lambda p: -p.area); P = polys[0]
    if ABBR[f] in NE: ne_list.append((f, P.representative_point() if P.area < 5000 else polylabel(P, 2))); continue
    cand = [polylabel(P, 2)]
    minx, miny, maxx, maxy = P.bounds
    for gx in np.linspace(minx, maxx, 14):
        for gy in np.linspace(miny, maxy, 14):
            q = Point(gx, gy)
            if P.contains(q) and P.exterior.distance(q) > 12: cand.append(q)
    best = None
    for q in cand:
        tt = ax.text(q.x, q.y, ABBR[f], fontsize=26, weight="bold", color=STATE, ha="center", va="center", zorder=9, alpha=.9, path_effects=halo("#ffffff", 3.4, .75))
        bb = bbox_of(tt); free = not any(hit(bb, o) for o in obst + placed)
        inside = all(P.buffer(-4).contains(Point(*p)) for p in [])  # (kept simple: the candidate point is inside by construction)
        tt.remove()
        if free: best = q; break
    if best is None: best = cand[0]; print("label overlaps something:", ABBR[f])
    tt = ax.text(best.x, best.y, ABBR[f], fontsize=26, weight="bold", color=STATE, ha="center", va="center", zorder=9, alpha=.9, path_effects=halo("#ffffff", 3.4, .75))
    placed.append(bbox_of(tt))
ne_list.sort(key=lambda t: -t[1].y)
LX = 2140; ly = 700
for f, q in ne_list:                                                    # north-east cluster: column of labels in the Atlantic with leader lines
    ax.annotate(ABBR[f], (q.x, q.y), xytext=(LX, ly), textcoords="data", ha="left", va="center", fontsize=25, weight="bold", color=STATE, zorder=9, annotation_clip=False,
                arrowprops=dict(arrowstyle="-", color=STATE, lw=1.1, shrinkA=2, shrinkB=1, alpha=.8), path_effects=halo(WATER, 3.2, .8))
    ly -= 98
# mill names: the eight mills with the most wood inside their cell
top = list(df.sort_values("supply", ascending=False).index[:8])
if df.dens.idxmax() not in top: top.append(df.dens.idxmax())
inv = ax.transData.inverted()
gx_ = np.arange(ax_box.x0 + 10, ax_box.x1 - 10, 12.0); gy_ = np.arange(ax_box.y0 + 10, ax_box.y1 - 10, 12.0)
GX, GY = np.meshgrid(gx_, gy_); GX = GX.ravel(); GY = GY.ravel()
for i in top:
    nm = df.name[i].replace(" (", "\n(") + (", %s" % df.state[i]) + (" (2 mills)" if df.n_mills[i] > 1 else "")
    t0 = ax.text(0, 0, nm, fontsize=24, weight="bold", ha="center", va="center", path_effects=halo("#ffffff", 3.6, .9)); b0 = bbox_of(t0, 9); t0.remove()
    w_, h_ = b0[2] - b0[0], b0[3] - b0[1]
    mx_p, my_p = ax.transData.transform((df.x[i], df.y[i]))
    order = np.argsort(np.hypot(GX - mx_p, GY - my_p)); done = False
    for k in order:
        cx, cy = GX[k], GY[k]
        if np.hypot(cx - mx_p, cy - my_p) < 0.5 * h_ + 10: continue
        bb = (cx - w_ / 2, cy - h_ / 2, cx + w_ / 2, cy + h_ / 2)
        if not (ax_box.x0 + 8 < bb[0] and bb[2] < ax_box.x1 - 8 and ax_box.y0 + 8 < bb[1] and bb[3] < ax_box.y1 - 8): continue
        if any(hit(bb, o) for j, o in enumerate(obst) if True) or any(hit(bb, o) for o in placed): continue
        seg = [(mx_p + (cx - mx_p) * u, my_p + (cy - my_p) * u) for u in np.linspace(.12, 1, 30)]           # leader line must not cross another label
        if any(p[0] > o[0] and p[0] < o[2] and p[1] > o[1] and p[1] < o[3] for p in seg for o in placed): continue
        dxk, dyk = inv.transform((cx, cy))
        near = np.hypot(cx - mx_p, cy - my_p) < w_ / 2 + 30
        ax.annotate(nm, (df.x[i], df.y[i]), xytext=(dxk, dyk), textcoords="data", ha="center", va="center", fontsize=24, weight="bold", color=INK, zorder=12,
                    path_effects=halo("#ffffff", 3.6, .9), arrowprops=dict(arrowstyle="-", color=INK, lw=1.3, shrinkA=2, shrinkB=6) if np.hypot(cx - mx_p, cy - my_p) > 0.5 * h_ + 26 else None)
        placed.append(bb); done = True; break
    if not done: print("NO FREE SLOT for", df.name[i])
for nm, x, y in G["water"]:
    if nm.startswith("Pacific"): x, y = -2130, -800
    if nm.startswith("Atlantic"): x, y = 2050, -560
    ax.text(x, y, "\n".join((p if nm.startswith("Atlantic") else " ".join(p)) for p in nm.split("\n")), fontsize=31.5, style="italic", color=WLAB, ha="center", va="center", linespacing=1.15, zorder=3)
ax.text(*G["mexico"], " ".join("MEXICO"), fontsize=25.5, color=MUT, ha="center", va="center", alpha=.8, zorder=3)
ax.text(-100, 1520, " ".join("CANADA"), fontsize=25.5, color=MUT, ha="center", va="center", alpha=.8, zorder=3)

# scale bar (lower left) + north arrow (lower right), both inside the frame
sx, sy = xmin + 140, ymin + 330
for k, (a, b) in enumerate([(0, 500), (500, 1000)]):
    ax.add_patch(Rectangle((sx + a, sy), b - a, 40, fc=INK if k == 0 else "#ffffff", ec=INK, lw=1.8, zorder=40))
for v in (0, 500, 1000): ax.text(sx + v, sy + 70, f"{v}", fontsize=22, ha="center", va="bottom", color=INK, zorder=40, path_effects=halo(WATER, 3, .8))
ax.text(sx + 1000 + 50, sy + 20, "km", fontsize=22, ha="left", va="center", color=INK, zorder=40)
ax.text(sx, sy - 45, "Albers equal-area projection.\nScale is true along 29.5°N and 45.5°N.", fontsize=19, ha="left", va="top", color=MUT, zorder=40, path_effects=halo(WATER, 3, .8), linespacing=1.2)
nx_, ny_ = xmax - 190, ymin + 140
ax.add_patch(MPoly([[nx_, ny_ + 230], [nx_ - 65, ny_], [nx_, ny_ + 58], [nx_ + 65, ny_]], closed=True, fc=INK, ec=INK, lw=1, zorder=40))
ax.text(nx_, ny_ + 262, "N", fontsize=36, weight="bold", ha="center", va="bottom", color=INK, zorder=40, path_effects=halo(WATER, 3, .8))

# ------------------------------------------------------------------ right column: legend table, mill key, two charts
def wrap(s, w): return textwrap.fill(s, w)
y = MAP_T
T(XR, y, "WOOD SUPPLY INSIDE EACH POLYGON", fontsize=29, weight="bold", color=INK, va="top")
y -= .8
T(XR, y, wrap("Annual FIA forest removals inside the polygon divided by its area, in thousand ft³ per km² per year. Five quintile classes of %d to %d polygons each." % (np.bincount(cls).min(), np.bincount(cls).max()), 100),
  fontsize=21, color=MUT, va="top", linespacing=1.25)
y -= .95
cols = [XR + .05, XR + 1.3, XR + 5.0, XR + 7.3, XR + 9.6]
for c_, s_ in zip(cols[1:], ["Range", "Polygons", "Land area", "Wood"]): T(c_, y, s_, fontsize=21, weight="bold", color=MUT, va="center")
y -= .55
area_sh = np.array([df.area_km2[cls == k].sum() / tot_area for k in range(5)]); sup_sh = np.array([df.supply[cls == k].sum() / tot_supply for k in range(5)])
for k in range(4, -1, -1):
    ov.add_patch(Rectangle((cols[0], y - .27), .9, .54, fc=CLS[k], ec=INK, lw=1.3))
    T(cols[1], y, f"{brk[k]:.1f} to {brk[k + 1]:.1f}", fontsize=24, va="center")
    T(cols[2], y, f"{(cls == k).sum()}", fontsize=24, va="center"); T(cols[3], y, f"{area_sh[k] * 100:.0f}%", fontsize=24, va="center"); T(cols[4], y, f"{sup_sh[k] * 100:.0f}%", fontsize=24, va="center")
    y -= .66
T(XR, y + .08, "Land area and wood are shares of the lower 48 total.", fontsize=20, color=MUT, va="top", style="italic")
y -= .75

T(XR, y, "MILL TYPE AND SIZE", fontsize=29, weight="bold", color=INK, va="top"); y -= .85
cnt = df.mill_type.value_counts()
for k, (t, mk) in enumerate(MK.items()):
    xx = XR + .35 + (k % 3) * 3.95; yy = y - (k // 3) * .62
    ov.scatter([xx], [yy], s=230 * (2.4 if t == "paper" else 1), marker=mk, c=INK, edgecolors="#ffffff", linewidths=1.4)
    T(xx + .42, yy, f"{MLAB[t]} ({cnt[t]})", fontsize=22, va="center")
y -= 2 * .62 + .1
T(XR, y, "Symbol size, M ft³/yr:", fontsize=21, color=MUT, va="center")
for k, v in enumerate((100, 300, 600)):
    xx = XR + 5.6 + k * 2.2
    ov.scatter([xx], [y], s=size(v) * 1.9, marker="o", c=INK, edgecolors="#ffffff", linewidths=1.4); T(xx + .45, y, f"{v}", fontsize=22, va="center")
y -= .5
T(XR, y, wrap("Named on the map: the eight mills with the most wood in their polygon, and the densest polygon.", 104), fontsize=20, color=MUT, va="top", style="italic", linespacing=1.25)
y -= .95

def chart(top_, h, title):
    T(XR, top_, title, fontsize=29, weight="bold", va="top")
    a = fig.add_axes(Rr(XR + 1.7, top_ - .85 - h, RW - 1.95, h)); a.set_facecolor(PANEL)
    for s in a.spines.values(): s.set_color(INK); s.set_linewidth(1.3)
    a.tick_params(labelsize=21, colors=INK, length=5, width=1.2); a.grid(color=LINE, lw=1.0, zorder=0); a.set_axisbelow(True)
    return a
CH = 1.7
a = chart(y, CH, "SIZE OF POLYGON AND WOOD INSIDE")
a.scatter(df.area_km2, df.supply, s=130, c=[CLS[k] for k in cls], edgecolors=INK, linewidths=1.1, zorder=3)
a.set_xscale("log"); a.set_xlabel("Polygon area (km², log scale)", fontsize=22, color=INK); a.set_ylabel("Wood (M ft³/yr)", fontsize=22, color=INK); a.set_ylim(0, 760)
a.set_yticks([0, 200, 400, 600])
T(XR, y - .85 - CH - 1.25, wrap(f"Areas differ {asz:,.0f}-fold, wood only {df.supply.max() / df.supply.min():.0f}-fold, so a small polygon mostly means a dense mill network, not a rich forest.", 104), fontsize=20, color=MUT, va="top", linespacing=1.25)
y2 = y - .85 - CH - 2.3
b = chart(y2, CH, "STRAIGHT LINE AGAINST ROAD")
mx_ = 760
b.plot([0, mx_], [0, mx_], color=ACC, lw=2.0, zorder=2); b.scatter(df.supply, df.alloc, s=110, c="#8f8468", edgecolors=INK, linewidths=1.0, zorder=3, alpha=.9)
b.set_xlim(0, mx_); b.set_ylim(0, 400); b.set_yticks([0, 200, 400]); b.set_xlabel("Wood inside the polygon (M ft³/yr)", fontsize=22, color=INK); b.set_ylabel("By road (M ft³/yr)", fontsize=22, color=INK)
b.text(740, 330, "red line: road equals polygon", fontsize=20, color=ACC, ha="right", va="center")
nbelow = int((df.alloc < df.supply).sum()); nabove = int((df.alloc > df.supply).sum())
T(XR, y2 - .85 - CH - 1.25, wrap(f"{nbelow} mills receive less by road than their polygon holds and {nabove} receive more. Road time within 120 minutes, not straight distance, decides who gets the wood.", 104),
  fontsize=20, color=MUT, va="top", linespacing=1.25)

# ------------------------------------------------------------------ notes under the map (full sentences)
nt = MAP_B - 1.15
CW = 9.9
T(X0, nt, "HOW TO READ THIS MAP", fontsize=29, weight="bold", va="top")
read = ("A Voronoi polygon holds every point that is nearer to its mill than to any other mill, so the map answers one question: which mill is closest in a straight line? "
        "Every mill has a polygon. Where mills are few, one polygon covers a whole region; the single California mill owns most of the Southwest. "
        "Colour is the wood removed from forests inside the polygon per square kilometre, and symbol size is the same wood as a total. "
        "Dark polygons are heavily harvested, and pale ones are lightly harvested or very large.")
T(X0, nt - .75, wrap(read, 64), fontsize=22, va="top", linespacing=1.32)
T(X0 + CW + .8, nt, "LIMITATIONS", fontsize=29, weight="bold", va="top")
lim = ("Trucks follow roads, so a mill's real catchment differs from its polygon; the Day 2 web map shows road time. "
       "Wood is cut in forests only, so a polygon's colour is an average over all of its land. "
       "The 117 mills are a sample of open mills, so large western polygons show missing mills as much as empty forest. "
       "Removals are county totals shared evenly among forest hexes and include land clearing. "
       "Two Camas, Washington, mills share one point and therefore one polygon.")
T(X0 + CW + .8, nt - .75, wrap(lim, 64), fontsize=22, va="top", linespacing=1.32)
T(X0, .8, wrap("Data: USDA Forest Service FIA annual removals by county (hexes of 842 km²); 117 open wood mills in a working sample; Natural Earth states. Polygons built from mill points in spherical Albers and clipped to the lower 48.", 125),
  fontsize=20, color=MUT, va="center", linespacing=1.3)

# ------------------------------------------------------------------ checks, export
fig.canvas.draw(); rend = fig.canvas.get_renderer(); ab = ax.get_window_extent(rend); bad = []
for t in ax.texts:
    bb = t.get_window_extent(rend)
    if t.get_text() and not (ab.x0 - 80 < bb.x0 and bb.x1 < ab.x1 + 80): bad.append(t.get_text())
fb = fig.bbox
for t in ov.texts:
    bb = t.get_window_extent(rend)
    if not (fb.x0 <= bb.x0 and bb.x1 <= fb.x1 and fb.y0 <= bb.y0 and bb.y1 <= fb.y1): bad.append("PAGE:" + t.get_text()[:40])
for t in ov.texts:                                         # nothing in the right column may run past the right margin, nothing under the map may touch the footer
    bb = t.get_window_extent(rend); xr_ = fb.x1 * (RIGHT + .1) / W
    if bb.x0 > fb.x1 * XR / W - 2 and bb.x1 > xr_: bad.append("RIGHT:" + t.get_text()[:40])
print("labels crossing the frame / page / right margin:", bad)
fig.savefig(OUT + ".png", dpi=125, facecolor=PAGE); fig.savefig(OUT + ".pdf", facecolor=PAGE)
print("saved", OUT)
