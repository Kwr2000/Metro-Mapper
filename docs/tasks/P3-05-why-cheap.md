# P3-05 — "Why might it be cheap?" checklist

- **Agent:** Codex. Branch `codex/p3-05-why-cheap`. Regular (not draft) PR to `main`.
- **Phase:** 3 (approved 2026-10-27). **Depends on:** P2-07, P3-01 (merged). If P3-02 or P3-04 has
  merged first, rebase on it (all three touch `homes.py`).
- **No network.** Synthetic fixtures only. Claude does the live runs.
- **No new source and no budget change.** Two existing adapters keep a little more of what they
  already download: `fema_nfhl` (budget 40/day) and `access` (6/day). Each needs one live re-run
  by Claude after merge, within its budget.
- **Core changes allowed:** those two adapters, `pipeline/mm/homes.py` (one shard column and
  `meta.json` text), the home card and the batch table, tests.

## What the owner sees

On every home card a section **Things to check** — facts that often explain a lower price, each
with its source, never a verdict:

| Code | Shown when | Text (example) |
|---|---|---|
| `flood1` | the home's point is inside a FEMA 1% annual chance flood zone (`SFHA_TF` = T) | "In a FEMA 1% annual chance flood zone (Zone AE). Flood insurance is usually required with a mortgage." |
| `flood02` | inside the 0.2% zone only | "In a FEMA 0.2% annual chance flood zone (moderate risk)." |
| `highway` | within 150 m of an OSM `highway=motorway` or `trunk` (not `_link`) | "About 90 m from a highway (I-35). Traffic noise is likely." |
| `major_road` | within 60 m of `highway=primary` (and not `highway`) | "About 40 m from a major road (S Lamar Blvd)." |
| `rail` | within 150 m of `railway=rail` (not abandoned, disused or a siding/yard `service`) | "About 120 m from a railway line." |
| `pre1978` | `year_built` < 1978 | "Built before 1978: federal lead-based paint disclosure applies." |
| `old_systems` | `year_built` < 1990 (and not `pre1978`) | "Built in 1985: original roof, HVAC or plumbing may be near the end of their life." |
| `small_lot` | `land_acres` below the 10th percentile of homes in the same appraisal neighbourhood and category (groups ≥ 20 with a lot size) | "Lot smaller than about 90% of similar homes in its appraisal neighbourhood." |
| `range_flags` | P2-06 flags | the existing flag wording |

Plus, in the batch table (P3-01), a **Things to check** column with short icons/labels and the
same text on hover/expand, and the existing listing-vs-appraisal sq ft warning. Homes without a
location get only the non-location items, with "Location checks not available (no map point)".

Header text: "Things that often go with a lower price. None of them is a verdict; check the home."

## Data changes

- **`fema_nfhl`:** keep the flood-zone polygons it already fetches: dissolve into two
  `MultiPolygon` records (`dataset="flood_zone"`, `feature_id` `sfha` and `x02`) with the zone
  labels found inside (e.g. `["A","AE","AO"]`), simplified to 2 m in EPSG:5070 then back to WGS84,
  6 decimals. Report the stored size (expect a few MB; fail above 25 MB). Existing block-group
  shares are unchanged. A version note records the NFHL `VERSION_ID`s.
- **`access`:** while parsing OSM, also keep `highway=motorway|trunk|primary` and `railway=rail`
  ways inside the study bbox (excluding `abandoned`, `disused`, `service=siding|yard|spur`,
  `tunnel=yes`) as `dataset="nuisance_line"` records with `kind` (`highway`, `major_road`,
  `rail`), `name`/`ref` (public road names only), and a `LineString`. Report count and size.
- **`homes.py`:** for each placed home, point-in-polygon against the two flood records (spatial
  index) and distance in EPSG:5070 to the nearest line of each kind (spatial index, 200 m search);
  write a shard column `checks` (comma-joined codes, plus distances in metres and the zone, e.g.
  `flood1:AE,highway:90:I 35`) — keep it short; check `homes/` stays under its 300 MB limit and
  report the new size. `small_lot` and age codes are computed for every home.
- `meta.json` gains the texts, thresholds, sources and dates (FEMA retrieval date and versions,
  OSM extract date).

## Rules

- Facts, not judgments: no "bad", "avoid", "deal", "bargain", "undervalued"; banned-words test
  covers the new copy.
- Only property facts and public map features; nothing about people or demographics.
- Missing stays missing: no location → no location checks (stated), unknown year → no age check.
- Distances are approximate (OSM centrelines, parcel interior points): say "about".

## Tests

Flood dissolve and simplification on a tiny synthetic NFHL page (both zones, nested parts,
invalid ring repair); size guard; OSM filter (each excluded tag, links, tunnels, sidings);
point-in-polygon and nearest-distance on hand-made geometries in EPSG:5070; thresholds at the
boundaries (150/60/150 m); `checks` encoding/decoding round trip; age and small-lot rules incl.
group-size fallback (skip below 20); card text for every code; batch column; homes size check.
Both adapters' existing tests keep passing; fixtures extended with native shapes.

## Other requirements

`make test` and web e2e pass; methodology page gets a "Things to check" section. STATUS one entry;
DECISIONS for unsettled choices.

## Done when

CI green, tests pass. Claude re-runs `fema_nfhl` and `access` live (within budget), checks stored
sizes, and spot-checks a dozen homes on the map (a home near I-35, one by a rail line, one in a
mapped flood zone) before closing.
