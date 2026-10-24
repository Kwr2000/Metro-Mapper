"""DPS agency-wide statistics, never apportioned to smaller geographies."""
from __future__ import annotations

import gzip
import json
import math
import posixpath
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timezone
from io import BytesIO
from zipfile import ZipFile

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature
from pyproj import Transformer
from shapely import make_valid, union_all, transform
from shapely.geometry import MultiPolygon, mapping, shape

DPS = "https://txucr.nibrs.com/Report/DownloadReportExcel"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services"
EMPTY = {"type": "GeometryCollection", "geometries": []}
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
COUNTIES = {"453": "Travis", "491": "Williamson", "209": "Hays"}
# Verified by Claude, 2026-10-24: ORI -> (current place GEOID, native BASENAME).
CITIES = {
    "TX2270100": ("4805000", "Austin"),
    "TX2270900": ("4857176", "Pflugerville"),
    "TX2270200": ("4846440", "Manor"),
    "TX2271100": ("4840984", "Lakeway"),
    "TX2273600": ("4807156", "Bee Cave"),
    "TX2272100": ("4840264", "Lago Vista"),
    "TX2272200": ("4838020", "Jonestown"),
    "TX2270300": ("4863008", "Rollingwood"),
    "TX2271900": ("4871324", "Sunset Valley"),
    "TX2270400": ("4877632", "West Lake Hills"),
    "TX2272300": ("4850200", "Mustang Ridge"),
    "TX2460500": ("4863500", "Round Rock"),
    "TX2460200": ("4829336", "Georgetown"),
    "TX2460900": ("4813552", "Cedar Park"),
    "TX2461700": ("4842016", "Leander"),
    "TX2460400": ("4835624", "Hutto"),
    "TX2460600": ("4871948", "Taylor"),
    "TX2462500": ("4837396", "Jarrell"),
    "TX2462400": ("4842664", "Liberty Hill"),
    "TX2460300": ("4830548", "Granger"),
    "TX2461800": ("4872824", "Thrall"),
    "TX2460100": ("4826136", "Florence"),
    "TX1050100": ("4865600", "San Marcos"),
    "TX1050700": ("4839952", "Kyle"),
    "TX1051200": ("4811080", "Buda"),
}
SHERIFFS = {"453": "TX2270000", "491": "TX2460000", "209": "TX1050000"}
MAPPED = CITIES.keys() | set(SHERIFFS.values())
PREFIXES = ("TX227", "TX246", "TX105")
COVERAGE = "Excludes reports by school, university, transit and constable police"
SHERIFF_COVERAGE = "Unincorporated areas and cities without their own police department"
SMALL = "Small population: one shopping area or event can swing this rate"
SPLIT = "Not available: split between police agencies"
SAFETY_FIELDS = ("agency", "ori", "agency_share", "agency_population", "violent", "property", "part1",
                 "rate_part1", "rate_violent", "part1_prev", "part1_change")
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def report_year(now):
    now = now.astimezone(timezone.utc)
    return now.year - (1 if now.month >= 7 else 2)


def xlsx_body(data):
    """Small native XLSX reader: workbook order/relationships, sparse cells, text only."""
    with ZipFile(BytesIO(data)) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(t.text or "" for t in si.findall(".//s:t", NS))
                       for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        rels = {r.attrib["Id"]: r.attrib["Target"]
                for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            target = rels[sheet.attrib[f"{{{NS['r']}}}id"]]
            path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
            if not path.startswith("xl/"):
                raise ValueError("unexpected XLSX sheet path")
            rows = []
            for row in ET.fromstring(z.read(path)).findall("s:sheetData/s:row", NS):
                index = int(row.attrib["r"])
                if index <= len(rows) or index > 100000:
                    raise ValueError("invalid XLSX row reference")
                rows.extend([] for _ in range(index - len(rows)))
                cells = rows[-1]
                for cell in row.findall("s:c", NS):
                    ref = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell.attrib["r"])
                    if ref is None or int(ref[2]) != index:
                        raise ValueError("invalid XLSX cell reference")
                    col = 0
                    for letter in ref[1]:
                        col = col * 26 + ord(letter) - 64
                    if col <= len(cells) or col > 16384:
                        raise ValueError("invalid XLSX column reference")
                    cells.extend("" for _ in range(col - len(cells)))
                    kind = cell.get("t", "n")
                    value = cell.find("s:v", NS)
                    text = value.text if value is not None and value.text else ""
                    if kind == "s":
                        idx = int(text)
                        if not 0 <= idx < len(strings):
                            raise ValueError("invalid XLSX shared string")
                        text = strings[idx]
                    elif kind == "inlineStr":
                        text = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                    elif kind not in {"n", "str"}:
                        raise ValueError("unexpected XLSX cell type")
                    cells[-1] = text
            name = sheet.attrib["name"]
            if name in sheets:
                raise ValueError("duplicate XLSX sheet name")
            sheets[name] = rows
        return {"sheets": sheets}


def header_key(text):
    return re.sub(r"[\s-]", "", text.lower())


HEADERS = {header_key(k): v for k, v in {
    "ORI": "ori", "Agency": "agency", "Population": "population", "Murder": "murder",
    "Rape": "rape", "Robbery": "robbery", "Aggravated Assault": "assault", "Assault": "assault",
    "Burglary": "burglary", "Larceny": "larceny", "Auto Theft": "auto_theft",
    "Human Trafficking Commercial Sex Acts": "trafficking_sex",
    "Human Trafficking Involuntary Servitude": "trafficking_servitude",
    "Arson": "arson", "Total": "total", "%Change": "change",
}.items()}
OFFENSES = ("murder", "rape", "robbery", "assault", "burglary", "larceny", "auto_theft")


def integer(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.0+)?", value.strip()):
        raise ValueError("expected a nonnegative integer count/population")
    return int(value.strip().replace(",", "").split(".")[0])


def agency_name(name):
    return " ".join({"PD": "PD", "SO": "Sheriff's Office", "CO": "County"}.get(w, w.title())
                    for w in name.split())


def table_rows(body, year):
    if (not isinstance(body, dict) or not isinstance(body.get("sheets"), dict) or not body["sheets"]):
        raise ValueError("expected XLSX sheets")
    table = next(iter(body["sheets"].values()))
    if (not isinstance(table, list) or len(table) < 2 or
            any(not isinstance(row, list) or any(not isinstance(c, str) for c in row) for row in table)):
        raise ValueError("expected text-only XLSX table")
    columns = []
    for label in table[1]:
        key = HEADERS.get(header_key(label))
        if key is None:
            raise ValueError("unknown DPS header: update column map")
        if key in columns:
            raise ValueError("duplicate DPS header")
        columns.append(key)
    if set(columns) != set(HEADERS.values()):
        raise ValueError("missing DPS header")
    agencies, current = [], None
    for cells in table[2:]:
        if not any(c.strip() for c in cells):
            continue
        if len(cells) > len(columns):
            raise ValueError("unexpected extra DPS columns")
        row = dict(zip(columns, cells + [""] * (len(columns) - len(cells))))
        if row["ori"].strip():
            ori = row["ori"].strip()
            if not re.fullmatch(r"TX[0-9]{7}", ori) or not row["agency"].strip():
                raise ValueError("invalid DPS agency row")
            current = {"ori": ori, "agency": agency_name(row["agency"].strip()),
                       "agency_population": integer(row["population"]) if ori.startswith(PREFIXES) else 0, "years": {}}
            agencies.append(current)
        else:
            match = re.fullmatch(r"Number of Offenses\s*-\s*([0-9]{4})", row["agency"].strip())
            if current is None or match is None or row["population"].strip():
                raise ValueError("unpaired DPS year row")
            if not current["ori"].startswith(PREFIXES):
                continue
            y = int(match[1])
            if y not in {year - 1, year} or y in current["years"]:
                raise ValueError("unexpected or duplicate DPS year row")
            counts = {key: integer(row[key]) for key in (*OFFENSES, "trafficking_sex", "trafficking_servitude", "arson", "total")}
            current["years"][y] = counts
    result = []
    for agency in agencies:
        if not agency["ori"].startswith(PREFIXES):
            continue
        if year not in agency["years"]:
            raise ValueError("missing DPS current-year row")
        counts = agency.pop("years")
        current, prev = counts[year], counts.get(year - 1)
        violent = sum(current[k] for k in OFFENSES[:4])
        prop = sum(current[k] for k in OFFENSES[4:])
        previous = sum(prev[k] for k in OFFENSES) if prev is not None else None
        population = agency["agency_population"]
        result.append({**agency, "violent": violent, "property": prop, "part1": violent + prop,
            "rate_part1": round((violent + prop) / population * 1000, 1) if population else None,
            "rate_violent": round(violent / population * 1000, 1) if population else None,
            "part1_prev": previous,
            "part1_change": round(((violent + prop) - previous) / previous * 100, 1) if previous else None,
            "safety_note": SMALL if 0 < population < 5000 else None,
            "reported_total": current["total"]})
    return result


def projected(doc, *, repair=False):
    geom = shape(doc)
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("expected TIGER polygon")
    if repair and not geom.is_valid:
        fixed = make_valid(geom)
        def parts(g):
            if g.geom_type == "Polygon":
                return [g]
            return [p for child in getattr(g, "geoms", []) for p in parts(child)]
        geom = MultiPolygon(parts(fixed))
    if (not geom.is_valid or geom.is_empty or not all(math.isfinite(v) for v in geom.bounds)
            or not -180 <= geom.bounds[0] <= geom.bounds[2] <= 180
            or not -90 <= geom.bounds[1] <= geom.bounds[3] <= 90):
        raise ValueError("invalid TIGER polygon")
    result = transform(geom, TO_AREA, interleaved=False)
    if not result.is_valid or not math.isfinite(result.area) or result.area <= 0:
        raise ValueError("invalid equal-area polygon")
    return result


def assign(geom, cities, city_union, county):
    shares = [(ori, min(1, max(0, geom.intersection(city).area / geom.area)))
              for ori, city in cities.items() if city.intersects(geom)]
    eligible = [(ori, share) for ori, share in shares if share >= .5 - 1e-9]
    if eligible:
        # Greatest share wins; stable ORI ordering breaks equal-half city ties.
        return sorted(eligible, key=lambda pair: (-pair[1], pair[0]))[0]
    outside = min(1, max(0, geom.difference(city_union).area / geom.area))
    return (SHERIFFS[county], outside) if outside >= .5 - 1e-9 else (None, None)


class DPSAgency(SourceAdapter):
    id = "dps_agency"
    entity = "area_feature"
    cadence = "annual"
    user_agent = "Mozilla/5.0 (compatible; metro-mapper/0.1 (+https://github.com/Kwr2000/metro-mapper))"

    def plan(self, ctx):
        self.year = report_year(ctx.now)
        self.as_of = date(self.year, 12, 31)
        self.retrieved = ctx.now.astimezone(timezone.utc).date().isoformat()
        return [Request(f"dps_{report}", {"url": DPS, "query": {
            "offenses": "", "startdate": f"Jan - {self.year}", "enddate": f"Dec - {self.year}",
            "reportId": report}}) for report in (615, 613, 652)] + [
            Request("places", {"url": TIGER + "/TIGERweb/tigerWMS_Current/MapServer/28/query", "query": {
                "where": "GEOID IN (" + ",".join(f"'{g}'" for g, _ in CITIES.values()) + ")",
                "outFields": "GEOID,BASENAME", "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}),
            Request("block_groups", {"url": TIGER + "/Census2020/tigerWMS_Census2020/MapServer/8/query", "query": {
                "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                "outSR": 4326, "f": "geojson", "returnGeometry": "true"}}),
        ]

    def fetch(self, req, ctx):
        # The compatibility user agent is required only by the DPS portal.
        from mm.adapter import USER_AGENT
        request = urllib.request.Request(req.params["url"] + "?" + urllib.parse.urlencode(req.params["query"]),
            headers={"User-Agent": self.user_agent if req.key.startswith("dps_") else USER_AGENT,
                     "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status != 200:
                    return RawPayload(req, None, status=response.status)
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                body = xlsx_body(data) if req.key.startswith("dps_") else json.loads(data)
                return RawPayload(req, body, status=response.status)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)

    def normalize(self, raw):
        if raw.status != 200:
            raise ValueError(f"dps_agency: HTTP {raw.status}")
        key, body = raw.request.key, raw.body
        if key in {"dps_615", "dps_613", "dps_652"}:
            for row in table_rows(body, self.year):
                yield AreaFeature(dataset="agency_input", feature_id=row["ori"], geometry=EMPTY, properties=row)
            return
        if key not in {"places", "block_groups"}:
            raise ValueError("unexpected request")
        if (not isinstance(body, dict) or body.get("type") != "FeatureCollection" or
                not isinstance(body.get("features"), list) or not body["features"] or
                body.get("exceededTransferLimit") or (body.get("properties") or {}).get("exceededTransferLimit")):
            raise ValueError("invalid or truncated TIGER response")
        expected = dict(CITIES.values())
        for f in body["features"]:
            props = f.get("properties", {})
            geoid = props.get("GEOID")
            if f.get("type") != "Feature" or not isinstance(geoid, str):
                raise ValueError("missing TIGER GEOID")
            if key == "places":
                if geoid not in expected or props.get("BASENAME") != expected[geoid]:
                    raise ValueError("unexpected place GEOID/BASENAME")
            elif not re.fullmatch(r"48(?:453|491|209)[0-9]{7}", geoid):
                raise ValueError("unexpected study block group")
            geom = projected(f.get("geometry"), repair=key == "places")
            # Store repaired places in canonical WGS84; block groups remain strict/original.
            geometry = f["geometry"]
            if key == "places" and not shape(geometry).is_valid:
                undo = Transformer.from_crs(5070, 4326, always_xy=True).transform
                geometry = mapping(transform(geom, undo, interleaved=False))
            yield AreaFeature(dataset=key + "_input", feature_id=geoid, geometry=geometry,
                              properties={"geoid": geoid})

    def follow_up(self, raw, ctx):
        list(self.normalize(raw))
        return []

    def finalize(self, records):
        groups = {}
        for dataset in ("agency_input", "places_input", "block_groups_input"):
            selected = [r for r in records if r.dataset == dataset]
            group = {r.feature_id: r for r in selected}
            if len(group) != len(selected):
                raise ValueError("duplicate agency/place/block group")
            groups[dataset] = group
        agencies, places, bgs = (groups[k] for k in ("agency_input", "places_input", "block_groups_input"))
        if not MAPPED <= agencies.keys():
            raise ValueError("missing mapped DPS ORI")
        for ori, agency in agencies.items():
            pop = agency.properties["agency_population"]
            if ori in MAPPED and pop <= 0:
                raise ValueError("mapped agency requires positive population")
            if ori not in MAPPED and pop > 0:
                raise ValueError("new agency: update the table")
        if places.keys() != {g for g, _ in CITIES.values()}:
            raise ValueError("missing current place")
        if not bgs:
            raise ValueError("missing block groups")
        cities = {ori: projected(places[geoid].geometry) for ori, (geoid, _) in CITIES.items()}
        city_union = union_all(list(cities.values()))
        output, counts = [], Counter(dict.fromkeys(sorted(MAPPED), 0))
        for geoid, bg in sorted(bgs.items()):
            ori, share = assign(projected(bg.geometry), cities, city_union, geoid[2:5])
            props = {"geoid": geoid, "county": COUNTIES[geoid[2:5]], "year": self.year,
                     "period": f"{self.year} (calendar year)", "retrieved": self.retrieved,
                     "coverage_note": COVERAGE, **dict.fromkeys(SAFETY_FIELDS), "safety_note": SPLIT}
            if ori is not None:
                source = agencies[ori].properties
                props.update({k: source[k] for k in SAFETY_FIELDS if k != "agency_share"})
                props.update(agency_share=round(share, 3), safety_note=source["safety_note"])
                if ori in SHERIFFS.values():
                    props["coverage_note"] = SHERIFF_COVERAGE + "; " + COVERAGE
                counts[ori] += 1
            output.append(AreaFeature(dataset="block_group", feature_id=geoid, geometry=bg.geometry,
                                      properties=props, source_as_of=self.as_of))
        summary = {"year": self.year, "agencies mapped": len(MAPPED), "places matched": len(places),
                   "block groups": len(bgs), "block groups per agency": dict(counts),
                   "split block groups": sum(r.properties["ori"] is None for r in output),
                   "unmapped agency totals": {ori: {k: r.properties[k] for k in
                        ("violent", "property", "part1", "reported_total")}
                        for ori, r in sorted(agencies.items()) if ori not in MAPPED}}
        print("dps_agency: run note: " + json.dumps(summary, sort_keys=True), file=sys.stderr)
        output.append(AreaFeature(dataset="run_summary", feature_id=str(self.as_of), geometry=EMPTY,
                                  properties=summary, source_as_of=self.as_of))
        return output

    def source_as_of(self, raws):
        return self.as_of


ADAPTER = DPSAgency
