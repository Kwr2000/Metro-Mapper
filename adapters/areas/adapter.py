"""2020 Census boundaries, named from publisher polygons; synthetic fixtures only in dev."""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

from mm import config
from mm.adapter import RawPayload, Request, RunContext, SourceAdapter
from mm.schemas import AreaFeature
from pyproj import Transformer
import sys

from shapely import STRtree, make_valid, transform, union_all
from shapely.geometry import MultiPolygon, mapping, shape

TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer"
AUSTIN = "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_neighborhood_planning_areas/FeatureServer/0/query"
AUSTIN_SUBDIVISIONS = "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_subdivision_boundaries/FeatureServer/0/query"
HAYS_SUBDIVISIONS = "https://services5.arcgis.com/bVphnK8rPe5MHUSr/arcgis/rest/services/Subdivisions/FeatureServer/4/query"
WCAD = "https://data.wcad.org/resource/em3v-vwsk.geojson"
VINTAGE = date(2020, 1, 1)
PAGE_SIZE = 2000
SQ_METERS_PER_SQ_MILE = 1609.344 ** 2
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(5070, 4326, always_xy=True).transform
FIELDS = {
    "block_group": "GEOID,STATE,COUNTY,TRACT,BLKGRP,AREALAND,AREAWATER",
    "tract": "GEOID,STATE,COUNTY,TRACT,AREALAND,AREAWATER",
    "place": "GEOID,NAME,BASENAME,LSADC",
    "austin": "PLANNING_AREA_NAME",
    "wcad": "name,scode,type,filedate",
    "austin_subdivision": "SUBDIVISION_NAME",
    "hays_subdivision": "SUB_NAME",
}
# Remove only trailing plat qualifiers, including repeated qualifiers in either order.
QUALIFIER = re.compile(
    r"(?:[,;\s-]+)(?:(?:SEC(?:TION)?|PH(?:ASE)?|UNIT)\.?\s+[A-Z0-9-]+"
    r"|AMENDED|REPLAT|REVISED|RESUB)\.?\s*$", re.IGNORECASE
)


def clean_subdivision_name(value: str) -> str:
    value = " ".join(value.split())
    while True:
        cleaned = QUALIFIER.sub("", value).strip(" ,;-")
        if cleaned == value:
            return value.title()
        value = cleaned


PLAT_QUALIFIER = re.compile(
    r"\b(?:SECTION|SEC|PHASE|PH|UNIT|BLOCK|BLK|LOTS|LOT)\.?\s+"
    r"(?:\d[\w-]*|[A-Z](?:-?\d+[A-Z]?)?|[IVX]+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b",
    re.IGNORECASE)


def clean_austin_subdivision_name(value: str) -> str | None:
    value = value.rstrip().removesuffix("*")
    # Truncation can leave a parenthesis open; discard that annotation through the end.
    outside, depth = [], 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
            if depth == 0:
                outside.append(" ")
        elif depth == 0:
            outside.append(char)
    value = "".join(outside).split(",", 1)[0]
    # Drop a plat qualifier only with an identifier after it ("SEC 3", "PH B", "PHASE ONE",
    # "LOTS 42"), so names like "Block House Creek" keep their words.
    value = PLAT_QUALIFIER.sub(" ", value)
    value = re.sub(r"\b(?:AMENDED|REPLAT|REVISED|RESUB\w*|RESUBDIV\w*|FINAL\s+PLAT(?:\s+OF)?|PLAT\s+OF|PRELIMINARY)\b",
                   " ", value, flags=re.IGNORECASE)
    value = " ".join(value.split()).strip(" ;:-").title()
    # Preserve Roman numerals in base names, as in the spec's "Met Center II" example.
    value = re.sub(r"\b(?:Ii|Iii|Iv|Vi|Vii|Viii|Ix|Xi|Xii|Xiii|Xiv|Xv|Xvi|Xvii|Xviii|Xix|Xx)\b",
                   lambda match: match.group().upper(), value)
    return value if len(value) > 1 else None


def exceeded_transfer_limit(body):
    metadata = body.get("properties") or {}
    flags = [body.get("exceededTransferLimit", False)]
    if isinstance(metadata, dict):
        flags.append(metadata.get("exceededTransferLimit", False))
    if any(not isinstance(flag, bool) for flag in flags):
        raise ValueError("invalid exceededTransferLimit flag")
    return any(flags)


def polygon(geometry):
    """Reject missing, non-polygonal and invalid geometry; never silently lose coverage."""
    geom = shape(geometry)
    if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid:
        raise ValueError("expected a valid nonempty Polygon or MultiPolygon")
    if not all(math.isfinite(v) for v in geom.bounds):
        raise ValueError("nonfinite polygon coordinates")
    west, south, east, north = geom.bounds
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise ValueError("expected WGS84 coordinates")
    return geom


SUBDIVISION_SOURCES = {
    "Williamson": ("wcad", "WCAD subdivision"),
    "Travis": ("austin_subdivision", "City of Austin subdivision"),
    "Hays": ("hays_subdivision", "Hays County subdivision"),
}
SUBDIVISION_KINDS = {kind for kind, _ in SUBDIVISION_SOURCES.values()}
NAMING_KINDS = {"austin", "place", *SUBDIVISION_KINDS}


def naming_polygon(geometry):
    """Naming polygons come from city and appraisal-district layers, which often carry small
    self-intersections. Repair them; return None for rows with no usable polygon (counted
    and skipped: a missing name falls through to the next rule, it never invents one)."""
    if not isinstance(geometry, dict) or not geometry.get("coordinates"):
        return None
    try:
        geom = shape(geometry)
    except (ValueError, TypeError, AttributeError):
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    parts = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type in {"Polygon", "MultiPolygon"}]
    polys = [p for g in parts for p in getattr(g, "geoms", [g]) if not p.is_empty]
    if not polys:
        return None
    geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
    if not all(math.isfinite(v) for v in geom.bounds):
        return None
    return geom


def reproject(geom, operation):
    """Shapely 2 coordinate-array transform, compatible with the whole supported range."""
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = operation(xy[:, 0], xy[:, 1])
        return result

    return transform(geom, coordinates)


def display_geometry(projected):
    geom = reproject(projected.simplify(5, preserve_topology=True), TO_WGS84)

    def rounded(value):
        if isinstance(value, (tuple, list)):
            return [rounded(v) for v in value]
        return round(value, 6)

    doc = mapping(geom)
    return {"type": doc["type"], "coordinates": rounded(doc["coordinates"])}


class NameIndex:
    """Index individual naming areas, or union cleaned subdivision name groups."""

    def __init__(self, rows, group_names=False):
        rows = [(name, geom) for name, geom in rows if name]
        if group_names:
            groups = {}
            for name, geom in rows:
                groups.setdefault(name, []).append(geom)
            rows = [(name, union_all(geometries)) for name, geometries in groups.items()]
        rows.sort(key=lambda row: row[0])
        self.names = [name for name, _ in rows]
        self.geometries = [geom for _, geom in rows]
        self.tree = STRtree(self.geometries)

    def largest(self, geom):
        choices = []
        for i in self.tree.query(geom, predicate="intersects"):
            share = min(1.0, geom.intersection(self.geometries[i]).area / geom.area)
            if share > 0:
                choices.append((self.names[i], share))
        return min(choices, key=lambda row: (-row[1], row[0])) if choices else (None, 0.0)


def meets(share, threshold):
    # Projection round trips can move an exact boundary by a few floating-point ulps.
    return share >= threshold or math.isclose(share, threshold, rel_tol=0, abs_tol=1e-9)


class Areas(SourceAdapter):
    id = "areas"
    entity = "area_feature"
    cadence = "yearly (names monthly)"

    def plan(self, ctx: RunContext):
        self.names_as_of = ctx.now.date()
        requests = []
        for kind, layer in (("block_group", 8), ("tract", 6)):
            for county in ("453", "491", "209"):
                requests.append(Request(f"{kind}_{county}", {
                    "kind": kind, "url": f"{TIGER}/{layer}/query", "query": {
                        "where": f"STATE='48' AND COUNTY='{county}'",
                        "outFields": FIELDS[kind], "outSR": 4326,
                        "f": "geojson", "returnGeometry": "true",
                    },
                }))
        for layer in (26, 28):
            requests.append(Request(f"place_{layer}", {
                "kind": "place", "url": f"{TIGER}/{layer}/query", "query": {
                    "where": "1=1", "geometry": ",".join(map(str, config.app_config().study_bbox)),
                    "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects", "outFields": FIELDS["place"],
                    "outSR": 4326, "f": "geojson", "returnGeometry": "true",
                },
            }))
        requests.append(Request("austin", {"kind": "austin", "url": AUSTIN, "query": {
            "where": "1=1", "outFields": FIELDS["austin"], "outSR": 4326,
            "f": "geojson", "returnGeometry": "true",
        }}))
        requests.append(self.austin_subdivision_request(0))
        requests.append(Request("hays_subdivisions", {"kind": "hays_subdivision", "url": HAYS_SUBDIVISIONS,
            "query": {"where": "1=1", "outFields": FIELDS["hays_subdivision"], "outSR": 4326,
                      "f": "geojson", "returnGeometry": "true", "resultRecordCount": PAGE_SIZE}}))
        requests.append(self.wcad_request(0))
        return requests

    @staticmethod
    def austin_subdivision_request(offset):
        return Request(f"austin_subdivisions_{offset}", {"kind": "austin_subdivision", "url": AUSTIN_SUBDIVISIONS,
            "query": {"where": "1=1", "outFields": FIELDS["austin_subdivision"], "outSR": 4326,
                      "f": "geojson", "returnGeometry": "true", "orderByFields": "OBJECTID",
                      "resultOffset": offset, "resultRecordCount": PAGE_SIZE}})

    @staticmethod
    def wcad_request(offset):
        return Request(f"wcad_{offset}", {"kind": "wcad", "url": WCAD, "query": {
            "$select": "name,scode,type,filedate,geometry", "$order": "scode",
            "$limit": PAGE_SIZE, "$offset": offset,
        }})

    def fetch(self, req, ctx):
        url = req.params["url"] + "?" + urllib.parse.urlencode(req.params["query"])
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent,
                                                      "Accept": "application/geo+json, application/json"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return RawPayload(req, json.load(response), status=response.status,
                                  fetched_at=datetime.now(timezone.utc))
        except urllib.error.HTTPError as exc:
            # Return HTTP failures to validation, so the entire run fails closed.
            return RawPayload(req, None, status=exc.code)

    def features(self, raw):
        body = raw.body
        if raw.status != 200:
            raise ValueError(f"{raw.request.key}: HTTP {raw.status}")
        if not isinstance(body, dict) or body.get("type") != "FeatureCollection":
            raise ValueError(f"{raw.request.key}: expected GeoJSON FeatureCollection")
        kind = raw.request.params["kind"]
        more = exceeded_transfer_limit(body)
        if more and kind != "austin_subdivision":
            raise ValueError(f"{raw.request.key}: exceededTransferLimit")
        features = body.get("features")
        if not isinstance(features, list):
            raise ValueError("expected GeoJSON features list")
        if kind == "austin_subdivision":
            offset = raw.request.params.get("query", {}).get("resultOffset", 0)
            if not features and (more or offset > 0):
                raise ValueError("empty Austin subdivision page while more features were promised")
            if len(features) > PAGE_SIZE:
                raise ValueError("Austin subdivision page exceeds requested limit")
        expected = set(FIELDS[kind].split(","))
        for feature in features:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError("expected GeoJSON Feature")
            props = feature.get("properties")
            # Every requested field must be present. Extra fields some services add (e.g. an
            # object id) are ignored: normalize() copies only the named fields, so nothing
            # else can reach a published file.
            if not isinstance(props, dict) or not expected <= set(props):
                raise ValueError(f"{raw.request.key}: missing fields; expected {sorted(expected)}")
            if kind not in NAMING_KINDS:
                polygon(feature.get("geometry"))  # Census boundaries stay strict
        return features

    def follow_up(self, raw, ctx):
        features = self.features(raw)
        if raw.request.params["kind"] == "austin_subdivision" and exceeded_transfer_limit(raw.body):
            return [self.austin_subdivision_request(raw.request.params["query"]["resultOffset"] + PAGE_SIZE)]
        if raw.request.params["kind"] == "wcad":
            if len(features) > PAGE_SIZE:
                raise ValueError("WCAD page exceeds requested limit")
            if len(features) == PAGE_SIZE:
                return [self.wcad_request(raw.request.params["query"]["$offset"] + PAGE_SIZE)]
        return []

    def normalize(self, raw):
        kind = raw.request.params["kind"]
        skipped = skipped_names = 0
        for index, feature in enumerate(self.features(raw)):
            row = feature["properties"]
            geometry = feature["geometry"]
            if kind in NAMING_KINDS:
                geom = naming_polygon(geometry)
                if geom is None:
                    skipped += 1
                    continue
                geometry = mapping(geom)
            props = {"kind": kind}
            if kind in {"block_group", "tract"}:
                geoid = row["GEOID"]
                county = row["STATE"] + row["COUNTY"]
                tract = row["TRACT"]
                suffix = row["BLKGRP"] if kind == "block_group" else ""
                if (county not in config.app_config().counties or not isinstance(geoid, str)
                        or not re.fullmatch(r"\d{6}", tract)
                        or (kind == "block_group" and not re.fullmatch(r"\d", suffix))
                        or geoid != county + tract + suffix):
                    raise ValueError("unexpected Census identifier")
                props.update(geoid=geoid, county=config.app_config().counties[county],
                             tract=tract, block_group=suffix)
            else:
                name = row[{"place": "BASENAME", "austin": "PLANNING_AREA_NAME", "wcad": "name",
                            "austin_subdivision": "SUBDIVISION_NAME", "hays_subdivision": "SUB_NAME"}[kind]]
                if name is not None and not isinstance(name, str):
                    raise ValueError("expected text name")
                if kind == "austin_subdivision":
                    name = clean_austin_subdivision_name(name) if name else None
                    if name is None:
                        skipped_names += 1
                        continue
                elif kind in SUBDIVISION_KINDS and name:
                    name = clean_subdivision_name(name)
                props["name"] = name
            yield AreaFeature(dataset="area_input", feature_id=f"{raw.request.key}_{index}",
                              geometry=geometry, properties=props)
        if skipped:
            print(f"areas: {raw.request.key}: skipped {skipped} naming rows without a usable polygon",
                  file=sys.stderr)

        if skipped_names:
            print(f"areas: {raw.request.key}: skipped {skipped_names} rows without a usable subdivision name",
                  file=sys.stderr)

    def finalize(self, records):
        names = {kind: [] for kind in NAMING_KINDS}
        boundaries = []
        for record in records:
            props = record.properties
            geom = reproject(polygon(record.geometry), TO_AREA)
            if geom.is_empty or not geom.is_valid or not math.isfinite(geom.area) or geom.area <= 0:
                raise ValueError("invalid equal-area polygon")
            if props["kind"] in names:
                names[props["kind"]].append((props["name"], geom))
            else:
                boundaries.append((record, geom))
        indexes = {kind: NameIndex(rows, group_names=kind in SUBDIVISION_KINDS) for kind, rows in names.items()}
        output = []
        seen = set()
        names_as_of = getattr(self, "names_as_of", datetime.now(timezone.utc).date())
        for record, geom in boundaries:
            row = record.properties
            kind = row["kind"]
            identity = (kind, row["geoid"])
            if identity in seen:
                raise ValueError(f"duplicate boundary {identity}")
            seen.add(identity)
            props = {key: row[key] for key in ("geoid", "county")}
            props["area_sq_mi"] = round(geom.area / SQ_METERS_PER_SQ_MILE, 3)
            if kind == "block_group":
                name, share = indexes["austin"].largest(geom)
                source = "City of Austin neighborhood planning area"
                if not meets(share, .5):
                    subdivision, source = SUBDIVISION_SOURCES[row["county"]]
                    name, share = indexes[subdivision].largest(geom)
                    if not meets(share, .4):
                        name, share = indexes["place"].largest(geom)
                        source = "Census place"
                        if name and not meets(share, .5):
                            name = "Near " + name
                if not name:
                    name = f"{row['county']} County area {row['tract']}.{row['block_group']}"
                    source, share = "Census block group", None
                props.update(tract=row["tract"], name=name, name_source=source,
                             name_share=round(share, 3) if share is not None else None,
                             boundary_note=f"2020 Census boundaries; names as of {names_as_of.isoformat()}")
            output.append(AreaFeature(dataset=kind, feature_id=row["geoid"],
                                      geometry=display_geometry(geom), properties=props,
                                      source_as_of=VINTAGE))
        return sorted(output, key=lambda rec: (rec.dataset, rec.feature_id))

    def source_as_of(self, raws):
        return VINTAGE


ADAPTER = Areas
