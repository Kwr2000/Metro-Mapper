# Sources

Every data source Metro Mapper uses or considered, with what was verified at the publisher,
when, and whether its data may appear on the public site (ground rule 6). Newest facts first;
re-verify anything older than a year before relying on it.

**Checked 2026-10-22** by Claude, on the publishers' own pages and files, plus the source probe
(`.github/workflows/probe.yml`, runs 39891186379 and the 02:46 UTC re-run) from GitHub's runners.

**Publish?** column:
- **Yes**: public domain, CC0, or an open license; attribution as noted.
- **Yes, conditions**: allowed with stated conditions (e.g. attribution, share-alike, no logos).
- **Yes, no license stated**: public government data with no stated license. Published with credit,
  the publisher's disclaimer and personal fields stripped (owner decision, DECISIONS 2026-10-23).
- **Checks only**: not published; used to validate our numbers, at most as summary statistics.
- **No**: terms forbid it, or we chose not to use it.

Counties: **T** Travis (48453), **W** Williamson (48491), **H** Hays (48209).

## Summary

| Source | What we use | Grain | Counties | Refresh | Unattended from Actions | Publish? |
|---|---|---|---|---|---|---|
| TCAD certified appraisal export | Market value, deed date, situs, improvements, land, subdivision | Parcel | T | Yearly (July) + supplements | Yes (direct zip, byte ranges OK) | Yes, no license stated |
| WCAD open data portal (data.wcad.org) | Property, values, improvement segments, parcels, subdivisions, permits | Parcel | W | Daily–monthly | Yes (Socrata API) | Yes, no license stated |
| WCAD certified roll downloads (SharePoint) | — | Parcel | W | Yearly | **No** (HTTP 401) | — |
| WCAD sale records (sales ratios) | Possibly area-level checks | Sale | W | Monthly | Yes (Socrata API) | Checks only, area level (DECISIONS 2026-10-23) |
| Hays CAD property data exports | Market value, living area, segments, neighborhood | Parcel | H | Monthly + certified | Yes (direct zip) | Yes, no license stated |
| TxGIO StratMap Land Parcels 2026 | Parcel polygons | Parcel | T W H | Yearly | Yes (public S3) | **Yes** (CC0) |
| Travis County GIS, TCAD parcels layer | Parcel polygons (fresher than StratMap) | Parcel | T | Monthly | Yes (2,000 per page) | Yes, no license stated |
| Hays County GIS parcels | Parcel polygons (fresher than StratMap) | Parcel | H | Irregular (last 2026-03-12) | Yes | Yes, no license stated |
| Comptroller Property Value Study 2024 | Appraisal accuracy by district | CAD | T W H | Every 2 years | Yes (page) | Yes (state facts, cited) |
| Census TIGERweb 2020 block groups | Base map unit | Block group | T W H | Fixed (2020) | Yes | Yes (public domain) |
| Census TIGERweb 2020 populated blocks | Access population weights and interior points | Census block | T W H | Fixed (2020) | Yes | Yes (public domain) |
| Census ACS 5-year 2020–2024 | Demographics with margins of error | Block group / tract | T W H | Yearly (Dec) | Yes, with key (503s on first runs were transient) | Yes (public domain) |
| APD Crime Reports (`fdj4-gpfu`) | Reported incidents by block group | Block group | Austin PD area only | Weekly | Yes (Socrata API) | **Yes** (Public Domain) |
| Texas Legislative Council, Capitol Data Portal | Presidential returns, registered voters and ballots | 2024 precinct | T W H | Yearly | Yes (two ZIPs, probe 2026-10-24/25) | Yes, conditions (CC BY) |
| Texas DPS, Crime in Texas 2025 (UCR portal) | Agency-level offense counts | Agency | T W H | Yearly | Yes (XLSX from txucr.nibrs.com; needs a "compatible" user agent) | Yes, no license stated (state statistics, cited) |
| TEA ratings on data.texas.gov (`nui6-x374`, 2024–25) | Ratings, School Progress / Academic Growth | Campus | T W H | Yearly (posted ~June) | Yes (Socrata API) | Yes, no license stated |
| TEA 2026 campus CSV (tea.texas.gov broker) | — | Campus | T W H | Yearly | Yes | No (TEA site terms) |
| District attendance-zone layers | Assigned schools | Zone | Partial | Yearly | Yes where a layer exists | No — link to each district's finder instead |
| NCES school locations / TIGER school districts | Campus points, district boundaries | Campus / district | T W H | Yearly | To probe in Phase 1 | Yes (public domain) |
| CapMetro GTFS (data.texas.gov `r4v4-vz24`) | Stops, routes, scheduled frequency | Stop / route | T, parts of W | Per service change | Yes (zip) | Yes, conditions |
| OpenStreetMap via Geofabrik Texas extract | Streets, groceries, parks, daily needs | Feature | T W H | Daily (we use ≤ monthly) | Yes (725.6 MB file) | Yes, conditions (ODbL) |
| FEMA NFHL | Flood hazard zones | Polygon | T W H | Continuous | Yes (ArcGIS service) | Yes (public domain) |
| HMDA 2025 (FFIEC/CFPB) | Tract property values of mortgaged purchases (validation, trends) | Tract | T W H | Yearly (June) | Yes (data browser API) | Yes (public) |
| City of Austin neighborhood planning areas | Area names | Polygon | Austin | Irregular | Yes | Yes, no license stated |
| WCAD subdivisions; TCAD subdivision codes; Hays County subdivisions | Area names | Polygon / code | W, T, H | Monthly / yearly | Yes | Yes, no license stated |
| Census places (TIGER) | Place names | Polygon | T W H | Yearly | Yes | Yes (public domain) |
| Redfin Data Center | Market checks | ZIP / city / metro | T W H | Was weekly/monthly; ZIP file last modified 2026-06-02 | Yes (1.5 GB file) | Checks only |
| Zillow Research (ZHVI) | Market checks | ZIP / neighborhood | T W H | Monthly | Yes (124 MB file) | Checks only |

## Appraisal rolls

### TCAD — Travis Central Appraisal District
- Page: <https://traviscad.org/publicinformation> (page modified 2026-10-09). Free downloads,
  no fee and no terms on the page; footer "Copyright 2026 | Travis Central Appraisal District".
  The TCAD FAQ "Can I get a copy of the appraisal roll?" says a full electronic copy is free on
  the website. The **maps** page (<https://traviscad.org/maps>) says "Data mining is
  prohibited". It reads as applying to the online maps and property search, which we won't use.
- **2026 Certified Appraisal Export (Supp 0, 07/18/2026)**: 557.2 MB zip, Last-Modified
  2026-07-22, byte ranges supported. 21 fixed-width files, including `PROP.TXT` (4.9 GB, record
  length 9,922, ≈ 493k records), `IMP_DET.TXT` (2.07 GB), `IMP_INFO.TXT`, `IMP_ATR.TXT`,
  `LAND_DET.TXT`, `ABS_SUBD.TXT`, `SKETCH_INFO.TXT`.
- Also: a 2026 certified JSON special export (3.55 GB zip, 29.9 GB JSON), supplemental exports
  (the latest JSON supplement is dated 10/06/2026), EARS submissions 2022–2026, and totals PDFs 2022–2026.
- Layout: `Legacy8.0.33-AppraisalExportLayout` (PDF + XLSX, dated 06/18/2026).
- Fields confirmed in the layout and in 33 sampled records: `prop_id`, `prop_type_cd`,
  `prop_val_yr`, `geo_id`, situs (`situs_num`, `situs_street`, `situs_zip`; `situs_city` often
  blank), `hood_cd`, `abs_subdv_cd`, `market_value` (cols 4214–4227), `appraised_val`,
  `assessed_val`, `deed_dt` (MM-DD-YYYY), `land_acres`. `IMP_DET.TXT` has `imprv_det_type_cd`/`desc`
  (e.g. "1st Floor"), `yr_built`, `imprv_det_area`. There is no living-area field, so living area
  is the sum of main-area segment types (code list to be confirmed in Phase 2).
- **Re-checked 2026-10-25 for P2-02** (Claude, in the browser at the publisher): layout positions
  for `PROP.TXT`, `IMP_INFO.TXT`, `IMP_DET.TXT`, `ABS_SUBD.TXT` and `TOTALS.TXT` match real
  records (line lengths 9,922 / 114 / 622 / 50 / 2,491, CRLF; `PROP` values zero-padded,
  `land_acres` with 4 implied decimals). `TOTALS.TXT` entity `03` Travis County: 453,779
  real/mobile properties, 492,900 overall, `sup_num` 0. **Living area** = segments `1ST`, `2ND`,
  `3RD`, `4TH`, `5TH`, `1/2`, `ADDL`, `FBSMT`, `RSBLW`: on TCAD's March 2026 "Improvement Details
  Report 2026" CSV (same codes and IDs; preliminary, not certified) it matches the `095` HVAC
  RESIDENTIAL area within 2% for 99.1% of 319,432 residential properties. Spec
  `docs/tasks/P2-02-tcad.md`.
- No prior-year value in the 2026 export, and no 2025 certified export is posted; the page has
  the 2025 EARS submission (Comptroller format, 81.9 MB zip). 2025 values need an owner decision.
- The certified JSON special export (3.55 GB zip, 29.9 GB JSON) also carries owner, appeal,
  sale and permit sections; we don't use it.
- **Strip at ingest** (ground rule 5): every `*_owner_*`, `*_addr_*`, `*_confidential_*`,
  every `*_exempt` and `*_qualify_yr` field, `mortgage_*`, agent names and addresses,
  `deed_num`, `deed_book_*`.
- No sale price.

### WCAD — Williamson Central Appraisal District
- Pages: <https://www.wcad.org/data-downloads/>, <https://www.wcad.org/historical-data/>.
  Certified rolls 2014–2026 (TXT in zip; 2026 = 58 MB). Most links are **SharePoint links,
  which answered HTTP 401 from GitHub** (not unattended). 2016, 2017, 2019 and 2020 are
  on `documents.wcad.org` (direct). Layout PDFs on `documents.wcad.org/DataDownloads/`.
  Disclaimer only ("As Is", may contain errors); no license.
- **Open data portal <https://data.wcad.org>** (Tyler Data & Insights/Socrata, 97 items,
  no per-dataset license; platform terms at tylertech.com/terms). Verified datasets (rows
  updated 2026-10-21/22):
  - `an3x-cnmw` Parcels: 291,178 polygons (MultiPolygon), `resflrarea`, `resyrblt`,
    `nghbrhdcd`, values. Owner and postal-address fields must be excluded in the query.
  - `ai3c-c9pf` Property – Certified: 323,073 rows for 2026, `totalsqftlivingarea` on 253,378,
    `totalpropmktvalue`, `neighborhoodcode`/`desc`, situs fields.
  - `xs93-mfpk` Imp Seg Real Property – certified; `2a8c-uwfx` Final Values – Certified;
    `yeqp-u7bx` Asmt – Certified (market, assessed, homestead cap).
  - `em3v-vwsk` Subdivisions: 8,859 polygons with name and file date.
  - `fqhf-gyjx` Building Permits: 302,883 rows, issue dates to 2026-07-22 (has party names; strip).
  - `7bnq-gqjq` ISD boundaries, `iwdk-wcuk` cities, MUD/PID/ESD/TIF layers.
  - **Sales**: `2k72-e257` Sale – Certified (1,047,066 rows), `kdj3-9hpg` Sales History,
    `8tew-hn9u` Recent Sales. No price column, but a **`salesratio`** field is filled
    (e.g. 87.90, 94.04, 121.73; 10,605 deeds in 2025 with a ratio > 0). Combined with the
    appraised value, a per-sale ratio could reveal individual sale prices. See Q3.
- The Socrata API allows column selection, counts and paging; SoQL `$query` works without a token.

### Hays CAD
- Page: <https://hayscad.com/data-downloads/>. Free; no terms or disclaimer on the page.
- **Monthly "Property Data Export"** zips (latest "as of 10-19-2026": 40.4 MB, Last-Modified
  2026-10-20), going back to 2019, plus certified (2026-07-18, Orion export, 19 MB) and
  preliminary exports. Each monthly zip holds nested zips: PROPERTY, OWNER, SALES, LAND,
  IMPROVEMENT, SEGMENT (CSV).
- PROPERTY (134,553 rows): `CurrMarketValue`, `MarketValue` (prior), `SquareFootage`
  (non-zero on 93,502), `NbhdCode`/`NbhdDesc`, situs fields, `TaxingUnitList`. SEGMENT: `Type`
  (`MA` = Main Area), `ActYrBuilt`, `EffYrBuilt`, `Area`, `Bedrooms`.
- SALES has dates, instrument and **previous owner name** (strip) but **no sale amount**, even
  though the 2018 layout PDF lists one. OWNER holds names, addresses and exemptions (don't ingest).
- Shapefile on the page (`shapefile-data.zip`, 45 MB) dates from 2024-04-19, which is stale. Use StratMap
  or Hays County GIS instead.

### Comptroller Property Value Study 2024 (category A, single-family)
| District | Ratios | Median level | COD | PRD | Within ±10% |
|---|---|---|---|---|---|
| Travis CAD | 4,732 | 1.00 | 7.59 | 1.01 | 72.97% |
| Williamson CAD | 3,670 | 0.96 | 7.57 | 1.01 | 75.59% |
| Hays CAD | 1,278 | 1.00 | 7.12 | 1.02 | 73.63% |

Pages: `comptroller.texas.gov/auto-data/PT2/ratio-study/2024/{2270000001A,2460000001A,1050000001A}.php`.
These districts are studied every other year (the 2025 pages return 404). The next study is 2026,
published in 2027.

## Parcel shapes

- **TxGIO StratMap Land Parcels 2026** — DataHub collection `1d33dafb-…`, acquisition date
  2026-09-25, **License CC0-1.0**. Per-county zips on the public S3 bucket
  `tnris-data-warehouse/LCD/collection/stratmap-2026-land-parcels/items/shp/`: Travis 104.1 MB
  (≈ 386,752 parcels), Williamson 65.7 MB (≈ 287,194), Hays 31.7 MB (≈ 121,110), all dated
  2026-10-01. The fields include `OWNER_NAME` and `MAIL_*` (strip), plus `MKT_VALUE`, `YEAR_BUILT`,
  `DATE_ACQ` and `TAX_YEAR`. The metadata suggests the underlying CAD deliveries differ by county
  (Travis 2026-02; Williamson 2025-07; Hays 2025). Check `DATE_ACQ`. TxGIO says the data is "AS-IS" and
  meant as a basemap, "not for detailed analysis".
  **Re-checked 2026-10-25 (browser):** zips still dated 2026-10-01; `.prj` WGS84; `DATE_ACQ`
  2026-07-01 for Travis (386,752 records) and Williamson (287,194), 2026-02-01 for Hays
  (121,110). Williamson `PROP_ID`s look like `R070302`; Hays has 257 blank and 292 "0" IDs;
  repeated IDs are multi-polygon parcels. Phase 2 reads only `PROP_ID`, `GEO_ID`, `GIS_AREA(_U)`,
  `FIPS`, `DATE_ACQ`, `TAX_YEAR` and geometry; owner, mailing and legal-description fields are
  never read.
- **Travis County GIS — TCAD parcels** (`gis.traviscountytx.gov/server1/rest/services/
  Boundaries_and_Jurisdictions/TCAD_public/MapServer/0`): 386,682 parcels, updated monthly
  by Travis County TNR from TCAD data, with no owner fields. Copyright text "Travis Central Appraisal
  District"; no license. Max 2,000 records per request (≈ 194 pages).
- **WCAD parcels** (`an3x-cnmw`, above): updated daily.
- **Hays County GIS — Parcels** (`services5.arcgis.com/bVphnK8rPe5MHUSr/.../Hays_County_Parcels`):
  120,913 features, item modified 2026-03-12, no license.
- TCAD also sells a countywide shapefile for $4 (per the brief). It isn't needed given the above.

## Schools

- **TEA accountability**: the 2026 campus CSV from the `rptsvr1.tea.texas.gov` broker works from
  GitHub (header `"Campus #","Campus Name","District #",…,"2026 Overall Rating"…`). The 2026 ratings
  are preliminary, with final ratings scheduled for 2026-12-11 (per Austin Watch, 2026-10-12).
  **Terms:** TEA site policies (page dated 2026-07-29): "All content on this site is copyrighted by
  the Texas Education Agency" and "cannot be used without the express written permission of
  TEA", except for districts' educational use and Texas residents' personal use. Contact:
  Copyrights@tea.texas.gov. **Not republished** (owner decision 2026-10-23).
- **TEA on the Texas Open Data Portal** (checked 2026-10-23): "School Year 2024-2025 Statewide
  Accountability Ratings", `data.texas.gov` dataset `nui6-x374`, attribution "Performance
  Reporting Division at Texas Education Agency", rows updated 2026-06-14, update frequency
  "Annually", no license field. Columns include `campus_number`, `county`, `overall_rating`/
  `score`, `student_achievement_*`, `school_progress_*`, `academic_growth_*`,
  `relative_performance_*`, `closing_the_gaps_*`, distinctions. TEA also posts AskTED
  (campus directory, `hzek-udky`, May 2026). **Published source for ratings** (a year behind
  TEA's website).
- **TEA geography** (district boundaries and school points) dates from 2010 and says it "should not
  be used to attempt determination of a school attendance zones". Not used.
- **Attendance zones**: no district attaches a license. **We don't copy zone layers**; we link to
  each district's finder (owner decision 2026-10-23). Found on ArcGIS Online on 2026-10-22:

| District | Counties | What exists | School year | Machine-readable |
|---|---|---|---|---|
| Austin ISD | T | `Reassignments` FeatureServer (81 elementary zones; MS, HS, campuses) | 2026–27 (app dated 2026-07-30) | Yes |
| Hays CISD | H | PASA "Hays School Finder" FeatureServer (17 ES zones; MS, HS, district) | Not labeled; item modified 2026-09-01 | Yes |
| Dripping Springs ISD | H, T | PASA "Dripping Springs School Finder" + "2025_26 Attendance Zones" | 2025–26 (newer item 2026-08-24) | Yes |
| Taylor ISD | W | PASA "Taylor School Finder Map" | 2025–26 app; item 2026-07-01 | Yes |
| Leander ISD | W, T | PASA lookup app (titled 2024–25; modified 2026-04-22); 2026–27 Faubion rezoning | Unclear | Behind an app |
| Elgin ISD | Mostly Bastrop; check T/W share | PASA 2025–26 lookup app | 2025–26 | Behind an app |
| Pflugerville ISD | T, W | District ArcGIS app (modified 2026-02-26) | Unclear | Behind an app |
| Hutto ISD | W | Planware "Find My Campus" + PDF maps | Not stated | No |
| Georgetown ISD | W | Zones page; rezoned for 2026–27 | 2026–27 | Not found |
| Liberty Hill ISD | W | Zones page; rezoned for 2026–27 | 2026–27 | Not found |
| Lake Travis ISD | T | Zones page | ? | Not checked |
| San Marcos CISD | H | District pages | ? | Not checked |
| Round Rock, Manor, Del Valle, Eanes, Lago Vista, Jarrell, Wimberley, others | | Not found yet | | |

  The Leander ISD page says its finder isn't for home purchase or rental decisions. Every zone
  layer is the district's (or its demographer's) current answer and can change yearly.
- **District boundaries** (checked 2026-10-23): TIGERweb `TIGERweb/School/MapServer` layer 0,
  "Unified School Districts" (current vintage; BAS 2026, ACS 2025 and Census 2020 vintages are
  layers 5, 10, 15). 53 districts intersect the study envelope; secondary and elementary
  district layers are empty here. Public domain, "Source: U.S. Census Bureau".
- **Campus points** (checked 2026-10-23): NCES EDGE `K12_School_Locations/EDGE_GEOCODE_PUBLICSCH_2425`
  layer 0, school year 2024–25, 596 public schools in Travis, Williamson and Hays
  (`CNTY` 48453/48491/48209), max 2,000 records per request. Fields include `NCESSCH`,
  `LEAID`, `NAME`, `CITY`, `LAT`/`LON`. No state campus ID; join through AskTED
  (`hzek-udky`: `school_number` ↔ `nces_school_id`, values prefixed with an apostrophe),
  which matches 582 of 596. Of those, 534 have a 2024–25 TEA rating row (`nui6-x374`: 572
  campus rows for districts headquartered in the three counties). AskTED also holds
  principals' and superintendents' names and contacts: request only the ID and district
  website columns. Public domain (NCES).

## Safety

- **APD Crime Reports** `fdj4-gpfu` (data.austintexas.gov): **license Public Domain**,
  attribution "City of Austin, Texas - data.austintexas.gov". Rows updated 2026-10-19 (newest
  report date 2026-10-18), weekly, 2003 to present. Only the highest offense per report is included.
  `census_block_group` is 10-digit text (county+tract+group, e.g. `4530011011`), present on
  92,104 of 92,613 reports since 2025-10-01 (7,412 of 7,437 in Sept 2026). **Vintage: 2020**
  (checked 2026-10-23): all 712 distinct codes reported 2025-10-01..2026-09-30 match 2020 TIGER
  block groups. `category_description` is null for non-Part I offenses (56,461 of 88,424 in
  that period).
- **Other agencies**: no open incident feed found for Round Rock, Cedar Park, Georgetown,
  Pflugerville, Leander, San Marcos or Kyle (only third-party aggregators). Use agency-level data
  from **Texas DPS Crime in Texas** (checked by Claude 2026-10-24):
  - The 2025 PDF (`dps.texas.gov/sites/default/files/documents/crimereports/25/2025cit.pdf`, 2.6 MB)
    has agency tables for the Top 25 only. DPS's 2025 supplemental reports (20 XLSX files) are
    statewide breakdowns, not by agency.
  - DPS's **UCR "Crime in Texas Public Portal"** (<https://txucr.nibrs.com>, linked from
    DPS's UCR overview page) has "Index Crime by Agency" reports for every agency, in three
    population bands (report ids 615 over 100k, 613 50k–100k, 652 under 50k), downloadable as
    XLSX by a plain GET: `Report/DownloadReportExcel?offenses=&startdate=Jan%20-%202025&enddate=Dec%20-%202025&reportId=<id>`.
    Columns: ORI, agency, DPS jurisdictional population, the 7 Part I offenses, two
    human-trafficking columns, arson, total; rows for the year and the year before. A legend
    sheet lists the NIBRS codes. All 28 Travis/Williamson/Hays city police and sheriff agencies
    are present for 2025, plus 13 zero-population agencies (schools, universities, transit,
    constables). Figures are live and revisable (Austin PD 2025: portal 35,806, PDF 35,500).
  - From GitHub's runners the portal answers HTTP 500 to unrecognised user agents; it works with
    `Mozilla/5.0 (compatible; metro-mapper/0.1 (+…))` (probe 2026-10-24).
  - Terms: none stated by DPS or on the portal; footer "© 2026 Optimum Technology, Inc. All
    Rights Reserved" (the vendor). Treated as public government statistics with no stated
    license, credited (owner's Q1 decision).
  - City limits for agency areas: TIGERweb **Current** layer 28 "Incorporated Places" (public
    domain), not 2020, since cities have annexed since 2020.
  - FBI Crime Data Explorer remains an alternative (API key needed).

## Benchmarks (P1-11)

Publisher checks and probe results supplied by Claude in `docs/tasks/P1-11-benchmarks.md`,
2026-10-25; Codex used synthetic fixtures only.

- **Census ACS 2020–2024 5-year**: the same variables, annotations, margins of error and
  definitions as the map. Four requests to <https://api.census.gov/data/2024/acs/acs5> use
  `ucgid` for US, Texas, current Austin metro (`310M700US12420`), Austin city and the three
  counties, plus the twelve named 700,000–1.5 million-population cities in the task. Census
  public-domain terms/credit are unchanged. Direct Census medians are used, not averages of
  block-group medians. The peer value is the plain mean of all twelve city values, not a
  pooled median; no peer value is emitted if any city's estimate is missing or capped.
- **Texas DPS UCR report 633**, "Crime Rate by Offense": same XLSX portal, user agent and
  Q1 publication decision as the agency tables above. The sheet supplies previous/current
  year rates per 100,000. Sum the seven Part I categories (exclude arson/trafficking), then
  divide by 100 for rates per 1,000. Report 615 also supplies combined counts/population of
  all included city agencies; ORIs can contain letters. No budget increase for DPS.
- **FBI Crime Data API / Crime Data Explorer**: <https://cde.ucr.cjis.gov/> and documented
  API base <https://api.usa.gov/crime/fbi/cde>. Public-domain U.S. government data; credit
  "FBI Crime Data API". `summarized/national/V` and `/P`, with January–December of the same
  full year as DPS. `offenses.actuals["United States Offenses"]` are monthly reported
  offenses; `populations.participated_population["United States"]` is participating
  population. Use annual total / mean participating population, not FBI estimates; about
  97% coverage. Checked 2026-10-25 (probe run 40232292906): P includes arson exactly (P = burglary + larceny
  + motor vehicle theft + arson), so the adapter also reads `ARS` (3 calls a run) and removes it,
  matching DPS Part I. An API key is required and is supplied only at transport.
  The FBI permits a city-to-state and state-to-national perspective and asks users not to
  rank/compare peer cities for crime; therefore there are no peer-city crime benchmarks.
- Schools use rated statewide campus/district rows already fetched from the TEA open-data
  source; access uses existing OSM/GTFS values weighted by populated Census blocks; elections
  use statewide totals from the same TLC files. Their original licenses/attributions remain
  unchanged. These benchmarks make no additional source requests.

## Elections

Checked by Claude on 2026-10-25 for `docs/tasks/P1-10-elections.md` (publisher and probe;
Codex builds only with synthetic fixtures). Publisher: **Texas Legislative Council, Capitol
Data Portal**; license **Creative Commons Attribution (CC BY)**. Credit "Texas Legislative
Council, Capitol Data Portal". Precinct context only; no score/ranking/model use.

- **2024 general VTD election data**, 82.1 MB ZIP, Last-Modified 2025-02-25:
  <https://data.capitol.texas.gov/dataset/35b16aee-0bb0-4866-b1ec-859f1f044241/resource/e1cd6332-6a7a-4c78-ad2a-852268f6c7a2/download/2024-general-vtds-election-data.zip>.
  Read only `2024_General_Election_Returns.csv`, `2020_General_Election_Returns.csv`, and
  each year's `General_Election_VRTO.csv`. Returns native fields: `County,FIPS,VTD,cntyvtd,
  vtdkeyvalue,Office,Name,Party,Incumbent,Votes`; use only `Office=President` in counties
  453/491/209. Parties D/R/L/G/W; L/G/W count as Other. VRTO retains only `vtdkey,TotalVR,
  TotalTO`; use FIPS transiently to filter counties. **Drop `SpanishSurnamePercent` and
  `TotalPop` immediately**, before keeping response bodies or records; never publish them.
  All historical results were re-tabulated by TLC to 2024 general precincts, not reconstructed
  by Metro Mapper. Texas has no party registration; TotalVR includes all registered voters.
- **VTDs 2024 primary & general**, 46.6 MB ZIP, Last-Modified 2025-01-29:
  <https://data.capitol.texas.gov/dataset/4d8298d0-d176-4c19-b174-42837027b73e/resource/906f47e4-4e39-4156-b1bd-4969be0b2780/download/vtds_24pg.zip>.
  Read only `VTDs_24PG.shp/.shx/.dbf/.prj`, retaining shapes for counties 453/491/209 and
  native fields `CNTY,VTD,VTDKEY,CNTYVTD`. VTDKEY joins vtdkeyvalue/vtdkey. Other DBF fields
  COLOR/CNTYKEY/Shape_area/Shape_len are unused. Parse NAD83 Texas State Mapping System
  Lambert Conformal Conic from `.prj`, reproject to WGS84, simplify for display at 5 m.
- Expected: 553 precincts (Travis 300, Williamson 166, Hays 87); 2024 D 612,262, R 384,529,
  others about 22,500; registered 1,564,474, ballots 1,024,839. About 27 precincts have under
  50 presidential votes in 2024 (16 zero); suppress their vote values, not registration or
  turnout. Thirteen have zero registered voters. Re-tabulation can produce ballots above
  registration (one 2020 precinct); suppress that turnout and explain it.
- Downloads are temporary only and deleted before fetch returns. Canonical results stay at
  precinct grain; never apportioned to block groups, tracts or addresses.

## Access

- **2020 Census populated blocks**, TIGERweb Census2020 layer 10, checked by Claude
  2026-10-24 (P1-07 spec): 21,924 blocks in Travis, Williamson and Hays with `POP100>0`.
  Request `GEOID,POP100,INTPTLAT,INTPTLON`, no geometry; one request, transfer-limit guard.
  `POP100` supplies exact 2020 population weights, and signed-text interior points are
  snapped to the access networks. Public domain; credit "U.S. Census Bureau".
  Endpoint: <https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/10/query>.
- **CapMetro GTFS**: CapMetro's developer page (<https://www.capmetro.org/developertools>) points
  to data.texas.gov. Download `https://data.texas.gov/download/r4v4-vz24/application%2Fzip`
  (33.3 MB, 11 files). `feed_info.txt`: feed start 2026-10-07, end 2027-01-09, version
  261007_1345. **The feed is current; the earlier note that the data.texas.gov copy is stale is
  out of date.** Terms ("Open Data License Agreement and Terms of Use"): CMTA "grants you
  (Licensee) non-exclusive, limited and revocable rights to use, reproduce, and redistribute CMTA
  Data". CMTA trademarks can't be used with the data, and the license is as-is and revocable.
  Much of W and H has no fixed-route service; show that as "no fixed-route service".
  San Marcos Transit and other providers: check in Phase 1.
- **OpenStreetMap**: Geofabrik `texas-latest.osm.pbf`, 725.6 MB, Last-Modified 2026-10-21.
  ODbL: credit "© OpenStreetMap contributors"; derived databases are share-alike.

## Flood

- **FEMA NFHL** (`hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28`): 20,851
  flood hazard polygons intersect the three-county box. Federal, public domain.
- Local Atlas 14 floodplains (City of Austin and others): check in Phase 1 (Austin Watch used City
  layers; reuse its findings after re-verifying).

## Demographics

- **TIGERweb Census2020 layer 8**: 1,206 block groups in T+W+H (public domain).
- **ACS 5-year 2020–2024** is the newest. The 2025 ACS releases are delayed, with no date announced.
  **Key required:** from a browser, even a keyless county-level request now redirects to
  `missing_key.html`. From GitHub, two early runs on 2026-10-23 got HTTP 503; the re-run (39891997771) with the key
  returned JSON for all 116 Hays block groups, and the keyless request got the "Missing Key" page.
  Austin Watch's request split still applies (`group(B01001)` alone; ≤ 50 variables otherwise; 60 s timeout).

## Validation and trends

- **HMDA 2025** released 2026-06-23 (snapshot as of 2026-06-01). The data browser API answered
  from GitHub: 30,323 home-purchase originations in T+W+H in 2025. `property_value` is rounded to
  the nearest $10,000 midpoint, and cash buyers are excluded (per the brief; re-verify the field
  definition against the FFIEC data dictionary in Phase 1).
- **Redfin Data Center**: no data license on the downloads page (site terms; "© 2026 Redfin.
  All rights reserved."). The ZIP tracker file was last modified 2026-06-02, so it may no longer be updating.
- **Zillow Research**: no license on the data page ("© 2026 Zillow Group"). ZHVI is available by ZIP
  and neighborhood; the ZIP file was last modified 2026-10-16.
- Both stay **checks only**, as the brief says. Summary statistics are published only after their terms are read in full.

## Names

- City of Austin neighborhood planning areas (95 areas; item modified 2026-09-25; disclaimer only)
  and subdivision boundaries.
- WCAD subdivisions (8,859), TCAD `ABS_SUBD.TXT` subdivision descriptions, Hays County GIS
  "Active Subdivisions" (modified 2026-10-22) and "Hays County Subdivisions" (2024-04-10).
- Census places (TIGER, public domain) and OSM `place=neighbourhood` (ODbL).
- Checked 2026-10-23 for P1-02b: **City of Austin subdivisions**
  (`PLANNINGCADASTRE_subdivision_boundaries/FeatureServer/0`, 16,726 features, field
  `SUBDIVISION_NAME`, names truncated at 50 characters, extent covers Travis and edges of W/H)
  and **Hays County subdivisions** (`services5.arcgis.com/bVphnK8rPe5MHUSr/.../Subdivisions/FeatureServer/4`,
  1,519 features, field `SUB_NAME`). No license stated (published under the 2026-10-23 decision).

## Gaps

- No sale prices anywhere, except WCAD's per-sale ratios (Q3).
- Crime outside Austin PD's area is agency-level only.
- Attendance zones: machine-readable for about 4–7 districts; the rest are lookup tools or PDFs.
- Transit outside CapMetro is unverified.

## Open questions for the owner

None (Q1–Q3 decided 2026-10-23; see DECISIONS).
