"""Offline home/address publisher; no source calls and no location inference.

P2-07 lookup contract: normalize_query(text), obtain shard_id(street_key), then use
meta['shards'][base] (one file or its <base>-<third> splits). A split uses the third
alphanumeric street-name character, or '0' if absent. Match number + street_key;
restrict unit/ZIP only when supplied. Return ALL matching rows, including condos.
Grid cells contain [id, lon, lat, shard]; inspect the clicked cell and its eight
neighbors, choose the nearest point within 30 m, then load that address shard.

Address fields are strings (leading zeros removed only from number/unit, ZIP kept).
Missing compact cells are null, not a substituted zero. address_key and tract live
in the harmonized intermediate record; the public shard columns are exactly FIELDS.
No timestamp/runtime is serialized, so equal inputs produce byte-identical output.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import re
import tempfile

from . import adapter, canonical, values
from .adapter import RunContext
from .budget import CallBudget
from .paths import paths
from .privacy import check_properties

COUNTIES = {"Travis": ("tcad", "48453", 80), "Williamson": ("wcad", "48491", 98), "Hays": ("hays_cad", "48209", 98)}
FIELDS = ["id", "number", "street_key", "unit", "zip", "situs", "city", "county", "category", "lon", "lat",
          "block_group", "hood_cd", "living_area", "year_built", "land_acres", "floors", "market_value",
          "land_value", "improvement_value", "value_year", "certified", "placed", "range_pct", "range_flags"]
KEEP = ("county", "prop_id", "category", "situs_number", "situs_prefix", "situs_street", "situs_suffix",
        "situs_unit", "situs_city", "situs_zip", "situs", "hood_cd", "market_value", "land_value",
        "improvement_value", "value_year", "certified", "living_area", "year_built", "land_acres", "floors")
MAX_SHARD_BYTES = 2_000_000
MAX_TOTAL_BYTES = 200_000_000
DIRECTIONS = dict(zip("NORTH SOUTH EAST WEST NORTHEAST NORTHWEST SOUTHEAST SOUTHWEST".split(),
                      "N S E W NE NW SE SW".split()))
DIRS = set(DIRECTIONS.values()) | set(DIRECTIONS)
SUFFIXES = {}
for forms in (
    "AVE AVENUE AV AVEN AVENU AVN AVNUE", "BLVD BOULEVARD BOUL BOULV", "CIR CIRCLE CIRC CIRCL CRCL CRCLE",
    "CT COURT", "CV COVE", "XING CROSSING CRSSNG", "DR DRIVE DRIV DRV", "EXPY EXPRESSWAY EXP EXPW EXPRESS",
    "FWY FREEWAY FREEWY FRWAY FRWY", "HWY HIGHWAY HIGHWY HIWAY HIWY HWAY", "LN LANE", "LOOP LOOPS",
    "PKWY PARKWAY PARKWY PKWAY PKY", "PASS", "PATH PATHS", "PL PLACE", "PLZ PLAZA PLAZ", "PT POINT",
    "RD ROAD", "RUN", "SQ SQUARE SQR SQRE SQU", "ST STREET STR STRT", "TER TERRACE TERR", "TRCE TRACE TRACES",
    "TRL TRAIL TRAILS TR TRLS", "VW VIEW", "WAY", "ALY ALLEY", "BND BEND", "CRES CRESCENT", "HL HILL",
    "HLS HILLS", "HTS HEIGHTS", "HOLW HOLLOW", "RDG RIDGE", "RTE ROUTE", "WALK", "BCH BEACH", "GRV GROVE",
    "GLN GLEN", "LNDG LANDING", "MDW MEADOW", "PASSAGE PSGE", "RAMP", "VLY VALLEY", "VIS VISTA", "ROW",
):
    words = forms.split()
    SUFFIXES.update({word: words[0] for word in words})
SUFFIX_FORMS = set(SUFFIXES.values())
ORDINALS = dict(zip("FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH THIRTEENTH FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH NINETEENTH TWENTIETH".split(),
                   "1ST 2ND 3RD 4TH 5TH 6TH 7TH 8TH 9TH 10TH 11TH 12TH 13TH 14TH 15TH 16TH 17TH 18TH 19TH 20TH".split()))
UNIT_WORDS = {"APT", "APARTMENT", "UNIT", "STE", "SUITE", "BLDG"}
# Common locality tails in the stored CADs, not an address/location data source. Commas,
# TX and suffix boundaries work without this list; these cover unpunctuated CAD display lines.
CITIES = sorted((city.split() for city in (
    "AUSTIN", "ROUND ROCK", "GEORGETOWN", "LEANDER", "KYLE", "CEDAR PARK", "PFLUGERVILLE", "HUTTO",
    "SAN MARCOS", "BUDA", "LIBERTY HILL", "DRIPPING SPRINGS", "JARRELL", "TAYLOR", "WIMBERLEY", "MANOR",
    "LAGO VISTA", "DEL VALLE", "LAKEWAY", "DRIFTWOOD", "SPICEWOOD", "FLORENCE", "MAXWELL", "ELGIN",
    "MANCHACA", "GRANGER", "THRALL", "THE HILLS", "JONESTOWN", "WEST LAKE HILLS", "BEE CAVE", "UHLAND",
    "COUPLAND", "BARTLETT", "NIEDERWALD", "MOUNTAIN CITY", "WEBBERVILLE", "SUNSET VALLEY", "POINT VENTURE",
    "MARBLE FALLS", "BRIARCLIFF", "VOLENTE", "THORNDALE", "CEDAR CREEK", "CREEDMOOR", "ROLLINGWOOD", "WEIR",
    "NEW BRAUNFELS", "WESTLAKE HILLS", "BEE CAVES", "FISCHER", "HENLY",
    "DRIPPING SPGS", "DRIPPING SPRIGNS", "DRIPPIING SPRINGS", "AUSITN", "AUSTN", "PLUGERVILLE",
    "NEIDERWALD", "WIMBERELY", "ROUND MOUNTAIN", "WOODCREEK", "BLANCO", "SCHWERTNER", "BERTRAM",
)), key=lambda words: (-len(words), words))
HIGHWAYS = [
    (r"(?:F M|FM|FARM TO MARKET)(?: ROAD| RD)?", "FM"),
    (r"(?:RANCH ROAD|RANCH RD|RR|RM|R M)", "RR"),
    (r"(?:STATE HIGHWAY|STATE HWY|SH|HWY|HIGHWAY)", "SH"),
    (r"(?:US HIGHWAY|US HWY|US|U S HIGHWAY|U S HWY|U S)", "US"),
    (r"(?:COUNTY ROAD|COUNTY RD|CR)", "CR"),
    (r"(?:INTERSTATE|IH|I H|I)", "IH"),
]


def clean(value):
    return " ".join(re.sub(r"[.,#]", " ", value or "").upper().split())


def unpad(value):
    return re.sub(r"(?<![A-Z0-9])0+(?=[0-9])", "", value)


def normalize_unit(value):
    words = [word for word in clean(value).split() if word not in UNIT_WORDS]
    return unpad(" ".join(words))


def normalize_street(prefix, name, suffix):
    words = clean(" ".join(v for v in (prefix, name, suffix) if v)).split()
    words = [ORDINALS.get(word, word) for word in words]
    if words and words[0] in DIRS:
        words[0] = DIRECTIONS.get(words[0], words[0])
    if len(words) > 1 and words[-1] in DIRS:
        words[-1] = DIRECTIONS.get(words[-1], words[-1])
    end = len(words)-1 if len(words) > 1 and words[-1] in DIRS else len(words)
    if end:
        words[end-1] = SUFFIXES.get(words[end-1], words[end-1])
    # TCAD stores numbered streets bare ("E 17 ST"); listings say "E 17th St". A bare number
    # that is the whole street name before a suffix becomes an ordinal (2026-10-27 review).
    start = 1 if len(words) > 2 and words[0] in DIRECTIONS.values() else 0
    if end and end-1 == start+1 and re.fullmatch(r"[0-9]+", words[start]) and words[end-1] in SUFFIX_FORMS:
        n = int(words[start])
        words[start] = f"{n}{'TH' if 10 <= n % 100 <= 20 else {1: 'ST', 2: 'ND', 3: 'RD'}.get(n % 10, 'TH')}"
    text = " ".join(words)
    # Whole highway prefixes only, after an optional directional. Never rewrite interior words.
    for pattern, replacement in HIGHWAYS:
        text, changes = re.subn(r"^(?:(N|S|E|W|NE|NW|SE|SW) )?"+pattern+r" (\d+)\b",
            lambda m: ((m[1]+" ") if m[1] else "")+replacement+" "+str(int(m[2])), text)
        if changes:
            break
    return text


def normalize_query(text):
    """Return {number, street_key, unit, zip}; unknown/missing parts are empty strings.

    Comma-separated locality tails are discarded; without commas use trailing TX, known
    localities, then the last suffix boundary. Do not geocode or infer a missing number/ZIP.
    """
    original = (text or "").upper()
    normalized = clean(original)
    zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", normalized)
    if zip_match and (re.search(r"\b(?:APT|APARTMENT|UNIT|STE|SUITE|BLDG)\s*$", normalized[:zip_match.start()]) or re.search(r"#\s*\d{5}\s*$", original)):
        zip_match = None
    zip5 = zip_match[1] if zip_match else ""
    if zip_match:
        normalized = normalized[:zip_match.start()].strip()
    normalized = re.sub(r"\s+(?:TX|TEXAS)$", "", normalized)
    # Preserve '#'/comma unit markers until after localities are removed.
    comma = original.find(",")
    if comma >= 0:
        chunks = original.split(",")
        address = chunks[0]
        for chunk in chunks[1:]:
            if re.match(r"^\s*(?:#|APT\b|APARTMENT\b|UNIT\b|STE\b|SUITE\b|BLDG\b)", chunk):
                address += " "+chunk
            else:
                break
        normalized = clean(address)
        if zip5 and re.search(r"\s+"+zip5+r"(?:-\d{4})?$", normalized):
            normalized = re.sub(r"\s+"+zip5+r"(?:-\d{4})?$", "", normalized)
    words = normalized.split()
    number = ""
    if words and re.fullmatch(r"\d+[A-Z]?(?:[-/](?:\d+[A-Z]?|[A-Z]))*", words[0]):
        number = unpad(words.pop(0))
        if words and re.fullmatch(r"\d+/\d+", words[0]):
            number += " "+words.pop(0)
        elif (len(words) > 1 and words[0] not in DIRS and words[1] not in SUFFIXES
              and not any(re.match(pattern+r" \d+\b", " ".join(words)) for pattern, _ in HIGHWAYS)
              and re.fullmatch(r"(?:[A-Z](?:[0-9]+|[/&-][A-Z])?|[0-9]+)", words[0])):
            # CADs also store a separate house-letter/building token or a second number.
            number += " "+unpad(words.pop(0))
    for city in CITIES:
        if len(words) > len(city) and words[-len(city):] == city:
            words = words[:-len(city)]
            break
    unit = ""
    markers = [i for i, word in enumerate(words) if word in UNIT_WORDS]
    if markers:
        pos = markers[0]
        unit = normalize_unit(" ".join(words[pos+1:]))
        words = words[:pos]
    elif "#" in original:
        # '#' becomes a space in the street key but retains unit semantics here.
        candidate = clean(original.split("#", 1)[1].split(",", 1)[0]).split()
        if candidate:
            unit = normalize_unit(candidate[0])
            if unit and words and normalize_unit(words[-1]) == unit:
                words.pop()
    words = normalize_street(None, " ".join(words), None).split()
    if not unit:
        # A short token after a street suffix/postdirection is an implicit CAD unit.
        suffixes = [i for i, word in enumerate(words) if word in SUFFIXES and i > 0]
        if suffixes:
            end = suffixes[-1]+1
            if end < len(words) and words[end] in DIRS:
                end += 1
            if len(words) == end+1 and re.fullmatch(r"[A-Z0-9][A-Z0-9/&-]*", words[-1]):
                unit = normalize_unit(words[-1]); words = words[:end]
    return {"number": number, "street_key": normalize_street(None, " ".join(words), None), "unit": unit, "zip": zip5}


def address_parts(p):
    prefix, name, suffix = (p.get(field) or "" for field in ("situs_prefix", "situs_street", "situs_suffix"))
    unit = normalize_unit(p.get("situs_unit"))
    for field in ("name", "suffix"):
        value = name if field == "name" else suffix
        marker = re.search(r"#|\b(?:APT|APARTMENT|UNIT|STE|SUITE|BLDG)\b", value, re.I)
        if marker:
            unit = unit or normalize_unit(value[marker.end():])
            if field == "name":name = value[:marker.start()]
            else:suffix = value[:marker.start()]
    key = normalize_street(prefix, name, suffix)
    return {"number": unpad(clean(p.get("situs_number"))), "street_key": key,
            "unit": unit, "zip": match[0] if (match := re.match(r"[0-9]{5}", clean(p.get("situs_zip")))) else ""}


def address_key(parts):
    return "|".join(parts[field] for field in ("number", "street_key", "unit", "zip"))


def street_name(key):
    words = clean(key).split()
    if len(words) > 1 and words[0] in DIRS:
        words.pop(0)
    if len(words) > 1 and words[-1] in DIRS:
        words.pop()
    if len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return "".join(re.findall(r"[A-Z0-9]", " ".join(words)))


def shard_id(key):
    return (street_name(key)+"00")[:2]


def shard_third(key):
    return (street_name(key)+"000")[2]


def cell_id(lon, lat):
    return f"{math.floor(lon/.01)}_{math.floor(lat/.01)}"


def nearest(rows, lon, lat, max_metres=30):
    """Small-grid lookup reference: return all tied closest rows inside max_metres."""
    distances = []
    for row in rows:
        dx = math.radians(row[1]-lon)*math.cos(math.radians((row[2]+lat)/2))
        dy = math.radians(row[2]-lat)
        distances.append((6371008.8*math.hypot(dx, dy), row))
    if not distances:
        return []
    best = min(d for d, _ in distances)
    return [row for d, row in distances if best <= max_metres and abs(d-best) < 1e-6]


def fixture_records(source):
    """Pure fixture adapter execution; no runner/fetch, live reads, or run-log writes."""
    ad = adapter.load(source)
    ctx = RunContext("fixture", datetime(2026, 1, 1, tzinfo=timezone.utc),
                     CallBudget.for_adapter(source, datetime(2026, 1, 1, tzinfo=timezone.utc)), adapter.adapter_dir(source))
    queue = deque(ad.plan(ctx)); records = []
    while queue:
        raw = adapter.read_fixture(source, queue.popleft())
        queue.extendleft(reversed(ad.follow_up(raw, ctx)))
        records.extend(ad.normalize(raw))
    return [r.model_dump(mode="json") for r in ad.finalize(records)]


def source_records(source):
    target = canonical.path_for("area_feature", source)
    if target.is_file():
        def stream():
            with gzip.open(target, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield json.loads(line)
        return stream(), False
    return iter(fixture_records(source)), True


def harmonize(record, parcel):
    p = {key: record["properties"].get(key) for key in KEEP}
    for field in ("market_value", "land_value", "improvement_value", "value_year", "living_area", "year_built", "land_acres", "floors"):
        value = p[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError("homes: invalid numeric property")
    p.update(id=record["feature_id"], lon=None, lat=None, block_group=None, tract=None, placed=None)
    if parcel is not None:
        point = parcel["geometry"]
        if point.get("type") != "Point" or len(point.get("coordinates", [])) != 2:
            raise ValueError("homes: invalid parcel point")
        lon, lat = point["coordinates"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lon, lat)) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("homes: invalid parcel coordinates")
        p.update(lon=lon, lat=lat, block_group=parcel["properties"].get("block_group"),
                 tract=parcel["properties"].get("tract"), placed="parcel")
    parts = address_parts(p)
    p.update(parts)
    p["city"] = p["situs_city"]
    p["address_key"] = address_key(parts)
    return p


def natural(value):
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", value or ""))


def matches(row, query):
    return (row[1] or "") == query["number"] and (row[2] or "") == query["street_key"] and all(
        not query[field] or (row[index] or "") == query[field] for field, index in (("unit", 3), ("zip", 4)))


def encoded(document):
    return json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()+b"\n"


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = encoded(document)
    path.write_bytes(data)
    return len(data)


def publish():
    """Validate in staging, then replace homes/; a failed build keeps its last good files."""
    check_properties("home shard", FIELDS)
    cfg = values.settings()
    hpi_records, hpi_fixture = source_records("fhfa_hpi")
    hpi = values.hpi_factor(hpi_records, "2026-01-01")
    range_counties, hood_rows = {}, []
    parcels = {}; parcel_dates = defaultdict(set)
    parcel_records, parcel_fixture = source_records("parcels")
    for r in parcel_records:
        if r["dataset"] != "parcel":
            continue
        identity = r["feature_id"]
        if identity in parcels:
            raise ValueError("homes: duplicate parcel id")
        parcels[identity] = {"geometry": r["geometry"], "properties": {k:r["properties"].get(k) for k in ("block_group", "tract")}}
        if r["properties"].get("parcel_as_of"):
            parcel_dates[r["properties"]["county"]].add(r["properties"]["parcel_as_of"])
    buckets = defaultdict(list); seen = set(); meta_counties = {}; descriptions = {}
    for county, (source, fips, threshold) in COUNTIES.items():
        inputs, fixture = source_records(source)
        test_data = fixture or parcel_fixture
        categories, placed_categories, unplaced_categories = Counter(), Counter(), Counter()
        source_dates, certified_dates, value_dates = set(), set(), set()
        expected = None; eligible = misses = placed = 0; hoods = {}
        value_rows = []
        for r in inputs:
            if r["dataset"] == "run_summary":
                if expected is not None:
                    raise ValueError("homes: duplicate county summary")
                expected = r["properties"]["kept"]
                continue
            if r["dataset"] != "property":
                continue
            identity = r["feature_id"]
            if identity in seen or not identity.startswith(fips+":") or r["properties"]["county"] != county or identity != fips+":"+r["properties"]["prop_id"]:
                raise ValueError("homes: duplicate or inconsistent home id")
            seen.add(identity)
            p = harmonize(r, parcels.get(identity))
            value_home = {key:p.get(key) for key in values.HOME_INPUTS}
            value_home["partial_owner"] = r["properties"].get("partial_owner") if source == "tcad" else None
            if value_home["partial_owner"] is not None and type(value_home["partial_owner"]) is not bool:
                raise ValueError("homes: invalid internal property-share indicator")
            categories[p["category"]] += 1
            (placed_categories if p["placed"] else unplaced_categories)[p["category"]] += 1
            placed += p["placed"] is not None
            query = normalize_query(p["situs"])
            row = [p.get(field) if p.get(field) != "" else None for field in FIELDS]
            # Only these fixed columns are published, never the original properties dictionary.
            if p["number"]:
                eligible += 1
                misses += not matches(row, query)
            buckets[shard_id(p["street_key"])].append(row)
            value_rows.append((row,value_home))
            code = p["hood_cd"]
            desc = r["properties"].get("hood_desc")
            if code and desc:
                # Pick a deterministic description when a code has spelling variations.
                hoods[code] = min(hoods.get(code, desc), desc)
            if r.get("source_as_of"):source_dates.add(r["source_as_of"])
            if p["certified"]:certified_dates.add(p["certified"])
            if r["properties"].get("value_as_of"):value_dates.add(r["properties"]["value_as_of"])
        count = sum(categories.values())
        if not isinstance(expected, int) or isinstance(expected, bool) or expected != count:
            raise ValueError("homes: county home count differs from run summary")
        if not test_data and placed*100 < threshold*count:
            raise ValueError("homes: county placement below required share")
        if misses*100 > eligible:
            raise ValueError(f"homes: round-trip misses exceed 1 percent for {county} - {misses} of {eligible}")
        meta_counties[county] = {"source": source, "source_as_of": sorted(source_dates), "value_as_of": sorted(value_dates),
            "certified": sorted(certified_dates), "parcel_as_of": sorted(parcel_dates[county]), "test_data": test_data,
            "homes": count, "placed": placed, "unplaced": count-placed,
            "by_category": dict(categories), "placed_by_category": dict(placed_categories), "unplaced_by_category": dict(unplaced_categories),
            "round_trip_eligible": eligible, "round_trip_misses": misses}
        if value_dates and value_dates != {"2026-01-01"}:
            raise ValueError("homes: value dates differ from the HPI base date")
        annotations, stats, range_summary = values.prepare(
            [home for _,home in value_rows], hpi["factor"], cfg, test_data=fixture)
        limits = values.size_bounds([home for _,home in value_rows],cfg)
        for (row,home),(pct,codes) in zip(value_rows,annotations):
            row[-2:] = [pct,codes]
            values.validate_annotation(home,row[-2],row[-1],limits,cfg)
        range_counties[county] = range_summary
        hood_rows.extend(stats)
        descriptions[county] = hoods
    del parcels, value_rows
    range_test_data = hpi_fixture or any(c["test_data"] for c in meta_counties.values())
    range_meta = values.metadata(cfg,hpi,range_test_data,range_counties)
    folder = paths().web_public/"data";folder.mkdir(parents=True, exist_ok=True)
    target = folder/"homes"
    with tempfile.TemporaryDirectory(prefix=".homes-", dir=folder) as temporary:
        stage = Path(temporary)/"homes";stage.mkdir()
        shards = {}; grid = defaultdict(list); sizes = {}
        for base, rows in sorted(buckets.items()):
            rows.sort(key=lambda row:(row[2] or "", natural(row[1]), natural(row[3]), row[0]))
            test = any(meta_counties[row[7]]["test_data"] for row in rows)
            document = {"v":1, "test_data":test, "fields":FIELDS, "rows":rows}
            groups = {base:rows}
            if len(encoded(document)) > MAX_SHARD_BYTES:
                groups = defaultdict(list)
                for row in rows:groups[base+"-"+shard_third(row[2])].append(row)
            shards[base] = sorted(groups)
            for shard, group in sorted(groups.items()):
                sizes[shard] = write_json(stage/"addr"/(shard+".json"), {"v":1,
                    "test_data":any(meta_counties[row[7]]["test_data"] for row in group), "fields":FIELDS, "rows":group})
                for row in group:
                    if row[22] == "parcel":
                        grid[cell_id(row[9],row[10])].append([row[0],row[9],row[10],shard])
        for cell, rows in sorted(grid.items()):
            write_json(stage/"grid"/(cell+".json"), {"v":1, "test_data":any(meta_counties[county_from_id(row[0])]["test_data"] for row in rows),
                "rows":sorted(rows)})
        write_json(stage/"hoods.json", {"v":1,"test_data":range_test_data,"rows":hood_rows})
        metadata = {"v":1, "test_data":any(c["test_data"] for c in meta_counties.values()), "counties":meta_counties,
            "sources":{"parcels":"TxGIO StratMap 2026 (CC0-1.0)", "tcad":"Travis Central Appraisal District",
                       "wcad":"Williamson Central Appraisal District", "hays_cad":"Hays Central Appraisal District"},
            "hood_desc":descriptions, "shards":shards, "cells":sorted(grid), "shard_count":len(sizes),
            "largest_shard_bytes":max(sizes.values(), default=0), "value_range":range_meta}
        write_json(stage/"meta.json",metadata)
        total = sum(file.stat().st_size for file in stage.rglob("*.json"))
        if total >= MAX_TOTAL_BYTES:
            raise ValueError(f"homes: total output {total} bytes exceeds size limit")
        # Renames are on one filesystem. Roll back if the second rename fails.
        backup = Path(temporary)/"previous"
        if target.exists():os.replace(target,backup)
        try:os.replace(stage,target)
        except BaseException:
            if backup.exists():os.replace(backup,target)
            raise
    report = {"bytes":total,"shard_count":len(sizes),"largest_shard_bytes":metadata["largest_shard_bytes"],"counties":meta_counties,"value_range":range_meta}
    print("homes: "+json.dumps(report, sort_keys=True))
    return metadata


def county_from_id(identity):
    return next(county for county, (_, fips, _) in COUNTIES.items() if identity.startswith(fips+":"))
