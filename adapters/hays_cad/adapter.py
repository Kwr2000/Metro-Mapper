"""Hays monthly 2026 export: header discovery and allowlisted CSV projection only."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import json
from pathlib import Path
import re
import resource
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from zipfile import ZipFile

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.paths import paths
from mm.schemas import AreaFeature

URL = "https://hayscad.com/wp-content/uploads/2026/10/2026-PROPERTY-DATA-EXPORT-FILES-AS-OF-10-19-2026.zip"
AS_OF = date(2026, 1, 1)
CERTIFIED = "2026-10-19"
CODE = r"[A-Z0-9][A-Z0-9.-]{0,15}"
EMPTY = {"type": "GeometryCollection", "geometries": []}
COLUMNS = {
    "property": ("PropertyID", "QuickRefID", "CurrMarketValue", "CurrLandValue", "CurrImprovmentValue",
        "SquareFootage", "NbhdCode", "NbhdDesc", "SitusPreDirectional", "SitusStreetNumber",
        "SitusStreetName", "SitusStreetSuffix", "SitusPostDirectional", "SitusCity", "SitusZip", "LegalAcres"),
    "improvement": ("PropertyID", "InstanceID", "Type", "StateCode", "ImpValue"),
    "segment": ("PropertyID", "InstanceID", "Type", "Area", "ActYrBuilt"),
    "land": ("PropertyID", "Acres", "SquareFeet"),
}
KINDS = {*COLUMNS, "owner", "sales"}
CATEGORIES = {("A", "R"): "single_family", ("A1", "R"): "single_family",
    ("A", "M"): "mobile_home", ("A5", "M"): "mobile_home", ("B", "R"): "two_to_four_units",
    ("E", "R"): "rural_home", ("E", "M"): "rural_home", ("O", "R"): "builder_inventory"}
DERIVED = {"StateCode", "Type", "ma_area", "year_built", "floors", "land_acres"}
SUMMARY_FIELDS = {"rows_by_file", "distinct_property_ids", "repeated_rows", "conflicting_ids",
                  "skipped_by_code", "invalid_quickref"}


def number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Hays invalid numeric cell")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Hays invalid numeric cell") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Hays invalid numeric cell")
    return result


def integer(value):
    result = number(value)
    if result is None or result != result.to_integral_value():
        raise ValueError("Hays invalid integer cell")
    return int(result)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value.strip()):
        raise ValueError("Hays invalid property identifier")
    return str(int(value.strip()))


def text(row, field):
    value = row[field]
    if not isinstance(value, str):
        raise ValueError("Hays native cells must be strings")
    return value.strip() or None


def file_kind(header):
    markers = {"property": "CurrMarketValue", "segment": "ActYrBuilt", "land": "LandType",
               "owner": "OwnerName", "sales": "PrevOwnerName"}
    kinds = [kind for kind, field in markers.items() if field in header]
    if "ImpValue" in header and "ActYrBuilt" not in header:
        kinds.append("improvement")
    if len(kinds) != 1 or len(set(header)) != len(header):
        raise ValueError("Hays unknown or ambiguous CSV header")
    kind = kinds[0]
    if kind in COLUMNS and not set(COLUMNS[kind]) <= set(header):
        raise ValueError("Hays missing required CSV columns")
    return kind


def selected_rows(source, header, kind):
    """Parse CSV structure as bytes; buffer/decode ONLY selected cell contents.

    Unlike DictReader, this never materializes LegalDesc, Situs or any other unused
    cell. Quotes/delimiters in discarded cells still determine the CSV structure.
    Header is already consumed. Owner/sales streams never enter this function.
    """
    selected = {header.index(field): field for field in COLUMNS[kind]}
    row, cell, index = {}, bytearray(), 0
    state, active = "start", False

    def finish_cell():
        nonlocal cell, index, state
        if index in selected:
            row[selected[index]] = cell.decode("latin-1")
        cell = bytearray()
        index += 1
        state = "start"

    for line in source:
        # Iteration keeps multiline quoted fields intact across physical lines.
        for char in line:
            if state == "quoted":
                if char == 34:
                    state = "closed"
                elif index in selected:
                    cell.append(char)
                continue
            if state == "closed" and char == 34:
                if index in selected:
                    cell.append(34)
                state = "quoted"
                continue
            if char in (44, 10, 13):
                if char == 13:  # Ignore CR in CRLF outside quoted cells.
                    continue
                if not active and char == 10:
                    continue
                finish_cell()
                if char == 10:
                    if index != len(header):
                        raise ValueError("Hays CSV column count mismatch")
                    yield row
                    row, index, active = {}, 0, False
                else:
                    active = True
                continue
            if state == "closed" or char == 34 and state != "start":
                raise ValueError("Hays malformed CSV quoting")
            active = True
            if char == 34:
                state = "quoted"
            else:
                state = "plain"
                if index in selected:
                    cell.append(char)
    if state == "quoted":
        raise ValueError("Hays unterminated CSV quote")
    if active:
        finish_cell()
        if index != len(header):
            raise ValueError("Hays CSV column count mismatch")
        yield row


def rank(value):
    return value if value is not None else Decimal(-1)


def rounded_positive(value, digits):
    rounded = round(value, digits) if value is not None else None
    return float(rounded) if rounded is not None and rounded > 0 else None


def parse_export(path):
    properties, improvements, segments, land = {}, {}, {}, {}
    conflicts = set()
    repeated = 0
    counts = {}
    # Nested archives need seekable storage, but members are never extracted.
    with ZipFile(path) as outer:
        nested = [info for info in outer.infolist() if not info.is_dir()]
        if len(nested) != 6:
            raise ValueError("Hays expected six nested ZIPs")
        for info in nested:
            with tempfile.TemporaryFile(dir=Path(path).parent) as temporary:
                with outer.open(info) as source:
                    shutil.copyfileobj(source, temporary, length=1024*1024)
                temporary.seek(0)
                with ZipFile(temporary) as inner:
                    members = [item for item in inner.infolist() if not item.is_dir()]
                    if len(members) != 1:
                        raise ValueError("Hays expected one CSV per nested ZIP")
                    with inner.open(members[0]) as source:
                        # Exactly one physical read for discovery; no TextIOWrapper read-ahead.
                        header = next(csv.reader([source.readline().decode("latin-1").rstrip("\r\n")], strict=True), [])
                        kind = file_kind(header)
                        if kind in counts:
                            raise ValueError("Hays duplicate file kind")
                        counts[kind] = None if kind in {"owner", "sales"} else 0
                        if kind in {"owner", "sales"}:
                            continue  # Never iterate, decode or count private rows.
                        for row in selected_rows(source, header, kind):
                            counts[kind] += 1
                            pid = identifier(row["PropertyID"])
                            if kind == "property":
                                if pid in properties:
                                    repeated += 1
                                    if properties[pid] != row:
                                        conflicts.add(pid)
                                else:
                                    properties[pid] = row
                            elif kind == "improvement":
                                code, typ = text(row, "StateCode"), text(row, "Type")
                                for value in (code, typ):
                                    # Real exempt codes carry a statute suffix, e.g. "XE-11.182" (probe 2026-10-27).
                                    if value is not None and not re.fullmatch(CODE, value):
                                        raise ValueError("Hays invalid classification code")
                                candidate = (code, typ, number(row["ImpValue"]))
                                best = improvements.setdefault(pid, [None, None])
                                if best[0] is None or rank(candidate[2]) > rank(best[0][2]):
                                    best[0] = candidate
                                if (code, typ) in CATEGORIES and (best[1] is None or rank(candidate[2]) > rank(best[1][2])):
                                    best[1] = candidate
                            elif kind == "segment":
                                if not (text(row, "Type") or "").startswith("MA"):
                                    continue
                                area = number(row["Area"])
                                built = integer(row["ActYrBuilt"]) or None if row["ActYrBuilt"].strip() else None
                                state = segments.setdefault(pid, [None, None, None, 0])
                                state[3] += 1
                                if area is not None:
                                    state[0] = (state[0] or Decimal(0)) + area
                                    if state[1] is None or area > state[1]:
                                        state[1], state[2] = area, built
                            else:
                                state = land.setdefault(pid, [Decimal(0), Decimal(0)])
                                state[0] += number(row["Acres"]) or 0
                                state[1] += number(row["SquareFeet"]) or 0
    if set(counts) != KINDS:
        raise ValueError("Hays missing required file kind")
    skipped, output, identities = Counter(), [], set()
    invalid_quickref = 0
    for pid, row in properties.items():
        if pid in conflicts:
            continue
        best = improvements.get(pid, [None, None])
        chosen = best[1]
        if chosen is None:
            code, typ = best[0][:2] if best[0] else (None, None)
            skipped[(code or "(blank)")+"|"+(typ or "(blank)")] += 1
            continue
        quickref = text(row, "QuickRefID")
        if quickref is None or not re.fullmatch(r"R[0-9]+", quickref):
            invalid_quickref += 1
            continue
        identity = quickref[1:]
        if identity in identities:
            raise ValueError("Hays repeated QuickRefID digits")
        identities.add(identity)
        main = segments.get(pid, [None, None, None, 0])
        acres, sqft = land.get(pid, [Decimal(0), Decimal(0)])
        legal = number(row["LegalAcres"])
        lot = acres if acres > 0 else sqft/43560 if sqft > 0 else legal if legal and legal > 0 else None
        output.append({**row, "StateCode": chosen[0], "Type": chosen[1],
            "ma_area": float(round(main[0], 6)) if main[0] is not None else None,
            "year_built": main[2], "floors": main[3], "land_acres": rounded_positive(lot, 4)})
    return {"properties": output, "summary": {"rows_by_file": counts, "distinct_property_ids": len(properties),
        "repeated_rows": repeated, "conflicting_ids": len(conflicts), "skipped_by_code": dict(sorted(skipped.items())),
        "invalid_quickref": invalid_quickref}}


def normalize_property(row):
    if not isinstance(row, dict) or set(row) != set(COLUMNS["property"]) | DERIVED:
        raise ValueError("Hays invalid compact property columns")
    for field in (*COLUMNS["property"], "StateCode", "Type"):
        text(row, field)
    quickref = text(row, "QuickRefID")
    key = (text(row, "StateCode"), text(row, "Type"))
    if quickref is None or not re.fullmatch(r"R[0-9]+", quickref) or key not in CATEGORIES:
        raise ValueError("Hays invalid kept property")
    living = number(row["SquareFootage"])
    p = {"county": "Hays", "prop_id": quickref[1:], "quickrefid": row["QuickRefID"],
        "hays_property_id": int(identifier(row["PropertyID"])), "geo_id": None, "category": CATEGORIES[key],
        "state_cd": key[0], "prop_type": key[1], "hood_cd": text(row, "NbhdCode"), "hood_desc": text(row, "NbhdDesc"),
        "subdivision_code": None, "subdivision": None, "value_year": 2026, "value_as_of": AS_OF.isoformat(),
        "certified": CERTIFIED, "living_area": int(round(living)) if living is not None and round(living) > 0 else None,
        "ma_area": float(number(row["ma_area"])) if row["ma_area"] is not None else None,
        "year_built": integer(row["year_built"]) or None if row["year_built"] is not None else None,
        "floors": integer(row["floors"]), "land_acres": rounded_positive(number(row["land_acres"]), 4),
        "hvac_area": None, "adu_area": None, "dwelling_count": None, "has_adu": None,
        "deed_date": None, "partial_owner": None, "udi_group": None, "situs_unit": None}
    for dest, source in {"market_value": "CurrMarketValue", "land_value": "CurrLandValue", "improvement_value": "CurrImprovmentValue"}.items():
        value = number(row[source])
        p[dest] = round(value) if value is not None else None
    for dest, source in {"situs_number": "SitusStreetNumber", "situs_prefix": "SitusPreDirectional",
            "situs_street": "SitusStreetName", "situs_city": "SitusCity", "situs_zip": "SitusZip"}.items():
        p[dest] = text(row, source)
    p["situs_suffix"] = " ".join(v for field in ("SitusStreetSuffix", "SitusPostDirectional") if (v := text(row, field))) or None
    p["situs"] = " ".join(p[k] for k in ("situs_number", "situs_prefix", "situs_street", "situs_suffix", "situs_unit", "situs_city", "situs_zip") if p[k]) or None
    return p


def volume_checks(rows, kept):
    if abs(rows - 134553) > Decimal(".02") * 134553:
        raise ValueError("Hays property rows outside 2% of 134553")
    if not 82000 <= kept <= 100000:
        raise ValueError("Hays kept count outside 82000 to 100000")


def quality_counts(properties):
    cats = Counter()
    living = eligible = covered = both = agree = built = lots = 0
    for p in properties:
        cats[p["category"]] += 1
        has_living = p["living_area"] is not None
        living += has_living
        built += p["year_built"] is not None
        lots += p["land_acres"] is not None
        if p["category"] == "single_family":
            eligible += 1
            covered += has_living
        if has_living and p["ma_area"] is not None:
            both += 1
            agree += abs(Decimal(str(p["living_area"])) - Decimal(str(p["ma_area"]))) <= 1
    total = len(properties)
    return {"kept": total, "kept_by_category": dict(sorted(cats.items())), "living_area_present": living,
        "living_area_share": living/total if total else None, "single_family": eligible,
        "single_family_with_living_area": covered, "living_area_coverage": covered/eligible if eligible else None,
        "ma_comparable": both, "ma_agree": agree, "ma_agreement": agree/both if both else None,
        "year_built_present": built, "year_built_share": built/total if total else None,
        "lot_size_present": lots, "lot_size_share": lots/total if total else None}


def quality_checks(counts):
    if counts["single_family_with_living_area"] * 100 < counts["single_family"] * 95:
        raise ValueError("Hays single-family living-area coverage below 95 percent")
    if counts["ma_agree"] * 100 < counts["ma_comparable"] * 95:
        raise ValueError("Hays living and main-area agreement below 95 percent")


class HaysCAD(SourceAdapter):
    id = "hays_cad"
    entity = "area_feature"
    cadence = "annual"
    retain_raw = False
    recordable = False

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        self.started = time.monotonic()
        return [Request("hays_cad_2026", {"url": URL})]

    def fetch(self, req, ctx):
        if req != Request("hays_cad_2026", {"url": URL}):
            raise ValueError("Hays unexpected request")
        try:
            paths().raw.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="hays-cad-", dir=paths().raw) as folder:
                archive = Path(folder)/"download.zip"
                request = urllib.request.Request(URL, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(request, timeout=180) as response:
                    if response.status != 200:
                        return RawPayload(req, None, status=response.status)
                    with archive.open("wb") as target:
                        shutil.copyfileobj(response, target, length=1024*1024)
                    length = response.headers.get("Content-Length")
                    if length is not None and archive.stat().st_size != int(length):
                        raise ValueError("Hays incomplete download")
                body = parse_export(archive)
            return RawPayload(req, body)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception as exc:
            # No source cells or arbitrary exception text enter public run logs.
            return RawPayload(req, {"error": "Hays download or parse failed", "error_type": type(exc).__name__}, status=502)

    def follow_up(self, raw, ctx):
        if raw.status != 200:
            raise ValueError("Hays failed response withheld")
        return []

    def normalize(self, raw):
        if raw.status != 200 or raw.request != Request("hays_cad_2026", {"url": URL}):
            raise ValueError("Hays failed or unexpected response")
        body = raw.body
        if not isinstance(body, dict) or set(body) != {"properties", "summary"} or not isinstance(body["properties"], list):
            raise ValueError("Hays invalid compact body")
        counts = body["summary"]
        if not isinstance(counts, dict) or set(counts) != SUMMARY_FIELDS or set(counts["rows_by_file"]) != KINDS:
            raise ValueError("Hays invalid compact summary")
        for row in body["properties"]:
            p = normalize_property(row)
            yield AreaFeature(dataset="property", feature_id="48209:"+p["prop_id"], geometry=EMPTY, properties=p, source_as_of=AS_OF)
        clean = {k: integer(v) for k, v in counts.items() if k not in {"rows_by_file", "skipped_by_code"}}
        clean["rows_by_file"] = {k: integer(counts["rows_by_file"][k]) for k in COLUMNS}
        if any(counts["rows_by_file"][k] is not None for k in ("owner", "sales")):
            raise ValueError("Hays private row counts must be unavailable")
        clean["rows_by_file"].update(owner=None, sales=None)
        clean["skipped_by_code"] = {}
        for code, count in counts["skipped_by_code"].items():
            if not isinstance(code, str) or not re.fullmatch(rf"(?:{CODE}|\(blank\))\|(?:{CODE}|\(blank\))", code):
                raise ValueError("Hays invalid skip code")
            clean["skipped_by_code"][code] = integer(count)
        yield AreaFeature(dataset="hays_input_summary", feature_id="2026", geometry=EMPTY, properties=clean)

    def finalize(self, records):
        properties = [r for r in records if r.dataset == "property"]
        summaries = [r for r in records if r.dataset == "hays_input_summary"]
        if len(summaries) != 1 or len(records) != len(properties)+1 or not properties or len({r.feature_id for r in properties}) != len(properties):
            raise ValueError("Hays missing or duplicate property and summary inputs")
        counts = summaries[0].properties
        if (counts["rows_by_file"]["property"] != counts["distinct_property_ids"] + counts["repeated_rows"] or
                counts["distinct_property_ids"] != len(properties) + sum(counts["skipped_by_code"].values()) + counts["invalid_quickref"] + counts["conflicting_ids"]):
            raise ValueError("Hays counts do not reconcile")
        if self.live:
            volume_checks(counts["rows_by_file"]["property"], len(properties))
        quality = quality_counts([r.properties for r in properties])
        quality_checks(quality)
        identities = {r.properties["prop_id"] for r in properties}
        matched = None
        parcel_path = paths().canonical/"area_feature/parcels.ndjson.gz"
        if self.live and parcel_path.is_file():
            found = set()
            with gzip.open(parcel_path, "rt", encoding="utf-8") as source:
                for line in source:
                    r = json.loads(line)
                    if r["dataset"] == "parcel" and r["properties"]["county"] == "Hays" and r["properties"]["prop_id"] in identities:
                        found.add(r["properties"]["prop_id"])
            matched = len(found)
        summary = {**counts, **quality, "parcel_matches": matched,
            "parcel_match_share": matched/len(properties) if matched is not None else None,
            "runtime_seconds": round(time.monotonic()-self.started, 3),
            "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1)}
        print("hays_cad: run note: " + json.dumps(summary, sort_keys=True), file=sys.stderr)
        return [*properties, AreaFeature(dataset="run_summary", feature_id="2026", geometry=EMPTY, properties=summary, source_as_of=AS_OF)]

    def source_as_of(self, raws):
        return AS_OF


ADAPTER = HaysCAD
