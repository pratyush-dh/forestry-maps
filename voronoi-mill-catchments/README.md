# Nearest mill, mapped: Voronoi catchments of U.S. wood mills

A print-size static map (36 x 25 in, PNG and vector PDF). For each of 116 open wood-mill sites in the lower 48 states it draws the Voronoi polygon, the area that is closer to that mill than to any other, and colours the polygon by the FIA forest removals inside it per square kilometre. This is the Day 3 (Polygons) map of the author's 30 Days 30 Maps series.

Open it on the page: <https://pratyush-dh.github.io/forestry-maps/voronoi-mill-catchments/>

## What the map shows

- **Colour** is the annual FIA forest removals inside the polygon divided by its area (thousand ft3 per km2 per year), in five quintile classes.
- **Symbol size** is the same wood as a total (million ft3 per year); **symbol shape** is the mill type (pulp, sawmill, OSB, plywood, MDF, paper).
- Every mill has a polygon. Where mills are few, one polygon covers a whole region: the single California mill owns most of the Southwest.
- Polygon areas range from 2,120 km2 to 1,019,202 km2 (481-fold), while the wood inside ranges only 79-fold (8.8 to 693 million ft3 a year), so a small polygon mostly means a dense mill network, not a rich forest.
- A second chart compares the wood inside each polygon with the wood the mill receives by road within 120 minutes (the [forest-to-mill](../forest-to-mill/) allocation): 92 mills receive less by road than their polygon holds, 24 receive more.

## Files

| Path | Purpose |
|---|---|
| `index.html` | Landing page showing the map with download links |
| `static-map/voronoi_mill_catchments.png` / `.pdf` | The map, 36 x 25 in (4500 x 3125 px at 125 dpi, and vector) |
| `data/voronoi_cells.gpkg` | The 116 polygons with their statistics, in the same custom spherical Albers projection as the forest-to-mill data |
| `data/voronoi_cell_stats.csv` | The same statistics as a table |
| `scripts/vor_analysis.py` | Builds the polygons and statistics |
| `scripts/voronoi_map.py` | Draws the map |

## Read before citing

- Trucks follow roads, so a mill's real catchment differs from its polygon. The road-time version is the [forest-to-mill web map](../forest-to-mill/).
- Wood is cut in forests only, so a polygon's colour is an average over all of its land, not the density at any one place.
- The 117 mills are a sample of open mills, so large western polygons show missing mills as much as empty forest.
- FIA removals are county totals shared evenly among forest hexes (842 km2) and include land clearing.
- Two Camas, Washington, mills (a pulp mill and a panel/paper complex) share one point and therefore one polygon, so there are 116 polygons for 117 mills.
- The polygons are clipped to a simplified outline of the lower 48 states, so a few coastal hexes sit just outside their polygon; their wood is still counted for the nearest mill.

## Rebuild

`vor_analysis.py` reads `source/mills_flow.csv` and `source/hexes.csv` from the forest_to_mill_package (the paths in the script point at `../forest_to_mill_package/`) plus a pickle of state outlines; `voronoi_map.py` also needs `app_data_nat.json` (graticule and water labels) from the [forest-to-mill](../forest-to-mill/scripts/) build. Run `python vor_analysis.py` and then `python voronoi_map.py <output_name>`. Requires Python 3 with shapely 2, scipy, pandas, numpy, matplotlib and pillow; the font is Candara when installed, otherwise Segoe UI or DejaVu Sans.
