# Static maps

Print-style companions to the [web map](https://pratyush-dh.github.io/forestry-maps/forest-to-mill/). Wide sheet (26 x 17.6 in),
main map first, one key chart. Both palettes come as a PNG (about 4400 x 3000 px) and a vector PDF.

| File | Palette |
|---|---|
| `forest_to_mill_map_paper.png` / `.pdf` | Cream paper, red traffic, for print |
| `forest_to_mill_map_night.png` / `.pdf` | Black map, amber traffic, for screens |

Map elements: labelled 5-degree graticule (drawn beneath the land), km and mile scale bar, north arrow with the note that true
north is only at 96 W, a lower-48 locator showing the extent, a label-type key (study states, neighbouring states, water, mills,
busiest road segments), the NLCD tree-canopy underlay, a legend, and a "Before citing" note. The key chart is "How far is each
state's wood from a mill?".

Rebuild from [`../scripts/static_map.py`](../scripts/static_map.py); the data are in [`../data/`](../data/).
Read the caveats in the [folder README](../README.md) before citing: this is a model, the mill list is a sample, and canopy
is not the FIA definition of forest.
