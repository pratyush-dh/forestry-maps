# Nearest mill, mapped: Voronoi catchments of U.S. wood mills

Which wood mill is nearest to a forest? This folder answers it two ways for 116 open wood-mill sites in the lower 48 states:

- **Straight line:** the Voronoi polygon of each mill, the area closer to that mill than to any other.
- **Road time:** the area from which that mill is the fastest to reach on the road network.

Each polygon is coloured by the FIA forest removals inside it. It has two parts: an **interactive web map** that switches between the two versions, and a **print-size poster** (the straight-line version, the Day 3 Polygons map of the author's 30 Days 30 Maps series).

Open the web map: <https://pratyush-dh.github.io/forestry-maps/voronoi-mill-catchments/> · the poster: <https://pratyush-dh.github.io/forestry-maps/voronoi-mill-catchments/poster.html>

## The web map

- **Nearest mill by** straight line, road time, or compare (road-time polygons with the straight-line outlines dashed).
- **Colour polygons by** wood per km2, wood inside, or area, in five quintile classes shared by both versions so the two modes can be compared.
- Tap a polygon or a mill, or pick one from the list, to see its area, wood and wood per km2 both ways, how much of its straight-line polygon is also in its road-time polygon, and how many minutes its wood is from the mill. Deep links such as `#mill=MS-columbus&mode=B&var=sup` work.
- Pan, pinch and scroll to zoom, a light and a dark map, and a layout that works on a phone.
- Lists of the mills that gain and lose the most wood when the road network decides.

## What the two versions show

- By road, a different mill is nearest for **24% of the land** (24.2% of the 9,558 hexes), but only **15% of the wood** changes mill, because the wood is concentrated in the Southeast where mills are close together.
- Mills that gain the most wood by road include Columbus, Mississippi (85 to 193 million ft3 a year), Demopolis, Alabama (92 to 202), Vicksburg, Mississippi (43 to 92) and Pensacola, Florida (40 to 77). Those that lose the most include Fulton sawmill, Alabama (177 to 67), Wauna, Oregon (647 to 349), Palatka, Florida (173 to 96) and Barnwell, South Carolina (52 to 21).
- In the straight-line version, polygon area ranges 481-fold (2,120 to 1,019,202 km2) while the wood inside ranges only 79-fold, so a small polygon mostly means a dense mill network, not a rich forest.

## How the road-time polygons are built

1. The road graph, speeds and off-road legs are those of the [forest-to-mill](../forest-to-mill/) map (major roads, 40 km/h and a 1.35 detour off the network). Travel time is computed from every mill site to every hex with land or forest removals, with no 120-minute cap.
2. A hex can also reach a mill straight across country at the off-road speed when that is faster than the road route. Without this, a mill that sits 20 to 40 km from any mapped road pays its whole off-road leg on every route to it and loses even the hexes next to it (this emptied two polygons in a first attempt). The direct route is the fastest option for 9.0% of hexes.
3. Each land hex goes to the mill with the shortest time. Hexes are 842 km2, so the boundaries are accurate to about one hex.
4. The assignment is drawn on a 5 km grid, smoothed over about 20 km for display (the hex assignment and the wood per mill are not changed), and detached fragments under 3,000 km2 are merged into the surrounding polygon.

## Files

| Path | Purpose |
|---|---|
| `index.html` | The interactive map (one self-contained file, about 0.4 MB) |
| `poster.html` | Landing page for the poster, with download links |
| `static-map/voronoi_mill_catchments.png` / `.pdf` | The straight-line poster, 36 x 25 in |
| `data/voronoi_cells.gpkg` | Two layers, `straight_line_cells` and `road_time_cells`, 116 polygons each, with the statistics of both versions, in the custom spherical Albers projection of the forest-to-mill data |
| `data/voronoi_cell_stats.csv` | The same statistics as a table |
| `scripts/vor_analysis.py` | Straight-line polygons and statistics |
| `scripts/vor_road.py`, `scripts/vor_road_smooth.py` | Road-time assignment, polygons and statistics |
| `scripts/build_vor_app.py`, `scripts/vor_app_tpl.html` | Builds `index.html` |
| `scripts/export_gpkg_vor.py` | Writes the GeoPackage and CSV |
| `scripts/voronoi_map.py` | Draws the poster |

## Read before citing

- A model, not a traffic count. Trucks do not all go to the nearest mill, and the road graph is the major roads only.
- Colour is the wood removed from forests inside the polygon, averaged over all of its land, so it is not the density at any one place.
- The 117 mills are a sample of open mills, so large western polygons show missing mills as much as empty forest. California has one listed mill, so its polygon covers most of the Southwest.
- FIA removals are county totals shared evenly among forest hexes and include land clearing.
- Two Camas, Washington, mills (a pulp mill and a panel/paper complex) share one point and therefore one polygon, so there are 116 polygons for 117 mills.
- Road-time polygons are built from hexes, so two mills, Fernandina Beach (containerboard, 2.4 km from the Rayonier mill) and Woodland, Maine, sit just outside their own road-time polygon. Their wood is still counted for them.
- The road-time version has no 120-minute limit, so its wood per mill is larger than the Forest to Mill allocation (11,368 of 20,800 million ft3 reaches a mill within 120 minutes).

## Rebuild

`vor_analysis.py` and `vor_road.py` read `source/mills_flow.csv`, `source/hexes.csv` and `source/edges.csv` from the forest_to_mill_package (the paths point at `../forest_to_mill_package/`), plus a pickle of state outlines; the web map and poster also use `app_data_nat.json` (graticule, water labels, state outlines) from the [forest-to-mill](../forest-to-mill/scripts/) build. Run `vor_analysis.py`, `vor_road.py`, `vor_road_smooth.py`, then `build_vor_app.py` and `export_gpkg_vor.py`; run `voronoi_map.py <output_name>` for the poster. Requires Python 3 with shapely 2, scipy, pandas, numpy, rasterio, geopandas, matplotlib and pillow.
