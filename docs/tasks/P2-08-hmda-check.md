# P2-08 — HMDA check that switches the value range on

- **Agent:** Codex (the plan listed Claude; the method is fixed here, so Codex builds it).
  Branch `codex/p2-08-hmda-check`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25; "Validation" in `docs/PLAN.md`). **Depends on:** P2-06
  (merged). Read `AGENTS.md`, the Phase 2 plan and `docs/tasks/P2-06-value-range.md` first.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **One new source:** `hmda` (budget `{per_day: 6}`, refresh annual, approved with the Phase 2
  plan). A normal run is **1 call**. Live gate "awaiting Claude's first live check".
- **Core changes allowed:** `pipeline/mm/values.py` (the check), `pipeline/mm/homes.py`
  (`meta.json` fields and the published switch), `config/value_range.yaml`, tests. No web code.

## Source (checked by probes 40608377396 and 40608476927, 2026-10-28)

CFPB/FFIEC HMDA Data Browser API, public loan-level data (public U.S. government data; credit
"FFIEC Home Mortgage Disclosure Act data, 2025"):
`https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?counties=48453,48491,48209&years=2025&actions_taken=1&loan_purposes=1`
→ 11.6 MB CSV, 30,323 originated home-purchase loans (Travis 13,478, Williamson 11,542, Hays
5,303), 99 columns, header row, comma-separated.

**Columns read (only these, by header name):** `activity_year`, `county_code`, `census_tract`,
`action_taken`, `loan_purpose`, `lien_status`, `derived_dwelling_category`, `total_units`,
`property_value`. **Never read** any applicant or co-applicant column (race, ethnicity, sex, age,
income, credit score, debt-to-income) or lender identifiers: HMDA's demographic fields must not
touch this project at all (ground rule 4). A test plants canaries in those columns and proves they
never reach records or logs, and `pipeline/mm/inputs.py` lists the read columns.

**Filters:** `action_taken` 1, `loan_purpose` 1, `lien_status` 1, `derived_dwelling_category`
"Single Family (1-4 Units):Site-Built", `total_units` "1", `property_value` all digits (skip
"Exempt"/"NA"/blank and count them). HMDA property values are the midpoint of a $10,000 band.

**Stored records (aggregates only, never loan rows):** one per 2020 census tract,
`dataset="hmda_tract"`, `feature_id="<census_tract>"`, properties `county`, `tract`, `year`,
`loans`, `median_value`, `p25_value`, `p75_value` (nearest-rank on the filtered values). Plus a
count-only `run_summary` (rows read, kept, skipped by reason, tracts, tracts with ≥ 30 loans).
`source_as_of` = 2025-12-31. Checks: exact required header names present; rows within 5% of
30,323; every county present; ≥ 250 tracts with ≥ 30 loans (probe: 281). `publish: none` manifest
`layers/hmda_tracts.yaml` with `refresh: annual`; SOURCES entry.

## The check (in `values.py`, run by `homes.publish`)

- **Ours:** for each tract, the median of the value-range **centre** (`mid` from the reference
  formula) over `single_family` homes that have a range and a tract (from the parcel point).
- **HMDA:** each tract's `median_value`, moved to the same date with the FHFA SA index: factor =
  latest SA quarter ÷ mean SA of the HMDA year's four quarters (2025: (705.28 + 683.03 + 677.00 +
  680.77)/4 = 686.52; 681.16 / 686.52 = 0.9922).
- Tracts with ≥ 30 loans **and** ≥ 30 of our homes. Ratio = ours ÷ HMDA (adjusted).
- **Pass** when the median ratio is between 0.90 and 1.10 **and** ≥ 75% of tracts are within
  ±20% (ratio 0.80–1.20). Also report per county (a county outside 0.90–1.10 is a warning in the
  report, not a failure).
- Preview on the real data (probe 40608476927): 263 tracts, median ratio 0.956, 85.2% within
  ±20%; Travis 148 tracts, median 0.916; Williamson 87, 1.030; Hays 28, 0.991. It passes.

## The switch

`meta.json` → `value_range.published = config.published AND check.passed AND not
value_range.test_data AND hmda is live data`. Set `published: true` in `config/value_range.yaml`
in this PR (the owner approved showing ranges once the check passes). Add to `meta.json`
`value_range.validation`: `passed`, `tracts`, `median_ratio`, `share_within_20`, per-county
figures, HMDA year and loan count, the FHFA adjustment used, the thresholds, and a one-paragraph
plain-language note: "Compared with what 2025 home buyers' lenders recorded as the property value
… sold homes are newer and larger on average than all homes, so this is an area-level check, not a
test of any one home." If the check fails, ranges stay hidden and the publish still succeeds
(facts show; the report says why).

The WCAD area-level sales-ratio check in the plan stays out of this task (Q3 caution; a later
task if wanted).

## Tests

HMDA parsing (header by name, filters, "Exempt", canaries in applicant columns, nearest-rank
percentiles, tract aggregation); check arithmetic on a hand-worked set (tract minimums, ratio
bounds at exactly 0.80/1.20 and 0.90/1.10, the 75% boundary); the FHFA adjustment (0.9922);
the switch truth table (config off, check fails, test data, HMDA fixture); `meta.json` fields;
demographic-input guard covers the HMDA columns; budget and gate.

## Other requirements

`make test` passes; report `mm publish` time and the check's result on the real canonical files
plus the HMDA fixture (labeled test data, so `published` stays false locally). STATUS one entry;
DECISIONS for unsettled choices.

## Done when

CI green, `make test` passes. Claude runs the first HMDA live check, compares the tract counts and
the check figures with the preview above, and ungates `hmda`; the next Pages build then shows
ranges once P2-07 is live.
