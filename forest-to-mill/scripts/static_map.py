"""Static map v5: the main map first, one key chart. Same data and model as the web app (NLCD canopy underlay,
removals placed by canopy, spread 15 min, cap 120 min). Layout is in inches on a 26 x 17.6 in page.
Inputs: ../data/map_data.json, ../data/states_albers_km.json.   Run from this folder: python static_map.py <paper|night> <out_basename> [canopy|nocanopy]"""
import json, sys, io, base64, textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle, Polygon as MPoly
from PIL import Image

THEME = sys.argv[1] if len(sys.argv) > 1 else "paper"
OUT = sys.argv[2] if len(sys.argv) > 2 else "map"
CANOPY = (sys.argv[3] if len(sys.argv) > 3 else "canopy") == "canopy"
have = {f.name for f in fm.fontManager.ttflist}
FONT = ["Candara", "Segoe UI", "DejaVu Sans"] if "Candara" in have else ["Segoe UI", "DejaVu Sans"]
plt.rcParams.update({"font.family": FONT, "axes.unicode_minus": False, "pdf.fonttype": 42})

PAL = {
 "paper": dict(page="#f6f2e8", water="#e4e9e8", land="#f9f6ec", study="#fcfaf2", ink="#23201a", mut="#5f5a4c", line="#d9d1bd", panel="#fffdf7",
   stS="#4a4434", stO="#b9b19a", road="#8f8468", traf="#c2331f", halo="#f9f6ec", mill="#23201a", grat="#8c8573", wlab="#58809a", nbr="#8f876f",
   tagtxt="#ffffff", acc="#c2331f", can=(78, 128, 92), can_a=.48, t=["#d9d9d9", "#a3a3a3", "#5e5e5e", "#111111"], none="#efeadb"),
 "night": dict(page="#0c0c0c", water="#000000", land="#0b0b0b", study="#141414", ink="#ecece8", mut="#a0a0a0", line="#2a2a2a", panel="#101010",
   stS="#a6a6a6", stO="#303030", road="#5c5c5c", traf="#ffa21a", halo="#000000", mill="#ffffff", grat="#3a3a3a", wlab="#6f93a8", nbr="#7a7a7a",
   tagtxt="#1a1000", acc="#ffa21a", can=(118, 158, 124), can_a=.66, t=["#4a4a4a", "#7e7e7e", "#b4b4b4", "#f0f0f0"], none="#1d1d1d"),
}[THEME]
INK, MUT = PAL["ink"], PAL["mut"]

# ------------------------------------------------------------------ data + model (identical to the web app)
D = json.load(open("../data/map_data.json"))
N = D["n"]; raw = base64.b64decode(D["e"])
EC = np.frombuffer(raw[:N * 8], dtype=np.int16).reshape(N, 4) / 10.0       # km: x1,y1,x2,y2
ECLS = np.frombuffer(raw[N * 8:], dtype=np.uint8)
HX = [dict(id=r[0], x=r[1], y=r[2], st=r[4], ff=r[6], forest=bool(r[8]), routes=r[9], rem=(r[11] or 0.0)) for r in D["hexes"]]
M = [dict(name=m[2], st=m[4], type=m[5], x=m[6], y=m[7]) for m in D["mills"]]
mIdx = {m[0]: i for i, m in enumerate(D["mills"])}
NAMES = {40: "Oklahoma", 48: "Texas", 5: "Arkansas", 22: "Louisiana", 28: "Mississippi", 1: "Alabama", 47: "Tennessee", 21: "Kentucky",
         13: "Georgia", 12: "Florida", 45: "South Carolina", 37: "North Carolina", 51: "Virginia"}
CAP, SPREAD, REF = 120, 15.0, 270.0
load = np.zeros(N); mload = np.zeros(len(M))
for h in HX:
    if not h["rem"]: continue
    rs = [r for r in h["routes"] if r[1] <= CAP]
    if not rs: continue
    t0 = rs[0][1]; w = np.array([np.exp(-(r[1] - t0) / SPREAD) for r in rs]); w /= w.sum()
    for r, f in zip(rs, w):
        mload[mIdx[r[0]]] += h["rem"] * f
        for i in r[4]: load[i] += h["rem"] * f
F = [h for h in HX if h["forest"]]
tot = sum(h["rem"] for h in F)
def nclass(h):
    rs = [r for r in h["routes"] if r[1] <= CAP]
    return min(int(rs[0][1] // 30), 3) if rs else 4
reached = sum(h["rem"] for h in F if nclass(h) < 4)
ts = sorted((h["routes"][0][1], h["rem"]) for h in F if h["routes"] and h["routes"][0][1] <= CAP)
c_ = 0; med = 0
for t, v in ts:
    c_ += v
    if c_ >= reached / 2: med = t; break
n_recv = int((mload > 0).sum())

# ------------------------------------------------------------------ page grid (inches)
W, HT = 26.0, 17.6
X0, MAPW = 1.9, 16.5                 # alignment line 1: map frame, title, legend, footer
XR = X0 + MAPW + .8                  # alignment line 2: right column
RIGHT = W - .9; RW = RIGHT - XR
xmin, xmax, ymin, ymax = -1060, 1865, -1385, 405
MAPH = MAPW * (ymax - ymin) / (xmax - xmin)
RULE_Y = HT - 2.2; MAP_T = RULE_Y - .95; MAP_B = MAP_T - MAPH
fig = plt.figure(figsize=(W, HT), facecolor=PAL["page"])
ov = fig.add_axes([0, 0, 1, 1]); ov.set_xlim(0, W); ov.set_ylim(0, HT); ov.axis("off"); ov.set_zorder(30)
def Rr(x, y, w, h): return [x / W, y / HT, w / W, h / HT]
def T(x, y, s, **k):
    k.setdefault("color", INK); return ov.text(x, y, s, **k)

T(X0, HT - 1.05, "Forest to mill: where wood moves in the southern United States", fontsize=52, weight="bold", va="center")
T(X0, HT - 1.78, "Modelled hauling of FIA annual forest removals to wood mills by road   |   13 states, Oklahoma and Texas to Virginia   |   a model, not a traffic count",
  fontsize=21, color=MUT, va="center")
T(RIGHT, HT - 1.05, "DAY 2  /  30 DAYS 30 MAPS", fontsize=20, color=PAL["acc"], weight="bold", ha="right", va="center")
ov.plot([X0, RIGHT], [RULE_Y, RULE_Y], color=INK, lw=1.6)

# ------------------------------------------------------------------ main map
ax = fig.add_axes(Rr(X0, MAP_B, MAPW, MAPH))
ax.set_facecolor(PAL["water"])
for s in ax.spines.values(): s.set_linewidth(1.6); s.set_color(INK); s.set_zorder(50)
ax.set_xticks([]); ax.set_yticks([])

def edge_cross(xx, yy, level, axis):
    v = (xx if axis == "x" else yy) - level
    i = np.where(np.sign(v[:-1]) * np.sign(v[1:]) < 0)[0]
    if not len(i): return None
    i = i[0]; t = v[i] / (v[i] - v[i + 1]); return xx[i] + t * (xx[i + 1] - xx[i]), yy[i] + t * (yy[i + 1] - yy[i])
GL = 14.3
lats = list(range(25, 50, 5)); lons = list(range(-110, -65, 5))
for k, g in enumerate(D["grat"]):
    g = np.array(g); ax.plot(g[:, 0], g[:, 1], color=PAL["grat"], lw=.8, ls=(0, (2, 3)), zorder=.8)      # graticule sits BELOW the land
    if k < len(lats):
        for lvl, ha, dx in ((xmin, "right", -9), (xmax, "left", 9)):
            c = edge_cross(g[:, 0], g[:, 1], lvl, "x")
            if c and ymin < c[1] < ymax: ax.annotate(f"{lats[k]}°N", c, xytext=(dx, 0), textcoords="offset points", ha=ha, va="center", fontsize=GL, color=MUT, style="italic", annotation_clip=False)
    else:
        lon = lons[k - len(lats)]
        for lvl, va, dy in ((ymin, "top", -7), (ymax, "bottom", 7)):
            c = edge_cross(g[:, 0], g[:, 1], lvl, "y")
            if c and xmin < c[0] < xmax: ax.annotate(f"{abs(lon)}°W", c, xytext=(0, dy), textcoords="offset points", ha="center", va=va, fontsize=GL, color=MUT, style="italic", annotation_clip=False)

for s in D["states"]:
    for r in s[3]:
        ax.add_patch(MPoly(np.array(r), closed=True, fc=PAL["study"] if s[2] else PAL["land"], ec="none", alpha=.95, zorder=1))

if CANOPY:                                            # NLCD tree canopy cover, 2 km mean of 30 m pixels
    cn = D["can"]; v = np.asarray(Image.open(io.BytesIO(base64.b64decode(cn["png"]))).convert("L")) / 255.0
    rgba = np.zeros(v.shape + (4,)); rgba[..., 0], rgba[..., 1], rgba[..., 2] = [c / 255 for c in PAL["can"]]
    rgba[..., 3] = np.clip(v, 0, 1) ** .9 * PAL["can_a"]
    ax.imshow(rgba, extent=[cn["x0"], cn["x0"] + cn["w"] * cn["cell"], cn["y1"] - cn["h"] * cn["cell"], cn["y1"]], origin="upper", interpolation="bilinear", zorder=2, aspect="auto")
ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_aspect("equal")

for s in D["states"]:
    for r in s[3]:
        r = np.array(r); ax.plot(r[:, 0], r[:, 1], color=PAL["stS"] if s[2] else PAL["stO"], lw=1.9 if s[2] else .9, zorder=5, solid_joinstyle="round")
segs = np.stack([EC[:, :2], EC[:, 2:]], axis=1)
wcls = np.array([.95, .7, .85, .7, .4]) * (1.0 if CANOPY else 1.45)
ax.add_collection(LineCollection(segs, colors=PAL["road"], linewidths=wcls[ECLS], zorder=6, capstyle="round"))
idx = np.where(load >= .5)[0]; idx = idx[np.argsort(load[idx])]
wid = lambda l: (0.35 + 3.7 * np.sqrt(l / REF)) * 1.25
ax.add_collection(LineCollection(segs[idx], colors=PAL["halo"], linewidths=wid(load[idx]) + 1.7, zorder=7, capstyle="round", alpha=.9))
ax.add_collection(LineCollection(segs[idx], colors=PAL["traf"], linewidths=wid(load[idx]), zorder=8, capstyle="round"))

mx = np.array([m["x"] for m in M]); my = np.array([m["y"] for m in M])
ax.scatter(mx, my, s=62, c=PAL["mill"], edgecolors=PAL["halo"], linewidths=1.3, zorder=10)
def spaced(s): return " ".join(s)
def halo_of(c, w=3.2, al=.85): return [pe.withStroke(linewidth=w, foreground=c, alpha=al)]
for j in np.argsort(-mload)[:8]:
    ax.annotate(M[j]["name"].replace(" (", "\n("), (mx[j], my[j]), xytext=(9, 7), textcoords="offset points", fontsize=14.3, color=INK, weight="bold", zorder=11, path_effects=halo_of(PAL["halo"]))
for nm, ab, x, y in D["sl"]:
    ax.text(x, y, spaced(nm.upper()), fontsize=17.5 if len(nm) <= 9 else 14.5, color=PAL["stS"], ha="center", va="center", alpha=.88, weight="bold", zorder=9.5, path_effects=halo_of(PAL["study"]))
for nm, x, y in D["nbr"]:
    if (x < -100 and y > 40) or not (xmin + 110 < x < xmax - 110 and ymin + 80 < y < ymax - 80): continue   # label key sits top-left; keep labels inside the frame
    ax.text(x, y, nm, fontsize=13.5, style="italic", color=PAL["nbr"], ha="center", va="center", zorder=4.2, clip_on=True, path_effects=halo_of(PAL["land"], 2.6, .8))
ax.text(*D["mexico"], spaced("MEXICO"), fontsize=15, color=PAL["nbr"], ha="center", va="center", zorder=4.2)
for nm, x, y in D["water"]:
    ax.text(x, y, "\n".join(spaced(p) for p in nm.split("\n")), fontsize=19.5, style="italic", color=PAL["wlab"], ha="center", linespacing=1.15)
picked = []
for i in np.argsort(-load):
    if load[i] < 60 or len(picked) >= 7: break
    xm, ym = (EC[i, 0] + EC[i, 2]) / 2, (EC[i, 1] + EC[i, 3]) / 2
    if all(np.hypot(xm - a, ym - b) > 230 for a, b, _ in picked): picked.append((xm, ym, load[i]))
for x_, y_, l_ in picked:
    ax.annotate(f"{l_:.0f}", (x_, y_), ha="center", va="center", fontsize=12.5, weight="bold", color=PAL["tagtxt"], zorder=11,
                bbox=dict(boxstyle="round,pad=.22,rounding_size=.6", fc=PAL["traf"], ec=PAL["halo"], lw=1.3))
# label-type key (top-left of the frame)
kx0, ky0, kw, kh = -1035, 392, 900, 330
ax.add_patch(Rectangle((kx0, ky0 - kh), kw, kh, fc=PAL["panel"], ec=INK, lw=1, alpha=.96, zorder=13))
ax.text(kx0 + 28, ky0 - 32, "LABEL TYPES", fontsize=13, weight="bold", color=MUT, va="center", zorder=14)
def krow(k, fn, desc):
    y_ = ky0 - 92 - k * 47; fn(kx0 + 28, y_); ax.text(kx0 + 420, y_, desc, fontsize=12.5, color=INK, va="center", zorder=14)
krow(0, lambda x, y: ax.text(x, y, spaced("OKLAHOMA"), fontsize=14, weight="bold", color=PAL["stS"], va="center", zorder=14), "Study state")
krow(1, lambda x, y: ax.text(x, y, "Missouri", fontsize=13.5, style="italic", color=PAL["nbr"], va="center", zorder=14), "Neighbouring state")
krow(2, lambda x, y: ax.text(x, y, spaced("Gulf of America"), fontsize=13, style="italic", color=PAL["wlab"], va="center", zorder=14), "Water body")
krow(3, lambda x, y: ax.text(x, y, "Macon", fontsize=14.3, weight="bold", color=INK, va="center", zorder=14), "Mill (eight largest receivers)")
krow(4, lambda x, y: ax.text(x + 55, y, "257", fontsize=12.5, weight="bold", color=PAL["tagtxt"], ha="center", va="center", zorder=14,
     bbox=dict(boxstyle="round,pad=.22,rounding_size=.6", fc=PAL["traf"], ec=PAL["halo"], lw=1.3)), "Busiest road segments, M ft³/yr")
# scale bar + north arrow
sx0, sy0, bh = -1010, -1170, 24
for i in range(5): ax.add_patch(Rectangle((sx0 + i * 100, sy0), 100, bh, fc=INK if i % 2 == 0 else PAL["land"], ec=INK, lw=1, zorder=12))
for i in range(6): ax.annotate(f"{i * 100}", (sx0 + i * 100, sy0 + bh), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=14.3, color=INK, zorder=12)
ax.annotate("km", (sx0 + 500, sy0 + bh), xytext=(22, 4), textcoords="offset points", fontsize=14.3, color=INK, va="bottom", zorder=12)
mi = 160.934
for i in range(4): ax.add_patch(Rectangle((sx0 + i * mi, sy0 - bh - 30), mi, bh, fc=INK if i % 2 == 0 else PAL["land"], ec=INK, lw=1, zorder=12))
for i in range(5): ax.annotate(f"{i * 100}", (sx0 + i * mi, sy0 - bh - 30), xytext=(0, -4), textcoords="offset points", ha="center", va="top", fontsize=14.3, color=INK, zorder=12)
ax.annotate("mi", (sx0 + 4 * mi, sy0 - bh - 30), xytext=(22, -4), textcoords="offset points", fontsize=14.3, color=INK, va="top", zorder=12)
ax.annotate("Albers equal-area; scale varies ±1.5% across the sheet", (sx0, sy0 - bh - 30), xytext=(0, -30), textcoords="offset points", fontsize=12.3, color=MUT, va="top", zorder=12)
nx0, ny0 = 1790, -820
ax.add_patch(MPoly([[nx0, ny0 + 120], [nx0 - 30, ny0 - 10], [nx0, ny0 + 15], [nx0 + 30, ny0 - 10]], fc=INK, ec=INK, zorder=12))
ax.annotate("N", (nx0, ny0 + 120), xytext=(0, 5), textcoords="offset points", fontsize=24.7, weight="bold", ha="center", va="bottom", color=INK, zorder=12)
ax.annotate("true north at 96°W;\nmeridians converge", (nx0, ny0 - 10), xytext=(0, -6), textcoords="offset points", fontsize=12.3, ha="center", va="top", color=MUT, zorder=12)

# ------------------------------------------------------------------ right column: locator, key figures, ONE chart, notes
LH, LW = 2.4, 3.9
loc = fig.add_axes(Rr(XR, MAP_T - LH, LW, LH), facecolor=PAL["water"])
for f, s in ((int(k), v) for k, v in json.load(open("../data/states_albers_km.json")).items()):
    if f in (2, 15) or f > 56: continue
    for r in s["rings"]:
        loc.add_patch(MPoly(r, closed=True, fc=(PAL["acc"] if f in NAMES else PAL["land"]), ec=PAL["stS"], lw=.4, alpha=.9 if f in NAMES else 1))
loc.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, fc="none", ec=INK, lw=2.2))
loc.set_xlim(-2700, 2500); loc.set_ylim(-1480, 1640); loc.set_aspect("equal"); loc.set_xticks([]); loc.set_yticks([])
for s in loc.spines.values(): s.set_color(INK); s.set_linewidth(1)
T(XR + LW + .3, MAP_T - .05, "STUDY AREA", fontsize=13, weight="bold", color=MUT, va="top")
T(XR + LW + .3, MAP_T - .45, "Thirteen states from\nOklahoma and Texas\nto Virginia, shown in\ncolour. The box is the\nmap extent.", fontsize=12.5, va="top", linespacing=1.3)
figs = [(f"{tot/1000:.1f} bn", "ft³/yr of FIA\nremovals"), (f"{reached/tot*100:.0f}%", "within a 2 h\nhaul of a mill"),
        (f"{med:.0f} min", "median haul to\nnearest mill"), (f"{n_recv}", "mills receiving\nwood")]
FY = MAP_T - LH - .55
for i, (big, small) in enumerate(figs):
    x = XR + i * (RW / 4)
    T(x, FY, big, fontsize=28, weight="bold", color=PAL["acc"], va="center")
    T(x, FY - .4, small, fontsize=11.5, va="top", linespacing=1.2)

# the one key chart: how far is each state's wood from a mill
CT = FY - 1.55
sd = {}
for h in F: sd.setdefault(h["st"], [0, 0, 0, 0, 0])[nclass(h)] += h["rem"]
order_s = sorted(sd, key=lambda s: sum(sd[s]))
AXL = 2.1
ch_h = .22 * len(order_s)
a = fig.add_axes(Rr(XR + AXL, CT - ch_h - .55, RW - AXL - .15, ch_h), facecolor=PAL["panel"])
for s in ("top", "right"): a.spines[s].set_visible(False)
for s in ("left", "bottom"): a.spines[s].set_color(MUT); a.spines[s].set_linewidth(.9)
a.tick_params(colors=MUT, labelsize=13, length=4); a.set_axisbelow(True)
cols = PAL["t"] + [PAL["none"]]
for yi, s in enumerate(order_s):
    left = 0
    for ci in range(5):
        a.barh(yi, sd[s][ci], left=left, color=cols[ci], edgecolor=PAL["panel"], linewidth=.5, height=.76); left += sd[s][ci]
    a.text(left + 30, yi, f"{(1 - sd[s][4] / sum(sd[s])) * 100:.0f}%", va="center", fontsize=12.5, color=INK)
a.set_yticks(range(len(order_s))); a.set_yticklabels([NAMES[s] for s in order_s], fontsize=12.5, color=INK)
a.set_xlim(0, max(sum(v) for v in sd.values()) * 1.2); a.grid(axis="x", color=PAL["line"], lw=.6)
T(XR, CT, "How far is each state's wood from a mill?", fontsize=22, weight="bold", va="bottom")
T(XR, CT - .12, "FIA removals by minutes to the nearest sample mill, million ft³ a year.\nLabel = share of the state's removals within a 2 h haul of any mill.", fontsize=12.5, color=MUT, va="top", linespacing=1.25)
a.legend([plt.Rectangle((0, 0), 1, 1, fc=c, ec=PAL["panel"]) for c in cols], ["0–30 min", "30–60", "60–90", "90–120", "no mill in reach"], ncol=5, labelcolor=INK, fontsize=12.5,
         frameon=False, loc="upper left", bbox_to_anchor=(-.62, -.1), columnspacing=.9, handlelength=1, handletextpad=.35)
NY = CT - ch_h - 1.8
notes = [("HOW TO READ IT", "Each forest hex (842 km²) sends its FIA removals to every mill within a 2 h road haul, weighted by travel time: a mill 15 minutes farther than the nearest receives about 37% of its share. Road thickness is the wood summed over every route crossing a segment; each haul counts once."),
         ("FOREST AND CANOPY", "The underlay is USFS NLCD tree canopy cover for 2021 (percent of each 30 m pixel under tree crowns, averaged to 2 km). It is satellite-modelled and is not the FIA definition of forest. FIA gives county totals only, so each county's removals are placed in proportion to canopy; county totals are unchanged.")]
for h_, t_ in notes:
    T(XR, NY, h_, fontsize=15, weight="bold", color=MUT, va="top")
    T(XR, NY - .42, "\n".join(textwrap.wrap(t_, 74)), fontsize=12.8, va="top", linespacing=1.3)
    NY -= 1.75

# ------------------------------------------------------------------ under the map: legend strip + cautions
ZT = MAP_B - .95
T(X0, ZT, "LEGEND", fontsize=15, weight="bold", color=MUT, va="top")
T(X0, ZT - .45, "Road traffic, million ft³/yr", fontsize=15, weight="bold", va="top")
for i, v in enumerate([1, 10, 50, 150, 250]):
    x = X0 + i * .95
    ov.plot([x, x + .6], [ZT - 1.15] * 2, color=PAL["traf"], lw=wid(v), solid_capstyle="round"); T(x + .3, ZT - 1.42, f"{v}", fontsize=14, ha="center", va="top")
CX = X0 + 5.5
T(CX, ZT - .45, "Tree canopy cover", fontsize=15, weight="bold", va="top")
if CANOPY:
    gax = fig.add_axes(Rr(CX, ZT - 1.25, 2.6, .32)); g = np.linspace(0, 1, 256)[None, :]
    gr = np.zeros((1, 256, 4)); gr[..., 0], gr[..., 1], gr[..., 2] = [c / 255 for c in PAL["can"]]; gr[..., 3] = g ** .9 * PAL["can_a"]
    gax.set_facecolor(PAL["study"]); gax.imshow(gr, aspect="auto", extent=[0, 100, 0, 1]); gax.set_yticks([]); gax.set_xticks([0, 50, 100]); gax.set_xticklabels(["0%", "50%", "100%"])
    gax.tick_params(colors=INK, labelsize=13, length=3)
    for sp in gax.spines.values(): sp.set_color(INK); sp.set_linewidth(.8)
    T(CX, ZT - 1.8, "NLCD 2021, 2 km mean", fontsize=12.5, color=MUT, va="top")
else:
    T(CX, ZT - 1.0, "not shown in this version", fontsize=13, color=MUT, va="top")
SX = X0 + 8.7
ov.scatter([SX + .1], [ZT - .6], s=80, c=PAL["mill"], edgecolors=PAL["halo"], linewidths=1.3); T(SX + .35, ZT - .6, "Sample mill, no closure recorded", fontsize=14, va="center")
ov.plot([SX, SX + .22], [ZT - 1.1] * 2, color=PAL["road"], lw=2); T(SX + .35, ZT - 1.1, "Other roads (Natural Earth 1:10m)", fontsize=14, va="center")
ov.plot([SX, SX + .22], [ZT - 1.6] * 2, color=PAL["grat"], lw=1.2, ls=(0, (2, 3))); T(SX + .35, ZT - 1.6, "5° graticule (beneath the land)", fontsize=14, va="center")
BX = X0 + 12.3
T(BX, ZT, "BEFORE CITING", fontsize=15, weight="bold", color=MUT, va="top")
T(BX, ZT - .45, "\n".join(textwrap.wrap("Mills are a 117-mill sample, so empty areas (Texas, Oklahoma, Kentucky) show missing mills as much as distance. Major roads only; speeds and circuity are assumed; mill capacity is ignored.", 56)),
  fontsize=12.8, va="top", linespacing=1.3)
ov.plot([X0, RIGHT], [1.15, 1.15], color=INK, lw=.9)
src = ("Data: USDA Forest Service FIA county estimates (annual removals, forest area; 2016-2025 evaluations); USFS NLCD Tree Canopy Cover v2025-6 (2021); Natural Earth 1:10m roads; "
       "US Census state and county boundaries via us-atlas; author-compiled mill list (Forisk / PPRC 2025, company announcements, trade press).  Projection: spherical Albers equal-area conic "
       "(standard parallels 29.5°N and 45.5°N, origin 37.5°N 96°W, R = 6,371,008.8 m).")
T(X0, .95, "\n".join(textwrap.wrap(src, 215)), fontsize=13, color=MUT, va="top", linespacing=1.3)
fig.savefig(f"{OUT}.png", dpi=170, facecolor=PAL["page"]); fig.savefig(f"{OUT}.pdf", facecolor=PAL["page"])
print("saved", OUT, "| top segment", round(load.max()), "| median", med, "| reached", round(reached / tot * 100, 1), "| mills", n_recv)
