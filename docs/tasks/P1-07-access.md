# P1-07 — Access: walking and biking minutes, transit frequency

- **Agent:** Codex. Branch `codex/p1-07-access`. Regular (not draft) PR to `main`.
- **Phase:** 1, wave 1b. **Depends on:** P1-02 (merged). Read `AGENTS.md` first and follow its
  seams. Don't change `pipeline/mm/` core files or web application code.
- **No network.** Synthetic fixtures only. Claude does the live run.
- **Budget:** `access: {per_day: 6, min_interval_seconds: 5, max_minutes: 25}`, refresh monthly
  (owner approval recorded in `docs/DECISIONS.md` before this task starts). Live gate "awaiting
  Claude's first live check".

## Goal

For each 2020 block group in Travis, Williamson and Hays: typical walking and biking minutes
to the nearest grocery store, park, school and a "daily needs" basket, and how often CapMetro
buses and trains leave nearby on a weekday morning. Context only: no combined score.

## Sources (checked by Claude)

1. **OpenStreetMap**, Geofabrik `https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf`
   (725.6 MB, Last-Modified 2026-10-21; checked 2026-10-22). ODbL 1.0, credit
   "© OpenStreetMap contributors". **One download per run.**
2. **CapMetro GTFS**, `https://data.texas.gov/download/r4v4-vz24/application%2Fzip` (33.3 MB,
   feed 2026-10-07 to 2027-01-09; checked 2026-10-22). CMTA Open Data License: use and
   redistribution allowed; no CMTA trademarks with the data; as-is. Credit "Capital Metro (CMTA)".
3. **2020 census blocks with population** (checked 2026-10-24): TIGERweb Census2020 layer 10
   "Census Blocks", `where=STATE='48' AND COUNTY IN ('453','491','209') AND POP100>0`,
   `outFields=GEOID,POP100,INTPTLAT,INTPTLON`, `returnGeometry=false`, `f=json` — 21,924 blocks,
   max 100,000 per request, so one request; fail on a transfer limit. `INTPTLAT`/`INTPTLON` are
   signed text ("+29.8846580", "-097.9660667").
4. **Block-group polygons**: TIGERweb Census2020 layer 8 as in other adapters (one request).

**4 calls per run.**

## Handling the large download (no core changes)

`fetch()` streams the OSM file to a temporary file under `data/raw/` (gitignored; delete it
before returning), and uses **pyosmium** to return a compact dict that is the same shape as the
fixture:
- `nodes`: id → [lon, lat] for nodes used by kept ways and destinations, inside the study
  bbox (`config/app.yaml` `study_bbox`) expanded by 0.05° (about 5 km);
- `ways`: list of {id, nodes, tags} for `highway=*` ways (only the tags listed below);
- `destinations`: list of {kind, lon, lat, osm_id} (points; for areas use the centroid of the
  way's nodes, and for parks also every boundary node).
The GTFS fetch returns the text of `calendar.txt`, `calendar_dates.txt`, `trips.txt`,
`stops.txt`, `routes.txt` and `stop_times.txt` (only `trip_id,stop_id,departure_time` columns).
Fixtures are tiny synthetic versions of these dicts. Add `osmium` (pyosmium) and `scipy` to the
pipeline dependencies (pin major versions).

## Networks

- **Walk** (4.8 km/h = 80 m/min): any `highway` value except motorway, motorway_link, trunk,
  trunk_link, construction, proposed, raceway, bus_guideway, abandoned; drop ways with `foot=no` or
  `access=private|no` (unless `foot=yes|designated|permissive`).
- **Bike** (16 km/h ≈ 267 m/min, flat; no hills): same base, but exclude steps, and footway/
  pedestrian unless `bicycle=yes|designated|permissive`; drop `bicycle=no`; motorway/trunk
  excluded.
- Undirected graphs; edge length = great-circle distance between consecutive nodes. Build with
  `scipy.sparse`; distances with `scipy.sparse.csgraph.dijkstra(..., indices=<destination
  nodes>, min_only=True, limit=<60 minutes in metres>)`.
- Snap each destination and each block interior point to the nearest graph node with a KD-tree
  (`scipy.spatial.cKDTree` in EPSG:5070 metres); farther than 300 m → not snapped (block counts
  as unreachable; destination ignored).

## Destinations (OSM tags; document them on the layer)

- **Grocery:** `shop=supermarket|grocery|greengrocer`.
- **Park:** `leisure=park` (any boundary node is an entrance; ignore parks under 0.1 ha).
- **School:** `amenity=school` (context only; not attendance; P1-06 has real school data).
- **Daily needs basket:** minutes to the nearest of *each* of pharmacy (`amenity=pharmacy` or
  `shop=chemist`), café or restaurant (`amenity=cafe|restaurant|fast_food`), hardware
  (`shop=hardware|doityourself`), bank (`amenity=bank`), library (`amenity=library`); the basket
  value for a block is the **largest** of the five (time to reach all of them), capped as below.

## Per block group

For each measure and mode: the **population-weighted median** minutes over the block group's
populated blocks (2020 `POP100`), rounded to whole minutes. Over 60 minutes or unreachable
blocks count as 61 in the median; a median of 61 shows as null with note "More than 60 minutes".
A block group with no populated blocks: null, note "No residents in 2020".
Fields: `walk_grocery`, `walk_park`, `walk_school`, `walk_basket`, `bike_grocery`, `bike_park`,
`bike_school`, `bike_basket`, `access_note`, `geoid`, `osm_as_of` (Geofabrik Last-Modified date,
from the response header; fixture: a fixed date).

## Transit frequency

- Representative weekday: the first Wednesday on or after the run date that is inside the feed's
  calendar and not a holiday exception in `calendar_dates.txt` (exception_type 2 removes service);
  build the active service_ids from both files.
- For each stop, count departures between 07:00:00 and 08:59:59 on that day (GTFS times can
  exceed 24:00; only 07–09 counts). Per block, sum the departures (all routes) at stops within
  **800 m network walking distance** (10 minutes), counting each trip once per block (a trip that
  stops at several nearby stops counts once). Per block group: population-weighted median, as
  `transit_departures_7_9` (departures per 2 hours) and `transit_per_hour` = /2, one decimal.
- Zero nearby departures is a real 0 with note "No CapMetro departures 7–9 am within a 10-minute
  walk". Every value notes "CapMetro only; other transit agencies (e.g. San Marcos, Round Rock,
  Georgetown) are not included yet".
- `gtfs_feed_version` and `service_date` properties.

## Layers

Group "Access", `refresh: monthly`, `default_visible: false`, all sharing `data_bundle:
access_block_group`. Attribution "© OpenStreetMap contributors; Capital Metro (CMTA) GTFS;
U.S. Census Bureau". License: "ODbL 1.0 (derived from OpenStreetMap); CMTA Open Data License".
Use the variant seam for mode: one family per destination with keys `walk` and `bike` (labels
"Walk", "Bike"), layer ids `access_<dest>_walk` / `access_<dest>_bike` (8 layers), plus
`access_transit` (1 layer). Single-hue green sequential palette (`#edf8e9`, `#bae4b3`,
`#74c476`, `#31a354`, `#006d2c`) with **darker = shorter** for minutes, and darker = more for
transit; grey for null. Minute breaks 5, 10, 20, 30 (walk) and 3, 5, 10, 15 (bike); transit
breaks 1, 4, 8, 16 departures per hour. Popup: all eight minute values, transit, notes,
OSM date, feed version, service date, GEOID. Description: "Typical minutes from homes in this
area (2020 census blocks, weighted by population) along OpenStreetMap streets and paths. Flat
speeds; no traffic, hills or crossings. OSM coverage of shops and paths varies."

## Checks (fail closed)

- OSM extract has ≥ 100,000 walk-graph nodes and ≥ 50 grocery destinations in the study area;
  GTFS has ≥ 1,000 stops and the chosen service date has ≥ 1,000 trips; ≥ 20,000 blocks.
- ≥ 95% of populated blocks snap to the walk graph.
- Run notes: node and edge counts, destination counts per kind, snapped share, service date,
  feed version, runtime.

## Tests

Hand-built tiny graphs: shortest path picks the right destination; `foot=no`/motorway excluded;
bike excludes steps and unmarked footways; snapping limit; population-weighted median (even/odd
and ties); the 61-minute cap; basket = max of five; service-day selection including a
calendar_dates removal and a >24:00 time; one-count-per-trip rule; budget and live gate.

## Other requirements

- Add `access` to `config/budgets.yaml` and `config/live_gates.yaml` as above; a
  `docs/SOURCES.md` row for TIGER census blocks; a DECISIONS entry recording that published
  access values are a derivative database offered under ODbL 1.0.
- `make test` passes. Update `docs/STATUS.md` (one entry).

## Done when

CI is green and `make test` passes locally. The PR description lists files changed and what
Claude should check in the live run (runtime and memory within the Actions job; node and
destination counts; snapped share; a few known areas' minutes look plausible).
