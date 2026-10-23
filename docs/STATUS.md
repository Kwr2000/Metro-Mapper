# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-23 (P1-02)._

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

- **P1-02** (Codex): areas adapter, synthetic naming/paging fixtures and tests, block-group
  and tract manifests, budget and live gate; demo removed. `make setup` and `make test`
  pass. Awaiting Claude's review and first live check (expect 1,206 block groups).

## Next

1. Owner: turn on GitHub Pages once (Settings → Pages → Source: GitHub Actions).
2. Claude: review P1-02 and run its first budgeted live check before merging. After it merges,
   refine P1-03 (ACS) and P1-04 (flood) against its code and give their prompts.
   Claude reviews each PR, runs `make test`, and does the live run before merging.
3. ACS works from GitHub with the key (run 39891997771). Early 503s were transient.

## Open issues

- APD block-group code vintage (2010 vs 2020) is unverified (P1-05).
- District finder-link list is incomplete for about 11 districts (P1-06).

## Waiting on the owner

- Turn on GitHub Pages: Settings → Pages → Build and deployment → Source: GitHub Actions.
  The first deploy (after PR #7) failed only because Pages is off; re-run "Deploy site" after.

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
