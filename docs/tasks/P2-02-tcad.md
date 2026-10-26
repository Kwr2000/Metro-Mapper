# P2-02 — Travis homes: TCAD 2026 certified facts and values

- **Agent:** Codex. Branch `codex/p2-02-tcad`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25). **Depends on:** P2-01 (parcel base) merged. Read
  `AGENTS.md`, the Phase 2 plan in `docs/PLAN.md` and `docs/tasks/P2-01-parcel-base.md` first.
  Don't change `pipeline/mm/` core or web code.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **Budget:** `tcad: {per_day: 2, max_minutes: 45}`, refresh annual (approved with the Phase 2
  plan). A normal run is **1 call**. Live gate "awaiting Claude's first live check".
- **No map layer and no site change.** This task stores canonical property records that P2-05
  joins to P2-01's parcels and publishes.

## Source (verified by Claude at the publisher on 2026-10-25)

Page <https://traviscad.org/publicinformation>. File:
`https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip`
(557,228,168 bytes, Last-Modified 2026-07-22, byte ranges supported; zip64). Layout
`Legacy8.0.33-AppraisalExportLayout` (XLSX in
`Website_Legacy8.0.33-AppraisalExportLayout_06182026.zip`). Fixed-width text, one record per
line (CRLF), single-byte encoding: decode each line as `latin-1` so byte positions = character
positions. Positions below are 1-based inclusive, from the layout and checked against real
records.

Members used (and only these): `PROP.TXT` (4,895.7 MB, record length 9,922, ≈ 492,900 records),
`IMP_INFO.TXT` (52.8 MB, 114), `IMP_DET.TXT` (2,065.5 MB, 622), `ABS_SUBD.TXT` (1.5 MB, 50),
`TOTALS.TXT` (0.6 MB). Never open the others (owners, agents, ARB, lawsuits, deferrals, sketches).

### PROP.TXT — read only these byte ranges

| Field | Pos | Notes |
|---|---|---|
| `prop_id` | 1–12 | zero-padded integer; store as a string without leading zeros |
| `prop_type_cd` | 13–17 | keep `R` and `M` only |
| `prop_val_yr` | 18–22 | must be 2026 on every record |
| `sup_num` | 23–34 | must be 0 (certified) on every record |
| `geo_id` | 547–596 | |
| `partial_owner` | 679 | `T`/`F` |
| `udi_group` | 680–691 | integer; 0 = none |
| `situs_street_prefx` | 1040–1049 | |
| `situs_street` | 1050–1099 | |
| `situs_street_suffix` | 1100–1109 | |
| `situs_city` | 1110–1139 | often blank → null |
| `situs_zip` | 1140–1149 | |
| `abs_subdv_cd` | 1676–1685 | |
| `hood_cd` | 1686–1695 | appraisal neighborhood |
| `land_hstd_val`, `land_non_hstd_val` | 1796–1810, 1811–1825 | store only their **sum** |
| `imprv_hstd_val`, `imprv_non_hstd_val` | 1826–1840, 1841–1855 | store only their **sum** |
| `deed_dt` | 2034–2058 | `MM-DD-YYYY` → ISO date; blank → null |
| `imprv_state_cd` | 2732–2741 | |
| `land_state_cd` | 2742–2751 | |
| `land_acres` | 2772–2791 | 4 implied decimals (`…1435` = 0.1435) |
| `market_value` | 4214–4227 | whole dollars |
| `situs_num` | 4460–4474 | |
| `situs_unit` | 4475–4479 | |

**Never slice any other range** (ground rule 5). In particular not owner name/ID/address
(597–678, 694–1012), confidential name (4931–5000), `hs_exempt` (2609), any `*_qualify_yr`
(5464 onward), mortgage fields, `ten_percent_cap`/`assessed_val` (they reveal a homestead), DBA,
entities. Don't store the homestead/non-homestead split, only the sums.

### IMP_INFO.TXT (one row per improvement)

`prop_id` 1–12, `prop_val_yr` 13–16, `imprv_id` 17–28, `imprv_type_cd` 29–38,
`imprv_type_desc` 39–63, `imprv_state_cd` 64–68. (Don't read `imprv_homesite` 69.)

### IMP_DET.TXT (one row per improvement segment)

`prop_id` 1–12, `prop_val_yr` 13–16, `imprv_id` 17–28, `imprv_det_id` 29–40,
`imprv_det_type_cd` 41–50, `imprv_det_type_desc` 51–75, `yr_built` 86–89 (0/blank → null),
`imprv_det_area` 94–108 (decimal, e.g. `00002986.000000`).

### ABS_SUBD.TXT

`abs_subdv_cd` 1–10, `abs_subdv_desc` 11–50 (subdivision name; title-case like P1-02c).

### TOTALS.TXT

Find the row with `entity_cd` (13–17) = `03` (`TRAVIS COUNTY`, `entity_name` 18–87); read
`num_real_mobile` 283–294 (2026: **453,779**) and `sup_num` 809–820 (must be 0).

## Living area (codes verified 2026-10-25)

TCAD has no living-area field. Living area = sum of `imprv_det_area` for these segment codes on
the property's dwelling improvements:

- Floors: `1ST`, `2ND`, `3RD`, `4TH`, `5TH`, `1/2` (Half Floor), `ADDL` (Additional Floor)
- `FBSMT` (Finished Basement), `RSBLW` (Residence Below)

Not living area: `ATTIC`, `UBSMT`, `PBSMT`, `SO` (Sketch Only), porches (`011`, `012`, `013`,
`630`, `631`), garages and carports (`031`, `041`, `051`, `061`), decks, terraces, storage, pools
and everything else.

Evidence: TCAD's "Improvement Details Report 2026" (March 2026 preliminary CSV, same codes and
IDs) for 354,065 residential properties (state codes A*): this rule gives a living area for
351,994, and for the 319,432 that also have an `095` "HVAC RESIDENTIAL" segment, the HVAC area
equals the living area within 2% for **99.1%**. Adding `ATTIC` or `SO` breaks that match; adding
`FBSMT` and `RSBLW` is what makes it.

**Dwelling improvements** = all improvements of a kept property except `imprv_type_cd` `120`
(ADU), `21` (garage apartment) and `00` (detail only/solar). ADU and garage-apartment floor area
goes to `adu_area` instead (null if none).

## Which properties are kept

`prop_type_cd` `R` or `M`, and the state code (`imprv_state_cd`, or `land_state_cd` when the
improvement code is blank) in this map to `category`:

| State codes | `category` |
|---|---|
| A1 | `single_family` |
| A4 | `condo` |
| A2 | `mobile_home` |
| B2, B3, B4 | `two_to_four_units` |
| E1, E2 | `rural_home` |
| O1 | `builder_inventory` (new construction held by a builder) |
| A3, A5, A9 | `other_residential` |

Everything else is skipped and counted by state code (apartments B1/B5, commercial, vacant
land C1, ag, utilities, etc.).

## Record per kept property

`AreaFeature(dataset="property", feature_id="48453:<prop_id>", geometry=EMPTY)` (EMPTY as in
P2-01), properties:

- `county` "Travis", `prop_id`, `geo_id`, `category`, `state_cd`, `prop_type`
- `situs_number`, `situs_prefix`, `situs_street`, `situs_suffix`, `situs_unit`, `situs_city`,
  `situs_zip` (trimmed; blank → null) and `situs` (one display line, e.g. "1008 S 8TH ST 78704")
- `hood_cd`, `subdivision_code`, `subdivision` (from ABS_SUBD; null if no match)
- `market_value` (2026, whole dollars), `land_value`, `improvement_value` (sums above),
  `value_year` 2026, `value_as_of` "2026-01-01", `certified` "2026-07-18"
- `land_acres` (round 4), `living_area` (round 0; null if none), `adu_area`, `hvac_area`
  (sum of `095` on dwelling improvements; null if none; kept as a check value)
- `year_built`: `yr_built` of the largest floor segment of the dwelling improvement with the most
  living area; null if none. `floors`: count of distinct floor codes on that improvement.
- `dwelling_count` (number of dwelling improvements with living area), `has_adu` (bool)
- `deed_date` (ISO or null), `partial_owner` (bool), `udi_group` (int or null)

No 2025 value in this task (the 2026 export has none; the owner decides the source separately).
No bedrooms/bathrooms (TCAD's `250/251/252` segments look like counts but aren't documented).

One count-only `run_summary` record: records read; R+M count; kept per category; skipped per state
code; kept with/without living area; HVAC agreement (share within 2%); partial-owner records;
TOTALS `num_real_mobile`; if `data/canonical/area_feature/parcels.ndjson.gz` exists, the share of
kept `prop_id`s found among P2-01's Travis parcels (report only); runtime; peak memory.

## Fetch and parse

One request, key `tcad_2026`. Stream the zip to a temporary folder under `data/raw`
(gitignored), then read members with `zipfile` **without extracting** (stream line by line);
delete everything before `fetch` returns, including on error (as P1-10 and P2-01 do). Read
`TOTALS`, `ABS_SUBD`, `IMP_INFO` and `IMP_DET` into compact per-property aggregates first, then
stream `PROP` once. The parsed body is JSON-able (`{"properties": [...], "summary": {...}}`);
fixtures use that shape. A separate test builds a tiny real zip of fixed-width members (correct
record lengths and positions) to test the parser.

## Checks (fail closed; nothing stored on failure)

- Every PROP record: `prop_val_yr` 2026 and `sup_num` 0; TOTALS county row `sup_num` 0.
- R+M record count within 2% of TOTALS `num_real_mobile` for entity `03`.
- Kept properties between 330,000 and 430,000 (Claude narrows this after the first run).
- ≥ 97% of kept `single_family` and `condo` properties have a living area.
- ≥ 97% of kept properties that have both a living area and an HVAC area agree within 2%.
- Every PROP line is exactly 9,922 characters (after removing CRLF); IMP_DET 622; IMP_INFO 114.
- Runtime under 45 minutes, measured in the run summary.

## Tests

Parser on the tiny zip, with canaries: an owner name in 609–678, a mailing address in 694–753,
a confidential name in 4931–5000, `T` in 2609 and a year in `hs_qualify_yr` — prove none of
them appear in records, files or logs; hs/non-hs values only appear summed. Living-area rule
(each included and excluded code, ADU split, two dwellings, half floor, finished basement,
residence below); year built from the largest floor; category mapping and skip counts; implied
decimals in `land_acres`; deed date parsing and blank; `prop_id` without leading zeros; `sup_num`
≠ 0 and wrong year fail; wrong line length fails; TOTALS count check; HVAC agreement check; temp
files removed on success and error; budget and live gate. Mark large-synthetic tests `slow`.

## Other requirements

- Add `tcad` to `config/budgets.yaml` (exactly as approved) and `config/live_gates.yaml`.
- Update the TCAD entry in `docs/SOURCES.md` (fields used, fields never read).
- `make test` passes. STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green, `make test` passes. PR lists files and Claude's live checks: R+M count vs TOTALS
(453,779), kept per category, living-area coverage, HVAC agreement, share matched to P2-01
parcels, a spot check of five properties' living area and year built against TCAD's own
property pages (by Claude in the browser), canonical file size, runtime and peak memory, and a
grep of stored data for owner/mail/exempt fields (none).
