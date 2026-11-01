#!/usr/bin/env python3
"""Static "US wood mills" map whose symbology carries the data's uncertainty.

Design rules (see dataviz validation in the README of this folder):
  * Colour carries STATUS only, in two validated categorical hues + neutral gray:
        blue   = no closure recorded (operating status NOT confirmed)  -> filled
        orange = closed / idled                                       -> rings, hatch
        gray   = status unknown                                       -> dashed outline
    Blue and orange pass the all-pairs CVD / normal-vision checks (dE 24.7 / 33.6).
    Orange is <3:1 on a pale surface, so land is near-white (~3:1) and every
    colour has a secondary encoding (fill style) plus a table view (the CSV).
  * SHAPE carries mill type (5 shapes), so no rainbow is needed.
  * Capacity is deliberately not mapped (13 of 196 records, four incompatible units).

Projection: spherical Albers equal-area conic, parallels 29.5/45.5 N, origin
37.5 N / 96 W. Alaska is an inset (parallels 55/65 N, origin 50 N / 154 W,
scaled 0.35, not to scale). Co-located records are offset ~22 km, display only.

State outlines (--states): us-atlas style TopoJSON or lon/lat GeoJSON. Without
it the map renders as a clearly-labelled DRAFT.

Usage:
    python make_static_map.py --mills out/mills_clean.csv --states data/us-states.geojson \
        --out out/us_wood_mills.png
"""
from __future__ import annotations

import argparse
import json
import logging
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)  # fallback-weight chatter
R = 6371008.8  # m, spherical earth

# ---- palette (validated: blue/orange all-pairs; see header) -----------------
PAGE = "#F2F3EE"      # page
OCEAN = "#E1E7E0"     # inside the map frame
LAND = "#FBFBF8"      # near-white so orange marks reach ~3:1
BORDER = "#CDD3C8"
INK, INK2, MUTED, RULE = "#16201A", "#44504A", "#6B756E", "#C4CBC1"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#52514e"
SHAPE_INK = "#3A463F"

# shape = mill type group: (marker, size, label)
SHAPES = {
    "pulp_paper": ("o", 54, "Pulp & paper"),
    "sawmill": ("s", 48, "Sawmill"),
    "plywood": ("^", 66, "Plywood"),
    "osb": ("D", 46, "OSB"),
    "mdf": ("*", 118, "MDF / particleboard"),
}
TYPE_TO_SHAPE = {"pulp": "pulp_paper", "paper": "pulp_paper", "other": "pulp_paper",
                 "sawmill": "sawmill", "plywood": "plywood", "osb": "osb", "mdf": "mdf"}

# status class -> scatter kwargs (shared by map and legend)
STATUS = {
    "filled": dict(c=BLUE, edgecolors=LAND, linewidths=0.9, alpha=0.95),
    "ring_verified": dict(facecolors=LAND, edgecolors=ORANGE, linewidths=2.0),
    "ring_approx": dict(facecolors="none", edgecolors=ORANGE, linewidths=1.3, alpha=0.6),
    "hatched": dict(facecolors=ORANGE, edgecolors=LAND, linewidths=0.9, hatch="/////"),
    "dashed": dict(facecolors=LAND, edgecolors=GRAY, linewidths=1.6, linestyles="--"),
}
NON_CONUS_FIPS = {"02", "15", "60", "66", "69", "72", "78"}


def tracked(s: str) -> str:
    """Faux letter-spacing for small-caps labels (matplotlib has no tracking)."""
    return " ".join(s.upper())


# ---------------------------------------------------------------- projection
def albers(lon, lat, p1, p2, lat0, lon0):
    """Spherical Albers equal-area conic -> metres."""
    p1, p2, f0, l0 = map(np.radians, (p1, p2, lat0, lon0))
    n = (np.sin(p1) + np.sin(p2)) / 2
    C = np.cos(p1) ** 2 + 2 * n * np.sin(p1)
    rho0 = R * np.sqrt(C - 2 * n * np.sin(f0)) / n
    lon, lat = np.radians(np.asarray(lon, float)), np.radians(np.asarray(lat, float))
    rho = R * np.sqrt(C - 2 * n * np.sin(lat)) / n
    th = n * (lon - l0)
    return rho * np.sin(th), rho0 - rho * np.cos(th)


def conus(lon, lat):
    return albers(lon, lat, 29.5, 45.5, 37.5, -96)


AK_SCALE = 0.35
AK_LL = (-2.40e6, -1.57e6)  # lower-left corner of the Alaska inset, CONUS metres


def _ak_extent() -> tuple[float, float, float, float]:
    lo, la = np.meshgrid(np.linspace(-170, -130, 60), np.linspace(54.5, 71.5, 60))
    x, y = albers(lo, la, 55, 65, 50, -154)
    return x.min(), y.min(), x.max(), y.max()


_AK = _ak_extent()
AK_BOX = (AK_LL[0], AK_LL[1], AK_LL[0] + (_AK[2] - _AK[0]) * AK_SCALE, AK_LL[1] + (_AK[3] - _AK[1]) * AK_SCALE)


def alaska(lon, lat):
    x, y = albers(lon, lat, 55, 65, 50, -154)
    return (x - _AK[0]) * AK_SCALE + AK_LL[0], (y - _AK[1]) * AK_SCALE + AK_LL[1]


# Hawaii inset: Esri-style Hawaii Albers (parallels 8/18 N, origin 3 N / 157 W), same reduced scale as Alaska
# so that ONE scale bar serves both insets. The box is wider than the islands: it also carries the "no records" note.
HI_SCALE = AK_SCALE
HI_W, HI_H, HI_GAP = 0.46e6, 0.34e6, 0.05e6
HI_BOX = (AK_BOX[2] + HI_GAP, AK_BOX[1], AK_BOX[2] + HI_GAP + HI_W, AK_BOX[1] + HI_H)
INSET_BAR_XY = (HI_BOX[2] + 0.14e6, AK_BOX[1] + 0.075e6)  # lower-left of the shared inset scale bar


def _hi_extent() -> tuple[float, float, float, float]:
    lo, la = np.meshgrid(np.linspace(-160.6, -154.7, 40), np.linspace(18.8, 22.4, 40))
    x, y = albers(lo, la, 8, 18, 3, -157)
    return x.min(), y.min(), x.max(), y.max()


_HI = _hi_extent()


def hawaii(lon, lat):
    """Islands centred horizontally in HI_BOX, sitting 0.04e6 above its bottom edge."""
    x, y = albers(lon, lat, 8, 18, 3, -157)
    cx = (HI_BOX[0] + HI_BOX[2]) / 2
    return (x - (_HI[0] + _HI[2]) / 2) * HI_SCALE + cx, (y - _HI[1]) * HI_SCALE + HI_BOX[1] + 0.04e6


# ---------------------------------------------------------------- boundaries
def _topo_features(topo: dict) -> list[tuple[str, list]]:
    sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sc[0] + tr[0], y * sc[1] + tr[1]))
        arcs.append(pts)

    def ring(idxs):
        pts: list = []
        for i in idxs:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(a if not pts else a[1:])
        return pts

    out = []
    for g in topo["objects"]["states"]["geometries"]:
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        out.append((str(g.get("id", "")).zfill(2), [[ring(r) for r in poly] for poly in polys]))
    return out


def _geojson_features(gj: dict) -> list[tuple[str, list]]:
    out = []
    for f in gj["features"]:
        pr = f.get("properties", {})
        fips = str(pr.get("STATEFP") or pr.get("GEOID") or f.get("id") or "").zfill(2)[:2]
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        out.append((fips, [[[tuple(c[:2]) for c in r] for r in poly] for poly in polys]))
    return out


def load_states(path: Path) -> list[tuple[str, list]]:
    data = json.loads(path.read_text())
    return _topo_features(data) if data.get("type") == "Topology" else _geojson_features(data)


def fits_ak_box(poly) -> bool:
    """False for Alaska polygons that would spill outside the inset box (far-west Aleutians, beyond 170 W)."""
    x, y = alaska(*np.array(poly[0])[:, :2].T)
    return bool(x.min() >= AK_BOX[0] and x.max() <= AK_BOX[2] and y.min() >= AK_BOX[1] and y.max() <= AK_BOX[3])


def draw_states(ax, feats) -> None:
    for fips, polys in feats:
        if fips in NON_CONUS_FIPS - {"02", "15"}:
            continue
        proj = {"02": alaska, "15": hawaii}.get(fips, conus)
        for poly in polys:
            verts, codes = [], []
            if fips == "02" and not fits_ak_box(poly):
                continue
            for r in poly:
                arr = np.array(r)
                x, y = proj(arr[:, 0], arr[:, 1])
                verts += list(zip(x, y))
                codes += [MPath.MOVETO] + [MPath.LINETO] * (len(arr) - 2) + [MPath.CLOSEPOLY]
            ax.add_patch(PathPatch(MPath(verts, codes), fc=LAND, ec=BORDER, lw=0.7, zorder=1))


# --------------------------------------------------------------------- data
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["in_us_scope"]].copy()
    ak = d["state"] == "AK"
    x, y = conus(d["lon"].values, d["lat"].values)
    xa, ya = alaska(d["lon"].values, d["lat"].values)
    xh, yh = hawaii(d["lon"].values, d["lat"].values)
    hi = d["state"] == "HI"  # no Hawaii records in the current sample; handled so new rows land in the inset
    d["x"] = np.where(ak, xa, np.where(hi, xh, x))
    d["y"] = np.where(ak, ya, np.where(hi, yh, y))
    for _, g in d[d["colocated_n"] > 1].groupby("site_id"):  # display-only offset
        d.loc[g.index, "x"] += np.linspace(-1, 1, len(g)) * 22000
    st, conf = d["operational_status"], d["status_confidence"]
    d["cls"] = np.select(
        [st.isin(["open", "partial", "reopened"]), (st == "closed") & (conf == "verified"),
         st == "closed", st == "idled", st == "unknown"],
        ["filled", "ring_verified", "ring_approx", "hatched", "dashed"], default="?")
    assert (d["cls"] != "?").all(), d.loc[d["cls"] == "?", "name"].tolist()
    d["shape"] = d["mill_type"].map(TYPE_TO_SHAPE)
    assert d["shape"].notna().all()
    return d


SIZE_K = 0.55   # symbol area factor (was 1.0): smaller marks overlap less; same size in every map frame
LW_K = 0.72     # outline-width factor, matched to SIZE_K


ZOOM_SIZE_K, ZOOM_LW_K = 0.70, 0.82  # symbols are a little larger inside the enlarged frames


def mk_kw(cls: str, lwk: float = LW_K) -> dict:
    """STATUS style with outline widths scaled; used by the map frames AND the legend so they always agree."""
    kw = dict(STATUS[cls])
    kw["linewidths"] = kw["linewidths"] * lwk
    return kw


def plot_mills(ax, d: pd.DataFrame, k: float = SIZE_K, lwk: float = LW_K, clip: bool = True) -> None:
    order = ["ring_approx", "ring_verified", "filled", "hatched", "dashed"]  # filled sits above rings
    for i, cls in enumerate(order):
        for sh, (mk, sz, _) in SHAPES.items():
            g = d[(d["cls"] == cls) & (d["shape"] == sh)]
            if not g.empty:
                ax.scatter(g.x, g.y, marker=mk, s=sz * k, zorder=3 + i, clip_on=clip, **mk_kw(cls, lwk))


# ------------------------------------------------- graticule and scale bar
GRID = "#B7C2B5"      # visible on OCEAN; graticule sits UNDER the land, so it shows only off-shore
XLIM, YLIM = (-2.45e6, 2.45e6), (-1.80e6, 1.65e6)
SCALE_ORIGIN = (0.55e6, -1.64e6)  # lower-left of the scale bar, CONUS metres


def _visible(x, y):
    """NaN-out samples outside the frame, in the inset strip (Alaska, Hawaii, their scale bar), or behind the main scale bar."""
    x, y = np.array(x, float), np.array(y, float)
    sx, sy = SCALE_ORIGIN
    bad = (x < XLIM[0]) | (x > XLIM[1]) | (y < YLIM[0]) | (y > YLIM[1])
    bad |= (x > AK_BOX[0] - 0.05e6) & (x < HI_BOX[2] + 0.05e6) & (y < AK_BOX[3] + 0.05e6)
    bad |= (x > INSET_BAR_XY[0] - 0.06e6) & (x < INSET_BAR_XY[0] + 0.68e6) & (y < INSET_BAR_XY[1] + 0.13e6)
    bad |= (x > sx - 0.08e6) & (x < sx + 1.45e6) & (y > sy - 0.14e6) & (y < sy + 0.16e6)
    x[bad], y[bad] = np.nan, np.nan
    return x, y


def graticule(ax, step: int = 10) -> None:
    """Lon/lat lines every `step` degrees (solid hairlines), labelled at the frame edge."""
    lab = dict(fontsize=8.2, color=MUTED, zorder=2.5)
    for lat in range(30, 61, step):
        x, y = _visible(*conus(np.linspace(-140, -50, 500), np.full(500, lat)))
        ax.plot(x, y, color=GRID, lw=0.8, zorder=0.6, solid_capstyle="butt")
        ok = ~np.isnan(x)
        if ok.sum() > 20:  # label on the Atlantic side, where the frame is empty ocean
            i = np.nanargmax(x)
            near_top = y[i] > YLIM[1] - 0.12e6  # keep the label inside the frame
            ax.text(x[i] - 0.035e6, y[i] + (-0.012e6 if near_top else 0.012e6), f"{lat}°N",
                    va="top" if near_top else "bottom", ha="right", **lab)
    for lon in range(-140, -49, step):
        x, y = _visible(*conus(np.full(500, lon), np.linspace(18, 58, 500)))
        ax.plot(x, y, color=GRID, lw=0.8, zorder=0.6, solid_capstyle="butt")
        ok = ~np.isnan(x)
        if ok.sum() > 20:
            i = np.nanargmax(np.where(ok, y, -np.inf))
            ax.text(x[i] + 0.012e6, y[i] - 0.035e6, f"{abs(lon)}°W", va="top", ha="left", **lab)


def scale_bar(ax, x0: float, y0: float, km: int = 1000, seg: int = 4) -> None:
    """Alternating-segment bar in km, with a miles equivalent; lower-48 projection only."""
    w, h = km * 1000.0, 0.042e6
    for i in range(seg):
        ax.add_patch(plt.Rectangle((x0 + i * w / seg, y0), w / seg, h, fc=INK if i % 2 == 0 else LAND,
                                   ec=INK, lw=0.7, zorder=6))
    for i in range(seg + 1):
        v = i * km // seg
        txt = f"{v:,} km" if i == seg else f"{v:,}"
        ax.text(x0 + i * w / seg, y0 - 0.02e6, txt, fontsize=8.4, color=INK2, ha="center", va="top", zorder=6)
    ax.text(x0 + w + 0.07e6, y0 + h / 2, f"≈ {km * 0.621371:,.0f} mi", fontsize=8.4, color=MUTED,
            ha="left", va="center", zorder=6)
    ax.text(x0, y0 + h + 0.025e6, "Lower 48 only. Equal-area; scale varies ±1.5%.",
            fontsize=7.9, color=MUTED, ha="left", va="bottom", zorder=6)


def inset_scale_bar(ax, x0: float, y0: float, km: int = 1000, seg: int = 2, k: float = AK_SCALE) -> None:
    """One bar for both insets. Drawn length = km * k, because the insets are k times the main-map scale."""
    w, h = km * 1000.0 * k, 0.03e6
    for i in range(seg):
        ax.add_patch(plt.Rectangle((x0 + i * w / seg, y0), w / seg, h, fc=INK if i % 2 == 0 else LAND,
                                   ec=INK, lw=0.6, zorder=6))
    for i in range(seg + 1):
        v = i * km // seg
        ax.text(x0 + i * w / seg, y0 - 0.014e6, f"{v:,}", fontsize=7.9, color=INK2, ha="center", va="top", zorder=6)
    ax.text(x0 + w + 0.09e6, y0 - 0.014e6, "km", fontsize=7.9, color=INK2, ha="left", va="top", zorder=6)
    ax.text(x0, y0 + h + 0.022e6, "Alaska and Hawaii insets", fontsize=7.9, color=MUTED, ha="left", va="bottom", zorder=6)




# ------------------------------------------------------- enlarged map frames
# Extent boxes in map metres. Chosen from a nearest-neighbour check (marks closer than ~one symbol width).
ZOOMS = [
    dict(tag="A", name="Pacific Northwest", box=(-2.40e6, 0.62e6, -1.80e6, 1.58e6), km=200, grid=5),
    dict(tag="B", name="Upper Midwest", box=(0.10e6, 0.66e6, 0.80e6, 1.18e6), km=150, grid=5),
    dict(tag="C", name="Gulf South", box=(0.00e6, -0.92e6, 1.015e6, -0.17e6), km=250, grid=5),
    dict(tag="D", name="Southeast", box=(0.98e6, -0.77e6, 1.77e6, 0.20e6), km=200, grid=5),
    dict(tag="E", name="New England", box=(1.62e6, 0.78e6, 2.32e6, 1.38e6), km=150, grid=5),
]
FIPS_ABBR = {
    "01": "AL", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV",
    "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR",
    "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA",
    "53": "WA", "54": "WV", "55": "WI", "56": "WY",
}


def chip(ax, x, y, text, transform, **kw):
    """White-on-ink label chip: legible over land, ocean and gridlines alike."""
    return ax.text(x, y, text, transform=transform, fontsize=kw.pop("fontsize", 9), fontweight="semibold", color=LAND,
                   bbox=dict(boxstyle="square,pad=0.28", fc=INK, ec="none"), zorder=10, **kw)


def extent_boxes(ax) -> None:
    """Extent indicators on the main map: thin ink rectangles with a letter chip at the top-left corner."""
    for z in ZOOMS:
        x0, y0, x1, y1 = z["box"]
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=INK, lw=1.0, zorder=2.9))
        chip(ax, x0 + 0.012e6, y1 - 0.012e6, z["tag"], ax.transData, ha="left", va="top", fontsize=8.6)


def graticule_zoom(ax, box, step: int) -> None:
    x0, y0, x1, y1 = box
    lab = dict(fontsize=7.4, color=MUTED, zorder=2.5)
    w, h = x1 - x0, y1 - y0

    def inside(x, y):
        x, y = np.array(x, float), np.array(y, float)
        bad = (x < x0) | (x > x1) | (y < y0) | (y > y1)
        x[bad], y[bad] = np.nan, np.nan
        return x, y

    for lat in range(20, 60, step):
        x, y = inside(*conus(np.linspace(-135, -60, 900), np.full(900, lat)))
        ok = ~np.isnan(x)
        if ok.sum() < 5:
            continue
        ax.plot(x, y, color=GRID, lw=0.8, zorder=0.6, solid_capstyle="butt")
        i = np.nanargmax(np.where(ok, x, -np.inf))
        ax.text(x[i] - 0.012 * w, y[i] + 0.008 * h, f"{lat}°N", va="bottom", ha="right", **lab)
    for lon in range(-135, -59, step):
        x, y = inside(*conus(np.full(900, lon), np.linspace(20, 55, 900)))
        ok = ~np.isnan(x)
        if ok.sum() < 5:
            continue
        ax.plot(x, y, color=GRID, lw=0.8, zorder=0.6, solid_capstyle="butt")
        i = np.nanargmin(np.where(ok, y, np.inf))
        if x[i] > x1 - 0.14 * w:      # label would run off the frame edge
            continue
        ax.text(x[i] + 0.008 * w, y[i] + 0.012 * h, f"{abs(lon)}°W", va="bottom", ha="left", **lab)


def zoom_scale_bar(ax, box, km: int, in_per_unit: float) -> None:
    """Two-segment bar just BELOW the frame (outside it), so it can never cover a mark."""
    x0, y0, x1, y1 = box
    u = 1.0 / in_per_unit                      # data units per inch
    w, h = km * 1000.0, 0.07 * u
    bx, by = x0 + 0.02 * u, y0 - 0.15 * u - h
    for i in range(2):
        ax.add_patch(plt.Rectangle((bx + i * w / 2, by), w / 2, h, fc=INK if i == 0 else LAND, ec=INK, lw=0.6,
                                   zorder=9, clip_on=False))
    for i, v in enumerate((0, km // 2, km)):
        ax.text(bx + i * w / 2, by - 0.03 * u, f"{v}", fontsize=7.6, color=INK2, ha="center", va="top", clip_on=False)
    ax.text(bx + w + 0.17 * u, by - 0.03 * u, "km", fontsize=7.6, color=INK2, ha="left", va="top", clip_on=False)


def nudge_apart(x, y, dmin: float, iters: int = 400):
    """Display-only: push marks closer than dmin apart until they just touch, capped at 0.6 * dmin of movement each."""
    pos = np.c_[x, y].astype(float)
    orig = pos.copy()
    n = len(pos)
    for _ in range(iters):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                v = pos[i] - pos[j]
                dist = float(np.hypot(*v))
                if dist < dmin * 0.999:
                    u = v / dist if dist > 1 else np.array([1.0, 0.0]) * (1 if (i + j) % 2 else -1)
                    push = (dmin - dist) / 2 * 0.6
                    pos[i] += u * push
                    pos[j] -= u * push
                    moved = True
        off = pos - orig
        L = np.hypot(off[:, 0], off[:, 1])
        big = L > 0.6 * dmin
        pos[big] = orig[big] + off[big] * (0.6 * dmin / L[big])[:, None]
        if not moved:
            break
    return pos[:, 0], pos[:, 1]


def zoom_panel(fig, rect, z, d, feats) -> None:
    """One enlarged frame: states, 5° grid, state labels, marks at the SAME symbol size, own scale bar."""
    x0, y0, x1, y1 = z["box"]
    ax = fig.add_axes(rect)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor(INK)
        sp.set_linewidth(1.1)
    ax.set_facecolor(OCEAN)
    draw_states(ax, feats)
    graticule_zoom(ax, z["box"], z["grid"])
    for fips, polys in feats:                      # state abbreviations, muted
        if fips not in FIPS_ABBR:
            continue
        big = max(polys, key=lambda p: len(p[0]))
        xs, ys = conus(*np.array(big[0])[:, :2].T)
        cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        if x0 + 0.04 * (x1 - x0) < cx < x1 - 0.04 * (x1 - x0) and y0 + 0.04 * (y1 - y0) < cy < y1 - 0.10 * (y1 - y0):
            ax.text(cx, cy, FIPS_ABBR[fips], fontsize=8.6, color=MUTED, ha="center", va="center", zorder=2.6,
                    fontweight="semibold", alpha=0.75)
    in_per_unit = rect[2] * fig.get_figwidth() / (x1 - x0)
    sel = (d.x >= x0) & (d.x <= x1) & (d.y >= y0) & (d.y <= y1)
    dz = d[sel].copy()
    dmin = (54 * ZOOM_SIZE_K) ** 0.5 / 72.0 / in_per_unit          # one circle-symbol diameter, in map metres
    dz["x"], dz["y"] = nudge_apart(dz["x"].values, dz["y"].values, dmin)
    plot_mills(ax, dz, ZOOM_SIZE_K, ZOOM_LW_K, clip=False)
    zoom_scale_bar(ax, z["box"], z["km"], in_per_unit)
    inside = int(sel.sum())
    name = z["name"] if rect[2] * fig.get_figwidth() > 2.2 else z["name"].replace("Pacific Northwest", "Pacific NW")
    chip(ax, 0.02, 0.975, f"{z['tag']}   {name}", ax.transAxes, ha="left", va="top", fontsize=9)
    ax.text(0.03, 0.905, f"{inside} mills", transform=ax.transAxes, fontsize=8.2, color=INK2, ha="left", va="top",
            zorder=10, bbox=dict(boxstyle="square,pad=0.2", fc=LAND, ec="none", alpha=0.9))


# ----------------------------------------------------------------- panels
def side_panel(ax, d: pd.DataFrame, h_in: float) -> None:
    """Headline + legend. Spacing constants were tuned on a 9.1 in tall axes, so ylim is h_in / 9.1."""
    top = h_in / 9.1
    ax.set_xlim(0, 1)
    ax.set_ylim(0, top)
    ax.axis("off")
    cnt = d["cls"].value_counts()
    shp = d["shape"].value_counts()
    n = len(d)
    closed = cnt.get("ring_verified", 0) + cnt.get("ring_approx", 0)
    verified = cnt.get("ring_verified", 0)

    y = top - 0.015
    headline = (f"Of {n} mills in this sample, {closed} are recorded as closed. "
                f"Only {verified} of those closure years are verified.")
    ax.text(0, y, "\n".join(textwrap.wrap(headline, 34)), fontfamily="Caladea", fontsize=17.5,
            color=INK, va="top", linespacing=1.2)
    y -= 0.148

    def section(label):
        nonlocal y
        ax.plot([0, 1], [y + 0.004, y + 0.004], color=RULE, lw=0.9)
        y -= 0.014
        ax.text(0, y, tracked(label), fontsize=8.4, fontweight="semibold", color=MUTED, va="top")
        y -= 0.034

    def row(marker_kw, marker, size, label, count, sub=None):
        nonlocal y
        ax.scatter([0.035], [y - 0.0105], marker=marker, s=size * 1.15, clip_on=False, zorder=5, **marker_kw)
        ax.text(0.10, y, label, fontsize=11.5, color=INK, va="top")
        ax.text(1.0, y, f"{count}", fontsize=11.5, fontweight="medium", color=INK2, va="top", ha="right")
        y -= 0.027
        if sub:
            ax.text(0.10, y + 0.002, sub, fontsize=9.3, color=MUTED, va="top")
            y -= 0.022
        y -= 0.007

    sz = 54 * SIZE_K * 1.6   # legend swatches a little larger than map marks so the outline styles stay readable
    section("Status")
    row(mk_kw("filled"), "o", sz, "No closure recorded", cnt.get("filled", 0), "Operating status not confirmed")
    row(mk_kw("ring_verified"), "o", sz, "Closed, year verified", cnt.get("ring_verified", 0))
    row(mk_kw("ring_approx"), "o", sz, "Closed, year approximate", cnt.get("ring_approx", 0))
    row(mk_kw("hatched"), "o", sz, "Idled or largely shut", cnt.get("hatched", 0))
    row(mk_kw("dashed"), "o", sz, "Status unknown", cnt.get("dashed", 0), "Startup not confirmed")
    y -= 0.02
    section("Mill type")
    for sh, (mk, s, lab) in SHAPES.items():
        row(dict(c=SHAPE_INK, edgecolors="none"), mk, s * SIZE_K * 1.6, lab, shp.get(sh, 0))


def notes_band(ax, d: pd.DataFrame, df_all: pd.DataFrame) -> None:
    """Six caveats in one row across the page: bold lead-in + muted body."""
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fam = d["industry_family"].value_counts()
    cnt = d["cls"].value_counts()
    ver, apx = cnt.get("ring_verified", 0), cnt.get("ring_approx", 0)
    cap_n = int(df_all["capacity_available"].sum())
    notes = [
        ("A sample, not a census",
         f"{len(d)} US mills: {fam.get('pulp_paper', 0)} pulp and paper, {fam.get('wood_products', 0)} solid wood. "
         "Many operating mills are missing."),
        ("No closure recorded is not operating",
         "The dataset has no field confirming that a mill runs today."),
        ("Closure years",
         f"Verified for {ver} of {ver + apx} closed mills. The rest are approximate."),
        ("Capacity is not mapped",
         f"Known for {cap_n} of {len(df_all)} records, in four units that cannot be compared or summed."),
        ("Locations are town-level",
         "Not mill footprints. Three co-located pairs are drawn slightly apart."),
        ("History is incomplete",
         "Closures before ~1970 are under-represented; no central record exists."),
    ]
    ax.plot([0, 6], [0.985, 0.985], color=RULE, lw=0.9)
    ax.text(0, 0.90, tracked("Read this before citing"), fontsize=8.4, fontweight="semibold", color=MUTED, va="top")
    for i, (lead, body) in enumerate(notes):
        x0 = i * 1.0
        y0 = 0.68
        lead_lines = textwrap.wrap(lead, 24)
        ax.text(x0, y0, "\n".join(lead_lines), fontsize=10.2, fontweight="semibold", color=INK, va="top", linespacing=1.25)
        ax.text(x0, y0 - 0.11 - 0.14 * len(lead_lines), "\n".join(textwrap.wrap(body, 35)), fontsize=9.3, color=INK2,
                va="top", linespacing=1.4)


def footer(ax) -> None:
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    lines = [
        "Data: author-compiled from company announcements, trade press and Forisk / PPRC 2025 mill lists. Compiled November 2026.   "
        "Interactive, time-enabled version: pratyush-dh.github.io/forestry-maps/wood-mills",
        "Albers equal-area conic; graticule every 10° (5° in frames A to E). Scale varies ±1.5% across the lower 48. Alaska and Hawaii "
        "are reduced-scale insets. State outlines are low resolution.",
        "Frames A to E enlarge areas where symbols overlap; their extents are boxed on the map. Symbols are slightly larger there, and marks "
        "closer than one symbol width are nudged apart by up to about 10 km (display only).",
    ]
    ax.text(0, 1.0, "\n".join(lines), fontsize=8.0, color=MUTED, va="top", linespacing=1.6)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mills", type=Path, default=Path("out/mills_clean.csv"))
    ap.add_argument("--states", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("out/us_wood_mills.png"))
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args()

    for f in list(Path("/usr/share/fonts/opentype/inter").glob("Inter-*.otf")) + \
             list(Path("/usr/share/fonts/truetype/crosextra").glob("Caladea-*.ttf")):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]

    df = pd.read_csv(a.mills)
    d = prepare(df)
    feats = load_states(a.states) if a.states else None

    # ---- page geometry in inches, measured from the top edge
    W, H = 16.0, 14.6
    fig = plt.figure(figsize=(W, H), facecolor=PAGE)

    def rect(left, top, width, height):          # inches -> figure fractions
        return [left / W, 1 - (top + height) / H, width / W, height / H]

    map_top, map_w, map_h = 1.35, 10.48, 7.29
    fig.text(0.5, 1 - 0.55 / H, "US wood mills", fontfamily="Caladea", fontweight="bold", fontsize=46,
             color=INK, ha="center", va="center")
    fig.text(0.5, 1 - 1.05 / H, tracked("A working sample, not a census"), fontsize=9.4, fontweight="semibold",
             color=MUTED, ha="center", va="center")

    ax = fig.add_axes(rect(0.19, map_top, map_w, map_h))
    ax.set_facecolor(PAGE)
    ax.set_aspect("equal")
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.axis("off")
    fw, fh = XLIM[1] - XLIM[0], YLIM[1] - YLIM[0]
    ax.add_patch(plt.Rectangle((XLIM[0], YLIM[0]), fw, fh, fc=OCEAN, ec="none", zorder=0.1))
    ax.add_patch(plt.Rectangle((XLIM[0], YLIM[0]), fw, fh, fill=False, ec=INK, lw=1.1, zorder=9, clip_on=False))
    if feats:
        draw_states(ax, feats)
    else:
        ax.text(0, 0, "DRAFT: state boundaries not loaded", ha="center", va="center", fontsize=15, color=MUTED, alpha=0.5)
    graticule(ax)
    scale_bar(ax, *SCALE_ORIGIN)
    extent_boxes(ax)
    plot_mills(ax, d)
    for (bx0, by0, bx1, by1), name in ((AK_BOX, "Alaska"), (HI_BOX, "Hawaii")):
        ax.add_patch(plt.Rectangle((bx0, by0), bx1 - bx0, by1 - by0, fc=OCEAN, ec="none", zorder=0.2))
        ax.add_patch(plt.Rectangle((bx0, by0), bx1 - bx0, by1 - by0, fill=False, ec=INK, lw=0.9, zorder=9))
        ax.text(bx0, by0 - 0.025e6, name, fontsize=8.4, fontweight="semibold", color=INK2, ha="left", va="top")
    if int((d["state"] == "HI").sum()) == 0:  # an empty inset must not read as "checked, none found"
        ax.text((HI_BOX[0] + HI_BOX[2]) / 2, HI_BOX[3] - 0.03e6, "No records\nin this sample", fontsize=7.9,
                color=MUTED, ha="center", va="top", linespacing=1.3, zorder=6)
    inset_scale_bar(ax, *INSET_BAR_XY)

    side_panel(fig.add_axes(rect(11.28, map_top, 4.4, map_h)), d, map_h)

    # ---- enlarged frames: one justified row, west to east
    if feats:
        zh, ztop, gap, left = 2.85, 8.92, 0.10, 0.19
        widths = [zh * (z["box"][2] - z["box"][0]) / (z["box"][3] - z["box"][1]) for z in ZOOMS]
        total = sum(widths) + gap * (len(ZOOMS) - 1)
        assert total <= 15.62, f"zoom row too wide: {total:.2f} in"
        extra = (15.62 - total) / (len(ZOOMS) - 1)          # justify the row to the page margins
        x = left
        for z, w in zip(ZOOMS, widths):
            zoom_panel(fig, rect(x, ztop, w, zh), z, d, feats)
            x += w + gap + extra

    notes_band(fig.add_axes(rect(0.19, 12.22, 15.62, 1.55)), d, df)
    footer(fig.add_axes(rect(0.19, 13.95, 15.62, 0.6)))

    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, dpi=a.dpi, facecolor=PAGE)
    print(f"wrote {a.out}  ({len(d)} mills plotted)")


if __name__ == "__main__":
    main()
