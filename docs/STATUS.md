# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-27 (P2-08 built; awaiting HMDA first live check)._
_Last updated 2026-10-28 (P2-07 built; Phase 3 approved; awaiting home-page review)._

## Phase

**Phase 3 — approved 2026-10-27** (find value in good areas; plan in `docs/PLAN.md`). P3-01 and P3-03
specs ready. **Phase 2 — in progress** (P2-01 to P2-06 done; P2-07 and P2-08 being built).

## Done

- Scaffold: `AGENTS.md`, `LICENSE` (MIT), `.gitignore`, `docs/reference/austin-watch-lessons.md` (PR #1).
- Source probe: `tools/probe/probe.py` + `.github/workflows/probe.yml`, manual only (PRs #2, #3).
  Run 39891186379: 26/29 OK; re-run fixed GTFS. Read results with
  `gh api repos/Kwr2000/metro-mapper/check-runs/{job_id}/annotations`.
- `docs/SOURCES.md` (all sources verified 2026-10-22), `docs/PLAN.md` (scope, architecture,
  validation targets, Phase 1 tasks), Phase 1 specs in `docs/tasks/`.
- Decided: Hays is in v1; StratMap 2026 (CC0) as baseline parcel shapes; WCAD via its open-data
  portal; GTFS from data.texas.gov (current); APD block groups + DPS agency-level crime.

- **P1-01 skeleton** (merged, PR #7; finalize hook PR #8; P1-02 spec PR #9): pipeline `mm` (adapters, budgets, run log,
  canonical store, empty-layer guard, registry/health, privacy and demographics guards),
  site shell (Map/Sources/Health/About, Test data banner), CI, Pages deploy workflow.
  58 pipeline + 18 web tests; checked in Chromium at 1440×900 and 390×844.

- **P1-02** (Codex, PR #11; Claude review fixes): areas adapter. First live run 40001981957:
  1,206 block groups and 471 tracts, published on the live site (PR #13). Ungated.
- **Site live** on GitHub Pages: https://kwr2000.github.io/Metro-Mapper/ (real boundaries,
  basemap working).
- `Live run` workflow (PR #12) and the test-data labeling fix (PR #14).

- **P1-04** (Codex, PR #17; Claude fixes PRs #18, #21): FEMA flood shares. First live run
  40012121921 published 1,206 block groups (PR #22); 12 "not available" at county-map
  seams. Ungated. Runner now retries a failed request once; FEMA pages go 15 s apart.

- **P1-03** (Codex, PR #16; Claude fixes: one file per data bundle, plain-language Census
  notes PR #24): ACS demographics. First live check (run 40015773545) passed on the numbers;
  its data was held back because of raw Census codes, and only its run log merged (PR #25).
  Re-run 40043682058 published (2026-10-24). Ungated.

- **P1-02b** (Codex): Census base names, county-specific Austin/Hays subdivision names,
  stronger Austin cleanup and the approved areas budget of 30/day. Synthetic fixtures only;
  `make test` passes (318 pipeline + 19 web tests and build). Awaiting Claude's live check.

- **P1-06** (Codex): schools adapter, checked finder links, synthetic fixtures/tests and
  district/campus manifests; budget 10/day and live gate. `make test` passes (381 pipeline
  + 19 web tests and build). Awaiting Claude's live counts and finder-link checks.

- **P1-06** (Codex, PR #30; Claude fix PR #31): schools. Live (31 districts, 596 campuses
  with TEA 2024–25 ratings). Ungated.

- **P1-05** (Codex): aggregate-only APD adapter, synthetic fixtures/tests, shared rate/density
  layers, budget 10/day and live gate. Checks totals, 2020 codes, city coverage and empirical
  Bayes rates. `make test` passes (434 pipeline + 19 web tests and build). Awaiting Claude's
  first live totals and APD-area count check.

- **P1-05** (Codex, PR #36; Claude fix PR #37): APD safety layers. Live (605 block groups in
  Austin PD's area; 12 months of reports). Ungated. P1-05b (other agencies) is next for safety.

- **P1-08** (Codex): registry-driven ranges and map highlights, four-area comparison,
  private shortlist/notes, shareable view links and methodology draft. People stays context
  only, with no sorting/ranking. `make test` passes (435 pipeline + 34 web tests and build);
  local Chromium smoke passes at 1440×900 and 390×844, outside CI. Awaiting Claude's
  live-site filter and methodology review.

- **P1-02c** (Codex): planning-area title case with MLK/digit/Mc handling; WCAD whole-word
  abbreviation and parenthesis cleanup; small words in subdivision names. Synthetic tests
  verify polished spellings merge before the existing share rules. `make test` passes
  (496 pipeline + 34 web tests and build). Awaiting Claude's live check for all-capital
  planning names and remaining Crk/Ests abbreviations.

- **P1-07** (Codex): access adapter and nine shared-bundle walk/bike/transit layers, small
  synthetic fixtures/tests, ODbL and budget approvals, and live gate. Routes and Census
  population-weighted medians include cap/missing notes; GTFS trips are counted once.
  `make test` passes (559 pipeline, one local parser skip, 34 web tests and build). Awaiting
  Claude's live runtime/memory, graph counts, snap share and plausibility checks.

- **P1-09** (Claude, PR #54): monthly refresh `refresh.yml` (09:15 UTC on the 3rd), `mm validate`
  and `mm refresh`, `data/validation/validation.json` + `report.md`. Hard checks keep last month
  live on failure. Dry run on GitHub (run 40059861605) passed; nothing due until 2026-12-03 for
  FEMA/APD. First scheduled run 2026-11-03 commits the run log and first report.
- **P1-05b spec** (Claude): DPS agency-level data is XLSX from the DPS UCR portal (needs a
  "compatible" user agent; probe PRs #55, #56, #57). Spec `docs/tasks/P1-05b-agency-safety.md`.

- **P1-05b** (Codex): DPS agency-wide safety adapter, native XLSX/TIGER synthetic fixtures,
  strict 28-agency/25-place joins, city/sheriff/split assignment, layer and count-only audit.
  Owner budget/publication approvals recorded; live use gated. PR #59: full local
  `make test` passes after installing declared dependencies (629 pipeline tests, no skips;
  34 web tests, schema/type checks, fixture and production builds). No live source calls.
  Live (Claude, run 40108617517; ORI fix PR #60): 28 agencies, 1,206 block groups, 6 split;
  Austin PD 35.7 per 1,000. Ungated.

- **P1-07** access: live (run 40146625568, 2026-10-25). Ungated.

- **Owner fixes 2026-10-25** (Claude, PRs #66–#70): map popup × closes; violent-rate layer and
  under-1,000-residents note for Austin PD areas; empty notes hidden; distinct campus colours;
  TEA district ratings on districts plus a district rating layer (24 of 31 districts rated).

- **P1-10 spec** (Claude): election results by precinct (TLC, CC BY), context only.
  Spec `docs/tasks/P1-10-elections.md`; owner budget/dependency approvals recorded in DECISIONS.

- **P1-10** (Codex): TLC precinct election adapter, two context-only layers sharing one
  bundle, native synthetic ZIP/CSV/shapefile tests, temporary download cleanup and count-only
  audit. Added the approved pyshp dependency and budget; live use gated. Core change limited
  to the precinct join enum and generated outputs. `make test` passes (679 pipeline tests,
  35 web tests, schemas/types and builds). Claude fix: the real DBF's float `VTDKEY`. Live run
  40161817419: 553 precincts, totals match the source, 27 small precincts hidden; ungated.

- **Phase 1 closing review** (Claude, 2026-10-25): every layer checked on real data at desktop
  and phone sizes; layout fixes; methodology page complete.

- **P1-11** (Codex, PR #82; Claude fixes PRs #86, #90): comparisons (benchmarks) for ACS, DPS, APD,
  schools, access, elections and the new FBI national source. Merged 2026-10-25, then live
  checks (data PRs #85, #87–#89, #92–#94): ACS median household income US 80,734, Texas 78,476,
  Austin city 93,658 (exact, 168 records, all 12 peer cities); DPS Texas Part I 21.6 and violent
  3.4 per 1,000; FBI US violent 3.3, Part I 18.7; Austin PD area 32.7 / 3.7; schools Texas campus
  mean score 81.0 (59.5% A or B); access three-county medians; Texas election and turnout totals.
  `benchmarks.json` has no personal fields and is not test data. FBI's property series includes
  arson (probe 40232292906), so the adapter now removes it (3 calls a run). `fbi_national` ungated
  (run 40249786937). Web test fixed for layers that publish no file.

- **P2-01** (Codex, PR #83): StratMap parcel base (canonical records only, no layer). First live
  check passed (run 40250516420, PR #95): 793,461 kept IDs, exactly the expected counts per
  county; 0.02% of points outside the study block groups; 116 s; 13.9 MB; no personal fields.
  Ungated. Acreage is unreliable in this source (see Open issues).

- **P1-12** (Codex, PR #98): colour by comparison. Reviewed (schema forces `neutral` on all 44 ACS
  and election layers; 759 pipeline + 51 web tests; e2e at 1440×900 and 390×844), merged 2026-10-26,
  then checked on a local build of the deployed site with the real committed data (github.io is
  blocked from the agent sandbox): crime vs Texas 21.6, access vs three-county 32 min, school
  campuses vs Texas 81.0, ACS bachelor's share vs Texas 33.8%, 2024 margin vs Texas 13.7 points.
  Every sampled area's popup class matched an independent classification; better/worse words and
  green–red colours appear only on crime, access and school layers; ACS and elections are brown–teal
  with "lower/higher than" wording.

- **P2-02** (Codex, PR #99; Claude fixes #100, #101, #105): TCAD 2026 property facts. Reviewed and
  merged 2026-10-26 (byte-range allowlist enforced by a slice-guard test, canaries in owner/mail/
  confidential/exemption/qualify-year ranges). Three live attempts failed on real-data shapes
  (blank improvement type, partial-owner repeat rows, mobile homes missing from the TOTALS count);
  the fourth, run 40425025647 (2026-10-27), passed: 384,236 properties kept, real/mobile count
  453,705 vs TOTALS 453,779, living area on 99.67%, HVAC agreement 98.92%, 66 s, 1.76 GB, 19.2 MB, no
  personal fields. Ungated. See DECISIONS 2026-10-27 for the numbers, the condo parcel gap and the
  mobile-home correction.

- **Review verification 2026-10-26** (Codex, fresh clone): confirmed PRs #98/#99 were
  already merged with green CI. Current `make test`: 831 pipeline + 51 web tests and build;
  fixture e2e passes at 1440×900 and 390×844. Rechecked the five real-data comparison UIs at
  both sizes on a local copy of the deployed inputs (github.io is blocked): all 4,767 feature
  classes/paint match an independent calculation, including 375 ACS MOE middle cases. All
  42 demographic comparison layers are neutral (the two population layers have no compare).
  TCAD byte-range/canary/native-ZIP checks pass. No source calls made: today's two failed
  calls are already logged, budget remaining is 0, and no TCAD canonical file exists yet.
  Live metrics and the five stored-property examples remain pending the next successful run.

- **P2-03** (Codex): WCAD 2026 canonical property facts from the four certified datasets,
  strict query/select allowlists, native string/omitted-null fixtures, count-checked paging,
  duplicate validation and improvement/MA/land joins. TCAD-compatible fields and count-only
  audit; approved 40/day budget and first-live-check gate. No core/web changes or layer.
  `make test` passes (903 pipeline, 51 web tests and builds), including 71 WCAD tests and
  canaries. No data-source calls. Awaiting Claude's live counts, coverage/MA agreement,
  parcel match, five-property browser check, resource/size and stored-field privacy check.

- **P2-03** (Codex, PR #110; Claude fix: alias the distinct land count): WCAD 2026 certified facts
  and values. Live run 40559703311: 236,087 homes kept, living area agrees with main-area segments
  for 99.6%, 99.2% matched to parcels. Ungated (PR #111).

- **P2-04** (Codex): Hays CAD monthly 2026 canonical facts, six numeric nested ZIPs
  identified by header, private files closed after the header and allowed-cell-only CSV decoding.
  Shared TCAD/WCAD names, mapped improvement choice, all MA-prefixed segments, duplicate conflict
  skips, count-only audit, exact approved 2/day budget and first-live-check gate. `make test`
  passes (981 pipeline + 51 web tests, schema/type checks and builds), including 76 Hays tests
  with canaries and temp cleanup. No source calls, core/web changes or layer. Awaiting Claude's
  counts/categories, living/MA/year/lot coverage, parcel match, five-property browser check,
  runtime/memory, canonical size and privacy scan; owner/sales row counts intentionally unavailable.

- **P2-04** (Codex, PR #113; Claude fix: exempt codes like `XE-11.182`): Hays CAD 2026 facts
  and values from the monthly export. Live run 40575881166: 90,157 homes kept, living area agrees
  with `MA*` segments for 97.9%, 98.4% matched to parcels. Ungated. WCAD and Hays spot checks passed.

- **P2-05** (Codex): canonical-only homes publisher and address/grid lookup, 114 shared
  synthetic address vectors, fixture provenance, exact parcel-ID joins and transactional
  validation. `make test` passes (1,127 pipeline + 51 web tests and builds). Full local
  `mm publish` with networking blocked: 159.3 s, 190,599,658 bytes, 664 shards (largest
  `ME.json` 1,953,427 bytes), 6,048 grid cells, ~3.44 GiB peak RSS. Homes/placed/unplaced:
  Travis 384,236/326,568/57,668; Williamson 236,087/234,152/1,935; Hays 90,157/88,758/1,399.
  Round-trip misses among numbered homes: 3,084/377,311, 1,007/235,581, 440/89,687 (all <1%).
  No source calls, adapter/web changes or generated-data commits. Unplaced condos stay
  address-searchable; Claude should check a dozen Zillow-style addresses per county.

- **P2-05** (Codex, PR #116; Claude fix: bare numbered streets → ordinals): one record per home
  in all three counties (710,480), address shards and a map grid built by `mm publish` (190.6 MB,
  662 shards); 20 listing-style addresses checked. Travis condos have no map point yet.

- **P2-06** (Codex): synthetic quoted-TSV FHFA adapter, approved 2/day monthly budget and
  live gate, reference arithmetic/41 shared vectors, size/hood statistics and two appended
  shard columns. Ranges stay switched off; no web code or demographics used. `make test` passes
  (1,206 pipeline + 51 web tests, schema/type checks and builds).
  Strict real-data `mm publish` failed after 159.1 s: Travis range coverage 366,469/384,236
  (95.38%) is below the specified 97%, mostly zero-building-value builder inventory. The prior
  190.6 MB homes build is byte-identical and preserved. An isolated, uninstalled diagnostic
  candidate is 197.49 MB (homes-only 105.7 s), with >99% single-family hood coverage in all
  counties. No source calls; FHFA remains fixture/Test data. Claude must resolve the coverage
  expectation and first-live-check FHFA; full counts and the blocker are in DECISIONS/the PR.

- **P2-06** (Codex, PR #118; Claude spec fix: builder inventory left out of the coverage check;
  homes size limit 300 MB): appraisal-based value ranges for 692,591 homes, built but unpublished.
  FHFA live (run 40607922630), ungated. HMDA preview: 263 tracts, median ratio 0.956, 85% within ±20%.

- **P2-08** (Codex): nine-column HMDA parser, tract aggregates/count-only audit, canary
  tests, annual non-published manifest, approved 6/day budget and first-live-check gate.
  Tract comparison and effective range switch are confined to `values.py`/`homes.py`;
  config requests publication, but fixtures/failing checks keep it off. No web changes.
  `make test` passes (1,255 pipeline + 51 web tests, schemas/types and build).
  Full offline `mm publish` with real canonical files and the HMDA fixture: 140.6 s,
  197.49 MB, zero source calls, canonical hashes unchanged. The three synthetic HMDA tracts
  have no eligible real-home overlap: check not passed, ratio/share unavailable, ranges
  hidden and facts published. Claude should first-live-check HMDA, compare with the
  263-tract / 0.956 median ratio / 85.2% within ±20% preview, then ungate per REVIEW.

- **P2-07** (Codex): Check a home search/card, ID-only links, nearest-home map panel/phone
  sheet, per-home browser-only asking prices and methodology. Web build derives public ID
  locators from existing shards; no pipeline, adapter, manifest, config or source changes.
  All 120 shared address and 41 range vectors pass; `make test` passes (1,207 pipeline +
  242 web tests, schema/type checks and builds). Fixture-only local e2e passes at 1440×900
  and 390×844, including keyboard selection, fresh links, range off/on, price reload/privacy
  and map lookup. Ranges obey the unpublished flag. Claude should check a dozen real addresses
  across the counties, a condo unit, map click, hidden ranges and phone layout after merge. Merged as PR #122 after Claude checked real addresses.

## Next

1. Claude: P2-08 HMDA first live check; then ranges show on the live site.
2. Owner: paste the P3-03 ("good place to live" score) prompt into Codex; P3-01 (batch listing
   check) can start once P2-08 is live.
3. Owner: download one real Redfin "Download all" CSV of a saved search, for checking P3-01.
4. Claude: spec P3-02, P3-04, P3-05.
5. Owner decision (P2-05b): how to place about 54,000 Travis condos (see Waiting on the owner).
6. Check the 2026-11-03 refresh report (FHFA is monthly now; expect it to be due).

## Open issues

- Six small-town PDs (Florence, Granger, Jarrell, Liberty Hill, Mustang Ridge, Thrall) cover under
  half of any block group, so those areas show the county sheriff's rate.
- FEMA and APD will read "stale" from about 2026-11-27 until the 2026-12-03 refresh (one-time).
- Areas cadence: P1-02 spec said "names monthly", layer manifests say annual; left annual.
- Schools: four checked finder links; other districts link to their AskTED website or show
  Not available.
- Transit covers CapMetro only; other agencies are labeled as not included.
- Parcels: `acres` is dropped (owner decision 2026-10-26); the stored file was re-run without it (run
  40425928158, same counts). Williamson has no `GEO_ID`; one Williamson ID is the text "PRIVATE ROAD".
- The test-data banner appears whenever any comparison came from fixtures; all comparison sources
  are live now, so it is off. A source that is ever re-gated would bring it back for that source.

- TCAD mobile homes coded `MH` (11,744 records, 2.4%) stay skipped (owner re-confirmed 2026-10-26).
- TCAD condos (54,675 kept) mostly have no match in the P2-01 parcel file (1,030 matched): the parcel
  file has no polygon per condo unit. Single-family match is 99.9%. P2-05 must place condos another way.
- The live workflow job times out at 30 minutes while `tcad` is allowed 45. Owner decision
  2026-10-26: leave it; raise the workflow `timeout-minutes` only if a run is cut off.
- P1-12 header nits: school score header shows 81.033 (three decimals) and the election header shows
  "13.7%" for a margin (a Republican lead in points). Cosmetic.
- The tcad probe checks (`tcad_layout`, `tcad_small_members`, `tcad_shapes`, `tcad_dups`,
  `tcad_estimate`) are in `tools/probe/probe.py`; they print shapes and counts only.

## Ideas from the owner (not started; need a spec and approval)

- (Taken up: comparisons are P1-11/P1-12.)

## Waiting on the owner

- **Travis condo placement (P2-05b).** 53,645 of TCAD's 54,675 condos have no parcel polygon
  of their own, and matching their street address to StratMap's parcel addresses places only
  about 1,000 (probe 40579380664). They stay findable by address without a map point until a
  location source is chosen. Options: (a) the U.S. Census Geocoder batch service (free, public
  domain, no key; about 6 calls of 10,000 addresses; street-interpolated, so "approximate
  location"); (b) a city/county address-point layer (terms to check first); (c) leave them
  unplaced. Recommended: (a). Needs approval as a new source with a budget.

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
