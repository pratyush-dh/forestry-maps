"""Build the interactive page: vor_app_tpl.html + straight-line cells (vor_cells.pkl) + road-time cells (vor_road_s.pkl) + map helpers (app_data_nat.json) -> vor_app.html"""
import json, pickle, numpy as np
S = pickle.load(open("vor_cells.pkl", "rb")); R = pickle.load(open("vor_road_s.pkl", "rb"))
G = json.load(open("app_data_nat.json"))
df = R["df"].reset_index(drop=True)
assert (df.mill_id.values == S["df"].mill_id.values).all()

def rings(g, tol=1.5):
    out = []
    if g.is_empty: return out
    g = g.simplify(tol)
    for p in (g.geoms if g.geom_type in ("MultiPolygon", "GeometryCollection") else [g]):
        if p.geom_type != "Polygon" or p.is_empty: continue
        for ring in [p.exterior] + list(p.interiors):
            a = np.round(np.array(ring.coords)[:-1] * 10).astype(int)
            if len(a) >= 3: out.append(a.ravel().tolist())
    return out

def num(v, d):
    return None if v is None or not np.isfinite(v) else round(float(v), d)
sites = []
for i, r in df.iterrows():
    sites.append([r["name"], r["company"] if isinstance(r["company"], str) else "", r["state"], r["mill_type"], round(r["x"], 1), round(r["y"], 1), int(r["n_mills"]),
                  num(r["area_straight"], 0), num(r["supply_straight"], 1), num(r["dens_straight"], 2), num(r["area_road"], 0), num(r["supply_road"], 1), num(r["dens_road"], 2),
                  num(r["alloc_day2"], 1), num(r["share_of_straight_cell_kept"], 3), num(r["wood_minutes_to_mill"], 0), r["mill_id"]])
d_area = df.area_road - df.area_straight
facts = dict(agreeLand=R["share_agree"], woodChanged=R["share_wood_changed"],
             grow="%s, %s (+%s km²)" % (df.name[d_area.idxmax()], df.state[d_area.idxmax()], format(int(round(d_area.max())), ",")),
             shrink="%s, %s (−%s km²)" % (df.name[d_area.idxmin()], df.state[d_area.idxmin()], format(int(round(-d_area.min())), ",")))
data = dict(sites=sites, cS=[rings(c) for c in S["cells"]], cR=[rings(c) for c in R["cells"]], states=G["states"], sl=G["sl"], grat=G["grat"], water=G["water"], mexico=G["mexico"], facts=facts)
js = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
html = open("vor_app_tpl.html", encoding="utf-8").read().replace("__DATA__", js)
open("vor_app.html", "w", encoding="utf-8").write(html)
print("vor_app.html MB %.2f | data MB %.2f | facts %s" % (len(html.encode()) / 1e6, len(js.encode()) / 1e6, facts))
print("points straight %d road %d" % (sum(len(r) // 2 for c in data["cS"] for r in c), sum(len(r) // 2 for c in data["cR"] for r in c)))
