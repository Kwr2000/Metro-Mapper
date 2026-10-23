# Decisions

Design decisions and the owner's approvals, newest first. Each entry says what was decided,
why, and (for approvals) that the owner approved it in writing.

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
