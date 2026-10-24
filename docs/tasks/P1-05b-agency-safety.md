# P1-05b — Safety: agency-level reported crime (DPS)

- **Agent:** Codex. Branch `codex/p1-05b-agency-safety`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1b. **Depends on:** P1-05 (merged). Read `AGENTS.md` first and follow its
  seams. Don't change `pipeline/mm/` core files or web application code.
- **No network.** Synthetic fixtures with native field names only. Claude does the live run.
- **Budget:** `dps_agency: {per_day: 10, min_interval_seconds: 2}`, refresh **annual**
  (owner approval recorded in `docs/DECISIONS.md` before this task starts). A normal run is 5
  calls. Live gate "awaiting Claude's first live check".
- **Scope:** every block group in Travis, Williamson and Hays gets the rate of the police agency
  that covers it, labeled as agency-wide. Austin PD is included here on the same method, so all
  areas compare on one basis; the APD block-group layers (P1-05) stay as they are.

## Rules (AGENTS.md)

- **Agency-level only.** One number per agency, the same for every block group that agency
  covers. Never spread or apportion agency counts onto block groups, streets or points. The
  layer title and description say "agency-wide".
- Reports are not convictions; DPS counts offenses reported by each agency (NIBRS).
- Missing is "Not available", never zero.

## Sources (checked by Claude on 2026-10-24)

1. **Texas DPS UCR "Crime in Texas" public portal** (<https://txucr.nibrs.com>, linked from DPS's
   UCR page as the "Crime in Texas Public Portal"). The 2025 *Crime in Texas* PDF has agency
   tables for the Top 25 only; the portal's Crime in Texas reports cover every agency and download
   as **XLSX** (GET, no sign-in, no cookies needed):
   `https://txucr.nibrs.com/Report/DownloadReportExcel?offenses=&startdate=Jan%20-%20{YYYY}&enddate=Dec%20-%20{YYYY}&reportId={id}`
   - `615` "Index Crime by Agency with Over 100k Jurisdictional Population" (18 KB for 2025)
   - `613` "Index Crime by Agency with 50k to 100k Jurisdictional Population" (15 KB)
   - `652` "Index Crime by Agency under 50k Jurisdictional Population" (235 KB)
   - **User agent:** the portal answers HTTP 500 ("Runtime Error") to unrecognised agents,
     including our standard one (probe runs 2026-10-24). It works from GitHub with
     `Mozilla/5.0 (compatible; metro-mapper/0.1 (+https://github.com/Kwr2000/metro-mapper))`.
     Use exactly that string for this source only (set `user_agent` on the adapter class); it
     still names the project.
   - **Workbook layout:** sheet 1 is the table, sheet 2 "Legend Info" (5 lines: "Printed On: …",
     "Beginning Date: 01/01/2025", "Ending Date: 12/31/2025", "Offenses: 09A, 09B, 11A, 11B, 11C,
     120, 13A, 200, 220, 23A-23H, 240, 64A, 64B", "Data Type: NIBRS"). Sheet 1: row 1 a title
     ("Texas Cities with 50,000 to 100,000 Population - 2025 vs 2024"); row 2 headers `ORI`,
     `Agency`, `Population`, `Murder`, `Rape`, `Robbery`, `Aggravated Assault` (the two smaller
     reports say `Assault`; it is NIBRS 13A, aggravated assault), `Burglary`, `Larceny`,
     `AutoTheft` / `Auto Theft`, two human-trafficking columns (headers contain line breaks),
     `Arson`, `Total`, `%Change` / `% Change`. Then, per agency, three rows: an agency row
     (`ORI` like `TX2460500`, name, population; other cells empty), then
     `Number of Offenses - 2024` and `Number of Offenses - 2025` rows (ORI and population empty;
     counts in the offense columns). An agency may lack the previous-year row. Numbers are stored
     as numeric cells or shared strings; parse both. Header labels vary, so map columns by
     normalised header (lower case, spaces/line breaks/hyphens removed) and fail on any header
     you can't map.
   - The portal figures are live and revisable: for 2025 the portal shows Austin PD 35,806
     total offenses, the June PDF 35,500. Label the layer with the retrieval date.
   - Terms: no license or terms stated on the portal or DPS pages; footer "© 2026 Optimum
     Technology, Inc. All Rights Reserved" (the vendor's site). Published here as state
     government statistics with credit, under the owner's Q1 decision (DECISIONS 2026-10-23).
2. **Current city limits:** TIGERweb Current, layer 28 "Incorporated Places"
   (`https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/28/query`),
   `where=GEOID IN (<the 25 place GEOIDs below>)`, `outFields=GEOID,BASENAME`, `outSR=4326`,
   `f=geojson` (one request; probe 2026-10-24: 55 places in the study bbox, max 100,000 records).
   Current boundaries, not 2020, because fast-growing cities have annexed since 2020 and DPS
   populations are 2025 jurisdictions.
3. **Block groups:** TIGERweb Census2020 layer 8, `where=STATE='48' AND COUNTY IN
   ('453','491','209')`, `outFields=GEOID`, `outSR=4326`, `f=geojson` (one request, 1,206 features;
   as in P1-05).

## Requests (5 calls)

Year `Y`: the latest full calendar year DPS has published: `run year − 1` if the run month is
July or later, else `run year − 2` (UTC). For a run in October 2026, `Y = 2025`. Keys
`dps_615`, `dps_613`, `dps_652`, `places`, `block_groups`.

`fetch()` for the three XLSX requests parses the workbook with the standard library (`zipfile`
+ `xml.etree.ElementTree`; no new dependency): sheet order from `xl/workbook.xml` and its rels,
shared strings, inline strings and numbers, cell references for column positions (empty cells
are omitted from the XML). It returns a JSON-able body
`{"sheets": {"<sheet name>": [[cell, …], …]}}` with every cell as text (empty string if blank).
The fixtures use this same shape. A response that isn't a ZIP, or HTTP status ≠ 200 → fail.

## Agency table (in the adapter; verified 2026-10-24)

City police departments and the current place they cover (ORI → place GEOID, TIGER BASENAME):

| County | ORI | Agency | Place GEOID | BASENAME |
|---|---|---|---|---|
| Travis | TX2270100 | AUSTIN PD | 4805000 | Austin |
| Travis | TX2270900 | PFLUGERVILLE PD | 4857176 | Pflugerville |
| Travis | TX2270200 | MANOR PD | 4846440 | Manor |
| Travis | TX2271100 | LAKEWAY PD | 4840984 | Lakeway |
| Travis | TX2273600 | BEE CAVE PD | 4807156 | Bee Cave |
| Travis | TX2272100 | LAGO VISTA PD | 4840264 | Lago Vista |
| Travis | TX2272200 | JONESTOWN PD | 4838020 | Jonestown |
| Travis | TX2270300 | ROLLINGWOOD PD | 4863008 | Rollingwood |
| Travis | TX2271900 | SUNSET VALLEY PD | 4871324 | Sunset Valley |
| Travis | TX2270400 | WEST LAKE HILLS PD | 4877632 | West Lake Hills |
| Travis | TX2272300 | MUSTANG RIDGE PD | 4850200 | Mustang Ridge |
| Williamson | TX2460500 | ROUND ROCK PD | 4863500 | Round Rock |
| Williamson | TX2460200 | GEORGETOWN PD | 4829336 | Georgetown |
| Williamson | TX2460900 | CEDAR PARK PD | 4813552 | Cedar Park |
| Williamson | TX2461700 | LEANDER PD | 4842016 | Leander |
| Williamson | TX2460400 | HUTTO PD | 4835624 | Hutto |
| Williamson | TX2460600 | TAYLOR PD | 4871948 | Taylor |
| Williamson | TX2462500 | JARRELL PD | 4837396 | Jarrell |
| Williamson | TX2462400 | LIBERTY HILL PD | 4842664 | Liberty Hill |
| Williamson | TX2460300 | GRANGER PD | 4830548 | Granger |
| Williamson | TX2461800 | THRALL PD | 4872824 | Thrall |
| Williamson | TX2460100 | FLORENCE PD | 4826136 | Florence |
| Hays | TX1050100 | SAN MARCOS PD | 4865600 | San Marcos |
| Hays | TX1050700 | KYLE PD | 4839952 | Kyle |
| Hays | TX1051200 | BUDA PD | 4811080 | Buda |

County sheriffs (the rest of each county, including cities with no police department in DPS's
data, such as Dripping Springs, Wimberley, Webberville, The Hills and Volente): `TX2270000`
TRAVIS CO SO (48453), `TX2460000` WILLIAMSON CO SO (48491), `TX1050000` HAYS CO SO (48209).

Not mapped (DPS population 0; their jurisdictions overlap the ones above): school-district,
university, transit, constable and fire-marshal agencies in the three counties (ORI prefixes
`TX227`, `TX246`, `TX105`), e.g. UNIV OF TX AUSTIN PD, TX STATE UNIV SAN MARCOS PD, AUSTIN ISD
PD, CAPITAL METRO TRANSIT AUTHORITY PD, TRAVIS CO CONSTABLE PCT 5. Their year-`Y` totals go in
the run summary only.

Checks on the table (fail closed): each of the 28 ORIs appears exactly once across the three
reports with a year-`Y` row and population > 0; each of the 25 place GEOIDs comes back exactly
once with the listed BASENAME; any other agency with prefix `TX227`/`TX246`/`TX105` and population
> 0 → fail ("new agency: update the table"), so a new city police department is never silently
folded into a sheriff's rate. Agencies elsewhere in Texas are ignored.

## Per agency

- `violent` = Murder + Rape + Robbery + Aggravated Assault; `property` = Burglary + Larceny +
  Auto Theft; `part1` = violent + property (arson and human trafficking excluded, matching the
  APD layer's Part I categories). The Murder column covers NIBRS 09A and 09B (legend sheet).
- `rate_part1`, `rate_violent` = per 1,000 of DPS's jurisdictional population, one decimal,
  Python nearest-even rounding. Population < 5,000 → keep the rate, and `safety_note` = "Small
  population: one shopping area or event can swing this rate".
- `part1_prev` from the `Y−1` row (null if absent); `part1_change` = percent change, one decimal
  (null if `part1_prev` is null or 0).

## Per block group (all 1,206)

Shares on unsimplified 2020 block groups and current places in EPSG:5070 (repair place
geometry with `make_valid`, as in P1-02; block groups strict). Compare unrounded shares with
the 1e-9 tolerance used elsewhere.

1. If one city in the table covers ≥ 50% of the block group → that city's police department.
2. Else, if the area outside all 25 cities is ≥ 50% → the sheriff of the block group's county
   (`GEOID[2:5]`).
3. Else → no agency: every safety value null, `safety_note` = "Not available: split between
   police agencies".

Properties: `geoid`, `county`, `agency` (e.g. "Round Rock PD"; title case of the DPS name with
`PD`, `SO`, `CO` kept as "PD", "Sheriff's Office", "County": e.g. "Travis County Sheriff's
Office"), `ori`, `agency_share` (share of the block group in the assigned jurisdiction, three
decimals), `agency_population`, `year`, `violent`, `property`, `part1`, `rate_part1`,
`rate_violent`, `part1_prev`, `part1_change`, `safety_note`, `coverage_note`, `retrieved` (run
date), `period` ("2025 (calendar year)"). `coverage_note`: for sheriffs "Unincorporated areas
and cities without their own police department"; for all: "Excludes reports by school,
university, transit and constable police". `source_as_of` = Dec 31 of `Y`.

Also emit one non-spatial `run_summary` record (as in P1-05): year, block groups per agency,
split block groups, agencies mapped, and the unmapped agencies' totals (counts only). Print it
as a count-only run note too.

## Layer

`safety_agency_rate`, group "Safety", `default_visible: false`, `refresh: annual`, `join:
block_group`, `dataset: block_group`, attribution "Texas Department of Public Safety, UCR
Crime in Texas; U.S. Census Bureau (TIGER)", `license` left empty (the site then shows "No
license stated"), disclaimer "Figures as reported to DPS by each agency; DPS
updates them as agencies revise reports."

Title "Reported Part I crime per 1,000 residents (agency-wide)". Fill on `rate_part1`, the same
5 oranges as `apd_part1_rate`, grey `#bdbdbd` for null; breaks 10, 20, 30, 50. Legend "Below 10",
"10 to below 20", "20 to below 30", "30 to below 50", "50 or more", "Not available".
Description: "One number per police agency for calendar year 2025, from reports to the Texas
Department of Public Safety, shown on every area that agency covers. It does not vary within a
city or county area and is not specific to any street. Reports are not convictions. Sheriff
rates cover unincorporated areas and cities without their own police. For detail inside Austin,
see the Austin PD block-group layers."

Popup: agency, Part I rate, violent rate, Part I offenses (violent / property), previous year
and change, agency population, share of this area in the agency's jurisdiction, period,
retrieved date (annotation on the rate), coverage note, note, GEOID.

## Fixtures and tests

Synthetic native-shape fixtures (`{"sheets": …}` bodies with the real headers, including the
line-broken trafficking headers and both "Assault" spellings; TIGER GeoJSON with native fields):
all 28 agencies across the three reports plus one university PD and one out-of-area agency;
a handful of block groups covering: inside a city, a city straddling two counties, unincorporated,
a city with no police department (falls to the sheriff), a three-way split (not available),
an exact 0.5 edge.

Tests: the year rule (June vs July runs); the XLSX parser on a tiny workbook built in the test
with `zipfile` (shared strings, numeric cells, omitted empty cells, two sheets); header mapping
and an unknown-header failure; agency row/year-row pairing, including a missing previous-year
row; sums, rates and rounding on hand-worked numbers; the small-population note; every
table check above (missing ORI, missing/duplicate place, new agency with population); the three
assignment rules and the 0.5 tolerance; unmapped agencies only in the run summary; no
apportioning (every block group of an agency has identical counts and rates); the user agent
string; budget and live gate.

## Other requirements

- Add `dps_agency` to `config/budgets.yaml` and `config/live_gates.yaml` as above.
- Update `docs/SOURCES.md` (DPS row: format XLSX via the portal) only if Claude hasn't already.
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for any
  choice not settled here.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run: 28 agencies matched; 25 places matched; block groups per
agency; how many are split (expected a handful); Austin PD 2025 Part I about 35,700 on about
1,000,639 people (about 35.7 per 1,000); unmapped-agency totals in the run summary.
