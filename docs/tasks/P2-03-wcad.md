# P2-03 — Williamson homes: WCAD 2026 certified facts and values

- **Agent:** Codex. Branch `codex/p2-03-wcad`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25). **Depends on:** P2-01 (merged). Read `AGENTS.md`, the
  Phase 2 plan in `docs/PLAN.md`, and `docs/tasks/P2-02-tcad.md` (same record shape) first.
  Don't change `pipeline/mm/` core or web code.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **Budget:** `wcad: {per_day: 40, min_interval_seconds: 2}`, refresh annual (approved with the
  Phase 2 plan). A normal run is about **18 calls** (below). Live gate "awaiting Claude's first
  live check".
- **No map layer and no site change.** Like P2-02, this task only stores canonical records.

## Source (verified by Claude at the publisher on 2026-10-26)

WCAD open-data portal <https://data.wcad.org> (Socrata SODA 2.1, no key; disclaimer only, no
license, recorded in `docs/SOURCES.md`). Base `https://data.wcad.org/resource/<id>.json` with
`$select`, `$where`, `$order`, `$limit`, `$offset` (or `$query`). Real responses are JSON arrays
of objects; **every value is a string** (numbers look like `"435394.000000"`, dates like
`"2026-10-21T02:00:32.620"`); a null or empty field is **omitted** from the object.

Four datasets, 2026 certified only (each holds only 2026 rows today; filter anyway):

| Dataset | Id | 2026 rows | Columns read (**only these**; always pass `$select`) |
|---|---|---|---|
| Property – Certified | `ai3c-c9pf` | 323,073 rows, 319,443 distinct `propertyid` | `propertyid`, `quickrefid`, `propertytypecode`, `neighborhoodcode`, `neighborhooddesc`, `totalpropmktvalue`, `totallandmktvalue`, `totalimpmktvalue`, `totalsqftlivingarea`, `streetnumber`, `streetdirectional`, `streetname`, `streetsuffix`, `streetsuffixdirectional`, `unitnumber`, `city`, `zip`, `condobuilding`, `condounit`, `datadate` (`$where=tax_year=2026`) |
| Improvement Real Property – Certified | `2huh-jk3y` | 254,565 | `propertyid`, `fsptb`, `vtsgimp_impvalue` (`$where=adhoctaxyear=2026`) |
| Imp Seg Real Property – certified | `xs93-mfpk` | 337,824 main-area rows | `propertyid`, `fsegtype`, `farea`, `factyear` (`$where=adhoctaxyear=2026 AND fsegtype in('MA','MA2','MA3','MA4')`) |
| TSGLand – Certified | `bens-i2m7` | 287,677 properties | grouped: `$select=propertyid, sum(faclandsize) AS acres, sum(fsftlandsize) AS sqft`, `$where=adhoctaxyear=2026`, `$group=propertyid` |

**Never query** any other dataset (Owner, PropOwner, Asmt, Exemptions, Agents, Appeals, any Sale
or Sales History table, Building Permits, Property Characteristics) and never select
`legaldescription`, `propertycomment`, `dba`, `address`, `mh*` or any owner, exemption, cap or
sale column (ground rule 5; Q3 for sales). A test checks every request's `$select` against this
allowlist.

## Requests (about 18 calls)

For each dataset: one count request (`$select=count(*)` with the same `$where`; for TSGLand,
`count(distinct propertyid)`), then pages of **100,000** rows ordered by `propertyid` (plus
`:id` as a tie-breaker; for the grouped land query, `propertyid` alone) until a short page.
Keys: `property_count`, `property_p0`, `property_p1`, …; likewise `improvement_*`, `segment_*`,
`land_*`. Fail if the rows fetched differ from the count (the portal updates daily). Expected
today: 4 + 4 + 3 + 4 + 3 = 18. Fixtures: one synthetic page per dataset in this native shape
(string values, omitted nulls), plus a test that pages correctly at a smaller page size.

## Which properties are kept

Each property's improvements carry a state code (`fsptb`). WCAD's meanings, checked on WCAD's
own property pages (search.wcad.org) and improvement descriptions on 2026-10-26: A1 single-family
residence, A2 and A5 mobile homes on real property (A5 "Mobile Homes – Permanent"), A3
misc. residential (outbuildings), A7 community property (HOA amenities), A8 condominium, A9
duplex-style single-family residence, B2 duplex, B4 four-plex, E1/E2 rural home / rural mobile
home, O1 builder inventory, M1 mobile home as personal property.

Category = the mapped code of the property's improvement with the highest `vtsgimp_impvalue`
among improvements whose code is in this map (ties: first in row order):

| `fsptb` | `category` |
|---|---|
| A1, A9 | `single_family` |
| A8 | `condo` |
| A2, A5 | `mobile_home` |
| B2, B3, B4 | `two_to_four_units` |
| E1, E2 | `rural_home` |
| O1 | `builder_inventory` |

A property with no mapped improvement is skipped and counted by its highest-value improvement's
code (or "no improvement"). M1 (personal-property mobile homes, `propertytypecode` `M`) stays
skipped, matching the owner's TCAD decision of 2026-10-26.

## Duplicates

The property table repeats some `propertyid`s (3,630 extra rows; up to 6 per property). In the
samples checked, the repeats are identical. Keep the first row if every selected column is
identical across the repeats; otherwise fail. Count `repeated_rows`.

## Record per kept property

`AreaFeature(dataset="property", feature_id="48491:<quickrefid>", geometry=EMPTY)`, with the
same property names as P2-02 so P2-05 can treat counties alike:

- `county` "Williamson", `prop_id` = `quickrefid` (e.g. `R302683`; it matches P2-01's Williamson
  IDs), `wcad_property_id` (integer `propertyid`), `geo_id` null, `category`, `state_cd`
  (the chosen `fsptb`), `prop_type` (`propertytypecode`)
- `situs_number`, `situs_prefix` (`streetdirectional`), `situs_street`, `situs_suffix`
  (`streetsuffix` plus `streetsuffixdirectional` if present), `situs_unit` (`unitnumber`, else
  `condounit`), `situs_city`, `situs_zip`, `situs` (one display line, as P2-02), `condo_building`
- `hood_cd` (`neighborhoodcode`), `hood_desc` (`neighborhooddesc`), `subdivision_code` null,
  `subdivision` null (P1-02's WCAD subdivision names already exist by area)
- `market_value`, `land_value`, `improvement_value` (whole dollars), `value_year` 2026,
  `value_as_of` "2026-01-01", `certified` = the latest `datadate` (ISO date)
- `living_area` = `totalsqftlivingarea` (round 0; 0 or missing → null). `ma_area` = sum of the
  property's MA/MA2/MA3/MA4 `farea` (null if none; kept as the check value, like `hvac_area`).
  `hvac_area` null, `adu_area` null.
- `year_built` = `factyear` of the property's largest main-area segment (null if none or 0);
  `floors` = number of main-area segments
- `land_acres` = `acres` if > 0, else `sqft` / 43,560 if > 0, else null (round 4). WCAD prices
  most subdivision lots per lot without an area, so about 70% of homes have no lot size;
  acreage-priced (larger, rural) lots do have one. Never 0.
- `dwelling_count` null, `has_adu` null, `deed_date` null, `partial_owner` null, `udi_group` null
  (not in these datasets).

One count-only `run_summary` record: rows and distinct IDs per dataset; repeated rows; kept per
category; skipped per code; living area present; MA agreement; year built present; lot size
present; if P2-01's parcels file exists, the share of kept `prop_id`s found among its
Williamson IDs (report only); runtime; peak memory.

## Checks (fail closed; nothing stored on failure)

Expected values are from Claude's full-county check on 2026-10-26.

- Rows fetched equal each dataset's count; distinct property IDs within 2% of 319,443.
- Kept properties between 215,000 and 255,000 (observed 236,087: single family 208,788, condo
  12,169, rural 5,836, mobile home 4,978, two-to-four 2,337, builder inventory 1,979).
- Every kept `quickrefid` matches `^R[0-9]+$`.
- ≥ 97% of kept `single_family` and `condo` properties have a living area (observed 99.5% of
  all kept).
- Among kept properties with both a living area and a main-area sum, ≥ 97% agree within 1 sq ft
  (observed 99.62% of 230,113).
- Numbers parse from the string form; a non-numeric value in a numeric field fails.

## Tests

Native-shape parsing (string numbers with decimals, omitted nulls, ISO `datadate`); `$select`
allowlist on every request and no forbidden dataset; paging and the count match (including a
short last page and a changed count → fail); duplicate rows identical → kept once, differing →
fail; category choice by highest improvement value and ties; skip counts; living area, MA sum,
year built from the largest MA segment; lot size from acres, then square feet, else null (never
0); `R` ID pattern; canaries: put owner-like and legal-description values in extra fields of a
fixture row and prove they never reach records or logs; budget and live gate.

## Other requirements

- Add `wcad` to `config/budgets.yaml` (exactly as approved) and `config/live_gates.yaml`.
- Update the WCAD entry in `docs/SOURCES.md` (datasets and columns used, datasets never queried).
- `make test` passes. STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green, `make test` passes. PR lists files and Claude's live checks: counts vs the numbers
above, MA agreement, living-area, year-built and lot-size coverage, share matched to P2-01
parcels, a five-property spot check against search.wcad.org (by a chat session with a
browser: two single-family, one condo, one two-to-four units, one rural home), canonical file
size, runtime, and a grep of stored data for owner/mail/exempt/legal fields (none).
