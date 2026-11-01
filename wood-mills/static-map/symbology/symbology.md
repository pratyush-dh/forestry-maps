# Symbology rules: US wood mills: a working sample, not a census

Colour carries STATUS only (2 validated hues + neutral gray); SHAPE carries mill type; fill style repeats colour so colour is never the only cue. Capacity is not mapped.

## Status (colour + fill style)

| Class | Legend | Derive from | Face | Outline | Width pt | Alpha | Style | Count |
|---|---|---|---|---|---|---|---|---|
| ring_approx | Closed, closure year approximate | `operational_status = 'closed' AND status_confidence <> 'verified'` | none | #eb6834 | 0.936 | 0.6 | solid | 41 |
| ring_verified | Closed, closure year verified | `operational_status = 'closed' AND status_confidence = 'verified'` | #FBFBF8 | #eb6834 | 1.44 | 1.0 | solid | 30 |
| filled | No closure recorded (operating status not confirmed) | `operational_status IN ('open','partial','reopened')` | #2a78d6 | #FBFBF8 | 0.648 | 0.95 | solid | 117 |
| hatched | Idled or largely shut | `operational_status = 'idled'` | #eb6834 | #FBFBF8 | 0.648 | 1.0 | solid, hatch ///// | 2 |
| dashed | Status unknown (startup not confirmed) | `operational_status = 'unknown'` | #FBFBF8 | #52514e | 1.152 | 1.0 | dashed | 5 |

Draw order (bottom to top): ring_approx, ring_verified, filled, hatched, dashed.

## Shape (mill type)

| Group | Marker | Size pt2 (~mm) | Mill types | Count |
|---|---|---|---|---|
| Pulp & paper | circle (`o`) | 29.7 (~1.92) | pulp, paper, other | 137 |
| Sawmill | square (`s`) | 26.4 (~1.81) | sawmill | 22 |
| Plywood | triangle (`^`) | 36.3 (~2.13) | plywood | 14 |
| OSB | diamond (`D`) | 25.3 (~1.77) | osb | 13 |
| MDF / particleboard | star (`*`) | 64.9 (~2.84) | mdf | 9 |

## Colour validation

Blue `#2a78d6` and orange `#eb6834` validated on land `#FBFBF8` with `--pairs all` (map = scatter form): CVD worst dE 24.7, tritan 32.7, normal vision 33.6, contrast >= 3:1. Gray `#52514e` is a neutral for 'unknown', not a series.

## Palette

- page: `#F2F3EE`
- ocean: `#E1E7E0`
- land: `#FBFBF8`
- state_border: `#CDD3C8`
- graticule: `#B7C2B5`
- ink: `#16201A`
- ink_secondary: `#44504A`
- muted: `#6B756E`
- rule: `#C4CBC1`
- status_blue: `#2a78d6`
- status_orange: `#eb6834`
- status_gray: `#52514e`
- shape_ink: `#3A463F`

## Furniture

- **graticule**: {"interval_deg": 10, "colour": "#B7C2B5", "width_pt": 0.8, "drawn": "under the land polygons (z 0.6 < 1)", "labels": "Inter 8.2 pt, muted; parallels on the Atlantic edge, meridians on the top edge"}
- **land**: {"fill": "#FBFBF8", "border": "#CDD3C8", "border_width_pt": 0.7}
- **ocean**: {"fill": "#E1E7E0"}
- **frame**: {"colour": "#16201A", "width_pt": 1.1, "note": "bounding box of the main map"}
- **inset_box**: {"colour": "#16201A", "width_pt": 0.9, "fill": "#E1E7E0", "applies_to": ["Alaska", "Hawaii"]}
- **scale_bar**: {"length_km": 1000, "segments": 4, "colours": ["#16201A", "#FBFBF8"], "also_in_miles": "621 mi", "note": "Lower 48 only; equal-area, scale varies +/-1.5%"}

## Projection

```json
{
  "lonlat_layers": "EPSG:4326 (WGS84)",
  "projected_layers": {
    "name": "US_Wood_Mills_Albers_Sphere (custom; see .prj)",
    "projection": "Albers equal-area conic, spherical",
    "standard_parallels": [
      29.5,
      45.5
    ],
    "latitude_of_origin": 37.5,
    "central_meridian": -96.0,
    "sphere_radius_m": 6371008.8,
    "units": "metre",
    "alaska_inset": {
      "projection": "Albers",
      "standard_parallels": [
        55,
        65
      ],
      "origin": [
        50,
        -154
      ],
      "scale": 0.35,
      "lower_left_m": [
        -2400000.0,
        -1570000.0
      ],
      "box_m": [
        -2400000.0,
        -1570000.0,
        -1510606.7,
        -855621.2
      ]
    },
    "hawaii_inset": {
      "projection": "Albers",
      "standard_parallels": [
        8,
        18
      ],
      "origin": [
        3,
        -157
      ],
      "scale": 0.35,
      "box_m": [
        -1460606.7,
        -1570000.0,
        -1000606.7,
        -1230000.0
      ],
      "records_in_sample": 0,
      "note": "drawn with a 'No records in this sample' label"
    },
    "inset_scale_bar": {
      "length_km": 1000,
      "segments": 2,
      "drawn_length_m": 350000.0,
      "lower_left_m": [
        -860606.7,
        -1495000.0
      ],
      "note": "one bar serves both insets; drawn length = km x 0.35"
    },
    "scale_distortion": "parallels 0.990-1.015; max +/-1.5% across the lower 48"
  }
}
```

## Typography

| Role | Family | Weight | Size pt | Colour | Notes |
|---|---|---|---|---|---|
| Title | Caladea | Bold | 46 | `#16201A` | align centre |
| Deck | Inter | SemiBold | 9.4 | `#6B756E` | note UPPERCASE, faux-tracked |
| Headline sentence | Caladea | Regular | 17.5 | `#16201A` | line_height 1.2 |
| Section label | Inter | SemiBold | 8.4 | `#6B756E` | note UPPERCASE, faux-tracked |
| Legend label | Inter | Regular | 11.5 | `#16201A` |  |
| Legend count | Inter | Medium | 11.5 | `#44504A` | align right |
| Legend sub-label | Inter | Regular | 9.3 | `#6B756E` |  |
| Caveat lead-in | Inter | SemiBold | 10.6 | `#16201A` |  |
| Caveat body | Inter | Regular | 9.7 | `#44504A` | line_height 1.4 |
| Map labels (graticule, scale bar, inset) | Inter | Regular | 7.9-8.4 | `#6B756E` |  |
| Footer | Inter | Regular | 8.0 | `#6B756E` | line_height 1.55 |

_status_class derives from the pipeline fields operational_status and status_confidence; see source/qa_report.md. 'checked=1' verifies the CLOSURE YEAR only._
