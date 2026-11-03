"""Fetch NLCD tree canopy cover (USFS TCC v2025-6, NLCD series, 30 m) for the study region, aggregate to
 (a) a 1 km grid in the package's spherical Albers, (b) per-hex mean canopy, (c) a 2 km display raster.
Run from the scratchpad folder. Tiles are cached in tiles/."""
import os, datetime, subprocess, json, sys
import importlib.util
_rb = os.path.dirname(importlib.util.find_spec("rasterio").origin)
_pd = os.path.join(_rb, "proj_data")
if os.path.exists(_pd): os.environ["PROJ_LIB"] = _pd; os.environ["PROJ_DATA"] = _pd
else: os.environ.pop("PROJ_LIB", None); os.environ.pop("PROJ_DATA", None)
import numpy as np, rasterio, geopandas as gpd
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize
from rasterio.crs import CRS as RCRS
from pyproj import CRS, Transformer
from PIL import Image

YEAR = 2021
SVC = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_NLCD_TCC_CONUS/ImageServer/exportImage"
R = "../forest_to_mill_package/"
os.makedirs("tiles", exist_ok=True)
sph = CRS.from_wkt(open(R + "data/map_projected/hexes.prj").read())
to5070 = Transformer.from_crs(sph, "EPSG:5070", always_xy=True)
# study rectangle in sphere-Albers (m), densified, into EPSG:5070
xmin, xmax, ymin, ymax = -1060e3, 1865e3, -1385e3, 405e3
t = np.linspace(0, 1, 60)
bx = np.r_[xmin + t * (xmax - xmin), np.full(60, xmax), xmax - t * (xmax - xmin), np.full(60, xmin)]
by = np.r_[np.full(60, ymin), ymin + t * (ymax - ymin), np.full(60, ymax), ymax - t * (ymax - ymin)]
X, Y = to5070.transform(bx, by)
x0, x1, y0, y1 = [float(v) for v in (np.floor(min(X) / 500) * 500 - 5000, np.ceil(max(X) / 500) * 500 + 5000, np.floor(min(Y) / 500) * 500 - 5000, np.ceil(max(Y) / 500) * 500 + 5000)]
CELL = 500.0
W = int(round((x1 - x0) / CELL)); H = int(round((y1 - y0) / CELL))
print("EPSG:5070 box", x0, y0, x1, y1, "->", W, "x", H, "px at 500 m")
ts = int(datetime.datetime(YEAR, 7, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)

# ---- fetch in 3 x 2 tiles
NX, NY = 3, 2
cw = int(np.ceil(W / NX)); ch = int(np.ceil(H / NY))
mosaic = np.full((H, W), np.nan, np.float32)
for j in range(NY):
    for i in range(NX):
        c0, r0 = i * cw, j * ch; c1, r1 = min(W, c0 + cw), min(H, r0 + ch)
        bb = (x0 + c0 * CELL, y1 - r1 * CELL, x0 + c1 * CELL, y1 - r0 * CELL)
        fn = f"tiles/tcc_{YEAR}_{i}_{j}.tif"
        if not os.path.exists(fn) or os.path.getsize(fn) < 1000:
            url = (f"{SVC}?bbox={bb[0]},{bb[1]},{bb[2]},{bb[3]}&bboxSR=5070&imageSR=5070&size={c1-c0},{r1-r0}&format=tiff&pixelType=U8"
                   f"&interpolation=RSP_NearestNeighbor&time={ts}&f=image")
            for attempt in range(3):
                rc = subprocess.run(["curl", "-sL", "-m", "300", url, "-o", fn, "-w", "%{http_code}"], capture_output=True, text=True)
                if rc.stdout.strip() == "200" and os.path.getsize(fn) > 1000:
                    try:
                        rasterio.open(fn).read(1); break
                    except Exception: pass
                print("  retry tile", i, j, rc.stdout, file=sys.stderr)
        a = rasterio.open(fn).read(1).astype(np.float32)
        assert a.shape == (r1 - r0, c1 - c0), (a.shape, r1 - r0, c1 - c0)
        a[a > 100] = np.nan                      # 254 = non-processing area, 255 = background
        mosaic[r0:r1, c0:c1] = a
        print("tile", i, j, a.shape, "mean %.1f" % np.nanmean(a), flush=True)
print("mosaic valid share %.3f, mean canopy %.1f" % (np.isfinite(mosaic).mean(), np.nanmean(mosaic)))

# ---- aggregate to a 1 km grid in the package's spherical Albers (area-weighted mean of valid pixels)
src_tr = from_origin(x0, y1, CELL, CELL)
G = 1000.0
nx = int((xmax - xmin) / G); ny = int((ymax - ymin) / G)
dst_tr = from_origin(xmin, ymax, G, G)
dst = np.full((ny, nx), np.nan, np.float32)
reproject(mosaic, dst, src_transform=src_tr, src_crs=RCRS.from_epsg(5070), src_nodata=np.nan,
          dst_transform=dst_tr, dst_crs=RCRS.from_wkt(sph.to_wkt()), dst_nodata=np.nan, resampling=Resampling.average)
print("1 km grid", dst.shape, "valid share %.3f" % np.isfinite(dst).mean())
np.save("canopy_1km.npy", dst)

# ---- per-hex statistics
hp = gpd.read_file(R + "data/map_projected/hexes.shp")
ids = hp.hex_id.values
shapes = [(g, int(i) + 1) for i, g in enumerate(hp.geometry)]
lab = rasterize(shapes, out_shape=(ny, nx), transform=dst_tr, fill=0, dtype="int32")
m = lab > 0
val = dst[m]; l = lab[m] - 1
ok = np.isfinite(val)
cnt = np.bincount(l, minlength=len(ids)); vcnt = np.bincount(l[ok], minlength=len(ids))
s = np.bincount(l[ok], weights=val[ok], minlength=len(ids))
ge10 = np.bincount(l[ok], weights=(val[ok] >= 10).astype(float), minlength=len(ids))
mean = np.where(vcnt > 0, s / np.maximum(vcnt, 1), np.nan)
out = np.c_[ids, mean, np.where(vcnt > 0, ge10 / np.maximum(vcnt, 1) * 100, np.nan), vcnt / np.maximum(cnt, 1)]
np.savetxt("canopy_hex.csv", out, delimiter=",", header="hex_id,canopy_mean,pct_ge10,valid_frac", comments="", fmt=["%d", "%.2f", "%.2f", "%.3f"])
print("hexes with canopy: %d of %d | mean of hex means %.1f" % (np.isfinite(mean).sum(), len(ids), np.nanmean(mean)))

# ---- 2 km display raster (8-bit grey, 0 = no data), same geometry
d2 = dst[: ny // 2 * 2, : nx // 2 * 2].reshape(ny // 2, 2, nx // 2, 2)
with np.errstate(all="ignore"):
    d2 = np.nanmean(np.nanmean(d2, axis=3), axis=1)
img = np.nan_to_num(d2, nan=0.0)
Image.fromarray(np.clip(np.round(img * 2.55), 0, 255).astype(np.uint8), "L").save("canopy_2km.png", optimize=True)
json.dump(dict(year=YEAR, x0=xmin / 1000, y1=ymax / 1000, cell_km=2.0, w=int(d2.shape[1]), h=int(d2.shape[0])), open("canopy_meta.json", "w"))
print("2 km raster", d2.shape, os.path.getsize("canopy_2km.png") // 1024, "KB")
