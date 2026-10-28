# P3-02 — Neighbourhood calibration of the value range

- **Agent:** Codex. Branch `codex/p3-02-calibration`. Regular (not draft) PR to `main`.
- **Phase:** 3 (approved 2026-10-27). **Depends on:** P2-06, P2-08 (merged). Read `AGENTS.md`, the
  Phase 3 plan, and `docs/tasks/P2-06-value-range.md` and `docs/tasks/P2-08-hmda-check.md` first.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **Budget:** `hmda` stays `{per_day: 6}`; a normal run becomes **2 calls** (the latest year and the
  year before). No new source.
- **Core changes allowed:** `adapters/hmda` (second year), `pipeline/mm/values.py`,
  `pipeline/mm/homes.py` (a calibration file and `meta.json` fields), `web/src/homes/range.ts` and
  the range vectors, the card's "How this is worked out" text, `config/value_range.yaml`, tests.

## Why

Appraisals lag differently by neighbourhood: 2025 buyers paid about 9% more than our centres in
Travis tracts and 3% less in Williamson. A tract-level factor, fitted on one year of HMDA and
tested on another, makes the range more local. Probe 40720982283 (2026-10-28), fitted on 2025 and
tested on 2024 (261 tracts with ≥ 30 loans):

| Method | Median ratio | Within ±10% | Within ±20% | Median abs log error |
|---|---|---|---|---|
| No calibration (today) | 0.960 | 64.4% | 88.1% | 0.077 |
| County factor only | 1.002 | 68.2% | 92.0% | 0.069 |
| Tract factor, shrunk (n₀ = 30) | 1.004 | **80.5%** | 92.7% | **0.049** |

## Method

- HMDA tract aggregates for two years: `fit_year` (latest, 2025) and `test_year` (2024). Same
  filters as P2-08; the adapter fetches both years (keys `purchase_2025`, `purchase_2024`).
- For each tract: `ours_t` = median uncalibrated centre (P2-06 formula) over single-family homes
  with a range; `hmda_t` = HMDA median × FHFA factor for that year (P2-08 method).
- County factor `k_c` = median over tracts with ≥ 30 fit-year loans of `hmda_t / ours_t`.
- Tract factor, for tracts with ≥ 10 fit-year loans and ≥ 30 of our homes:
  `k_t = k_c × (raw_t / k_c)^(n/(n+30))`, `raw_t = hmda_t / ours_t`, `n` = loans; then clamp to
  [0.80, 1.25]. Other tracts and homes without a tract (unplaced Travis condos) use `k_c`.
- Calibrated centre `M' = round(V / L[c] × F × k, -3)`, with `k` = the home's tract or county
  factor; widths and flags unchanged. Add a `cal` flag code when `|k − 1| ≥ 0.10` (shown as
  "Neighbourhood adjustment of +12% from 2025 home-purchase loans").
- Publish `homes/calibration.json`: `{v, fit_year, test_year, county: {fips: k}, tract: {geoid: k}}`
  (about 460 entries) and in `meta.json` the method text, `n0`, clamps, counts of tracts with
  their own factor and the hold-out figures.

## The check (replaces P2-08's switch rule while calibration is on)

- Evaluate on the **test year** only (never the year it was fitted on): tracts with ≥ 30 test-year
  loans and ≥ 30 homes; ratio = calibrated tract median ÷ HMDA test-year median (adjusted).
- Calibration is **used** only if: median ratio 0.90–1.10, ≥ 75% within ±20%, and the share within
  ±10% is not lower than without calibration on the same tracts. Otherwise the publish falls back
  to the uncalibrated range and P2-08's check (report why).
- `meta.json` `value_range.validation` reports both: the hold-out result (with and without
  calibration) and the fit-year result, plainly labelled.
- Expected with today's data: the hold-out figures in the table above (± small differences from
  rounding and the 2026 Q2 base).

## Ports and vectors

`valueRange(marketValue, countyFips, rangePct, factor, levels, k = 1)` in `values.py` and
`range.ts`; vectors gain `k` (keep all existing cases with `k = 1`, add at least 10 with other
`k`, incl. clamps and rounding ties). The card and the batch table read `k` from
`calibration.json` by the home's tract (`block_group[:11]`), else the county factor.

## Tests

Shrinkage arithmetic and clamps on hand-worked numbers; county fallback; tracts below the minimums;
the fit/test split (a test fails if the test-year data ever feed the factors); the use/fallback
rule incl. the "not worse within ±10%" condition; the `cal` flag; calibration file shape;
vectors in both languages; HMDA adapter with two years (fixture shape, both keys, 2 calls).

## Other requirements

`make test` and web e2e pass; report `mm publish` time and the hold-out figures on the real
canonical files with the HMDA fixture (labelled test data). Update the methodology page and
`docs/SOURCES.md` (HMDA years). STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green, tests pass. Claude runs the HMDA live check (2 calls), compares the hold-out figures with
the table above, and spot-checks a few calibrated ranges on the live site.
