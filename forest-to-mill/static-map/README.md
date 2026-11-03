# Static maps

Print-style companions to the [web map](https://pratyush-dh.github.io/forestry-maps/forest-to-mill/), in two page shapes. Each comes as a PNG and a vector PDF.

| File | Page | Palette |
|---|---|---|
| `forest_to_mill_map_landscape_paper.png` / `.pdf` | Landscape, 26 x 17.6 in (4420 x 2992 px) | Cream paper, red traffic, for print |
| `forest_to_mill_map_landscape_night.png` / `.pdf` | Landscape, 26 x 17.6 in | Black map, amber traffic, for screens |
| `forest_to_mill_map_portrait_paper.png` / `.pdf` | Portrait 4:5, 24 x 30 in (3600 x 4500 px) | Cream paper, red traffic, for print |

The portrait sheet sets all text 1.5 times larger than the landscape sheet, so it stays readable when printed at its own size (24 x 30 in). It also carries the mill-type shapes (pulp, sawmill, OSB, plywood, MDF, paper) in the legend. Printed smaller, the text scales down with the page.

Map elements: labelled 5-degree graticule (drawn beneath the land), km and mile scale bar, north arrow with the note that true
north is only at 96 W, a lower-48 locator showing the extent, a label-type key (study states, neighbouring states, water, mills,
busiest road segments), the NLCD tree-canopy underlay, a legend, and a "Before citing" note. The key chart is "How far is each
state's wood from a mill?".

Rebuild from [`../scripts/static_map.py`](../scripts/static_map.py) (landscape) and [`../scripts/static_map_portrait.py`](../scripts/static_map_portrait.py); the data are in [`../data/`](../data/). Both scripts stop with an error if any map label crosses the map frame.
Read the caveats in the [folder README](../README.md) before citing: this is a model, the mill list is a sample, and canopy
is not the FIA definition of forest.
