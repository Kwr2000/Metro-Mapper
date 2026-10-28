# P3-03 — "Good place to live" score (owner-weighted, non-demographic)

- **Agent:** Codex. Branch `codex/p3-03-area-score`. Regular (not draft) PR to `main`.
- **Phase:** 3 (approved by the owner 2026-10-27; plan in `docs/PLAN.md`). **Depends on:** Phase 1
  layers only, so it can be built now, in parallel with P2-07/P2-08.
- **No network, no new source, no budget change.** Inputs are the stored canonical files.
- **Core changes allowed:** a new module `pipeline/mm/area_score.py`, one call from `mm publish`
  (after the adapters, like `homes.publish`), its registration in `pipeline/mm/inputs.py`, tests;
  web code for the score panel and a map mode. No adapter changes.

## What the owner sees

A **Good place to live** panel on the map page:

- Sliders 0–5 for each factor (defaults in brackets): **Safety** (3), **Schools** (3), **Flood**
  (3), **Walk/bike to daily needs** (2), **Grocery and parks** (2), **Transit** (1). Weights live in
  the browser (`store.ts`) and in shared view links (numbers only).
- A **Colour by score** map mode: each block group coloured by its weighted score 0–100 in five
  classes (green better, as these inputs have a clear direction). Areas missing a factor still get
  a score from the others, marked "partial" (hatched or lighter) in the legend.
- The block-group popup gains a "Good place to live: 72 / 100 (your weights)" line with a
  breakdown: each factor's percentile, its raw value with source and date, and its weight.
- A short note: "Built only from safety, schools, flood, and access layers. Census demographics and
  election results are never used." (The People group's note already says this.)

## Factors (each a percentile 0–100 across the 1,206 block groups, 100 = best)

| Factor | Source field (canonical) | Better is | Notes |
|---|---|---|---|
| Safety | `dps_agency.block_group.rate_part1` | lower | Agency-wide rate: one number per police agency (say so). The finer APD layer covers only Austin, so it is **not** mixed in. |
| Schools | `schools.district.overall_score` of the district containing the block group's interior point | higher | District ratings only; never campus or attendance zones (ground rule 3). Districts without a rating → missing. |
| Flood | `fema_nfhl.block_group.flood_share_1pct` | lower | Share of the area in the 1% annual chance flood zone. |
| Walk/bike to daily needs | mean of the percentiles of `access.walk_basket` and `access.bike_basket` | lower | |
| Grocery and parks | mean of the percentiles of `access.walk_grocery` and `access.walk_park` | lower | |
| Transit | `access.transit_per_hour` | higher | CapMetro only; outside its area the raw value is 0 trips, which is real (not missing) where the access adapter says so. |

- Percentile = mid-rank percentile among block groups with a value (ties share the average rank),
  flipped for "lower is better", rounded to a whole number. Missing stays missing (never 0).
- Score (browser) = Σ(weight × percentile) / Σ(weight over factors present). If factors with
  weights summing to less than half the total weight are present, the score is "not available".

## Output

`web/public/data/area_score.json` (gitignored, built by `mm publish`): `{v, test_data, factors:
[{id, label, source, field, better, as_of, note}], rows: {geoid: [p_safety, p_schools, p_flood,
p_daily, p_grocery_parks, p_transit, raw...]}}`, with raw values alongside for the popup. Under
1 MB.

## Rules

- **No demographic or election input, ever.** Register the score's input fields in
  `pipeline/mm/inputs.py` so `assert_no_demographics` runs on them, and add a web test that the
  score code imports nothing from ACS or election layers.
- Every factor shows source and as-of date; percentiles are labelled as relative to the three
  counties, not absolute quality.
- The score ranks areas on the owner's chosen weights; it never ranks people or uses who lives
  there.

## Tests

Percentiles (ties, flips, missing), district assignment by interior point (a block group across
two districts takes the one containing its point), score arithmetic and the half-weight rule,
transit zero vs missing, `inputs.py` registration and the demographic guard, output size,
determinism, fixture fallback marks test data; web: sliders, defaults, persistence and view-link
round trip, map colours and the partial marker, popup breakdown text. E2E at 1440×900 and 390×844.

## Other requirements

`make test` and `cd web && npm run e2e` pass; methodology page gets a "Good place to live score"
section. STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green, tests pass. Claude then checks a handful of block groups by hand against the layers and
reviews the default weights with the owner.
