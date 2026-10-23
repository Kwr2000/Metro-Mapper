# Decisions

Design decisions and the owner's approvals, newest first. Each entry says what was decided,
why, and (for approvals) that the owner approved it in writing.

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
  scale. The current core publisher still writes identical files under each layer id;
  removing those redundant disk copies would require a separate core change. No core or
  web application code is changed for this task.
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
