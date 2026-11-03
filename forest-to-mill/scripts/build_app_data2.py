"""Build app_data.json (v2): v1 content + NLCD canopy per hex, canopy-weighted removals, and the 2 km canopy raster."""
import json, base64, os
import numpy as np, pandas as pd
d = json.load(open('app_data.json'))                       # v1 (edges, hexes, mills, states, labels, grat)
R = "../forest_to_mill_package/source/"
hx = pd.read_csv(R + "hexes.csv").set_index("hex_id")
cn = pd.read_csv("canopy_hex.csv").set_index("hex_id")
rows = d['hexes']                                          # [id,x,y,county,state,rem,ff,km2,isF,routes]
fips = np.array([int(hx.loc[r[0], "county_fips"]) for r in rows])
can = np.array([float(cn.loc[r[0], "canopy_mean"]) for r in rows])
remE = np.array([np.nan if r[5] is None else r[5] for r in rows], float)
remC = remE.copy()
for f in np.unique(fips):
    idx = np.where((fips == f) & np.isfinite(remE))[0]
    if len(idx) < 2: continue
    tot = remE[idx].sum(); w = np.nan_to_num(can[idx])
    if w.sum() <= 0: continue
    remC[idx] = tot * w / w.sum()
print("county totals preserved: even %.1f vs canopy %.1f M ft3" % (np.nansum(remE), np.nansum(remC)))
mv = np.nansum(np.abs(remC - remE)) / 2
print("wood moved between hexes: %.0f M ft3 (%.1f%% of total)" % (mv, mv / np.nansum(remE) * 100))
for r, c, rc in zip(rows, can, remC):
    r.append(int(round(c)))
    r.append(None if not np.isfinite(rc) else round(float(rc), 2))
meta = json.load(open('canopy_meta.json'))
d['can'] = dict(png=base64.b64encode(open('canopy_2km_q.png', 'rb').read()).decode(), x0=meta['x0'], y1=meta['y1'], cell=meta['cell_km'], w=meta['w'], h=meta['h'], year=meta['year'])
json.dump(d, open('app_data2.json', 'w'), separators=(',', ':'))
print("app_data2.json MB", round(os.path.getsize('app_data2.json') / 1e6, 2))
