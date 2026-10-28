"""FHFA purchase-only Austin HPI, native tab-separated quoted metro names."""
from __future__ import annotations
import calendar
import csv
from datetime import date
from io import StringIO
import math
import urllib.error
import urllib.request

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature

URL = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_po_metro.txt"
HEADER = ["cbsa", "metro_name", "yr", "qtr", "index_nsa", "index_sa"]
EMPTY = {"type":"GeometryCollection", "geometries":[]}
FIXTURE_DATE = date(2026, 10, 27)


def quarter_end(year, quarter):
    month = quarter*3
    return date(year, month, calendar.monthrange(year, month)[1])


def parse(body, today):
    if not isinstance(body, str):
        raise ValueError("FHFA expected tab-separated text")
    if not body.splitlines() or body.splitlines()[0] != "\t".join(HEADER):
        raise ValueError("FHFA exact header required")
    reader = csv.reader(StringIO(body, newline=""), delimiter="\t", strict=True)
    if next(reader, None) != HEADER:
        raise ValueError("FHFA exact header required")
    rows = {}
    for cells in reader:
        if not cells:
            continue
        if len(cells) != 6:
            raise ValueError("FHFA invalid column count")
        if cells[0] != "12420":
            continue
        try:
            year, quarter = int(cells[2]), int(cells[3])
            nsa, sa = float(cells[4]), float(cells[5])
        except ValueError:
            raise ValueError("FHFA invalid Austin numeric cells") from None
        if not 1900 <= year <= 2200 or quarter not in (1,2,3,4) or not cells[1].strip() or not all(math.isfinite(v) and v > 0 for v in (nsa,sa)):
            raise ValueError("FHFA invalid Austin quarter or indexes")
        serial = year*4+quarter-1
        if serial in rows:
            raise ValueError("FHFA duplicate Austin quarter")
        rows[serial] = {"cbsa":"12420", "metro":cells[1], "year":year, "quarter":quarter, "index_nsa":nsa, "index_sa":sa}
    quarters = sorted(rows)
    if len(quarters) < 140:
        raise ValueError("FHFA needs at least 140 Austin rows")
    if quarters != list(range(quarters[0],quarters[-1]+1)):
        raise ValueError("FHFA Austin quarters have gaps")
    if not {2025*4+3,2026*4} <= set(quarters):
        raise ValueError("FHFA missing 2025Q4 or 2026Q1 base quarter")
    latest = rows[quarters[-1]]
    end = quarter_end(latest["year"], latest["quarter"])
    month = today.year*12+today.month-1-9
    cutoff = date(month//12, month%12+1, min(today.day, calendar.monthrange(month//12,month%12+1)[1]))
    if end < cutoff or end > today:
        raise ValueError("FHFA latest quarter must end within the last nine months")
    return [rows[q] for q in quarters], end


class FHFAHPI(SourceAdapter):
    id = "fhfa_hpi"
    entity = "area_feature"
    cadence = "monthly"
    retain_raw = False
    recordable = False

    def plan(self, ctx):
        # Reproducible fixtures also work in homes' fixed-date fixture-only runner.
        self.today = ctx.now.date() if ctx.mode == "live" else FIXTURE_DATE
        return [Request("austin_hpi", {"url":URL})]

    def fetch(self, req, ctx):
        if req != Request("austin_hpi", {"url":URL}):
            raise ValueError("FHFA unexpected request")
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent":self.user_agent}), timeout=90) as response:
                return RawPayload(req, response.read().decode("utf-8") if response.status == 200 else None, status=response.status)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception:
            return RawPayload(req, None, status=502)

    def follow_up(self, raw, ctx):
        if raw.status != 200:
            raise ValueError("FHFA failed response withheld")
        return []

    def normalize(self, raw):
        if raw.status != 200 or raw.request != Request("austin_hpi", {"url":URL}):
            raise ValueError("FHFA failed or unexpected response")
        rows, self.as_of = parse(raw.body, self.today)
        for p in rows:
            yield AreaFeature(dataset="hpi",feature_id=f"12420:{p['year']}Q{p['quarter']}", geometry=EMPTY,
                              properties=p, source_as_of=self.as_of)

    def source_as_of(self, raws):
        return self.as_of


ADAPTER = FHFAHPI
