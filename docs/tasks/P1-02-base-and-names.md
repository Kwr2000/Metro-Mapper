# P1-02 — Block groups, tracts and area names

- **Agent:** Codex. Branch `codex/p1-02-base-and-names`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1a. **Depends on:** P1-01 (merged). Read `AGENTS.md` first and follow its
  seams; do not change `pipeline/mm/` core files except to add dependencies in
  `pipeline/pyproject.toml`.
- **No network.** Build and test on synthetic fixtures only. Claude does the live run.

## Goal

The base map: every 2020 Census block group and tract in Travis (48453), Williamson (48491)
and Hays (48209) counties, each block group with a human-friendly name and the source of
that name.

## One adapter: `adapters/areas/`

`ADAPTER.id = "areas"`, `entity = "area_feature"`, `cadence = "yearly (names monthly)"`.
Its `plan()` makes the requests below. `normalize()` turns each response into AreaFeature
records for an internal dataset. `finalize(records)` (see `pipeline/mm/adapter.py`) does the
naming and returns only the published datasets `block_group` and `tract`. Polygons used only
for naming are not published.

### Sources (verified 2026-10-23 by the source probe; field names are exact)

1. **TIGERweb 2020 block groups**:
   `https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/8/query`
   with `where=STATE='48' AND COUNTY='<453|491|209>'`, `outFields=GEOID,STATE,COUNTY,TRACT,BLKGRP,AREALAND,AREAWATER`,
   `outSR=4326`, `f=geojson`, `returnGeometry=true`. One request per county (layer max is
   100,000 records). Expect 1,206 block groups in total. Public domain; credit "U.S. Census
   Bureau, 2020 TIGER/Line via TIGERweb".
2. **TIGERweb 2020 tracts**: same service, **layer 6**, same query shape and fields (without
   `BLKGRP`). One request per county.
3. **Census places**: same service, **layer 26** (Incorporated Places) and **layer 28** (Census
   Designated Places). Query with an envelope of the study area
   (`config/app.yaml` `study_bbox`), `outFields=GEOID,NAME,BASENAME,LSADC`. One request each.
4. **City of Austin neighborhood planning areas**:
   `https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_neighborhood_planning_areas/FeatureServer/0/query`
   (layer 0, named "Neighborhood Plan Status", 95 areas, max 2,000 per request),
   `where=1=1`, `outFields=PLANNING_AREA_NAME`, `outSR=4326`, `f=geojson`. One request. No
   license stated; publishing approved (DECISIONS 2026-10-23). Credit "City of Austin" and
   show its disclaimer: "This product is for informational purposes and may not have been
   prepared for or be suitable for legal, engineering, or surveying purposes."
5. **WCAD subdivisions** (Williamson only): Socrata
   `https://data.wcad.org/resource/em3v-vwsk.geojson` with `$select=name,scode,type,filedate,geometry`,
   `$order=scode`, `$limit=2000`, `$offset=0,2000,…` (8,859 rows ≈ 5 pages; use `follow_up()`
   to request the next page until a page has fewer than 2,000 rows). Columns are
   `name:text, scode:text, type:text, acres:number, numberlots:number, documentnumber:text,
   filedate:calendar_date, geometry:multipolygon`. No license stated; publishing approved.
   Credit "Williamson Central Appraisal District".

Every request fails closed: a non-200, non-GeoJSON, `exceededTransferLimit: true` or an
unexpected field set raises an error (the runner then publishes nothing).

## Naming rule (per block group), in `finalize`

All areas in EPSG:5070 (equal-area). Shares are the share of the block group's polygon area.

1. **Austin neighborhood planning area** covering ≥ 50% → `name = PLANNING_AREA_NAME`,
   `name_source = "City of Austin neighborhood planning area"`.
2. Else (Williamson only) **WCAD subdivision**. Clean names first: title case; drop trailing
   section, phase, unit and replat words (e.g. "SEC 3", "SECTION 3B", "PH 2", "PHASE II",
   "UNIT 4", "AMENDED", "REPLAT", "REVISED", "RESUB"); collapse spaces. Group subdivisions by
   cleaned name. If the largest group covers ≥ 40% → that name,
   `name_source = "WCAD subdivision"`.
3. Else the **Census place** with the largest share: if ≥ 50% → the place's `NAME`; if
   between 0 and 50% → `"Near " + NAME`. `name_source = "Census place"`.
4. Else `"<County> County area <TRACT>.<BLKGRP>"` (e.g. "Hays County area 010804.2"),
   `name_source = "Census block group"`.

Store `name`, `name_source`, `name_share` (0–1, 3 decimals; null for rule 4). Never invent
names. If a naming source returned nothing, fall through to the next rule.

Unit tests cover each rule, the 50%/40% edges, the name cleaning (at least 10 real-looking
cases) and the fall-through.

## Published records

- Dataset `block_group`: `feature_id` = GEOID; properties `geoid`, `county` (name),
  `tract`, `name`, `name_source`, `name_share`, `area_sq_mi` (whole polygon, 3 decimals).
  Geometry simplified for display (about 5 m tolerance, topology-preserving), 6 decimals.
- Dataset `tract`: `feature_id` = GEOID; properties `geoid`, `county`, `area_sq_mi`.
- `source_as_of`: 2020-01-01 for geometry (TIGER 2020 vintage). In the popup, say
  "2020 Census boundaries; names as of <run date>".

## Layer manifests (`layers/`)

- `block_groups.yaml`: group "Areas", polygon, `join: block_group`, line style (thin, dark grey),
  `default_visible: true`, order 10. Popup: Name, Name source, GEOID, County, Area (sq mi).
  Attribution lists all naming sources. Disclaimer: the City of Austin text above.
- `tracts.yaml`: group "Areas", polygon, line style (thicker, lighter), `default_visible: false`,
  order 11. Popup: GEOID, County, Area.
- Remove `layers/demo_landmarks.yaml`, `adapters/demo_points/` and the `demo_points` budget line
  (core tests carry their own copy in `pipeline/tests/demo/`).

## Other requirements

- Dependencies: add `shapely>=2.0,<3` and `pyproj>=3.6,<4` to `pipeline/pyproject.toml`.
- Budget line in `config/budgets.yaml`: `areas: {per_day: 20, min_interval_seconds: 1}`
  (≈ 16 calls per run). Add `areas` to `config/live_gates.yaml` with the reason "awaiting
  Claude's first live check"; Claude removes it after the live run.
- Synthetic fixtures with native field names: a handful of square block groups across the
  three counties, two tracts, one incorporated place and one CDP, one Austin planning area
  covering 60% of one block group, and WCAD subdivisions whose cleaned names cover 45% and
  35% of two block groups. Include a second WCAD page so paging is tested.
- `refresh: annual` on both layers.
- Contract test passes; `make test` passes; no live calls in tests.
- Update `docs/STATUS.md` (one short entry) and add a DECISIONS entry for any choice the spec
  didn't settle.

## Done when

CI is green and `make test` passes locally. The fixtures render on the map labeled "Test
data". The PR description lists the files changed and anything Claude should check in the
live run (expect 1,206 block groups).
