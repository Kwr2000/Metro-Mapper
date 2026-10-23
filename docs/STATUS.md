# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-23 (owner decisions Q1, Q2)._

## Phase

**Phase 0 — discovery and verification: done; waiting for the owner's approval of Phase 1**
and the answer to Q3 (`DECISIONS.md`). Q1 and Q2 were decided 2026-10-23: no permission requests,
stay public, TEA ratings from data.texas.gov, district finder links instead of zone maps.

## Done

- Scaffold: `AGENTS.md`, `LICENSE` (MIT), `.gitignore`, `docs/reference/austin-watch-lessons.md` (PR #1).
- Source probe: `tools/probe/probe.py` + `.github/workflows/probe.yml`, manual only (PRs #2, #3).
  Run 39891186379: 26/29 OK; re-run fixed GTFS. Read results with
  `gh api repos/Kwr2000/metro-mapper/check-runs/{job_id}/annotations`.
- `docs/SOURCES.md` (all sources verified 2026-10-22), `docs/PLAN.md` (scope, architecture,
  validation targets, Phase 1 tasks), Phase 1 specs in `docs/tasks/`.
- Decided: Hays is in v1; StratMap 2026 (CC0) as baseline parcel shapes; WCAD via its open-data
  portal; GTFS from data.texas.gov (current); APD block groups + DPS agency-level crime.

## Next

1. Owner: approve Phase 1 (or adjust) and answer Q3.
2. Claude: P1-01 skeleton (ports Austin Watch seams). Then Codex prompts for P1-02, P1-03, P1-04.
3. ACS works from GitHub with the key (run 39891997771). Early 503s were transient.

## Open issues

- APD block-group code vintage (2010 vs 2020) is unverified (P1-05).
- District finder-link list is incomplete for about 11 districts (P1-06).

## Waiting on the owner

- Q3 (WCAD sales ratios).

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
