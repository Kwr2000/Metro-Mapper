# P1-08 — Filters, comparison, shortlist, methodology page

- **Agent:** Codex. Branch `codex/p1-08-filters-compare`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1c. **Depends on:** P1-02..P1-06 (merged). P1-07 (access) is not built
  yet; everything here is registry-driven, so its layers join in automatically later.
- Web only (`web/`), plus small manifest/schema additions if needed. **No pipeline adapters, no
  network calls, no new data sources.** Read `AGENTS.md` first; app code never names a layer id.

## Goal

Help the owner narrow down and compare areas (2020 block groups) using the layers already on the
map, and keep a private shortlist.

## Rules (AGENTS.md)

- Every value shown keeps its source and as-of date, and estimates keep MOE and reliability.
  Missing values show "Not available" (or the layer's own note), never 0.
- **Demographics:** demographic layers (`demographic: true`) may be filtered and compared, but
  they sit in their own section headed "People (context only)", with neutral labels, no default
  selection, and **no sorting or ranking by a demographic field anywhere**. No combined score of
  any kind is added in this task.
- Personal state (shortlist, notes) stays in the browser via `web/src/store.ts`; it is never
  put in a URL or sent anywhere.

## 1. Filters

- Built from the registry. A layer contributes a filter when `join` is `block_group` and its
  first popup field has format `number`, `percent` or `currency`. For layers that share a
  variant family, use only the block-group variant. Label = the popup field label, with the
  layer's as-of date beside it.
- Each filter is a two-handle range slider over the field's observed min–max (read from the
  loaded GeoJSON), with numeric inputs for exact values; percent fields show 0–100%. Off by
  default; turning one on loads its data.
- Areas with no value for an active filter don't match, and the panel says how many were
  excluded for that reason ("312 areas have no value for this filter").
- Matching areas get a strong outline; non-matching areas are dimmed. Show "N of 1,206 areas
  match". "Clear filters" resets all.
- Sections: one per layer group (Areas, Flood, Safety, …), then "People (context only)" last,
  collapsed by default, with this line: "Census estimates for context. They are not used in any
  score."

## 2. Compare (up to 4 areas)

- Clicking an area offers "Add to compare". A compare tray lists the chosen areas by name (from
  the block-groups layer) with a remove button; a fifth add asks the user to remove one first.
- "Compare" opens a table: one column per area, one row per block-group-joined layer's popup
  fields (same formats and MOE/reliability/annotation rendering as popups, reusing `popup.ts`),
  grouped by layer group, each group showing source and as-of. Demographic rows go last under
  "People (context only)". No sorting.
- Also show, per area, the school district(s) whose polygon contains the area's interior point,
  from any loaded layer with `join: jurisdiction` (just the name and its link field), when that
  layer's data has been loaded.

## 3. Shortlist and notes

- "Save area" adds it to a shortlist with an optional free-text note (both in localStorage via
  `store.ts`). A "Shortlist" panel lists saved areas; clicking one flies the map to it; notes can
  be edited or deleted; "Compare shortlist" fills the compare tray (first 4).
- If storage is unavailable, the shortlist works for the session and says it won't be kept.

## 4. Shareable link

- The URL hash keeps the view: map centre and zoom, visible layers, chosen variant per family,
  active filters and the compare list (area GEOIDs). Opening the link restores them. Never notes
  or the shortlist. Keep the existing `#/` page routes working (e.g. `#/?v=...`).

## 5. Methodology page (`#/methodology`)

- Static page content in `web/src/content/methodology.md` (render it with a small, safe markdown
  renderer or plain JSX; no raw HTML from the file). Draft it from `docs/DECISIONS.md` and the
  task specs, plain language, short sections: what an area is (2020 block groups, tracts as the
  steadier view); how areas are named (rule order and sources); flood shares (1% / 0.2%, the 99%
  coverage rule, county-map seams); ACS estimates (90% MOE, the 30% reliability rule, Census
  notes, capped values); safety (APD reports, 12 full months, the 50% city-limits rule, smoothing
  toward the Austin-wide rate, "not available" outside Austin PD); schools (TEA 2024–25 ratings,
  growth first, no attendance zones, check the district finder); what "Not available" means;
  the demographics rule; refresh cadence. Mark anything you were unsure of with
  `<!-- Claude: check -->` so Claude reviews it.
- Link it from the header and footer.

## 6. Layout and tests

- Desktop-first; at 390 px wide the panels become a bottom sheet with tabs (Layers / Filters /
  Compare / Shortlist) and nothing overflows horizontally.
- Unit tests (Vitest): filter construction from a registry fixture (including the demographic
  section and variant handling), match/exclude counts with missing values, compare limit, URL
  hash round trip (and that notes never appear in it), storage-unavailable fallback.
- Playwright smoke (local only, **not in CI**): `npm run e2e` against `vite preview` with the
  fixture build, at 1440×900 and 390×844: page loads, a filter narrows the count, two areas
  compare, a shortlist entry survives reload. Use the preinstalled Chromium if present.
- `make test` passes. Update `docs/STATUS.md` (one entry) and add a DECISIONS entry for any
  choice not settled here.

## Done when

CI is green and `make test` passes locally. The PR description lists files changed, screenshots
at both sizes (attach or describe), and what Claude should check: filters on the live site, the
People section's wording and lack of sorting, the methodology draft's `Claude: check` markers.
