# Forestry maps

Interactive maps on forestry and forest-products topics, one per subfolder with its own `index.html`.

| Map | Description | Live demo |
|---|---|---|
| [`wood-mills`](wood-mills/) | US wood-products mills, a working sample (~196 mills, 1860–present) gathered from public web sources, not an official census. Pulp, paper, sawmill, plywood, OSB and MDF/particleboard mills as color- and shape-coded markers, with a play/scrub timeline of openings and closures, a type filter, zoom and pan, a click-to-pin detail card per mill, and support for loading your own CSV. | [Demo](https://pratyush-dh.github.io/forestry-maps/wood-mills/) |
| [`forest-to-mill`](forest-to-mill/) | Modelled wood-haul traffic on the road network, from FIA forest removals to 117 open wood mills across the lower 48 states, over NLCD tree canopy. Haul-time cap, mill-choice spread and canopy-weighted removals are adjustable; click a patch, mill or chart bar and the map zooms to it. Includes print-style static maps and a GeoPackage. A model, not a traffic count. | [Demo](https://pratyush-dh.github.io/forestry-maps/forest-to-mill/) |

The static, print-style companion to `wood-mills` (PNG poster, GIS layers in WGS84 and projected form, QGIS style, QA report and build scripts) is in [`wood-mills/static-map`](wood-mills/static-map/); the same for `forest-to-mill` is in [`forest-to-mill/static-map`](forest-to-mill/static-map/).

More maps will be added here over time.
