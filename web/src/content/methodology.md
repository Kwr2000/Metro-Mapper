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

The violent-rate layer uses the same reports, counting murder, rape, robbery and aggravated assault only. Areas with 100 to 999 residents carry a note: shops, offices or hospitals can make per-resident rates look high there, so check reports per square mile too. Most of the highest Part I rates are property crime in areas with few residents.

## Safety outside Austin PD (agency-wide)

Outside the Austin PD block-group detail, the only consistent source is each police agency's yearly total reported to the Texas Department of Public Safety (Crime in Texas, 2025). The agency-wide layer shows one rate per agency on every area that agency covers; it does not vary within a city or county and is never spread onto streets. An area belongs to a city police department when at least half of it is inside that city's current limits; when at least half is outside every city with its own police department, it gets the county sheriff's rate; otherwise it is not available. Sheriff rates cover unincorporated areas and cities without their own police. Rates use DPS's jurisdictional population and count the seven Part I offenses (arson and human trafficking excluded). Reports by school, university, transit and constable police are not included in any area's rate. DPS figures are revised as agencies update their reports. Austin PD appears here too, on the same agency-wide basis, so areas compare on one method; the block-group layers remain the detail inside Austin.

## Schools

Campus points come from NCES 2024–25 and TEA accountability ratings for 2024–25. Academic Growth and School Progress appear before raw Student Achievement. Missing ratings are unavailable, not failing grades. District outlines are not attendance zones. A district at an area's interior point supplies context only; it does not assign a campus. Check the district's own school finder for the school serving an address, because assignments change. Open-enrollment charters have no attendance zone.

District ratings come from the same TEA 2024–25 release. A district rating summarises all of its campuses; individual schools vary. Districts based outside the three counties may show no rating.

## Access

Access layers estimate typical travel minutes from where people live, along OpenStreetMap streets and paths. Each 2020 Census block with residents is a starting point; an area's value is the population-weighted median of its blocks. Walking assumes 4.8 km/h and biking 16 km/h on flat ground, with no traffic, hills or waits at crossings. Destinations are OpenStreetMap groceries, parks (at least 0.1 hectare), schools and a daily-needs basket (pharmacy, food, hardware, bank and library); the basket time is the longest of the five, so one sparse errand sets it. Times above 60 minutes show as “More than 60 minutes”. OpenStreetMap coverage varies, and missing shops make times look longer than they are.

Transit counts scheduled CapMetro departures between 7 and 9 am on a representative weekday at stops within about a 10-minute walk, counting each trip once. Other transit agencies are not included yet, and “no fixed-route service” is a real result in much of the three counties.

## Not available

Not available can mean missing source data, suppressed estimates, an uncovered geography or a layer that has not loaded. Each layer's notes explain more. A genuine observed zero is displayed as zero. An active filter excludes an area with a missing value and reports how many were excluded; that is not evidence about the area itself. Comparisons keep source dates, uncertainty, notes and test-data labels.

## Election results

Election layers show official general-election results by voting precinct from the Texas Legislative Council: the 2024 and 2020 presidential vote, registered voters and turnout. Results stay on precinct outlines and are never converted to Census areas or addresses, so they are not part of the area filters. TLC re-tabulated the 2020 results onto the 2024 precincts, so the two years compare directly. Texas has no party registration; registered voters include everyone registered. Precincts with fewer than 50 votes in an election do not show that election's results.

## People are context only

Census estimates and election results are for context only. They are not used in any score or ranking. These layers appear in People (context only), with no default selection. You may choose ranges or compare estimates, but they never sort or rank areas and never enter any combined score or home-value model. There is no combined score in this app.

## Refresh and private state

Austin PD, flood and access layers refresh monthly; Census estimates, schools, area boundaries and names, agency-wide safety and election results refresh yearly. A scheduled job runs on the 3rd of each month, refreshes whatever is due and checks the result before publishing: every layer must keep its source and date and at least half of last month's areas, no personal fields may appear, and Austin PD block-group counts must add up to APD's own total. If any of these fails, last month's data stays on the site. Source dates can differ; check them before comparing values. There are no new source calls when you use filters or compare: the browser reads already-published files.

Your shortlist and notes stay in this browser's local storage. If storage is blocked, they work for the session only. Shared links contain map position, visible layers, geography choices, active filters and comparison GEOIDs, never notes or your saved shortlist. Texas sale prices are not public; home ranges use public appraisals and are labeled appraisal-based value ranges.

## Comparisons

Comparisons use the same source and method as the local value. Medians come directly from the Census, never from averaging block groups. Crime compares a city with its state and the state with the US; there are no peer-city crime comparisons. Comparisons are context only: no scores, rankings or sorting. Demographic comparisons are plain numbers, without better or worse wording. Hover for all comparisons, sources, periods and margins of error; the comparison table also shows these details.

In the layer panel, Colour starts in Values mode. Compared with uses a published comparison from the same source and method, never an average calculated from the map. Five classes use the ratio to the comparison or the difference from it; the legend shows the cut points, comparison value, source and period. Missing values stay grey; a zero comparison cannot be used for a ratio. Where an estimate's margin-of-error range contains the comparison value, its colour is the middle class (about the same within margin of error). This uses the area's margin of error, not the comparison's. Demographic and election layers always use neutral colours and never better/worse wording. Colour classes are for display only, never scores, ranks, sorting or filters.

## Check a home

Check a home searches the 2026 public appraisal records for Travis, Williamson and Hays counties by street address. Units and ZIP codes help narrow a search; several records at one address remain separate choices. Property facts come from each county appraisal district, with the January 1 value date and export date shown. Parcel locations come from StratMap 2026. An exact property-ID match supplies the map point and Census block group. Homes without a parcel match remain searchable without an invented location; most Travis condo units are not yet placed. Area names follow the same boundary labels as the map, and no demographic data appears on a home card or enters its range.

The appraisal-based value range stays hidden until the published validation flag is enabled. When available, divide the 2026 market appraisal by the county's 2024 Comptroller category A median appraisal level (1.00 Travis, 0.96 Williamson, 1.00 Hays), then multiply by the seasonally adjusted FHFA purchase-only Austin metro HPI factor. The base is the mean of the quarter before and the quarter of January 1, 2026. The latest published quarter and its date are shown. Round the centre to the nearest $1,000 using nearest-even rounding, then apply ±10% and round the endpoints. Use ±20% for recent construction or builder inventory, lots over one acre, condos, unusually small or large living areas, and mobile, rural or two-to-four-unit homes. Missing market values, zero building values and TCAD partial-ownership records have no range. Year-over-year appraisal changes are unavailable because these files contain 2026 values only.

Size comparisons use the same category and appraisal neighbourhood with at least 20 measured homes, otherwise the same category county-wide. Neighbourhood tables require at least ten homes with living area and a range. Their percentiles describe adjusted appraisal-based centres per square foot, not disclosed transaction prices. The asking-price position interpolates between those published percentiles and caps its wording at the 10th and 90th percentiles. It is an approximate comparison with a source, date and sample count, rather than a precise rank.

The range cannot observe interiors, condition, recent remodels or changes in the market since the latest HPI quarter. The Comptroller study concerns single-family homes and leaves substantial variation between individual properties. Texas home sale prices are not public. The optional asking price comes from you, remains in this browser's local storage (or only this session when storage is blocked), and is never included in a URL, shared link or data request. Home links contain a property ID only. Test data is labeled wherever it supplies a displayed number.
