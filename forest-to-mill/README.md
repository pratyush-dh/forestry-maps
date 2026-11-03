# Forest to mill

Where wood moves by road across the lower 48 states: modelled haul traffic from FIA forest removals to 117 open wood
mills. **A model, not a traffic count, and the mill list is a sample.**

- **Live web map:** https://pratyush-dh.github.io/forestry-maps/forest-to-mill/
- **Static maps:** [`static-map/`](static-map/) (paper and night, PNG and vector PDF)
- **GIS data:** [`data/south_connectivity.gpkg`](data/south_connectivity.gpkg) (QGIS / ArcGIS)
- Mill sample: from [`wood-mills`](../wood-mills/).

Scope: the web map covers the whole lower 48. The static maps and the GeoPackage are a close-up of the 13 southern states
(Oklahoma and Texas to Virginia), where the open mills are densest.

## What the map shows

Each forest hex (842 km², equal-area, Albers) sends its FIA annual removals to every mill it can reach by road within a
haul cap (default 120 minutes), weighted by travel time. Road thickness is the wood summed over every route that crosses a
segment. Each haul is counted once; the empty return uses the same road, so the ranking is the same either way.

In the web map you can change the haul cap, the spread to farther mills (0 = nearest mill only), and where a county's
removals fall (by tree canopy, or evenly). Click a forest patch or a mill, or pick a bar in a chart, and the map zooms
to it with a spotlight. Every graph has an Enlarge button. Mills are drawn as a different shape for each type (pulp, sawmill, OSB, plywood, MDF, paper), and a Light / Dark switch changes the page and map together. Deep links: `#hex=<id>`, `#mill=<id>`, `#top=3`, `#state=<fips>`,
`#bin=<n>`, `#reach=<n>`.

## Method in brief

1. **Removals.** FIA county totals (annual removals, ft³/yr), 2016 to 2025 evaluations, from the
   `fia-forest-stand-profile` project. Counties under 20% forest are not treated as wood sources.
2. **Placing removals inside a county.** FIA gives county totals only. The default places each county's total across its
   hexes in proportion to NLCD tree canopy; the original method splits it evenly. County totals are identical either way
   (4.4% of the wood, about 584 million ft³ a year, changes hex).
3. **Roads.** Natural Earth 1:10m major roads, snapped to a graph. Edge time = length x 1.10 / class speed
   (80 / 72 / 64 / 64 / 48 km/h for Major / Beltway / Secondary / Bypass / Road). Off-network legs use 40 km/h and 1.35x circuity.
4. **Routing.** Multi-source Dijkstra from every mill; each hex snaps to its 6 nearest road nodes.
5. **Splitting wood between mills.** Share to mill j is proportional to exp(-(t_j - t_nearest) / spread); the default
   spread is 15 minutes, so a mill 15 minutes farther than the nearest gets about 37% of its share.

## Tree canopy (NLCD)

The underlay is USFS NLCD Tree Canopy Cover (TCC v2025-6, 2021 slice, 30 m, percent of each pixel under tree crowns),
fetched from the GeoPlatform ImageServer and averaged to 1 km and 2 km (`scripts/canopy.py`). **It is not the FIA
definition of forest**: it includes street and yard trees and can miss open woodland. Against FIA's county forest share it
agrees well (Spearman 0.80 across the 2,628 hexes of the southern extract), and it varies a lot inside counties (in 39% of counties with at
least three hexes it varies by more than 30% around the county mean). Per-hex values: [`data/nlcd_canopy_by_hex.csv`](data/nlcd_canopy_by_hex.csv).

## Files

| Path | What |
|---|---|
| `index.html` | The web map for the lower 48, one self-contained file (about 3 MB, data inline). |
| `static-map/` | Print-style maps, landscape (paper and night) and portrait 4:5: main map, scale bar, graticule, north arrow, locator, one key chart, legend. |
| `data/south_connectivity.gpkg` | GeoPackage, custom spherical Albers (metres): `hex_forest_connectivity`, `roads_traffic`, `mills`, `states`. |
| `data/map_data.json` | The compact southern-extract data behind the static maps (edges, hexes with routes, mills, states, canopy raster). |
| `data/nlcd_canopy_by_hex.csv` | Mean canopy, share of land at least 10% canopy, and valid-pixel share for each hex of the southern extract. |
| `data/nlcd_canopy_by_hex_conus.csv` | The same for all 9,694 lower-48 hexes (the web map). |
| `data/states_albers_km.json` | State outlines in the map projection (km), for the poster's locator map. |
| `scripts/` | `static_map.py` (landscape) and `static_map_portrait.py` (portrait), `export_gpkg.py` (GeoPackage), `canopy.py` and `canopy_check.py` (NLCD), plus the data builders. |

### GeoPackage layers

- `hex_forest_connectivity`: `hex_id`, `county`, `state_fips`, `fia_forest_share`, `fia_forest_km2`, `is_forest_source`,
  `nlcd_canopy_mean_pct`, `removals_even_Mft3`, `removals_canopy_Mft3` (million ft³/yr), `n_mills_60`, `n_mills_120`,
  `nearest_min`, `nearest_mill`.
- `roads_traffic`: `road_class`, `len_km`, and loads in million ft³/yr for four runs:
  `load_{even|canopy}_{nearest|spread15}_Mft3`. The web map and posters show `load_canopy_spread15_Mft3`.
- `mills`: `mill_id`, `name`, `company`, `state`, `mill_type`, `received_{even|canopy}_spread15_Mft3`, `hexes_in_range`.
- `states`: `fips`, `name`, `in_study`.

## Rebuild

- Maps: `cd scripts && python static_map.py paper out canopy` (or `night`; add `nocanopy` for roads only) for landscape, and `python static_map_portrait.py out 150` for portrait. Needs
  numpy, matplotlib, Pillow and the Candara font (falls back to Segoe UI / DejaVu Sans). Rebuilt output matches the
  published poster to within 0.05% of pixels.
- GeoPackage: `cd scripts && python export_gpkg.py` (geopandas, shapely).
- Canopy: `python canopy.py` re-fetches the tiles (needs rasterio and a network connection); `canopy_check.py` compares
  canopy with FIA county shares.
- Web map: `canopy_nat.py` fetches the national canopy, then `build_national.py` routes every forest hex to every open mill
  within 120 minutes and writes the data that `app_template.html` embeds. It reproduces the package's own result (99.9% of hexes
  agree on whether they are within reach, 98% on the nearest mill). `build_app_data.py` and `build_app_data2.py` build the
  southern-extract `map_data.json`. The input package is not republished here, so these scripts are included for provenance.

## Read before citing

- The 117 mills are the open ones (status open, partial or reopened) in a sample compiled from public sources, not an official
  registry. Closed, idled and unknown-status mills are left out. An empty area, such as much of the West, California and the
  Northeast, shows missing mills as much as distance.
- Roads are major roads only; speeds, the 1.10 circuity factor and the 2-hour cap are assumptions. Mill capacity,
  species and product mix are ignored, and there are no truck-route, weight or bridge limits.
- Volumes are county totals apportioned to hexes (by canopy or evenly), not measured at that location.
- FIA removals include harvest and land-use removals.

## Sources

USDA Forest Service FIA county estimates; USFS NLCD Tree Canopy Cover v2025-6; Natural Earth 1:10m roads; US Census
state and county boundaries via us-atlas; the author-compiled mill list from Day 1 (Forisk / PPRC 2025, company
announcements, trade press). Projection: spherical Albers equal-area conic, standard parallels 29.5 and 45.5 degrees N,
origin 37.5 N 96 W, R = 6,371,008.8 m.
