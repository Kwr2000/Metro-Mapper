"""TLC's 2020/2024 presidential returns on published 2024 precincts, context only."""
from __future__ import annotations

import csv
import json
import math
import resource
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

import shapefile
from mm.adapter import RawPayload, Request, SourceAdapter
from mm.paths import paths
from mm.schemas import AreaFeature
from pyproj import CRS, Transformer
from shapely import make_valid, transform
from shapely.geometry import MultiPolygon, mapping, shape

DATA_URL = "https://data.capitol.texas.gov/dataset/35b16aee-0bb0-4866-b1ec-859f1f044241/resource/e1cd6332-6a7a-4c78-ad2a-852268f6c7a2/download/2024-general-vtds-election-data.zip"
SHAPES_URL = "https://data.capitol.texas.gov/dataset/4d8298d0-d176-4c19-b174-42837027b73e/resource/906f47e4-4e39-4156-b1bd-4969be0b2780/download/vtds_24pg.zip"
COUNTIES = {453: "Travis", 491: "Williamson", 209: "Hays"}
YEARS = (2024, 2020)
RETURNS = ("County", "FIPS", "VTD", "cntyvtd", "vtdkeyvalue", "Office", "Name", "Party", "Incumbent", "Votes")
VRTO = ("vtdkey", "TotalVR", "TotalTO")
SHAPE_FIELDS = ("CNTY", "VTD", "VTDKEY", "CNTYVTD")
MEMBERS = {f"{y}_General_Election_{kind}.csv": (y, kind) for y in YEARS for kind in ("Returns", "VRTO")}
SOURCE_NOTE = "2024 voting precincts (TLC); 2020 results re-tabulated to 2024 precincts by TLC"
SMALL = "Fewer than 50 votes: not shown"
TURNOUT = "Turnout not shown: ballots exceed registered voters after re-tabulation"
AS_OF = date(2024, 11, 5)
EMPTY = {"type": "GeometryCollection", "geometries": []}
TO_AREA = Transformer.from_crs(4326, 5070, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(5070, 4326, always_xy=True).transform


def integer(value):
    # DBF numeric cells without decimal places are ints; CSV cells are text.
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError("expected a nonnegative integer")
    return int(value)


def key(value):
    return str(integer(value))


def member(z, filename):
    matches = [info for info in z.infolist() if Path(info.filename).name.casefold() == filename.casefold()]
    if len(matches) != 1:
        raise ValueError("missing or duplicate required ZIP member")
    return matches[0]


def parse_election_zip(path, check_time=lambda: None):
    """Stream four CSVs; never retain unused VRTO columns or non-presidential rows."""
    members = {}
    with ZipFile(path) as z:
        for filename, (_, kind) in MEMBERS.items():
            keep = RETURNS if kind == "Returns" else VRTO
            with z.open(member(z, filename)) as stream, TextIOWrapper(stream, encoding="utf-8-sig", newline="") as text:
                reader = csv.reader(text, strict=True)
                header = next(reader, [])
                if len(set(header)) != len(header) or not set((*keep, "FIPS")) <= set(header):
                    raise ValueError("missing or duplicate election CSV headers")
                positions = [header.index(col) for col in keep]
                county_col = header.index("FIPS")
                office_col = header.index("Office") if kind == "Returns" else None
                kept = [list(keep)]
                for i, row in enumerate(reader):
                    if i % 1000 == 0:
                        check_time()
                    if not row:
                        continue
                    if len(row) != len(header):
                        raise ValueError("invalid election CSV row width")
                    if integer(row[county_col]) not in COUNTIES:
                        continue
                    if office_col is not None and row[office_col] != "President":
                        continue
                    # Only these selected cells survive parsing; the raw CSV is never extracted.
                    kept.append([row[pos] for pos in positions])
                members[filename] = kept
    return {"members": members}


def reproject(geom, operation):
    # The same Shapely 2 coordinate-array form used by the areas adapter.
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = operation(xy[:, 0], xy[:, 1])
        return result
    return transform(geom, coordinates)


def polygon(doc, *, repair=False):
    geom = shape(doc)
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("expected precinct polygon")
    if repair and not geom.is_valid:
        def parts(g):
            if g.geom_type == "Polygon":
                return [g]
            return [p for child in getattr(g, "geoms", []) for p in parts(child)]
        geom = MultiPolygon(parts(make_valid(geom)))
    if geom.is_empty or not geom.is_valid or not all(math.isfinite(v) for v in geom.bounds):
        raise ValueError("invalid precinct polygon")
    return geom


def parse_shape_zip(path, folder, check_time=lambda: None):
    """Extract only four required shapefile components to the download's temporary folder."""
    components = {}
    with ZipFile(path) as z:
        for suffix in ("shp", "shx", "dbf", "prj"):
            info = member(z, "VTDs_24PG." + suffix)
            target = Path(folder) / ("precincts." + suffix)
            with z.open(info) as source, target.open("wb") as dest:
                while chunk := source.read(1024 * 1024):
                    check_time()
                    dest.write(chunk)
            components[suffix] = target
    crs = CRS.from_wkt(components["prj"].read_text())
    to_wgs84 = Transformer.from_crs(crs, 4326, always_xy=True).transform
    features = []
    with shapefile.Reader(shp=str(components["shp"]), shx=str(components["shx"]), dbf=str(components["dbf"])) as reader:
        if not set(SHAPE_FIELDS) <= {f[0] for f in reader.fields[1:]}:
            raise ValueError("missing precinct DBF fields")
        for record in reader.iterRecords(fields=list(SHAPE_FIELDS)):
            check_time()
            props = record.as_dict()
            if integer(props["CNTY"]) not in COUNTIES:
                continue
            geom = reproject(polygon(reader.shape(record.oid).__geo_interface__, repair=True), to_wgs84)
            features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
    return {"type": "FeatureCollection", "features": features}


def display_geometry(doc):
    geom = polygon(doc)
    w, s, e, n = geom.bounds
    if not (-180 <= w <= e <= 180 and -90 <= s <= n <= 90):
        raise ValueError("precinct coordinates outside WGS84")
    projected = reproject(geom, TO_AREA)
    if not math.isfinite(projected.area) or projected.area <= 0:
        raise ValueError("invalid projected precinct area")
    simplified = reproject(projected.simplify(5, preserve_topology=True), TO_WGS84)
    def rounded(value):
        return [rounded(v) for v in value] if isinstance(value, (list, tuple)) else round(value, 6)
    result = mapping(simplified)
    result = {"type": result["type"], "coordinates": rounded(result["coordinates"])}
    polygon(result)  # Never publish a collapsed/invalid rounded shape.
    return result


def production_checks(count, totals):
    if not 523 <= count <= 583:
        raise ValueError("elections: precinct count outside 553 +/- 30")
    for party, expected in (("D", 612262), ("R", 384529)):
        if abs(totals[2024][party] - expected) > expected * .01:
            raise ValueError("elections: 2024 presidential totals outside 1%")


class Elections(SourceAdapter):
    id = "elections"
    entity = "area_feature"
    cadence = "annual"

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        self.started = time.monotonic()
        return [Request("election_data", {"url": DATA_URL}), Request("vtd_shapes", {"url": SHAPES_URL})]

    def check_time(self):
        if time.monotonic() - self.started > 15 * 60:
            raise ValueError("elections: 15-minute runtime limit exceeded")

    def fetch(self, req, ctx):
        if req.key not in {"election_data", "vtd_shapes"}:
            raise ValueError("unexpected elections request")
        request = urllib.request.Request(req.params["url"], headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        try:
            paths().raw.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="elections-", dir=paths().raw) as folder:
                archive = Path(folder) / "download.zip"
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
                        raise ValueError("incomplete elections download")
                self.check_time()
                body = (parse_election_zip(archive, self.check_time) if req.key == "election_data" else
                        parse_shape_zip(archive, folder, self.check_time))
            # Both archive and extracted components are gone before returning.
            return RawPayload(req, body, status=200)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception as exc:
            # No generic retry/redownload of these large archives. Never log payloads or paths.
            return RawPayload(req, {"error": f"elections download/parse failed ({type(exc).__name__})"}, status=502)

    def normalize(self, raw):
        if raw.status != 200:
            raise ValueError(f"elections: HTTP {raw.status}")
        if raw.request.key == "vtd_shapes":
            body = raw.body
            if (not isinstance(body, dict) or body.get("type") != "FeatureCollection" or
                    not isinstance(body.get("features"), list) or not body["features"]):
                raise ValueError("expected precinct GeoJSON")
            for feature in body["features"]:
                props = feature["properties"]
                if feature.get("type") != "Feature" or set(props) != set(SHAPE_FIELDS):
                    raise ValueError("unexpected precinct properties")
                county = integer(props["CNTY"])
                if county not in COUNTIES:
                    raise ValueError("unexpected precinct county")
                if not isinstance(props["VTD"], str) or not props["VTD"].strip():
                    raise ValueError("missing precinct VTD")
                yield AreaFeature(dataset="shapes_input", feature_id=key(props["VTDKEY"]),
                    geometry=display_geometry(feature["geometry"]), properties={"county": COUNTIES[county],
                    "county_code": county, "precinct": f"{COUNTIES[county]} precinct {props['VTD']}"})
            return
        if raw.request.key != "election_data" or not isinstance(raw.body, dict) or set(raw.body.get("members", {})) != set(MEMBERS):
            raise ValueError("missing election CSV members")
        for filename, (year, kind) in MEMBERS.items():
            rows = raw.body["members"][filename]
            columns = RETURNS if kind == "Returns" else VRTO
            if not rows or rows[0] != list(columns):
                raise ValueError("unexpected retained election headers")
            for cells in rows[1:]:
                if len(cells) != len(columns) or any(not isinstance(c, str) for c in cells):
                    raise ValueError("invalid retained election row")
                row = dict(zip(columns, cells))
                if kind == "VRTO":
                    props = {"registered": integer(row["TotalVR"]), "ballots": integer(row["TotalTO"])}
                    identity = key(row["vtdkey"])
                    dataset = f"turnout_{year}_input"
                else:
                    if row["Office"] != "President" or row["Party"] not in {"D", "R", "L", "G", "W"}:
                        raise ValueError("unexpected presidential office/party")
                    county = integer(row["FIPS"])
                    if county not in COUNTIES or not row["Name"].strip():
                        raise ValueError("unexpected returns county/candidate")
                    vtd = key(row["vtdkeyvalue"])
                    props = {"vtdkey": vtd, "county_code": county, "party": row["Party"],
                             "candidate": row["Name"], "votes": integer(row["Votes"])}
                    identity = json.dumps([vtd, row["Party"], row["Name"]])
                    dataset = f"returns_{year}_input"
                yield AreaFeature(dataset=dataset, feature_id=identity, geometry=EMPTY, properties=props)

    def follow_up(self, raw, ctx):
        if raw.status != 200:
            raise ValueError(f"elections: HTTP {raw.status}")
        # Parsing errors and key checks are fatal; no extra requests or fallback sources.
        return []

    def finalize(self, records):
        datasets = ("shapes_input", *(f"{kind}_{year}_input" for year in YEARS for kind in ("returns", "turnout")))
        groups = {}
        for dataset in datasets:
            chosen = [r for r in records if r.dataset == dataset]
            group = {r.feature_id: r for r in chosen}
            if len(group) != len(chosen):
                raise ValueError("duplicate election key/candidate row")
            groups[dataset] = group
        shapes = groups["shapes_input"]
        if not shapes:
            raise ValueError("missing precinct shapes")
        totals, under, registered, ballots, returns = {}, {}, {}, {}, {}
        for year in YEARS:
            by_vtd = {}
            totals[year] = Counter(dict.fromkeys(("D", "R", "L", "G", "W"), 0))
            for r in groups[f"returns_{year}_input"].values():
                p = r.properties
                vtd = p["vtdkey"]
                if vtd not in shapes or p["county_code"] != shapes[vtd].properties["county_code"]:
                    raise ValueError("returns key/county does not match precinct shape")
                by_vtd.setdefault(vtd, []).append(p)
                totals[year][p["party"]] += p["votes"]
            if by_vtd.keys() != shapes.keys() or groups[f"turnout_{year}_input"].keys() != shapes.keys():
                raise ValueError("returns/VRTO and shapes must match both ways")
            under[year] = sum(sum(r["votes"] for r in rows) < 50 for rows in by_vtd.values())
            registered[year] = sum(r.properties["registered"] for r in groups[f"turnout_{year}_input"].values())
            ballots[year] = sum(r.properties["ballots"] for r in groups[f"turnout_{year}_input"].values())
            returns[year] = by_vtd
        if self.live:
            production_checks(len(shapes), totals)
        output = []
        for vtd, feature in sorted(shapes.items(), key=lambda pair: int(pair[0])):
            self.check_time()
            props = {"vtdkey": vtd, "county": feature.properties["county"],
                     "precinct": feature.properties["precinct"], "source_note": SOURCE_NOTE}
            notes = []
            for year in YEARS:
                rows = returns[year][vtd]
                major = {party: [r for r in rows if r["party"] == party] for party in ("D", "R")}
                if any(len(v) != 1 for v in major.values()):
                    raise ValueError("expected one Democratic and one Republican candidate per precinct/year")
                counts = Counter()
                for row in rows:
                    counts[row["party"]] += row["votes"]
                total = sum(counts.values())
                base = f"pres_{year}_"
                values = {"dem": counts["D"], "rep": counts["R"], "other": total - counts["D"] - counts["R"],
                          "total": total, "dem_share": counts["D"] / total if total else None,
                          "rep_share": counts["R"] / total if total else None,
                          "margin": (counts["R"] - counts["D"]) / total if total else None}
                if total < 50:
                    values = dict.fromkeys(values)
                    notes.append(f"{year}: {SMALL}")
                props.update({base + k: round(v, 3) if isinstance(v, float) else v for k, v in values.items()})
                props.update({base + "dem_name": major["D"][0]["candidate"], base + "rep_name": major["R"][0]["candidate"]})
                p = groups[f"turnout_{year}_input"][vtd].properties
                reg, cast = p["registered"], p["ballots"]
                props.update({f"registered_{year}": reg, f"ballots_{year}": cast,
                              f"turnout_{year}": round(cast / reg, 3) if reg > 0 and cast <= reg else None})
                if cast > reg:
                    notes.append(f"{year}: {TURNOUT}")
            props["election_note"] = "; ".join(notes) or None
            output.append(AreaFeature(dataset="precinct", feature_id=vtd, geometry=feature.geometry,
                                      properties=props, source_as_of=AS_OF))
        summary = {"precincts": len(shapes), "precincts per county": dict(Counter(r.properties["county"] for r in output)),
                   "presidential totals by party and year": {str(y): dict(totals[y]) for y in YEARS},
                   "registered by year": {str(y): registered[y] for y in YEARS},
                   "ballots by year": {str(y): ballots[y] for y in YEARS},
                   "precincts under 50 votes by year": {str(y): under[y] for y in YEARS},
                   "runtime_seconds": round(time.monotonic() - self.started, 2),
                   "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
        print("elections: run note: " + json.dumps(summary, sort_keys=True), file=sys.stderr)
        output.append(AreaFeature(dataset="run_summary", feature_id=str(AS_OF), geometry=EMPTY,
                                  properties=summary, source_as_of=AS_OF))
        return output

    def source_as_of(self, raws):
        return AS_OF


ADAPTER = Elections
