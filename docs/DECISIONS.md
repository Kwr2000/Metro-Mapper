# Decisions

Design decisions and the owner's approvals, newest first. Each entry says what was decided,
why, and (for approvals) that the owner approved it in writing.

## 2026-10-23 — Owner approvals: P1-07 access budget and ODbL

- **Owner approval:** `access: {per_day: 6, min_interval_seconds: 5, max_minutes: 25}`,
  refreshed monthly, confirmed in the owner's P1-07 build request. A normal run has four
  requests. The first live run remains gated for Claude's check.
- **Owner approval:** publish access values as a derivative database offered under
  **ODbL 1.0**, as explicitly approved in the P1-07 build request. Retain OpenStreetMap
  attribution, identify the derivation and make the derived values available on those
  terms. CapMetro's GTFS retains its CMTA Open Data License and attribution; Census inputs
  are public domain. Do not characterize the output as only a produced work to avoid the
  database share-alike obligation.

## 2026-10-23 — P1-07 access implementation choices (Codex)

- Tiny fixture mode bypasses only the production minimum volumes (100,000 walk nodes,
  50 study-area groceries, 1,000 stops/active trips, 20,000 populated blocks). Native schema,
  identifier, routing and 95% walking-snap checks remain active. Live mode always enforces
  the volume guards. Tests also exercise that distinction without live source calls.
- Walking/biking use undirected great-circle edges. Bike starts with the task's walking
  base, then applies its extra exclusions. Repeated edges take their minimum length rather
  than summing. Snapping is EPSG:5070, with a 1e-7-metre numerical tolerance at 300 m;
  snapped connector distances are not added to network times. Unreachable blocks contribute
  61 destination minutes and zero accessible CapMetro trips.
- Use the lower population-weighted median at an exact half-weight tie, avoiding interpolation
  of the 61 sentinel. Round final minutes to nearest-even whole numbers; transit is the median
  distinct-trip count divided by two. Per-measure notes distinguish capped values from finite
  values; `access_note` summarizes them. No populated blocks means nulls, never invented zeros.
- A Wednesday with any type-2 calendar removal is skipped as a holiday candidate; type-1
  additions apply on the selected date. Feed version is read from the ZIP's `feed_info.txt`
  when available and otherwise stays null. All routes count, and trips at several nearby stops
  count once per block. Stop searches hold one bounded distance vector at a time.
- Stream OSM with pyosmium's node/way callbacks, storing only bbox nodes, then compact to
  used nodes. Require node-before-way ordering, split ways at missing/outside refs, and
  ignore point parks with no measurable area. Park ways need 0.1 ha and add all boundary
  vertices. Destination ways crossing the clipping boundary cannot supply a complete vertex
  centroid and are ignored. No OSM relation destinations are added beyond the specified
  nodes/ways contract. Raw PBFs are deleted before fetch returns; OSM failures prevent a second
  core retry/download. Routing and extraction check the same 25-minute deadline.
- The unchanged adapter contract cannot append saved run notes. Print count-only notes and
  retain a separate canonical `run_summary` audit record, as in APD, with runtime and peak RSS.
  `tools/live_summary.py` displays it; map manifests select only block-group records. The layer
  as-of date is Geofabrik's Last-Modified date, with GTFS version and service date shown separately.
- pyosmium is imported only by the live-file parser. It is declared as a dependency and CI
  exercises a tiny native OSM file; offline local development can run compact fixtures without
  downloading the parser. The parser-specific test skips locally if it is not installed.

## 2026-10-24 — P1-02b live: better names published (Claude)

- Run 40044207313: 24 calls. 1,206 block groups named: Census place 641, City of Austin
  neighborhood planning area 343, City of Austin subdivision 109, WCAD subdivision 68, Hays
  County subdivision 18, fallback 27. Plain "Austin" names fell from 256 to 182.
- Spot checks read well ("Circle C Ranch", "Avalon", "Belterra", "Plum Creek", "Santa Rita
  Ranch"). Follow-ups for a later small task: planning-area names arrive in capitals ("NORTH
  AUSTIN CIVIC ASSOCIATION"); WCAD abbreviations such as "Crk" stay as given.

## 2026-10-24 — ACS published and ungated (Claude)

- Run 40043682058: 26 calls, 1,206 block groups and 471 tracts. Plain-language notes in place
  ("Census: too few survey responses to estimate" on 605 values); capped medians show ranges
  ("$250,000 or more" ×40, "$3,500 or more" ×29, "$2,000,000 or more" ×9, "2020 or later" ×8,
  "1939 or earlier" ×3, "$10,000 or less" ×1). `acs` ungated.

## 2026-10-23 — P1-02c name-polish details (Codex)

- A digit protects its entire whitespace-delimited planning-area token before hyphen
  casing; otherwise hyphen parts are cased independently, preserving `MLK` and applying
  `Mc` prefixes. Subdivision small words are lower case after the first lexical word,
  including within hyphenated names; the first word stays capitalized.
- WCAD reuses Austin's parenthesis scanner, including nested and truncated annotations.
  Strip annotations before removing repeated trailing plat qualifiers, using Austin's
  identifier grammar. Keep an ordinary word after `Sec`, and keep a non-trailing
  `Sec 1 West`; preserve numbered base names such as `Ranchettes #4`. Abbreviation
  expansion is limited to whole words in WCAD names. Hays keeps its existing qualifier
  behavior; all three subdivision sources get the small-word rule.
- Apply the polish during normalization, before the existing name-group union and share
  tests. Synthetic native-field fixtures exercise a planning name in capitals and WCAD
  spellings that combine to 45% only after polishing. No source, budget or coverage-rule
  changes; Claude checks the live output.

## 2026-10-23 — P1-08 filters and comparison choices (Codex)

- Identify named base areas by registry semantics (`join: block_group`, polygon geometry,
  a `name` popup field), never a layer id or source id. Filters and comparison use only
  block-group variants; no tract-to-block-group interpolation. Future eligible layers join
  automatically. Cache each local publication URL once for map, filters and comparison;
  load on demand, and never request a data-source API from these controls.
- Active numeric filters intersect inclusive ranges. A missing/non-finite value excludes
  the area; each missing count is measured against all loaded base areas independently of
  other filters. Disabled filters have no effect. Native shared-track range handles have
  exact numeric inputs; percentage values are converted from shares to percentage units.
  Observed bounds initialize the controls, and exact inputs may extend those bounds.
- People (context only) appears last, with the task's neutral wording, in filters, layers,
  comparison, sources and map inspection. People controls start off and collapsed; an
  explicitly shared or saved layer choice can restore them. No sorting control, ranking
  or combined score is added. Comparisons preserve the user's area order and reuse the
  popup formatter, including MOE, reliability, annotations, capped values and safe links.
- Jurisdiction context uses a scan-line interior point, avoiding holes and concave-boundary
  centres; only already-loaded jurisdiction polygons are queried. Show their name and
  link fields, with source/date, without assigning schools or attendance zones.
- The shortlist and free-text notes use the existing browser store, with a session-memory
  fallback for blocked storage and failed writes (including quota errors). Clearing a note
  preserves its saved area. Shortlist comparison takes the first four in saved order.
- Share links use versioned JSON in `#/?v=...`, explicitly allowing only camera, visible
  layer ids, geography choices, numeric filter bounds and up to four comparison GEOIDs.
  Notes, names and shortlist state are never serialized. Invalid/unknown registry choices
  are ignored. Existing page routes remain usable, and navigating between pages keeps the
  workbench mounted so private session state is not lost.
- At phone widths the tools are a collapsible bottom sheet with four tabs; comparison
  cells repeat area labels in a two-column grid rather than overflowing the page. Desktop
  comparison uses a native modal table with one column per selected area.
- Methodology is a text-only heading/paragraph Markdown subset, with no raw HTML rendering.
  Two `Claude: check` comments remain in the draft for naming wording and the APD explanation.
  Access-method text explicitly waits for P1-07 instead of inventing an unbuilt method.
- Local `npm run e2e` uses Python Playwright and preinstalled Chromium against a fixture
  `vite preview` build. External browser requests are fulfilled locally with a plain map
  background; no data sources are contacted. Screenshots cover 1440×900 and 390×844. The
  smoke runner and browser dependencies are not added to CI.

## 2026-10-23 — P1-05 merged; APD live check passed (Claude)

- First run 40041187416 failed (nothing published): TIGER's Austin city polygon is
  self-intersecting as served; now repaired with `make_valid` (PR #37).
- Run 40041503825: 4 calls. Period 2025-10-01 to 2026-09-30: 88,424 reports (464 without a
  block group); block-group counts sum exactly to the total. 712 block groups with reports
  (1 out-of-county code); 605 block groups in the APD area (≥50% inside 2020 city limits), 4 of
  them too few residents for a rate. Smoothed Part I rate quintiles about 10 / 18 / 30 / 51 per
  1,000, so the 10/25/50/100 breaks stay. Density quintiles about 36 / 85 / 157 / 311 per sq mi,
  so density breaks change from 50/150/400/1,000 to 25/75/150/300.
- `apd` ungated.

## 2026-10-23 — P1-05 APD aggregate safety layers (Codex)

- **Owner approval:** `apd: {per_day: 10, min_interval_seconds: 1}`, refreshed monthly,
  confirmed in the owner's P1-05 build request. Normal plan: four calls. Other adapters'
  budgets and gates stay unchanged; APD awaits Claude's first live check.
- Only grouped counts and an independent aggregate total are requested from APD. Reject
  unexpected response columns and duplicate group rows; never retain raw responses or
  enable recording. Socrata omits null-valued keys, so missing group/category cells mean
  unlocated/other; `n` is always required. Unknown non-null categories fail closed.
- The 99% vintage check uses distinct non-null codes, including out-of-county codes in
  its denominator. Every aggregate row still counts in reconciliation, including reports
  outside the city, outside the three counties and without a block group.
- Use unsimplified EPSG:5070 polygons for total area and city overlap; tolerate 1e-9
  floating-point error at exactly one-half. Leave population, area, share and period as
  context outside APD, but null every safety count, rate and density there. Inside APD,
  a missing group means a real zero; an independently verified zero-report period is valid.
- Apply the specified global empirical Bayes prior separately for Part I and violent
  reports, using only inside-area block groups with at least 100 residents. Zero mean or
  nonpositive between-area variance returns the common mean without division by zero.
  Round only final rates (one decimal) and densities (whole numbers), using Python's
  nearest-even rounding; retain full precision for area, overlap and the prior.
- The adapter seam cannot add saved IngestionRun notes without changing core. Emit count-only
  run notes to the job log and retain one non-spatial `run_summary` canonical audit record,
  separate from the block-group dataset. `tools/live_summary.py` displays its totals and
  period for a successful matching live run. Neither map layer publishes this audit record;
  both share the single `apd_block_group` file. No incident records or fields are stored.
- Use the source facts and 2020-code verification already recorded by Claude in the task
  and `SOURCES.md`; no source requests were made during development. Agency-wide safety
  layers remain deferred to P1-05b, as specified.

## 2026-10-23 — P1-06 merged; schools live check passed (Claude)

- First run 40038602598 failed (nothing published): one malformed NCES id somewhere in the
  statewide AskTED file. Statewide TEA rows that don't parse are now skipped and counted, and an
  NCES id claimed by two TEA campuses is dropped rather than guessed (PR #31).
- Run 40039008305: 5 calls. 31 districts kept, 596 campuses, 582 matched to a TEA campus
  number, 534 with a 2024–25 rating row (46 of them "Not Rated"), 62 with no rating found
  (mostly charters and special programs). 4 districts link to a school finder, 20 to their
  website, 7 fringe districts have no link. No personal columns requested or stored.
- `schools` ungated.

## 2026-10-23 — P1-06 schools implementation choices (Codex)

- Use synthetic fixtures large enough to meet the real production guards: 500 campuses,
  20 kept districts, 480 AskTED matches and 450 rating rows. No fixture-mode exception to
  the 500/20/90%/80% checks. District overlap uses unsimplified projected block-group area,
  with 1e-9 tolerance for floating-point error at exactly 0.5%.
- Socrata omits null-valued cells: require the selected column vocabulary across a response,
  require identifiers per row, and treat missing nullable cells as null. Identical duplicates
  collapse; conflicting identifiers or NCES/TEA district mappings fail. Unknown rating text
  fails; absent or non-numeric scores stay null. A Not Rated domain never gets a fake zero.
- Finder overrides use exact unshortened TIGER names. Fallback websites may come from any
  AskTED row with that TEA district number; choose HTTPS first, then alphabetical URL when
  several are provided. Reject unsafe protocols and credential-bearing URLs. The finder
  label appears as the link's popup annotation. No nearest-campus or attendance assignment.
- Report both rating-row coverage (the 80% guard) and actual A–F rated campuses separately
  from explicit Not Rated campuses. The adapter prints count-only run notes; the existing
  workflow summary tool adds them from successful published layers. The core adapter seam
  has no hook to add saved IngestionRun notes, so no core changes or raw-response retention.
- Source vintages are shown as NCES 2024–25 and TEA 2024–25, as verified in the task. Do not
  invent an exact source date from a school year; source_as_of stays unknown and the registry
  uses the successful run date. Current TIGER district geometry has no asserted calendar date.

## 2026-10-23 — Owner approval: `schools` budget 10 calls a day

- **Approved by the owner (2026-10-23):** `schools: {per_day: 10, min_interval_seconds: 1}`,
  refreshed yearly. A normal run is 5 calls (TIGERweb districts, TIGER block groups, NCES
  points, AskTED IDs, TEA ratings). The owner started P1-06 with the prompt stating this
  approval.
- P1-06 style correction (Codex's question, Claude agreed): district outlines use a
  transparent fill colour at opacity 1 with `fill-outline-color`, because `fill-opacity: 0`
  also hides the outline in MapLibre.

## 2026-10-23 — P1-02b naming details (Codex)

- Drop nested parenthetical annotations, including an unclosed final parenthesis caused
  by Austin's 50-character truncation. Treat "FINAL PLAT OF" as one removable phrase so
  cleaning cannot leave an orphan "Of". Preserve Roman numerals through XX in base names,
  matching the required "Met Center II" example while title-casing the rest.
- Hays subdivisions use the existing conservative subdivision cleaner (title case and
  trailing plat qualifiers); Austin alone uses the stronger cleaner. Each county's names
  are grouped and unioned only within its designated source. Existing alphabetical ties,
  coverage thresholds and projection tolerance stay as in P1-02.
- Austin paging accepts the GeoJSON transfer flag at the top level or in collection
  properties. An empty promised continuation fails, even if its final flag is false.
  Hays requests up to 2,000 records in its single call and fails on a transfer limit.
  Malformed pages preserve the last publication; short/empty cleaned Austin names are
  skipped and counted. The normal live plan is about 24 calls within the approved 30/day.
- Applied the owner's recorded areas budget approval by changing only that adapter's
  budget line. All other adapter budgets and live gates are untouched.
- (Claude, in review) A plat qualifier (SEC, PH, UNIT, BLOCK, LOT, …) is removed only with
  an identifier after it (a number, a single letter, a Roman numeral or ONE–TEN), so
  "Block House Creek Sec 2" stays "Block House Creek" rather than becoming "Creek".

## 2026-10-23 — ACS first live check; Census notes in plain words (Claude)

- Live run 40015773545: 26 calls in 38 s, no retries. 1,206 block groups and 471 tracts,
  each joined to exactly one ACS row. Population: Travis 1,330,015, Williamson 672,688,
  Hays 268,638; block-group and tract totals match exactly. No credential text in any output.
- Census annotation codes reached the popups raw ("-; MOE: **", "250,000+; MOE: ***"). They
  are now plain words ("Census: too few survey responses to estimate"), and capped medians
  show their range ("$250,000 or more", "1939 or earlier") instead of the stored number
  (250,001), which only sets the colour. New optional popup setting `display_field`.
- That run's data is not published; only its run log is merged, so its calls count. A fresh
  run (next UTC day, within the 30-call budget) publishes the cleaned version, then `acs`
  is ungated.

## 2026-10-23 — P1-04 merged; first live check of `fema_nfhl` passed (Claude)

- Live run 40012121921 (PR #22): 24 calls in about 7 minutes, no retries. 1,206 block
  groups (Travis 766, Williamson 324, Hays 116), one row each.
- 1% (SFHA) share: none 268, under 5% 306, 5–15% 410, 15–30% 143, 30% or more 67. The
  highest shares are along the San Marcos River, Onion Creek and the Colorado, as expected.
- 12 block groups read "not available" (FEMA coverage 95–99%), near the Travis–Williamson
  line. Checked one (484530341002) at full detail in a browser: about 5% of it has no FEMA
  polygon, a strip about 25 m wide where the two county flood maps don't meet. The 0.99
  rule stays; the label is accurate.
- `fema_nfhl` ungated. Today's spend: 34 of 40 calls.

## 2026-10-23 — FEMA paging: slower and gentler (Claude)

- Both first live checks of `fema_nfhl` from GitHub Actions ended with "connection reset" on
  the third FEMA page (offset 2000), and once on the first page. The same page loaded in
  about 1 s (0.8 MB, 1,000 polygons) from the owner's browser, so the page itself is fine.
- Changes: FEMA pages now start at least 15 s apart (`min_interval_seconds` 1 → 15; the
  daily limit stays 40), a run stops after 20 minutes, the one retry waits 60 s instead of
  5 s, and responses are requested gzip-compressed. This only makes us slower and lighter on
  FEMA's server, so it is not a budget increase. A full run is about 23 calls and 6 minutes.
- If resets continue, the next option is FEMA's official county NFHL downloads (3 files
  instead of about 22 pages), probed first.

## 2026-10-23 — Owner approval: `areas` budget 20 → 30 calls a day; wider study area

- **Approved by the owner in writing (2026-10-23):** raise `areas` from 20 to 30 calls a day
  for P1-02b (two more subdivision sources, about 24 calls per run). P1-02b makes the change.
- `study_bbox` widened to [-98.35, 29.70, -97.10, 30.95] (Claude, during P1-04 review): three
  eastern Williamson block groups (484910209001/003/004) reach -97.155, past the old east edge
  of -97.25, so FEMA zones beyond it were not fetched and those areas would have read "not
  available". Checked against the stored live block groups (extent -98.298, 29.752, -97.155, 30.904).

## 2026-10-23 — P1-04 flood-share choices (Codex)

- Use a spatial index to clip the intersecting FEMA polygons per block group, then union
  each category. Subtract the SFHA union from the 0.2% union, including overlaps across
  separate source features. This keeps the categories disjoint and avoids double counting.
- Compare unrounded mapped coverage to 0.99, with only 1e-9 tolerance for projection
  round-trip error at the exact boundary. A coverage value that merely rounds up to 0.990
  still makes both hazard shares null. Fully mapped areas with no hazards get actual zeros.
- A promised continuation page must contain features even if its own transfer-limit flag
  is false. An initially empty, complete NFHL response is allowed and yields zero mapped
  coverage with unavailable flood shares. Support transfer flags at the GeoJSON top level
  and in its collection properties. Paging always advances by the requested 1,000 rows.
- Require the requested attributes, nonempty zone text, T/F SFHA flags and text version
  identifiers; ignore extra service fields. Repair FEMA geometry, recursively retain all
  polygonal parts and print skipped-row counts per page. TIGER geometry remains strict.
- Collect distinct nonempty VERSION_ID strings from all usable NFHL polygons intersecting
  the block group, including boundary-only touches and AREA NOT INCLUDED. Sort them as text.
  VERSION_ID does not establish an effective date: leave `source_as_of` unknown, so the
  existing registry uses the successful run date without inventing a FEMA map vintage.
- Compute shares on unsimplified Census polygons in EPSG:5070. Simplify only their display
  geometry using the areas adapter's 5 m tolerance and six-decimal WGS84 coordinates.
  Hazard polygons are never published. No pipeline core or web application changes.

## 2026-10-23 — P1-03 ACS implementation choices (Codex)

- The adapter queues a single HTTP 5xx retry through `follow_up()`, rather than making an
  uncounted call inside `fetch()`. Retries obey the runner's budget and one-second pacing;
  the normal plan is 26 calls, leaving four retry calls inside the approved daily cap of 30.
  All transport errors discard URLs and response text so Census credentials cannot enter
  the run log. Only `fetch()` reads and adds the environment key.
- Keep unrounded numeric estimates and MOEs in canonical data. For a sum, any missing
  estimate makes the sum unavailable; any missing component MOE makes its uncertainty
  unknown. Missing numerator or denominator MOE preserves an otherwise valid share with
  unknown reliability. Shares outside 0–1 fail instead of silently clamping.
- Preserve EA and MA strings together, with MOE/numerator/denominator labels where needed.
  Raw Census cell names and intermediate cells never reach published properties.
- Use fixed legend breaks, identical at both scales: shares 20/40/60/80%; population
  500/1,000/2,000/4,000; income $50k/75k/100k/150k; home value $200k/350k/500k/750k;
  rent $1k/1.5k/2k/2.5k; year built 1960/1980/2000/2010; age 25/35/45/55. These are neutral
  display bins, not scores. Every measure uses the same five blue colors, with grey for null.
- Use the existing `data_bundle` seam: all metrics share one loaded map source/file per
  scale. (Claude, in review: the core publisher now writes one file per bundle, e.g.
  `data/layers/acs_block_group.geojson`, instead of an identical copy per layer, which
  would have been about 21 copies per scale. A bundle may not share a name with a layer id.)
- Simplify only display polygons, using the areas adapter's 5 m equal-area tolerance and
  six-decimal WGS84 coordinates. All ACS estimates describe the whole area without prorating.

## 2026-10-23 — P1-02 area naming choices (Codex)

- Union polygons in each cleaned WCAD name group before measuring coverage, so overlapping
  sections and replats never count the same land twice. Austin planning areas and Census
  places are compared individually. Choose the largest share, then alphabetical name for
  exact ties, independent of response order.
- Compare unrounded EPSG:5070 shares to the thresholds; allow only 1e-9 of floating-point
  projection error at exact edges. Round stored shares and square miles to three decimals.
- Reject invalid, missing or non-polygon geometry rather than repair it or silently drop
  rows. Enforce the requested native property sets; WCAD's selected `geometry` is the
  GeoJSON geometry, not an extra property. Claude must confirm this in the first live run.
- Add `boundary_note` to block-group properties and attach it to the Name popup through
  the existing manifest annotation field: "2020 Census boundaries; names as of <run date>".
  The run date comes from the runner; geometry `source_as_of` stays 2020-01-01.
- Fixtures include a full 2,000-row WCAD page, mostly identical synthetic polygons outside
  the study area, followed by one row completing a 45% naming group. This tests the real
  paging limit without any test-only behavior. The regeneration script makes no calls.

## 2026-10-23 — Owner decisions: no permission requests; stay public (Q1, Q2)

**Approved by the owner in writing (2026-10-23).** The owner prefers not to request written
permission to republish anything (a basic API-key signup is fine). Where a source would need
permission, take another route. The repo and site stay public. If the owner later decides to go
private, that is a separate decision that would revise these choices.

- **Q1 → publish public government data that has no stated license**, with credit to the
  publisher, its disclaimer, and personal fields stripped at ingest. Covers TCAD, WCAD and Hays
  CAD exports; Travis County and Hays County GIS; City of Austin GIS; and TEA's datasets on the
  Texas Open Data Portal. Gates on these sources in P1-02 and later tasks are open.
- **District attendance zones are not copied.** Each area shows its school district, nearby
  campuses, and a link to the district's own school finder. Showing zone outlines live in the
  browser from a district's own map service (with no copy stored) may be considered in P1-06,
  and would need the owner's approval then.
- **Q2 → TEA ratings come from TEA's own release on data.texas.gov**: "School Year 2024-2025
  Statewide Accountability Ratings" (`nui6-x374`, attribution "Performance Reporting Division
  at Texas Education Agency", updated 2026-06-14). It includes overall, School Progress and
  Academic Growth ratings and scores. No permission request. Trade-off: published ratings
  run a year behind TEA's website (2025–26 ratings are there now, final 2026-12-11). Use the
  newer year when TEA posts it to the portal. Content on tea.texas.gov itself (including the
  campus CSV broker) is not republished.
- Not legal advice. "No license stated" is a judgment call, judged low-risk because these are
  government records the agencies post for public download, and we always credit them.

## 2026-10-22 — Phase 0 results (Claude; for owner approval)

Details and citations in `docs/SOURCES.md`.

- **Hays County is in v1.** Hays CAD publishes free monthly exports with market value, living
  area and year built. CC0 parcel shapes cover it (StratMap 2026, plus Hays County GIS). The
  Comptroller's 2024 study covers it (median level 1.00, COD 7.12), and zone layers exist for Hays
  CISD and Dripping Springs ISD. Its gaps (crime only at agency level, little fixed-route transit)
  are the same as Williamson's.
- **Parcel shapes:** StratMap 2026 (CC0) for all three counties as the baseline. Fresher
  county layers (Travis County's monthly TCAD layer, WCAD's daily parcels, Hays County GIS) are
  used where they are fresher (Q1 decided 2026-10-23).
- **Williamson rolls come from WCAD's open-data portal** (Socrata API), not the certified-roll
  SharePoint links, which answered HTTP 401 from GitHub.
- **CapMetro GTFS from data.texas.gov** (`r4v4-vz24`). CapMetro's developer page points there and
  the feed is current (2026-10-07 to 2027-01-09). This replaces the earlier note that called that
  copy stale.
- **Crime:** APD block groups inside Austin PD's area; DPS agency-level elsewhere, labeled.
  No incident feeds found for other agencies.
- **Actions billing:** standard runners are free for public repos (GitHub docs, checked
  2026-10-22). The light-usage rules stay.
- **Validation targets** are set in `docs/PLAN.md` before any building.
- **Census API:** a key is required even for county-level requests. With the `CENSUS_API_KEY`
  secret it works from GitHub (run 39891997771). Two earlier 503s were transient.

## 2026-10-23 — P1-02 merged; first live check of `areas` passed (Claude)

- Review changes before merging (on the PR): extra service fields are ignored (only named
  fields are copied, so nothing extra can be published); naming polygons from the City,
  WCAD and Census places are repaired with `make_valid` or skipped and counted; Census
  boundaries stay strict.
- **Live run 40001981957** (Live run workflow, first check): success, 14/14 calls, 28 s.
  **1,206 block groups** (Travis 766, Williamson 324, Hays 116) and **471 tracts**, matching
  the Phase 0 count. Names: Census place 764, City of Austin planning area 343, WCAD
  subdivision 68, fallback 31. Stored data has boundary and name fields only. Merged as
  PR #13; the live site shows real boundaries. `areas` is ungated.
- CI on that data PR found that a fixture build labeled layers "Current" once the run log had
  a live run. Fixed in PR #14: the registry labels each layer from the file it publishes.
- **Naming is weak in Austin** (256 block groups named "Austin city"). Follow-up task P1-02b
  adds City of Austin and Hays County subdivisions and uses place base names. It needs the
  `areas` budget raised from 20 to 30 calls a day: **pending owner approval**.
- `Live run` workflow (PR #12): manual, budgeted, one adapter; pushes the run log and stored
  data to a `data/<adapter>-<run id>` branch for review; `first_check` bypasses the live gate
  for Claude's first check only.
- P1-03 trimmed to the measures in the brief (no commute, vehicle, language or moving
  measures), which fits its approved 30 calls a day. P1-04 publishes the per-area flood
  shares only; flood-zone outlines wait for a PMTiles publisher (too large as GeoJSON).

## 2026-10-23 — P1-01 skeleton: design choices (Claude)

Ported from Austin Watch piece by piece (package `aw` → `mm`), keeping only area layers.
Differences from Austin Watch, and why:

- **Canonical store is gzipped NDJSON**, written deterministically (no git churn when
  unchanged). DuckDB/Parquet are dropped until a task needs them, so the DuckDB 2.0
  breakage can't recur and CI installs less.
- **Partial live runs publish nothing** (Austin Watch published them). An incomplete area
  layer would show missing areas as gaps, so the last complete layer stays live.
- **No budget line means no live calls** (fails closed). Fixture runs are unaffected.
- **Raw live responses are gitignored** and kept only if an adapter opts in; **`mm record`
  is opt-in** per adapter. Public repo, and CAD files carry personal data.
- **Two guards from the ground rules:** `privacy.py` refuses to publish personal-looking
  property names (owner, mailing address, exemptions, agents, buyers/sellers…; property
  `situs_*` and ACS `owner_occupied*` allowed). `inputs.py` plus tests stop any field of a
  `demographic: true` layer from becoming a score or model input.
- **Missing values display as "Not available"**, never "—" or zero.
- **Site:** Map / Sources / Health / About pages, a footer on every page, a "Test data"
  banner whenever a visible layer shows fixtures, and layer choices and the map view
  remembered in the browser only. Basemap: OpenFreeMap (free, no key).
- **Pages deploy** runs `mm publish` (stored live data, fixtures elsewhere) and never calls
  a source. Turning Pages on (Settings → Pages → Source: GitHub Actions) is a one-time owner
  click; the API path is blocked for Claude here.

## 2026-10-23 — Owner approval: Phase 1 starts; Q3 decided

**Approved by the owner in writing (2026-10-23).**

- **Phase 1 approved** as planned in `docs/PLAN.md`, including the call budgets and refresh
  cadences proposed in `docs/tasks/P1-*.md`. Later changes to budgets or schedules need the
  owner again.
- **Q3 → WCAD per-sale sales ratios are used only for area-level checks.** For example, a median
  ratio by area with at least 30 sales. Never per property, and never published in a way that
  lets anyone work out an individual sale price. Before first use, confirm from WCAD's layout what
  the ratio compares (which year's value, which price).

## 2026-10-23 — Owner decisions: no permission requests; stay public (Q1, Q2)

**Approved by the owner in writing (2026-10-23).** The owner prefers not to request written
permission to republish anything (a basic API-key signup is fine). Where a source would need
permission, take another route. The repo and site stay public. If the owner later decides to go
private, that is a separate decision that would revise these choices.

- **Q1 → publish public government data that has no stated license**, with credit to the
  publisher, its disclaimer, and personal fields stripped at ingest. Covers TCAD, WCAD and Hays
  CAD exports; Travis County and Hays County GIS; City of Austin GIS; and TEA's datasets on the
  Texas Open Data Portal. Gates on these sources in P1-02 and later tasks are open.
- **District attendance zones are not copied.** Each area shows its school district, nearby
  campuses, and a link to the district's own school finder. Showing zone outlines live in the
  browser from a district's own map service (with no copy stored) may be considered in P1-06,
  and would need the owner's approval then.
- **Q2 → TEA ratings come from TEA's own release on data.texas.gov**: "School Year 2024-2025
  Statewide Accountability Ratings" (`nui6-x374`, attribution "Performance Reporting Division
  at Texas Education Agency", updated 2026-06-14). It includes overall, School Progress and
  Academic Growth ratings and scores. No permission request. Trade-off: published ratings
  run a year behind TEA's website (2025–26 ratings are there now, final 2026-12-11). Use the
  newer year when TEA posts it to the portal. Content on tea.texas.gov itself (including the
  campus CSV broker) is not republished.
- Not legal advice. "No license stated" is a judgment call, judged low-risk because these are
  government records the agencies post for public download, and we always credit them.

## 2026-10-22 — Phase 0 results (Claude; for owner approval)

Details and citations in `docs/SOURCES.md`.

- **Hays County is in v1.** Hays CAD publishes free monthly exports with market value, living
  area and year built. CC0 parcel shapes cover it (StratMap 2026, plus Hays County GIS). The
  Comptroller's 2024 study covers it (median level 1.00, COD 7.12), and zone layers exist for Hays
  CISD and Dripping Springs ISD. Its gaps (crime only at agency level, little fixed-route transit)
  are the same as Williamson's.
- **Parcel shapes:** StratMap 2026 (CC0) for all three counties as the baseline. Fresher
  county layers (Travis County's monthly TCAD layer, WCAD's daily parcels, Hays County GIS) are
  used where they are fresher (Q1 decided 2026-10-23).
- **Williamson rolls come from WCAD's open-data portal** (Socrata API), not the certified-roll
  SharePoint links, which answered HTTP 401 from GitHub.
- **CapMetro GTFS from data.texas.gov** (`r4v4-vz24`). CapMetro's developer page points there and
  the feed is current (2026-10-07 to 2027-01-09). This replaces the earlier note that called that
  copy stale.
- **Crime:** APD block groups inside Austin PD's area; DPS agency-level elsewhere, labeled.
  No incident feeds found for other agencies.
- **Actions billing:** standard runners are free for public repos (GitHub docs, checked
  2026-10-22). The light-usage rules stay.
- **Validation targets** are set in `docs/PLAN.md` before any building.
- **Census API:** a key is required even for county-level requests. With the `CENSUS_API_KEY`
  secret it works from GitHub (run 39891997771). Two earlier 503s were transient.

## Pending owner decisions

- **Q3. WCAD per-sale "sales ratios".** WCAD's open data includes a sales ratio for many sales,
  which together with the appraised value could reveal individual sale prices that Texas
  otherwise keeps private. Options: (a) don't use; (b) use only as area-level checks
  (e.g. median ratio by area with ≥ 30 sales), never per property; (c) use per property.
  **Claude recommends (b)**, after confirming with WCAD's layout what the ratio compares.

## 2026-10-22 — Source probe workflow (Phase 0)

- `tools/probe/probe.py` + `.github/workflows/probe.yml` (manual only). About 30 checks, one
  small request each: HEAD, byte ranges, count queries or a page fetch. Zip archives are
  inspected by reading only their directory, plus at most one small member (GTFS
  `feed_info.txt`). Output is counts, sizes, dates and status only — no personal data, since
  Actions logs in a public repo are public.
- Merged without CI: CI doesn't exist until Phase 1, and `workflow_dispatch` only works for
  workflows on the default branch. The script was syntax-checked and its zip reader was
  tested locally.

## 2026-10-22 — Owner approvals to start Phase 0

- **Phase 0 started** (owner: "Go", 2026-10-22). Phase 0 is discovery and verification, no
  app code.
- **One probe workflow and script allowed in Phase 0** (owner approved). Manual-only
  (`workflow_dispatch`), small requests or headers only, no bulk downloads, summary posted
  to the run page and as notice annotations.
- **Code license: MIT** (owner approved). Data keeps each publisher's terms.
- **Census API key:** the owner is adding it as the Actions secret `CENSUS_API_KEY`. Agents
  never sign up for services.
- **Austin Watch reference:** kept as `austin-watch-reference.zip` in the owner's Claude
  Project, never in this repo. Lessons and a reuse list are in
  `docs/reference/austin-watch-lessons.md`.

## 2026-10-22 — Docs-only PRs merge without CI

There is no CI yet, and the planned CI skips docs-only changes (`docs/**`, `**/*.md`). A
docs-only PR may merge after Claude's review against `AGENTS.md`. Any PR that changes code or
workflows needs green CI once CI exists.
