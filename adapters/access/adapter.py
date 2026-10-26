"""Population-weighted, network-based access; no scores, attendance or live calls in dev."""
from __future__ import annotations

import csv
import gzip
import io
import json
import math
import re
import resource
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
from mm import config
from mm.adapter import RawPayload, Request, SourceAdapter
from mm.paths import paths
from mm.schemas import AreaFeature
from mm.benchmarks import record as benchmark
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely import make_valid
from shapely.geometry import Polygon, shape

OSM = "https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf"
GTFS = "https://data.texas.gov/download/r4v4-vz24/application%2Fzip"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer"
EMPTY = {"type": "GeometryCollection", "geometries": []}
PROJECT = Transformer.from_crs(4326, 5070, always_xy=True).transform
SPEED = {"walk": 80, "bike": 16000 / 60}
EXCLUDED = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed", "raceway", "bus_guideway", "abandoned"}
PERMITTED = {"yes", "designated", "permissive"}
WAY_TAGS = ("highway", "foot", "access", "bicycle")
BASKET = ("pharmacy", "food", "hardware", "bank", "library")
KINDS = ("grocery", "park", "school", *BASKET)
MEASURES = tuple(f"{mode}_{dest}" for mode in SPEED for dest in ("grocery", "park", "school", "basket"))
NO_RESIDENTS = "No residents in 2020"
OVER_60 = "More than 60 minutes"
NO_TRANSIT = "No CapMetro departures 7–9 am within a 10-minute walk"
TRANSIT_SCOPE = "CapMetro only; other transit agencies (e.g. San Marcos, Round Rock, Georgetown) are not included yet"
CSV_FIELDS = {
    "calendar.txt": ("service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"),
    "calendar_dates.txt": ("service_id", "date", "exception_type"),
    "trips.txt": ("route_id", "service_id", "trip_id"),
    "stops.txt": ("stop_id", "stop_lat", "stop_lon"),
    "routes.txt": ("route_id", "route_type"),
    "stop_times.txt": ("trip_id", "stop_id", "departure_time"),
}


def coordinate(lon, lat):
    result = [float(lon), float(lat)]
    if not all(math.isfinite(v) for v in result) or not -180 <= result[0] <= 180 or not -90 <= result[1] <= 90:
        raise ValueError("invalid access coordinate")
    return result


def within(point, bbox):
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError("invalid access count/id")
    return int(value)


def allowed(tags, mode):
    highway = tags.get("highway")
    if not highway or highway in EXCLUDED or tags.get("foot") == "no":
        return False
    if tags.get("access") in {"no", "private"} and tags.get("foot") not in PERMITTED:
        return False
    return mode == "walk" or (highway != "steps" and tags.get("bicycle") != "no" and
        (highway not in {"footway", "pedestrian"} or tags.get("bicycle") in PERMITTED))


def great_circle(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


class Network:
    def __init__(self, osm, mode):
        nodes = osm["nodes"]
        edges = {}
        for way in osm["ways"]:
            if not allowed(way["tags"], mode):
                continue
            for a, b in zip(way["nodes"], way["nodes"][1:]):
                if a == b or a not in nodes or b not in nodes:
                    continue
                key = tuple(sorted((a, b)))
                distance = great_circle(nodes[a], nodes[b])
                if distance > 0:
                    edges[key] = min(edges.get(key, math.inf), distance)
        self.ids = sorted({node for edge in edges for node in edge}, key=int)
        positions = {node: i for i, node in enumerate(self.ids)}
        rows, cols, weights = [], [], []
        for (a, b), weight in edges.items():
            i, j = positions[a], positions[b]
            rows.extend((i, j)); cols.extend((j, i)); weights.extend((weight, weight))
        self.graph = csr_matrix((weights, (rows, cols)), shape=(len(self.ids), len(self.ids)), dtype=float)
        self.points = np.asarray([nodes[node] for node in self.ids], dtype=float).reshape(-1, 2)
        self.tree = cKDTree(np.column_stack(PROJECT(self.points[:, 0], self.points[:, 1]))) if self.ids else None

    def snap(self, points):
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        if not len(points) or self.tree is None:
            return np.full(len(points), -1, dtype=int)
        distances, indices = self.tree.query(np.column_stack(PROJECT(points[:, 0], points[:, 1])))
        return np.where(distances <= 300 + 1e-7, indices, -1).astype(int)

    def nearest(self, destinations, mode):
        sources = np.unique(self.snap(destinations))
        sources = sources[sources >= 0]
        if not len(sources):
            return np.full(len(self.ids), math.inf)
        return dijkstra(self.graph, directed=False, indices=sources, min_only=True, limit=60 * SPEED[mode]) / SPEED[mode]


def weighted_median(values, populations):
    """Lower population median: first cumulative weight at least half the total."""
    if not values or len(values) != len(populations) or any(p <= 0 for p in populations):
        raise ValueError("weighted median needs positive population weights")
    cumulative, total = 0, sum(populations)
    for value, population in sorted(zip(values, populations)):
        cumulative += population
        if 2 * cumulative >= total:
            return value
    raise ValueError("invalid population weights")


def capped_minutes(value):
    return value if math.isfinite(value) and value <= 60 else 61


def destination_kinds(tags):
    kinds = []
    if tags.get("shop") in {"supermarket", "grocery", "greengrocer"}:
        kinds.append("grocery")
    if tags.get("leisure") == "park":
        kinds.append("park")
    if tags.get("amenity") == "school":
        kinds.append("school")
    if tags.get("amenity") == "pharmacy" or tags.get("shop") == "chemist":
        kinds.append("pharmacy")
    if tags.get("amenity") in {"cafe", "restaurant", "fast_food"}:
        kinds.append("food")
    if tags.get("shop") in {"hardware", "doityourself"}:
        kinds.append("hardware")
    for kind in ("bank", "library"):
        if tags.get("amenity") == kind:
            kinds.append(kind)
    return kinds


class OSMCollector:
    """Keep only bbox nodes while streaming Texas; never cache nodes for the whole state.

    OSM PBF's node-before-way order lets ways resolve their local refs without a statewide
    location index. Outside refs split ways, so clipping never creates shortcut edges.
    """
    def __init__(self, bbox, check_time=lambda: None):
        self.bbox, self.nodes, self.ways, self.destinations = bbox, {}, [], []
        self.used = set()
        self.seen_way = False
        self.check_time, self.visited = check_time, 0

    def node(self, node):
        self.visited += 1
        if self.visited % 50000 == 0:
            self.check_time()
        if self.seen_way:
            raise ValueError("OSM extract must put nodes before ways")
        point = coordinate(node.location.lon, node.location.lat)
        if not within(point, self.bbox):
            return
        identity = str(node.id)
        self.nodes[identity] = point
        for kind in destination_kinds(node.tags):
            # A point park has no measurable area for the mandatory 0.1-ha cutoff.
            if kind != "park":
                self.destinations.append({"kind": kind, "lon": point[0], "lat": point[1], "osm_id": f"n{identity}"})
                self.used.add(identity)

    def way(self, way):
        self.seen_way = True
        self.visited += 1
        if self.visited % 2000 == 0:
            self.check_time()
        refs = [str(node.ref) for node in way.nodes]
        tags = {key: way.tags[key] for key in WAY_TAGS if key in way.tags}
        if tags.get("highway"):
            run = []
            for ref in [*refs, None]:
                if ref in self.nodes:
                    run.append(ref)
                else:
                    if len(run) >= 2:
                        self.ways.append({"id": int(way.id), "nodes": run, "tags": tags})
                        self.used.update(run)
                    run = []
        kinds = destination_kinds(way.tags)
        if not kinds or not refs or any(ref not in self.nodes for ref in refs):
            return
        points = [self.nodes[ref] for ref in (refs[:-1] if refs[0] == refs[-1] else refs)]
        centre = np.mean(points, axis=0)
        for kind in kinds:
            if kind == "park":
                if len(points) < 3 or refs[0] != refs[-1]:
                    continue
                x, y = PROJECT(*zip(*points))
                if make_valid(Polygon(zip(x, y))).area < 1000:
                    continue
            identity = f"w{way.id}"
            self.destinations.append({"kind": kind, "lon": float(centre[0]), "lat": float(centre[1]), "osm_id": identity})
            if kind == "park":
                self.destinations.extend({"kind": kind, "lon": p[0], "lat": p[1], "osm_id": identity} for p in points)
            self.used.update(refs)

    def compact(self, as_of):
        return {"nodes": {key: point for key, point in self.nodes.items() if key in self.used},
                "ways": self.ways, "destinations": self.destinations, "osm_as_of": as_of}


def parse_osm(path, bbox, as_of, check_time=lambda: None):
    import osmium  # Live binary parser; tiny compact JSON fixtures require no parser download.
    collector = OSMCollector(bbox, check_time)
    class Handler(osmium.SimpleHandler):
        def node(self, node):
            collector.node(node)
        def way(self, way):
            collector.way(way)
    Handler().apply_file(str(path))
    return collector.compact(as_of)


def csv_rows(text, fields):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not set(fields) <= set(reader.fieldnames):
        raise ValueError("missing native GTFS columns")
    for row in reader:
        yield {field: row[field] for field in fields}


def selected_csv(text, fields):
    out = io.StringIO()
    writer = csv.DictWriter(out, fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(csv_rows(text, fields))
    return out.getvalue()


def read_gtfs_zip(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = set(archive.namelist())
        # GTFS allows a feed to list service days only in calendar_dates.txt (CapMetro does,
        # 2026-10-24): either calendar file may be missing, but not both.
        if not names & {"calendar.txt", "calendar_dates.txt"}:
            raise ValueError("GTFS has neither calendar.txt nor calendar_dates.txt")
        files = {name: selected_csv(archive.read(name).decode("utf-8-sig"), fields)
                 if name in names or name not in OPTIONAL_GTFS else ",".join(fields) + "\n"
                 for name, fields in CSV_FIELDS.items()}
        version = None
        if "feed_info.txt" in archive.namelist():
            rows = list(csv_rows(archive.read("feed_info.txt").decode("utf-8-sig"), ("feed_version",)))
            if rows:
                version = rows[0]["feed_version"] or None
    return {"files": files, "gtfs_feed_version": version}


OPTIONAL_GTFS = {"calendar.txt", "calendar_dates.txt"}


def gtfs_date(text):
    return datetime.strptime(text, "%Y%m%d").date()


def service_day(files, run_date):
    calendar = list(csv_rows(files["calendar.txt"], CSV_FIELDS["calendar.txt"]))
    exceptions = list(csv_rows(files["calendar_dates.txt"], CSV_FIELDS["calendar_dates.txt"]))
    bounds = [gtfs_date(r[key]) for r in calendar for key in ("start_date", "end_date")]
    bounds.extend(gtfs_date(r["date"]) for r in exceptions)
    if not bounds:
        raise ValueError("GTFS has no service calendar")
    if any(r["exception_type"] not in {"1", "2"} for r in exceptions):
        raise ValueError("invalid GTFS calendar exception")
    day = max(run_date, min(bounds))
    day += timedelta(days=(2 - day.weekday()) % 7)
    while day <= max(bounds):
        changes = [r for r in exceptions if gtfs_date(r["date"]) == day]
        if not any(r["exception_type"] == "2" for r in changes):
            services = {r["service_id"] for r in calendar if gtfs_date(r["start_date"]) <= day <= gtfs_date(r["end_date"]) and r["wednesday"] == "1"}
            services.update(r["service_id"] for r in changes if r["exception_type"] == "1")
            if services:
                return day, services
        day += timedelta(days=7)
    raise ValueError("no non-holiday Wednesday remains in GTFS calendar")


def departure_seconds(text):
    if not re.fullmatch(r"\d+:\d{2}:\d{2}", text):
        raise ValueError("invalid GTFS departure time")
    hours, minutes, seconds = map(int, text.split(":"))
    if minutes >= 60 or seconds >= 60:
        raise ValueError("invalid GTFS departure time")
    return hours * 3600 + minutes * 60 + seconds


def unique_rows(rows, key):
    result = {}
    for row in rows:
        identity = row[key]
        if not identity or identity in result:
            raise ValueError("missing or duplicate access identifier")
        result[identity] = row
    return result


def transit_schedule(files, run_date):
    day, services = service_day(files, run_date)
    routes = unique_rows(csv_rows(files["routes.txt"], CSV_FIELDS["routes.txt"]), "route_id")
    trips = unique_rows(csv_rows(files["trips.txt"], CSV_FIELDS["trips.txt"]), "trip_id")
    stops = unique_rows(csv_rows(files["stops.txt"], CSV_FIELDS["stops.txt"]), "stop_id")
    active = {key for key, row in trips.items() if row["service_id"] in services}
    if any(row["route_id"] not in routes for row in trips.values()):
        raise ValueError("GTFS trip has unknown route")
    departures = defaultdict(set)
    for row in csv_rows(files["stop_times.txt"], CSV_FIELDS["stop_times.txt"]):
        if row["trip_id"] not in trips or row["stop_id"] not in stops:
            raise ValueError("GTFS stop time has unknown trip/stop")
        if row["departure_time"] and row["trip_id"] in active and 7 * 3600 <= departure_seconds(row["departure_time"]) < 9 * 3600:
            departures[row["stop_id"]].add(row["trip_id"])
    return day, stops, active, departures


def transit_counts(network, block_nodes, stops, departures, check_time=lambda: None):
    nodes = sorted({int(node) for node in block_nodes if node >= 0})
    seen = {node: set() for node in nodes}
    stop_ids = [key for key in stops if departures.get(key)]
    stop_nodes = network.snap([coordinate(stops[key]["stop_lon"], stops[key]["stop_lat"]) for key in stop_ids])
    grouped = defaultdict(set)
    for key, node in zip(stop_ids, stop_nodes):
        if node >= 0:
            grouped[int(node)].update(departures[key])
    # A single bounded distance vector at a time, never a stops×all-nodes matrix.
    for node, trips in grouped.items():
        check_time()
        distances = dijkstra(network.graph, directed=False, indices=node, limit=800)
        for reached in np.asarray(nodes)[distances[nodes] <= 800]:
            seen[int(reached)].update(trips)
    return [len(seen.get(int(node), ())) for node in block_nodes]


def volume_checks(stats):
    for key, minimum in (("walk_nodes", 100000), ("grocery_in_study", 50), ("stops", 1000), ("active_trips", 1000), ("blocks", 20000)):
        if stats[key] < minimum:
            raise ValueError(f"access: {key} below production minimum {minimum}")


class Access(SourceAdapter):
    id = "access"
    entity = "area_feature"
    cadence = "monthly"

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        self.run_date = ctx.now.astimezone(timezone.utc).date()
        self.started = time.monotonic()
        self.study = config.app_config().study_bbox
        west, south, east, north = self.study
        self.bbox = [west - .05, south - .05, east + .05, north + .05]
        return [Request("osm", {"url": OSM}), Request("gtfs", {"url": GTFS}),
            Request("blocks", {"url": TIGER + "/10/query", "query": {
                "where": "STATE='48' AND COUNTY IN ('453','491','209') AND POP100>0",
                "outFields": "GEOID,POP100,INTPTLAT,INTPTLON", "returnGeometry": "false", "f": "json", "resultRecordCount": 100000}}),
            Request("block_groups", {"url": TIGER + "/8/query", "query": {
                "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                "outSR": 4326, "f": "geojson", "returnGeometry": "true"}})]

    def fetch(self, req, ctx):
        url = req.params["url"]
        if req.params.get("query"):
            url += "?" + urllib.parse.urlencode(req.params["query"])
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"})
        stage = "OSM download"
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                if response.status != 200:
                    return RawPayload(req, None, status=response.status)
                if req.key == "osm":
                    stage = "OSM response metadata"
                    modified = response.headers.get("Last-Modified")
                    if not modified:
                        raise ValueError("OSM response has no Last-Modified date")
                    as_of = parsedate_to_datetime(modified).astimezone(timezone.utc).date().isoformat()
                    paths().raw.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(prefix="access-", dir=paths().raw) as folder:
                        pbf = Path(folder) / "texas.osm.pbf"
                        with pbf.open("wb") as target:
                            stage = "OSM download"
                            stream = gzip.GzipFile(fileobj=response) if response.headers.get("Content-Encoding") == "gzip" else response
                            while chunk := stream.read(1024 * 1024):
                                self.check_time()
                                target.write(chunk)
                        stage = "OSM parse"
                        body = parse_osm(pbf, self.bbox, as_of, self.check_time)
                    # Temporary PBF is gone before returning; compact safe fields only.
                else:
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    body = read_gtfs_zip(body) if req.key == "gtfs" else json.loads(body)
                return RawPayload(req, body, status=response.status)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception as exc:
            if req.key == "osm":
                # Returning a failed response prevents the core's generic retry from
                # downloading Texas twice. Never include source payloads in errors.
                return RawPayload(req, {"error": f"{stage} failed ({type(exc).__name__})"}, status=502)
            raise

    def check_time(self):
        if time.monotonic() - self.started > 25 * 60:
            raise ValueError("access: 25-minute runtime limit exceeded")

    def follow_up(self, raw, ctx):
        if raw.status != 200 or not isinstance(raw.body, dict):
            error = raw.body.get("error") if isinstance(raw.body, dict) else None
            raise ValueError(f"access: {error or 'invalid response'}; HTTP {raw.status}")
        if raw.body.get("exceededTransferLimit") or (raw.body.get("properties") or {}).get("exceededTransferLimit"):
            raise ValueError("access: exceededTransferLimit")
        return []

    def normalize(self, raw):
        if raw.status != 200 or not isinstance(raw.body, dict):
            raise ValueError(f"access: invalid response or HTTP {raw.status}")
        body, key = raw.body, raw.request.key
        if key == "osm":
            if not isinstance(body.get("nodes"), dict) or not isinstance(body.get("ways"), list) or not isinstance(body.get("destinations"), list):
                raise ValueError("missing compact OSM fields")
            as_of = date.fromisoformat(body["osm_as_of"]).isoformat()
            nodes = {str(integer(key)): coordinate(*point) for key, point in body["nodes"].items()}
            if any(not within(point, self.bbox) for point in nodes.values()):
                raise ValueError("OSM node outside expanded bbox")
            ways = []
            for way in body["ways"]:
                refs = [str(integer(ref)) for ref in way["nodes"]]
                if len(refs) < 2 or any(ref not in nodes for ref in refs):
                    raise ValueError("OSM way has missing local nodes")
                tags = {tag: way["tags"][tag] for tag in WAY_TAGS if tag in way["tags"]}
                if not tags.get("highway") or any(not isinstance(value, str) for value in tags.values()):
                    raise ValueError("invalid OSM highway tags")
                ways.append({"id": integer(way["id"]), "nodes": refs, "tags": tags})
            destinations = []
            for row in body["destinations"]:
                point = coordinate(row["lon"], row["lat"])
                if row["kind"] not in KINDS or not re.fullmatch(r"[nw]\d+", str(row["osm_id"])) or not within(point, self.bbox):
                    raise ValueError("invalid compact OSM destination")
                destinations.append({"kind": row["kind"], "lon": point[0], "lat": point[1], "osm_id": row["osm_id"]})
            yield AreaFeature(dataset="osm_input", feature_id="osm", geometry=EMPTY,
                properties={"nodes": nodes, "ways": ways, "destinations": destinations, "osm_as_of": as_of})
            return
        if key == "gtfs":
            files = {name: selected_csv(body["files"][name], fields) for name, fields in CSV_FIELDS.items()}
            version = body.get("gtfs_feed_version")
            if version is not None and not isinstance(version, str):
                raise ValueError("invalid GTFS feed version")
            yield AreaFeature(dataset="gtfs_input", feature_id="gtfs", geometry=EMPTY,
                              properties={"files": files, "gtfs_feed_version": version})
            return
        if body.get("exceededTransferLimit") or (body.get("properties") or {}).get("exceededTransferLimit"):
            raise ValueError("access: exceededTransferLimit")
        if not isinstance(body.get("features"), list) or not body["features"]:
            raise ValueError("missing TIGER access features")
        if key == "blocks" and len(body["features"]) >= 100000:
            raise ValueError("Census blocks may be truncated at request limit")
        if key == "block_groups" and body.get("type") != "FeatureCollection":
            raise ValueError("expected block-group GeoJSON")
        for feature in body["features"]:
            row = feature["attributes" if key == "blocks" else "properties"]
            geoid = row["GEOID"]
            if not isinstance(geoid, str) or not re.fullmatch(r"48(?:453|491|209)\d{" + ("10" if key == "blocks" else "7") + r"}", geoid):
                raise ValueError("invalid access Census geography")
            props, geometry = {"geoid": geoid}, EMPTY
            if key == "blocks":
                population = integer(row["POP100"])
                if population <= 0:
                    raise ValueError("expected populated Census block")
                point = coordinate(row["INTPTLON"], row["INTPTLAT"])
                props.update(population=population, lon=point[0], lat=point[1])
            elif key == "block_groups":
                geometry = feature["geometry"]
                geom = shape(geometry)
                if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid or geom.area <= 0:
                    raise ValueError("invalid access block-group polygon")
                if not all(math.isfinite(x) for x in geom.bounds) or not -180 <= geom.bounds[0] <= geom.bounds[2] <= 180 or not -90 <= geom.bounds[1] <= geom.bounds[3] <= 90:
                    raise ValueError("invalid access block-group coordinates")
            else:
                raise ValueError("unexpected access request key")
            yield AreaFeature(dataset=key + "_input", feature_id=geoid, geometry=geometry, properties=props)

    def finalize(self, records):
        self.check_time()
        groups = {kind: unique_rows([{"id": r.feature_id, "record": r} for r in records if r.dataset == kind + "_input"], "id")
                  for kind in ("osm", "gtfs", "blocks", "block_groups")}
        if len(groups["osm"]) != 1 or len(groups["gtfs"]) != 1 or not groups["blocks"] or not groups["block_groups"]:
            raise ValueError("incomplete access inputs")
        osm = groups["osm"]["osm"]["record"].properties
        gtfs = groups["gtfs"]["gtfs"]["record"].properties
        blocks = [row["record"].properties for row in groups["blocks"].values()]
        if any(block["geoid"][:12] not in groups["block_groups"] for block in blocks):
            raise ValueError("populated block has no study block group")
        day, stops, active, departures = transit_schedule(gtfs["files"], self.run_date)
        networks = {mode: Network(osm, mode) for mode in SPEED}
        stats = {"blocks": len(blocks), "stops": len(stops), "active_trips": len(active)}
        for mode, network in networks.items():
            stats[mode + "_nodes"] = len(network.ids)
            stats[mode + "_edges"] = network.graph.nnz // 2
        for kind in KINDS:
            stats[kind + "_destinations"] = len({r["osm_id"] for r in osm["destinations"] if r["kind"] == kind})
        stats["grocery_in_study"] = len({r["osm_id"] for r in osm["destinations"] if r["kind"] == "grocery" and within((r["lon"], r["lat"]), self.study)})
        if self.live:
            volume_checks(stats)
        points = [[block["lon"], block["lat"]] for block in blocks]
        snapped = {mode: network.snap(points) for mode, network in networks.items()}
        stats["snapped_share"] = float(np.mean(snapped["walk"] >= 0))
        if stats["snapped_share"] < .95:
            raise ValueError("access: fewer than 95% of populated blocks snap to walking graph")
        values = {}
        for mode, network in networks.items():
            distances = {}
            for kind in KINDS:
                self.check_time()
                distances[kind] = network.nearest([[r["lon"], r["lat"]] for r in osm["destinations"] if r["kind"] == kind], mode)
            for dest in ("grocery", "park", "school", "basket"):
                source = np.maximum.reduce([distances[kind] for kind in BASKET]) if dest == "basket" else distances[dest]
                values[f"{mode}_{dest}"] = [capped_minutes(float(source[node])) if node >= 0 else 61 for node in snapped[mode]]
        transit = transit_counts(networks["walk"], snapped["walk"], stops, departures, self.check_time)
        by_group = defaultdict(list)
        for i, block in enumerate(blocks):
            by_group[block["geoid"][:12]].append(i)
        self.as_of = date.fromisoformat(osm["osm_as_of"])
        output = []
        for geoid, row in sorted(groups["block_groups"].items()):
            indices = by_group[geoid]
            populations = [blocks[i]["population"] for i in indices]
            props = {"geoid": geoid, "osm_as_of": osm["osm_as_of"], "gtfs_feed_version": gtfs["gtfs_feed_version"], "service_date": day.isoformat()}
            notes = []
            for measure in MEASURES:
                median = weighted_median([values[measure][i] for i in indices], populations) if indices else None
                note = NO_RESIDENTS if not indices else OVER_60 if median == 61 else None
                props[measure] = round(median) if median is not None and median != 61 else None
                props[measure + "_note"] = note
                if note == OVER_60:
                    notes.append(f"{measure.replace('_', ' ')}: {note}")
            count = weighted_median([transit[i] for i in indices], populations) if indices else None
            props.update(transit_departures_7_9=count, transit_per_hour=round(count / 2, 1) if count is not None else None,
                transit_note="; ".join([*([NO_RESIDENTS] if count is None else [NO_TRANSIT] if count == 0 else []), TRANSIT_SCOPE]),
                access_note=NO_RESIDENTS if not indices else "; ".join(notes) or None)
            output.append(AreaFeature(dataset="block_group", feature_id=geoid, geometry=row["record"].geometry, properties=props, source_as_of=self.as_of))
        self.check_time()
        stats.update(service_date=day.isoformat(), gtfs_feed_version=gtfs["gtfs_feed_version"],
            runtime_seconds=round(time.monotonic() - self.started, 2), peak_memory_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1))
        print("access: run note: " + "; ".join(f"{key}={value}" for key, value in stats.items()), file=sys.stderr)
        output.append(AreaFeature(dataset="run_summary", feature_id=str(self.as_of), geometry=EMPTY, properties=stats, source_as_of=self.as_of))
        populations = [b["population"] for b in blocks]
        for field in MEASURES:
            median = weighted_median(values[field], populations)
            if median != 61:
                output.append(benchmark(field, "three_county", "Three-county typical home", round(median),
                    osm["osm_as_of"], "OpenStreetMap contributors; 2020 Census population",
                    note="Population-weighted median over populated blocks", as_of=self.as_of))
        count = weighted_median(transit, populations)
        output.append(benchmark("transit_per_hour", "three_county", "Three-county typical home", round(count / 2, 1),
            day.isoformat(), "CapMetro GTFS; 2020 Census population", note=TRANSIT_SCOPE, as_of=self.as_of))
        return output

    def source_as_of(self, raws):
        return self.as_of


ADAPTER = Access
