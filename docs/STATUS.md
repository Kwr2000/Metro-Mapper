# Status

Where the build stands, for whoever picks it up next (a new chat, Codex, or the owner).
Update at the end of each work session. History and reasons live in `DECISIONS.md`.

_Last updated 2026-10-23 (end of Phase 0 session)._

## Phase

**Phase 0 — discovery and verification: done; waiting for the owner's approval of Phase 1**
and answers to Q1–Q3 (`DECISIONS.md`, "Pending owner decisions").

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

1. Owner: approve Phase 1 (or adjust) and answer Q1–Q3.
2. Claude: P1-01 skeleton (ports Austin Watch seams). Then Codex prompts for P1-02, P1-03, P1-04.
3. Re-run the probe for ACS (`only=acs_keyless,acs_blockgroup_key`) before P1-03's live run.

## Open issues

- **Census API from GitHub answered HTTP 503** twice on 2026-10-23 (key set). Keyless requests
  are refused even at county level. If this persists, use the bulk summary files.
- APD block-group code vintage (2010 vs 2020) is unverified (P1-05).
- School-zone inventory is incomplete for about 11 districts (P1-06).

## Waiting on the owner

- Q1 (publishing unlicensed public government data), Q2 (TEA ratings), Q3 (WCAD sales ratios).
- If the ACS 503 persists: confirm the Census key was activated from the signup email.

## Working notes for agents

- The workspace can't reach source sites; use the probe workflow (GitHub runners) or the
  owner's built-in browser. `gh api` REST works; GraphQL and Actions log downloads don't.
- Actions logs in this public repo are public. Probes print counts and dates only.
