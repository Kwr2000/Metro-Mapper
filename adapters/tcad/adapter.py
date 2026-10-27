"""TCAD certified 2026 property facts; only allowlisted fixed-width cells are decoded."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import gzip
import json
import math
from pathlib import Path
import re
import resource
import sys
import tempfile
import time
import urllib.error
import urllib.request
from zipfile import ZipFile

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.paths import paths
from mm.schemas import AreaFeature

URL = "https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip"
EMPTY = {"type": "GeometryCollection", "geometries": []}
AS_OF = date(2026, 1, 1)
CERTIFIED = "2026-07-18"
LENGTHS = {"TOTALS.TXT": 2491, "ABS_SUBD.TXT": 50, "IMP_INFO.TXT": 114, "IMP_DET.TXT": 622, "PROP.TXT": 9922}
# Publisher positions, 1-based inclusive. This is the entire slicing/decoding allowlist.
RANGES = {
    "PROP.TXT": {
        "prop_id": (1,12), "prop_type_cd": (13,17), "prop_val_yr": (18,22), "sup_num": (23,34),
        "geo_id": (547,596), "partial_owner": (679,679), "udi_group": (680,691),
        "situs_street_prefx": (1040,1049), "situs_street": (1050,1099), "situs_street_suffix": (1100,1109),
        "situs_city": (1110,1139), "situs_zip": (1140,1149), "abs_subdv_cd": (1676,1685), "hood_cd": (1686,1695),
        "land_hstd_val": (1796,1810), "land_non_hstd_val": (1811,1825),
        "imprv_hstd_val": (1826,1840), "imprv_non_hstd_val": (1841,1855), "deed_dt": (2034,2058),
        "imprv_state_cd": (2732,2741), "land_state_cd": (2742,2751), "land_acres": (2772,2791),
        "market_value": (4214,4227), "situs_num": (4460,4474), "situs_unit": (4475,4479)},
    "IMP_INFO.TXT": {"prop_id": (1,12), "prop_val_yr": (13,16), "imprv_id": (17,28), "imprv_type_cd": (29,38)},
    "IMP_DET.TXT": {"prop_id": (1,12), "prop_val_yr": (13,16), "imprv_id": (17,28),
        "imprv_det_type_cd": (41,50), "yr_built": (86,89), "imprv_det_area": (94,108)},
    "ABS_SUBD.TXT": {"abs_subdv_cd": (1,10), "abs_subdv_desc": (11,50)},
    "TOTALS.TXT": {"entity_cd": (13,17), "num_real_mobile": (283,294), "sup_num": (809,820)},
}
FLOORS = ("1ST", "2ND", "3RD", "4TH", "5TH", "1/2", "ADDL")
LIVING = {*FLOORS, "FBSMT", "RSBLW"}
ADU_TYPES = {"120", "21"}
CATEGORIES = {"A1": "single_family", "A4": "condo", "A2": "mobile_home", "B2": "two_to_four_units",
    "B3": "two_to_four_units", "B4": "two_to_four_units", "E1": "rural_home", "E2": "rural_home",
    "O1": "builder_inventory", "A3": "other_residential", "A5": "other_residential", "A9": "other_residential"}
DERIVED = {"land_value", "improvement_value", "abs_subdv_desc", "living_area", "adu_area", "hvac_area",
           "year_built", "floors", "dwelling_count", "has_adu"}
SPLITS = {"land_hstd_val", "land_non_hstd_val", "imprv_hstd_val", "imprv_non_hstd_val"}
COMPACT_FIELDS = (RANGES["PROP.TXT"].keys() - SPLITS) | DERIVED
SAFE_NOTE = re.compile(r"[A-Za-z0-9 ,.()/+%–-]{1,200}")
ERROR_TEXT = re.compile(r"TCAD download/parse failed \(\w+(: [A-Za-z0-9 ,.()/+%–-]{1,200})?\)")
INPUT_COUNTS = {"records_read", "real_mobile", "skipped_by_state", "totals_num_real_mobile", "repeated_rows",
                "mobile_home_rows"}


def read_fields(line, member):
    # Unselected bytes only pass through the line buffer. Never decode the entire line.
    return {field: line[start-1:end].decode("latin-1").strip() for field, (start, end) in RANGES[member].items()}


def rows(archive, info, member, check_time):
    with archive.open(info) as source:
        for index, raw in enumerate(source):
            if index % 1000 == 0:
                check_time()
            line = raw.removesuffix(b"\n").removesuffix(b"\r")
            if len(line) != LENGTHS[member]:
                raise ValueError("invalid TCAD fixed-width record length in " + member)
            yield read_fields(line, member)


def integer(value, blank=None):
    if value is None or value == "":
        return blank
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).isascii() or not str(value).isdigit():
        raise ValueError("invalid TCAD nonnegative integer")
    return int(value)


def identifier(value):
    result = integer(value)
    if result is None:
        raise ValueError("missing TCAD identifier")
    return str(result)


def numeric(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("invalid TCAD area")
    try:
        number = float(value)
    except ValueError:
        raise ValueError("invalid TCAD area") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError("invalid TCAD area")
    return number


def year(row):
    if integer(row["prop_val_yr"]) != 2026:
        raise ValueError("TCAD property value year must be 2026")


def subdivision(value):
    if not value:
        return None
    value = " ".join(value.split()).title()
    first = re.search(r"\w+", value)
    return re.sub(r"\b\w+\b", lambda m: m.group().lower() if m.start() > first.start()
                  and m.group().lower() in {"at", "of", "the", "and", "on"} else m.group(), value)


def deed(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m-%d-%Y").date().isoformat()
    except (ValueError, TypeError):
        raise ValueError("invalid TCAD deed date") from None


def check_counts(summary, kept, live):
    total, count = summary["totals_num_real_mobile"], summary["real_mobile"]
    if total <= 0 or abs(count - total) > total * .02:
        raise ValueError(f"TCAD real/mobile count {count} outside 2% of TOTALS {total}")
    if live and not 330000 <= kept <= 430000:
        raise ValueError("TCAD kept count outside 330,000–430,000")


def quality_counts(properties):
    cats = Counter()
    covered = eligible = hvac_both = hvac_agree = living = partial = 0
    for p in properties:
        cats[p["category"]] += 1
        has_living = p["living_area"] is not None and p["living_area"] > 0
        living += has_living
        partial += p["partial_owner"]
        if p["category"] in {"single_family", "condo"}:
            eligible += 1
            covered += has_living
        if has_living and p["hvac_area"] is not None:
            hvac_both += 1
            hvac_agree += abs(p["living_area"] - p["hvac_area"]) <= p["living_area"] * .02 + 1e-8
    return {"kept": len(properties), "kept_by_category": dict(sorted(cats.items())),
        "with_living_area": living, "without_living_area": len(properties)-living,
        "single_family_condo": eligible, "single_family_condo_with_living_area": covered,
        "living_area_coverage": covered/eligible if eligible else None,
        "hvac_comparable": hvac_both, "hvac_agree": hvac_agree,
        "hvac_agreement": hvac_agree/hvac_both if hvac_both else None, "partial_owner_records": partial}


def quality_checks(counts):
    if counts["single_family_condo_with_living_area"] * 100 < counts["single_family_condo"] * 97:
        raise ValueError("TCAD single-family/condo living-area coverage below 97%")
    if counts["hvac_agree"] * 100 < counts["hvac_comparable"] * 97:
        raise ValueError("TCAD living/HVAC agreement below 97%")


def parse_export(path, check_time=lambda: None):
    with ZipFile(path, allowZip64=True) as archive:
        members = {}
        for member in LENGTHS:
            matches = [i for i in archive.infolist() if Path(i.filename).name.upper() == member]
            if len(matches) != 1:
                raise ValueError("missing or duplicate TCAD required ZIP member")
            members[member] = matches[0]
        totals = []
        for r in rows(archive, members["TOTALS.TXT"], "TOTALS.TXT", check_time):
            if r["entity_cd"] == "03":
                if integer(r["sup_num"]) != 0:
                    raise ValueError("TCAD TOTALS supplement must be zero")
                totals.append(integer(r["num_real_mobile"]))
        if len(totals) != 1 or totals[0] is None or totals[0] <= 0:
            raise ValueError("missing or duplicate TCAD county TOTALS")
        subdivisions = {}
        for r in rows(archive, members["ABS_SUBD.TXT"], "ABS_SUBD.TXT", check_time):
            code = r["abs_subdv_cd"]
            name = subdivision(r["abs_subdv_desc"])
            if not code or (code in subdivisions and subdivisions[code] != name):
                raise ValueError("invalid or conflicting TCAD subdivision code")
            subdivisions[code] = name
        # [kind, living, HVAC-or-None, largest-floor-area, year, floor bitmask]
        improvements = {}
        for r in rows(archive, members["IMP_INFO.TXT"], "IMP_INFO.TXT", check_time):
            year(r)
            key = (identifier(r["prop_id"]), identifier(r["imprv_id"]))
            # One real 2026 row has a blank type code. It is not ADU, garage apartment or detail
            # only, so it stays a dwelling improvement (the spec's rule), not a failed run.
            if key in improvements:
                raise ValueError("duplicate TCAD improvement")
            improvements[key] = [r["imprv_type_cd"], 0., None, -1., None, 0]
        for r in rows(archive, members["IMP_DET.TXT"], "IMP_DET.TXT", check_time):
            year(r)
            key = (identifier(r["prop_id"]), identifier(r["imprv_id"]))
            if key not in improvements:
                raise ValueError("TCAD segment has no improvement")
            code, state = r["imprv_det_type_cd"], improvements[key]
            if state[0] == "00" or code not in LIVING | {"095"}:
                continue
            area = numeric(r["imprv_det_area"])
            if area is None:
                continue
            if code == "095":
                state[2] = (state[2] or 0) + area
            else:
                state[1] += area
                if code in FLOORS and area > 0:
                    state[5] |= 1 << FLOORS.index(code)
                    if area > state[3]:
                        state[3], state[4] = area, integer(r["yr_built"]) or None
        # Collapse to one compact aggregate per property, retaining only the leading dwelling.
        facts = {}
        for index, ((pid, iid), state) in enumerate(improvements.items()):
            if index % 1000 == 0:
                check_time()
            fact = facts.setdefault(pid, [0., 0., None, None, 0, 0, False, -1.])
            kind, living, hvac, largest, built, floors = state
            if kind in ADU_TYPES:
                fact[1] += living
                fact[6] = True
            elif kind != "00":
                fact[0] += living
                if hvac is not None:
                    fact[2] = (fact[2] or 0) + hvac
                if living > 0:
                    fact[5] += 1
                    if living > fact[7]:
                        fact[3], fact[4], fact[7] = built, floors.bit_count(), living
        del improvements
        output, seen = [], {}
        summary = {"records_read": 0, "real_mobile": 0, "skipped_by_state": {}, "totals_num_real_mobile": totals[0],
                   "repeated_rows": 0, "mobile_home_rows": 0}
        skipped, types = Counter(), Counter()
        for r in rows(archive, members["PROP.TXT"], "PROP.TXT", check_time):
            summary["records_read"] += 1
            year(r)
            if integer(r["sup_num"]) != 0:
                raise ValueError("TCAD PROP supplement must be zero")
            pid = identifier(r["prop_id"])
            signature = (r["partial_owner"], r["prop_type_cd"], r["imprv_state_cd"] or r["land_state_cd"], r["udi_group"])
            if pid in seen:
                # The real PROP.TXT repeats a property once per undivided-interest row (partial_owner T,
                # the same udi_group; probe 2026-10-26: adjacent rows, same type and state, same values
                # or within 0.03%). Keep the first row and count the rest; any other repeat still fails.
                if signature[0] != "T" or seen[pid] != signature:
                    raise ValueError("duplicate TCAD property ID")
                summary["repeated_rows"] += 1
                continue
            seen[pid] = signature
            types[r["prop_type_cd"] or "blank"] += 1
            # TOTALS "real/mobile" counts real (R) plus mobile homes, coded MH in the real file. Only R
            # and M are kept (owner decision 2026-10-26: MH stays skipped), but MH counts for the check.
            kept_type = r["prop_type_cd"] in {"R", "M"}
            summary["real_mobile"] += kept_type or r["prop_type_cd"] == "MH"
            summary["mobile_home_rows"] += r["prop_type_cd"] == "MH"
            state = r["imprv_state_cd"] or r["land_state_cd"]
            if not kept_type or state not in CATEGORIES:
                skipped[state or "(blank)"] += 1
                continue
            # Consume each split locally; only the summed values can leave the parser.
            land = [integer(r.pop(k)) for k in ("land_hstd_val", "land_non_hstd_val")]
            improvement = [integer(r.pop(k)) for k in ("imprv_hstd_val", "imprv_non_hstd_val")]
            acres = integer(r["land_acres"])
            living, adu, hvac, built, floors, dwellings, has_adu, _ = facts.pop(pid, [0.,0.,None,None,0,0,False,-1.])
            r.update(land_value=sum(land) if None not in land else None,
                improvement_value=sum(improvement) if None not in improvement else None,
                land_acres=round(acres/10000, 4) if acres is not None else None,
                abs_subdv_desc=subdivisions.get(r["abs_subdv_cd"]), living_area=round(living) if living > 0 else None,
                adu_area=round(adu, 6) if adu > 0 else None, hvac_area=round(hvac, 6) if hvac is not None else None,
                year_built=built, floors=floors, dwelling_count=dwellings, has_adu=has_adu)
            r["prop_id"] = pid
            output.append(r)
        summary["skipped_by_state"] = dict(sorted(skipped.items()))
    try:
        check_counts(summary, len(output), live=False)
    except ValueError as exc:
        # Aggregates only (counts and type codes), to say why the count check failed.
        raise ValueError(f"{exc} - rows by type " + ", ".join(f"{k} {v}" for k, v in types.most_common(8))) from None
    return {"properties": output, "summary": summary}


def normalize_property(row):
    if not isinstance(row, dict) or set(row) != COMPACT_FIELDS:
        raise ValueError("invalid compact TCAD property fields")
    r = row.copy()
    year(r)
    if integer(r["sup_num"]) != 0:
        raise ValueError("TCAD PROP supplement must be zero")
    state = r["imprv_state_cd"] or r["land_state_cd"]
    if r["prop_type_cd"] not in {"R", "M"} or state not in CATEGORIES:
        raise ValueError("unexpected nonresidential compact TCAD property")
    for key in RANGES["PROP.TXT"].keys() - SPLITS - {"land_acres"}:
        if not isinstance(r[key], str):
            raise ValueError("invalid compact TCAD native cell")
        r[key] = r[key].strip()
    if r["partial_owner"] not in {"T", "F"} or not isinstance(r["has_adu"], bool):
        raise ValueError("invalid TCAD boolean")
    p = {"county": "Travis", "prop_id": identifier(r["prop_id"]), "geo_id": r["geo_id"] or None,
        "category": CATEGORIES[state], "state_cd": state, "prop_type": r["prop_type_cd"],
        "hood_cd": r["hood_cd"] or None, "subdivision_code": r["abs_subdv_cd"] or None,
        "subdivision": subdivision(r["abs_subdv_desc"]), "market_value": integer(r["market_value"]),
        "land_value": integer(r["land_value"]), "improvement_value": integer(r["improvement_value"]),
        "value_year": 2026, "value_as_of": AS_OF.isoformat(), "certified": CERTIFIED,
        "land_acres": numeric(r["land_acres"]), "living_area": integer(r["living_area"]),
        "adu_area": numeric(r["adu_area"]), "hvac_area": numeric(r["hvac_area"]),
        "year_built": integer(r["year_built"]) or None, "floors": integer(r["floors"]),
        "dwelling_count": integer(r["dwelling_count"]), "has_adu": r["has_adu"],
        "deed_date": deed(r["deed_dt"]), "partial_owner": r["partial_owner"] == "T", "udi_group": integer(r["udi_group"]) or None}
    p["land_acres"] = round(p["land_acres"], 4) if p["land_acres"] is not None else None
    for key, native in {"situs_number": "situs_num", "situs_prefix": "situs_street_prefx", "situs_street": "situs_street",
            "situs_suffix": "situs_street_suffix", "situs_unit": "situs_unit", "situs_city": "situs_city", "situs_zip": "situs_zip"}.items():
        p[key] = r[native] or None
    p["situs"] = " ".join(p[k] for k in ("situs_number", "situs_prefix", "situs_street", "situs_suffix", "situs_unit", "situs_city", "situs_zip") if p[k]) or None
    return p


class TCAD(SourceAdapter):
    id = "tcad"
    entity = "area_feature"
    cadence = "annual"

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        self.started = time.monotonic()
        return [Request("tcad_2026", {"url": URL})]

    def check_time(self):
        elapsed = time.monotonic() - self.started
        if elapsed >= 45 * 60:
            raise ValueError("TCAD 45-minute runtime limit exceeded")
        return elapsed

    def fetch(self, req, ctx):
        if req.key != "tcad_2026" or req.params != {"url": URL}:
            raise ValueError("unexpected TCAD request")
        try:
            paths().raw.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="tcad-", dir=paths().raw) as folder:
                archive = Path(folder) / "download.zip"
                request = urllib.request.Request(URL, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
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
                        raise ValueError("incomplete TCAD download")
                body = parse_export(archive, self.check_time)
            return RawPayload(req, body)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception as exc:
            # Suppress automatic re-download and never echo source cells. Only this adapter's own
            # static messages (always naming TCAD, no quotes or colons) are passed on, so a failed
            # first check says which check failed without a probe. Any other text is dropped.
            note = str(exc) if isinstance(exc, ValueError) and "TCAD" in str(exc) and SAFE_NOTE.fullmatch(str(exc)) else ""
            detail = f"{type(exc).__name__}: {note}" if note else type(exc).__name__
            return RawPayload(req, {"error": f"TCAD download/parse failed ({detail})"}, status=502)

    def follow_up(self, raw, ctx):
        if raw.status != 200:
            error = raw.body.get("error") if isinstance(raw.body, dict) else None
            if isinstance(error, str) and ERROR_TEXT.fullmatch(error):
                raise ValueError(f"TCAD HTTP {raw.status}; {error}")
            raise ValueError(f"TCAD HTTP {raw.status}; response withheld")
        return []

    def normalize(self, raw):
        if raw.status != 200 or raw.request.key != "tcad_2026":
            raise ValueError("failed or unexpected TCAD response")
        if not isinstance(raw.body, dict) or set(raw.body) != {"properties", "summary"} or not isinstance(raw.body["properties"], list):
            raise ValueError("invalid compact TCAD response")
        summary = raw.body["summary"]
        if not isinstance(summary, dict) or set(summary) != INPUT_COUNTS or not isinstance(summary["skipped_by_state"], dict):
            raise ValueError("invalid compact TCAD summary")
        for p in raw.body["properties"]:
            self.check_time()
            props = normalize_property(p)
            yield AreaFeature(dataset="property", feature_id="48453:"+props["prop_id"], geometry=EMPTY,
                              properties=props, source_as_of=AS_OF)
        counts = {key: integer(value) for key, value in summary.items() if key != "skipped_by_state"}
        counts["skipped_by_state"] = {key: integer(value) for key, value in summary["skipped_by_state"].items()
                                     if isinstance(key, str) and re.fullmatch(r"[A-Z0-9]{1,10}|\(blank\)", key)}
        if len(counts["skipped_by_state"]) != len(summary["skipped_by_state"]) or any(v is None for v in counts.values()):
            raise ValueError("invalid compact TCAD counts")
        yield AreaFeature(dataset="tcad_input_summary", feature_id="2026", geometry=EMPTY, properties=counts)

    def finalize(self, records):
        properties = [r for r in records if r.dataset == "property"]
        summaries = [r for r in records if r.dataset == "tcad_input_summary"]
        if len(summaries) != 1 or len(records) != len(properties)+1 or not properties or len({r.feature_id for r in properties}) != len(properties):
            raise ValueError("missing or duplicate TCAD property/summary input")
        counts = summaries[0].properties
        if (counts["records_read"] != len(properties)+sum(counts["skipped_by_state"].values())+counts["repeated_rows"]
                or not len(properties) <= counts["real_mobile"] <= counts["records_read"]):
            raise ValueError("TCAD read/kept/skipped counts do not reconcile")
        check_counts(counts, len(properties), self.live)
        quality = quality_counts([r.properties for r in properties])
        quality_checks(quality)
        parcel_path = paths().canonical / "area_feature/parcels.ndjson.gz"
        matched = None
        if self.live and parcel_path.is_file():
            ids = {r.properties["prop_id"] for r in properties}
            found = set()
            with gzip.open(parcel_path, "rt", encoding="utf-8") as source:
                for index, line in enumerate(source):
                    if index % 1000 == 0:
                        self.check_time()
                    rec = json.loads(line)
                    if rec["dataset"] == "parcel" and rec["properties"]["county"] == "Travis":
                        pid = rec["properties"]["prop_id"]
                        if isinstance(pid, str) and pid.isascii() and pid.isdigit() and str(int(pid)) in ids:
                            found.add(str(int(pid)))
            matched = len(found)
        self.check_time()
        summary = {**counts, **quality, "parcel_matches": matched,
            "parcel_match_share": matched/len(properties) if matched is not None else None,
            "runtime_seconds": round(self.check_time(), 3),
            "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1)}
        print("tcad: run note: " + json.dumps(summary, sort_keys=True), file=sys.stderr)
        return [*properties, AreaFeature(dataset="run_summary", feature_id="2026", geometry=EMPTY,
                                         properties=summary, source_as_of=AS_OF)]

    def source_as_of(self, raws):
        return AS_OF


ADAPTER = TCAD
