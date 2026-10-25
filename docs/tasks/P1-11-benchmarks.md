# P1-11 — Comparisons: Austin, Texas, US and similar-size cities

- **Agent:** Codex. Branch `codex/p1-11-benchmarks`. Regular (not draft) PR to `main`.
- **Phase:** 1 follow-up, owner request (2026-10-25: "Yes"). **Depends on:** P1-03, P1-05,
  P1-05b, P1-06, P1-07, P1-10.
- **No network.** Synthetic fixtures with native field names only. Claude does the live runs.
- **Core changes allowed** (listed below): a benchmark publisher, two optional manifest/schema
  fields, and web display code. Everything else uses the existing seams.
- **Budgets** (owner approval recorded in `docs/DECISIONS.md` before this task starts):
  - `acs`: `per_day` 30 → **40** (normal run 26 → 30 calls: four comparison requests).
  - `dps_agency`: unchanged (10/day); normal run 5 → 6 calls.
  - New adapter `fbi_national`: `{per_day: 4, min_interval_seconds: 2}`, refresh annual,
    2 calls a run. Needs the Actions secret `FBI_API_KEY`, which the owner creates (agents
    never sign up). Live gate "awaiting Claude's first live check".
- Part 2 (a "colour by comparison" map mode) is task P1-12, outlined at the end; not in this task.

## What the owner sees

Wherever a number has a fair comparison, the popup and the comparison table show it underneath:
"Austin city $93,658 · Texas $78,476 · US $80,734 · Similar-size cities $90,500", each with its
source and date. Nothing is compared across sources that count differently.

## Comparison rules (fair comparisons only)

1. **Same source and same method as the area's own value**, or it isn't shown.
2. **Crime: no peer-city comparisons.** The FBI asks users not to rank or compare places with
   each other, except "a city to its respective state, and that state to a national
   perspective" (FBI Crime Data API page, checked 2026-10-25). So crime compares with Austin,
   Texas and the US only.
3. Medians can't be averaged from block groups, so Austin/Texas/US medians come from the Census
   itself, never from our areas.
4. Comparisons are context: no score, no ranking, no sort. Demographic comparisons are shown
   as plain numbers, with no better/worse wording.

## Benchmark records (core change 1)

Any adapter may emit non-spatial `AreaFeature` records with `dataset="benchmark"`,
`geometry` empty, `feature_id` = `"<field>|<geography id>"`, and properties:
`field`, `geography` (id below), `label` (display name), `value` (number), `moe` (number or
null), `period` (text, e.g. "2020–2024" or "2025"), `source` (short credit), `note` (or null).
Geography ids: `us`, `texas`, `austin_metro`, `austin_city`, `travis`, `williamson`, `hays`,
`peer_cities`, `austin_pd_area`, `texas_cities_100k`, `three_county`.

`publish` (core) writes `web/public/benchmarks.json` from the benchmark records of every
adapter's published data: `{"<adapter id>": {"<field>": [record properties…]}}`, in the
geography order above, with `test_data` true when any record came from fixtures. Benchmark
records never appear in map layers (layers already select by `dataset`). The privacy guard runs
on benchmark property names. `mm publish` copies it like `validation.json`.

## Per source

### ACS (`acs`): 4 extra calls

One request per existing part (`values_0`, `values_1`, `values_2`, `age`) to
`https://api.census.gov/data/2024/acs/acs5` with the same `get` list and, instead of
`for`/`in`, `ucgid=` this comma-separated list (probe run 2026-10-25 returned all of them
except the 2020-vintage metro id, which is not used):

- `0100000US` United States; `0400000US48` Texas; `310M700US12420` Austin–Round Rock–San Marcos
  metro; `1600000US4805000` Austin city; `0500000US48453`, `0500000US48491`, `0500000US48209`.
- Peer cities: the 12 US cities with ACS 2020–2024 population between 700,000 and 1,500,000
  other than Austin (probe 2026-10-25): San Diego `0666000`, San Francisco `0667000`, San Jose
  `0668000`, Denver `0820000`, Jacksonville `1235000`, Indianapolis (balance) `1836003`,
  Charlotte `3712000`, Columbus `3918000`, Dallas `4819000`, Fort Worth `4827000`, San Antonio
  `4865000`, Seattle `5363000` (each prefixed `1600000US`).

Compute every metric with the existing `metrics.py` functions (shares, MOEs, annotations), so a
benchmark matches the map's definition exactly. `peer_cities` = the plain average of the 12
cities' values (MOE null; note "Average of 12 US cities with 700,000–1.5 million people:
<names>"); if any peer value is missing, leave the benchmark out rather than averaging fewer.
Run note warns (does not fail) if a peer's population is outside 700,000–1,500,000.
Benchmarks for all 21 metrics, including demographic ones (shown neutrally).

### Austin PD (`apd`): no extra calls

`austin_pd_area` for `rate_part1`, `rate_violent` (raw totals ÷ total 2020 population of
APD-area block groups with ≥ 100 residents × 1,000) and `density_part1`. Label "Austin PD area
(all areas combined)". These are the only comparisons for APD layers (other sources count
differently).

### DPS agency-wide (`dps_agency`): 1 extra call

- `texas`: report `633` "Crime Rate by Offense" (same URL pattern and user agent as the other
  reports). Sheet 1 header `Offense | <Y−1> | <Y> | % Change`; rows are rates per 100,000,
  including "Murder and Nonnegligent Manslaughter", "Rape", "Robbery", "Aggravated Assault",
  "Burglary/Breaking and Entering", "Larceny", "Motor Vehicle Theft" (2025 checked 2026-10-25:
  4.635, 38.488, 52.378, 242.817, 251.027, 1321.321, 253.214). `rate_part1` = sum of the seven
  ÷ 100 (per 1,000; 2025 ≈ 21.6); `rate_violent` = first four ÷ 100 (≈ 3.4). Fail on missing
  rows or headers.
- `texas_cities_100k`: from report 615 already fetched: Part I and violent totals over the sum
  of populations of all agencies in that report, per 1,000. Label "Texas cities over 100,000
  (combined)". Report 615 includes agencies with letters in their ORI (`TXDPD0000`); accept
  `TX[0-9A-Z]{7}` everywhere.
- `us`: from `fbi_national` (below), same fields.

### FBI national (`fbi_national`, new adapter): 2 calls

Documented FBI Crime Data API (base `https://api.usa.gov/crime/fbi/cde`, key in query
`API_KEY` from env `FBI_API_KEY`; never logged): `summarized/national/V` and
`summarized/national/P` with `from=01-<Y>&to=12-<Y>` (Y as in `dps_agency`). The response has
`offenses.actuals["United States Offenses"]` (monthly counts) and
`populations.participated_population["United States"]` (monthly). Annual rate per 1,000 =
sum of 12 monthly counts ÷ mean participated population × 1,000. Observed via the CDE web app
for 2025 (checked 2026-10-25): violent 1,098,778 reported offenses, about 334 million
participating population (≈ 3.3 per 1,000); property ≈ 15.5 per 1,000. Emit benchmark records
for `dps_agency` fields `rate_violent` (V) and `rate_part1` (V + P, excluding arson if the
property series includes it: check and note), geography `us`, note "Reported offenses (not FBI
estimates); about 97% of the US population covered". If `FBI_API_KEY` is missing, the run fails
with a clear message and nothing is published. Claude probes the documented endpoint once the
owner has added the key; the fixture shape must follow the response above.

### Schools (`schools`): no extra calls

From the statewide TEA rows already fetched: `texas` for campus `overall_score` (mean of rated
campuses statewide) and the share of rated campuses with A or B (field `overall_rating`, value
= share, note "Share of rated Texas campuses rated A or B"); the same two for districts.

### Access (`access`): no extra calls

`three_county` for each of the nine access fields: population-weighted median over all
populated blocks in the three counties (the adapter already has block populations), label
"Three-county typical home".

### Elections (`elections`): no extra calls

`texas` for `pres_2024_dem_share`, `pres_2024_rep_share`, `pres_2024_margin`, `turnout_2024`
and the 2020 equivalents, from statewide totals of the same TLC files (accumulate them while
parsing, before the three-county filter). Shown neutrally.

## Web display (core change 2)

- Load `benchmarks.json` once with the registry. A popup row whose layer source and field have
  benchmarks gets one extra line: "Compared with: Austin city $93,658 · Texas $78,476 · US
  $80,734 · Similar-size cities $90,500", formatted with the field's own format, at most four,
  in this order: `austin_pd_area` or `austin_city`, `texas`, `us`, `peer_cities`/`texas_cities_100k`.
  Hovering or the comparison table shows all, with MOE (±), period and source.
- The comparison table adds a "Compared with" column group under each measure.
- No colours, sorting or ranking from benchmarks in this task. Missing benchmark → no line
  (never "0").
- The methodology page gets a short "Comparisons" section stating rules 1–4.

## Tests

Benchmark record validation and publishing (order, test-data flag, privacy guard, never in
layers); ACS ucgid request shape and metric reuse (a share and a capped median); peer average
and the all-12 rule; APD area rate on hand-worked numbers; DPS 633 parsing (header/row
failures) and the 615 combined rate with lettered ORIs; FBI aggregation from monthly series and
the missing-key failure (no key in logs); schools and access aggregates; elections statewide
totals; web: popup line formatting and order, missing benchmark hidden, compare-table column;
budgets and live gate.

## Other requirements

Budgets and gate as above; `FBI_API_KEY` passed in `live-run.yml` and `refresh.yml` env like
`CENSUS_API_KEY`; SOURCES entries (FBI CDE: public domain U.S. government data; DPS 633);
`make test` passes; STATUS one entry; DECISIONS for unsettled choices.

## Done when

CI green and `make test` passes. PR lists files and Claude's live checks: ACS benchmarks for
US/Texas/Austin match the probe (e.g. median household income US 80,734, Texas 78,476, Austin
city 93,658); DPS Texas Part I ≈ 21.6 per 1,000; FBI US violent ≈ 3.3 per 1,000; schools,
access and elections benchmarks plausible; benchmarks.json has no personal fields.

---

## P1-12 (outline, next) — Colour by comparison

A per-layer switch "Colour: values | compared with <benchmark>". Five classes by ratio to the
chosen benchmark (below 0.67×, 0.67–0.9, 0.9–1.1, 1.1–1.5, above 1.5); signed fields (election
margin) use differences instead. Manifests gain `benchmark_direction: lower_is_better |
higher_is_better | neutral`. Better/worse colours (green to red) only for non-demographic
layers with a clear direction (crime, flood, access minutes, school scores); demographic and
election layers use neutral colours with "lower/higher than" wording. Specified after P1-11's
data is live.

Full spec: `docs/tasks/P1-12-colour-by-comparison.md` (2026-10-25).
