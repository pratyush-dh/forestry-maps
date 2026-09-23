# US wood-products mills, a working sample

An animated map of US pulp, paper, sawmill, plywood, OSB and MDF mills from 1860 to today. Each mill appears in the year it opened. When it shut down for good, it turns into a hollow ring.

Scroll or pinch to zoom, drag to pan, and click a mill to pin a detail card (click elsewhere or press Escape to close it).

## Run it

```bash
python serve.py              # serves on http://127.0.0.1:8000 and opens your browser
python serve.py --port 9000 --no-browser
```

To work offline, run `python fetch_assets.py` once while you have internet. It saves d3, topojson-client and the us-atlas state geometry into `vendor/`. Until you do, the app loads them from jsDelivr.

You need Python 3.8+. Only the standard library is used.

## Files

| Path | Purpose |
|---|---|
| `index.html`, `style.css`, `app.js` | The app (d3 v7, `geoAlbersUsa` with AK/HI insets) |
| `data/mills.csv` | The dataset. Edit it and reload the page |
| `serve.py` | Local static server, with caching disabled so CSV edits show up right away |
| `fetch_assets.py` | One-time download of the libraries and geometry for offline use |

## Data format

`name, company, city, state, lat, lon, open, close, checked, note, type, capacity, capacity_unit`

- `lat`/`lon` are WGS84 decimal degrees. The shipped coordinates are at town level, not the mill footprint.
- `open` and `close` are years. Leave `close` blank for a mill that is still operating. "Closed" means the mill's primary process (pulping, sawing, pressing) stopped permanently. Partial line/machine shutdowns stay as operating and get a `note`.
- `checked` = 1 means the closure year was verified against company announcements or trade press. Rows with 0 are approximate.
- `type` is one of `pulp`, `paper`, `pulp/chip`, `sawmill`, `plywood`, `osb`, `mdf`. Defaults to `pulp` if blank. Shown in the map as a different marker shape (see the legend) and filterable via the **Type** dropdown.
- `capacity` / `capacity_unit` are filled in only where a mill-specific figure was reported (e.g. `300` / `MMBF/yr`). Most published lumber/panel capacity numbers are **company-wide totals across many mills**, not per-facility — those are left blank rather than guessed. Shown in the tooltip when present.

You can also load a different CSV at runtime with the **Load your own CSV** button. `name, lat, lon, open` are required; the rest are optional.

## Caveats

The shipped dataset is a curated sample: ~135 pulp/paper mills, 23 sawmills, 14 plywood mills, 13 OSB mills and 9 MDF/particleboard mills, not a census of US wood-processing facilities (there are 1,000+ active today across all these categories). Pre-1950 closures are heavily under-represented, largely because no centralized historical closure record exists pre-EPA/SEC/WARN-Act reporting era (roughly the 1970s onward) — see the discussion in the chat this app came from. Cross-checked against the Pulp & Paperworkers' Resource Council's 2025 mill-status map (thepprc.org) for additional recent closures. For authoritative data:

- **Forisk North American Mill Capacity Database** or **FisherSolve** (commercial) — the only sources with real per-mill capacity figures across pulp, paper, sawmill and panel categories
- **Lockwood-Post's Directory** (historical annual editions, pulp/paper)
- **EPA FRS/ECHO** facilities filtered by NAICS — 322110 (pulp), 322121/322130 (paper/paperboard), 321113 (sawmills), 321211/321212 (plywood/OSB) — good for coordinates and permit status, not capacity
- **USDA Forest Service Timber Product Output (TPO)** studies — periodic state-level mill surveys, sawmill-focused
