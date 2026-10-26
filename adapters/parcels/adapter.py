"""StratMap parcel IDs and interior points, stripped before leaving temporary storage."""
from __future__ import annotations

import json
import math
import resource
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import shapefile
from mm.adapter import RawPayload, Request, SourceAdapter
from mm.paths import paths
from mm.schemas import AreaFeature
from pyproj import CRS, Transformer
from shapely import STRtree, make_valid, transform, union_all
from shapely.geometry import MultiPolygon, Point, shape

COUNTIES = {"48453": "Travis", "48491": "Williamson", "48209": "Hays"}
EXPECTED = {"48453": 386240, "48491": 286776, "48209": 120445}
# GIS_AREA/GIS_AREA_U are deliberately not read: the source acreage is unusable (owner decision 2026-10-26).
FIELDS = ("PROP_ID", "GEO_ID", "FIPS", "DATE_ACQ", "TAX_YEAR")
COUNTERS = ("records_read", "blank_ids", "zero_ids", "repeated_ids_merged", "repeated_records_merged", "geo_id_conflicts")
S3 = "https://tnris-data-warehouse.s3.us-east-1.amazonaws.com/LCD/collection/stratmap-2026-land-parcels/items/shp/stratmap-2026-land-parcels_{}_shp.zip"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/8/query"
EMPTY = {"type": "GeometryCollection", "geometries": []}
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(5070, 4326, always_xy=True).transform


def integer(value):
    if isinstance(value, bool):
        raise ValueError("invalid nonnegative integer")
    if isinstance(value, float) and math.isfinite(value) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, (str, int)) and str(value).isdigit():
        return int(value)
    raise ValueError("invalid nonnegative integer")


def iso_date(value):
    try:
        return value.isoformat() if type(value) is date else date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        raise ValueError("missing or invalid acquisition date") from None


def text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("expected a text parcel identifier")
    return value.strip()


def reproject(geom, operation):
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = operation(xy[:, 0], xy[:, 1])
        return result
    return transform(geom, coordinates)


def polygon(doc, repair=False):
    geom = shape(doc)
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("expected parcel/block-group polygon")
    if repair and not geom.is_valid:
        def parts(g):
            if g.geom_type == "Polygon":
                return [g]
            return [p for child in getattr(g, "geoms", []) for p in parts(child)]
        geom = MultiPolygon(parts(make_valid(geom)))
    if (geom.is_empty or not geom.is_valid or not all(math.isfinite(v) for v in geom.bounds)
            or not -180 <= geom.bounds[0] <= geom.bounds[2] <= 180
            or not -90 <= geom.bounds[1] <= geom.bounds[3] <= 90):
        raise ValueError("invalid parcel/block-group polygon")
    return geom


def components(archive, folder, fips, check_time):
    stem = f"stratmap-2026-land-parcels-{COUNTIES[fips].lower()}_{fips}"
    result = {}
    with ZipFile(archive) as z:
        for suffix in ("shp", "shx", "dbf", "prj"):
            name = stem + "." + suffix
            matches = [i for i in z.infolist() if Path(i.filename).name.casefold() == name.casefold()]
            if len(matches) != 1:
                raise ValueError("missing or duplicate parcel shapefile component")
            target = Path(folder) / ("parcels." + suffix)
            with z.open(matches[0]) as source, target.open("wb") as dest:
                while chunk := source.read(1024 * 1024):
                    check_time()
                    dest.write(chunk)
            result[suffix] = target
    return result


def parse_parcels(archive, folder, fips, check_time=lambda: None):
    files = components(archive, folder, fips, check_time)
    try:
        crs = CRS.from_wkt(files["prj"].read_text())
        if not crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError()
    except Exception:
        raise ValueError("parcel projection must be WGS84") from None
    counts = dict.fromkeys(COUNTERS, 0)
    states, dates, years = {}, set(), set()
    with shapefile.Reader(shp=str(files["shp"]), shx=str(files["shx"]), dbf=str(files["dbf"])) as reader:
        if not set(FIELDS) <= {f[0] for f in reader.fields[1:]}:
            raise ValueError("missing required parcel DBF field")
        # Only the selected fields are unpacked/decoded; other DBF columns are padding.
        # First scan attributes; then read geometry one property at a time, never statewide.
        for row in reader.iterRecords(fields=list(FIELDS)):
            if counts["records_read"] % 1000 == 0:
                check_time()
            props = row.as_dict()
            counts["records_read"] += 1
            if integer(props["FIPS"]) != int(fips):
                raise ValueError("parcel FIPS does not match requested county")
            dates.add(iso_date(props["DATE_ACQ"]))
            year = text(props["TAX_YEAR"])
            if len(year) != 4 or not year.isdigit():
                raise ValueError("missing or invalid parcel tax year")
            years.add(year)
            if len(years) != 1:
                raise ValueError("mixed parcel TAX_YEAR in county")
            if len(dates) != 1:
                raise ValueError("mixed parcel DATE_ACQ in county")
            identity, geo = text(props["PROP_ID"]), text(props["GEO_ID"])
            if not identity or identity == "0":
                counts["blank_ids" if not identity else "zero_ids"] += 1
                continue
            if identity not in states:
                states[identity] = [geo, row.oid, False]
                continue
            state = states[identity]
            if not isinstance(state[1], list):
                state[1] = [state[1]]
                counts["repeated_ids_merged"] += 1
            state[1].append(row.oid)
            counts["repeated_records_merged"] += 1
            if geo:
                if not state[0]:
                    state[0] = geo
                elif state[0] != geo and not state[2]:
                    state[2] = True
                    counts["geo_id_conflicts"] += 1
        if not states or not dates or not years:
            raise ValueError("empty parcel county")
        parcels = []
        for index, (identity, (geo, indices, conflict)) in enumerate(sorted(states.items())):
            if index % 1000 == 0:
                check_time()
            indices = indices if isinstance(indices, list) else [indices]
            polygons = []
            for oid in indices:
                geom = reproject(polygon(reader.shape(oid).__geo_interface__, repair=True), TO_AREA)
                if not geom.is_valid or not math.isfinite(geom.area) or geom.area <= 0:
                    raise ValueError("invalid projected parcel polygon")
                polygons.append(geom)
            geom = polygons[0] if len(polygons) == 1 else union_all(polygons)
            point = reproject(geom.representative_point(), TO_WGS84)
            lon, lat = round(point.x, 6), round(point.y, 6)
            if not math.isfinite(lon) or not math.isfinite(lat):
                raise ValueError("invalid parcel interior point")
            parcels.append([identity, geo or None, lon, lat])
    return {"parcels": parcels, "skipped": counts, "date_acq": next(iter(dates)), "tax_year": next(iter(years))}


def count_checks(counts):
    for fips, expected in EXPECTED.items():
        if abs(counts.get(fips, 0) - expected) > expected * .02:
            raise ValueError("parcel kept IDs outside 2% of expected county count")


class Parcels(SourceAdapter):
    id = "parcels"
    entity = "area_feature"
    cadence = "annual"

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        self.started = time.monotonic()
        self.as_of = None
        return [Request("stratmap_" + fips, {"fips": fips, "url": S3.format(fips)}) for fips in COUNTIES] + [
            Request("block_groups", {"url": TIGER, "query": {
                "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                "outSR": 4326, "f": "geojson", "returnGeometry": "true"}})]

    def check_time(self):
        if time.monotonic() - self.started >= 30 * 60:
            raise ValueError("parcels: 30-minute runtime limit exceeded")

    def fetch(self, req, ctx):
        url = req.params["url"]
        if req.key == "block_groups":
            url += "?" + urllib.parse.urlencode(req.params["query"])
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": self.user_agent}), timeout=90) as response:
                    return RawPayload(req, json.load(response) if response.status == 200 else None, status=response.status)
            except urllib.error.HTTPError as exc:
                return RawPayload(req, None, status=exc.code)
        if req.key != "stratmap_" + req.params.get("fips", "") or req.params.get("fips") not in COUNTIES:
            raise ValueError("unexpected parcel request")
        try:
            paths().raw.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="parcels-", dir=paths().raw) as folder:
                archive = Path(folder) / "download.zip"
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(request, timeout=180) as response:
                    if response.status != 200:
                        return RawPayload(req, None, status=response.status)
                    size = 0
                    with archive.open("wb") as target:
                        while chunk := response.read(1024 * 1024):
                            self.check_time()
                            target.write(chunk)
                            size += len(chunk)
                    length = response.headers.get("Content-Length")
                    if length is not None and size != int(length):
                        raise ValueError("incomplete parcel download")
                body = parse_parcels(archive, folder, req.params["fips"], self.check_time)
            return RawPayload(req, body)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception as exc:
            # A failed payload prevents a second large download by the core retry hook.
            # Never copy source text, identifiers or paths into public errors.
            return RawPayload(req, {"error": f"parcel download/parse failed ({type(exc).__name__})"}, status=502)

    def follow_up(self, raw, ctx):
        if raw.status != 200:
            raise ValueError(f"parcels: HTTP {raw.status}; source response withheld")
        return []

    def normalize(self, raw):
        if raw.status != 200:
            raise ValueError(f"parcels: HTTP {raw.status}; source response withheld")
        body = raw.body
        if raw.request.key == "block_groups":
            if (not isinstance(body, dict) or body.get("type") != "FeatureCollection" or
                    not isinstance(body.get("features"), list) or not body["features"] or
                    body.get("exceededTransferLimit") or (body.get("properties") or {}).get("exceededTransferLimit")):
                raise ValueError("invalid or truncated parcel block groups")
            for feature in body["features"]:
                geoid = feature.get("properties", {}).get("GEOID")
                if (feature.get("type") != "Feature" or not isinstance(geoid, str) or len(geoid) != 12 or
                        not geoid.isdigit() or geoid[:5] not in COUNTIES):
                    raise ValueError("invalid parcel block-group GEOID")
                polygon(feature["geometry"])
                yield AreaFeature(dataset="block_group_input", feature_id=geoid, geometry=feature["geometry"], properties={})
            return
        fips = raw.request.params["fips"]
        if fips not in COUNTIES or not isinstance(body, dict) or set(body) != {"parcels", "skipped", "date_acq", "tax_year"}:
            raise ValueError("invalid compact parcel response")
        acquired = iso_date(body["date_acq"])
        if not isinstance(body["tax_year"], str) or len(body["tax_year"]) != 4 or not body["tax_year"].isdigit():
            raise ValueError("invalid compact parcel tax year")
        if not isinstance(body["skipped"], dict) or set(body["skipped"]) != set(COUNTERS):
            raise ValueError("invalid compact parcel counts")
        stats = {k: integer(v) for k, v in body["skipped"].items()}
        if not isinstance(body["parcels"], list) or not body["parcels"]:
            raise ValueError("missing compact parcel points")
        stats["ids_kept"] = len(body["parcels"])
        if stats["records_read"] != stats["ids_kept"] + stats["blank_ids"] + stats["zero_ids"] + stats["repeated_records_merged"]:
            raise ValueError("parcel read/skip/merge counts do not reconcile")
        for row in body["parcels"]:
            if not isinstance(row, list) or len(row) != 4:
                raise ValueError("invalid compact parcel row")
            identity, geo, lon, lat = row
            if not isinstance(identity, str) or identity != text(identity) or identity in {"", "0"}:
                raise ValueError("invalid compact property ID")
            if geo is not None and (not isinstance(geo, str) or not geo or geo != text(geo)):
                raise ValueError("invalid compact geographic ID")
            if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lon, lat)) or
                    not -180 <= lon <= 180 or not -90 <= lat <= 90):
                raise ValueError("invalid compact parcel coordinates")
            yield AreaFeature(dataset="parcel", feature_id=f"{fips}:{identity}", geometry={"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                properties={"county": COUNTIES[fips], "prop_id": identity, "geo_id": geo,
                            "block_group": None, "tract": None, "parcel_as_of": acquired})
        yield AreaFeature(dataset="parcel_input_summary", feature_id=fips, geometry=EMPTY,
            properties={**stats, "date_acq": acquired, "tax_year": body["tax_year"]})

    def finalize(self, records):
        groups, parcels, summaries = {}, {}, {}
        for rec in records:
            target = groups if rec.dataset == "block_group_input" else parcels if rec.dataset == "parcel" else summaries if rec.dataset == "parcel_input_summary" else None
            if target is None or rec.feature_id in target:
                raise ValueError("unexpected or duplicate parcel/block-group input")
            target[rec.feature_id] = rec
        if not groups or summaries.keys() != COUNTIES.keys():
            raise ValueError("missing parcel county or block groups")
        self.as_of = max(date.fromisoformat(s.properties["date_acq"]) for s in summaries.values())
        geoids = sorted(groups)
        tree = STRtree([shape(groups[g].geometry) for g in geoids])
        counts = {fips: {**summary.properties, "points_without_block_group": 0} for fips, summary in summaries.items()}
        output = []
        for index, (identity, rec) in enumerate(sorted(parcels.items())):
            if index % 1000 == 0:
                self.check_time()
            fips = identity.split(":", 1)[0]
            matches = tree.query(Point(rec.geometry["coordinates"]), predicate="covered_by")
            geoid = geoids[min(matches)] if len(matches) else None
            rec.properties.update(block_group=geoid, tract=geoid[:11] if geoid else None)
            rec.source_as_of = self.as_of
            counts[fips]["points_without_block_group"] += geoid is None
            output.append(rec)
        if any(v["ids_kept"] != sum(r.feature_id.startswith(fips + ":") for r in output) for fips, v in counts.items()):
            raise ValueError("parcel county counts do not match records")
        if self.live:
            count_checks({f: v["ids_kept"] for f, v in counts.items()})
        outside = sum(v["points_without_block_group"] for v in counts.values())
        if outside * 100 > len(output):
            raise ValueError("parcels: fewer than 99% of points fall in study block groups")
        self.check_time()
        summary = {"counties": {COUNTIES[f]: v for f, v in counts.items()}, "parcels": len(output),
                   "points_without_block_group": outside, "runtime_seconds": round(time.monotonic() - self.started, 3),
                   "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
        print("parcels: run note: " + json.dumps(summary, sort_keys=True), file=sys.stderr)
        output.append(AreaFeature(dataset="run_summary", feature_id=self.as_of.isoformat(), geometry=EMPTY,
                                  properties=summary, source_as_of=self.as_of))
        return output

    def source_as_of(self, raws):
        return self.as_of


ADAPTER = Parcels
