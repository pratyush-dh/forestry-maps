# US wood mills: data and symbology package

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

## Rebuilding
The scripts use paths from the original build environment (`raw/`, `out/`, `data/`), so pass this package's layout explicitly:

```
python scripts/build_mills.py --input source/mills_raw.csv --outdir out
python scripts/make_static_map.py --mills out/mills_clean.csv --states source/us-states_lowres_source.geojson --out us_wood_mills.png
python scripts/export_package.py --mills out/mills_clean.csv --states source/us-states_lowres_source.geojson --raw source/mills_raw.csv --png us_wood_mills.png
```
Needs pandas, matplotlib and the Inter and Caladea fonts (font lookup in `make_static_map.py` is Linux-path based). These commands were not re-run when the package was published to GitHub.

The interactive, time-enabled version of this map is one folder up: [`../`](../).
