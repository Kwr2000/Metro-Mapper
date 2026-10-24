# Plan

The build plan for Metro Mapper. Changes after approval go in `DECISIONS.md`.
_Written 2026-10-22 at the end of Phase 0._

## Goal

A public, map-first static site for the Austin metro that helps the owner understand the housing
market and judge areas and individual homes found on listing sites, so they can buy well within
6 months to 2 years. No listings are pulled. Desktop-first; works on a phone. Public quality from
day one.

**Geography for v1: Travis, Williamson and Hays counties** (Hays decided in Phase 0, see
DECISIONS 2026-10-22). Base unit: 2020 Census block groups (1,206 in the three counties), with
tracts as the steadier view and H3 resolution 8 as a stability check.

## v1 phases (stop for the owner's approval between phases)

| Phase | Delivers | Status |
|---|---|---|
| 0 | Source verification, this plan, `SOURCES.md`, `DECISIONS.md`, Phase 1 specs | Done 2026-10-22 (awaiting approval) |
| 1 | Pipeline skeleton; block-group map with names; layers for schools, safety, access, flood, ACS demographics; filters; side-by-side comparison; methodology page | Next |
| 2 | Listing check: harmonized parcel base for T/W/H, static sharded address lookup, appraisal-based value range with flags | |
| 3 | Value-for-money map with browser-side weights | |
| 4 | Market trends: appraisal history by area (WCAD 2015–2026; TCAD and Hays exports by year), HMDA tract values | |
| Later | More counties, fixed destinations for commutes, verified sale prices and a calibrated model, launch polish | |

## Architecture

- **Pipeline** (Python 3.12) in `pipeline/`: one adapter per source (`plan → fetch → normalize`,
  recorded fixtures, contract test), one manifest per map layer, budgets computed from a
  committed run log, an empty-layer guard, and registry/health JSON for the site. Ported piece
  by piece from Austin Watch (`docs/reference/austin-watch-lessons.md`).
- **Site** in `web/`: MapLibre GL, static GeoJSON/PMTiles, GitHub Pages. App code never names a
  specific layer. Personal notes, weights and saved areas stay in the browser (localStorage).
- **Refresh**: one monthly scheduled workflow runs the due adapters, writes a validation report,
  and publishes. If a hard check fails, the previous month's data stays live. The workflow
  commits its run log every month, which keeps the scheduled job alive (60-day rule).
- **CI**: once per PR, fast subset, skips docs-only PRs, cancels superseded runs. The full suite
  runs locally before merge. Public repo, so standard runners are free (GitHub docs, checked
  2026-10-22). Keep usage light anyway.
- **Big files** (appraisal exports of 0.5–3.5 GB) are processed inside Actions runs and never
  committed. Only derived, stripped outputs are published.

## Phase 1 scope (small areas, filters, comparison)

Layers, each with source, as-of date and a "not available" state:

1. **Base and names**: 2020 block groups and tracts. Names come from (in order) City of Austin
   neighborhood planning areas, CAD subdivisions with the largest share of the block group's
   parcels, then Census places. The source of each name is shown.
2. **Demographics (ACS 2020–2024)**: income, education, age, household type, owner-occupancy,
   housing age, race and ethnicity. Estimates with MOE and a reliability flag; neutral
   sequential colors; filters only. Never inputs to any score (enforced by a test).
3. **Flood**: FEMA NFHL: share of each block group's area in the 1% and 0.2% annual-chance zones.
4. **Safety**: APD reported incidents per block group (Austin PD area only, 12 months, by
   category, small-count shrinkage toward neighbors, per-area density and per-resident rate);
   elsewhere the agency-level rate from DPS Crime in Texas, labeled as agency-level. Never
   spread onto streets.
5. **Schools**: district boundaries and campus points; TEA ratings including School Progress
   and Academic Growth from TEA's data.texas.gov release (2024–25, labeled with its year); no
   copied attendance zones, each area links to its district's school finder.
6. **Access**: walking and biking minutes on the OSM street network from each block group to
   the nearest grocery, park, school and a "daily needs" basket; CapMetro scheduled frequency
   (weekday 7–9 am) within a 10-minute walk, with "no fixed-route service" where none exists.
7. **UI**: layer panel, filters over any layer (demographic filters stay separate and neutral),
   side-by-side comparison of up to 4 areas, shortlist saved in the browser, sources page and
   methodology page.

## Validation targets (set before building)

Each refresh publishes `validation.json` and a readable report. **Hard** checks keep the
previous month live on failure; **soft** checks are reported only.

| Check | Target | Kind |
|---|---|---|
| Every published layer has source, as-of and feature count ≥ 50% of last month (empty-layer guard) | 100% | Hard |
| No demographic field reaches any score, ranking or value input (static test + runtime assertion) | 0 violations | Hard |
| No personal fields in published files (owner, mailing address, exemption flags) | 0 | Hard |
| Block-group crime counts sum to the APD aggregate for the same period (located reports only) | Exact | Hard |
| Area rankings stable between block groups and H3 res-8 hexagons, per non-demographic attribute | Spearman ≥ 0.8 | Soft |
| (Phase 2+) Tract median appraisal-based value vs HMDA median `property_value`, tracts with ≥ 30 purchase loans | Median ratio 0.90–1.10; ≥ 75% of tracts within ±20% | Soft (Hard from Phase 2) |
| (Phase 2+) ZIP medians vs Redfin/Zillow | Rank correlation ≥ 0.8 | Soft, checks only |

Context, not a check: the Comptroller's 2024 study (median level 1.00 / 0.96 / 1.00; COD
7.6 / 7.6 / 7.1 for T / W / H).

## Phase 1 tasks

Specs in `docs/tasks/`. Call budgets and refresh cadences in the specs are proposals: approving
Phase 1 approves them, and any later change needs the owner again. Wave 1a is ready to build. Waves 1b and 1c are outlined and get
refined before they are built.

| ID | Task | Agent | Wave | Depends on |
|---|---|---|---|---|
| P1-01 | Pipeline skeleton, CI, site shell on Pages (ported from Austin Watch) | Claude | 1a | — |
| P1-02 | Block groups, tracts and area names | Codex | 1a | P1-01 |
| P1-02b | Better area names (more subdivision sources) | Codex | 1a | P1-02; owner budget approval |
| P1-02c | Area-name polish (capitals, abbreviations) | Codex | 1a | P1-02b |
| P1-03 | ACS demographics layers (3 counties) | Codex | 1a | P1-01, P1-02 |
| P1-04 | FEMA flood shares | Codex | 1a | P1-01 |
| P1-05 | Safety: APD reported incidents by block group | Claude verified; Codex builds | 1b | P1-02 |
| P1-05b | Safety: agency-level rates outside Austin PD (DPS) | Claude verifies, Codex builds | 1b | P1-05 |
| P1-06 | Schools (district outlines, campuses, TEA ratings, finder links) | Claude verified; Codex builds | 1b | P1-02 |
| P1-07 | Access (OSM walk/bike minutes, CapMetro frequency) | Claude verified; Codex builds | 1b | P1-02 |
| P1-08 | Filters, comparison, shortlist, methodology page | Codex | 1c | P1-02..07 |
| P1-09 | Monthly refresh workflow and validation report | Claude | 1c | P1-02..07 |

## Risks

- **ACS API** had transient 503s from GitHub on 2026-10-23. Retry once; the fallback is the bulk summary files.
- **Terms**: CAD, county, city and TEA portal data are published with no stated license (owner
  decision 2026-10-23). If the owner later decides to go private, these choices get revisited.
- **APD block-group vintage** is undeclared and must be checked before joining to 2020 polygons.
- **Scope creep**: Phase 1 is the largest phase. Hold to the list above; new ideas go to "Later".
