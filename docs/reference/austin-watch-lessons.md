# Austin Watch — lessons and reuse list

Austin Watch (Oct 2026, repo deleted) was the owner's private, listings-based dashboard for
central Austin. Its code-and-docs snapshot, with all listing data removed, is
`austin-watch-reference.zip` in the owner's Claude Project. **It is never committed here.**
Reuse piece by piece, with tests, after review. Written 2026-10-22 from the snapshot's
`REFERENCE-README.md`, `docs/STATUS.md` and `docs/DECISIONS.md`.

## Lessons

1. **Scope creep was the main failure.** Six phases in ten days, listing sweep, digest,
   true-cost, text flags… Keep phases small and stop between them.
2. **Actions minutes ran out** (1,806 of 2,000 by 10-21). Causes: a daily ~54-min sweep, and
   CI running twice per change (PR and push to main) at ~14 min a run. Fixes that worked: CI
   once per PR, skip docs-only PRs, cancel superseded runs, fast subset (`-m "not slow"`,
   `pytest -n 2`), full suite run locally before merge. (Austin Watch was private; Metro
   Mapper is public — see `docs/SOURCES.md` for the Actions billing check.)
3. **Probe new endpoints first, from GitHub.** Several services behaved differently from
   Actions than from a laptop. A manual "Service probe" workflow with a summary posted as a
   notice annotation (readable via `gh api .../check-runs/{id}/annotations`) worked well.
4. **AI reviews misstated source facts** (licenses, grain, what HMDA's value means). Verify at
   the publisher and cite the page and date.
5. **Census API needs a key for block-group data.** Keyless requests returned HTTP 200 with an
   HTML "Missing Key" page; metadata worked without a key. Treat non-JSON as a failure.
6. **ACS request shape matters.** `group(B01001)` as its own request, other variables in
   explicit lists of ≤ 50, 60 s timeout. The 304-variable B01001 list timed out at 20 s.
7. **A live refresh can silently empty a layer.** The empty-layer guard holds the previous
   data when a refresh would drop a layer below 50% of its last count (if it had ≥ 20).
8. **Dependency majors break CI.** DuckDB 2.0.0 (2026-10-21) removed `Relation.fetchone()`.
9. **Gating new sources.** A `live_gates.yaml` gate plus a `verification_pending` flag in the
   adapter's `source.yaml` kept unverified sources in fixture mode. Ungating must clear both.
10. **Draft PRs from Codex** couldn't be merged over REST; ask for regular PRs.
11. **Source facts it found (to re-verify, not trust):** APD `fdj4-gpfu` has a text
    `census_block_group` (10 digits, county+tract+group; prefix `48`), vintage undeclared;
    AISD's GIS download page still offered 2022–23 zone files while its 2026–27 assignment
    app used an ArcGIS FeatureServer (`services2.arcgis.com/5HXFPHsCivNoDso0/.../Reassignments`);
    TEA's statewide campus accountability CSV via the `rptsvr1.tea.texas.gov` broker (2026
    preliminary, final ratings due 2026-12-11); CapMetro's developer page pointed to the
    data.texas.gov GTFS dataset `r4v4-vz24`, current (feed start 2026-10-07) as of 10-12;
    TIGERweb Census2020 MapServer layer 8 for 2020 block groups.

## Worth reusing (after review, with tests)

| Piece (path in the snapshot) | What it gives us | Notes |
|---|---|---|
| `pipeline/aw/adapter.py`, `runner.py`, `budget.py`, `runlog.py` | Adapter contract (plan/fetch/normalize/source_as_of), fixture mode, call budgets from a committed run log | Drop listing slices; rename package |
| `pipeline/aw/manifests.py`, `layers/*.yaml`, `registry.py`, `health.py` | One manifest per layer; registry/health JSON for the site | Keep "app never names a layer" test |
| `pipeline/aw/layer_guard.py` | Empty-layer guard | Small, self-contained |
| `pipeline/aw/probes/services.py` + `services-probe.yml` | Probe pattern with annotation summary | Remove the private-repo guard |
| `adapters/acs_block_groups` | ACS + TIGERweb, MOE handling, reliability flag, request split | Extend to three counties; demographics stay out of scores |
| `adapters/flood_fema_polys`, `fema_map_changes` | FEMA NFHL polygons/LOMRs | Check coverage beyond Travis |
| `adapters/tea_campus_ratings` | TEA CSV parser, preliminary/final handling | Extend beyond AISD |
| `adapters/osm_amenities` | Everyday amenities | Switch to a Geofabrik extract, not Overpass |
| `adapters/nrcs_soils` | Soil screening | Later phase, if at all |
| `adapters/crime_block_groups` | APD aggregate query (no incident rows) | Add vintage crosswalk |
| `web/src` layer panel, registry loading, sources page | MapLibre layer panel | Strip listing UI |
| `.github/workflows/ci.yml` | Fast-subset CI | Remove the "refuse public repo" job |

## Do not carry over

Listing sweep and Neuhaus/RentCast code, parcel matching via live TCAD search, listing
episodes/digest/text flags/true-cost, the "private by construction" rule and its CI guard,
and any listing-specific UI.
