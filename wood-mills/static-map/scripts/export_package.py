#!/usr/bin/env python3
"""Export the data layers and symbology rules behind the static US wood-mills map.

Writes (stdlib only; no GDAL/fiona needed):
  data/lonlat/          true lon/lat (WGS84) layers: mills, states, graticule  -> .geojson + .shp set
  data/map_projected/   the exact geometry drawn on the map, in metres in the map's
                        spherical Albers CRS (Alaska inset and co-located offsets applied)
  symbology/            symbology.json (machine-readable), symbology.md, mills_status_shape.qml (QGIS)
  source/ scripts/      inputs and the scripts that built everything
  us_wood_mills.png     the finished map

Usage:
    python export_package.py --mills out/mills_clean.csv --states data/us-states.geojson \
        --outdir out/package
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import uuid
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import make_static_map as ms

WGS84_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
ALBERS_PRJ = ('PROJCS["US_Wood_Mills_Albers_Sphere",GEOGCS["GCS_Sphere",DATUM["D_Sphere",'
              'SPHEROID["Sphere",6371008.8,0.0]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
              'PROJECTION["Albers"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
              'PARAMETER["Central_Meridian",-96.0],PARAMETER["Standard_Parallel_1",29.5],'
              'PARAMETER["Standard_Parallel_2",45.5],PARAMETER["Latitude_Of_Origin",37.5],UNIT["Meter",1.0]]')

LEGEND = {
    "filled": "No closure recorded (operating status not confirmed)",
    "ring_verified": "Closed, closure year verified",
    "ring_approx": "Closed, closure year approximate",
    "hatched": "Idled or largely shut",
    "dashed": "Status unknown (startup not confirmed)",
}
STATUS_RULE = {  # derivation of status_class from the pipeline fields
    "filled": "operational_status IN ('open','partial','reopened')",
    "ring_verified": "operational_status = 'closed' AND status_confidence = 'verified'",
    "ring_approx": "operational_status = 'closed' AND status_confidence <> 'verified'",
    "hatched": "operational_status = 'idled'",
    "dashed": "operational_status = 'unknown'",
}
# (shapefile field, geojson key, dbf type, width)
MILL_FIELDS = [
    ("mill_id", "mill_id", "C", 60), ("name", "name", "C", 60), ("company", "company", "C", 80),
    ("city", "city", "C", 40), ("state", "state", "C", 2), ("mill_type", "mill_type", "C", 10),
    ("shape_grp", "shape_group", "C", 12), ("op_status", "operational_status", "C", 10),
    ("confidence", "status_confidence", "C", 12), ("status_cls", "status_class", "C", 14),
    ("legend", "legend_label", "C", 60), ("opened", "open", "N", 6), ("closed", "close", "N", 6),
    ("checked", "checked", "N", 2), ("cap_label", "capacity_label", "C", 24), ("in_map", "in_map", "C", 1),
    ("review", "needs_review", "C", 1), ("reasons", "review_reasons", "C", 120), ("note", "note", "C", 254),
]


# ------------------------------------------------------------------ writers
def _ring_area(r):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1])) / 2


def _closed(r):
    r = [tuple(p) for p in r]
    return r if r[0] == r[-1] else r + [r[0]]


def _orient(rings):
    """Shapefile polygon rule: outer rings clockwise, holes counter-clockwise."""
    out = []
    for i, r in enumerate(rings):
        r = _closed(r)
        a = _ring_area(r[:-1])
        want_cw = i == 0
        out.append(r[::-1] if (a > 0) == want_cw else r)
    return out


def write_dbf(path: Path, fields, rows) -> None:
    n = len(rows)
    reclen = 1 + sum(f[2] for f in fields)
    hdr = 32 + 32 * len(fields) + 1
    out = bytearray(struct.pack("<BBBBIHH20x", 3, 126, 11, 1, n, hdr, reclen))
    for name, typ, width, dec in fields:
        out += struct.pack("<11sc4xBB14x", name.encode("ascii")[:10], typ.encode(), width, dec)
    out += b"\r"
    for row in rows:
        out += b" "
        for (name, typ, width, dec), v in zip(fields, row):
            if typ == "N":
                s = "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(int(v))
                out += s.rjust(width).encode()[:width]
            else:
                b = ("" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)).encode("utf-8")[:width]
                out += b.ljust(width)
    out += b"\x1a"
    path.write_bytes(bytes(out))


def write_shapefile(base: Path, kind: str, geoms, fields, rows, prj: str) -> None:
    """kind: point (x,y) | line [parts] | polygon [rings]. Writes .shp .shx .dbf .prj .cpg."""
    stype = {"point": 1, "line": 3, "polygon": 5}[kind]
    recs, xs, ys = [], [], []
    for g in geoms:
        if kind == "point":
            recs.append(struct.pack("<idd", 1, g[0], g[1]))
            xs.append(g[0])
            ys.append(g[1])
        else:
            parts = _orient(g) if kind == "polygon" else [[tuple(p) for p in part] for part in g]
            pts = [p for part in parts for p in part]
            starts, k = [], 0
            for part in parts:
                starts.append(k)
                k += len(part)
            bx, by = [p[0] for p in pts], [p[1] for p in pts]
            recs.append(struct.pack("<i4dii", stype, min(bx), min(by), max(bx), max(by), len(parts), len(pts))
                        + struct.pack(f"<{len(parts)}i", *starts)
                        + b"".join(struct.pack("<dd", *p) for p in pts))
            xs += bx
            ys += by
    bbox = (min(xs), min(ys), max(xs), max(ys))

    def header(nbytes):
        return struct.pack(">7i", 9994, 0, 0, 0, 0, 0, nbytes // 2) + struct.pack("<2i", 1000, stype) \
            + struct.pack("<8d", *bbox, 0, 0, 0, 0)

    shp = bytearray()
    shx = bytearray()
    off = 50
    for i, c in enumerate(recs):
        shp += struct.pack(">2i", i + 1, len(c) // 2) + c
        shx += struct.pack(">2i", off, len(c) // 2)
        off += (8 + len(c)) // 2
    base.with_suffix(".shp").write_bytes(header(100 + len(shp)) + bytes(shp))
    base.with_suffix(".shx").write_bytes(header(100 + len(shx)) + bytes(shx))
    write_dbf(base.with_suffix(".dbf"), fields, rows)
    base.with_suffix(".prj").write_text(prj)
    base.with_suffix(".cpg").write_text("UTF-8")


def write_geojson(path: Path, feats: list[dict], name: str, lonlat: bool) -> None:
    fc = {"type": "FeatureCollection", "name": name, "features": feats}
    if lonlat:
        fc["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}
    path.write_text(json.dumps(fc, ensure_ascii=False))


def clean(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def dbf_fields(spec, rows):
    out = []
    for j, (nm, _, typ, w) in enumerate(spec):
        if typ == "C":
            w = max(1, min(w, max((len(str(r[j] or "").encode("utf-8")) for r in rows), default=1)))
        out.append((nm, typ, w, 0))
    return out


# ------------------------------------------------------------------- layers
def mills_layer(dall: pd.DataFrame, projected: bool):
    d = dall[dall["in_map"] == "Y"] if projected else dall
    feats, geoms, rows = [], [], []
    for _, r in d.iterrows():
        props = {gk: clean(r[gk]) for _, gk, _, _ in MILL_FIELDS}
        for k in ("open", "close", "checked"):
            props[k] = None if props[k] is None else int(props[k])
        xy = (round(float(r["x"]), 1), round(float(r["y"]), 1)) if projected else \
             (round(float(r["lon"]), 6), round(float(r["lat"]), 6))
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(xy)}, "properties": props})
        geoms.append(xy)
        rows.append([props[gk] for _, gk, _, _ in MILL_FIELDS])
    return feats, geoms, rows


def states_layers(states_path: Path):
    gj = json.loads(states_path.read_text())
    ll, pj = [], []
    for f in gj["features"]:
        fips = str(f.get("id") or f["properties"].get("STATEFP") or "").zfill(2)
        name = f["properties"].get("name", "")
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        in_map = fips not in (ms.NON_CONUS_FIPS - {"02", "15"})
        ll.append(dict(fips=fips, name=name, in_map="Y" if in_map else "N", polys=polys))
        if in_map:
            proj = {"02": ms.alaska, "15": ms.hawaii}.get(fips, ms.conus)
            pp = []
            for poly in polys:
                if fips == "02" and not ms.fits_ak_box(poly):
                    continue  # same rule as the drawing: far-west Aleutians fall outside the inset box
                rings = []
                for ring in poly:
                    arr = np.array(ring)[:, :2]
                    x, y = proj(arr[:, 0], arr[:, 1])
                    rings.append([(round(float(a), 1), round(float(b), 1)) for a, b in zip(x, y)])
                pp.append(rings)
            pj.append(dict(fips=fips, name=name, in_map="Y", polys=pp))
    return ll, pj


def polygon_feats(items):
    feats, geoms, rows = [], [], []
    for it in items:
        polys = it["polys"]
        geom = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else \
               {"type": "MultiPolygon", "coordinates": polys}
        props = {"fips": it["fips"], "name": it["name"], "in_map": it["in_map"]}
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
        geoms.append([r for poly in polys for r in _orient_poly_group(poly)])
        rows.append([props["fips"], props["name"], props["in_map"]])
    return feats, geoms, rows


def _orient_poly_group(poly):
    """Orient one polygon (outer + holes); returned flat list of rings for the shapefile record."""
    return _orient([[tuple(p[:2]) for p in r] for r in poly])


def graticule_layers(step: int = 10):
    ll, pj = [], []
    for kind, rng in (("lat", range(30, 61, step)), ("lon", range(-140, -49, step))):
        for v in rng:
            if kind == "lat":
                lon, lat = np.linspace(-140, -50, 500), np.full(500, float(v))
                label = f"{v}°N"
            else:
                lon, lat = np.full(500, float(v)), np.linspace(18, 58, 500)
                label = f"{abs(v)}°W"
            ll.append(dict(kind=kind, value=v, label=label,
                           parts=[[(round(a, 5), round(b, 5)) for a, b in zip(lon, lat)]]))
            x, y = ms._visible(*ms.conus(lon, lat))  # same mask as the drawn map
            parts, cur = [], []
            for a, b in zip(x, y):
                if np.isnan(a):
                    if len(cur) > 1:
                        parts.append(cur)
                    cur = []
                else:
                    cur.append((round(float(a), 1), round(float(b), 1)))
            if len(cur) > 1:
                parts.append(cur)
            if parts:
                pj.append(dict(kind=kind, value=v, label=label, parts=parts))
    return ll, pj


def line_feats(items):
    feats, geoms, rows = [], [], []
    for it in items:
        parts = it["parts"]
        geom = {"type": "LineString", "coordinates": parts[0]} if len(parts) == 1 else \
               {"type": "MultiLineString", "coordinates": parts}
        props = {"kind": it["kind"], "value": it["value"], "label": it["label"]}
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
        geoms.append(parts)
        rows.append([props["kind"], props["value"], props["label"]])
    return feats, geoms, rows


def furniture_layer():
    """Frame, Alaska inset box and scale-bar segments, in map metres."""
    items = []

    def rect(x0, y0, x1, y1):
        return [[(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)]]

    items.append(("map_frame", "Main map bounding box", rect(ms.XLIM[0], ms.YLIM[0], ms.XLIM[1], ms.YLIM[1])))
    for z in ms.ZOOMS:
        items.append(("zoom_extent", f"{z['tag']} {z['name']} (enlarged frame)", rect(*z["box"])))
    items.append(("inset_box", "Alaska inset (reduced scale)", rect(*ms.AK_BOX)))
    items.append(("inset_box", "Hawaii inset (reduced scale)", rect(*ms.HI_BOX)))
    sx, sy = ms.SCALE_ORIGIN
    for i in range(4):
        items.append(("scalebar", f"main map {i * 250}-{(i + 1) * 250} km", rect(sx + i * 250e3, sy, sx + (i + 1) * 250e3, sy + 0.042e6)))
    ix, iy = ms.INSET_BAR_XY
    seg = 500e3 * ms.AK_SCALE
    for i in range(2):
        items.append(("inset_scalebar", f"inset {i * 500}-{(i + 1) * 500} km", rect(ix + i * seg, iy, ix + (i + 1) * seg, iy + 0.03e6)))
    feats, geoms, rows = [], [], []
    for el, lab, poly in items:
        poly = [[(round(x, 1), round(y, 1)) for x, y in poly[0]]]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": poly},
                      "properties": {"element": el, "label": lab}})
        geoms.append(poly)
        rows.append([el, lab])
    return feats, geoms, rows


# ---------------------------------------------------------------- symbology
def hex_rgba(h: str, a: float = 1.0) -> str:
    h = h.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{int(round(a * 255))}"


QGIS_MARKER = {"o": "circle", "s": "square", "^": "triangle", "D": "diamond", "*": "star"}


def pt2_to_mm(s: float) -> float:
    return round((s ** 0.5) * 0.3528, 2)


def build_symbology(d: pd.DataFrame) -> dict:
    cnt = d["cls"].value_counts().to_dict()
    shp = d["shape"].value_counts().to_dict()
    order = ["ring_approx", "ring_verified", "filled", "hatched", "dashed"]
    classes = []
    for i, c in enumerate(order):
        k = ms.STATUS[c]
        classes.append(dict(
            id=c, label=LEGEND[c], derive_from=STATUS_RULE[c], count=int(cnt.get(c, 0)), draw_order=i + 1,
            face=("none" if k.get("facecolors") == "none" else k.get("facecolors", k.get("c"))),
            outline=k["edgecolors"], outline_width_pt=round(k["linewidths"] * ms.LW_K, 3),
            outline_width_pt_enlarged_frames=round(k["linewidths"] * ms.ZOOM_LW_K, 3), alpha=k.get("alpha", 1.0),
            hatch=k.get("hatch"), outline_style="dashed" if k.get("linestyles") == "--" else "solid"))
    shapes = [dict(group=g, label=lab, matplotlib_marker=mk, qgis_marker=QGIS_MARKER[mk], size_pt2=round(s * ms.SIZE_K, 1),
                   size_pt2_enlarged_frames=round(s * ms.ZOOM_SIZE_K, 1), size_pt2_unscaled=s,
                   size_mm=pt2_to_mm(s * ms.SIZE_K), count=int(shp.get(g, 0)),
                   mill_types=[t for t, gg in ms.TYPE_TO_SHAPE.items() if gg == g])
              for g, (mk, s, lab) in ms.SHAPES.items()]
    return {
        "map": "US wood mills: a working sample, not a census", "generated": str(date.today()),
        "principle": "Colour carries STATUS only (2 validated hues + neutral gray); SHAPE carries mill type; "
                     "fill style repeats colour so colour is never the only cue. Capacity is not mapped.",
        "crs": {"lonlat_layers": "EPSG:4326 (WGS84)", "projected_layers": {
            "name": "US_Wood_Mills_Albers_Sphere (custom; see .prj)", "projection": "Albers equal-area conic, spherical",
            "standard_parallels": [29.5, 45.5], "latitude_of_origin": 37.5, "central_meridian": -96.0,
            "sphere_radius_m": ms.R, "units": "metre",
            "alaska_inset": {"projection": "Albers", "standard_parallels": [55, 65], "origin": [50, -154],
                             "scale": ms.AK_SCALE, "lower_left_m": list(ms.AK_LL), "box_m": [round(v, 1) for v in ms.AK_BOX]},
            "hawaii_inset": {"projection": "Albers", "standard_parallels": [8, 18], "origin": [3, -157],
                             "scale": ms.HI_SCALE, "box_m": [round(v, 1) for v in ms.HI_BOX],
                             "records_in_sample": 0, "note": "drawn with a 'No records in this sample' label"},
            "inset_scale_bar": {"length_km": 1000, "segments": 2, "drawn_length_m": 1000e3 * ms.AK_SCALE,
                                "lower_left_m": [round(v, 1) for v in ms.INSET_BAR_XY],
                                "note": "one bar serves both insets; drawn length = km x 0.35"},
            "scale_distortion": "parallels 0.990-1.015; max +/-1.5% across the lower 48"}},
        "layout": {"figure_in": [16, 10.8], "export_dpi": 200, "map_extent_m": {"x": list(ms.XLIM), "y": list(ms.YLIM)},
                   "colocated_display_offset_m": 22000},
        "palette": {"page": ms.PAGE, "ocean": ms.OCEAN, "land": ms.LAND, "state_border": ms.BORDER, "graticule": ms.GRID,
                    "ink": ms.INK, "ink_secondary": ms.INK2, "muted": ms.MUTED, "rule": ms.RULE,
                    "status_blue": ms.BLUE, "status_orange": ms.ORANGE, "status_gray": ms.GRAY, "shape_ink": ms.SHAPE_INK},
        "palette_validation": {"tool": "dataviz validate_palette.js", "colors": [ms.BLUE, ms.ORANGE], "mode": "light",
                               "surface": ms.LAND, "pairs": "all",
                               "cvd_worst_dE": 24.7, "tritan_worst_dE": 32.7, "normal_vision_dE": 33.6,
                               "contrast_vs_surface": ">= 3:1", "result": "ALL CHECKS PASS"},
        "symbol_scaling": {"main_map_area_factor": ms.SIZE_K, "main_map_outline_factor": ms.LW_K,
                           "enlarged_frames_area_factor": ms.ZOOM_SIZE_K, "enlarged_frames_outline_factor": ms.ZOOM_LW_K,
                           "note": "size_pt2 in shapes is already scaled for the main map; enlarged frames use the *_enlarged_frames values"},
        "enlarged_frames": {"purpose": "show areas where symbols overlap on the main map",
                            "extent_indicator": "ink rectangle + letter chip on the main map", "grid_deg": 5,
                            "state_labels": "USPS abbreviations, muted", "scale_bar": "own bar below each frame",
                            "display_nudge": "marks closer than one circle-symbol diameter are pushed apart (max 0.6 x diameter, "
                                             "about 10 km), display only; not applied to any exported coordinates",
                            "frames": [dict(tag=z["tag"], name=z["name"], box_m=[round(v) for v in z["box"]],
                                            scale_bar_km=z["km"]) for z in ms.ZOOMS]},
        "status_classes": classes, "shapes": shapes,
        "layers": {
            "graticule": {"interval_deg": 10, "colour": ms.GRID, "width_pt": 0.8, "drawn": "under the land polygons (z 0.6 < 1)",
                          "labels": "Inter 8.2 pt, muted; parallels on the Atlantic edge, meridians on the top edge"},
            "land": {"fill": ms.LAND, "border": ms.BORDER, "border_width_pt": 0.7},
            "ocean": {"fill": ms.OCEAN}, "frame": {"colour": ms.INK, "width_pt": 1.1, "note": "bounding box of the main map"},
            "inset_box": {"colour": ms.INK, "width_pt": 0.9, "fill": ms.OCEAN, "applies_to": ["Alaska", "Hawaii"]},
            "scale_bar": {"length_km": 1000, "segments": 4, "colours": [ms.INK, ms.LAND], "also_in_miles": "621 mi",
                          "note": "Lower 48 only; equal-area, scale varies +/-1.5%"}},
        "typography": [
            dict(role="Title", family="Caladea", weight="Bold", size_pt=46, colour=ms.INK, align="centre"),
            dict(role="Deck", family="Inter", weight="SemiBold", size_pt=9.4, colour=ms.MUTED, note="UPPERCASE, faux-tracked"),
            dict(role="Headline sentence", family="Caladea", weight="Regular", size_pt=17.5, colour=ms.INK, line_height=1.2),
            dict(role="Section label", family="Inter", weight="SemiBold", size_pt=8.4, colour=ms.MUTED, note="UPPERCASE, faux-tracked"),
            dict(role="Legend label", family="Inter", weight="Regular", size_pt=11.5, colour=ms.INK),
            dict(role="Legend count", family="Inter", weight="Medium", size_pt=11.5, colour=ms.INK2, align="right"),
            dict(role="Legend sub-label", family="Inter", weight="Regular", size_pt=9.3, colour=ms.MUTED),
            dict(role="Caveat lead-in", family="Inter", weight="SemiBold", size_pt=10.6, colour=ms.INK),
            dict(role="Caveat body", family="Inter", weight="Regular", size_pt=9.7, colour=ms.INK2, line_height=1.4),
            dict(role="Map labels (graticule, scale bar, inset)", family="Inter", weight="Regular", size_pt="7.9-8.4", colour=ms.MUTED),
            dict(role="Footer", family="Inter", weight="Regular", size_pt=8.0, colour=ms.MUTED, line_height=1.55)],
        "status_derivation_note": "status_class derives from the pipeline fields operational_status and status_confidence; "
                                  "see source/qa_report.md. 'checked=1' verifies the CLOSURE YEAR only.",
    }


def symbology_md(sym: dict) -> str:
    L = [f"# Symbology rules: {sym['map']}", "", sym["principle"], "",
         "## Status (colour + fill style)", "",
         "| Class | Legend | Derive from | Face | Outline | Width pt | Alpha | Style | Count |", "|---|---|---|---|---|---|---|---|---|"]
    for c in sym["status_classes"]:
        style = c["outline_style"] + (f", hatch {c['hatch']}" if c["hatch"] else "")
        L.append(f"| {c['id']} | {c['label']} | `{c['derive_from']}` | {c['face']} | {c['outline']} | {c['outline_width_pt']} | {c['alpha']} | {style} | {c['count']} |")
    L += ["", "Draw order (bottom to top): " + ", ".join(c["id"] for c in sym["status_classes"]) + ".", "",
          "## Shape (mill type)", "", "| Group | Marker | Size pt2 (~mm) | Mill types | Count |", "|---|---|---|---|---|"]
    for s in sym["shapes"]:
        L.append(f"| {s['label']} | {s['qgis_marker']} (`{s['matplotlib_marker']}`) | {s['size_pt2']} (~{s['size_mm']}) | {', '.join(s['mill_types'])} | {s['count']} |")
    pv = sym["palette_validation"]
    L += ["", "## Colour validation", "",
          f"Blue `{ms.BLUE}` and orange `{ms.ORANGE}` validated on land `{pv['surface']}` with `--pairs all` "
          f"(map = scatter form): CVD worst dE {pv['cvd_worst_dE']}, tritan {pv['tritan_worst_dE']}, normal vision "
          f"{pv['normal_vision_dE']}, contrast {pv['contrast_vs_surface']}. Gray `{ms.GRAY}` is a neutral for 'unknown', not a series.",
          "", "## Palette", ""] + [f"- {k}: `{v}`" for k, v in sym["palette"].items()]
    L += ["", "## Furniture", ""] + [f"- **{k}**: {json.dumps(v)}" for k, v in sym["layers"].items()]
    L += ["", "## Projection", "", f"```json\n{json.dumps(sym['crs'], indent=2)}\n```", "", "## Typography", "",
          "| Role | Family | Weight | Size pt | Colour | Notes |", "|---|---|---|---|---|---|"]
    for t in sym["typography"]:
        note = ", ".join(f"{k} {v}" for k, v in t.items() if k in ("align", "line_height", "note"))
        L.append(f"| {t['role']} | {t['family']} | {t['weight']} | {t['size_pt']} | `{t['colour']}` | {note} |")
    L += ["", f"_{sym['status_derivation_note']}_", ""]
    return "\n".join(L)


def qgis_qml(sym: dict) -> str:
    """Rule-based marker style: status_class x shape_group. Hatch is approximated (QGIS needs a 2nd symbol layer)."""
    symbols, rules = [], []
    for ci, c in enumerate(sym["status_classes"]):
        for si, s in enumerate(sym["shapes"]):
            sid = ci * len(sym["shapes"]) + si
            face = "0,0,0,0" if c["face"] == "none" else hex_rgba(c["face"], c["alpha"] if c["id"] == "filled" else 1.0)
            out_a = c["alpha"] if c["id"] == "ring_approx" else 1.0
            style = "dash" if c["outline_style"] == "dashed" else "solid"
            size = s["size_mm"]
            wmm = round(c["outline_width_pt"] * 0.3528, 2)
            symbols.append(f"""      <symbol type="marker" name="{sid}" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="{ci}">
          <Option type="Map">
            <Option name="angle" type="QString" value="0"/>
            <Option name="color" type="QString" value="{face}"/>
            <Option name="name" type="QString" value="{s['qgis_marker']}"/>
            <Option name="outline_color" type="QString" value="{hex_rgba(c['outline'], out_a)}"/>
            <Option name="outline_style" type="QString" value="{style}"/>
            <Option name="outline_width" type="QString" value="{wmm}"/>
            <Option name="outline_width_unit" type="QString" value="MM"/>
            <Option name="size" type="QString" value="{size}"/>
            <Option name="size_unit" type="QString" value="MM"/>
          </Option>
        </layer>
      </symbol>""")
            flt = f""""status_class" = '{c['id']}' AND "shape_group" = '{s['group']}'"""
            label = f"{c['label']} | {s['label']}"
            rules.append(f"""      <rule key="{{{uuid.uuid4()}}}" symbol="{sid}" filter="{flt.replace('"', '&quot;').replace("'", '&apos;')}" label="{label.replace('&', '&amp;')}"/>""")
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="Symbology">
  <renderer-v2 type="RuleRenderer" symbollevels="1" enableorderby="0" forceraster="0">
    <rules key="{{{uuid.uuid4()}}}">
{chr(10).join(rules)}
    </rules>
    <symbols>
{chr(10).join(symbols)}
    </symbols>
  </renderer-v2>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
</qgis>
"""


README = """# US wood mills: data and symbology package

A working sample, not a census. See symbology/symbology.md for how every mark is encoded and
source/qa_report.md for the data-quality findings.

## data/lonlat  (EPSG:4326, WGS84)
True coordinates for use in your own GIS. `mills` has all 196 records (`in_map` = Y when the record is drawn on the map); `states` is the source
outline (low resolution); `graticule_10deg` is unclipped.

## data/map_projected  (custom spherical Albers, metres; see the .prj)
The exact geometry drawn on the PNG: Alaska and Hawaii are moved into insets (0.35x the main-map scale;
Hawaii has no records in the sample), the five enlarged-frame extents (A to E) are in `map_furniture`, co-located mills are
offset ~22 km for legibility, the graticule is clipped the way it is drawn, and `map_furniture` holds
the frame, both inset boxes and the scale-bar segments (main map and shared inset bar). Set the QGIS project CRS to this layer's CRS to reproduce
the layout. These positions are for display only; use data/lonlat for analysis.

## Formats
Every layer is both .geojson (full attribute text) and a shapefile set (.shp .shx .dbf .prj .cpg).
DBF fields are limited to 254 characters, so very long `note` values are truncated there only.
The shapefiles were written by a small stdlib writer and re-read for validation, but they were not
opened in QGIS or ArcGIS in the build environment.

## symbology
- symbology.json: machine-readable rules (classes, colours, sizes, typography, projection, validation)
- symbology.md: the same, readable
- mills_status_shape.qml: QGIS rule-based style for the mills layers (status_class x shape_group).
  Not tested in QGIS. The hatched (idled) class is approximated as a filled orange marker.
  Load via Layer Properties > Symbology > Style > Load Style.

## source / scripts
Alaska polygons that do not fit the inset box (far-west Aleutians) are not drawn or exported in map_projected; data/lonlat keeps them.
Marks in the enlarged frames are nudged apart for display (up to ~10 km); no exported coordinate includes that nudge.
`source/mills_raw.csv` is the unmodified input. `scripts/` rebuilds everything:
`build_mills.py` (cleaning, status model, QA), `make_static_map.py` (the map),
`export_package.py` (this package). Fonts used: Inter and Caladea.
"""


# --------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mills", type=Path, default=Path("out/mills_clean.csv"))
    ap.add_argument("--states", type=Path, default=Path("data/us-states.geojson"))
    ap.add_argument("--outdir", type=Path, default=Path("out/package"))
    ap.add_argument("--raw", type=Path, default=Path("raw/mills_raw.csv"))
    ap.add_argument("--png", type=Path, default=Path("out/us_wood_mills.png"))
    a = ap.parse_args()

    if a.outdir.exists():
        shutil.rmtree(a.outdir)
    for sub in ("data/lonlat", "data/map_projected", "symbology", "source", "scripts"):
        (a.outdir / sub).mkdir(parents=True)

    df = pd.read_csv(a.mills)
    d = ms.prepare(df)                              # the 195 drawn records
    tmp = df.copy()
    tmp["in_us_scope"] = True
    dall = ms.prepare(tmp)                          # all 196, classified identically
    dall["in_map"] = np.where(dall["in_us_scope_orig"] if "in_us_scope_orig" in dall else dall["name"].isin(d["name"]), "Y", "N")
    dall["status_class"] = dall["cls"]
    dall["shape_group"] = dall["shape"]
    dall["legend_label"] = dall["cls"].map(LEGEND)
    dall["needs_review"] = np.where(dall["needs_review"], "Y", "N")
    dall["review_reasons"] = dall["review_reasons"].fillna("")
    dall["capacity_label"] = dall["capacity_label"].where(dall["capacity_label"].notna(), None)

    layers = {}
    # mills
    for tag, proj in (("lonlat", False), ("map_projected", True)):
        feats, geoms, rows = mills_layer(dall, proj)
        flds = dbf_fields(MILL_FIELDS, rows)
        base = a.outdir / "data" / tag / ("mills" if not proj else "mills")
        write_geojson(base.with_suffix(".geojson"), feats, "mills", not proj)
        write_shapefile(base, "point", geoms, flds, rows, ALBERS_PRJ if proj else WGS84_PRJ)
        layers[f"{tag}/mills"] = (len(feats), "point")
    # states
    sll, spj = states_layers(a.states)
    for tag, items, proj in (("lonlat", sll, False), ("map_projected", spj, True)):
        feats, geoms, rows = polygon_feats(items)
        flds = dbf_fields([("fips", "fips", "C", 2), ("name", "name", "C", 40), ("in_map", "in_map", "C", 1)], rows)
        base = a.outdir / "data" / tag / "states"
        write_geojson(base.with_suffix(".geojson"), feats, "states", not proj)
        write_shapefile(base, "polygon", geoms, flds, rows, ALBERS_PRJ if proj else WGS84_PRJ)
        layers[f"{tag}/states"] = (len(feats), "polygon")
    # graticule
    gll, gpj = graticule_layers()
    for tag, items, proj in (("lonlat", gll, False), ("map_projected", gpj, True)):
        feats, geoms, rows = line_feats(items)
        flds = dbf_fields([("kind", "kind", "C", 3), ("value", "value", "N", 5), ("label", "label", "C", 8)], rows)
        flds[1] = ("value", "N", 5, 0)
        base = a.outdir / "data" / tag / "graticule_10deg"
        write_geojson(base.with_suffix(".geojson"), feats, "graticule_10deg", not proj)
        write_shapefile(base, "line", geoms, flds, rows, ALBERS_PRJ if proj else WGS84_PRJ)
        layers[f"{tag}/graticule_10deg"] = (len(feats), "line")
    # furniture (projected only)
    feats, geoms, rows = furniture_layer()
    base = a.outdir / "data" / "map_projected" / "map_furniture"
    write_geojson(base.with_suffix(".geojson"), feats, "map_furniture", False)
    write_shapefile(base, "polygon", geoms, dbf_fields([("element", "element", "C", 12), ("label", "label", "C", 40)], rows), rows, ALBERS_PRJ)
    layers["map_projected/map_furniture"] = (len(feats), "polygon")

    # symbology
    sym = build_symbology(d)
    sdir = a.outdir / "symbology"
    (sdir / "symbology.json").write_text(json.dumps(sym, indent=2, ensure_ascii=False))
    (sdir / "symbology.md").write_text(symbology_md(sym))
    (sdir / "mills_status_shape.qml").write_text(qgis_qml(sym))

    # source, scripts, png, readme
    shutil.copy(a.raw, a.outdir / "source" / "mills_raw.csv")
    for f in (a.mills, a.mills.parent / "mills_clean.geojson", a.mills.parent / "mill_events.csv", a.mills.parent / "qa_report.md"):
        shutil.copy(f, a.outdir / "source" / f.name)
    for f in ("build_mills.py", "make_static_map.py", "export_package.py"):
        shutil.copy(Path(__file__).with_name(f), a.outdir / "scripts" / f)
    shutil.copy(a.states, a.outdir / "source" / "us-states_lowres_source.geojson")
    shutil.copy(a.png, a.outdir / "us_wood_mills.png")
    (a.outdir / "README.md").write_text(README)

    zpath = a.outdir.parent / "us_wood_mills_package.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(a.outdir.rglob("*")):
            if f.is_file():
                z.write(f, Path("us_wood_mills_package") / f.relative_to(a.outdir))
    for k, (n, t) in layers.items():
        print(f"{k:40s} {n:4d} {t}")
    print("zip:", zpath, f"{zpath.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
