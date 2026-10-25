# P2-01 — Parcel base: where each property is

- **Agent:** Codex. Branch `codex/p2-01-parcel-base`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved by the owner 2026-10-25). **Depends on:** Phase 1. Read `AGENTS.md`
  and the Phase 2 plan in `docs/PLAN.md` first. Don't change `pipeline/mm/` core or web code.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **Budget:** `parcels: {per_day: 6, min_interval_seconds: 5, max_minutes: 30}`, refresh
  annual (approved with the Phase 2 plan). A normal run is 4 calls. Live gate "awaiting
  Claude's first live check".
- **No map layer and no site change in this task.** P2-05 publishes the lookup; this task only
  produces stored canonical records that P2-02..P2-05 join to.

## Rules

- **Nothing about people (ground rule 5).** Read only the DBF fields listed below. Never read,
  keep or log `OWNER_NAME`, `NAME_CARE`, `MAIL_*`, `LEGAL_DESC` (legal descriptions can contain
  names) or any other field. A test plants personal values in those fields and proves they
  appear nowhere in records, files or logs.
- Locations are a point inside each parcel (not outlines) in this phase.

## Source (checked by Claude in the browser on 2026-10-25)

TxGIO StratMap Land Parcels 2026, license **CC0-1.0**, credit "Texas Geographic Information
Office (TxGIO), StratMap Land Parcels 2026". Public S3, no key, one zip per county:
`https://tnris-data-warehouse.s3.us-east-1.amazonaws.com/LCD/collection/stratmap-2026-land-parcels/items/shp/stratmap-2026-land-parcels_<FIPS>_shp.zip`

| County | FIPS | Zip size | Last-Modified | Records | `DATE_ACQ` |
|---|---|---|---|---|---|
| Travis | 48453 | 104,121,915 | 2026-10-01 | 386,752 | 2026-07-01 |
| Williamson | 48491 | 65,657,083 | 2026-10-01 | 287,194 | 2026-07-01 |
| Hays | 48209 | 31,731,719 | 2026-10-01 | 121,110 | 2026-02-01 |

Each zip holds `stratmap-2026-land-parcels-<county>_<FIPS>.{shp,shx,dbf,prj,cpg,shp.xml}`. The
`.prj` is plain WGS84 (`GCS_WGS_1984`); read it anyway and fail if it is anything else. The DBF
is wide (Hays alone 261 MB); stream it.

DBF fields used: `PROP_ID` (C10), `GEO_ID` (C50), `GIS_AREA` (F31.15), `GIS_AREA_U` (C8,
"Acres"), `FIPS` (N11), `DATE_ACQ` (D8), `TAX_YEAR` (C4, "2026"). Observed:
- Travis: 407 records with `PROP_ID` "0", 46 IDs repeated; IDs are digits.
- Williamson: 132 blank IDs, 284 IDs repeated; IDs look like `R070302` (WCAD's property IDs).
- Hays: 257 blank IDs and 292 records with ID "0" (no geo ID, no legal description), 100 other
  IDs repeated (e.g. one mobile-home park ID on 6 polygons).

## Requests (4 calls)

Keys `stratmap_48453`, `stratmap_48491`, `stratmap_48209`, then `block_groups` (TIGERweb
Census2020 layer 8, `where=STATE='48' AND COUNTY IN ('453','491','209')`, `outFields=GEOID`,
`outSR=4326`, `f=geojson`, one request, as in P1-05). Stream each zip to a temporary folder
under `data/raw` (gitignored), extract only `.shp/.shx/.dbf/.prj`, parse, and delete everything
before `fetch` returns, including on error (as P1-10 does). The parsed body is JSON-able:
`{"parcels": [[prop_id, geo_id, acres, lon, lat], …], "skipped": {...}, "date_acq": "...",
"tax_year": "..."}`. Fixtures use that shape; a separate test builds a tiny real shapefile with
pyshp (already a dependency) to test the parser.

## Per parcel

- Skip blank and "0" IDs (count them by county). Group records by `PROP_ID`; a repeated ID is
  one property with several polygons: union them (repair with `make_valid` only if needed) and
  take `representative_point()` of the union in EPSG:5070, back to WGS84, 6 decimals. Use one
  `GEO_ID` (first non-blank; note in the count if they differ). `acres` = sum of `GIS_AREA`
  (round 3); fail if `GIS_AREA_U` isn't "Acres".
- `block_group` = 2020 GEOID containing the point (spatial index); points outside every study
  block group get null and are counted (edge parcels can sit across a county line).
- Record: `AreaFeature(dataset="parcel", feature_id="<FIPS>:<PROP_ID>", geometry=Point,
  properties={"county": "Travis", "prop_id": ..., "geo_id": ..., "acres": ...,
  "block_group": ..., "tract": block_group[:11] or null, "parcel_as_of": DATE_ACQ (ISO)})`.
  `source_as_of` = the latest `DATE_ACQ`.
- One count-only `run_summary` record: per county records read, IDs kept, blank/"0" skipped,
  repeated IDs merged, GEO_ID conflicts, points without a block group, runtime, peak memory.

## Checks (fail closed; nothing stored on failure)

- Kept IDs within 2% of: Travis 386,240, Williamson 286,776, Hays 120,445 (the unique non-blank,
  non-"0" IDs observed above). Claude updates these each year.
- At least 99% of kept points fall in a study block group.
- `TAX_YEAR` is the same for all records in a county; fail on a missing DBF field.
- Runtime under 30 minutes, measured in the run summary.

## Tests

Parser on a tiny synthetic shapefile (with personal-field canaries, a repeated ID with two
polygons, a blank and a "0" ID, a non-WGS84 `.prj` failure); temp files removed on success and
error; grouping/union/representative point (inside the polygon); block-group assignment and the
outside-count; count checks; canaries absent everywhere; budget and live gate. Mark any test that
builds large synthetic data `slow`.

## Other requirements

- Add `parcels` to `config/budgets.yaml` and `config/live_gates.yaml`.
- Update `docs/SOURCES.md` StratMap entry (dates above, fields used and never read).
- `make test` passes. STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green, `make test` passes. PR lists files and Claude's live checks: kept counts per county,
skipped counts, points without a block group, canonical file size (expect tens of MB), runtime
and peak memory, and a canary-style grep of stored data for owner/mail fields (none).
