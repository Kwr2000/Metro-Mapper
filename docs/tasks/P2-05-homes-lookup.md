# P2-05 — One home record per property, address lookup files

- **Agent:** Codex. Branch `codex/p2-05-homes-lookup`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25). **Depends on:** P2-01 to P2-04 (all merged and live).
  Read `AGENTS.md`, the Phase 2 plan in `docs/PLAN.md`, and the P2-01 to P2-04 specs first.
- **No network, no new source, no budget change.** Inputs are the stored canonical files.
- **Core changes allowed:** a new module `pipeline/mm/homes.py`, one call from `mm publish`
  (after the adapters, before compile), its tests, and `Makefile`/docs if needed. No web code
  (P2-07 builds the page); no change to any adapter.

## What this produces

Static files under `web/public/data/homes/` (gitignored, built by `mm publish` in the Pages
build, like the layers) that P2-06 and P2-07 read:

1. **Address shards** `homes/addr/<shard>.json`: every kept home, findable by street address.
2. **Map grid** `homes/grid/<cell>.json`: placed homes by location, for "click a home on the map"
   at close zoom.
3. `homes/meta.json`: counties, record counts, sources and as-of dates, shard list, test-data
   flag, and the neighbourhood descriptions (`hood_desc` once per county and code, not per home).

## Inputs (stored canonical files, never sources)

`data/canonical/area_feature/{tcad,wcad,hays_cad}.ndjson.gz` (dataset `property`) and
`parcels.ndjson.gz` (dataset `parcel`). A county whose canonical file is missing is built from
that adapter's fixture records (as `mm publish` already does for layers), and `meta.json` sets
`test_data: true` for that county; the whole build is `test_data` if any county is.

## Home record (harmonized)

One record per kept property, from the P2-02/03/04 property names (all three counties already
share them). Keep: `county`, `prop_id`, `category`, `situs_*` parts and `situs`, `hood_cd`,
`market_value`, `land_value`, `improvement_value`, `value_year`, `certified`, `living_area`,
`year_built`, `land_acres`, `floors`. Add:

- `id` = the canonical `feature_id` (`48453:123456`, `48491:R302683`, `48209:123456`).
- **Location:** if `parcels` has a `parcel` record with the same `feature_id`, take its point
  (lon, lat), `block_group` and `tract`; `placed: "parcel"`. Otherwise lon/lat/block group/tract
  are null and `placed: null`. Expected today: Travis 326,568 placed of 384,236 (53,645 of the
  57,668 unplaced are condos: the parcel file has no polygon per condo unit); Williamson about
  234,152 of 236,087; Hays 88,758 of 90,157. Unplaced homes are still findable by address.
- `address_key` and `street_key` (below).

Never add owner, mailing, exemption, deed-number, sale or legal-description fields (none exist in
the inputs; the existing privacy guard runs on every published property name). No demographic
field is joined to a home record.

## Address normalization (one Python implementation, shared test vectors)

`normalize_street(prefix, name, suffix)` and `normalize_query(text)` in `homes.py`:

- Uppercase; replace `.`, `,` and `#` with spaces (keep `-` inside house numbers and `/` in
  fractions); collapse spaces.
- Directionals: NORTH/SOUTH/EAST/WEST/NORTHEAST/NORTHWEST/SOUTHEAST/SOUTHWEST → N/S/E/W/NE/NW/SE/SW
  (only as a whole word before or after the street name, never inside it: "NORTH LAMAR BLVD" →
  "N LAMAR BLVD", but "NORTHLAND DR" unchanged).
- Suffixes: the USPS Publication 28 (Appendix C1) common forms for at least: AVENUE AVE,
  BOULEVARD BLVD, CIRCLE CIR, COURT CT, COVE CV, CROSSING XING, DRIVE DR, EXPRESSWAY EXPY,
  FREEWAY FWY, HIGHWAY HWY, LANE LN, LOOP LOOP, PARKWAY PKWY, PASS PASS, PATH PATH, PLACE PL,
  PLAZA PLZ, POINT PT, RANCH RD RANCH RD, ROAD RD, RUN RUN, SQUARE SQ, STREET ST, TERRACE TER,
  TRACE TRCE, TRAIL TRL, VIEW VW, WAY WAY (last word only).
- Ordinals: FIRST…TWENTIETH → 1ST…20TH as a whole word; "1st" → "1ST".
- Highways: "FM 1626", "F M 1626", "FARM TO MARKET 1626" → "FM 1626"; "RR 620", "RANCH ROAD
  620", "RM 620" → "RR 620"; "STATE HIGHWAY 71", "SH 71", "HWY 71" → "SH 71"; "US HIGHWAY 290",
  "US 290", "US HWY 290" → "US 290"; "COUNTY ROAD 221", "CR 221" → "CR 221"; "IH 35",
  "I 35", "INTERSTATE 35" → "IH 35".
- Units: APT, APARTMENT, UNIT, STE, SUITE, BLDG, `#`, and a trailing token after the suffix
  that looks like a unit (digits/letters, e.g. "1401", "B", "12C") become the separate `unit`;
  leading zeros dropped in house numbers and units.
- `street_key` = normalized `prefix name suffix`; `address_key` = `number|street_key|unit|zip5`
  (empty parts kept as empty strings).
- `normalize_query` takes free text like Zillow's ("1008 S 8th St #2, Austin, TX 78704") and
  returns `{number, street_key, unit, zip}`; the city and state are dropped; a missing ZIP is
  allowed.
- **Test vectors** in `pipeline/mm/data/address_cases.json` (at least 60 cases: CAD forms and
  Zillow forms of the same address from each county, every rule above, units, highway names,
  "N" vs "NORTH", "NORTHLAND", ordinals, fractions, hyphenated numbers, no ZIP). P2-07 will port
  `normalize_query` to TypeScript and must pass the same file.

## Address shards

- Shard id = the first two characters (A–Z, 0–9) of the normalized street *name* (after any
  directional prefix; "FM 1626" uses "FM"). Expect a few hundred shards; any shard over 2 MB of
  JSON is split by the third character (`<two>-<third>.json`), and `meta.json` lists the split.
- Shard file: `{"v": 1, "test_data": bool, "fields": [...], "rows": [[...], ...]}`, rows sorted
  by `street_key`, then house number (numeric), then unit. `fields` (fixed order): `id`,
  `number`, `street_key`, `unit`, `zip`, `situs` (display), `city`, `county`, `category`, `lon`,
  `lat`, `block_group`, `hood_cd`, `living_area`, `year_built`, `land_acres`, `floors`,
  `market_value`, `land_value`, `improvement_value`, `value_year`, `certified`, `placed`.
  Numbers as numbers, missing as `null` (never 0).
- Lookup contract for P2-07 (documented in the module): load the shard for the query's street,
  match `number` + `street_key` (+ `unit` if given, + `zip` if given); several matches (e.g.
  condo units without a unit in the query, duplexes) are all returned.

## Map grid

Placed homes only. Cell = `floor(lon/0.01)_floor(lat/0.01)` (about 1 km); file
`homes/grid/<cell>.json` with rows `[id, lon, lat, shard]` so a click can find the nearest home
within 30 m and then load its address shard. `meta.json` lists the cells.

## Checks (fail the publish, keep the last build)

- Home counts per county equal the kept counts in each canonical `run_summary`.
- `id` unique; every placed home's lon/lat equal its parcel point exactly (no recomputation).
- Share placed ≥ 98% for Williamson and Hays and ≥ 80% for Travis (condos excepted, see above).
- Every row's `address_key` round-trips: `normalize_query(situs)` finds the home in its shard
  (≥ 99% of homes with a house number; report the misses by county with counts only).
- Total size of `homes/` under 200 MB; report it. No published property name fails the privacy
  guard.
- Deterministic output: the same inputs give byte-identical files.

## Tests

Normalization against every vector; shard id rules and the 2 MB split; merge and placement
(parcel hit, miss, condo); counts reconcile with run summaries; unique ids; nulls never 0; grid
cells and nearest lookup on a small set; fixture fallback marks test data; determinism; size
check; privacy guard; `mm publish` produces `homes/` from fixtures without network.

## Other requirements

`make test` passes and the Pages build stays under its time limit (measure `mm publish` time
with the real canonical files locally and report it). STATUS one entry; DECISIONS for unsettled
choices. Don't commit anything under `web/public/data/`.

## Done when

CI green, `make test` passes. PR lists files, the size of `homes/` and `mm publish` time on the
real data, counts per county (homes, placed, unplaced by category), shard count and largest
shard, and the round-trip miss counts. Claude then checks a dozen real Zillow-style addresses
from each county against the built files.

## Not in this task

Placing Travis condos (about 54,000) needs a location source; options are in STATUS for the
owner (P2-05b). Value ranges are P2-06; the page is P2-07.
