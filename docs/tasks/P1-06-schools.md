# P1-06 — Schools: district boundaries, campuses and TEA ratings

- **Agent:** Codex. Branch `codex/p1-06-schools`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1b. **Depends on:** P1-02 (merged). Read `AGENTS.md` first and follow its
  seams. Don't change `pipeline/mm/` core files or web application code.
- **No network.** Synthetic fixtures with native field names only. Claude does the live run.
- **Budget:** `schools: {per_day: 10, min_interval_seconds: 1}` (owner approval recorded in
  `docs/DECISIONS.md` before this task starts). Live gate "awaiting Claude's first live check".

## Goal

Two map layers: school-district outlines and public campus points with their TEA
accountability ratings. **No attendance zones** are copied or drawn, and no campus is ever
"assigned" to an area (owner decision 2026-10-23). Every district links to where the district
itself answers "which school serves this address".

## Sources (all checked by Claude on 2026-10-23)

1. **District boundaries** — TIGERweb School service, layer 0 "Unified School Districts"
   (current vintage): `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/School/MapServer/0/query`.
   Fields used: `GEOID`, `NAME`, `BASENAME`, `LOGRADE`, `HIGRADE`. Query the study-area
   envelope (`config/app.yaml` `study_bbox`, `inSR=4326`), `outSR=4326`, `f=geojson`,
   `returnGeometry=true`, `maxAllowableOffset=0.0001`. 53 districts intersect the envelope;
   one request. Public domain; credit "U.S. Census Bureau, TIGERweb". (Secondary and elementary
   district layers return nothing in this area: Texas has unified districts only.)
2. **Block-group polygons** — TIGERweb Census2020 layer 8, as in the flood adapter (one request).
   Used only to keep the districts that actually overlap Travis, Williamson or Hays block groups.
3. **Campus points** — NCES EDGE public school locations 2024–25:
   `https://nces.ed.gov/opengis/rest/services/K12_School_Locations/EDGE_GEOCODE_PUBLICSCH_2425/MapServer/0/query`,
   `where=STATE='TX' AND CNTY IN ('48453','48491','48209')`, `outFields=NCESSCH,LEAID,NAME,CITY,CNTY,SCHOOLYEAR`
   (**not** `STREET`, phone or anything else), `outSR=4326`, `f=geojson`. 596 schools; max 2,000
   per request, so one request; fail on a transfer limit. Public domain; credit "NCES EDGE".
4. **NCES ↔ TEA campus numbers** — TEA AskTED on data.texas.gov, dataset `hzek-udky`
   ("AskTED Data - May 12, 2026"): `https://data.texas.gov/resource/hzek-udky.json` with
   `$select=school_number,nces_school_id,district_number,district_name,district_web_page_address`,
   `$where=nces_school_id IS NOT NULL`, `$limit=20000` (9,791 rows; one request).
   **Request only these columns**: the dataset also holds principals' and superintendents' names,
   emails and phone numbers, which must never be fetched. Values carry a leading apostrophe
   (`'001902001`, `'481320000821`): strip it and keep digits only. 582 of the 596 NCES points
   match a TEA campus number.
5. **Ratings** — TEA "School Year 2024-2025 Statewide Accountability Ratings", data.texas.gov
   `nui6-x374`: `https://data.texas.gov/resource/nui6-x374.json` with
   `$select=campus_number,campus,district_number,district,school_type,grades_served,charter,alternative_education,overall_rating,overall_score,academic_growth_rating,academic_growth_score,school_progress_rating,school_progress_score,student_achievement_rating,student_achievement_score,relative_performance_rating,closing_the_gaps_rating,closing_the_gaps_score`,
   `$where=school_type != 'District'`, `$limit=20000` (about 9,084 rows; one request). Rating
   values are `A`–`F` or `Not Rated`. Credit "Texas Education Agency via data.texas.gov";
   label "TEA accountability ratings, 2024–25". 534 of the matched campuses have a rating row.
   (TEA's own website has newer ratings, but its terms don't allow republishing; it is never
   used.)

Socrata endpoints need no key. One normal run = **5 calls**.

## Districts layer (`school_districts`)

- Keep a district only if it overlaps a study-area block group by at least 0.5% of that block
  group's area (EPSG:5070), so slivers along county lines don't add districts. Expect roughly
  30.
- Properties: `geoid`, `name`, `grades` (`LOGRADE`–`HIGRADE`), `finder_link`, `finder_label`, `tea_district_number` (from
  AskTED via any matched campus with this NCES `LEAID`; null if none), `zone_note` =
  "Which school serves an address is set by the district and can change yearly. Check the
  district's school finder."
- **Finder links** come from a committed file `adapters/schools/finders.yaml`, keyed by the
  TIGER district `NAME` exactly as TIGER gives it:
  `{"<NAME>": {url: ..., label: "School finder", checked: 2026-10-23}}`. Start it with these,
  verified by Claude:
  - "Leander Independent School District": `https://leanderisd.org/msaz` ("School Zone Finder")
  - "Pflugerville Independent School District": `https://www.pfisd.net/registration-information/find-my-school-map`
  - "Georgetown Independent School District": `https://www.georgetownisd.org/fs/pages/3715`
    ("Attendance Zones")
  - "Hays Consolidated Independent School District": `https://www.hayscisd.net/page/rezone-2026`
    (2026–27 zone changes)
  A `finders.yaml` key that matches no kept district fails the run (typo guard). For every
  other district, use AskTED `district_web_page_address` (via `tea_district_number`) with
  `finder_label` "District website" (prefix `https://` if the value has no scheme); if neither
  exists, `finder_link` is null and the popup says "Not available".
- `name`: TIGER `NAME`, with "Independent School District" shortened to "ISD" and
  "Consolidated Independent School District" to "CISD" for display.
- Style: `fill` with `fill-opacity: 0` and a dark grey outline (`fill-outline-color`), so it
  sits over other layers. `default_visible: false`, `refresh: annual`, group "Schools".
  Popup: name, grades, finder link (format `link`), zone note.

## Campuses layer (`school_campuses`)

- One point per NCES school in the three counties. Properties:
  `nces_id`, `campus_number` (null if no AskTED match), `name` (title case is fine), `city`,
  `district` (TEA district name if matched, else NCES `LEAID`'s district name from the district
  layer, else null), `school_type`, `grades_served`, `charter` ("Yes"/"No"),
  `alternative_education`, the ratings and scores listed above, `ratings_year` = "2024–25",
  `rating_note`, `enrollment_note`.
- `rating_note`: "Not rated by TEA for 2024–25" when the row says `Not Rated`; "No TEA rating
  found for this campus" when there is no AskTED match or no rating row; otherwise null.
  Missing ratings are null, never "F" or 0.
- `enrollment_note`: for charters, "Open-enrollment charter: no attendance zone"; otherwise null.
- Points come from NCES coordinates as given (no snapping).
- Style: circle, radius 5, white stroke. Colour by `overall_rating` with one neutral
  sequential purple ramp (A darkest … F lightest; `#3f007d`, `#6a51a3`, `#9e9ac8`, `#cbc9e2`,
  `#f2f0f7`) and grey `#bdbdbd` for null or "Not Rated". No red/green. Legend "A" … "F",
  "Not rated / not available".
- Popup order (growth before raw achievement): name, district, grades, school type, charter
  note, **Academic Growth** rating and score, **School Progress** rating and score, overall
  rating and score, Student Achievement rating and score, Closing the Gaps rating and score,
  ratings year, rating note. Description: "Public campuses (NCES 2024–25) with TEA 2024–25
  ratings. A campus's rating is not a promise about the school that serves a given address."
- `default_visible: false`, `refresh: annual`, group "Schools", attribution
  "NCES EDGE; Texas Education Agency via data.texas.gov", license "Public domain (NCES);
  no license stated (TEA on data.texas.gov)".

## Checks (fail closed; previous layers stay)

- Each response has the expected native fields; non-JSON or HTTP errors fail.
- Fewer than 500 NCES points, fewer than 20 kept districts, AskTED matches below 90% of NCES
  points, or rating rows for below 80% of matched campuses → fail.
- No property named like a person, email or phone reaches canonical or published data (the
  privacy guard must pass; add a test that a fixture row with a `school_principal` value is
  never requested or stored).
- Run notes report counts: districts kept, campuses, matched, rated, not rated, unmatched.

## Fixtures and tests

Synthetic fixtures with native field names (TIGER, NCES GeoJSON, Socrata JSON with the
leading apostrophes), including: an unmatched NCES school, a charter, a `Not Rated` campus,
a campus with no rating row, a district that only touches the study area by a sliver, and a
district with a `finders.yaml` entry. Tests: apostrophe stripping, joins, sliver rule,
finder-link fallback order, rating notes, the requested `$select`/`outFields` never include
personal columns, the 5-call plan, budget and live gate.

## Other requirements

- Add `schools` to `config/budgets.yaml` and `config/live_gates.yaml` as above.
- Add rows for NCES EDGE 2024–25 and TIGERweb School districts to `docs/SOURCES.md` (Schools
  section) if not already there.
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for any
  choice not settled here.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run (about 30 districts kept, 596 campuses, 582 matched,
about 534 rated; that no personal columns were requested; finder links resolve).
