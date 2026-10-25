# P1-12 — Colour the map by comparison

- **Agent:** Codex. Branch `codex/p1-12-colour-by-comparison`. Regular (not draft) PR to `main`.
- **Phase:** 1 follow-up, owner request (2026-10-25), outlined at the end of
  `docs/tasks/P1-11-benchmarks.md`. **Depends on:** P1-11 (merged; its `benchmarks.json`).
- **No network, no new source, no budget change.** Synthetic fixtures only.
- **Core changes allowed:** one optional manifest block (`compare`) in `pipeline/mm/schemas.py`
  plus its validator and generated outputs; the three layer generators; layer YAML files; web
  display code. Nothing else in `pipeline/mm/`.

## What the owner sees

Each map layer that has a fair comparison gets a small switch in the layer panel:
**Colour: Values | Compared with [Texas ▾]**. Choosing "Compared with" recolours the layer in
five classes against the chosen comparison (for example "Lower than Texas", "About the same as
Texas") and swaps the legend to match. The legend header names the comparison value, its period
and source, e.g. "Compared with Texas: 21.6 per 1,000 (2025, Texas DPS)". Values mode is
unchanged and remains the default.

## Rules

1. **Only P1-11 comparisons.** The comparison values come from `benchmarks.json` (same source,
   same method). A geography appears in the dropdown only if `benchmarks.json` has it for that
   layer's source and compare field. No benchmarks → no switch. Never compute a comparison in
   the browser from our own areas.
2. **Better/worse colours only where the direction is clear and the layer is not demographic.**
   Green-to-red colours and "better/worse" words are allowed only for layers with
   `direction: lower_is_better` or `higher_is_better`. Demographic layers (`demographic: true`,
   which includes every ACS and election layer) must use `direction: neutral`: a neutral
   two-hue palette and "lower/higher than" wording only. A schema validator enforces this, and a
   test checks every manifest.
3. **Context only.** No score, rank, sort or filter is derived from the comparison classes.
   Filters and the comparison table are unchanged.
4. **Margins of error.** Where the colour field has a `moe_field` and the area's MOE is a number,
   an area whose MOE range (value ± MOE) contains the benchmark value goes in the middle class,
   labelled "About the same (within margin of error)". MOE null → classify normally.
5. **Missing stays missing.** Null area value, or a benchmark of 0 with method `ratio` → grey
   "Not available", never a class.

## Manifest block (core change)

Optional `compare` on `LayerManifest`:

```yaml
compare:
  field: rate_part1            # feature property that colours the layer in compare mode
  benchmark_field: rate_part1  # key in benchmarks.json (default: field)
  method: ratio                # ratio | difference
  breaks: [0.67, 0.9, 1.1, 1.5]  # four cut points → five classes
  direction: lower_is_better   # lower_is_better | higher_is_better | neutral
  unit: ""                     # optional, shown in legend text for difference ("pts", "years", "pp")
```

- `ratio` = area value ÷ benchmark; `difference` = area value − benchmark (for percent fields,
  differences are in fractions, shown as percentage points).
- Classes: below `breaks[0]`; `breaks[0]`–`breaks[1]`; `breaks[1]`–`breaks[2]` (the middle,
  "about the same"); `breaks[2]`–`breaks[3]`; `breaks[3]` and above. Breaks must be strictly
  increasing, and for `difference` symmetric around 0 (validator).
- Validator: `direction` must be `neutral` when `demographic: true`; `field` must be a field the
  popup already shows; `compare` is not allowed on `publish: none` layers.

## Which layers (set in the YAML or the generator that writes it)

| Layers | field | method | breaks | direction | unit |
|---|---|---|---|---|---|
| `safety_agency_rate` | `rate_part1` | ratio | 0.67, 0.9, 1.1, 1.5 | lower_is_better | |
| `apd_part1_rate`, `apd_violent_rate`, `apd_part1_density` | `rate_part1` / `rate_violent` / `density_part1` | ratio | 0.67, 0.9, 1.1, 1.5 | lower_is_better | |
| `school_campuses` | `overall_score` (benchmark `campus_overall_score`) | difference | −10, −3, 3, 10 | higher_is_better | points |
| `school_district_ratings` | `overall_score` (benchmark `district_overall_score`) | difference | −10, −3, 3, 10 | higher_is_better | points |
| 8 access minute layers (walk/bike × grocery/park/school/basket) | that layer's minutes field | ratio | 0.67, 0.9, 1.1, 1.5 | lower_is_better | |
| `access_transit` | `transit_per_hour` | ratio | 0.67, 0.9, 1.1, 1.5 | higher_is_better | |
| ACS currency medians (income, home value, rent), bg and tract | the median | ratio | 0.67, 0.9, 1.1, 1.5 | neutral | |
| ACS `median_age`, bg and tract | `median_age` | difference | −5, −2, 2, 5 | neutral | years |
| ACS `median_year_built`, bg and tract | `median_year_built` | difference | −15, −5, 5, 15 | neutral | years |
| ACS share layers (all `*_share`), bg and tract | the share | difference | −0.10, −0.03, 0.03, 0.10 | neutral | pp |
| `elections_turnout_2024` | `turnout_2024` | difference | −0.10, −0.03, 0.03, 0.10 | neutral | pp |
| `elections_president_2024` | `pres_2024_margin` | difference | −0.20, −0.05, 0.05, 0.20 | neutral | pts |

No `compare` on: `acs_population_*` (a count; comparing a block group with a state is
meaningless), `flood_share` (no benchmark), boundaries, `school_districts`. ACS share and
median layers set `moe_field` from their existing popup row (rule 4). For the ACS layers, the
compare benchmark field is the layer family's field (e.g. `median_household_income`), the same
key P1-11 used.

## Colours and wording

- Directional (5 classes, colour-blind-safe, best → worst): `#1a9641`, `#a6d96a`, `#f7f7f7`,
  `#fdae61`, `#d7191c`. For `lower_is_better` the lowest class is best; for `higher_is_better`
  the highest is.
- Neutral (lower → higher): `#8c510a`, `#d8b365`, `#f5f5f5`, `#5ab4ac`, `#01665e`.
- Not available: `#bdbdbd`. Fill opacity as in Values mode; for school campus points, colour the
  circle fill and keep the existing radius/stroke rules.
- Legend labels, `<B>` = the benchmark's label, numbers from `breaks` (ratios as "×", differences
  with `unit`):
  - ratio: "Under 0.67× <B>", "0.67–0.9×", "About the same as <B> (0.9–1.1×)", "1.1–1.5×",
    "Over 1.5× <B>".
  - difference: "More than 10 pts below <B>", "3–10 pts below", "About the same as <B>
    (within 3 pts)", "3–10 pts above", "More than 10 pts above <B>".
  - Directional layers append "(better)" or "(worse)" to the two outer classes on each side,
    e.g. "Under 0.67× Texas (better)". Neutral layers never do.
  - Election margin (positive = Republican lead): "Over 20 pts more Democratic than Texas",
    "5–20 pts more Democratic", "About the same as Texas (within 5 pts)", "5–20 pts more
    Republican", "Over 20 pts more Republican than Texas". Neutral palette (not party colours).
  - Plus "About the same (within margin of error)" folded into the middle label as a note when
    rule 4 applies to the layer, and "Not available".
- Legend header: "Compared with <B>: <formatted benchmark value> (<period>, <source>)", with
  "Test data · " in front when `benchmarks.json` is test data.
- The popup's existing "Compared with:" line is unchanged; in compare mode, add the area's class
  label under the colour field's row (e.g. "Higher than Texas (1.1–1.5×)").

## Web

- Build the MapLibre paint expression from `compare` and the chosen benchmark value at runtime
  (`case` for null/0 → grey, MOE rule, then `step` on the ratio or difference). Keep the values
  expression from the manifest untouched for Values mode.
- Dropdown order: the P1-11 popup order (`austin_pd_area`/`austin_city`, `texas`, `us`,
  `peer_cities`/`texas_cities_100k`, then the rest in `benchmarks.json` order). Default = first.
- State: add `colour: Record<layerId, geographyId>` to the view state (explicit allowlist like
  the rest; ids match `^[a-z0-9_]+$`; at most 100 entries) so shared links keep the mode. Unknown
  layer or geography → Values mode. Bump nothing else in the view format.
- Variant layers (block group / tract) share the choice per family.
- Methodology page: extend the "Comparisons" section with how colours are assigned, the MOE rule,
  and that demographic and election layers never get better/worse colours.
- No change to `web/src` that names a layer id (existing test).

## Tests

Schema: `compare` validation (breaks order/symmetry, demographic must be neutral, field in
popup, not on `publish: none`), and a check over every manifest in `layers/`. Generators produce
the table above (regenerate the YAML). Web: paint expression for ratio and difference, null and
zero benchmark → grey, MOE rule puts a straddling area in the middle class, legend labels for
each method and direction (incl. election margin wording and "(better)/(worse)" only on
directional layers), dropdown order and missing geographies hidden, view-state round trip and
rejection of bad ids, no switch when there are no benchmarks, test-data prefix. E2E smoke at
1440×900 and 390×844 switching one directional and one neutral layer.

## Other requirements

`make test` passes; `mm schema` and `cd web && npm run gen:types` outputs committed; STATUS one
entry; DECISIONS for unsettled choices (e.g. any palette or label wording changed).

## Done when

CI green, `make test` passes, local e2e passes at both sizes. PR lists files changed and a
screenshot description of one layer in each mode. Claude then checks on the live site (real
benchmarks) that the classes read correctly for crime (DPS vs Texas), access (vs three-county),
schools (vs Texas), an ACS share and the election margin.
