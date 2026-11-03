"""Two-layer GeoPackage: straight-line Voronoi cells and road-time cells, with the statistics of both versions on every feature (spherical Albers, metres)."""
import pickle, numpy as np, shapely.affinity as sa, geopandas as gpd
from pyproj import CRS
S = pickle.load(open("vor_cells.pkl", "rb")); R = pickle.load(open("vor_road_s.pkl", "rb")); df = R["df"].reset_index(drop=True)
crs = CRS.from_wkt(open("../forest_to_mill_package/data/map_projected/hexes.prj").read())
base = df.rename(columns={"dens_straight": "dens_straight_kft3_km2", "dens_road": "dens_road_kft3_km2", "supply_straight": "supply_straight_Mft3", "supply_road": "supply_road_Mft3",
                          "alloc_day2": "road_alloc_120min_Mft3", "share_of_straight_cell_kept": "share_of_straight_cell_in_road_cell", "wood_minutes_to_mill": "wood_weighted_minutes_to_mill",
                          "area_straight": "area_straight_km2", "area_road": "area_road_km2", "hexes_road": "hexes_in_road_cell"})
def layer(cells, name):
    g = gpd.GeoDataFrame(base.copy(), geometry=[sa.scale(c, 1000, 1000, origin=(0, 0)) for c in cells], crs=crs); g.to_file("voronoi_cells.gpkg", layer=name, driver="GPKG", mode="w" if name == "straight_line_cells" else "a"); return len(g)
base.to_csv("voronoi_cell_stats.csv", index=False)
import os
if os.path.exists("voronoi_cells.gpkg"): os.remove("voronoi_cells.gpkg")
print(layer(S["cells"], "straight_line_cells"), layer(R["cells"], "road_time_cells"))
