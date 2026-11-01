# Mills pipeline QA report

- Records: 196 (195 in US scope; 1 non-US)
- GeoPackage written: NO - geopandas not installed in this environment
- CRS: EPSG:4326 (WGS84 assumed; source CSV states none)
- Coordinates at <=2 decimals (~1 km precision): 184 of 196

## Operational status (all records)
| status | n |
| --- | --- |
| open | 106 |
| closed | 72 |
| partial | 7 |
| unknown | 5 |
| reopened | 4 |
| idled | 2 |

## Status by industry family
| industry_family | closed | idled | open | partial | reopened | unknown |
| --- | --- | --- | --- | --- | --- | --- |
| pulp_paper | 61 | 2 | 65 | 6 | 1 | 2 |
| wood_products | 11 | 0 | 41 | 1 | 3 | 3 |

## Capacity by group and status (only records with capacity; units are NOT comparable across groups)
| capacity_group | operational_status | n | total |
| --- | --- | --- | --- |
| board_m3 | open | 1 | 550,000 |
| lumber_MMBF | open | 4 | 1,150 |
| panel_MMSF | open | 4 | 2,520 |
| pulp_paper_tons | closed | 3 | 640,000 |
| pulp_paper_tons | reopened | 1 | 30,000 |

## Co-located records (identical coordinates)
| site_id | name | mill_type | operational_status |
| --- | --- | --- | --- |
| 31 | Morrilton | pulp | open |
| 31 | Morrilton expansion | pulp | unknown |
| 105 | Camas | pulp | partial |
| 105 | Camas panel/paper complex | other | partial |
| 134 | Dillard MDF | mdf | unknown |
| 134 | Dillard Plywood (hardwood line) | plywood | closed |

## Distinct sites closer than 2 km
None.

## State-median / bbox coordinate flags
None flagged.

## Records needing review (21)
| mill_id | operational_status | status_confidence | review_reasons |
| --- | --- | --- | --- |
| AR-morrilton | open | inferred | co-located site |
| WA-camas | partial | needs_review | status; co-located site |
| BC-100-mile-house-sawmill | closed | verified | non-US |
| WA-camas-panel-paper-complex | partial | needs_review | status; co-located site; non-standard record |
| TX-waco-recycled-paper-mill | unknown | needs_review | status |
| AR-morrilton-expansion | unknown | needs_review | status; co-located site; non-standard record |
| MS-taylorsville-plywood | open | inferred | open year uncertain |
| OR-dillard-plywood-hardwood-line | closed | verified | co-located site |
| SC-chester-plywood | open | inferred | open year uncertain |
| MS-wiggins-plywood | closed | needs_review | status |
| MS-beaumont-plywood | unknown | needs_review | status |
| MN-cohasset-osb | unknown | needs_review | status; open year uncertain |
| AL-huguley-osb | reopened | reported | open year uncertain |
| TX-jefferson-osb | reopened | reported | open year uncertain |
| WV-sutton-osb | open | inferred | open year uncertain |
| OR-medford-mdf | open | inferred | open year uncertain |
| AR-malvern-mdf | open | inferred | open year uncertain |
| OR-eugene-mdf | closed | verified | open year uncertain |
| OR-dillard-mdf | unknown | needs_review | status; co-located site |
| AL-westervelt-gulf-states-paper | closed | inferred | open year uncertain; close year estimated |
| FL-atlas-paper-mills | open | reported | open year uncertain |

## Assumptions to confirm
- `checked = 1` = closure year verified (per app README); it upgrades closed records to `verified` and does nothing for open ones.
- Blank `close` with no contrary note is `open` at confidence `inferred`; it is NOT confirmed operating as of today.
- Coordinates are town-level per the app README, not mill footprints.
- Capacity is nameplate/design where stated; it is not actual production, and groups must never be summed together.
- Statuses were derived from the CSV only; no external research was done.
