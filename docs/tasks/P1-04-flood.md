# P1-04 — FEMA flood shares

- **Agent:** Codex. Branch `codex/p1-04-flood`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1a. **Depends on:** P1-01 and P1-02 (merged). Read `AGENTS.md` first and
  follow its seams. Don't change `pipeline/mm/` core files.
- **No network.** Synthetic fixtures only. Claude does the live run.

## Goal

For each 2020 block group in Travis, Williamson and Hays: the share of its area in FEMA's
1% annual-chance flood hazard area (the Special Flood Hazard Area) and in the 0.2%
annual-chance zone, as one choropleth layer with both numbers in the popup.

Flood-zone **outlines** are not published in this task: about 20,000 detailed polygons are
too large for a GeoJSON file on the site. They come later with a PMTiles publisher. The popup
links to FEMA's own map for detail.

## Sources (fields verified by the source probe on 2026-10-23)

1. **FEMA NFHL, Flood Hazard Zones**:
   `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query`. Fields:
   `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `DFIRM_ID`, `VERSION_ID` (others exist; request only
   these). Query the study-area envelope (`config/app.yaml` `study_bbox`, `inSR=4326`),
   `outSR=4326`, `f=geojson`, `returnGeometry=true`, `maxAllowableOffset=0.00005` (about 5 m),
   ordered by `OBJECTID`, paged with `resultOffset`/`resultRecordCount=1000` (layer max is
   2,000; 20,851 polygons intersect the box → about 21 pages). Use `follow_up()` to request the
   next page while `exceededTransferLimit` is true. Public domain; credit "FEMA National Flood
   Hazard Layer".
2. **Block-group polygons**: TIGERweb Census2020 layer 8,
   `where=STATE='48' AND COUNTY IN ('453','491','209')`, `outFields=GEOID`, `outSR=4326`,
   `f=geojson`: one request.

## Classification

- **1% (SFHA):** `SFHA_TF = 'T'` (zones A, AE, AH, AO, AR, A99, V, VE).
- **0.2%:** `FLD_ZONE = 'X'` and `ZONE_SUBTY` contains `0.2 PCT ANNUAL CHANCE FLOOD HAZARD`
  (including variants such as "…CONTAINED IN CHANNEL" or "…WITH LEVEE"; match on that phrase).
- **Mapped:** any NFHL polygon except `FLD_ZONE = 'AREA NOT INCLUDED'`. Open water ('D' zones)
  counts as mapped.

## Per block group (EPSG:5070, whole polygon area)

- `flood_share_1pct` = area of union of SFHA polygons ∩ block group / block-group area.
- `flood_share_02pct` = same for 0.2% polygons (not including SFHA).
- `mapped_share` = area of union of mapped polygons ∩ block group / block-group area.
- If `mapped_share < 0.99`, both flood shares are **null** ("not available: FEMA map does
  not fully cover this area"), never 0, and `flood_note` says so.
- Round shares to 3 decimals. Also `geoid`, `effective_versions` (sorted distinct `VERSION_ID`
  values touching the block group, comma-joined) and `fema_map_link` =
  `https://msc.fema.gov/portal/search` (format `link`).

## Layer

`layers/flood_share.yaml`: group "Flood", polygon, `join: block_group`, fill choropleth on
`flood_share_1pct` with a 5-step sequential palette (light to dark blue), grey for null,
`default_visible: false`, `refresh: monthly`. Legend: "None", "Under 5%", "5–15%", "15–30%",
"30% or more", "Not available". Popup: 1% share, 0.2% share, mapped share, note, FEMA link,
GEOID. Description: "Share of each area inside FEMA's mapped flood zones. Not a prediction of
flooding at any address; local and Atlas 14 floodplains may be larger." Attribution as above;
license "Public domain".

## Other requirements

- Dependencies are already present (shapely, pyproj).
- Budget `fema_nfhl: {per_day: 40, min_interval_seconds: 1}` (already approved with Phase 1)
  and a live gate "awaiting Claude's first live check".
- Fail closed on a non-GeoJSON page, a page without features while more were promised, or a
  block group with no TIGER polygon. Repair invalid FEMA polygons with `shapely.make_valid`
  (keep polygonal parts); skip and count polygons with no usable geometry.
- Synthetic fixtures with native field names: a few square block groups; SFHA, 0.2% and X
  polygons including overlaps; an 'AREA NOT INCLUDED' polygon making one block group
  partially unmapped; two pages to test paging.
- Tests: classification, overlap (union, not sum), the 0.99 coverage rule, rounding, paging.
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for any
  choice not settled here.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run (1,206 block groups, nearly all fully mapped, and how
long the NFHL paging took).
