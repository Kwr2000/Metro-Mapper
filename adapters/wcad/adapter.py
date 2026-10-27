"""WCAD 2026 certified facts, selected explicitly and aggregated without personal data."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import gzip
import json
from pathlib import Path
import re
import resource
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.paths import paths
from mm.schemas import AreaFeature

PAGE_SIZE = 100000
AS_OF = date(2026, 1, 1)
EMPTY = {"type": "GeometryCollection", "geometries": []}
DATASETS = {"property": "ai3c-c9pf", "improvement": "2huh-jk3y", "segment": "xs93-mfpk", "land": "bens-i2m7"}
COLUMNS = {
    "property": ("propertyid", "quickrefid", "propertytypecode", "neighborhoodcode", "neighborhooddesc",
        "totalpropmktvalue", "totallandmktvalue", "totalimpmktvalue", "totalsqftlivingarea", "streetnumber",
        "streetdirectional", "streetname", "streetsuffix", "streetsuffixdirectional", "unitnumber", "city", "zip",
        "condobuilding", "condounit", "datadate"),
    "improvement": ("propertyid", "fsptb", "vtsgimp_impvalue"),
    "segment": ("propertyid", "fsegtype", "farea", "factyear"),
    "land": ("propertyid", "acres", "sqft"),
}
WHERE = {"property": "tax_year=2026", "improvement": "adhoctaxyear=2026",
         "segment": "adhoctaxyear=2026 AND fsegtype in('MA','MA2','MA3','MA4')", "land": "adhoctaxyear=2026"}
MAIN = {"MA", "MA2", "MA3", "MA4"}
CATEGORIES = {"A1": "single_family", "A9": "single_family", "A8": "condo", "A2": "mobile_home", "A5": "mobile_home",
    "B2": "two_to_four_units", "B3": "two_to_four_units", "B4": "two_to_four_units", "E1": "rural_home",
    "E2": "rural_home", "O1": "builder_inventory"}
NUMERIC = {"property": ("propertyid", "totalpropmktvalue", "totallandmktvalue", "totalimpmktvalue", "totalsqftlivingarea"),
    "improvement": ("propertyid", "vtsgimp_impvalue"), "segment": ("propertyid", "farea", "factyear"),
    "land": ("propertyid", "acres", "sqft")}


def number(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("WCAD numeric cells must be strings")
    try:
        result = Decimal(value.strip())
    except InvalidOperation:
        raise ValueError("WCAD nonnumeric cell") from None
    if not result.is_finite() or result < 0:
        raise ValueError("WCAD invalid numeric cell")
    return result


def integer(value):
    result = number(value)
    if result is None or result != result.to_integral_value():
        raise ValueError("WCAD missing or nonintegral identifier/count/year")
    return int(result)


def text(row, field):
    value = row.get(field)
    return value.strip() or None if value is not None else None


def request(kind, page=None):
    if kind not in DATASETS or (page is not None and (type(page) is not int or page < 0)):
        raise ValueError("WCAD unexpected dataset/page")
    query = {"$where": WHERE[kind]}
    if page is None:
        # Without an alias the portal names this column "count_distinct_propertyid" (checked
        # 2026-10-26); the alias makes the key explicit.
        query["$select"] = "count(distinct propertyid) AS count_propertyid" if kind == "land" else "count(*)"
        key = kind + "_count"
    else:
        query.update({"$select": "propertyid, sum(faclandsize) AS acres, sum(fsftlandsize) AS sqft" if kind == "land" else ",".join(COLUMNS[kind]),
            "$order": "propertyid" if kind == "land" else "propertyid,:id", "$limit": PAGE_SIZE, "$offset": page*PAGE_SIZE})
        if kind == "land":
            query["$group"] = "propertyid"
        key = f"{kind}_p{page}"
    return Request(key, {"kind": kind, "page": page, "query": query})


def validate_request(req):
    if not isinstance(req.params, dict):
        raise ValueError("WCAD invalid request")
    kind, page = req.params.get("kind"), req.params.get("page")
    expected = request(kind, page)
    if req.key != expected.key or req.params != expected.params:
        raise ValueError("WCAD request outside dataset/select allowlist")
    return kind, page


def selected_body(req, body):
    kind, page = validate_request(req)
    if not isinstance(body, list):
        raise ValueError("WCAD expected a native array response")
    fields = ("count_propertyid" if kind == "land" else "count",) if page is None else COLUMNS[kind]
    output = []
    for row in body:
        if not isinstance(row, dict):
            raise ValueError("WCAD expected native row objects")
        # Extra response fields are never accessed, copied, recorded or logged.
        safe = {field: row[field] for field in fields if field in row}
        if any(not isinstance(value, str) for value in safe.values()):
            raise ValueError("WCAD native cells must be strings; null cells must be omitted")
        output.append(safe)
    return output


def volume_checks(distinct, kept):
    if abs(distinct-319443) > Decimal(".02")*319443:
        raise ValueError("WCAD distinct property IDs outside 2% of 319,443")
    if not 215000 <= kept <= 255000:
        raise ValueError("WCAD kept count outside 215,000–255,000")


def quality_counts(properties):
    categories = Counter()
    living = year_built = lots = cohort = covered = both = agree = 0
    for p in properties:
        categories[p["category"]] += 1
        has_living = p["living_area"] is not None
        living += has_living
        year_built += p["year_built"] is not None
        lots += p["land_acres"] is not None
        if p["category"] in {"single_family", "condo"}:
            cohort += 1
            covered += has_living
        if has_living and p["ma_area"] is not None:
            both += 1
            agree += abs(Decimal(str(p["living_area"]))-Decimal(str(p["ma_area"]))) <= 1
    total = len(properties)
    return {"kept": total, "kept_by_category": dict(sorted(categories.items())), "living_area_present": living,
        "living_area_share": living/total if total else None, "single_family_condo": cohort,
        "single_family_condo_with_living_area": covered, "living_area_coverage": covered/cohort if cohort else None,
        "ma_comparable": both, "ma_agree": agree, "ma_agreement": agree/both if both else None,
        "year_built_present": year_built, "year_built_share": year_built/total if total else None,
        "lot_size_present": lots, "lot_size_share": lots/total if total else None}


def quality_checks(counts):
    if counts["single_family_condo_with_living_area"]*100 < counts["single_family_condo"]*97:
        raise ValueError("WCAD single-family/condo living-area coverage below 97%")
    if counts["ma_agree"]*100 < counts["ma_comparable"]*97:
        raise ValueError("WCAD living/main-area agreement below 97%")


def rank(value):
    return value if value is not None else Decimal(-1)


def acres(land):
    if land is None:
        return None
    area, sqft = land
    result = area if area is not None and area > 0 else sqft/43560 if sqft is not None and sqft > 0 else None
    result = round(result, 4) if result is not None else None
    return float(result) if result is not None and result > 0 else None


class WCAD(SourceAdapter):
    id = "wcad"
    entity = "area_feature"
    cadence = "annual"
    retain_raw = False
    recordable = False

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        self.started = time.monotonic()
        self.expected, self.fetched, self.next_page = {}, {}, {}
        self.completed, self.accepted, self.normalized = set(), set(), set()
        self.properties, self.improvements, self.segments, self.land = {}, {}, {}, {}
        self.repeated_rows, self.latest = 0, None
        self.last_property_id = {}
        return [request(kind) for kind in DATASETS]

    def fetch(self, req, ctx):
        kind, page = validate_request(req)
        url = "https://data.wcad.org/resource/" + DATASETS[kind] + ".json?" + urllib.parse.urlencode(req.params["query"])
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": self.user_agent}), timeout=180) as response:
                if response.status != 200:
                    return RawPayload(req, None, status=response.status)
                body = selected_body(req, json.load(response))
            return RawPayload(req, body)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception as exc:
            # No response text, source values or transport exception messages enter run logs.
            return RawPayload(req, {"error": f"WCAD fetch failed ({type(exc).__name__})"}, status=502)

    def follow_up(self, raw, ctx):
        kind, page = validate_request(raw.request)
        if raw.status != 200:
            raise ValueError(f"WCAD HTTP {raw.status}; source response withheld")
        if raw.request.key in self.accepted:
            raise ValueError("WCAD duplicate response")
        safe = selected_body(raw.request, raw.body)
        raw.body[:] = safe
        if page is None:
            field = "count_propertyid" if kind == "land" else "count"
            if len(safe) != 1:
                raise ValueError("WCAD invalid count response")
            self.expected[kind] = integer(safe[0].get(field))
            self.fetched[kind], self.next_page[kind] = 0, 0
            extra = [request(kind, 0)]
        else:
            if kind not in self.expected or page != self.next_page[kind] or kind in self.completed or len(safe) > PAGE_SIZE:
                raise ValueError("WCAD missing, unordered or oversized page")
            self.fetched[kind] += len(safe)
            if self.fetched[kind] > self.expected[kind]:
                raise ValueError("WCAD rows fetched differ from count")
            if len(safe) < PAGE_SIZE:
                if self.fetched[kind] != self.expected[kind]:
                    raise ValueError("WCAD rows fetched differ from count")
                self.completed.add(kind)
                extra = []
            else:
                self.next_page[kind] += 1
                extra = [request(kind, page+1)]
        self.accepted.add(raw.request.key)
        return extra

    def normalize(self, raw):
        kind, page = validate_request(raw.request)
        if raw.status != 200 or raw.request.key not in self.accepted or raw.request.key in self.normalized:
            raise ValueError("WCAD unvalidated or duplicate normalization input")
        rows = selected_body(raw.request, raw.body)
        if page is not None:
            for row in rows:
                pid = integer(row.get("propertyid"))
                if pid < self.last_property_id.get(kind, -1):
                    raise ValueError("WCAD pages are not ordered by property ID")
                self.last_property_id[kind] = pid
                values = {field: number(row.get(field)) for field in NUMERIC[kind]}
                if kind == "property":
                    stamp = text(row, "datadate")
                    if stamp:
                        try:
                            acquired = datetime.fromisoformat(stamp).date()
                        except ValueError:
                            raise ValueError("WCAD invalid datadate") from None
                        self.latest = max(self.latest, acquired) if self.latest else acquired
                    if pid in self.properties:
                        if self.properties[pid] != row:
                            raise ValueError("WCAD conflicting repeated property row")
                        self.repeated_rows += 1
                    else:
                        self.properties[pid] = row
                elif kind == "improvement":
                    code = text(row, "fsptb")
                    if code is not None and not re.fullmatch(r"[A-Z0-9]{1,10}", code):
                        raise ValueError("WCAD invalid state code")
                    candidate = (code, values["vtsgimp_impvalue"])
                    best = self.improvements.setdefault(pid, [None, None])
                    if best[0] is None or rank(candidate[1]) > rank(best[0][1]):
                        best[0] = candidate
                    if code in CATEGORIES and (best[1] is None or rank(candidate[1]) > rank(best[1][1])):
                        best[1] = candidate
                elif kind == "segment":
                    if text(row, "fsegtype") not in MAIN:
                        raise ValueError("WCAD non-main segment in filtered response")
                    built = integer(row["factyear"]) or None if "factyear" in row else None
                    area = values["farea"]
                    # [sum-or-None, largest-area-or-None, largest segment year, row count]
                    state = self.segments.setdefault(pid, [None, None, None, 0])
                    state[3] += 1
                    if area is not None:
                        state[0] = (state[0] or Decimal(0))+area
                        if state[1] is None or area > state[1]:
                            state[1], state[2] = area, built
                else:
                    if pid in self.land:
                        raise ValueError("WCAD repeated grouped land property")
                    self.land[pid] = (values["acres"], values["sqft"])
        self.normalized.add(raw.request.key)
        count = len(rows)
        raw.body.clear()  # Selected pages are aggregated once; never retained or recorded.
        yield AreaFeature(dataset="wcad_input", feature_id=raw.request.key, geometry=EMPTY, properties={"kind": kind, "rows": count})

    def finalize(self, records):
        if (self.completed != set(DATASETS) or self.normalized != self.accepted or
                {r.feature_id for r in records} != self.accepted or len(records) != len(self.accepted) or
                any(r.dataset != "wcad_input" for r in records)):
            raise ValueError("WCAD incomplete inputs")
        if self.latest is None:
            raise ValueError("WCAD missing property datadate")
        inputs = {"property": self.properties, "improvement": self.improvements, "segment": self.segments, "land": self.land}
        datasets = {kind: {"rows": self.fetched[kind], "distinct_ids": len(inputs[kind])} for kind in DATASETS}
        if any(self.fetched[k] != self.expected[k] for k in DATASETS):
            raise ValueError("WCAD rows fetched differ from count")
        output, skipped, quickrefs = [], Counter(), set()
        for pid in sorted(self.properties):
            row = self.properties.pop(pid)
            best = self.improvements.pop(pid, [None, None])
            code = best[1][0] if best[1] else None
            prop_type = text(row, "propertytypecode")
            if code is None:
                skipped[(best[0][0] or "(blank)") if best[0] else "no improvement"] += 1
                continue
            identity = text(row, "quickrefid")
            if identity is None or not re.fullmatch(r"R[0-9]+", identity) or identity in quickrefs:
                raise ValueError("WCAD missing, invalid or repeated quickrefid")
            quickrefs.add(identity)
            area = number(row.get("totalsqftlivingarea"))
            living = round(area) if area is not None else None
            segment = self.segments.pop(pid, [None, None, None, 0])
            p = {"county": "Williamson", "prop_id": identity, "wcad_property_id": pid, "geo_id": None,
                "category": CATEGORIES[code], "state_cd": code, "prop_type": prop_type,
                "hood_cd": text(row, "neighborhoodcode"), "hood_desc": text(row, "neighborhooddesc"),
                "subdivision_code": None, "subdivision": None, "value_year": 2026, "value_as_of": AS_OF.isoformat(),
                "certified": self.latest.isoformat(), "living_area": living if living is not None and living > 0 else None,
                "ma_area": float(round(segment[0], 6)) if segment[0] is not None else None,
                "year_built": segment[2], "floors": segment[3], "land_acres": acres(self.land.pop(pid, None)),
                "hvac_area": None, "adu_area": None, "dwelling_count": None, "has_adu": None,
                "deed_date": None, "partial_owner": None, "udi_group": None,
                "condo_building": text(row, "condobuilding")}
            for dest, field in {"market_value": "totalpropmktvalue", "land_value": "totallandmktvalue", "improvement_value": "totalimpmktvalue"}.items():
                value = number(row.get(field))
                p[dest] = round(value) if value is not None else None
            for dest, field in {"situs_number": "streetnumber", "situs_prefix": "streetdirectional", "situs_street": "streetname",
                    "situs_city": "city", "situs_zip": "zip"}.items():
                p[dest] = text(row, field)
            p["situs_suffix"] = " ".join(v for field in ("streetsuffix", "streetsuffixdirectional") if (v := text(row, field))) or None
            p["situs_unit"] = text(row, "unitnumber") or text(row, "condounit")
            p["situs"] = " ".join(p[k] for k in ("situs_number", "situs_prefix", "situs_street", "situs_suffix", "situs_unit", "situs_city", "situs_zip") if p[k]) or None
            output.append(AreaFeature(dataset="property", feature_id="48491:"+identity, geometry=EMPTY, properties=p, source_as_of=AS_OF))
        if not output:
            raise ValueError("WCAD no kept properties")
        if self.live:
            volume_checks(datasets["property"]["distinct_ids"], len(output))
        quality = quality_counts([r.properties for r in output])
        quality_checks(quality)
        matched = None
        parcel_path = paths().canonical/"area_feature/parcels.ndjson.gz"
        if self.live and parcel_path.is_file():
            found = set()
            with gzip.open(parcel_path, "rt", encoding="utf-8") as source:
                for line in source:
                    rec = json.loads(line)
                    if rec["dataset"] == "parcel" and rec["properties"]["county"] == "Williamson":
                        identity = rec["properties"]["prop_id"]
                        if identity in quickrefs:
                            found.add(identity)
            matched = len(found)
        summary = {"datasets": datasets, "repeated_rows": self.repeated_rows, **quality,
            "skipped_by_code": dict(sorted(skipped.items())), "parcel_matches": matched,
            "parcel_match_share": matched/len(output) if matched is not None else None,
            "runtime_seconds": round(time.monotonic()-self.started, 3),
            "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1)}
        print("wcad: run note: " + json.dumps(summary, sort_keys=True), file=sys.stderr)
        return [*output, AreaFeature(dataset="run_summary", feature_id="2026", geometry=EMPTY, properties=summary, source_as_of=AS_OF)]

    def source_as_of(self, raws):
        return AS_OF


ADAPTER = WCAD
