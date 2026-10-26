# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-25 (P2-02)._

## Phase

**Phase 2 — approved 2026-10-25, in progress** (P2-01 parcel base live). Phase 1 is complete.

**Phase 1 — done 2026-10-25** (approved 2026-10-23). Phase 0 is done. All owner questions (Q1–Q3)
are decided (`DECISIONS.md`).

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

- **P2-02** (Codex): TCAD 2026 canonical property facts, fixed-width byte allowlist,
  temporary streaming ZIP, living/ADU/HVAC aggregates, count-only audit and optional local
  parcel-match report. Native synthetic fixtures plus tiny ZIP/slice-guard/canary tests;
  approved 2/day budget and first-live-check gate. No core/web changes or layer. `make test`
  passes (812 pipeline, 41 web tests and builds). Awaiting Claude's live TOTALS/kept/coverage,
  HVAC, parcel-match, five-property, resource/size and stored-field privacy checks.

## Next

1. Owner: decide what to do about parcel `acres` (see Waiting on the owner).
2. Claude: review P1-12 PR #98 (colour by comparison) and P2-02 (TCAD), and run their checks.
3. Check the 2026-11-03 refresh report (expect nothing due; FBI and parcels are annual).

## Open issues

- Six small-town PDs (Florence, Granger, Jarrell, Liberty Hill, Mustang Ridge, Thrall) cover under
  half of any block group, so those areas show the county sheriff's rate.
- FEMA and APD will read "stale" from about 2026-11-27 until the 2026-12-03 refresh (one-time).
- Areas cadence: P1-02 spec said "names monthly", layer manifests say annual; left annual.
- Schools: four checked finder links; other districts link to their AskTED website or show
  Not available.
- Transit covers CapMetro only; other agencies are labeled as not included.
- Parcels: StratMap `acres` is unreliable (Williamson 0 for every parcel, Hays about twice the county
  area) and Williamson has no `GEO_ID`; one Williamson ID is the text "PRIVATE ROAD". Not used by
  anything yet.
- The test-data banner appears whenever any comparison came from fixtures; all comparison sources
  are live now, so it is off. A source that is ever re-gated would bring it back for that source.

## Ideas from the owner (not started; need a spec and approval)

- (Taken up: comparisons are P1-11/P1-12.)

## Waiting on the owner

- Parcel `acres`: drop it from the parcel record, or publish it as "not available" where the
  source is 0 (small follow-up fix plus one re-run of `parcels`, 4 calls).

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
