# Access values

The adapter makes four budgeted requests: one Geofabrik PBF, one CapMetro GTFS ZIP,
populated 2020 Census block interior points, and 2020 block-group polygons. Development
uses only the small synthetic inputs in `fixtures/`. `make_fixtures.py` regenerates them;
`make_layers.py` regenerates the nine manifests.

Live parsing uses pyosmium. The PBF is streamed to a temporary directory under `data/raw/`
and deleted before fetch returns, including failures. Only bbox nodes, highway refs with
four selected routing tags, destination coordinates and source dates survive compaction.
No statewide graph, street names, OSM contributors or contact tags are retained. The
extract must have nodes before ways; outside-bbox refs split ways without shortcut edges.
PBF failures return a failed response so the core does not download Texas a second time.

Networks are undirected, with great-circle edge lengths, flat speeds of 80 m/min walking
and 16,000/60 m/min biking. Bike eligibility starts with the specified walking base and
adds its bicycle restrictions. Duplicate edges use their shortest length. Snapping uses
EPSG:5070 and a 300 m limit; off-network connector distance is not added. The 800 m transit
radius also measures snapped-node network distance. An unreachable block contributes 61
minutes to destination medians and zero reachable CapMetro departures.

Each destination kind has a bounded multi-source shortest-path search; daily needs is
the largest time among the five required kinds, not an average. Census population weights
produce the lower weighted median: choose the first value reaching half the population,
including at an exact tie. Round only the final whole-minute result (nearest-even); 61
means unavailable with a More than 60 minutes note. Empty-population groups have nulls.
Each measure has its own note, plus the requested overall access note.

Park ways need at least 1,000 m² in EPSG:5070. Their vertex mean and boundary vertices are
destinations. Point-only parks have no measurable area and are excluded. Other mapped
node/way destinations use the tags documented on the layer manifests. OSM relations are
not additional destinations in this nodes/ways contract.

The service date is the first Wednesday on/after the UTC run date within the feed calendar
without a type-2 removal. Type-1 additions supply extra active services. Only departures
from 07:00:00 through 08:59:59 count; 24+ hour times do not. Distinct trip ids are unioned
across accessible stops so multiple stops never double-count a trip. Transit searches
retain one distance vector at a time, with no stops-by-graph matrix. Feed version comes
from `feed_info.txt` when provided; absent versions remain null.

The specified live volume guards are disabled only for fixture mode; shape, calendar,
identifier and 95% walking-snap checks still apply to fixtures. A 25-minute deadline covers
download, parsing and computation. Count-only job notes and a non-spatial canonical audit
record report graph/destination counts, snap share, service date/version, elapsed time and
peak process RSS. The existing live summary tool displays that audit record; the nine map
layers publish only the block-group dataset in one `access_block_group` bundle.

Published access values form an OpenStreetMap-derived database offered under
[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), as approved by the owner.
Credit © OpenStreetMap contributors. CapMetro GTFS retains its CMTA Open Data License and
credit; Census inputs are public domain. Code remains under the repository's MIT license.
