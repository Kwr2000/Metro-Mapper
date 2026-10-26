# StratMap parcel base (P2-01)

This adapter stores property IDs, acreage and an interior point for Travis, Williamson and
Hays. It adds no map layer or site lookup. Later Phase 2 tasks join appraisal facts and
publish the lookup. Source: TxGIO StratMap Land Parcels 2026, CC0-1.0; credit "Texas Geographic
Information Office (TxGIO), StratMap Land Parcels 2026". Publisher facts and the approved
annual budget are recorded in `docs/SOURCES.md` and `docs/DECISIONS.md`.

A normal live run makes four calls: three county ZIPs and one 2020 TIGER block-group request.
The budget is six calls/day, five seconds apart, at most 30 minutes. Live use remains gated
for Claude's first check. Cadence is annual; without a layer manifest this canonical-only
source is not yet discovered by the map-layer refresh scheduler. No new manifest is added.

Each ZIP streams in 1 MiB chunks to a temporary folder under ignored `data/raw/`. Extract
only SHP/SHX/DBF/PRJ. Read the PRJ and require WGS84; no assumed CRS or fallback reprojection.
The temporary archive/components are deleted before fetch returns, including on failure.
Raw retention and recording stay disabled. A failed download/parse returns a sanitized failed
payload, preventing the core's generic retry from downloading a large private DBF twice.

Use pyshp's selected-field reader with exactly `PROP_ID`, `GEO_ID`, `GIS_AREA`, `GIS_AREA_U`,
`FIPS`, `DATE_ACQ`, `TAX_YEAR`. Only selected fields are unpacked/decoded; all other DBF
columns are padding, never parsed or retained. Owner, care-of, mailing, legal-description
and all other attribute values never enter a retained body, record, log or publication.
Tests also put invalid UTF-8 in an unselected owner cell to prove it is not decoded.

The first pass streams safe DBF attributes and groups shape indices by trimmed property ID.
Blank and exact "0" IDs are skipped; other IDs retain case and leading zeros (including
Williamson IDs such as R070302). Use the first nonblank GEO_ID, count each conflicting
property once, and sum declared GIS_AREA before rounding to three decimals. Units must be
exactly Acres. Repeated-ID and extra-record counts are distinct and reconcile read totals.

The second pass reads one property's shapes at a time. Unique-ID polygons are discarded
immediately after computing their point; only a repeated property's pieces are held for its
union. Repair invalid polygons only when needed with `make_valid`, keeping polygonal parts.
Use the unsimplified EPSG:5070 union's representative point, transform back to WGS84, and
round coordinates to six decimals. Acreage is the source's sum, not recomputed union area.

The compact body carries a single DATE_ACQ and TAX_YEAR for each county. Require both to be
constant and nonmissing there, including skipped-ID rows, so dates cannot be silently
misstated. A future mixed acquisition-date delivery requires revisiting that compact contract.
Each parcel retains its county's acquisition date; source_as_of is the latest across counties.

An STRtree assigns each rounded point to an unsimplified study block group using covers,
including boundary points. The smallest GEOID breaks boundary/overlap ties deterministically.
A point in another study county retains that block group; an outside point stays null.
At least 99% must match in every mode. Live mode also enforces county kept-ID counts within
2% of 386,240 / 286,776 / 120,445. Tiny fixtures bypass only that production volume check.
All schema, duplicate, accounting, geometry, date, deadline and 99% checks remain active.

A count-only canonical `run_summary` and stderr note retain per-county counts, acquisition
dates/tax years, unmatched points, runtime and process peak memory at finalization. The runner validates and serializes
stored records afterward; Claude also checks the complete job's resources. View it with
`python tools/live_summary.py parcels`. Only parcel and summary datasets survive finalization;
block-group polygons and intermediate metadata never enter stored records.

Regenerate the four fixture responses (six synthetic properties) with
`python adapters/parcels/make_fixtures.py`. Tests separately build tiny real shapefiles with
native field types and personal-field canaries. No test builds production-sized data.
