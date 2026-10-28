# P2-07 — "Check a home" page and map click

- **Agent:** Codex. Branch `codex/p2-07-check-a-home`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25). **Depends on:** P2-05 and P2-06 (merged). Read `AGENTS.md`,
  the Phase 2 plan in `docs/PLAN.md`, `docs/tasks/P2-05-homes-lookup.md` and
  `docs/tasks/P2-06-value-range.md` first.
- **Web only.** No pipeline, adapter, manifest or config change, except: add the TypeScript ports'
  test runs to `make test`, and one optional setting in `web/` if needed. No network beyond the
  site's own static files. Develop against `mm publish` output from fixtures; the real files are
  built by Pages.

## What the owner sees

A new **Check a home** item in the header (route `#/home`), and at close map zoom, clicking a
home opens the same card.

1. **Search box:** "Paste an address from Zillow or similar". Typing an address like
   `1008 S 8th St #2, Austin, TX 78704` and pressing Enter finds the home. Several matches
   (condo units without a unit number, duplexes, two records at one address) → a short list to
   pick from (address line, category, living area). No match → "Not found in the 2026 appraisal
   records for Travis, Williamson and Hays counties" plus the normalized form searched, and a
   hint to try without the unit or ZIP. Search is by street address only (never owner names).
2. **Home card** (one column, works at 390 px):
   - Address line, county, category in plain words ("Single-family home", "Condo",
     "Mobile home", "2–4 units", "Rural home", "Builder inventory (new construction)").
   - **Facts:** living area (sq ft), year built, lot size (acres; "Not available" when null —
     Williamson lots priced per lot often have none), floors, appraisal neighbourhood (code and
     `hood_desc` from `meta.json`).
   - **2026 appraisal:** market value, land, improvements, "as of January 1, 2026", the source
     (county appraisal district) and the export date (`certified`).
   - **Appraisal-based value range** — only when `meta.json` `value_range.published` is true.
     When false: "The value range is being validated and will appear here." Never show a range
     from test data without the Test data label. When shown:
     - "$328,000 – $400,000 (centre $364,000)" computed with the ported reference formula from
       `market_value`, the county level and the HPI factor in `meta.json`; ±10% or ±20%.
     - A "How this is worked out" disclosure listing the steps with the actual numbers: 2026
       appraisal → divided by the county's appraisal level (study name and year) → times the
       FHFA factor (quarters and index values, as-of date) → ±10% or ±20%, with each flag in
       plain words ("Built in the last two years", "Lot over one acre", "Condo", "Unusually
       large/small for its neighbourhood", "Not a single-family home"). Also the note that
       year-over-year changes aren't checked, and the share of sales within 10% from the study.
     - No range (`range_pct` null): say why in plain words ("No building value on January 1, 2026",
       "Partial-ownership record", "No 2026 market value").
   - **Asking price** (optional input, kept only in this browser via `store.ts`, per home id;
     never in URLs or shared links): shows "below / inside / above the appraisal-based value
     range" (only when the range is shown), and the asking price per sq ft against the
     neighbourhood table from `hoods.json` ("higher than about 70% of similar homes in this
     appraisal neighbourhood, by appraisal-based $ per sq ft"), with n and the percentiles. No
     words like "good deal", "overpriced", "fair value" or "worth" anywhere (a test greps the built
     bundle and page text).
   - **The area:** the block group's name (as the map uses) and a "Show on map" button that opens
     the map centred on the home with its block group highlighted. Homes without a location: "No
     map location yet for this home (Travis condos are not yet placed)".
   - Sources line: county appraisal district, StratMap (location), FHFA and the Comptroller study
     (when the range is shown), each with its date.
3. **Map click:** at zoom ≥ 15, a click finds the nearest placed home within 30 m (load the
   clicked grid cell and its eight neighbours, as the P2-05 contract says), then opens the card in
   a side panel (bottom sheet on phones). Below zoom 15 the existing area popup behaviour is
   unchanged. Optionally draw home points from the loaded cells at zoom ≥ 16 (small grey dots,
   no labels).
4. **Shareable link:** `#/home?id=48491:R417015` opens that home (id only).

## Ports (TypeScript, one source of truth each)

- `web/src/homes/address.ts`: `normalizeQuery`, `shardId`, `matches` — ported from
  `pipeline/mm/homes.py`. Tests run **every case** in `pipeline/mm/data/address_cases.json` (the
  test reads that file; don't copy it).
- `web/src/homes/range.ts`: `valueRange(marketValue, countyFips, rangePct, factor, levels)` —
  ported from `pipeline/mm/values.py`, including nearest-even rounding at $500. Tests run every
  case in `pipeline/mm/data/value_range_cases.json`.
- `web/src/homes/data.ts`: loads `data/homes/meta.json` once, shards and cells on demand with a
  small cache (keep at most 20 shards and 50 cells); handles split shards via `meta.shards`.

## Rules

- Honest numbers: every figure with its source and date; "Not available" for nulls, never 0.
- No demographic data on the card. The area link goes to the map; it doesn't summarise people.
- Test data: if `meta.json` or a county is `test_data`, show the Test data badge on the card.
- Performance: a lookup loads one shard (≤ 2 MB); first card in under 2 s on a fast connection
  (e2e checks the number of requests, not timing).
- Accessibility: labelled input, keyboard-only flow (type, Enter, arrow through matches, Enter),
  focus moves to the card, the range disclosure is a `<details>`.

## Tests

Unit: both ports against the shared JSON vectors; data loader (split shards, cache limits,
missing shard → not found); card rendering for each category, null facts, range on/off, each
no-range reason, flags text, asking-price comparison and $/sq ft percentile wording; banned-words
check; asking price never in the URL or shared link; map click nearest-within-30 m on a small grid
(including a cell edge). E2E (fixtures, 1440×900 and 390×844): search a fixture address with a
unit, pick from multiple matches, open via link, map click at zoom 16, asking price persists after
reload, range hidden when `published` is false and shown when a test meta sets it true.

## Other requirements

`make test` passes (pipeline and web); `cd web && npm run e2e` passes at both sizes; methodology
page gets a "Check a home" section (what it uses, the range method, what it can't know: interiors,
condition, recent remodels, the market since the index's latest quarter). STATUS one entry;
DECISIONS for unsettled choices.

## Done when

CI green, `make test` and e2e pass. PR lists files and screenshots described in words. Claude then
checks the live site with real data: a dozen addresses across the three counties, a condo unit,
a map click, the range hidden while unpublished, and the phone layout.
