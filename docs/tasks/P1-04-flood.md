# P1-04 — FEMA flood shares

- **Agent:** Codex. Branch `codex/p1-04-flood`.
- **Phase:** 1, wave 1a. **Depends on:** P1-01 and P1-02 merged. Read `AGENTS.md` first.

## Goal

For each block group, the share of its land area in FEMA's 1% annual-chance flood zones (A, AE,
AH, AO, AR, A99, V, VE) and in the 0.2% annual-chance zone (X shaded / "0.2 PCT ANNUAL CHANCE
FLOOD HAZARD"), plus a flood-zone polygon layer for zooming in.

## Source

FEMA National Flood Hazard Layer, `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28`
(Flood Hazard Zones). 20,851 polygons intersect the three-county box (probe 2026-10-23). Public
domain. Use fields `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `DFIRM_ID`, `VERSION_ID`, and the
effective date from the FIRM panels layer if needed. Verify the field names against the service's
`?f=json` in the fixture-making script and record them in the adapter README.

## Requirements

- Page through results (respect `maxRecordCount`); fail closed on truncation. Budget 40/day,
  refresh monthly (polygons change with LOMRs).
- Overlay in EPSG:5070; shares are 0–1, rounded to 3 decimals. A block group with no NFHL
  coverage at all is "not available", not 0. FEMA uses "AREA NOT INCLUDED" and unmapped areas,
  so check that coverage polygons exist.
- Layers: `flood_share_1pct` (choropleth, sequential), `flood_zones` (polygons, visible from
  zoom 13). Popups show the zone, the effective date if available, and "Source: FEMA NFHL, as of …".
- Wording: "Mapped FEMA flood zone share. Not a prediction of flooding at any address; local
  and Atlas 14 floodplains may be larger." Local floodplains come in a later task.
- Synthetic fixtures with native field names and contract tests. The empty-layer guard applies.

## Done when

`make test` passes, fixtures render as "Test data", and STATUS.md is updated. Claude runs the
live check before merging.
