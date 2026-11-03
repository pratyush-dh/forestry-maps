import numpy as np, pandas as pd
from PIL import Image
R = "../forest_to_mill_package/source/"
h = pd.read_csv(R + "hexes.csv"); c = pd.read_csv("canopy_hex.csv")
m = h.merge(c, on="hex_id")
S = {40, 48, 5, 22, 28, 1, 47, 21, 13, 12, 45, 37, 51}
m = m[(m.county_fips // 1000).isin(S) & m.on_land].copy()
print("study hexes:", len(m), "| with canopy:", m.canopy_mean.notna().sum())
m["fia"] = m.forest_frac * 100
print("Spearman(canopy mean, FIA county forest share):", round(m[["canopy_mean", "fia"]].corr("spearman").iloc[0, 1], 2))
print("Pearson:", round(m[["canopy_mean", "fia"]].corr().iloc[0, 1], 2))
# within-county variation: how much does canopy vary between hexes of the same county? (what FIA-uniform apportionment ignores)
g = m.groupby("county_fips").canopy_mean
cv = (g.std() / g.mean()).dropna()
print("within-county canopy spread: median CV %.2f; counties with >=3 hexes: %d; share with CV>0.3: %.0f%%" % (cv.median(), (g.count() >= 3).sum(), (cv > .3).mean() * 100))
print("mean canopy of FIA 'forest' hexes (county >=20%%): %.1f | non-forest hexes: %.1f" % (m[m.is_forest].canopy_mean.mean(), m[~m.is_forest].canopy_mean.mean()))
big = m[(m.fia >= 20) & (m.canopy_mean < 10)]
print("FIA-forest hexes with mean canopy <10%%: %d (%.1f%% of forest hexes) e.g. %s" % (len(big), len(big) / m.is_forest.sum() * 100, big.county.head(4).tolist()))
low = m[(m.fia < 20) & (m.canopy_mean >= 30)]
print("non-forest hexes with mean canopy >=30%%: %d e.g. %s" % (len(low), low.county.head(4).tolist()))
# smaller PNG: 16 grey levels (6.25% steps)
a = np.array(Image.open("canopy_2km.png"))
q = np.round(a / 255 * 16).astype(np.uint8) * 16
q[q > 255] = 255
Image.fromarray(q.astype(np.uint8), "L").save("canopy_2km_q.png", optimize=True)
import os; print("2km png: %d KB -> quantised %d KB" % (os.path.getsize("canopy_2km.png") // 1024, os.path.getsize("canopy_2km_q.png") // 1024))
