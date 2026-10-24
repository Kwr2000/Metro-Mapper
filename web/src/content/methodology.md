# Methodology

## Areas and units

An area here is a 2020 Census block group, not a neighborhood boundary or a promise about an address. Census tracts offer a larger, steadier view of survey estimates. Counts describe whole areas. Percentages are shares of a whole; rates per 1,000 residents and reports per square mile describe different things. Every layer keeps its source, date and test-data label.

## Area names

Names describe the largest overlapping named area. First use a City of Austin neighborhood planning area covering at least half the block group. Next use a subdivision covering at least 40%: Austin subdivisions in Travis County, WCAD subdivisions in Williamson County and Hays County subdivisions in Hays County. Next use a Census place, adding “Near” below half coverage. Otherwise the name is the county plus the Census tract and block-group numbers (for example “Travis County area …”). Tracts are shown by their Census identifiers. Names are cleaned source labels, not invented neighborhoods; the name source remains visible.

## Flood shares

The 1% annual-chance share includes FEMA Special Flood Hazard Areas. The 0.2% share describes the mapped 0.2% annual-chance zone outside those areas. Shares use equal-area geometry, including land and water. If FEMA covers less than 99% of an area, flood shares are unavailable. Small county-map seams can cause this. Mapped shares are not predictions of flooding at a property; local and Atlas 14 floodplains may be larger.

## Census estimates

ACS 2020–2024 five-year estimates include a 90% margin of error (MOE). A margin greater than 30% of the estimate is marked low reliability; missing MOEs stay unknown. Percentage MOEs are shown in percentage points. Estimates are not exact counts. Census suppression notes explain missing estimates. Capped values show their published limit, such as “$250,000 or more,” rather than implying an exact number. Filters use the stored estimate; always review its MOE, reliability and displayed limit in the comparison or popup.

## Safety

Safety layers describe reports to Austin PD in the last 12 full calendar months, using report date in UTC. Reports are not convictions; only the highest offense on each report is counted. APD's own 2020 block-group assignments are kept. Areas at least 50% inside Austin's 2020 city limits count as the APD area for display. Outside it, values say Not available. This is a city-limits proxy, not a verified service-boundary map.

Rates use exact 2020 Census population, not an ACS estimate. Areas with fewer than 100 residents show counts and density but no resident-based rate. Part I combines violent and property reports. Raw rates are reports per 1,000 residents; density is reports per square mile, including land and water. Empirical Bayes smoothing pulls small-population rates toward the Austin-wide rate, separately for violent and Part I reports. The weight comes from observed between-area variance after accounting for sampling variation. No street-level conclusions or combined safety score are made.

## Schools

Campus points come from NCES 2024–25 and TEA accountability ratings for 2024–25. Academic Growth and School Progress appear before raw Student Achievement. Missing ratings are unavailable, not failing grades. District outlines are not attendance zones. A district at an area's interior point supplies context only; it does not assign a campus. Check the district's own school finder for the school serving an address, because assignments change. Open-enrollment charters have no attendance zone.

## Not available

Not available can mean missing source data, suppressed estimates, an uncovered geography or a layer that has not loaded. Each layer's notes explain more. A genuine observed zero is displayed as zero. An active filter excludes an area with a missing value and reports how many were excluded; that is not evidence about the area itself. Comparisons keep source dates, uncertainty, notes and test-data labels.

## People are context only

Census estimates for context. They are not used in any score. Demographic layers appear in People (context only), with no default selection. You may choose ranges or compare estimates, but they never sort or rank areas and never enter any combined score or home-value model. There is no combined score in this app.

## Refresh and private state

APD and flood layers refresh monthly; ACS and schools refresh annually. Base boundaries and names refresh annually. Source dates can differ; check them before comparing values. There are no new source calls when you use filters or compare: the browser reads already-published files. Access layers are not built yet and will document their method when available.

Your shortlist and notes stay in this browser's local storage. If storage is blocked, they work for the session only. Shared links contain map position, visible layers, geography choices, active filters and comparison GEOIDs, never notes or your saved shortlist. Texas sale prices are not public; any future home-value display must be labeled an appraisal-based value range, not a sale price.
