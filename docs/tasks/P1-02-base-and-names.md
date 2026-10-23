# P1-02 — Block groups, tracts and area names

- **Agent:** Codex. Branch `codex/p1-02-base-and-names`.
- **Phase:** 1, wave 1a. **Depends on:** P1-01 merged. Read `AGENTS.md` first.

## Goal

The base map for Metro Mapper: every 2020 Census block group and tract in Travis (48453),
Williamson (48491) and Hays (48209) counties, each with a human-friendly name and the source of
that name.

## Sources (verified 2026-10-22; see docs/SOURCES.md)

1. **TIGERweb Census2020 MapServer layer 8 (block groups)** and the tract layer of the same
   service. Query `STATE='48' AND COUNTY IN ('453','491','209')`. Expect 1,206 block groups.
   Fields: `GEOID`, `AREALAND`, `AREAWATER`. Public domain.
2. **Census places (TIGERweb, 2020 or current)**: incorporated places and CDPs in the three
   counties. Public domain.
3. **City of Austin neighborhood planning areas**: ArcGIS FeatureServer
   `services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_neighborhood_planning_areas/FeatureServer`
   (95 areas). No license stated; publishing approved (DECISIONS 2026-10-23). Credit
   "City of Austin" and include its disclaimer.
4. **WCAD subdivisions**: Socrata `data.wcad.org` dataset `em3v-vwsk` (8,859 polygons; select
   only `name`, `scode`, `filedate`, `geometry`). Publishing approved; credit WCAD.

## Naming rule (per block group)

1. If ≥ 50% of the block group's land area lies in one Austin neighborhood planning area → that
   name, source "City of Austin neighborhood planning area".
2. Else if ≥ 50% lies in one subdivision (Williamson only in this task) → that name, source
   "WCAD subdivision".
3. Else the Census place covering the largest share → "Near <place>" if < 50%, or the place name
   if ≥ 50%, source "Census place".
4. Else "<County> County block group <last 4 of GEOID>".

Store `name`, `name_source`, `name_share` (0–1). Never invent names. If a source is
missing or empty, the rule falls through to the next one.

## Requirements

- Adapters with recorded **synthetic** fixtures (native field names, made-up shapes) and
  contract tests. No live calls during development.
- Area computations in an equal-area projection (EPSG:5070). Store geometry rounded to 6
  decimals; simplify for display only.
- Layer manifests: `block_groups` (outline, default visible), `tracts` (outline). Popup:
  name, name source, GEOID, county.
- A `geography` table (GEOID → county, tract, name, name_source, land area) that later tasks
  join to.
- Budgets: TIGERweb 6/day, City of Austin 2/day, WCAD Socrata 4/day. Refresh: yearly.

## Done when

`make test` passes, fixtures render on the map labeled "Test data", there are no live calls in
tests, and STATUS.md is updated. Claude runs the live check (expects 1,206 block groups)
before merging.
