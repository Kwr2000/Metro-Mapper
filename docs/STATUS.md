# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-23 (P1-05)._

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

## Next

1. Claude: live run of `areas` for P1-02b (better names), check name-source counts.
2. Codex: P1-08 (filters, compare, shortlist, methodology). Claude reviews.
3. Claude: verify sources and write P1-07 (access) and P1-05b (agency-level safety) specs.

## Open issues

- APD codes verified as 2020 by Claude in P1-05's spec; the adapter enforces a 99% match.
  Agency-level safety elsewhere is deferred to P1-05b pending the DPS table-format check.
- Schools have four checked finder overrides; other districts use AskTED district websites
  or show Not available. Claude checks links and live join counts before ungating P1-06.

## Waiting on the owner

- Nothing right now.

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
