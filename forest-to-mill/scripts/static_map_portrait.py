"""Forest to mill: portrait static map, 4:5, 24 x 30 in, all text 1.5x the landscape sheet. Inputs: ../data/map_data.json, ../data/states_albers_km.json.
Run from this folder: python static_map_portrait.py <out_basename> [dpi]   (dpi 100 = 2400 x 3000 px; 150 = 3600 x 4500 px)
Aborts if any label crosses the map frame."""
import json, sys, io, base64, textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle, Polygon as MPoly
from matplotlib.transforms import Bbox
from shapely.geometry import Polygon as SPoly, Point as SPt, box as sbox
from shapely.ops import unary_union
from PIL import Image

OUT = sys.argv[1] if len(sys.argv) > 1 else "p45"
DPI = int(sys.argv[2]) if len(sys.argv) > 2 else 100
have = {f.name for f in fm.fontManager.ttflist}
plt.rcParams.update({"font.family": ["Candara", "Segoe UI", "DejaVu Sans"] if "Candara" in have else ["Segoe UI", "DejaVu Sans"], "axes.unicode_minus": False})
NL = chr(10)

P = dict(page="#ffffff", water="#e4e9e8", land="#f9f6ec", study="#fcfaf2", ink="#23201a", mut="#5f5a4c", line="#d9d1bd", road="#8f8468",
         bnd="#857d66", bnd_a=.5, bnd_o="#b3ab94", traf="#c2331f", halo="#f9f6ec", mill="#23201a", grat="#9d957f", wlab="#4f7a96", nbr="#8f876f",
         tagtxt="#ffffff", acc="#c2331f", can=(78, 128, 92), can_a=.48, t=["#d9d9d9", "#a3a3a3", "#5e5e5e", "#111111"], none="#efeadb")
INK, MUT = P["ink"], P["mut"]

# ------------------------------------------------------------------ data + model (identical to the poster and the web map)
D = json.load(open("../data/map_data.json")); N = D["n"]; raw = base64.b64decode(D["e"])
EC = np.frombuffer(raw[:N * 8], dtype=np.int16).reshape(N, 4) / 10.0
ECLS = np.frombuffer(raw[N * 8:], dtype=np.uint8)
HX = [dict(st=r[4], forest=bool(r[8]), routes=r[9], rem=(r[11] or 0.0)) for r in D["hexes"]]
M = [dict(name=m[2], type=m[5], x=m[6], y=m[7], nx=m[8], ny=m[9]) for m in D["mills"]]
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
F = [h for h in HX if h["forest"]]; tot = sum(h["rem"] for h in F)
def nclass(h):
    rs = [r for r in h["routes"] if r[1] <= CAP]
    return min(int(rs[0][1] // 30), 3) if rs else 4
reached = sum(h["rem"] for h in F if nclass(h) < 4); n_recv = int((mload > 0).sum())
wk = load * np.hypot(EC[:, 2] - EC[:, 0], EC[:, 3] - EC[:, 1]); w_ = np.sort(wk[wk > 0])[::-1]; cs = np.cumsum(w_) / w_.sum()
top10 = cs[int(round(len(w_) * .10)) - 1]
assert .45 < top10 < .55, top10             # the headline "half ... on 10% of segments" is only printed if this holds

# ------------------------------------------------------------------ page (inches): 16 x 20
W, HT = 16.0, 20.0
PHYS = 1.5
fig = plt.figure(figsize=(W * PHYS, HT * PHYS), facecolor=P["page"])
ov = fig.add_axes([0, 0, 1, 1]); ov.set_xlim(0, W); ov.set_ylim(0, HT); ov.axis("off"); ov.set_zorder(30)
def R(x, y, w, h): return [x / W, y / HT, w / W, h / HT]
def T(x, y, s, **k):
    k.setdefault("color", INK); return ov.text(x, y, s, **k)
X0, MW = 1.0, 14.0
xmin, xmax, ymin, ymax = -1060, 1865, -1385, 405
MH = MW * (ymax - ymin) / (xmax - xmin)
MAP_T = 17.3; MAP_B = MAP_T - MH

T(W / 2, 19.5, "30 DAYS 30 MAPS  ·  DAY 2  ·  LINES", fontsize=28.5, weight="bold", color=P["acc"], va="center", ha="center")
T(W / 2, 18.85, "Forest to mill", fontsize=93.0, weight="bold", va="center", ha="center")
T(W / 2, 18.02, "Half of the modelled wood movement runs on just" + NL + "10% of the road segments that carry any wood.", fontsize=36.0, color=MUT, va="center", ha="center", multialignment="center", linespacing=1.18)

# ------------------------------------------------------------------ main map
ax = fig.add_axes(R(X0, MAP_B, MW, MH)); ax.set_facecolor(P["water"])
for s in ax.spines.values(): s.set_linewidth(1.8); s.set_color(INK); s.set_zorder(50)
ax.set_xticks([]); ax.set_yticks([])
ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_aspect("equal")
def edge_cross(xx, yy, level, axis):
    v = (xx if axis == "x" else yy) - level
    i = np.where(np.sign(v[:-1]) * np.sign(v[1:]) < 0)[0]
    if not len(i): return None
    i = i[0]; t = v[i] / (v[i] - v[i + 1]); return xx[i] + t * (xx[i + 1] - xx[i]), yy[i] + t * (yy[i + 1] - yy[i])
lats = list(range(25, 50, 5)); lons = list(range(-110, -65, 5)); GL = 19.5
for k, g in enumerate(D["grat"]):                                   # 5-degree graticule, drawn beneath the land, labelled on all four edges
    g = np.array(g); ax.plot(g[:, 0], g[:, 1], color=P["grat"], lw=.9, ls=(0, (2, 3)), zorder=.8)
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
    for r in s[3]: ax.add_patch(MPoly(np.array(r), closed=True, fc=P["study"] if s[2] else P["land"], ec="none", alpha=.88, zorder=1))
cn = D["can"]; v = np.asarray(Image.open(io.BytesIO(base64.b64decode(cn["png"]))).convert("L")) / 255.0
rgba = np.zeros(v.shape + (4,)); rgba[..., 0], rgba[..., 1], rgba[..., 2] = [c / 255 for c in P["can"]]; rgba[..., 3] = np.clip(v, 0, 1) ** .9 * P["can_a"]
ax.imshow(rgba, extent=[cn["x0"], cn["x0"] + cn["w"] * cn["cell"], cn["y1"] - cn["h"] * cn["cell"], cn["y1"]], origin="upper", interpolation="bilinear", zorder=2, aspect="auto")
ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_aspect("equal")
segs = np.stack([EC[:, :2], EC[:, 2:]], axis=1)
ax.add_collection(LineCollection(segs, colors=P["road"], linewidths=np.array([.8, .6, .7, .6, .35])[ECLS] * .85, zorder=6, capstyle="round"))
idx = np.where(load >= .5)[0]; idx = idx[np.argsort(load[idx])]
wid = lambda l: (0.35 + 3.7 * np.sqrt(l / REF)) * 1.05
ax.add_collection(LineCollection(segs[idx], colors=P["halo"], linewidths=wid(load[idx]) + 1.6, zorder=7, capstyle="round", alpha=.9))
ax.add_collection(LineCollection(segs[idx], colors=P["traf"], linewidths=wid(load[idx]), zorder=8, capstyle="round"))
lk = [(j, m) for j, m in enumerate(M) if np.hypot(m["x"] - m["nx"], m["y"] - m["ny"]) > .8]
ax.add_collection(LineCollection([[(m["nx"], m["ny"]), (m["x"], m["y"])] for j, m in lk], colors=P["traf"], linewidths=[max(1.0, wid(mload[j])) for j, m in lk],
                                 linestyles=[(0, (2.4, 1.6))], alpha=.9, zorder=8.5, capstyle="butt"))
for s in D["states"]:                                              # state boundaries ON TOP of roads and traffic: faint and light
    for r in s[3]:
        r = np.array(r); ax.plot(r[:, 0], r[:, 1], color=P["bnd"] if s[2] else P["bnd_o"], alpha=P["bnd_a"] if s[2] else .6, lw=1.5 if s[2] else .8, zorder=9, solid_joinstyle="round")
mx = np.array([m["x"] for m in M]); my = np.array([m["y"] for m in M])
SHAPE = {"pulp": ("o", 60, "Pulp"), "sawmill": ("^", 80, "Sawmill"), "osb": ("s", 56, "OSB"), "plywood": ("D", 52, "Plywood"), "mdf": ("p", 84, "MDF"), "paper": ("*", 200, "Paper")}
mtype = np.array([m["type"] for m in M])
for tp, (mk, sz, lab) in SHAPE.items():
    k_ = mtype == tp
    if k_.any(): ax.scatter(mx[k_], my[k_], s=sz, marker=mk, c=P["mill"], edgecolors=P["halo"], linewidths=1.2, zorder=10)

# ---- scale bars + north arrow (fixed elements first, so labels can avoid them)
sx0, sy0, bh = -1020, -1190, 30
for i in range(5): ax.add_patch(Rectangle((sx0 + i * 100, sy0), 100, bh, fc=INK if i % 2 == 0 else P["land"], ec=INK, lw=1, zorder=12))
halo = lambda c, w=3.6, a=.9: [pe.withStroke(linewidth=w, foreground=c, alpha=a)]
for i in range(6): ax.annotate(f"{i * 100}", (sx0 + i * 100, sy0 + bh), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=21.0, color=INK, zorder=12, path_effects=halo(P["water"]))
ax.annotate("km", (sx0 + 500, sy0 + bh / 2), xytext=(8, 0), textcoords="offset points", ha="left", va="center", fontsize=21.0, color=INK, zorder=12, path_effects=halo(P["water"]))
mi = 160.934
for i in range(4): ax.add_patch(Rectangle((sx0 + i * mi, sy0 - bh - 22), mi, bh, fc=INK if i % 2 == 0 else P["land"], ec=INK, lw=1, zorder=12))
for i in range(5): ax.annotate(f"{i * 100}", (sx0 + i * mi, sy0 - bh - 22), xytext=(0, -4), textcoords="offset points", ha="center", va="top", fontsize=21.0, color=INK, zorder=12, path_effects=halo(P["water"]))
ax.annotate("mi", (sx0 + 4 * mi, sy0 - bh / 2 - 22), xytext=(8, 0), textcoords="offset points", ha="left", va="center", fontsize=21.0, color=INK, zorder=12, path_effects=halo(P["water"]))
nx0, ny0 = 1775, -1000
_arrow = ax.add_patch(MPoly([[nx0, ny0 + 250], [nx0 - 62, ny0 - 15], [nx0, ny0 + 40], [nx0 + 62, ny0 - 15]], fc=INK, ec=INK, zorder=12))
_n1 = ax.annotate("N", (nx0, ny0 + 250), xytext=(0, 4), textcoords="offset points", fontsize=45.0, weight="bold", ha="center", va="bottom", color=INK, zorder=12, path_effects=halo(P["water"], 5))
_n2 = ax.annotate("true north at 96°W;" + NL + "meridians converge", (nx0, ny0 - 15), xytext=(0, -6), textcoords="offset points", fontsize=18.0, ha="center", va="top", color=MUT, zorder=12, path_effects=halo(P["water"]))

# ---- keep the north arrow and its note fully inside the map frame, then verify that no label crosses the frame line
def _fit_north(arrow, n1, n2, pad_px=16):
    fig.canvas.draw(); r_ = fig.canvas.get_renderer(); axb = ax.get_window_extent(r_)
    for _ in range(4):
        over = max(n1.get_window_extent(r_).x1, n2.get_window_extent(r_).x1) - (axb.x1 - pad_px)
        if over <= 0: break
        dx = over * (xmax - xmin) / axb.width
        arrow.set_xy(arrow.get_xy() - np.array([dx, 0]))
        for n_ in (n1, n2): n_.xy = (n_.xy[0] - dx, n_.xy[1])
        fig.canvas.draw()
def _check_frame():
    r_ = fig.canvas.get_renderer(); axb = ax.get_window_extent(r_); bad = []
    for t_ in ax.texts:
        bb = t_.get_window_extent(r_)
        inter = not (bb.x1 < axb.x0 or bb.x0 > axb.x1 or bb.y1 < axb.y0 or bb.y0 > axb.y1)
        inside = bb.x0 >= axb.x0 - 1 and bb.x1 <= axb.x1 + 1 and bb.y0 >= axb.y0 - 1 and bb.y1 <= axb.y1 + 1
        if inter and not inside: bad.append(t_.get_text().replace(chr(10), " ")[:40])
    print("labels crossing the map frame:", bad if bad else "none")
    return bad
_fit_north(_arrow, _n1, _n2)

# ---- collision-aware labelling: no label may cover a mill symbol, a route tag, a fixed element or another label
fig.canvas.draw(); rend = fig.canvas.get_renderer(); inv = ax.transData.inverted()
mill_px = ax.transData.transform(np.c_[mx, my]); placed = []
def bb_of(t): return t.get_window_extent(rend)
def overlaps(bb, pad=4): return any(not (bb.x1 + pad < o.x0 or o.x1 + pad < bb.x0 or bb.y1 + pad < o.y0 or o.y1 + pad < bb.y0) for o in placed)
def hits_mill(bb, pad=9, skip=None):
    m = (mill_px[:, 0] > bb.x0 - pad) & (mill_px[:, 0] < bb.x1 + pad) & (mill_px[:, 1] > bb.y0 - pad) & (mill_px[:, 1] < bb.y1 + pad)
    if skip is not None: m[skip] = False
    return bool(m.any())
def in_axes(bb): a = ax.get_window_extent(rend); return bb.x0 > a.x0 + 3 and bb.x1 < a.x1 - 3 and bb.y0 > a.y0 + 3 and bb.y1 < a.y1 - 3
for el in ax.texts + [a for a in ax.patches if isinstance(a, Rectangle)]:           # fixed elements already on the map
    try: placed.append(el.get_window_extent(rend))
    except Exception: pass
# route tags (value of the busiest segments) are fixed to their segment, so they go first
picked = []
for i in np.argsort(-load):
    if load[i] < 100 or len(picked) >= 4: break
    xm, ym = (EC[i, 0] + EC[i, 2]) / 2, (EC[i, 1] + EC[i, 3]) / 2
    if all(np.hypot(xm - a, ym - b) > 380 for a, b, _ in picked): picked.append((xm, ym, load[i]))
for x_, y_, l_ in picked:
    t = ax.annotate(f"{l_:.0f}", (x_, y_), ha="center", va="center", fontsize=19.5, weight="bold", color=P["tagtxt"], zorder=11, bbox=dict(boxstyle="round,pad=.25,rounding_size=.6", fc=P["traf"], ec=P["halo"], lw=1.3))
    placed.append(bb_of(t))
# study-state names: the position nearest the state's centre that keeps the whole label inside the state and off every mill
polys = {}
for s in D["states"]:
    if s[2]: polys[s[1]] = unary_union([SPoly(r).buffer(0) for r in s[3]])
ideal = {nm: (x, y, ab) for nm, ab, x, y in D["sl"]}
def state_label(nm, poly, ix, iy, ab):
    kmpp = (xmax - xmin) / ax.get_window_extent(rend).width
    cands = []
    x0_, y0_, x1_, y1_ = poly.bounds
    for gx in np.arange(x0_, x1_, 18):
        for gy in np.arange(y0_, y1_, 18):
            if poly.contains(SPt(gx, gy)): cands.append((np.hypot(gx - ix, gy - iy), gx, gy))
    cands.sort()
    for text, fs in ((nm.upper().replace(" ", NL, 1) if " " in nm else nm.upper(), 22.5), (nm.upper(), 22.5), (ab, 30.0)):
        t = ax.text(ix, iy, text, fontsize=fs, color="#5c5642", ha="center", va="center", alpha=.9, weight="bold", zorder=9.5, path_effects=halo(P["study"], 3.2, .85), multialignment="center")
        for d, gx, gy in cands[:600]:
            t.set_position((gx, gy)); bb = bb_of(t)
            if overlaps(bb) or hits_mill(bb) or not in_axes(bb): continue
            c0 = inv.transform((bb.x0, bb.y0)); c1 = inv.transform((bb.x1, bb.y1)); box = sbox(c0[0], c0[1], c1[0], c1[1])
            if poly.intersection(box).area / box.area < .86: continue
            placed.append(bb); return text
        t.remove()
    return None
used = {}
for nm in sorted(polys, key=lambda n: polys[n].area):
    ix, iy, ab = ideal[nm]
    used[nm] = state_label(nm, polys[nm], ix, iy, ab)
print("state labels:", used)
# mills: name the five that receive the most wood, each on a free side of its symbol
OFFS = [(10, 8, "left", "bottom"), (-10, 8, "right", "bottom"), (10, -8, "left", "top"), (-10, -8, "right", "top"), (0, 14, "center", "bottom"), (0, -14, "center", "top")]
for j in np.argsort(-mload)[:5]:
    for dx, dy, ha, va in OFFS:
        t = ax.annotate(M[j]["name"], (mx[j], my[j]), xytext=(dx, dy), textcoords="offset points", fontsize=22.5, weight="bold", color=INK, ha=ha, va=va, zorder=11, path_effects=halo(P["halo"], 4.2))
        bb = bb_of(t)
        if overlaps(bb, 2) or hits_mill(bb, 6, skip=j) or not in_axes(bb): t.remove(); continue
        placed.append(bb); break
# water, country and neighbouring-state names (context), only where free
for nm, x, y in D["water"]:
    if nm.startswith("Gulf"): t = ax.text(x, y, "Gulf of America", fontsize=28.5, style="italic", color=P["wlab"], ha="center", zorder=4.2)
    else: t = ax.text(1690, -470, "Atlantic" + NL + "Ocean", fontsize=25.5, style="italic", color=P["wlab"], ha="center", zorder=4.2, linespacing=1.1)
    placed.append(bb_of(t))
t = ax.text(-640, -1010, "MEXICO", fontsize=22.5, color="#9a917a", ha="center", va="center", zorder=4.2); placed.append(bb_of(t))
for nm, x, y in D["nbr"]:
    if not (xmin + 110 < x < xmax - 110 and ymin + 80 < y < ymax - 80): continue
    t = ax.text(x, y, nm, fontsize=19.5, style="italic", color=P["nbr"], ha="center", va="center", zorder=4.2, path_effects=halo(P["land"], 2.6, .8))
    bb = bb_of(t)
    if overlaps(bb, 2) or hits_mill(bb, 6) or not in_axes(bb): t.remove(); continue
    placed.append(bb)

# ------------------------------------------------------------------ row A: the one key chart, extent locator, key figures
RA_T = MAP_B - .62                      # row A: chart | locator | key figures
CH_H = 2.2; CH_B = RA_T - .95 - CH_H    # bottom of the chart and locator frames
sd = {}
for h in F: sd.setdefault(h["st"], [0, 0, 0, 0, 0])[nclass(h)] += h["rem"]
order_s = sorted(sd, key=lambda s: sum(sd[s]))
T(X0, RA_T, "How far is each state's wood from a mill?", fontsize=28.5, weight="bold", va="center")
T(X0, RA_T - .34, "FIA removals by minutes to the nearest sample mill, million ft³ a year." + NL + "The label is the share of the state's removals within a 2 h haul of any mill.", fontsize=18.8, color=MUT, va="top", linespacing=1.2)
ca = fig.add_axes(R(X0 + 1.95, CH_B, 5.2, CH_H), facecolor="#fffdf7")
for s in ("top", "right"): ca.spines[s].set_visible(False)
for s in ("left", "bottom"): ca.spines[s].set_color(MUT); ca.spines[s].set_linewidth(.9)
ca.tick_params(colors=MUT, labelsize=17.2, length=3); ca.set_axisbelow(True)
cols = P["t"] + [P["none"]]
for yi, s in enumerate(order_s):
    left = 0
    for ci in range(5):
        ca.barh(yi, sd[s][ci], left=left, color=cols[ci], edgecolor="#fffdf7", linewidth=.5, height=.78); left += sd[s][ci]
    ca.text(left + 30, yi, f"{(1 - sd[s][4] / sum(sd[s])) * 100:.0f}%", va="center", fontsize=17.2, color=INK)
ca.set_yticks(range(len(order_s))); ca.set_yticklabels([NAMES[s] for s in order_s], fontsize=18.0, color=INK)
ca.set_xlim(0, max(sum(v) for v in sd.values()) * 1.2); ca.grid(axis="x", color=P["line"], lw=.6)
lg = ca.legend([plt.Rectangle((0, 0), 1, 1, fc=c, ec="#fffdf7") for c in cols], ["0-30 min", "30-60", "60-90", "90-120", "no mill in 2 h"], ncol=5, labelcolor=INK, fontsize=17.2,
               frameon=False, loc="upper left", bbox_to_anchor=(-.37, -.13), columnspacing=.8, handlelength=1, handletextpad=.35)
# locator: where the study states sit in the lower 48, and where the map frame is
LX, LW_, LH = 9.1, 3.85, CH_H
T(LX, RA_T, "Study area", fontsize=28.5, weight="bold", va="center")
T(LX, RA_T - .34, "Colour = the 13 study states." + NL + "Box = the extent of the map above.", fontsize=18.8, color=MUT, va="top", linespacing=1.2)
loc = fig.add_axes(R(LX, CH_B, LW_, LH), facecolor=P["water"])
for f, s in ((int(k), v) for k, v in json.load(open("../data/states_albers_km.json")).items()):
    if f in (2, 15) or f > 56: continue
    for r in s["rings"]: loc.add_patch(MPoly(r, closed=True, fc=(P["acc"] if f in NAMES else P["land"]), ec=P["bnd"], lw=.4, alpha=.9 if f in NAMES else 1))
loc.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, fc="none", ec=INK, lw=2.2))
loc.set_xlim(-2650, 2500); loc.set_ylim(-1480, 1640); loc.set_aspect("equal"); loc.set_xticks([]); loc.set_yticks([])
for s in loc.spines.values(): s.set_color(INK); s.set_linewidth(1)
KX = LX + LW_ + .3
for i, (big, small) in enumerate([(f"{tot/1000:.1f} bn", "ft³ a year of FIA removals"), (f"{reached/tot*100:.0f}%", "within 2 h of a mill"), (f"{n_recv}", "mills receiving wood")]):
    y = CH_B + CH_H - .25 - i * .72
    T(KX, y, big, fontsize=37.5, weight="bold", color=P["acc"], va="center"); T(KX, y - .3, small, fontsize=16.5, va="top")

# ------------------------------------------------------------------ row B: complete legend, how to read, limitations
LT = CH_B - .8; LB = LT - 3.15; LW2 = 7.55
ov.add_patch(Rectangle((X0, LB), LW2, LT - LB, fc="#ffffff", ec=INK, lw=1.2))
lx = X0 + .18
T(lx, LT - .25, "LEGEND", fontsize=22.5, weight="bold", color=MUT, va="center")
T(lx, LT - .6, "Wood moved, million ft³ a year (modelled)", fontsize=22.5, weight="bold", va="center")
for i, vv in enumerate([1, 10, 50, 150, 250]):
    x = lx + .05 + i * .8
    ov.plot([x, x + .55], [LT - .93] * 2, color=P["traf"], lw=wid(vv), solid_capstyle="round"); T(x + .275, LT - 1.17, f"{vv}", fontsize=20.2, ha="center", va="center")
rows = LT - 1.5; st_ = .285
def sym_line(y, color, lw, ls=None, alpha=1): ov.plot([lx, lx + .55], [y] * 2, color=color, lw=lw, ls=ls or "-", alpha=alpha, solid_capstyle="butt")
sym_line(rows, P["road"], 1.6); T(lx + .72, rows, "Other roads", fontsize=20.2, va="center")
sym_line(rows - st_, P["bnd"], 2.0, alpha=.65); T(lx + .72, rows - st_, "State boundary", fontsize=20.2, va="center")
sym_line(rows - 2 * st_, P["traf"], 2.2, ls=(0, (2.4, 1.6))); T(lx + .72, rows - 2 * st_, "Link between mapped road and mill", fontsize=20.2, va="center")
sym_line(rows - 3 * st_, P["grat"], 1.4, ls=(0, (2, 3))); T(lx + .72, rows - 3 * st_, "5° graticule", fontsize=20.2, va="center")
tg = dict(boxstyle="round,pad=.25,rounding_size=.6", fc=P["traf"], ec=P["halo"], lw=1.2)
T(lx + .27, rows - 4 * st_, "259", fontsize=18.8, weight="bold", color=P["tagtxt"], ha="center", va="center", bbox=tg); T(lx + .72, rows - 4 * st_, "Busiest road segment, million ft³/yr", fontsize=20.2, va="center")
RXc = lx + 4.35
gax = fig.add_axes(R(RXc, LT - 1.27, 1.45, .22)); g = np.linspace(0, 1, 256)[None, :]
gr = np.zeros((1, 256, 4)); gr[..., 0], gr[..., 1], gr[..., 2] = [c / 255 for c in P["can"]]; gr[..., 3] = g ** .9 * P["can_a"]
gax.set_facecolor(P["study"]); gax.imshow(gr, aspect="auto", extent=[0, 100, 0, 1]); gax.set_yticks([]); gax.set_xticks([0, 100]); gax.set_xticklabels(["0%", "100%"]); gax.set_zorder(40)
gax.tick_params(colors=INK, labelsize=18.0, length=3, pad=2)
for sp in gax.spines.values(): sp.set_color(INK); sp.set_linewidth(.9)
T(RXc, LT - .93, "Tree canopy, NLCD 2021", fontsize=20.2, weight="bold", va="center")
T(RXc, LT - 1.95, "Mill type", fontsize=20.2, weight="bold", va="center")
for i_, (tp, (mk, sz, lab)) in enumerate(SHAPE.items()):
    cx_ = RXc + .14 + (i_ // 3) * 1.45; cy_ = LT - 2.28 - (i_ % 3) * .3
    ov.scatter([cx_], [cy_], s=sz * 1.35, marker=mk, c=P["mill"], edgecolors=P["halo"], linewidths=1.3)
    T(cx_ + .22, cy_, f"{lab} ({int((mtype == tp).sum())})", fontsize=18.8, va="center")

TX = X0 + LW2 + .4; TW = W - X0 - TX
T(TX, LT - .12, "HOW TO READ IT", fontsize=22.5, weight="bold", color=MUT, va="center")
read = ("Each forest hex (842 km²) sends its FIA removals to every mill within a 2 hour road haul, weighted by travel time: a mill 15 minutes farther than the "
        "nearest receives about 37% of its share. Road thickness is the wood summed over every route crossing a segment, and each haul is counted once.")
T(TX, LT - .36, NL.join(textwrap.wrap(read, 82)), fontsize=19.8, va="top", linespacing=1.12)
T(TX, LT - 1.5, "WHAT THIS MAP CAN AND CANNOT TELL YOU", fontsize=22.5, weight="bold", color=P["acc"], va="center")
lim = ("This is a model of potential wood movement, not a count of real trucks. It assumes that all forest removals reported by the USDA Forest Service, which include "
       "land clearing as well as harvest, go to the mills in my sample by the fastest route on major roads. A dashed link shows where a mill sits off those roads. The mill "
       "list is a sample, so an empty area usually means missing mills, not missing demand. Tree canopy is a satellite estimate and is not the FIA definition of forest. "
       "Speeds are assumed; mill size, tree species and truck weight limits are not included.")
T(TX, LT - 1.72, NL.join(textwrap.wrap(lim, 82)), fontsize=19.2, va="top", linespacing=1.08)
ov.plot([X0, W - X0], [.82, .82], color=INK, lw=.9)
T(X0, .7, NL.join(textwrap.wrap("Data: USDA Forest Service FIA county estimates (2016-2025 evaluations); USFS NLCD Tree Canopy Cover v2025-6 (2021); Natural Earth 1:10m roads; US Census state boundaries; "
                                 "mills: author-compiled sample (Forisk / PPRC 2025, company announcements, trade press). Spherical Albers equal-area conic, standard parallels 29.5°N and 45.5°N, origin 37.5°N 96°W.", 150)),
  fontsize=17.2, color=MUT, va="top", linespacing=1.2)
_bad = _check_frame()
assert not _bad, _bad
fig.savefig(f"{OUT}.png", dpi=DPI, facecolor=P["page"])
fig.savefig(f"{OUT}.pdf", facecolor=P["page"])
print("saved", OUT, "dpi", DPI, "->", int(W * PHYS * DPI), "x", int(HT * PHYS * DPI))
