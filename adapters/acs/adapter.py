"""ACS estimates and uncertainty, joined exactly to complete Census polygons."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature
from pyproj import Transformer
from shapely import transform
from shapely.geometry import mapping, shape

# The adapter loader loads files by path, so sibling imports cannot rely on sys.path.
_spec = importlib.util.spec_from_file_location("acs_metrics", Path(__file__).with_name("metrics.py"))
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)

API = "https://api.census.gov/data/2024/acs/acs5"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer"
AS_OF = date(2024, 12, 31)
CELL_IDS = {base: str(i) for i, base in enumerate(metrics.BASES)}
EMPTY_GEOMETRY = {"type": "GeometryCollection", "geometries": []}
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(5070, 4326, always_xy=True).transform


def number(value):
    """All negative Census codes, blanks and nonfinite/non-numeric cells are missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def annotation(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


# Census annotation codes (EA/MA columns), in plain words.
# https://www.census.gov/data/developers/data-sets/acs-1year/notes-on-acs-estimate-and-annotation-values.html
ESTIMATE_NOTES = {
    "-": "Census: too few survey responses to estimate",
    "N": "Census: not shown (too few cases)",
    "(X)": "Census: not applicable",
}
MOE_NOTES = {
    "**": "Census: margin of error not computed (too few responses)",
    "***": "Census: no margin of error for an open-ended range",
    "*****": "Census: controlled estimate, no sampling margin of error",
    "N": "Census: margin of error not shown (too few cases)",
    "(X)": "Census: margin of error not applicable",
}
OPEN_ENDED = re.compile(r"^(\d[\d,]*)([+-])$")


def open_ended(text, fmt):
    """'250,000+' -> '$250,000 or more'; '1939-' -> '1939 or earlier'. None if not a range code."""
    match = OPEN_ENDED.fullmatch(text or "")
    if not match:
        return None
    value, sign = match.groups()
    if fmt == "currency":
        return f"${value} or {'more' if sign == '+' else 'less'}"
    if len(value) == 4 and "," not in value:  # a year
        return f"{value} or {'later' if sign == '+' else 'earlier'}"
    return f"{value} or {'more' if sign == '+' else 'less'}"


def plain_note(text, kind):
    """A Census code in plain words; unknown codes are kept as given."""
    table = ESTIMATE_NOTES if kind == "estimate" else MOE_NOTES
    if text in table:
        return table[text]
    if kind == "estimate" and OPEN_ENDED.fullmatch(text):
        return f"Census reports a range: {open_ended(text, None)}"
    return f"Census note: {text}"


def reliability(estimate, moe):
    if estimate is None:
        return "estimate unavailable"
    if moe is None:
        return "reliability unknown"
    return "low reliability" if moe > .3 * estimate else "MOE ≤30% of estimate"


def measure(cells, numerator, denominator=None, fmt=None):
    selected = [cells[CELL_IDS[base]] for base in numerator]
    estimates = [cell["estimate"] for cell in selected]
    moes = [cell["moe"] for cell in selected]
    estimate = sum(estimates) if all(value is not None for value in estimates) else None
    moe = math.sqrt(sum(value ** 2 for value in moes)) if all(value is not None for value in moes) else None
    annotations = []
    display = None
    for role, base in [("Numerator", base) for base in numerator] + ([("Denominator", denominator)] if denominator else []):
        cell = cells[CELL_IDS[base]]
        ea, ma = cell["estimate_annotation"], cell["moe_annotation"]
        if not denominator and ea and cell["estimate"] is not None and open_ended(ea, fmt):
            # A capped median: show the range; its stored number only sets the colour.
            display, ea = open_ended(ea, fmt), None
            ma = None if ma == "***" else ma
        if ea == "-" and ma == "**":
            ma = None  # the estimate note already says why
        for kind, text in (("estimate", ea), ("moe", ma)):
            if text:
                text = plain_note(text, kind)
                text = f"{role}: {text}" if denominator else text
                if text not in annotations:
                    annotations.append(text)
    if denominator:
        total = cells[CELL_IDS[denominator]]
        d, md = total["estimate"], total["moe"]
        if estimate is None or d is None or d == 0:
            estimate, moe = None, None
        else:
            estimate /= d
            if not 0 <= estimate <= 1:
                raise ValueError("ACS share outside 0–1")
            if moe is None or md is None:
                moe = None
            else:
                radicand = moe ** 2 - estimate ** 2 * md ** 2
                if radicand < 0:
                    radicand = moe ** 2 + estimate ** 2 * md ** 2
                moe = math.sqrt(radicand) / d
    return estimate, moe, reliability(estimate, moe), "; ".join(annotations) or None, display


def valid_geoid(value, scale, county=None):
    size = 12 if scale == "block_group" else 11
    if (not isinstance(value, str) or not re.fullmatch(rf"\d{{{size}}}", value)
            or value[:2] != "48" or value[2:5] not in metrics.COUNTIES
            or (county is not None and value[2:5] != county)):
        raise ValueError("unexpected Census geography")
    return value


def display_geometry(doc):
    geom = shape(doc)
    if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid:
        raise ValueError("invalid Census polygon")
    if not all(math.isfinite(v) for v in geom.bounds):
        raise ValueError("nonfinite Census polygon")
    if geom.bounds[0] < -180 or geom.bounds[2] > 180 or geom.bounds[1] < -90 or geom.bounds[3] > 90:
        raise ValueError("Census polygon must use WGS84")

    def project(geom, operation):
        def coordinates(xy):
            result = xy.copy()
            result[:, 0], result[:, 1] = operation(xy[:, 0], xy[:, 1])
            return result
        return transform(geom, coordinates)

    geom = project(project(geom, TO_AREA).simplify(5, preserve_topology=True), TO_WGS84)

    def rounded(value):
        return [rounded(v) for v in value] if isinstance(value, (tuple, list)) else round(value, 6)

    result = mapping(geom)
    return {"type": result["type"], "coordinates": rounded(result["coordinates"])}


class ACS(SourceAdapter):
    id = "acs"
    entity = "area_feature"
    cadence = "yearly (February)"

    def plan(self, ctx):
        requests = []
        for scale, layer in (("block_group", 8), ("tract", 6)):
            requests.append(Request(f"polygons_{scale}", {"kind": "polygons", "scale": scale,
                "url": f"{TIGER}/{layer}/query", "query": {
                    "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                    "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}))
            for county in metrics.COUNTIES:
                for part, bases in metrics.PARTS.items():
                    requests.append(Request(f"{scale}_{county}_{part}", {
                        "kind": "acs", "scale": scale, "county": county, "part": part, "attempt": 0,
                        "url": API, "query": {
                            "get": "group(B01001)" if part == "age" else ",".join(metrics.variables(bases)),
                            "for": "block group:*" if scale == "block_group" else "tract:*",
                            "in": f"state:48 county:{county}" + (" tract:*" if scale == "block_group" else ""),
                        }}))
        return requests

    def fetch(self, req, ctx):
        # Nothing containing a credential leaves this transport boundary. Never echo an
        # exception: urllib messages and Census error pages can include the full URL.
        query = dict(req.params["query"])
        if req.params["kind"] == "acs":
            key = os.environ.get("CENSUS_API_KEY")
            if not key:
                raise RuntimeError("CENSUS_API_KEY is required")
            query["key"] = key
        request = urllib.request.Request(req.params["url"] + "?" + urllib.parse.urlencode(query),
                                         headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                try:
                    body = json.load(response) if status == 200 else None
                except (ValueError, UnicodeError):
                    body = None
        except urllib.error.HTTPError as exc:
            status, body = exc.code, None
        except Exception:
            raise RuntimeError("Census transport failed; URL and response withheld") from None
        return RawPayload(req, body, status=status, fetched_at=datetime.now(timezone.utc))

    def follow_up(self, raw, ctx):
        if 500 <= raw.status < 600 and raw.request.params.get("attempt", 0) == 0:
            # Queue the retry through the runner: its call budget, pacing and run log count it.
            return [Request(raw.request.key, {**raw.request.params, "attempt": 1})]
        if raw.status != 200:
            raise ValueError(f"Census HTTP {raw.status}; response withheld")
        return []

    def normalize(self, raw):
        if 500 <= raw.status < 600 and raw.request.params.get("attempt", 0) == 0:
            return  # An initial 5xx is replaced by the runner's single queued retry.
        if raw.status != 200:
            raise ValueError(f"Census HTTP {raw.status}; response withheld")
        scale = raw.request.params["scale"]
        if raw.request.params["kind"] == "polygons":
            body = raw.body
            if not isinstance(body, dict) or body.get("type") != "FeatureCollection" or not isinstance(body.get("features"), list):
                raise ValueError("expected Census GeoJSON FeatureCollection")
            if body.get("exceededTransferLimit") or (body.get("properties") or {}).get("exceededTransferLimit"):
                raise ValueError("Census polygons exceededTransferLimit")
            for feature in body["features"]:
                if feature.get("type") != "Feature":
                    raise ValueError("expected Census GeoJSON Feature")
                geoid = valid_geoid(feature.get("properties", {}).get("GEOID"), scale)
                yield AreaFeature(dataset="acs_polygons", feature_id=geoid,
                    geometry=display_geometry(feature.get("geometry")), properties={"scale": scale, "geoid": geoid})
            return
        body = raw.body
        if (not isinstance(body, list) or not body or not isinstance(body[0], list)
                or not all(isinstance(field, str) for field in body[0])):
            raise ValueError("expected Census JSON header and rows")
        header = body[0]
        if len(set(header)) != len(header):
            raise ValueError("duplicate Census columns")
        part = raw.request.params["part"]
        bases = metrics.PARTS[part]
        geography = ["state", "county", "tract"] + (["block group"] if scale == "block_group" else [])
        if not set(metrics.variables(bases) + geography) <= set(header):
            raise ValueError("missing Census columns")
        for values in body[1:]:
            if not isinstance(values, list) or len(values) != len(header):
                raise ValueError("malformed Census row")
            row = dict(zip(header, values))
            if (not all(isinstance(row[field], str) for field in geography)
                    or row["state"] != "48" or row["county"] != raw.request.params["county"]
                    or not re.fullmatch(r"\d{6}", row["tract"])
                    or (scale == "block_group" and not re.fullmatch(r"\d", row["block group"]))):
                raise ValueError("invalid Census geography columns")
            geoid = valid_geoid("".join(row[field] for field in geography), scale, raw.request.params["county"])
            cells = {CELL_IDS[base]: {
                "estimate": number(row[base + "E"]), "moe": number(row[base + "M"]),
                "estimate_annotation": annotation(row[base + "EA"]), "moe_annotation": annotation(row[base + "MA"]),
            } for base in bases if base in CELL_IDS}
            yield AreaFeature(dataset="acs_values", feature_id=geoid, geometry=EMPTY_GEOMETRY,
                              properties={"scale": scale, "geoid": geoid, "part": part, "cells": cells})

    def finalize(self, records):
        boundaries = {scale: {} for scale in metrics.SCALES}
        parts = {scale: {part: {} for part in metrics.PARTS} for scale in metrics.SCALES}
        for record in records:
            props = record.properties
            scale, geoid = props["scale"], props["geoid"]
            target = boundaries[scale] if record.dataset == "acs_polygons" else parts[scale][props["part"]]
            if geoid in target:
                raise ValueError("duplicate Census geography within a response part")
            target[geoid] = record
        output = []
        for scale, polygons in boundaries.items():
            if not polygons:
                raise ValueError(f"missing {scale} Census polygons")
            for part, rows in parts[scale].items():
                if rows.keys() != polygons.keys():
                    raise ValueError(f"{scale} {part}: ACS row / polygon mismatch")
            for geoid, polygon in sorted(polygons.items()):
                cells = {}
                for rows in parts[scale].values():
                    cells.update(rows[geoid].properties["cells"])
                props = {"geoid": geoid, "geography": metrics.SCALES[scale], "vintage": metrics.VINTAGE}
                for metric, (_, fmt, numerator, denominator, _) in metrics.METRICS.items():
                    value, moe, flag, note, display = measure(cells, numerator, denominator, fmt)
                    props.update({metric: value, metric + "_moe": moe, metric + "_reliability": flag,
                                  metric + "_annotation": note})
                    if display:
                        props[metric + "_display"] = display  # only capped medians carry it
                output.append(AreaFeature(dataset=scale, feature_id=geoid, geometry=polygon.geometry,
                                          properties=props, source_as_of=AS_OF))
        return output

    def source_as_of(self, raws):
        return AS_OF


ADAPTER = ACS
