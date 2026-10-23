"""Public campus points, district outlines and TEA ratings; never assigns attendance."""
from __future__ import annotations

import gzip
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from mm import config
from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature
from pyproj import Transformer
from shapely import STRtree, transform
from shapely.geometry import mapping, shape

DISTRICTS = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/School/MapServer/0/query"
BLOCK_GROUPS = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/8/query"
CAMPUSES = "https://nces.ed.gov/opengis/rest/services/K12_School_Locations/EDGE_GEOCODE_PUBLICSCH_2425/MapServer/0/query"
ASKTED = "https://data.texas.gov/resource/hzek-udky.json"
RATINGS = "https://data.texas.gov/resource/nui6-x374.json"
FIELDS = {
    "district": "GEOID,NAME,BASENAME,LOGRADE,HIGRADE",
    "block_group": "GEOID",
    "campus": "NCESSCH,LEAID,NAME,CITY,CNTY,SCHOOLYEAR",
    "directory": "school_number,nces_school_id,district_number,district_name,district_web_page_address",
    "rating": "campus_number,campus,district_number,district,school_type,grades_served,charter,alternative_education,overall_rating,overall_score,academic_growth_rating,academic_growth_score,school_progress_rating,school_progress_score,student_achievement_rating,student_achievement_score,relative_performance_rating,closing_the_gaps_rating,closing_the_gaps_score",
}
DOMAINS = ("overall", "academic_growth", "school_progress", "student_achievement", "closing_the_gaps")
RATING_FIELDS = [f"{domain}_{suffix}" for domain in DOMAINS for suffix in ("rating", "score")] + ["relative_performance_rating"]
YEAR = "2024–25"
ZONE_NOTE = "Which school serves an address is set by the district and can change yearly. Check the district's school finder."
NO_RATING = "No TEA rating found for this campus"
NOT_RATED = "Not rated by TEA for 2024–25"
EMPTY = {"type": "GeometryCollection", "geometries": []}
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform


def digits(value, length):
    if not isinstance(value, str):
        raise ValueError("school identifier must be text")
    result = re.sub(r"\D", "", value)
    if len(result) != length:
        raise ValueError("unexpected school identifier length")
    return result


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def website(value):
    value = text(value)
    if not value:
        return None
    if value.startswith("//"):
        value = "https:" + value
    elif not urllib.parse.urlsplit(value).scheme:
        value = "https://" + value
    try:
        url = urllib.parse.urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or any(c.isspace() for c in value):
            return None
    except ValueError:
        return None
    return value


def yes_no(value):
    value = text(value)
    if value is None:
        return None
    if value.lower() in {"yes", "y", "true", "1"}:
        return "Yes"
    if value.lower() in {"no", "n", "false", "0"}:
        return "No"
    raise ValueError("unexpected charter flag")


def rating(value):
    value = text(value)
    if value is None or value in {"-", "--", "N/A"}:
        return None
    if value not in {"A", "B", "C", "D", "F", "Not Rated"}:
        raise ValueError("unexpected TEA rating")
    return value


def score(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) and 0 <= result <= 100 else None


def polygon(doc):
    try:
        geom = shape(doc)
        if (geom.geom_type not in {"Polygon", "MultiPolygon"} or not geom.is_valid or geom.is_empty
                or geom.area <= 0 or not all(math.isfinite(x) for x in geom.bounds)
                or geom.bounds[0] < -180 or geom.bounds[2] > 180 or geom.bounds[1] < -90 or geom.bounds[3] > 90):
            raise ValueError("invalid school/study polygon")
        return geom
    except (TypeError, AttributeError):
        raise ValueError("missing school/study polygon") from None


def projected(doc):
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = TO_AREA(xy[:, 0], xy[:, 1])
        return result
    geom = transform(polygon(doc), coordinates)
    if not geom.is_valid or geom.is_empty or not math.isfinite(geom.area) or geom.area <= 0:
        raise ValueError("invalid equal-area polygon")
    return geom


def unique(records, key):
    result = {}
    for record in records:
        identity = record.properties[key]
        if identity in result and record != result[identity]:
            raise ValueError("conflicting duplicate school identifier")
        result[identity] = record
    return result


def summary_counts(districts, campuses):
    matched = sum(rec.properties["campus_number"] is not None for rec in campuses)
    not_rated = sum(rec.properties["rating_note"] == NOT_RATED for rec in campuses)
    rows = sum(rec.properties["rating_note"] != NO_RATING for rec in campuses)
    rated = sum(rec.properties["overall_rating"] in {"A", "B", "C", "D", "F"} for rec in campuses)
    return {"districts kept": len(districts), "campuses": len(campuses), "matched": matched,
            "rating rows": rows, "rated": rated, "not rated": not_rated, "unmatched": len(campuses) - matched}


class Schools(SourceAdapter):
    id = "schools"
    entity = "area_feature"
    cadence = "yearly"

    def plan(self, ctx):
        self.finders_path = ctx.adapter_dir / "finders.yaml"
        return [
            Request("districts", {"kind": "district", "url": DISTRICTS, "query": {
                "where": "1=1", "geometry": ",".join(map(str, config.app_config().study_bbox)),
                "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
                "outFields": FIELDS["district"], "outSR": 4326, "f": "geojson", "returnGeometry": "true",
                "maxAllowableOffset": .0001}}),
            Request("block_groups", {"kind": "block_group", "url": BLOCK_GROUPS, "query": {
                "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}),
            Request("campuses", {"kind": "campus", "url": CAMPUSES, "query": {
                "where": "STATE='TX' AND CNTY IN ('48453','48491','48209')", "outFields": FIELDS["campus"],
                "outSR": 4326, "f": "geojson", "returnGeometry": "true", "resultRecordCount": 2000}}),
            Request("directory", {"kind": "directory", "url": ASKTED, "query": {
                "$select": FIELDS["directory"], "$where": "nces_school_id IS NOT NULL", "$limit": 20000}}),
            Request("ratings", {"kind": "rating", "url": RATINGS, "query": {
                "$select": FIELDS["rating"], "$where": "school_type != 'District'", "$limit": 20000}}),
        ]

    def fetch(self, req, ctx):
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

    def rows(self, raw):
        if raw.status != 200:
            raise ValueError(f"schools: HTTP {raw.status}")
        kind, body = raw.request.params["kind"], raw.body
        required = set(FIELDS[kind].split(","))
        if kind in {"directory", "rating"}:
            if not isinstance(body, list) or not body or any(not isinstance(row, dict) for row in body):
                raise ValueError("expected Socrata JSON rows")
            if len(body) >= 20000:
                raise ValueError("school response may be truncated at Socrata limit")
            # Socrata omits null-valued cells. Validate the response's column vocabulary;
            # per-row identifiers stay mandatory, while absent nullable cells become null.
            if not required <= set().union(*(row.keys() for row in body)):
                raise ValueError("missing school response columns")
            return body
        if not isinstance(body, dict) or body.get("type") != "FeatureCollection" or not isinstance(body.get("features"), list):
            raise ValueError("expected school GeoJSON FeatureCollection")
        metadata = body.get("properties") or {}
        if body.get("exceededTransferLimit") or (isinstance(metadata, dict) and metadata.get("exceededTransferLimit")):
            raise ValueError("schools exceededTransferLimit")
        rows = body["features"]
        for row in rows:
            if (not isinstance(row, dict) or row.get("type") != "Feature"
                    or not isinstance(row.get("properties"), dict) or not required <= row["properties"].keys()):
                raise ValueError("missing school GeoJSON fields")
        return rows

    def follow_up(self, raw, ctx):
        self.rows(raw)
        return []

    def normalize(self, raw):
        kind = raw.request.params["kind"]
        for feature in self.rows(raw):
            row = feature if kind in {"directory", "rating"} else feature["properties"]
            geom = EMPTY
            if kind in {"district", "block_group"}:
                identity = digits(row["GEOID"], 7 if kind == "district" else 12)
                if (not identity.startswith("48") or (kind == "block_group" and identity[:5] not in {"48453", "48491", "48209"})):
                    raise ValueError("unexpected study geography")
                geom = mapping(polygon(feature.get("geometry")))
                props = {"geoid": identity}
                if kind == "district":
                    if not text(row["NAME"]):
                        raise ValueError("missing TIGER district name")
                    props.update(name=row["NAME"], grades=f"{row['LOGRADE']}–{row['HIGRADE']}" if row["LOGRADE"] is not None and row["HIGRADE"] is not None else None)
            elif kind == "campus":
                identity = digits(row["NCESSCH"], 12)
                lea_id = digits(row["LEAID"], 7)
                if row["CNTY"] not in {"48453", "48491", "48209"}:
                    raise ValueError("NCES campus outside study counties")
                if row["SCHOOLYEAR"] not in {"2024-2025", "2024-25", "2024–25"}:
                    raise ValueError("unexpected NCES school year")
                geom = feature.get("geometry")
                coords = geom.get("coordinates") if isinstance(geom, dict) else None
                if (not isinstance(coords, (list, tuple)) or len(coords) not in {2, 3} or geom.get("type") != "Point"
                        or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in coords)
                        or not -180 <= coords[0] <= 180 or not -90 <= coords[1] <= 90):
                    raise ValueError("invalid NCES point")
                props = {"nces_id": identity, "lea_id": lea_id, "name": text(row["NAME"]), "city": text(row["CITY"])}
            elif kind == "directory":
                identity = digits(row.get("nces_school_id"), 12)
                props = {"nces_id": identity, "campus_number": digits(row.get("school_number"), 9),
                    "tea_district_number": digits(row.get("district_number"), 6),
                    "district": text(row.get("district_name")), "website": website(row.get("district_web_page_address"))}
            else:
                identity = digits(row.get("campus_number"), 9)
                if row.get("school_type") == "District":
                    raise ValueError("district row in campus ratings")
                props = {"campus_number": identity, "tea_district_number": digits(row.get("district_number"), 6),
                    "school_type": text(row.get("school_type")), "grades_served": text(row.get("grades_served")),
                    "charter": yes_no(row.get("charter")), "alternative_education": text(row.get("alternative_education"))}
                for domain in DOMAINS:
                    value = rating(row.get(domain + "_rating"))
                    props[domain + "_rating"] = value
                    props[domain + "_score"] = score(row.get(domain + "_score")) if value not in {None, "Not Rated"} else None
                props["relative_performance_rating"] = rating(row.get("relative_performance_rating"))
            yield AreaFeature(dataset="school_" + kind + "_input", feature_id=identity, geometry=geom, properties=props)

    def finalize(self, records):
        groups = {kind: [record for record in records if record.dataset == "school_" + kind + "_input"]
                  for kind in FIELDS}
        districts = unique(groups["district"], "geoid")
        campuses = unique(groups["campus"], "nces_id")
        directory = unique(groups["directory"], "nces_id")
        ratings = unique(groups["rating"], "campus_number")
        if len(campuses) < 500:
            raise ValueError("schools: fewer than 500 NCES campuses")
        if not groups["block_group"]:
            raise ValueError("schools: missing study block groups")
        bgs = [projected(record.geometry) for record in unique(groups["block_group"], "geoid").values()]
        index = STRtree(bgs)
        kept = {}
        for geoid, district in districts.items():
            geom = projected(district.geometry)
            shares = [geom.intersection(bgs[i]).area / bgs[i].area for i in index.query(geom, predicate="intersects")]
            if any(share >= .005 or math.isclose(share, .005, rel_tol=0, abs_tol=1e-9) for share in shares):
                kept[geoid] = district
        if len(kept) < 20:
            raise ValueError("schools: fewer than 20 kept districts")
        finder_path = getattr(self, "finders_path", Path(__file__).with_name("finders.yaml"))
        finders = yaml.safe_load(finder_path.read_text()) or {}
        if not isinstance(finders, dict) or set(finders) - {d.properties["name"] for d in kept.values()}:
            raise ValueError("finder key does not match a kept TIGER district")
        lea_tea, website_options = {}, {}
        for match in directory.values():
            if match.properties["website"]:
                website_options.setdefault(match.properties["tea_district_number"], set()).add(match.properties["website"])
        tea_websites = {tea: min(urls, key=lambda url: (not url.startswith("https://"), url))
                        for tea, urls in website_options.items()}
        for campus in campuses.values():
            match = directory.get(campus.feature_id)
            if not match:
                continue
            lea, tea = campus.properties["lea_id"], match.properties["tea_district_number"]
            if lea in lea_tea and lea_tea[lea] != tea:
                raise ValueError("conflicting NCES / TEA district mapping")
            lea_tea[lea] = tea
        district_output = []
        for geoid, district in sorted(kept.items()):
            name = district.properties["name"]
            entry = finders.get(name)
            tea = lea_tea.get(geoid)
            url = tea_websites.get(tea)
            label = "District website" if url else None
            if entry is not None:
                if not isinstance(entry, dict) or not entry.get("checked") or not text(entry.get("label")) or not website(entry.get("url")):
                    raise ValueError("invalid checked district finder")
                url, label = website(entry["url"]), entry["label"]
            display = name.replace("Consolidated Independent School District", "CISD").replace("Independent School District", "ISD")
            district_output.append(AreaFeature(dataset="district", feature_id=geoid, geometry=district.geometry,
                properties={"geoid": geoid, "name": display, "grades": district.properties["grades"],
                    "finder_link": url, "finder_label": label, "tea_district_number": tea, "zone_note": ZONE_NOTE}))
        district_names = {record.feature_id: record.properties["name"] for record in district_output}
        campus_output = []
        matched = row_count = 0
        for identity, campus in sorted(campuses.items()):
            match = directory.get(identity)
            value = ratings.get(match.properties["campus_number"]) if match else None
            matched += match is not None
            row_count += value is not None
            props = {"nces_id": identity, "campus_number": match.properties["campus_number"] if match else None,
                "name": campus.properties["name"], "city": campus.properties["city"],
                "district": (match.properties["district"] if match else None) or
                    district_names.get(campus.properties["lea_id"]),
                "school_type": None, "grades_served": None, "charter": None, "alternative_education": None,
                **{field: None for field in RATING_FIELDS}, "ratings_year": YEAR,
                "rating_note": NO_RATING, "enrollment_note": None}
            if value:
                row = value.properties
                if row["tea_district_number"] != match.properties["tea_district_number"]:
                    raise ValueError("TEA campus district mismatch")
                props.update({field: row[field] for field in (*RATING_FIELDS, "school_type", "grades_served", "charter", "alternative_education")})
                props["rating_note"] = NOT_RATED if row["overall_rating"] == "Not Rated" else None
                if row["charter"] == "Yes":
                    props["enrollment_note"] = "Open-enrollment charter: no attendance zone"
            campus_output.append(AreaFeature(dataset="campus", feature_id=identity, geometry=campus.geometry, properties=props))
        if matched * 10 < len(campuses) * 9:
            raise ValueError("schools: AskTED match rate below 90%")
        if row_count * 5 < matched * 4:
            raise ValueError("schools: TEA rating-row coverage below 80%")
        counts = summary_counts(district_output, campus_output)
        print("schools: run note: " + "; ".join(f"{key}={value}" for key, value in counts.items()), file=sys.stderr)
        return district_output + campus_output


ADAPTER = Schools
