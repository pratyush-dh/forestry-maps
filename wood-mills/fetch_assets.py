#!/usr/bin/env python3
"""Download the JS libraries and US state geometry into ./vendor so the app runs offline.

Run once with internet access. Standard library only. Fonts still come from Google Fonts;
without internet the page falls back to Arial Narrow / Arial.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor"
ASSETS: dict[str, str] = {
    "d3.min.js": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "topojson-client.min.js": "https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js",
    # Unprojected lon/lat (EPSG:4326-style) TopoJSON of US states from Census cartographic boundaries, 1:10m.
    "states-10m.json": "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json",
}


def download(name: str, url: str, timeout: float = 30.0) -> bool:
    """Fetch `url` into vendor/`name`. Returns True on success."""
    dest = VENDOR / name
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  failed  {name}: {exc}", file=sys.stderr)
        return False
    if name.endswith(".json"):
        try:
            json.loads(data)
        except json.JSONDecodeError:
            print(f"  failed  {name}: response wasn't valid JSON", file=sys.stderr)
            return False
    dest.write_bytes(data)
    print(f"  saved   {name} ({len(data) / 1024:.0f} KB)")
    return True


def main() -> int:
    VENDOR.mkdir(exist_ok=True)
    print(f"Downloading assets to {VENDOR}")
    ok = all([download(n, u) for n, u in ASSETS.items()])
    print("Done. The app now works offline." if ok else "Some downloads failed; the app will fall back to the CDN for those.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
