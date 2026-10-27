# P2-04 — Hays homes: Hays CAD 2026 facts and values

- **Agent:** Codex. Branch `codex/p2-04-hays-cad`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25). **Depends on:** P2-01 (merged). Read `AGENTS.md`, the
  Phase 2 plan in `docs/PLAN.md`, and `docs/tasks/P2-02-tcad.md` and `docs/tasks/P2-03-wcad.md`
  (same record shape) first. Don't change `pipeline/mm/` core or web code.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **Budget:** `hays_cad: {per_day: 2}`, refresh annual (approved with the Phase 2 plan). A
  normal run is **1 call**. Live gate "awaiting Claude's first live check".
- **No map layer and no site change.** Like P2-02/P2-03, this task only stores canonical records.

## Source (verified by Claude with probes 40559298690, 40559789367 and 40560747935, 2026-10-27)

Hays CAD data downloads <https://hayscad.com/data-downloads/> (free; no terms; recorded in
`docs/SOURCES.md`). **Use the monthly "Property Data Export"**, not the certified export: the
2026 certified (Orion) export has no improvement or segment files, so no living area or year
built, and its value file mixes in freeze and exemption amounts.

File (fixed in the adapter; Claude updates it each year):
`https://hayscad.com/wp-content/uploads/2026/10/2026-PROPERTY-DATA-EXPORT-FILES-AS-OF-10-19-2026.zip`
(40.4 MB, Last-Modified 2026-10-20). It holds six nested zips, each with one CSV (header row,
comma-separated, quoted fields possible; decode as `latin-1`). **Member names are numeric**
(`PropertyDataExport1419107.txt` …), so identify each file by its header row:

| File | Identify by header containing | Rows | Use |
|---|---|---|---|
| Property | `CurrMarketValue` | 134,553 (134,552 distinct `PropertyID`) | read |
| Improvement | `ImpValue` (and not `ActYrBuilt`) | 103,491 | read |
| Segment | `ActYrBuilt` | 419,776 | read |
| Land | `LandType` | 130,100 | read |
| Owner | `OwnerName` | 135,527 | **never read past the header** |
| Sales | `PrevOwnerName` | 284,269 | **never read past the header** |

Any other header, a missing file, or two files of one kind → fail. Open the outer zip in memory
or a temp folder under `data/raw` (deleted before `fetch` returns, including on error).

### Columns read (only these; look them up by header name)

- Property: `PropertyID`, `QuickRefID`, `CurrMarketValue`, `CurrLandValue`, `CurrImprovmentValue`
  (sic), `SquareFootage`, `NbhdCode`, `NbhdDesc`, `SitusPreDirectional`, `SitusStreetNumber`,
  `SitusStreetName`, `SitusStreetSuffix`, `SitusPostDirectional`, `SitusCity`, `SitusZip`,
  `LegalAcres`. Never read `LegalDesc` (legal descriptions can contain names), `Situs`
  (free text), `TaxingUnitList`, `LeaseNumber` or the prior-year value columns.
- Improvement: `PropertyID`, `InstanceID`, `Type`, `StateCode`, `ImpValue`.
- Segment: `PropertyID`, `InstanceID`, `Type`, `Area`, `ActYrBuilt`.
- Land: `PropertyID`, `Acres`, `SquareFeet`.

## Which properties are kept

Hays uses one-letter state codes on improvements (`A`, `B`, `E`, `O`; a handful of `A1`/`A5`),
and the improvement `Type` says what it is (`R` residential, `M` mobile home, `C` commercial, `I`
misc. improvement). Category = from the property's improvement with the highest `ImpValue` among
those that map (ties: first in file order):

| `StateCode` | `Type` | `category` |
|---|---|---|
| A, A1 | R | `single_family` (Hays doesn't separate condos/townhomes; say so in the README) |
| A, A5 | M | `mobile_home` |
| B | R | `two_to_four_units` (`B` with `Type` C is apartments: not kept) |
| E | R or M | `rural_home` |
| O | R | `builder_inventory` |

Everything else is skipped and counted by `StateCode|Type` (including `M1` personal-property
mobile homes, matching the owner's 2026-10-26 decision, and exempt `X*` codes).

## Record per kept property

`AreaFeature(dataset="property", feature_id="48209:<prop_id>", geometry=EMPTY)`, with P2-02's
property names:

- `county` "Hays", `prop_id` = the digits of `QuickRefID` (`R123456` → `123456`; this is the ID
  StratMap uses: 120,368 of P2-01's 120,445 Hays IDs match it, against 78,290 for `PropertyID`),
  `quickrefid` (as given), `hays_property_id` (`PropertyID`), `geo_id` null, `category`,
  `state_cd` (`StateCode`), `prop_type` (the improvement `Type`)
- situs fields from the columns above (`situs_prefix` = `SitusPreDirectional`, `situs_suffix` =
  `SitusStreetSuffix` plus `SitusPostDirectional`), `situs_unit` null, `situs` (one line)
- `hood_cd` (`NbhdCode`), `hood_desc` (`NbhdDesc`), `subdivision_code` null, `subdivision` null
- `market_value` (`CurrMarketValue`), `land_value` (`CurrLandValue`), `improvement_value`
  (`CurrImprovmentValue`), whole dollars; `value_year` 2026, `value_as_of` "2026-01-01",
  `certified` "2026-10-19" (the export date: certified values with corrections to that date)
- `living_area` = `SquareFootage` (round 0; 0 or blank → null). `ma_area` = sum of `Area` of the
  property's segments whose `Type` starts with `MA` (Hays's main-area codes: `MA`, `MA2`,
  `MAUPS9` "Main Area Upst 90%", `MAADDN` "Main Area Addition", `MAENCL` "Main Area Enclosed
  Cp/ga", and similar; check value only). `hvac_area`, `adu_area` null.
- `year_built` = `ActYrBuilt` of the property's largest `MA*` segment (0/blank → null); `floors`
  = number of `MA*` segments
- `land_acres` = sum of land `Acres` if > 0, else sum of `SquareFeet` / 43,560 if > 0, else
  `LegalAcres` if > 0, else null (round 4; never 0)
- `dwelling_count`, `has_adu`, `deed_date`, `partial_owner`, `udi_group` null.

Repeated `PropertyID` in the property file (one today): keep the first if all read columns are
identical; otherwise skip that property and count it (don't fail the run for it).

One count-only `run_summary` record: rows per file kind; kept per category; skipped per
`StateCode|Type`; living area present; `MA*` agreement; year built present; lot size present;
repeated/conflicting IDs; if P2-01's parcels file exists, the share of kept `prop_id`s among
its Hays IDs (report only); runtime; peak memory.

## Checks (fail closed; nothing stored on failure)

Expected values from the probes on 2026-10-27.

- Property file rows within 2% of 134,553; every file kind present exactly once.
- Kept properties between 82,000 and 100,000 (about 91,000 properties have an A/B/E/O
  improvement; B commercial is excluded).
- ≥ 95% of kept `single_family` properties have a living area (about 98% expected).
- Among kept properties with both a living area and an `MA*` sum, ≥ 95% agree within 1 sq ft
  (probe: 91,507 of 93,502 properties = 97.9%; the strict `MA`/`MA2` rule gives only 71%).
- Kept properties must have a `QuickRefID` matching `^R[0-9]+$`; any other (`M`, `P`, `N`
  prefixes are personal property, mobile homes and minerals) is skipped and counted, not a failure.

## Tests

A tiny real outer zip with six nested zips named like the real ones (numbers), built in the test;
file kinds found by header, in any order; owner and sales files: put canaries in their rows and
prove they are never read (the reader stops after the header), and in `LegalDesc`/`Situs` of the
property file and prove they never reach records or logs; CSV quoting; category rules incl.
`B`+`C` skipped, `M1` skipped, highest-value improvement and ties; living area, `MA*` sum and
year built from the largest `MA*` segment; lot size order and never 0; `prop_id` digits from
`QuickRefID`; repeated IDs identical → once, conflicting → skipped and counted; missing or
duplicate file kind fails; temp files removed on success and error; budget and live gate.

## Other requirements

- Add `hays_cad` to `config/budgets.yaml` (exactly as approved: `{per_day: 2}`) and
  `config/live_gates.yaml`.
- Update the Hays CAD entry in `docs/SOURCES.md` (file, columns used, files never read).
- `make test` passes. STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green, `make test` passes. PR lists files and Claude's live checks: rows per file, kept per
category, living-area coverage, `MA*` agreement, year built and lot size coverage, share matched
to P2-01 parcels (expect about 99%), a five-property spot check against Hays CAD's property
search (by a chat session with a browser), canonical file size, runtime, and a grep of stored
data for owner/mail/exempt/legal fields (none).
