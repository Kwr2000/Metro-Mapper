# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-24 (P1-05b)._

## Phase

**Phase 1 — approved 2026-10-23, in progress.** Phase 0 is done. All owner questions (Q1–Q3)
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
  Owner budget/publication approvals recorded; live use gated. All 47 adapter tests, fixture
  build, schema/type checks and 34 web tests pass; full `make test` awaits the workspace's
  missing existing `h3` dependency. Awaiting Claude's live agency/place counts, assignment
  counts, Austin rate and unmapped-agency totals.

## Next

1. Claude (scheduled, 2026-10-25 00:15 UTC): `areas` live run for P1-02c name polish
   (merged PR #48); check no all-capital planning-area names (except MLK/RMMA/UT) and no
   "Crk"/"Ests"; merge the data PR.
2. Claude (scheduled, 2026-10-25 00:25 UTC): re-run the `access` first live check (P1-07,
   merged PR #50; first run 40054053666 failed only on CapMetro's missing `calendar.txt`,
   fixed PR #51; OSM processing took ~12 min). Then merge data, ungate `access`.
3. Claude: P1-05b review and first live check (28 agencies, 25 places, split count, Austin PD
   about 35.7 per 1,000), then ungate.
4. Later: P1-08 is merged (filters, compare, shortlist, methodology); look at it on the live
   site once all layers are in. Check the 2026-11-03 refresh report (expect nothing due).

## Open issues

- Agency-level safety outside Austin PD: P1-05b built on fixtures, awaiting Claude's live check.
- FEMA and APD will read "stale" from about 2026-11-27 until the 2026-12-03 refresh (one-time).
- Areas cadence: P1-02 spec said "names monthly", layer manifests say annual; left annual.
- APD reconciliation check is skipped until APD's next refresh stores the new summary count.
- Schools: four checked finder links; other districts link to their AskTED website or show
  Not available.
- Transit covers CapMetro only; other agencies are labeled as not included.

## Waiting on the owner

- Nothing right now.

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
