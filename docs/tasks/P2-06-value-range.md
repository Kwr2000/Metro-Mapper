# P2-06 — Appraisal-based value range

- **Agent:** Codex. Branch `codex/p2-06-value-range`. Regular (not draft) PR to `main`.
- **Phase:** 2 (approved 2026-10-25; method in `docs/PLAN.md`, "How the value range works").
  **Depends on:** P2-05 (merged). Read `AGENTS.md`, the Phase 2 plan and `docs/tasks/P2-05-homes-lookup.md`.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **One new source:** `fhfa_hpi` (budget `{per_day: 2}`, refresh monthly, approved with the Phase 2
  plan). A normal run is **1 call**. Live gate "awaiting Claude's first live check".
- **Core changes allowed:** a new module `pipeline/mm/values.py`, calls from `pipeline/mm/homes.py`
  (two shard columns and `meta.json` fields), one config file, tests. No web code (P2-07).
- **Published but switched off.** Ranges stay hidden until P2-08's validation passes:
  `meta.json` → `value_range.published: false` (from config). P2-08 turns it on.

## Wording (ground rules 1–2)

Always "appraisal-based value range". Never "fair value", "worth", "estimate of sale price" or
"good deal". Every number carries its source and as-of date in `meta.json`.

## The method (each step shown on the page later)

For a home with a 2026 market value `V` in county `c`:

1. **Appraisal level** `L[c]`: Comptroller 2024 Property Value Study, category A (single-family)
   median level: Travis 1.00, Williamson 0.96, Hays 1.00 (`docs/SOURCES.md`). Level-adjusted value
   `V / L[c]`.
2. **Time adjustment** `F`: FHFA purchase-only house price index, Austin–Round Rock–San Marcos
   (CBSA 12420), **seasonally adjusted** column. Base = mean of the SA index for the quarter before
   and the quarter of the value date (value date 2026-01-01 → mean of 2025 Q4 and 2026 Q1); `F` =
   latest SA quarter ÷ base. With today's file: base (680.77 + 656.56) / 2 = 668.665, latest
   2026 Q2 681.16, `F` = 1.0187. `F` is the same for all three counties.
3. **Centre** `M = round(V / L[c] × F, -3)` (nearest $1,000).
4. **Width:** ±10% (about 3 in 4 single-family sales fell within 10% of the appraisal in the
   study: 73–76%). **±20%** when any of these flags applies (codes in brackets):
   - `new`: built in the last two years (`year_built ≥ value_year − 2`) or `builder_inventory`;
   - `lot`: `land_acres > 1`;
   - `condo`: category condo;
   - `size`: living area below the 5th or above the 95th percentile of homes of the same
     category in the same county and `hood_cd` (groups of ≥ 20 with living area; otherwise the
     same category county-wide);
   - `type`: `mobile_home`, `two_to_four_units` or `rural_home` (the study's level is for
     single-family homes).
   Year-over-year jumps (in the plan) aren't available: P2-02–P2-04 store 2026 values only (owner
   decision 2026-10-26). Say so in the method note.
5. **No range** (`range_pct` null) with a reason code when: `V` missing or 0 (`no_value`);
   improvement value 0 (`no_building`); a TCAD partial-ownership record (`partial`).
6. Low/high = `M × (1 ∓ w)`, rounded to $1,000.

## Implementation

### `fhfa_hpi` adapter (one call)

`https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_po_metro.txt` (checked by probe
40587875637, 2026-10-27): tab-separated, header exactly
`cbsa	metro_name	yr	qtr	index_nsa	index_sa`, `metro_name` in double quotes, 14,201 lines, 142
rows for `12420`, latest 2026 Q2 (NSA 693.01, SA 681.16). Public domain U.S. government data,
credit "FHFA House Price Index (purchase-only)". Keep only CBSA 12420; canonical records
`dataset="hpi"`, `feature_id="12420:<yr>Q<qtr>"`, properties `cbsa`, `metro`, `year`, `quarter`,
`index_nsa`, `index_sa`. `source_as_of` = last day of the latest quarter. Checks: exact header;
≥ 140 Austin rows; consecutive quarters with no gaps; positive indexes; the latest quarter ends
within 9 months of the run date; the two base quarters exist. Add
`layers/fhfa_hpi_index.yaml` with `publish: none`, `refresh: monthly` (as FBI's benchmark manifest
does, so the monthly refresh picks it up). Budget and gate lines; SOURCES entry.

### `config/value_range.yaml`

```yaml
published: false            # P2-08 turns this on after the HMDA check passes
study: "Texas Comptroller, 2024 Property Value Study, category A (single-family), median level"
levels: {"48453": 1.00, "48491": 0.96, "48209": 1.00}
within_10pct: {"48453": 0.7297, "48491": 0.7559, "48209": 0.7363}
base_width: 0.10
wide_width: 0.20
new_years: 2
large_lot_acres: 1.0
size_percentiles: [5, 95]
size_min_group: 20
hood_min_group: 10
```

### `pipeline/mm/values.py`

- `hpi_factor(records, value_date)` → `{factor, base_quarters, base_index, latest_quarter,
  latest_index, as_of}` (fails closed if the base or latest quarter is missing).
- `flags(home, size_bounds)` → list of codes in the fixed order `new, lot, condo, size, type`, or
  `["no_value"]` / `["no_building"]` / `["partial"]` for no range.
- `value_range(market_value, county_fips, range_pct, factor, levels)` → `{low, mid, high}`: the
  **reference implementation** P2-07 ports to TypeScript. Test vectors in
  `pipeline/mm/data/value_range_cases.json` (at least 30 cases: each county, each flag, rounding at
  $500 boundaries, no-range reasons).
- `size_bounds(homes)` → per (county, category, hood_cd) and county-wide fallback, the 5th/95th
  percentiles (nearest-rank), from homes with a living area.
- `hood_stats(homes, factor, levels)` → per county, `hood_cd` and category (`single_family`,
  `condo`, others grouped as `other`) with ≥ 10 homes that have a living area and a range:
  `n`, and the 10th/25th/50th/75th/90th percentiles of `mid / living_area` ($ per sq ft, whole
  dollars). This is the "where the asking price per square foot sits among similar homes" table.

### Changes in `homes.py`

- Two new shard columns at the end of `FIELDS`: `range_pct` (10, 20 or null) and `range_flags`
  (comma-joined codes, or null). Do **not** add low/mid/high columns (the page computes them with
  the reference formula from `market_value` and `meta.json`; this keeps `homes/` under its limit).
- `meta.json` gains `value_range`: `published`, the method text, levels with the study name and
  year, `hpi` (factor, base and latest quarters and index values, FHFA as-of date), widths, flag
  descriptions in plain words, the "year-over-year not available" note, and the county counts of
  homes per `range_pct` and per flag.
- New file `homes/hoods.json`: the `hood_stats` table, with the same `test_data` flag rules.
- Read `partial_owner` from the canonical TCAD record for the `partial` reason (it is not
  published).
- If `fhfa_hpi` has no stored live data, use its fixture and mark `value_range.test_data: true`.
- Keep the 200 MB total limit; report the new total.

## Checks (fail the publish, keep the last build)

- `F` between 0.80 and 1.20 (a bigger move means something is wrong with the file).
- Share of homes with a range ≥ 97% in each county; share with ±20% reported per county and flag.
- Every home's `range_pct` and flags match a recomputation from its own fields.
- `hoods.json` covers ≥ 90% of single-family homes that have a range.
- No published name fails the privacy guard; no demographic field used anywhere in `values.py`
  (add `values.py` inputs to `pipeline/mm/inputs.py` so the existing demographics test covers them).

## Tests

FHFA parsing (header, quotes, gaps, missing base quarter, stale latest quarter); factor
arithmetic on the numbers above (1.0187); every flag and its boundary (`year_built` 2024 vs 2023,
1.0 vs 1.0001 acres, the 5th/95th percentile edges, group-size fallback); no-range reasons;
rounding; value-range vectors; hood stats percentiles on a hand-worked set; `published: false`
carried into `meta.json`; fixture fallback marks test data; demographic-input guard; budget and
gate; determinism.

## Other requirements

`make test` passes; report `mm publish` time and `homes/` size on the real canonical files locally
(the `fhfa_hpi` part from its fixture, labeled test data). STATUS one entry; DECISIONS for
unsettled choices.

## Done when

CI green, `make test` passes. PR lists files, the size and time, and per county: homes with a
range, ±10% vs ±20%, counts per flag, and hood-stats coverage. Claude then runs the first FHFA live
check and compares the factor with the probe.
