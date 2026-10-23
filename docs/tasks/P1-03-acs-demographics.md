# P1-03 — ACS demographics layers

- **Agent:** Codex. Branch `codex/p1-03-acs-demographics`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1a. **Depends on:** P1-01 and P1-02 (merged). Read `AGENTS.md` first and
  follow its seams. Don't change `pipeline/mm/` core files.
- **No network.** Synthetic fixtures only. Claude does the live run.

## Goal

ACS 2020–2024 5-year estimates for every block group and tract in Travis (48453),
Williamson (48491) and Hays (48209), with margins of error, as map layers (filters come in
P1-08). Measures: income, education, age, household type, owner-occupancy, housing age, home
value and rent, race and ethnicity.

## Rules (non-negotiable; AGENTS.md rule 4)

- Every ACS layer manifest sets `demographic: true`. Demographics are context and filters
  only. They never feed any score, ranking, value or "value for money" field; the existing
  guard test enforces it.
- Neutral presentation: one sequential single-hue blue palette for every measure (5 steps),
  no red/green, no "better/worse" words. Legends and labels say "estimate". Missing data is
  grey, "Estimate unavailable", never zero.
- Every value carries its native 90% MOE and a reliability label: `"low reliability"` when
  MOE > 30% of the estimate (zero estimate with positive MOE counts as low; exactly 30% does
  not), `"MOE ≤30% of estimate"` otherwise, `"reliability unknown"` when the MOE is missing,
  `"estimate unavailable"` when the estimate is missing.
- Negative sentinel values (e.g. -666666666, -222222222) and non-numeric cells become null,
  never numbers. Keep the EA/MA annotation strings (e.g. "250,000+") in `<metric>_annotation`.
- Estimates describe the **whole** area; never prorate.

## Source facts (verified; re-checked by Claude in the live run)

- API: `https://api.census.gov/data/2024/acs/acs5`. A key is required (keyless requests
  redirect to `missing_key.html`, checked 2026-10-22). Read `CENSUS_API_KEY` from the
  environment; add it as `key=` only inside `fetch()`; never put it in `Request.params`, fixtures,
  errors, logs or published data. Non-JSON responses are failures. Retry once on HTTP 5xx, then
  fail closed (the API gave transient 503s on 2026-10-23).
- One request may ask for one `group(...)` **or** at most 50 variables. `group(B01001)` must be
  its own request (as an explicit list it timed out at 20 s). Timeout 60 s per request.
- Geography: block groups `for=block group:*&in=state:48 county:<c> tract:*`; tracts
  `for=tract:*&in=state:48 county:<c>`. One request set per county per scale.
- Polygons: TIGERweb Census2020 layer 8 (block groups) and layer 6 (tracts),
  `where=STATE='48' AND COUNTY IN ('453','491','209')`, `outFields=GEOID`, `outSR=4326`,
  `f=geojson`: **one request per scale**. Join ACS rows by GEOID (state+county+tract[+bg]).
  Every polygon needs exactly one ACS row and vice versa; otherwise fail.
- As-of = 2024-12-31 (survey period end). Label "ACS 2020–2024 5-year estimates".

## Variables (request E, M, EA and MA for each base; keep a base's four together in one list)

| Metric (property) | Cells | Universe / denominator |
|---|---|---|
| `population` | B01003_001 | — |
| `median_household_income` (currency) | B19013_001 | — |
| `median_home_value` (currency) | B25077_001 | — |
| `median_gross_rent` (currency) | B25064_001 | — |
| `median_year_built` (number) | B25035_001 | — |
| `median_age` (number) | B01002_001 | — |
| `owner_occupied_share` | B25003_002 | B25003_001 (occupied units) |
| `under_18_share` | B01001 cells 003–006 and 027–030 | B01001_001 |
| `age_18_34_share` | B01001 cells 007–012 and 031–036 | B01001_001 |
| `age_65_plus_share` | B01001 cells 020–025 and 044–049 | B01001_001 |
| `family_children_share` | B11003_003, _010, _016 | B11003_001 (family households) |
| `one_person_share` | B11001_008 | B11001_001 (households) |
| `bachelors_plus_share` | B15003_022–025 | B15003_001 (population 25+) |
| `hispanic_latino_share` | B03002_012 | B03002_001 |
| `nh_white_share`, `nh_black_share`, `nh_aian_share`, `nh_asian_share`, `nh_nhpi_share`, `nh_some_other_share`, `nh_two_or_more_share` | B03002_003 … _009 respectively | B03002_001 |

That is 28 non-B01001 bases × 4 = 112 variables: three lists of at most 50, plus
`group(B01001)` = **4 ACS requests per county per scale = 24**, plus 2 TIGER = **26 calls per
run** (budget `acs: {per_day: 30}`, already approved with Phase 1).

Shares are fractions (0–1). Numerator estimate = sum of cells; numerator MOE =
root-sum-of-squares of cell MOEs. Share MOE = `sqrt(MN² − p²·MD²) / D`; if the radicand is
negative use `sqrt(MN² + p²·MD²) / D`. Zero or missing denominator → share unavailable.
Keep for each share: `<m>`, `<m>_moe`, `<m>_reliability`, `<m>_annotation`. Don't publish raw
cell values.

## Layers

One adapter `adapters/acs/` (`entity = "area_feature"`), datasets `block_group` and `tract`;
properties also include `geoid`, `geography` ("Block group" / "Tract") and `vintage`.
One layer per metric **per scale**, using the variant seam: `variant: {family: <metric>, key:
block_group|tract, label: "Block group"|"Tract"}`, group "People", `data_bundle:
acs_block_group` / `acs_tract` (one file per scale shared by all metrics), `demographic: true`,
`default_visible: false`, `refresh: annual`, `join: block_group|tract`, fill style with
`fill-opacity: 0.55`, popup = the metric with its MOE, reliability and annotation fields plus
GEOID, geography and vintage. Layer ids: `acs_<metric>_bg` and `acs_<metric>_tract`.
Attribution "U.S. Census Bureau, ACS 2020–2024 5-year estimates; 2020 TIGER/Line via
TIGERweb"; license "Public domain". Description says block groups are finer but noisier and
tracts steadier.

Keep the number of layers manageable: generate the manifests with a small script
(`adapters/acs/make_layers.py`, committed) rather than by hand, and commit its output.

## Other requirements

- Add `acs` to `config/budgets.yaml` (`per_day: 30, min_interval_seconds: 1`) and to
  `config/live_gates.yaml` ("awaiting Claude's first live check").
- Synthetic fixtures with native variable names (E/M/EA/MA): include sentinels, a zero
  denominator, a missing MOE, an annotation such as "250,000+", and the low-reliability edge
  (exactly 30% and just above).
- Tests: sentinel handling, MOE formulas (both branches), reliability edges, polygon/row
  mismatch fails, key never appears in request params or fixtures, demographics guard sees the
  new fields.
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for
  anything this spec didn't settle.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run (1,206 block groups and 471 tracts, every one with a row).
