#!/usr/bin/env python3
"""Build a map-ready, QA'd dataset of US wood-products / pulp & paper mills.

Reads the raw mills CSV (never modified), derives an explicit operational-status
model, normalised mill types, unit-aware capacity fields, spatial QA flags and a
facility-events table, then writes:

    mills_clean.csv / mills_clean.geojson / mills_clean.gpkg (needs geopandas)
    mill_events.csv
    qa_report.md

CRS: all geometry is lon/lat in EPSG:4326 (WGS84). The source CSV does not state
a datum; WGS84 is assumed. Distances in QA use a spherical haversine
(R = 6371.0088 km), which is adequate for the ~km-scale checks done here.

Usage:
    python build_mills.py --input raw/mills_raw.csv --outdir out
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLS = [
    "name", "company", "city", "state", "lat", "lon", "open", "close",
    "checked", "note", "type", "capacity", "capacity_unit",
]
NON_US_STATES = {"BC"}  # Canadian province codes present in the source
EARTH_R_KM = 6371.0088

# ---------------------------------------------------------------------------
# Type / capacity vocabularies
# ---------------------------------------------------------------------------
TYPE_MAP = {
    "pulp": "pulp", "paper": "paper", "sawmill": "sawmill", "plywood": "plywood",
    "osb": "osb", "mdf": "mdf",
    "pulp/chip": "pulp",   # Morrilton expansion project: a project at a pulp mill
    "mill": "other",       # Camas panel/paper complex: not a standard category
}
FAMILY = {  # solid wood products vs fibre (pulp & paper)
    "sawmill": "wood_products", "plywood": "wood_products", "osb": "wood_products",
    "mdf": "wood_products", "pulp": "pulp_paper", "paper": "pulp_paper",
    "other": "pulp_paper",
}
CAPACITY_GROUP = {  # units are NOT interchangeable; one scale per group
    "MMBF/yr": "lumber_MMBF",
    "MMSF/yr": "panel_MMSF",
    "tons/yr": "pulp_paper_tons",
    "m3/yr": "board_m3",
}

# ---------------------------------------------------------------------------
# Evidence-based status overrides, keyed on source `name`.
# (status, confidence, status_year, rationale)
# status: open | closed | idled | partial | reopened | unknown
# confidence: verified | reported | inferred | needs_review
# ---------------------------------------------------------------------------
STATUS_OVERRIDES: dict[str, tuple[str, str, int | None, str]] = {
    "Barnwell": ("reopened", "reported", 2025, "Closed 2023 by Cascades; reopened 2025 by ST Group (per note)."),
    "Pensacola": ("partial", "reported", 2023, "One fluff pulp machine shut 2023; mill still runs."),
    "Riegelwood": ("partial", "reported", 2023, "One pulp machine shut end of 2023; mill continues."),
    "Franklin": ("partial", "reported", 2010, "Paper making ended 2010; fluff pulp continues."),
    "Crossett": ("partial", "reported", 2019, "Bleached board ended 2019; pulp mill and chemical plant continue."),
    "Moncure MDF": ("partial", "reported", 2020, "Co-located particleboard line closed 2020; MDF/millwork retained."),
    "Camas": ("partial", "needs_review", 2018, "Pulping ended 2018; 'reduced paper operation remained' - current state unknown."),
    "Camas panel/paper complex": ("partial", "needs_review", 2018, "Same site as 'Camas'; likely duplicate of the same complex."),
    "Longview (Nippon Dynawave)": ("idled", "reported", 2026, "Largely shut after May 2026 white-liquor tank collapse; long-term status unresolved."),
    "Old Town": ("idled", "reported", 2023, "Idled indefinitely April 2023; not restarted per note."),
    "Spring City OSB": ("reopened", "reported", 2018, "Idled 2011; production restarted April 2018."),
    "Huguley OSB": ("reopened", "reported", 2017, "Previously idled mill restarted by West Fraser 2017."),
    "Jefferson OSB": ("reopened", "reported", 2013, "Previously idled mill restarted by West Fraser 2013."),
    "Dillard Plywood (hardwood line)": ("closed", "verified", 2025, "Hardwood plywood LINE closed Sept 2025; rest of Dillard complex operates."),
    "Wiggins Plywood": ("closed", "needs_review", 2026, "2026 closure was 'announced'; confirm actual shutdown date."),
    "Westervelt (Gulf States Paper)": ("closed", "inferred", 1975, "Close year is an estimate ('mid-1970s')."),
    "Waco recycled paper mill": ("unknown", "needs_review", 2025, "New mill targeted Q4 2025 startup; startup not confirmed in source."),
    "Cohasset OSB": ("unknown", "needs_review", 2025, "Production-start date not confirmed in source."),
    "Beaumont Plywood": ("unknown", "needs_review", 2025, "Targeted early-2025 production; start not confirmed."),
    "Dillard MDF": ("unknown", "needs_review", 2024, "Targeted late-summer 2024 start; start not confirmed."),
    "Morrilton expansion": ("unknown", "needs_review", None, "Expansion PROJECT at the Morrilton pulp mill, not a separate facility; completion unconfirmed."),
    "Los Angeles Paper Box & Board Mill": ("open", "reported", None, "Note states still operating."),
    "Atlas Paper Mills": ("open", "reported", None, "Note states still operating."),
    "Roses SouthEast Papers": ("open", "reported", None, "Note states still operating."),
    "Caraustar Austell": ("open", "reported", None, "Note states still operating."),
}

# Manually curated events that the open/close columns cannot express.
# (name, event_type, year, detail)
MANUAL_EVENTS: list[tuple[str, str, int | None, str]] = [
    ("Barnwell", "reopened", 2025, "Reacquired and reopened by ST Group as Barnwell Tissue Solutions."),
    ("Pensacola", "line_closed", 2023, "One fluff pulp machine permanently shut."),
    ("Riegelwood", "line_closed", 2023, "One pulp machine permanently shut (end of year)."),
    ("Franklin", "line_closed", 2010, "Paper making ended; fluff pulp continues."),
    ("Crossett", "line_closed", 2019, "Bleached board production ended; shift toward tissue/towel."),
    ("Moncure MDF", "line_closed", 2020, "Co-located particleboard line closed April 2020."),
    ("Camas", "line_closed", 2018, "Pulping ended; reduced paper operation remained."),
    ("Spring City OSB", "idled", 2011, "Idled amid housing downturn."),
    ("Spring City OSB", "restarted", 2018, "Production restarted April 2018."),
    ("Huguley OSB", "restarted", 2017, "Restarted by West Fraser."),
    ("Jefferson OSB", "restarted", 2013, "Restarted by West Fraser."),
    ("Old Town", "idled", 2015, "Shuttered by Expera (restarted 2019 by ND Paper)."),
    ("Old Town", "idled", 2023, "Idled indefinitely April 2023."),
    ("Longview (Nippon Dynawave)", "idled", 2026, "Largely shut after May 2026 white-liquor tank collapse."),
    ("Wiggins Plywood", "closure_announced", 2026, "Closure announced after Tropical Storm Arthur damage."),
    ("Dillard Plywood (hardwood line)", "line_closed", 2025, "Hardwood plywood line closed Sept 2025."),
    ("Waco recycled paper mill", "startup_targeted", 2025, "Targeted Q4 2025."),
    ("Beaumont Plywood", "startup_targeted", 2025, "Targeted early 2025."),
    ("Dillard MDF", "startup_targeted", 2024, "Targeted late summer 2024."),
]

# Capacity fields that need a caveat beyond the raw value.
CAPACITY_NOTES = {
    "Eastaboga Particleboard": "Particleboard line only; site also has a separate 329,000 m3/yr MDF line not included.",
    "Angelina sawmill": "Design capacity at full build-out (~700,000 m3/yr), not actual output.",
    "Meldrim sawmill": "Source gives 750 MMBF/yr combined for FOUR Interfor mills; not assignable to this mill.",
}

UNCERTAIN_OPEN_RE = re.compile(
    r"exact (?:original construction )?year|not specified|not confirmed|implying|unclear|sources differ|exact production-start",
    re.I,
)
UNCERTAIN_CLOSE_RE = re.compile(r"estimate", re.I)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def decimals(x: float) -> int:
    """Number of decimal places in the source coordinate (via repr)."""
    s = repr(float(x))
    return len(s.split(".")[1]) if "." in s and not s.endswith(".0") else 0


def haversine_matrix(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Pairwise great-circle distances in km (vectorised, n x n)."""
    p = np.radians(lat)[:, None]
    q = np.radians(lat)[None, :]
    dlon = np.radians(lon)[:, None] - np.radians(lon)[None, :]
    a = np.sin((q - p) / 2) ** 2 + np.cos(p) * np.cos(q) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "None."
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------
def load_raw(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype={"name": str, "company": str, "city": str, "state": str,
                                  "note": str, "type": str, "capacity_unit": str})
    missing = set(REQUIRED_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    for c in ("open", "close", "capacity", "checked"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in ("lat", "lon"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("name", "company", "city", "state", "note", "type", "capacity_unit"):
        df[c] = df[c].astype("string").str.strip()
    if df["name"].duplicated().any():
        raise ValueError(f"Duplicate names: {df.loc[df['name'].duplicated(), 'name'].tolist()}")
    unknown = set(STATUS_OVERRIDES) | {n for n, *_ in MANUAL_EVENTS} | set(CAPACITY_NOTES)
    absent = unknown - set(df["name"])
    if absent:
        raise ValueError(f"Overrides reference names not in CSV: {sorted(absent)}")
    return df


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Derive operational_status from evidence, not from `close IS NULL`.

    `checked` semantics (per the web app README): checked == 1 means the
    CLOSURE YEAR was verified against company announcements / trade press;
    0 means approximate. It therefore upgrades confidence for closed records
    only. It says nothing about whether an open mill is operating today, so
    default-open records are always 'inferred'. `checked` is kept unchanged.
    """
    out = []
    for _, r in df.iterrows():
        ov = STATUS_OVERRIDES.get(r["name"])
        if ov:
            status, conf, year, why = ov
        elif pd.notna(r["close"]):
            status, year = "closed", int(r["close"])
            conf = "verified" if r["checked"] == 1 else "inferred"
            why = "Close year populated."
        else:
            status, year, conf = "open", None, "inferred"
            why = "No close year recorded; operating status not independently confirmed."
        out.append((status, conf, year, why))
    df = df.copy()
    df[["operational_status", "status_confidence", "status_year", "status_rationale"]] = pd.DataFrame(
        out, index=df.index)
    df["status_year"] = pd.to_numeric(df["status_year"]).astype("Int64")
    return df


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mill_type"] = df["type"].map(TYPE_MAP)
    if df["mill_type"].isna().any():
        raise ValueError(f"Unmapped types: {df.loc[df['mill_type'].isna(), 'type'].unique()}")
    df["industry_family"] = df["mill_type"].map(FAMILY)
    df["mill_subtype"] = np.where(df["name"].str.contains("Particleboard", case=False), "particleboard", pd.NA)
    df["in_us_scope"] = ~df["state"].isin(NON_US_STATES)
    df["mill_id"] = df["state"] + "-" + df["name"].map(slug)
    if df["mill_id"].duplicated().any():
        raise ValueError("mill_id collision")
    df["open_year_uncertain"] = df["note"].fillna("").str.contains(UNCERTAIN_OPEN_RE)
    df["close_year_uncertain"] = df["note"].fillna("").str.contains(UNCERTAIN_CLOSE_RE) & df["close"].notna()
    return df


def capacity(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    has = df["capacity"].notna()
    bad_unit = has & ~df["capacity_unit"].isin(CAPACITY_GROUP)
    if bad_unit.any():
        raise ValueError(f"Capacity without known unit: {df.loc[bad_unit, 'name'].tolist()}")
    df["capacity_value"] = df["capacity"].astype("Float64")
    df["capacity_group"] = df["capacity_unit"].map(CAPACITY_GROUP)
    df["capacity_available"] = has
    df["capacity_label"] = np.where(
        has, df["capacity"].map(lambda v: f"{int(v):,}" if pd.notna(v) else "") + " " + df["capacity_unit"].fillna(""), pd.NA)
    basis = df["note"].fillna("").str.contains(r"3/8-in basis")
    df["capacity_basis"] = np.where(basis, "3/8-in basis", pd.NA)
    df["capacity_note"] = df["name"].map(CAPACITY_NOTES)
    return df


def spatial_qa(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Coordinate validity, precision, co-location, near-overlap, state outliers."""
    df = df.copy()
    findings: dict = {}
    bad = df["lat"].isna() | df["lon"].isna() | ~df["lat"].between(-90, 90) | ~df["lon"].between(-180, 180)
    if bad.any():
        raise ValueError(f"Invalid coordinates: {df.loc[bad, 'name'].tolist()}")

    df["coord_decimals"] = np.minimum(df["lat"].map(decimals), df["lon"].map(decimals))
    df["coord_precision"] = np.where(df["coord_decimals"] <= 2, "approx (~1 km)", "fine")

    key = df["lat"].round(5).astype(str) + "," + df["lon"].round(5).astype(str)
    df["site_id"] = pd.factorize(key)[0] + 1
    df["colocated_n"] = df.groupby("site_id")["name"].transform("size")

    conus = df["in_us_scope"] & (df["state"] != "AK")
    outside = conus & ~(df["lat"].between(24, 50) & df["lon"].between(-125, -66.5))
    df["flag_outside_conus_bbox"] = outside

    # distance to state median (coarse bad-coordinate detector; no boundary data offline)
    med = df.groupby("state")[["lat", "lon"]].transform("median")
    d = haversine_matrix(np.r_[df["lat"].values, med["lat"].values],
                         np.r_[df["lon"].values, med["lon"].values])
    n = len(df)
    df["km_from_state_median"] = np.round(np.diag(d[:n, n:]), 0)
    counts = df.groupby("state")["name"].transform("size")
    df["flag_state_outlier"] = (df["km_from_state_median"] > 800) & (counts >= 5) & df["in_us_scope"]

    D = haversine_matrix(df["lat"].values, df["lon"].values)
    iu = np.triu_indices(n, k=1)
    near = (D[iu] < 2.0) & (D[iu] > 0)
    pairs = pd.DataFrame({
        "mill_a": df["name"].values[iu[0]][near],
        "mill_b": df["name"].values[iu[1]][near],
        "km": np.round(D[iu][near], 2),
    }).sort_values("km")
    findings["near_pairs"] = pairs
    findings["colocated"] = df[df["colocated_n"] > 1][["site_id", "name", "mill_type", "operational_status"]] \
        .sort_values(["site_id", "name"])
    return df, findings


def review_reasons(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    reasons = []
    for _, r in df.iterrows():
        x = []
        if r["status_confidence"] == "needs_review":
            x.append("status")
        if not r["in_us_scope"]:
            x.append("non-US")
        if r["colocated_n"] > 1:
            x.append("co-located site")
        if r["open_year_uncertain"]:
            x.append("open year uncertain")
        if r["close_year_uncertain"]:
            x.append("close year estimated")
        if r["flag_outside_conus_bbox"] or r["flag_state_outlier"]:
            x.append("coordinate outlier")
        if r["mill_type"] == "other" or r["name"] in ("Morrilton expansion",):
            x.append("non-standard record")
        reasons.append("; ".join(x))
    df["review_reasons"] = reasons
    df["needs_review"] = df["review_reasons"] != ""
    return df


def build_events(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    idmap = dict(zip(df["name"], df["mill_id"]))
    for _, r in df.iterrows():
        if pd.notna(r["open"]):
            rows.append((r["mill_id"], r["name"], "opened", int(r["open"]),
                         "Year uncertain per note." if r["open_year_uncertain"] else "", "csv:open"))
        if pd.notna(r["close"]):
            rows.append((r["mill_id"], r["name"], "closed", int(r["close"]),
                         "Year estimated." if r["close_year_uncertain"] else "", "csv:close"))
    for name, etype, year, detail in MANUAL_EVENTS:
        rows.append((idmap[name], name, etype, year, detail, "csv:note (manual curation)"))
    ev = pd.DataFrame(rows, columns=["mill_id", "name", "event_type", "event_year", "detail", "source"])
    return ev.sort_values(["mill_id", "event_year", "event_type"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
def to_geojson(df: pd.DataFrame, path: Path) -> None:
    props = df.drop(columns=["lat", "lon"]).astype(object).where(df.notna(), None)
    feats = []
    for i, rec in enumerate(props.to_dict("records")):
        rec = {k: (v.item() if hasattr(v, "item") else v) for k, v in rec.items()}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [float(df["lon"].iloc[i]), float(df["lat"].iloc[i])]},
                      "properties": rec})
    path.write_text(json.dumps({"type": "FeatureCollection", "name": "mills_clean",
                                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                                "features": feats}, ensure_ascii=False))


def to_gpkg(df: pd.DataFrame, path: Path) -> bool:
    try:
        import geopandas as gpd
    except ImportError:
        return False
    gdf = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    gdf.to_file(path, layer="mills", driver="GPKG")
    return True


def write_report(df: pd.DataFrame, ev: pd.DataFrame, findings: dict, path: Path, gpkg_ok: bool) -> None:
    us = df[df["in_us_scope"]]
    st = df["operational_status"].value_counts().rename_axis("status").reset_index(name="n")
    fam = pd.crosstab(df["industry_family"], df["operational_status"]).reset_index()
    cap = (df[df["capacity_available"]]
           .groupby(["capacity_group", "operational_status"])["capacity_value"]
           .agg(["count", "sum"]).reset_index().rename(columns={"count": "n", "sum": "total"}))
    cap["total"] = cap["total"].map(lambda v: f"{v:,.0f}")
    rev = df[df["needs_review"]][["mill_id", "operational_status", "status_confidence", "review_reasons"]]
    prec = int((df["coord_precision"] == "approx (~1 km)").sum())
    out = [
        "# Mills pipeline QA report", "",
        f"- Records: {len(df)} ({len(us)} in US scope; {int((~df['in_us_scope']).sum())} non-US)",
        f"- GeoPackage written: {'yes' if gpkg_ok else 'NO - geopandas not installed in this environment'}",
        f"- CRS: EPSG:4326 (WGS84 assumed; source CSV states none)",
        f"- Coordinates at <=2 decimals (~1 km precision): {prec} of {len(df)}", "",
        "## Operational status (all records)", md_table(st), "",
        "## Status by industry family", md_table(fam), "",
        "## Capacity by group and status (only records with capacity; units are NOT comparable across groups)",
        md_table(cap), "",
        "## Co-located records (identical coordinates)", md_table(findings["colocated"]), "",
        "## Distinct sites closer than 2 km", md_table(findings["near_pairs"]), "",
        "## State-median / bbox coordinate flags",
        md_table(df[df["flag_state_outlier"] | df["flag_outside_conus_bbox"]][["name", "state", "km_from_state_median"]])
        if (df["flag_state_outlier"] | df["flag_outside_conus_bbox"]).any() else "None flagged.", "",
        f"## Records needing review ({len(rev)})", md_table(rev), "",
        "## Assumptions to confirm",
        "- `checked = 1` = closure year verified (per app README); it upgrades closed records to `verified` and does nothing for open ones.",
        "- Blank `close` with no contrary note is `open` at confidence `inferred`; it is NOT confirmed operating as of today.",
        "- Coordinates are town-level per the app README, not mill footprints.",
        "- Capacity is nameplate/design where stated; it is not actual production, and groups must never be summed together.",
        "- Statuses were derived from the CSV only; no external research was done.", "",
    ]
    path.write_text("\n".join(out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=Path("raw/mills_raw.csv"))
    ap.add_argument("--outdir", type=Path, default=Path("out"))
    a = ap.parse_args()
    a.outdir.mkdir(parents=True, exist_ok=True)

    df = load_raw(a.input)
    df = classify(df)
    df = normalise(df)
    df = capacity(df)
    df, findings = spatial_qa(df)
    df = review_reasons(df)
    ev = build_events(df)

    cols_front = ["mill_id", "name", "company", "city", "state", "in_us_scope", "mill_type", "mill_subtype",
                  "industry_family", "operational_status", "status_confidence", "status_year", "status_rationale",
                  "open", "close", "open_year_uncertain", "close_year_uncertain", "checked",
                  "capacity_value", "capacity_unit", "capacity_group", "capacity_label", "capacity_available",
                  "capacity_basis", "capacity_note", "site_id", "colocated_n", "coord_precision",
                  "needs_review", "review_reasons", "note", "lat", "lon"]
    keep = cols_front + [c for c in df.columns if c not in cols_front
                         and c in ("coord_decimals", "km_from_state_median", "flag_outside_conus_bbox", "flag_state_outlier")]
    df = df[keep]

    df.to_csv(a.outdir / "mills_clean.csv", index=False)
    to_geojson(df, a.outdir / "mills_clean.geojson")
    gpkg_ok = to_gpkg(df, a.outdir / "mills_clean.gpkg")
    ev.to_csv(a.outdir / "mill_events.csv", index=False)
    write_report(df, ev, findings, a.outdir / "qa_report.md", gpkg_ok)
    print(f"{len(df)} mills, {len(ev)} events; gpkg={'yes' if gpkg_ok else 'skipped (no geopandas)'}")


if __name__ == "__main__":
    main()
