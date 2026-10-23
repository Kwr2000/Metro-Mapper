# P1-02b — Better area names

- **Agent:** Codex. Branch `codex/p1-02b-better-names`. Regular (not draft) PR to `main`.
- **Depends on:** P1-02 (merged) and the owner's approval to raise the `areas` budget from
  20 to 30 calls a day (DECISIONS). Read `AGENTS.md` first. Only change `adapters/areas/`,
  its tests and fixtures, `layers/block_groups.yaml`, `config/budgets.yaml` and docs.
- **No network.** Synthetic fixtures only. Claude does the live run.

## Why

The first live run (2026-10-23) named 1,206 block groups: Census place 764, City of Austin
planning area 343, WCAD subdivision 68, fallback 31. 256 are just "Austin city" because the
City's neighborhood planning areas cover only part of Austin, and place names carry the Census
suffix ("Austin city", "Round Rock city", "Wells Branch CDP").

## Changes

1. **Census places:** use `BASENAME` (e.g. "Austin", "Wells Branch") instead of `NAME`, in both
   "<place>" and "Near <place>".
2. **Two more subdivision sources** (no license stated; publishing approved, DECISIONS
   2026-10-23), checked 2026-10-23:
   - **City of Austin subdivisions**:
     `https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_subdivision_boundaries/FeatureServer/0/query`,
     layer "Subdivision", 16,726 features, max 2,000 per request, extent about
     −98.16, 30.01, −97.38, 30.62 (Travis plus edges of Williamson and Hays). Request
     `where=1=1`, `outFields=SUBDIVISION_NAME`, `outSR=4326`, `f=geojson`,
     `orderByFields=OBJECTID`, `resultOffset`/`resultRecordCount=2000`, and page with
     `follow_up()` while `exceededTransferLimit` is true (about 9 pages). Credit "City of Austin".
     Names are messy and truncated at 50 characters with a trailing `*`, e.g.
     `MET CENTER II SECTION 3, LOT 4, BLOCK D, RESUBDIV*`,
     `NORTHWOODS PHASE 1-A (AKA STONE HEDGE) (RESUBMITT*`,
     `WELLS BRANCH, PH B SEC 3, AMENDED PLAT OF LOTS 42*`.
   - **Hays County subdivisions**:
     `https://services5.arcgis.com/bVphnK8rPe5MHUSr/arcgis/rest/services/Subdivisions/FeatureServer/4/query`,
     1,519 features, `outFields=SUB_NAME`; one request. Names are clean (e.g. "Wimberley
     View Estates"). Credit "Hays County".
3. **Stronger name cleaning for the City of Austin names** (keep the WCAD cleaner working):
   drop a trailing `*`; drop parenthetical text; cut at the first comma; remove
   `SECTION|SEC|PHASE|PH|UNIT|BLOCK|BLK|LOT|LOTS` and the token after each, wherever they
   appear; remove `AMENDED|REPLAT|REVISED|RESUB\w*|RESUBDIV\w*|PLAT OF|FINAL PLAT|PRELIMINARY`;
   collapse spaces; title case. If the result is empty or a single character, drop the row.
   The examples above become "Met Center II", "Northwoods", "Wells Branch". Test at least 15
   real-looking cases.
4. **Rule order per block group:**
   1. Austin neighborhood planning area ≥ 50%.
   2. Subdivision group ≥ 40%, from the source for the block group's county: WCAD for
      Williamson, City of Austin subdivisions for Travis, Hays County subdivisions for Hays.
      Group by cleaned name, union polygons, choose the largest.
   3. Census place by `BASENAME` (≥ 50% → name; otherwise "Near <name>").
   4. Fallback as now.
   `name_source` values: "City of Austin neighborhood planning area", "WCAD subdivision",
   "City of Austin subdivision", "Hays County subdivision", "Census place",
   "Census block group".
5. Update `layers/block_groups.yaml` attribution to list Hays County, and its license note.
6. Budget: `areas: {per_day: 30, min_interval_seconds: 1}` (about 24 calls per run).

## Done when

`make test` passes, CI is green, the PR lists files changed, and it says what Claude should
check in the live run (fewer "Austin" place names, and the count of each `name_source`).
