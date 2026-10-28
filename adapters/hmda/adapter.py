"""HMDA purchase-loan validation: decode nine allowed cells, retain tract aggregates only.

The wide CSV passes through a byte scanner. Unselected cell contents are never copied
into a field buffer, decoded, logged or returned. No raw response or loan row is stored.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from io import BytesIO
import json
import re
import urllib.error
import urllib.request

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.inputs import assert_no_demographics
from mm.schemas import AreaFeature
from mm.values import HMDA_INPUTS, percentile

URL = "https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?counties=48453,48491,48209&years=2025&actions_taken=1&loan_purposes=1"
COUNTIES = {"48453": "Travis", "48491": "Williamson", "48209": "Hays"}
EMPTY = {"type": "GeometryCollection", "geometries": []}
AS_OF = date(2025, 12, 31)
REQUEST = Request("purchase_2025", {"url": URL})
DWELLING = "Single Family (1-4 Units):Site-Built"


def decode_cell(name, value):
    """Only this allowlisted boundary converts a loan cell to text."""
    if name not in HMDA_INPUTS:
        raise ValueError("HMDA unapproved column")
    try:
        return value.decode("ascii")
    except UnicodeError:
        raise ValueError("HMDA invalid allowed cell encoding") from None


def selected_rows(stream):
    """RFC-4180 comma/quote scanning, including CRLF and quoted embedded newlines.

    Header names are public schema, not cell contents. After the header, buffer only
    approved columns. Even non-UTF8 canaries in all other cells pass without decoding.
    """
    header = None
    selected = {}
    column = 0
    cells = {}
    buffer = bytearray()
    state = "start"
    skip_lf = False

    def finish_cell():
        if header is None or column in selected:
            cells[column] = bytes(buffer)
        buffer.clear()

    def finish_row():
        nonlocal header, selected
        if header is None:
            try:
                header = [cells[i].decode("utf-8-sig") for i in range(column + 1)]
            except UnicodeError:
                raise ValueError("HMDA invalid header encoding") from None
            if len(set(header)) != len(header) or not set(HMDA_INPUTS) <= set(header):
                raise ValueError("HMDA required header names missing or duplicated")
            selected = {i: name for i, name in enumerate(header) if name in HMDA_INPUTS}
            return None
        if column == 0 and not cells.get(0) and state == "start":
            return None  # Empty lines are not loan rows.
        if column + 1 != len(header):
            raise ValueError("HMDA invalid column count")
        return {name: decode_cell(name, cells[i]) for i, name in selected.items()}

    for chunk in iter(lambda: stream.read(65536), b""):
        if not isinstance(chunk, bytes):
            raise ValueError("HMDA binary CSV stream required")
        for byte in chunk:
            if skip_lf:
                skip_lf = False
                if byte == 10:
                    continue
            capture = header is None or column in selected
            if state == "quoted":
                if byte == 34:
                    state = "after_quote"
                elif capture:
                    buffer.append(byte)
            elif state == "after_quote" and byte == 34:
                if capture:
                    buffer.append(byte)
                state = "quoted"
            elif byte == 44 or byte in (10, 13):
                finish_cell()
                if byte == 44:
                    column += 1
                else:
                    row = finish_row()
                    if row is not None:
                        yield row
                    column = 0
                    cells = {}
                    skip_lf = byte == 13
                state = "start"
            elif state == "after_quote" or byte == 34 and state != "start":
                raise ValueError("HMDA invalid CSV quoting")
            elif byte == 34:
                state = "quoted"
            else:
                if capture:
                    buffer.append(byte)
                state = "plain"
            if len(buffer) > 4096 or column > 1024:
                raise ValueError("HMDA CSV cell or header exceeds limit")
    if state == "quoted":
        raise ValueError("HMDA truncated CSV quoting")
    if column or state != "start":
        finish_cell()
        row = finish_row()
        if row is not None:
            yield row
    if header is None:
        raise ValueError("HMDA missing header")


def check_counts(summary, live):
    if set(summary["counties"]) != set(COUNTIES.values()):
        raise ValueError("HMDA every county required")
    if live and abs(summary["rows_read"] - 30323) * 100 > 30323 * 5:
        raise ValueError("HMDA row count differs from 30,323 by more than 5 percent")
    if live and summary["tracts_30_loans"] < 250:
        raise ValueError("HMDA requires at least 250 tracts with 30 loans")


def parse(stream, *, live=False):
    assert_no_demographics("hmda_validation", HMDA_INPUTS)
    groups = defaultdict(list)
    counties = Counter()
    skipped = Counter()
    total = 0
    for row in selected_rows(stream):
        total += 1
        if row["activity_year"] != "2025":
            raise ValueError("HMDA unexpected activity year")
        code = row["county_code"]
        if code not in COUNTIES:
            raise ValueError("HMDA unexpected county")
        counties[COUNTIES[code]] += 1
        reason = next((field for field, expected in (
            ("action_taken", "1"), ("loan_purpose", "1"), ("lien_status", "1"),
            ("derived_dwelling_category", DWELLING), ("total_units", "1")) if row[field] != expected), None)
        if reason:
            skipped[reason] += 1
            continue
        value = row["property_value"]
        if not re.fullmatch(r"[0-9]+", value):
            skipped[{"Exempt": "value_exempt", "NA": "value_na", "": "value_blank"}.get(value, "value_non_digits")] += 1
            continue
        tract = row["census_tract"]
        if not re.fullmatch(code + r"[0-9]{6}", tract):
            skipped["tract_invalid"] += 1
            continue
        groups[tract].append(int(value))
    rows = []
    for tract, observations in sorted(groups.items()):
        ordered = sorted(observations)
        rows.append({"county": COUNTIES[tract[:5]], "tract": tract, "year": 2025, "loans": len(ordered),
                     "median_value": percentile(ordered, 50), "p25_value": percentile(ordered, 25),
                     "p75_value": percentile(ordered, 75)})
    summary = {"rows_read": total, "kept": sum(len(v) for v in groups.values()), "skipped_by_reason": dict(sorted(skipped.items())),
               "counties": dict(sorted(counties.items())), "tracts": len(rows), "tracts_30_loans": sum(r["loans"] >= 30 for r in rows)}
    check_counts(summary, live)
    return {"tracts": rows, "summary": summary}


class HMDA(SourceAdapter):
    id = "hmda"
    entity = "area_feature"
    cadence = "annual"
    retain_raw = False
    recordable = False

    def plan(self, ctx):
        self.live = ctx.mode == "live"
        return [REQUEST]

    def fetch(self, req, ctx):
        if req != REQUEST:
            raise ValueError("HMDA unexpected request")
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": self.user_agent}), timeout=120) as response:
                if response.status != 200:
                    return RawPayload(req, None, status=response.status)
                # Do not return the wide CSV to the runner, even in memory.
                return RawPayload(req, parse(response, live=True))
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception:
            return RawPayload(req, None, status=502)

    def follow_up(self, raw, ctx):
        if raw.status != 200:
            raise ValueError("HMDA failed response withheld")
        return []

    def normalize(self, raw):
        if raw.status != 200 or raw.request != REQUEST:
            raise ValueError("HMDA failed or unexpected response")
        # Fixtures are native CSV text. Live fetch returns aggregates only.
        data = parse(BytesIO(raw.body.encode("utf-8"))) if isinstance(raw.body, str) else raw.body
        check_counts(data["summary"], self.live)
        for properties in data["tracts"]:
            yield AreaFeature(dataset="hmda_tract", feature_id=properties["tract"], geometry=EMPTY,
                              properties=properties, source_as_of=AS_OF)
        yield AreaFeature(dataset="run_summary", feature_id="2025", geometry=EMPTY, properties=data["summary"], source_as_of=AS_OF)

    def finalize(self, records):
        summary = next(r.properties for r in records if r.dataset == "run_summary")
        print("hmda: run note: " + json.dumps(summary, sort_keys=True))
        return records

    def source_as_of(self, raws):
        return AS_OF


ADAPTER = HMDA
