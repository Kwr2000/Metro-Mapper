# P1-05 — Safety: Austin PD reported incidents by block group

- **Agent:** Codex. Branch `codex/p1-05-safety`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1b. **Depends on:** P1-02 (merged). Read `AGENTS.md` first and follow its
  seams. Don't change `pipeline/mm/` core files or web application code.
- **No network.** Synthetic fixtures with native field names only. Claude does the live run.
- **Budget:** `apd: {per_day: 10, min_interval_seconds: 1}`, refresh monthly (owner approval
  recorded in `docs/DECISIONS.md` before this task starts). Live gate "awaiting Claude's first
  live check".
- **Scope:** Austin PD only. Other agencies (Round Rock, Cedar Park, Georgetown, sheriffs, …)
  have no open incident feed; their agency-level layer is a later task (P1-05b) after Claude
  checks the DPS table format. Here, block groups outside Austin PD's area are
  "Not available (outside Austin PD)", never zero.

## Rules (AGENTS.md)

- **Aggregate queries only.** Never request incident rows, report numbers, addresses, times,
  or any per-incident field. Only grouped counts by block group and category.
- No spatial detail beyond APD's own block-group assignment: no points, no heat maps, nothing
  on streets.
- Reports are not convictions or verified crimes; say so in the description.

## Sources (checked by Claude on 2026-10-23)

1. **APD Crime Reports**, data.austintexas.gov `fdj4-gpfu` (license Public Domain; credit
   "City of Austin, Texas - data.austintexas.gov"). Weekly updates; one row per report with
   only the highest offense. Fields used: `rep_date` (report date), `census_block_group`
   (10-digit text, county+tract+group, e.g. `4530011011`), `category_description`.
   - `census_block_group` codes are **2020** block groups: all 712 distinct codes in
     2025-10-01..2026-09-30 match 2020 TIGER block groups (prefix `48` to get the GEOID). 464
     of 88,424 reports in that period have no block group.
   - `category_description` is one of Murder, Rape, Robbery, Aggravated Assault (**violent**),
     Burglary, Theft, Auto Theft (**property**), or null (**other**: all remaining reported
     offenses; 56,461 of 88,424 in that period).
2. **Block groups with population**: TIGERweb Census2020 layer 8,
   `where=STATE='48' AND COUNTY IN ('453','491','209')`, `outFields=GEOID,POP100`,
   `outSR=4326`, `f=geojson` (one request). `POP100` is the 2020 Census count (exact, no
   margin of error); label it "2020 Census population".
3. **Austin city limits (2020)**: TIGERweb Census2020 layer 26 "Incorporated Places",
   `where=GEOID='4805000'`, `outSR=4326`, `f=geojson` (one request). Used only to decide
   which block groups are inside Austin PD's area.

## Requests (4 calls)

Period: the last 12 full calendar months before the run date (UTC). For a run on 2026-10-24,
that is `rep_date >= '2025-10-01T00:00:00' AND rep_date < '2026-10-01T00:00:00'`.

1. Grouped counts: `https://data.austintexas.gov/resource/fdj4-gpfu.json` with
   `$select=census_block_group,category_description,count(*) AS n`,
   `$group=census_block_group,category_description`, `$where=<period>`, `$limit=50000`
   (about 5,000 rows). Fail if the response has 50,000 rows.
2. Total for the period: `$select=count(*) AS n`, `$where=<period>`.
3. and 4. The two TIGERweb requests above.

## Per block group

- `apd_share` = area share (EPSG:5070) of the block group inside Austin's 2020 city limits.
  Block groups with `apd_share < 0.5` get every safety value null and
  `safety_note` = "Not available (outside Austin PD)". (Reports APD located there still count
  in the totals check.)
- Counts: `violent`, `property`, `other`, `total` (integers; 0 is a real zero inside the APD
  area).
- `population_2020` (`POP100`), `area_sq_mi` (land and water, EPSG:5070).
- `rate_part1` = (violent + property) per 1,000 residents, **smoothed** (below);
  `rate_part1_raw` unsmoothed; `rate_violent` smoothed and `rate_violent_raw`. If
  `population_2020 < 100`: rates are null and the note says "Too few residents for a rate"
  (mostly commercial, park or campus areas); counts and density still show.
- `density_part1` = (violent + property) per square mile (no smoothing).
- `period` = "2025-10-01 to 2026-09-30" style text; `as_of` = period end date.

### Smoothing (empirical Bayes, global prior)

Small populations make raw rates jumpy. For each measure (Part I, violent), over block groups
in the APD area with `population_2020 >= 100`: with counts yᵢ and populations nᵢ (in
thousands), the overall rate m = Σy / Σn and the between-area variance
s² = Σnᵢ(yᵢ/nᵢ − m)² / Σn − m / (Σn / N) (method of moments, Marshall 1991; if s² ≤ 0 use
s² = 0, which means every area gets m). Shrinkage weight wᵢ = s² / (s² + m / nᵢ). Smoothed
rate = wᵢ · yᵢ/nᵢ + (1 − wᵢ) · m. Round rates to 1 decimal and density to whole numbers. Write the
method on the layer description in one sentence ("Rates for small populations are pulled
toward the Austin-wide rate").

## Checks (fail closed; previous layers stay)

- Hard check (PLAN validation): Σ over all `census_block_group` counts (including null-block-group
  rows) equals request 2's total.
- At least 99% of non-null APD block-group codes match a 2020 block group in the three counties;
  otherwise fail (catches a future change of vintage). Codes outside the three counties are
  counted in a run note, not joined.
- Non-JSON, HTTP errors, missing fields, or an unknown non-null `category_description` → fail.
- Run notes: reports in period, without block group, block groups in APD area, period dates.

## Layers

Group "Safety", `default_visible: false`, `refresh: monthly`, attribution "City of Austin,
Texas - data.austintexas.gov (APD Crime Reports); U.S. Census Bureau", license "Public domain".
Both layers share one `data_bundle: apd_block_group`.

1. `apd_part1_rate`: fill choropleth on `rate_part1`, 5-step single-hue orange sequential
   (`#feedde`, `#fdbe85`, `#fd8d3c`, `#e6550d`, `#a63603`), grey `#bdbdbd` for null. Fixed breaks
   (Claude may tune them after the live run): 10, 25, 50, 100 per 1,000. Legend says "reported Part I incidents per 1,000 residents
   (smoothed)" and "Not available".
2. `apd_part1_density`: same palette on `density_part1`, breaks 50, 150, 400, 1,000 per sq mi.

Popup (both): smoothed and raw Part I rate, violent rate (smoothed and raw), density, counts
(violent / property / other / total), 2020 population, period, note, GEOID.
Description: "Reports to Austin PD over the last 12 full months, by the block group APD
assigns. Reports are not convictions; only the highest offense per report is counted. Rates for
small populations are pulled toward the Austin-wide rate. Not specific to any street. Outside
Austin PD's area: not available."

## Fixtures and tests

Synthetic Socrata grouped-count JSON and TIGER GeoJSON with native field names: a block group
outside the city, one half-inside, one with population under 100, one with zero reports, a
null-block-group row, an out-of-county code, an unknown category (failure case). Tests: period
calculation (including January runs), the totals check, the 99% vintage check, the 0.5 share rule,
the smoothing formula on a hand-worked example (including s² ≤ 0), rounding, that no planned
request selects a non-aggregate field, budget and live gate.

## Other requirements

- Add `apd` to `config/budgets.yaml` and `config/live_gates.yaml` as above.
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for any
  choice not settled here.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run (totals check passes; about 88,000 reports for the 12
months; about 712 block groups with reports; how many block groups are in the APD area).
