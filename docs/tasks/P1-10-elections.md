# P1-10 — Election results by precinct (context only)

- **Agent:** Codex. Branch `codex/p1-10-elections`. Regular (not draft) PR to `main`.
- **Phase:** 1 follow-up, owner request (2026-10-25: "Yes please add it"). **Depends on:** P1-01.
  Read `AGENTS.md` first and follow its seams. Don't change web application code. One small
  core change is allowed: add `"precinct"` to `LayerManifest.join` in `pipeline/mm/schemas.py`
  (then `mm schema` and `cd web && npm run gen:types`, commit both).
- **No network.** Synthetic fixtures with native field names only. Claude does the live run.
- **Budget:** `elections: {per_day: 4, min_interval_seconds: 5, max_minutes: 15}`, refresh
  **annual** (owner approval recorded in `docs/DECISIONS.md` before this task starts). A normal
  run is 2 calls (two large files). Live gate "awaiting Claude's first live check".
- **New dependency:** `pyshp>=2.3,<3` (MIT, pure Python) to read the precinct shapefile.

## Rules

- **Context only, like demographics.** Both layers set `demographic: true`, so they sit under
  "People (context only)", start off, and their fields can never feed a score, ranking or value
  model (the existing guard in `pipeline/mm/inputs.py` enforces this).
- **Precinct grain only.** Show precinct shapes as published. Never convert, apportion or join
  results to block groups, tracts or addresses.
- **Small precincts:** if a precinct has fewer than 50 presidential votes in an election, that
  election's vote counts and shares are null with note "Fewer than 50 votes: not shown".
  Registered voters and turnout still show (they are counts, not votes for anyone).
- Never request, store or publish `SpanishSurnamePercent` or `TotalPop`.
- Neutral wording. Texas has no party registration: "registered voters" means all voters.

## Sources (checked by Claude on 2026-10-25; CC BY, Texas Legislative Council)

Texas Legislative Council (TLC) Capitol Data Portal, license "Creative Commons Attribution".
Credit "Texas Legislative Council, Capitol Data Portal". Probe 2026-10-24/25: both files return
HTTP 200 from GitHub.

1. **Election data, 2024 general VTDs** (zip, 82.1 MB, Last-Modified 2025-02-25):
   `https://data.capitol.texas.gov/dataset/35b16aee-0bb0-4866-b1ec-859f1f044241/resource/e1cd6332-6a7a-4c78-ad2a-852268f6c7a2/download/2024-general-vtds-election-data.zip`.
   226 CSV members for 2012–2024 elections, all re-tabulated by TLC to 2024 general-election
   precincts. Use only:
   - `2024_General_Election_Returns.csv` and `2020_General_Election_Returns.csv`: header
     `County,FIPS,VTD,cntyvtd,vtdkeyvalue,Office,Name,Party,Incumbent,Votes`; one row per precinct,
     office and candidate. `FIPS` is the county code without leading zeros (Travis 453,
     Williamson 491, Hays 209). Some fields are quoted and contain commas (e.g. court offices):
     parse with the `csv` module. Use `Office == "President"` only. Parties: D, R, L, G, W.
   - `2024_General_Election_VRTO.csv` and `2020_General_Election_VRTO.csv`: header
     `County,FIPS,VTD,CNTYVTD,vtdkey,TotalPop,TotalVR,SpanishSurnamePercent,TotalTO`. Use only
     `vtdkey`, `TotalVR` (registered voters) and `TotalTO` (ballots cast).
   Real counts for the three counties: 553 precincts (Travis 300, Williamson 166, Hays 87).
   President 2024: Harris 612,262, Trump 384,529, others about 22,500; 2020: Biden 637,693,
   Trump 347,584. Registered 2024: 1,564,474; ballots 1,024,839. 27 precincts have fewer than
   50 presidential votes in 2024 (16 have none); 13 have zero registered voters; one 2020
   precinct has more ballots than registered voters (re-tabulation).
2. **Precinct shapes, VTDs 2024 primary & general** (zip, 46.6 MB, Last-Modified 2025-01-29):
   `https://data.capitol.texas.gov/dataset/4d8298d0-d176-4c19-b174-42837027b73e/resource/906f47e4-4e39-4156-b1bd-4969be0b2780/download/vtds_24pg.zip`.
   Shapefile `VTDs_24PG.*` (9,712 statewide). DBF fields `CNTY` (county code, numeric),
   `COLOR`, `VTD`, `CNTYKEY`, `VTDKEY` (joins `vtdkeyvalue` and `vtdkey`), `CNTYVTD`,
   `Shape_area`, `Shape_len`. Projection from `VTDs_24PG.prj`: NAD83 Lambert Conformal Conic,
   central meridian −100, standard parallels 27.4167 and 34.9167, origin 31.1667, false
   easting/northing 1,000,000 m (Texas State Mapping System). Read the `.prj` with
   `pyproj.CRS.from_wkt` and reproject to WGS84.

## Requests (2 calls)

Keys `election_data`, `vtd_shapes`. Stream each download to a temporary file (never into
memory whole, never committed), read only the members above, keep only rows/shapes for
counties 453, 491 and 209, and delete the temporary file before `fetch` returns (as P1-07 does
with OSM). `fetch` returns a JSON-able body: for `election_data`
`{"members": {"<member name>": [[header…], [row…], …]}}` limited to the three counties and the
columns above (drop `SpanishSurnamePercent` and `TotalPop` here, before anything is kept); for
`vtd_shapes` `{"type": "FeatureCollection", "features": [...]}` in WGS84 with properties
`CNTY`, `VTD`, `VTDKEY`, `CNTYVTD`. Fixtures use these same shapes. Transfer errors, a missing
member or a non-ZIP response → fail.

## Per precinct (553 features)

Properties: `vtdkey`, `county` (name), `precinct` (county name + " precinct " + `VTD`),
`registered_2024`, `ballots_2024`, `turnout_2024` (ballots ÷ registered, 3 decimals; null if
registered is 0 or ballots exceed registered, with note "Turnout not shown: ballots exceed
registered voters after re-tabulation" in that case), the same three for 2020, and for each of
2024 and 2020: `pres_<yr>_dem`, `pres_<yr>_rep`, `pres_<yr>_other` (L + G + W), `pres_<yr>_total`,
`pres_<yr>_dem_share`, `pres_<yr>_rep_share` (of all presidential votes, 3 decimals),
`pres_<yr>_margin` (rep share − dem share, 3 decimals; positive = Republican lead), and the
candidate names as `pres_<yr>_dem_name`, `pres_<yr>_rep_name` from the file.
`election_note` (small-precinct and turnout notes joined with "; ", or null). `source_note`:
"2024 voting precincts (TLC); 2020 results re-tabulated to 2024 precincts by TLC".
Simplify display geometry with the areas adapter's 5 m tolerance and 6-decimal coordinates.

Checks (fail closed): 553 ± 30 precincts in the three counties; every returns/VRTO `vtdkey`
for those counties matches exactly one shape and vice versa; duplicate keys fail; three-county
presidential totals for 2024 within 1% of Harris 612,262 / Trump 384,529 (catches a wrong
member or column; Claude updates these when TLC posts a new vintage); counts are non-negative
integers. Emit a count-only `run_summary` record and run note (precincts per county, totals per
party and year, registered and ballots, precincts under 50 votes), as in P1-05.

## Layers (group "People", `demographic: true`, `default_visible: false`, `refresh: annual`)

Attribution "Texas Legislative Council, Capitol Data Portal", license "CC BY (Texas Legislative
Council)". `join: precinct`, `geometry: polygon`, both sharing `data_bundle: elections_precinct`.

1. `elections_president_2024`: "2024 presidential vote by precinct". Fill on
   `pres_2024_margin` (grey `#bdbdbd` for null), exactly:
   `[step, [get, pres_2024_margin], "#2166ac", -0.4, "#67a9cf", -0.2, "#d1e5f0", -0.05, "#f7f7f7",
   0.05, "#fddbc7", 0.2, "#ef8a62", 0.4, "#b2182b"]`. Legend, in that order: "Democratic lead 40+
   pts", "Democratic lead 20–40", "Democratic lead 5–20", "Within 5 pts", "Republican lead
   5–20", "Republican lead 20–40", "Republican lead 40+ pts", "Not shown".
2. `elections_turnout_2024`: "2024 turnout by precinct (ballots ÷ registered voters)".
   Fill on `turnout_2024`, the ACS neutral blues, breaks 0.5 / 0.6 / 0.7 / 0.8, grey for null.

Popup (both): precinct, county, 2024 votes (Dem name and votes, share; Rep name and votes,
share; other), margin, 2020 the same, registered voters, ballots, turnout for both years,
`election_note` (`hide_if_empty: true`), `source_note`. Description: "Official general-election
results by voting precinct, from the Texas Legislative Council. Texas has no party registration;
registered voters include everyone registered. Precincts with fewer than 50 votes are not shown.
For context only: never used in any score or ranking."

## Fixtures and tests

Synthetic fixtures in the `fetch` body shapes, with native headers (including quoted fields
with commas in a non-presidential office, the two dropped columns present in the raw-member
parser test, a zero-registered precinct, a precinct under 50 votes, a ballots-over-registered
precinct, write-in rows). Tests: CSV quoting; dropped columns never reach a record or file;
county filter; key matching both ways and duplicates; the 50-vote rule; turnout rules; shares,
margin and rounding on hand-worked numbers; the totals check; `.prj` reprojection on a tiny
synthetic shapefile written with pyshp in the test; temporary files deleted after fetch
(including on error); both layers `demographic: true` and their fields in
`inputs.demographic_fields()`; no block-group fields or joins; budget and live gate.

## Other requirements

- Add `elections` to `config/budgets.yaml` and `config/live_gates.yaml`; add `pyshp` to
  `pipeline/pyproject.toml`.
- Add a `docs/SOURCES.md` entry (license CC BY, files, dates, columns used and dropped).
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for any
  choice not settled here.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run: 553 precincts; totals match the figures above; precincts
under 50 votes about 27; peak memory and runtime; no dropped column anywhere in outputs.
