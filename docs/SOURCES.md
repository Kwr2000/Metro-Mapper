# Sources

Every data source Metro Mapper uses or considered, with what was verified at the publisher,
when, and whether its data may appear on the public site (ground rule 6). Newest facts first;
re-verify anything older than a year before relying on it.

**Checked 2026-10-22** by Claude, on the publishers' own pages and files, plus the source probe
(`.github/workflows/probe.yml`, runs 39891186379 and the 02:46 UTC re-run) from GitHub's runners.

**Publish?** column:
- **Yes**: public domain, CC0, or an open license; attribution as noted.
- **Yes, conditions**: allowed with stated conditions (e.g. attribution, share-alike, no logos).
- **Owner decision**: public government data with **no license stated**. See "Open questions".
- **Checks only**: not published; used to validate our numbers, at most as summary statistics.
- **No**: terms forbid it, or we chose not to use it.

Counties: **T** Travis (48453), **W** Williamson (48491), **H** Hays (48209).

## Summary

| Source | What we use | Grain | Counties | Refresh | Unattended from Actions | Publish? |
|---|---|---|---|---|---|---|
| TCAD certified appraisal export | Market value, deed date, situs, improvements, land, subdivision | Parcel | T | Yearly (July) + supplements | Yes (direct zip, byte ranges OK) | Owner decision |
| WCAD open data portal (data.wcad.org) | Property, values, improvement segments, parcels, subdivisions, permits | Parcel | W | Daily–monthly | Yes (Socrata API) | Owner decision |
| WCAD certified roll downloads (SharePoint) | — | Parcel | W | Yearly | **No** (HTTP 401) | — |
| WCAD sale records (sales ratios) | Possibly area-level checks | Sale | W | Monthly | Yes (Socrata API) | **Owner decision** (see Q3) |
| Hays CAD property data exports | Market value, living area, segments, neighborhood | Parcel | H | Monthly + certified | Yes (direct zip) | Owner decision |
| TxGIO StratMap Land Parcels 2026 | Parcel polygons | Parcel | T W H | Yearly | Yes (public S3) | **Yes** (CC0) |
| Travis County GIS, TCAD parcels layer | Parcel polygons (fresher than StratMap) | Parcel | T | Monthly | Yes (2,000 per page) | Owner decision |
| Hays County GIS parcels | Parcel polygons (fresher than StratMap) | Parcel | H | Irregular (last 2026-03-12) | Yes | Owner decision |
| Comptroller Property Value Study 2024 | Appraisal accuracy by district | CAD | T W H | Every 2 years | Yes (page) | Yes (state facts, cited) |
| Census TIGERweb 2020 block groups | Base map unit | Block group | T W H | Fixed (2020) | Yes | Yes (public domain) |
| Census ACS 5-year 2020–2024 | Demographics with margins of error | Block group / tract | T W H | Yearly (Dec) | Yes, with key (503s on first runs were transient) | Yes (public domain) |
| APD Crime Reports (`fdj4-gpfu`) | Reported incidents by block group | Block group | Austin PD area only | Weekly | Yes (Socrata API) | **Yes** (Public Domain) |
| Texas DPS, Crime in Texas 2025 | Agency-level offense counts | Agency | T W H | Yearly | Yes (PDF) | Yes (state facts, cited) — format to check |
| TEA 2026 accountability (campus CSV) | Ratings, School Progress / growth | Campus | T W H | Yearly (Aug; final Dec) | Yes | **Owner decision** (terms restrict; see Q2) |
| District attendance-zone layers | Assigned schools | Zone | Partial | Yearly | Yes where a layer exists | Owner decision (see Q1) |
| NCES school locations / TIGER school districts | Campus points, district boundaries | Campus / district | T W H | Yearly | To probe in Phase 1 | Yes (public domain) |
| CapMetro GTFS (data.texas.gov `r4v4-vz24`) | Stops, routes, scheduled frequency | Stop / route | T, parts of W | Per service change | Yes (zip) | Yes, conditions |
| OpenStreetMap via Geofabrik Texas extract | Streets, groceries, parks, daily needs | Feature | T W H | Daily (we use ≤ monthly) | Yes (725.6 MB file) | Yes, conditions (ODbL) |
| FEMA NFHL | Flood hazard zones | Polygon | T W H | Continuous | Yes (ArcGIS service) | Yes (public domain) |
| HMDA 2025 (FFIEC/CFPB) | Tract property values of mortgaged purchases (validation, trends) | Tract | T W H | Yearly (June) | Yes (data browser API) | Yes (public) |
| City of Austin neighborhood planning areas | Area names | Polygon | Austin | Irregular | Yes | Owner decision |
| WCAD subdivisions; TCAD subdivision codes; Hays County subdivisions | Area names | Polygon / code | W, T, H | Monthly / yearly | Yes | Owner decision |
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
  Copyrights@tea.texas.gov. See Q2.
- **TEA geography** (district boundaries and school points) dates from 2010 and says it "should not
  be used to attempt determination of a school attendance zones". Not used.
- **Attendance zones**: no district attaches a license. Found on ArcGIS Online on 2026-10-22:

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
- **District boundaries and campus points**: Census TIGER school districts and NCES school
  locations are public domain; to probe in Phase 1. WCAD also publishes ISD boundaries.

## Safety

- **APD Crime Reports** `fdj4-gpfu` (data.austintexas.gov): **license Public Domain**,
  attribution "City of Austin, Texas - data.austintexas.gov". Rows updated 2026-10-19 (newest
  report date 2026-10-18), weekly, 2003 to present. Only the highest offense per report is included.
  `census_block_group` is 10-digit text (county+tract+group, e.g. `4530011011`), present on
  92,104 of 92,613 reports since 2025-10-01 (7,412 of 7,437 in Sept 2026). The block-group
  vintage isn't declared; check 2010 vs 2020 codes in Phase 1 before joining to 2020 polygons.
- **Other agencies**: no open incident feed found for Round Rock, Cedar Park, Georgetown,
  Pflugerville, Leander, San Marcos or Kyle (only third-party aggregators). Use agency-level data:
  **Texas DPS Crime in Texas 2025** (PDF, 2.6 MB, Last-Modified 2026-06-02;
  `dps.texas.gov/sites/default/files/documents/crimereports/25/2025cit.pdf`). Shown as
  jurisdiction-level only, labeled. FBI Crime Data Explorer is an alternative (API key needed).

## Access

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

## Gaps

- No sale prices anywhere, except WCAD's per-sale ratios (Q3).
- Crime outside Austin PD's area is agency-level only.
- Attendance zones: machine-readable for about 4–7 districts; the rest are lookup tools or PDFs.
- Transit outside CapMetro is unverified.

## Open questions for the owner

- **Q1. Public government data with no license** (CAD exports, county/city GIS layers,
  district zone layers): publish with attribution and the publisher's disclaimer, or ask each
  publisher first? See `docs/DECISIONS.md` (pending).
- **Q2. TEA ratings:** TEA's terms require written permission to republish.
- **Q3. WCAD sales ratios:** use them at all, and how?
