"""FEMA NFHL coverage and flood shares on 2020 Census block groups."""

from __future__ import annotations

import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from mm import config
from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature
from pyproj import Transformer
from shapely import STRtree, make_valid, transform, union_all
from shapely.errors import GEOSException
from shapely.geometry import mapping, shape

FEMA = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/8/query"
FIELDS = ("FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "DFIRM_ID", "VERSION_ID")
PAGE_SIZE = 1000
PHRASE_02 = "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"
MISSING_COVERAGE = "not available: FEMA map does not fully cover this area"
FEMA_MAP = "https://msc.fema.gov/portal/search"
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(5070, 4326, always_xy=True).transform


def classify(row):
    zone = row["FLD_ZONE"]
    flag = row["SFHA_TF"]
    subtype = row["ZONE_SUBTY"]
    if not isinstance(zone, str) or not zone.strip() or flag not in {"T", "F"}:
        raise ValueError("unexpected FEMA classification fields")
    if subtype is not None and not isinstance(subtype, str):
        raise ValueError("unexpected FEMA zone subtype")
    zone = zone.strip().upper()
    subtype = " ".join((subtype or "").upper().split())
    sfha = flag == "T"
    return {"mapped": zone != "AREA NOT INCLUDED", "sfha": sfha,
            "annual_02": not sfha and zone == "X" and PHRASE_02 in subtype}


def polygon_parts(geom):
    if geom.geom_type == "Polygon":
        return [geom] if not geom.is_empty and geom.area > 0 else []
    return [part for child in getattr(geom, "geoms", ()) for part in polygon_parts(child)]


def wgs84(geom):
    return (not geom.is_empty and all(math.isfinite(v) for v in geom.bounds)
            and -180 <= geom.bounds[0] <= geom.bounds[2] <= 180
            and -90 <= geom.bounds[1] <= geom.bounds[3] <= 90)


def fema_polygon(doc):
    """Repair NFHL geometry and keep all polygonal parts, including nested collections."""
    try:
        geom = shape(doc)
        if not geom.is_valid:
            geom = make_valid(geom)
        parts = polygon_parts(geom)
        if not parts:
            return None
        geom = union_all(parts)
        return geom if geom.is_valid and wgs84(geom) else None
    except (ValueError, TypeError, AttributeError, GEOSException):
        return None


def tiger_polygon(doc):
    try:
        geom = shape(doc)
    except (ValueError, TypeError, AttributeError, GEOSException):
        raise ValueError("block group has no usable TIGER polygon") from None
    if geom.geom_type not in {"Polygon", "MultiPolygon"} or not geom.is_valid or not wgs84(geom) or geom.area <= 0:
        raise ValueError("block group has no usable TIGER polygon")
    return geom


def reproject(geom, operation):
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = operation(xy[:, 0], xy[:, 1])
        return result
    result = transform(geom, coordinates)
    if result.is_empty or not result.is_valid or not math.isfinite(result.area) or result.area <= 0:
        raise ValueError("invalid equal-area polygon")
    return result


def hazard_area_polygon(geom):
    """FEMA polygon in EPSG:5070, repaired; None when nothing with area is left."""
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = TO_AREA(xy[:, 0], xy[:, 1])
        return result
    try:
        result = transform(geom, coordinates)
        if not result.is_valid:
            result = make_valid(result)
        parts = polygon_parts(result)
        if not parts:
            return None
        result = union_all(parts)
    except (ValueError, TypeError, AttributeError, GEOSException):
        return None
    if result.is_empty or not math.isfinite(result.area) or result.area <= 0:
        return None
    return result


def display_geometry(projected):
    doc = mapping(reproject(projected.simplify(5, preserve_topology=True), TO_WGS84))

    def rounded(value):
        return [rounded(v) for v in value] if isinstance(value, (list, tuple)) else round(value, 6)

    return {"type": doc["type"], "coordinates": rounded(doc["coordinates"])}


def more_pages(body):
    flags = [body.get("exceededTransferLimit", False)]
    metadata = body.get("properties")
    if isinstance(metadata, dict):
        flags.append(metadata.get("exceededTransferLimit", False))
    if any(not isinstance(flag, bool) for flag in flags):
        raise ValueError("invalid exceededTransferLimit flag")
    return any(flags)


def bounded_share(geom, denominator):
    return min(1.0, max(0.0, geom.area / denominator))


class FemaNFHL(SourceAdapter):
    id = "fema_nfhl"
    entity = "area_feature"
    cadence = "monthly"

    def plan(self, ctx):
        return [Request("block_groups", {"kind": "tiger", "url": TIGER, "query": {
            "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
            "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}), self.page_request(0)]

    @staticmethod
    def page_request(offset):
        return Request(f"nfhl_{offset}", {"kind": "fema", "url": FEMA, "query": {
            "where": "1=1", "geometry": ",".join(map(str, config.app_config().study_bbox)),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "outFields": ",".join(FIELDS), "outSR": 4326, "f": "geojson", "returnGeometry": "true",
            "maxAllowableOffset": .00005, "orderByFields": "OBJECTID", "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE}})

    def fetch(self, req, ctx):
        request = urllib.request.Request(req.params["url"] + "?" + urllib.parse.urlencode(req.params["query"]),
                                         headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return RawPayload(req, json.load(response), status=response.status,
                                  fetched_at=datetime.now(timezone.utc))
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)

    def features(self, raw):
        if raw.status != 200:
            raise ValueError(f"{raw.request.key}: HTTP {raw.status}")
        body = raw.body
        if (not isinstance(body, dict) or body.get("type") != "FeatureCollection"
                or not isinstance(body.get("features"), list)):
            raise ValueError(f"{raw.request.key}: expected GeoJSON FeatureCollection")
        features = body["features"]
        more = more_pages(body)
        if raw.request.params["kind"] == "tiger":
            if more:
                raise ValueError("TIGER exceededTransferLimit")
            if not features:
                raise ValueError("no TIGER block-group polygons")
        else:
            offset = raw.request.params["query"]["resultOffset"]
            if not features and (more or offset > 0):
                raise ValueError("empty FEMA page while more features were promised")
            if len(features) > PAGE_SIZE:
                raise ValueError("FEMA page exceeds requested record count")
        required = {"GEOID"} if raw.request.params["kind"] == "tiger" else set(FIELDS)
        for feature in features:
            if (not isinstance(feature, dict) or feature.get("type") != "Feature"
                    or not isinstance(feature.get("properties"), dict)
                    or not required <= feature["properties"].keys()):
                raise ValueError(f"{raw.request.key}: missing source fields or malformed feature")
        return features

    def follow_up(self, raw, ctx):
        self.features(raw)  # Validate before spending more of the run's budget.
        if raw.request.params["kind"] == "fema" and more_pages(raw.body):
            return [self.page_request(raw.request.params["query"]["resultOffset"] + PAGE_SIZE)]
        return []

    def normalize(self, raw):
        skipped = 0
        for index, feature in enumerate(self.features(raw)):
            row = feature["properties"]
            if raw.request.params["kind"] == "tiger":
                geoid = row["GEOID"]
                if not isinstance(geoid, str) or not re.fullmatch(r"48(?:453|491|209)\d{7}", geoid):
                    raise ValueError("unexpected block-group GEOID")
                geom = tiger_polygon(feature.get("geometry"))
                yield AreaFeature(dataset="block_group_input", feature_id=geoid,
                                  geometry=mapping(geom), properties={"geoid": geoid})
                continue
            props = classify(row)
            geom = fema_polygon(feature.get("geometry"))
            if geom is None:
                skipped += 1
                continue
            version = row["VERSION_ID"]
            if version is not None and not isinstance(version, str):
                raise ValueError("unexpected FEMA VERSION_ID")
            props["effective_version"] = version.strip() if version else None
            yield AreaFeature(dataset="nfhl_input", feature_id=f"{raw.request.key}_{index}",
                              geometry=mapping(geom), properties=props)
        if skipped:
            print(f"fema_nfhl: {raw.request.key}: skipped {skipped} rows without usable polygon geometry",
                  file=sys.stderr)

    def finalize(self, records):
        boundaries, hazards = {}, []
        skipped = 0
        for record in records:
            if record.dataset != "block_group_input":
                # FEMA slivers can turn invalid or zero-area when projected: repair, or skip
                # and count. Census block groups stay strict.
                geom = hazard_area_polygon(shape(record.geometry))
                if geom is None:
                    skipped += 1
                else:
                    hazards.append((geom, record.properties))
                continue
            geom = reproject(shape(record.geometry), TO_AREA)
            if record.dataset == "block_group_input":
                if record.feature_id in boundaries:
                    raise ValueError("duplicate TIGER block-group polygon")
                boundaries[record.feature_id] = geom
            else:
                hazards.append((geom, record.properties))
        if skipped:
            print(f"fema_nfhl: skipped {skipped} FEMA polygons with no area after projection",
                  file=sys.stderr)
        if not boundaries:
            raise ValueError("no TIGER block-group polygons")
        tree = STRtree([geom for geom, _ in hazards])
        output = []
        for geoid, boundary in sorted(boundaries.items()):
            clipped = {kind: [] for kind in ("mapped", "sfha", "annual_02")}
            versions = set()
            for i in tree.query(boundary, predicate="intersects"):
                geom, props = hazards[i]
                intersection = geom.intersection(boundary)
                if props["effective_version"]:
                    versions.add(props["effective_version"])
                for kind in clipped:
                    if props[kind]:
                        clipped[kind].append(intersection)
            unions = {kind: union_all(parts) for kind, parts in clipped.items()}
            mapped = bounded_share(unions["mapped"], boundary.area)
            covered = mapped >= .99 or math.isclose(mapped, .99, rel_tol=0, abs_tol=1e-9)
            sfha = bounded_share(unions["sfha"], boundary.area) if covered else None
            annual_02 = bounded_share(unions["annual_02"].difference(unions["sfha"]), boundary.area) if covered else None
            output.append(AreaFeature(dataset="block_group", feature_id=geoid,
                geometry=display_geometry(boundary), properties={
                    "geoid": geoid, "flood_share_1pct": round(sfha, 3) if sfha is not None else None,
                    "flood_share_02pct": round(annual_02, 3) if annual_02 is not None else None,
                    "mapped_share": round(mapped, 3), "flood_note": MISSING_COVERAGE if not covered else "FEMA map covers at least 99% of this area.",
                    "effective_versions": ",".join(sorted(versions)), "fema_map_link": FEMA_MAP,
                }))
        return output

    # VERSION_ID is not an effective date. Leave source_as_of unknown; registry uses the
    # successful run date, while the actual publisher version identifiers stay per area.


ADAPTER = FemaNFHL
