"""Austin PD aggregate reports on the source's own 2020 block groups."""
from __future__ import annotations

import gzip
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature
from pyproj import Transformer
from shapely import make_valid, transform, union_all
from shapely.geometry import MultiPolygon, mapping, shape

APD = "https://data.austintexas.gov/resource/fdj4-gpfu.json"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer"
CATEGORIES = {"Murder": "violent", "Rape": "violent", "Robbery": "violent",
              "Aggravated Assault": "violent", "Burglary": "property", "Theft": "property", "Auto Theft": "property"}
COUNT_FIELDS = ("violent", "property", "other", "total")
RATE_FIELDS = ("rate_part1", "rate_part1_raw", "rate_violent", "rate_violent_raw", "density_part1")
OUTSIDE = "Not available (outside Austin PD)"
TOO_FEW = "Too few residents for a rate"
EMPTY = {"type": "GeometryCollection", "geometries": []}
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
SQ_METRES_PER_SQ_MILE = 1609.344 ** 2
COUNT_SELECT = "census_block_group,category_description,count(*) AS n"


def period(now: datetime) -> tuple[date, date]:
    """Inclusive start and exclusive end of the last twelve full UTC months."""
    end = now.astimezone(timezone.utc).date().replace(day=1)
    return end.replace(year=end.year - 1), end


def integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("expected a nonnegative integer count/population")
    return int(value)


def polygonal(geom):
    parts = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type in {"Polygon", "MultiPolygon"}]
    flat = [p for g in parts for p in getattr(g, "geoms", [g])]
    return MultiPolygon(flat) if len(flat) > 1 else (flat[0] if flat else geom)


def projected(doc):
    try:
        geom = shape(doc)
        if geom.geom_type in {"Polygon", "MultiPolygon"} and not geom.is_valid:
            # TIGER's Austin city limits are self-intersecting as served (2026-10-23 live run).
            # Repair and keep only the polygonal parts, as the areas and flood adapters do.
            geom = polygonal(make_valid(geom))
        if (geom.geom_type not in {"Polygon", "MultiPolygon"} or not geom.is_valid or geom.is_empty
                or not all(math.isfinite(v) for v in geom.bounds)
                or not -180 <= geom.bounds[0] <= geom.bounds[2] <= 180
                or not -90 <= geom.bounds[1] <= geom.bounds[3] <= 90):
            raise ValueError("invalid TIGER polygon")
        def coordinates(xy):
            result = xy.copy()
            result[:, 0], result[:, 1] = TO_AREA(xy[:, 0], xy[:, 1])
            return result
        result = transform(geom, coordinates)
        if not result.is_valid or not math.isfinite(result.area) or result.area <= 0:
            raise ValueError("invalid equal-area polygon")
        return result
    except (TypeError, AttributeError):
        raise ValueError("missing TIGER polygon") from None


def smooth(counts, populations):
    """Marshall method-of-moments global empirical Bayes, in people per thousand."""
    if not counts:
        return []
    ns = [p / 1000 for p in populations]
    mean = sum(counts) / sum(ns)
    variance = max(0, sum(n * (y / n - mean) ** 2 for y, n in zip(counts, ns)) / sum(ns)
                   - mean / (sum(ns) / len(ns)))
    if variance == 0:
        return [mean] * len(ns)
    return [(variance / (variance + mean / n)) * (y / n)
            + (1 - variance / (variance + mean / n)) * mean for y, n in zip(counts, ns)]


def unique(records):
    result = {}
    for rec in records:
        if rec.feature_id in result:
            raise ValueError("duplicate aggregate/geography row")
        result[rec.feature_id] = rec
    return result


def summary_text(props):
    return "; ".join(f"{key}={value}" for key, value in props.items())


class APDReports(SourceAdapter):
    id = "apd"
    entity = "area_feature"
    cadence = "monthly"

    def plan(self, ctx):
        self.start, self.end = period(ctx.now)
        self.as_of = self.end - timedelta(days=1)
        where = f"rep_date >= '{self.start}T00:00:00' AND rep_date < '{self.end}T00:00:00'"
        return [
            Request("counts", {"url": APD, "query": {"$select": COUNT_SELECT,
                "$group": "census_block_group,category_description", "$where": where, "$limit": 50000}}),
            Request("total", {"url": APD, "query": {"$select": "count(*) AS n", "$where": where}}),
            Request("block_groups", {"url": TIGER + "/8/query", "query": {
                "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID,POP100",
                "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}),
            Request("city", {"url": TIGER + "/26/query", "query": {"where": "GEOID='4805000'",
                "outFields": "GEOID", "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}),
        ]

    def fetch(self, req, ctx):
        # Refuse any accidental widening to individual report fields before a request.
        if req.params["url"] == APD:
            query = req.params["query"]
            expected = COUNT_SELECT if req.key == "counts" else "count(*) AS n"
            allowed = {"$select", "$where", "$group", "$limit"} if req.key == "counts" else {"$select", "$where"}
            if req.key not in {"counts", "total"} or query.keys() != allowed or query.get("$select") != expected or (req.key == "counts" and
                    query.get("$group") != "census_block_group,category_description"):
                raise ValueError("APD requests must be aggregate-only")
        request = urllib.request.Request(req.params["url"] + "?" + urllib.parse.urlencode(req.params["query"]),
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return RawPayload(req, json.loads(body), status=response.status)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)

    def normalize(self, raw):
        if raw.status != 200:
            raise ValueError(f"apd: HTTP {raw.status}")
        key, body = raw.request.key, raw.body
        if key in {"counts", "total"}:
            allowed = {"n", "census_block_group", "category_description"} if key == "counts" else {"n"}
            if (not isinstance(body, list) or len(body) >= 50000
                    or (key == "total" and len(body) != 1)):
                raise ValueError("invalid or truncated APD aggregate response")
            for row in body:
                if not isinstance(row, dict) or "n" not in row or not row.keys() <= allowed:
                    raise ValueError("missing aggregate fields or unexpected non-aggregate columns")
                props = {"count": integer(row["n"])}
                if key == "counts":
                    # Socrata omits null-valued keys; absent group/category means null.
                    code, category = row.get("census_block_group"), row.get("category_description")
                    if code is not None and (not isinstance(code, str) or not re.fullmatch(r"[0-9]{10}", code)):
                        raise ValueError("unexpected APD block-group code")
                    if category is not None and category not in CATEGORIES:
                        raise ValueError("unknown APD category")
                    props.update(geoid="48" + code if code else None, category=CATEGORIES.get(category, "other"))
                    identity = f"{code or 'unlocated'}-{category or 'other'}"
                else:
                    identity = "total"
                yield AreaFeature(dataset=key + "_input", feature_id=identity, geometry=EMPTY, properties=props)
            return
        if (not isinstance(body, dict) or body.get("type") != "FeatureCollection"
                or not isinstance(body.get("features"), list) or not body["features"]):
            raise ValueError("expected TIGER GeoJSON features")
        if body.get("exceededTransferLimit") or (body.get("properties") or {}).get("exceededTransferLimit"):
            raise ValueError("TIGER exceededTransferLimit")
        for feature in body["features"]:
            row = feature.get("properties") if isinstance(feature, dict) else None
            required = {"GEOID", "POP100"} if key == "block_groups" else {"GEOID"}
            if not isinstance(row, dict) or not required <= row.keys() or feature.get("type") != "Feature":
                raise ValueError("missing TIGER fields")
            geoid = row["GEOID"]
            if key == "block_groups":
                if not isinstance(geoid, str) or not re.fullmatch(r"48(?:453|491|209)[0-9]{7}", geoid):
                    raise ValueError("unexpected study block group")
                props = {"population_2020": integer(row["POP100"]), "geoid": geoid}
            elif key == "city" and geoid == "4805000":
                props = {"geoid": geoid}
            else:
                raise ValueError("unexpected TIGER geography")
            projected(feature.get("geometry"))
            yield AreaFeature(dataset=key + "_input", feature_id=geoid,
                              geometry=feature["geometry"], properties=props)

    def follow_up(self, raw, ctx):
        # Validate immediately; no pagination and never a fallback incident query.
        list(self.normalize(raw))
        return []

    def finalize(self, records):
        groups = {key: unique([r for r in records if r.dataset == key + "_input"])
                  for key in ("counts", "total", "block_groups", "city")}
        if len(groups["total"]) != 1 or not groups["block_groups"] or len(groups["city"]) != 1:
            raise ValueError("missing APD totals or geography")
        counts = [r.properties for r in groups["counts"].values()]
        total = groups["total"]["total"].properties["count"]
        if sum(r["count"] for r in counts) != total:
            raise ValueError("APD grouped counts do not equal period total")
        codes = {r["geoid"] for r in counts if r["geoid"] is not None}
        matched = codes & groups["block_groups"].keys()
        if codes and len(matched) / len(codes) < .99:
            raise ValueError("APD 2020 block-group match below 99%")
        by_geoid = {}
        for row in counts:
            by_geoid.setdefault(row["geoid"], Counter())[row["category"]] += row["count"]
        city = union_all([projected(r.geometry) for r in groups["city"].values()])
        output = []
        for geoid, bg in sorted(groups["block_groups"].items()):
            geom = projected(bg.geometry)
            share = min(1, max(0, geom.intersection(city).area / geom.area))
            inside = share >= .5 or math.isclose(share, .5, rel_tol=0, abs_tol=1e-9)
            population = bg.properties["population_2020"]
            area = geom.area / SQ_METRES_PER_SQ_MILE
            props = {**bg.properties, "apd_share": share, "area_sq_mi": area,
                "period": f"{self.start} to {self.as_of}", "as_of": str(self.as_of),
                "safety_note": None if inside else OUTSIDE,
                **dict.fromkeys((*COUNT_FIELDS, *RATE_FIELDS))}
            if inside:
                local = by_geoid.get(geoid, Counter())
                props.update({field: local[field] for field in COUNT_FIELDS[:3]})
                props["total"] = sum(local.values())
                part1 = props["violent"] + props["property"]
                props["density_part1"] = round(part1 / area)
                if population >= 100:
                    props["rate_part1_raw"] = round(part1 / population * 1000, 1)
                    props["rate_violent_raw"] = round(props["violent"] / population * 1000, 1)
                else:
                    props["safety_note"] = TOO_FEW
            output.append(AreaFeature(dataset="block_group", feature_id=geoid, geometry=bg.geometry,
                                      properties=props, source_as_of=self.as_of))
        inside_ids = {r.feature_id for r in output if r.properties["safety_note"] != OUTSIDE}
        eligible = [r for r in output if r.properties["safety_note"] is None]
        populations = [r.properties["population_2020"] for r in eligible]
        for field, count_fields in (("rate_part1", ("violent", "property")), ("rate_violent", ("violent",))):
            ys = [sum(r.properties[f] for f in count_fields) for r in eligible]
            for rec, value in zip(eligible, smooth(ys, populations)):
                rec.properties[field] = round(value, 1)
        summary = {"reports in period": total,
            "without block group": sum(r["count"] for r in counts if r["geoid"] is None),
            "block groups with reports": len(codes),
            "block groups in APD area": sum(r.properties["safety_note"] != OUTSIDE for r in output),
            # For the refresh validation (P1-09): located reports the map does not show.
            "reports in block groups outside APD area": sum(
                r["count"] for r in counts if r["geoid"] is not None and r["geoid"] not in inside_ids),
            "out-of-county codes": sum(g[:5] not in {"48453", "48491", "48209"} for g in codes),
            "unmatched codes": len(codes - matched), "period start": str(self.start), "period end": str(self.as_of)}
        print("apd: run note: " + summary_text(summary), file=sys.stderr)
        # Count-only audit record preserves totals for the live summary without a core hook.
        output.append(AreaFeature(dataset="run_summary", feature_id=str(self.as_of), geometry=EMPTY,
                                  properties=summary, source_as_of=self.as_of))
        return output

    def source_as_of(self, raws):
        return self.as_of


ADAPTER = APDReports
