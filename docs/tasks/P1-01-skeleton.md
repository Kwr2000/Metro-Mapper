# P1-01 — Pipeline skeleton, CI and site shell

- **Agent:** Claude (it can read the Austin Watch snapshot, which Codex can't). Branch `claude/p1-01-skeleton`.
- **Phase:** 1, wave 1a. **Depends on:** owner approval of Phase 1.

## Goal

A working, tested skeleton that later tasks extend without touching core code. It covers a
Python pipeline with the adapter/layer seams, fixture mode, budgets, run log, empty-layer
guard, registry/health JSON, CI, and a MapLibre site shell deployed to GitHub Pages that renders
one demo layer from fixtures, labeled "Test data".

## Port from Austin Watch (piece by piece, with their tests, renamed `aw` → `mm`)

`pipeline/aw/adapter.py`, `runner.py`, `budget.py`, `runlog.py`, `paths.py`, `config.py`,
`manifests.py`, `registry.py`, `health.py`, `layer_guard.py`, `publish.py` (GeoJSON only),
`cli.py` (build/run/publish/schema/layers-due), `schemas.py` (keep only area-layer entities,
no listings), `probes/services.py` pattern (fold in `tools/probe/probe.py`). Web: `MapView`,
`LayerPanel`, `registry.ts`, `popup.ts`, `SourcesPage`, `HealthPage`, `layer-variants.ts`, with
their tests. CI: `ci.yml` without the "refuse public repo" job.

Do **not** port: listings, enrichers (until Phase 2), watchlist, digest, costs, condition,
hail, soils, text flags.

## Requirements

1. `pipeline/` installable (`pip install -e "pipeline[dev]"`), Python 3.12. `make test`,
   `make build`, `make dev` as in Austin Watch.
2. Test: app code (`web/src`) never names a specific layer id.
3. Test: a **demographics guard**. Any field tagged `demographic: true` in a layer manifest may
   not appear in a declared score or model input. A small registry `pipeline/mm/inputs.py`
   lists score/model input fields; it starts empty, and the test fails if any demographic field
   is listed.
4. Test: a **personal-fields guard**. Published files may not contain keys matching owner,
   mailing-address or exemption patterns (`owner`, `mail`, `addr` except `situs`, `_exempt`,
   `confidential`, `agent`).
5. Fixture runs are labeled "Test data" in the registry and in the UI.
6. CI: once per PR, `paths-ignore: docs/**, **/*.md`, concurrency cancel, `pytest -n 2 -m "not
   slow"`, web typecheck and tests, `vite build`. Pin `duckdb<2` only if DuckDB is used.
7. Pages: a workflow builds the site from committed published data and deploys to GitHub
   Pages on push to `main` when `web/**` or `data/published/**` changes (no schedule).
8. Footer on every page: "Data sources and terms" link, OSM/Census attribution placeholders,
   and "Appraisal-based values are not sale prices" text reserved for Phase 2.
9. `AGENTS.md` updated with paths and commands.

## Done when

`make test` passes locally, CI is green on the PR, the Pages site loads the demo layer with
"Test data" shown, and STATUS.md is updated.
