# P3-04 — Value for money: area score against price per square foot

- **Agent:** Codex. Branch `codex/p3-04-value-for-money`. Regular (not draft) PR to `main`.
- **Phase:** 3 (approved 2026-10-27). **Depends on:** P3-01, P3-03 (merged); build on top of P3-02
  if it has merged (use whatever centre formula `values.py`/`range.ts` provide).
- **No network, no new source, no budget change.**
- **Core changes allowed:** a small publisher in `pipeline/mm/homes.py` or a new
  `pipeline/mm/area_price.py` called from `mm publish`, its `inputs.py` registration, tests; web
  code for a map mode, an areas list and two batch-table columns.

## What the owner sees

1. **Map mode "Score vs price"** (in the Good place to live panel, next to "Colour by score"):
   each block group in one of four colours by the owner's current weights —
   **Higher score, lower price per sq ft** · Higher score, higher price · Lower score, lower price ·
   Lower score, higher price — split at the three-county medians, plus grey "Not available" (fewer
   than 10 homes with a range, or no score). The legend says what "price" means: the median
   appraisal-based centre per sq ft of single-family homes in the area.
2. **"Areas list"** (a tab in the same panel): a table of block groups with name, score (your
   weights), median $ per sq ft, number of homes, and a **max $ per sq ft** slider; sorted by score,
   highest first, among areas under the slider. Each row links to the map (zoom to the area). A note:
   "Prices are appraisal-based, not sale prices; a high score reflects only the factors and weights
   you chose."
3. **Batch table (P3-01):** two new sortable columns for matched homes with a block group: **Area
   score** (your weights) and **Area $/sq ft percentile** (where the area's median sits among all
   areas). Default sort unchanged.
4. The block-group popup's score breakdown gains "Median appraisal-based $ per sq ft: $243 (n = 412
   single-family homes)".

## Data

`web/public/data/area_price.json` (gitignored, built by `mm publish` after homes):
`{v, test_data, as_of, method, rows: {geoid: [n, median_psf]}}` for block groups with ≥ 10
single-family homes that have a range and a living area; `median_psf` = median of centre ÷ living
area (whole dollars). Homes without a location are not counted (say so). Under 100 KB.

## Rules

- No demographic or election input: register the publisher's fields (`category`, `market_value`,
  `living_area`, `block_group`, `range_pct`, plus the centre inputs) in `inputs.py`; the browser's
  quadrant and list use only `area_score.json` and `area_price.json` (a web test checks imports).
- Words: "higher/lower score", "higher/lower price per sq ft". Never "good deal", "bargain",
  "undervalued", "fair value", "overpriced" or "worth" (the banned-words test covers the new copy).
- Missing stays missing; quadrant splits ignore areas without both values.
- Test data badges as elsewhere.

## Tests

Publisher (medians, n threshold, unplaced homes excluded, determinism, size); quadrant splits at
medians incl. ties and missing; list filter and sort; slider bounds from the data; batch columns
and sorting; popup line; weights change → colours and list update; demographic-import guard;
banned words. E2E at 1440×900 and 390×844 (map mode on/off, list filter, batch columns).

## Other requirements

`make test` and web e2e pass; methodology page gets a "Score vs price" section. STATUS one entry;
DECISIONS for unsettled choices.

## Done when

CI green, tests pass. Claude checks on the real data that the four quadrants and the areas list
look plausible (e.g. which areas appear under $250/sq ft with high scores) and reports a few.
